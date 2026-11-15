"""Task 3 (`insert_shapes`): each block through the hole of its own shape in the lid.

Scoring (Aalto's RULES_AND_SCORING.md): +3 through the matching hole; -1 if it ends on / jammed in the lid or dropped
beside it; 0 if it stays on the counter. So a block only goes to the lid with a plan we trust.

`configure()` (called by policies/oracle_v15.py before every reset) switches this on for task insert_shapes or the
rung-3 instruction, and restores the sorting planners for any other task. On top of the v1.5/v1.6 stack:
  * planner: Aalto's oracle planner with the lid's three holes as its "bins" (InsertPlanner). It picks the block (face
    grasp for the square and the triangle, as when sorting), carries it above its hole, lowers it until the block's
    bottom is LID_GAP above the lid, opens and lifts away. When one arm reaches the block but not its hole (the
    circle hole, for the right arm), Aalto's relay hands it to the other arm (relay points kept clear of the lid box).
  * wrist: between the grasp and the hole the hand turns so the block lines up with its hole. The square repeats
    every 90 deg and the triangle every 120 deg, so the turn is at most 45 / 60 deg. A plan whose wrist ends more than
    ALIGN_TOL_DEG off, or whose block centre misses the hole centre by more than DROP_TOL, is rejected. The square and
    the triangle need a face grasp (their yaw in the hand is then known); a lying triangle is left alone.
  * clearance: the hand stays above the lid box and the bins still on the table, instead of the sorting bins. A pick
    (or relay pickup) whose hand would come down on the lid box is refused (HAND_BODY: the 8 hand points the planner
    checks do not cover the palm's body).
  * park: both arms wait at PARK (hands out to the sides) instead of the sim home pose. At home the left hand hangs
    over the lid, right where the right hand has to go to reach the triangle hole (Modal run t3-v16-b, Sun 15 Nov),
    and the right hand hangs over the right half of the band, where the left arm picks cubes and cylinders (only it
    reaches the square and circle holes). Every plan starts and ends there; the first move of each episode goes there.
  * lid: the placement we asked Aalto for (docs/research/task3-lid-placement.md), refined from head depth at the first
    look of each episode (find_lid: the lid's top plane gives its centre, turn and height). Blocks inside or on the
    lid box are never detected as objects.

Env:
  LID_CENTER   "x,y" lid centre, pelvis frame, m (default "0.39,0.15": the requested placement)
  LID_YAW_DEG  lid turn about z from the requested orientation, deg (default 0)
  LID_LAYOUT   request | mirror (square and circle holes swapped) (default request)
  LID_TOP      lid top above the counter (m) until depth measures it (default 0.075)
  LID_REFINE   on | off: centre, turn and height from head depth (default on)
  LID_GAP      block bottom above the lid top at release, m (default 0.008)
  LID_BINS     bins still on the table besides the lid box, comma-separated (default "right")
  LID_PARK     on | off: both arms wait at PARK between moves (default on)
  LID_DWELL    s to hold the block still over the hole before letting go (default 0: open at once, as Aalto's planner)
  LID_GRASP_H  grasp point height as a fraction of the block's height, task 3 only (default 0.5 = Aalto's). Above
               0.5 the pinch sits above the block's centre of mass, so it hangs straight instead of tilting.
  LID_SHAPES   shapes that are put through the lid, comma-separated (default "cylinder"); the others stay on the
               counter (0 points instead of a likely -1). Modal t3-v16-e (Sun 15 Nov, 3 trials, both fixes above):
               cylinders 2/2 inserted, triangles 0/5 (2 forced), cubes 0/2 (1 forced): +2, +2, -1 with all shapes,
               +3, +3, 0 with cylinders only. "cube,cylinder,triangle" tries all three.
"""
from __future__ import annotations

import copy
import os
import types
from dataclasses import dataclass, field

import numpy as np

from aaltonomous.baselines.classical.perception import Detection
from aaltonomous.baselines.classical.planner import Plan
from aaltonomous.interface.tasks import INSERT_INSTRUCTION
from aaltonomous.scene.scene import Scene
from aaltonomous.sim import oracle as O

