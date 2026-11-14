"""v1.5 upgrades, on top of upgrades.py and kept in a file of their own (the other files of this folder are unchanged;
everything here subclasses them). Used by the v1.5 policy server (`policy/policies/oracle_v15.py`) and by the sim
evaluation below.

    # sim evaluation, same arguments as upgrades.py (camera perception + memory chooser + grasp check by default)
    PYTHONPATH=/root/aaltonomous-humanoid:/root python -m decision_oracle.upgrades_v15 --task sort_fixed --trials 6 \
        --seed 1000 --out /root/runs_do [--sides off]
    python -m decision_oracle.upgrades_v15 --selftest 6     # no sim: side rule + ridge grasp plans on random layouts

1. Same-side arms (`--sides strict`, the default). Each arm works only on its own half of the table: the left arm
   grasps objects with pelvis y > -SIDE_BAND and drops only into bins (or relay points) with y > -SIDE_BAND; the
   right arm mirrored. The two arms then never reach across the body, so they cannot hit each other or sweep over
   the other half. An object on one side that belongs in the other side's bin goes through Aalto's relay: the arm
   on its side puts it down on the centre line, the other arm takes it from there (relay points nearest y = 0 first).
   The rule sits in the planner (`SidedPlanner._plan_side`), so every route (Aalto's own choice, grasp variants,
   relays) obeys it. `--sides off` = Aalto's rule (the bin's side first, any arm allowed).

2. Lying ("tipped") triangles. A triangular prism that fell over lies on a rectangular face with a ridge on top
   (seen in the sim after a failed claw grasp, and on the real table). Its two triangular end faces are parallel and
   one object size apart (45 mm), like two faces of a cube. Grasp: fingers along the ridge, thumb on one end face,
   fingers on the other, from above. (Pinching across the two sloped faces would squeeze it upwards out of the hand.)
     - camera: `classify_top` already calls such an object "tipped"; RidgeCamera adds the ridge direction as its yaw
       (main axis of the top strip of points).
     - plan: SidedPlanner._plan_side_faces tries the two finger directions (ridge yaw, ridge yaw + 180 deg) with
       Aalto's face-grasp settings (same IK weight, same 12 deg finger-direction check), allowing up to 95 deg from
       the arm's natural finger direction (Aalto: 75 deg; with only two faces 180 deg apart, one is always within 90),
       then the stock hints. Every route that uses Aalto's arm/grasp rule gets it (labelled "face").
     - chooser: the stock claw on a tipped object is a last resort, as on a standing triangle.
   A lying cylinder shows a ridge too and gets the same grasp across its flat ends.

Classes: SidedPlanner, RidgeCamera, V15Chooser, V15OraclePolicy.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import time

import numpy as np

from aaltonomous.baselines.classical.perception import Detection
from aaltonomous.baselines.classical.planner import Plan, Planner
from aaltonomous.sim import oracle as O

from . import camera as CAMMOD
from .chooser import _grasp_kind
from .upgrades import MemoryChooser, TrackingCamera, UpgradedOraclePolicy

SIDE_BAND = 0.03          # m. Either arm may work within this distance of the centre line (relay points sit at y = 0).
TIP_MAX_DEV_DEG = 95.0    # ridge grasp: finger direction may be this far from the arm's natural one (Aalto faces: 75)
RIDGE_MIN_RATIO = 2.0     # top strip length / width below which the ridge direction is not trusted
SIDES = ("strict", "off")


def _ridge_shift(spec):
    """V15_RIDGE_SHIFT: "SX,SZ" (both hands) or "left:SX,SZ;right:SX,SZ", mm. See RIDGE_SHIFT_MM."""
    out = {"left": (0.0, 0.0), "right": (0.0, 0.0)}
    for part in filter(None, (spec or "").replace(" ", "").split(";")):
        sides, _, val = part.rpartition(":")
        sx, sz = (float(v) for v in val.split(","))
        for sd in ([sides] if sides else ("left", "right")):
            out[sd] = (sx, sz)
    return out


# Ridge grasp: where the hand sits relative to the lying object, in the hand's own frame (mm): SX along the finger
# direction (+ = hand further along the ridge), SZ along palm +z (the index finger's side; mirror-symmetric for the
# two hands). (0, 0) = Aalto's grasp point (palm (99, -84, 15) mm), where the closed thumb stops ~15 mm short of the
# near end face and the fingers must sweep the object back into it (policy/decision_oracle/README.md, ridge grasp).
RIDGE_SHIFT_MM = _ridge_shift(os.environ.get("V15_RIDGE_SHIFT", ""))
# Lying object: first look for a ridge plan on either arm, the stock claw only if neither has one (Aalto's plan() keeps
# the quickest plan over both arms, and a stock plan on one arm counts as a plan, so it could beat the other arm's ridge).
# Both default off in v1.5 (its behaviour unchanged); v1.6 turns them on (upgrades_v16.V16OraclePolicy).
RIDGE_FIRST = os.environ.get("V15_RIDGE_FIRST", "off").lower() in ("1", "on", "true", "yes")


def palm_z_dir(side, f):
    """World direction of palm +z for a hand pointing its fingers along horizontal f, palm facing down (left palm
    +y up, right palm +y down: kinematics.py)."""
    return np.array([f[1], -f[0], 0.0]) if side == "left" else np.array([-f[1], f[0], 0.0])
MAX_RELAYS_STRICT = 3     # relay tries per object with same-side arms (Aalto: 1). There a cross-side object has no
                          # other way to its bin, and Aalto's count includes relays whose grasp closed on nothing


def arm_allowed(arm, y, band=SIDE_BAND):
    """May `arm` work at pelvis y (left = +y)?"""
    return y > -band if arm == "left" else y < band


# ---------------------------------------------------------------------------------------------------- planner
class SidedPlanner(O._OraclePlanner):
    """Aalto's oracle planner with the same-side rule. Every grasp plan goes through _plan_side, so checking there
    covers Aalto's arm choice, the grasp variants and both legs of a relay."""
    sides = "strict"

    def side_ok(self, det, side, bin_name, place_xy=None):
        if self.sides != "strict":
            return True, ""
        y = float(det.top[1])
        if not arm_allowed(side, y):
            return False, f"{side} arm: object on the other side (y {100 * y:+.1f} cm)"
        ty = float(place_xy[1]) if place_xy is not None else (float(self.bin_xy(bin_name)[1]) if bin_name else 0.0)
        if not arm_allowed(side, ty):
            return False, f"{side} arm: {bin_name} is on the other side"
        return True, ""

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, place_xy=None):
        ok, why = self.side_ok(det, side, bin_name, place_xy)
        if not ok:
            return Plan(False, side=side, color=det.color, reason=why)
        return super()._plan_side(det, side, bin_name, arm_q, hand_q, place_xy=place_xy)

    _ridge_only = False
    face_only = False                 # v1.6 near-body relay (near_v16.py): face / ridge grasps only, no stock claw
    ridge_shift = RIDGE_SHIFT_MM      # per planner: v1.6 sets its own
    ridge_first = RIDGE_FIRST

    def plan(self, det, arm_q, hand_q, bin_name=None, obstacles=(), relocate=True):
        """A lying object with a ridge direction: Aalto's plan() over both arms with ridge grasps only (no relocation),
        then, if no arm has one, Aalto's plan() as is (stock claw, relocation). Anything else: Aalto's plan()."""
        if self.ridge_first and getattr(det, "shape", None) == "tipped" and getattr(det, "yaw", None) is not None:
            self._ridge_only = True
            try:
                p = super().plan(det, arm_q, hand_q, bin_name=bin_name, obstacles=obstacles, relocate=False)
            finally:
                self._ridge_only = False
            if p.ok:
                return p
        return super().plan(det, arm_q, hand_q, bin_name=bin_name, obstacles=obstacles, relocate=relocate)

    def _plan_side_faces(self, det, side, bin_name, arm_q, hand_q, **kw):
        """A lying object: fingers along its ridge (across the two flat end faces), then the stock hints. Other
        shapes: Aalto's face-aligned grasp."""
        yaw = getattr(det, "yaw", None)
        if getattr(det, "shape", None) != "tipped" or yaw is None:
            p = super()._plan_side_faces(det, side, bin_name, arm_q, hand_q, **kw)
            if self.face_only and p.ok and not str(p.reason).startswith("face-aligned"):
                return Plan(False, side=side, color=det.color, reason=f"{side}: no face plan")
            return p
        ref = np.radians(O.FINGER_REF_DEG[side])
        cands = []
        for k in range(2):
            a = yaw + k * np.pi
            da = abs((a - ref + np.pi) % (2 * np.pi) - np.pi)
            if da <= np.radians(TIP_MAX_DEV_DEG):
                cands.append((da, a))
        saved = (self.kin.hint, self.kin.w_hint)
        try:
            sx, sz = self.ridge_shift[side]
            for _, a in sorted(cands):
                f = np.array([np.cos(a), np.sin(a), 0.0])
                d2 = det
                if sx or sz:
                    d2 = copy.copy(det)
                    d2.top = det.top + (sx * f + sz * palm_z_dir(side, f)) / 1000.0
                self.kin.hint, self.kin.w_hint = f, O.FACE_HINT_WEIGHT
                p = self._plan_side(d2, side, bin_name, arm_q, hand_q, **kw)
                if p.ok:
                    err = self._finger_err(p, side, f)
                    if err <= O.FACE_TOL_DEG:
                        p.reason = f"face-aligned ridge ({np.degrees(a):.0f} deg, err {err:.0f})"
                        return p
        finally:
            self.kin.hint, self.kin.w_hint = saved
        if self._ridge_only or self.face_only:
            return Plan(False, side=side, color=det.color, reason=f"{side}: no ridge plan")
        return Planner._plan_side_hints(self, det, side, bin_name, arm_q, hand_q, **kw)


