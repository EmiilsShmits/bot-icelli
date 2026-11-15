"""Unit tests for decision_oracle/boxes_v16.py: the three boxes and the shape lid measured from head depth.

    python -m unittest policy/tests/test_boxes_v16.py -v        # from the repo root

Always run (need OpenCV): boxes and lid on point clouds built here from plain geometry.
Run when the files are there (all git-ignored, see eval/analysis/real_depth/README.md):
  - Aalto's real depth frames  artifacts/real_frames/drop3/depth_ep*_start.npy
  - venue-look sim frames      artifacts/monitor/sim_frames/f_*.npz
  - the lid's STL + MuJoCo     sim/task3/lid_shape_holes_200mm.stl (or a copy in artifacts/real_frames/lid/)
"""
from __future__ import annotations

import copy
import glob
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid"),
                str(ROOT / "eval" / "analysis" / "real_depth")]

from aaltonomous.scene.scene import Scene  # noqa: E402

try:
    import cv2  # noqa: F401
    from decision_oracle import boxes_v16 as B
    HAVE_CV = True
except ImportError:
    HAVE_CV = False

REAL = sorted(glob.glob(str(ROOT / "artifacts/real_frames/drop3/depth_ep*_start.npy")))
SIM = sorted(glob.glob(str(ROOT / "artifacts/monitor/sim_frames/f_*.npz")))
STL = next((q for q in (ROOT / "sim/task3/lid_shape_holes_200mm.stl", ROOT / "artifacts/real_frames/lid/lid_shape_holes_200mm.stl")
            if q.exists()), ROOT / "sim/task3/lid_shape_holes_200mm.stl")
# the lid's holes as stl_holes.py reads them from the STL (m, lip up); written out here, not taken from boxes_v16
STL_HOLES = {"cube": (-0.048, -0.035), "cylinder": (0.048, -0.035), "triangle": (0.0, 0.0393)}
CAM = np.array([0.05, 0.0, 0.50])            # camera above the table (frame x, y; height above the table)


def rot(a):
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def in_hole(kind, d):
    """d: (n, 2) offsets from the hole centre in the lid's own axes (STL outlines, corner rounding left out)."""
    if kind == "cube":
        return np.all(np.abs(d) < 0.030, axis=1)
    if kind == "cylinder":
        return np.linalg.norm(d, axis=1) < 0.030
    n = np.radians([-90.0, 30.0, 150.0])                       # outward normals of the three sides; one tip towards +b
    return np.all(d @ np.c_[np.cos(n), np.sin(n)].T < 0.02157, axis=1) & (np.linalg.norm(d, axis=1) < 0.033)