SHAPES = ("cube", "cylinder", "triangle")
HOLE = {s: f"hole_{s}" for s in SHAPES}               # shape -> the planner's "bin" name
HOLE_SHAPE = {v: k for k, v in HOLE.items()}
MAPPING = dict(HOLE)                                    # scene.resolve_bin by shape; colour does not matter
# Hole centres relative to the lid centre, pelvis frame (m), lid placed as requested: triangle nearest the robot (apex
# towards it), square and circle in the back row, square on the robot's right. From lid_shape_holes_200mm.stl
# (Aalto): square (-48, -35) mm, circle (+48, -35), triangle centroid (0, +39.2) with its apex at +v; lid frame (u, v)
# -> pelvis (-v, u).
LAYOUTS = {
    "request": {"cube": (0.035, -0.048), "cylinder": (0.035, 0.048), "triangle": (-0.0392, 0.0)},
    "mirror": {"cube": (0.035, 0.048), "cylinder": (0.035, -0.048), "triangle": (-0.0392, 0.0)},
}
# Hole yaw in the camera's convention (camera.classify_top): cube faces at yaw + k 90 deg, triangle corners at
# yaw + 90 + k 120 deg. The triangle hole's apex points at the robot (180 deg) -> yaw 90 deg.
HOLE_YAW = {"cube": 0.0, "cylinder": 0.0, "triangle": np.pi / 2}
PERIOD = {"cube": np.pi / 2, "triangle": 2 * np.pi / 3}
LID_SIZE, BOX_SIZE = 0.20, 0.21          # lid plate, box under it (the bins are 21 cm)
ALIGN_TOL_DEG = 8.0                      # wrist at the hole vs the turn that lines the block up
DROP_TOL = 0.004                         # m: block centre at release vs the hole centre (holes: 7.5 mm per side)
BOX_MARGIN = 0.005                       # m around the lid box where the hand must stay above the lid
FOUND_MAX_SHIFT = 0.08                   # m: a lid found further than this from the expected place is not believed
ALIGN_PHASES = ("carry", "carry_mid", "lower", "retreat")
# Relay points (pelvis xy) for task 3: on the centre line and right of it, in front of the lid box. Points where the
# picking hand would come down on the box are skipped per arm (_pick_clear).
RELAY_POINTS = [(0.26, 0.0), (0.23, 0.0), (0.26, -0.04), (0.23, -0.04), (0.29, -0.02), (0.23, 0.04)]
# Park poses (7 arm joints) for task 3. At the sim home pose (layout.ARM_HOME) the left hand hangs 11 cm above the
# requested lid, over the triangle hole: the right hand, lowering a block into that hole, reaches into the same space.
# Parked, the left hand points are at pelvis x 0.20-0.36, y +0.32..+0.42, z 0.17-0.24 (FK, Aalto's ArmKinematics):
# beside the box, which ends at y +0.255. The right arm's pose mirrors it (y -0.42..-0.32, short of the right bin).
PARK = {"left": (0.0, 0.5, 0.6, 0.0, 0.0, 0.0, 0.0), "right": (0.0, -0.5, -0.6, 0.0, 0.0, 0.0, 0.0)}
# Footprint of a hand picking from the counter, around its grasp point (m, pelvis axes; "own" = towards the hand's
# own side, +y for the left hand). FK of a top-down grasp puts the hand points at x -0.099..+0.057, y -0.014..+0.044
# (left) from the grasp point; the palm, wrist and fingers are thicker than those points.
HAND_BODY = {"back": 0.11, "front": 0.07, "own": 0.06, "other": 0.03}
PICK_MARGIN = 0.01                       # m around the lid box for HAND_BODY


def _env_xy(name, default):
    try:
        x, y = (float(v) for v in os.environ.get(name, default).split(","))
        return np.array([x, y])
    except ValueError:
        x, y = (float(v) for v in default.split(","))
        return np.array([x, y])


def _wrap(a, period=2 * np.pi):
    """a wrapped into [-period/2, period/2)."""
    return (a + period / 2) % period - period / 2


