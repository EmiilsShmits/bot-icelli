"""Offline test of the v1.5 "lying block" handling on saved head frames with true poses (no sim):

    PYTHONPATH=third_party/aaltonomous-humanoid:policy GEMINI_API_KEY=... python -m decision_oracle.test_tipcheck \
        --frames artifacts/monitor/sim_frames [--models d1,hydrogen] [--venue sim/venue_look/venue.yaml]

For every object the camera geometry (RidgeCamera, as v1.5 runs it) calls "tipped":
  - is it really lying? (true pose: a cylinder or prism tilted 45-135 deg) -> geometry precision;
  - the model check (TipChecker) on its crop: lying_prism / lying_cylinder / upright / unclear, latency;
  - for a lying prism: ridge direction from the geometry vs the true one.
Also counts lying objects the geometry did not call "tipped" (the model is only asked about "tipped" ones).
"""
from __future__ import annotations

import argparse
import collections
import copy
import glob
import json
import os

import numpy as np
import yaml

from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene

from .upgrades_v15 import RidgeCamera, TipChecker


def venue_scene(venue_yaml):
    """Aalto's scene.yaml + the `scene:` overrides of venue.yaml (what make_assets.scene_venue writes), in memory."""
    base = Scene.load().cfg
    if not venue_yaml:
        return Scene(base)
    over = (yaml.safe_load(open(venue_yaml)) or {}).get("scene") or {}
    cfg = copy.deepcopy(base)

    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v
    merge(cfg, over)
    return Scene(cfg)


def rot(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--models", default="d1")
    ap.add_argument("--venue", default="sim/venue_look/venue.yaml")
    ap.add_argument("--out", default=None, help="json with every row")
    a = ap.parse_args(argv)
    scene, cal = venue_scene(a.venue), Calibration.load()
    checkers = {m: TipChecker(m, timeout=8.0, deadline_s=9.0) for m in a.models.split(",") if m}
    from .labels import crop_jpeg
    rows, missed, n_lying = [], 0, 0
    for f in sorted(glob.glob(os.path.join(a.frames, "f_*.npz"))):
        z = np.load(f)
        st = json.loads(str(z["state"]))
        truth = []
        for o in st["objects"]:
            if not o["active"]:
                continue
            p = np.asarray(o["pos"], float)
            if p[2] > 0.05 or p[2] < -0.04:          # in the air / off the table
                continue
            R = rot(o.get("quat_xyzw") or [0, 0, 0, 1])
            tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
            lying = o["shape"] != "cube" and 45 < tilt < 135
            ax = R[:, 2]                                # extrusion axis = ridge of a lying prism
            truth.append(dict(name=o["name"], shape=o["shape"], xy=p[:2], lying=lying,
                              ridge=float(np.arctan2(ax[1], ax[0])) if lying else None))
        n_lying += sum(t["lying"] for t in truth)
        cam = RidgeCamera(scene, cal)
        dets = cam.detect(z["rgb"], z["depth"])
        seen_lying = set()
        for d in dets:
            t = min(truth, key=lambda t: np.linalg.norm(t["xy"] - d.top[:2]), default=None)
            if t is None or np.linalg.norm(t["xy"] - d.top[:2]) > 0.05:
                t = None
            if d.shape != "tipped":
                continue
            if t is not None and t["lying"]:
                seen_lying.add(t["name"])
            row = {"frame": os.path.basename(f), "obj": None if t is None else t["name"],
                   "true_shape": None if t is None else t["shape"], "true_lying": None if t is None else t["lying"],
                   "ridge_err_deg": None}
            if t is not None and t["lying"] and t["shape"] == "triangle" and d.yaw is not None:
                e = abs((d.yaw - t["ridge"] + np.pi / 2) % np.pi - np.pi / 2)
                row["ridge_err_deg"] = round(float(np.degrees(e)), 1)
            j = crop_jpeg(np.asarray(z["rgb"]), d.bbox)
            for m, ck in checkers.items():
                try:
                    row[m] = ck.ask(j)
                except Exception as e:
                    row[m] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            rows.append(row)
            print(row, flush=True)
        missed += sum(1 for t in truth if t["lying"] and t["name"] not in seen_lying)
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=1, default=str)
    # ---- report
    print(f"\n{len(rows)} detections the geometry calls 'tipped'; true lying objects on these frames: {n_lying} "
          f"(object-frames), of which the geometry missed {missed}")
    kinds = collections.Counter(("lying " + r["true_shape"]) if r["true_lying"] else
                                ("upright " + str(r["true_shape"])) for r in rows)
    print("geometry 'tipped' is really:", dict(kinds))
    errs = sorted(r["ridge_err_deg"] for r in rows if r["ridge_err_deg"] is not None)
    if errs:
        print(f"ridge direction error (lying prisms, n={len(errs)}): median {errs[len(errs) // 2]}, "
              f"p90 {errs[int(len(errs) * 0.9)]}, max {errs[-1]} deg")
    for m in checkers:
        c = collections.Counter()
        lat = sorted(r[m]["latency_s"] for r in rows if "latency_s" in r.get(m, {}))
        for r in rows:
            ans = r[m].get("pose", "error")
            truth = "lying" if r["true_lying"] else "upright"
            c[(truth, ans)] += 1
        print(f"\n{m}: answers by truth: " + ", ".join(f"{t}->{p}: {n}" for (t, p), n in sorted(c.items())))
        right = sum(n for (t, p), n in c.items() if (t == "lying" and p.startswith("lying")) or (t == "upright" and p == "upright"))
        wrong_flip = sum(n for (t, p), n in c.items() if t == "lying" and p == "upright")
        print(f"   right {right}/{len(rows)}; lying objects it would wrongly call upright: {wrong_flip}; "
              f"latency median {lat[len(lat) // 2] if lat else None} s, max {lat[-1] if lat else None} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
