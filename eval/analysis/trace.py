"""Turn Aalto sim evaluation runs into tables that say what happened, grasp by grasp.

Runs where Aalto's sim is installed (Pinocchio + the G1 URDF), e.g. the Verda sim machine:

    cd ~/aaltonomous-humanoid && PYTHONPATH=$PWD ~/miniforge3/envs/isaac/bin/python ~/bot-icelli/eval/analysis/trace.py \
        --runs ~/runs/eval/*/ ~/video/runs/*/ --logs ~/policy_logs/*.log --out ~/analysis/out

Per run folder (output of `aaltonomous.sim.evaluate` or `eval/analysis/traced_eval.py`) it reads:
  episode_NNN.jsonl   the evaluator's summary: layout, instruction, true mapping, outcome per object, final poses,
                      safety, rates, end reason
  episode_NNN.npz     every 30 Hz tick: t, arm_q, hand_q, arm_q_cmd, hand_q_cmd, hold, policy_wait, clipped, mode
  episode_NNN.poses.jsonl, container.log   (only from traced_eval.py) object poses every 0.2 s, the policy's log
Policy logs (--logs): the policy's own lines, "[classical t=..] execute <colour> <arm> arm -> <bin> bin grasp=..";
matched to a run by start time.

What it reconstructs (no camera needed):
  - grasp attempts: a hand's command reaching Aalto's `closed` posture (config.yaml `hand`) = one attempt
  - held or empty: Dex3 fingers stop short of the command on an object; an empty hand reaches it
    (Emils, 40db2e6: empty 0.000-0.010 rad, held 0.021-0.100 rad)
  - slipped: held at the lift, empty before the release
  - where: forward kinematics of the grasp point at closing and at opening -> which object, which bin / counter
  - where each object ended, by Aalto's own rule (centre inside a bin's inner walls AND below its 6 cm rim), and
    why each unsorted object was lost (objects.csv loss_reason)
  - which object: nearest object of the layout to the planned grasp point (policy log) or the grasp point (FK),
    preferring the colour the policy said it was picking (unless another object is 4 cm closer); an object put down
    on the counter (hand-over) is looked for at that spot afterwards
  - hand-overs: a held object released on the counter by a plan that targets the counter (v1.1's hand-over, or
    Aalto's own relocation) = "handed_over", not a failure

Outputs in --out: episodes.csv, objects.csv, picks.csv, policy_events.csv, events.jsonl, summary.md.
Column meanings: eval/analysis/README.md.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import json
import os
import re
from pathlib import Path

import numpy as np

HZ = 30.0
FAR_CROSS = 0.08        # m: object this far on the far side of its arm = "far cross-body" (v1.1's rule)
# Grip check, calibrated on these runs (eval/analysis/README.md): once the fingers settle at Aalto's `closed`
# command, an EMPTY hand reaches it exactly (every joint 0.000 rad off), while a HELD block leaves at least one
# finger 0.013-0.047 rad short. Measure: the largest per-joint median |hand_q - hand_q_cmd| (thumb0 excluded).
HELD, EMPTY = 0.008, 0.004


# ----------------------------------------------------------------------------------------------- inputs
def load_episodes(run: Path):
    for j in sorted(run.glob("episode_*.jsonl")):
        summ = None
        events = []
        for line in j.read_text().splitlines():
            rec = json.loads(line)
            if "summary" in rec:
                summ = rec["summary"]
            elif "event" in rec:
                events.append(rec["event"])
        npz = j.with_suffix(".npz")
        if summ is None or not npz.exists():
            continue
        poses = j.with_name(j.stem + ".poses.jsonl")
        yield j.stem, summ, events, np.load(npz), (poses if poses.exists() else None)


LOG_RE = re.compile(r"^(?:(\S+T\S+)\s+)?(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (.*)$")
EXEC_RE = re.compile(r"\[classical t=\s*([\d.]+)\] execute (\w+)\s+(left|right)\s+arm -> (\w+) bin\s+"
                     r"grasp=\(([-+\d.]+),([-+\d.]+),([-+\d.]+)\) drop=\(([-+\d.]+),([-+\d.]+),([-+\d.]+)\)\s+"
                     r"IK (\w+) max_err=([\d.]+)mm max_tilt=(\d+)deg\s+([\d.]+)s")
GEN_RE = re.compile(r"\[classical t=\s*([\d.]+)\] (.*)$")
RESET_RE = re.compile(r"reset task=(\w+) seed=(\d+)(?: mapping=(\{.*?\}) \[(.*?)\])?")
NAME_RE = re.compile(r"policy server '([^']+)' listening")


def parse_log(path):
    """-> (start datetime, {seed: [event, ...]}, policy name). One file = one policy server = one or more runs."""
    eps, cur, start, name = collections.defaultdict(list), None, None, None
    for raw in Path(path).read_text(errors="replace").splitlines():
        m = LOG_RE.match(raw.strip())
        if not m:
            continue
        stamp = dt.datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S")
        start = start or stamp
        msg = m.group(4)
        n = NAME_RE.search(msg)
        if n:
            name = name or n.group(1)
        r = RESET_RE.search(msg)
        if r:
            cur = int(r.group(2))
            eps[cur].append({"kind": "reset", "wall": stamp.isoformat(), "task": r.group(1),
                             "policy_mapping": r.group(3), "mapping_source": r.group(4)})
            continue
        if cur is None:
            continue
        e = EXEC_RE.search(msg)
        if e:
            g = e.groups()
            eps[cur].append({"kind": "execute", "t": float(g[0]), "color": g[1], "arm": g[2], "bin": g[3],
                             "grasp": [float(g[4]), float(g[5]), float(g[6])],
                             "drop": [float(g[7]), float(g[8]), float(g[9])], "ik": g[10],
                             "ik_err_mm": float(g[11]), "tilt_deg": int(g[12]), "plan_s": float(g[13])})
            continue
        g = GEN_RE.search(msg)
        if g:
            text = g.group(2)
            kind = ("skip" if text.startswith("skip") else "done" if text.startswith("nothing left")
                    else "home" if text.startswith("to home") else "note")
            eps[cur].append({"kind": kind, "t": float(g.group(1)), "text": text})
        elif m.group(3) in ("WARNING", "ERROR"):
            eps[cur].append({"kind": m.group(3).lower(), "text": msg[:300]})
    return start, eps, name


def oracle_log(run: Path):
    """Aalto's oracle keeps its own planner messages ([t, msg]) per trial in eval.json (written when the run ends):
    same text as the classical log, so the same parser applies. -> {seed: [event, ...]}"""
    f = run / "eval.json"
    if not f.exists():
        return {}
    out = {}
    for tr in json.loads(f.read_text()).get("trials", []):
        evs = []
        for t, msg in tr.get("oracle_events") or []:
            line = f"2000-01-01 00:00:00,000 INFO [classical t={float(t):6.2f}] {msg}"
            evs.extend(parse_lines([line]))
        out[int(tr.get("seed", -1))] = evs
    return out


def parse_lines(lines):
    eps = collections.defaultdict(list)
    for raw in lines:
        m = LOG_RE.match(raw.strip())
        g = GEN_RE.search(m.group(4)) if m else None
        if not g:
            continue
        e = EXEC_RE.search(m.group(4))
        if e:
            x = e.groups()
            eps[0].append({"kind": "execute", "t": float(x[0]), "color": x[1], "arm": x[2], "bin": x[3],
                           "grasp": [float(x[4]), float(x[5]), float(x[6])], "drop": [float(x[7]), float(x[8]), float(x[9])],
                           "ik": x[10], "ik_err_mm": float(x[11]), "tilt_deg": int(x[12]), "plan_s": float(x[13])})
        else:
            text = g.group(2)
            eps[0].append({"kind": "skip" if text.startswith("skip") else "done" if text.startswith("nothing left")
                           else "home" if text.startswith("to home") else "note", "t": float(g.group(1)), "text": text})
    return eps[0]


def run_start(run: Path):
    m = re.search(r"_(\d{8}_\d{6})$", run.name.rstrip("/"))
    return dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S") if m else None


# ----------------------------------------------------------------------------------------------- geometry
class Geo:
    def __init__(self):
        from aaltonomous.baselines.classical.config import load_config
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.scene.scene import Scene, resolve_bin
        self.cfg = load_config()
        self.kin = ArmKinematics(self.cfg)
        self.scene = Scene.load(os.environ.get("AALTO_SCENE") or None)
        self.resolve_bin = resolve_bin
        left = {k: np.asarray(v, float) for k, v in self.cfg["hand"].items() if isinstance(v, list)}
        self.postures = {"left": left, "right": {k: -v for k, v in left.items()}}   # right fingers mirror the left

    def where(self, p_pelvis):
        """'bin:<name>' if the point is above a bin's inner footprint, else 'counter'."""
        pm = self.scene.pelvis_to_mat(np.asarray(p_pelvis, float))
        for name in self.scene.bin_names:
            lo, hi = self.scene.bin_inner_box(name)
            if np.all(pm[:2] >= lo[:2]) and np.all(pm[:2] <= hi[:2]):
                return f"bin:{name}"
        return "counter"

    def final_where(self, p_pelvis):
        """Where an object ended, by Aalto's rule (Scene.classify_cube): 'bin:<name>' = centre inside the inner walls
        and below the rim (scores); 'above_rim:<name>' = over a bin's floor but higher than the rim, i.e. resting on
        an object already in the bin (Aalto counts it as left on the counter); 'raised' = centre higher than the rim
        elsewhere (on bin walls); 'off' = knocked off the counter; else 'counter'."""
        pm = self.scene.pelvis_to_mat(np.asarray(p_pelvis, float))
        if not self.scene.on_counter(pm):
            return "off"
        b = self.scene.bin_of(pm)
        if b:
            return f"bin:{b}"
        rim = float(self.scene.cfg["bins"]["wall_height"])
        if pm[2] > rim:
            for name in self.scene.bin_names:
                lo, hi = self.scene.bin_inner_box(name)
                if np.all(pm[:2] >= lo[:2]) and np.all(pm[:2] <= hi[:2]):
                    return f"above_rim:{name}"
            return "raised"
        return "counter"

    def grasp_point(self, side, arm_q):
        return self.kin.grasp_pose(side, np.asarray(arm_q, float))[0]


