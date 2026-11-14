#!/usr/bin/env python3
"""Markdown table of every eval.json (aaltonomous.sim.evaluate output) under a folder, oldest run first.

    python3 summarize.py [folder, default ~/runs/eval] [--trials]     # --trials: one row per trial as well

The policy column shows what really ran: Aalto's evaluator stores `oracle_events` in every trial of an oracle run,
so a run is labelled "ORACLE" whatever its folder or --team name says (`--container` without `--policy` silently
runs the oracle; that mislabelled two of our runs on Sat 14 Nov).
"""
import json
import sys
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
root = Path(args[0]) if args else Path.home() / "runs" / "eval"
per_trial = "--trials" in sys.argv


def kv(d):
    return ", ".join(f"{k} {v}" for k, v in sorted((d or {}).items()))


def who(d):
    """What ran, from the trials themselves: the oracle leaves `oracle_events` in each trial."""
    s = d["summary"]
    name = s.get("team") or s["policy"]
    if any("oracle_events" in t for t in d.get("trials", [])):
        return "ORACLE (privileged poses)" + ("" if name == "oracle" else f", labelled {name}")
    return name


print("| run | policy | task | variant | trials (seeds) | score mean ± sd | % of max | objects correct "
      "| episodes all correct | outcomes | end reasons | clips | min cmd Hz | min real-time Hz | gate |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
runs = sorted(root.glob("*/eval.json"), key=lambda p: p.stat().st_mtime)
for f in runs:
    d = json.loads(f.read_text())
    s = d["summary"]
    if not s.get("trials"):
        continue
    gate = "PASS" if s["gate"]["passed"] else f"FAIL {s['gate']['failed_trials']}"
    print(f"| {f.parent.name} | {who(d)} | {s['task']} | {s['variant']} "
          f"| {s['trials']} ({s['seeds'][0]}–{s['seeds'][-1]}) | {s['score_mean']:+.2f} ± {s['score_std']:.2f} "
          f"| {100 * s['score_frac']:.0f} % | {s['objects_correct']}/{s['objects']} | {s['episodes_all_correct']}/{s['trials']} "
          f"| {kv(s['outcome_counts'])} | {kv(s['end_reasons'])} | {s['safety_clipped_steps_total']} "
          f"| {s['command_hz_min']} | {s['policy_hz_rt_min']} | {gate} |")
if per_trial:
    for f in runs:
        d = json.loads(f.read_text())
        print(f"\n### {f.parent.name}\n\n| seed | instruction | mapping | correct | score | end | clips | wall s | gate |")
        print("|---|---|---|---|---|---|---|---|---|")
        for t in d["trials"]:
            m = t.get("mapping") or {}
            print(f"| {t['seed']} | {t.get('instruction', '')} | {', '.join(f'{c}→{b}' for c, b in m.items())} "
                  f"| {t['n_correct']}/{t['n_objects']} | {t['score']:+d} | {t['end_reason']} "
                  f"| {(t.get('safety') or {}).get('clipped_steps')} | {t.get('episode_wall_s')} "
                  f"| {'ok' if t['gate_ok'] else ', '.join(t['gate_why'])} |")
