"""Offline checks for task 3 (insert.py), no sim:

    PYTHONPATH=/app/aaltonomous-humanoid:/app/policy python -m decision_oracle.test_insert [--layouts 12]

1. find_lid on synthetic head-depth points (lid moved 2 cm, turned 4 deg, 7.2 cm high, holes cut out, table and
   box walls around it, 1 mm noise): centre within 5 mm, turn within 1.5 deg, height within 3 mm.
2. Planning with exact poses (fake scene service), blocks in the requested right half of the band: for each layout
   and object, the planner's options for the insert (arm, grasp, route), wrist error and block-centre error at the
   hole. Every direct plan must end with the wrist within ALIGN_TOL_DEG and the block within DROP_TOL of its hole.
"""
from __future__ import annotations

import argparse
import collections
import time

import numpy as np

from aaltonomous.interface import tasks
from aaltonomous.scene.scene import Scene

from . import insert as I
from .test_offline import FakeClient, setup


def synthetic_lid_points(lid, zc, rng, noise=0.001):
    """Points the head camera would see: table, the lid's top plate with its holes, the near box wall."""
    pts = []
    g = np.arange(-0.35, 0.35, 0.004)
    X, Y = np.meshgrid(g + lid.center[0], g + lid.center[1])
    tab = np.c_[X.ravel(), Y.ravel(), np.full(X.size, zc)]
    tab = tab[~np.array([lid.covers(p[:2]) for p in tab])]
    pts.append(tab)
    u = np.arange(-I.LID_SIZE / 2, I.LID_SIZE / 2, 0.003)
    U, V = np.meshgrid(u, u)
    L = np.c_[U.ravel(), V.ravel()]
    keep = np.ones(len(L), bool)
    for s in I.SHAPES:
        off = np.asarray(I.LAYOUTS[lid.layout][s], float)
        keep &= np.linalg.norm(L - off, axis=1) > 0.03          # 60 mm openings (as circles: enough here)
    L = L[keep]
    world = lid.center + L @ lid.rot().T
    pts.append(np.c_[world, np.full(len(world), zc + lid.top)])
    z = np.arange(zc + 0.005, zc + lid.top - 0.012, 0.004)       # near wall of the box (towards the robot)
    t = np.arange(-I.BOX_SIZE / 2, I.BOX_SIZE / 2, 0.004)
    T, Z = np.meshgrid(t, z)
    wall = lid.center + np.c_[np.full(T.size, -I.BOX_SIZE / 2), T.ravel()] @ lid.rot().T
    pts.append(np.c_[wall, Z.ravel()])
    P = np.vstack(pts)
    return P + rng.normal(0, noise, P.shape)


def check_find_lid():
    scene = Scene.load()
    zc = scene.counter_z
    rng = np.random.default_rng(0)
    req = I.requested_lid()
    bad = 0
    for dx, dy, turn, top in ((0.0, 0.0, 0.0, 0.072), (0.02, -0.01, 4.0, 0.072), (-0.03, 0.02, -6.0, 0.087),
                              (0.05, 0.03, 10.0, 0.079)):
        true = I.Lid(req.center + [dx, dy], np.radians(turn), top, req.layout)
        found, why = I.find_lid(synthetic_lid_points(true, zc, rng), zc, req)
        if found is None:
            print(f"find_lid: moved ({dx:+.2f}, {dy:+.2f}) turned {turn:+.0f}: NOT FOUND ({why})")
            bad += 1
            continue
        e_c = float(np.linalg.norm(found.center - true.center))
        e_y = float(np.degrees(abs(I._wrap(found.yaw - true.yaw, np.pi / 2))))
        e_t = abs(found.top - true.top)
        ok = e_c < 0.005 and e_y < 1.5 and e_t < 0.003
        bad += not ok
        print(f"find_lid: moved ({dx:+.2f}, {dy:+.2f}) turned {turn:+.0f} top {100 * top:.1f}: centre err "
              f"{1000 * e_c:.1f} mm, turn err {e_y:.2f} deg, top err {1000 * e_t:.1f} mm  {'ok' if ok else 'BAD'}")
    return bad