def obj_names(layout):
    """Aalto names layout objects obj_<colour>_<shape>_<k>, k counting repeats of the same colour + shape."""
    seen, out = collections.Counter(), []
    for o in layout:
        key = (o["color"], o.get("shape", "cube"))
        out.append(f"obj_{key[0]}_{key[1]}_{seen[key]}")
        seen[key] += 1
    return out


# ----------------------------------------------------------------------------------------------- grasps from ticks
def grasp_segments(geo, d):
    """Per hand: (i0, i1) tick spans where the command sits at the `closed` posture."""
    out = []
    for side, sl in (("left", slice(0, 7)), ("right", slice(7, 14))):
        cmd = d["hand_q_cmd"][:, sl]
        closed = np.linalg.norm(cmd - geo.postures[side]["closed"], axis=1) < 0.15
        i, n = 0, len(closed)
        while i < n:
            if not closed[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and (closed[j + 1] or (j + 2 < n and closed[j + 2])):   # bridge 1-tick gaps
                j += 1
            if j - i >= 3:
                out.append((side, sl, i, j))
            i = j + 1
    return sorted(out, key=lambda s: s[2])


def finger_err(d, sl, i0, i1):
    if i1 <= i0:
        return float("nan")
    q, c = d["hand_q"][i0:i1, sl], d["hand_q_cmd"][i0:i1, sl]
    return float(np.median(np.abs(q[:, 1:] - c[:, 1:]), axis=0).max())


def loss_reason(o, mine):
    """Why an object did not score ('' if it did), from where it ended and its grasp attempts (first match wins)."""
    if o["outcome"] == "correct":
        return ""
    res = [p["result"] for p in mine]
    fw = o["final_where"] or ""
    if mine and mine[-1]["t_open"] is None:
        return "in_hand_at_episode_end"
    if o["outcome"] == "off":
        return "off_the_counter"
    if o["outcome"] == "wrong":
        return "wrong_bin"
    if fw.startswith("above_rim") or fw == "raised":
        return "resting_above_rim"              # on an object already in the bin, or on bin walls: scores 0
    if not res:
        return "never_attempted"
    if all(r == "empty_grasp" for r in res):
        return "never_held"
    if "released_in_target_bin" in res:
        return "bounced_out_of_bin"
    if "handed_over" in res:
        return "handed_over_then_lost"
    if "slipped_in_carry" in res:
        return "slipped_in_carry"
    if "released_on_counter" in res or "released_in_other_bin" in res:
        return "released_outside_target_bin"
    return "unclear"


# ----------------------------------------------------------------------------------------------- one episode
def analyse(geo, run_name, ep_name, summ, events, d, log_events, poses_path, policy_name=None):
    layout = summ.get("layout") or []
    names = obj_names(layout)
    mapping = summ.get("mapping") or {}
    outcome = {o["name"]: o["outcome"] for o in summ.get("outcomes") or []}
    final = {o["name"]: o for o in summ.get("final_objects") or []}
    t = d["t"]
    sim_end = float(t[-1]) if len(t) else 0.0

    objs = []
    for nm, o in zip(names, layout):
        shape = o.get("shape", "cube")
        p0 = geo.scene.mat_to_pelvis([o["x"], o["y"]])
        tb = geo.resolve_bin(mapping, o["color"], shape) if mapping else None
        arm = "left" if tb == "left" else "right" if tb == "right" else ("left" if p0[1] >= 0 else "right")
        far = (arm == "left" and p0[1] < -FAR_CROSS) or (arm == "right" and p0[1] > FAR_CROSS)
        fp = final.get(nm, {}).get("pos")
        moved = float(np.linalg.norm(np.asarray(fp[:2]) - p0[:2])) if fp else None
        objs.append({"name": nm, "color": o["color"], "shape": shape, "x": round(float(p0[0]), 3),
                     "y": round(float(p0[1]), 3), "yaw_deg": round(float(np.degrees(o.get("yaw", 0.0))), 1),
                     "target_bin": tb, "bin_arm": arm, "far_cross_body": bool(far),
                     "outcome": outcome.get(nm, "?"), "final_where": geo.final_where(fp) if fp else None,
                     "moved_m": round(moved, 3) if moved is not None else None,
                     "final_x": round(fp[0], 3) if fp else None, "final_y": round(fp[1], 3) if fp else None,
                     "final_z": round(fp[2], 3) if fp else None})
    by_name = {o["name"]: o for o in objs}
    pts = np.array([[o["x"], o["y"]] for o in objs]) if objs else np.zeros((0, 2))   # where each object is, as known

    execs = [e for e in log_events if e["kind"] == "execute"]
    used = set()
    picks = []
    for k, (side, sl, i0, i1) in enumerate(grasp_segments(geo, d)):
        t_close = float(t[i0])
        t_open = float(t[i1 + 1]) if i1 + 1 < len(t) else None
        gp = geo.grasp_point(side, d["arm_q"][i0])
        rp = geo.grasp_point(side, d["arm_q"][i1])
        e_lift = finger_err(d, sl, min(i0 + 15, i1), min(i0 + 36, i1 + 1))
        e_end = finger_err(d, sl, max(i0, i1 - 9), i1 + 1)
        ex = None   # the policy's own "execute" line for this grasp: same arm, logged before the close
        for n_, e in enumerate(execs):
            if n_ not in used and e["arm"] == side and e["t"] <= t_close + 0.5 and t_close - e["t"] < e["plan_s"] + 2:
                ex, _ = e, used.add(n_)
                break
        aim = np.asarray(ex["grasp"][:2]) if ex else gp[:2]
        if len(pts):
            dist = np.linalg.norm(pts - aim, axis=1)
            j = int(np.argmin(dist))
            same = [i for i, o in enumerate(objs) if ex and o["color"] == ex["color"]]
            if same:   # the colour the policy meant, unless an object of another colour is much closer (misread colour)
                js = min(same, key=lambda i: dist[i])
                j = js if dist[js] < dist[j] + 0.04 else j
            tgt, tgt_d = objs[j]["name"], float(dist[j])
        else:
            tgt, tgt_d = None, None
        held_lift = e_lift > HELD
        empty_lift = e_lift < EMPTY
        released_at = geo.where(rp)
        earlier = sum(1 for q in picks if q["released_at"] == released_at and released_at.startswith("bin:")
                      and q["result"] in ("released_in_target_bin", "released_in_other_bin"))
        j = j if len(pts) else None
        if empty_lift:
            result = "empty_grasp"
        elif held_lift and e_end < EMPTY:
            result = "slipped_in_carry"
        elif held_lift and ex and ex["bin"] == "counter" and not released_at.startswith("bin:"):
            result = "handed_over"            # placed on the counter on purpose, for the other arm
        elif held_lift and released_at.startswith("bin:"):
            want = by_name[tgt]["target_bin"] if tgt else None
            result = "released_in_target_bin" if want and released_at == f"bin:{want}" else "released_in_other_bin"
        elif held_lift:
            result = "released_on_counter"
        else:
            result = "unclear"
        if j is not None and result in ("handed_over", "released_on_counter"):
            pts[j] = rp[:2]                   # it now lies where the hand let go
        picks.append({"pick": k, "arm": side, "t_close": round(t_close, 2),
                      "t_open": round(t_open, 2) if t_open is not None else None,
                      "hold_s": round((i1 - i0 + 1) / HZ, 2), "object": tgt,
                      "object_dist_m": round(tgt_d, 3) if tgt_d is not None else None,
                      "shape": by_name[tgt]["shape"] if tgt else None, "object_color": by_name[tgt]["color"] if tgt else None,
                      "far_cross_body": by_name[tgt]["far_cross_body"] if tgt else None,
                      "grasp_x": round(float(gp[0]), 3), "grasp_y": round(float(gp[1]), 3), "grasp_z": round(float(gp[2]), 3),
                      "release_x": round(float(rp[0]), 3), "release_y": round(float(rp[1]), 3), "release_z": round(float(rp[2]), 3),
                      "released_at": released_at, "earlier_releases_same_bin": earlier if released_at.startswith("bin:") else None,
                      "finger_err_lift": round(e_lift, 4), "finger_err_end": round(e_end, 4),
                      "result": result, "planned_color": ex["color"] if ex else None, "planned_bin": ex["bin"] if ex else None,
                      "planned_grasp": ex["grasp"] if ex else None, "planned_drop": ex["drop"] if ex else None,
                      "ik_err_mm": ex["ik_err_mm"] if ex else None, "plan_s": ex["plan_s"] if ex else None,
                      "t_planned": ex["t"] if ex else None})
    # per object: attempts and how each ended
    for o in objs:
        mine = [p for p in picks if p["object"] == o["name"]]
        o["attempts"] = len(mine)
        o["attempt_results"] = "|".join(p["result"] for p in mine)
        o["arms_used"] = "|".join(sorted({p["arm"] for p in mine}))
        o["first_attempt"] = mine[0]["result"] if mine else "never_attempted"
        o["loss_reason"] = loss_reason(o, mine)
    for p in picks:
        o = by_name.get(p["object"]) or {}
        p["object_outcome"], p["object_final_where"] = o.get("outcome"), o.get("final_where")

    hold = d["hold"].astype(bool) if "hold" in d.files else np.zeros(len(t), bool)
    wait = d["policy_wait"].astype(bool) if "policy_wait" in d.files else np.zeros(len(t), bool)
    s = summ.get("safety") or {}
    # Which policy really ran. Aalto's evaluate.py runs its privileged oracle whenever --policy is left at its default,
    # even with --container IMAGE given (it tests --policy first); oracle trials carry "mapping_source".
    actual = "oracle (exact sim poses: not a submission)" if "mapping_source" in summ else (
        f"classical baseline ({policy_name})" if (policy_name or "").startswith("classical")
        else f"our image ({policy_name})" if (policy_name or "").startswith("bot-icelli")
        else "classical baseline" if log_events and run_name.startswith("baseline")
        else f"policy server ({policy_name})" if policy_name else "unknown (no policy log)")
    ep = {"run": run_name, "policy_actual": actual, "episode": ep_name, "seed": summ.get("seed"), "task": summ.get("task"),
          "variant": summ.get("variant"), "n_objects": summ.get("n_objects"), "n_correct": summ.get("n_correct"),
          "score": summ.get("score"), "max_score": summ.get("max_score"), "end_reason": summ.get("end_reason"),
          "sim_s": round(sim_end, 1), "wall_s": summ.get("wall_s"), "rtf": summ.get("rtf"),
          "hold_frac": round(float(hold.mean()), 3) if len(t) else None,
          "policy_wait_frac": round(float(wait.mean()), 3) if len(t) else None,
          "clipped_steps": s.get("clipped_steps"), "command_hz": summ.get("command_hz"),
          "policy_hz_rt": summ.get("policy_hz_rt"), "picks": len(picks),
          "empty_grasps": sum(p["result"] == "empty_grasp" for p in picks),
          "slips": sum(p["result"] == "slipped_in_carry" for p in picks),
          "into_target_bin": sum(p["result"] == "released_in_target_bin" for p in picks),
          "never_attempted": sum(o["first_attempt"] == "never_attempted" for o in objs),
          "far_cross_body_objects": sum(o["far_cross_body"] for o in objs),
          "instruction": summ.get("instruction"), "true_mapping": json.dumps(mapping, sort_keys=True),
          "policy_mapping": next((e.get("policy_mapping") for e in log_events if e["kind"] == "reset"), None),
          "policy_log": bool(log_events)}

    timeline = [{"t": 0.0, "kind": "start", "instruction": summ.get("instruction")}]
    timeline += [{"t": e.get("t"), **{k: v for k, v in e.items() if k != "t"}} for e in log_events if e["kind"] != "reset"]
    for p in picks:
        timeline.append({"t": p["t_close"], "kind": "grasp_closed", "arm": p["arm"], "object": p["object"],
                         "finger_err": p["finger_err_lift"]})
        if p["t_open"] is not None:
            timeline.append({"t": p["t_open"], "kind": "released", "arm": p["arm"], "where": p["released_at"],
                             "result": p["result"]})
    if poses_path:   # traced_eval.py: when each object first moved more than 1 cm, and its highest point
        tr = [json.loads(x) for x in Path(poses_path).read_text().splitlines() if x.strip()]
        for o in objs:
            first = None
            for rec in tr:
                p = rec["objects"].get(o["name"])
                if p and np.linalg.norm(np.asarray(p[:2]) - [o["x"], o["y"]]) > 0.01:
                    first = rec["t"]
                    break
            zmax = max((rec["objects"][o["name"]][2] for rec in tr if o["name"] in rec["objects"]), default=None)
            o["first_moved_t"], o["max_z"] = first, (round(zmax, 3) if zmax is not None else None)
            if first is not None:
                timeline.append({"t": first, "kind": "object_moved", "object": o["name"]})
    timeline.append({"t": sim_end, "kind": "end", "reason": summ.get("end_reason"), "score": summ.get("score")})
    timeline.sort(key=lambda e: (e["t"] is None, e["t"] or 0.0))
    for o in objs:
        o.update({"run": run_name, "policy_actual": actual, "episode": ep_name, "seed": summ.get("seed"), "task": summ.get("task")})
    for p in picks:
        p.update({"run": run_name, "policy_actual": actual, "episode": ep_name, "seed": summ.get("seed"), "task": summ.get("task")})
    return ep, objs, picks, timeline


# ----------------------------------------------------------------------------------------------- summary
def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f} %)" if b else "–"


