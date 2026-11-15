"""Shape putting (rung 3) in the MuJoCo venue scene: Aalto's printed lid on the middle box, boxes 7 cm closer to the
robot, one block per case put through its hole, filmed.

Per case:
1. the scene: venue_measured.yaml with the boxes moved closer (--closer) and 2.7 cm apart (as measured on Aalto's real
   depth), and the lid from lid_shape_holes_200mm.stl lying lip down on the middle box. Its plate collides as thin
   strips around the three holes (MuJoCo would fill the holes of a mesh), the STL is drawn on top;
2. perception, from the head camera only: v1.6's camera fit + object detection (camera.py), the boxes and the lid
   with its holes (boxes_v16.py). The policy's scene is Aalto's scene.yaml, as in the submission image;
3. the move (InsertPlanner below, on Aalto's oracle planner): face-aligned grasp as the oracle does it, lift, carry
   to above the hole while the wrist turns the block to the hole's angle, lower until the block's underside is
   --gap above the plate, open the hand, retreat, home;
4. played open-loop at 30 Hz (no policy server); the plan is checked against Aalto's safety filter first (0 clips);
5. scored like Aalto's classify_insert: inserted (in the box, entered through its own hole), wrong_hole, forced
   (resting on or jammed in the lid), dropped (beside the lid), counter.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python sim/mujoco/insert_demo.py \
        --stl artifacts/real_frames/lid/lid_shape_holes_200mm.stl --video --tag insert-demo

Results and videos (head camera | close-up of the lid) go to artifacts/eval/mujoco/<tag>/.
Needs the MuJoCo venue scene (sim/mujoco/build.py, backend.py, venue_measured.yaml, get_assets.sh) and, for
--calib hands / lean, policy/decision_oracle/handeye.py with the V16_CALIB camera.py; on Sun 15 Nov ~03:30 those were
in Emīls's working tree, not yet on GitHub.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]
import build as B                                                       # noqa: E402

# the lid's holes in the STL's own frame (m, lid centre = 0), eval/analysis/real_depth/stl_holes.py
STL_HOLES = {"cube": (-0.048, -0.035), "cylinder": (0.048, -0.035), "triangle": (0.0, 0.0393)}
PLATE = 0.004
TRI_PHI = {"left": 75.0, "right": 45.0}     # finger direction vs the apex that holds in MuJoCo (eval/analysis/grasps)
# Where the block really sits in the closed hand, against the planner's grasp point (grasp.point_in_palm), in the LEFT
# palm frame (right: y mirrored). Measured here after the lift, 4 cases per shape, spread +-2 mm: the pinch holds the
# block 13 mm further back and 15 mm further towards the thumb side than the grasp point says. Fine for dropping into
# a 21 cm box; 7.5 mm of room in a hole is not enough without it.
# How far the block turns in the hand beyond the plan (deg, LEFT hand; right: the opposite sign), measured here from
# the grasp to the release with the camera's yaw within 0.2 deg: prisms -12 (spread 1), cubes -5 (spread 2).
IN_HAND_TURN = {"cube": -5.0, "triangle": -12.0}
IN_HAND = {"cube": (-0.013, -0.015, -0.002), "cylinder": (-0.012, -0.015, -0.003), "triangle": (-0.007, -0.013, -0.0015)}


# ------------------------------------------------------------------------------------------------ scene
def lid_cfg(closer, gap):
    cfg = B.load_cfg()
    cfg["bins"]["table_edge_to_bins"] = round(cfg["bins"]["table_edge_to_bins"] - closer, 4)
    cfg["bins"]["gap"] = gap
    return cfg


def lid_world(cfg, turn_deg):
    """Lid centre (world xy), plate underside z, and the map STL xy -> world xy (lip down: x mirrored, then turned)."""
    sc = B.Scene.load(str(B.scene_yaml(cfg)))
    c = sc.mat_to_pelvis(np.r_[sc.cfg["bins"]["centers"]["center"], 0.0])[:2]
    z0 = cfg["table"]["height"] + cfg["bins"]["wall_height"]
    a = np.radians(turn_deg)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ np.diag([-1.0, 1.0])
    return c, z0, (lambda q: c + np.asarray(q, float) @ R.T), a


def plate_strips(res=0.002, fine=0.0005):
    """The plate outside the holes as boxes (STL frame, m): strips `res` wide along y, merged runs along x."""
    import cv2
    from decision_oracle.boxes_v16 import real_lid
    n = int(round(0.2 / fine))
    img = np.zeros((n, n), np.uint8)                     # row = y, column = x, cell (0, 0) at (-0.1, -0.1)
    for k, _, poly in real_lid()["holes"]:
        q = poly * [-1.0, 1.0] + np.asarray(STL_HOLES[k])
        cv2.fillPoly(img, [np.round((q + 0.1) / fine * 16).astype(np.int32)], 1, shift=4)
    xs = np.arange(-0.1 + fine / 2, 0.1, fine)
    out = []
    for y in np.arange(-0.1 + res / 2, 0.1, res):
        solid = img[min(int((y + 0.1) / fine), n - 1)] == 0
        k = 0
        while k < len(xs):
            if not solid[k]:
                k += 1
                continue
            j = k
            while j + 1 < len(xs) and solid[j + 1]:
                j += 1
            out.append(((xs[k] + xs[j]) / 2, y, (j - k + 1) * fine / 2, res / 2))
            k = j + 1
    return out


def add_lid(spec, cfg, stl, turn_deg):
    c, z0, to_w, a = lid_world(cfg, turn_deg)
    wb = spec.worldbody
    for i, (x, y, hx, hy) in enumerate(plate_strips()):
        p = to_w([x, y])
        wb.add_geom(name=f"lid_strip{i}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[p[0], p[1], z0 + PLATE / 2],
                    size=[hx, hy, PLATE / 2], euler=[0, 0, a], rgba=[0.9, 0.9, 0.92, 0.0],
                    contype=B.ENV_CONTYPE, conaffinity=B.ENV_CONAFF, friction=[0.6, 0.005, 0.0001], group=3)
    spec.add_mesh(name="lid_stl", file=str(Path(stl).resolve()), scale=[0.001] * 3)
    # lip down: the STL's plate face (z 0..4 mm) on top, lip below; turned about z by a after mirroring x
    q = np.zeros(4)
    Rm = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]]) @ np.diag([-1.0, 1.0, -1.0])
    mujoco.mju_mat2Quat(q, Rm.flatten())
    lo, hi = stl_bounds(stl)
    off = np.r_[(lo[:2] + hi[:2]) / 2, lo[2]]
    pos = np.r_[c, z0 + PLATE] - Rm @ off
    wb.add_geom(name="lid_visual", type=mujoco.mjtGeom.mjGEOM_MESH, meshname="lid_stl", pos=list(pos), quat=list(q),
                rgba=[0.93, 0.93, 0.95, 1.0], contype=0, conaffinity=0)
    wb.add_camera(name="lidcam", pos=[c[0] - 0.30, c[1] - 0.42, z0 + 0.42],
                  xyaxes=[0.81, -0.58, 0, 0.36, 0.5, 0.79], fovy=40)
    return {k: to_w(v) for k, v in STL_HOLES.items()}, (c, z0, a)


def stl_bounds(path):
    import struct
    with open(path, "rb") as f:
        raw = f.read()
    n = struct.unpack("<I", raw[80:84])[0]
    v = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
    v = v["v"].reshape(-1, 3).astype(float) * 0.001
    return v.min(0), v.max(0)


# ------------------------------------------------------------------------------------------------ move
def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


class InsertPlanner:
    """Aalto's oracle planner (face-aligned grasps, IK, timing, safety dry-run) with the drop replaced by
    "carry over the hole, turn the block to the hole's angle, lower, let go"."""

    def __init__(self, pl, gap=0.012, in_hand=None):
        self.pl, self.gap = pl, gap
        self.in_hand = IN_HAND if in_hand is None else in_hand
        self.carry_speed = {}                                  # shape -> fraction of the arm speed while carrying
        self.turn = dict(IN_HAND_TURN)

    def finger_dirs(self, det, side):
        """Candidate finger directions (rad) at the grasp, nearest the arm's natural direction first."""
        from aaltonomous.sim import oracle as O
        ref = np.radians(O.FINGER_REF_DEG[side])
        if det.shape == "cube":
            c = [det.yaw + k * np.pi / 2 for k in range(4)]
        elif det.shape == "triangle":
            c = [det.yaw + np.pi / 2 + np.radians(TRI_PHI[side]) + 2 * np.pi * k / 3 for k in range(3)]
        else:
            c = [ref + np.radians(d) for d in (0, -25, 25)]
        c = [wrap(x) for x in c if abs(wrap(x - ref)) <= np.radians(O.FACE_MAX_DEV_DEG)]
        return sorted(c, key=lambda x: abs(wrap(x - ref)))

    def drop_dirs(self, det, fg, hole_axis, side="left"):
        """Finger directions at the drop that put the block square to its hole, smallest wrist turn first."""
        hole_axis = hole_axis - np.radians(self.turn.get(det.shape, 0.0)) * (1 if side == "left" else -1)
        if det.shape == "cube":
            c = [hole_axis + k * np.pi / 2 for k in range(4)]
        elif det.shape == "triangle":           # apex at fg - phi now; it must point at one of the hole's tips
            phi = wrap(fg - (det.yaw + np.pi / 2))
            c = [hole_axis + 2 * np.pi * k / 3 + phi for k in range(3)]
        else:
            return [fg]
        return sorted([wrap(x) for x in c], key=lambda x: abs(wrap(x - fg)))

    def plan(self, det, hole_xy, hole_axis, plate_top, arm_q, hand_q, sides=("left", "right")):
        """Tries (arm, grasp direction, drop direction) with the smallest wrist turn first: a block held while the
        wrist turns 50 deg or more fell out in MuJoCo; the object's own side breaks ties."""
        from aaltonomous.sim import oracle as O
        cands = []
        for side in sides:
            ref = np.radians(O.FINGER_REF_DEG[side])
            own = 0.0 if (det.top[1] > 0) == (side == "left") else 0.35
            for fg in self.finger_dirs(det, side):
                for fd in self.drop_dirs(det, fg, hole_axis, side)[:2]:
                    cands.append((abs(wrap(fd - fg)) + 0.3 * abs(wrap(fg - ref)) + own, side, fg, fd))
        last = None
        for _, side, fg, fd in sorted(cands)[:8]:
            p = self._plan(det, side, fg, fd, hole_xy, plate_top, arm_q, hand_q)
            if p.ok:
                return p
            last = p
        return last

    def _solve_path(self, side, p0, p1, f0, f1, q0, name, plan, w):
        """Straight line p0 -> p1 while the finger direction turns f0 -> f1; IK seeded step to step."""
        pl, kin = self.pl, self.pl.kin
        turn = abs(wrap(f1 - f0))
        n = max(1, int(np.ceil(max(np.linalg.norm(np.subtract(p1, p0)) / pl.cfg["motion"]["cart_step"],
                                   turn / np.radians(5.0)))))
        qs, q = [], q0
        jmax = float(pl.cfg["motion"].get("max_joint_step", 0.4))
        for k in range(1, n + 1):
            t = k / n
            a = f0 + wrap(f1 - f0) * t
            kin.hint, kin.w_hint = np.array([np.cos(a), np.sin(a), 0.0]), w
            qn, ok, err, tilt = kin.solve(side, np.asarray(p0) + (np.asarray(p1) - p0) * t, q, top_down=True, restarts=False)
            if not ok or np.abs(qn - q).max() > jmax:
                qn, ok, err, tilt = kin.solve(side, np.asarray(p0) + (np.asarray(p1) - p0) * t, q, top_down=True)
                if not ok or np.abs(qn - q).max() > jmax:
                    plan.reason = f"IK {'jump' if ok else 'failed'} on {name} at {t:.2f}"
                    return None
            qs.append(qn)
            q = qn
        return qs

    def _plan(self, det, side, fg, fd, hole_xy, plate_top, arm_q, hand_q):
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        from aaltonomous.baselines.classical.planner import Plan, ramp, time_scale
        from aaltonomous.sim import oracle as O
        pl = self.pl
        kin, g, mo, post = pl.kin, pl.cfg["grasp"], pl.cfg["motion"], pl.post
        zc, H = pl.scene.counter_z, pl.height
        plan = Plan(False, side=side, color=det.color, target_bin="center")
        sl = ArmKinematics.sl(side)
        hand_pre = hand_q.copy(); hand_pre[sl] = post["preshape"][sl]
        hand_cls = hand_q.copy(); hand_cls[sl] = post["closed"][sl]
        hand_open = hand_q.copy(); hand_open[sl] = post["open"][sl]
        hand_rel = hand_q.copy(); hand_rel[sl] = post[g.get("release_posture", "preshape")][sl]
        saved = (kin.hint, kin.w_hint)
        w = O.FACE_HINT_WEIGHT
        try:
            fgv = np.array([np.cos(fg), np.sin(fg), 0.0])
            fdv = np.array([np.cos(fd), np.sin(fd), 0.0])
            shift_g = np.zeros(3)
            if det.shape == "triangle":         # pinch midpoint along the fingers is not the centroid
                shift_g = O._tri_shift(fg - (det.yaw + np.pi / 2)) * fgv
            xy = (det.top + shift_g)[:2]
            kin.hint, kin.w_hint = fgv, w
            z = zc + g["height_frac"] * H
            for _ in range(4):
                qg, ok = pl._ik(side, np.r_[xy, z], arm_q, "grasp", plan)
                if not ok:
                    plan.reason = f"IK grasp {side}"
                    return plan
                c = pl.clearance(side, qg, hand_pre, fingers_only=True)
                if c >= g["fingertip_clearance"] - 1e-3:
                    break
                z += g["fingertip_clearance"] - c
            if pl._finger_err_q(side, qg, fgv) > O.FACE_TOL_DEG:
                plan.reason = "finger direction at the grasp off by more than 12 deg"
                return plan
            hz = z - zc                                       # grasp point above the block's underside
            wall = float(pl.scene.cfg["bins"]["wall_height"])
            z_carry = zc + max(g["carry_height"], wall + H + 0.05)
            z_drop = plate_top + self.gap + hz
            P = {"pregrasp": np.r_[xy, max(z + g["approach_height"], z_carry)], "grasp": np.r_[xy, z],
                 "lift": np.r_[xy, z_carry]}
            q_pre, ok = pl._ik(side, P["pregrasp"], qg, "pregrasp", plan)
            if not ok:
                plan.reason = f"IK pregrasp {side}"
                return plan
            down = pl._cartesian(side, P["pregrasp"], P["grasp"], q_pre, "descend", plan)
            up = down and pl._cartesian(side, P["grasp"], P["lift"], down[-1], "lift", plan)
            if not up:
                plan.reason = plan.reason or f"IK failed on the lift ({side})"
                return plan
            # the block's centre over the hole: grasp point = hole - (block in the hand), turned with the palm at the
            # drop (two rounds: the palm's turn there depends on the target)
            ih = np.asarray(self.in_hand.get(det.shape, (0.0, 0.0, 0.0)), float) * ([1, 1, 1] if side == "left" else [1, -1, 1])
            corr = np.zeros(3)
            for _ in range(2):
                tgt = np.r_[np.asarray(hole_xy, float), z_drop] - corr
                P.update(above=np.r_[tgt[:2], z_carry], drop=tgt, retreat=tgt + [0.0, 0.0, 0.08])
                plan.reason = ""
                carry = self._solve_path(side, P["lift"], P["above"], fg, fd, up[-1], "carry", plan, w)
                plan.carry_mode = "cartesian"
                if not carry:                                  # joint-space instead, above the box rims
                    plan.carry_mode = "joint"
                    kin.hint, kin.w_hint = fdv, w
                    plan.reason = ""
                    carry = pl._joint_carry(side, up[-1], P["lift"], P["above"], plate_top + H + 0.02, "carry", plan)
                lower = carry and self._solve_path(side, P["above"], P["drop"], fd, fd, carry[-1], "lower", plan, w)
                retreat = lower and self._solve_path(side, P["drop"], P["retreat"], fd, fd, lower[-1], "retreat", plan, w)
                if not retreat:
                    plan.reason = plan.reason or f"IK failed ({side})"
                    return plan
                kin._fk(lower[-1])
                Rp = kin.data.oMf[kin.palm[side]].rotation
                corr = Rp @ ih                                 # (for triangles ih includes the pinch shift)
            err_d = pl._finger_err_q(side, lower[-1], fdv)
            if err_d > 6.0:
                plan.reason = f"finger direction at the drop off by {err_d:.0f} deg"
                return plan
        finally:
            kin.hint, kin.w_hint = saved

        vmax, amax, hv = mo["arm_max_vel"], mo["arm_max_acc"], mo["hand_max_vel"]
        home = arm_q.copy(); home[sl] = pl.home[sl]
        A, Hh, phases = [], [], []
        cur = {"a": arm_q.copy(), "h": hand_q.copy()}

        def add(name, a, h):
            if len(a):
                s = sum(len(x) for x in A)
                A.append(a); Hh.append(h); phases.append((name, s, s + len(a)))
                cur["a"] = a[-1].copy()

        def move(name, Qs, hand_to=None, vscale=1.0):
            a = time_scale([cur["a"]] + list(Qs), vmax * vscale, amax * vscale, pl.dt)
            h = np.repeat(cur["h"][None], len(a), 0)
            if hand_to is not None:
                hr = ramp(cur["h"], hand_to, hv, pl.dt)
                if len(hr) > len(a):
                    a = np.vstack([a, np.repeat((a[-1] if len(a) else cur["a"])[None], len(hr) - len(a), 0)])
                    h = np.repeat(cur["h"][None], len(a), 0)
                h[:len(hr)] = hr
                h[len(hr):] = hand_to
                cur["h"] = np.asarray(hand_to, float).copy()
            add(name, a, h)

        def hand(name, to, hold_s):
            h = ramp(cur["h"], to, hv, pl.dt)
            h = np.vstack([h, np.repeat(np.asarray(to, float)[None], int(round(hold_s / pl.dt)), 0)])
            cur["h"] = np.asarray(to, float).copy()
            add(name, np.repeat(cur["a"][None], len(h), 0), h)

        move("to_pregrasp", [q_pre], hand_to=hand_pre)
        move("descend", down)
        hand("close", hand_cls, mo["close_hold_s"])
        move("lift", up)
        move("carry", carry, vscale=self.carry_speed.get(det.shape, 1.0))
        move("lower", lower, vscale=0.5)                       # slow and steady over the hole
        hand("settle", hand_cls, 0.4)
        hand("open", hand_rel, mo["open_hold_s"] + 0.3)
        move("retreat", retreat)
        move("home", [home], hand_to=hand_open)
        plan.arm, plan.hand, plan.phases = np.vstack(A), np.vstack(Hh), phases
        plan.waypoints.update(P)
        plan.safety_clips = pl.dry_run_safety(arm_q, hand_q, plan.arm, plan.hand)
        if plan.safety_clips:
            plan.reason = f"{plan.safety_clips} safety clips in dry run"
            return plan
        plan.ok = True
        plan.reason = (f"{side} arm, fingers {np.degrees(fg):.0f} deg at the grasp, {np.degrees(fd):.0f} deg at the "
                       f"drop (wrist turn {np.degrees(wrap(fd - fg)):+.0f})")
        return plan


