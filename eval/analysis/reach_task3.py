"""Task 3 (insert_shapes): where can the G1 hold a block over the lid's holes? -> where should Aalto put the lid box.

Runs where Aalto's classical package + Pinocchio are installed (e.g. a bot-icelli/policy image):
    python reach_task3.py [out.json]

1. Reach map: for each arm, top-down IK (Aalto's ArmKinematics: palm down within 25 deg, grasp point within 6 mm) for
   the grasp point (= block centre) on a 2 cm grid at the release heights below, pelvis frame.
2. Placements: the 200 mm lid (holes from lid_shape_holes_200mm.stl: square (-48, -35) mm, circle (+48, -35),
   triangle (0, +39.2), 60 mm openings) on a 0.21 m box, box centre on a 1 cm grid, lid turned 0/90/180/270 deg; keeps
   placements where every hole is reachable (by the arm on its side when possible) and the box stays clear of the object
   band; ranks them by reach margin (distance from each hole to the nearest unreachable grid point).
3. Yaw: at the best placement's holes, which wrist yaws the hand can hold there (square and triangle must be turned to
   match their hole; the circle needn't).
"""
import json
import sys
from multiprocessing import Pool

import numpy as np

from aaltonomous.baselines.classical.config import home_arm, load_config
from aaltonomous.baselines.classical.kinematics import ArmKinematics

ZS = (0.12, 0.14, 0.16)          # grasp point (block centre) heights tried at release, pelvis frame
XS = np.round(np.arange(0.16, 0.621, 0.02), 3)
YS = np.round(np.arange(-0.44, 0.441, 0.02), 3)
HOLES = {"square": (-0.048, -0.035), "circle": (0.048, -0.035), "triangle": (0.0, 0.0392)}  # lid frame (u right, v away)
BOX = 0.21
BAND = (0.26 - 0.035, 0.33 + 0.035, -0.17 - 0.035, 0.17 + 0.035)   # object band + object radius + margin (pelvis)
cfg = load_config(None)
kin = ArmKinematics(cfg)
HOME = home_arm(cfg)


def row(args):
    side, z, y = args
    out, last = [], None
    for x in XS:
        extra = [last] if last is not None else []
        q, ok, perr, tilt = kin.solve(side, np.array([x, y, z]), HOME, top_down=True, extra_seeds=extra, restarts=False)
        if ok:
            last = q[kin.sl(side)]
        out.append((bool(ok), float(perr), float(np.degrees(tilt))))
    return side, z, y, out


def reach_maps():
    jobs = [(s, z, y) for s in ("left", "right") for z in ZS for y in YS]
    maps = {(s, z): np.zeros((len(YS), len(XS)), bool) for s in ("left", "right") for z in ZS}
    with Pool(8) as p:
        for side, z, y, out in p.imap_unordered(row, jobs):
            maps[(side, z)][list(YS).index(y)] = [o[0] for o in out]
    return maps


def margin_map(ok):
    """Distance (m) from each reachable cell to the nearest unreachable one (0 where unreachable)."""
    bad = np.argwhere(~ok)
    d = np.zeros(ok.shape)
    for i, j in np.argwhere(ok):
        d[i, j] = np.min(np.hypot((bad[:, 0] - i) * 0.02, (bad[:, 1] - j) * 0.02)) if len(bad) else 1.0
    return d


def lookup(m, x, y):
    i, j = (y - YS[0]) / 0.02, (x - XS[0]) / 0.02
    if not (0 <= i <= len(YS) - 1 and 0 <= j <= len(XS) - 1):
        return 0.0
    i0, j0 = int(np.floor(i)), int(np.floor(j))
    i1, j1 = min(i0 + 1, len(YS) - 1), min(j0 + 1, len(XS) - 1)
    return float(min(m[i0, j0], m[i0, j1], m[i1, j0], m[i1, j1]))   # conservative: the worst corner


def hole_xy(bx, by, rot_deg, uv):
    """Lid frame (u to the robot's right, v away from the robot) at 0 deg; rotated CCW (seen from above) by rot_deg."""
    u, v = uv
    a = np.radians(rot_deg)
    ur, vr = u * np.cos(a) - v * np.sin(a), u * np.sin(a) + v * np.cos(a)
    return bx + vr, by - ur