def summary_md(eps, objs, picks):
    L = ["# Sim trace summary (generated by eval/analysis/trace.py)", ""]
    runs = sorted({e["run"] for e in eps})
    L += ["## Per run", "", "| run | policy that actually ran | episodes | objects sorted | picks | empty grasps | slips | "
          "released in target bin | objects never attempted | far cross-body sorted | policy log |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        E = [e for e in eps if e["run"] == r]
        O = [o for o in objs if o["run"] == r]
        P = [p for p in picks if p["run"] == r]
        far = [o for o in O if o["far_cross_body"]]
        L.append(f"| {r} | {E[0]['policy_actual']} | {len(E)} | {pct(sum(o['outcome'] == 'correct' for o in O), len(O))} | {len(P)} | "
                 f"{pct(sum(p['result'] == 'empty_grasp' for p in P), len(P))} | "
                 f"{pct(sum(p['result'] == 'slipped_in_carry' for p in P), len(P))} | "
                 f"{pct(sum(p['result'] == 'released_in_target_bin' for p in P), len(P))} | "
                 f"{sum(o['first_attempt'] == 'never_attempted' for o in O)} | "
                 f"{pct(sum(o['outcome'] == 'correct' for o in far), len(far))} | {'yes' if any(e['policy_log'] for e in E) else 'no'} |")
    def table(title, key, rows, label):
        L.extend(["", f"## {title}", "", f"| {label} | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)])
        for k in sorted({key(x) for x in rows}, key=str):
            cells = []
            for r in runs:
                R = [x for x in rows if x["run"] == r and key(x) == k]
                cells.append(pct(sum(x.get("_ok", False) for x in R), len(R)) if R else "–")
            L.append(f"| {k} | " + " | ".join(cells) + " |")
    for o in objs:
        o["_ok"] = o["outcome"] == "correct"
    for p in picks:
        p["_ok"] = p["result"] == "released_in_target_bin"
    table("Objects sorted, by shape", lambda o: o["shape"], objs, "shape")
    table("Objects sorted, far cross-body or not", lambda o: "far cross-body" if o["far_cross_body"] else "near side", objs, "object")
    table("Objects sorted, by distance from the robot (pelvis x)",
          lambda o: "< 0.30 m" if o["x"] < 0.30 else "0.30-0.38 m" if o["x"] < 0.38 else ">= 0.38 m", objs, "x")
    table("Grasps that ended in the target bin, by shape and arm", lambda p: f"{p['shape']} / {p['arm']}", picks, "shape / arm")
    table("Grasps that ended in the target bin, by attempt result", lambda p: p["result"], picks, "result")
    L += ["", "## Why unsorted objects were lost (objects.csv loss_reason)", "",
          "| loss reason | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
    for k in sorted({o["loss_reason"] for o in objs if o["loss_reason"]}):
        L.append(f"| {k} | " + " | ".join(str(sum(o["run"] == r and o["loss_reason"] == k for o in objs)) for r in runs) + " |")
    L += ["", "## Releases over the target bin: did the object score? By earlier releases over that bin", "",
          "| run | earlier releases over the bin | released | scored | resting above the rim |", "|---|---|---|---|---|"]
    for r in runs:
        R = [p for p in picks if p["run"] == r and p["result"] == "released_in_target_bin"]
        for k in sorted({min(p["earlier_releases_same_bin"] or 0, 2) for p in R}):
            K = [p for p in R if min(p["earlier_releases_same_bin"] or 0, 2) == k]
            L.append(f"| {r} | {k if k < 2 else '2+'} | {len(K)} | {sum(p['object_outcome'] == 'correct' for p in K)} | "
                     f"{sum(str(p['object_final_where']).startswith(('above_rim', 'raised')) for p in K)} |")
    L += ["", "## How objects ended", "", "| run | outcome | first attempt | count |", "|---|---|---|---|"]
    cnt = collections.Counter((o["run"], o["outcome"], o["first_attempt"]) for o in objs)
    for (r, oc, fa), n in sorted(cnt.items()):
        L.append(f"| {r} | {oc} | {fa} | {n} |")
    for o in objs:
        o.pop("_ok", None)
    for p in picks:
        p.pop("_ok", None)
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- main
def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True, help="evaluate output folders")
    ap.add_argument("--logs", nargs="*", default=[], help="policy logs (baseline server logs, policy_logs/*.log)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    geo = Geo()
    logs = []
    for f in a.logs:
        for g in glob.glob(f):
            start, eps, name = parse_log(g)
            if start:
                logs.append((start, g, eps, name))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    E, O, P, PE = [], [], [], []
    with open(out / "events.jsonl", "w") as tl:
        for r in a.runs:
            run = Path(r)
            rs = run_start(run)
            own = run / "container.log"
            seeds = {int(s.get("seed", -1)) for _, s, _, _, _ in load_episodes(run)}
            # the policy log that started closest to the run (within 90 s) and has episodes of the run's seeds
            cand = [(abs((s - rs).total_seconds()), g, eps, nm) for s, g, eps, nm in logs
                    if rs and seeds & set(eps)] if rs else []
            match = min(cand, key=lambda c: c[0]) if cand else None
            match = match if match and match[0] < 90 else None
            if own.exists():
                _, log_eps, pname = parse_log(own)
                log_src = str(own)
            else:
                log_eps, log_src, pname = (match[2], match[1], match[3]) if match else ({}, None, None)
            if not log_eps and (run / "eval.json").exists():
                log_eps, log_src = oracle_log(run), str(run / "eval.json")
            for ep_name, summ, events, d, poses in load_episodes(run):
                le = log_eps.get(int(summ.get("seed", -1)), [])
                ep, objs, picks, timeline = analyse(geo, run.name, ep_name, summ, events, d, le, poses, pname)
                ep["policy_log_file"] = os.path.basename(log_src) if (log_src and le) else None
                E.append(ep)
                O.extend(objs)
                P.extend(picks)
                PE.extend({"run": run.name, "episode": ep_name, "seed": summ.get("seed"), **e} for e in le)
                tl.write(json.dumps({"run": run.name, "episode": ep_name, "seed": summ.get("seed"),
                                     "timeline": timeline}) + "\n")
                print(f"{run.name} {ep_name} seed {summ.get('seed')}: {ep['n_correct']}/{ep['n_objects']} "
                      f"picks {ep['picks']} (empty {ep['empty_grasps']}, slipped {ep['slips']}, "
                      f"into target {ep['into_target_bin']}) log={'yes' if le else 'no'}")
    write_csv(out / "episodes.csv", E)
    write_csv(out / "objects.csv", O)
    write_csv(out / "picks.csv", P)
    write_csv(out / "policy_events.csv", PE)
    (out / "summary.md").write_text(summary_md(E, O, P))
    print(f"-> {out}: {len(E)} episodes, {len(O)} objects, {len(P)} grasp attempts, {len(PE)} policy log events")


if __name__ == "__main__":
    main()
