"""v1.6, experimental: triangles close to the body (V16_NEAR = off | relay | push; default off).

Within ~0.23 m of the pelvis a top-down grasp can point the fingers in only a few directions (offline: 3 of 17 for
the left hand at 0.18 m, 7 at 0.26 m), so a triangle's faces (every 120 deg) or a lying prism's ridge (every 180 deg)
rarely line up, and the planner falls back to the stock claw (near the body it held 2 of 30 standing triangles in our
sim logs). Two ways to get the object out to where the hand has room, tried only for a triangle (standing or lying)
within NEAR_X of the pelvis that has no face / ridge option straight to its bin:

  relay  pick it with a face / ridge grasp only (either arm) and put it down at one of Aalto's relay points
         (0.27-0.34 m out, oracle.RELAY_POINTS); the next look sorts it from there. Most of the limit near the body is
         the carry to the side bin, not the grasp: to the centre relay point the left hand reaches 75 deg of finger
         directions instead of 15, and the other hand reaching across adds 105 deg.
  push   a closed hand comes down behind the object (between it and the body), slides it PUSH_END_M past where it
         was, outwards and a little towards the centre line, and goes home; the next look sorts it from there. One push
         per spot (a push that did not move it is not repeated). Planner-checked like a pick: IK along each line,
         counter / bin clearance, safety dry run. Not checked: contact with the robot's own body.

Classes: NearEnumerator, V16Chooser.
"""
from __future__ import annotations

import os

import numpy as np

from aaltonomous.baselines.classical.kinematics import ArmKinematics
from aaltonomous.baselines.classical.planner import Plan, ramp, time_scale
from aaltonomous.sim import oracle as O

from .motions import face_options, parse_face
from .upgrades import MemoryEnumerator
from .upgrades_v15 import V15Chooser

NEAR_X = 0.235            # m, pelvis x: "close to the body" (layout area 0.18-0.34)
PUSH_START_M = 0.065      # grasp point of the closed hand this far behind the object centre at the start of the push
PUSH_END_M = 0.06         # ... and this far past it at the end
PUSH_SIDE = 0.35          # push direction: outwards, plus this much towards the centre line
PUSH_SPEED = 0.5          # fraction of the arm speed limit during the push
PUSH_HEIGHT = 0.02        # m above the counter (grasp point); raised until the closed fingers clear the counter
PUSH_ABOVE = 0.10         # m above the counter: where the hand goes back up to after the push
PUSH_TOP = 0.18           # m above the counter: the joint-space move from home ends here, above the push start
MODES = ("off", "relay", "push")


def near_mode():
    m = os.environ.get("V16_NEAR", "off").strip().lower()
    return m if m in MODES else "off"


def _is_tri(d):
    return getattr(d, "shape", None) in ("triangle", "tipped")


class V16Chooser(V15Chooser):
    """V15Chooser; a push is not a last resort (the stock claw on a triangle is). Crowding counts any neighbour within
    CROWD_RADIUS, not only one for another bin, so a cluster is picked from the outside in (crowd_v16.py)."""

    @staticmethod
    def _last_resort(o):
        return o.route != "push" and V15Chooser._last_resort(o)

    def choose(self, options, ctx):
        """crowd_v16: options whose open fingers would come down on another object (NearEnumerator._crowd_gaps) are
        set aside while any clear option exists; an object left with only those waits for its neighbours to go."""
        from .crowd_v16 import CROWD_CLEAR_M, crowd_on
        gap = lambda o: getattr(o, "crowd_m", None)
        tight = [o for o in options if gap(o) is not None and gap(o) < CROWD_CLEAR_M]
        if crowd_on() and tight and len(tight) < len(options):
            clear = [o for o in options if not any(o is t for t in tight)]
            if not any(o.is_default for o in clear):       # MemoryChooser needs a default (it was a tight one)
                import copy
                clear[0] = copy.copy(clear[0])
                clear[0].is_default = True
            o, drop, rec = super().choose(clear, ctx)
            if o is not None:
                rec["crowd_set_aside"] = sorted({f"{t.obj}:{t.arm}/{t.grasp}" for t in tight})[:12]
                return o, drop, rec
        return super().choose(options, ctx)

    def _crowded(self, options, ctx):
        from .crowd_v16 import crowd_on
        if not crowd_on():
            return super()._crowded(options, ctx)
        from .upgrades import CROWD_RADIUS
        dets = ctx.get("dets") or []
        return {a.name for a in dets for b in dets
                if a is not b and np.linalg.norm(np.asarray(a.top[:2]) - np.asarray(b.top[:2])) < CROWD_RADIUS}


