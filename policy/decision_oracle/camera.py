"""Camera perception for the decision oracle: head RGB-D -> objects (colour, shape, position, yaw) in the pelvis frame.

Replaces Aalto's `PrivilegedPerception` (exact poses from the sim) with something a submission may use: only `obs`.

    cam = CameraPerception(scene, calibration)
    cam.update(obs)                       # every act(): keeps a reference to the latest head image + depth
    dets = cam.detect()                   # in the planning thread: list of Detection (+ .shape, .name, .yaw)

Three steps:
  1. Head camera pose (`fit_head_pose`). Aalto's calibration.yaml pose is a URDF default; the real camera (and our
     venue-look sim) points ~10 deg further down. The pose is re-fitted from the depth image itself: the table plane
     gives tilt, roll and height; the bin walls (known 21 cm boxes at known places) give x, y and yaw.
  2. Objects: pixels that have an object colour (HSV) AND lie at object height above the table, outside the bins.
     One blob = one object; its top face (highest 6 mm) gives the centre.
  3. Shape and yaw from the outline of the top face seen from above: square / circle / triangle fit. A triangle
     lying on its side shows a ridge instead of a face ("tipped").

No network calls here. Decision 1 crop labels are added on top in `labels.py` (optional, with this as fallback).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from aaltonomous.baselines.classical.perception import Detection

# OpenCV HSV (H 0-180). Each class covers the sim colour and the real one (measured on Aalto's real head frames,
# docs/research/aalto-discord-notes.md; same ranges as policy/policies/classical_v1.py).
HSV = {
    "red": [[[0, 70, 70], [17, 255, 255]], [[165, 70, 70], [180, 255, 255]]],     # sim red + real orange
    "yellow": [[[18, 50, 90], [55, 255, 255]]],
    "blue": [[[90, 60, 60], [165, 255, 255]]],                                   # sim blue + real purple
}
CAM = "head"


@dataclass
class PoseFit:
    T: np.ndarray                 # 4x4 pelvis <- optical
    ok: bool
    plane_inliers: float = 0.0    # fraction of sampled points on the table plane
    wall_score: float = 0.0       # fraction of wall-band points within 4 mm of a bin outline
    n_wall: int = 0
    tilt_deg: float = 0.0         # rotation applied to the calibration pose by the plane fit
    dxy: tuple = (0.0, 0.0)       # shift applied by the bin fit (m)
    dyaw_deg: float = 0.0
    why: str = ""


def _points(cal, depth, step=1):
    """Optical-frame points (h, w, 3) for a depth image (mm), subsampled by `step`."""
    c = cal.cams[CAM]
    h, w = depth.shape
    v, u = np.mgrid[0:h:step, 0:w:step]
    z = depth[::step, ::step].astype(np.float32) * c.depth_scale
    x = (u - c.K[0, 2]) / c.K[0, 0] * z
    y = (v - c.K[1, 2]) / c.K[1, 1] * z
    return np.stack([x, y, z], axis=-1)


def _rot_a_to_b(a, b):
    """Smallest rotation taking unit vector a to unit vector b."""
    v, c = np.cross(a, b), float(a @ b)
    s = np.linalg.norm(v)
    if s < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]]) / s
    return np.eye(3) + s * K + (1 - c) * K @ K


def _bin_outlines(scene, res=0.002):
    """Points (pelvis xy) along the wall centre lines of every bin, `res` apart."""
    b = scene.cfg["bins"]
    half = np.asarray(b["outer_size"], float) / 2 - float(b.get("wall_thickness", 0.003)) / 2
    pts = []
    for cx, cy in b["centers"].values():
        t = np.arange(-1, 1, res / half.max())
        for sx in (-1, 1):
            pts.append(np.stack([np.full_like(t, cx + sx * half[0]), cy + t * half[1]], 1))
            pts.append(np.stack([cx + t * half[0], np.full_like(t, cy + sx * half[1])], 1))
    pm = np.vstack(pts)
    return scene.mat_to_pelvis(np.c_[pm, np.zeros(len(pm))])[:, :2]


def fit_head_pose(depth, cal, scene, T0=None, rng=None, max_range_mm=1600):
    """Fit the head camera pose (pelvis <- optical) to one depth image. Returns PoseFit; .ok False keeps T0."""
    import cv2
    T0 = np.asarray(cal._T(CAM) if T0 is None else T0, float)
    rng = rng or np.random.default_rng(0)
    P = _points(cal, depth, step=4).reshape(-1, 3)
    d = depth[::4, ::4].reshape(-1)
    P = P[(d > 150) & (d < max_range_mm)]
    if len(P) < 2000:
        return PoseFit(T0, False, why="too little valid depth")
    Q = P @ T0[:3, :3].T + T0[:3, 3]              # pelvis frame according to the calibration
    zc = scene.counter_z

    # 1. table plane: RANSAC among planes roughly horizontal and near the expected table height
    best, best_n = None, 0
    for _ in range(150):
        a, b, c = Q[rng.integers(len(Q), size=3)]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-8:
            continue
        n = n / ln
        if n[2] < 0:
            n = -n
        if n[2] < 0.85:                         # more than ~32 deg off the calibration's vertical
            continue
        off = float(n @ a)
        if abs(off - zc) > 0.25:
            continue
        k = int((np.abs(Q @ n - off) < 0.005).sum())
        if k > best_n:
            best, best_n = (n, off), k
    if best is None or best_n < 0.15 * len(Q):
        return PoseFit(T0, False, plane_inliers=best_n / len(Q), why="no table plane")
    n, off = best
    inl = np.abs(Q @ n - off) < 0.006
    c0 = Q[inl].mean(0)                           # refine: least squares on the inliers
    _, _, vt = np.linalg.svd(Q[inl] - c0, full_matrices=False)
    n = vt[2] if vt[2][2] > 0 else -vt[2]
    R1 = _rot_a_to_b(n, np.array([0.0, 0.0, 1.0]))
    T1 = np.eye(4)
    T1[:3, :3] = R1 @ T0[:3, :3]
    T1[:3, 3] = R1 @ T0[:3, 3]
    T1[2, 3] += zc - float((R1 @ c0)[2])          # table plane -> counter height
    tilt = float(np.degrees(np.arccos(np.clip(n[2], -1, 1))))
    fit = PoseFit(T1, True, plane_inliers=float(inl.mean()), tilt_deg=tilt)

    # 2. bins: wall points between object height and the rim, seen from above, against the known box outlines
    Q1 = P @ T1[:3, :3].T + T1[:3, 3]
    wall = float(scene.cfg["bins"]["wall_height"])
    hobj = scene.object_height()
    h = Q1[:, 2] - zc
    band = (h > min(hobj + 0.006, wall - 0.03)) & (h < wall - 0.006)
    W = Q1[band][:, :2]
    out = _bin_outlines(scene)
    lo, hi = out.min(0) - 0.15, out.max(0) + 0.15
    W = W[np.all((W > lo) & (W < hi), axis=1)]
    fit.n_wall = len(W)
    if len(W) < 150:
        fit.why = "too few bin wall points: kept calibration x, y, yaw"
        return fit
    res = 0.002
    size = np.ceil((hi - lo) / res).astype(int)   # (nx, ny)
    tpl = np.full((size[0], size[1]), 255, np.uint8)
    ij = np.floor((out - lo) / res).astype(int)
    tpl[ij[:, 0], ij[:, 1]] = 0
    dist = cv2.distanceTransform(tpl, cv2.DIST_L2, 3) * res            # m to the nearest outline
    cap = 0.02
    cost_map = np.minimum(dist, cap).astype(np.float32)

    def cost(yaw, dx, dy):
        c, s = np.cos(yaw), np.sin(yaw)
        X = W @ np.array([[c, s], [-s, c]]) + [dx, dy]
        ij = np.floor((X - lo) / res).astype(int)
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < size[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < size[1])
        cst = np.full(len(X), cap, np.float32)
        cst[ok] = cost_map[ij[ok, 0], ij[ok, 1]]
        return float(cst.mean()), cst

    best = (cost(0.0, 0.0, 0.0)[0], 0.0, 0.0, 0.0)
    for span_yaw, st_yaw, span, st in ((8.0, 1.0, 0.10, 0.01), (1.0, 0.25, 0.01, 0.002), (0.25, 0.05, 0.002, 0.0005)):
        _, y0, x0, yy0 = best[0], best[1], best[2], best[3]
        for yaw in np.radians(np.arange(-span_yaw, span_yaw + 1e-9, st_yaw)) + y0:
            for dx in np.arange(-span, span + 1e-9, st) + x0:
                for dy in np.arange(-span, span + 1e-9, st) + yy0:
                    c_ = cost(yaw, dx, dy)[0]
                    if c_ < best[0]:
                        best = (c_, yaw, dx, dy)
    _, yaw, dx, dy = best
    cst = cost(yaw, dx, dy)[1]
    fit.wall_score = float((cst < 0.004).mean())
    if fit.wall_score < 0.35:
        fit.why = f"bin outline fit weak ({fit.wall_score:.2f}): kept calibration x, y, yaw"
        return fit
    c, s = np.cos(yaw), np.sin(yaw)
    R2 = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    T2 = np.eye(4)
    T2[:3, :3] = R2 @ T1[:3, :3]
    T2[:3, 3] = R2 @ T1[:3, 3] + [dx, dy, 0.0]
    fit.T, fit.dxy, fit.dyaw_deg = T2, (float(dx), float(dy)), float(np.degrees(yaw))
    return fit


# ---------------------------------------------------------------------- shape + yaw from the top face
def classify_top(xy):
    """Top-face points (n, 2) in m, seen from above -> (shape, yaw, centre, features).
    shape: cube | cylinder | triangle | tipped (a ridge, not a face) | None (too few points).
    yaw follows the sim's convention: cube faces at yaw + k*90 deg, triangle corners at yaw + 90 + k*120 deg."""
    import cv2
    if len(xy) < 25:
        return None, None, None, {}
    pts = (np.asarray(xy, np.float32) * 1000.0)                 # mm
    hull = cv2.convexHull(pts)
    A = float(cv2.contourArea(hull))
    if A < 1.0:
        return None, None, None, {}
    (rc, (rw, rh), rang) = cv2.minAreaRect(hull)
    (_, cr) = cv2.minEnclosingCircle(hull)
    At, tri = cv2.minEnclosingTriangle(hull)
    m = cv2.moments(hull)
    centre = np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]]) / 1000.0
    f = {"area_mm2": A, "rect": A / max(rw * rh, 1e-6), "circle": A / max(np.pi * cr * cr, 1e-6),
         "tri": A / max(float(At), 1e-6), "short_mm": float(min(rw, rh)), "long_mm": float(max(rw, rh))}
    if f["short_mm"] < 22.0 or f["short_mm"] < 0.45 * f["long_mm"]:
        return "tipped", None, centre, f
    # distance to the ideal (rect, circle, tri) fill ratios of each outline
    ideal = {"cube": (1.0, 0.637, 0.5), "cylinder": (0.785, 1.0, 0.605), "triangle": (0.5, 0.413, 1.0)}
    v = np.array([f["rect"], f["circle"], f["tri"]])
    d = {k: float(np.linalg.norm(v - np.array(i))) for k, i in ideal.items()}
    shape = min(d, key=d.get)
    f["dist"] = d
    yaw = 0.0
    if shape == "cube":
        a = np.radians(rang)
        yaw = float((a + np.pi / 4) % (np.pi / 2) - np.pi / 4)
    elif shape == "triangle":
        t = tri.reshape(3, 2) / 1000.0
        ang = np.arctan2(t[:, 1] - centre[1], t[:, 0] - centre[0]) - np.pi / 2
        # the three corners agree modulo 120 deg: circular mean of 3 * angle
        a3 = np.arctan2(np.sin(3 * ang).mean(), np.cos(3 * ang).mean()) / 3
        yaw = float((a3 + np.pi / 3) % (2 * np.pi / 3) - np.pi / 3)
    return shape, yaw, centre, f


