"""Compare Gemini Decision 1 with the Gemma students and the rule parser, plus fallback chains.

  python3 compare_gemini.py            # prints a markdown table, writes results/gemini_compare.md

Chains: try each parser in order; a refusal (None / invalid) passes the instruction to the next one.
Reads the per-item predictions in results/<method>/<set>.preds.jsonl written by eval.py.
"""
from __future__ import annotations

import json
import os

from spec import INVALID

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
SETS = ["t1", "t2a", "t2b", "t3"]
M = {
    "rule": "rule",
    "gemma-1b": "ft_--root--ckpt--s1b-full_B",
    "gemma-e2b": "ft_--root--ckpt--sE2B-lora_B",
    "gemini": "gemini-decision",
}


def load(method, ts):
    return {r["id"]: r for r in map(json.loads, open(os.path.join(R, M[method], ts + ".preds.jsonl")))}


def refused(p):
    return p is None or p == INVALID


def chain(names, ts):
    tables = [load(n, ts) for n in names]
    out = []
    for i, r in tables[0].items():
        pred = None
        for t in tables:
            pred = t[i]["pred"]
            if not refused(pred):
                break
        out.append({"category": r["category"], "label": r["label"], "pred": pred})
    return out


def score(rows, skip_cat=None):
    rows = [r for r in rows if r["category"] != skip_cat]
    valid = [r for r in rows if r["label"] != INVALID]
    inv = [r for r in rows if r["label"] == INVALID]
    s = {}
    if valid:
        n = len(valid)
        s["exact"] = sum(r["pred"] == r["label"] for r in valid) / n
        s["cw"] = sum((not refused(r["pred"])) and r["pred"] != r["label"] for r in valid) / n
        s["refused"] = sum(refused(r["pred"]) for r in valid) / n
    if inv:
        s["t3_refusal"] = sum(refused(r["pred"]) for r in inv) / len(inv)
    return s


def main():
    configs = [
        ("rule parser", ["rule"]),
        ("Gemma 3 1B (fine-tuned)", ["gemma-1b"]),
        ("Gemma 4 E2B (LoRA)", ["gemma-e2b"]),
        ("Gemini Decision 1", ["gemini"]),
        ("Gemini → Gemma 1B → rule", ["gemini", "gemma-1b", "rule"]),
        ("Gemma 1B → rule (offline only)", ["gemma-1b", "rule"]),
    ]
    head = ("| Method | T1 exact | T2a exact / CW | T2a w/o orange-purple exact / CW | T2b exact / CW | T3 refusal |\n"
            "|---|---|---|---|---|---|")
    lines = [head]
    f = lambda x: f"{100 * x:.1f}%"
    for name, chain_names in configs:
        res = {ts: chain(chain_names, ts) for ts in SETS}
        t1, t2a, t2b, t3 = (score(res[ts]) for ts in SETS)
        t2a_x = score(res["t2a"], skip_cat="real_colour_names")
        lines.append(f"| {name} | {f(t1['exact'])} | {f(t2a['exact'])} / {f(t2a['cw'])} | "
                     f"{f(t2a_x['exact'])} / {f(t2a_x['cw'])} | {f(t2b['exact'])} / {f(t2b['cw'])} | "
                     f"{f(t3['t3_refusal'])} |")
    md = "\n".join(lines)
    print(md)
    with open(os.path.join(R, "gemini_compare.md"), "w") as fh:
        fh.write(md + "\n")


if __name__ == "__main__":
    main()
