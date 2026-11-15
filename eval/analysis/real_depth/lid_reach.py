"""Rung 3: how much closer must the boxes be for each lid hole to be reachable? Aalto's IK + scene.yaml.
For every shift d (bins moved d towards the robot): can the left hand hold an object centred over the hole,
top-down (<= 25 deg tilt), with its bottom 1 cm above the lid (release) and 3 cm above (approach)? And which finger
directions (hand yaw) are possible there (hint weight 3.0, achieved within 12 deg, as Aalto's face grasps)?
Usage: PYTHONPATH=third_party/aaltonomous-humanoid python lid_shift.py <urdf>"""
import sys, numpy as np
from aaltonomous.baselines.classical.config import load_config, home_arm
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from aaltonomous.scene.scene import Scene

urdf = sys.argv[1]
cfg = load_config(); sc = Scene.load(); kin = ArmKinematics(cfg, urdf=urdf); home = home_arm(cfg)
lid_top = sc.counter_z + sc.lid_z[1]
half = sc.object_height() / 2
holes = {h["shape"]: sc.mat_to_pelvis([h["center"][0], h["center"][1], 0.0])[:2] for h in sc.lid_holes()}
side = sys.argv[2] if len(sys.argv) > 2 else "left"

def reach(p):
    return kin.solve(side, np.asarray(p, float), home, top_down=True)[1]

def yaw_window(p):
    ok = []
    saved = (kin.hint, kin.w_hint)
    for deg in range(-180, 180, 15):
        f = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg)), 0.0])
        kin.hint, kin.w_hint = f, 3.0
        q, good, err, tilt = kin.solve(side, np.asarray(p, float), home, top_down=True)
        if good:
            kin._fk(q)
            x = kin.data.oMf[kin.palm[side]].rotation[:, 0]
            a = np.degrees(np.arctan2(x[1], x[0])) - deg
            if abs((a + 180) % 360 - 180) <= 12:
                ok.append(deg)
    kin.hint, kin.w_hint = saved
    return ok

print("arm:", side, "| lid top z %.3f | object centre at release z %.3f, at approach z %.3f" % (lid_top, lid_top + half + 0.01, lid_top + half + 0.03))
print("%-6s | %-34s | %-34s | %-34s" % ("closer", "triangle hole (x at d=0: %.3f)" % holes["triangle"][0],
                                        "circle hole (x %.3f, y %.2f)" % tuple(holes["cylinder"]), "square hole (x %.3f, y %.2f)" % tuple(holes["cube"])))
for d in (0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12):
    row = []
    for k in ("triangle", "cylinder", "cube"):
        x, y = holes[k][0] - d, holes[k][1]
        r1 = reach([x, y, lid_top + half + 0.01]); r3 = reach([x, y, lid_top + half + 0.03])
        if r1 and r3:
            w = yaw_window([x, y, lid_top + half + 0.01])
            row.append("reach; fingers %s" % (("%d..%d deg (%d of 24)" % (min(w), max(w), len(w))) if w else "no direction held"))
        else:
            row.append("no (release %s, approach %s)" % ("ok" if r1 else "no", "ok" if r3 else "no"))
    print("%3.0f cm | %-34s | %-34s | %-34s" % (100 * d, *row))