def scene_points(zc, near=0.36, yaw=0.0, mid=0.02, width=0.212, depth=0.208, gaps=(0.028, 0.026), wall=0.071,
                 lid=None, thick=0.006):
    """What a camera at CAM sees of a table with three boxes (no occlusion): points in the frame, z above the table
    + zc. lid = (box name, turn, lip_up, extra yaw, offset xy): Aalto's lid on that box."""
    R = rot(yaw)
    e1, e2 = R @ [1.0, 0.0], R @ [0.0, 1.0]
    o = np.array([near, 0.0])
    us = {"left": mid + width + gaps[0], "center": mid, "right": mid - width - gaps[1]}
    g = lambda a, b, st: np.arange(a, b + 1e-9, st)
    pts, cen = [], {}
    xx, yy = np.meshgrid(g(0.12, 0.9, 0.004), g(-0.55, 0.55, 0.004))
    tab = np.c_[xx.ravel(), yy.ravel()]
    for n, u in us.items():
        c = o + e1 * depth / 2 + e2 * u
        cen[n] = c
        d = (tab - c) @ np.c_[e1, e2]
        tab = tab[~((np.abs(d[:, 0]) < depth / 2) & (np.abs(d[:, 1]) < width / 2))]
        loc = []                                                 # (across, along, height) in the box's own axes
        for s in (-1, 1):                                        # near / far wall, then the two side walls
            a, b, z = np.meshgrid(s * (depth / 2 - g(0, thick, 0.002)), g(-width / 2, width / 2, 0.002), [wall])
            loc.append(np.c_[a.ravel(), b.ravel(), z.ravel()])
            a, b, z = np.meshgrid([s * depth / 2 if s < 0 else depth / 2 - thick], g(-width / 2, width / 2, 0.002), g(0, wall, 0.003))
            loc.append(np.c_[a.ravel(), b.ravel(), z.ravel()])
            a, b, z = np.meshgrid(g(-depth / 2, depth / 2, 0.002), s * (width / 2 - g(0, thick, 0.002)), [wall])
            loc.append(np.c_[a.ravel(), b.ravel(), z.ravel()])
        a, b = np.meshgrid(g(-depth / 2 + thick, depth / 2 - thick, 0.004), g(-width / 2 + thick, width / 2 - thick, 0.004))
        if not (lid and lid[0] == n):
            loc.append(np.c_[a.ravel(), b.ravel(), np.full(a.size, 0.003)])
        L = np.vstack(loc)
        pts.append(np.c_[c + L[:, :1] * e1 + L[:, 1:2] * e2, L[:, 2]])
    pts.append(np.c_[tab, np.zeros(len(tab))])
    truth = None
    if lid:
        n, turn, lip_up, dyaw, off = lid
        Rl = rot(yaw + np.radians(90.0 * turn + dyaw))
        c = cen[n] + np.asarray(off)
        mir = np.array([1.0, 1.0]) if lip_up else np.array([-1.0, 1.0])
        truth = {k: c + Rl @ (np.array(q) * mir) for k, q in STL_HOLES.items()}
        a, b = np.meshgrid(g(-0.1, 0.1, 0.0012), g(-0.1, 0.1, 0.0012))
        loc = np.c_[a.ravel(), b.ravel()]                        # lid axes as seen from above
        hole = np.zeros(len(loc), bool)
        for k, q in STL_HOLES.items():
            hole |= in_hole(k, (loc - np.array(q) * mir) * mir)
        top = wall + 0.004
        pts.append(np.c_[c + loc[~hole] @ Rl.T, np.full((~hole).sum(), top)])
        through = np.c_[c + loc[hole] @ Rl.T, np.full(hole.sum(), top - 0.002)]      # on the plate's mid-plane
        t = (CAM[2] - 0.003) / (CAM[2] - through[:, 2])          # the same rays, down to the box floor
        pts.append(CAM + (through - CAM) * t[:, None])
    Q = np.vstack(pts)
    Q[:, 2] += zc
    return Q, cen, truth


def to_optical(Q, zc):
    """Points for find_boxes / find_lid with the levelled pose T (axes of the frame, camera at CAM)."""
    T = np.eye(4)
    T[:3, 3] = CAM + [0.0, 0.0, zc]
    return Q - T[:3, 3], T


