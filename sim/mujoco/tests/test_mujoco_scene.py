"""Checks of the MuJoCo venue scene (sim/mujoco/build.py, backend.py). Needs `bash sim/mujoco/get_assets.sh` and
`pip install -r sim/mujoco/requirements.txt`.

    PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python -m unittest sim/mujoco/tests/test_mujoco_scene.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "sim" / "mujoco"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

try:
    import mujoco
    HAVE = (ROOT / "artifacts" / "mujoco" / "g1" / "g1_body29_hand14.xml").exists()
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "needs mujoco + sim/mujoco/get_assets.sh")
class TestScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build as B
        from backend import MujocoBackend
        cls.B = B
        cls.be = MujocoBackend()
        cls.cfg = cls.be.cfg

    @classmethod
    def tearDownClass(cls):
        cls.be.close()

    def test_joint_order_matches_aalto_spec(self):
        spec = yaml.safe_load(open(ROOT / "third_party/aaltonomous-humanoid/aaltonomous/interface/joint_spec.yaml"))
        names = [j["name"] for j in spec["arm"]] + [j["name"] for j in spec["hand"]]
        self.assertEqual(names, self.B.ARM + self.B.HAND)

    def test_head_camera_pose(self):
        m, d = self.be.model, self.be.data
        mujoco.mj_forward(m, d)
        cam = self.be.cam
        p_pelvis = d.cam_xpos[cam] - self.be.pelvis_w
        T = self.B.head_T_pelvis_optical(self.cfg)
        self.assertLess(np.abs(p_pelvis - T[:3, 3]).max(), 1e-4)
        table_z = self.cfg["table"]["height"] - self.cfg["robot"]["pelvis_height"]
        self.assertAlmostEqual(p_pelvis[2] - table_z, self.cfg["camera"]["above_table"], places=4)
        R_opt = d.cam_xmat[cam].reshape(3, 3) @ np.diag([1.0, -1.0, -1.0])
        self.assertLess(np.abs(R_opt - T[:3, :3]).max(), 1e-4)
        # without the venue turn it is Aalto's calibration.yaml direction (URDF d435_link)
        cal = np.asarray(yaml.safe_load(open(ROOT / "third_party/aaltonomous-humanoid/aaltonomous/interface/"
                                              "calibration.yaml"))["cameras"]["head"]["T_pelvis_optical"], float)
        c0 = dict(self.cfg["camera"], pitch_down_deg=0, roll_deg=0, yaw_deg=0, shift_y=0)
        T0 = self.B.head_T_pelvis_optical(dict(self.cfg, camera=c0))
        self.assertLess(np.abs(T0[:3, :3] - cal[:3, :3]).max(), 1e-6)

    def test_depth_of_the_table(self):
        """Deproject the head depth with Aalto's intrinsics: table pixels must sit on the table plane (+-3 mm)."""
        from aaltonomous.interface import tasks
        self.be.reset_scene([])
        im = self.be.images()
        dep = im["head_depth"].astype(float) / 1000.0
        T = self.B.head_T_pelvis_optical(self.cfg)
        c = self.cfg["camera"]
        fy = c["fy"]
        v, u = np.mgrid[300:470:10, 200:440:10]                 # lower middle of the image: table only
        z = dep[v, u]
        pts = np.stack([(u - c["cx"]) * z / c["fx"], (v - c["cy"]) * z / fy, z], -1).reshape(-1, 3)
        p = pts @ T[:3, :3].T + T[:3, 3]
        table_z = self.cfg["table"]["height"] - self.cfg["robot"]["pelvis_height"]
        err = p[:, 2] - table_z
        self.assertLess(np.abs(np.median(err)), 0.0015, f"median {np.median(err) * 1000:.1f} mm")
        self.assertLess(np.percentile(np.abs(err), 95), 0.004, f"p95 {np.percentile(np.abs(err), 95) * 1000:.1f} mm")

    def test_cube_position_from_head_depth(self):
        """A cube's top face, deprojected with Aalto's K and the camera pose, lands within 3 mm of the cube."""
        be, c = self.be, self.cfg["camera"]
        be.reset_scene([{"color": "red", "shape": "cube", "x": 0.45, "y": 0.20, "yaw": 0.0}])
        be.settle(0.5)
        dep = be.images()["head_depth"].astype(float) / 1000.0
        T = self.B.head_T_pelvis_optical(self.cfg)
        v, u = np.mgrid[0:480, 0:640]
        Q = np.stack([(u - c["cx"]) * dep / c["fx"], (v - c["cy"]) * dep / c["fy"], dep], -1) @ T[:3, :3].T + T[:3, 3]
        truth = np.asarray([o for o in be.state() if o["active"]][0]["pos"])
        top = Q[(Q[..., 2] > truth[2] + 0.02) & (Q[..., 2] < truth[2] + 0.03)
                & (np.abs(Q[..., 0] - truth[0]) < 0.05) & (np.abs(Q[..., 1] - truth[1]) < 0.05)]
        self.assertGreater(len(top), 50)
        self.assertLess(np.abs(top[:, :2].mean(0) - truth[:2]).max(), 0.003)

    def test_arm_tracks_a_1rad_per_s_move(self):
        from aaltonomous.sim.aalto_task import layout as LAY
        be = self.be
        be.reset_scene([])
        home = np.array([LAY.ARM_HOME[n] for n in self.B.ARM])
        err = []
        for k in range(30):                                   # 1 s at 30 Hz, shoulder pitch -1 rad at 1 rad/s
            tgt = home.copy()
            tgt[0] -= (k + 1) / 30.0
            tgt[7] -= (k + 1) / 30.0
            be.command(tgt, np.zeros(14))
            be.advance(1 / 30)
            err.append(np.abs(be.joints()[0] - tgt).max())
        be.settle(0.5)
        self.assertLess(np.abs(be.joints()[0] - tgt).max(), 0.02)   # settled
        self.assertLess(max(err), 0.15)                       # lag while moving

    def test_object_in_bin_scores_correct(self):
        from aaltonomous.sim.aalto_task import layout as LAY
        be = self.be
        cx, cy = be.sc.cfg["bins"]["centers"]["left"]
        be.reset_scene([{"color": "red", "shape": "cube", "x": cx, "y": cy, "yaw": 0.0, "z": 0.2}])
        be.settle(2.0)
        ev = LAY.evaluate(be.sc, "sort_fixed", be.state(), None)
        self.assertEqual([o["outcome"] for o in ev["outcomes"]], ["correct"])


if __name__ == "__main__":
    unittest.main()
