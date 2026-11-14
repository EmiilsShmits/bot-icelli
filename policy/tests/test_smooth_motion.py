"""Unit tests for policy/smooth_motion.py (the jerk-limited replacement for Aalto's planner.time_scale).

    python -m unittest policy/tests/test_smooth_motion.py -v        # from the repo root; needs numpy + scipy only
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

import smooth_motion  # noqa: E402

DT = 1.0 / 30.0
CAP = smooth_motion._cfg()[1]


def original_time_scale(Qs, vmax, amax, dt):
    """Copy of Aalto's planner.time_scale (the code it replaces), so the tests need no Pinocchio."""
    Qs = np.asarray(Qs, float)
    seg = np.abs(np.diff(Qs, axis=0)).max(axis=1)
    S = float(seg.sum())
    if S < 1e-9:
        return np.empty((0, Qs.shape[1]))
    ta = vmax / amax
    if amax * ta * ta > S:
        ta = np.sqrt(S / amax)
        vpk, T = amax * ta, 2 * ta
    else:
        vpk, T = vmax, 2 * ta + (S - amax * ta * ta) / vmax
    n = max(1, int(np.ceil(T / dt)))
    t = np.arange(1, n + 1) * (T / n)
    s = np.where(t < ta, 0.5 * amax * t ** 2,
                 np.where(t <= T - ta, 0.5 * amax * ta ** 2 + vpk * (t - ta), S - 0.5 * amax * (T - t) ** 2))
    s = np.clip(s, 0, S)
    cum = np.r_[0.0, np.cumsum(seg)]
    out = np.empty((n, Qs.shape[1]))
    for k, sk in enumerate(s):
        i = min(int(np.searchsorted(cum, sk, side="right")) - 1, len(seg) - 1)
        f = 0.0 if seg[i] < 1e-12 else (sk - cum[i]) / seg[i]
        out[k] = Qs[i] + f * (Qs[i + 1] - Qs[i])
    return out


def stats(Qs, out):
    q = np.vstack([np.asarray(Qs, float)[:1], out])
    v = np.diff(q, axis=0) / DT
    a = np.diff(np.vstack([np.zeros((1, q.shape[1])), v, np.zeros((1, q.shape[1]))]), axis=0) / DT
    return float(np.abs(v).max()), float(np.abs(a).max())


def ik_like_path(rng, n=6, d=7):
    """A curved joint path like a Cartesian line through IK waypoints (smooth, 0.1-0.5 rad steps)."""
    t = np.linspace(0, 1, n)[:, None]
    base = rng.uniform(-1, 1, d)
    return base + 0.8 * np.sin(np.pi * t * rng.uniform(0.5, 1.5, d)) * rng.uniform(-1, 1, d)


class TestSmoothTimeScale(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SMOOTH_MOTION", None)
        os.environ.pop("SMOOTH_ARM_ACC", None)

    def test_endpoints_and_shape(self):
        rng = np.random.default_rng(0)
        for _ in range(30):
            Qs = ik_like_path(rng)
            out = smooth_motion.smooth_time_scale(Qs, 0.97, 8.0, DT)
            self.assertEqual(out.shape[1], Qs.shape[1])
            np.testing.assert_allclose(out[-1], Qs[-1], atol=1e-12)
            self.assertGreater(np.abs(out[0] - Qs[0]).max(), 0.0)      # Qs[0] itself is excluded, as in Aalto's

    def test_speed_never_above_vmax(self):
        rng = np.random.default_rng(1)
        for vmax in (0.5, 0.97):
            for _ in range(30):
                Qs = ik_like_path(rng)
                v, _ = stats(Qs, smooth_motion.smooth_time_scale(Qs, vmax, 8.0, DT))
                self.assertLessEqual(v, vmax * 1.001)

    def test_acceleration_far_below_original(self):
        rng = np.random.default_rng(2)
        worst_new, worst_old = 0.0, 0.0
        for _ in range(40):
            Qs = ik_like_path(rng)
            _, a_new = stats(Qs, smooth_motion.smooth_time_scale(Qs, 0.97, 8.0, DT))
            _, a_old = stats(Qs, original_time_scale(Qs, 0.97, 8.0, DT))
            worst_new, worst_old = max(worst_new, a_new), max(worst_old, a_old)
        self.assertLessEqual(worst_new, CAP * 1.4)              # the cap (+ curve and tick rounding)
        self.assertGreater(worst_old, 2 * worst_new)            # the original really was much rougher

    def test_two_point_move_and_tiny_move(self):
        Qs = np.array([np.zeros(7), np.r_[0.6, np.zeros(6)]])
        out = smooth_motion.smooth_time_scale(Qs, 0.97, 8.0, DT)
        v, a = stats(Qs, out)
        self.assertLessEqual(v, 0.97 * 1.001)
        self.assertLessEqual(a, CAP * 1.4)
        self.assertLess(len(out), 3 * len(original_time_scale(Qs, 0.97, 8.0, DT)) + 10)
        tiny = np.array([np.zeros(7), np.full(7, 1e-4)])
        self.assertGreaterEqual(len(smooth_motion.smooth_time_scale(tiny, 0.97, 8.0, DT)), 1)
        self.assertEqual(len(smooth_motion.smooth_time_scale(np.zeros((3, 7)), 0.97, 8.0, DT)), 0)

    def test_path_stays_between_neighbouring_waypoints(self):
        rng = np.random.default_rng(3)
        for _ in range(20):
            Qs = ik_like_path(rng)
            out = smooth_motion.smooth_time_scale(Qs, 0.97, 8.0, DT)
            lo, hi = Qs.min(axis=0) - 1e-9, Qs.max(axis=0) + 1e-9
            self.assertTrue(np.all(out >= lo) and np.all(out <= hi))

    def test_off_switch_uses_the_original(self):
        smooth_motion._ORIGINAL = original_time_scale
        try:
            os.environ["SMOOTH_MOTION"] = "0"
            Qs = ik_like_path(np.random.default_rng(4))
            np.testing.assert_allclose(smooth_motion.smooth_time_scale(Qs, 0.97, 8.0, DT),
                                       original_time_scale(Qs, 0.97, 8.0, DT))
        finally:
            smooth_motion._ORIGINAL = None
            os.environ.pop("SMOOTH_MOTION", None)


if __name__ == "__main__":
    unittest.main()
