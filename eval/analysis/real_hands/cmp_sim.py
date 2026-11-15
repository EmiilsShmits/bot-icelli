"""MuJoCo, ground truth known: camera pose error and reach error of ours vs Marcus's camera_from_arms, same frames."""
import importlib.util, sys
import numpy as np
S = sys.argv[1]
sys.path[:0] = ["sim/mujoco", "policy"]
import build as B, dr as DR
from backend import MujocoBackend
from aaltonomous.interface import tasks
from aaltonomous.interface.calibration import Calibration
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from aaltonomous.baselines.classical.config import load_config
from decision_oracle.handeye import HandEye
spec = importlib.util.spec_from_file_location("selfcal", f"{S}/marcus/repo/adk_agents/robot_sorter/selfcal.py")
SC = importlib.util.module_from_spec(spec); sys.modules["selfcal"] = SC; spec.loader.exec_module(SC)
cal = Calibration.load(); cam = cal.cams["head"]; T0 = cal._T("head"); K = np.asarray(cam.K, float)
he, kin = HandEye(), ArmKinematics(load_config())
mods = [SC.ArmModel(kin, urdf=f"{S}/urdf/g1_body29_hand14.urdf", hands=h) for h in (False, True)]
W = np.array([[x, y, 0.04] for x in (0.25, 0.4, 0.55) for y in (-0.2, 0.0, 0.2)])

def err(T, Tt):
    if T is None: return (np.nan, np.nan)
    dR = T[:3, :3] @ Tt[:3, :3].T
    rot = np.degrees(np.arccos(np.clip((np.trace(dR) - 1) / 2, -1, 1)))
    # a point the true camera sees at W, placed by the estimate
    po = (W - Tt[:3, 3]) @ Tt[:3, :3]
    return rot, float(np.linalg.norm(po @ T[:3, :3].T + T[:3, 3] - W, axis=1).max() * 1000)

res = {"ours": [], "ours75": [], "marcus": []}
for mode in ("none", "lean", "bins"):
    for seed in (7000, 7003, 7008, 7011):
        cfg, cols, tip, p = DR.sample(B.load_cfg(), seed, mode)
        be = MujocoBackend(cfg=cfg, colors=cols, tip=tip)
        lay = tasks.sample_layout(np.random.default_rng(seed), shapes=tuple(be.sc.cfg["objects"]["shapes"]), **be.sc.layout_kwargs())
        be.reset_scene(lay); im = be.images(); aq, _, hq = be.joints()
        Tt = B.head_T_pelvis_optical(cfg)
        depth = im["head_depth"].astype(float)
        P = SC.optical_points(depth, K, cam.depth_scale, step=2); plane = SC.table_plane(P); h = P @ plane[0] + plane[1]
        P4 = SC.optical_points(depth, K, cam.depth_scale, step=4); h4 = P4 @ plane[0] + plane[1]
        out = []
        for key, mh in (("ours", 0.015), ("ours75", 0.075)):
            r = he.fit_pose(P4, T0, aq, hq, off_table=(h4 > mh) & (h4 < 0.6))
            e = err(r["T"] if r["ok"] else None, Tt); res[key].append(e); out.append(f"{key} {e[0]:.2f} deg {e[1]:.1f} mm")
        A = P[(h > SC.ABOVE_TABLE_M) & (h < 0.6)]; A = A[:: max(1, len(A) // 4000)]
        best = None
        for m in mods:
            fm = SC.camera_from_arms([(A, aq, hq)], m, SC.starts(T0))
            sc = (fm.ok and fm.matched >= SC.MIN_MATCHED and fm.rms_m <= SC.MAX_RMS_M, fm.matched - fm.rms_m / 0.01 if fm.ok else -1)
            if best is None or sc > best[0]: best = (sc, fm)
        e = err(best[1].T if best[0][0] else None, Tt); res["marcus"].append(e); out.append(f"marcus {e[0]:.2f} deg {e[1]:.1f} mm")
        print(f"{mode:5s} {seed} lean {cfg['robot'].get('lean_deg', 0):4.1f}: " + " | ".join(out), flush=True)
for k, v in res.items():
    a = np.array(v, float)
    print(f"{k:7s} ok {np.isfinite(a[:, 0]).sum()}/{len(a)}  rot err median {np.nanmedian(a[:, 0]):.2f} max {np.nanmax(a[:, 0]):.2f} deg | "
          f"work-area error median {np.nanmedian(a[:, 1]):.1f} max {np.nanmax(a[:, 1]):.1f} mm")
