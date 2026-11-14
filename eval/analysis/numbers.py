"""Every number quoted in FINDINGS.md, recomputed from a trace.py output folder. Runs anywhere with pandas.

    python eval/analysis/numbers.py eval/analysis/data/2026-11-14_1745 [--runs SUBSTRING ...]

Runs are labelled by folder name without the date suffix. "Held" = the fingers stopped on something after closing
(picks.csv result is not empty_grasp). Column meanings: README.md.
"""
from __future__ import annotations

import argparse
import re

import pandas as pd


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f} %)" if b else "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data")
    ap.add_argument("--runs", nargs="*", help="only runs whose folder name contains one of these")
    a = ap.parse_args()
    ep, ob, pk = (pd.read_csv(f"{a.data}/{n}.csv") for n in ("episodes", "objects", "picks"))
    for df in (ep, ob, pk):
        df["R"] = df["run"].map(lambda r: re.sub(r"_\d{8}_\d{6}/?$", "", r))
        if a.runs:
            df.drop(df.index[~df["run"].apply(lambda r: any(s in r for s in a.runs))], inplace=True)
    pk = pk.sort_values(["R", "episode", "t_close"]).copy()
    pk["held"] = pk["result"] != "empty_grasp"
    pk["attempt"] = pk.groupby(["R", "episode", "object"]).cumcount() + 1
    runs = list(dict.fromkeys(ep.sort_values("run")["R"]))

    def section(title):
        print(f"\n## {title}")

    section("Runs")
    for R in runs:
        E, O, P = ep[ep.R == R], ob[ob.R == R], pk[pk.R == R]
        print(f"- {R}: {', '.join(sorted(E.policy_actual.unique()))}; {len(E)} episodes (seeds {E.seed.min()}-{E.seed.max()}); "
              f"sorted {pct(int((O.outcome == 'correct').sum()), len(O))}; score {E.score.sum():+.0f}; "
              f"end {E.end_reason.value_counts().to_dict()}; sim s per sorted object "
              f"{E.sim_s.sum() / max(1, (O.outcome == 'correct').sum()):.0f}")

    section("Grasps")
    for R in runs:
        P = pk[pk.R == R]
        print(f"- {R}: {len(P)} grasps; empty {pct(int((P.result == 'empty_grasp').sum()), len(P))}; "
              f"results {P.result.value_counts().to_dict()}")

    section("Held after closing, by attempt on the same object")
    for R in runs:
        P = pk[pk.R == R]
        print(f"- {R}: " + "; ".join(f"attempt {int(n)} {pct(int(g.held.sum()), len(g))}" for n, g in P.groupby("attempt") if n <= 4))

    section("Held on the first attempt, by shape")
    for R in runs:
        P = pk[(pk.R == R) & (pk.attempt == 1)]
        print(f"- {R}: " + "; ".join(f"{s} {pct(int(g.held.sum()), len(g))}" for s, g in P.groupby("shape")))

    section("First-attempt aim: planned (or FK) grasp point to the object's start position, cm (x, y only)")
    for R in runs:
        P = pk[(pk.R == R) & (pk.attempt == 1)]
        md = lambda s: f"{100 * s.median():.1f}" if len(s) else "-"
        print(f"- {R}: median empty {md(P[~P.held].object_dist_m)}, held {md(P[P.held].object_dist_m)}, "
              f"max {100 * P.object_dist_m.max():.1f}")

    section("Objects sorted: by shape / far cross-body / distance from the robot (pelvis x)")
    for R in runs:
        O = ob[ob.R == R]
        ok = lambda g: pct(int((g.outcome == "correct").sum()), len(g))
        shapes = "; ".join(f"{s} {ok(g)}" for s, g in O.groupby("shape"))
        far = O.far_cross_body.astype(str) == "True"
        print(f"- {R}: {shapes} | far cross-body {ok(O[far])}, near side {ok(O[~far])} | "
              f"x < 0.30 m {ok(O[O.x < 0.30])}, x >= 0.30 m {ok(O[O.x >= 0.30])}")

    section("Why unsorted objects were lost (objects.csv loss_reason)")
    for R in runs:
        O = ob[(ob.R == R) & (ob.outcome != "correct")]
        print(f"- {R}: {len(O)} unsorted: {O.loss_reason.value_counts().to_dict()}")

    section("Released over the target bin: scored or not, by earlier releases over that bin in the episode")
    for R in runs:
        P = pk[(pk.R == R) & (pk.result == "released_in_target_bin")]
        rows = []
        for k, g in P.groupby(P.earlier_releases_same_bin.fillna(0).clip(upper=2)):
            above = g.object_final_where.astype(str).str.startswith(("above_rim", "raised")).sum()
            rows.append(f"{int(k) if k < 2 else '2+'} earlier: {len(g)} released, {int((g.object_outcome == 'correct').sum())} "
                        f"scored, {int(above)} resting above the rim")
        print(f"- {R}: " + "; ".join(rows))

    section("Episodes")
    cols = ["seed", "n_correct", "n_objects", "score", "picks", "empty_grasps", "slips", "never_attempted", "end_reason"]
    for R in runs:
        print(f"\n{R}\n" + ep[ep.R == R].sort_values("seed")[cols].to_string(index=False))


if __name__ == "__main__":
    main()
