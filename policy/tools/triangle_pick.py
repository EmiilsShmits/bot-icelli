"""Plan a face-aligned triangle pick-and-place from a vision-supplied pose.

This tool plans only. The policy executor is responsible for sending the returned joint
targets through the normal safety guard. A triangle pose must include pelvis-frame yaw;
the stock colour detector does not estimate shape or yaw yet.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from aaltonomous.baselines.classical.perception import Detection
from aaltonomous.baselines.classical.kinematics import ArmKinematics


TRIANGLE_FINGER_ANGLE_DEG = 105.0  # tested by Aalto's privileged oracle grasp sweep
FINGER_REF_DEG = {"left": -25.0, "right": 25.0}
FACE_MAX_DEV_DEG = 75.0
FACE_HINT_WEIGHT = 3.0
FACE_TOL_DEG = 12.0

TOOL_DECLARATION = {
    "name": "pick_triangle",
    "description": (
        "Plan a safety-checked triangle pick-and-place. Use only when vision has identified one triangle and "
        "estimated its top centre and in-plane yaw in the pelvis frame. Returns a joint trajectory; it does not "
        "execute it. Never call with a guessed or missing pose."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "color": {"type": "string", "enum": ["red", "yellow", "blue"]},
            "top_xyz_m": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            "yaw_rad": {"type": "number", "description": "Triangle top-face orientation in pelvis frame."},
            "target_bin": {"type": "string", "enum": ["left", "center", "right"]},
        },
        "required": ["color", "top_xyz_m", "yaw_rad", "target_bin"],
    },
}


def triangle_midpoint_shift(phi: float, radius: float = 0.030) -> float:
    """Offset the pinch point from the centroid to the midpoint of a triangular prism's support face."""
    vertices = np.radians([0.0, 120.0, 240.0])
    return float(0.5 * (radius * np.cos(phi - vertices).max()
                        - radius * np.cos(phi + np.pi - vertices).max()))


class _TrianglePlannerMixin:
    """Face-aligned triangle behavior mixed into the active Aalto planner variant."""

    def _plan_side_hints(self, det, side, bin_name, arm_q, hand_q, **kw):
        yaw = getattr(det, "yaw", None)
        if getattr(det, "shape", None) != "triangle" or yaw is None or not math.isfinite(float(yaw)):
            return super()._plan_side_hints(det, side, bin_name, arm_q, hand_q, **kw)

        # The triangle's apex points along yaw + pi/2; try each face normal, nearest the hand's natural direction.
        ref = math.radians(FINGER_REF_DEG[side])
        offset = math.pi / 2 + math.radians(TRIANGLE_FINGER_ANGLE_DEG)
        candidates = []
        for k in range(3):
            angle = float(yaw) + offset + 2.0 * math.pi * k / 3.0
            error = abs((angle - ref + math.pi) % (2.0 * math.pi) - math.pi)
            if error <= math.radians(FACE_MAX_DEV_DEG):
                candidates.append((error, angle))

        saved_hint, saved_weight = self.kin.hint, self.kin.w_hint
        first_failure = None
        try:
            for _, angle in sorted(candidates):
                finger = np.array([math.cos(angle), math.sin(angle), 0.0])
                shifted = copy.copy(det)
                phi = angle - (float(yaw) + math.pi / 2)
                shifted.top = np.asarray(det.top, float) + triangle_midpoint_shift(phi) * finger
                self.kin.hint, self.kin.w_hint = finger, FACE_HINT_WEIGHT
                plan = self._plan_side(shifted, side, bin_name, arm_q, hand_q, **kw)
                if plan.ok and self._finger_error(plan, side, finger) <= FACE_TOL_DEG:
                    plan.reason = f"triangle face-aligned ({math.degrees(angle):.0f} deg)"
                    plan.waypoints["object_center"] = np.asarray(det.top, float).copy()
                    return plan
                first_failure = first_failure or plan
        finally:
            self.kin.hint, self.kin.w_hint = saved_hint, saved_weight

        # Keep Aalto's ordinary grasp as a checked fallback if face alignment cannot be solved.
        fallback = super()._plan_side_hints(det, side, bin_name, arm_q, hand_q, **kw)
        if fallback.ok:
            fallback.reason = "triangle fallback: " + fallback.reason
            fallback.waypoints["object_center"] = np.asarray(det.top, float).copy()
            return fallback
        if first_failure is not None:
            first_failure.reason = f"triangle face grasp failed; fallback failed: {fallback.reason}"
            return first_failure
        return fallback

    def _finger_error(self, plan, side, finger):
        _, start, end = next(p for p in plan.phases if p[0] == "descend")
        self.kin._fk(plan.arm[end - 1])
        x_axis = self.kin.data.oMf[self.kin.palm[side]].rotation[:, 0]
        diff = math.atan2(x_axis[1], x_axis[0]) - math.atan2(finger[1], finger[0])
        return abs(math.degrees((diff + math.pi) % (2.0 * math.pi) - math.pi))