# ---------------------------------------------------------------------------------------------------- camera
def ridge_yaw(xy):
    """Top strip points (n, 2) of a lying object -> (ridge direction in rad mod pi, length/width ratio)."""
    p = np.asarray(xy, float)
    c = p - p.mean(0)
    w, v = np.linalg.eigh(c.T @ c)
    ax = v[:, -1]
    yaw = float((np.arctan2(ax[1], ax[0]) + np.pi / 2) % np.pi - np.pi / 2)
    return yaw, float(np.sqrt(w[-1] / max(w[0], 1e-12)))


_classify_top = CAMMOD.classify_top


def classify_top_v15(xy):
    """camera.classify_top + a yaw for "tipped": the ridge direction (None if the strip is not clearly long)."""
    try:
        shape, yaw, centre, f = _classify_top(xy)
    except Exception as e:      # OpenCV's triangle fit can fail on a thin strip (seen with OpenCV 5.0): a lying object
        import cv2
        pts = np.asarray(xy, np.float32) * 1000.0
        hull = cv2.convexHull(pts)
        (_, (rw, rh), _) = cv2.minAreaRect(hull)
        shape, yaw, centre = "tipped", None, np.asarray(xy, float).mean(0)
        f = {"area_mm2": float(cv2.contourArea(hull)), "short_mm": float(min(rw, rh)), "long_mm": float(max(rw, rh)),
             "fit_error": type(e).__name__}
    if shape == "tipped" and len(xy) >= 25:
        ry, ratio = ridge_yaw(xy)
        f["ridge_ratio"] = ratio
        if ratio >= RIDGE_MIN_RATIO:
            yaw = ry
    return shape, yaw, centre, f


