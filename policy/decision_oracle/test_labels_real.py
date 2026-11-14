"""Offline check on Aalto's real head frames (artifacts/real_frames/, data drop 2; RGB only, so no depth geometry):
v1.5's HSV colour classes against Gemini Decision 1 crop labels (v1.6), scored against hand labels.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy python -m decision_oracle.test_labels_real CROPS.json LABELS.txt

CROPS.json: [{"i", "frame", "bbox": [x, y, w, h]}, ...] (saturated blobs cut from the frames);
LABELS.txt: "i colour shape" items separated by ";" or newlines; colour o / y / p or x (no single block: a hand, the
arm, glare, several blocks), shape cube / cyl / tri (upright prism) / prism (lying) / ? (cannot tell).
Needs GEMINI_API_KEY. LABELER=v16 (default: labels_v16 criteria) or v15 (labels.py). Prints the confusion of each method and the Decision answers on the non-block crops (what a
leftover blob of the any-colour camera would be called).
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys

import cv2
import numpy as np

from .camera import HSV
from .labels import CropLabeler, crop_jpeg

COL = {"o": "red", "y": "yellow", "p": "blue"}
SHP = {"cube": "cube", "cyl": "cylinder", "tri": "triangle", "prism": "triangle"}


def hsv_class(rgb, bbox, min_frac=0.3):
    x, y, w, h = bbox
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb[y:y + h, x:x + w]), cv2.COLOR_RGB2HSV)
    sat = (hsv[..., 1] >= 70) & (hsv[..., 2] >= 60)
    counts = {}
    for c, ranges in HSV.items():
        m = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in ranges:
            m |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        counts[c] = int(((m > 0) & sat).sum())
    best = max(counts, key=counts.get)
    return best if counts[best] >= min_frac * max(1, int(sat.sum())) else None


def main(argv=None):
    a = argv or sys.argv[1:]
    crops = json.load(open(a[0]))
    lab = {}
    for item in re.split(r"[;\n]", open(a[1]).read()):
        p = item.split()
        if p:
            lab[int(p[0])] = (p[1], p[2] if len(p) > 2 else None)
    root = os.path.dirname(os.path.abspath(a[0])) if len(a) < 3 else a[2]
    if os.environ.get("LABELER", "v16") == "v16":
        from .labels_v16 import CropLabelerV16 as Lab
    else:
        Lab = CropLabeler
    L = Lab(mode="log", timeout=20.0, deadline_s=60.0)
    imgs, jobs = {}, []
    for c in crops:
        f = os.path.join("artifacts/real_frames", c["frame"])
        if f not in imgs:
            imgs[f] = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB)
        jobs.append((c, imgs[f]))
    res = list(L.pool.map(lambda j: _safe(L, crop_jpeg(j[1], j[0]["bbox"])), jobs))
    fc = collections.Counter(); hc = collections.Counter(); dc = collections.Counter(); ds = collections.Counter(); xs = collections.Counter()
    rows = []
    for (c, rgb), r in zip(jobs, res):
        col, shp = lab[c["i"]]
        h = hsv_class(rgb, c["bbox"])
        d_col = r.get("colour") if r.get("colour_conf", 0) >= 0.6 else None
        d_shp = r.get("shape") if r.get("shape_conf", 0) >= 0.6 else None
        if col == "x":
            xs[(d_col or "unsure")] += 1
            if (r.get("colour") not in (None, "other") and r.get("colour_conf", 0) >= 0.85
                    and r.get("shape") in SHP.values() and r.get("shape_conf", 0) >= 0.6):
                xs["would be kept as a leftover object"] += 1
            continue
        truth = COL[col]
        hc["right" if h == truth else ("missed" if h is None else "wrong")] += 1
        dc["right" if d_col == truth else ("unsure/other" if d_col in (None, "other") else "wrong")] += 1
        if shp in SHP:
            ds["right" if d_shp == SHP[shp] else ("unsure/other" if d_shp in (None, "other") else "wrong")] += 1
        fused = d_col if d_col not in (None, "other") else h
        fc["right" if fused == truth else ("missed" if fused is None else "wrong")] += 1
        rows.append((c["i"], col, shp, h, r))
    n = sum(hc.values())
    print(f"{n} single-block crops ({len(crops) - n} non-block crops)")
    print(f"colour, v1.5 HSV classes : {dict(hc)}")
    print(f"colour, Decision (>=0.6) : {dict(dc)}")
    print(f"colour, v1.6 fused       : {dict(fc)}")
    print(f"shape,  Decision (>=0.6) : {dict(ds)}  (on {sum(ds.values())} crops whose shape I could tell)")
    print(f"non-block crops, Decision colour (>=0.6): {dict(xs)}")
    for i, col, shp, h, r in rows:
        t = COL[col]
        dcol = r.get("colour") if r.get("colour_conf", 0) >= 0.6 else None
        dshp = r.get("shape") if r.get("shape_conf", 0) >= 0.6 else None
        if h != t or dcol != t or (shp in SHP and dshp != SHP[shp]):
            print(f"  crop {i}: truth {t}/{shp}  hsv {h}  d1 {r.get('colour')} {r.get('colour_conf', 0):.2f} / "
                  f"{r.get('shape')} {r.get('shape_conf', 0):.2f} {r.get('error', '')}")
    lat = sorted(r["latency_s"] for r in res if "latency_s" in r)
    if lat:
        print(f"Decision latency p50 {lat[len(lat) // 2]:.2f} s, p95 {lat[int(.95 * (len(lat) - 1))]:.2f} s")


def _safe(L, jpeg):
    for _ in range(3):
        try:
            return L._call(jpeg)
        except Exception as e:
            err = {"error": f"{type(e).__name__}: {str(e)[:60]}"}
    return err


if __name__ == "__main__":
    main()
