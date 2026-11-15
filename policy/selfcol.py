"""Real robot: keep each elbow off the robot's own body.

The sims do not collide the arms with the torso, so a plan that swings an elbow in front of the chest passes every
sim check and then pushes against the body on the real robot. Sun 15 Nov 06:55 run (docs/research/real-run-0655.md):
  - purple cube, right arm: the plan took the elbow to 9 cm from the midline beside the torso; the real elbow stopped
    at ~10 cm, the hand was pushed ~2 cm to the right and missed the cube;
  - orange cube retry, left arm: the plan took the elbow to 2 cm from the midline; the real elbow stopped at ~11 cm
    and the arm kept pushing (0.55 rad shoulder error, the whole robot twisted) until the run was stopped.

Patch: Aalto's `Planner._plan_side`, which every v1.x plan goes through (face and triangle grasps, crowd, task 3, the
planner's own side/hint search). A plan whose elbow joint comes within SELFCOL_Y_MIN of the midline while it is
beside the torso (pelvis frame: x < SELFCOL_X_MAX, -0.10 < z < 0.40) is refused like an IK failure, so the planner
and the option search move on to the next option (other grasp, other arm, hand-over) or skip the object.
Measured in the pelvis frame, so the arm-based camera fit (`handeye.set_kin_base`) does not change it.
SELFCOL=off turns it off.
"""
from __future__ import annotations

import logging
import os

import numpy as np

log = logging.getLogger("bot-icelli.selfcol")

Y_MIN = float(os.environ.get("SELFCOL_Y_MIN", "0.13") or 0.13)   # m, elbow joint centre to the midline (contacts at 0.10-0.12)
X_MAX = float(os.environ.get("SELFCOL_X_MAX", "0.10") or 0.10)   # m forward of the pelvis origin (contacts at x 0.07-0.09)
Z_LO, Z_HI = -0.10, 0.40                                          # m, the torso's height range in the pelvis frame
STEP = 3                                                          # check every 3rd tick (0.1 s)
_ORIG = {}
_FRAMES = {}


def _frame(model, name):
    key = (id(model), name)
    if key not in _FRAMES:
        _FRAMES[key] = model.getFrameId(name)
    return _FRAMES[key]


def elbow(kin, side, arm_q):
    """-> (inside the body zone?, elbow distance from the midline (m, outward positive), elbow xyz in the pelvis frame)."""
    kin._fk(np.asarray(arm_q, float))
    d, m = kin.data, kin.model
    e = d.oMf[_frame(m, f"{side}_elbow_link")].translation
    x, y, z = (float(v) for v in d.oMf[_frame(m, "pelvis")].actInv(e))
    out = y if side == "left" else -y
    return (x < X_MAX and out < Y_MIN and Z_LO < z < Z_HI), out, (x, y, z)


def check_plan(kin, plan):
    """None if the plan keeps the elbow clear of the body, else the reason (str)."""
    arm = getattr(plan, "arm", None)
    side = getattr(plan, "side", None)
    if arm is None or side not in ("left", "right"):
        return None
    for k in list(range(0, len(arm), STEP)) + [len(arm) - 1]:
        inside, out, _ = elbow(kin, side, arm[k])
        if inside:
            phase = next((n for n, s, e in getattr(plan, "phases", []) if s <= k < e), "?")
            return f"{side} elbow {100 * out:.1f} cm from the midline during {phase} (body; needs {100 * Y_MIN:.0f})"
    return None


def _plan_side(self, *a, **kw):
    plan = _ORIG["plan_side"](self, *a, **kw)
    if not getattr(plan, "ok", False) or os.environ.get("SELFCOL", "on").lower() == "off":
        return plan
    try:
        why = check_plan(self.kin, plan)
    except Exception as e:                       # never let the check break planning
        log.warning("elbow check failed: %r", e)
        return plan
    if why:
        plan.ok, plan.reason = False, why
    return plan


def install():
    """Patch Aalto's Planner._plan_side (class level, idempotent)."""
    from aaltonomous.baselines.classical import planner as P
    if getattr(P.Planner, "_bot_icelli_selfcol", False):
        return
    _ORIG["plan_side"] = P.Planner._plan_side
    P.Planner._plan_side = _plan_side
    P.Planner._bot_icelli_selfcol = True
    log.info("elbow-body check on (SELFCOL=%s): plans refused when an elbow comes within %.0f cm of the midline "
             "beside the torso (x < %.2f m)", os.environ.get("SELFCOL", "on"), 100 * Y_MIN, X_MAX)