class RidgeCamera(TrackingCamera):
    """TrackingCamera whose shape step also gives a lying object's ridge direction (camera.py stays unchanged: its
    module-level classify_top is swapped for the duration of this camera's own detection only)."""

    def _detect(self, rgb, depth):
        saved = CAMMOD.classify_top
        CAMMOD.classify_top = classify_top_v15
        try:
            return super()._detect(rgb, depth)
        finally:
            CAMMOD.classify_top = saved


# ---------------------------------------------------------------------------------------------------- model check
TIP_POSES = {
    "lying_prism": "A triangular prism lying on one of its long rectangular sides: a sharp ridge runs along its top "
                   "and one triangular end face can be seen.",
    "lying_cylinder": "A cylinder lying on its curved side: a round end face can be seen and its top is rounded.",
    "upright": "A block standing upright on a flat end: a cube (square top), a cylinder (round top) or a triangular "
               "prism with a triangle on top.",
    "unclear": "The block is mostly hidden (by a robot hand or the edge of the crop), or there is no single block.",
}
TIP_SHAPES = {"cube": "A cube.", "cylinder": "A cylinder.", "triangle": "A triangular prism."}
TIP_TEXT = ("This is a small crop from a robot's head camera, looking down at a table at an angle. It shows one small "
            "coloured block (about 4.5 cm). Look at the block in the middle of the crop.")
