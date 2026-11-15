"""Where is the real Dex3 hand in Aalto's head-camera footage, compared with where the joint angles put it?

Tests three explanations of the 4-6 cm hand offset seen in Aalto's real datasets (Hugging Face zupermiez/g1_pick_cube
and zupermiez/g1_junction_drop_2: LeRobot v3.0, 30 Hz, 28 joint angles + head camera `cam_high`, no head depth):
  1. the head camera is tilted on its mount (the ~8-12 deg found by fitting the bins in the image);
  2. the whole torso leans (camera and arms rotate together, so the hands stay where calibration.yaml projects them);
  3. calibration camera plus a constant per-arm offset in xyz (pelvis frame).

Method: frames where an arm is still (no camera/joint sync error) and its hand is in view; the hand is modelled as
spheres on Aalto's kinematics (the URDF, the same hand points as ArmKinematics.hand_points); its silhouette is slid
over the image's dark-navy hand pixels to find where the real hand is (a 2-D shift per frame and hand); then each
model's parameters are fitted to all those shifts (robust least squares on the 8 hand points' pixels).

    python -I eval/analysis/hand_offset.py                      # all steps; writes artifacts/analysis/hand_offset/
    python -I eval/analysis/hand_offset.py --fit-only           # refit from the saved registrations (frames.csv)
    PYTHONPATH=third_party/aaltonomous-humanoid python eval/analysis/hand_offset.py --validate-fk
                                                                # where Pinocchio is installed: own FK vs Aalto's

Result (Sun 15 Nov, drops 1-3): the hands match calibration.yaml's camera within ~2.2 deg; the 8-15 deg the scene
shows (bins in drops 1-2, our policies' fit_head_pose on drop 3's real depth) is the robot leaning relative to the
table. Details, per-arm offsets and what the policies should do: docs/research/hand-offset-real-data.md.

Needs numpy, opencv-python, pyarrow, pandas, av (PyAV, for the AV1 and HEVC videos), scipy, pyyaml, matplotlib. No
Pinocchio: the kinematics here are a numpy port, identical to Aalto's ArmKinematics on 1,200 recorded poses. Data: the
datasets in artifacts/drops/<name>/ (data/, meta/, videos/observation.images.cam_high/ and, for drop 3,
videos/observation.images.head_depth/); a dataset without its cam_high video is skipped.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
# eval/analysis/numbers.py shadows the standard library's `numbers` (numpy imports it): never import from this folder
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != HERE]

import numpy as np  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "../.."))
AALTO = os.path.join(REPO, "third_party/aaltonomous-humanoid")
URDF = os.path.join(AALTO, "third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf")
CALIB = os.path.join(AALTO, "aaltonomous/interface/calibration.yaml")
DATASETS = ("g1_pick_cube", "g1_junction_drop_2", "g1_junction_drop_3")   # drop 3 (Sun 00:07) has head depth
DROP_NAME = {"g1_pick_cube": "drop 1", "g1_junction_drop_2": "drop 2", "g1_junction_drop_3": "drop 3"}
DEPTH_KEY = "observation.images.head_depth"
CAM_KEY = "observation.images.cam_high"

ARM = ["shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch", "wrist_yaw"]
ARM_NAMES = [f"left_{j}_joint" for j in ARM] + [f"right_{j}_joint" for j in ARM]
# observation.state order (= Aalto's joint_spec.yaml): left hand thumb0,1,2, middle0,1, index0,1; right hand
# thumb0,1,2, index0,1, middle0,1
HAND_NAMES = [f"left_hand_{j}_joint" for j in ("thumb_0", "thumb_1", "thumb_2", "middle_0", "middle_1", "index_0",
                                                "index_1")] + \
             [f"right_hand_{j}_joint" for j in ("thumb_0", "thumb_1", "thumb_2", "index_0", "index_1", "middle_0",
                                                 "middle_1")]
SIDES = ("left", "right")
# Aalto's ArmKinematics (baselines/classical/kinematics.py + config.yaml grasp.point_in_palm, right mirrored in y)
FINGER_LINKS = ("hand_index_1_link", "hand_middle_1_link", "hand_thumb_2_link")
TIP = {"left": ([0.052, 0, 0], [0.052, 0, 0], [0, -0.052, 0]), "right": ([0.052, 0, 0], [0.052, 0, 0], [0, 0.052, 0])}
GRASP = {"left": np.array([0.099, -0.084, 0.015]), "right": np.array([0.099, 0.084, 0.015])}

# The head camera pose that fits the middle bin's corners in frame 0 of each dataset (sim/venue_look/README.md,
# fit_head_camera.py): pitch = further down (deg), roll (deg), camera moved to the robot's left (m)
SCENE_FIT = {"g1_pick_cube": dict(pitch=7.9, roll=1.0, dy=0.047), "g1_junction_drop_2": dict(pitch=12.2, roll=1.1, dy=0.007)}


# ---------------------------------------------------------------------------------------------- kinematics
def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _axis_angle(axis, q):
    """Batched rotation matrices (N, 3, 3) about a unit axis by angles q (N,)."""
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    q = np.asarray(q, float)[:, None, None]
    return np.eye(3) + np.sin(q) * K + (1 - np.cos(q)) * (K @ K)


class G1FK:
    """Forward kinematics of the G1 URDF with the pelvis as fixed base and the waist at 0, batched over frames.
    Same model as Aalto's ArmKinematics (Pinocchio on the same URDF); `--validate-fk` compares the two."""

    def __init__(self, urdf=URDF):
        root = ET.parse(urdf).getroot()
        self.joint = {}                                    # child link -> (name, type, parent, T_origin, axis)
        for j in root.findall("joint"):
            o = j.find("origin")
            xyz = np.array([float(v) for v in (o.get("xyz", "0 0 0") if o is not None else "0 0 0").split()])
            rpy = np.array([float(v) for v in (o.get("rpy", "0 0 0") if o is not None else "0 0 0").split()])
            T = np.eye(4)
            T[:3, :3], T[:3, 3] = _rpy(*rpy), xyz
            ax = j.find("axis")
            axis = np.array([float(v) for v in ax.get("xyz").split()]) if ax is not None else None
            self.joint[j.find("child").get("link")] = (j.get("name"), j.get("type"), j.find("parent").get("link"),
                                                       T, axis)

    def poses(self, links, q, offsets=None):
        """{link: (N, 4, 4) pose in the pelvis frame} for joint values q = {joint name: (N,)} (missing joints = 0).
        offsets: {joint name: constant added to that joint} (joint-offset models)."""
        n = len(next(iter(q.values())))
        cache = {"pelvis": np.broadcast_to(np.eye(4), (n, 4, 4))}

        def get(link):
            if link in cache:
                return cache[link]
            name, typ, parent, T0, axis = self.joint[link]
            T = get(parent) @ T0
            if typ in ("revolute", "continuous"):
                qa = np.asarray(q.get(name, np.zeros(n)), float) + (offsets or {}).get(name, 0.0)
                Rj = np.broadcast_to(np.eye(4), (n, 4, 4)).copy()
                Rj[:, :3, :3] = _axis_angle(axis, qa)
                T = T @ Rj
            cache[link] = T
            return T

        return {l: get(l) for l in links}


def qdict(arm_q, hand_q):
    arm_q, hand_q = np.atleast_2d(arm_q), np.atleast_2d(hand_q)
    d = {n: arm_q[:, i] for i, n in enumerate(ARM_NAMES)}
    d.update({n: hand_q[:, i] for i, n in enumerate(HAND_NAMES)})
    return d


