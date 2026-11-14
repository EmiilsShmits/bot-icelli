"""Where was the hand, really, when it closed? Forward kinematics on a recorded episode (episode_NNN.npz from Aalto's
evaluator: actual arm_q / hand_q and the commanded arm_q_cmd / hand_q_cmd at every tick).

    python grasp_geometry.py <episode.npz> <side> <t0> <t1> <obj_x> <obj_y> [label]

For the grasp in sim-time window [t0, t1] by arm <side>: finds the tick the fingers start closing, and prints, in
the pelvis frame, the palm / grasp point / fingertips from the ACTUAL joint angles and from the COMMANDED ones,
and each point's offset from the object centre (obj_x, obj_y). Runs where Aalto's classical package and Pinocchio
are installed (e.g. inside a bot-icelli/policy image).
"""
import sys

import numpy as np

from aaltonomous.baselines.classical.config import load_config
from aaltonomous.baselines.classical.kinematics import ArmKinematics

f, side, t0, t1, ox, oy = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:7])
label = sys.argv[7] if len(sys.argv) > 7 else ""
z = np.load(f)
t = z["t"]
sl = slice(0, 7) if side == "left" else slice(7, 14)
w = np.where((t >= t0) & (t <= t1))[0]
hc = z["hand_q_cmd"][:, sl]
moved = np.abs(hc[w] - hc[w[0]]).sum(axis=1)
# the hand opens (preshape) on the way down, then closes: take the tick after which it changes most quickly
dh = np.r_[0, np.abs(np.diff(hc[w], axis=0)).sum(axis=1)]
i_close = None
for k in range(len(w) - 15):
    seg = dh[k:k + 15].sum()
    if seg > 0.8 and moved[k] > 0.3:
        i_close = w[k]
        break
if i_close is None:
    i_close = w[int(np.argmax(dh))]
kin = ArmKinematics(load_config(None))
obj = np.array([ox, oy])
names = ["palm", "grasp point", "finger link", "finger link", "finger link", "tip", "tip", "tip"]
print(f"\n== {label} ({side} arm) window t {t0:.1f}-{t1:.1f}: fingers start closing at t = {t[i_close]:.2f} s")
for what, aq, hq in (("ACTUAL   ", z["arm_q"][i_close], z["hand_q"][i_close]),
                     ("COMMANDED", z["arm_q_cmd"][i_close], z["hand_q_cmd"][i_close])):
    P = kin.hand_points(side, aq, hq)
    g = P[1]
    print(f"  {what} grasp point ({g[0] * 100:6.1f}, {g[1] * 100:+6.1f}, z {g[2] * 100:5.1f}) cm; "
          f"offset from object centre ({(g[0] - ox) * 100:+5.1f}, {(g[1] - oy) * 100:+5.1f}) cm")
    tips = P[5:]
    print("            tips: " + "  ".join(f"({p[0] * 100:5.1f},{p[1] * 100:+5.1f},z{p[2] * 100:4.1f}) d={np.linalg.norm(p[:2] - obj) * 100:4.1f}"
                                         for p in tips))
a, c = z["arm_q"][i_close], z["arm_q_cmd"][i_close]
print(f"  arm tracking error at that tick: max {np.degrees(np.abs(a - c)[sl]).max():.2f} deg "
      f"(joint {int(np.argmax(np.abs(a - c)[sl]))} of the {side} arm)")
Pa = kin.hand_points(side, z["arm_q"][i_close], z["hand_q"][i_close])[1]
Pc = kin.hand_points(side, z["arm_q_cmd"][i_close], z["hand_q_cmd"][i_close])[1]
print(f"  grasp point actual - commanded: ({(Pa[0] - Pc[0]) * 100:+.1f}, {(Pa[1] - Pc[1]) * 100:+.1f}, {(Pa[2] - Pc[2]) * 100:+.1f}) cm")
