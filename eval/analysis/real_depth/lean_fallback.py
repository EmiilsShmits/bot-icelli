"""v1.7's lean fallback on Aalto's 15 real frames (drop 3), through CameraPerception as the policy uses it: which arm fit
each episode ends up using, and how far the base lifts a grasp 35 cm in front of the pelvis.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lean_fallback.py \
        artifacts/real_frames/drop3
"""
import sys, time, numpy as np
from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene
from aaltonomous.baselines.classical.config import load_config
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from decision_oracle import camera as C
from decision_oracle.handeye import HandEye
src = sys.argv[1]
st = np.load(f"{src}/state0.npy")
he = HandEye()
def cam_kin():
    sc = Scene.load(); kin = ArmKinematics(load_config())
    cam = C.CameraPerception(sc, Calibration.load(), log=lambda m: None)
    cam.lean, cam.kins = he, (lambda: [kin])
    cam.lean_fallback = "--v16" not in sys.argv              # v1.7's fallback; --v16: without it
    return cam, kin, sc
def look(cam, kin, sc, ep):
    cam.reset()                                                    # new episode
    cam._joints = (st[ep, :14].astype(float), st[ep, 14:].astype(float))
    t = time.time()
    f = cam.ensure_pose(np.load(f"{src}/depth_ep{ep:02d}_start.npy").astype(np.uint16))
    A = getattr(kin, "base", None)
    lift = None
    if A is not None and not np.allclose(A, np.eye(4)):
        W = np.array([[0.35, y, sc.counter_z + 0.03] for y in (-0.15, 0.15)])
        Ai = np.linalg.inv(A)
        lift = float(((W @ Ai[:3, :3].T + Ai[:3, 3]) - W)[:, 2].mean() * 100)
    a = f.arm_pose or {}
    print("ep%02d %-34s | %-52s | this look: lean %s deg, move %s mm | grasp lifted at 35 cm: %s cm  (%.0f s)" % (
        ep, a.get("base"), a.get("source"), a.get("lean_deg"), a.get("move_mm"), "none" if lift is None else "%+.1f" % lift, time.time() - t), flush=True)
    return lift, a
print("A. 15 episodes in order, one policy process"); cam, kin, sc = cam_kin()
lifts = [look(cam, kin, sc, ep)[0] for ep in range(15)]
print("   episodes with a correction: %d/15; lift at 35 cm: min %+.1f max %+.1f cm" % (sum(l is not None for l in lifts), min(l for l in lifts if l is not None), max(l for l in lifts if l is not None)))
print("B. the rejected frame (ep14) as the FIRST episode of a fresh process"); cam, kin, sc = cam_kin(); look(cam, kin, sc, 14)
print("C. arm fit fails outright (arms hidden) in an episode after a good one"); cam, kin, sc = cam_kin(); look(cam, kin, sc, 3)
orig = he.fit_pose; he.fit_pose = lambda *a, **k: {"ok": False, "T": np.eye(4), "why": "arms not in view (simulated)"}
look(cam, kin, sc, 5)
print("D. arm fit fails outright in the first episode (nothing to fall back on)"); cam, kin, sc = cam_kin(); look(cam, kin, sc, 5)
he.fit_pose = orig
