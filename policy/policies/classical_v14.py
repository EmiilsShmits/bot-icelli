"""v1.4 = v1.3 + a grasp check right after the lift + a retry that changes the grasp.

Why (`eval/analysis/FINDINGS.md`, grasp-by-grasp trace of Sat 14 Nov): about half of the baseline's grasps close on
nothing (34 of 69 in the nominal sim, 38 of 54 with AALTO_DR=train), and Aalto's executor plays every planned
pick-and-place to the end: an empty hand still travels to the bin and back (~10 s each; with randomisation episodes
then run out of time). A retry then repeats the grasp that just failed, and second tries hold less often than first
tries (37 % vs 58 %). Slips during the carry are rare (2 of 69), so squeezing harder would not help much.

  1. Grasp check (ported from Emīls's `policy/decision_oracle/upgrades.py`, right on 45 of 45 aborts there): the
     planned trajectory is cut at the end of its `lift` phase. There a held object keeps the closed fingers short of
     their command, while an empty hand reaches it. If the largest |hand_q - command| of that hand is below EMPTY_RAD,
     the hand is empty: the carry is skipped, the arm goes straight to the pose the plan would have ended in (home,
     hand opening on the way) and the policy looks again. Otherwise the rest of the plan runs unchanged. On 215
     logged grasps (median over the lift) empty hands read <= 0.0036 rad and held objects >= 0.0081 rad, hence
     EMPTY_RAD = 0.006 (Emīls's 0.012 would have called 3 of 115 held objects empty). If the move home would come
     closer to the counter than the planner allows, or would be clipped, the plan runs on as in v1.3.
  2. The retry changes the grasp. Aalto's planner tries the arm on the bin's side first, each arm with the finger
     directions of `grasp.finger_hints` (forward, forward-inward, inward) in turn, and takes the first plan that
     passes. An (arm, finger direction) pair that closed on nothing is now skipped for that object (within
     RETRY_RADIUS of where it was tried: a failed grasp pushes the object 1-3 cm) as long as another pair has a valid
     plan; only if none has does it retry the same grasp, as v1.3 would. v1.1's limit of 3 tries per object stays.

  3. Bug fix in v1.2's head-camera re-fit, found in the venue-look sim (Sat 14 Nov, sim c): the fit was right
     (tilt 9.8°, the camera itself moved (-0.3, +1.9, -0.3) cm) but v1.2 rejected it as "shift (-8.3, +2.8) cm"
     > 6 cm, so v1.2/v1.3 ran on a camera ~10° off there: objects mislocated, the bin walls taken for objects. That
     "shift" is the bin fit's step only: the plane fit first tilts the pose about the pelvis origin, which moves the
     camera ~8 cm for 10°, and the bin fit moves it back. v1.4 judges where the camera ends up instead
     (camera_move_ok). Same limits (15° tilt, 6 cm, 6° yaw). In Aalto's nominal sim and with AALTO_DR=train every
     fit was accepted before (25 of 25 logged), so this changes nothing there; it matters in the venue look and, if
     the real head camera is tilted ~10° as Aalto's footage suggests, on the real robot.

Everything else is v1.3. Env: V14_GRASP_CHECK=0 turns 1 and 2 off; V14_EMPTY_RAD (default 0.006).
The threshold is a sim value: on the real Dex3 an empty hand that stops short of its command reads as "held", which
only falls back to v1.3's behaviour (carry on).
"""
from __future__ import annotations

import logging
import os

import numpy as np

from aaltonomous.baselines.classical.planner import Plan

from headpose import CAM, fit_head_pose
from policies.classical_v11 import PolicyV11
from policies.classical_v12 import MAX_FIT_TRIES
from policies.classical_v13 import ClassicalV13, PlannerV13, PolicyV13

log = logging.getLogger("bot-icelli.v1.4")

