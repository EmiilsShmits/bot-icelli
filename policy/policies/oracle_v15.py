"""v1.5 submission policy: Aalto's oracle motions, driven by the head camera instead of privileged poses, with our
upgrades. Built from `policy/decision_oracle/` (Emīls), which scored best in the sim without privileged state:
sort_language 26/28 and sort_fixed 21/27 in the venue look (eval/RESULTS.md e-022, e-019).

What runs (all offline, no API calls):
  * perception: head RGB-D only (`decision_oracle/camera.py`): head-camera pose re-fitted from depth (table plane +
    bin walls), objects by colour + height, shape and yaw from the top face.
  * motions: Aalto's oracle planner (`aaltonomous/sim/oracle.py`: face-aligned grasps, relay for cross-body objects,
    drop spots inside a bin), every plan pre-checked against the safety filter.
  * upgrades (`decision_oracle/upgrades.py`): failure memory per object, face grasp first, grasp check from the
    finger angles at the end of the lift, an option search that plans every object.
  * v1.5 (`decision_oracle/upgrades_v15.py`): same-side arms (each arm stays on its half of the table; cross-side
    objects are handed over on the centre line) and a grasp for lying triangles (fingers along the ridge, across
    the two triangular end faces).
  * instruction: Emīls's rule parser (`policy/instruction.py`), with colour x shape keys when the instruction names
    shapes.
  * every target passes our shadow safety filter (`policy/guard.py`); reset() never blocks (as v1).

Env: V15_SIDES (strict | off, default strict), V15_TIP_CHECK (off | d1 | hydrogen, default off: a Gemini check of the
camera's "lying" label; needs GEMINI_API_KEY; measured on 59 sim crops it did not beat the geometry, see
decision_oracle/README.md), AALTO_TIME_LIMIT (s, default 120), V15_DLOG (path: decision log,
default off), GUARD_ARM_VEL / GUARD_HAND_VEL (default 0.98 / 2.7).
"""
from __future__ import annotations

import logging
import os
import time

import numpy as np

from aaltonomous.deploy.policy_server import Policy
from aaltonomous.interface.tasks import FIXED_INSTRUCTION

from guard import Guard
from instruction import mapping_for

log = logging.getLogger("bot-icelli.v1.5")


def mapping_with_shapes(instruction, task=None):
    """instruction.mapping_for (one bin per colour) plus (colour, shape) keys wherever the parser gives a shape of
    that colour another bin (or "leave"). A lying triangle ("tipped") follows the triangle answer."""
    mapping, src = mapping_for(instruction, task)
    text = (instruction or "").strip()
    if text == FIXED_INSTRUCTION:
        return mapping, src
    try:
        import rule_parser
        from spec import BINS, COLORS, SHAPES
        slots = rule_parser.parse(text)
    except Exception:  # the colour mapping above is still valid
        log.exception("shape keys: parser failed on %r", text)
        return mapping, src
    if not isinstance(slots, dict):
        return mapping, src
    out, n = dict(mapping), 0
    for c in COLORS:
        for s in SHAPES:
            v = slots.get(f"{c} {s}")
            want = v if v in BINS else None
            if want != mapping.get(c):
                out[(c, s)] = want
                n += 1
                if s == "triangle":
                    out[(c, "tipped")] = want
    return out, src + (f" + {n} colour/shape keys" if n else "")


class OracleV15(Policy):
    name = "bot-icelli-v1.5"

    def __init__(self):
        from decision_oracle.upgrades_v15 import V15OraclePolicy
        self.pol = V15OraclePolicy(None, sides=os.environ.get("V15_SIDES", "strict"), perception="camera",
                                   grasp_check="on", dlog=os.environ.get("V15_DLOG") or None, threaded=True,
                                   tip_check=os.environ.get("V15_TIP_CHECK", "off"),
                                   time_limit=float(os.environ.get("AALTO_TIME_LIMIT", 120.0)),
                                   log=lambda m: log.info(m))
        self.guard = Guard(float(os.environ.get("GUARD_ARM_VEL", 0.98)), float(os.environ.get("GUARD_HAND_VEL", 2.7)))
        self.action_horizon = int(self.pol.cfg["motion"]["chunk"])
        self.mapping, self.mapping_source = {}, ""
        self._pending_reset, self._stale_since = None, None
        log.info("v1.5 ready: sides=%s time_limit=%.0f s", self.pol.sides, self.pol.time_limit)

    # ------------------------------------------------------------------ episode (same pattern as classical_v1.py)
    def reset(self, instruction, task=None, seed=None):
        # Never block here: the runner's watchdog stops the robot after 3 s without a command (classical_v1.py).
        if self.guard.shaped:
            log.info("previous episode: guard shaped %d of %d ticks", self.guard.shaped, self.guard.ticks)
        self.mapping, self.mapping_source = mapping_with_shapes(instruction, task)
        self._pending_reset = ({"instruction": instruction, "mapping": self.mapping}, task, seed)
        self.guard.reset()
        if self._planning():
            self._stale_since = time.monotonic()
            log.warning("previous episode's planning thread still running: holding until it finishes")
        else:
            self._apply_reset()
        log.info("reset task=%s seed=%s mapping=%s [%s] instruction=%r", task, seed, self.mapping,
                 self.mapping_source, instruction)

    def _planning(self):
        job = self.pol._job
        return job is not None and job["result"] is None

    def _apply_reset(self):
        from decision_oracle import insert
        info, task, seed = self._pending_reset
        self.pol.episode_seed, self.pol.task = seed, task
        info = insert.configure(self.pol, task, info)   # task 3: the lid's holes are the targets (insert.py)
        self.pol.reset(info)
        insert.after_reset(self.pol)
        self._pending_reset = None
        if self._stale_since is not None:
            log.info("old planning thread done after %.1f s: episode starts", time.monotonic() - self._stale_since)
            self._stale_since = None

    def _hold(self, obs):
        sp, k = self.pol.spec, max(1, int(self.pol.cfg["motion"].get("hold_ticks", 1)))
        a = np.clip(np.asarray(obs["arm_q"], float), sp.arm_lower, sp.arm_upper)
        h = np.clip(np.asarray(obs["hand_q"], float), sp.hand_lower, sp.hand_upper)
        return {"arm_q_target": np.repeat(a[None], k, 0), "hand_q_target": np.repeat(h[None], k, 0), "done": False}

    def act(self, obs):
        if self._pending_reset is not None:
            if self._planning():
                a = self._hold(obs)
            else:
                self._apply_reset()
                a = self.pol.act(obs)
        else:
            a = self.pol.act(obs)
        arm, hand = self.guard(a["arm_q_target"], a["hand_q_target"], obs)
        return {"arm_q_target": arm.astype(np.float64), "hand_q_target": hand.astype(np.float64),
                "done": bool(a.get("done", False))}
