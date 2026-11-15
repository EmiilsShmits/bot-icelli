"""Real robot: aim the arms in the robot's own frame, not in the table frame the head-camera fit gives.

Why (docs/research/hand-offset-real-data.md, measured on Aalto's real footage): on the real G1 the upper body, head
camera and arms together, leans 5-10 deg forward relative to the table, and the head camera sits within ~2.4 deg of
calibration.yaml. Our policies (v1.4-v1.6, Marcus's agent) fit the head camera to the table and bins every episode and
plan in that fitted (table) frame. That is right for perception and for clearance checks against the table and bins,
but the arms live in calibration.yaml's frame: solving IK in the fitted frame puts the real hand 6-9 cm short of the
object and too low.

What this does: a runtime patch of Aalto's ArmKinematics (used by Aalto's planner, the oracle, v1.x and Marcus's
skills) that maps every IK target from the fitted frame into the arm frame just before IK, and forward kinematics
back, so every planner keeps working in the table frame:
    p_arm = R p_fit + t - offset[side],   [R | t] = M = T0 @ inv(T_fit)   (T0: calibration.yaml head pose)
The palm's "down" axis and the finger hint are mapped with R, so the grasp stays square to the table.
`set_fit()` is called once per episode by whoever fits the head camera (decision_oracle/camera.py; Marcus's agent via
policy/adk/patch_lean.py). Gate: on only if that fit tilts the camera >= LEAN_MIN_TILT from calibration.yaml. Aalto's
real footage gives 8-12 deg, their sims ~1-2 deg, so in their sims nothing changes.

Env: LEAN_MAP auto | on | off (default off); LEAN_OFFSETS on | off (default on: the per-arm offsets measured in §3
of the doc); LEAN_MIN_TILT deg (default 5).

Default off since Sun 15 Nov ~02:00: in a sim where the robot leans 8 deg forward with the head camera 2.4 deg
further down on its mount (modal_pipeline/sim/scene_variant.py --lean 8 --cam-mount 2.4, Aalto look, v1.6,
seeds 1000-1002), LEAN_MAP=auto sorted 7/12 objects and LEAN_MAP=off 12/12 (Modal runs lean-v16-auto,
lean-v16-off; 0 clipped steps in both). In the venue look (camera tilted ~10 deg on its mount, robot upright)
auto would also switch on, wrongly. Untested on the real robot either way.
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

log = logging.getLogger("bot-icelli.lean")

# Real hand minus joint-angle hand, pelvis frame, seen through calibration.yaml's camera (doc §3; across the line of
# sight only, the right arm from 23 frames of one dataset).
OFFSETS = {"left": np.array([0.015, -0.008, 0.011]), "right": np.array([0.010, -0.029, 0.011])}
_ZERO = {"left": np.zeros(3), "right": np.zeros(3)}
_S = {"on": False, "M": np.eye(4), "Minv": np.eye(4), "off": dict(_ZERO), "info": {}}
_tl = threading.local()          # > 0 inside solve(): Aalto's IK checks its own FK in the arm frame
_ORIG = {}


def active():
    return bool(_S["on"])


def info():
    return dict(_S["info"])


def off():
    _S.update(on=False, M=np.eye(4), Minv=np.eye(4), off=dict(_ZERO), info={"on": False})


def set_gravity(down_arm, log_fn=None):
    """Gravity feed-forward (policy/gravity_ff.py) with gravity along `down_arm` (pelvis frame, None = straight down
    or GRAVITY_FF_PITCH_DEG): on a leaning robot the arms' gravity torque turns with it. GRAVITY_FF_LEAN=off: keep."""
    if os.environ.get("GRAVITY_FF_LEAN", "on").strip().lower() == "off":
        return
    try:
        import gravity_ff
        gravity_ff.set_down(down_arm, log_fn)
    except Exception as e:                       # never break the episode for it
        (log_fn or log.info)(f"[lean] gravity direction not set: {e!r}")


