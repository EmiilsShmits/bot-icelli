# Run from the repo root: PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python eval/analysis/real_hands/pose.py
"""Which head-camera pose (relative to the pelvis/arms) explains where the real Dex3 hands appear?
For all 61 real head frames: project the FK hand model through a camera pose and score how many points land on dark
(hand) pixels. Compare Aalto's calibration, the venue-look pose (9 deg down on the mount) and the best global turn."""
import json, sys
import numpy as np, yaml
from PIL import Image
from scipy.ndimage import distance_transform_edt, binary_opening
sys.path.insert(0, "policy"); sys.path.insert(0, "sim/mujoco")
from aaltonomous.interface.calibration import Calibration
from decision_oracle.handeye import HandEye
from build import head_T_pelvis_optical
cal = Calibration.load(); he = HandEye(); T0 = cal._T("head")
K = np.array([[604.827, 0, 325.042], [0, 604.298, 250.927], [0, 0, 1]])
Tv = head_T_pelvis_optical(yaml.safe_load(open("sim/mujoco/venue_measured.yaml")))
poses = json.load(open("artifacts/real_frames/poses.json"))
black = np.array(["hand" in n for n in he.names])
frames = []
for key, q in poses.items():
    ds, idx = key.rsplit(":", 1)
    try:
        im = np.asarray(Image.open(f"artifacts/real_frames/{ds}_head_{int(idx):06d}.jpg").convert("HSV")).astype(int)
    except FileNotFoundError:
        continue
    dt = distance_transform_edt(~binary_opening(im[..., 2] < 70))
    P, N = he.cloud(q[:14], q[14:])
    m = black[he.link] & (np.einsum("ij,ij->i", N, T0[:3, 3] - P) > 0)
    frames.append((key, P[m][::3], dt))

def r(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]

def score(T, which=None):
    ds, fs = [], []
    for key, P, dt in frames:
        if which and not key.startswith(which):
            continue
        X = (P - T[:3, 3]) @ T[:3, :3]
        X = X[X[:, 2] > 0.05]
        uv = X @ K.T; uv = uv[:, :2] / uv[:, 2:]
        ok = (uv[:, 0] >= 0) & (uv[:, 0] < 640) & (uv[:, 1] >= 0) & (uv[:, 1] < 480)
        if ok.sum() < 200:
            continue
        d = dt[uv[ok, 1].astype(int), uv[ok, 0].astype(int)]
        ds.append(np.mean(np.minimum(d, 30))); fs.append(np.mean(d < 3))
    return np.mean(ds), np.mean(fs), len(ds)

def turned(p, y, ro):
    T = T0.copy(); T[:3, :3] = T0[:3, :3] @ r("x", -p) @ r("z", ro) @ r("y", y); return T

print("Aalto calibration      dist %.1f px, on-hand %.2f (%d frames)" % score(T0))
print("venue look (9 deg down) dist %.1f px, on-hand %.2f (%d frames)" % score(Tv))
for which in (None, "g1_pick_cube", "g1_junction_drop_2"):
    best = min((score(turned(p, y, ro), which)[0], p, y, ro) for p in np.arange(-6, 12.1, 1.0) for y in np.arange(-6, 6.1, 1.0) for ro in (-2, 0, 2))
    _, p0, y0, r0 = best
    best = min((score(turned(p, y, ro), which)[0], p, y, ro) for p in np.arange(p0 - 1, p0 + 1.01, 0.25) for y in np.arange(y0 - 1, y0 + 1.01, 0.25) for ro in np.arange(r0 - 2, r0 + 2.01, 0.5))
    s = score(turned(*best[1:]), which)
    print(f"best turn [{which or 'all'}]: pitch down {best[1]:.2f}, yaw {best[2]:.2f}, roll {best[3]:.2f} deg -> dist {s[0]:.1f} px, on-hand {s[1]:.2f} ({s[2]} frames)")
