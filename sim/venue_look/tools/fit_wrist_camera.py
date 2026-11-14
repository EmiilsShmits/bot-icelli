"""Estimate where a wrist camera sits and where it looks, from real wrist frames.

    python fit_wrist_camera.py <left|right> <real_dir> <g1_body29_hand14.urdf> [--n 4000] [--seed 0]

<real_dir> = output of real_frames.py (use about 30 frames per dataset: `--n 30`). For every frame the robot model
gives the wrist pose from the recorded joint angles. The bins (scene.yaml, 7.5 cm walls) are projected through a
candidate camera fixed to the <side>_wrist_yaw_link and should cover the orange paper in the real image. Random
search, then hill-climbing from the 12 best. Prints the best 8 as: position x, y, z in the link frame (m, mirrored
for the right hand), pitch down, yaw towards the thumb, roll, horizontal field of view (degrees): the same values
as `camera.wrist` in venue.yaml.

Read the result as a range, not a number: the direction comes out similar across the best candidates, the position
and the lens do not. Needs pinocchio (`pip install pin`; the sim machine's `isaac` environment has it) and the URDF
from Aalto's clone: third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf. About 2 min per hand with --n 4000.
"""
import argparse, json
import numpy as np, cv2
import pinocchio as pin
import fit_head_camera as geo

ap = argparse.ArgumentParser()
ap.add_argument("side", choices=["left", "right"]); ap.add_argument("real"); ap.add_argument("urdf")
ap.add_argument("--n", type=int, default=4000); ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
side = a.side
S = 4                                        # work at 160 x 120

# wrist pose in the pelvis frame for every recorded pose
ARM = ["shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch", "wrist_yaw"]
JOINTS = [f"left_{j}_joint" for j in ARM] + [f"right_{j}_joint" for j in ARM] + \
         [f"left_hand_{j}_joint" for j in ("thumb_0", "thumb_1", "thumb_2", "middle_0", "middle_1", "index_0", "index_1")] + \
         [f"right_hand_{j}_joint" for j in ("thumb_0", "thumb_1", "thumb_2", "index_0", "index_1", "middle_0", "middle_1")]
m = pin.buildModelFromUrdf(a.urdf); d = m.createData()
pel, wrist = m.getFrameId("pelvis"), m.getFrameId(f"{side}_wrist_yaw_link")


def orange(img):
    h = cv2.cvtColor(img, cv2.COLOR_BGR2HSV); H, Sa, V = h[..., 0], h[..., 1], h[..., 2]
    mask = (((H < 11) | (H > 172)) & (Sa > 85) & (V > 110)).astype(np.float32)
    return cv2.GaussianBlur(cv2.resize(mask, (640 // S, 480 // S), interpolation=cv2.INTER_AREA), (0, 0), 3)


REAL, POSE = [], []
for key, qv in json.load(open(f"{a.real}/poses.json")).items():
    ds, fr = key.split(":")
    img = cv2.imread(f"{a.real}/{ds}_{side}_wrist_{int(fr):06d}.jpg")
    if img is None: continue
    q = pin.neutral(m)
    for n, v in zip(JOINTS, qv): q[m.joints[m.getJointId(n)].idx_q] = v
    pin.forwardKinematics(m, d, q); pin.updateFramePlacements(m, d)
    T = d.oMf[pel].inverse() * d.oMf[wrist]
    REAL.append(orange(img)); POSE.append((T.rotation.copy(), T.translation.copy()))
print(f"{len(REAL)} frames")

QUADS = []                                   # the bins' outer walls in the pelvis frame, with outward normals
for bot, top in geo.bins(0.075).values():
    cen = np.mean(bot + top, 0)
    for k in range(4):
        quad = np.array([bot[k], bot[(k + 1) % 4], top[(k + 1) % 4], top[k]]); n = quad.mean(0) - cen; n[2] = 0
        QUADS.append((quad, n / np.linalg.norm(n)))


def cam(p):
    """Camera position and rotation in the wrist frame; same convention as wrist_camera_cfg() in patch_aalto.py."""
    x, y, z, pitch, yaw, roll, hfov = p
    mir = np.array([1.0, 1.0 if side == "left" else -1.0, 1.0])
    pa, ya = np.radians(pitch), np.radians(yaw)
    fwd = np.array([np.cos(pa) * np.cos(ya), -np.cos(pa) * np.sin(ya), -np.sin(pa)]) * mir
    right = np.cross(fwd, [0, 0, 1.0]); nr = np.linalg.norm(right)
    right = np.array([0, -1.0, 0]) * mir if nr < 1e-6 else right / nr
    R = np.stack([right, np.cross(fwd, right), fwd], 1)
    r = np.radians(roll) * mir[1]
    return np.array([x, y, z]) * mir, R @ np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])


def render(p, i):
    c, R = cam(p); f = (320 / np.tan(np.radians(p[6]) / 2)) / S
    Rw, pw = POSE[i]; Rc = Rw @ R; pc = pw + Rw @ c
    im = np.zeros((480 // S, 640 // S), np.float32)
    for quad, n in QUADS:
        if (pc - quad.mean(0)) @ n <= 0: continue
        P = (quad - pc) @ Rc
        if (P[:, 2] < 0.03).any(): continue
        uv = np.stack([320 / S + f * P[:, 0] / P[:, 2], 240 / S + f * P[:, 1] / P[:, 2]], 1)
        if np.abs(uv).max() > 3000: continue
        cv2.fillConvexPoly(im, np.round(uv).astype(np.int32), 1.0)
    return cv2.GaussianBlur(im, (0, 0), 3)


def score(p):                                # soft Dice overlap, averaged over the frames (1 = perfect)
    s = 0.0
    for i in range(len(REAL)):
        x, y = render(p, i), REAL[i]
        s += 2 * (x * y).sum() / ((x * x).sum() + (y * y).sum() + 1e-6)
    return s / len(REAL)


rng = np.random.default_rng(a.seed)
lo = np.array([-0.03, -0.07, -0.08, -80, -80, -180, 60]); hi = np.array([0.10, 0.07, 0.11, 80, 80, 180, 100])
cands = sorted(((score(p), p) for p in (lo + (hi - lo) * rng.random(7) for _ in range(a.n))), key=lambda t: -t[0])
best = []
for s, p in cands[:12]:
    st = np.array([0.01, 0.01, 0.01, 6, 6, 8, 5])
    for it in range(400):
        q = np.clip(p + st * rng.normal(size=7), lo, hi); sq = score(q)
        if sq > s: p, s = q, sq
        if it % 100 == 99: st *= 0.6
    best.append((s, p))
np.set_printoptions(precision=3, suppress=True)
for s, p in sorted(best, key=lambda t: -t[0])[:8]:
    print(f"score {s:.3f}  x,y,z {p[:3]}  pitch {p[3]:.0f} yaw {p[4]:.0f} roll {p[5]:.0f} hfov {p[6]:.0f}")
