"""Put the sim robot into a recorded real joint pose, to compare sim and real camera images like for like.

    # on the sim machine, sim running, venue_env.sh sourced:
    bash aaltonomous/cloud/aalto.sh py pose_from_real.py poses.json <key>
    bash aaltonomous/cloud/aalto.sh snap --out /root/snap_pose

poses.json maps a key to 28 joint values (one row of observation.state from a real dataset: 14 arm + 14 hand).
The script resets the episode (new object layout), ramps there under the speed caps, holds 1.5 s and exits;
the robot stays in the pose until the next reset.
"""
import json, os, ssl, sys, time  # noqa
import numpy as np
from aaltonomous.baselines.classical.planner import ramp
from aaltonomous.interface.env import AaltoEnv
from aaltonomous.sim.evaluate import apply_instance_env
q = np.array(json.load(open(sys.argv[1]))[sys.argv[2]], float)
apply_instance_env()
env = AaltoEnv(backend="sim", task="sort_fixed", realtime=True, img_server_ip="127.0.0.1", cameras=False, time_limit=300.0)
env.filter.cfg.max_clipped_steps = 100000
env.reset()
arm_q, hand_q = env.filter.arm_cmd.copy(), env.filter.hand_cmd.copy()
RA, RH = ramp(arm_q, q[:14], 0.5, env.dt), ramp(hand_q, q[14:], 1.0, env.dt)
n = max(len(RA), len(RH), 1) + 45
pad = lambda R, x: np.vstack([R, np.repeat(x[None], n - len(R), 0)]) if len(R) else np.repeat(x[None], n, 0)
clips = 0
for ar, hr in zip(pad(RA, q[:14]), pad(RH, q[14:])):
    _, info = env.step({"arm_q_target": ar, "hand_q_target": hr}); clips += info["clipped"]
arm_q, _, hand_q = env.backend.joints()
print("clipped", clips, "arm err", np.abs(arm_q - q[:14]).max().round(3), "hand err", np.abs(hand_q - q[14:]).max().round(3))
sys.stdout.flush(); os._exit(0)
