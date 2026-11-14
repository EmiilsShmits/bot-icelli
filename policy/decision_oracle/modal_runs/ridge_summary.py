"""Summarise ridge_sweep.py runs fetched from Modal (aalto-sim-out/<tag>/runs/ridge_<tag>.json).

    python3 policy/decision_oracle/modal_runs/ridge_summary.py artifacts/eval/ridge/ridge-*/

Per run and arm: ridge grasps that closed on the object (grasp check), objects sorted, and for the misses how far the
prism moved and turned during the pick (pushed vs untouched)."""
import glob
import json
import os
import sys

import numpy as np


def main(dirs):
    print("| run | shift (mm) | arm | ridge grasps held | sorted | misses: object moved (mm) / tilted (deg) |")
    print("|---|---|---|---|---|---|")
    for d in dirs:
        f = (glob.glob(os.path.join(d, "**", "ridge_*.json"), recursive=True) or [None])[0]
        if f is None:
            print(f"| {os.path.basename(d.rstrip('/'))} | no results | | | | |")
            continue
        rows = json.load(open(f))
        for arm in ("left", "right"):
            rr = [r for r in rows if r["arm"] == arm]
            if not rr:
                continue
            ridge = [r for r in rr if r["grasp"] == "face"]
            miss = []
            for r in ridge:
                if r["held"] or not r["trace"]:
                    continue
                p0, p1 = np.array(r["trace"][0]["pos"]), np.array(r["trace"][-1]["pos"])
                miss.append(f"{np.linalg.norm(p1[:2] - p0[:2]) * 1000:.0f}/{abs(r['trace'][-1]['tilt_deg'] - r['trace'][0]['tilt_deg']):.0f}")
            print(f"| {os.path.basename(d.rstrip('/'))} | {tuple(rr[0]['shift_mm'])} | {arm} | "
                  f"{sum(bool(r['held']) for r in ridge)}/{len(ridge)} | {sum(r['outcome'] == 'correct' for r in rr)}/{len(rr)} | "
                  f"{', '.join(miss) or '-'} |")


if __name__ == "__main__":
    main(sys.argv[1:])
