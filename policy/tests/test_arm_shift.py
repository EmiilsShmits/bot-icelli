"""V16_ARM_SHIFT: after the two-arm camera fit, each arm is measured against its own model (handeye.arm_shifts) and
its IK targets are corrected by that for the episode (camera.fit_head_pose per_arm -> lean.set_fit_err).

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python -m unittest policy.tests.test_arm_shift -v
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

import lean  # noqa: E402

try:
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False

RIGHT = np.array([-0.009, -0.014, -0.007])      # the right hand on Aalto's real frames (real minus model, m)


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF")
class TestArmShifts(unittest.TestCase):
    """handeye.arm_shifts on a synthetic cloud: the model's own camera-facing surface, the right arm moved by RIGHT."""

    @classmethod
    def setUpClass(cls):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle import camera as C
        from decision_oracle.handeye import HandEye
        cls.he = HandEye()
        cls.T = np.asarray(Calibration.load()._T(C.CAM), float)
        cls.arm_q, cls.hand_q = np.asarray(home_arm(load_config(None)), float), np.zeros(14)

    def cloud(self, shift_right):
        M, N = self.he.cloud(self.arm_q, self.hand_q)
        vis = np.einsum("ij,ij->i", N, self.T[:3, 3] - M) > 0
        right = np.array([self.he.names[i].startswith("right") for i in self.he.link])
        P = M + np.where(right[:, None], shift_right, 0.0)
        P = P[vis][::3]
        Ti = np.linalg.inv(self.T)
        return P @ Ti[:3, :3].T + Ti[:3, 3]             # optical frame

    def test_finds_the_right_arms_shift_and_leaves_the_left(self):
        r = self.he.arm_shifts(self.cloud(RIGHT), self.T, self.arm_q, self.hand_q)
        self.assertIsNotNone(r["right"]["d"], r["right"])
        self.assertLess(np.linalg.norm(r["right"]["d"] - RIGHT), 0.003, r["right"])
        self.assertIsNone(r["left"]["d"])                # within the deadband: no correction
        self.assertIn("within", r["left"]["why"])

    def test_no_shift_in_a_sim(self):
        r = self.he.arm_shifts(self.cloud(np.zeros(3)), self.T, self.arm_q, self.hand_q)
        self.assertIsNone(r["left"]["d"])
        self.assertIsNone(r["right"]["d"])

    def test_refuses_what_it_cannot_trust(self):
        r = self.he.arm_shifts(self.cloud(np.array([0.0, -0.10, 0.0])), self.T, self.arm_q, self.hand_q)
        self.assertIsNone(r["right"]["d"])               # 10 cm: not the hand it is looking for
        r = self.he.arm_shifts(np.zeros((0, 3)), self.T, self.arm_q, self.hand_q)
        self.assertIsNone(r["left"]["d"])