def insert_layout(rng, scene):
    """Blocks in the requested right half of the band (mat x 0.28-0.42, y 0.12-0.19), one of each shape."""
    L = scene.cfg["layout"]
    kw = dict(n_min=3, n_max=3, region=((0.28, 0.42), (0.12, 0.19)), min_spacing=0.08,
              yaw_range=tuple(np.radians(L["yaw_range_deg"])))
    lay = tasks.sample_layout(rng, **kw)
    for o, s in zip(lay, rng.permutation(I.SHAPES)):
        o["shape"] = str(s)
    return lay


def check_planning(layouts, seed, budget):
    from .upgrades_v16 import V16OraclePolicy
    scene = Scene.load()
    bad, n_obj, n_direct, n_relay, n_none = 0, 0, 0, 0, 0
    kinds = collections.Counter()
    for i in range(layouts):
        rng = np.random.default_rng(seed + i)
        lay = insert_layout(rng, scene)
        fc = FakeClient(scene, lay)
        pol = V16OraclePolicy(fc, sides="off", perception="privileged", threaded=False, prefetch=False, log=None,
                              labels="off", instruction="rules")
        info = I.configure(pol, "insert_shapes", {"instruction": tasks.INSERT_INSTRUCTION})
        pol.reset(info)
        I.after_reset(pol)
        setup(pol)
        dets = pol.perception.detect()
        t = time.monotonic()
        opts, inf = pol.enum.feasible_options(dets, pol.arm_cmd, pol.hand_cmd, budget_s=budget)
        dt = time.monotonic() - t
        by_obj = collections.defaultdict(list)
        for o in opts:
            by_obj[o.obj].append(o)
            ins = getattr(o.plan, "insert", None) or {}
            kinds[(o.shape, o.arm, o.grasp[:4], o.route)] += 1
            if o.route == "direct" and (not o.plan.ok or ins.get("wrist_err_deg", 99) > I.ALIGN_TOL_DEG
                                        or ins.get("drop_err_mm", 99) > 1000 * I.DROP_TOL or o.plan.safety_clips):
                bad += 1
                print(f"   BAD option {o.to_json()} {ins}")
        print(f"layout {i}: {len(dets)} blocks, {len(opts)} options in {dt:.1f} s")
        for d in dets:
            n_obj += 1
            os_ = by_obj.get(d.name, [])
            route = "direct" if any(o.route == "direct" for o in os_) else "relay" if os_ else "none"
            n_direct += route == "direct"
            n_relay += route == "relay"
            n_none += route == "none"
            best = next((o for o in os_ if o.route == route), None)
            ins = getattr(best.plan, "insert", {}) if best is not None else {}
            print(f"   {d.color:<6} {getattr(d, 'shape', '?'):<8} at ({d.top[0]:.3f}, {d.top[1]:+.3f}) yaw "
                  f"{np.degrees(d.yaw or 0):+5.0f}: {route:<6} {len(os_)} options"
                  + (f"  e.g. {best.arm} {best.grasp} {best.duration:.1f} s {ins}" if best is not None else
                     f"  tried: {[t['reason'][:70] for t in inf['tried'] if t['obj'] == d.name][:3]}"))
    print(f"\nblocks {n_obj}: direct {n_direct}, relay only {n_relay}, no plan {n_none}; bad options {bad}")
    for k, v in sorted(kinds.items()):
        print(f"  {k}: {v}")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--layouts", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=float, default=6.0)
    a = ap.parse_args(argv)
    bad = check_find_lid()
    bad += check_planning(a.layouts, a.seed, a.budget)
    print("PASS" if bad == 0 else f"FAIL ({bad})")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
