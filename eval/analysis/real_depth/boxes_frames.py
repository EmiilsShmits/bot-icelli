"""The box finder (policy/decision_oracle/boxes_v16.py) on saved depth frames: Aalto's real ones (frame 0 of every
drop-3 episode, depth_ep*_start.npy from extract.py) or sim ones (f_*.npz with rgb, depth, state).

Prints, per frame: where the row's near wall is, the wall height, the box depth, the gaps, each box's centre against
scene.yaml (in the frame of the bin-wall camera fit), and whether a lid was seen (none of these frames has one).
With an output folder, also writes a top-down picture per frame with the boxes found drawn in (white: found; black
cross: scene.yaml).

Usage (repo root, .venv):
    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/boxes_frames.py \
        artifacts/real_frames/drop3 [out dir]
"""
import glob
import sys
import time

import numpy as np

from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene
from decision_oracle import boxes_v16 as B
from decision_oracle import camera as C
LEVELLED = getattr(C, "fit_head_pose_levelled", C.fit_head_pose)   # levelled table-frame fit (older camera.py: fit_head_pose)

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else None
sc, cal = Scene.load(), Calibration.load()
nom = {n: sc.mat_to_pelvis(np.r_[xy, 0.0])[:2] for n, xy in sc.cfg["bins"]["centers"].items()}
rows, n_ok, n_all = [], 0, 0
quiet = len(sys.argv) > 3 and sys.argv[3] == "quiet"        # print only the frames where the boxes were not found
for f in sorted(glob.glob(f"{src}/depth_ep*_start.npy")) + sorted(glob.glob(f"{src}/f_*.npz")):
    ep = f.split("depth_ep")[1][:2] if "depth_ep" in f else f.split("f_")[-1][-8:-4]
    d = np.load(f) if f.endswith(".npy") else np.load(f)["depth"]
    fit = LEVELLED(d, cal, sc)
    t0 = time.time()
    found = B.find_boxes(B.points(cal, d, 2), fit.T, sc)
    t1 = time.time()
    lid = B.find_lid(B.points(cal, d, 1), fit.T, sc, found) if found["boxes"] else {"why": "-"}
    t2 = time.time()
    foot = fit.T[:2, 3]                                      # the point of the table straight below the camera
    line = f"ep{ep} {'ok ' if found['ok'] else 'NO '}"
    if "wall" in found:
        line += f"yaw {found['yaw_deg']:+.1f} deg, near wall {100 * (found['near'] - foot[0]):.1f} cm from the camera's foot, wall {100 * found['wall']:.1f} cm"
    if "depth" in found:
        line += f", depth {100 * found['depth']:.1f}"
    if found["boxes"]:
        worst = max(np.abs(found["boxes"][n]["center"] - nom[n]).max() for n in nom)
        line += f", gaps {100 * found['gaps'][0]:.1f} / {100 * found['gaps'][1]:.1f} cm | "
        for n in ("left", "center", "right"):
            b = found["boxes"][n]
            dx, dy = b["center"] - nom[n]
            line += f"{n} w {100 * b['size'][0]:.1f} vs yaml ({100 * dx:+.1f}, {100 * dy:+.1f}) d {100 * b['size'][1]:.1f}{'' if b['far_seen'] else '*'} edges {''.join('y' if b['edges_found'][k] else '-' for k in ('left', 'right'))} fill {b['fill']:.2f} | "
        if found["ok"]:
            rows.append([found["wall"], found["depth"], *found["gaps"], *[found["boxes"][n]["size"][0] for n in ("left", "center", "right")],
                         *np.concatenate([found["boxes"][n]["center"] - nom[n] for n in ("left", "center", "right")]), found["near"] - foot[0]])
    n_ok += found["ok"]
    n_all += 1
    if quiet and found["ok"]:
        continue
    print(line + f"{found['why']} | lid: {lid['why']} | {1000 * (t1 - t0):.0f} + {1000 * (t2 - t1):.0f} ms")
    if out and out != "-" and found["boxes"]:
        import cv2
        P = B.points(cal, d, 1)
        Q = P @ fit.T[:3, :3].T + fit.T[:3, 3]
        h = Q[:, 2] - sc.counter_z
        R, x0, x1, y0, y1 = 0.001, 0.15, 0.75, -0.42, 0.42
        H, W = int((x1 - x0) / R), int((y1 - y0) / R)
        top = np.full((H, W), -1.0, np.float32)
        xi, yi = ((Q[:, 0] - x0) / R).astype(int), ((y1 - Q[:, 1]) / R).astype(int)
        g = (xi >= 0) & (xi < H) & (yi >= 0) & (yi < W)
        np.maximum.at(top, (H - 1 - xi[g], yi[g]), h[g])
        img = cv2.applyColorMap((np.clip(top, 0, 0.10) / 0.10 * 255).astype(np.uint8), cv2.COLORMAP_JET)
        img[top < -0.5] = 0
        px = lambda p: (int((y1 - p[1]) / R), H - 1 - int((p[0] - x0) / R))
        e1, e2 = found["frame"]["e1"], found["frame"]["e2"]
        for n, b in found["boxes"].items():
            hw, hd = b["size"][0] / 2, b["size"][1] / 2
            cs = [b["center"] + e1 * sx * hd + e2 * sy * hw for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
            cv2.polylines(img, [np.array([px(q) for q in cs], np.int32)], True, (255, 255, 255), 2)
            cv2.circle(img, px(b["center"]), 4, (255, 255, 255), -1)
            cv2.drawMarker(img, px(nom[n]), (0, 0, 0), cv2.MARKER_CROSS, 14, 2)
        cv2.imwrite(f"{out}/boxes_ep{ep}.png", img)
if rows:
    r = np.array(rows) * 100
    names = ["wall", "depth", "gap L-C", "gap C-R", "width L", "width C", "width R", "L dx", "L dy", "C dx", "C dy", "R dx", "R dy", "near wall from foot"]
    print(f"\nboxes found on {n_ok}/{n_all} frames; those frames, cm: median (min .. max)")
    for k, n in enumerate(names):
        print(f"  {n:20s} {np.median(r[:, k]):+6.1f}  ({r[:, k].min():+.1f} .. {r[:, k].max():+.1f})")
