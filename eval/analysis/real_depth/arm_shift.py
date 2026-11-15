"""V16_ARM_SHIFT on Aalto's real frames (drop 3): each arm measured against its own model after the two-arm fit.

A. frame 0 of the 15 episodes, through CameraPerception as the policy runs it: the correction each arm would get.
B. (with drop3_mid.npz from extract_mid.py) frames later in the episode where an arm is still and reaching out:
   how far the real hand is from the model there, without the correction and with the one measured at frame 0.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/arm_shift.py \
        artifacts/real_frames/drop3 [artifacts/real_frames/drop3/drop3_mid.npz]
"""
import sys, time, numpy as np
from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene
from aaltonomous.baselines.classical.config import load_config
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from decision_oracle import camera as C
from decision_oracle.handeye import HandEye
import lean

src = sys.argv[1]
st0 = np.load(f"{src}/state0.npy")
he, cal, kin, sc = HandEye(), Calibration.load(), ArmKinematics(load_config()), Scene.load()
cam = C.CameraPerception(sc, cal, log=lambda m: None)
cam.lean, cam.kins, cam.arm_shift = he, (lambda: [kin]), True
print("A. frame 0 of each episode: real hand minus model hand per arm (cm, table frame), as the policy would correct it")
home, T_arm, T_tab = {}, {}, {}
for ep in range(15):
    cam.reset()
    cam._joints = (st0[ep, :14].astype(float), st0[ep, 14:].astype(float))
    t = time.time()
    f = cam.ensure_pose(np.load(f"{src}/depth_ep{ep:02d}_start.npy").astype(np.uint16))
    a = f.arm_pose or {}
    print("ep%02d lean %s deg | %s | fit + per-arm %.1f s" % (ep, a.get("lean_deg"), a.get("hand_off_cm"), time.time() - t), flush=True)
    if f.arm_shift is not None and f.arm_T is not None:
        Ri = np.asarray(kin.base if getattr(kin, "base", None) is not None else np.eye(4))[:3, :3].T
        home[ep] = {s: Ri @ v for s, v in f.arm_shift.items()}          # back in the arm frame
        T_arm[ep], T_tab[ep] = f.arm_T, np.asarray(f.T, float)
R = np.array([home[e]["right"] for e in home]); L = np.array([home[e]["left"] for e in home])
print("   right: median (%+.1f %+.1f %+.1f) cm, size %.1f cm (max %.1f); left: size %.1f cm (max %.1f)" % (
    *(100 * np.median(R, 0)), 100 * np.median(np.linalg.norm(R, axis=1)), 100 * np.linalg.norm(R, axis=1).max(),
    100 * np.median(np.linalg.norm(L, axis=1)), 100 * np.linalg.norm(L, axis=1).max()))
cam.reset()
if len(sys.argv) < 3:
    sys.exit()

z0 = np.load(sys.argv[2]); z = {k: z0[k] for k in z0.files}
print("\nB. later frames, arm still (< 0.12 rad/s) and its grasp point >= 29 cm in front of the pelvis")
rows = []
for i in range(len(z["ep"])):
    ep = int(z["ep"][i])
    if ep not in home or z["fr"][i] < 15 or z["speed"][i].min() > 0.12:
        continue
    st = z["state"][i]
    g = {s: lean._ORIG["grasp_pose"](kin, s, st[:14])[0] if lean._ORIG else kin.grasp_pose(s, st[:14])[0] for s in ("left", "right")}
    if max(g["left"][0], g["right"][0]) < 0.29:
        continue
    P = C._points(cal, z["depth"][i], step=3).reshape(-1, 3)
    d = z["depth"][i][::3, ::3].reshape(-1)
    P = P[(d > 150) & (d < 1200)]
    h = P @ T_tab[ep][2, :3] + T_tab[ep][2, 3]
    r = he.arm_shifts(P[h > sc.counter_z + 0.015], T_arm[ep], st[:14], st[14:], deadband=0.0)
    for si, s in enumerate(("left", "right")):
        if z["speed"][i][si] <= 0.12 and g[s][0] >= 0.29 and r[s]["d"] is not None:
            rows.append((s, ep, r[s]["d"], r[s]["d"] - home[ep][s]))
for s in ("left", "right"):
    Q = [q for q in rows if q[0] == s]
    if not Q:
        continue
    raw, cor = np.array([q[2] for q in Q]), np.array([q[3] for q in Q])
    n = lambda v: np.linalg.norm(v, axis=1)
    print("  %-5s %3d frames, episodes %s" % (s, len(Q), sorted({q[1] for q in Q})))
    print("     as v1.6 now:        hand off by median %.1f cm (90 %% under %.1f), direction (%+.1f %+.1f %+.1f) cm" % (100 * np.median(n(raw)), 100 * np.percentile(n(raw), 90), *(100 * np.median(raw, 0))))
    print("     with V16_ARM_SHIFT: hand off by median %.1f cm (90 %% under %.1f), direction (%+.1f %+.1f %+.1f) cm" % (100 * np.median(n(cor)), 100 * np.percentile(n(cor), 90), *(100 * np.median(cor, 0))))
    for ep in sorted({q[1] for q in Q}):
        a, b = np.array([q[2] for q in Q if q[1] == ep]), np.array([q[3] for q in Q if q[1] == ep])
        print("       ep%02d n=%3d  %.1f -> %.1f cm" % (ep, len(a), 100 * np.median(n(a)), 100 * np.median(n(b))))
