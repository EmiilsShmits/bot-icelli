"""DecisionOraclePolicy: Aalto's OraclePolicy with its look split into motion functions + a chooser.

Only `_plan_next` (what to do next) is replaced; Aalto's threading is kept as is: the first look of an episode runs
in ClassicalPolicy's look thread, later ones are prefetched while the previous plan executes (`_prefetch_job`), and
act() returns hold targets while either is busy. So the chooser (Gemini call included) never runs inside act().

Logs one JSON line per event to `dlog` (decisions.jsonl):
    episode  seed, task, instruction, mapping, chooser
    look     options (feasible, planner-checked), planner info, chooser record (questions, answers, latency,
             fallback), chosen option + drop spot, prefetch or blocking
    exec     the option that started executing (sim time)
    outcome  where that object was at the next look (bin / counter / off the table), correct or not
"""
from __future__ import annotations

import json
import threading
import time

import numpy as np

from aaltonomous.sim.oracle import OraclePolicy

from . import chooser as C
from .camera import CameraPerception
from .motions import MotionLibrary, OptionEnumerator

FRESH_WAIT_S = 0.4        # sim s to wait before using a head frame for a look (arm lag, camera latency)
FIRST_LOOK_T = 1.0        # sim s: the first frames of a sim episode still show the previous (empty) scene
EMPTY_RETRIES = 2         # camera: looks that see nothing are repeated this many times before giving up
GRASP_EMPTY_ERR = 0.012   # rad. Grasp check at the end of `lift`: largest |measured - commanded| finger angle of the
                          # closed hand. Sim logs (56 picks): holding an object 0.021-0.100, empty hand 0.000-0.010.


class _FreshCamera:
    """The oracle calls perception.detect() with no arguments, from its planning thread: wait for a settled, current
    head frame (act() keeps holding and feeding frames meanwhile), then detect."""

    def __init__(self, pol):
        self.pol = pol

    def detect(self, rgb=None, depth=None, debug=False):
        pol = self.pol
        pol._wait_sim(max(FIRST_LOOK_T, pol._t + FRESH_WAIT_S))
        dets = pol.cam.detect()
        for _ in range(EMPTY_RETRIES):
            if dets:
                break
            pol._wait_sim(pol._t + 0.5)
            dets = pol.cam.detect()
        if pol.labeler is not None and dets:
            try:
                pol.labeler.label(dets, pol._rgb)
            except Exception as e:           # labels are optional: the geometric ones stay
                pol.log(f"[camera] crop labels failed: {e!r}")
        pol._log_perception(dets)
        dets = [d for d in dets if not getattr(d, "other", False)]
        pol.cam.last = dets
        return (dets, []) if debug else dets

    def masks(self, rgb):
        return {}


