"""Ridge-grasp sweep in the Aalto sim: one lying triangular prism per episode, one pick with a forced arm, v1.5's
camera perception + planner (V15OraclePolicy), the hand shift from V15_RIDGE_SHIFT. Like Aalto's
aaltonomous/sim/grasp_test.py, plus: the arm is forced, the object is traced through the pick, and the grasp check's
result is recorded.

Needs the sim with lying prisms (modal_pipeline/sim/scene_variant.py --tip triangles). On Modal:
    modal run sim/modal_sim.py --action sh --variant "--tip triangles" --tag ridge-s18-0 --script \
      "aalto sim && cd /opt/bot/policy && PYTHONPATH=/opt/aalto:/opt/bot/policy V15_RIDGE_SHIFT=18,0 \
       python -m decision_oracle.ridge_sweep --out /opt/aalto/runs/ridge.json"

Per episode: arm, position, layout yaw, the ridge yaw the camera saw, the planned finger direction, whether the hand
closed on something (grasp check), where the object ended (bin / counter), and its pose before and after the pick.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

COLOUR = {"left": "red", "right": "blue"}      # sort_fixed: red -> left bin, blue -> right bin (bin on the arm's side)


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
    ap.add_argument("--arms", default="left,right")
    ap.add_argument("--yaws", default="-40,0,40", help="layout yaw, deg, mat frame; mirrored for the right arm")
    ap.add_argument("--spots", default="0.52:0.07,0.58:0.15",
                    help="left-arm object spots, mat x:y (m; mat x = pelvis y + 0.45, mat y = pelvis x - 0.14); the "
                         "right arm gets their mirror images (mat x -> 0.90 - x), so both arms see the same picks")
    ap.add_argument("--time-limit", type=float, default=30.0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)

    from aaltonomous.deploy.runner import Recorder, run_episode
    from aaltonomous.interface import env as env_mod
    from aaltonomous.interface.env import AaltoEnv
    from aaltonomous.sim import evaluate as ev
    from aaltonomous.sim.scene_client import SceneClient

    from . import upgrades_v15 as U

    class ForcedPlanner(U.SidedPlanner):
        force = None

        def side_ok(self, det, side, bin_name, place_xy=None):
            if self.force and side != self.force:
                return False, f"sweep: {self.force} arm only"
            return super().side_ok(det, side, bin_name, place_xy)

    ev.apply_instance_env()
    sc = SceneClient(a.host)
    env = AaltoEnv(backend="sim", task="sort_fixed", seed=0, time_limit=a.time_limit, realtime=True,
                   img_server_ip=a.host, head_rgbd=True, cameras=False,
                   head_rgbd_port=int(os.environ.get("AALTO_RGBD_PORT", "55560")))
    L = env.scene.cfg["layout"]
    W = float(env.scene.cfg["counter"]["mat_size"][0])
    spots = [tuple(float(v) for v in sp.split(":")) for sp in a.spots.split(",")]
    tmp = Path(tempfile.mkdtemp(prefix="ridge_sweep_"))
    dlog = str(Path(a.out).with_suffix(".decisions.jsonl"))
    print(f"[ridge_sweep] shift {U.RIDGE_SHIFT_MM} region_x {L['region_x']} region_y {L['region_y']}", flush=True)
    rows, stop = [], threading.Event()
    cases = []
    for arm in a.arms.split(","):
        for yaw, (x, y) in itertools.product([float(v) for v in a.yaws.split(",")], spots):
            cases.append((arm, yaw, x, y) if arm == "left" else (arm, -yaw, W - x, y))
    try:
        for i, (arm, yaw, x, y) in enumerate(cases):
            lay = [{"color": COLOUR[arm], "shape": "triangle", "x": x, "y": y, "yaw": float(np.radians(yaw))}]
            env_mod.sample_layout = lambda rng, _l=lay, **kw: [dict(o) for o in _l]
            ev.home_arms(env, sc)
            pol = U.V15OraclePolicy(SceneClient(a.host), sides="off", perception="camera", grasp_check="on",
                                    max_tries=1, dlog=dlog, threaded=True, safety=env.filter.cfg,
                                    time_limit=a.time_limit, log=None)
            for pl in (pol.planner, pol.relay):
                pl.__class__ = ForcedPlanner
                pl.force = arm
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
            r = {"i": i, "arm": arm, "layout_yaw": yaw, "x": x, "y": y, "shift_mm": U.RIDGE_SHIFT_MM[arm],
                 "seen_yaw_deg": det.get("yaw_deg"), "seen_xy": det.get("xy"),
                 "grasp": ex[0]["option"]["grasp"] if ex else None, "arm_used": ex[0]["option"]["arm"] if ex else None,
                 "finger_deg": ex[0]["option"].get("finger_deg") if ex else None,
                 "reason": ex[0]["option"].get("reason") if ex else None,
                 "held": (not gc[0]["empty"]) if gc else None, "outcome": out, "end": summ.get("end_reason"),
                 "before": before, "after": after, "trace": trace}
            rows.append(r)
            print(f"{i:3d} {arm:5s} yaw={yaw:+4.0f} x={x:.2f} y={y:.2f} seen={r['seen_yaw_deg']} "
                  f"grasp={r['grasp']} finger={r['finger_deg']} held={r['held']} -> {out}", flush=True)
            json.dump(rows, open(a.out, "w"), indent=1, default=str)
    finally:
        env.close()
    for arm in a.arms.split(","):
        rr = [r for r in rows if r["arm"] == arm]
        ridge = [r for r in rr if r["grasp"] == "face"]
        print(f"{arm}: ridge grasps held {sum(bool(r['held']) for r in ridge)}/{len(ridge)}, "
              f"sorted {sum(r['outcome'] == 'correct' for r in rr)}/{len(rr)}")
    return 0


def _read(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
