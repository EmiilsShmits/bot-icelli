"""Motion function library: Aalto's scripted oracle split into explicit, parameterised motion functions.

Aalto's `OraclePolicy._plan_next` (third_party/.../aaltonomous/sim/oracle.py) makes six choices internally. Here
each is a parameter of a function that returns a validated `Plan` (every check of the classical planner: IK, counter
and bin-rim clearance, speed limits, safety-filter dry run with 0 clips) or a failure reason:

    object      which object next                      candidates()
    arm         "left" | "right"                       plan_direct(..., arm=...)
    grasp       "face<k>" (fingers on face k) | "stock"  plan_direct(..., grasp=...), face_options()
    route       "direct" | "relay"                     plan_direct() / plan_relay()
    bin         from the mapping (scene.resolve_bin)   target_bin()
    drop        index into DROP_OFFSETS                plan_direct(..., drop=...), drop_ok()
    retry/skip  after a failed pick                    (policy.py, by object name)

`OptionEnumerator.feasible_options()` lists, for the current state, only options whose plan passed those checks:
first the oracle's own choice (so the default always exists), then alternatives until a time budget runs out.

Privileged object poses (scene service) only: this is for exploration and data generation, not a submission.
Never edits third_party/: everything is imported (and the planner subclassed) like oracle.py does itself.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

from aaltonomous.baselines.classical.planner import Plan, Planner
from aaltonomous.scene.scene import resolve_bin
from aaltonomous.sim import oracle as O

GRASP_STOCK = "stock"


@dataclass
class Option:
    """One fully planned, checked way to handle one object (what a chooser picks from)."""
    obj: str
    color: str
    shape: str
    bin: str
    arm: str
    grasp: str                 # "face<k>" | "stock"
    route: str                 # "direct" | "relay"
    drop: int                  # DROP_OFFSETS index (direct only; -1 for relay)
    plan: Plan = field(repr=False)
    det: object = field(repr=False, default=None)
    is_default: bool = False
    finger_deg: float | None = None   # finger direction at the grasp, pelvis yaw (deg)
    face_deg: float | None = None     # requested face normal (deg), face grasps only

    @property
    def key(self):
        return (self.obj, self.arm, self.grasp, self.route, self.drop)

    @property
    def duration(self):
        return float(self.plan.duration)

    def to_json(self):
        return {"obj": self.obj, "color": self.color, "shape": self.shape, "bin": self.bin, "arm": self.arm,
                "grasp": self.grasp, "route": self.route, "drop": self.drop, "default": self.is_default,
                "duration_s": round(self.duration, 2), "finger_deg": _r(self.finger_deg), "face_deg": _r(self.face_deg),
                "reason": self.plan.reason}


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def target_bin(mapping, det):
    """Target bin from the instruction mapping (colour, shape, (colour, shape) or `default` keys)."""
    return resolve_bin(mapping, det.color, getattr(det, "shape", None))


TRI_PHI_ALTS = (75.0, 90.0)   # triangle finger direction vs apex (deg) besides Aalto's TRI_PHI_DEG (105); Aalto's
                              # grasp_test (noisy, 6 tries each): 105 -> 4/6, 90 -> 3/6, 60 -> worst, 30 -> 1/6, 0 -> 0/6


def face_options(det, side, phi_deg=None):
    """Face-aligned finger directions (rad, pelvis yaw) that Aalto's oracle would try for this object and arm, nearest
    the arm's natural finger direction first. Empty for shapes without flat faces (cylinders) or unknown yaw.
    phi_deg: triangles only, finger direction vs the apex (None = Aalto's TRI_PHI_DEG)."""
    shape, yaw = getattr(det, "shape", None), getattr(det, "yaw", None)
    if shape not in O.FACE_ALIGN or yaw is None:
        return []
    off, n = O.FACE_ALIGN[shape]
    if shape == "triangle" and phi_deg is not None:
        off = np.pi / 2 + np.radians(phi_deg)
    ref = np.radians(O.FINGER_REF_DEG[side])
    out = []
    for k in range(n):
        a = yaw + off + 2 * np.pi * k / n
        da = abs((a - ref + np.pi) % (2 * np.pi) - np.pi)
        if da <= np.radians(O.FACE_MAX_DEV_DEG):
            out.append((da, k, float((a + np.pi) % (2 * np.pi) - np.pi)))
    return [(k, a) for _, k, a in sorted(out)]


class MotionLibrary:
    """The parameterised motion functions, bound to an OraclePolicy's planners (`pol.planner`, `pol.relay`)."""

    def __init__(self, pol):
        self.pol = pol

    @property
    def planner(self):
        return self.pol.planner

    # ------------------------------------------------------------------ helpers
    def finger_deg(self, plan, side):
        """Finger direction (palm x axis, horizontal, pelvis yaw in deg) at the end of `descend`."""
        try:
            e = next(e for name, s, e in plan.phases if name == "descend")
            self.planner.kin._fk(plan.arm[e - 1])
            x = self.planner.kin.data.oMf[self.planner.kin.palm[side]].rotation[:, 0]
            return float(np.degrees(np.arctan2(x[1], x[0])))
        except Exception:
            return None

    def _with_drop(self, bin_name, drop):
        """Context: temporarily put the drop point of `bin_name` at DROP_OFFSETS[drop]."""
        pl = self.planner

        class _Ctx:
            def __enter__(s):
                s.saved = dict(pl.drop_offsets)
                if drop is not None and drop >= 0:
                    pl.drop_offsets = dict(pl.drop_offsets)
                    pl.drop_offsets[bin_name] = O.DROP_OFFSETS[drop % len(O.DROP_OFFSETS)]

            def __exit__(s, *a):
                pl.drop_offsets = s.saved
        return _Ctx()

    # ------------------------------------------------------------------ motion functions
    def plan_direct(self, det, arm, grasp, bin_name, arm_q, hand_q, drop=None):
        """Pick `det` with `arm` and put it in `bin_name` directly.
        grasp: "face<k>" = fingers along the outward normal of face k (Aalto's face-aligned grasp, that face only);
               "stock"   = the classical planner's finger hints (forward, forward-inward, inward);
               "auto"    = Aalto's oracle rule for this arm (faces nearest first, then stock).
        drop: DROP_OFFSETS index for this bin (None = the oracle's current per-bin offset).
        Returns (Plan or None, reason)."""
        pl = self.planner
        arm_q, hand_q = np.asarray(arm_q, float), np.asarray(hand_q, float)
        if bin_name in pl.scene.cfg["bins"]["centers"] and not pl._reaches_bin(arm, bin_name):
            return None, f"{arm} arm cannot reach the {bin_name} bin"
        with self._with_drop(bin_name, drop):
            if grasp == "auto":
                p = pl._plan_side_faces(det, arm, bin_name, arm_q, hand_q)
            elif grasp == GRASP_STOCK:
                p = Planner._plan_side_hints(pl, det, arm, bin_name, arm_q, hand_q)
            elif grasp.startswith("face"):
                k, phi = parse_face(grasp)
                a = dict(face_options(det, arm, phi)).get(k)
                if a is None:
                    return None, f"face {k} is not within {O.FACE_MAX_DEV_DEG:.0f} deg of the {arm} hand's direction"
                p = self._plan_face(det, arm, bin_name, arm_q, hand_q, a)
            else:
                raise ValueError(grasp)
        if p is None or not p.ok:
            return None, (p.reason if p is not None else "no plan")
        return p, p.reason or "ok"

    def _plan_face(self, det, side, bin_name, arm_q, hand_q, a):
        """One face of Aalto's `_plan_side_faces` loop (same hint weight, triangle shift and tolerance)."""
        pl = self.planner
        f = np.array([np.cos(a), np.sin(a), 0.0])
        d2 = copy.copy(det)
        if det.shape == "triangle":
            d2.top = det.top + O._tri_shift(a - (det.yaw + np.pi / 2)) * f
        saved = (pl.kin.hint, pl.kin.w_hint)
        try:
            pl.kin.hint, pl.kin.w_hint = f, O.FACE_HINT_WEIGHT
            p = pl._plan_side(d2, side, bin_name, arm_q, hand_q)
        finally:
            pl.kin.hint, pl.kin.w_hint = saved
        if p.ok:
            err = pl._finger_err(p, side, f)
            if err > O.FACE_TOL_DEG:
                p.ok, p.reason = False, f"finger direction {err:.0f} deg off the face (tol {O.FACE_TOL_DEG:.0f})"
            else:
                p.reason = f"face-aligned ({np.degrees(a):.0f} deg, err {err:.0f})"
        return p

    def plan_relay(self, det, dets, arm_q, hand_q):
        """Aalto's relay: put `det` down at a free relay point near the centre line that the other arm can carry
        to the bin from (both legs checked). Returns (Plan or None, reason)."""
        p = self.pol._plan_relay(det, dets, arm_q, hand_q)
        if p is None:
            return None, "no relay point with both legs planned"
        return p, f"relay via point {p.relay}"

    def drop_ok(self, arm, bin_name, drop):
        """Cheap check (two IKs): can `arm` put its grasp point above and at the drop point DROP_OFFSETS[drop]?"""
        pl = self.planner
        g, sc = pl.cfg["grasp"], pl.scene
        wall = float(sc.cfg["bins"]["wall_height"])
        xy = Planner.drop_xy(pl, bin_name) + np.asarray(O.DROP_OFFSETS[drop], float)
        for z in (sc.counter_z + max(g["carry_height"], wall + pl.height + 0.03),
                  sc.counter_z + wall + pl.height / 2 + g["drop_above_rim"]):
            if not pl.kin.solve(arm, np.r_[xy, z], pl.home, restarts=False)[1]:
                return False
        return True


def parse_face(grasp):
    """'face1' -> (1, None); 'face1p90' -> (1, 90.0)."""
    s = grasp[4:]
    if "p" in s:
        k, phi = s.split("p")
        return int(k), float(phi)
    return int(s), None


def grasp_variants(det, arm):
    """Grasp labels to try for one object and arm: Aalto's faces, stock hints, then triangle finger-angle variants."""
    out = [f"face{k}" for k, _ in face_options(det, arm)] + [GRASP_STOCK]
    if getattr(det, "shape", None) == "triangle":
        out += [f"face{k}p{phi:.0f}" for phi in TRI_PHI_ALTS for k, _ in face_options(det, arm, phi)]
    return out


def grasp_label(plan):
    """'face<k>' / 'stock' from a plan made by Aalto's rule (reason 'face-aligned (<deg> deg, ...)')."""
    return "face" if str(plan.reason).startswith("face-aligned") else GRASP_STOCK


class OptionEnumerator:
    """Lists feasible options for one look. The oracle's own choice comes first (is_default=True)."""

    def __init__(self, pol, lib: MotionLibrary):
        self.pol, self.lib = pol, lib

    def candidates(self, dets):
        """Objects on the counter (not in a bin), with a target bin, not given up on (Aalto's failed / attempts rule),
        nearest their bin first (Aalto's order)."""
        pol = self.pol
        r = pol.cfg["policy"]["same_object_radius"]
        cands = []
        for d in dets:
            xy = d.top[:2]
            if any(np.linalg.norm(xy - f) < r for f in pol.failed):
                continue
            if getattr(pol, "retry", "position") == "object":
                # retries counted per object (failure memory), not per table position; the position rule stays as
                # a backstop at twice the number of tries
                if len(pol.hist.get(d.name, [])) >= pol.max_tries:
                    continue
                if sum(c for p, c in pol.attempts if np.linalg.norm(xy - p) < r) >= 2 * pol.max_tries:
                    continue
            elif sum(c for p, c in pol.attempts if np.linalg.norm(xy - p) < r) >= pol.cfg["policy"]["max_attempts"]:
                continue
            d.bin = target_bin(pol.mapping, d)
            if d.bin is not None:
                cands.append(d)
        cands.sort(key=lambda d: np.linalg.norm(d.top[:2] - pol.planner.bin_xy(d.bin)))
        return cands

    def _option(self, d, p, arm, grasp, route, drop, default=False, face_a=None):
        if grasp == "face" and face_a is None:       # Aalto's rule picked a face: find which
            fd = self.lib.finger_deg(p, arm)
            if fd is not None:
                best = min(face_options(d, arm), key=lambda ka: abs((np.radians(fd) - ka[1] + np.pi) % (2 * np.pi) - np.pi),
                           default=None)
                if best is not None:
                    grasp, face_a = f"face{best[0]}", best[1]
        o = Option(d.name, d.color, getattr(d, "shape", "?"), d.bin, arm, grasp, route, drop, p, det=d,
                   is_default=default, finger_deg=self.lib.finger_deg(p, arm) if route == "direct" else None,
                   face_deg=None if face_a is None else float(np.degrees(face_a)))
        p.obj, p.obj_xy = d.name, d.top[:2].copy()
        p.relay = getattr(p, "relay", None) if route == "relay" else None
        return o

    def default_drop(self, bin_name):
        off = tuple(self.pol.planner.drop_offsets.get(bin_name, (0.0, 0.0)))
        return next((i for i, o in enumerate(O.DROP_OFFSETS) if tuple(o) == off), 0)

    def feasible_options(self, dets, arm_q, hand_q, budget_s=0.0, relay_budget_s=O.RELAY_BUDGET_S):
        """Returns (options, info). info: tried / failed reasons per (obj, arm, grasp), unplannable objects, timings.
        budget_s = extra time for alternatives after the default (0 = exactly Aalto's search)."""
        pol, lib = self.pol, self.lib
        t0 = time.monotonic()
        info = {"tried": [], "no_direct": [], "relay_tried": [], "t_default_s": None, "t_total_s": None,
                "budget_s": budget_s, "budget_hit": False}
        cands = self.candidates(dets)
        options, seen = [], set()

        def add(o):
            if o.key not in seen:
                seen.add(o.key)
                options.append(o)

        # 1. the oracle's own choice: first object (nearest its bin) with a direct plan (Aalto's planner.plan)
        direct_done = {}
        for d in cands:
            p = pol.planner.plan(d, arm_q, hand_q, bin_name=d.bin, relocate=False)
            direct_done[d.name] = p.ok
            info["tried"].append({"obj": d.name, "arm": "auto", "grasp": "auto", "ok": bool(p.ok),
                                  "reason": p.reason[:160]})
            if p.ok:
                add(self._option(d, p, p.side, grasp_label(p), "direct", self.default_drop(d.bin), default=True))
                break
        # no direct plan for any object: Aalto relays (first object that has one)
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

        # 2. alternatives, cheapest-information first, until the budget runs out
        deadline = time.monotonic() + budget_s

        def out_of_time():
            if time.monotonic() > deadline:
                info["budget_hit"] = True
                return True
            return False

        d_def = options[0].det
        others = [d for d in cands if d.name != d_def.name]
        hist = getattr(pol, "hist", {}) if getattr(pol, "retry", "position") == "object" else None

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
            """Arm x grasp variants of one object."""
            pairs = [(arm, g) for arm in ("left", "right") for g in grasp_variants(d, arm)]
            if hist is not None:
                # Aalto's rule already tried every face on its arm before it fell back to the stock claw
                stock_arms = {o.arm for o in options if o.obj == d.name and o.grasp == GRASP_STOCK}
                pairs = [(a, g) for a, g in pairs if not (a in stock_arms and g.startswith("face") and "p" not in g)]
                # untried (arm, grasp) first, face grasps before the stock claw
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

        done_variants = set()
        if hist is not None:
            # failure memory: the chooser takes the object with the fewest failures, so spend the budget there
            # first: find that object, then plan its grasp variants before anything else
            def nf(d):
                return len(hist.get(d.name, []))
            target = d_def
            for d in sorted(others, key=nf):
                if nf(d) >= nf(d_def) or out_of_time():
                    break
                if plan_other(d):
                    target = d
                    break
            info["target"] = target.name
            variants(target)
            done_variants.add(target.name)
        # 2a. one plan per other object
        for d in others:
            if out_of_time():
                break
            plan_other(d)
        # 2b. arm x grasp variants, default object first
        for d in [d_def] + [d for d in others if direct_done.get(d.name)]:
            if d.name not in done_variants:
                variants(d)
        # 2c. relay for objects that have no direct plan at all (Aalto only relays when nothing else is plannable)
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

    def drop_choices(self, opt):
        """DROP_OFFSETS indices that pass the cheap IK check for this option's arm and bin (direct only)."""
        if opt.route != "direct":
            return []
        return [k for k in range(len(O.DROP_OFFSETS)) if k == opt.drop or self.lib.drop_ok(opt.arm, opt.bin, k)]

    def replan_drop(self, opt, drop, arm_q, hand_q):
        """The same option with another drop spot (one full plan). Returns a new Option or None."""
        if opt.route != "direct" or drop == opt.drop:
            return opt
        grasp = opt.grasp if opt.grasp.startswith("face") or opt.grasp == GRASP_STOCK else "auto"
        p, why = self.lib.plan_direct(opt.det, opt.arm, grasp, opt.bin, arm_q, hand_q, drop=drop)
        if p is None:
            return None
        o = self._option(opt.det, p, opt.arm, opt.grasp, "direct", drop,
                         face_a=None if opt.face_deg is None else np.radians(opt.face_deg))
        return o