def placements(margins, z):
    res = []
    for bx in np.round(np.arange(0.20, 0.60, 0.01), 3):
        for by in np.round(np.arange(-0.40, 0.401, 0.01), 3):
            x0, x1, y0, y1 = bx - BOX / 2, bx + BOX / 2, by - BOX / 2, by + BOX / 2
            if x0 < 0.15:
                continue                                     # table edge / body
            if not (x0 >= BAND[1] or x1 <= BAND[0] or y0 >= BAND[3] or y1 <= BAND[2]):
                continue                                     # overlaps the object band
            for rot in (0, 90, 180, 270):
                holes, worst = {}, 1.0
                for name, uv in HOLES.items():
                    x, y = hole_xy(bx, by, rot, uv)
                    ml, mr = lookup(margins[("left", z)], x, y), lookup(margins[("right", z)], x, y)
                    side = "left" if ml >= mr else "right"
                    m = max(ml, mr)
                    holes[name] = {"xy": [round(x, 3), round(y, 3)], "arm": side, "margin_m": round(m, 3),
                                   "both_arms": bool(ml > 0 and mr > 0)}
                    worst = min(worst, m)
                if worst > 0:
                    res.append({"box_centre": [float(bx), float(by)], "box_near_edge_x": round(float(x0), 3),
                                "lid_rot_deg": rot, "worst_margin_m": round(worst, 3), "holes": holes})
    res.sort(key=lambda r: (-r["worst_margin_m"], abs(r["box_centre"][1]), r["box_centre"][0]))
    return res


def yaw_span(side, x, y, z):
    """Wrist yaws (finger direction in the pelvis xy plane, deg; 0 = fingers forward) the hand can hold at (x, y, z)."""
    w0, h0 = kin.w_hint, kin.hint.copy()
    kin.w_hint = 2.0
    got = []
    for psi in range(-180, 180, 15):
        kin.hint = np.array([np.cos(np.radians(psi)), np.sin(np.radians(psi)), 0.0])
        q, ok, perr, tilt = kin.solve(side, np.array([x, y, z]), HOME, top_down=True, restarts=True)
        if ok:
            kin._fk(q)
            f = kin.data.oMf[kin.palm[side]].rotation[:, 0]
            yaw = float(np.degrees(np.arctan2(f[1], f[0])))
            if abs(((yaw - psi + 180) % 360) - 180) <= 10:
                got.append(psi)
    kin.w_hint, kin.hint = w0, h0
    return got


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "reach_task3.json"
    maps = reach_maps()
    margins = {k: margin_map(v) for k, v in maps.items()}
    report = {"xs": XS.tolist(), "ys": YS.tolist(), "maps": {f"{s}@{z}": maps[(s, z)].astype(int).tolist() for s, z in maps}}
    for z in ZS:
        print(f"\n== release height z = {z} m (block centre): reachable cells left {maps[('left', z)].sum()}, right {maps[('right', z)].sum()}")
        # Aalto's default: lid on the left bin, centre (0.505, +0.26)
        for rot in (0, 90, 180, 270):
            row_ = []
            for name, uv in HOLES.items():
                x, y = hole_xy(0.505, 0.26, rot, uv)
                m = max(lookup(margins[("left", z)], x, y), lookup(margins[("right", z)], x, y))
                row_.append(f"{name} ({x:.3f},{y:+.3f}) {'OK' if m > 0 else 'OUT'}")
            print(f"  Aalto's default (left bin), lid turned {rot:3d}: " + "; ".join(row_))
        best = placements(margins, z)
        report[f"placements@{z}"] = best[:20]
        print(f"  placements with every hole reachable: {len(best)}")
        for r in best[:6]:
            print(f"   box centre ({r['box_centre'][0]:.2f}, {r['box_centre'][1]:+.2f}), near edge x {r['box_near_edge_x']:.2f}, lid {r['lid_rot_deg']:3d} deg, "
                  f"worst margin {r['worst_margin_m'] * 100:.0f} cm: " +
                  "; ".join(f"{n} {h['xy']} {h['arm']}{' (both)' if h['both_arms'] else ''}" for n, h in r["holes"].items()))
    z = 0.14
    best = report[f"placements@{z}"]
    if best:
        r = best[0]
        print(f"\n== yaw at the best placement (z {z}): box ({r['box_centre'][0]:.2f}, {r['box_centre'][1]:+.2f}), lid {r['lid_rot_deg']} deg")
        r["yaws"] = {}
        for name, h in r["holes"].items():
            ys = yaw_span(h["arm"], h["xy"][0], h["xy"][1], z)
            r["yaws"][name] = ys
            print(f"   {name}: {h['arm']} arm holds finger yaws {ys[:1] and (str(min(ys)) + '..' + str(max(ys)))} deg ({len(ys)} of 24 tried)")
    json.dump(report, open(out_path, "w"))
    print(f"\n-> {out_path}")