class DecisionOraclePolicy(OraclePolicy):
    def __init__(self, client, chooser="default", dlog=None, look_budget_s=3.0, perception="privileged",
                 labels="off", grasp_check="off", max_tries=4, **kw):
        """perception: "privileged" = exact poses from the sim's scene service (Aalto's oracle);
                       "camera"     = head RGB-D only (camera.py). The scene service is then used ONLY to log the
                                      truth next to what the camera saw (and not at all when client is None).
        grasp_check: "off" | "log" (record only) | "on": at the end of `lift`, an empty hand (finger angles reach
                     the commanded closed posture) aborts the pick: open, go home, look again.
        max_tries:   failed picks per object before it is given up (choosers with a failure memory only)."""
        self.chooser = C.make(chooser) if isinstance(chooser, str) else chooser
        self.grasp_check, self.max_tries = grasp_check, int(max_tries)
        self.retry = "object" if getattr(self.chooser, "wants_history", False) else "position"
        self.hist, self._gc, self._last_pick = {}, None, None
        self.look_budget_s = look_budget_s
        self.perception_mode = perception
        self._dlog = open(dlog, "a", buffering=1) if dlog else None
        self._dlock = threading.Lock()
        self.episode_seed, self.task = None, None
        super().__init__(client, **kw)
        self.lib = MotionLibrary(self)
        self.enum = OptionEnumerator(self, self.lib)
        self.truth = self.perception                 # PrivilegedPerception: logging only in camera mode
        self.cam, self.labeler = None, None
        if perception == "camera":
            self.cam = CameraPerception(self.scene, self.cal, log=self.log)
            self.perception = _FreshCamera(self)
            if labels != "off":        # Decision 1 crop labels: "log" = record only, "fuse" = may fix a close call
                from .labels import CropLabeler
                self.labeler = CropLabeler(mode=labels)

    # ------------------------------------------------------------------ logging
    def _w(self, rec):
        if self._dlog is None:
            return
        rec = {"seed": self.episode_seed, **rec}
        with self._dlock:
            self._dlog.write(json.dumps(rec, default=_js) + "\n")

    # ------------------------------------------------------------------ episode
    def reset(self, info=None):
        super().reset(info)
        self._rgb, self._t = None, 0.0
        self._executing = None
        self._look_n = 0
        self.picks = {}            # obj name -> [route, ...] of executed picks
        self.hist = {}             # obj name -> [{arm, grasp, route, source}, ...] of FAILED picks
        self._gc = None            # grasp check pending for the plan being executed
        self._last_pick = None     # the pick whose result is not known yet
        self._bin_count = {}       # camera mode: objects we released into each bin
        if getattr(self, "cam", None) is not None:
            self.cam.reset()
            if self.labeler is not None:
                self.labeler.reset()
        if hasattr(self.chooser, "reseed") and self.episode_seed is not None:
            self.chooser.reseed(self.episode_seed)
        if info is not None:
            inst = info.get("instruction") if isinstance(info, dict) else info
            self._w({"type": "episode", "task": self.task, "instruction": inst, "mapping": self.mapping,
                     "mapping_source": self.mapping_source, "chooser": self.chooser.name})

    def act(self, obs):
        self._rgb = obs.get("head_rgb")      # reference only; encoded in the planning thread
        self._t = float(obs.get("t", self._t))
        if self.cam is not None:
            self.cam.update(obs)
        if self._gc is not None and self.state == "executing" and (self.queue_a is None or not len(self.queue_a)):
            return self._grasp_check(obs)      # the queue was cut at the end of `lift`
        return super().act(obs)

    # ------------------------------------------------------------------ grasp check + failure memory
    def _grasp_check(self, obs):
        """End of `lift`: is something in the hand? Holding an object keeps the fingers short of the commanded closed
        posture; an empty hand reaches it. Empty -> skip the carry: open, go to the pose the plan would have ended
        in (so a prefetched next plan stays valid) and look again."""
        gc, self._gc = self._gc, None
        plan, o = gc["plan"], gc["option"]
        sl = slice(0, 7) if gc["side"] == "left" else slice(7, 14)
        err = float(np.abs(np.asarray(obs["hand_q"], float)[sl] - self.hand_cmd[sl]).max())
        empty = err < GRASP_EMPTY_ERR
        abort = empty and self.grasp_check == "on"
        self._w({"type": "grasp_check", "decision": getattr(plan, "decision_id", None), "t": round(self._t, 2),
                 "obj": o.obj, "arm": o.arm, "grasp": o.grasp, "err": round(err, 4), "empty": empty, "abort": abort})
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

    def _fail(self, o, source):
        lp = self._last_pick
        if lp is None or lp["o"] is not o or lp["failed"]:
            return
        lp["failed"] = source
        self.hist.setdefault(o.obj, []).append({"arm": o.arm, "grasp": o.grasp, "route": o.route, "source": source})
        if self.cam is not None:       # the failed pick pushed it: keep its name at the next look
            self.cam.expect_moved(o.obj)

    def _settle_last_pick(self, dets):
        """At a fresh look: a directly picked object that is still on the counter is a failed pick (backup for the
        grasp check: slipped during the carry, or the check is off)."""
        lp, self._last_pick = self._last_pick, None
        if lp is None or lp["failed"] or lp["o"].route != "direct":
            return
        if any(d.name == lp["o"].obj for d in dets):
            self._last_pick = lp
            self._fail(lp["o"], "look")
            self._last_pick = None

    # ------------------------------------------------------------------ outcome of the last pick
    def _classify(self, name):
        for o in self.client.state()["objects"]:
            if o["name"] != name:
                continue
            p = np.asarray(o["pos"], float)
            m = self.scene.pelvis_to_mat(p)
            b = self.scene.bin_of(m)
            if b is not None:
                return f"bin:{b}", p
            if self.scene.on_counter(m) and p[2] < self.scene.counter_z + 0.1:
                return "counter", p
            if p[2] < self.scene.counter_z - 0.05:
                return "off_table", p
            return "air", p
        return "missing", None

    def _record_outcome(self):
        ex, self._executing = self._executing, None
        if ex is None:
            return
        o, t0, did, tname = ex
        if tname is None:
            return
        try:
            where, p = self._classify(tname)
        except Exception as e:
            where, p = f"error {e!r}", None
        ok = (where == f"bin:{o.bin}") if o.route == "direct" else (where == "counter")
        self._w({"type": "outcome", "decision": did, "obj": o.obj, "truth": tname, "shape": o.shape, "route": o.route, "arm": o.arm,
                 "grasp": o.grasp, "drop": o.drop, "bin": o.bin, "result": where, "ok": ok,
                 "pos": None if p is None else np.round(p, 3).tolist(), "t_start": t0, "t_look": round(self._t, 2)})

    def _look_locked(self):
        self._record_outcome()
        res = super()._look_locked()
        if self._last_pick is not None:      # a prefetched plan was accepted: _plan_next did not run for this look
            try:
                self._settle_last_pick(list(self.cam.last) if self.cam is not None else self.truth.detect())
            except Exception as e:
                self.log(f"[decision-oracle] failure memory: {e!r}")
        return res

    def _start(self, plan, t):
        o = getattr(plan, "option", None)
        if o is not None:
            tname = self._truth_name(o)
            self._executing = (o, round(t, 2), getattr(plan, "decision_id", None), tname)
            self.picks.setdefault(o.obj, []).append(o.route)
            if o.route == "direct":
                self._bin_count[o.bin] = self._bin_count.get(o.bin, 0) + 1
            self._w({"type": "exec", "decision": getattr(plan, "decision_id", None), "t": round(t, 2),
                     "option": o.to_json(), "truth": tname})
            self._last_pick = {"o": o, "failed": None}
        out = super()._start(plan, t)
        self._gc = None
        if o is not None and self.grasp_check != "off":
            cut = next((e for name, s, e in plan.phases if name == "lift"), None)
            done = len(plan.arm) - len(self.queue_a)          # ticks already handed out by super()._start
            if cut is not None and done < cut < len(plan.arm):
                self._gc = {"plan": plan, "option": o, "side": plan.side, "rest_a": plan.arm[cut:], "rest_h": plan.hand[cut:]}
                self.queue_a, self.queue_h = plan.arm[done:cut], plan.hand[done:cut]
        return out

    def _commit(self, p):
        super()._commit(p)
        for xy in getattr(p, "skip_xy", None) or []:
            self.failed.append(np.asarray(xy, float))

    # ------------------------------------------------------------------ camera mode helpers
    def _wait_sim(self, t_until, wall_timeout=15.0):
        """Planning thread only: sleep until the sim clock (from obs) reaches t_until."""
        t0 = time.monotonic()
        while self._t < t_until and time.monotonic() - t0 < wall_timeout:
            time.sleep(0.02)

    def _truth_objects(self):
        """Evaluation-only: true objects on the counter from the scene service (None without a client)."""
        if self.client is None:
            return None
        try:
            return self.truth.detect()
        except Exception:
            return None

    def _truth_name(self, o):
        """Evaluation-only: the sim's name of the object an option is about (for outcome logging)."""
        if self.cam is None:
            return o.obj
        gt = self._truth_objects()
        if not gt:
            return None
        d = min(gt, key=lambda g: np.linalg.norm(g.top[:2] - o.det.top[:2]))
        return d.name if np.linalg.norm(d.top[:2] - o.det.top[:2]) < 0.04 else None

    def _log_perception(self, dets):
        """Evaluation-only: what the camera saw next to the truth (position error, shape, yaw, misses, extras)."""
        gt = self._truth_objects()
        if gt is None:
            return
        used, rows = set(), []
        for g in gt:
            best = None
            for i, d in enumerate(dets):
                e = float(np.linalg.norm(d.top[:2] - g.top[:2]))
                if i not in used and e < 0.04 and (best is None or e < best[0]):
                    best = (e, i)
            if best is None:
                rows.append({"truth": g.name, "seen": None})
                continue
            used.add(best[1])
            d = dets[best[1]]
            n = {"cube": 4, "triangle": 3}.get(g.shape)
            ye = None
            if n and d.yaw is not None and d.shape == g.shape:
                per = 2 * np.pi / n
                ye = float(np.degrees(abs((d.yaw - g.yaw + per / 2) % per - per / 2)))
            rows.append({"truth": g.name, "seen": d.name, "err_mm": round(best[0] * 1000, 1), "color": d.color,
                         "shape": d.shape, "shape_geom": getattr(d, "shape_geom", d.shape), "true_shape": g.shape,
                         "d1": getattr(d, "d1", None), "yaw_err_deg": _r(ye), "feat": {k: _r(v, 3) for k, v in d.feat.items()
                                                                            if not isinstance(v, dict)}})
        extra = [{"seen": d.name, "color": d.color, "shape": d.shape, "xy": np.round(d.top[:2], 3).tolist()}
                 for i, d in enumerate(dets) if i not in used]
        f = self.cam.fit
        self._w({"type": "perception", "t": round(self._t, 2), "rows": rows, "extra": extra,
                 "pose": None if f is None else {"ok": f.ok, "tilt_deg": _r(f.tilt_deg, 2), "dxy": np.round(f.dxy, 4).tolist(),
                                                 "dyaw_deg": _r(f.dyaw_deg, 2), "walls": _r(f.wall_score, 2), "why": f.why}})

    def _update_drop_offsets(self, exclude=None):
        if self.cam is None:
            return super()._update_drop_offsets(exclude)
        from aaltonomous.sim.oracle import DROP_OFFSETS
        # no view into the bins used: cycle by how many objects we have released into each bin (the one being
        # carried now is already counted at _start)
        self.planner.drop_offsets = {b: DROP_OFFSETS[self._bin_count.get(b, 0) % len(DROP_OFFSETS)]
                                     for b in self.scene.bin_names}

    def _detections(self, fresh):
        if self.cam is not None and not fresh:
            return list(self.cam.last)     # prefetch: the arm is moving through the view; reuse the last look
        return self.perception.detect()

    # ------------------------------------------------------------------ the look
    def _plan_next(self, arm, hand, exclude=None, commit=True):
        self._look_n += 1
        did = f"{self.episode_seed}-{self._look_n}"
        t0 = time.monotonic()
        self._update_drop_offsets(exclude)
        dets = [d for d in self._detections(fresh=commit) if d.name != exclude]
        self.last_detections = dets
        if commit:
            self._settle_last_pick(dets)
        budget = self.chooser.budget_s if not commit else min(self.chooser.budget_s, self.look_budget_s)
        if commit and self.retry == "object" and any(self.hist.get(d.name) for d in dets):
            budget = self.chooser.budget_s      # a retry needs the alternatives: the default is what just failed
        options, info = self.enum.feasible_options(dets, arm, hand, budget_s=budget)
        rec = {"type": "look", "decision": did, "prefetch": not commit, "t": round(self._t, 2),
               "perception": self.perception_mode,
               "n_dets": len(dets), "dets": [{"obj": d.name, "xy": np.round(d.top[:2], 3).tolist(),
                                              "yaw_deg": _r(np.degrees(d.yaw) if d.yaw is not None else None)}
                                             for d in dets],
               "planner": info, "options": [o.to_json() for o in options],
               "history": {k: [f"{f['arm']}/{f['grasp']}/{f['source']}" for f in v] for k, v in self.hist.items()}}
        if not options:
            if commit:   # Aalto: objects with neither a direct nor a relay plan are given up on
                xy = {d.name: d.top[:2] for d in dets}
                for r in info["relay_tried"]:
                    if not r["ok"] and r["obj"] in xy:
                        self.failed.append(xy[r["obj"]].copy())
                        self.log(f"[decision-oracle] skip {r['obj']}: no direct or relay plan")
            rec["chosen"] = None
            rec["t_look_s"] = round(time.monotonic() - t0, 2)
            self._w(rec)
            return ("none", None, len(dets))

        retry = sorted(n for n, routes in self.picks.items() if "direct" in routes and any(o.obj == n for o in options))
        ctx = {"dets": dets, "mapping_text": ", ".join(f"{k} objects -> {v} bin" for k, v in self.mapping.items()),
               "time_left": max(0.0, float(self.time_limit) - self._t), "attempts": {n: len(r) for n, r in self.picks.items()},
               "retry_objs": retry, "drop_choices": self.enum.drop_choices, "history": self.hist,
               "jpeg": C.jpeg(self._rgb) if self.chooser.name == "decision" else None}
        try:
            o, drop, crec = self.chooser.choose(options, ctx)
        except Exception as e:   # never lose the look to a chooser bug
            o = next(x for x in options if x.is_default)
            drop, crec = o.drop, {"chooser": self.chooser.name, "fallback": f"error {e!r}"}
        rec["choice"] = crec
        skip_xy = []
        if crec.get("skip"):
            xy = {d.name: d.top[:2] for d in dets}
            skip_xy = [xy[n].copy() for n in crec["skip"] if n in xy]
        if o is None:              # the chooser skipped everything that was left
            if commit:
                self.failed.extend(skip_xy)
            rec["chosen"] = None
            rec["t_look_s"] = round(time.monotonic() - t0, 2)
            self._w(rec)
            return ("none", None, len(dets))
        if drop is not None and drop != o.drop:
            o2 = self.enum.replan_drop(o, drop, arm, hand)
            if o2 is None:
                rec["drop_fallback"] = f"spot{drop} did not plan; kept spot{o.drop}"
            else:
                o = o2
        p = o.plan
        p.option, p.decision_id, p.skip_xy = o, did, skip_xy
        if commit:
            self._commit(p)
        rec["chosen"] = o.to_json()
        rec["t_look_s"] = round(time.monotonic() - t0, 2)
        self._w(rec)
        return ("plan", p, len(dets))

    def close(self):
        if self._dlog:
            self._dlog.close()
            self._dlog = None


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def _js(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
