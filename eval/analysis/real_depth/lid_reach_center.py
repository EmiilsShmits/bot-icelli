"""Rung 3 with the real lid (lid_shape_holes_200mm.stl, on the MIDDLE box): which holes can a held object reach?

Hole centres from the STL (mm from the lid centre): square (-48, -35), circle (+48, -35), triangle (0, +39.3).
How the lid is turned on the box is not known, so all four turns are tried. Two geometries:
  sim   Aalto's scene.yaml, upright robot, boxes d cm closer to the robot than scene.yaml (0.40 m near edge)
  real  the table frame of a drop-3 frame where the arm fit worked (V16_CALIB=lean: torso leaning ~15 deg), boxes
        where they stood in drop 3 (d = 0) or glued d cm closer; IK moved into that frame (handeye.set_kin_base)
A hole counts as reached when Aalto's IK holds the object's centre over it, top-down (<= 25 deg tilt), with the
object's bottom 1 cm and 3 cm above the lid, with either arm.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lid_reach_center.py \
        artifacts/urdf/g1_body29_hand14.urdf [artifacts/real_frames/drop3 ep ...]
"""
import sys

import numpy as np
from aaltonomous.baselines.classical.config import home_arm, load_config
from aaltonomous.baselines.classical.kinematics import ArmKinematics
from aaltonomous.scene.scene import Scene

HOLES = {"square": (-0.048, -0.035), "circle": (0.048, -0.035), "triangle": (0.0, 0.0393)}   # lid frame (STL x, y), m
WALL, PLATE = 0.07, 0.004                # real box wall (measured 7-7.3 cm) and lid plate thickness
TURNS = {"triangle near": 180, "triangle far": 0, "triangle left": 90, "triangle right": -90}   # STL +y -> pelvis

urdf = sys.argv[1]
cfg = load_config()
sc = Scene.load()
home = home_arm(cfg)
cx, cy = sc.mat_to_pelvis(np.r_[sc.cfg["bins"]["centers"]["center"], 0.0])[:2]
z_lid = sc.counter_z + WALL + PLATE
half = sc.object_height() / 2


def hole_xy(name, turn_deg, d):
    """Pelvis / table xy of a hole: STL +y points away from the robot at turn 0."""
    hx, hy = HOLES[name]
    a = np.radians(turn_deg)
    # STL (x, y) -> pelvis (forward, left): at turn 0, STL +y = forward (+x pelvis), STL +x = robot's right (-y pelvis)
    fwd, left = hy, -hx
    return np.array([cx - d + np.cos(a) * fwd - np.sin(a) * left, cy + np.sin(a) * fwd + np.cos(a) * left])


def reached(kin, xy):
    arms = []
    for side in ("left", "right"):
        if all(kin.solve(side, np.r_[xy, z_lid + half + dz], home, top_down=True)[1] for dz in (0.01, 0.03)):
            arms.append(side[0].upper())
    return "".join(arms) or "--"


def table(kin, title, shifts):
    print(f"\n{title}\n(L / R = arm that reaches it, -- = neither)")
    print("%-15s %-9s" % ("lid turned", "closer") + "".join("%-10s" % k for k in HOLES))
    for turn, deg in TURNS.items():
        for d in shifts:
            print("%-15s %2.0f cm    " % (turn, 100 * d) + "".join("%-10s" % reached(kin, hole_xy(k, deg, d)) for k in HOLES))


table(ArmKinematics(cfg, urdf=urdf), "SIM geometry (scene.yaml, upright robot), lid on the middle box", (0.0, 0.03, 0.05, 0.07))

if len(sys.argv) > 3:
    from aaltonomous.interface.calibration import Calibration
    from decision_oracle import camera as C
    from decision_oracle.handeye import HandEye, set_kin_base
    src = sys.argv[2]
    cal, he, st = Calibration.load(), HandEye(), np.load(f"{src}/state0.npy")
    for ep in [int(e) for e in sys.argv[3:]]:
        depth = np.load(f"{src}/depth_ep{ep:02d}_start.npy").astype(np.uint16)
        s2 = Scene.load()
        s2.cfg["bins"]["wall_height"] = WALL
        fit = C.fit_head_pose(depth, cal, s2, lean=(he, st[ep, :14], st[ep, 14:]))
        if fit.base is None:
            print(f"\nREAL ep{ep:02d}: arm fit failed ({(fit.arm_pose or {}).get('why')}), skipped")
            continue
        kin = ArmKinematics(cfg, urdf=urdf)
        set_kin_base(kin, fit.base)
        table(kin, f"REAL geometry, drop-3 ep{ep:02d} (lean {fit.arm_pose['lean_deg']} deg, boxes as in drop 3 = 0 cm)", (0.0, 0.03, 0.05, 0.07))