def set_fit(T0, T_fit, tilt_deg, log_fn=None, mode=None):
    """Once per episode, after the head-camera fit. T0 = calibration.yaml pose, T_fit = fitted pose (both 4x4,
    pelvis <- optical); tilt_deg = the fit's tilt from T0. T_fit None (fit rejected) -> off.
    mode: auto | on | off, None = env LEAN_MAP (V16_CALIB=lean passes its own: auto only when its arm fit failed)."""
    mode = mode or os.environ.get("LEAN_MAP", "off")
    thr = float(os.environ.get("LEAN_MIN_TILT", 5.0) or 5.0)
    on = T_fit is not None and (mode == "on" or (mode == "auto" and float(tilt_deg) >= thr))
    if not on:
        off()
        _S["info"] = {"on": False, "tilt_deg": round(float(tilt_deg or 0.0), 2), "mode": mode}
    else:
        M = np.asarray(T0, float) @ np.linalg.inv(np.asarray(T_fit, float))
        offsets = OFFSETS if os.environ.get("LEAN_OFFSETS", "on") != "off" else _ZERO
        R = M[:3, :3]
        z = R @ np.array([0.0, 0.0, 1.0])
        lean = float(np.degrees(np.arccos(np.clip(z[2], -1.0, 1.0))))
        _S.update(on=True, M=M, Minv=np.linalg.inv(M), off={k: np.asarray(v, float) for k, v in offsets.items()})
        _S["info"] = {"on": True, "tilt_deg": round(float(tilt_deg), 2), "mode": mode,
                      "lean_deg": round(lean, 2), "shift_cm": [round(100 * float(v), 1) for v in M[:3, 3]],
                      "offsets": "on" if offsets is OFFSETS else "off"}
    msg = (f"arm-frame mapping {'ON' if _S['on'] else 'off'}: {_S['info']}")
    (log_fn or log.info)(f"[lean] {msg}")
    if _S["on"]:
        set_gravity(_S["M"][:3, :3] @ np.array([0.0, 0.0, -1.0]), log_fn)
    return _S["on"]


def to_arm(p, side):
    """Fitted-frame point -> where the arm model must put its grasp point."""
    M = _S["M"]
    return M[:3, :3] @ np.asarray(p, float) + M[:3, 3] - _S["off"][side]


def from_arm(p, side):
    """Arm-model point(s) (3,) or (n, 3) -> fitted frame (where the real hand is)."""
    Mi = _S["Minv"]
    return (np.asarray(p, float) + _S["off"][side]) @ Mi[:3, :3].T + Mi[:3, 3]


# ---------------------------------------------------------------------------------------------- the patch
def _solve(self, side, target, arm_q_seed, top_down=True, extra_seeds=(), restarts=True):
    if not _S["on"]:
        return _ORIG["solve"](self, side, target, arm_q_seed, top_down, extra_seeds, restarts)
    from aaltonomous.baselines.classical import kinematics as K
    R = _S["M"][:3, :3]
    down0, hint0 = K.DOWN, self.hint
    K.DOWN = R @ np.array([0.0, 0.0, -1.0])
    self.hint = R @ np.asarray(hint0, float)
    _tl.raw = getattr(_tl, "raw", 0) + 1
    try:
        return _ORIG["solve"](self, side, to_arm(target, side), arm_q_seed, top_down, extra_seeds, restarts)
    finally:
        K.DOWN, self.hint = down0, hint0
        _tl.raw -= 1


def _grasp_pose(self, side, arm_q):
    p, a = _ORIG["grasp_pose"](self, side, arm_q)
    if not _S["on"] or getattr(_tl, "raw", 0):
        return p, a
    return from_arm(p, side), _S["Minv"][:3, :3] @ a


def _hand_points(self, side, arm_q, hand_q):
    pts = _ORIG["hand_points"](self, side, arm_q, hand_q)
    if not _S["on"] or getattr(_tl, "raw", 0):
        return pts
    return from_arm(pts, side)


def install():
    """Patch Aalto's ArmKinematics (class level, idempotent). Does nothing until set_fit() turns the mapping on."""
    from aaltonomous.baselines.classical import kinematics as K
    A = K.ArmKinematics
    if getattr(A, "_bot_icelli_lean", False):
        return
    _ORIG.update(solve=A.solve, grasp_pose=A.grasp_pose, hand_points=A.hand_points)
    A.solve, A.grasp_pose, A.hand_points = _solve, _grasp_pose, _hand_points
    A._bot_icelli_lean = True
    log.info("arm-frame mapping installed (LEAN_MAP=%s): off until a head-camera fit tilts >= %s deg",
             os.environ.get("LEAN_MAP", "off"), os.environ.get("LEAN_MIN_TILT", "5"))
