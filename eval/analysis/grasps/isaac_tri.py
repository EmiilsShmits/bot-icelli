"""V16_TRI off vs mid in Isaac: reads the tri_sweep.py results (one standing triangle per episode, the same 24 cases
for both settings) and prints sorted per case and held per grasp attempt, by arm and by setting.

    python3 eval/analysis/grasps/isaac_tri.py artifacts/eval/isaac/tri16
(the folder holds one sub-folder per Modal tag, tri16-<off|mid>-<k>, each with a tri.json somewhere inside)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(root):
    rows = []
    for p in sorted(Path(root).rglob("tri.json")):
        rows += json.load(open(p))
    return rows


def main(root):
    rows = load(root)
    by = defaultdict(dict)
    for r in rows:
        by[r["tri"]][r["i"]] = r
    print(f"{root}: " + ", ".join(f"{k} {len(v)} cases" for k, v in sorted(by.items())))
    for mode in ("off", "mid"):
        rr = list(by.get(mode, {}).values())
        if not rr:
            continue
        print(f"\nV16_TRI={mode}")
        for arm in ("left", "right", None):
            g = [r for r in rr if arm is None or r["arm_side"] == arm]
            mv = [m for r in g for m in r["moves"]]
            held = sum(m.endswith(":H") for m in mv)
            empty = sum(m.endswith(":E") for m in mv)
            ok = sum(r["outcome"] == "correct" for r in g)
            print(f"  {arm or 'all':5s} sorted {ok}/{len(g)}   grasps held {held}/{held + empty}   "
                  f"tries per case {len(mv) / max(len(g), 1):.1f}")
    common = sorted(set(by.get("off", {})) & set(by.get("mid", {})))
    if common:
        better = sum(by["mid"][i]["outcome"] == "correct" and by["off"][i]["outcome"] != "correct" for i in common)
        worse = sum(by["off"][i]["outcome"] == "correct" and by["mid"][i]["outcome"] != "correct" for i in common)
        print(f"\nPaired over {len(common)} cases: mid better {better}, worse {worse}, same {len(common) - better - worse}")
        print("\n  i  arm    mat x,y     yaw | off moves -> outcome | mid moves -> outcome")
        for i in common:
            o, m = by["off"][i], by["mid"][i]
            print(f"{i:3d}  {o['arm_side']:5s} ({o['x']:.2f},{o['y']:.2f}) {o['layout_yaw']:4.0f} | "
                  f"{' '.join(o['moves'])} -> {o['outcome']} | {' '.join(m['moves'])} -> {m['outcome']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/eval/isaac/tri16")
