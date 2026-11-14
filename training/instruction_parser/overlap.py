"""Word n-gram overlap between texts (template overlap for T2a, train-vs-test leakage for Phase 3).

  python3 overlap.py templates data/t2a.jsonl           # overlap of T2a with Aalto's 8 templates
  python3 overlap.py dedupe TRAIN.jsonl OUT.jsonl data/t2a.jsonl data/t2b.jsonl [--max-jacc 0.6]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics


def grams(text, n=3):
    w = re.findall(r"[a-z]+", text.lower())
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def jacc(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def contain(a, b):
    """share of a's n-grams that also appear in b"""
    return len(a & b) / len(a) if a else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--max-jacc", type=float, default=0.6)
    a = ap.parse_args()
    if a.mode == "templates":
        from build_t1 import TEMPLATES
        tg = set()
        for t in TEMPLATES:
            tg |= grams(re.sub(r"\{[cCb]\d\}", "x", t))
        for f in a.files:
            rows = [json.loads(l) for l in open(f)]
            cs = [contain(grams(re.sub(r"\b(red|yellow|blue|left|center|right)\b", "x", r["text"].lower())), tg)
                  for r in rows]
            print(json.dumps({"file": f, "n": len(rows), "trigram_containment_in_templates_mean": round(statistics.mean(cs), 4),
                              "max": round(max(cs), 4), "share_over_0.5": round(sum(c > 0.5 for c in cs) / len(cs), 4)}))
        return
    if a.mode == "dedupe":
        train, out, tests = a.files[0], a.files[1], a.files[2:]
        test_g = [grams(json.loads(l)["text"]) for f in tests for l in open(f)]
        kept = removed = 0
        maxes = []
        with open(out, "w") as fo:
            for l in open(train):
                g = grams(json.loads(l)["text"])
                m = max((jacc(g, t) for t in test_g), default=0.0)
                maxes.append(m)
                if m > a.max_jacc:
                    removed += 1
                    continue
                kept += 1
                fo.write(l)
        print(json.dumps({"train": train, "kept": kept, "removed_near_dupes": removed,
                          "max_trigram_jaccard_mean": round(statistics.mean(maxes), 4),
                          "max_trigram_jaccard_p95": round(sorted(maxes)[int(0.95 * (len(maxes) - 1))], 4),
                          "threshold": a.max_jacc}))


if __name__ == "__main__":
    main()