CHECK_ON = os.environ.get("V14_GRASP_CHECK", "1") != "0"
EMPTY_RAD = float(os.environ.get("V14_EMPTY_RAD", 0.006))
RETRY_RADIUS = 0.06       # = v1.1's ATTEMPT_RADIUS


def camera_move_ok(fit, T0, max_tilt_deg=15.0, max_move_m=0.06, max_yaw_deg=6.0):
    """headpose.plausible() with the shift measured where the camera ends up (module doc, change 3)."""
    if not fit.ok or fit.tilt_deg > max_tilt_deg or abs(fit.dyaw_deg) > max_yaw_deg:
        return False
    move = np.asarray(fit.T, float)[:3, 3] - np.asarray(T0, float)[:3, 3]
    return float(np.linalg.norm(move)) <= max_move_m


class PlannerV14(PlannerV13):
    failed_grasps = None      # [{"xy", "side", "hint"}] of grasps that closed on nothing this episode (PolicyV14)
    _strict = False           # True while plan() looks for an (arm, finger direction) pair not tried yet

    def tried_pairs(self, det):
        """(arm, finger-direction index) pairs that already closed on nothing for the object at det."""
        xy = np.asarray(det.top[:2], float)
        return {(f["side"], f["hint"]) for f in (self.failed_grasps or [])
                if np.linalg.norm(xy - f["xy"]) < RETRY_RADIUS}

    def plan(self, det, arm_q, hand_q, bin_name=None, obstacles=(), relocate=True):
        tried = self.tried_pairs(det) if CHECK_ON else set()
        if tried:
            self._strict = True
            try:
                p = super().plan(det, arm_q, hand_q, bin_name, obstacles, relocate)
            finally:
                self._strict = False
            if p.ok:
                p.reason = f"{p.reason + '; ' if p.reason else ''}new grasp: {sorted(tried, key=str)} closed on nothing"
                return p
        return super().plan(det, arm_q, hand_q, bin_name, obstacles, relocate)

    def _plan_side_hints(self, det, side, bin_name, arm_q, hand_q, **kw):
        """Aalto's _plan_side_hints, plus: remembers which finger direction the plan uses (plan.hint) and, in the
        strict pass, skips the directions that already closed on nothing for this object."""
        hints = self.cfg["grasp"].get("finger_hints") or [self.cfg["grasp"].get("finger_hint", [1.0, 0.0, 0.0])]
        skip = self.tried_pairs(det) if self._strict else set()
        saved, first = self.kin.hint, None
        try:
            for i, h in enumerate(hints):
                if (side, i) in skip:
                    continue
                h = np.asarray(h, float) * ([1.0, -1.0, 1.0] if side == "right" else 1.0)
                self.kin.hint = h / np.linalg.norm(h)
                p = self._plan_side(det, side, bin_name, arm_q, hand_q, **kw)
                if p.ok:
                    p.hint = i
                    return p
                first = first or p
            return first or Plan(False, side=side, color=det.color,
                                 reason=f"{side}: every finger direction already closed on nothing here")
        finally:
            self.kin.hint = saved


