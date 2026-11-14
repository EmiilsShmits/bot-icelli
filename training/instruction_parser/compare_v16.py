"""v1.6 instruction parsing on a test set: rule parser vs Gemini Decision 1 as first tested (gemini_decision.py, with
the invalid veto and the red/yellow/blue-only task text) vs v1.6's Decision (policy/instruction_d1.py: real-colour
task text, no veto, confidence >= 0.6 on all 10 slots) vs the v1.6 chain (Decision, else rules).

    python3 compare_v16.py data/t2c.jsonl [data/t2a.jsonl ...]       # needs GEMINI_API_KEY in the repo's .env

Exact = all 10 slots right. Wrong = answered but not exact (confidently wrong). Refused = no answer (fallback).
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(REPO, "policy"), os.path.join(REPO, "third_party", "aaltonomous-humanoid")]

import rule_parser  # noqa: E402
from gemini_decision import GeminiDecision, _key  # noqa: E402
from spec import INVALID, interpret  # noqa: E402

os.environ.setdefault("GEMINI_API_KEY", _key())
import instruction_d1 as D  # noqa: E402


def v16(text, retries=4):
    d = D.DecisionInstruction(deadline_s=30.0, timeout=20.0)
    for i in range(retries):
        d.start(text)
        slots, rec = d.result()
        if slots is not None or "low confidence" in rec.get("why", "") or "no answer" in rec.get("why", ""):
            return slots, rec
        time.sleep(2 ** i)                     # 429 / network: retry (the policy does not; this is for scoring)
    return slots, rec


def score(name, preds, rows, extra=""):
    ex = wr = rf = 0
    for p, r in zip(preds, rows):
        if p is None or p == INVALID:
            rf += 1
        elif p == r["label"]:
            ex += 1
        else:
            wr += 1
    n = len(rows)
    return f"| {name} | {ex}/{n} ({100 * ex / n:.1f}%) | {wr} | {rf} |{extra}"


def main(paths):
    for path in paths:
        rows = [json.loads(l) for l in open(path) if l.strip()]
        for r in rows:
            r["label"] = interpret(r["spec"])
        texts = [r["text"] for r in rows]
        rules = []
        for t in texts:
            try:
                rules.append(rule_parser.parse(t))
            except Exception:
                rules.append(None)
        old = [o["pred"] for o in GeminiDecision(workers=4).predict_batch(texts)]
        with ThreadPoolExecutor(4) as ex:
            new = list(ex.map(v16, texts))
        lat = sorted(rec["latency_s"] for _, rec in new if "latency_s" in rec)
        chain = [s if s is not None else r for (s, _), r in zip(new, rules)]
        print(f"\n### {os.path.basename(path)} ({len(rows)} items)\n")
        print("| Parser | Exact | Wrong | Refused |\n|---|---|---|---|")
        print(score("rule parser", rules, rows))
        print(score("Decision as first tested", old, rows))
        print(score("Decision v1.6 prompt", [s for s, _ in new], rows))
        print(score("v1.6 chain (Decision, else rules)", chain, rows))
        if lat:
            print(f"\nv1.6 Decision latency p50 {lat[len(lat) // 2]:.2f} s, p95 {lat[int(.95 * (len(lat) - 1))]:.2f} s, "
                  f"max {lat[-1]:.2f} s")
        cats = sorted({r["category"] for r in rows})
        if len(cats) > 1:
            print("\nPer category, exact (rules / first Decision / v1.6 chain):")
            for c in cats:
                idx = [i for i, r in enumerate(rows) if r["category"] == c]
                f = lambda P: sum(P[i] == rows[i]["label"] for i in idx)
                print(f"  {c}: {f(rules)} / {f(old)} / {f(chain)} of {len(idx)}")
        for i, r in enumerate(rows):
            s, rec = new[i]
            if chain[i] != r["label"]:
                bad = {k: v for k, v in (chain[i] or {}).items() if v != r["label"][k]} if isinstance(chain[i], dict) else chain[i]
                print(f"  MISS {r['id']} [{'decision' if s is not None else 'rules: ' + rec.get('why', '')}] "
                      f"{r['text'][:80]!r} -> {bad}")


if __name__ == "__main__":
    main(sys.argv[1:])