class NearEnumerator(MemoryEnumerator):
    def __init__(self, pol, lib, mode):
        super().__init__(pol, lib)
        self.mode = mode
        self.pushed = []          # pelvis xy where a push started (this episode)

    def reset(self):
        self.pushed = []

    def _option(self, d, p, arm, grasp, route, drop, default=False, face_a=None):
        """A V16_TRI plan carries its own label (face<k>p<angle>), so failure memory tells its angles apart."""
        lab = getattr(p, "tri_label", None)
        if lab and grasp == "face" and face_a is None:
            k, phi = parse_face(lab)
            face_a = dict(face_options(d, arm, phi)).get(k)
            if face_a is not None:
                grasp = lab
        return super()._option(d, p, arm, grasp, route, drop, default=default, face_a=face_a)

    def feasible_options(self, dets, arm_q, hand_q, budget_s=0.0, relay_budget_s=None):
        for pl in (self.pol.planner, self.pol.relay):
            pl.dets = list(dets)                           # crowd_v16.CrowdPlanner: the neighbours of each object
        options, info = super().feasible_options(dets, arm_q, hand_q, budget_s=budget_s, relay_budget_s=relay_budget_s)
        self._crowd_gaps(options)
        if self.mode == "off":
            return options, info
        info["near"] = []
        for d in self.candidates(dets):
            if not _is_tri(d) or float(d.top[0]) > NEAR_X:
                continue
            if any(o.obj == d.name and o.route == "direct" and o.grasp.startswith("face") for o in options):
                continue                                   # a face / ridge grasp straight to the bin exists
            p, why = (self._relay(d, dets, arm_q, hand_q) if self.mode == "relay"
                      else self._push(d, arm_q, hand_q))
            info["near"].append({"obj": d.name, "mode": self.mode, "ok": p is not None, "reason": str(why)[:120]})
            if p is not None:
                if self.mode == "relay":
                    o = self._option(d, p, p.side, "face", "relay", -1)
                else:
                    o = self._option(d, p, p.side, "push", "push", -1)
                if o.key not in {x.key for x in options}:
                    # the stock claw straight to the bin (2/30 held here) would rank first as a direct route: drop it
                    # while this way out exists (it is back once the relay / push for this object is used up)
                    options[:] = [x for x in options if not (x.obj == d.name and x.route == "direct")]
                    o.is_default = o.is_default or not any(x.is_default for x in options)
                    options.append(o)
        return options, info

    def _crowd_gaps(self, options):
        """crowd_v16: the finger gap to the other objects of every option (the forced arm / grasp variants are planned
        outside CrowdPlanner.plan, so the planner's own check never saw them)."""
        pl = self.pol.planner
        if not getattr(pl, "crowd", False):
            return
        for o in options:
            p = getattr(o, "plan", None)
            if p is not None and getattr(o, "crowd_m", None) is None and o.route in ("direct", "relay"):
                try:
                    o.crowd_m = float(pl.finger_clearance(p, p.side, o.det))
                except Exception:
                    o.crowd_m = None

    # ------------------------------------------------------------------ relay with a face / ridge grasp only
    def _relay(self, d, dets, arm_q, hand_q):
        pol = self.pol
        rl = pol.relay
        rl.face_only = True
        try:
            p = pol._plan_relay(d, dets, arm_q, hand_q)
        finally:
            rl.face_only = False
        if p is None:
            return None, "no relay with a face / ridge grasp"
        return p, f"relay via point {p.relay}"

    # ------------------------------------------------------------------ push
    def _push(self, d, arm_q, hand_q):
        if any(np.linalg.norm(d.top[:2] - xy) < 0.03 for xy in self.pushed):
            return None, "already pushed from here"
        y = float(d.top[1])
        sides = ["left", "right"] if y >= 0 else ["right", "left"]
        last = "no arm"
        for side in sides:
            p = plan_push(self.pol.planner, d, side, np.asarray(arm_q, float), np.asarray(hand_q, float))
            if p.ok:
                p.push_xy = d.top[:2].copy()
                return p, p.reason
            last = f"{side}: {p.reason}"
        return None, last


def plan_push(pl, d, side, arm_q, hand_q):
    """Closed hand down behind `d`, slide it outwards past where it was, back up, home. The closed hand pushes with
    its curled fingers whichever way they point, so finger directions are tried from the hand's natural one out.
    Returns a Plan (target_bin "counter"); not ok with a reason when no direction passes every check."""
    ref = O.FINGER_REF_DEG[side]
    first = None
    for off in (0, 30, -30, 60, -60):
        p = _plan_push_f(pl, d, side, arm_q, hand_q, ref + off)
        if p.ok:
            return p
        first = first or p
    return first


