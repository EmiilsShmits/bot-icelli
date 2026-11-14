"""v1.1 = v1 + two changes to Aalto's classical planner, aimed at the misses seen in Aalto's sim (Sat 14 Nov, nominal
sim, baseline seeds 1000-1003: 6 of 15 objects left on the table; `eval/RESULTS.md`).

  1. Hand-over for far cross-body objects. An object more than CROSS_Y m on the far side of its bin's arm (a red
     object on the robot's right going to the left bin; a blue one on its left going to the right bin) is first
     moved by the arm on its own side to a spot near the middle, HANDOVER_Y m towards the bin; the bin-side arm
     finishes from there on the next look. Aalto's planner hands over only when the cross-body grasp is impossible.
     It was possible in all 3 such cases (IK error ~5 mm, the arm at the edge of its reach), and all 3 failed.
  2. A retry budget per object. A failed grasp pushes the object 1-2 cm, and Aalto counts attempts only within a
     3 cm "same object" radius, so its 2-attempt limit never triggers (it tried one object 4 times, each time from
     where the last try had pushed it). Attempts now count within ATTEMPT_RADIUS, at most MAX_ATTEMPTS per object.

Everything else is v1 (`policies/classical_v1.py`): instruction parsing, real-object colours, speed guard.
Env (for tuning in the sim): V11_CROSS_Y (0.08), V11_HANDOVER_Y (0.07), V11_ATTEMPT_RADIUS (0.06), V11_MAX_ATTEMPTS (3).
"""
from __future__ import annotations

import logging
import os

import numpy as np

from aaltonomous.baselines.classical.planner import Planner
from aaltonomous.baselines.classical.policy import ClassicalPolicy

from policies.classical_v1 import ClassicalV1

log = logging.getLogger("bot-icelli.v1.1")

CROSS_Y = float(os.environ.get("V11_CROSS_Y", 0.08))
HANDOVER_Y = float(os.environ.get("V11_HANDOVER_Y", 0.07))
ATTEMPT_RADIUS = float(os.environ.get("V11_ATTEMPT_RADIUS", 0.06))
MAX_ATTEMPTS = int(os.environ.get("V11_MAX_ATTEMPTS", 3))


def far_cross_body(object_y, bin_y, cross_y=CROSS_Y):
    """True if the object lies more than cross_y on the far side of the arm that serves this bin."""
    return (bin_y > 0.1 and object_y < -cross_y) or (bin_y < -0.1 and object_y > cross_y)


class PlannerV11(Planner):
    def plan(self, det, arm_q, hand_q, bin_name=None, obstacles=(), relocate=True):
        bin_name = bin_name or self.mapping.get(det.color)
        rel = self.cfg["grasp"].get("relocate", {}).get("enabled", True)
        if relocate and rel and bin_name is not None and far_cross_body(float(det.top[1]), self.bin_xy(bin_name)[1]):
            r = self.plan_relocation(det, bin_name, np.asarray(arm_q, float), np.asarray(hand_q, float), obstacles)
            if r.ok:
                r.reason = f"hand-over ({r.reason})"
                return r
        return super().plan(det, arm_q, hand_q, bin_name, obstacles, relocate)

    def relocation_spots(self, det, bin_name, obstacles=()):
        """Aalto's candidate spots (a grid over the object area, clear of the object and of the other objects),
        nearest a hand-over point first: the middle of the object area, HANDOVER_Y towards the target bin, where
        both arms reach well. (Aalto sorts by distance to the bin: spots the carrying arm reaches worst.)"""
        rc = self.cfg["grasp"].get("relocate", {})
        sc = self.scene
        L = sc.cfg["layout"]
        m = float(rc.get("region_margin", 0.02))
        xs = np.linspace(L["region_x"][0] - m, L["region_x"][1] + m, 9)
        ys = np.linspace(L["region_y"][0] - m, L["region_y"][1] + m, 4)
        pts = sc.mat_to_pelvis(np.array([[x, y, 0.0] for x in xs for y in ys]))[:, :2]
        clear = float(rc.get("clearance", L["min_spacing"]))
        obs = np.asarray(list(obstacles), float).reshape(-1, 2)
        keep = [p for p in pts if np.linalg.norm(p - det.top[:2]) > 0.06
                and (len(obs) == 0 or np.linalg.norm(obs - p, axis=1).min() > clear)]
        target = np.array([pts[:, 0].mean(), np.sign(self.bin_xy(bin_name)[1]) * HANDOVER_Y])
        keep.sort(key=lambda p: np.linalg.norm(p - target))
        return keep[: int(rc.get("max_spots", 6))]


class PolicyV11(ClassicalPolicy):
    def _look(self, obs):
        """Aalto's _look (policy.py), with attempts counted per object within ATTEMPT_RADIUS (see module doc)."""
        dets = self.perception.detect(obs["head_rgb"], obs["head_depth"])
        self.last_detections = dets
        P = self.cfg["policy"]
        cands = []
        for d in dets:
            xy = d.top[:2]
            if any(np.linalg.norm(xy - f) < P["same_object_radius"] for f in self.failed):
                continue
            n = sum(c for p, c in self.attempts if np.linalg.norm(xy - p) < ATTEMPT_RADIUS)
            if n >= MAX_ATTEMPTS:
                continue
            cands.append(d)
        if P["order"] == "nearest_bin":
            def key(d):
                b = self.mapping.get(d.color)
                return np.inf if b is None else np.linalg.norm(d.top[:2] - self.planner.bin_xy(b))
        else:
            def key(d):
                return -d.n_px
        cands.sort(key=key)
        for d in cands:
            others = [o.top[:2] for o in dets if o is not d]
            p = self.planner.plan(d, self.arm_cmd, self.hand_cmd, obstacles=others)
            self.plans.append(p)
            if p.ok:
                return ("plan", p, len(dets))
            self.failed.append(d.top[:2])
            self.log(f"[classical] skip {d}: {p.reason}")
        return ("none", None, len(dets))


class ClassicalV11(ClassicalV1):
    name = "bot-icelli-v1.1"

    def __init__(self):
        super().__init__()
        # Same objects, our subclasses' methods: everything else (config, state, threads) stays Aalto's / v1's.
        self.pol.__class__ = PolicyV11
        self.pol.planner.__class__ = PlannerV11
        log.info("v1.1: hand-over beyond %.2f m cross-body (spot %.2f m towards the bin), %d attempts within %.2f m",
                 CROSS_Y, HANDOVER_Y, MAX_ATTEMPTS, ATTEMPT_RADIUS)
