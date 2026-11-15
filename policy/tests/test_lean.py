"""Unit tests for policy/lean.py (arm-frame mapping on the real robot). Needs Pinocchio and the G1 URDF, e.g. in the
policy image:
    docker run --rm -v $PWD/policy/lean.py:/app/policy/lean.py -v $PWD/policy/tests:/app/policy/tests -w /app/policy \
        bot-icelli/policy:v1.6 python3 -m unittest tests.test_lean -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lean  # noqa: E402

try:  # Pinocchio is in the policy image and the sim's env, not on Windows laptops
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False


def _pitch(deg, pivot=(0.0, 0.0, 0.25)):
    """4x4: rotation about the pelvis y axis through `pivot` (a forward lean of the upper body is a positive pitch)."""
    a = np.radians(deg)
    R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(pivot) - R @ np.asarray(pivot)
    return T


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (policy image or the sim machine)")
class TestLean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.sim.oracle import ORACLE_OVERRIDES
        cls.cfg = load_config(None, dict(ORACLE_OVERRIDES))
        cls.kin = ArmKinematics(cls.cfg)
        cls.home = home_arm(cls.cfg)
        lean.install()

    def setUp(self):
        import os
        os.environ["LEAN_MAP"] = "auto"                 # the default is off since Sun 15 Nov; test the mapping itself

    def tearDown(self):
        import os
        os.environ.pop("LEAN_MAP", None)
        lean.off()

    def targets(self, side):
        s = 1.0 if side == "left" else -1.0
        return [np.array([x, s * y, z]) for x, y, z in ((0.30, 0.10, 0.05), (0.26, 0.02, 0.04), (0.36, 0.15, 0.12))]

    def test_off_is_a_passthrough(self):
        lean.set_fit(np.eye(4), np.eye(4), 0.0)
        self.assertFalse(lean.active())
        for side in ("left", "right"):
            t = self.targets(side)[0]
            q1 = self.kin.solve(side, t, self.home)[0]
            q2 = lean._ORIG["solve"](self.kin, side, t, self.home)[0]
            np.testing.assert_allclose(q1, q2)
            np.testing.assert_allclose(self.kin.grasp_pose(side, q1)[0], lean._ORIG["grasp_pose"](self.kin, side, q1)[0])

    def test_small_tilt_stays_off_in_auto(self):
        lean.set_fit(np.eye(4), np.linalg.inv(_pitch(2.0)), 2.0)
        self.assertFalse(lean.active())

    def test_mapped_targets_and_fk_back(self):
        M = _pitch(8.0) @ np.r_[np.c_[np.eye(3), [0.01, -0.005, 0.0]], [[0, 0, 0, 1]]]
        lean.set_fit(np.eye(4), np.linalg.inv(M), 9.0)          # T0 @ inv(T_fit) = M
        self.assertTrue(lean.active())
        np.testing.assert_allclose(lean._S["M"], M, atol=1e-12)
        tol = float(self.cfg["ik"]["pos_tol"]) + 1e-4
        for side in ("left", "right"):
            for t in self.targets(side):
                q, ok, err, tilt = self.kin.solve(side, t, self.home)
                self.assertTrue(ok, f"{side} {t}: IK failed (err {err:.4f}, tilt {np.degrees(tilt):.1f})")
                raw, axis = lean._ORIG["grasp_pose"](self.kin, side, q)
                want = M[:3, :3] @ t + M[:3, 3] - lean.OFFSETS[side]
                self.assertLess(np.linalg.norm(raw - want), tol, f"{side} {t}: arm-frame grasp point off")
                p_fit, a_fit = self.kin.grasp_pose(side, q)
                self.assertLess(np.linalg.norm(p_fit - t), tol, f"{side} {t}: fitted-frame FK off")
                # palm square to the table: approach axis near the table's down in the fitted frame
                ang = np.degrees(np.arccos(np.clip(a_fit @ np.array([0, 0, -1.0]), -1, 1)))
                self.assertLess(ang, float(self.cfg["ik"]["max_tilt_deg"]) + 1)
                pts = self.kin.hand_points(side, q, np.zeros(14))
                raw_pts = lean._ORIG["hand_points"](self.kin, side, q, np.zeros(14))
                np.testing.assert_allclose(pts, lean.from_arm(raw_pts, side), atol=1e-12)

    def test_env_off(self):
        import os
        os.environ["LEAN_MAP"] = "off"
        lean.set_fit(np.eye(4), np.linalg.inv(_pitch(10.0)), 10.0)
        self.assertFalse(lean.active())

    def test_default_is_off(self):
        import os
        os.environ.pop("LEAN_MAP", None)
        lean.set_fit(np.eye(4), np.linalg.inv(_pitch(10.0)), 10.0)
        self.assertFalse(lean.active())


if __name__ == "__main__":
    unittest.main()