def settings():
    return {
        "center": _env_xy("LID_CENTER", "0.39,0.15"),
        "yaw": np.radians(float(os.environ.get("LID_YAW_DEG", "0") or 0)),
        "layout": os.environ.get("LID_LAYOUT", "request") if os.environ.get("LID_LAYOUT", "request") in LAYOUTS
        else "request",
        "top": float(os.environ.get("LID_TOP", "0.075") or 0.075),
        "refine": os.environ.get("LID_REFINE", "on") != "off",
        "gap": float(os.environ.get("LID_GAP", "0.008") or 0.008),
        "bins": [b.strip() for b in os.environ.get("LID_BINS", "right").split(",") if b.strip()],
        "park": os.environ.get("LID_PARK", "on") != "off",
        "shapes": [v.strip() for v in os.environ.get("LID_SHAPES", "cylinder").split(",") if v.strip() in SHAPES],
        "grasp_h": float(os.environ.get("LID_GRASP_H", "0.5") or 0.5),
        "dwell": float(os.environ.get("LID_DWELL", "0") or 0),
    }


@dataclass
class Lid:
    center: np.ndarray                   # pelvis xy (m)
    yaw: float = 0.0                     # turn about z from the requested orientation (rad)
    top: float = 0.075                   # lid top above the counter (m)
    layout: str = "request"
    source: str = "request"
    info: dict = field(default_factory=dict)

    def rot(self):
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        return np.array([[c, -s], [s, c]])

    def hole_xy(self, shape):
        return np.asarray(self.center, float) + self.rot() @ np.asarray(LAYOUTS[self.layout][shape], float)

    def hole_yaw(self, shape):
        return HOLE_YAW[shape] + self.yaw

    def local(self, xy):
        """Pelvis xy (2,) or (n, 2) -> lid frame (box axes)."""
        return (np.asarray(xy, float) - np.asarray(self.center, float)) @ self.rot()

    def covers(self, xy, margin=0.0):
        return bool(np.all(np.abs(self.local(xy)) <= BOX_SIZE / 2 + margin))

    def describe(self):
        holes = ", ".join(f"{s} ({self.hole_xy(s)[0]:.3f}, {self.hole_xy(s)[1]:+.3f})" for s in SHAPES)
        return (f"lid [{self.source}] centre ({self.center[0]:.3f}, {self.center[1]:+.3f}) turn "
                f"{np.degrees(self.yaw):+.1f} deg, top {100 * self.top:.1f} cm; holes {holes}")


def requested_lid():
    s = settings()
    return Lid(s["center"], s["yaw"], s["top"], s["layout"])


