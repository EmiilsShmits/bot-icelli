"""Monitoring rules measured on saved runs (no sim, no API): what cheap rules can tell the planner about its picks.

    python monitor_rules.py RUN_DIR=decisions.jsonl [RUN_DIR2=decisions2.jsonl ...]      (numpy only)
    python monitor_rules.py --table RUN_DIR=decisions.jsonl ...      prompt + one line per pick, for a large model

RUN_DIR holds Aalto's episode_NNN.npz (t, hand_q, hand_q_cmd per tick) and eval.json; decisions.jsonl is ours.
Per executed pick it joins the `exec` / `outcome` records with the finger angles and prints:
  1. grasp check   closed fingers stall on a held block: sum |hand_q - hand_q_cmd| over the picking hand
  2. retries       what the retry after a failed pick repeated, and whether another (arm, grasp) was on offer
  3. critique      rules that predict a failed pick before it runs
Write-up: docs/research/model-monitor-oracle.md.
"""
from __future__ import annotations

import collections
import json
import os
import sys

import numpy as np

HELD_RAD = 0.03          # summed tracking error (rad) above which the hand counts as holding something


def grasp_kind(g):
    return "stock" if g == "stock" else ("face_alt" if "p" in g[4:] else "face")


def load(pairs):
    """-> list of picks (dicts) over all runs, in execution order."""
    picks = []
    for run, log in pairs:
        recs = [json.loads(l) for l in open(log) if l.strip()]
        seeds = []
        for r in recs:
            if r["type"] == "episode" and r["seed"] not in seeds:
                seeds.append(r["seed"])
        final = {}
        ev = os.path.join(run, "eval.json")
        if os.path.exists(ev):
            for t in json.load(open(ev))["trials"]:
                for o in t["outcomes"]:
                    final[(t["seed"], o["name"])] = o["outcome"]
        for ep, seed in enumerate(seeds):
            f = os.path.join(run, f"episode_{ep:03d}.npz")
            if not os.path.exists(f):
                continue
            z = np.load(f)
            t, hq, hc = z["t"], z["hand_q"].astype(float), z["hand_q_cmd"]
            mine = [r for r in recs if r["seed"] == seed]
            outs = {r["decision"]: r for r in mine if r["type"] == "outcome"}
            looks = {r["decision"]: r for r in mine if r["type"] == "look"}
            ex = [r for r in mine if r["type"] == "exec"]
            tried = collections.defaultdict(list)          # object -> [(arm, grasp kind, ok)]
            for k, e in enumerate(ex):
                o, out = e["option"], outs.get(e["decision"])
                name = e.get("truth") or o["obj"]
                if out is not None:
                    ok, res = bool(out["ok"]), out["result"]
                else:                                       # last pick of an episode: Aalto's final outcome
                    fo = final.get((seed, name))
                    ok, res = (None if fo is None else fo == "correct"), f"final:{fo}"
                t0, t1 = e["t"], (ex[k + 1]["t"] if k + 1 < len(ex) else float(t[-1]))
                sl = slice(0, 7) if o["arm"] == "left" else slice(7, 14)
                i0, i1 = np.searchsorted(t, t0), np.searchsorted(t, t1)
                c, q, tt = hc[i0:i1, sl], hq[i0:i1, sl], t[i0:i1]
                closed = np.abs(c[:, 3]) > 0.8              # finger joints commanded well past open
                p = dict(run=os.path.basename(run.rstrip("/")), seed=seed, ep=ep, dec=e["decision"], obj=name,
                         shape=o["shape"], color=o["color"], arm=o["arm"], grasp=o["grasp"], kind=grasp_kind(o["grasp"]),
                         route=o["route"], bin=o["bin"], ok=ok, res=res, t0=t0, t1=t1, tt=tt, closed=closed,
                         err=np.abs(q - c).sum(1), before=list(tried[name]), look=looks.get(e["decision"]),
                         opt_obj=o["obj"])
                lk = p["look"]                               # distance to the nearest other object at the look (m)
                xy = {d["obj"]: np.asarray(d["xy"]) for d in lk["dets"]} if lk else {}
                me = xy.get(o["obj"])
                p["nn"] = None if me is None else min([float(np.linalg.norm(me - v)) for n, v in xy.items() if n != o["obj"]] or [9.0])
                idx = np.where(closed)[0]
                p["t_close"] = float(tt[idx[0]]) if len(idx) else None
                p["t_open"] = float(tt[idx[-1]]) if len(idx) else None
                picks.append(p)
                if ok is not None:
                    tried[name].append((o["arm"], p["kind"], ok))
    return picks