@unittest.skipUnless(HAVE_CV, "needs OpenCV")
class Geometry(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load()
        self.zc = self.sc.counter_z

    def test_boxes_where_they_stand_not_where_the_yaml_says(self):
        for near, yaw, mid, gaps in ((0.36, 0.0, 0.02, (0.028, 0.026)), (0.29, 4.0, -0.03, (0.02, 0.035)), (0.40, -5.0, 0.05, (0.05, 0.05))):
            Q, cen, _ = scene_points(self.zc, near=near, yaw=np.radians(yaw), mid=mid, gaps=gaps)
            P, T = to_optical(Q, self.zc)
            r = B.find_boxes(P, T, self.sc)
            self.assertTrue(r["ok"], r["why"])
            self.assertAlmostEqual(r["yaw_deg"], -yaw, delta=0.6)          # the row's line x = m*y + c turns the other way
            self.assertAlmostEqual(r["wall"], 0.071, delta=0.002)
            for g_found, g_true in zip(r["gaps"], gaps):
                self.assertAlmostEqual(g_found, g_true, delta=0.005)
            for n in ("left", "center", "right"):
                self.assertLess(np.linalg.norm(r["boxes"][n]["center"] - cen[n]), 0.005, n)
            self.assertGreater(r["boxes"]["left"]["center"][1], r["boxes"]["right"]["center"][1])

    def test_shifted_row_found_or_refused_never_mislabelled(self):
        """Real run Sun 06:55: the robot stood ~11 cm right of the row and its raised left hand hid most of the left
        box. Shifted rows, left box cut off at several widths, right side at the image edge: every box within 1 cm, or
        "not found" (scene.yaml bins); never the visible boxes taken as left + centre."""
        for mid in (0.0, 0.06, 0.11, 0.13):
            for ymax in (None, 0.30, 0.27, 0.25, 0.235):
                Q, cen, _ = scene_points(self.zc, mid=mid)
                keep = (Q[:, 1] > -0.27) & ((Q[:, 1] < ymax) if ymax is not None else True)
                r = B.find_boxes(*to_optical(Q[keep], self.zc), self.sc)
                if r["ok"]:
                    for n in ("left", "center", "right"):
                        self.assertLess(np.linalg.norm(r["boxes"][n]["center"] - cen[n]), 0.01, f"{mid} {ymax} {n}")
                if ymax is None or ymax >= 0.27:
                    self.assertTrue(r["ok"], f"mid {mid}, view to y {ymax}: {r['why']}")

    def test_as_bins_gives_centres_and_shifts(self):
        Q, cen, _ = scene_points(self.zc)
        P, T = to_optical(Q, self.zc)
        b = B.as_bins(B.find_boxes(P, T, self.sc), self.sc)
        self.assertEqual(set(b["centers"]), {"left", "center", "right"})
        nom = self.sc.mat_to_pelvis(np.r_[self.sc.cfg["bins"]["centers"]["center"], 0.0])[:2]
        np.testing.assert_allclose(np.asarray(b["centers"]["center"]) - nom, b["shift"]["center"], atol=1e-9)

    def test_no_boxes_no_result(self):
        xx, yy = np.meshgrid(np.arange(0.1, 0.9, 0.004), np.arange(-0.5, 0.5, 0.004))
        Q = np.c_[xx.ravel(), yy.ravel(), np.full(xx.size, self.zc)]
        P, T = to_optical(Q, self.zc)
        r = B.find_boxes(P, T, self.sc)
        self.assertFalse(r["ok"])
        self.assertFalse(B.find_lid(P, T, self.sc, r)["ok"])

    def test_lid_found_in_every_turn_and_either_side_up(self):
        for turn in range(4):
            for lip_up in (False, True):
                Q, _, truth = scene_points(self.zc, near=0.29, yaw=np.radians(2.0), lid=("center", turn, lip_up, 4.0, (0.003, -0.002)))
                P, T = to_optical(Q, self.zc)
                boxes = B.find_boxes(P, T, self.sc)
                self.assertTrue(boxes["ok"], boxes["why"])
                lid = B.find_lid(P, T, self.sc, boxes)
                self.assertTrue(lid["ok"], f"turn {turn} lip_up {lip_up}: {lid['why']}")
                self.assertEqual((lid["box"], lid["turn"], lid["lip_up"]), ("center", turn, lip_up))
                self.assertAlmostEqual(lid["z"], 0.075, delta=0.0015)
                for k, c in truth.items():
                    self.assertLess(np.linalg.norm(lid["holes"][k]["center"] - c), 0.003, f"{k} turn {turn} lip_up {lip_up}")

    def test_open_boxes_have_no_lid(self):
        Q, _, _ = scene_points(self.zc)
        P, T = to_optical(Q, self.zc)
        lid = B.find_lid(P, T, self.sc, B.find_boxes(P, T, self.sc))
        self.assertFalse(lid["ok"])
        self.assertIn("no lid", lid["why"])

    def test_real_lid_model_is_the_stl(self):
        m = B.real_lid()
        self.assertEqual(m["size"], 0.2)
        for k, ctr, poly in m["holes"]:                          # seen from above with the lip down: a mirrored
            np.testing.assert_allclose(ctr, np.array(STL_HOLES[k]) * [-1, 1], atol=1e-6)
            x, y = poly[:, 0], poly[:, 1]
            area = abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2 * 1e6
            self.assertAlmostEqual(area, {"cube": 3558.0, "cylinder": 2827.0, "triangle": 2208.0}[k], delta=40.0)   # 3*sqrt(3)*(r-rho)^2 + 6*sqrt(3)*(r-rho)*rho + pi*rho^2


@unittest.skipUnless(HAVE_CV and REAL, "needs the real drop-3 depth frames (eval/analysis/real_depth/extract.py)")
class RealFrames(unittest.TestCase):
    def test_boxes_on_every_real_frame_and_no_lid(self):
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle import camera as C
        sc, cal = Scene.load(), Calibration.load()
        for f in REAL:
            d = np.load(f)
            fit = getattr(C, "fit_head_pose_levelled", C.fit_head_pose)(d, cal, sc)
            r = B.find_boxes(B.points(cal, d, 2), fit.T, sc)
            self.assertTrue(r["ok"], f"{f}: {r['why']}")
            self.assertAlmostEqual(r["wall"], 0.071, delta=0.003)
            for gap in r["gaps"]:
                self.assertTrue(0.015 < gap < 0.035, gap)
            self.assertFalse(B.find_lid(B.points(cal, d, 1), fit.T, sc, r)["ok"])

    def test_hook_moves_the_bins_and_reset_puts_them_back(self):
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle import camera as C
        sc, cal = Scene.load(), Calibration.load()
        before = copy.deepcopy(sc.cfg["bins"]["centers"])
        cam = B.enable(C.CameraPerception(sc, cal))
        cam.ensure_pose(np.load(REAL[3]))
        self.assertTrue(cam.boxes["ok"])
        moved = np.asarray(sc.cfg["bins"]["centers"]["right"]) - before["right"]
        self.assertTrue(0.03 < moved[0] < 0.05, moved)           # the real boxes are 24 cm apart, scene.yaml says 26
        cam.reset()
        self.assertEqual(sc.cfg["bins"]["centers"], before)


@unittest.skipUnless(HAVE_CV and SIM, "needs the saved venue-look sim frames")
class SimFrames(unittest.TestCase):
    def test_boxes_match_the_sim_where_found(self):
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle import camera as C
        sc, cal = Scene.load(), Calibration.load()
        nom = {n: sc.mat_to_pelvis(np.r_[xy, 0.0])[:2] for n, xy in sc.cfg["bins"]["centers"].items()}
        ok = 0
        frames = SIM[::8]
        for f in frames:
            d = np.load(f)["depth"]
            fit = getattr(C, "fit_head_pose_levelled", C.fit_head_pose)(d, cal, sc)
            r = B.find_boxes(B.points(cal, d, 2), fit.T, sc)
            if r["ok"]:                                          # an arm over the boxes: not found, and it says so
                ok += 1
                for n in nom:
                    self.assertLess(np.abs(r["boxes"][n]["center"] - nom[n]).max(), 0.006, f"{f} {n}")
        self.assertGreaterEqual(ok, 0.85 * len(frames))


def _have_mujoco():
    try:
        import mujoco  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(HAVE_CV and REAL and STL.exists() and _have_mujoco(), "needs MuJoCo, the lid STL and a real frame")
class RenderedLid(unittest.TestCase):
    def test_real_lid_rendered_on_the_middle_box(self):
        import lid_render as L
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle import camera as C
        sc, cal = Scene.load(), Calibration.load()
        zc = sc.counter_z
        real = np.load(REAL[3])
        T = getattr(C, "fit_head_pose_levelled", C.fit_head_pose)(real, cal, sc).T
        fb = B.find_boxes(B.points(cal, real, 2), T, sc)
        cal = copy.deepcopy(cal)
        cal.cams["head"].K = np.array([[L.FOCAL, 0, 319.5], [0, L.FOCAL, 239.5], [0, 0, 1.0]])
        e1 = fb["frame"]["e1"]
        yaw_row = float(np.arctan2(e1[1], e1[0]))
        lo, hi = L.stl_bounds(str(STL))
        c_file = np.r_[(lo[:2] + hi[:2]) / 2, lo[2]]
        rng = np.random.default_rng(1)
        for turn, lip_up in ((0, False), (1, False), (2, True), (3, True)):
            boxes = [{"center": b["center"] - 0.07 * e1, "size": b["size"], "yaw": yaw_row} for b in fb["boxes"].values()]
            c_lid = fb["boxes"]["center"]["center"] - 0.07 * e1 + [0.003, -0.002]
            psi = yaw_row + np.radians(90.0 * turn + 3.0)
            if lip_up:
                R = L.rz(psi)
                p = np.r_[c_lid, zc + fb["wall"]] - R @ c_file
            else:
                R = L.rz(psi) @ np.diag([-1.0, 1.0, -1.0])
                p = np.r_[c_lid, zc + fb["wall"] + L.PLATE] - R @ c_file
            depth, _ = L.render(L.scene_xml(str(STL), T, zc, boxes, fb["wall"], R, p), rng)
            found = B.find_boxes(B.points(cal, depth, 2), T, sc)
            lid = B.find_lid(B.points(cal, depth, 1), T, sc, found)
            self.assertTrue(lid["ok"], lid["why"])
            self.assertEqual((lid["box"], lid["turn"], lid["lip_up"]), ("center", turn, lip_up))
            for k, q in L.STL_HOLES.items():
                c = c_lid + L.rz(psi)[:2, :2] @ (np.array(q) * ([1, 1] if lip_up else [-1, 1]))
                self.assertLess(np.linalg.norm(lid["holes"][k]["center"] - c), 0.004, f"{k} turn {turn}")


if __name__ == "__main__":
    unittest.main()