TIP_MODELS = {"hydrogen": "gemini-4-hydrogen", "d1": "gemini-decision-1"}
GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
D1_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"


class TipChecker:
    """Model check of the camera's "lying" label (only for objects the geometry calls "tipped"; the angle stays the
    geometry's). One call per such object and name, in parallel, inside the planning thread, with a deadline; no
    key, an error or a late answer = the geometry stands. Used as the policy's `labeler` (`label(dets, rgb)`)."""

    def __init__(self, model="d1", timeout=2.5, deadline_s=3.0, log=None, workers=4):
        from concurrent.futures import ThreadPoolExecutor
        from .chooser import _api_key
        if model not in TIP_MODELS:
            raise ValueError(f"tip check model {model!r}: use one of {sorted(TIP_MODELS)}")
        self.model, self.timeout, self.deadline_s = model, timeout, deadline_s
        self.log = log or (lambda *a: None)
        try:
            self.key = _api_key()
        except Exception:
            self.key = None
        if not self.key:
            self.log("[v1.5] tip check: no API key, the camera's geometry decides alone")
        self.pool = ThreadPoolExecutor(workers)
        self.cache = {}

    def reset(self):
        self.cache = {}

    def forget(self, name):
        """The object was touched (a failed pick): ask again at the next look."""
        self.cache.pop(name, None)

    def ask(self, jpeg):
        """-> {"pose": one of TIP_POSES, "shape": one of TIP_SHAPES, "latency_s"}; raises on any failure."""
        import base64
        import json
        import time
        import urllib.request
        b64 = base64.b64encode(jpeg).decode()
        q_pose = "How is the block resting on the table?"
        q_shape = "What kind of block is it?"
        if self.model == "d1":
            body = {"model": TIP_MODELS["d1"], "input": [{"type": "text", "text": TIP_TEXT},
                                                         {"type": "image", "data": b64, "mime_type": "image/jpeg"}],
                    "questions": {"pose": {"type": "choice", "instructions": q_pose, "criteria": TIP_POSES},
                                  "shape": {"type": "choice", "instructions": q_shape, "criteria": TIP_SHAPES}}}
            url = D1_URL
        else:
            text = (TIP_TEXT + "\nAnswer as JSON:\n- pose: " + q_pose + " Options: "
                    + "; ".join(f"{k} = {v}" for k, v in TIP_POSES.items())
                    + "\n- shape: " + q_shape + " Options: " + "; ".join(f"{k} = {v}" for k, v in TIP_SHAPES.items()))
            props = {"pose": {"type": "STRING", "enum": list(TIP_POSES)},
                     "shape": {"type": "STRING", "enum": list(TIP_SHAPES)}}
            body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                                                            {"text": text}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                         "responseSchema": {"type": "OBJECT", "properties": props,
                                                            "required": list(props)},
                                         "thinkingConfig": {"thinkingBudget": 0}}}
            url = GEN_URL.format(TIP_MODELS[self.model])
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
        t = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.load(r)
        dt = round(time.monotonic() - t, 2)
        if self.model == "d1":
            a = out["answers"]
            return {"pose": a["pose"]["choice"], "shape": a["shape"]["choice"], "latency_s": dt}
        txt = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"] if not p.get("thought"))
        a = json.loads(txt)
        return {"pose": a["pose"], "shape": a["shape"], "latency_s": dt}

    def label(self, dets, rgb):
        """Adds d.tip_check to every "tipped" detection and applies the answer:
             lying_prism / lying_cylinder -> keep "tipped" (ridge grasp);
             upright -> the geometry misread it (usually part of it hidden): shape = the model's, no yaw (stock grasp),
                        d.recheck = True (the chooser takes other objects first; a later look may see it whole);
             unclear / error / late -> the geometry stands."""
        from concurrent.futures import wait
        from .labels import crop_jpeg
        todo = {}
        for d in dets:
            if d.shape != "tipped":
                continue
            if d.name in self.cache:
                d.tip_check = self.cache[d.name]
            elif self.key and getattr(d, "bbox", None) is not None and rgb is not None:
                j = crop_jpeg(np.asarray(rgb), d.bbox)
                if j is not None:
                    todo[self.pool.submit(self.ask, j)] = d
        if todo:
            wait(list(todo), timeout=self.deadline_s)
        for fut, d in todo.items():
            if fut.done():
                try:
                    d.tip_check = fut.result()
                    self.cache[d.name] = d.tip_check
                except Exception as e:
                    d.tip_check = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            else:
                d.tip_check = {"error": "deadline"}
                fut.cancel()
        for d in dets:
            r = getattr(d, "tip_check", None) or {}
            if d.shape == "tipped" and r.get("pose") == "upright":
                d.shape_geom, d.shape, d.yaw, d.recheck = "tipped", r.get("shape") or "cube", None, True
                self.log(f"[v1.5] tip check: {d.name} is upright ({d.shape}) by {self.model}, not lying")
        return dets