def _plan_push_f(pl, d, side, arm_q, hand_q, fdeg):
    g, mo, sc = pl.cfg["grasp"], pl.cfg["motion"], pl.scene
    zc, kin = sc.counter_z, pl.kin
    sl = ArmKinematics.sl(side)
    plan = Plan(False, side=side, color=d.color, target_bin="counter")
    hand_cls = hand_q.copy(); hand_cls[sl] = pl.post["closed"][sl]
    hand_open = hand_q.copy(); hand_open[sl] = pl.post["open"][sl]
    y = float(d.top[1])
    u = np.array([1.0, -PUSH_SIDE * np.sign(y) if abs(y) > 0.03 else 0.0])
    u /= np.linalg.norm(u)
    c = np.asarray(d.top[:2], float)
    p0, p1 = c - PUSH_START_M * u, c + PUSH_END_M * u
    saved = (kin.hint, kin.w_hint)
    kin.hint, kin.w_hint = np.array([np.cos(np.radians(fdeg)), np.sin(np.radians(fdeg)), 0.0]), O.FACE_HINT_WEIGHT
    try:
        z = zc + PUSH_HEIGHT
        for _ in range(4):
            q0, ok = pl._ik(side, np.r_[p0, z], arm_q, "push_start", plan)
            if not ok:
                plan.reason = f"IK push start {side}"
                return plan
            cl = pl.clearance(side, q0, hand_cls, fingers_only=True)
            if cl >= 0.006 - 1e-3:
                break
            z += 0.006 - cl
        else:
            plan.reason = "closed fingers hit the counter"
            return plan
        if z > zc + 0.7 * pl.height:
            plan.reason = f"push height {100 * (z - zc):.1f} cm: would go over the object"
            return plan
        z_hi = zc + PUSH_ABOVE
        pc = kin.grasp_pose(side, arm_q)[0]                     # where the hand is now (home)
        for top in (PUSH_TOP, 0.15, 0.12):
            z_top = zc + top
            q_a, ok = pl._ik(side, np.r_[pc[:2], max(pc[2], z_top)], arm_q, "turn", plan)   # turn the hand up here
            q_t, ok2 = pl._ik(side, np.r_[p0, z_top], q0, "push_above", plan)                 # same IK branch as q0
            if ok and ok2:
                break
        else:
            plan.reason = f"IK above push start {side}"
            return plan
        za = max(pc[2], z_top)
        over = [q_t]                                   # joint move between two high poses (clearance checked below)
        down = pl._cartesian(side, np.r_[p0, z_top], np.r_[p0, z], q_t, "descend", plan)
        push = down and pl._cartesian(side, np.r_[p0, z], np.r_[p1, z], down[-1], "push", plan)
        up = push and pl._cartesian(side, np.r_[p1, z], np.r_[p1, z_top], push[-1], "push_up", plan)
        back = [q_a] if up else None
        if not back:
            plan.reason = plan.reason or f"IK failed on the push path ({side})"
            return plan
    finally:
        kin.hint, kin.w_hint = saved

    vmax, amax, hv = mo["arm_max_vel"], mo["arm_max_acc"], mo["hand_max_vel"]
    home = arm_q.copy(); home[sl] = pl.home[sl]
    arm_parts, hand_parts, phases = [], [], []
    cur = {"a": arm_q.copy(), "h": hand_q.copy()}

    def add(name, a, h):
        if len(a):
            s = sum(len(x) for x in arm_parts)
            arm_parts.append(a); hand_parts.append(h); phases.append((name, s, s + len(a)))
            cur["a"] = a[-1].copy()

    def move(name, Qs, hand_to=None, speed=1.0):
        a = time_scale([cur["a"]] + list(Qs), vmax * speed, amax, pl.dt)
        h = np.repeat(cur["h"][None], len(a), 0)
        if hand_to is not None:
            hr = ramp(cur["h"], hand_to, hv, pl.dt)
            if len(hr) > len(a):
                a = np.vstack([a, np.repeat((a[-1] if len(a) else cur["a"])[None], len(hr) - len(a), 0)])
                h = np.repeat(cur["h"][None], len(a), 0)
            h[:len(hr)] = hr
            h[len(hr):] = hand_to
            cur["h"] = np.asarray(hand_to, float).copy()
        add(name, a, h)

    move("turn", [q_a], hand_to=hand_cls)
    move("to_push", over)
    move("descend", down)
    move("push", push, speed=PUSH_SPEED)
    move("push_up", up)
    move("back", back)
    move("home", [home], hand_to=hand_open)
    plan.arm, plan.hand, plan.phases = np.vstack(arm_parts), np.vstack(hand_parts), phases
    low = {"descend", "push", "push_up"}
    for k in range(0, len(plan.arm), 2):
        name = next(n for n, s, e in phases if s <= k < e)
        need = 0.004 if name in low else mo["counter_clearance"]
        cl = pl.clearance(side, plan.arm[k], plan.hand[k])
        if cl < need - 2e-3:
            plan.reason = f"hand {100 * cl:.1f} cm above counter during {name} (need {100 * need:.1f})"
            return plan
        if pl.bin_clearance(side, plan.arm[k], plan.hand[k]) < 0.003:
            plan.reason = f"hand over a bin rim during {name}"
            return plan
    plan.safety_clips = pl.dry_run_safety(arm_q, hand_q, plan.arm, plan.hand)
    if plan.safety_clips:
        plan.reason = f"{plan.safety_clips} safety clips in dry run"
        return plan
    plan.waypoints["push_from"], plan.waypoints["push_to"] = np.r_[p0, z], np.r_[p1, z]
    plan.waypoints["grasp"] = np.r_[c, z]               # Aalto's _start logs the attempt at waypoints["grasp"]
    plan.ok, plan.reason = True, f"push {side} from ({p0[0]:.2f},{p0[1]:+.2f}) to ({p1[0]:.2f},{p1[1]:+.2f})"
    return plan
