"""Gemini Decision 1 as an instruction parser (online; needs GEMINI_API_KEY in the repo's .env).

One createDecision call per instruction: 10 `choice` questions (the 9 known types + `other`, each
left / center / right / leave) plus one `noul` question "is the instruction invalid?".

  python3 eval.py gemini-decision data/t2a.jsonl --batch 8 --latency 20

The prediction is INVALID when P(invalid) >= 0.5. Per-item details go into `raw` (JSON):
p_invalid, min_choice_conf (the lowest confidence over the 10 choices) and latency_s, so a
confidence threshold / fallback can be studied afterwards (compare_gemini.py).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from prompts import TASK
from spec import INVALID, SLOTS

URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CRITERIA = {
    "left": "The left bin.",
    "center": "The center bin (also called middle or centre).",
    "right": "The right bin.",
    "leave": "No bin: it stays on the table.",
}
INVALID_Q = ("Is this instruction invalid? It is invalid if it is contradictory, names a bin that does not exist, "
             "is unrelated to sorting, or leaves some known object (a red, yellow or blue cube, cylinder or "
             "triangle) without any destination.")


def _key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    with open(os.path.join(REPO, ".env")) as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY not set")


def _qname(slot):
    return slot.replace(" ", "_")


def build_body(instruction: str) -> dict:
    questions = {}
    for slot in SLOTS:
        if slot == "other":
            q = ("Where should the robot put an object that is NOT one of the 9 known types "
                 "(an unknown colour or an unknown shape)?")
        else:
            q = f"Where should the robot put a {slot}?"
        questions[_qname(slot)] = {"type": "choice", "instructions": q, "criteria": CRITERIA}
    questions["is_invalid"] = {"type": "noul", "instructions": INVALID_Q}
    return {"model": MODEL, "input": TASK + "\nInstruction: " + instruction, "questions": questions}


class GeminiDecision:
    def __init__(self, workers: int = 4, timeout: float = 30.0):
        self.key = _key()
        self.workers = workers
        self.timeout = timeout
        self.load_s = 0.0

    def _call(self, instruction: str) -> dict:
        body = json.dumps(build_body(instruction)).encode()
        for attempt in range(6):
            req = urllib.request.Request(URL, data=body, method="POST", headers={
                "x-goog-api-key": self.key, "Content-Type": "application/json"})
            t = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                return self._parse(out, time.time() - t)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                return {"pred": None, "raw": json.dumps({"error": e.code, "msg": e.read()[:300].decode("utf-8", "replace")})}
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                return {"pred": None, "raw": json.dumps({"error": str(e)})}

    @staticmethod
    def _parse(out: dict, latency: float) -> dict:
        a = out.get("answers", {})
        try:
            p_invalid = float(a["is_invalid"]["noul"])
            pred = {s: a[_qname(s)]["choice"] for s in SLOTS}
            confs = [float(a[_qname(s)]["confidence"]) for s in SLOTS]
        except (KeyError, TypeError, ValueError):
            return {"pred": None, "raw": json.dumps({"bad_response": out})[:2000]}
        if p_invalid >= 0.5:
            pred = INVALID
        raw = {"p_invalid": p_invalid, "min_choice_conf": min(confs), "latency_s": latency,
               "tokens": out.get("usage", {}).get("total_input_tokens")}
        return {"pred": pred, "raw": json.dumps(raw)}

    def predict_batch(self, texts):
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(self._call, texts))