# ---------------------------------------------------------------------------------------------------- lid from depth
def find_lid(P, zc, lid, max_shift=FOUND_MAX_SHIFT):
    """The lid's top plane in head-depth points P (n, 3), pelvis frame -> (Lid or None, why).
    Takes the most common height 3-14 cm above the counter near the expected lid, the largest connected patch at that
    height (5 mm grid), and its minimum-area rectangle: centre, turn (nearest the expected one, modulo 90 deg) and
    height. Rejected unless the patch is lid-sized and near the expected place."""
    import cv2
    P = np.asarray(P, np.float64).reshape(-1, 3)
    P = P[np.isfinite(P).all(1)]
    reach = LID_SIZE / 2 + max_shift + 0.03
    rel = lid.local(P[:, :2])
    h = P[:, 2] - zc
    sel = (np.abs(rel) < reach).all(1) & (h > 0.03) & (h < 0.14)
    if sel.sum() < 400:
        return None, f"{int(sel.sum())} depth points near the lid"
    hist, edges = np.histogram(h[sel], bins=np.arange(0.03, 0.14 + 1e-9, 0.002))
    k = int(hist.argmax())
    top = 0.5 * (edges[k] + edges[k + 1])
    on = sel & (np.abs(h - top) < 0.004)
    xy, hz = P[on, :2], h[on]
    if len(xy) < 300:
        return None, f"top plane at {100 * top:.1f} cm has {len(xy)} points"
    res = 0.005
    lo = xy.min(0)
    ij = np.floor((xy - lo) / res).astype(int)
    img = np.zeros(tuple(ij.max(0) + 1), np.uint8)
    img[ij[:, 0], ij[:, 1]] = 255
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(img, connectivity=8)
    if n < 2:
        return None, "no patch at the top height"
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = lab[ij[:, 0], ij[:, 1]] == big
    pts = xy[keep]
    (cx, cy), (w, l), ang = cv2.minAreaRect((pts * 1000.0).astype(np.float32))
    w, l = w / 1000.0, l / 1000.0
    c = np.array([cx, cy]) / 1000.0
    info = {"top_cm": round(100 * float(np.median(hz[keep])), 1), "size_cm": [round(100 * w, 1), round(100 * l, 1)],
            "shift_cm": [round(100 * float(v), 1) for v in c - lid.center], "points": int(len(pts))}
    if not (0.16 <= min(w, l) and max(w, l) <= 0.24):
        return None, f"top patch {100 * w:.1f} x {100 * l:.1f} cm is not the lid ({info})"
    if np.linalg.norm(c - lid.center) > max_shift:
        return None, f"lid-sized patch {100 * np.linalg.norm(c - lid.center):.1f} cm from the expected place ({info})"
    yaw = lid.yaw + _wrap(np.radians(ang) - lid.yaw, np.pi / 2)
    info["turn_deg"] = round(float(np.degrees(yaw)), 1)
    return Lid(c, float(yaw), float(np.median(hz[keep])), lid.layout, "depth", info), "ok"


# ---------------------------------------------------------------------------------------------------- planners
def _points_scene(base, points, wall):
    """Copy of `base` whose bins are the given pelvis points (name -> (x, y)) with walls `wall` m high."""
    cfg = copy.deepcopy(base.cfg)
    b = cfg["bins"]
    b["wall_height"] = float(wall)
    b["centers"] = {}
    for name, (x, y) in points.items():
        m = base.pelvis_to_mat([float(x), float(y), 0.0])
        b["centers"][name] = [float(m[0]), float(m[1])]
    return Scene(cfg)


def _hole_scene(base, lid):
    return _points_scene(base, {HOLE[s]: lid.hole_xy(s) for s in SHAPES}, lid.top)


def _camera_scene(base, lid, real_bins):
    """The table as the camera should model it: the bins still there plus the lid box (for the pose fit's wall outlines
    and the 'not inside a bin' rule)."""
    cfg = copy.deepcopy(base.cfg)
    b = cfg["bins"]
    b["centers"] = {n: list(base.cfg["bins"]["centers"][n]) for n in real_bins}
    m = base.pelvis_to_mat([float(lid.center[0]), float(lid.center[1]), 0.0])
    b["centers"]["lid"] = [float(m[0]), float(m[1])]
    return Scene(cfg)


class _LidAware:
    """bin_clearance against the lid box and the bins still on the table (not the planner's own 'bins')."""

    def _lid_setup(self, base, lid, real_bins):
        self.base, self.lid, self.real_bins = base, lid, list(real_bins)

    def set_lid(self, lid):
        self.lid = lid

    def _pick_clear(self, side, xy):
        """False if `side`'s hand, picking at pelvis xy from the counter, would come down on the lid box."""
        x, y = float(xy[0]), float(xy[1])
        hb = HAND_BODY
        y0, y1 = (y - hb["other"], y + hb["own"]) if side == "left" else (y - hb["own"], y + hb["other"])
        corners = np.array([[x - hb["back"], y0], [x - hb["back"], y1], [x + hb["front"], y0], [x + hb["front"], y1]])
        loc = self.lid.local(corners)                   # box axes; the rectangle's box-aligned hull (lid turns are small)
        h = BOX_SIZE / 2 + PICK_MARGIN
        return bool(loc[:, 0].max() < -h or loc[:, 0].min() > h or loc[:, 1].max() < -h or loc[:, 1].min() > h)

    def _pick_refused(self, det, side):
        if self._pick_clear(side, det.top[:2]):
            return None
        return Plan(False, side=side, color=det.color, reason=f"insert: the {side} hand would come down on the lid box")

    def bin_clearance(self, side, arm_q, hand_q, margin=None):
        m = BOX_MARGIN if margin is None else margin
        pts = self.kin.hand_points(side, arm_q, hand_q)
        zc = self.base.counter_z
        out = np.inf
        over = np.all(np.abs(self.lid.local(pts[:, :2])) <= BOX_SIZE / 2 + m, axis=1)
        if over.any():
            out = min(out, float((pts[over, 2] - (zc + self.lid.top)).min()))
        if self.real_bins:
            b = self.base.cfg["bins"]
            pm = self.base.pelvis_to_mat(pts)
            half = np.asarray(b["outer_size"], float) / 2 + m
            rim = zc + float(b["wall_height"])
            for name in self.real_bins:
                ov = np.all(np.abs(pm[:, :2] - np.asarray(b["centers"][name], float)) <= half, axis=1)
                if ov.any():
                    out = min(out, float((pts[ov, 2] - rim).min()))
        return out


