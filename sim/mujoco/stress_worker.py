"""One worker of a MuJoCo stress run on a plain Linux machine (e.g. a Verda GPU box): takes episodes from a shared
queue (an atomic mkdir per episode id under OUT/claims/), and for each one starts its own policy server (its own
decision log), runs run.py --dr, and appends a result line to OUT/all.jsonl (the same lines as
modal_mujoco.py::stress, so stress_report.py reads both). Run several workers per machine, each on its own ports.

    python sim/mujoco/stress_worker.py --run stress-a --n 200 --worker 0 --machine 0 --machines 2
        # episodes id with id % machines == machine; ports 8100+worker (policy) and 8180+worker (live feed)

The episode list (seed, randomisation seed, task) depends only on --n, --seed0 and --language, so every worker on
every machine sees the same list.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def make_specs(n, seed0=5000, language=0.4, policy="v1.6", rtf=0.4, modes=("all",), calibs=(None,)):
    """With several dr modes and/or calibration settings (V16_CALIB), episodes come in groups of
    len(modes) * len(calibs) that share the seed (same layout, task and random draws), so they compare pairwise."""
    rnd = random.Random(seed0)
    combos = [(m, c) for c in calibs for m in modes]
    specs = []
    for i in range(n):
        g = i // len(combos)
        if i % len(combos) == 0:
            task = "sort_language" if rnd.random() < language else "sort_fixed"
        mode, calib = combos[i % len(combos)]
        sp = {"id": i, "seed": seed0 + g, "dr": seed0 + g, "mode": mode, "policy": policy, "rtf": rtf, "task": task}
        if calib:
            sp["calib"] = calib
        specs.append(sp)
    return specs


def log_stats(path):
    """Counts from the policy's decision log: Decision calls answered / missing, grasps tried / empty."""
    st = {"labels": 0, "d1_ok": 0, "d1_missing": 0, "grasps": 0, "empty": 0}
    try:
        for ln in open(path):
            d = json.loads(ln)
            if d.get("type") == "labels":
                for r in d.get("rows", []):
                    st["labels"] += 1
                    st["d1_ok" if r.get("d1") else "d1_missing"] += 1
            if "grasp" in d and "obj" in d:
                st["grasps"] += 1
            if "empty" in d:
                st["empty"] += bool(d.get("empty"))
    except FileNotFoundError:
        pass
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--language", type=float, default=0.4)
    ap.add_argument("--policy", default="v1.6")
    ap.add_argument("--rtf", type=float, default=0.4)
    ap.add_argument("--modes", default="all", help="comma list of dr.py modes, e.g. none,camera,bins (paired)")
    ap.add_argument("--calibs", default="", help="comma list of V16_CALIB settings, e.g. bins,hands (paired); an entry KEY=VAL[+KEY=VAL] sets "
                    "those environment variables instead, e.g. V16_TRI=off,V16_TRI=mid")
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--machine", type=int, default=0)
    ap.add_argument("--machines", type=int, default=1)
    ap.add_argument("--out", default=None, help="default artifacts/eval/mujoco/<run>")
    a = ap.parse_args()
    out_root = Path(a.out or ROOT / "artifacts" / "eval" / "mujoco" / a.run)
    (out_root / "claims").mkdir(parents=True, exist_ok=True)
    pport, lport = 8100 + a.worker, 8180 + a.worker
    modes, calibs = tuple(a.modes.split(",")), tuple(a.calibs.split(",")) if a.calibs else (None,)
    group = len(modes) * len(calibs)        # episodes that share a seed stay on one machine (a fair pairwise comparison)
    specs = [s for s in make_specs(a.n, a.seed0, a.language, a.policy, a.rtf, modes, calibs)
             if (s["id"] // group) % a.machines == a.machine]
    for spec in specs:
        try:
            os.mkdir(out_root / "claims" / f"{spec['id']:03d}")          # atomic: one worker per episode
        except FileExistsError:
            continue
        tag = f"{a.run}/{spec['id']:03d}"
        out = ROOT / "artifacts" / "eval" / "mujoco" / tag
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, V15_DLOG=str(out / f"decisions_{spec['policy']}.jsonl"))
        for c in str(spec.get("calib") or "").split("+"):     # "bins" -> V16_CALIB=bins; "V16_TRI=mid+V16_X=1" -> those
            if "=" in c:
                k, v = c.split("=", 1)
                env[k] = v
            elif c:
                env["V16_CALIB"] = c
        t0 = time.time()
        slog = open(out / "server.log", "w")
        server = subprocess.Popen([sys.executable, str(HERE / "serve.py"), "--", "--policy", spec["policy"],
                                   "--port", str(pport)], env=env, stdout=slog, stderr=subprocess.STDOUT, cwd=ROOT)
        rc = None
        try:
            for _ in range(240):
                time.sleep(0.5)
                if "listening" in (out / "server.log").read_text():
                    break
            with open(out / "run.log", "w") as rlog:
                rc = subprocess.run([sys.executable, str(HERE / "run.py"), "--tag", tag, "--task", spec["task"],
                                     "--seed", str(spec["seed"]), "--trials", "1", "--dr", str(spec["dr"]), "--dr-mode", spec.get("mode", "all"),
                                     "--rtf", str(spec["rtf"]), "--policy", f"ws://localhost:{pport}",
                                     "--video", "--live", str(lport)],
                                    env=env, cwd=ROOT, stdout=rlog, stderr=subprocess.STDOUT, timeout=30 * 60).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        finally:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
            slog.close()
        res = {"id": spec["id"], "spec": spec, "rc": rc, "host": os.uname().nodename, "worker": a.worker,
               "wall_s": round(time.time() - t0, 1)}
        try:
            res["trial"] = json.loads((out / "eval.json").read_text())["trials"][0]
        except Exception as e:
            res["error"] = repr(e)
        res["log"] = log_stats(out / f"decisions_{spec['policy']}.jsonl")
        (out / "result.json").write_text(json.dumps(res, default=str))
        with open(out_root / "all.jsonl", "a") as f:
            f.write(json.dumps(res, default=str) + "\n")
        t = res.get("trial") or {}
        print(f"[w{a.worker}] id {spec['id']:03d} {spec['task']}: {t.get('n_correct')}/{t.get('n_objects')} "
              f"hz {t.get('command_hz')} wall {res['wall_s']} s", flush=True)


if __name__ == "__main__":
    main()