def hand_points(fk, side, arm_q, hand_q, offsets=None):
    """(N, 8, 3) pelvis-frame points of one hand, as ArmKinematics.hand_points: palm origin, grasp point, origins of
    the index_1 / middle_1 / thumb_2 links, then the three fingertips."""
    links = [f"{side}_hand_palm_link"] + [f"{side}_{f}" for f in FINGER_LINKS]
    P = fk.poses(links, qdict(arm_q, hand_q), offsets)
    palm = P[links[0]]
    pts = [palm[:, :3, 3], palm[:, :3, 3] + palm[:, :3, :3] @ GRASP[side]]
    pts += [P[l][:, :3, 3] for l in links[1:]]
    pts += [P[l][:, :3, 3] + P[l][:, :3, :3] @ np.asarray(t, float) for l, t in zip(links[1:], TIP[side])]
    return np.stack(pts, 1)


# Silhouette model: spheres in the palm (3 x 3 grid, r 1.6 cm) and every ~1.2 cm along the fingers (r 1.0 cm)
PALM_GRID = [(x, 0.0, z) for x in (0.015, 0.04, 0.065) for z in (-0.025, 0.0, 0.025)]
R_PALM, R_FINGER = 0.016, 0.010


def hand_spheres(fk, side, arm_q, hand_q, offsets=None):
    """(N, M, 3) sphere centres (pelvis frame) and (M,) radii approximating one Dex3 hand."""
    names = ["hand_palm_link", "hand_index_0_link", "hand_index_1_link", "hand_middle_0_link", "hand_middle_1_link",
             "hand_thumb_1_link", "hand_thumb_2_link"]
    P = fk.poses([f"{side}_{n}" for n in names], qdict(arm_q, hand_q), offsets)
    L = {n: P[f"{side}_{n}"] for n in names}

    def at(n, t=(0, 0, 0)):
        return L[n][:, :3, 3] + L[n][:, :3, :3] @ np.asarray(t, float)

    sgn = -1.0 if side == "left" else 1.0
    pts, rad = [at("hand_palm_link", g) for g in PALM_GRID], [R_PALM] * len(PALM_GRID)
    chains = [[at("hand_index_0_link"), at("hand_index_1_link"), at("hand_index_1_link", [0.042, 0, 0])],
              [at("hand_middle_0_link"), at("hand_middle_1_link"), at("hand_middle_1_link", [0.042, 0, 0])],
              [at("hand_thumb_1_link"), at("hand_thumb_2_link"), at("hand_thumb_2_link", [0, sgn * 0.042, 0])]]
    for ch in chains:
        for a, b in zip(ch[:-1], ch[1:]):
            for t in (0.0, 0.25, 0.5, 0.75):
                pts.append(a + t * (b - a)); rad.append(R_FINGER)
        pts.append(ch[-1]); rad.append(R_FINGER)
    return np.stack(pts, 1), np.array(rad)


# ---------------------------------------------------------------------------------------------- camera
def calibration():
    import yaml
    c = yaml.safe_load(open(CALIB))["cameras"]["head"]
    i = c["intrinsics"]
    return np.array(c["T_pelvis_optical"], float), np.array([[i["fx"], 0, i["cx"]], [0, i["fy"], i["cy"]], [0, 0, 1]])