def _finger_err_q(self, side, q, f):
    self.kin._fk(q)
    x = self.kin.data.oMf[self.kin.palm[side]].rotation[:, 0]
    a = np.arctan2(x[1], x[0]) - np.arctan2(f[1], f[0])
    return float(np.degrees(abs((a + np.pi) % (2 * np.pi) - np.pi)))


# ------------------------------------------------------------------------------------------------ scoring
def classify(track, lid, shape, final_speed, rest=0.02):
    """Aalto's classify_insert, for the real lid: track = (n, 3) block centre over the episode (pelvis frame)."""
    c, z_under, a, holes, half, inner, counter_z = (lid[k] for k in ("c", "z_under", "a", "holes", "half", "inner",
                                                                      "counter_z"))
    R = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    loc = lambda p: R @ (np.asarray(p[:2]) - c)
    p = track[-1]
    over = np.all(np.abs(loc(p)) <= half)
    near = np.all(np.abs(loc(p)) <= half + 0.05)
    if p[2] < counter_z - 0.05:
        return "dropped" if near else "off"
    if over and p[2] < z_under and np.all(np.abs(loc(p)) <= inner):
        below = np.flatnonzero((track[:, 2] < z_under) & np.all(np.abs([loc(q) for q in track]) <= half, axis=1))
        k = max(below[0] - 1, 0)
        used = min(holes, key=lambda h: np.linalg.norm(track[k, :2] - holes[h]))
        if np.linalg.norm(track[k, :2] - holes[used]) > 0.04:
            used = None
        return ("inserted" if used == shape else "wrong_hole") if final_speed < rest else "moving"
    if over:
        return "forced"
    return "dropped" if near else "counter"