class InsertPlanner(_LidAware, O._OraclePlanner):
    """Aalto's oracle planner whose 'bins' are the lid's holes; the wrist turns between grasp and hole."""

    def __init__(self, cfg, base, lid, real_bins, post, home, kin, safety, spec):
        self._lid_setup(base, lid, real_bins)
        super().__init__(cfg, _hole_scene(base, lid), post, home, kin, safety, spec, mapping=dict(MAPPING))
        self.drop_offsets = {}
        self._align, self._shift = None, np.zeros(2)

    def set_lid(self, lid):
        self.lid = lid
        self.scene = _hole_scene(self.base, lid)
        self.__dict__.pop("_reach", None)          # _OraclePlanner._reaches_bin cache

    # -------------------------------------------------------------- targets
    def bin_xy(self, name):
        s = HOLE_SHAPE.get(name)
        return self.lid.hole_xy(s) if s else super().bin_xy(name)

    def drop_xy(self, name):
        s = HOLE_SHAPE.get(name)
        return self.lid.hole_xy(s) + self._shift if s else super().drop_xy(name)

    # -------------------------------------------------------------- wrist turn for carry / lower / retreat
    def _aligned(self, name, fn):
        if self._align is None or name not in ALIGN_PHASES:
            return fn()
        saved = (self.kin.hint, self.kin.w_hint)
        self.kin.hint, self.kin.w_hint = self._align, O.FACE_HINT_WEIGHT
        try:
            return fn()
        finally:
            self.kin.hint, self.kin.w_hint = saved

    def _ik(self, side, p, seed, name, plan):
        return self._aligned(name, lambda: super(InsertPlanner, self)._ik(side, p, seed, name, plan))

    def _cartesian(self, side, p0, p1, q0, name, plan):
        return self._aligned(name, lambda: super(InsertPlanner, self)._cartesian(side, p0, p1, q0, name, plan))

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, place_xy=None):
        refused = self._pick_refused(det, side)
        if refused is not None:
            return refused
        shape = HOLE_SHAPE.get(bin_name)
        if shape is None or place_xy is not None:
            return super()._plan_side(det, side, bin_name, arm_q, hand_q, place_xy=place_xy)
        if shape not in settings()["shapes"]:              # left on the counter (0) rather than risk -1 on the lid
            return Plan(False, side=side, color=det.color, reason=f"insert: {shape} not attempted (LID_SHAPES)")
        hint = np.asarray(self.kin.hint, float)
        a = float(np.arctan2(hint[1], hint[0]))          # finger direction at the grasp (the face the plan uses)
        P = PERIOD.get(shape)
        if P is None:
            cands = [None]                               # the circle hole: any wrist turn fits
        else:
            yaw = getattr(det, "yaw", None)
            if yaw is None or self.kin.w_hint < O.FACE_HINT_WEIGHT - 1e-6:
                return Plan(False, side=side, color=det.color, reason=f"insert: the {shape} needs a face grasp")
            base = a + _wrap(self.lid.hole_yaw(shape) - yaw, P)
            cands = sorted((base, base + P, base - P), key=lambda x: abs(x - a))
        last = None
        for a2 in cands:
            shift = np.zeros(2)
            if shape == "triangle":                      # the grasp point is off the centroid along the fingers
                shift = O._tri_shift(a - (det.yaw + np.pi / 2)) * np.array([np.cos(a2), np.sin(a2)])
            self._shift = shift
            self._align = None if a2 is None else np.array([np.cos(a2), np.sin(a2), 0.0])
            try:
                p = super()._plan_side(det, side, bin_name, arm_q, hand_q)
                target = self.drop_xy(bin_name)
            finally:
                self._align, self._shift = None, np.zeros(2)
            if p.ok:
                err, derr = self._at_hole(p, side, a2, P, target)
                p.insert = {"shape": shape, "hole": [round(float(v), 4) for v in target - shift],
                            "turn_deg": None if a2 is None else round(float(np.degrees(_wrap(a2 - a))), 1),
                            "wrist_err_deg": round(err, 1), "drop_err_mm": round(1000 * derr, 1)}
                if err > ALIGN_TOL_DEG:
                    p.ok, p.reason = False, f"wrist {err:.0f} deg off the {shape} hole"
                elif derr > DROP_TOL:
                    p.ok, p.reason = False, f"block centre {1000 * derr:.0f} mm off the {shape} hole"
            if p.ok:
                return _add_dwell(p, settings()["dwell"], self.dt)
            last = p
        return last

    def _at_hole(self, plan, side, a2, P, target):
        """(wrist error deg, grasp point error m) at the release pose (end of the carry + lower phase)."""
        e = next(e for name, s, e in plan.phases if name == "carry")
        q = plan.arm[e - 1]
        g = self.kin.grasp_pose(side, q)[0]
        derr = float(np.linalg.norm(np.asarray(g[:2]) - target))
        if a2 is None:
            return 0.0, derr
        self.kin._fk(q)
        x = self.kin.data.oMf[self.kin.palm[side]].rotation[:, 0]
        ach = float(np.arctan2(x[1], x[0]))
        return float(np.degrees(abs(_wrap(ach - a2, P)))), derr


