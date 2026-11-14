"""Scores of fetched v1.5 runs (artifacts/eval/v15/<tag>), per run and per group of tags.

    python3 policy/decision_oracle/modal_runs/summarize.py TAG [TAG ...]     one or more runs
    python3 policy/decision_oracle/modal_runs/summarize.py --group v15off-fixed-   every fetched run starting with that

Per run: sorted / objects, outcomes, gate, clips, command rate, every trial, and every executed pick
(seed:shape/arm/grasp/route/grasp check E=empty H=held) from the decision log.
"""
import glob
import json
import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASE = os.environ.get("V15_RUNS") or os.path.join(ROOT, "artifacts", "eval", "v15")   # V15_RUNS: another folder


def load(tag):
    fs = glob.glob(os.path.join(BASE, tag, "**", "eval.json"), recursive=True)
    return json.load(open(fs[0])) if fs else None


def run(tag):
    d = load(tag)
    if d is None:
        print(f"{tag}: no eval.json yet")
        return
    s = d["summary"]
    print(f"{tag}: {s['objects_correct']}/{s['objects']} correct, outcomes {s['outcome_counts']}, "
          f"gate {s['gate']['passed']}, clips {s['safety_clipped_steps_total']}, hz {s['command_hz_min']}")
    for t in d["trials"]:
        print(f"  seed {t['seed']}: {t['n_correct']}/{t['n_objects']} score {t['score']}/{t['max_score']} "
              f"end={t['end_reason']} sim {t['sim_s']:.0f}s  {t['instruction'][:90]}")
    dl = glob.glob(os.path.join(BASE, tag, "**", "decisions_*.jsonl"), recursive=True)
    if dl:
        recs = [json.loads(line) for line in open(dl[0]) if line.strip()]
        gc = {r["decision"]: r for r in recs if r["type"] == "grasp_check"}
        rows = []
        for r in recs:
            if r["type"] == "exec":
                o, g = r["option"], gc.get(r["decision"])
                rows.append(f"{r['seed']}:{o['shape'][:4]}/{o['arm'][0]}/{o['grasp']}/{o['route'][0]}/"
                            f"{'E' if g and g['empty'] else ('H' if g else '-')}")
        print("  picks (seed:shape/arm/grasp/route/grasp-check):", " ".join(rows))


def group(prefix):
    tags = sorted(os.path.basename(p) for p in glob.glob(os.path.join(BASE, prefix + "*")) if os.path.isdir(p))
    scores, c, n, clips, gate, outs, hz = [], 0, 0, 0, True, {}, []
    for tag in tags:
        d = load(tag)
        if d is None:
            continue
        s = d["summary"]
        for t in d["trials"]:
            scores.append(t["score"]); c += t["n_correct"]; n += t["n_objects"]
        clips += s["safety_clipped_steps_total"]; gate &= s["gate"]["passed"]; hz.append(s["command_hz_min"])
        for k, v in s["outcome_counts"].items():
            outs[k] = outs.get(k, 0) + v
    if not scores:
        print(f"{prefix}*: nothing fetched")
        return
    print(f"{prefix}* ({len(tags)} runs, {len(scores)} episodes): {c}/{n} sorted, score {statistics.mean(scores):+.2f} "
          f"± {statistics.pstdev(scores):.2f}, outcomes {outs}, clips {clips}, gate {gate}, hz min {min(hz)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--group"]:
        for p in a[1:]:
            group(p)
    else:
        for tag in a:
            run(tag)