class TrianglePickTool:
    """Agent-callable planner; measured joint state is taken from the observation, never model arguments."""

    declaration = TOOL_DECLARATION

    def __init__(self, planner):
        # Own Pinocchio model/data: tool planning must not race the policy's background planner.
        kin = ArmKinematics(planner.cfg, planner.spec)
        base_type = type(planner)
        triangle_type = type(f"Triangle{base_type.__name__}", (_TrianglePlannerMixin, base_type), {})
        self.planner = triangle_type.__new__(triangle_type)
        self.planner.__dict__.update(planner.__dict__)
        self.planner.kin = kin

    def __call__(self, observation: dict, color: str, top_xyz_m, yaw_rad: float, target_bin: str,
                 obstacles_xy_m=()) -> dict:
        """Return a checked trajectory or a refusal. `observation` must be the latest Aalto observation."""
        if not isinstance(color, str) or color not in {"red", "yellow", "blue"}:
            return self._refusal("unsupported color")
        if (not isinstance(target_bin, str) or target_bin not in {"left", "center", "right"}
                or target_bin not in self.planner.scene.cfg["bins"]["centers"]):
            return self._refusal("unknown target bin")
        try:
            top = np.asarray(top_xyz_m, dtype=float)
            yaw = float(yaw_rad)
            arm_q = np.asarray(observation["arm_q"], dtype=float)
            hand_q = np.asarray(observation["hand_q"], dtype=float)
            obstacles = np.asarray(obstacles_xy_m, dtype=float).reshape(-1, 2)
        except (KeyError, TypeError, ValueError, OverflowError):
            return self._refusal("invalid or incomplete pose/state")

        if top.shape != (3,) or not np.all(np.isfinite(top)) or not math.isfinite(yaw):
            return self._refusal("triangle pose must contain finite xyz and yaw")
        if arm_q.shape != (14,) or hand_q.shape != (14,) or not np.all(np.isfinite(arm_q)) or not np.all(np.isfinite(hand_q)):
            return self._refusal("observation must contain finite 14-joint arm_q and hand_q")
        if not np.all(np.isfinite(obstacles)):
            return self._refusal("obstacle positions must be finite")
        if np.any(arm_q < self.planner.spec.arm_lower) or np.any(arm_q > self.planner.spec.arm_upper):
            return self._refusal("measured arm state is outside joint limits")
        if np.any(hand_q < self.planner.spec.hand_lower) or np.any(hand_q > self.planner.spec.hand_upper):
            return self._refusal("measured hand state is outside joint limits")

        det = Detection(color, top.copy(), 0, 0, "tool", yaw=yaw)
        det.shape = "triangle"
        plan = self.planner.plan(det, arm_q, hand_q, bin_name=target_bin, obstacles=obstacles, relocate=True)
        if not plan.ok or plan.arm is None or plan.hand is None:
            return self._refusal(plan.reason or "no safe triangle plan")
        planned_bin = getattr(plan, "target_bin", None)
        return {
            "ok": True,
            "skill": "pick_triangle",
            "side": plan.side,
            "target_bin": planned_bin or target_bin,
            "route": "direct" if planned_bin in (None, target_bin) else "relay",
            "duration_s": plan.duration,
            "safety_clips": plan.safety_clips,
            "grasp_xyz_m": plan.waypoints.get("grasp", np.zeros(3)).tolist(),
            "arm_q_target": plan.arm.tolist(),
            "hand_q_target": plan.hand.tolist(),
        }

    def bind(self, observation: dict):
        """Bind a snapshot of measured state and return a model function-call compatible skill."""
        try:
            snapshot = {
                "arm_q": np.asarray(observation["arm_q"], dtype=float).copy(),
                "hand_q": np.asarray(observation["hand_q"], dtype=float).copy(),
            }
        except (KeyError, TypeError, ValueError):
            snapshot = observation

        def pick_triangle(color: str, top_xyz_m: list[float], yaw_rad: float, target_bin: str) -> dict:
            """Plan a safety-checked pick-and-place for a vision-confirmed triangle pose."""
            return self(snapshot, color, top_xyz_m, yaw_rad, target_bin)

        pick_triangle.__name__ = TOOL_DECLARATION["name"]
        return pick_triangle

    @staticmethod
    def _refusal(reason: str) -> dict:
        return {"ok": False, "skill": "pick_triangle", "reason": reason}
