"""Gemini Decision 1 labels for single-object crops of the head image: colour, shape, or "other" (not one of ours).

    lab = CropLabeler(mode="log")          # "log": record next to the geometric label; "fuse": may override it
    lab.label(dets, rgb)                   # planning thread only; <= `deadline_s` in total, cached per object name

One createDecision call per new object (parallel, each with its own timeout), two `choice` questions. Offline
fallback = the geometric shape and HSV colour from camera.py, which are always computed first; a failed or slow call
changes nothing. On real Aalto frames this labelling scored 41/42 (hand-labelled, small sample).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

import numpy as np

from .chooser import MODEL, URL, _api_key

SHAPES = {
    "cube": "A cube: a box with a square top face and four flat vertical sides.",
    "cylinder": "A cylinder: a round disc-like top face, curved side, no corners.",
    "triangle": "A triangular prism standing upright: the top face is a triangle with three corners.",
    "other": "Something else: a block lying on its side, a different kind of object, part of the robot, or nothing clear.",
}
COLOURS = {
    "red": "Red or orange.",
    "yellow": "Yellow.",
    "blue": "Blue, violet or purple.",
    "other": "Any other colour (green, white, black, grey, brown, pink ...).",
}
TEXT = ("This is a small crop from a robot's head camera. It shows one small coloured block (about 4.5 cm) standing on "
        "a table, seen from above at an angle. Classify the block in the middle of the crop.")


def crop_jpeg(rgb, bbox, pad=14, out=192, q=85):
    import cv2
    x, y, w, h = bbox
    H, W = rgb.shape[:2]
    s = max(w, h) + 2 * pad
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    x1, y1 = int(min(W, cx + s / 2)), int(min(H, cy + s / 2))
    c = rgb[y0:y1, x0:x1]
    if c.size == 0:
        return None
    c = cv2.resize(c, (out, int(round(out * c.shape[0] / c.shape[1]))), interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(c, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes() if ok else None


class CropLabeler:
    def __init__(self, mode="log", timeout=2.0, deadline_s=2.5, min_conf=0.6, workers=6):
        self.mode, self.timeout, self.deadline_s, self.min_conf = mode, timeout, deadline_s, min_conf
        self.key = _api_key()
        self.pool = ThreadPoolExecutor(workers)
        self.cache = {}            # object name -> label dict
        self.calls = []            # latency / errors, for the log

    def reset(self):
        self.cache = {}

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
        return {"shape": a["shape"]["choice"], "shape_conf": float(a["shape"]["confidence"]),
                "colour": a["colour"]["choice"], "colour_conf": float(a["colour"]["confidence"]),
                "latency_s": round(time.monotonic() - t, 2)}

    def label(self, dets, rgb):
        """Adds d.d1 (label dict or {'error': ...}) to every detection; in "fuse" mode a confident Decision label
        replaces a geometric shape that was a close call, and a confident "other" marks the object as not ours."""
        rgb = np.asarray(rgb)
        todo = {}
        for d in dets:
            if d.name in self.cache:
                d.d1 = self.cache[d.name]
                continue
            j = crop_jpeg(rgb, d.bbox)
            if j is not None:
                todo[self.pool.submit(self._call, j)] = d
        if todo:
            wait(list(todo), timeout=self.deadline_s)
        for fut, d in todo.items():
            if fut.done():
                try:
                    d.d1 = fut.result()
                    self.cache[d.name] = d.d1
                except Exception as e:
                    d.d1 = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            else:
                d.d1 = {"error": "deadline"}
                fut.cancel()
        if self.mode == "fuse":
            for d in dets:
                self.fuse(d)
        return dets

    def fuse(self, d):
        l = getattr(d, "d1", None) or {}
        if "shape" not in l or l["shape_conf"] < self.min_conf:
            return
        dist = (getattr(d, "feat", {}) or {}).get("dist") or {}
        close_call = False
        if dist:
            v = sorted(dist.values())
            close_call = len(v) > 1 and v[1] - v[0] < 0.12
        if d.shape == "tipped":
            return        # measured on sim frames: Decision calls a tipped triangle "triangle"; the ridge test is right
        if l["shape"] == "other":
            if l["shape_conf"] >= 0.8 and close_call:
                d.other = True
        elif l["shape"] != d.shape and (close_call or d.shape is None):
            d.shape_geom, d.shape = d.shape, l["shape"]
            if d.shape != "cylinder" and d.yaw is None:
                d.yaw = 0.0