# ---------------------------------------------------------------------- perception
class CameraPerception:
    """Drop-in for the oracle's perception: detect() -> Detections with .shape, .name, .yaw from head RGB-D."""

    def __init__(self, scene, calibration, hsv=None, log=None, refit_every_look=False):
        self.scene, self.cal0 = scene, calibration
        self.cal = copy.deepcopy(calibration)
        self.hsv = hsv or HSV
        self.log = log or (lambda *a: None)
        self.refit_every_look = refit_every_look
        self.H = scene.object_height()
        self.reset()

    def reset(self):
        self.fit = None
        self.tracks = []          # [name, color, xy]
        self._n = 0
        self._obs = None
        self.last = []            # detections of the last fresh look
        self.last_debug = {}

    def update(self, obs):
        self._obs = (obs.get("head_rgb"), obs.get("head_depth"))

    # ------------------------------------------------------------------ camera pose
    def ensure_pose(self, depth):
        if self.fit is not None and self.fit.ok and not self.refit_every_look:
            return self.fit
        fit = fit_head_pose(depth, self.cal0, self.scene)
        if fit.ok or self.fit is None:
            self.fit = fit
            self.cal.cams[CAM].T_pelvis_optical = fit.T
            self.log(f"[camera] head pose: tilt {fit.tilt_deg:.1f} deg, shift ({fit.dxy[0] * 100:+.1f}, "
                     f"{fit.dxy[1] * 100:+.1f}) cm, yaw {fit.dyaw_deg:+.1f} deg, walls {fit.wall_score:.2f} {fit.why}")
        return self.fit

    # ------------------------------------------------------------------ detection
    def detect(self, rgb=None, depth=None, debug=False):
        if rgb is None or depth is None:
            if self._obs is None or self._obs[0] is None or self._obs[1] is None:
                return ([], []) if debug else []
            rgb, depth = self._obs
        dets, rej = self._detect(np.asarray(rgb), np.asarray(depth))
        self._track(dets)
        self.last = dets
        return (dets, rej) if debug else dets

    def _detect(self, rgb, depth):
        import cv2
        sc = self.scene
        self.ensure_pose(depth)
        T = self.cal.cams[CAM].T_pelvis_optical
        P = _points(self.cal, depth) @ T[:3, :3].T.astype(np.float32) + T[:3, 3].astype(np.float32)   # (h, w, 3)
        h = (P[..., 2] - sc.counter_z) / self.H
        pm = (P[..., :2] - sc.origin[:2].astype(np.float32))[..., ::-1]   # mat coords: mat x = pelvis y, mat y = pelvis x
        W, D = sc.cfg["counter"]["mat_size"]
        ok = (depth > 150) & (depth < 2000) & (h > 0.3) & (h < 1.5)
        ok &= (pm[..., 0] > -0.02) & (pm[..., 0] < W + 0.02) & (pm[..., 1] > -0.02) & (pm[..., 1] < D + 0.02)
        half = np.asarray(sc.cfg["bins"]["outer_size"], float) / 2 + 0.006
        for ctr in sc.cfg["bins"]["centers"].values():
            ok &= ~((np.abs(pm[..., 0] - ctr[0]) <= half[0]) & (np.abs(pm[..., 1] - ctr[1]) <= half[1]))
        ok = ok.astype(np.uint8) * 255
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
        dets, rejected = [], []
        k3 = np.ones((3, 3), np.uint8)
        for color, ranges in self.hsv.items():
            m = np.zeros(hsv.shape[:2], np.uint8)
            for lo, hi in ranges:
                m |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            m = cv2.morphologyEx(m & ok, cv2.MORPH_OPEN, k3)
            n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
            for i in range(1, n):
                area = int(stats[i, cv2.CC_STAT_AREA])
                if area < 150:
                    continue
                v, u = np.nonzero(lab == i)
                p = P[v, u]
                z_top = np.percentile(p[:, 2], 92)
                sel = p[:, 2] >= z_top - 0.006
                top = p[sel]
                shape, yaw, centre, feat = classify_top(top[:, :2])
                if centre is None:
                    rejected.append((color, "too few top points", area))
                    continue
                ht = (float(np.median(top[:, 2])) - sc.counter_z) / self.H
                if not 0.6 <= ht <= 1.4:
                    rejected.append((color, f"top at {ht:.2f} object heights", area))
                    continue
                if feat["long_mm"] > 95 or feat["area_mm2"] < 250:
                    rejected.append((color, f"size {feat['long_mm']:.0f} mm / {feat['area_mm2']:.0f} mm2", area))
                    continue
                d = Detection(color, np.array([centre[0], centre[1], sc.counter_z + self.H]), area, int(sel.sum()),
                              "camera", yaw, (float(np.median(u)), float(np.median(v))))
                d.shape = shape                       # "tipped": no face grasp (not in the oracle's FACE_ALIGN)
                d.tipped = shape == "tipped"
                d.feat = feat
                d.bbox = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                          int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
                d.z_top = float(np.median(top[:, 2]))
                dets.append(d)
        return dets, rejected

    def _track(self, dets, radius=0.03):
        """Stable names across looks: a detection within `radius` of a known track of the same colour keeps its name
        (and its shape, if the new view could not tell)."""
        free = list(self.tracks)
        tracks = []
        for d in dets:
            best = None
            for t in free:
                if t[1] == d.color:
                    e = float(np.linalg.norm(t[2] - d.top[:2]))
                    if e < radius and (best is None or e < best[0]):
                        best = (e, t)
            if best is not None:
                free.remove(best[1])
                d.name = best[1][0]
            else:
                self._n += 1
                d.name = f"cam_{d.color}_{self._n}"
            tracks.append([d.name, d.color, d.top[:2].copy()])
        self.tracks = tracks + free          # unseen tracks are kept (occluded now, maybe back later)

    def masks(self, rgb):
        return {}
