"""Standing-triangle grasp bench in MuJoCo: one standing prism per case, one pick by Aalto's oracle planner with a
forced arm and a forced finger angle, played open-loop (no policy server, no rendering, no clock), so a case takes
about a second.

Per case it records:
- the plan's finger direction vs the nearest apex (phi, deg, mod 120);
- which hand links touch the prism at the end of the close, and the contact normals;
- how far the prism moved and turned during descend + close;
- whether it is still in the hand at the end of the lift.

    PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python sim/mujoco/tri_bench.py --out artifacts/mujoco/tri_bench.json
    .venv/bin/python sim/mujoco/tri_bench.py --report artifacts/mujoco/tri_bench.json

Options that change the physics or the grasp for a variant: --friction (prism), --hand-friction, --height-frac,
--condim, --point, --phis, --yaws, --spots.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend as BK                                                    # noqa: E402
import build as B                                                       # noqa: E402


def _yaw(qwxyz):
    w, x, y, z = qwxyz
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _tilt(qwxyz):
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, np.asarray(qwxyz, float))
    return float(np.degrees(np.arccos(np.clip(R[8], -1, 1))))


def run(a):
    from aaltonomous.baselines.classical.perception import Detection
    from aaltonomous.sim import oracle as O

    cfg = B.load_cfg()
    if a.friction is not None:
        cfg["objects"]["friction"] = a.friction
    be = BK.MujocoBackend(cfg=cfg, rtf=None)
    m, d = be.model, be.data
    if a.hand_friction is not None or a.condim is not None:
        for g in range(m.ngeom):
            b = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, m.geom_bodyid[g]) or ""
            if "hand" in b and m.geom_contype[g]:
                if a.hand_friction is not None:
                    m.geom_friction[g, 0] = a.hand_friction
                if a.condim is not None:
                    m.geom_condim[g] = a.condim
    ov = {}
    if a.point:
        ov["grasp.point_in_palm"] = [float(v) for v in a.point.split(",")]
    pol = O.OraclePolicy(client=None, scene=be.sc, threaded=False, log=None, prefetch=False, overrides=ov)
    if a.height_frac is not None:
        pol.planner.cfg["grasp"]["height_frac"] = a.height_frac
    pl, sc = pol.planner, be.sc
    H = sc.object_height("triangle")
    zc = sc.counter_z
    name = next(n for n in be.objects if "_triangle_" in n and n.startswith("obj_red"))
    color = "red"
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, name)
    adr = be.obj_adr[name]
    hand_bodies = {i: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)}

    spots = [tuple(float(v) for v in s.split(":")) for s in a.spots.split(",")]     # pelvis x:|y| (m)
    rows = []
    cases = list(itertools.product(a.arms.split(","), spots, [float(v) for v in a.yaws.split(",")],
                                   [float(v) for v in a.phis.split(",")]))
    t0 = time.time()
    rng = np.random.default_rng(a.seed)
    for i, (side, (px, py), yaw_deg, phi_deg) in enumerate(cases):
        py = py if side == "left" else -py                         # each arm on its own side
        mat = sc.pelvis_to_mat(np.array([px, py, zc]))
        lay = [{"color": color, "shape": "triangle", "x": float(mat[0]), "y": float(mat[1]),
                "yaw": float(np.radians(yaw_deg))}]
        be.reset_scene(lay)
        if name not in be.active:
            print("layout did not place the red triangle", lay); continue
        p0 = d.qpos[adr:adr + 3] - be.pelvis_w
        q0 = d.qpos[adr + 3:adr + 7].copy()
        yaw = _yaw(q0)
        if a.noise_mm or a.noise_deg:                               # perception error: what the planner sees
            seen_xy = p0[:2] + rng.normal(0, a.noise_mm / 1000, 2)
            yaw = yaw + np.radians(rng.normal(0, a.noise_deg))
        else:
            seen_xy = p0[:2]
        det = Detection(color, np.r_[seen_xy, p0[2] + H / 2], 1000, 1000, "oracle", yaw=yaw)
        det.shape, det.name = "triangle", name
        # the finger direction at phi from an apex nearest this arm's natural direction (Aalto's rule for k)
        ref = np.radians(O.FINGER_REF_DEG[side])
        cands = [yaw + np.pi / 2 + np.radians(phi_deg) + 2 * np.pi * k / 3 for k in range(3)]
        fa = min(cands, key=lambda c: abs((c - ref + np.pi) % (2 * np.pi) - np.pi))
        dev = float(np.degrees(abs((fa - ref + np.pi) % (2 * np.pi) - np.pi)))
        f = np.array([np.cos(fa), np.sin(fa), 0.0])
        d2 = copy.copy(det)
        d2.top = det.top + O._tri_shift(fa - (yaw + np.pi / 2)) * f
        arm_q, _, hand_q = be.joints()
        arm_q, hand_q = arm_q.astype(float), hand_q.astype(float)
        saved = (pl.kin.hint, pl.kin.w_hint)
        pl.kin.hint, pl.kin.w_hint = f, O.FACE_HINT_WEIGHT
        try:
            p = pl._plan_side(d2, side, side, arm_q, hand_q)
        finally:
            pl.kin.hint, pl.kin.w_hint = saved
        row = dict(i=i, arm=side, x=px, y=py, yaw_deg=yaw_deg, phi=phi_deg, finger_deg=round(float(np.degrees(fa)), 1),
                   dev_ref=round(dev, 1), plan_ok=bool(p.ok), reason=p.reason)
        if p.ok:
            row["finger_err"] = round(pl._finger_err(p, side, f), 1)
            ph = {n: (s, e) for n, s, e in p.phases}
            end = ph["lift"][1]
            snap = {}
            for k in range(end):
                be.command(p.arm[k], p.hand[k])
                be.advance(1.0 / 30.0)
                for nm in ("descend", "close", "lift"):
                    if k == ph[nm][1] - 1:
                        snap[nm] = (d.qpos[adr:adr + 3] - be.pelvis_w).copy(), d.qpos[adr + 3:adr + 7].copy()
                if k == ph["close"][1] - 1:          # contacts at the end of the close
                    con = defaultdict(list)
                    for c in d.contact[:d.ncon]:
                        b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
                        if bid in (b1, b2):
                            other = hand_bodies[b2 if b1 == bid else b1]
                            nrm = c.frame[:3] * (1 if b1 == bid else -1)      # normal pointing out of the prism
                            con[other].append([round(float(v), 2) for v in nrm])
                    row["contacts"] = {k2: v[0] for k2, v in con.items()}
            pc, qc = snap["close"]
            pd_, qd = snap["descend"]
            pl_, ql = snap["lift"]
            row.update(push_mm=round(1000 * float(np.linalg.norm((pd_ - p0)[:2])), 1),
                       close_move_mm=round(1000 * float(np.linalg.norm((pc - pd_)[:2])), 1),
                       close_turn_deg=round(float(np.degrees((_yaw(qc) - _yaw(qd) + np.pi) % (2 * np.pi) - np.pi)), 1),
                       tilt_after_close=round(_tilt(qc), 1),
                       lift_dz_mm=round(1000 * float(pl_[2] - p0[2]), 1))
            row["held"] = row["lift_dz_mm"] > 30
        rows.append(row)
        print(f"{i:3d} {side:5s} x={px:.2f} y={py:+.2f} yaw={yaw_deg:+4.0f} phi={phi_deg:5.1f} "
              f"ok={row['plan_ok']} held={row.get('held')} push={row.get('push_mm')} "
              f"close_move={row.get('close_move_mm')} turn={row.get('close_turn_deg')} "
              f"tilt={row.get('tilt_after_close')} contacts={sorted(row.get('contacts', {}))} "
              f"{'' if p.ok else p.reason}", flush=True)
    print(f"{len(rows)} cases in {time.time() - t0:.0f} s")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"args": vars(a), "rows": rows}, open(a.out, "w"), indent=1)
    report(a.out)


def report(path):
    rows = json.load(open(path))["rows"]
    print(f"\n{path}")
    for side in ("left", "right"):
        rr = [r for r in rows if r["arm"] == side and r["plan_ok"]]
        if not rr:
            continue
        by = defaultdict(list)
        for r in rr:
            by[r["phi"]].append(r)
        print(f"{side}: phi held/planned (of {len([r for r in rows if r['arm'] == side])} cases)")
        for phi in sorted(by):
            g = by[phi]
            h = sum(r["held"] for r in g)
            mv = np.median([r["close_move_mm"] for r in g])
            tn = np.median([abs(r["close_turn_deg"]) for r in g])
            print(f"   phi {phi:5.1f}: {h}/{len(g)}  close move {mv:4.1f} mm  turn {tn:4.1f} deg")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="left,right")
    ap.add_argument("--spots", default="0.22:0.10,0.27:0.16", help="pelvis x:|y| (m), y mirrored per arm")
    ap.add_argument("--yaws", default="0,20,40,60,80,100")
    ap.add_argument("--phis", default="0,15,30,45,60,75,90,105")
    ap.add_argument("--friction", type=float, default=None)
    ap.add_argument("--hand-friction", type=float, default=None)
    ap.add_argument("--condim", type=int, default=None)
    ap.add_argument("--height-frac", type=float, default=None)
    ap.add_argument("--point", default=None, help="grasp.point_in_palm x,y,z (left palm frame, m); Aalto's oracle: "
                    "0.099,-0.084,0.015")
    ap.add_argument("--noise-mm", type=float, default=0.0, help="sd of the seen position error (each axis)")
    ap.add_argument("--noise-deg", type=float, default=0.0, help="sd of the seen yaw error")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="artifacts/mujoco/tri_bench.json")
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    if a.report:
        report(a.report)
    else:
        run(a)