# ---------------------------------------------------------------------------------------------------- chooser
class V15Chooser(MemoryChooser):
    """MemoryChooser; the stock claw on a lying object is a last resort too (0 of 9 held in e-019), and an object the
    model check found upright after the camera called it lying (part of it hidden) waits until the others are done."""
    name = "memory_v15"

    @staticmethod
    def _last_resort(o):
        return o.shape in ("triangle", "tipped") and _grasp_kind(o.grasp) == "stock"

    def choose(self, options, ctx):
        later = [o for o in options if getattr(o.det, "recheck", False)]
        if later and len(later) < len(options):
            o, drop, rec = super().choose([o for o in options if not getattr(o.det, "recheck", False)], ctx)
            if o is not None:
                rec["recheck_later"] = sorted({x.obj for x in later})
                return o, drop, rec
        return super().choose(options, ctx)


# ---------------------------------------------------------------------------------------------------- policy
class V15OraclePolicy(UpgradedOraclePolicy):
    def __init__(self, client, sides="strict", chooser=None, tip_check="off", **kw):
        """sides: "strict" (same-side arms) | "off" (Aalto's arm rule).
        tip_check: "off" | "d1" (Gemini Decision 1) | "hydrogen": model check of the camera's "lying" label (TipChecker; camera only).
        Other arguments: UpgradedOraclePolicy."""
        if sides not in SIDES:
            raise ValueError(f"sides={sides!r}: use one of {SIDES}")
        self.sides = sides
        super().__init__(client, chooser=chooser or V15Chooser(), **kw)
        for pl in (self.planner, self.relay):
            pl.__class__ = SidedPlanner
            pl.sides = sides
        if self.cam is not None:
            self.cam = RidgeCamera(self.scene, self.cal, log=self.log)
            if tip_check != "off":
                self.labeler = TipChecker(tip_check, log=self.log)

    def _fail(self, o, source):
        super()._fail(o, source)
        if isinstance(self.labeler, TipChecker):     # a failed pick may have tipped or righted it: ask again
            self.labeler.forget(o.obj)

    def _w(self, rec):
        if isinstance(rec.get("mapping"), dict):        # (colour, shape) keys: JSON keys must be strings
            rec = {**rec, "mapping": {(k if isinstance(k, str) else " ".join(k)): v for k, v in rec["mapping"].items()}}
        super()._w(rec)

    def _plan_relay(self, d, dets, arm, hand):
        """Aalto's relay (oracle.py) with the same-side rule: relay points nearest the centre line first, and points
        one of the two arms may not use are skipped without counting as a try."""
        if self.sides != "strict":
            return super()._plan_relay(d, dets, arm, hand)
        if self.relays.get(d.name, 0) >= MAX_RELAYS_STRICT:
            return None
        others = [o.top[:2] for o in dets if o.name != d.name]
        tried = 0
        for i, xy in sorted(enumerate(O.RELAY_POINTS), key=lambda ixy: abs(ixy[1][1])):
            if tried >= O.MAX_RELAY_POINTS_TRIED:
                break
            xy = np.asarray(xy, float)
            if not (arm_allowed("left", xy[1]) and arm_allowed("right", xy[1])):
                continue
            if np.linalg.norm(xy - d.top[:2]) < 0.04 or any(np.linalg.norm(xy - o) < O.RELAY_CLEAR for o in others):
                continue
            fake = Detection(d.color, np.r_[xy, d.top[2]], 1000, 1000, "relay")
            tried += 1
            p2 = self.planner.plan(fake, self.home, self.post["open"], bin_name=d.bin, relocate=False)
            if not p2.ok:
                continue
            p1 = self.relay.plan(d, arm, hand, bin_name=f"relay{i}", relocate=False)
            if p1.ok:
                p1.target_bin = f"relay -> {d.bin}"
                p1.obj, p1.obj_xy, p1.relay = d.name, d.top[:2].copy(), i
                self.log(f"[v1.5] relay {d.name} via ({xy[0]:.2f},{xy[1]:+.2f}): {p1.side} then {p2.side}")
                return p1
        return None