def _add_dwell(plan, dwell_s, dt):
    """Hold the release pose for dwell_s before the hand opens (Aalto's planner opens the moment the lowering ends,
    so a block still swinging in the pinch is let go mid-swing). A new phase "settle" sits between carry and open."""
    n = int(round(float(dwell_s) / dt))
    starts = {name: s for name, s, e in plan.phases}
    if n <= 0 or "open" not in starts or starts["open"] == 0:
        return plan
    k = starts["open"]
    plan.arm = np.vstack([plan.arm[:k], np.repeat(plan.arm[k - 1][None], n, 0), plan.arm[k:]])
    plan.hand = np.vstack([plan.hand[:k], np.repeat(plan.hand[k - 1][None], n, 0), plan.hand[k:]])
    phases = []
    for name, s, e in plan.phases:
        if name == "open":
            phases.append(("settle", k, k + n))
        phases.append((name, s + n, e + n) if s >= k else (name, s, e))
    plan.phases = phases
    return plan


class RelayPlanner(_LidAware, O._OraclePlanner):
    """Aalto's relay planner (blocks put down at RELAY_POINTS) that keeps the hand above the lid box."""

    def __init__(self, cfg, base, lid, real_bins, post, home, kin, safety, spec):
        self._lid_setup(base, lid, real_bins)
        super().__init__(cfg, _points_scene(base, {f"relay{i}": xy for i, xy in enumerate(RELAY_POINTS)}, 0.0),
                         post, home, kin, safety, spec)
        self.drop_offsets = {}

    def _plan_side(self, det, side, bin_name, arm_q, hand_q, place_xy=None):
        return self._pick_refused(det, side) or super()._plan_side(det, side, bin_name, arm_q, hand_q,
                                                                    place_xy=place_xy)


