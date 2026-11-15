"""Instruction -> bins with Gemini Decision 1 (v1.6), the rule parser as the offline fallback.

    d1 = DecisionInstruction()                 # key from GEMINI_API_KEY; without one it is off (rule parser only)
    d1.start(instruction)                      # in reset(): starts one call in a background thread, returns at once
    slots, rec = d1.result()                   # planning thread, first look: waits until `deadline_s` after start()
    mapping = slots_to_mapping(slots)          # same keys as oracle_v15.mapping_with_shapes

One createDecision call: the 10 slots of `training/instruction_parser/gemini_decision.py` (9 colour x shape types +
`other`, each left / center / right / leave), with two prompt fixes found on the T2a test set
(`training/instruction_parser/RESULTS.md`, "Follow-up: Gemini Decision 1"):
  * the task text names the real-table colours: orange = the red class, purple = the blue class (it refused every
    orange / purple instruction because the text said red / yellow / blue only);
  * no yes/no "invalid?" question: it vetoed 8 of 31 valid "leave" instructions, and finals instructions are valid.
The answer is used only if every slot came back with confidence >= `min_conf`; otherwise, and on no key / network
error / deadline, the caller keeps the rule parser's mapping. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import instruction  # noqa: F401  (puts training/instruction_parser on sys.path)
from instruction import fold_to_colours
from spec import BINS, COLORS, SHAPES, SLOTS, VALUES

log = logging.getLogger("bot-icelli.instruction_d1")

URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"

TASK = (
    "You turn a robot sorting instruction into a fixed answer.\n"
    "Objects: colours red, yellow, blue x shapes cube, cylinder, triangle (9 known types). On the real table the red "
    "objects look orange and the blue objects look purple: 'orange' in an instruction means red and 'purple' "
    "(or violet) means blue. A triangle is a triangular prism. "
    "Any other object (unknown colour or shape) is 'other'.\n"
    "Bins: left, center, right (named by position only; middle/centre = center).\n"
    "For each of the 10 slots give where it goes: left, center, right, or leave (stays on the table).\n"
    "Rules: a colour-only rule applies to all three shapes of that colour. A shape-only rule applies to all three "
    "colours of that shape. 'other' is leave unless the instruction explicitly says what to do with unknown/other "
    "objects. 'Everything' means the known blocks. Objects the instruction says to skip, ignore, not touch or leave "
    "stay on the table: leave. The instruction is valid.\n"
)
CRITERIA = {
    "left": "The left bin.",
    "center": "The center bin (also called middle or centre).",
    "right": "The right bin.",
    "leave": "No bin: it stays on the table.",
}


def _qname(slot):
    return slot.replace(" ", "_")


def build_body(text: str) -> dict:
    """gemini_decision.build_body with the v1.6 task text and without the is_invalid question."""
    questions = {}
    for slot in SLOTS:
        if slot == "other":
            q = ("Where should the robot put an object that is NOT one of the 9 known types "
                 "(an unknown colour or an unknown shape)?")
        else:
            c, s = slot.split()
            alias = {"red": " (orange on the real table)", "blue": " (purple on the real table)"}.get(c, "")
            q = f"Where should the robot put a {c}{alias} {s}?"
        questions[_qname(slot)] = {"type": "choice", "instructions": q, "criteria": CRITERIA}
    return {"model": MODEL, "input": TASK + "\nInstruction: " + text, "questions": questions}


def parse_answers(out: dict, min_conf: float):
    """createDecision response -> (slots or None, info). None when a slot is missing or below min_conf."""
    a = (out or {}).get("answers") or {}
    slots, confs = {}, {}
    for s in SLOTS:
        q = a.get(_qname(s)) or {}
        v, c = q.get("choice"), q.get("confidence")
        if v not in VALUES or c is None:
            return None, {"why": f"no answer for {s!r}"}
        slots[s], confs[s] = v, float(c)
    low = min(confs.values())
    info = {"min_conf": round(low, 3), "slots": slots}
    if low < min_conf:
        info["why"] = f"low confidence {low:.2f} ({min(confs, key=confs.get)})"
        return None, info
    return slots, info


def slots_to_mapping(slots: dict) -> dict:
    """10-slot answer -> the oracle's mapping: one bin per colour (most common over the 3 shapes; colours to leave on
    the table are omitted), (colour, shape) keys where a shape differs from its colour, a lying triangle ("tipped")
    following the triangle, and "other" when unknown objects get a bin. Same keys as oracle_v15.mapping_with_shapes."""
    mapping, _ = fold_to_colours(slots)
    out = dict(mapping)
    for c in COLORS:
        for s in SHAPES:
            want = slots[f"{c} {s}"] if slots[f"{c} {s}"] in BINS else None
            if want != mapping.get(c):
                out[(c, s)] = want
                if s == "triangle":
                    out[(c, "tipped")] = want
    if slots.get("other") in BINS:
        out["other"] = slots["other"]
    return out


def _clean_key(text):
    """Bare key, or a `GEMINI_API_KEY= <key>` line (same as decision_oracle/chooser.py clean_key)."""
    t = (text or "").strip()
    for line in t.splitlines():
        if "=" in line and line.split("=", 1)[0].strip().endswith("API_KEY"):
            return line.split("=", 1)[1].strip().strip("\"'") or None
    return t.strip("\"'") or None


def _api_key():
    """GEMINI_API_KEY, else the key file baked into the image (same lookup as decision_oracle/chooser.py)."""
    k = _clean_key(os.environ.get("GEMINI_API_KEY"))
    if k:
        return k
    for path in (os.environ.get("DECISION_KEY_FILE", ""), "/root/.decision_key"):
        if path and os.path.exists(path):
            with open(path) as f:
                k = _clean_key(f.read())
            if k:
                return k
    return None


class DecisionInstruction:
    def __init__(self, deadline_s=2.5, timeout=2.0, min_conf=0.6, key=None, call=None):
        """call: optional fake (body -> response dict), for tests."""
        self.deadline_s, self.timeout, self.min_conf = deadline_s, timeout, min_conf
        self.key = key if key is not None else _api_key()
        self._fake = call
        self.enabled = bool(self.key) or call is not None
        self.pool = ThreadPoolExecutor(1) if self.enabled else None
        self._job = None           # (future, text, t_start)
        self._lock = threading.Lock()

    def _call(self, text):
        body = build_body(text)
        t = time.monotonic()
        if self._fake is not None:
            out = self._fake(body)
        else:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
                "x-goog-api-key": self.key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.load(r)
        slots, info = parse_answers(out, self.min_conf)
        info["latency_s"] = round(time.monotonic() - t, 2)
        return slots, info

    def start(self, text):
        """reset(): never blocks. A previous episode's call that is still running is dropped (not waited for)."""
        with self._lock:
            self._job = None
            if not self.enabled or not (text or "").strip():
                return
            self._job = (self.pool.submit(self._call, text), text, time.monotonic())

    def result(self):
        """-> (slots or None, record). Waits at most until deadline_s after start(); never raises."""
        with self._lock:
            job = self._job
        if job is None:
            return None, {"used": False, "why": "off (no key)" if not self.enabled else "no call"}
        fut, text, t0 = job
        try:
            slots, info = fut.result(timeout=max(0.0, self.deadline_s - (time.monotonic() - t0)))
        except Exception as e:   # deadline, network, HTTP error, bad JSON
            fut.cancel()
            why = "deadline" if type(e).__name__ == "TimeoutError" else f"{type(e).__name__}: {str(e)[:80]}"
            return None, {"used": False, "why": why, "waited_s": round(time.monotonic() - t0, 2)}
        return slots, {"used": slots is not None, **info}
