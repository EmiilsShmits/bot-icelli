"""Near-body triangle sweep in the Aalto sim: one standing triangle per episode, close to the robot (where top-down
grasps can barely turn the hand), full v1.6 policy (camera, planner, chooser, retries; no API calls), V16_NEAR from
the environment (off | relay | push, decision_oracle/near_v16.py). Copied from ridge_sweep.py.

On Modal (venue look):
    modal run sim/modal_sim.py --action sh --tag near-push --script \
      "aalto sim && cd /opt/bot/policy && PYTHONPATH=/opt/aalto:/opt/bot/policy V16_NEAR=push \
       python -m decision_oracle.near_sweep --out /opt/aalto/runs/near.json"

Per episode: position, layout yaw, every executed move (arm / grasp / route) with its grasp check, where the object
ended (bin / counter) and its pose before and after.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

COLOUR = {"left": "red", "right": "blue"}      # sort_fixed: red -> left bin, blue -> right bin (bin on the object's side)
# (mat x, mat y, layout yaw deg): pelvis x = mat y + 0.14 (0.18-0.21 m in front), pelvis y = mat x - 0.45
CASES = [(0.52, 0.04, 60.0), (0.52, 0.04, 90.0), (0.39, 0.06, 30.0), (0.52, 0.07, 60.0), (0.39, 0.06, 0.0)]


def _pose(sc):
    o = next((o for o in sc.state()["objects"] if o["active"]), None)
    if o is None:
        return None
    q = o["quat_xyzw"]
    R = _rot(q)
    tilt = float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))
    return {"pos": [round(float(v), 4) for v in o["pos"]], "tilt_deg": round(tilt, 1),
            "axis_yaw_deg": round(float(np.degrees(np.arctan2(R[1, 2], R[0, 2]))), 1)}


def _rot(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=50.0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)

    from aaltonomous.deploy.runner import Recorder, run_episode
    from aaltonomous.interface import env as env_mod
    from aaltonomous.interface.env import AaltoEnv
    from aaltonomous.sim import evaluate as ev
    from aaltonomous.sim.scene_client import SceneClient

    from .upgrades_v16 import V16OraclePolicy

    ev.apply_instance_env()
    sc = SceneClient(a.host)
    env = AaltoEnv(backend="sim", task="sort_fixed", seed=0, time_limit=a.time_limit, realtime=True,
                   img_server_ip=a.host, head_rgbd=True, cameras=False,
                   head_rgbd_port=int(os.environ.get("AALTO_RGBD_PORT", "55560")))
    L = env.scene.cfg["layout"]
    W = float(env.scene.cfg["counter"]["mat_size"][0])
    tmp = Path(tempfile.mkdtemp(prefix="ridge_sweep_"))
    dlog = str(Path(a.out).with_suffix(".decisions.jsonl"))
    print(f"[near_sweep] V16_NEAR={os.environ.get('V16_NEAR', 'off')} region_x {L['region_x']} region_y {L['region_y']}", flush=True)
    rows, stop = [], threading.Event()
    try:
        for i, (x, y, yaw) in enumerate(CASES):
            arm = "left" if x > W / 2 else "right"
            lay = [{"color": COLOUR[arm], "shape": "triangle", "x": x, "y": y, "yaw": float(np.radians(yaw))}]
            env_mod.sample_layout = lambda rng, _l=lay, **kw: [dict(o) for o in _l]
            ev.home_arms(env, sc)
            pol = V16OraclePolicy(SceneClient(a.host), sides="off", perception="camera", grasp_check="on",
                                  dlog=dlog, threaded=True, safety=env.filter.cfg, labels="off", instruction="rules",
                                  time_limit=a.time_limit, log=None)
            pol.episode_seed, pol.task = 9000 + i, "sort_fixed"
            client = ev.LocalClient(pol)
            trace, tr_stop = [], threading.Event()

            def tracer():
                t0 = time.monotonic()
                tsc = SceneClient(a.host)
                while not tr_stop.is_set():
                    p = _pose(tsc)
                    if p:
                        trace.append({"t": round(time.monotonic() - t0, 2), **p})
                    time.sleep(0.25)
            threading.Thread(target=tracer, daemon=True).start()
            before = None
            try:
                summ, _ = run_episode(env, client, i, 9000 + i, Recorder(tmp / f"ep{i:03d}"), stop, "sort_fixed")
            finally:
                tr_stop.set()
                client.close()
            ev.settle(sc, 3.0, float(env.scene.cfg["success"]["at_rest_speed"]))
            out = sc.evaluate("sort_fixed", env.mapping)["outcomes"][0]["outcome"]
            before = trace[0] if trace else None
            after = _pose(sc)
            picks = [r for r in _read(dlog) if r.get("seed") == 9000 + i]
            ex = [r for r in picks if r.get("type") == "exec"]
            gc = [r for r in picks if r.get("type") == "grasp_check"]
            looks = [r for r in picks if r.get("type") == "look"]
            det = (looks[0]["dets"][0] if looks and looks[0].get("dets") else {})
            gcd = {g.get("decision"): g for g in gc}
            moves = [f"{e['option']['arm'][0]}/{e['option']['grasp']}/{e['option']['route']}"
                     + {True: ":E", False: ":H"}.get(gcd.get(e["decision"], {}).get("empty"), "")
                     for e in ex]
            r = {"i": i, "x": x, "y": y, "layout_yaw": yaw, "seen_xy": det.get("xy"), "seen_yaw_deg": det.get("yaw_deg"),
                 "moves": moves, "outcome": out, "end": summ.get("end_reason"), "sim_s": summ.get("sim_s"),
                 "before": before, "after": after, "trace": trace}
            rows.append(r)
            print(f"{i:3d} mat ({x:.2f},{y:.2f}) yaw={yaw:+4.0f} seen={det.get('xy')} moves={moves} -> {out} "
                  f"({summ.get('sim_s')} s)", flush=True)
            json.dump(rows, open(a.out, "w"), indent=1, default=str)
    finally:
        env.close()
    print(f"[near_sweep] V16_NEAR={os.environ.get('V16_NEAR', 'off')}: sorted "
          f"{sum(r['outcome'] == 'correct' for r in rows)}/{len(rows)}")
    return 0


def _read(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