def _rot(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def camera(T0, pitch=0.0, roll=0.0, yaw=0.0, d=(0, 0, 0)):
    """The calibration camera rotated about its own optical axes (deg; pitch + = further down) and moved by d (m,
    pelvis frame): the same parametrisation as sim/venue_look/tools/fit_head_camera.py."""
    T = T0.copy()
    T[:3, :3] = T0[:3, :3] @ _rot("x", -pitch) @ _rot("z", roll) @ _rot("y", yaw)
    T[:3, 3] = T0[:3, 3] + np.asarray(d, float)
    return T


def scene_camera(T0, ds, episode=None, fits=None):
    """The camera as the scene (table, bins) says: the hand-clicked bin fit of drops 1-2, or for a dataset with head
    depth the policies' own fit_head_pose of that episode (fits = {episode: 4x4})."""
    if fits is not None and episode in fits:
        return fits[episode]
    s = SCENE_FIT[ds]
    return camera(T0, s["pitch"], s["roll"], 0.0, (0, s["dy"], 0))


def project(T, K, P):
    """Pixels (..., 2) and depth (...) of pelvis-frame points P (..., 3) for camera pose T (pelvis <- optical)."""
    Pc = (np.asarray(P, float) - T[:3, 3]) @ T[:3, :3]
    z = Pc[..., 2]
    zs = np.where(np.abs(z) < 1e-6, 1e-6, z)
    return np.stack([K[0, 0] * Pc[..., 0] / zs + K[0, 2], K[1, 1] * Pc[..., 1] / zs + K[1, 2]], -1), z


# ---------------------------------------------------------------------------------------------- image
W_IMG, H_IMG = 640, 480


def hand_mask(bgr):
    """Dark navy Dex3 pixels: dark, bluer than red, saturated (rejects the pink table, its grey shadows and the brown
    bin interiors), plus near-black pixels."""
    import cv2
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    V, S = hsv[..., 2].astype(np.int16), hsv[..., 1].astype(np.int16)
    B, R = bgr[..., 0].astype(np.int16), bgr[..., 2].astype(np.int16)
    m = ((V < 80) & (B - R >= 3) & (S >= 60)) | ((V < 28) & (B >= R - 3))
    return cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def silhouette(uv, rpx, shape=(H_IMG, W_IMG)):
    import cv2
    m = np.zeros(shape, np.uint8)
    for (u, v), r in zip(uv, rpx):
        cv2.circle(m, (int(round(u * 16)), int(round(v * 16))), max(16, int(round(r * 16))), 1, -1, cv2.LINE_8, 4)
    return m


def sphere_pixels(T, K, centres, radii):
    uv, z = project(T, K, centres)
    return uv, K[0, 0] * radii / np.maximum(z, 1e-3), z


def in_view(uv, rpx, z, margin=4):
    return bool((z > 0.15).all() and (uv[:, 0] - rpx > margin).all() and (uv[:, 0] + rpx < W_IMG - margin).all()
                and (uv[:, 1] - rpx > margin).all() and (uv[:, 1] + rpx < H_IMG - margin).all())


WIN = (-110, 110, -170, 110)    # searched shifts (px): du from, to, dv from, to (the bin-fit camera is ~100 px up)
RING = 14


def register(mask, sil):
    """Shift (du, dv) of the model silhouette that best matches the real hand: a matched filter that rewards hand
    pixels inside the silhouette and penalises hand pixels in a 14 px ring around it. Returns (du, dv, score, score
    at (0, 0)); score = fraction of the silhouette on hand pixels minus the fraction of the ring on hand pixels."""
    import cv2
    dil = cv2.dilate(sil, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * RING + 1, 2 * RING + 1)))
    ring = (dil > 0) & (sil == 0)
    ys, xs = np.nonzero(dil)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    W = (sil[y0:y1, x0:x1] > 0) / max(1, int(sil.sum())) - ring[y0:y1, x0:x1] / max(1, int(ring.sum()))
    W = W.astype(np.float32)
    du0, du1, dv0, dv1 = WIN
    pad = max(-du0, du1, -dv0, dv1) + 2
    M = cv2.copyMakeBorder(mask.astype(np.float32), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    region = M[y0 + pad + dv0:y1 + pad + dv1, x0 + pad + du0:x1 + pad + du1]
    S = cv2.matchTemplate(region, W, cv2.TM_CCORR)
    iv, iu = np.unravel_index(int(np.argmax(S)), S.shape)
    return iu + du0, iv + dv0, float(S[iv, iu]), float(S[-dv0, -du0])


# ---------------------------------------------------------------------------------------------- data
def load_states(ds_dir):
    import pyarrow.parquet as pq
    files = sorted(glob.glob(os.path.join(ds_dir, "data", "*", "*.parquet")))
    assert len(files) == 1, f"expected one data file in {ds_dir}, found {len(files)}"
    t = pq.read_table(files[0], columns=["observation.state", "episode_index", "frame_index", "index"]).to_pandas()
    st = np.stack(t["observation.state"].values).astype(float)
    assert (t["index"].values == np.arange(len(t))).all(), "rows not in global frame order"
    return st, t["episode_index"].values.astype(int), t["frame_index"].values.astype(int)


def still(q, half=4, tol=0.01):
    """(N,) True where no joint of q (N, k) moves more than tol rad within +- half frames (133 ms at 30 Hz)."""
    n = len(q)
    worst = np.zeros(n)
    for k in range(1, half + 1):
        d = np.abs(q[k:] - q[:-k]).max(1)
        worst[:-k] = np.maximum(worst[:-k], d)
        worst[k:] = np.maximum(worst[k:], d)
    ok = worst < tol
    ok[:half] = ok[-half:] = False
    return ok


ARM_TOL = {"left": 0.015, "right": 0.03}   # rad within +-133 ms; the right arm is rarely still while in view


def select(st, ep, fk, T0, K, Ts, max_per_ep=6, min_gap=15):
    """Frames per side where that arm and hand are still, the hand is in view with the calibration camera AND with
    the scene's camera (Ts: one 4x4, or {episode: 4x4}; so the choice favours neither), and the other hand is not
    close in the image. At most max_per_ep frames per episode and side, spread over the still stretches."""
    out = []
    for side in SIDES:
        sl = slice(0, 7) if side == "left" else slice(7, 14)
        hs = slice(14, 21) if side == "left" else slice(21, 28)
        ok = still(st[:, sl], tol=ARM_TOL[side]) & still(st[:, hs], tol=0.05)
        cand = np.flatnonzero(ok)
        if not len(cand):
            continue
        C, R = hand_spheres(fk, side, st[cand, :14], st[cand, 14:])
        other = "right" if side == "left" else "left"
        Co, Ro = hand_spheres(fk, other, st[cand, :14], st[cand, 14:])
        good = []
        for j, f in enumerate(cand):
            fine = True
            for T in (T0, Ts.get(int(ep[f]), T0) if isinstance(Ts, dict) else Ts):
                uv, rpx, z = sphere_pixels(T, K, C[j], R)
                if not in_view(uv, rpx, z, margin=6):
                    fine = False
                    break
                uvo, rpo, zo = sphere_pixels(T, K, Co[j], Ro)
                vis = zo > 0.1
                if vis.any():
                    dd = np.linalg.norm(uv[:, None, :] - uvo[None, vis, :], axis=2) - rpx[:, None] - rpo[None, vis]
                    if dd.min() < 35:
                        fine = False
                        break
            if fine:
                good.append(f)
        good = np.array(good, int)
        for e in np.unique(ep[good]):
            g = good[ep[good] == e]
            runs = np.split(g, np.flatnonzero(np.diff(g) > 1) + 1)          # still stretches
            mids = [int(r[len(r) // 2]) for r in runs if len(r)]
            picked = []
            for m in mids:
                if all(abs(m - p) >= min_gap for p in picked):
                    picked.append(m)
            if len(picked) > max_per_ep:
                picked = [picked[i] for i in np.linspace(0, len(picked) - 1, max_per_ep).round().astype(int)]
            out += [(f, side) for f in picked]
    return sorted(out)


def video_index(ds_dir, key):
    """Per global row: (video file, frame number inside that file), from meta/episodes (LeRobot v3: episodes are
    concatenated into chunk/file videos; drop 3's depth is split over two files)."""
    import pyarrow.parquet as pq
    import pandas as pd
    e = pd.concat([pq.read_table(p).to_pandas()
                   for p in sorted(glob.glob(os.path.join(ds_dir, "meta", "episodes", "*", "*.parquet")))])
    out = [None] * int((e["dataset_from_index"] + e["length"]).max())
    for _, r in e.iterrows():
        path = os.path.join(ds_dir, "videos", key, f"chunk-{int(r[f'videos/{key}/chunk_index']):03d}",
                            f"file-{int(r[f'videos/{key}/file_index']):03d}.mp4")
        k0 = int(round(float(r[f"videos/{key}/from_timestamp"]) * 30))
        a = int(r["dataset_from_index"])
        for k in range(int(r["length"])):
            out[a + k] = (path, k0 + k)
    return out


def decode(index, rows):
    """Yield (row, image) for the wanted rows: BGR uint8 for colour, uint16 mm for depth; each file decoded once."""
    import av
    by_file = {}
    for r in sorted(set(int(x) for x in rows)):
        path, k = index[r]
        by_file.setdefault(path, []).append((k, r))
    for path, items in by_file.items():
        j = 0
        with av.open(path) as c:
            for i, fr in enumerate(c.decode(video=0)):
                while j < len(items) and items[j][0] == i:
                    yield items[j][1], (fr.to_ndarray() if fr.format.name.startswith("gray")
                                        else fr.to_ndarray(format="bgr24"))
                    j += 1
                if j == len(items):
                    break


def head_fits(ds_dir, ep, tries=(0, 10, 20)):
    """Per episode, the head-camera fit our policies make at their first look (policy/headpose.py fit_head_pose =
    Emīls's decision_oracle fit, on the real depth, with Aalto's calibration.yaml and scene.yaml), on the episode's
    frames 0, 10, 20 (first one that fits), and whether v1.4's camera_move_ok would accept it."""
    import importlib.util
    if AALTO not in sys.path:
        sys.path.append(AALTO)
    from aaltonomous.interface.calibration import Calibration
    from aaltonomous.scene.scene import Scene
    spec = importlib.util.spec_from_file_location("headpose", os.path.join(REPO, "policy", "headpose.py"))
    hp = importlib.util.module_from_spec(spec)
    sys.modules["headpose"] = hp                   # its dataclass looks itself up there
    spec.loader.exec_module(hp)
    cal, scene = Calibration.load(), Scene.load()
    T0 = np.asarray(cal._T("head"), float)
    want = {}
    for e in np.unique(ep):
        r = np.flatnonzero(ep == e)
        for t in tries:
            if t < len(r):
                want[int(r[t])] = int(e)
    out = {}
    for row, depth in decode(video_index(ds_dir, DEPTH_KEY), list(want)):
        e = want[row]
        if e in out and out[e]["ok"]:
            continue
        fit = hp.fit_head_pose(np.asarray(depth), cal, scene)
        T = np.asarray(fit.T, float)
        move = float(np.linalg.norm(T[:3, 3] - T0[:3, 3]))
        out[e] = dict(T=T, ok=bool(fit.ok), row=int(row), tilt_deg=float(fit.tilt_deg), dyaw_deg=float(fit.dyaw_deg),
                      move_m=move, summary=fit.summary(),
                      v14_accepts=bool(fit.ok and fit.tilt_deg <= 15 and abs(fit.dyaw_deg) <= 6 and move <= 0.06))
    return out


def depth_at(depth_mm, u, v, half=2):
    """Median depth (m) of the valid pixels in a 5x5 window, or None (as look.py's hand_check)."""
    ui, vi = int(round(u)), int(round(v))
    if not (half <= ui < W_IMG - half and half <= vi < H_IMG - half):
        return None
    win = depth_mm[vi - half:vi + half + 1, ui - half:ui + half + 1].astype(float) * 0.001
    win = win[win > 0.1]
    return float(np.median(win)) if len(win) else None


def look_check(depth_mm, T, K, P8):
    """policy/policies/look.py hand_check for one hand: median |measured - predicted depth| (m) at the 8 joint-angle
    hand points projected with camera T, and how many were in view."""
    uv, z = project(T, K, P8)
    res = [abs(m - zi) for (u, v), zi in zip(uv, z) if zi >= 0.1 and (m := depth_at(depth_mm, u, v)) is not None]
    return (float(np.median(res)) if res else None), len(res)


def hand_3d(depth_mm, mask, T0, K, C, R, du, dv):
    """3-D offset of the real hand from the model hand, pelvis frame (m): each sphere's registered pixel (calibration
    projection + the measured shift) is back-projected at the depth measured there plus the sphere's radius, minus
    the sphere centre; median over the spheres that land on hand pixels with valid depth. Also returns the median
    depth difference (m, + = real hand further from the camera) and the number of spheres used."""
    Pc = (C - T0[:3, 3]) @ T0[:3, :3]
    uv, z = project(T0, K, C)
    offs, los = [], []
    for (u, v), pc, r, zz in zip(uv, Pc, R, z):
        u2, v2 = u + du, v + dv
        ui, vi = int(round(u2)), int(round(v2))
        if not (0 <= ui < W_IMG and 0 <= vi < H_IMG) or not mask[vi, ui]:
            continue
        zm = depth_at(depth_mm, u2, v2)
        if zm is None:
            continue
        ray = np.array([(u2 - K[0, 2]) / K[0, 0], (v2 - K[1, 2]) / K[1, 1], 1.0])
        offs.append(ray * zm + r * ray / np.linalg.norm(ray) - pc)
        los.append(zm - (zz - r))
    if len(offs) < 5:
        return None, None, len(offs)
    return T0[:3, :3] @ np.median(np.array(offs), 0), float(np.median(los)), len(offs)


# ---------------------------------------------------------------------------------------------- steps
def extract(drops, out, max_per_ep):
    """Select frames, register the model hand to the real hand in each, write frames.csv (+ the frames as jpg).
    For a dataset with head depth also: the policies' head fit per episode (head_fits.json), look.py's depth hand
    check with the calibration and the fitted camera, and the hand's 3-D offset from depth."""
    import cv2
    fk = G1FK()
    T0, K = calibration()
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    rows, fits_out = [], {}
    for ds in DATASETS:
        d = os.path.join(drops, ds)
        if not os.path.isdir(os.path.join(d, "videos", CAM_KEY)):
            print(f"{ds}: no {CAM_KEY} video in {d}, skipped")
            continue
        st, ep, fi = load_states(d)
        has_depth = os.path.isdir(os.path.join(d, "videos", DEPTH_KEY))
        fits = head_fits(d, ep) if has_depth else {}
        if has_depth:
            fits_out[ds] = {str(e): {k: (v.tolist() if k == "T" else v) for k, v in f.items()} for e, f in fits.items()}
            for e, f in sorted(fits.items()):
                print(f"  {ds} episode {e}: {f['summary']}; camera moved {100 * f['move_m']:.1f} cm; v1.4 "
                      f"{'accepts' if f['v14_accepts'] else 'REJECTS'}", flush=True)
        Ts = {e: f["T"] for e, f in fits.items() if f["ok"]} if has_depth else scene_camera(T0, ds)
        sel = select(st, ep, fk, T0, K, Ts, max_per_ep=max_per_ep)
        print(f"{ds}: {len(sel)} (frame, hand) pairs in {len(set(f for f, _ in sel))} frames", flush=True)
        by_frame = {}
        for f, s in sel:
            by_frame.setdefault(f, []).append(s)
        imgs = dict(decode(video_index(d, CAM_KEY), list(by_frame)))
        depths = dict(decode(video_index(d, DEPTH_KEY), list(by_frame))) if has_depth else {}
        for f in sorted(by_frame):
            img = imgs[f]
            cv2.imwrite(os.path.join(out, "frames", f"{ds}_{f:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            mask = hand_mask(img)
            Tsf = Ts.get(int(ep[f]), T0) if isinstance(Ts, dict) else Ts
            for s in by_frame[f]:
                C, R = hand_spheres(fk, s, st[f:f + 1, :14], st[f:f + 1, 14:])
                uv, rpx, z = sphere_pixels(T0, K, C[0], R)
                du, dv, score, score0 = register(mask, silhouette(uv, rpx))
                uvs, rps, _ = sphere_pixels(Tsf, K, C[0], R)
                _, _, _, score_scene = register(mask, silhouette(uvs, rps))
                hp = hand_points(fk, s, st[f:f + 1, :14], st[f:f + 1, 14:])[0]
                row = dict(dataset=ds, frame=int(f), episode=int(ep[f]), t=round(fi[f] / 30.0, 3), side=s,
                           du=int(du), dv=int(dv), score=round(score, 4), score_calib=round(score0, 4),
                           score_scene=round(score_scene, 4), depth=round(float(np.median(z)), 4),
                           u0=round(float(uv[:, 0].mean()), 1), v0=round(float(uv[:, 1].mean()), 1),
                           px=round(float(hp[1, 0]), 4), py=round(float(hp[1, 1]), 4), pz=round(float(hp[1, 2]), 4),
                           hc_calib="", hc_fit="", off_x="", off_y="", off_z="", los="", n3=0)
                if f in depths:
                    dm = depths[f]
                    c0, _ = look_check(dm, T0, K, hp)
                    c1, _ = look_check(dm, Tsf, K, hp)
                    o3, los, n3 = hand_3d(dm, mask, T0, K, C[0], R, du, dv)
                    row.update(hc_calib="" if c0 is None else round(c0, 4), hc_fit="" if c1 is None else round(c1, 4),
                               n3=n3)
                    if o3 is not None:
                        row.update(off_x=round(float(o3[0]), 4), off_y=round(float(o3[1]), 4),
                                   off_z=round(float(o3[2]), 4), los=round(los, 4))
                rows.append(row)
    with open(os.path.join(out, "frames.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    json.dump(fits_out, open(os.path.join(out, "head_fits.json"), "w"), indent=1)
    print(f"{len(rows)} registrations -> {out}/frames.csv")
    return rows


def validate_fk(drops, n=300, seed=0):
    """Compare this file's kinematics with Aalto's ArmKinematics.hand_points (Pinocchio) on real recorded poses.
    Run where Aalto's package and Pinocchio are installed (e.g. inside the policy image) with PYTHONPATH set."""
    from aaltonomous.baselines.classical.config import load_config
    from aaltonomous.baselines.classical.kinematics import ArmKinematics
    from aaltonomous.interface.safety import DEFAULT_URDF
    kin = ArmKinematics(load_config())
    fk = G1FK(str(DEFAULT_URDF))
    rng = np.random.default_rng(seed)
    worst = 0.0
    for ds in DATASETS:
        st = load_states(os.path.join(drops, ds))[0]
        idx = rng.choice(len(st), min(n, len(st)), replace=False)
        for side in SIDES:
            a = np.stack([kin.hand_points(side, st[i, :14], st[i, 14:]) for i in idx])
            b = hand_points(fk, side, st[idx, :14], st[idx, 14:])
            e = float(np.abs(a - b).max())
            worst = max(worst, e)
            print(f"{ds} {side}: {len(idx)} poses, max |difference| {1000 * e:.4f} mm")
    print("FK OK" if worst < 1e-6 else "FK MISMATCH")


def read_rows(out):
    with open(os.path.join(out, "frames.csv")) as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("frame", "episode", "du", "dv", "n3"):
            r[k] = int(r.get(k) or 0)
        for k in ("t", "score", "score_calib", "score_scene", "depth", "u0", "v0", "px", "py", "pz"):
            r[k] = float(r[k])
        for k in ("hc_calib", "hc_fit", "off_x", "off_y", "off_z", "los"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return rows


class Obs:
    """The registrations as fitting data: per (frame, hand) the 8 hand points (pelvis frame, from the joint angles)
    and where they are in the image (calibration-camera pixels + the measured shift)."""

    def __init__(self, rows, drops, fk, T0, K, fits=None):
        self.rows = rows
        st = {ds: load_states(os.path.join(drops, ds))[0] for ds in sorted(set(r["dataset"] for r in rows))}
        P = []
        for r in rows:
            s = st[r["dataset"]]
            f = r["frame"]
            P.append(hand_points(fk, r["side"], s[f:f + 1, :14], s[f:f + 1, 14:])[0])
        self.P = np.array(P)                                             # (n, 8, 3)
        uv0, z0 = project(T0, K, self.P)
        self.z = z0
        self.obs = uv0 + np.array([[r["du"], r["dv"]] for r in rows], float)[:, None, :]
        self.side = np.array([r["side"] for r in rows])
        self.ds = np.array([r["dataset"] for r in rows])
        self.ep = np.array([f'{r["dataset"]}:{r["episode"]}' for r in rows])
        fits = fits or {}                                                # {dataset: {episode: 4x4}}
        self.Ts = np.array([scene_camera(T0, r["dataset"], r["episode"], fits.get(r["dataset"])) for r in rows])
        self.T0, self.K = T0, K

    def subset(self, idx):
        o = object.__new__(Obs)
        o.rows = [self.rows[i] for i in idx]
        for k in ("P", "z", "obs", "side", "ds", "ep", "Ts"):
            setattr(o, k, getattr(self, k)[idx])
        o.T0, o.K = self.T0, self.K
        return o


def load_fits(out):
    """{dataset: {episode: 4x4}} of the accepted-or-not but successful head fits saved by extract()."""
    p = os.path.join(out, "head_fits.json")
    if not os.path.exists(p):
        return {}
    j = json.load(open(p))
    return {ds: {int(e): np.array(f["T"], float) for e, f in v.items() if f["ok"]} for ds, v in j.items()}


def _offset(P, side, dl, dr):
    return P + np.where((side == "left")[:, None, None], np.asarray(dl, float), np.asarray(dr, float))


def _cam_for(o, base):
    """Per-observation camera: the calibration camera, or the scene's camera of that observation (the bin fit of its
    dataset, or its episode's depth fit)."""
    if base == "calibration":
        return [o.T0] * len(o.P)
    return list(o.Ts)


def predict(o, model, p):
    """Predicted pixels (n, 8, 2) of the 8 hand points under `model` with parameters p."""
    if model in ("calibration", "lean"):
        return project(o.T0, o.K, o.P)[0]
    if model == "bin_fit":
        return np.stack([project(T, o.K, P)[0] for T, P in zip(_cam_for(o, "bin_fit"), o.P)])
    if model == "camera_rotation":
        return project(camera(o.T0, p[0], p[1], p[2]), o.K, o.P)[0]
    if model == "camera_pose":
        return project(camera(o.T0, p[0], p[1], p[2], p[3:6]), o.K, o.P)[0]
    if model in ("arm_offset", "bin_fit_arm_offset"):
        P = _offset(o.P, o.side, p[0:3], p[3:6])
        Ts = _cam_for(o, "calibration" if model == "arm_offset" else "bin_fit")
        return np.stack([project(T, o.K, Pi)[0] for T, Pi in zip(Ts, P)])
    if model == "arm_offset_seen":
        return project(o.T0, o.K, _offset(o.P, o.side, *seen_offsets(o, p)))[0]
    raise ValueError(model)


def seen_basis(o, side):
    """Two unit vectors (pelvis frame) across the mean line of sight from the calibration camera to that hand: the
    directions in which an offset shows in the image. Along the line of sight RGB alone can't measure it."""
    m = o.side == side
    ray = (o.P[m].reshape(-1, 3).mean(0) if m.any() else np.array([0.3, 0.0, 0.1])) - o.T0[:3, 3]
    ray /= np.linalg.norm(ray)
    e1 = np.cross(ray, [0.0, 0.0, 1.0])
    e1 /= np.linalg.norm(e1)                       # sideways (horizontal)
    e2 = np.cross(e1, ray)                         # up across the line of sight
    return e1, e2


def seen_offsets(o, p):
    out = []
    for k, side in enumerate(SIDES):
        e1, e2 = seen_basis(o, side)
        out.append(p[2 * k] * e1 + p[2 * k + 1] * e2)
    return out


MODELS = {   # name: (parameter names, description)
    "calibration": ([], "calibration.yaml camera, joint-angle hands (no parameters)"),
    "lean": ([], "torso leans, camera and arms together: in the image the same as calibration (no parameters)"),
    "bin_fit": ([], "camera tilted on its mount as the scene says (bin fit 8-12 deg in drops 1-2; drop 3: the "
                    "policies' own depth fit of that episode)"),
    "camera_rotation": (["pitch_deg", "roll_deg", "yaw_deg"], "camera rotation fitted to the hands"),
    "camera_pose": (["pitch_deg", "roll_deg", "yaw_deg", "dx_m", "dy_m", "dz_m"],
                    "camera rotation + position fitted to the hands"),
    "arm_offset": (["left_dx", "left_dy", "left_dz", "right_dx", "right_dy", "right_dz"],
                   "calibration camera + constant xyz offset per arm (pelvis frame, m)"),
    "bin_fit_arm_offset": (["left_dx", "left_dy", "left_dz", "right_dx", "right_dy", "right_dz"],
                           "bin-fit camera + constant xyz offset per arm (pelvis frame, m)"),
    "arm_offset_seen": (["left_side_m", "left_up_m", "right_side_m", "right_up_m"],
                        "calibration camera + per-arm offset across the line of sight only (what the image shows)"),
}


def fit_model(o, model, f_scale=8.0):
    from scipy.optimize import least_squares
    names = MODELS[model][0]
    if not names:
        return np.zeros(0)
    has = {s: bool((o.side == s).any()) for s in SIDES}

    per = 2 if model == "arm_offset_seen" else 3

    def zero_missing(p):                            # an arm with no observations keeps a zero offset
        p = np.asarray(p, float).copy()
        if "offset" in model:
            if not has["left"]:
                p[0:per] = 0
            if not has["right"]:
                p[per:2 * per] = 0
        return p

    r = least_squares(lambda p: (predict(o, model, zero_missing(p)) - o.obs).ravel(), np.zeros(len(names)),
                      loss="soft_l1", f_scale=f_scale, x_scale=_xscale(names))
    return zero_missing(r.x)


def _xscale(names):
    return np.array([1.0 if n.endswith("deg") else 0.01 for n in names])


def residuals(o, model, p):
    """Per observation: pixel error of the hand (mean over its 8 points, px) and the same in cm at the hand."""
    e = predict(o, model, p) - o.obs                                    # (n, 8, 2)
    px = np.linalg.norm(e.mean(1), axis=1)
    cm = 100 * px * np.median(o.z, 1) / o.K[0, 0]
    return px, cm


def bootstrap(o, model, n=200, seed=0):
    """Parameter spread from resampling whole episodes (frames of one episode are not independent)."""
    rng = np.random.default_rng(seed)
    eps = np.unique(o.ep)
    out = []
    for _ in range(n):
        pick = rng.choice(eps, len(eps))
        idx = np.concatenate([np.flatnonzero(o.ep == e) for e in pick])
        out.append(fit_model(o.subset(idx), model))
    return np.array(out)


def fit_all(o, boot=200):
    """Every model on every subset: both datasets, each dataset, each arm. Returns a list of result dicts."""
    subsets = [("all datasets", np.arange(len(o.P)))]
    subsets += [(ds, np.flatnonzero(o.ds == ds)) for ds in DATASETS]
    subsets += [(f"{s} hand", np.flatnonzero(o.side == s)) for s in SIDES]
    out = []
    for label, idx in subsets:
        if len(idx) < 5:
            continue
        sub = o.subset(idx)
        for model, (names, desc) in MODELS.items():
            if label.endswith("hand") and "offset" in model:
                continue
            p = fit_model(sub, model)
            px, cm = residuals(sub, model, p)
            r = dict(subset=label, model=model, n=len(idx), episodes=len(np.unique(sub.ep)),
                     params={k: round(float(v), 4) for k, v in zip(names, p)},
                     median_px=round(float(np.median(px)), 1), rms_px=round(float(np.sqrt((px ** 2).mean())), 1),
                     median_cm=round(float(np.median(cm)), 2), p90_cm=round(float(np.percentile(cm, 90)), 2))
            if model == "arm_offset_seen":            # the same offsets in pelvis xyz (m)
                for side, d in zip(SIDES, seen_offsets(sub, p)):
                    r[f"{side}_offset_xyz"] = [round(float(v), 4) for v in d]
            if names and boot and label in ("all datasets",) + DATASETS:
                b = bootstrap(sub, model, n=boot)
                r["params_p5_p95"] = {k: [round(float(np.percentile(b[:, i], 5)), 4),
                                          round(float(np.percentile(b[:, i], 95)), 4)] for i, k in enumerate(names)}
                if model == "arm_offset_seen":
                    xyz = np.array([np.concatenate(seen_offsets(sub, q)) for q in b])
                    for k, side in enumerate(SIDES):
                        r[f"{side}_offset_xyz_p5_p95"] = [[round(float(np.percentile(xyz[:, 3 * k + j], q)), 4)
                                                           for q in (5, 95)] for j in range(3)]
            out.append(r)
            print(f"{label:16s} {model:20s} n={len(idx):3d} median {r['median_px']:5.1f} px "
                  f"({r['median_cm']:.2f} cm) rms {r['rms_px']:5.1f} px  "
                  + " ".join(f"{k}={v:+.3f}" for k, v in r["params"].items()), flush=True)
    return out


COUNTER_Z = 0.01           # scene.yaml: mat_origin_in_pelvis z (table top in the pelvis frame)
OBJ_HALF = 0.0225          # 4.5 cm objects


def policy_errors(o, p_offset, p_rot):
    """How far the hand lands from an object, for objects on the table where the real ones lie in Aalto's footage
    (pelvis x 0.20-0.34 m, |y| <= 0.15 m on that arm's side; sim/venue_look/README.md: mat x 0.30-0.60, y 0.04-0.20),
    if the real camera sits relative to the TABLE as the bin fit of that dataset
    says and relative to the ARMS as the hands say. Ways to turn a seen object into an arm target:
      fit            v1.4/v1.5/v1.6/ADK today: target = position in the fitted (table-aligned) frame;
      calibration    calibration.yaml camera, no fit (the table then looks tilted to the perception);
      mapped         fit for perception, target mapped into the arm frame: T0 @ inv(T_fit) @ p - arm offset;
      mapped (rot)   the same with the hand-fitted camera rotation instead of the arm offsets: Tr @ inv(T_fit) @ p.
    Each is scored against both explanations of the hand data (arm_offset model p_offset, camera_rotation p_rot).
    The scene's camera: the bin fit for drops 1-2; for drop 3 every episode's own depth fit (pooled).
    Returns {dataset: {way: {truth: {side: (median, max) cm}}}}."""
    T0 = o.T0
    Tr = camera(T0, p_rot[0], p_rot[1], p_rot[2])
    out = {}
    for ds in DATASETS:
        Tbs = list({id(T): T for T in o.Ts[o.ds == ds]}.values()) if ds not in SCENE_FIT else [scene_camera(T0, ds)]
        Tbs = list({tuple(np.round(T, 9).ravel()): T for T in Tbs}.values())
        if not Tbs:
            continue
        res = {}
        for side, d in (("left", np.asarray(p_offset[0:3])), ("right", np.asarray(p_offset[3:6]))):
            ys = (0.0, 0.075, 0.15) if side == "left" else (0.0, -0.075, -0.15)
            W = np.array([[x, y, COUNTER_Z + OBJ_HALF] for x in (0.20, 0.27, 0.34) for y in ys])
            errs = {}
            for Tb in Tbs:
                c = (W - Tb[:3, 3]) @ Tb[:3, :3]                        # the objects in the camera frame
                A = c @ T0[:3, :3].T + T0[:3, 3]       # object in the arm frame, offset model (hand lands at cmd + d)
                B = c @ Tr[:3, :3].T + Tr[:3, 3]       # object in the arm frame, rotation model (hand lands at cmd)
                cmds = {"fit": W, "calibration": A, "mapped": A - d, "mapped (rot)": B}
                for way, cmd in cmds.items():
                    for truth, err in (("offset", cmd + d - A), ("rotation", cmd - B)):
                        errs.setdefault((way, truth), []).append(np.linalg.norm(err, axis=1))
            for (way, truth), v in errs.items():
                v = np.concatenate(v)
                res.setdefault(way, {}).setdefault(truth, {})[side] = (round(float(100 * np.median(v)), 1),
                                                                       round(float(100 * v.max()), 1))
        out[ds] = res
    return out


VENUE_CAM = dict(pitch=10.0, roll=1.0, yaw=0.0, d=(0.0, 0.025, 0.0))   # sim/venue_look: ~10 deg down on the mount


def _sample(depth_m, uv):
    """Depth (m, NaN where invalid) at the pixels uv (..., 2): nearest pixel, no smoothing."""
    u = np.round(uv[..., 0]).astype(int)
    v = np.round(uv[..., 1]).astype(int)
    ok = (u >= 0) & (u < W_IMG) & (v >= 0) & (v < H_IMG)
    out = np.full(u.shape, np.nan)
    out[ok] = depth_m[v[ok], u[ok]]
    return out


def depth_agreement(depth_m, T, K, C, R, tol=0.02):
    """Depth-only test of one camera model for one hand: the hand's sphere centres (inside the hand, unlike
    look.py's grasp point and fingertip ends) projected with camera T; at each pixel the measured depth is compared
    with the model's front surface (centre depth - radius). Returns (fraction within tol, median |error| m, n)."""
    uv, z = project(T, K, C)
    m = _sample(depth_m, uv)
    e = np.abs(m - (z - R))
    e = e[np.isfinite(e)]
    if len(e) < 5:
        return None, None, len(e)
    return float((e < tol).mean()), float(np.median(e)), len(e)


def depth_checks(drops, rows, out, ds="g1_junction_drop_3", hand_rot=None, offsets=None):
    """Drop 3: which camera model puts the hands where the DEPTH image has them (no colour involved)?
    Models: calibration.yaml (= leaning robot: camera and arms move together, so the hands project the same),
    the venue look's ~10 deg mount tilt, the policies' own fit_head_pose of the episode (~14.5 deg) as a mount tilt,
    the camera rotation fitted to the hands in colour, and calibration + per-arm offset. Then a depth-only search
    of the per-arm 3-D offset (grid +-5 cm, 5 mm steps) that best puts the hand spheres on the measured surface."""
    d = os.path.join(drops, ds)
    if not os.path.isdir(os.path.join(d, "videos", DEPTH_KEY)):
        return {}
    fk = G1FK()
    T0, K = calibration()
    st, ep, _ = load_states(d)
    fits = load_fits(out).get(ds, {})
    R_ = [r for r in rows if r["dataset"] == ds]
    depths = {f: dm.astype(float) * 0.001 for f, dm in decode(video_index(d, DEPTH_KEY), [r["frame"] for r in R_])}
    for dm in depths.values():
        dm[dm < 0.1] = np.nan
    models = {"calibration.yaml (= leaning robot)": lambda r: (T0, 0.0),
              "venue look: camera ~10 deg down on its mount": lambda r: (camera(T0, VENUE_CAM["pitch"],
                                                                                VENUE_CAM["roll"], VENUE_CAM["yaw"],
                                                                                VENUE_CAM["d"]), 0.0),
              "policies' own fit as a mount tilt (~14.5 deg)": lambda r: (fits.get(r["episode"], T0), 0.0)}
    if hand_rot is not None:
        models["camera rotation fitted to the hands (colour)"] = lambda r: (camera(T0, *hand_rot), 0.0)
    if offsets is not None:
        models["calibration + per-arm offset (colour)"] = lambda r: (T0, np.asarray(offsets[r["side"]], float))
    res = {"models": {}, "frames": len(R_)}
    print(f"\n{ds}: depth-only check on {len(R_)} (frame, hand) pairs (sphere centres inside the hand, |depth error| "
          f"< 2 cm counts as on the hand)")
    for name, fn in models.items():
        fr, er = [], []
        for r in R_:
            f = r["frame"]
            C, Rr = hand_spheres(fk, r["side"], st[f:f + 1, :14], st[f:f + 1, 14:])
            T, off = fn(r)
            a, e, n = depth_agreement(depths[f], T, K, C[0] + off, Rr)
            if a is not None:
                fr.append(a)
                er.append(e)
        res["models"][name] = dict(n=len(fr), on_hand_fraction=round(float(np.median(fr)), 3),
                                   median_abs_error_cm=round(100 * float(np.median(er)), 2))
        print(f"  {name:48s} on the hand {100 * np.median(fr):3.0f} % of points (median over {len(fr)}), "
              f"median depth error {100 * np.median(er):.1f} cm")
    # Depth-only per-arm 3-D offset for each camera model: grid search of a constant pelvis-frame shift of the hand
    # spheres (+-12 cm in 1 cm steps, then +-1 cm in 2.5 mm steps around the best). A model that needs a large
    # offset to put the hands on the measured surface is the wrong model (joint offsets don't do 6-9 cm).
    g1 = np.arange(-0.12, 0.1201, 0.01)
    G1 = np.stack(np.meshgrid(g1, g1, g1, indexing="ij"), -1).reshape(-1, 3)
    g2 = np.arange(-0.01, 0.01001, 0.0025)
    G2 = np.stack(np.meshgrid(g2, g2, g2, indexing="ij"), -1).reshape(-1, 3)
    data = {side: [] for side in SIDES}
    for r in R_:
        f = r["frame"]
        C, Rr = hand_spheres(fk, r["side"], st[f:f + 1, :14], st[f:f + 1, 14:])
        data[r["side"]].append((r, C[0], Rr))

    def score(T_of, side, G):
        s = np.zeros(len(G))
        for r, C, Rr in data[side]:
            uv, z = project(T_of(r), K, C[None] + G[:, None, :])           # (G, M)
            e = np.abs(_sample(depths[r["frame"]], uv) - (z - Rr[None]))
            s += np.where(np.isfinite(e), e < 0.015, False).mean(1)
        return s / max(1, len(data[side]))

    res["offset_depth_only"] = {}
    print("  depth-only best per-arm offset for each camera model (|depth error| < 1.5 cm counts as on the hand):")
    for name, fn in list(models.items())[:3]:
        T_of = (lambda fn_: (lambda r: fn_(r)[0]))(fn)
        for side in SIDES:
            if len(data[side]) < 3:
                continue
            s1 = score(T_of, side, G1)
            b1 = G1[int(np.argmax(s1))]
            s2 = score(T_of, side, b1 + G2)
            best = b1 + G2[int(np.argmax(s2))]
            zero = score(T_of, side, np.zeros((1, 3)))[0]
            res["offset_depth_only"].setdefault(name, {})[side] = dict(
                n=len(data[side]), offset_xyz_m=[round(float(v), 4) for v in best],
                offset_norm_cm=round(100 * float(np.linalg.norm(best)), 1),
                on_hand_fraction=round(float(s2.max()), 3), on_hand_fraction_no_offset=round(float(zero), 3))
            print(f"    {name:48s} {side:5s} ({len(data[side]):2d} frames): needs "
                  + ", ".join(f"{a} {100 * v:+.1f}" for a, v in zip("xyz", best))
                  + f" cm (|{100 * np.linalg.norm(best):.1f}| cm); on the hand {100 * s2.max():.0f} % "
                    f"(without offset {100 * zero:.0f} %)", flush=True)
    return res


def depth_summary(rows, out, min_score):
    """Drop 3 (head depth): the policies' own head-camera fit per episode, what look.py's hand check would conclude,
    and the hands' 3-D offset measured with depth. Printed and returned for fits.json."""
    from collections import Counter
    p = os.path.join(out, "head_fits.json")
    if not os.path.exists(p):
        return {}
    res = {}
    for ds, eps in json.load(open(p)).items():
        ok = [f for f in eps.values() if f["ok"]]
        tilt = np.array([f["tilt_deg"] for f in ok])
        acc = sum(f["v14_accepts"] for f in eps.values())
        print(f"\n{ds}: policies' head fit on real depth: {len(ok)} of {len(eps)} episodes fit, tilt "
              f"{np.median(tilt):.1f} deg (median; {tilt.min():.1f}-{tilt.max():.1f}), v1.4 would use {acc}")
        R = [r for r in rows if r["dataset"] == ds]
        frames = {}
        for r in R:
            if r["hc_calib"] is not None and r["hc_fit"] is not None:
                frames.setdefault((r["frame"], r["episode"]), []).append((r["hc_calib"], r["hc_fit"]))
        verdicts, cs, fs = Counter(), [], []
        for (f, e), v in frames.items():          # look.py: mean over the hands seen, then its rules
            c, fz = float(np.mean([a for a, _ in v])), float(np.mean([b for _, b in v]))
            cs.append(c)
            fs.append(fz)
            t = eps.get(str(e), {}).get("tilt_deg", 0.0)
            verdicts["inconclusive" if min(c, fz) > 0.04 else "camera close to calibration" if t < 3 else
                     "TILTED CAMERA" if fz + 0.02 < c else "LEANING ROBOT" if c + 0.02 < fz else "unclear"] += 1
        if frames:
            print(f"  look.py hand check on {len(frames)} frames: calibration camera {100 * np.median(cs):.1f} cm, "
                  f"fitted camera {100 * np.median(fs):.1f} cm (median depth error); verdicts {dict(verdicts)}")
        d3 = {}
        for side in SIDES:
            S = [r for r in R if r["side"] == side and r["off_x"] is not None and r["score"] >= min_score]
            if not S:
                continue
            O = np.array([[r["off_x"], r["off_y"], r["off_z"], r["los"]] for r in S])
            med, q1, q3 = np.median(O, 0), np.percentile(O, 25, 0), np.percentile(O, 75, 0)
            d3[side] = dict(n=len(S), episodes=len(set(r["episode"] for r in S)),
                            offset_xyz_m=[round(float(v), 4) for v in med[:3]],
                            iqr_xyz_m=[[round(float(a), 4), round(float(b), 4)] for a, b in zip(q1[:3], q3[:3])],
                            line_of_sight_m=round(float(med[3]), 4))
            print(f"  {side} hand 3-D offset with depth (n={len(S)}): "
                  + ", ".join(f"{a} {100 * m:+.1f} [{100 * lo:+.1f}, {100 * hi:+.1f}]"
                              for a, m, lo, hi in zip("xyz", med, q1, q3))
                  + f" cm; real hand {100 * med[3]:+.1f} cm further from the camera than the model")
        res[ds] = dict(episodes=len(eps), fits_ok=len(ok), tilt_median_deg=round(float(np.median(tilt)), 2),
                       tilt_range_deg=[round(float(tilt.min()), 2), round(float(tilt.max()), 2)], v14_accepts=acc,
                       look_frames=len(frames), look_calib_cm=round(100 * float(np.median(cs)), 2) if cs else None,
                       look_fit_cm=round(100 * float(np.median(fs)), 2) if fs else None, look_verdicts=dict(verdicts),
                       hand_3d=d3)
    return res


def figures(o, rows, drops, out_dir, frames_dir, pick=None):
    """hand-offset-overlay.jpg: real frames with the hand where each model puts it; hand-offset-scatter.png: the
    measured hand shift per frame vs the shift the bin-fit camera predicts."""
    import cv2
    fk = G1FK()
    os.makedirs(out_dir, exist_ok=True)
    present = sorted(set(o.ds), key=DATASETS.index)
    st = {ds: load_states(os.path.join(drops, ds))[0] for ds in present}
    per_ds = 6 // max(1, len(present))
    if pick is None:          # clear frames: high score, spread over the datasets and both hands
        order = np.argsort([-r["score"] for r in rows])
        pick, seen = [], set()
        for i in order:
            r = rows[i]
            key = (r["dataset"], r["side"], r["episode"])
            if key in seen or len([j for j in pick if rows[j]["dataset"] == r["dataset"]]) >= per_ds:
                continue
            if r["side"] == "right" and any(rows[j]["side"] == "right" for j in pick):
                continue
            seen.add(key)
            pick.append(int(i))
            if len(pick) == per_ds * len(present):
                break
    tiles = []
    for i in pick:
        r = rows[i]
        ds, f, s = r["dataset"], r["frame"], r["side"]
        img = cv2.imread(os.path.join(frames_dir, f"{ds}_{f:06d}.jpg"))
        C, R = hand_spheres(fk, s, st[ds][f:f + 1, :14], st[ds][f:f + 1, 14:])
        for T, col, sh in ((o.Ts[i], (60, 220, 60), (0, 0)), (o.T0, (40, 40, 255), (0, 0)),
                           (o.T0, (0, 230, 255), (r["du"], r["dv"]))):
            uv, rpx, _ = sphere_pixels(T, o.K, C[0], R)
            cnt, _ = cv2.findContours(silhouette(uv + np.array(sh, float), rpx), cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(img, cnt, -1, col, 2, cv2.LINE_AA)
        label = f"{DROP_NAME[ds]}  frame {f}  {s} hand"
        cv2.putText(img, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(img)
    grid = np.vstack([np.hstack(tiles[k:k + 3]) for k in range(0, len(tiles), 3)])
    legend = np.full((40, grid.shape[1], 3), 255, np.uint8)
    x = 10
    for text, col in (("camera tilted on its mount as the scene says (bin / depth fit)", (60, 220, 60)),
                      ("calibration.yaml camera (= leaning robot)", (40, 40, 255)),
                      ("where the real hand is (fitted to the image)", (0, 230, 255))):
        cv2.rectangle(legend, (x, 12), (x + 28, 28), col, -1)
        cv2.putText(legend, text, (x + 36, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        x += 46 + cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0]
    grid = np.vstack([grid, legend])
    cv2.imwrite(os.path.join(out_dir, "hand-offset-overlay.jpg"), cv2.resize(grid, None, fx=0.75, fy=0.75,
                interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 85])

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    uv0 = project(o.T0, o.K, o.P)[0].mean(1)
    meas = o.obs.mean(1) - uv0
    pred = np.stack([project(T, o.K, P)[0].mean(0) for T, P in zip(o.Ts, o.P)]) - uv0
    fig, ax = plt.subplots(figsize=(9.6, 5.8), dpi=120)
    for ds, mk in zip(DATASETS, ("o", "^", "s")):
        if ds not in present:
            continue
        for side, col in (("left", "#d4a017"), ("right", "#7a3cc0")):
            m = (o.ds == ds) & (o.side == side)
            if m.any():
                ax.scatter(meas[m, 0], meas[m, 1], s=16, marker=mk, color=col, alpha=0.75,
                           label=f"measured, {side} hand, {DROP_NAME[ds]}")
        m = o.ds == ds
        ax.scatter(pred[m, 0], pred[m, 1], s=10, marker=mk, color="#3a9a3a", alpha=0.35,
                   label=f"{'bin' if ds in SCENE_FIT else 'depth'}-fit camera predicts, {DROP_NAME[ds]}")
    ax.scatter([0], [0], marker="+", s=300, color="#d02020", linewidths=2.5,
               label="calibration camera (= leaning robot)")
    ax.axhline(0, color="#bbb", lw=0.8)
    ax.axvline(0, color="#bbb", lw=0.8)
    ax.invert_yaxis()
    ax.set_xlabel("hand shift in the head image, right (px)")
    ax.set_ylabel("hand shift in the head image, down (px)")
    ax.set_title("Where the real hand is, relative to the calibration-camera projection", fontsize=10)
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.03, 1.0), frameon=False)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "hand-offset-scatter.png"))
    plt.close(fig)
    return pick


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--drops", default=os.path.join(REPO, "artifacts/drops"))
    ap.add_argument("--out", default=os.path.join(REPO, "artifacts/analysis/hand_offset"))
    ap.add_argument("--max-per-episode", type=int, default=12)
    ap.add_argument("--min-score", type=float, default=0.4,
                    help="registrations below this are mostly hands at the image edge, half masked (checked by eye)")
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--fit-only", action="store_true")
    ap.add_argument("--figures", default=os.path.join(REPO, "docs/research/img"),
                    help="where the two figures go ('' = none)")
    ap.add_argument("--validate-fk", action="store_true")
    a = ap.parse_args()
    if a.validate_fk:
        validate_fk(a.drops)
        sys.exit(0)
    rows = read_rows(a.out) if a.fit_only else extract(a.drops, a.out, a.max_per_episode)
    keep = [r for r in rows if r["score"] >= a.min_score]
    print(f"{len(keep)} of {len(rows)} registrations with score >= {a.min_score}")
    T0, K = calibration()
    o = Obs(keep, a.drops, G1FK(), T0, K, fits=load_fits(a.out))
    res = fit_all(o, boot=a.boot)
    both = {r["model"]: r for r in res if r["subset"] == "all datasets"}
    pe = policy_errors(o, list(both["arm_offset"]["params"].values()), list(both["camera_rotation"]["params"].values()))
    print("\nHand-to-object error at typical grasp spots, cm (median / max), if the policy turns a seen object into an "
          "arm target this way:")
    for ds, ways in pe.items():
        for way, truths in ways.items():
            print(f"  {ds:20s} {way:13s} " + "   ".join(
                f"{truth} model: " + ", ".join(f"{s} {m:.1f}/{x:.1f}" for s, (m, x) in v.items())
                for truth, v in truths.items()))
    ds_depth = depth_summary(rows, a.out, a.min_score)
    json.dump({"fits": res, "policy_errors": pe, "depth": ds_depth, "n_registrations": len(rows), "n_used": len(keep)},
              open(os.path.join(a.out, "fits.json"), "w"), indent=1)
    if a.figures:
        pick = figures(o, keep, a.drops, a.figures, os.path.join(a.out, "frames"))
        print(f"figures -> {a.figures} (frames {[keep[i]['dataset'][:8] + ':' + str(keep[i]['frame']) for i in pick]})")
