"""Oracle upgrades, kept in ONE separate file so the original decision oracle (policy.py, chooser.py, motions.py,
camera.py, run_eval.py) stays exactly as it was. Everything here subclasses the originals; nothing is patched.

    # sim evaluation with the upgrades (same arguments as run_eval.py; --chooser memory --grasp-check on by default)
    PYTHONPATH=/root/aaltonomous-humanoid:/root python -m decision_oracle.upgrades --task sort_fixed --trials 6 \
        --seed 1000 --out /root/runs_do
    python -m decision_oracle.upgrades --selftest 6          # no sim: memory chooser rules on random layouts
    python -m decision_oracle.upgrades --analyze decisions_*.jsonl   # grasp check vs outcome, picks by try number

The three upgrades (all rules, no API call):
1. Failure memory. Every failed pick is stored per object as (arm, grasp). MemoryChooser never repeats a pair that
   failed on that object while another planner-checked option exists, and takes objects that have not failed yet
   first. Retries are counted per object (`max_tries`), not per table position as in Aalto's code.
2. Face grasp first. Cubes and triangles: Aalto's face grasp, then the alternative triangle angles, then the stock
   claw. The option search spends its time budget on the object that will be picked.
3. Grasp check from the finger angles. At the end of `lift`, a held block keeps the fingers short of the commanded
   closed posture (0.021-0.100 rad on 29 logged sim picks); an empty hand reaches it (0.000-0.010 rad on 27).
   Empty -> the pick is aborted: open, straight home, look again. The threshold is a sim value.

Classes: MemoryChooser, MemoryEnumerator(OptionEnumerator), TrackingCamera(CameraPerception),
UpgradedOraclePolicy(DecisionOraclePolicy).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

import numpy as np

from .camera import CameraPerception
from .chooser import _grasp_kind
from .chooser import make as make_chooser
from .motions import GRASP_STOCK, OptionEnumerator, face_options, grasp_label, grasp_variants, parse_face, target_bin
from .policy import DecisionOraclePolicy

GRASP_EMPTY_ERR = float(os.environ.get("GRASP_EMPTY_ERR", "0.03") or 0.03)
                          # rad. Largest |measured - commanded| angle of the PINCH joints of the closed hand at the end of
                          # `lift`. Sim logs: holding 0.018-0.100, empty 0.000-0.010. Real robot (Sun 06:19 run): empty
                          # 0.01-0.02 on the pinch joints, while the left hand's middle_0 is stuck near -0.15 rad whatever
                          # it is told, so a check over all 7 joints always said "holding" there and never retried.
GRASP_JOINTS = [int(v) for v in os.environ.get("GRASP_JOINTS", "1,2,5,6").split(",") if v.strip()]
                          # hand joints the check reads (DDS order: thumb_0..2, middle_0..1, index_0..1): thumb + index,
                          # the pinch (grasp.point_in_palm sits 15 mm towards the index finger)
MOVED_RADIUS = 0.10       # m. Camera mode: a failed pick keeps the object's name if it is found this close.
BASIC_PLANS_S = 6.0       # s. Least time allowed for one plan per object before grasp variants are searched.
CROWD_RADIUS = 0.08       # m. A neighbour for another bin this close can be grabbed instead of the target (seen at 6.2 cm).


# ---------------------------------------------------------------------------------------------------- chooser
class MemoryChooser:
    """Rule with a memory of failed picks (no API):
      - objects that have not failed yet go first (the oracle's order among them), so easy ones are sorted before
        time is spent on a hard one;
      - never repeat an (arm, grasp) that already failed on this object while another checked option exists;
      - for cubes and triangles prefer a face grasp, then the alternative triangle angles, then the stock claw;
      - the stock claw on a triangle is a last resort (it held in 1 of 15 sim picks); a failed claw grasp on a
        lying object is not retried because it can tip the object over;
      - an object with a neighbour for ANOTHER bin within 8 cm goes after the others: the hand can close on the
        neighbour instead and carry it to the wrong bin (seen in sim: -1 point). A last-resort grasp is not tried
        at all next to such a neighbour.
    Aalto's oracle retries with the same grasp and ignores neighbours."""
    name = "memory"
    budget_s = 8.0
    wants_history = True       # UpgradedOraclePolicy then counts retries per object
    pol = None                 # set by UpgradedOraclePolicy: the failure history lives there (pol.hist)

    @staticmethod
    def _last_resort(o):
        return o.shape == "triangle" and _grasp_kind(o.grasp) == "stock"

    def _crowded(self, options, ctx):
        """Names of objects that have a neighbour with a different target bin within CROWD_RADIUS."""
        dets = ctx.get("dets") or []
        if self.pol is None or not dets:
            return set()
        bins = {d.name: target_bin(self.pol.mapping, d) for d in dets}
        out = set()
        for a in dets:
            for b in dets:
                if a is not b and bins[a.name] != bins[b.name] \
                        and np.linalg.norm(a.top[:2] - b.top[:2]) < CROWD_RADIUS:
                    out.add(a.name)
        return out

    def choose(self, options, ctx):
        hist = ctx.get("history") or (self.pol.hist if self.pol is not None else {})
        crowded = self._crowded(options, ctx)
        order = {}
        for i, o in enumerate(options):
            order.setdefault(o.obj, i)
        rank = {"face": 0, "face_alt": 1, "stock": 2}

        def best(obj):
            fails = hist.get(obj, [])

            def sig_fail(o):
                return sum(1 for f in fails if f["arm"] == o.arm and f["grasp"] == o.grasp)

            def kind_fail(o):
                return sum(1 for f in fails if f["arm"] == o.arm and _grasp_kind(f["grasp"]) == _grasp_kind(o.grasp))

            same = [o for o in options if o.obj == obj]
            o = min(same, key=lambda x: (sig_fail(x), x.route != "direct", kind_fail(x), rank[_grasp_kind(x.grasp)],
                                         not x.is_default, x.duration))
            return o, sig_fail(o) > 0

        picks = {n: best(n) for n in order}
        skip, wait = [], []
        for n, (o, _) in picks.items():
            claw_failed = any(_grasp_kind(f["grasp"]) == "stock" for f in hist.get(n, []))
            if o.shape == "tipped" and claw_failed:
                skip.append(n)                    # the claw has most likely tipped it over: no grasp works then
            elif self._last_resort(o) and n in crowded:
                wait.append(n)                    # ~7 % to hold it, and the hand may take the neighbour instead:
                                                  # not now; given up only if nothing else is left
        live = [n for n in order if n not in skip and n not in wait]
        d = next(x for x in options if x.is_default)
        rec = {"chooser": self.name, "fallback": None}
        if not live:
            rec.update(skip=skip + wait, changed=True, failed_before=[], repeat=False)
            return None, None, rec
        if skip:
            rec["skip"] = skip
        if wait:
            rec["wait"] = wait
        obj = min(live, key=lambda n: (self._last_resort(picks[n][0]), len(hist.get(n, [])), n in crowded, order[n]))
        o, repeat = picks[obj]
        rec.update(changed=o is not d, failed_before=[f"{f['arm']}/{f['grasp']}" for f in hist.get(obj, [])],
                   repeat=repeat, crowded=sorted(crowded), last_resort=self._last_resort(o))
        return o, o.drop, rec


# ---------------------------------------------------------------------------------------------------- options
class MemoryEnumerator(OptionEnumerator):
    """OptionEnumerator with per-object retry counting and a search order that follows the failure history.
    With a chooser that has no failure memory it behaves exactly like the original."""

    def candidates(self, dets):
        pol = self.pol
        if not getattr(pol, "memory", False):
            return super().candidates(dets)
        r = pol.cfg["policy"]["same_object_radius"]
        cands = []
        for d in dets:
            xy = d.top[:2]
            if any(np.linalg.norm(xy - f) < r for f in pol.failed):
                continue
            # retries per object (failure memory); the position rule stays as a backstop at twice the tries
            if len(pol.hist.get(d.name, [])) >= pol.max_tries:
                continue
            if sum(c for p, c in pol.attempts if np.linalg.norm(xy - p) < r) >= 2 * pol.max_tries:
                continue
            d.bin = target_bin(pol.mapping, d)
            if d.bin is not None:
                cands.append(d)
        cands.sort(key=lambda d: np.linalg.norm(d.top[:2] - pol.planner.bin_xy(d.bin)))
        return cands

    def feasible_options(self, dets, arm_q, hand_q, budget_s=0.0, relay_budget_s=None):
        pol, lib = self.pol, self.lib
        if not getattr(pol, "memory", False):
            kw = {} if relay_budget_s is None else {"relay_budget_s": relay_budget_s}
            return super().feasible_options(dets, arm_q, hand_q, budget_s=budget_s, **kw)
        from aaltonomous.sim import oracle as O
        relay_budget_s = O.RELAY_BUDGET_S if relay_budget_s is None else relay_budget_s
        hist = pol.hist
        if budget_s > 0 and any(hist.get(d.name) for d in dets):
            budget_s = max(budget_s, pol.chooser.budget_s)   # a retry needs alternatives: the default just failed
        t0 = time.monotonic()
        info = {"tried": [], "no_direct": [], "relay_tried": [], "t_default_s": None, "t_total_s": None,
                "budget_s": budget_s, "budget_hit": False}
        cands = self.candidates(dets)
        options, seen = [], set()

        def add(o):
            if o.key not in seen:
                seen.add(o.key)
                options.append(o)

        # 1. the oracle's own choice (identical to the original enumerator)
        direct_done = {}
        for d in cands:
            p = pol.planner.plan(d, arm_q, hand_q, bin_name=d.bin, relocate=False)
            direct_done[d.name] = p.ok
            info["tried"].append({"obj": d.name, "arm": "auto", "grasp": "auto", "ok": bool(p.ok),
                                  "reason": p.reason[:160]})
            if p.ok:
                add(self._option(d, p, p.side, grasp_label(p), "direct", self.default_drop(d.bin), default=True))
                break
        if not options:
            tr = time.monotonic()
            for d in cands:
                if time.monotonic() - tr > relay_budget_s:
                    break
                p, why = lib.plan_relay(d, dets, arm_q, hand_q)
                info["relay_tried"].append({"obj": d.name, "ok": p is not None, "reason": why})
                if p is not None:
                    add(self._option(d, p, p.side, grasp_label(p), "relay", -1, default=True))
                    break
                info["no_direct"].append(d.name)
        info["t_default_s"] = round(time.monotonic() - t0, 2)
        if budget_s <= 0 or not options:
            info["t_total_s"] = info["t_default_s"]
            return options, info

        # 2. alternatives until the budget runs out
        deadline = time.monotonic() + budget_s

        def out_of_time():
            if time.monotonic() > deadline:
                info["budget_hit"] = True
                return True
            return False

        d_def = options[0].det
        others = [d for d in cands if d.name != d_def.name]

        def plan_other(d):
            """One plan for another object by Aalto's rule: makes "which object" a real choice."""
            if d.name in direct_done:
                return direct_done[d.name]
            p = pol.planner.plan(d, arm_q, hand_q, bin_name=d.bin, relocate=False)
            direct_done[d.name] = p.ok
            info["tried"].append({"obj": d.name, "arm": "auto", "grasp": "auto", "ok": bool(p.ok),
                                  "reason": p.reason[:160]})
            if p.ok:
                add(self._option(d, p, p.side, grasp_label(p), "direct", self.default_drop(d.bin)))
            return p.ok

        def variants(d):
            """Arm x grasp variants of one object: untried pairs first, face grasps before the stock claw."""
            pairs = [(arm, g) for arm in ("left", "right")
                     for g in grasp_variants(d, arm, getattr(pol, "tri_phis", None))]
            # Aalto's rule already tried every face on its arm before it fell back to the stock claw
            stock_arms = {o.arm for o in options if o.obj == d.name and o.grasp == GRASP_STOCK}
            pairs = [(a, g) for a, g in pairs if not (a in stock_arms and g.startswith("face") and "p" not in g)]
            fails = [(f["arm"], f["grasp"]) for f in hist.get(d.name, [])]
            pairs.sort(key=lambda ag: (fails.count(ag), ag[1] == GRASP_STOCK, "p" in ag[1]))
            for arm, grasp in pairs:
                if out_of_time():
                    break
                if any(o.obj == d.name and o.arm == arm and o.grasp == grasp for o in options):
                    continue
                p, why = lib.plan_direct(d, arm, grasp, d.bin, arm_q, hand_q)
                info["tried"].append({"obj": d.name, "arm": arm, "grasp": grasp, "ok": p is not None,
                                      "reason": str(why)[:160]})
                if p is not None:
                    fa = dict(face_options(d, arm, parse_face(grasp)[1])).get(parse_face(grasp)[0]) \
                        if grasp.startswith("face") else None
                    add(self._option(d, p, arm, grasp, "direct", self.default_drop(d.bin), face_a=fa))

        # 2a. one plan per other object, whatever the budget says (with its own allowance): an object without a
        #     plan can never be chosen, and the episode ends when the chooser has nothing left
        t_basic = time.monotonic() + max(budget_s, BASIC_PLANS_S)
        for d in others:
            if time.monotonic() > t_basic:
                info["budget_hit"] = True
                break
            plan_other(d)
        deadline = time.monotonic() + budget_s          # the variants get the full budget after the basic plans
        # 2b. grasp variants of the object the chooser would take now
        target = d_def
        try:
            o, _, _ = pol.chooser.choose(options, {"dets": dets})
            if o is not None:
                target = o.det
        except Exception:
            pass
        info["target"] = target.name
        variants(target)
        # 2c. grasp variants of the rest
        for d in [d_def] + [d for d in others if direct_done.get(d.name)]:
            if d.name != target.name:
                variants(d)
        # 2d. relay for objects that have no direct plan at all
        for d in cands:
            if out_of_time():
                break
            if direct_done.get(d.name) is False and not any(o.obj == d.name for o in options):
                p, why = lib.plan_relay(d, dets, arm_q, hand_q)
                info["relay_tried"].append({"obj": d.name, "ok": p is not None, "reason": why})
                if p is not None:
                    add(self._option(d, p, p.side, grasp_label(p), "relay", -1))
        info["no_direct"] = sorted({d.name for d in cands if direct_done.get(d.name) is False})
        info["t_total_s"] = round(time.monotonic() - t0, 2)
        return options, info


# ---------------------------------------------------------------------------------------------------- camera
class TrackingCamera(CameraPerception):
    """CameraPerception whose tracker lets a just-failed object keep its name after it was pushed."""
    _moved = None

    def reset(self):
        super().reset()
        self._moved = None

    def expect_moved(self, name, radius=MOVED_RADIUS):
        """A failed pick pushes the object (1-3 cm, sometimes more, sometimes onto its side). At the next look a
        detection of the same colour within `radius` of that track keeps its name, so its failure history survives."""
        self._moved = (name, radius)

    def _track(self, dets, radius=0.03):
        moved, self._moved = self._moved, None
        if moved is None:
            return super()._track(dets, radius)
        free = list(self.tracks)
        tracks = []
        for d in dets:
            best = None
            for t in free:
                if t[1] == d.color:
                    e = float(np.linalg.norm(t[2] - d.top[:2]))
                    r = moved[1] if t[0] == moved[0] else radius
                    if e < r and (best is None or e < best[0]):
                        best = (e, t)
            if best is not None:
                free.remove(best[1])
                d.name = best[1][0]
            else:
                self._n += 1
                d.name = f"cam_{d.color}_{self._n}"
            tracks.append([d.name, d.color, d.top[:2].copy()])
        self.tracks = tracks + free


# ---------------------------------------------------------------------------------------------------- policy
class UpgradedOraclePolicy(DecisionOraclePolicy):
    def __init__(self, client, chooser="memory", grasp_check="on", max_tries=4, **kw):
        """chooser:     "memory" (MemoryChooser) or any original chooser / chooser name.
        grasp_check: "off" | "log" (record only) | "on": an empty hand at the end of `lift` aborts the pick.
        max_tries:   failed picks per object before it is given up (memory chooser only)."""
        self.grasp_check, self.max_tries = grasp_check, int(max_tries)
        self.hist, self._gc, self._last_pick, self.memory = {}, None, None, False
        super().__init__(client, chooser=MemoryChooser() if chooser == "memory" else chooser, **kw)
        self.memory = bool(getattr(self.chooser, "wants_history", False))
        if self.memory:
            self.chooser.pol = self
        self.enum = MemoryEnumerator(self, self.lib)
        if self.cam is not None:
            self.cam = TrackingCamera(self.scene, self.cal, log=self.log)

    def reset(self, info=None):
        super().reset(info)
        self.hist = {}             # obj name -> [{arm, grasp, route, source}, ...] of FAILED picks
        self._gc = None            # grasp check pending for the plan being executed
        self._last_pick = None     # the pick whose result is not known yet

    def act(self, obs):
        if self._gc is not None and self.state == "executing" and (self.queue_a is None or not len(self.queue_a)):
            self._rgb = obs.get("head_rgb")          # the queue was cut at the end of `lift`
            self._t = float(obs.get("t", self._t))
            if self.cam is not None:
                self.cam.update(obs)
            return self._grasp_check(obs)
        return super().act(obs)

    # ------------------------------------------------------------------ grasp check
    def _start(self, plan, t):
        out = super()._start(plan, t)
        o = getattr(plan, "option", None)
        self._gc = None
        if o is not None:
            self._last_pick = {"o": o, "failed": None}
            if self.grasp_check != "off":
                cut = next((e for name, s, e in plan.phases if name == "lift"), None)
                done = len(plan.arm) - len(self.queue_a)          # ticks already handed out by super()._start
                if cut is not None and done < cut < len(plan.arm):
                    self._gc = {"plan": plan, "option": o, "side": plan.side,
                                "rest_a": plan.arm[cut:], "rest_h": plan.hand[cut:]}
                    self.queue_a, self.queue_h = plan.arm[done:cut], plan.hand[done:cut]
        return out

    def _grasp_check(self, obs):
        """End of `lift`: is something in the hand? Holding an object keeps the fingers short of the commanded closed
        posture; an empty hand reaches it. Empty -> skip the carry: open, go to the pose the plan would have ended
        in (so a prefetched next plan stays valid) and look again."""
        gc, self._gc = self._gc, None
        plan, o = gc["plan"], gc["option"]
        base = 0 if gc["side"] == "left" else 7
        idx = [base + j for j in GRASP_JOINTS]
        err = float(np.abs(np.asarray(obs["hand_q"], float)[idx] - np.asarray(self.hand_cmd, float)[idx]).max())
        empty = err < GRASP_EMPTY_ERR
        # Triangle prisms can fit inside the closed hand without moving a finger joint, even when held.
        abort = empty and o.shape not in ("triangle", "tipped") and self.grasp_check == "on"
        self._w({"type": "grasp_check", "decision": getattr(plan, "decision_id", None), "t": round(self._t, 2),
                 "obj": o.obj, "arm": o.arm, "grasp": o.grasp, "err": round(err, 4), "empty": empty,
                 "inconclusive": empty and o.shape in ("triangle", "tipped"), "abort": abort})
        if not abort:
            self._enqueue(gc["rest_a"], gc["rest_h"])
            return self._pop()
        self._fail(o, "fingers")
        if o.route == "direct":
            self._bin_count[o.bin] = max(0, self._bin_count.get(o.bin, 0) - 1)
        a, h = self.planner.go_to(self.arm_cmd, self.hand_cmd, plan.arm[-1], plan.hand[-1])
        self._enqueue(a, h)
        self._note(self._t, f"grasp check: hand empty (finger error {err:.3f} rad), back home")
        return self._pop() if len(a) else self._hold()

    # ------------------------------------------------------------------ failure memory
    def _fail(self, o, source):
        lp = self._last_pick
        if lp is None or lp["o"] is not o or lp["failed"]:
            return
        lp["failed"] = source
        self.hist.setdefault(o.obj, []).append({"arm": o.arm, "grasp": o.grasp, "route": o.route, "source": source})
        self._w({"type": "fail", "t": round(self._t, 2), "obj": o.obj, "arm": o.arm, "grasp": o.grasp,
                 "route": o.route, "source": source, "n": len(self.hist[o.obj])})
        if self.cam is not None:       # the failed pick pushed it: keep its name at the next look
            self.cam.expect_moved(o.obj)

    def _settle_last_pick(self, dets):
        """At a fresh look: a directly picked object that is still on the counter is a failed pick (backup for the
        grasp check: slipped during the carry, or the check is off)."""
        lp = self._last_pick
        if lp is not None and not lp["failed"] and lp["o"].route == "direct" \
                and any(d.name == lp["o"].obj for d in dets):
            self._fail(lp["o"], "look")
        self._last_pick = None

    def _detections(self, fresh):
        dets = super()._detections(fresh)
        if fresh:
            self._settle_last_pick(dets)
        return dets

    def _look_locked(self):
        res = super()._look_locked()
        if self._last_pick is not None:      # a prefetched plan was accepted: no fresh _detections for this look
            try:
                self._settle_last_pick(list(self.cam.last) if self.cam is not None else self.truth.detect())
            except Exception as e:
                self.log(f"[upgrades] failure memory: {e!r}")
        return res


# ---------------------------------------------------------------------------------------------------- tools
def analyze(path):
    """Extra tables for a decisions.jsonl written with the upgrades (analyze.py prints the rest)."""
    recs = [json.loads(l) for l in open(path) if l.strip()]
    outs = [r for r in recs if r["type"] == "outcome"]
    gcs = {r["decision"]: r for r in recs if r["type"] == "grasp_check"}
    print(f"\n### upgrades {os.path.basename(path)}: {len(outs)} pick outcomes, {len(gcs)} grasp checks")
    if gcs:
        c = collections.Counter()
        for r in outs:
            g = gcs.get(r["decision"])
            if g is not None and r["route"] == "direct":   # a relay counts as ok when the block is on the counter
                c[("empty" if g["empty"] else "held", "pick ok" if r["ok"] else "pick failed")] += 1
        held = sorted(g["err"] for g in gcs.values() if not g["empty"])
        emp = sorted(g["err"] for g in gcs.values() if g["empty"])
        print(f"grasp check: {sum(1 for g in gcs.values() if g['abort'])} aborted; vs outcome of direct picks: "
              + ", ".join(f"{k[0]} + {k[1]}: {v}" for k, v in sorted(c.items()))
              + (f"; finger error held {held[0]:.3f}-{held[-1]:.3f}" if held else "")
              + (f", empty {emp[0]:.3f}-{emp[-1]:.3f}" if emp else ""))
    tries, by_try = collections.Counter(), collections.defaultdict(lambda: [0, 0])
    for r in sorted((r for r in outs if r["route"] == "direct"), key=lambda r: (r["seed"], r.get("t_start", 0))):
        k = (r["seed"], r.get("truth") or r["obj"])
        tries[k] += 1
        by_try[tries[k]][1] += 1
        by_try[tries[k]][0] += bool(r["ok"])
    print("picks ok by try on the same object: " + ", ".join(f"try {k}: {v[0]}/{v[1]}" for k, v in sorted(by_try.items())))
    src = collections.Counter(r["source"] for r in recs if r["type"] == "fail")
    print(f"failures recorded: {dict(src)}")
    changed = [r["choice"] for r in recs if r["type"] == "look" and r.get("choice", {}).get("chooser") == "memory"]
    if changed:
        print(f"memory chooser: {sum(1 for c in changed if c.get('changed'))}/{len(changed)} looks differ from the "
              f"oracle's choice, {sum(1 for c in changed if c.get('repeat'))} had to repeat a failed pair")


def selftest(layouts=6, seed=0, budget=8.0):
    """No sim: after the default option "fails", MemoryChooser must not repeat it while another checked option
    exists; an object with max_tries failures is given up; with another chooser the enumerator is the original."""
    from aaltonomous.interface import tasks
    from aaltonomous.scene.scene import Scene
    from .test_offline import FakeClient, setup
    scene = Scene.load()
    n = changed = bad = 0
    for i in range(layouts):
        rng = np.random.default_rng(seed + i)
        fc = FakeClient(scene, tasks.sample_layout(rng, **scene.layout_kwargs()))
        base = DecisionOraclePolicy(fc, chooser="default", threaded=False, prefetch=False, log=None)
        setup(base)
        base._update_drop_offsets()
        o0, _ = base.enum.feasible_options(base.perception.detect(), base.arm_cmd, base.hand_cmd, budget_s=0.0)
        same = UpgradedOraclePolicy(fc, chooser="default", grasp_check="off", threaded=False, prefetch=False, log=None)
        setup(same)
        same._update_drop_offsets()
        o1, _ = same.enum.feasible_options(same.perception.detect(), same.arm_cmd, same.hand_cmd, budget_s=0.0)
        if [o.key for o in o0] != [o.key for o in o1]:
            bad += 1
            print(f"layout {i}: upgraded enumerator differs from the original with the default chooser")
        if not o0:
            continue
        mem = UpgradedOraclePolicy(fc, chooser="memory", threaded=False, prefetch=False, log=None)
        setup(mem)
        mem._update_drop_offsets()
        d0 = o0[0]
        mem.hist[d0.obj] = [{"arm": d0.arm, "grasp": d0.grasp, "route": d0.route, "source": "test"}]
        dets = mem.perception.detect()
        t = time.monotonic()
        o2, info = mem.enum.feasible_options(dets, mem.arm_cmd, mem.hand_cmd, budget_s=budget)
        if o2:
            c, _, rec = mem.chooser.choose(o2, {})
            alt = [o for o in o2 if (o.obj, o.arm, o.grasp) != (d0.obj, d0.arm, d0.grasp)]
            n += 1
            changed += (c.obj, c.arm, c.grasp) != (d0.obj, d0.arm, d0.grasp)
            if alt and (c.obj, c.arm, c.grasp) == (d0.obj, d0.arm, d0.grasp):
                bad += 1
            print(f"layout {i}: {len(dets)} objects, {len(o2)} options in {time.monotonic() - t:.1f} s; after "
                  f"{d0.obj} {d0.arm}/{d0.grasp} failed -> {c.obj} {c.arm}/{c.grasp}", flush=True)
        for d in dets:
            mem.hist[d.name] = [{"arm": "left", "grasp": "stock", "route": "direct", "source": "test"}] * mem.max_tries
        if mem.enum.candidates(mem.perception.detect()):
            bad += 1
    print(f"\nmemory chooser changed the pick after a failure in {changed}/{n} layouts; rule violations {bad}")
    return 0 if bad == 0 else 1


def main(argv=None):
    """aaltonomous.sim.evaluate with UpgradedOraclePolicy (same pattern as run_eval.py)."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--chooser", default="memory", choices=["memory", "default", "decision", "random", "prefer_face"])
    ap.add_argument("--grasp-check", default="on", choices=["off", "log", "on"])
    ap.add_argument("--max-tries", type=int, default=4)
    ap.add_argument("--perception", default="privileged", choices=["privileged", "camera"])
    ap.add_argument("--labels", default="off", choices=["off", "log", "fuse"])
    ap.add_argument("--dlog", default=None)
    ap.add_argument("--look-budget", type=float, default=3.0)
    ap.add_argument("--selftest", type=int, default=0, help="no sim: check the memory chooser on N random layouts")
    ap.add_argument("--analyze", nargs="+", default=None, help="decisions.jsonl files: print the upgrade tables")
    a, rest = ap.parse_known_args(argv)
    if a.analyze:
        for p in a.analyze:
            analyze(p)
        return 0
    if a.selftest:
        return selftest(a.selftest)

    import aaltonomous.sim.evaluate as E
    import aaltonomous.sim.oracle as O

    out = rest[rest.index("--out") + 1] if "--out" in rest else "runs/eval"
    task = rest[rest.index("--task") + 1] if "--task" in rest else "sort_fixed"
    cam = "_cam" if a.perception == "camera" else ""
    if "--team" not in rest:
        rest += ["--team", f"do_up_{a.chooser}{cam}"]
    rest = ["--policy", "oracle"] + list(rest)
    dlog = a.dlog or os.path.join(out, f"decisions_up_{a.chooser}{cam}_{task}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    os.makedirs(os.path.dirname(dlog) or ".", exist_ok=True)
    print(f"[upgrades] chooser={a.chooser} grasp_check={a.grasp_check} dlog={dlog}", flush=True)
    ch = MemoryChooser() if a.chooser == "memory" else make_chooser(a.chooser)

    def factory(client, **kw):
        return UpgradedOraclePolicy(client, chooser=ch, grasp_check=a.grasp_check, max_tries=a.max_tries, dlog=dlog,
                                    look_budget_s=a.look_budget, perception=a.perception, labels=a.labels, **kw)

    O.OraclePolicy = factory   # evaluate() imports it from the module at call time

    class SeededClient(E.LocalClient):
        def reset(self, task, instruction, seed):
            self.policy.episode_seed, self.policy.task = seed, task
            super().reset(task, instruction, seed)

    E.LocalClient = SeededClient
    return E.main(rest)


if __name__ == "__main__":
    sys.exit(main())
