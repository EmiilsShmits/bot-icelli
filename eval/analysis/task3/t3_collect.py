"""Per-shape task-3 outcomes for downloaded Modal runs: python t3_collect.py <sim_out dir> tag [tag ...]"""
import collections
import glob
import json
import os
import sys

root, tags = sys.argv[1], sys.argv[2:]
for tag in tags:
    files = glob.glob(os.path.join(root, tag, "runs", "eval", "*", "eval.json"))
    if not files:
        print(f"{tag}: no eval.json")
        continue
    per = collections.Counter()
    scores = []
    for f in files:
        d = json.load(open(f))
        for e in d["trials"]:
            scores.append(e["score"])
            outs = [(o["name"].split("_")[2], o["outcome"]) for o in e["outcomes"]]
            for shape, out in outs:
                per[(shape, out)] += 1
            print(f"{tag} seed {e['seed']} score {e['score']:+d} {outs}")
    shapes = sorted({s for s, _ in per})
    summary = "; ".join(f"{s}: " + ", ".join(f"{o} {n}" for (s2, o), n in sorted(per.items()) if s2 == s) for s in shapes)
    print(f"== {tag}: scores {scores} sum {sum(scores):+d} | {summary}")
