"""v1.6 crop labels: Gemini Decision 1 names colour and shape; the camera's HSV colour and depth shape are the fallback.

Same calls as `labels.py` (`CropLabeler`: one createDecision per new object, parallel, 2.5 s deadline, cached per
tracked object name, planning thread only). Only the fuse rules differ (labels.py stays as v1.5 uses it):

  colour  Decision's colour if its confidence >= min_conf and it is not "other"; else the HSV class.
          An object HSV did not classify (a leftover blob, upgrades_v16.AnyColourCamera) keeps a colour only if
          Decision gives one with conf >= LEFTOVER_CONF and also a known shape (robot parts and glare never got one); Decision "other" (conf >= OTHER_CONF) makes it colour "other" (sorted only if the
          instruction gives unknown objects a bin); anything else drops it.
  shape   the depth geometry's "tipped" (lying) always stands: the ridge grasp needs it, and Decision calls a lying
          prism "triangle" (labels.py). Otherwise Decision's shape if conf >= min_conf, with the yaw re-fitted for
          that shape from the same top-face points; Decision "other" keeps the geometric shape.
  failure no key / network error / deadline: the detection keeps exactly what the camera gave it (v1.5).

Each detection gets `color_src` / `shape_src` ("d1", "hsv", "geom") for the decision log.
"""
from __future__ import annotations

import numpy as np

import base64
import hashlib
import json
import os
import time
import urllib.request

from .chooser import MODEL, URL
from .labels import SHAPES, TEXT, CropLabeler

KNOWN_SHAPES = ("cube", "cylinder", "triangle")
OTHER_CONF = 0.8
LEFTOVER_CONF = 0.85       # a blob no HSV class took needs a sure colour AND a known shape (>= min_conf): on real
                           # frames Decision gave a colour to robot-arm reflections and glare, never a known shape
# labels.py's colour criteria, changed on the real head frames (test_labels_real.py): the real yellow is pale (Decision
# called it "other"), and "other" also covers what is not a block at all. Then orange: the sim's venue orange renders
# as a pale peach, which "pale, light ... yellow" pulled to yellow (5/5 sim crops, 4 of them >= 0.6); naming pale orange
# / peach under red and excluding them from yellow: 5/5 orange there, real frames 75/81 right, 0 wrong (was 74/81, 0).
COLOURS = {
    "red": "Red or orange, including pale or washed-out orange, peach, salmon and tan-orange.",
    "yellow": "Yellow (lemon), including pale or slightly greenish yellow. Not orange, peach or tan.",
    "blue": "Blue, violet or purple.",
    "other": "Any other colour (green, white, black, grey, brown, pink ...), or no coloured block at all: part of the "
             "robot, the bare table, a reflection or glare.",
}


def yaw_for(shape, xy):
    """Top-face points (n, 2, m) -> yaw for `shape` in the sim's convention (camera.classify_top): cube faces at
    yaw + k*90 deg, triangle corners at yaw + 90 + k*120 deg, cylinder 0. None if there are too few points."""
    import cv2
    if xy is None or len(xy) < 25:
        return None
    if shape == "cylinder":
        return 0.0
    pts = np.asarray(xy, np.float32) * 1000.0
    hull = cv2.convexHull(pts)
    if shape == "cube":
        (_, _, rang) = cv2.minAreaRect(hull)
        a = np.radians(rang)
        return float((a + np.pi / 4) % (np.pi / 2) - np.pi / 4)
    if shape == "triangle":
        m = cv2.moments(hull)
        if m["m00"] <= 0:
            return None
        centre = np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]]) / 1000.0
        try:
            _, tri = cv2.minEnclosingTriangle(hull)
        except cv2.error:
            return None
        t = tri.reshape(3, 2) / 1000.0
        ang = np.arctan2(t[:, 1] - centre[1], t[:, 0] - centre[0]) - np.pi / 2
        a3 = np.arctan2(np.sin(3 * ang).mean(), np.cos(3 * ang).mean()) / 3
        return float((a3 + np.pi / 3) % (2 * np.pi / 3) - np.pi / 3)
    return None


class CropLabelerV16(CropLabeler):
    def __init__(self, mode="fuse", **kw):
        super().__init__(mode=mode, **kw)
        self.dump = os.environ.get("V16_DUMP_CROPS") or None    # folder: every crop sent + its answer (debugging)
        if self.dump:
            os.makedirs(self.dump, exist_ok=True)

    def _call(self, jpeg):
        body = {"model": MODEL, "input": [{"type": "text", "text": TEXT},
                                          {"type": "image", "data": base64.b64encode(jpeg).decode(), "mime_type": "image/jpeg"}],
                "questions": {"shape": {"type": "choice", "instructions": "What shape is the block?", "criteria": SHAPES},
                              "colour": {"type": "choice", "instructions": "What colour is the block?", "criteria": COLOURS}}}
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "x-goog-api-key": self.key, "Content-Type": "application/json"})
        t = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.load(r)
        a = out.get("answers") or {}
        res = {"shape": a["shape"]["choice"], "shape_conf": float(a["shape"]["confidence"]),
               "colour": a["colour"]["choice"], "colour_conf": float(a["colour"]["confidence"]),
               "latency_s": round(time.monotonic() - t, 2)}
        if self.dump:
            res["crop"] = hashlib.sha1(jpeg).hexdigest()[:12]
            with open(os.path.join(self.dump, res["crop"] + ".jpg"), "wb") as f:
                f.write(jpeg)
        return res

    def label(self, dets, rgb):
        super().label(dets, rgb)
        if self.mode != "fuse":                 # "log": record only; leftover blobs still need a colour or go
            for d in dets:
                if getattr(d, "hsv_color", d.color) is None:
                    d.other = True
        return dets

    def fuse(self, d):
        l = getattr(d, "d1", None) or {}
        hsv = getattr(d, "hsv_color", d.color)
        d.color_src = "hsv" if hsv is not None else None
        d.shape_src = "geom"
        # ---- colour
        c, cc = l.get("colour"), float(l.get("colour_conf", 0.0))
        if hsv is None and c not in (None, "other") and not (
                cc >= LEFTOVER_CONF and l.get("shape") in KNOWN_SHAPES and l.get("shape_conf", 0.0) >= self.min_conf):
            d.other = True                      # a leftover blob Decision is not sure is one of our blocks
            return
        if c is not None and c != "other" and cc >= self.min_conf:
            if c != d.color:
                d.color = c
            d.color_src = "d1"
        elif hsv is None:
            if c == "other" and cc >= OTHER_CONF:
                d.color, d.color_src = "other", "d1"
            else:
                d.other = True                  # nobody knows its colour: not an object we sort
                return
        # ---- shape
        if d.shape == "tipped":
            return
        s, sc = l.get("shape"), float(l.get("shape_conf", 0.0))
        if s in KNOWN_SHAPES and sc >= self.min_conf:
            d.shape_src = "d1"
            if s != d.shape:
                d.shape_geom, d.shape = d.shape, s
                y = yaw_for(s, getattr(d, "top_xy", None))
                d.yaw = y if y is not None else (d.yaw if d.yaw is not None else 0.0)