class TestFitCarriesIt(unittest.TestCase):
    """camera.fit_head_pose(per_arm=True) turns the shifts into the table frame; CameraPerception hands them to lean."""

    def setUp(self):
        from aaltonomous.interface.calibration import Calibration
        from aaltonomous.scene.scene import Scene
        from decision_oracle import camera as C
        from decision_oracle.handeye import _rodrigues
        self.C, self.cal, self.scene = C, Calibration.load(), Scene.load()
        self.T = np.asarray(self.cal._T(C.CAM), float)
        self.depth = np.zeros((480, 640), np.uint16)
        lev = C.fit_head_pose_levelled
        C.fit_head_pose_levelled = lambda *a, **k: C.PoseFit(self.T.copy(), True)
        self.addCleanup(lambda: setattr(C, "fit_head_pose_levelled", lev))
        self.addCleanup(lambda: lean.set_fit_err(None))
        self.A = np.eye(4)
        self.A[:3, :3] = _rodrigues(np.radians([0.0, 15.0, 0.0]))        # the robot leans 15 deg
        arm_T = np.linalg.inv(self.A) @ self.T
        self.he = types.SimpleNamespace(
            fit_pose=lambda *a, **k: {"ok": True, "T": arm_T, "why": ""},
            arm_shifts=lambda *a, **k: {"left": {"d": None, "n": 900, "why": "within 3 mm"},
                                        "right": {"d": RIGHT.copy(), "n": 600, "why": ""}})

    def test_fit_gives_table_frame_shifts(self):
        z = np.zeros(14)
        f = self.C.fit_head_pose(self.depth, self.cal, self.scene, lean=(self.he, z, z), per_arm=True)
        np.testing.assert_allclose(f.arm_shift["right"], self.A[:3, :3] @ RIGHT)
        np.testing.assert_allclose(f.arm_shift["left"], 0.0)
        self.assertIn("hand_off_cm", f.arm_pose)
        f = self.C.fit_head_pose(self.depth, self.cal, self.scene, lean=(self.he, z, z))
        self.assertIsNone(f.arm_shift)                   # off: as before

    def test_camera_sets_and_clears_the_correction(self):
        cam = self.C.CameraPerception(self.scene, self.cal)
        cam.lean, cam.arm_shift = self.he, True
        cam._joints = (np.zeros(14), np.zeros(14))
        cam.ensure_pose(self.depth)
        np.testing.assert_allclose(lean.FIT_ERR["right"], self.A[:3, :3] @ RIGHT)
        np.testing.assert_allclose(lean.ERR["right"], lean.ARM_ERR["right"] + lean.FIT_ERR["right"])
        cam.reset()                                      # next episode: measured again, nothing carried over
        np.testing.assert_allclose(lean.FIT_ERR["right"], 0.0)

    def test_off_by_default(self):
        cam = self.C.CameraPerception(self.scene, self.cal)
        cam.lean = self.he
        cam._joints = (np.zeros(14), np.zeros(14))
        cam.ensure_pose(self.depth)
        self.assertIsNone(cam.fit.arm_shift)
        np.testing.assert_allclose(lean.FIT_ERR["right"], 0.0)


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF")
class TestTargetsMove(unittest.TestCase):
    """With a measured shift the model is sent to target - shift, and the planners' FK reports the real hand."""

    def test_solve_and_fk(self):
        from aaltonomous.baselines.classical.config import home_arm, load_config
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.sim.oracle import ORACLE_OVERRIDES
        cfg = load_config(None, dict(ORACLE_OVERRIDES))
        kin, home = ArmKinematics(cfg), home_arm(cfg)
        lean.install()
        self.addCleanup(lambda: lean.set_fit_err(None))
        t = np.array([0.30, -0.10, 0.05])
        lean.set_fit_err({"right": RIGHT, "left": np.zeros(3)})
        q, ok = kin.solve("right", t, home)[:2]
        self.assertTrue(ok)
        tol = float(cfg["ik"]["pos_tol"]) + 1e-4
        raw = lean._ORIG["grasp_pose"](kin, "right", q)[0]
        self.assertLess(np.linalg.norm(raw - (t - RIGHT)), tol)          # the model goes to target - shift
        self.assertLess(np.linalg.norm(kin.grasp_pose("right", q)[0] - t), tol)   # so the real hand is on the target
        q_left = kin.solve("left", t * [1, -1, 1], home)[0]
        np.testing.assert_allclose(q_left, lean._ORIG["solve"](kin, "left", t * [1, -1, 1], home)[0])


class TestSwitch(unittest.TestCase):
    def build(self, **env):
        import server
        e = {"GEMINI_API_KEY": "", "DECISION_KEY_FILE": "/nonexistent", "V16_LABELS": "off", "V16_INSTRUCTION": "rules"}
        with mock.patch.dict(os.environ, {**e, **env}):
            return server.POLICIES["v1.6"]()

    def test_env(self):
        self.assertFalse(self.build().pol.cam.arm_shift)
        self.assertTrue(self.build(V16_ARM_SHIFT="on").pol.cam.arm_shift)
        self.assertFalse(self.build(V16_ARM_SHIFT="on", V16_CALIB="bins").pol.cam.arm_shift)


if __name__ == "__main__":
    unittest.main()
