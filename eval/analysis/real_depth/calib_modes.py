"""All three calibration modes on the first frame of every drop-3 episode: one line per episode."""
import sys, numpy as np
from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene
from decision_oracle import camera as C
from decision_oracle.handeye import HandEye
src = sys.argv[1]
cal = Calibration.load(); he = HandEye(); st = np.load(f"{src}/state0.npy")
T0 = np.asarray(cal._T(C.CAM), float)
rows = []
for ep in range(15):
    depth = np.load(f"{src}/depth_ep{ep:02d}_start.npy").astype(np.uint16)
    arm_q, hand_q = st[ep, :14], st[ep, 14:]
    r = {"ep": ep}
    sc = Scene.load(); sc.cfg["bins"]["wall_height"] = 0.07
    f = C.fit_head_pose_levelled(depth, cal, sc)
    r.update(b_ok=f.ok and f.wall_score >= 0.35, tilt=f.tilt_deg, dx=100 * f.dxy[0], dy=100 * f.dxy[1], wall=f.wall_score,
             cam_move=100 * np.linalg.norm(np.asarray(f.T)[:3, 3] - T0[:3, 3]))
    sc = Scene.load(); sc.cfg["bins"]["wall_height"] = 0.07
    f = C.fit_head_pose(depth, cal, sc, hands=(he, arm_q, hand_q))
    h = f.hands or {}
    r.update(h_ok=bool(h.get("ok")), h_shift=100 * float(np.hypot(*h.get("dxy", (0, 0)))), h_frac=h.get("frac"), h_why=h.get("why", ""),
             bins=(f.bins or {}).get("why", ""))
    sc = Scene.load(); sc.cfg["bins"]["wall_height"] = 0.07
    f = C.fit_head_pose(depth, cal, sc, lean=(he, arm_q, hand_q))
    a = f.arm_pose or {}
    r.update(l_ok=bool(a.get("ok")), l_frac=a.get("frac"), l_move=a.get("move_mm"), l_lean=a.get("lean_deg"), l_base=a.get("base"), l_why=a.get("why", ""))
    rows.append(r)
    print("ep%02d | bins fit: %s tilt %.1f dx %+.1f dy %+.1f cm wall %.2f, camera moved %.1f cm | hands: %s shift %.1f cm frac %s %s | lean: %s frac %s move %s mm lean %s deg -> %s %s"
          % (ep, "ok" if r["b_ok"] else "NO", r["tilt"], r["dx"], r["dy"], r["wall"], r["cam_move"], "ok" if r["h_ok"] else "NO", r["h_shift"], r["h_frac"],
             ("(" + r["bins"][:40] + ")") if r["h_ok"] else "", "ok" if r["l_ok"] else "NO", r["l_frac"], r["l_move"], r["l_lean"], r["l_base"], ""), flush=True)
n = len(rows)
print("\nSUMMARY over %d real frames: bin-wall fit ok %d | hands mode ok %d | lean mode arm fit ok %d, base moved %d" % (
    n, sum(r["b_ok"] for r in rows), sum(r["h_ok"] for r in rows), sum(r["l_ok"] for r in rows), sum(r["l_base"] == "moved" for r in rows)))
print("bin-wall fit: dx %.1f..%.1f cm (search limit +-10, then +-1.2), wall score %.2f..%.2f (needs 0.35), camera moved %.1f..%.1f cm (v1.4 / ADK accept <= 6)" % (
    min(r["dx"] for r in rows), max(r["dx"] for r in rows), min(r["wall"] for r in rows), max(r["wall"] for r in rows), min(r["cam_move"] for r in rows), max(r["cam_move"] for r in rows)))