# ---------------------------------------------------------------------------------------------------- tools
def selftest(layouts=6, seed=0, budget=6.0):
    """No sim (fake scene service, exact poses): every option obeys the side rule; a lying triangle gets ridge-
    aligned plans; with --sides off the original options come back."""
    from aaltonomous.interface import tasks
    from aaltonomous.scene.scene import Scene
    from .test_offline import FakeClient, setup
    scene = Scene.load()
    bad = n_opt = n_ridge = n_tip = 0
    for i in range(layouts):
        rng = np.random.default_rng(seed + i)
        fc = FakeClient(scene, tasks.sample_layout(rng, **scene.layout_kwargs()))
        pol = V15OraclePolicy(fc, sides="strict", threaded=False, prefetch=False, log=None)
        setup(pol)
        pol._update_drop_offsets()
        dets = pol.perception.detect()
        if dets:                                   # make one triangle (or the first object) lie on its side
            k = next((j for j, d in enumerate(dets) if d.shape == "triangle"), 0)
            dets[k].shape, dets[k].yaw = "tipped", float(rng.uniform(-np.pi / 2, np.pi / 2))
            n_tip += 1
        opts, info = pol.enum.feasible_options(dets, pol.arm_cmd, pol.hand_cmd, budget_s=budget)
        for o in opts:
            n_opt += 1
            pts = [o.det.top[1]]
            if o.route == "direct":
                pts.append(pol.planner.bin_xy(o.bin)[1])
            else:
                pts.append(O.RELAY_POINTS[o.plan.relay][1])
            if not all(arm_allowed(o.arm, y) for y in pts):
                bad += 1
                print(f"layout {i}: {o.obj} {o.arm} {o.grasp} {o.route} breaks the side rule (y {pts})")
            if o.shape == "tipped" and o.grasp.startswith("face"):
                n_ridge += 1
        tip = [o for o in opts if o.shape == "tipped"]
        print(f"layout {i}: {len(dets)} objects, {len(opts)} options; lying object: "
              + (", ".join(f"{o.arm}/{o.grasp}/{o.route}" for o in tip) or "no plan"), flush=True)
    print(f"\n{n_opt} options, {bad} break the side rule; ridge-aligned plans for lying objects: {n_ridge} "
          f"(over {n_tip} layouts)")
    print("ridge yaw on a synthetic 45 x 7 mm strip at 30 deg:", end=" ")
    a = np.radians(30.0)
    s = np.linspace(-0.0225, 0.0225, 40)
    t = np.linspace(-0.0035, 0.0035, 5)
    pts = np.array([[u * np.cos(a) - v * np.sin(a), u * np.sin(a) + v * np.cos(a)] for u in s for v in t])
    shape, yaw, _, f = classify_top_v15(pts)
    err = abs((yaw - a + np.pi / 2) % np.pi - np.pi / 2) if yaw is not None else None
    print(f"shape {shape}, yaw {np.degrees(yaw) if yaw is not None else None}, ratio {f.get('ridge_ratio', 0):.1f}")
    if shape != "tipped" or err is None or err > np.radians(3):
        bad += 1
    return 0 if bad == 0 else 1


