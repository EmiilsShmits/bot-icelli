"""v1.3 = v1.2 + a free drop spot in each bin.

Aalto's planner releases every object at the same point of a bin: the inner corner nearest the pelvis,
`grasp.drop_inset` (5 cm) inside the walls. The second object into a bin then lands on the first, rests with its
centre above the 6 cm rim, and counts as "left on the counter" (Aalto's rule, `scene.py`). In the nominal sim the
baseline scored 24 of 24 first drops into a bin but 2 of 8 drops into a bin that already held an object: 6 of its
14 lost objects (`eval/analysis/FINDINGS.md` §1).

v1.3 counts the drops it has executed into each bin this episode and releases the n-th one at spot n (mod 3):
  side bins:   Aalto's point, then 5 cm further out along the bin, then 4.7 cm deeper (the far half is out of reach)
  centre bin:  Aalto's point, then 5 cm towards the arm's own side, then 5 cm the other way
Every spot stays at least MIN_WALL from every inner wall: the objects are 4.5 cm wide, and the oracle's second
spot, 2 cm from a wall, put a cube on the wall. If the plan to the chosen spot fails (reach), Aalto's point is used.
A failed grasp still advances the count (we can't tell an empty hand yet), which only skips a spot.
Env: V13_SPOTS=0 turns the spots off (= v1.2).
"""
from __future__ import annotations

import logging
import os

import numpy as np

from aaltonomous.baselines.classical.planner import Planner

from policies.classical_v11 import PlannerV11
from policies.classical_v12 import ClassicalV12, PolicyV12

log = logging.getLogger("bot-icelli.v1.3")

SPOTS_ON = os.environ.get("V13_SPOTS", "1") != "0"
MIN_WALL = 0.04
SIDE_OFFSETS = [(0.0, 0.0), (0.0, 0.05), (0.047, 0.0)]      # pelvis xy from Aalto's point; y points outwards
CENTER_OFFSETS = [(0.0, 0.0), (0.0, 0.05), (0.0, -0.05)]    # y towards the arm's own side first


class PlannerV13(PlannerV11):
    _drop_try = None
    drop_count = None          # {bin name: drops executed this episode}, owned by PolicyV13

    def drop_xy(self, name):
        return self._drop_try if self._drop_try is not None else super().drop_xy(name)

    def _inner_box(self, name):
        lo, hi = self.scene.bin_inner_box(name)
        a = self.scene.mat_to_pelvis(np.r_[lo[:2], 0.0])[:2]
        b = self.scene.mat_to_pelvis(np.r_[hi[:2], 0.0])[:2]
        return np.minimum(a, b), np.maximum(a, b)

    def drop_spots(self, name, side):
        """Release points (pelvis xy) for bin `name`, in order, each >= MIN_WALL inside every inner wall."""
        base = Planner.drop_xy(self, name)
        by = self.bin_xy(name)[1]
        if abs(by) > 0.1:
            offs = [(dx, dy * np.sign(by)) for dx, dy in SIDE_OFFSETS]
        else:
            s = 1.0 if side == "left" else -1.0
            offs = [(dx, dy * s) for dx, dy in CENTER_OFFSETS]
        lo, hi = self._inner_box(name)
        spots = [base + np.array(o) for o in offs]
        spots = [p for p in spots if np.all(p >= lo + MIN_WALL - 1e-9) and np.all(p <= hi - MIN_WALL + 1e-9)]
        return spots or [base]

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, place_xy=None):
        counts = self.drop_count
        if not SPOTS_ON or place_xy is not None or counts is None or bin_name not in self.scene.cfg["bins"]["centers"]:
            return super()._plan_side(det, side, bin_name, arm_q, hand_q, place_xy=place_xy)
        spots = self.drop_spots(bin_name, side)
        k = counts.get(bin_name, 0) % len(spots)
        if k:   # spot 0 is Aalto's point: the fallback below
            self._drop_try = spots[k]
            try:
                plan = super()._plan_side(det, side, bin_name, arm_q, hand_q, place_xy=None)
            finally:
                self._drop_try = None
            if plan.ok:
                plan.drop_spot = k
                return plan
        plan = super()._plan_side(det, side, bin_name, arm_q, hand_q, place_xy=None)
        plan.drop_spot = 0
        return plan


class PolicyV13(PolicyV12):
    def reset(self, info=None):
        super().reset(info)
        self.planner.drop_count = {}

    def _start(self, plan, t):
        b = plan.target_bin
        if b in self.scene.cfg["bins"]["centers"]:
            self.planner.drop_count[b] = self.planner.drop_count.get(b, 0) + 1
        return super()._start(plan, t)


class ClassicalV13(ClassicalV12):
    name = "bot-icelli-v1.3"

    def __init__(self):
        super().__init__()
        self.pol.__class__ = PolicyV13
        self.pol.planner.__class__ = PlannerV13
        self.pol.planner.drop_count = {}
        log.info("v1.3: drop spots %s (side bins %s, centre %s, >= %.0f cm from the walls)",
                 "on" if SPOTS_ON else "OFF", SIDE_OFFSETS, CENTER_OFFSETS, MIN_WALL * 100)
