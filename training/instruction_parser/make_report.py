"""Build the tables for RESULTS.md from results/*/*.summary.json and preds.

  python3 make_report.py > results/tables.md
"""
from __future__ import annotations

import glob
import json
import os

from spec import INVALID, SLOTS, fixed_order

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")


def load():
    out = {}
    for f in glob.glob(os.path.join(R, "*", "*.summary.json")):
        d = os.path.basename(os.path.dirname(f))
        if "smoke" in d:
            continue
        s = json.load(open(f))
        out[(s["method"], s["testset"].replace(".jsonl", ""))] = (s, d)
    return out


def p(x):
    return "–" if x is None else f"{100 * x:.1f}"


def main():
    S = load()
    methods = sorted({m for m, _ in S}, key=lambda m: (m != "rule", m))
    print("## Full results (method × test set)\n")
    print("Exact = all 10 slots right. CW = confidently wrong (valid answer, ≥1 wrong slot). Inv = refused/malformed. "
          "DS = distractor safety (`other` correct). T3 = refusal rate on invalid instructions. Latency = warm, batch 1, on T2a.\n")
    print("| Method | T1 exact | T2a exact | T2a CW | T2a inv | T2b exact | T2b CW | T2b inv | T2b DS | T3 refusal | p50 / p95 s | peak VRAM GB |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in methods:
        g = lambda t, k: S.get((m, t), ({}, ""))[0].get(k)
        lat = g("t2a", "latency_p50_s")
        latstr = f"{lat:.3f} / {g('t2a', 'latency_p95_s'):.3f}" if lat is not None else "–"
        vram = g("t2a", "peak_vram_gb")
        print(f"| `{m}` | {p(g('t1', 'exact_acc'))} | {p(g('t2a', 'exact_acc'))} | {p(g('t2a', 'confidently_wrong_rate'))} | "
              f"{p(g('t2a', 'invalid_rate'))} | {p(g('t2b', 'exact_acc'))} | {p(g('t2b', 'confidently_wrong_rate'))} | "
              f"{p(g('t2b', 'invalid_rate'))} | {p(g('t2b', 'distractor_safety'))} | {p(g('t3', 't3_refusal_rate'))} | "
              f"{latstr} | {'–' if vram is None else f'{vram:.1f}'} |")
    for t in ("t2a", "t2b"):
        cats = sorted({c for m in methods for c in S.get((m, t), ({}, ""))[0].get("per_category", {})})
        print(f"\n## Per-category exact accuracy, {t.upper()} (%)\n")
        print("| Method | " + " | ".join(cats) + " |")
        print("|---|" + "---|" * len(cats))
        for m in methods:
            pc = S.get((m, t), ({}, ""))[0].get("per_category")
            if pc:
                print(f"| `{m}` | " + " | ".join(p(pc.get(c, {}).get("exact_acc")) for c in cats) + " |")
    print("\n## T3 refusal per category (%)\n")
    cats = sorted({c for m in methods for c in S.get((m, "t3"), ({}, ""))[0].get("t3_per_category_refusal", {})})
    print("| Method | " + " | ".join(cats) + " |")
    print("|---|" + "---|" * len(cats))
    for m in methods:
        pc = S.get((m, "t3"), ({}, ""))[0].get("t3_per_category_refusal")
        if pc:
            print(f"| `{m}` | " + " | ".join(p(pc.get(c)) for c in cats) + " |")
    print("\n## Format C: accuracy vs confidence threshold (low-confidence answers go to the fallback)\n")
    for m in methods:
        if not m.endswith(":C"):
            continue
        print(f"\n`{m}`\n")
        print("| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |")
        print("|---|---|---|---|---|---|---|---|")
        ca = {c["threshold"]: c for c in S.get((m, "t2a"), ({}, ""))[0].get("confidence_curve", [])}
        cb = {c["threshold"]: c for c in S.get((m, "t2b"), ({}, ""))[0].get("confidence_curve", [])}
        c3 = {c["threshold"]: c for c in S.get((m, "t3"), ({}, ""))[0].get("confidence_curve", [])}
        for th in sorted(ca):
            a, b, c = ca[th], cb.get(th, {}), c3.get(th, {})
            print(f"| {th} | {p(a.get('coverage'))} | {p(a.get('exact_acc_overall'))} | {p(a.get('confidently_wrong_rate'))} | "
                  f"{p(b.get('coverage'))} | {p(b.get('exact_acc_overall'))} | {p(b.get('confidently_wrong_rate'))} | "
                  f"{p(c.get('t3_refusal_rate'))} |")


def worst(method_dir, n=10):
    """Wrong answers of one method on T2a+T2b, confidently-wrong first, most wrong slots first."""
    rows = []
    for t in ("t2a", "t2b"):
        f = os.path.join(R, method_dir, f"{t}.preds.jsonl")
        if os.path.exists(f):
            rows += [json.loads(l) for l in open(f)]
    bad = []
    for r in rows:
        if r["pred"] == r["label"]:
            continue
        cw = r["pred"] not in (None, INVALID)
        nwrong = sum(r["pred"][s] != r["label"][s] for s in SLOTS) if cw else 10
        bad.append((not cw, -nwrong, r))
    bad.sort(key=lambda x: (x[0], x[1]))
    print(f"\n## Worst failures: `{method_dir}`\n")
    print("| id | category | instruction | expected | got |")
    print("|---|---|---|---|---|")
    for _, _, r in bad[:n]:
        got = r["pred"] if r["pred"] in (None, INVALID) else fixed_order(r["pred"])
        if got is None:
            got = "malformed: " + (r.get("raw") or "")[:60].replace("\n", " ")
        txt = r["text"].replace("|", "/").replace("\n", " ")
        print(f"| {r['id']} | {r['category']} | {txt} | {fixed_order(r['label'])} | {got} |")


if __name__ == "__main__":
    import sys
    main()
    for d in sys.argv[1:]:
        worst(d)
