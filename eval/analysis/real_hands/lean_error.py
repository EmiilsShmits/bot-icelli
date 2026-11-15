# Run from the repo root: PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python eval/analysis/real_hands/lean_error.py
"""If the torso leans by `a` deg relative to the table (camera exact on its mount), what object-position error do
(1) Aalto's calibration as-is, (2) table-plane levelling (v1.2..v1.6), (3) levelling + hand yaw/xy fit (V16_CALIB=hands)
give? Synthetic points, the real HandEye.fit code. Table plane in the pelvis frame tilts up away from the robot."""
import json, sys
import numpy as np
sys.path.insert(0, "policy")
from aaltonomous.interface.calibration import Calibration
from decision_oracle.handeye import HandEye
from decision_oracle.camera import _rot_a_to_b
cal = Calibration.load(); he = HandEye(); T0 = cal._T("head")
poses = json.load(open("artifacts/real_frames/poses.json"))
qs = [poses[k] for k in ("g1_junction_drop_2:0", "g1_pick_cube:0", "g1_pick_cube:8062")]
table_z, piv_x = -0.03, 0.45        # nominal table top in the pelvis frame (scene), tilt pivot at the work area
rng = np.random.default_rng(0)
def plane_z(x, a): return table_z + np.tan(np.radians(a)) * (x - piv_x)
for a in (0, 4, 8, 12):
    out = {"calib": [], "level": [], "hands": []}
    for q in qs:
        Tt = T0                                   # the camera really is where calibration says (relative to the arms)
        tx, ty = rng.uniform(0.15, 0.85, 6000), rng.uniform(-0.4, 0.4, 6000)
        tab = np.c_[tx, ty, plane_z(tx, a)]
        ox, oy = rng.uniform(0.30, 0.60, 50), rng.uniform(-0.20, 0.20, 50)
        obj = np.c_[ox, oy, plane_z(ox, a) + 0.045]    # object top centres (approx; ignores the 8 deg tilt of the block)
        H, N = he.cloud(q[:14], q[14:]); H = H[np.einsum("ij,ij->i", N, Tt[:3, 3] - H) > 0]
        H = H[H[:, 2] > plane_z(H[:, 0], a) + 0.02]
        world = np.vstack([tab, H])
        Popt = (world - Tt[:3, 3]) @ Tt[:3, :3]        # what the depth camera measures
        Oopt = (obj - Tt[:3, 3]) @ Tt[:3, :3]
        # (1) calibration as-is
        e = lambda T: np.linalg.norm((Oopt @ T[:3, :3].T + T[:3, 3] - obj)[:, :2], axis=1)
        out["calib"].append(e(T0))
        # (2) levelling on the table plane (rotate about the camera, table at table_z)
        Q = Popt[:len(tab)] @ T0[:3, :3].T + T0[:3, 3]
        c0 = Q.mean(0); n = np.linalg.svd(Q - c0)[2][2]; n = n if n[2] > 0 else -n
        R1 = _rot_a_to_b(n, np.array([0, 0, 1.0]))
        Th = np.eye(4); Th[:3, :3] = R1 @ T0[:3, :3]; Th[:3, 3] = T0[:3, 3]
        Th[2, 3] += table_z - float((R1 @ (c0 - T0[:3, 3]) + T0[:3, 3])[2])
        out["level"].append(e(Th))
        r = he.fit(Popt, Th, q[:14], q[14:], table_z)
        out["hands"].append(e(r["T"]) if r["ok"] else np.full(len(obj), np.nan))
        if not r["ok"]: print("  hand fit failed:", r["why"])
    print(f"lean {a:2d} deg: " + ", ".join(f"{k} {np.nanmedian(np.concatenate(v))*1000:.0f} mm (p90 {np.nanpercentile(np.concatenate(v), 90)*1000:.0f})" for k, v in out.items()))
