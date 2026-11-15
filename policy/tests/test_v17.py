"""v1.7 (policies/oracle_v17.py): v1.6 + the lean fallback (the fallback itself: test_v16.py TestLeanFallback) + the
higher drop (V17_DROP=high).

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python -m unittest policy.tests.test_v17 -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

ENV = {"GEMINI_API_KEY": "", "DECISION_KEY_FILE": "/nonexistent", "V16_LABELS": "off", "V16_INSTRUCTION": "rules"}


class TestV17(unittest.TestCase):
    def build(self, name, **env):
        import server
        with mock.patch.dict(os.environ, {**ENV, **env}):
            return server.POLICIES[name]()

    def test_registered_and_fallback_on(self):
        p = self.build("v1.7")
        self.assertEqual(p.name, "bot-icelli-v1.7")
        self.assertTrue(p.lean_keep)
        self.assertTrue(p.pol.cam.lean_fallback)

    def test_switches(self):
        self.assertFalse(self.build("v1.7", V17_LEAN_KEEP="off").pol.cam.lean_fallback)
        self.assertFalse(self.build("v1.7", V16_CALIB="bins").pol.cam.lean_fallback)

    def test_v16_keeps_its_behaviour(self):
        self.assertFalse(self.build("v1.6").pol.cam.lean_fallback)

    def test_drop_off_by_default(self):
        p, ref = self.build("v1.7"), self.build("v1.6")
        self.assertEqual(p._drop_high, {})
        self.assertIsNone(p._climb)
        self.assertNotIn("_cartesian", p.pol.planner.__dict__)         # the planner is v1.6's, untouched
        p.reset("Put the red objects in the left bin.", task="sort_language", seed=1)
        for k in ("carry_height", "drop_above_rim", "drop_inset"):
            self.assertEqual(p.pol.cfg["grasp"][k], ref.pol.cfg["grasp"][k])

    def test_drop_high_for_sorting_only(self):
        p = self.build("v1.7", V17_DROP="high", V17_DROP_INSET="0.07")
        g0 = dict(p.pol.cfg["grasp"])
        sort_planner = p.pol.planner
        p.reset("Put the red objects in the left bin.", task="sort_language", seed=1)
        g = p.pol.planner.cfg["grasp"]                       # what the planner reads
        # the lift at the pick stays v1.6's: only the release and the end of the carry are higher
        self.assertEqual((g["carry_height"], g["drop_above_rim"], g["drop_inset"]), (g0["carry_height"], 0.10, 0.07))
        self.assertTrue(p._climb["on"])
        self.assertEqual(p._climb["over"], 0.22)
        self.assertEqual(p._climb["floor"], g0["drop_above_rim"])
        p.pol.planner.__dict__["_reach"] = {"stale": True}
        p.reset("insert", task="insert_shapes", seed=2)      # task 3: v1.6's values, reach cache dropped
        for k in ("carry_height", "drop_above_rim", "drop_inset"):
            self.assertEqual(g[k], g0[k])
        self.assertFalse(p._climb["on"])
        self.assertNotIn("stale", sort_planner.__dict__.get("_reach", {}))
        self.assertIsNot(p.pol.planner, sort_planner)        # task 3 plans with its own planner
        self.assertNotIn("_cartesian", p.pol.planner.__dict__)
        g3 = p.pol.planner.cfg["grasp"]                      # v1.6's carry, its own release
        self.assertEqual(g3["carry_height"], g0["carry_height"])
        self.assertLess(g3["drop_above_rim"], 0.02)          # lowered to LID_GAP above the lid, not dropped from high
        p.reset("Put the red objects in the left bin.", task="sort_language", seed=3)
        self.assertIs(p.pol.planner, sort_planner)
        self.assertTrue(p._climb["on"])
        self.assertEqual((g["carry_height"], g["drop_above_rim"]), (g0["carry_height"], 0.10))


class TestClimb(unittest.TestCase):
    """install_climb on Aalto's oracle planner (ground-truth detections): lift as v1.6, carry ends high over the box."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        from aaltonomous.interface import tasks
        from aaltonomous.scene.scene import Scene
        from aaltonomous.sim.oracle import OraclePolicy
        from decision_oracle.test_offline import FakeClient, setup
        cls.scene = Scene.load()
        layout = tasks.sample_layout(np.random.default_rng(100), **cls.scene.layout_kwargs())

        def make(overrides):
            pol = OraclePolicy(FakeClient(cls.scene, layout), overrides=overrides, threaded=False, prefetch=False,
                               log=None)
            setup(pol)
            return pol
        cls.make = staticmethod(make)

    def heights(self, pol, p):
        """Grasp point above the table (m): end of lift, highest and lowest of carry + lower, at release."""
        ph = {name: (s, e) for name, s, e in p.phases}
        z = [pol.kin.grasp_pose(p.side, q)[0][2] - self.scene.counter_z for q in p.arm]
        c = z[ph["carry"][0]:ph["carry"][1]]
        return z[ph["lift"][1] - 1], max(c), min(c), z[ph["open"][0]]

    def plans(self, pol):
        out = []
        for det in pol.perception.detect():
            p = pol.planner.plan(det, pol.arm_cmd, pol.hand_cmd, relocate=False)
            if p.ok:
                out.append(p)
        return out

    def test_lift_low_then_climb(self):
        from policies.oracle_v17 import install_climb
        ref = self.make({})
        g0 = ref.cfg["grasp"]
        pol = self.make({"grasp.drop_above_rim": 0.10, "grasp.drop_inset": 0.08})
        st = install_climb(pol.planner, g0["drop_above_rim"], 0.22)
        self.assertIs(install_climb(pol.planner, g0["drop_above_rim"], 0.22), st)      # installed once
        st["on"] = True
        plans, ref_plans = self.plans(pol), self.plans(ref)
        self.assertGreaterEqual(len(plans), len(ref_plans))
        self.assertGreater(st["level"] + st["raised"], 0)
        wall = float(self.scene.cfg["bins"]["wall_height"])
        release = wall + pol.planner.height / 2 + 0.10
        raised = 0
        for p in plans:
            lift, top, low, rel = self.heights(pol, p)
            self.assertAlmostEqual(lift, g0["carry_height"], delta=0.005)      # at the pick: v1.6's lift
            self.assertAlmostEqual(rel, release, delta=0.005)                  # released 10 cm above the rim
            self.assertGreater(low, wall + pol.planner.height / 2 + g0["drop_above_rim"] - 0.005)
            self.assertEqual(p.safety_clips, 0)
            raised += top > 0.215
        self.assertGreater(raised, 0)
        for p in ref_plans:                                                    # v1.6 for comparison: released low
            self.assertLess(self.heights(ref, p)[3], release - 0.05)

    def test_off_is_a_passthrough(self):
        from policies.oracle_v17 import install_climb
        ref, pol = self.make({}), self.make({})
        st = install_climb(pol.planner, ref.cfg["grasp"]["drop_above_rim"], 0.22)
        a, b = self.plans(pol), self.plans(ref)
        self.assertEqual((st["level"], st["raised"], st["plain"]), (0, 0, 0))
        self.assertEqual(len(a), len(b))
        for p, q in zip(a, b):
            self.assertEqual(p.arm.shape, q.arm.shape)
            self.assertLess(abs(p.arm - q.arm).max(), 1e-9)


if __name__ == "__main__":
    unittest.main()