# ------------------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", default=str(next((q for q in (ROOT / "sim/task3/lid_shape_holes_200mm.stl",
                                                           ROOT / "artifacts/real_frames/lid/lid_shape_holes_200mm.stl")
                                                if q.exists()), ROOT / "sim/task3/lid_shape_holes_200mm.stl")))
    ap.add_argument("--closer", type=float, default=0.07, help="boxes this much closer to the robot than venue_measured")
    ap.add_argument("--box-gap", type=float, default=0.027, help="gap between the boxes (real drop 3: 2.6-2.8 cm)")
    ap.add_argument("--turn", type=float, default=0.0, help="lid turn on the box (deg)")
    ap.add_argument("--gap", type=float, default=0.012, help="block underside above the plate when released (m)")
    ap.add_argument("--shapes", default="cube,cylinder,triangle")
    ap.add_argument("--spots", default="0.20:0.12,0.24:-0.10", help="pelvis x:y of the block (m)")
    ap.add_argument("--yaws", default="10,-25")
    ap.add_argument("--privileged", action="store_true", help="true block pose instead of the camera (to separate "
                    "perception error from the move)")
    ap.add_argument("--calib", default="hands", help="camera fit: bins (v1.6 default: the box walls set x, y, yaw; "
                    "assumes scene.yaml's boxes) | hands (x, y, yaw from the arms) | lean (full pose from the arms)")
    ap.add_argument("--carry-speed", default="", help="shape:fraction of the arm speed while carrying, e.g. triangle:0.5")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--tag", default="insert-demo")
    a = ap.parse_args(argv)

    from aaltonomous.interface.calibration import Calibration
    from aaltonomous.scene.scene import Scene
    from aaltonomous.sim import oracle as O
    from aaltonomous.sim.aalto_task import layout as LAY
    from aaltonomous.baselines.classical.perception import Detection
    from decision_oracle import boxes_v16 as BX
    from decision_oracle.camera import CameraPerception
    import backend as BK

    cfg = lid_cfg(a.closer, a.box_gap)
    lidinfo = {}
    orig = B.build_spec

    def build_with_lid(cfg_=None, colors="venue"):
        spec, sc = orig(cfg_, colors)
        holes, (c, z0, ang) = add_lid(spec, cfg_ or cfg, a.stl, a.turn)
        pel = cfg["robot"]["pelvis_height"]
        lidinfo.update(holes=holes, c=c, z_under=z0 - pel, top=z0 + PLATE - pel, a=ang, half=0.1,
                       inner=float(cfg["bins"]["outer_size"]) / 2 - float(cfg["bins"]["wall_thickness"]),
                       counter_z=cfg["table"]["height"] - pel)
        return spec, sc
    B.build_spec = build_with_lid
    be = BK.MujocoBackend(cfg=cfg, rtf=None)
    m, d = be.model, be.data
    lidcam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "lidcam")
    rend = mujoco.Renderer(m, 480, 640) if a.video else None
    vopt = mujoco.MjvOption()
    vopt.geomgroup[B.HEAD_GROUP] = 0

    psc = Scene.load()                                   # the policy's scene: Aalto's scene.yaml, as in the image
    cal = Calibration.load()
    pol = O.OraclePolicy(client=None, scene=psc, threaded=False, log=None, prefetch=False)
    pl = pol.planner
    pl._finger_err_q = _finger_err_q.__get__(pl)
    ip = InsertPlanner(pl, gap=a.gap)
    ip.carry_speed = {k: float(v) for k, v in (kv.split(":") for kv in a.carry_speed.split(",") if kv)}
    handeye = None
    if a.calib in ("hands", "lean"):
        from decision_oracle.handeye import HandEye
        handeye = HandEye()
    true_T = B.head_T_pelvis_optical(cfg)                # where the sim's head camera really is (pelvis frame)

    out = ROOT / "artifacts" / "eval" / "mujoco" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    spots = [tuple(float(v) for v in s.split(":")) for s in a.spots.split(",")]
    rows = []
    t0 = time.time()
    for shape in a.shapes.split(","):
        for (px, py) in spots:
            for yaw_deg in [float(v) for v in a.yaws.split(",")]:
                case = f"{shape}_{px:.2f}_{py:+.2f}_{yaw_deg:+.0f}"
                mat = be.sc.pelvis_to_mat(np.array([px, py, be.sc.counter_z]))
                lay = [{"color": "red", "shape": shape, "x": float(mat[0]), "y": float(mat[1]), "yaw": float(np.radians(yaw_deg))}]
                be.reset_scene(lay)
                name = be.active[0]
                adr, vadr = be.obj_adr[name], be.obj_vadr[name]
                im = be.images()
                row = {"case": case, "shape": shape, "x": px, "y": py, "yaw_deg": yaw_deg}
                # --- perception: camera fit, boxes, lid, block
                cam = CameraPerception(copy.deepcopy(psc), cal)
                arm0, _, hand0 = be.joints()
                if a.calib in ("hands", "lean"):               # the camera's x, y, yaw (or full pose) from the arms
                    setattr(cam, "handeye" if a.calib == "hands" else "lean", handeye)
                    cam.kins = lambda: [pl.kin]                # lean: the IK model moves into the camera's frame
                    cam.update({"arm_q": arm0, "hand_q": hand0})
                fit = cam.ensure_pose(im["head_depth"])
                row["camera_err_mm"] = round(1000 * float(np.linalg.norm(fit.T[:3, 3] - true_T[:3, 3])), 1)
                found = BX.find_boxes(BX.points(cal, im["head_depth"], 2), fit.T, cam.scene)
                lid = BX.find_lid(BX.points(cal, im["head_depth"], 1), fit.T, cam.scene, found) if found["boxes"] else {"ok": False, "why": found["why"]}
                row.update(fit_ok=bool(fit.ok), boxes=found["why"], lid=lid["why"])
                if lid.get("ok"):
                    row["holes"] = {k: [round(float(v), 3) for v in q["center"]] for k, q in lid["holes"].items()}
                truth_p = d.qpos[adr:adr + 3] - be.pelvis_w
                q0 = d.qpos[adr + 3:adr + 7].copy()
                yaw0 = float(np.arctan2(2 * (q0[0] * q0[3] + q0[1] * q0[2]), 1 - 2 * (q0[2] ** 2 + q0[3] ** 2)))
                if lid.get("ok"):
                    row["hole_err_mm"] = {k: round(1000 * float(np.linalg.norm(lid["holes"][k]["center"] - lidinfo["holes"][k])), 1)
                                          for k in lid["holes"]}
                if a.privileged:
                    q = d.qpos[adr + 3:adr + 7]
                    det = Detection("red", np.r_[truth_p[:2], truth_p[2] + 0.0225], 1000, 1000, "oracle",
                                    yaw=float(np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))))
                    det.shape = shape
                else:
                    dets = [dd for dd in cam.detect(im["head_rgb"], im["head_depth"]) if dd.shape in ("cube", "cylinder", "triangle")]
                    det = min(dets, key=lambda dd: np.linalg.norm(dd.top[:2] - truth_p[:2])) if dets else None
                if det is None or not lid.get("ok"):
                    cam.reset()
                    row.update(outcome="not seen", why="block not detected" if det is None else lid["why"])
                    rows.append(row); print(case, row["outcome"], row["why"], flush=True)
                    continue
                row.update(seen_shape=det.shape, seen_err_mm=round(1000 * float(np.linalg.norm(det.top[:2] - truth_p[:2])), 1))
                sym = {"cube": np.pi / 2, "triangle": 2 * np.pi / 3}.get(det.shape)
                if sym and det.yaw is not None:
                    row["seen_yaw_err_deg"] = round(float(np.degrees((det.yaw - yaw0 + sym / 2) % sym - sym / 2)), 1)
                if det.shape != shape:
                    row["note"] = f"seen as {det.shape}"
                hole = lid["holes"].get(det.shape)
                axis = np.radians(hole["axis_deg"])
                arm_q, _, hand_q = be.joints()
                plan = ip.plan(det, hole["center"], axis, lid["z"] + cam.scene.counter_z, arm_q.astype(float), hand_q.astype(float))
                row["plan"] = plan.reason if plan is not None else "no plan"
                row["carry_mode"] = getattr(plan, "carry_mode", None)
                if plan is None or not plan.ok:
                    cam.reset()
                    row["outcome"] = "no plan"
                    rows.append(row); print(case, "no plan:", row["plan"], flush=True)
                    continue
                # --- play it
                frames, track = [], []
                ph = {nm: (s, e) for nm, s, e in plan.phases}
                for k in range(len(plan.arm) + 75):                   # + 2.5 s to settle
                    kk = min(k, len(plan.arm) - 1)
                    be.command(plan.arm[kk], plan.hand[kk])
                    be.advance(1.0 / 30.0)
                    track.append(d.qpos[adr:adr + 3] - be.pelvis_w)
                    if k in (ph["lift"][1] - 1, ph["open"][0]):   # where the block sits in the hand (palm frame)
                        pl.kin._fk(be.joints()[0].astype(float))       # the palm where the arm really is (URDF FK)
                        M = pl.kin.data.oMf[pl.kin.palm[plan.side]]
                        pb, Rb = M.translation, M.rotation
                        inhand = Rb.T @ (track[-1] - pb) - pl.kin.offset[plan.side]
                        qo = d.qpos[adr + 3:adr + 7]
                        oy = float(np.arctan2(2 * (qo[0] * qo[3] + qo[1] * qo[2]), 1 - 2 * (qo[2] ** 2 + qo[3] ** 2)))
                        sym = {"cube": np.pi / 2, "triangle": 2 * np.pi / 3}.get(shape)
                        key = "lift" if k == ph["lift"][1] - 1 else "release"
                        row[f"inhand_{key}_mm"] = [round(1000 * float(v), 1) for v in inhand]
                        if sym:
                            # block faces vs the hole's: the sim's prism has its apex at yaw + 90 deg, the hole a tip at
                            # lid turn + 90 deg; a cube's faces at yaw + k 90, the square hole's at the lid turn
                            row[f"yaw_{key}_deg"] = round(float(np.degrees((oy - lidinfo["a"] + sym / 2) % sym - sym / 2)), 1)
                            if key == "lift":                  # how much the block turned in the hand, beyond the plan
                                row["turn_in_hand_deg"] = round(float(np.degrees((oy - yaw0 + sym / 2) % sym - sym / 2)), 1)
                    if k == ph["open"][0]:
                        row["release_xy_err_mm"] = round(1000 * float(np.linalg.norm(track[-1][:2] - lidinfo["holes"][shape])), 1)
                        row["release_dxy_mm"] = [round(1000 * float(v), 1) for v in track[-1][:2] - lidinfo["holes"][shape]]
                        row["release_z_mm"] = round(1000 * float(track[-1][2] - lidinfo["top"]), 1)
                    if rend is not None and k % 2 == 0:
                        rend.update_scene(d, camera=be.cam, scene_option=vopt)
                        h = rend.render().copy()
                        rend.update_scene(d, camera=lidcam)
                        frames.append(np.hstack([h, rend.render().copy()]))
                track = np.array(track)
                e_l = ph["lift"][1] - 1
                lost = np.flatnonzero(track[e_l:ph["open"][0], 2] < track[e_l, 2] - 0.03 + (track[e_l:ph["open"][0], 2] * 0))
                zg = np.array([pl.kin.grasp_pose(plan.side, plan.arm[k])[0][2] for k in range(e_l, ph["open"][0])])
                lost = np.flatnonzero(track[e_l:ph["open"][0], 2] < zg - 0.04)
                if len(lost):
                    row["lost_in"] = next(nm for nm, s_, e_ in plan.phases if s_ <= e_l + lost[0] < e_)
                speed = float(np.linalg.norm(d.qvel[vadr:vadr + 3]))
                row["outcome"] = classify(track, lidinfo, shape, speed)
                row["score"] = {"inserted": 3, "wrong_hole": 0, "forced": -1, "dropped": -1, "counter": 0}.get(row["outcome"], 0)
                rows.append(row)
                cam.reset()                                    # IK model back to the pelvis frame
                if frames:
                    import imageio.v2 as iio
                    iio.mimwrite(out / f"{case}.mp4", frames, fps=15, quality=7)
                print(f"{case}: {row['outcome']}  release off the hole {row.get('release_xy_err_mm')} mm  "
                      f"block seen {row['seen_err_mm']} mm off, hole err {row.get('hole_err_mm')}  {row['plan']}", flush=True)
    (out / "insert.json").write_text(json.dumps({"args": vars(a), "rows": rows}, indent=1, default=float))
    n = len(rows)
    ins = sum(r["outcome"] == "inserted" for r in rows)
    print(f"\n{ins}/{n} inserted in {time.time() - t0:.0f} s -> {out}")
    for s in a.shapes.split(","):
        rr = [r for r in rows if r["shape"] == s]
        print(f"  {s:9s} " + ", ".join(r["outcome"] for r in rr))


if __name__ == "__main__":
    main()
