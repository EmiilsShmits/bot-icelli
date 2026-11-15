"""Runtime patches for Aalto's evaluator (aaltonomous.sim.evaluate) in our Modal runs; their file stays unchanged.

modal_sim.py's eval command runs `eval_patches.install(E)` before `E.main(...)`.

An arm caught at sim start (home_arms). The sim starts with both arms near the joint-zero pose (probe below, Modal
t3-probe-a, Sun 15 Nov): the evaluator's homing then raises them to the sim home pose (layout.ARM_HOME). In the rung-3
scene as we asked for it (scene_variant.py --task3 request) the left hand's zero pose overlaps the lid plate, so that
hand starts caught under the lid and the homing cannot raise it ("[evaluate] warning: arms 0.40 rad from home after
homing" before every trial of t3-v16-b; lifting it with IK did not free it either). The policy then ran every episode
with that arm stuck. Here, when the homing leaves an arm more than 0.1 rad from home, the sim is told to reset the
whole scene (rt/reset_pose/cmd category 2: joints set to the robot's default pose, objects to their defaults) and the
homing runs again. Nothing changes when the homing works (every sorting run so far).
"""
from __future__ import annotations

import time

import numpy as np

TOL = 0.1                                           # rad: the evaluator's own "not home" threshold


def install(E):
    orig = E.home_arms

    def home_arms(env, sc, vmax=0.6, hold_s=0.5):
        err = orig(env, sc, vmax, hold_s)
        if err <= TOL:
            return err
        try:
            reset_all()
            err2 = orig(env, sc, vmax, hold_s)
        except Exception as e:                       # keep the evaluator's own result
            print(f"[eval_patches] arms {err:.2f} rad from home; the scene reset failed: {e!r}", flush=True)
            return err
        print(f"[eval_patches] arms {err:.2f} rad from home after homing (an arm caught at sim start); after a scene "
              f"reset {err2:.2f} rad", flush=True)
        return err2

    E.home_arms = home_arms


def reset_all(wait_s=1.5):
    """rt/reset_pose/cmd "2": the sim resets every asset to its default state (unitree_sim_isaaclab sim_main.py,
    event reset_all_self). Needs the DDS channel factory, which the evaluator's backend has set up."""
    from unitree_sdk2py.core.channel import ChannelPublisher
    from unitree_sdk2py.idl.std_msgs.msg.dds_ import String_

    pub = ChannelPublisher("rt/reset_pose/cmd", String_)
    pub.Init()
    time.sleep(0.3)                                  # let discovery match the sim's reader
    for _ in range(3):
        pub.Write(String_(data="2"))
        time.sleep(0.1)
    time.sleep(wait_s)


def probe(task="insert_shapes", hold_s=3):
    """Where are the arms right after a client connects, while nothing is commanded, after Aalto's homing, and after
    a scene reset plus homing?
    modal_sim.py --action sh --task Aalto-Insert-G129-Dex3-Joint --look none --variant "--task3 request"
                  --script "aalto sim && python /opt/sim/eval_patches.py" """
    import ssl  # noqa: F401  before any DDS import, as in evaluate.py

    from aaltonomous.interface.env import AaltoEnv
    from aaltonomous.sim import evaluate as E
    from aaltonomous.sim.scene_client import SceneClient

    np.set_printoptions(precision=2, suppress=True, linewidth=160)
    E.apply_instance_env()
    sc = SceneClient("127.0.0.1")
    t0 = time.monotonic()
    env = AaltoEnv(backend="sim", task=task, seed=0, time_limit=60.0, realtime=True, img_server_ip="127.0.0.1",
                   head_rgbd=False, cameras=False)
    q = env.backend.joints()[0]
    print(f"[probe] connected after {time.monotonic() - t0:.1f} s: L {q[:7]}  R {q[7:]}", flush=True)
    for k in range(hold_s):
        time.sleep(1.0)
        print(f"[probe] +{k + 1} s, nothing commanded: L {env.backend.joints()[0][:7]}", flush=True)
    err = E.home_arms(env, sc)
    print(f"[probe] after Aalto's home_arms: {err:.2f} rad from home, L {env.backend.joints()[0][:7]}", flush=True)
    reset_all()
    q = env.backend.joints()[0]
    print(f"[probe] right after a scene reset: L {q[:7]}  R {q[7:]}", flush=True)
    err = E.home_arms(env, sc)
    print(f"[probe] after the reset + home_arms: {err:.2f} rad from home, L {env.backend.joints()[0][:7]}", flush=True)


if __name__ == "__main__":
    probe()