def _plan_relay(pol, d, dets, arm, hand):
    """Aalto's OraclePolicy._plan_relay over RELAY_POINTS, with the second leg's stand-in block keeping the block's
    shape and yaw (a square or triangle is only inserted with a face grasp)."""
    if pol.relays.get(d.name, 0) >= O.MAX_RELAYS_PER_OBJECT:
        return None
    others = [o.top[:2] for o in dets if o.name != d.name]
    tried = 0
    for i, xy in enumerate(RELAY_POINTS):
        if tried >= O.MAX_RELAY_POINTS_TRIED:
            break
        xy = np.asarray(xy, float)
        if np.linalg.norm(xy - d.top[:2]) < 0.04 or any(np.linalg.norm(xy - o) < O.RELAY_CLEAR for o in others):
            continue
        fake = Detection(d.color, np.r_[xy, d.top[2]], 1000, 1000, "relay", getattr(d, "yaw", None))
        fake.shape = getattr(d, "shape", None)
        tried += 1
        p2 = pol.planner.plan(fake, pol.home, pol.post["open"], bin_name=d.bin, relocate=False)
        if not p2.ok:
            continue
        p1 = pol.relay.plan(d, arm, hand, bin_name=f"relay{i}", relocate=False)
        if p1.ok:
            p1.target_bin = f"relay -> {d.bin}"
            p1.obj, p1.obj_xy, p1.relay = d.name, d.top[:2].copy(), i
            pol.log(f"[insert] relay {d.name} via ({xy[0]:.2f},{xy[1]:+.2f}): {p1.side} then {p2.side}")
            return p1
    return None


# ---------------------------------------------------------------------------------------------------- camera
class _InsertCamera:
    """Wraps the policy's perception for task 3: the lid from depth at the first look of the episode, and no
    detections inside or on the lid box."""

    def __init__(self, pol, inner):
        self.pol, self.inner = pol, inner

    def detect(self, rgb=None, depth=None, debug=False):
        out = self.inner.detect(rgb, depth, debug)
        dets, rej = out if debug else (out, None)
        pol = self.pol
        st = pol._insert
        if not st["refined"]:
            st["refined"] = True
            try:
                refine_lid(pol)
            except Exception as e:                    # the requested placement stays
                pol.log(f"[insert] lid from depth failed: {e!r}")
        lid = st["lid"]
        keep = [d for d in dets if not lid.covers(d.top[:2], 0.03)]
        if len(keep) != len(dets):
            pol.log(f"[insert] ignored {len(dets) - len(keep)} detection(s) on or in the lid box")
        if pol.cam is not None:
            pol.cam.last = keep
        return (keep, rej) if debug else keep

    def masks(self, rgb):
        return self.inner.masks(rgb)


def refine_lid(pol):
    """find_lid on the current head depth (camera mode); updates the planners and the camera's table model."""
    from .camera import CAM, _points
    cam, st = pol.cam, pol._insert
    if cam is None or cam._obs is None or cam._obs[1] is None:
        return
    depth = np.asarray(cam._obs[1])
    T = cam.cal.cams[CAM].T_pelvis_optical
    pts = _points(cam.cal, depth, step=2).reshape(-1, 3)
    d = depth[::2, ::2].reshape(-1)
    pts = pts[(d > 150) & (d < 2000)]
    P = pts @ T[:3, :3].T + T[:3, 3]
    found, why = find_lid(P, pol.scene.counter_z, st["lid"])
    if found is None:
        pol.log(f"[insert] lid not found in depth ({why}): {st['lid'].describe()}")
        pol._w({"type": "lid", "found": False, "why": why})
        return
    _set_lid(pol, found)
    pol.log(f"[insert] {found.describe()} {found.info}")
    pol._w({"type": "lid", "found": True, "center": found.center.tolist(), "yaw_deg": float(np.degrees(found.yaw)),
            "top": found.top, **found.info})


