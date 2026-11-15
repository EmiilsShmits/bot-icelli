"""policy/gravity_ff.py: arm_tau_ff on every action (needs Pinocchio + the G1 URDF: run in the policy image).

    PYTHONPATH=/app:/app/policy python3 -m unittest policy/tests/test_gravity_ff.py -v
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gravity_ff  # noqa: E402


class TestGravityFF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = gravity_ff.GravityFF()
        sh = [i for i, n in enumerate(cls.g.names) if "shoulder_pitch" in n]
        cls.sh = sh                                            # left, right shoulder pitch
        cls.wrist = [i for i, n in enumerate(cls.g.names) if "wrist" in n]

    def test_order_matches_aalto(self):
        from aaltonomous.interface.safety import JointSpec
        self.assertEqual(self.g.names, list(JointSpec().arm_names))
        self.assertEqual(len(self.g.names), 14)

    def test_outstretched_arm(self):
        """The left arm held straight out in front at shoulder height (found by forward kinematics, so no sign
        conventions are assumed): Aalto measured ~10 Nm needed at the shoulder for ~0.5 m reach."""
        pin, m = self.g.pin, self.g.model
        d = m.createData()
        sp = self.sh[0]
        el = next(i for i, n in enumerate(self.g.names) if n.startswith("left_elbow"))
        j_sh = m.getJointId(self.g.names[sp])
        palm = m.getFrameId("left_hand_palm_link")
        best = None
        for a in np.linspace(-2.5, 2.5, 51):
            for b in np.linspace(-1.5, 2.5, 41):
                arm = np.zeros(14)
                arm[sp], arm[el] = a, b
                q = self.g.q0.copy()
                q[self.g.arm_iq] = arm
                pin.forwardKinematics(m, d, q)
                pin.updateFramePlacements(m, d)
                s, p = d.oMi[j_sh].translation, d.oMf[palm].translation
                if abs(p[2] - s[2]) < 0.04 and (best is None or p[0] - s[0] > best[0]):
                    best = (float(p[0] - s[0]), arm.copy(), q.copy())
        reach, arm, q = best
        raw = pin.computeGeneralizedGravity(m, d, q)[self.g.arm_iv]
        clamped = self.g.torque(arm)
        print(f"\nreach {reach:.2f} m: shoulder pitch {raw[sp]:+.1f} Nm (sent {clamped[sp]:+.1f}), "
              f"elbow {raw[el]:+.1f} Nm; zero pose shoulder {self.g.torque(np.zeros(14))[sp]:+.1f} Nm")
        self.assertGreater(reach, 0.3)
        self.assertTrue(5.0 < abs(raw[sp]) < 20.0)
        self.assertAlmostEqual(clamped[sp], float(np.clip(raw[sp], -15, 15)), places=6)

    def test_bounds(self):
        rng = np.random.default_rng(0)
        for _ in range(200):
            t = self.g.torque(rng.uniform(-1.5, 1.5, 14))
            self.assertTrue(np.all(np.abs(t) <= self.g.limit + 1e-9))
            self.assertTrue(np.all(np.abs(t[self.wrist]) <= 2.5 + 1e-9))
            self.assertTrue(np.all(np.isfinite(t)))

    def test_shapes(self):
        one = {"arm_q_target": np.zeros(14), "hand_q_target": np.zeros(14)}
        self.assertEqual(self.g.for_action(one).shape, (14,))
        chunk = {"arm_q_target": np.zeros((10, 14)), "hand_q_target": np.zeros(14)}
        self.assertEqual(self.g.for_action(chunk).shape, (10, 14))
        both = {"arm_q_target": np.zeros((5, 14)), "hand_q_target": np.zeros((5, 14))}
        self.assertEqual(self.g.for_action(both).shape, (5, 14))
        lists = {"arm_q_target": [[0.0] * 14] * 3, "hand_q_target": [0.0] * 14}
        self.assertEqual(self.g.for_action(lists).shape, (3, 14))

    def test_install_wraps_handle(self):
        from aaltonomous.deploy import policy_server as ps
        orig = ps.handle
        try:
            os.environ["GRAVITY_FF"] = "on"
            g = gravity_ff.install()
            self.assertIsNotNone(g)
            self.assertIs(gravity_ff.install(), g)            # idempotent
            pol = ps.HoldPolicy()
            ps.handle(pol, {"type": "reset", "instruction": ""})
            out = ps.handle(pol, {"type": "act", "obs": {"arm_q": np.zeros(14), "hand_q": np.zeros(14)}})
            self.assertEqual(out["type"], "action")
            self.assertEqual(np.asarray(out["action"]["arm_tau_ff"]).shape, (14,))
            self.assertEqual(ps.handle(pol, {"type": "reset"})["type"], "reset_ok")
            bad = ps.handle(pol, {"type": "act", "obs": {"arm_q": np.zeros(14), "hand_q": np.zeros(14)}})
            self.assertIn("arm_tau_ff", bad["action"])
        finally:
            ps.handle = orig
            os.environ.pop("GRAVITY_FF", None)

    def test_off(self):
        from aaltonomous.deploy import policy_server as ps
        orig = ps.handle
        try:
            os.environ["GRAVITY_FF"] = "off"
            self.assertIsNone(gravity_ff.install())
            self.assertIs(ps.handle, orig)
        finally:
            ps.handle = orig
            os.environ.pop("GRAVITY_FF", None)

    def test_broken_action_passes_through(self):
        """A malformed arm_q_target: the action goes out unchanged (the runner judges it), no exception."""
        from aaltonomous.deploy import policy_server as ps
        orig = ps.handle
        try:
            os.environ["GRAVITY_FF"] = "on"
            gravity_ff.install()

            class Bad(ps.Policy):
                def act(self, obs):
                    return {"arm_q_target": np.zeros(13), "hand_q_target": np.zeros(14)}

            out = ps.handle(Bad(), {"type": "act", "obs": {}})
            self.assertNotIn("arm_tau_ff", out["action"])
        finally:
            ps.handle = orig
            os.environ.pop("GRAVITY_FF", None)


if __name__ == "__main__":
    unittest.main()
