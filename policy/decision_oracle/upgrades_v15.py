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

    def _plan_side_faces(self, det, side, bin_name, arm_q, hand_q, **kw):
        """A lying object: fingers along its ridge (across the two flat end faces), then the stock hints. Other
        shapes: Aalto's face-aligned grasp."""
        yaw = getattr(det, "yaw", None)
        if getattr(det, "shape", None) != "tipped" or yaw is None:
            return super()._plan_side_faces(det, side, bin_name, arm_q, hand_q, **kw)
        ref = np.radians(O.FINGER_REF_DEG[side])
        cands = []
        for k in range(2):
            a = yaw + k * np.pi
            da = abs((a - ref + np.pi) % (2 * np.pi) - np.pi)
            if da <= np.radians(TIP_MAX_DEV_DEG):
                cands.append((da, a))
        saved = (self.kin.hint, self.kin.w_hint)
        try:
            for _, a in sorted(cands):
                f = np.array([np.cos(a), np.sin(a), 0.0])
                self.kin.hint, self.kin.w_hint = f, O.FACE_HINT_WEIGHT
                p = self._plan_side(det, side, bin_name, arm_q, hand_q, **kw)
                if p.ok:
                    err = self._finger_err(p, side, f)
                    if err <= O.FACE_TOL_DEG:
                        p.reason = f"face-aligned ridge ({np.degrees(a):.0f} deg, err {err:.0f})"
                        return p
        finally:
            self.kin.hint, self.kin.w_hint = saved
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


# ---------------------------------------------------------------------------------------------------- chooser
class V15Chooser(MemoryChooser):
    """MemoryChooser; the stock claw on a lying object is a last resort too (0 of 9 held in e-019)."""
    name = "memory_v15"

    @staticmethod
    def _last_resort(o):
        return o.shape in ("triangle", "tipped") and _grasp_kind(o.grasp) == "stock"


# ---------------------------------------------------------------------------------------------------- policy
class V15OraclePolicy(UpgradedOraclePolicy):
    def __init__(self, client, sides="strict", chooser=None, **kw):
        """sides: "strict" (same-side arms) | "off" (Aalto's arm rule). Other arguments: UpgradedOraclePolicy."""
        if sides not in SIDES:
            raise ValueError(f"sides={sides!r}: use one of {SIDES}")
        self.sides = sides
        super().__init__(client, chooser=chooser or V15Chooser(), **kw)
        for pl in (self.planner, self.relay):
            pl.__class__ = SidedPlanner
            pl.sides = sides
        if self.cam is not None:
            self.cam = RidgeCamera(self.scene, self.cal, log=self.log)

    def _w(self, rec):
        if isinstance(rec.get("mapping"), dict):        # (colour, shape) keys: JSON keys must be strings
            rec = {**rec, "mapping": {(k if isinstance(k, str) else " ".join(k)): v for k, v in rec["mapping"].items()}}
        super()._w(rec)

    def _plan_relay(self, d, dets, arm, hand):
        """Aalto's relay (oracle.py) with the same-side rule: relay points nearest the centre line first, and points
        one of the two arms may not use are skipped without counting as a try."""
        if self.sides != "strict":
            return super()._plan_relay(d, dets, arm, hand)
        if self.relays.get(d.name, 0) >= O.MAX_RELAYS_PER_OBJECT:
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
                               look_budget_s=a.look_budget, perception=a.perception, **kw)

    O.OraclePolicy = factory

    class SeededClient(E.LocalClient):
        def reset(self, task, instruction, seed):
            self.policy.episode_seed, self.policy.task = seed, task
            super().reset(task, instruction, seed)

    E.LocalClient = SeededClient
    return E.main(rest)


if __name__ == "__main__":
    sys.exit(main())