def err_at(p, dt):
    """Tracking error `dt` s after the close command started (None when the hand is open again by then)."""
    if p["t_close"] is None or p["t_close"] + dt > p["t_open"]:
        return None
    return float(p["err"][np.searchsorted(p["tt"], p["t_close"] + dt)])


def err_carry(p):
    """Mean tracking error over the second half of the closed phase (the carry)."""
    idx = np.where(p["closed"])[0]
    return float(p["err"][idx[len(idx) // 2:]].mean()) if len(idx) else 0.0


def grasp_check(P):
    print("\n## 1. Grasp check from hand_q (sum |q - cmd| over the picking hand, rad)")
    P = [p for p in P if p["ok"] is not None and p["t_close"] is not None]
    ok, bad = [err_carry(p) for p in P if p["ok"]], [err_carry(p) for p in P if not p["ok"]]
    print(f"picks {len(P)}: ok {len(ok)}, failed {len(bad)}")
    print(f"carry error, ok picks:     min {min(ok):.3f}  median {np.median(ok):.3f}  max {max(ok):.3f}")
    print(f"carry error, failed picks: min {min(bad):.3f}  median {np.median(bad):.3f}  max {max(bad):.3f}")
    for dt in (1.0, 1.5, 2.0, 2.5):
        tp = fp = tn = fn = 0
        for p in P:
            e = err_at(p, dt)
            held = e is not None and e > HELD_RAD
            tp += held and p["ok"]
            fp += held and not p["ok"]
            tn += (not held) and not p["ok"]
            fn += (not held) and p["ok"]
        print(f"rule 'held if error > {HELD_RAD} rad' {dt:.1f} s after the close starts: right {tp + tn}/{len(P)} "
              f"(held+ok {tp}, held+failed {fp}, empty+failed {tn}, empty+ok {fn})")
    held_end = [(err_carry(p) > HELD_RAD) == p["ok"] for p in P]
    print(f"same rule over the carry: right {sum(held_end)}/{len(P)}")
    slipped = [p for p in P if not p["ok"] and max(err_at(p, d) or 0 for d in (1.0, 1.5, 2.0)) > HELD_RAD]
    print(f"failed picks that held something for a moment and lost it: {len(slipped)} "
          f"({', '.join(p['dec'] + ' ' + p['shape'] for p in slipped)})")
    saved = [p["t1"] - (p["t_close"] + 2.0) for p in P if not p["ok"]]
    total = sum(p["t1"] - p["t0"] for p in P)
    print(f"sim time from 'close + 2 s' to the next pick, summed over failed picks: {sum(saved):.0f} s of {total:.0f} s "
          f"spent picking ({np.median(saved):.1f} s per failed pick)")


def retries(P):
    print("\n## 2. Retries after a failed pick")
    P = [p for p in P if p["ok"] is not None]
    first = [p for p in P if not p["before"]]
    again = [p for p in P if p["before"] and not any(b[2] for b in p["before"])]
    print(f"first attempts ok {sum(p['ok'] for p in first)}/{len(first)}; attempts after a failure ok "
          f"{sum(p['ok'] for p in again)}/{len(again)}")
    same = [p for p in again if (p["arm"], p["kind"]) in {b[:2] for b in p["before"]}]
    diff = [p for p in again if p not in same]
    print(f"retry repeats an (arm, grasp) that already failed on this object: {len(same)}/{len(again)}, "
          f"ok {sum(p['ok'] for p in same)}/{len(same)}")
    print(f"retry uses a new (arm, grasp): {len(diff)}/{len(again)}, ok {sum(p['ok'] for p in diff)}/{len(diff)}")
    c = collections.defaultdict(lambda: [0, 0])
    for p in same:
        c[p["shape"]][1] += 1
        c[p["shape"]][0] += p["ok"]
    print("repeats ok by shape: " + ", ".join(f"{k}: {v[0]}/{v[1]}" for k, v in sorted(c.items())))
    for key, name in ((lambda p: p["shape"], "shape"), (lambda p: len(p["before"]) + 1, "attempt number")):
        c = collections.defaultdict(lambda: [0, 0])
        for p in P:
            c[key(p)][1] += 1
            c[key(p)][0] += p["ok"]
        print(f"ok by {name}: " + ", ".join(f"{k}: {v[0]}/{v[1]}" for k, v in sorted(c.items(), key=str)))
    # was another (arm, grasp) on offer at the look that chose the repeat?
    alt = n = 0
    for p in same:
        lk = p["look"]
        if not lk:
            continue
        n += 1
        failed = {b[:2] for b in p["before"]}
        alt += any(o["obj"] == p["opt_obj"] and (o["arm"], grasp_kind(o["grasp"])) not in failed for o in lk["options"])
    print(f"repeats where the look listed an untried (arm, grasp) for the same object: {alt}/{n}")
    wasted = sum(p["t1"] - p["t0"] for p in same if not p["ok"])
    print(f"sim time spent on repeats that failed again: {wasted:.0f} s of {sum(p['t1'] - p['t0'] for p in P):.0f} s")
    left = collections.Counter()
    for p in P:
        left[(p["run"], p["seed"], p["obj"])] = p["ok"]
    print(f"objects picked at least once: {len(left)}, sorted in the end: {sum(left.values())}")


def rule_a(p):
    return p["shape"] in ("triangle", "tipped") and p["kind"] == "stock"


def rule_b(p):
    return (p["arm"], p["kind"]) in {b[:2] for b in p["before"] if not b[2]}


def rule_c(p):
    return p["nn"] is not None and p["nn"] < 0.07


def critique(P):
    print("\n## 3. Rules that flag a pick before it runs (flag = predict failure)")
    P = [p for p in P if p["ok"] is not None]
    for title, Q in (("all picks", P), ("first attempts, no triangle + stock claw",
                                        [p for p in P if not p["before"] and not rule_a(p)])):
        print(f"ok by distance to the nearest other object, {title}: " + ", ".join(
            f"{lo}-{hi} cm: {sum(p['ok'] for p in Q if p['nn'] is not None and lo <= p['nn'] * 100 < hi)}/"
            f"{sum(1 for p in Q if p['nn'] is not None and lo <= p['nn'] * 100 < hi)}" for lo, hi in ((0, 7), (7, 10), (10, 999))))
    rules = {
        "A triangle + stock claw": rule_a,
        "B this (arm, grasp) already failed on this object": rule_b,
        "C another object within 7 cm": rule_c,
        "A or B": lambda p: rule_a(p) or rule_b(p),
        "A or C": lambda p: rule_a(p) or rule_c(p),
        "never flag": lambda p: False,
    }
    for run in sorted({p["run"] for p in P}) + ["all runs"]:
        Q = [p for p in P if run in (p["run"], "all runs")]
        print(f"{run}: {len(Q)} picks, {sum(not p['ok'] for p in Q)} failed")
        for name, f in rules.items():
            fl = [p for p in Q if f(p)]
            right = sum(f(p) == (not p["ok"]) for p in Q)
            print(f"   {name}: flags {len(fl)}, of which failed {sum(not p['ok'] for p in fl)}; "
                  f"misses {sum((not f(p)) and not p['ok'] for p in Q)} failures; right {right}/{len(Q)}")


REVIEW_PROMPT = """You are reviewing logs of a scripted pick-and-place planner on a humanoid robot (Unitree G1, three-finger
hands) that sorts 4.5 cm blocks (cube, cylinder, triangle = triangular prism; 'tipped' = a block lying on its side) from a
table into bins. Each line is one executed pick. Columns: run, seed (episode), pick id, object name, shape, arm, grasp
('stock' = generic claw from above; 'faceN' = fingers aligned to side face N; 'faceNpXX' = face grasp turned to XX
degrees), attempt number on that object in the episode, finger_error_rad (how far the closed fingers stayed from their
commanded closed angles during the carry, summed over the hand), nearest_cm (distance to the nearest other object when
the pick was planned), result (in_bin = success; counter = the block stayed on the table). The planner retries a failed
object, usually with the same arm and grasp.

Task: from this table alone, list at most 6 concrete findings, each with counts from the table (x of y), and for each one
a rule change the planner could apply at run time using only information it has before or during a pick. Rank by how
many failed picks or how much wasted time the change would address. Do not invent numbers.
"""


def table(P):
    """The prompt and one line per pick, for a large model to read offline (role 6 in the write-up)."""
    rows = [REVIEW_PROMPT, "run seed pick object shape arm grasp attempt_on_object finger_error_rad nearest_cm result"]
    for p in P:
        nn = "-" if p["nn"] is None or p["nn"] > 1 else f"{p['nn'] * 100:.0f}"
        rows.append(f"{p['run'].split('_nominal')[0]} {p['seed']} {p['dec']} {p['obj']} {p['shape']} {p['arm']} {p['grasp']} "
                    f"{len(p['before']) + 1} {err_carry(p):.3f} {nn} {'in_bin' if p['ok'] else p['res']}")
    return "\n".join(rows)


def main(argv):
    pairs = [a.split("=", 1) for a in argv if "=" in a]
    P = load(pairs)
    if "--table" in argv:
        print(table(P))
        return
    print(f"{len(P)} executed picks in {len(pairs)} runs")
    grasp_check(P)
    retries(P)
    critique(P)


if __name__ == "__main__":
    main(sys.argv[1:])
