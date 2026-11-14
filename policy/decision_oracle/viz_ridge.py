"""Visual check of the v1.5 lying-triangle handling on saved head frames with true poses (no sim, no planner).

    PYTHONPATH=third_party/aaltonomous-humanoid:policy python -m decision_oracle.viz_ridge \
        --frames artifacts/monitor/sim_frames --out artifacts/monitor/ridge_viz [--max 12]

For every frame with a lying triangular prism it draws on the head image:
  green   the true ridge (the prism's extrusion axis, from the sim state), drawn along the top edge
  orange  the ridge direction the camera geometry found (RidgeCamera, as v1.5 runs it), through its top centre
  cyan    where the v1.5 ridge grasp puts the thumb and fingers: on the two triangular end faces, 22.5 mm either side
          of the centre along the ridge, at Aalto's grasp height (counter + 0.5 x 45 mm before the fingertip check)
and writes a crop of each prism (x4) plus a contact sheet. Prints the angle error per prism.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import cv2
import numpy as np

from aaltonomous.interface.calibration import Calibration

from .test_tipcheck import rot, venue_scene
from .upgrades_v15 import RidgeCamera

CAM = "head"
SIZE = 0.045            # objects.size: prism altitude and length
GRASP_Z = 0.5 * SIZE    # Aalto grasp.height_frac x size, before the fingertip-clearance raise


def project(cal, P):
    """Pelvis-frame points (n, 3) -> pixels (n, 2) with the camera pose currently in cal."""
    c = cal.cams[CAM]
    T = np.asarray(c.T_pelvis_optical, float)
    Q = (np.asarray(P, float) - T[:3, 3]) @ T[:3, :3]          # optical frame
    uv = Q[:, :2] / Q[:, 2:3]
    return np.c_[uv[:, 0] * c.K[0, 0] + c.K[0, 2], uv[:, 1] * c.K[1, 1] + c.K[1, 2]]


def seg(img, cal, a, b, colour, w=2):
    p = project(cal, np.array([a, b]))
    cv2.line(img, tuple(np.round(p[0]).astype(int)), tuple(np.round(p[1]).astype(int)), colour, w, cv2.LINE_AA)


def dot(img, cal, a, colour, r=4):
    p = project(cal, np.array([a]))[0]
    cv2.circle(img, tuple(np.round(p).astype(int)), r, colour, -1, cv2.LINE_AA)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--venue", default="sim/venue_look/venue.yaml")
    ap.add_argument("--max", type=int, default=12, help="crops on the contact sheet")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    scene, cal = venue_scene(a.venue), Calibration.load()
    zc = scene.counter_z
    crops, errs, shown = [], [], set()
    for f in sorted(glob.glob(os.path.join(a.frames, "f_*.npz"))):
        z = np.load(f)
        st = json.loads(str(z["state"]))
        lying = []
        for o in st["objects"]:
            p = np.asarray(o["pos"], float)
            if not o["active"] or o["shape"] != "triangle" or not (-0.04 < p[2] < 0.05):
                continue
            R = rot(o.get("quat_xyzw") or [0, 0, 0, 1])
            tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
            if 45 < tilt < 135:
                lying.append((o["name"], p, R[:, 2]))
        if not lying:
            continue
        cam = RidgeCamera(scene, cal)
        dets = cam.detect(z["rgb"], z["depth"])           # also fits the head pose (into cam.cal, a copy)
        fcal = cam.cal
        img = cv2.cvtColor(np.ascontiguousarray(z["rgb"]), cv2.COLOR_RGB2BGR)
        for name, p, ax in lying:
            d = min(dets, key=lambda d: np.linalg.norm(d.top[:2] - p[:2]), default=None)
            if d is None or np.linalg.norm(d.top[:2] - p[:2]) > 0.05:
                continue
            ridge_true = np.arctan2(ax[1], ax[0])
            c = np.r_[d.top[:2], zc + SIZE]                 # top centre at ridge height
            u_true = np.r_[np.cos(ridge_true), np.sin(ridge_true), 0.0]
            seg(img, fcal, c - 0.03 * u_true, c + 0.03 * u_true, (60, 200, 60), 3)
            row = f"{os.path.basename(f)} {name}: shape '{d.shape}'"
            if d.shape == "tipped" and d.yaw is not None:
                u = np.r_[np.cos(d.yaw), np.sin(d.yaw), 0.0]
                seg(img, fcal, c - 0.03 * u, c + 0.03 * u, (0, 140, 255), 2)
                g = np.r_[d.top[:2], zc + GRASP_Z]
                for s in (-1, 1):                           # thumb / finger contacts on the two end faces
                    dot(img, fcal, g + s * (SIZE / 2) * u, (255, 220, 0), 4)
                e = float(np.degrees(abs((d.yaw - ridge_true + np.pi / 2) % np.pi - np.pi / 2)))
                errs.append(e)
                row += f", ridge error {e:.1f} deg"
            print(row)
            x, y, w, h = d.bbox
            m = 30
            crop = img[max(0, y - m):y + h + m, max(0, x - m):x + w + m]
            key = (name, tuple(np.round(p[:2], 2)))       # one crop per prism position
            if crop.size and len(crops) < a.max and key not in shown and d.shape == "tipped":
                shown.add(key)
                crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                cv2.putText(crop, f"{name} err {errs[-1]:.1f} deg" if d.shape == "tipped" else f"{name}: {d.shape}",
                            (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
                crops.append(crop)
        cv2.imwrite(os.path.join(a.out, os.path.basename(f).replace(".npz", ".jpg")), img)
    if crops:
        H = 300
        tiles = [cv2.resize(c, (int(c.shape[1] * H / c.shape[0]), H)) for c in crops]
        rows, cur, wsum = [], [], 0
        for t in tiles:
            if wsum + t.shape[1] > 1600 and cur:
                rows.append(cur); cur, wsum = [], 0
            cur.append(t); wsum += t.shape[1]
        rows.append(cur)
        W = max(sum(t.shape[1] for t in r) for r in rows)
        sheet = np.vstack([np.hstack(r + [np.zeros((H, W - sum(t.shape[1] for t in r), 3), np.uint8)]) for r in rows])
        cv2.imwrite(os.path.join(a.out, "sheet.jpg"), sheet)
    if errs:
        s = sorted(errs)
        print(f"\n{len(s)} lying prisms with a ridge: error median {s[len(s) // 2]:.1f}, p90 {s[int(.9 * len(s))]:.1f}, "
              f"max {s[-1]:.1f} deg. Images in {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
