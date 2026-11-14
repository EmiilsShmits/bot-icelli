"""v1.6: grasps next to other objects (V16_CROWD = on | off, default on).

Seed 1004 (e-050, e-051): a purple triangle between a yellow cylinder and an orange cube. Three face grasps closed on
nothing, each time with the open fingers coming down on a neighbour; the misses also knocked the cube out of reach.
The planner never looked at the other objects. Here it does:

  CrowdPlanner  every candidate plan (each face direction, each arm, the stock claw, the ridge grasp) is checked
                along its descend: any finger point lower than an object's top + CROWD_ABOVE_M must stay CROWD_CLEAR_M
                clear of every other detected object's footprint (a circle per shape). A plan that does not is
                refused, so the planner's own search moves on to the next face direction / arm / grasp. If no plan
                is clear, the least tight of the refused plans comes back (nothing that was pickable becomes
                unpickable, and no second search); it is marked `crowd_mm` so the log shows it.
  ordering      V16Chooser (near_v16.py) counts any neighbour within CROWD_RADIUS as crowding, not only one for
                another bin, so a cluster is picked from the outside in.

Classes: CrowdPlanner. Functions: crowd_on.
"""
from __future__ import annotations

import os

import numpy as np

from aaltonomous.baselines.classical.planner import Plan

from .upgrades_v15 import SidedPlanner

CROWD_CLEAR_M = 0.008     # finger points this far at least from a neighbour's footprint
CROWD_ABOVE_M = 0.015     # finger points higher than an object's top + this cannot hit it
FOOTPRINT_R = {"cube": 0.032, "cylinder": 0.0225, "triangle": 0.026, "tipped": 0.035}   # m, centre to farthest edge
FOOTPRINT_DEFAULT = 0.032
NEAR_M = 0.12             # only objects this close (centre to centre) can be under the open hand


def crowd_on():
    return os.environ.get("V16_CROWD", "on").strip().lower() not in ("0", "off", "false", "no")


class CrowdPlanner(SidedPlanner):
    crowd = True              # V16OraclePolicy sets it from V16_CROWD
    dets = ()                 # the last look's detections (NearEnumerator sets them before planning)
    _target = None            # the object being planned for (plan() sets it)
    _strict = False
    _refused = ()

    # ------------------------------------------------------------------ planning
    def plan(self, det, *a, **kw):
        if not self.crowd or not self._neighbours(det):
            return super().plan(det, *a, **kw)
        self._target, self._strict, self._refused = det, True, []
        try:
            p = super().plan(det, *a, **kw)
        finally:
            self._strict, self._target = False, None
        refused, self._refused = self._refused, []
        if p.ok or not refused:
            return p
        c, p2 = max(refused, key=lambda x: x[0])        # nothing clear: the least tight of the plans it refused
        p2.crowd_mm = round(1000 * c, 1)
        p2.reason = f"{p2.reason} [crowded {p2.crowd_mm:.0f} mm]"
        return p2

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, **kw):
        p = super()._plan_side(det, side, bin_name, arm_q, hand_q, **kw)
        if p.ok and self._strict and self._target is not None:
            c = self.finger_clearance(p, side, self._target)
            if c < CROWD_CLEAR_M:
                self._refused.append((c, p))
                return Plan(False, side=side, color=det.color,
                            reason=f"{side}: fingers {1000 * c:.0f} mm from a neighbour")
        return p

    # ------------------------------------------------------------------ geometry
    def _neighbours(self, det):
        out = []
        for o in self.dets or ():
            if o is det or getattr(o, "name", None) == getattr(det, "name", object()):
                continue
            dist = np.linalg.norm(np.asarray(o.top[:2]) - np.asarray(det.top[:2]))
            if dist < 0.01 or dist > NEAR_M:
                continue
            out.append(o)
        return out

    def finger_clearance(self, plan, side, det):
        """Smallest horizontal gap (m) between the finger points (distal links, fingertips) and a neighbour's footprint
        over the descend phase, counting only points low enough to hit it. inf if no point is."""
        nb = self._neighbours(det)
        if not nb:
            return np.inf
        ph = next(((s, e) for name, s, e in plan.phases if name == "descend"), None)
        if ph is None:
            return np.inf
        s, e = ph
        ks = sorted(set(list(range(s, e, 3)) + [e - 1]))
        xy = np.array([np.asarray(o.top[:2], float) for o in nb])
        r = np.array([FOOTPRINT_R.get(getattr(o, "shape", None), FOOTPRINT_DEFAULT) for o in nb])
        ztop = np.array([float(getattr(o, "z_top", None) or o.top[2]) for o in nb])
        best = np.inf
        for k in ks:
            pts = self.kin.hand_points(side, plan.arm[k], plan.hand[k])[2:]        # finger links + tips
            for q in pts:
                low = q[2] < ztop + CROWD_ABOVE_M
                if not low.any():
                    continue
                gap = np.linalg.norm(xy[low] - q[:2], axis=1) - r[low]
                best = min(best, float(gap.min()))
        return best
