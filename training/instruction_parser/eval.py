"""Evaluation harness (EXPERIMENT.md Phase 0 step 4).

  python3 eval.py rule data/t2a.jsonl
  python3 eval.py hf:google/gemma-3-1b-it:B data/t2a.jsonl [--batch 16] [--latency 30] [--device cpu]
  python3 eval.py ft:/root/ckpt/student-270m:B data/t2b.jsonl

Writes results/<method-slug>/<testset>.preds.jsonl and .summary.json, and prints the summary.
A prediction of None (malformed output) counts as a refusal (the policy would fall back).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from spec import INVALID, SLOTS  # noqa: E402

THRESHOLDS = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0]


def slug(method: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", method.replace("/", "--"))


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def summarize(rows, method, testset, latencies=None, extra=None):
    n = len(rows)
    valid_items = [r for r in rows if r["label"] != INVALID]
    inv_items = [r for r in rows if r["label"] == INVALID]
    s = {"method": method, "testset": testset, "n": n}

    def is_refusal(r):
        return r["pred"] is None or r["pred"] == INVALID

    if valid_items:
        nv = len(valid_items)
        exact = sum(r["pred"] == r["label"] for r in valid_items)
        refused = sum(is_refusal(r) for r in valid_items)
        malformed = sum(r["pred"] is None for r in valid_items)
        conf_wrong = sum((not is_refusal(r)) and r["pred"] != r["label"] for r in valid_items)
        slot_ok = sum(0 if is_refusal(r) else sum(r["pred"][k] == r["label"][k] for k in SLOTS) for r in valid_items)
        other_ok = sum((not is_refusal(r)) and r["pred"]["other"] == r["label"]["other"] for r in valid_items)
        other_bad = sum((not is_refusal(r)) and r["pred"]["other"] != r["label"]["other"] for r in valid_items)
        known_ok = sum(0 if is_refusal(r) else sum(r["pred"][k] == r["label"][k] for k in SLOTS[:-1]) for r in valid_items)
        s.update({
            "exact_acc": exact / nv, "per_slot_acc": slot_ok / (nv * len(SLOTS)),
            "known_slot_acc": known_ok / (nv * 9),
            "invalid_rate": refused / nv, "malformed_rate": malformed / nv, "confidently_wrong_rate": conf_wrong / nv,
            "distractor_safety": other_ok / nv, "distractor_unsafe_rate": other_bad / nv,
        })
        cats = defaultdict(lambda: [0, 0, 0])
        for r in valid_items:
            c = cats[r["category"]]
            c[0] += 1
            c[1] += r["pred"] == r["label"]
            c[2] += (not is_refusal(r)) and r["pred"] != r["label"]
        s["per_category"] = {k: {"n": v[0], "exact_acc": v[1] / v[0], "confidently_wrong": v[2] / v[0]}
                             for k, v in sorted(cats.items())}
    if inv_items:
        s["t3_refusal_rate"] = sum(is_refusal(r) for r in inv_items) / len(inv_items)
        cats = defaultdict(lambda: [0, 0])
        for r in inv_items:
            cats[r["category"]][0] += 1
            cats[r["category"]][1] += is_refusal(r)
        s["t3_per_category_refusal"] = {k: v[1] / v[0] for k, v in sorted(cats.items())}
    if any("conf" in r for r in rows):
        curve = []
        for t in THRESHOLDS:
            acc = [r for r in rows if r.get("conf", 0) >= t]
            pt = {"threshold": t, "coverage": len(acc) / n}
            if valid_items:
                va = [r for r in valid_items if r.get("conf", 0) >= t]
                pt["exact_acc_overall"] = sum(r["pred"] == r["label"] for r in va) / len(valid_items)
                pt["confidently_wrong_rate"] = sum(r["pred"] != r["label"] for r in va) / len(valid_items)
                pt["acc_on_accepted"] = (sum(r["pred"] == r["label"] for r in va) / len(va)) if va else None
            if inv_items:
                pt["t3_refusal_rate"] = sum(r.get("conf", 0) < t for r in inv_items) / len(inv_items)
            curve.append(pt)
        s["confidence_curve"] = curve
    if latencies:
        s["latency_p50_s"] = pct(latencies, 0.5)
        s["latency_p95_s"] = pct(latencies, 0.95)
        s["latency_n"] = len(latencies)
    if extra:
        s.update(extra)
    return s


def load_method(method, args):
    if method == "rule":
        import rule_parser

        class Rule:
            load_s = 0.0

            def predict_batch(self, texts):
                return [{"pred": rule_parser.parse(t)} for t in texts]
        return Rule()
    if method == "gemini-decision":
        from gemini_decision import GeminiDecision
        return GeminiDecision()
    from llm import HFMethod
    return HFMethod(method, device=args.device, load_8bit=args.load_8bit, shots=args.shots)


def run(method_obj, method, testset, args):
    rows = [json.loads(l) for l in open(testset) if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    t0 = time.time()
    for i in range(0, len(rows), args.batch):
        chunk = rows[i: i + args.batch]
        for r, p in zip(chunk, method_obj.predict_batch([r["text"] for r in chunk])):
            r.update(p)
    total_s = time.time() - t0
    lat = []
    if args.latency:  # warm, batch size 1
        sample = rows[: args.latency + 3]
        for j, r in enumerate(sample):
            t = time.time()
            method_obj.predict_batch([r["text"]])
            if j >= 3:
                lat.append(time.time() - t)
    extra = {"throughput_items_per_s": len(rows) / total_s if total_s else None,
             "load_s": getattr(method_obj, "load_s", None), "device": args.device}
    try:
        import torch
        if torch.cuda.is_available():
            extra["peak_vram_gb"] = torch.cuda.max_memory_allocated() / 1e9
            extra["gpu"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    s = summarize(rows, method, os.path.basename(testset), lat, extra)
    out = os.path.join(args.out, slug(method) + ("__" + args.tag if args.tag else ""))
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, os.path.basename(testset).replace(".jsonl", ""))
    with open(base + ".preds.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in ("id", "category", "text", "label", "pred", "raw", "conf")}) + "\n")
    with open(base + ".summary.json", "w") as f:
        json.dump(s, f, indent=1)
    brief = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()
             if k not in ("per_category", "t3_per_category_refusal", "confidence_curve")}
    print(json.dumps(brief), flush=True)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("testsets", nargs="+")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--latency", type=int, default=0, help="warm batch-1 latency over N items")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--load-8bit", action="store_true")
    ap.add_argument("--shots", type=int, default=3)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    args = ap.parse_args()
    m = load_method(args.method, args)
    for ts in args.testsets:
        run(m, args.method, ts, args)


if __name__ == "__main__":
    main()
