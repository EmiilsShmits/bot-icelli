"""Real drop 3 (head depth): our HandEye.fit_pose vs Marcus's selfcal.camera_from_arms on the same still moments."""
import glob, importlib.util, sys, time
import numpy as np
S = sys.argv[1]
sys.path[:0] = ["policy"]
from aaltonomous.interface.calibration import Calibration
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from aaltonomous.baselines.classical.config import load_config
from decision_oracle.handeye import HandEye
spec = importlib.util.spec_from_file_location("selfcal", f"{S}/marcus/repo/adk_agents/robot_sorter/selfcal.py")
SC = importlib.util.module_from_spec(spec); sys.modules["selfcal"] = SC; spec.loader.exec_module(SC)
cal = Calibration.load(); cam = cal.cams["head"]; T0 = cal._T("head"); K = np.asarray(cam.K, float)
he = HandEye()
kin = ArmKinematics(load_config())
mod_h = SC.ArmModel(kin, urdf=f"{S}/urdf/g1_body29_hand14.urdf", hands=True)
mod_a = SC.ArmModel(kin, urdf=f"{S}/urdf/g1_body29_hand14.urdf", hands=False)

def angles(T):                                   # Marcus's convention: camera axes x pitch, y pan, z roll
    R = T0[:3, :3].T @ T[:3, :3]
    return (np.degrees(np.arctan2(R[2, 1], R[2, 2])), np.degrees(np.arcsin(np.clip(-R[2, 0], -1, 1))),
            np.degrees(np.arctan2(R[1, 0], R[0, 0])), np.linalg.norm(T[:3, 3] - T0[:3, 3]) * 1000)

def table_tilt(T, plane):
    n = T[:3, :3] @ plane[0]                      # table normal in the arm frame
    n = n if n[2] > 0 else -n
    return np.degrees(np.arccos(np.clip(n[2], -1, 1))), np.degrees(np.arctan2(-n[1], -n[0]))

rows = []
for f in sorted(glob.glob(f"{S}/d3/*.npz")):
    z = np.load(f); depth, st = z["depth"].astype(float) / 16.0, z["state"]
    aq, hq = st[:14], st[14:]
    P = SC.optical_points(depth, K, cam.depth_scale, step=2)
    plane = SC.table_plane(P)
    if plane is None:
        print(f.split("/")[-1], "no table"); continue
    h = P @ plane[0] + plane[1]
    # ours: points >1.5 cm above the table (step 4 like the policy)
    P4 = SC.optical_points(depth, K, cam.depth_scale, step=4); h4 = P4 @ plane[0] + plane[1]
    t = time.time(); r = he.fit_pose(P4, T0, aq, hq, off_table=(h4 > float(__import__("os").environ.get("MIN_H", "0.015"))) & (h4 < 0.6)); t_o = time.time() - t
    # Marcus: above 7.5 cm, both models, his starts from the calibration (no table-fit guess here)
    A = P[(h > SC.ABOVE_TABLE_M) & (h < 0.6)]; A = A[:: max(1, len(A) // 4000)]
    t = time.time(); best = None
    for m in (mod_a, mod_h):
        fm = SC.camera_from_arms([(A, aq, hq)], m, SC.starts(T0))
        sc = (fm.ok and fm.matched >= SC.MIN_MATCHED and fm.rms_m <= SC.MAX_RMS_M, fm.matched - fm.rms_m / 0.01 if fm.ok else -1)
        if best is None or sc > best[0]: best = (sc, fm, "hands" if m.hands else "arms")
    t_m = time.time() - t
    fm = best[1]
    o = angles(r["T"]) if r["ok"] else (np.nan,) * 4
    mm = angles(fm.T) if fm.ok else (np.nan,) * 4
    dT = np.linalg.inv(r["T"]) @ fm.T if (r["ok"] and fm.ok) else None
    agree = (np.degrees(np.arccos(np.clip((np.trace(dT[:3, :3]) - 1) / 2, -1, 1))), np.linalg.norm(r["T"][:3, 3] - fm.T[:3, 3]) * 1000) if dT is not None else (np.nan, np.nan)
    to = table_tilt(r["T"], plane) if r["ok"] else (np.nan, np.nan); tm = table_tilt(fm.T, plane) if fm.ok else (np.nan, np.nan)
    rows.append(o + mm + agree + to + tm)
    print(f"{f.split('/')[-1]}: OURS ok={r['ok']} p/pan/r {o[0]:+.1f}/{o[1]:+.1f}/{o[2]:+.1f} deg, {o[3]:.0f} mm, table tilt {to[0]:.1f} dir {to[1]:+.0f}, "
          f"frac {r.get('frac')} rms {r.get('rms_mm')} [{t_o:.1f}s]  |  MARCUS({best[2]}) ok={best[0][0]} {mm[0]:+.1f}/{mm[1]:+.1f}/{mm[2]:+.1f}, {mm[3]:.0f} mm, "
          f"tilt {tm[0]:.1f} dir {tm[1]:+0.0f}, on-arm {fm.matched:.2f} rms {fm.rms_m*1000:.1f} [{t_m:.1f}s]  |  agree {agree[0]:.2f} deg {agree[1]:.0f} mm", flush=True)
a = np.array(rows)
names = ["ours pitch", "ours pan", "ours roll", "ours mm", "marcus pitch", "marcus pan", "marcus roll", "marcus mm", "agree deg", "agree mm", "ours tilt", "ours dir", "marcus tilt", "marcus dir"]
for i, n in enumerate(names):
    print(f"{n:13s} median {np.nanmedian(a[:, i]):+7.2f}  std {np.nanstd(a[:, i]):5.2f}  n {np.isfinite(a[:, i]).sum()}")
