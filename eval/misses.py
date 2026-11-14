#!/usr/bin/env python3
"""Where a run's misses are: success rate by object position (cross-body or not), shape and side.

    python3 misses.py <run folder or eval.json> [...]      # e.g. ~/runs/eval/baseline_sort_fixed_nominal_*/

"Far cross-body" = more than 8 cm on the far side of the arm that serves the object's bin (what v1.1 hands over).
Positions come from the trial layout (mat coords) through scene.yaml's default mat_origin_in_pelvis.
"""
import json
import sys
from pathlib import Path

MAT_X_TO_PELVIS_Y = -0.45            # scene.yaml mat_origin_in_pelvis[1]: pelvis y = mat x - 0.45
BIN_Y = {"left": 0.21, "center": 0.0, "right": -0.21}


def objects(run):
    f = Path(run)
    d = json.loads((f / "eval.json" if f.is_dir() else f).read_text())
    for t in d["trials"]:
        pool = {}
        for o in t["layout"]:
            pool.setdefault(f"obj_{o['color']}_{o['shape']}", []).append(o)
        used = {}
        for oc in t["outcomes"]:
            base = oc["name"].rsplit("_", 1)[0]
            i = used.get(base, 0)
            used[base] = i + 1
            o = pool[base][i]
            y = o["x"] + MAT_X_TO_PELVIS_Y
            b = (t.get("mapping") or {}).get(o["color"])
            by = BIN_Y.get(b, 0.0)
            cross = (by > 0.1 and y < -0.08) or (by < -0.1 and y > 0.08)
            yield {"seed": t["seed"], "shape": o["shape"], "color": o["color"], "bin": b, "y": round(y, 3),
                   "cross": cross, "outcome": oc["outcome"]}


def rate(rows):
    n, k = len(rows), sum(r["outcome"] == "correct" for r in rows)
    return f"{k}/{n} ({100 * k / max(1, n):.0f} %)" if n else "-"


for run in sys.argv[1:]:
    rows = list(objects(run))
    print(f"\n{Path(run).name or run}")
    print(f"  all objects           {rate(rows)}")
    print(f"  far cross-body        {rate([r for r in rows if r['cross']])}")
    print(f"  not cross-body        {rate([r for r in rows if not r['cross']])}")
    for s in sorted({r["shape"] for r in rows}):
        print(f"  {s:21s} {rate([r for r in rows if r['shape'] == s])}")
    for lo, hi in ((-0.2, -0.08), (-0.08, 0.08), (0.08, 0.2)):
        print(f"  pelvis y {lo:+.2f}..{hi:+.2f}  {rate([r for r in rows if lo <= r['y'] < hi])}")
    miss = [r for r in rows if r["outcome"] != "correct"]
    print("  misses:", ", ".join(f"{r['seed']} {r['color']} {r['shape']}->{r['bin']} y={r['y']:+.2f}"
                                 f"{' CROSS' if r['cross'] else ''} [{r['outcome']}]" for r in miss))
