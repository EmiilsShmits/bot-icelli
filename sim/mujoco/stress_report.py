"""Report of a MuJoCo stress run (modal_mujoco.py::stress): success overall, per task, per randomised factor, and the
misses by cause. Reads aalto-sim-out/mujoco/<run>/all.jsonl (fetched into artifacts/eval/mujoco/<run>/).

    .venv/bin/modal volume get aalto-sim-out mujoco/<run>/all.jsonl artifacts/eval/mujoco/<run>/
    python3 sim/mujoco/stress_report.py <run> [--md out.md]
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NUMERIC = {  # factor: bucket edges (values below the first edge go in the first bucket)
    "table_edge_cm": [8, 10, 12], "cam_pitch_deg": [-1, 0, 1], "cam_yaw_deg": [-0.75, 0, 0.75],
    "cam_roll_deg": [-0.5, 0, 0.5], "cam_height_cm": [-0.75, 0, 0.75], "cam_shift_cm": [-0.5, 0, 0.5],
    "bin_wall_cm": [6.5, 7, 7.5], "bin_jitter_cm": [0.75, 1.0, 1.25], "friction": [0.875, 1.05, 1.225],
    "mass_g": [42, 55, 68], "key_light": [0.75, 1.0, 1.25], "ambient": [0.22, 0.3, 0.38], "brightness": [0.92, 1.0, 1.08],
}


def bucket(v, edges):
    for i, e in enumerate(edges):
        if v < e:
            return f"< {e}" if i == 0 else f"{edges[i - 1]}–{e}"
    return f">= {edges[-1]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(ROOT / "artifacts/eval/mujoco" / a.run / "all.jsonl") if l.strip()]
    ok = [r for r in rows if r.get("trial")]
    bad = [r for r in rows if not r.get("trial")]
    L = []
    p = L.append
    obj = sum(r["trial"]["n_objects"] for r in ok)
    cor = sum(r["trial"]["n_correct"] for r in ok)
    gate = sum(bool(r["trial"].get("gate_ok")) for r in ok)
    allc = sum(bool(r["trial"].get("all_correct")) for r in ok)
    hz = sorted(r["trial"].get("command_hz") or 0 for r in ok)
    d1m = sum(r["log"]["d1_missing"] for r in ok)
    d1 = sum(r["log"]["labels"] for r in ok)
    p(f"# MuJoCo stress run {a.run}\n")
    p(f"- episodes: {len(ok)} scored, {len(bad)} crashed/missing")
    p(f"- objects sorted: **{cor}/{obj} ({100 * cor / max(obj, 1):.1f} %)**; episodes all correct {allc}/{len(ok)}")
    p(f"- gate passed {gate}/{len(ok)}; command Hz min {hz[0] if hz else '-'} median {hz[len(hz) // 2] if hz else '-'}")
    p(f"- Decision 1 answers missing for {d1m}/{d1} labelled detections (API failures -> v1.5 HSV fallback)\n")
    outc = collections.Counter(o["outcome"] for r in ok for o in r["trial"]["outcomes"])
    p("## Outcomes of all objects\n")
    p("| outcome | n |\n|---|---|")
    for k, v in outc.most_common():
        p(f"| {k} | {v} |")
    gr = sum(r["log"]["grasps"] for r in ok)
    em = sum(r["log"]["empty"] for r in ok)
    p(f"\nGrasps planned {gr}, grasp check found the hand empty {em} times.\n")

    def table(title, key):
        g = collections.defaultdict(lambda: [0, 0, 0])
        for r in ok:
            k = key(r)
            g[k][0] += r["trial"]["n_correct"]
            g[k][1] += r["trial"]["n_objects"]
            g[k][2] += 1
        p(f"### {title}\n")
        p("| value | episodes | sorted | rate |\n|---|---|---|---|")
        for k in sorted(g, key=str):
            c, n, e = g[k]
            p(f"| {k} | {e} | {c}/{n} | {100 * c / max(n, 1):.0f} % |")
        p("")

    p("## Success by factor\n")
    if any(r["trial"]["dr"].get("mode", "all") != "all" for r in ok):
        table("randomisation mode (paired: same seeds)", lambda r: r["trial"]["dr"].get("mode", "all"))
    if any(r.get("spec", {}).get("calib") for r in ok):
        table("calibration x randomisation mode (paired)", lambda r: f"{r['spec'].get('calib')} / "
              f"{r['trial']['dr'].get('mode', 'all')}")
    table("task", lambda r: r["trial"]["task"])
    table("lying prisms", lambda r: r["trial"]["dr"]["tip"])
    table("colour set", lambda r: r["trial"]["dr"]["colors"])
    for f, edges in NUMERIC.items():
        table(f, lambda r, f=f, e=edges: bucket(r["trial"]["dr"][f], e))
    by_shape = collections.defaultdict(lambda: [0, 0])
    for r in ok:
        for o in r["trial"]["outcomes"]:
            s = o["name"].split("_")[2]
            by_shape[s][0] += o["outcome"] == "correct"
            by_shape[s][1] += 1
    p("### shape\n\n| shape | sorted | rate |\n|---|---|---|")
    for s, (c, n) in sorted(by_shape.items()):
        p(f"| {s} | {c}/{n} | {100 * c / max(n, 1):.0f} % |")
    p("\n## Worst episodes\n")
    for r in sorted(ok, key=lambda r: r["trial"]["n_correct"] / max(r["trial"]["n_objects"], 1))[:12]:
        t = r["trial"]
        miss = [f"{o['name'][4:]}:{o['outcome']}" for o in t["outcomes"] if o["outcome"] != "correct"]
        p(f"- id {r['id']:03d} seed {t['seed']} {t['task']} {t['n_correct']}/{t['n_objects']} end={t['end_reason']} "
          f"hz={t.get('command_hz')} misses {miss} dr {t['dr']}")
    for r in bad:
        p(f"- FAILED id {r.get('id')}: {r.get('error') or r.get('rc')}")
    text = "\n".join(L)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n")


if __name__ == "__main__":
    main()