class PolicyV14(PolicyV13):
    def reset(self, info=None):
        super().reset(info)
        self.planner.failed_grasps = []
        self._gc = None                     # grasp check pending for the plan being executed

    def act(self, obs):
        if self._gc is not None and self.state == "executing" and (self.queue_a is None or not len(self.queue_a)):
            return self._grasp_check(obs)  # the queue was cut at the end of `lift`
        return super().act(obs)

    def _look(self, obs):
        """v1.2's head-camera re-fit with the corrected acceptance (camera_move_ok), then v1.1's look."""
        if self.head_fit is None and self._fit_tries < MAX_FIT_TRIES and obs.get("head_depth") is not None:
            self._fit_tries += 1
            depth = np.asarray(obs["head_depth"])
            if depth.ndim == 2 and depth.any():
                T0 = self._cal0._T(CAM)               # the pose fit_head_pose starts from
                fit = fit_head_pose(depth, self._cal0, self.scene)
                move = np.asarray(fit.T, float)[:3, 3] - np.asarray(T0, float)[:3, 3]
                note = f"{fit.summary()}, camera moved ({', '.join(f'{100 * v:+.1f}' for v in move)}) cm"
                if camera_move_ok(fit, T0):
                    self.cal.cams[CAM].T_pelvis_optical = fit.T
                    self.head_fit = fit
                    self.log(f"[v1.4] head pose fitted: {note}")
                else:
                    self.log(f"[v1.4] head pose fit not used (try {self._fit_tries}): {note}")
        return PolicyV11._look(self, obs)

    def _start(self, plan, t):
        out = super()._start(plan, t)       # v1.3 counts the drop; Aalto's queues the plan and hands out one chunk
        self._gc = None
        if CHECK_ON:
            cut = next((e for name, s, e in plan.phases if name == "lift"), None)
            done = len(plan.arm) - len(self.queue_a)
            if cut is not None and done < cut < len(plan.arm):
                self._gc = {"plan": plan, "rest_a": plan.arm[cut:], "rest_h": plan.hand[cut:]}
                self.queue_a, self.queue_h = plan.arm[done:cut], plan.hand[done:cut]
        return out

    def _grasp_check(self, obs):
        gc, self._gc = self._gc, None
        plan, t = gc["plan"], float(obs.get("t", 0.0))
        sl = slice(0, 7) if plan.side == "left" else slice(7, 14)
        err = float(np.abs(np.asarray(obs["hand_q"], float)[sl] - self.hand_cmd[sl]).max())
        what = f"{plan.side} arm, finger direction {getattr(plan, 'hint', '?')}, {plan.color} -> {plan.target_bin}"
        if err >= EMPTY_RAD:
            self.log(f"[v1.4 t={t:6.2f}] grasp check: held (finger error {err:.4f} rad; {what})")
            self._enqueue(gc["rest_a"], gc["rest_h"])
            return self._pop()
        a, h = self.planner.go_to(self.arm_cmd, self.hand_cmd, plan.arm[-1], plan.hand[-1])
        if not self._clear(plan.side, a, h):
            self._note(t, f"grasp check: hand empty (finger error {err:.4f} rad; {what}) but the way home is not "
                          f"clear: carrying on")
            self._enqueue(gc["rest_a"], gc["rest_h"])
            return self._pop()
        self.planner.failed_grasps.append({"xy": np.asarray(plan.waypoints["grasp"][:2], float).copy(),
                                           "side": plan.side, "hint": getattr(plan, "hint", None)})
        counts = self.planner.drop_count
        if counts is not None and counts.get(plan.target_bin):
            counts[plan.target_bin] -= 1    # nothing went into the bin: its next drop uses the same spot
        self._note(t, f"grasp check: hand empty (finger error {err:.4f} rad; {what}): back home, look again")
        self._enqueue(a, h)
        return self._pop() if len(a) else self._hold()

    def _clear(self, side, a, h):
        """The way home from the end of the lift: above the counter as the planner requires, and never clipped."""
        need = float(self.cfg["motion"]["counter_clearance"])
        if any(self.planner.clearance(side, a[k], h[k]) < need - 2e-3 for k in range(0, len(a), 3)):
            return False
        return self.planner.dry_run_safety(self.arm_cmd, self.hand_cmd, a, h) == 0


class ClassicalV14(ClassicalV13):
    name = "bot-icelli-v1.4"

    def __init__(self):
        super().__init__()
        self.pol.__class__ = PolicyV14
        self.pol.planner.__class__ = PlannerV14
        self.pol.planner.failed_grasps = []
        self.pol._gc = None
        log.info("v1.4: grasp check %s (empty below %.4f rad), new grasp on retry within %.2f m, head fit judged by "
                 "the camera's own move", "on" if CHECK_ON else "OFF", EMPTY_RAD, RETRY_RADIUS)