# ---------------------------------------------------------------------------------------------------- switch
def is_insert(task, instruction=None):
    """Task 3: Aalto's runner sends the task name with every reset; the instruction is the fallback (sorting
    instructions name bins, never holes, a lid or inserting)."""
    if task == "insert_shapes":
        return True
    if task in ("sort_fixed", "sort_language"):
        return False
    text = (instruction or "").strip().lower()
    return text == INSERT_INSTRUCTION.lower() or any(w in text for w in ("hole", " lid", "insert"))


def _set_lid(pol, lid):
    st = pol._insert
    st["lid"] = lid
    pol.planner.set_lid(lid)
    pol.relay.set_lid(lid)
    if pol.cam is not None:
        pol.cam.scene = _camera_scene(pol.scene, lid, st["bins"])


def _install(pol, s):
    base = pol.scene
    bins = [b for b in s["bins"] if b in base.cfg["bins"]["centers"]]
    st = {"planner": pol.planner, "relay": pol.relay, "relay_points": O.RELAY_POINTS,
          "perception": pol.perception, "cam_scene": getattr(pol.cam, "scene", None), "bins": bins,
          "lid": None, "refined": True, "home": pol.home, "park": None}
    lid = requested_lid()
    home = np.asarray(pol.home, float).copy()
    if s["park"]:
        for side in ("left", "right"):
            home[pol.kin.sl(side)] = PARK[side]
        st["park"] = home.tolist()
    pol.home = home                                      # the policy's first move of each episode goes here
    icfg = copy.deepcopy(pol.cfg)
    icfg["grasp"]["drop_inset"] = None                   # release over the hole centre
    icfg["grasp"]["drop_above_rim"] = s["gap"]           # block bottom this far above the lid
    icfg["grasp"]["height_frac"] = s["grasp_h"]          # grasp point height on the block (Aalto default 0.5)
    rcfg = copy.deepcopy(pol.cfg)
    rcfg["grasp"]["drop_above_rim"] = 0.012              # as Aalto's relay
    pol._insert = st
    pol.planner = InsertPlanner(icfg, base, lid, bins, pol.post, home, pol.kin, pol.safety, pol.spec)
    pol.relay = RelayPlanner(rcfg, base, lid, bins, pol.post, home, pol.kin, pol.safety, pol.spec)
    O.RELAY_POINTS = list(RELAY_POINTS)                  # read by the policies' _plan_relay at call time
    pol._plan_relay = types.MethodType(_plan_relay, pol)
    if pol.cam is not None:
        pol.perception = _InsertCamera(pol, st["perception"])
    return st


def _restore(pol):
    st = pol._insert
    pol.planner, pol.relay, pol.perception = st["planner"], st["relay"], st["perception"]
    pol.home = st["home"]
    O.RELAY_POINTS = st["relay_points"]
    pol.__dict__.pop("_plan_relay", None)
    if pol.cam is not None and st["cam_scene"] is not None:
        pol.cam.scene = st["cam_scene"]
    pol._insert = None


def configure(pol, task, info):
    """Before pol.reset(info): task 3 on (lid holes as targets) or off (sorting as before). Returns the info to reset
    with (task 3: mapping shape -> hole)."""
    info = dict(info or {})
    on = is_insert(task, info.get("instruction"))
    if not on:
        if getattr(pol, "_insert", None) is not None:
            _restore(pol)
        return info
    s = settings()
    if getattr(pol, "_insert", None) is None:
        _install(pol, s)
    _set_lid(pol, requested_lid())
    pol._insert["refined"] = not (s["refine"] and pol.cam is not None)
    info["mapping"] = dict(MAPPING)
    pol.log(f"[insert] task 3: {pol._insert['lid'].describe()}; release {100 * s['gap']:.1f} cm above the lid; "
            + ("arms parked out to the sides between moves" if pol._insert["park"] else "arms wait at home")
            + f"; shapes tried: {','.join(s['shapes']) or 'none'}")
    return info


def after_reset(pol):
    """After pol.reset(): v1.6's Decision instruction call (a colour -> bin mapping) does not apply to task 3."""
    if getattr(pol, "_insert", None) is not None and hasattr(pol, "_instr_pending"):
        pol._instr_pending = False
