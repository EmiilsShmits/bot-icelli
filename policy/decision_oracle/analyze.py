"""Tables from evaluation runs: Aalto's eval.json (+ our decisions.jsonl when there is one).

    python analyze.py RUN_DIR[=decisions.jsonl] [RUN_DIR2[=...]] ...    (plain Python 3, numpy-free)

Per run: objects correct per shape, score, clipped steps, command / policy rate, sim time per correct object.
Per run with a decision log: every executed pick by shape x arm x grasp x route x drop with its outcome at the next
look (in the right bin / on the counter / off the table), Decision latency and fallback rate, and why options were
rejected by the planner.
"""
from __future__ import annotations

import collections
import json
import os
import sys


def shape_of(name):
    parts = str(name).split("_")
    return parts[2] if len(parts) >= 4 else "?"


def load_eval(d):
    p = d if d.endswith(".json") else os.path.join(d, "eval.json")
    with open(p) as f:
        return json.load(f)


def eval_table(ev, label):
    trials = ev["trials"]
    per = collections.defaultdict(lambda: [0, 0])
    sim_s, correct = 0.0, 0
    for t in trials:
        for o in t["outcomes"]:
            s = shape_of(o.get("name"))
            per[s][1] += 1
            per[s][0] += o["outcome"] == "correct"
        sim_s += t.get("sim_s") or 0.0
        correct += t["n_correct"]
    s = ev["summary"]
    print(f"\n## {label}: {s['task']}, {s['trials']} trials, seeds {s['seeds'][0]}-{s['seeds'][-1]}")
    print(f"objects correct {s['objects_correct']}/{s['objects']} ({100 * s['object_success']:.0f} %), "
          f"score {s['score_mean']:+.2f} ± {s['score_std']:.2f}, outcomes {s['outcome_counts']}")
    print("per shape: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(per.items())))
    print(f"clips total {s['safety_clipped_steps_total']}, command Hz min {s['command_hz_min']}, policy rt Hz min "
          f"{s['policy_hz_rt_min']}, rtf mean {s['rtf_mean']}, gate {'PASS' if s['gate']['passed'] else 'FAIL'}")
    if correct:
        print(f"sim time per correct object: {sim_s / correct:.1f} s (episodes {sim_s:.0f} s)")
    for t in trials:
        print(f"  seed {t['seed']}: {t['n_correct']}/{t['n_objects']} "
              + " ".join(f"{shape_of(o['name'])[:3]}:{o['outcome'][:4]}" for o in t["outcomes"])
              + f"  end={t['end_reason']} sim {t.get('sim_s')} s")
    return per


def dlog_table(path, ev=None):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    looks = [r for r in recs if r["type"] == "look"]
    outs = [r for r in recs if r["type"] == "outcome"]
    execs = [r for r in recs if r["type"] == "exec"]
    print(f"\n### decision log {os.path.basename(path)}: {len(looks)} looks, {len(execs)} picks executed, "
          f"{len(outs)} outcomes seen")
    # final outcome of picks whose outcome was not seen at a later look (last pick of an episode): from eval.json
    final = {}
    if ev:
        for t in ev["trials"]:
            for o in t["outcomes"]:
                final[(t["seed"], o["name"])] = o["outcome"]
    seen = {r["decision"] for r in outs}
    rows = [dict(r, src="look") for r in outs]
    for e in execs:
        if e["decision"] in seen:
            continue
        o = e["option"]
        fo = final.get((e["seed"], o["obj"]))
        ok = (fo == "correct") if o["route"] == "direct" else None
        rows.append({"obj": o["obj"], "shape": o["shape"], "route": o["route"], "arm": o["arm"], "grasp": o["grasp"],
                     "drop": o["drop"], "ok": ok, "result": f"final:{fo}", "src": "final"})

    def g(r):
        gr = r["grasp"]
        return "stock" if gr == "stock" else ("face_alt" if "p" in gr[4:] else "face")

    for title, key in (("shape", lambda r: r["shape"]), ("shape x grasp", lambda r: (r["shape"], g(r))),
                       ("arm", lambda r: r["arm"]), ("route", lambda r: r["route"]),
                       ("shape x arm x grasp x route", lambda r: (r["shape"], r["arm"], g(r), r["route"])),
                       ("drop spot (direct)", lambda r: r["drop"] if r["route"] == "direct" else None)):
        c = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            k = key(r)
            if k is None or r["ok"] is None:
                continue
            c[k][1] += 1
            c[k][0] += bool(r["ok"])
        print(f"picks ok by {title}: " + ", ".join(f"{k}: {v[0]}/{v[1]}" for k, v in sorted(c.items(), key=str)))
    fails = collections.Counter(r["result"] for r in rows if r["ok"] is False)
    print(f"failed pick results: {dict(fails)}")
    # chooser
    dec = [r["choice"] for r in looks if r.get("choice")]
    lat = [c["latency_s"] for c in dec if c.get("latency_s") is not None]
    fb = collections.Counter((c.get("fallback") or "none").split(":")[0] for c in dec)
    if lat:
        lat.sort()
        print(f"decision latency s: median {lat[len(lat) // 2]:.2f}, max {lat[-1]:.2f}, n {len(lat)}; fallbacks {dict(fb)}")
    chosen = [r for r in looks if r.get("chosen")]
    nd = sum(1 for r in chosen if not r["chosen"]["default"])
    print(f"looks choosing a non-default option: {nd}/{len(chosen)}; options per look mean "
          f"{sum(len(r['options']) for r in looks) / max(1, len(looks)):.1f}; look time s mean "
          f"{sum(r.get('t_look_s', 0) for r in looks) / max(1, len(looks)):.1f}")
    # grasp check (finger angles at the end of the lift) against what really happened
    gcs = {r["decision"]: r for r in recs if r["type"] == "grasp_check"}
    if gcs:
        c = collections.Counter()
        for r in outs:
            g_ = gcs.get(r["decision"])
            if g_ is not None:
                c[("empty" if g_["empty"] else "held", "pick ok" if r["ok"] else "pick failed")] += 1
        held = sorted(g_["err"] for g_ in gcs.values() if not g_["empty"])
        emp = sorted(g_["err"] for g_ in gcs.values() if g_["empty"])
        print(f"grasp check: {len(gcs)} checks, {sum(1 for g_ in gcs.values() if g_['abort'])} aborted; vs outcome: "
              + ", ".join(f"{k[0]} + {k[1]}: {v}" for k, v in sorted(c.items()))
              + (f"; finger error held {held[0]:.3f}-{held[-1]:.3f}" if held else "")
              + (f", empty {emp[0]:.3f}-{emp[-1]:.3f}" if emp else ""))
    # failure memory: how the n-th try on the same object went
    tries, by_try = collections.Counter(), collections.defaultdict(lambda: [0, 0])
    for r in sorted((r for r in rows if r["ok"] is not None and r["route"] == "direct"), key=lambda r: r.get("t_start", 1e9)):
        k = (r.get("seed"), r.get("truth") or r["obj"])
        tries[k] += 1
        by_try[tries[k]][1] += 1
        by_try[tries[k]][0] += bool(r["ok"])
    print("picks ok by try on the same object: " + ", ".join(f"try {k}: {v[0]}/{v[1]}" for k, v in sorted(by_try.items())))
    rej = collections.Counter()
    for r in looks:
        for t in r["planner"]["tried"]:
            if not t["ok"]:
                why = t["reason"].split("(")[0].split(":")[0].strip()[:60]
                rej[why] += 1
    print("planner rejections: " + "; ".join(f"{k} x{v}" for k, v in rej.most_common(8)))
    return rows


def main(argv):
    for a in argv:
        d, _, log = a.partition("=")
        ev = load_eval(d)
        eval_table(ev, os.path.basename(d.rstrip("/")))
        if log:
            dlog_table(log, ev)


if __name__ == "__main__":
    main(sys.argv[1:])
