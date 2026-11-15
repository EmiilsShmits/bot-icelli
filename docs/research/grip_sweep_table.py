"""Hold-rate table from grasp-bench sweep results (Marcus's sim/modal_sim.py --action grasp-bench --sweep ...).

    python grip_sweep_table.py grip-sweep-data/gs1 grip-sweep-data/gs1dr [--base base]

Each input folder holds one <setting>.json per setting ({"env", "bench", "dr", "rows"}), written by the sweep.
One row = one bench case = one standing object; with BENCH_TRIES=1 the agent makes exactly one grasp on it.
  held     the grasp lifted the object and it ended in a bin (outcome correct or wrong)
  dropped  the grasp check passed but the object did not reach a bin (lost in the carry / release)
  missed   the hand closed on nothing (grasp check after the lift)
  no plan  no grasp was made (planner found no safe plan); left out of the hold rate
  tipped   the object ended lying down (axis > 45 deg from vertical) on the counter
Hold rate = held / grasps made, with a Wilson 95 % interval. "vs base" counts the cases (same shape, yaw, position)
that this setting held and base did not, and the other way round.
"""
import json
import math
import sys
from pathlib import Path


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def classify(r):
    """The FIRST grasp on the object. (Without BENCH_MAX_PICKS=1 the bench may grasp again when a miss moved the
    object far enough to get a new id; later grasps are ignored here.)"""
    att = r.get("attempts") or []
    if not att or att[0] == "failed":
        return "no plan"
    if att[0] == "missed":
        return "missed"
    if att[0] == "completed":
        return "held" if len(att) == 1 and r["outcome"] in ("correct", "wrong") else "dropped"
    return "other"


def key(r):
    return (r["shape"], r["yaw"], r["x"], r["y"])


def main(argv):
    base_name = "base"
    if "--base" in argv:
        i = argv.index("--base")
        base_name = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    settings = {}
    for folder in argv:
        for f in sorted(Path(folder).glob("*.json")):
            d = json.loads(f.read_text())
            settings[f"{Path(folder).name}/{f.stem}"] = d
    base = next((d for k, d in settings.items() if k.endswith("/" + base_name)), None)
    base_by = {key(r): classify(r) for r in (base or {}).get("rows", [])}
    print("| setting | shape | grasps | held | hold rate (95 % CI) | missed | dropped | tipped | no plan | grasp z (cm) | vs base (+/-) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, d in settings.items():
        rows = d.get("rows") or []
        if d.get("error") or not rows:
            print(f"| {name} | - | 0 | - | run failed: {str(d.get('error'))[:60]} | | | | | | |")
            continue
        for shape in dict.fromkeys(r["shape"] for r in rows):
            v = [r for r in rows if r["shape"] == shape]
            c = [classify(r) for r in v]
            made = sum(x != "no plan" for x in c)
            held = c.count("held")
            lo, hi = wilson(held, made)
            tipped = sum(1 for r, x in zip(v, c) if x != "held" and (r.get("tilt_deg") or 0) > 45)
            zs = [z for r in v for z in (r.get("grasp_z_cm") or [])[:1] if z is not None]
            zt = f"{sum(zs) / len(zs):.1f}" if zs else "-"
            plus = sum(1 for r, x in zip(v, c) if x == "held" and base_by.get(key(r)) not in (None, "held", "no plan"))
            minus = sum(1 for r, x in zip(v, c) if x not in ("held", "no plan") and base_by.get(key(r)) == "held")
            rate = f"{100 * held / made:.0f} % ({100 * lo:.0f}-{100 * hi:.0f})" if made else "-"
            print(f"| {name} | {shape} | {made} | {held} | {rate} | {c.count('missed')} | {c.count('dropped')} | "
                  f"{tipped} | {c.count('no plan')} | {zt} | {'' if d is base else f'+{plus} / -{minus}'} |")


if __name__ == "__main__":
    main(sys.argv[1:])
