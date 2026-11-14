"""Choosers: pick one Option (motions.py) from the feasible list of one look.

    DefaultChooser   Aalto's oracle rule (the default option). Also the fallback of the others.
    DecisionChooser  Gemini Decision 1: ONE createDecision call per look, head-camera image + scene text, one
                     `choice` question per parameter whose criteria are the feasible values only (+ "default").
                     2 s timeout; any error / timeout / missing answer -> the default.
    RandomChooser    uniform over objects, then over that object's options and drop spots (seeded). Explores
                     movements the oracle never picks, to see which ones work.

Every chooser returns (option, drop_index, record); `record` is logged as JSON (decisions.jsonl).
Runs inside the oracle's planning thread (never in act()), so a slow call only lengthens the robot's hold.
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.error
import urllib.request

import numpy as np

from aaltonomous.sim import oracle as O

URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"

DROP_WORDS = ["the middle of the bin's front half", "3 cm further away and 3 cm to the left",
              "3 cm closer and 3 cm to the right", "3 cm further away and 3 cm to the right",
              "3 cm closer and 3 cm to the left"]
GRASP_WORDS = {
    "face": "Fingers pointing at one flat side face of the block, thumb on the opposite face (for a triangle: thumb "
            "on the apex). Pinches across the block's narrow width.",
    "face_alt": "Triangle only: fingers on a side face but turned 15-30 degrees further towards the apex than "
                "the usual triangle grasp.",
    "stock": "Generic claw grasp from above with the fingers pointing forward or inward, not aligned to the block's "
             "faces (the only grasp for cylinders).",
}


def _api_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k.strip()
    for path in (os.environ.get("DECISION_KEY_FILE", ""), "/root/.decision_key"):
        if path and os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
    raise RuntimeError("no GEMINI_API_KEY / key file")


def where(xy):
    """Pelvis xy (x forward, y left) -> words."""
    x, y = float(xy[0]), float(xy[1])
    side = "straight ahead" if abs(y) < 0.03 else f"{abs(y) * 100:.0f} cm to the robot's {'left' if y > 0 else 'right'}"
    return f"{x * 100:.0f} cm in front of the robot, {side}"


def _grasp_kind(g):
    if g.startswith("face"):
        return "face_alt" if "p" in g else "face"
    return "stock"


class DefaultChooser:
    name = "default"
    budget_s = 0.0          # no alternatives needed: exactly Aalto's search

    def choose(self, options, ctx):
        o = next(o for o in options if o.is_default)
        return o, o.drop, {"chooser": self.name, "fallback": None}


class PreferFaceChooser:
    """Rule: keep the oracle's object, but for cubes and triangles take a face grasp whenever one has a checked plan
    (Aalto's face angle first, then the alternative triangle angles), and the stock claw only as a last resort.
    Aalto's oracle falls back to the stock claw as soon as its first-choice arm has no face plan; in our sim runs the
    stock claw held a triangle in 1 of 9 picks."""
    name = "prefer_face"
    budget_s = 8.0

    def choose(self, options, ctx):
        d = next(o for o in options if o.is_default)
        same = [o for o in options if o.obj == d.obj and o.route == d.route]
        rank = {"face": 0, "face_alt": 1, "stock": 2}
        o = min(same, key=lambda x: (rank[_grasp_kind(x.grasp)], not x.is_default, x.duration))
        return o, o.drop, {"chooser": self.name, "fallback": None, "changed": o is not d}


class RandomChooser:
    name = "random"
    budget_s = 8.0

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def reseed(self, seed):
        self.rng = random.Random(int(seed) * 7919 + 13)

    def choose(self, options, ctx):
        objs = sorted({o.obj for o in options})
        obj = self.rng.choice(objs)
        o = self.rng.choice([o for o in options if o.obj == obj])
        drops = ctx["drop_choices"](o)
        d = self.rng.choice(drops) if drops else o.drop
        return o, d, {"chooser": self.name, "fallback": None}


class DecisionChooser:
    name = "decision"
    budget_s = 8.0

    def __init__(self, timeout=2.0, image=True, jpeg_quality=80):
        self.timeout, self.image, self.q = timeout, image, jpeg_quality
        self.key = _api_key()

    # ------------------------------------------------------------------ request
    def build(self, options, ctx):
        """-> (body, labels): labels[question][criterion] = value it stands for."""
        default = next(o for o in options if o.is_default)
        by_obj = {}
        for o in options:
            by_obj.setdefault(o.obj, []).append(o)
        letters = {}
        for i, name in enumerate(sorted(by_obj, key=lambda n: (n != default.obj, n))):
            letters[name] = chr(ord("A") + i)
        Q, labels = {}, {}

        # object
        crit, lab = {}, {}
        for name, os_ in by_obj.items():
            o = os_[0]
            fast = min(x.duration for x in os_)
            relay = all(x.route == "relay" for x in os_)
            att = ctx["attempts"].get(name, 0)
            txt = (f"The {o.color} {o.shape} {where(o.det.top[:2])}, goes to the {o.bin} bin. "
                   f"{'Needs a relay (put down near the centre, other hand finishes). ' if relay else ''}"
                   f"{len(os_)} checked ways to do it, fastest {fast:.1f} s."
                   f"{f' Already tried {att} time(s) and it is still on the table.' if att else ''}")
            c = f"object_{letters[name]}"
            crit[c], lab[c] = txt, name
        crit["default"], lab["default"] = ("Let the planner decide (it takes the object nearest its bin that it can "
                                           "plan for)."), None
        Q["object"], labels["object"] = {"type": "choice", "criteria": crit, "instructions":
                                         "Which object should the robot pick up next? Prefer one that is easy to grasp "
                                         "and whose pick does not disturb the other objects."}, lab

        def param_q(qname, values, words, instr):
            if len(values) < 2:
                return
            crit, lab = {}, {}
            for v in values:
                crit[v], lab[v] = words[v], v
            crit["default"], lab["default"] = "Use the planner's default choice.", None
            Q[qname], labels[qname] = {"type": "choice", "criteria": crit, "instructions": instr}, lab

        arms = sorted({o.arm for o in options})
        param_q("arm", arms, {"left": "The robot's left arm.", "right": "The robot's right arm."},
                "Which arm should pick the chosen object? The left arm reaches the left side best, the right arm the "
                "right side; reaching across the body is slower and less reliable.")
        kinds = sorted({_grasp_kind(o.grasp) for o in options})
        param_q("grasp", kinds, GRASP_WORDS, "Which grasp should the hand use on the chosen object?")
        routes = sorted({o.route for o in options})
        param_q("route", routes, {"direct": "Carry it straight to its bin with one arm.",
                                  "relay": "Put it down near the centre line first; the other arm then takes it to "
                                           "the bin (slower, two picks)."},
                "Should the object go straight to its bin or via a hand-over spot?")
        drops = ctx["drop_choices"](default)
        param_q("drop_spot", [f"spot{k}" for k in drops],
                {f"spot{k}": f"Release over {DROP_WORDS[k]}." for k in range(len(O.DROP_OFFSETS))},
                "Where inside its target bin should the chosen object be released? Pick a spot where it will not land "
                "on top of objects already in that bin (look at the image).")
        if ctx.get("retry_objs"):
            names = ", ".join(f"the {by_obj[n][0].color} {by_obj[n][0].shape}" for n in ctx["retry_objs"] if n in by_obj)
            if names:
                Q["retry"], labels["retry"] = {"type": "choice", "instructions":
                                               f"A previous pick of {names} failed; it is still on the table. Try again or "
                                               "skip it and leave it on the table?",
                                               "criteria": {"retry": "Try it again (maybe with another arm or grasp).",
                                                            "skip": "Skip it for the rest of the episode.",
                                                            "default": "Use the planner's default (retry once)."}}, \
                    {"retry": "retry", "skip": "skip", "default": None}

        text = ("A humanoid robot (Unitree G1, two arms with three-finger hands) stands at a table and sorts small "
                "coloured blocks (cubes, cylinders, triangles) into three bins in a row behind the objects (left, "
                "center, right, as seen from the robot). The image is the robot's head camera. A motion planner has "
                "already checked every option listed below for reachability, collisions and speed limits, so every "
                "option is possible; choose the ones most likely to end with the object resting inside the correct "
                "bin, and choose 'default' when unsure.\n"
                f"Objects still on the table: {len(ctx['dets'])}. Sorting rule: {ctx['mapping_text']}.\n"
                f"Time left in the episode: {ctx['time_left']:.0f} s.")
        parts = [{"type": "text", "text": text}]
        img = ctx.get("jpeg")
        if self.image and img is not None:
            parts.append({"type": "image", "data": base64.b64encode(img).decode(), "mime_type": "image/jpeg"})
        return {"model": MODEL, "input": parts, "questions": Q}, labels

    def call(self, body):
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "x-goog-api-key": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    # ------------------------------------------------------------------ choose
    def choose(self, options, ctx):
        default = next(o for o in options if o.is_default)
        rec = {"chooser": self.name, "fallback": None}
        try:
            body, labels = self.build(options, ctx)
        except Exception as e:
            rec["fallback"] = f"build: {e!r}"
            return default, default.drop, rec
        rec["questions"] = {q: list(v["criteria"]) for q, v in body["questions"].items()}
        rec["criteria_obj"] = {k: v for k, v in labels["object"].items()}
        t = time.monotonic()
        try:
            out = self.call(body)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            rec["latency_s"] = round(time.monotonic() - t, 2)
            rec["fallback"] = f"call: {type(e).__name__}: {str(e)[:120]}"
            return default, default.drop, rec
        rec["latency_s"] = round(time.monotonic() - t, 2)
        ans = out.get("answers") or {}
        rec["answers"] = {q: {"choice": a.get("choice"), "confidence": a.get("confidence"),
                              "probabilities": a.get("probabilities")} for q, a in ans.items() if isinstance(a, dict)}
        pick = {q: labels[q].get((ans.get(q) or {}).get("choice")) for q in labels}
        rec["picked"] = pick
        if not any(q in ans for q in labels):
            rec["fallback"] = "no answers"
            return default, default.drop, rec

        # resolve: object -> arm -> grasp -> route (each only if a matching feasible option is left)
        cand = [o for o in options if o.obj == (pick.get("object") or default.obj)] or [default]
        for q, attr in (("arm", lambda o: o.arm), ("grasp", lambda o: _grasp_kind(o.grasp)), ("route", lambda o: o.route)):
            v = pick.get(q)
            if v is not None:
                sub = [o for o in cand if attr(o) == v]
                if sub:
                    cand = sub
                else:
                    rec.setdefault("unmatched", []).append(q)
        o = next((x for x in cand if x.is_default), None) or min(cand, key=lambda x: x.duration)
        if pick.get("retry") == "skip" and ctx.get("retry_objs"):
            rec["skip"] = list(ctx["retry_objs"])
            if o.obj in ctx["retry_objs"]:
                rest = [x for x in options if x.obj not in ctx["retry_objs"]]
                if not rest:
                    return None, None, rec
                o = next((x for x in rest if x.is_default), None) or min(rest, key=lambda x: x.duration)
        drop = o.drop
        dp = pick.get("drop_spot")
        if dp is not None and o.route == "direct":
            k = int(dp[4:])
            if k in ctx["drop_choices"](o):
                drop = k
        return o, drop, rec


def make(name, seed=0):
    if name == "default":
        return DefaultChooser()
    if name == "random":
        return RandomChooser(seed)
    if name == "decision":
        return DecisionChooser()
    if name == "prefer_face":
        return PreferFaceChooser()
    raise ValueError(name)


def jpeg(rgb, q=80):
    """RGB uint8 (H, W, 3) -> JPEG bytes (or None)."""
    if rgb is None:
        return None
    try:
        import cv2
        a = np.asarray(rgb)
        if a.ndim != 3 or a.size == 0 or not a.any():
            return None
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
        return buf.tobytes() if ok else None
    except Exception:
        return None
