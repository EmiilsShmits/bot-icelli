"""Unit tests for policy/selfcol.py (elbow-body check). Needs Pinocchio and the G1 URDF, e.g. in the policy image:
    docker run --rm -w /app/policy bot-icelli/policy:<tag> python3 -m unittest tests.test_selfcol -v
Joint vectors are the commanded poses of the real 06:55 run (docs/research/real-run-0655.md)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import selfcol  # noqa: E402

try:
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False

# 7 joints per arm: shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw (rad), from arm_q_cmd of the real run
LEFT_RETRY_CRASH = [-0.59, -0.75, 1.48, -0.95, 1.0, -1.32, -1.12]    # t 45.0: real elbow stopped at ~11 cm, pushed on
RIGHT_PURPLE = [-0.32, 0.22, 1.11, 0.39, -1.22, 1.17, -0.29]         # t 36.1: real elbow stopped at ~10 cm, hand pushed
LEFT_ORANGE_FIRST = [0.13, 0.52, -0.76, -0.33, 1.17, 0.77, 0.29]     # t 26.0: tracked within 1 mm
RIGHT_YELLOW = [-0.05, -0.09, 0.66, -0.01, -1.47, 0.57, -0.10]       # t 14.3: the pick that worked


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (policy image or the sim machine)")
class TestSelfCol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.sim.oracle import ORACLE_OVERRIDES
        cfg = load_config(None, dict(ORACLE_OVERRIDES))
        cls.kin = ArmKinematics(cfg)
        cls.home = home_arm(cfg)

    def q(self, side, seven):
        q = np.asarray(self.home, float).copy()
        q[(slice(0, 7) if side == "left" else slice(7, 14))] = seven
        return q

    def test_real_collisions_are_refused(self):
        for side, seven in (("left", LEFT_RETRY_CRASH), ("right", RIGHT_PURPLE)):
            inside, out, xyz = selfcol.elbow(self.kin, side, self.q(side, seven))
            self.assertTrue(inside, f"{side}: elbow {out:.3f} m from the midline at {np.round(xyz, 3)}")

    def test_real_clear_poses_pass(self):
        for side, seven in (("left", LEFT_ORANGE_FIRST), ("right", RIGHT_YELLOW)):
            inside, out, xyz = selfcol.elbow(self.kin, side, self.q(side, seven))
            self.assertFalse(inside, f"{side}: elbow {out:.3f} m at {np.round(xyz, 3)}")
        for side in ("left", "right"):
            self.assertFalse(selfcol.elbow(self.kin, side, self.home)[0], f"home {side}")

    def test_plan_refused_with_its_phase(self):
        arm = np.vstack([self.home] * 4 + [self.q("left", LEFT_RETRY_CRASH)] * 4)
        plan = SimpleNamespace(ok=True, side="left", arm=arm, phases=[("to_pregrasp", 0, 4), ("descend", 4, 8)])
        why = selfcol.check_plan(self.kin, plan)
        self.assertIsNotNone(why)
        self.assertIn("left elbow", why)
        self.assertIn("descend", why)
        clear = SimpleNamespace(ok=True, side="left", arm=np.vstack([self.home, self.q("left", LEFT_ORANGE_FIRST)]),
                                phases=[("descend", 0, 2)])
        self.assertIsNone(selfcol.check_plan(self.kin, clear))

    def test_patch_refuses_like_an_ik_failure(self):
        bad = SimpleNamespace(ok=True, side="right", arm=np.vstack([self.q("right", RIGHT_PURPLE)]), phases=[],
                              reason="")
        saved = selfcol._ORIG.get("plan_side")
        selfcol._ORIG["plan_side"] = lambda self_, *a, **kw: bad
        try:
            out = selfcol._plan_side(SimpleNamespace(kin=self.kin), None, "right", "right", self.home, None)
        finally:
            if saved is not None:
                selfcol._ORIG["plan_side"] = saved
        self.assertFalse(out.ok)
        self.assertIn("right elbow", out.reason)

    def test_arm_based_camera_fit_does_not_change_it(self):
        from decision_oracle.handeye import set_kin_base
        a = np.radians(6.0)
        A = np.eye(4)
        A[:3, :3] = [[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]]
        A[:3, 3] = [0.02, -0.03, 0.01]
        before = [selfcol.elbow(self.kin, s, self.q(s, v)) for s, v in (("left", LEFT_RETRY_CRASH), ("right", RIGHT_YELLOW))]
        set_kin_base(self.kin, A)
        try:
            after = [selfcol.elbow(self.kin, s, self.q(s, v)) for s, v in (("left", LEFT_RETRY_CRASH), ("right", RIGHT_YELLOW))]
        finally:
            set_kin_base(self.kin, None)
        for b, c in zip(before, after):
            self.assertEqual(b[0], c[0])
            self.assertAlmostEqual(b[1], c[1], places=6)


if __name__ == "__main__":
    unittest.main()