def main(argv=None):
    """aaltonomous.sim.evaluate with V15OraclePolicy (same pattern as upgrades.py)."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--sides", default="strict", choices=SIDES)
    ap.add_argument("--grasp-check", default="on", choices=["off", "log", "on"])
    ap.add_argument("--max-tries", type=int, default=4)
    ap.add_argument("--perception", default="camera", choices=["privileged", "camera"])
    ap.add_argument("--tip-check", default="off", choices=["off"] + sorted(TIP_MODELS))
    ap.add_argument("--dlog", default=None)
    ap.add_argument("--look-budget", type=float, default=3.0)
    ap.add_argument("--selftest", type=int, default=0)
    a, rest = ap.parse_known_args(argv)
    if a.selftest:
        return selftest(a.selftest)

    import aaltonomous.sim.evaluate as E

    out = rest[rest.index("--out") + 1] if "--out" in rest else "runs/eval"
    task = rest[rest.index("--task") + 1] if "--task" in rest else "sort_fixed"
    tag = f"v15_{a.sides}{'_cam' if a.perception == 'camera' else ''}"
    if "--team" not in rest:
        rest += ["--team", tag]
    rest = ["--policy", "oracle"] + list(rest)
    dlog = a.dlog or os.path.join(out, f"decisions_{tag}_{task}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    os.makedirs(os.path.dirname(dlog) or ".", exist_ok=True)
    print(f"[v1.5] sides={a.sides} perception={a.perception} dlog={dlog}", flush=True)

    def factory(client, **kw):
        return V15OraclePolicy(client, sides=a.sides, grasp_check=a.grasp_check, max_tries=a.max_tries, dlog=dlog,
                               look_budget_s=a.look_budget, perception=a.perception, tip_check=a.tip_check, **kw)

    O.OraclePolicy = factory

    class SeededClient(E.LocalClient):
        def reset(self, task, instruction, seed):
            self.policy.episode_seed, self.policy.task = seed, task
            super().reset(task, instruction, seed)

    E.LocalClient = SeededClient
    return E.main(rest)


if __name__ == "__main__":
    sys.exit(main())
