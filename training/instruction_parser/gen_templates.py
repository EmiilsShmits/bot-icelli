"""Renders of Aalto's 8 sort_language training templates for the student's training data (RESULTS.md: "Aalto templates:
1,200 examples rendered from the 8 training templates", added after the programmatic-only student refused 13 % of T1).
The 14 Nov run made them by hand; this script makes the same kind of rows for the v1.6g re-train (run_v16g_retrain.sh).

  python3 gen_templates.py --n 1200 --out data_train/templates.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random

from build_t1 import BINS, COLORS, TEMPLATES
from spec import interpret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out", default="data_train/templates.jsonl")
    a = ap.parse_args()
    R = random.Random(a.seed)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        for i in range(a.n):
            colors, bins = R.sample(COLORS, 3), R.sample(BINS, 3)
            w = {f"c{j}": c for j, c in enumerate(colors)}
            w.update({f"C{j}": c.capitalize() for j, c in enumerate(colors)})
            w.update({f"b{j}": b for j, b in enumerate(bins)})
            spec = {"mapping": dict(zip(colors, bins))}
            f.write(json.dumps({"text": TEMPLATES[i % len(TEMPLATES)].format(**w), "spec": spec,
                                "label": interpret(spec), "kind": "aalto_template"}) + "\n")
    print(f"wrote {a.n} template rows to {a.out}")


if __name__ == "__main__":
    main()
