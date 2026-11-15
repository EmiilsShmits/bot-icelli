"""v1.6 standing-triangle grasp (V16_TRI=mid, default off): the grasp point midway between the closed fingertips and
the thumb, and finger angles per hand.

Why (sim/mujoco/tri_bench.py, eval/analysis/grasps/README.md §4):
- Aalto's oracle puts the object centre almost at the fingertips (grasp.point_in_palm x = 0.099 m; closed fingertips
  at 0.101, thumb tip at 0.065). The closed thumb then stops ~11 mm short of the object, and the index finger has to
  push the object into it.
- A cube slides back flat and is caught; a standing prism is pushed on a slanted face or a corner and turns or slides
  away (MuJoCo: 17 % held with 4 mm / 4 deg perception noise).
- With the point at the midpoint (x = 0.083) both sides touch at once: 47 % over all angles, 61-76 % at the best ones.
- The pinch is thumb vs the index finger, so the good angles are mirrored between the hands: left 30, 90, 15, 75 deg
  from the apex; right 120 minus those.

Only standing triangles ("triangle") change; cubes, cylinders and lying prisms keep Aalto's grasp point.
"""
from __future__ import annotations

import copy
import os

import numpy as np
from aaltonomous.baselines.classical.planner import Plan
from aaltonomous.sim import oracle as O

from .crowd_v16 import CrowdPlanner
from .motions import face_options

TRI_POINT_X = 0.083                       # m along the left palm x: midway closed fingertips (0.101) <-> thumb (0.065)
TRI_ANGLES_LEFT = (30.0, 90.0, 15.0, 75.0)   # finger direction vs the apex, deg, best first (MuJoCo bench with noise)


def tri_mode():
    """V16_TRI: "off" (Aalto's grasp point and angles) | "mid" (this file)."""
    m = os.environ.get("V16_TRI", "mid").strip().lower()
    return m if m in ("off", "mid") else "off"


def tri_angles(side):
    """Finger angles vs the apex for this hand, best first (right = mirror of left)."""
    if side == "left":
        return TRI_ANGLES_LEFT
    return tuple(float((120.0 - a) % 120.0) for a in TRI_ANGLES_LEFT)


def standing_tri(det):
    return getattr(det, "shape", None) == "triangle"


class TriPlanner(CrowdPlanner):
    tri = "off"               # V16OraclePolicy sets it from V16_TRI

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, **kw):
        """Any plan for a standing triangle (face angles, Aalto's faces, stock claw) uses the midpoint grasp point."""
        if self.tri != "mid" or not standing_tri(det):
            return super()._plan_side(det, side, bin_name, arm_q, hand_q, **kw)
        saved = self.kin.offset[side]
        p = np.array([TRI_POINT_X, saved[1], saved[2]], float)
        self.kin.offset[side] = p
        try:
            return super()._plan_side(det, side, bin_name, arm_q, hand_q, **kw)
        finally:
            self.kin.offset[side] = saved

    def _plan_side_faces(self, det, side, bin_name, arm_q, hand_q, **kw):
        """Standing triangle: this hand's angles in order (labelled face<k>p<angle>), then Aalto's faces and the stock
        claw as before."""
        yaw = getattr(det, "yaw", None)
        if self.tri != "mid" or not standing_tri(det) or yaw is None:
            return super()._plan_side_faces(det, side, bin_name, arm_q, hand_q, **kw)
        saved = (self.kin.hint, self.kin.w_hint)
        try:
            for phi in tri_angles(side):
                for k, a in face_options(det, side, phi):
                    p = self._plan_tri(det, side, bin_name, arm_q, hand_q, a, **kw)
                    if p.ok:
                        p.tri_label = f"face{k}p{phi:.0f}"
                        return p
        finally:
            self.kin.hint, self.kin.w_hint = saved
        return super()._plan_side_faces(det, side, bin_name, arm_q, hand_q, **kw)

    def _plan_tri(self, det, side, bin_name, arm_q, hand_q, a, **kw):
        """One finger direction `a` (rad, pelvis yaw): Aalto's face plan (hint weight, triangle shift, tolerance)."""
        f = np.array([np.cos(a), np.sin(a), 0.0])
        d2 = copy.copy(det)
        d2.top = det.top + O._tri_shift(a - (det.yaw + np.pi / 2)) * f
        self.kin.hint, self.kin.w_hint = f, O.FACE_HINT_WEIGHT
        p = self._plan_side(d2, side, bin_name, arm_q, hand_q, **kw)
        if p.ok:
            err = self._finger_err(p, side, f)
            if err > O.FACE_TOL_DEG:
                return Plan(False, side=side, color=det.color,
                            reason=f"finger direction {err:.0f} deg off (tol {O.FACE_TOL_DEG:.0f})")
            p.reason = f"face-aligned ({np.degrees(a):.0f} deg, err {err:.0f}) [tri mid]"
        return p
