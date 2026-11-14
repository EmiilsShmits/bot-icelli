"""Score camera perception against the sim's true poses, on frames saved with their scene state.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy python -m decision_oracle.test_camera FRAMES_DIR \
        [--scene scene_venue.yaml] [--save DIR] [--max 200]

FRAMES_DIR holds f_*.npz with rgb (H, W, 3), depth (H, W) uint16 mm and state (the scene service's JSON).
Per frame: fit the head pose, detect, match detections to the true objects resting on the counter (nearest, < 4 cm).
Prints position error, shape and colour accuracy, yaw error, misses and false detections. --save writes annotated
images of frames with a miss, a false detection or a wrong shape.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os

import numpy as np

from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene

from .camera import CAM, CameraPerception


def truth(scene, state):
    out = []
    for o in state["objects"]:
        if not o["active"]:
            continue
        p = np.asarray(o["pos"], float)
        m = scene.pelvis_to_mat(p)
        if not scene.on_counter(m) or scene.bin_of(m) is not None:
            continue
        hz = p[2] - scene.counter_z
        if hz > scene.object_height() * 0.75 or o.get("speed", 0.0) > 0.02:
            continue                                   # in a hand / moving
        q = o.get("quat_xyzw") or [0, 0, 0, 1]
        yaw = float(np.arctan2(2 * (q[3] * q[2] + q[0] * q[1]), 1 - 2 * (q[1] ** 2 + q[2] ** 2)))
        up = 1 - 2 * (q[0] ** 2 + q[1] ** 2)           # z component of the object's z axis
        out.append({"name": o["name"], "color": o["color"], "shape": o["shape"], "xy": p[:2], "yaw": yaw,
                    "tipped": up < 0.9})
    return out


def yaw_err(shape, a, b):
    n = {"cube": 4, "triangle": 3}.get(shape)
    if n is None or a is None:
        return None
    per = 2 * np.pi / n
    return float(np.degrees(abs((a - b + per / 2) % per - per / 2)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--scene", default=os.environ.get("AALTO_SCENE"))
    ap.add_argument("--save", default=None)
    ap.add_argument("--max", type=int, default=10000)
    ap.add_argument("--d1", type=int, default=0, help="also ask Decision 1 for crop labels on every k-th frame (needs "
                    "GEMINI_API_KEY); prints its accuracy next to the geometric one")
    ap.add_argument("--refit", action="store_true", help="fit the head pose on every frame (default: every frame too, "
                    "frames are independent)")
    a = ap.parse_args(argv)
    scene = Scene.load(a.scene)
    cal = Calibration.load()
    files = sorted(glob.glob(os.path.join(a.frames, "*.npz")))[: a.max]
    errs, yerrs, shape_ok, color_ok = [], collections.defaultdict(list), collections.Counter(), collections.Counter()
    conf = collections.Counter()
    miss = fp = n_true = n_frames = tipped_seen = tipped_true = 0
    fits = []
    lab, d1 = None, collections.Counter()
    d1_conf, d1_lat, d1_wrong = [], [], []
    if a.d1:
        from .labels import CropLabeler
        lab = CropLabeler(mode="log")
    for fi, f in enumerate(files):
        z = np.load(f)
        rgb, depth, state = z["rgb"], z["depth"], json.loads(str(z["state"]))
        cam = CameraPerception(scene, cal)
        dets = cam.detect(rgb, depth)
        fit = cam.fit
        if lab is not None and fi % a.d1 == 0:
            lab.reset()
            lab.label(dets, rgb)
        fits.append((fit.ok, fit.tilt_deg, fit.dxy, fit.dyaw_deg, fit.wall_score, fit.plane_inliers, fit.why))
        gt = truth(scene, state)
        n_frames += 1
        n_true += len(gt)
        used, bad = set(), False
        for g in gt:
            best = None
            for i, d in enumerate(dets):
                if i in used:
                    continue
                e = float(np.linalg.norm(d.top[:2] - g["xy"]))
                if e < 0.04 and (best is None or e < best[0]):
                    best = (e, i)
            if best is None:
                miss += 1
                bad = True
                continue
            used.add(best[1])
            d = dets[best[1]]
            errs.append(best[0])
            color_ok[d.color == g["color"]] += 1
            l = getattr(d, "d1", None)
            if l is not None:
                if "error" in l:
                    d1["error"] += 1
                else:
                    want = "other" if g["tipped"] else g["shape"]
                    d1[("shape", l["shape"] == want)] += 1
                    d1[("colour", l["colour"] == g["color"])] += 1
                    d1[("geom_on_same", (d.shape if not g["tipped"] else ("other" if d.tipped else d.shape)) == want)] += 1
                    d1_conf.append((l["shape_conf"], l["shape"] == want))
                    d1_lat.append(l["latency_s"])
                    if l["shape"] != want:
                        d1_wrong.append((want, l["shape"], round(l["shape_conf"], 2), d.shape))
            if g["tipped"]:
                tipped_true += 1
                tipped_seen += bool(getattr(d, "tipped", False))
                continue
            conf[(g["shape"], d.shape or "none")] += 1
            shape_ok[d.shape == g["shape"]] += 1
            bad |= d.shape != g["shape"]
            ye = yaw_err(g["shape"], d.yaw, g["yaw"]) if d.shape == g["shape"] else None
            if ye is not None:
                yerrs[g["shape"]].append(ye)
        extra = [d for i, d in enumerate(dets) if i not in used]
        fp += len(extra)
        bad |= bool(extra)
        if a.save and bad:
            import cv2
            os.makedirs(a.save, exist_ok=True)
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).copy()
            for i, d in enumerate(dets):
                x, y, w, h = d.bbox
                col = (0, 255, 0) if i in used else (0, 0, 255)
                cv2.rectangle(img, (x, y), (x + w, y + h), col, 1)
                cv2.putText(img, f"{d.color[:1]}{(d.shape or 'non')[:3]}", (x, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
            c2 = cam.cal
            for g in gt:
                uvz = c2.project(CAM, np.r_[g["xy"], scene.counter_z + scene.object_height()])
                cv2.circle(img, (int(uvz[0]), int(uvz[1])), 4, (255, 255, 255), 1)
            cv2.imwrite(os.path.join(a.save, os.path.basename(f).replace(".npz", ".jpg")), img)
    errs = np.array(errs) * 1000
    print(f"frames {n_frames}, true objects on the counter {n_true}")
    ok = [x for x in fits if x[0]]
    print(f"head pose fit ok {len(ok)}/{len(fits)}; tilt deg mean {np.mean([x[1] for x in fits]):.2f} "
          f"(std {np.std([x[1] for x in fits]):.2f}); shift cm mean ({np.mean([x[2][0] for x in fits]) * 100:+.2f}, "
          f"{np.mean([x[2][1] for x in fits]) * 100:+.2f}) std ({np.std([x[2][0] for x in fits]) * 100:.2f}, "
          f"{np.std([x[2][1] for x in fits]) * 100:.2f}); yaw deg mean {np.mean([x[3] for x in fits]):+.2f} "
          f"std {np.std([x[3] for x in fits]):.2f}; wall score mean {np.mean([x[4] for x in fits]):.2f}")
    print("fit notes:", dict(collections.Counter(x[6] for x in fits)))
    if len(errs):
        print(f"matched {len(errs)}: position error mm median {np.median(errs):.1f}, 90% {np.percentile(errs, 90):.1f}, "
              f"max {errs.max():.1f}")
    print(f"missed {miss}/{n_true}, false detections {fp}")
    print(f"colour right {color_ok[True]}/{sum(color_ok.values())}, shape right {shape_ok[True]}/{sum(shape_ok.values())}, "
          f"tipped recognised {tipped_seen}/{tipped_true}")
    print("shape confusion (true, seen):", dict(conf))
    if lab is not None:
        print(f"Decision 1 crop labels: shape right {d1[('shape', True)]}/{d1[('shape', True)] + d1[('shape', False)]}, "
              f"colour right {d1[('colour', True)]}/{d1[('colour', True)] + d1[('colour', False)]}, errors {d1['error']}; "
              f"geometry on the same objects {d1[('geom_on_same', True)]}/{d1[('geom_on_same', True)] + d1[('geom_on_same', False)]}")
        if d1_lat:
            print(f"  latency s median {np.median(d1_lat):.2f} max {max(d1_lat):.2f}; confidence when right "
                  f"{np.mean([c for c, ok in d1_conf if ok] or [0]):.2f}, when wrong {np.mean([c for c, ok in d1_conf if not ok] or [0]):.2f}")
            print("  wrong (true, Decision, conf, geometry):", d1_wrong[:20])
    for s, v in yerrs.items():
        print(f"yaw error deg ({s}): median {np.median(v):.1f}, 90% {np.percentile(v, 90):.1f}, max {max(v):.1f}, n {len(v)}")


if __name__ == "__main__":
    main()
