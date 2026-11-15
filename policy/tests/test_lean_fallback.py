"""Sun 15 Nov 06:15: the real robot leans ~15-21 deg. Tests for what changed after the 05:30 robot test:
lean.set_fit(mode=...) (V16_CALIB=lean falls back to lean.py when its arm fit can't be used), gravity feed-forward
turned with the measured lean (gravity_ff.set_down), and the wider plausibility limits of the arm-based correction.
Needs Pinocchio + the G1 URDF (policy image):
    docker run --rm -v $PWD/policy:/app/policy -w /app/policy bot-icelli/policy:final-v16 \
        python3 -m unittest tests.test_lean_fallback -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lean  # noqa: E402


def _pitch(deg):
    a = np.radians(deg)
    T = np.eye(4)
    T[:3, :3] = [[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]]
    return T


class TestLeanMode(unittest.TestCase):
    def tearDown(self):
        lean.off()

    def test_mode_argument_overrides_env(self):
        os.environ["LEAN_MAP"] = "off"
        try:
            self.assertTrue(lean.set_fit(np.eye(4), np.linalg.inv(_pitch(20.0)), 20.0, mode="auto"))
            self.assertFalse(lean.set_fit(np.eye(4), np.linalg.inv(_pitch(20.0)), 20.0, mode="off"))
            self.assertFalse(lean.set_fit(np.eye(4), np.linalg.inv(_pitch(20.0)), 20.0))      # env: off
            self.assertFalse(lean.set_fit(np.eye(4), np.linalg.inv(_pitch(2.0)), 2.0, mode="auto"))   # < 5 deg
        finally:
            os.environ.pop("LEAN_MAP")


class TestGravityLean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gravity_ff
        from aaltonomous.deploy import policy_server as ps
        cls.gff, cls.ps = gravity_ff, ps
        cls.g = gravity_ff.install()
        if cls.g is None:
            raise unittest.SkipTest("gravity feed-forward not installed (no Pinocchio / URDF)")

    def tearDown(self):
        self.gff.set_down(None)

    def test_set_down_turns_gravity_and_resets(self):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        q = np.asarray(home_arm(load_config(None)), float)
        q[1] = 0.0                                          # something with a lever arm
        t0 = self.g.torque(q)
        a = np.radians(20.0)
        self.gff.set_down(np.array([np.sin(a), 0.0, -np.cos(a)]))
        np.testing.assert_allclose(np.asarray(self.g.model.gravity.linear), 9.81 * np.array([np.sin(a), 0, -np.cos(a)]))
        t1 = self.g.torque(q)
        self.assertGreater(np.abs(t1 - t0).max(), 0.05)    # the torque changes with the lean
        self.gff.set_down(None)
        np.testing.assert_allclose(np.asarray(self.g.model.gravity.linear), [0.0, 0.0, -9.81], atol=1e-9)
        np.testing.assert_allclose(self.g.torque(q), t0, atol=1e-9)

    def test_implausible_lean_is_ignored(self):
        self.gff.set_down(np.array([1.0, 0.0, -0.2]))      # ~79 deg: not believed
        np.testing.assert_allclose(np.asarray(self.g.model.gravity.linear), [0.0, 0.0, -9.81], atol=1e-9)

    def test_lean_set_fit_turns_gravity(self):
        lean.set_fit(np.eye(4), np.linalg.inv(_pitch(15.0)), 15.0, mode="on")
        d = np.asarray(self.g.model.gravity.linear) / 9.81
        self.assertAlmostEqual(float(np.degrees(np.arccos(-d[2]))), 15.0, places=4)
        lean.off()


class TestLimits(unittest.TestCase):
    def test_wider_limits_by_default(self):
        from decision_oracle import camera
        self.assertGreaterEqual(camera.LEAN_MAX_DEG, 30.0)
        self.assertGreaterEqual(camera.LEAN_MAX_MOVE_M, 0.30)



class TestArmErr(unittest.TestCase):
    """ARM_ERR: a measured per-arm landing error, corrected on every IK target (no mapping needed)."""

    @classmethod
    def setUpClass(cls):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.sim.oracle import ORACLE_OVERRIDES
        cls.cfg = load_config(None, dict(ORACLE_OVERRIDES))
        cls.kin = ArmKinematics(cls.cfg)
        cls.home = home_arm(cls.cfg)
        lean.install()

    def tearDown(self):
        lean.ERR.update({"left": np.zeros(3), "right": np.zeros(3)})
        lean.off()

    def test_parse(self):
        e = lean._parse_err("right=0,-0.02,0.03; left=0.01")
        np.testing.assert_allclose(e["right"], [0, -0.02, 0.03])
        np.testing.assert_allclose(e["left"], [0.01, 0, 0])

    def test_targets_move_by_minus_the_error_and_fk_maps_back(self):
        e = np.array([-0.03, -0.02, 0.01])                 # lands 3 cm short, 2 cm right, 1 cm high
        lean.ERR["right"] = e.copy()
        t = np.array([0.30, -0.10, 0.05])
        q, ok, err, tilt = self.kin.solve("right", t, self.home)
        self.assertTrue(ok)
        raw = lean._ORIG["grasp_pose"](self.kin, "right", q)[0]
        self.assertLess(np.linalg.norm(raw - (t - e)), float(self.cfg["ik"]["pos_tol"]) + 1e-4)
        self.assertLess(np.linalg.norm(self.kin.grasp_pose("right", q)[0] - t), float(self.cfg["ik"]["pos_tol"]) + 1e-4)
        q2 = self.kin.solve("left", np.array([0.30, 0.10, 0.05]), self.home)[0]   # the other arm: unchanged
        q3 = lean._ORIG["solve"](self.kin, "left", np.array([0.30, 0.10, 0.05]), self.home)[0]
        np.testing.assert_allclose(q2, q3)


if __name__ == "__main__":
    unittest.main()
