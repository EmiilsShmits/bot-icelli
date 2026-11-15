"""Score a policy server in the MuJoCo venue scene, the way Aalto's sim/evaluate.py does in Isaac: same episode loop
(aaltonomous.deploy.runner.run_episode over the WebSocket), same safety filter, same gate (0 clipped steps, >= 27 Hz),
same scorer (aalto_task.layout.evaluate) and the same eval.json format (policy/decision_oracle/modal_runs/summarize.py
reads it with V15_RUNS=artifacts/eval/mujoco).

    # terminal 1: the policy, as in the finals (key from .env for v1.6)
    PYTHONPATH=third_party/aaltonomous-humanoid V15_DLOG=artifacts/eval/mujoco/v16-fixed/decisions_v1.6.jsonl \
        .venv/bin/python policy/server.py --policy v1.6
    # terminal 2: the sim (mjpython for the live window on macOS)
    PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/mjpython sim/mujoco/run.py --tag v16-fixed \
        --task sort_fixed --seed 1000 --trials 6 --viewer --video

Per trial: layout from the seed (same layouts as the Isaac venue runs), episode, 3 s settle, score.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend import MujocoBackend                                  # noqa: E402
from aaltonomous.deploy.runner import PolicyClient, Recorder, run_episode   # noqa: E402
from aaltonomous.interface.env import AaltoEnv                     # noqa: E402
from aaltonomous.sim import evaluate as EV                          # noqa: E402
from aaltonomous.sim.aalto_task import layout as LAY               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="ws://localhost:8000")
    ap.add_argument("--task", default="sort_fixed", choices=["sort_fixed", "sort_language"])
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--tag", default=None, help="output folder name under artifacts/eval/mujoco/")
    ap.add_argument("--colors", default="venue", help="venue (default) | sim | real_camera (venue_measured.yaml)")
    ap.add_argument("--time-limit", type=float, default=120.0)
    ap.add_argument("--viewer", action="store_true", help="live MuJoCo window (macOS: run with mjpython)")
    ap.add_argument("--video", action="store_true", help="head camera | overview mp4 per episode (10 fps)")
    ap.add_argument("--rtf", type=float, default=0.4,
                    help="run on a sim clock at this real-time factor, as Aalto's Isaac sim does (0.27-0.45 in our Modal runs); "
                         "rates and the gate then count sim seconds. 0 = wall time (the real-robot timing)")
    ap.add_argument("--dr", type=int, default=None, help="domain randomisation seed (dr.py): one random variant of "
                    "the scene for this run (colours, lights, camera, table, bins, friction, mass, lying prisms)")
    ap.add_argument("--dr-mode", default="all", help="dr.py mode: all | camera | bins | none")
    ap.add_argument("--live", type=int, default=0, help="serve a live feed (MJPEG) on this port, e.g. 8080")
    ap.add_argument("--team", default="bot-icelli")
    ap.add_argument("--startup-timeout", type=float, default=120.0)
    ap.add_argument("--gate-max-clips", type=int, default=0)
    ap.add_argument("--gate-min-hz", type=float, default=27.0)
    a = ap.parse_args(argv)
    a.container = None                    # fields EV.summarize reads

    tag = a.tag or f"{a.task}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = ROOT / "artifacts" / "eval" / "mujoco" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg, colors, tip, dr_params = None, a.colors, False, None
    if a.dr is not None:
        import build as B
        import dr as DR
        cfg, colors, tip, dr_params = DR.sample(B.load_cfg(), a.dr, a.dr_mode)
        print(f"dr {a.dr}: {dr_params}", flush=True)
    be = MujocoBackend(cfg=cfg, colors=colors, viewer=a.viewer, overview=a.video or bool(a.live), rtf=a.rtf or None,
                       tip=tip)
    env = AaltoEnv(backend="mock", task=a.task, seed=a.seed, time_limit=a.time_limit, realtime=True)
    env.backend.close()
    env.backend, env.scene = be, be.sc    # measured geometry: layouts (venue region) and scoring
    env.clock = be.clock                  # sim clock (as Isaac) or None (wall time)
    variant = (f"mujoco-dr{a.dr}" if a.dr is not None else f"mujoco-{a.colors}") + (f"-rtf{a.rtf:g}" if a.rtf else "-wall")
    live = None
    if a.live:
        from live import Live
        live = Live(be, a.live)
        live.status = {"tag": tag, "task": a.task, "rtf": a.rtf, "dr": dr_params, "state": "waiting for the policy server"}
    client = PolicyClient(a.policy, a.startup_timeout)
    print(f"policy: {client.metadata}  -> {out_dir}", flush=True)
    trials, stop = [], threading.Event()
    rest = float(be.sc.cfg["success"]["at_rest_speed"])
    good = be.sc.cfg["scoring"][a.task]["correct"]
    try:
        for i in range(a.trials):
            seed = a.seed + i
            env.rng = np.random.default_rng(seed)
            rec = Recorder(out_dir / f"episode_{i:03d}")
            be.video = [] if a.video else None
            if live:
                live.status.update(state="running", trial=i, seed=seed)
            t0 = time.monotonic()
            try:
                summary, events = run_episode(env, client, i, seed, rec, stop, a.task)
            except KeyboardInterrupt:
                stop.set()
                summary, events = {"episode": i, "seed": seed, "end_reason": "interrupted"}, list(env.filter.events)
            except Exception as e:
                traceback.print_exc()
                summary, events = {"episode": i, "seed": seed, "end_reason": "crash", "error": repr(e),
                                   "safety": env.filter.summary()}, list(env.filter.events)
            settled = 0.0
            while settled < 6.0:          # at most 6 s: until every object is at rest (3 s minimum, as Aalto)
                be.settle(0.5)
                settled += 0.5
                if settled >= 3.0 and all(o["speed"] < rest for o in be.state() if o["active"]):
                    break
            objs = be.state()
            ev = LAY.evaluate(be.sc, a.task, objs, env.mapping)
            outc = [o["outcome"] for o in ev["outcomes"]]
            final = [{"name": o["name"], "pos": o["pos"], "speed": o["speed"]} for o in objs if o["active"]]
            trial = {**summary, "seed": seed, "task": a.task, "variant": variant, "layout": env.layout,
                     "mapping": env.mapping, "outcomes": ev["outcomes"], "score": ev["score"],
                     "max_score": good * len(outc), "n_objects": len(outc), "n_correct": outc.count("correct"),
                     "all_correct": ev["all_correct"], "settle_s": settled,
                     "episode_wall_s": round(time.monotonic() - t0, 1), "final_objects": final, "dr": dr_params}
            trial["gate_ok"], trial["gate_why"] = EV.gate_ok(trial, a.gate_max_clips, a.gate_min_hz)
            if events or summary.get("end_reason") != "done":
                trial["safety_events"] = events[:20]
            rec.save(events, trial)
            trials.append(trial)
            if live:
                live.status.setdefault("results", []).append(
                    f"seed {seed}: {trial['n_correct']}/{trial['n_objects']}  hz {trial.get('command_hz')}  "
                    f"{'gate ok' if trial['gate_ok'] else 'gate FAIL'}  ({trial.get('instruction')})")
            if be.video:
                import imageio.v2 as iio
                iio.mimwrite(out_dir / f"episode_{i:03d}.mp4", be.video, fps=30 / be.video_every, quality=7)
            print(f"trial {i:3d} seed {seed:4d}: {trial['n_correct']}/{trial['n_objects']} correct  score "
                  f"{trial['score']:+d}/{trial['max_score']}  end={trial['end_reason']}  "
                  f"clips={(trial.get('safety') or {}).get('clipped_steps')}  hz={trial.get('command_hz')}  "
                  f"rt_hz={trial.get('policy_hz_rt')}  gate={'ok' if trial['gate_ok'] else 'FAIL ' + ','.join(trial['gate_why'])}"
                  f"  {[(o['name'][4:], o['outcome']) for o in ev['outcomes']]}", flush=True)
            if stop.is_set():
                break
    finally:
        client.close()
        env.close()
        if live:
            live.status["state"] = "done"

    res = EV.summarize(trials, a, variant, {"dr": None})
    (out_dir / "eval.json").write_text(json.dumps({"summary": res, "trials": trials}, indent=1, default=EV._js))
    EV.print_table(res)
    print(f"-> {out_dir / 'eval.json'}")
    return 0 if res.get("gate", {}).get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
