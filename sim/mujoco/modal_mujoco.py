"""The MuJoCo venue scene (sim/mujoco) on Modal, one container per configuration, each with a live feed.

Each container runs our policy server (policy/server.py through sim/mujoco/serve.py, port 8000) and run.py against
it, as batch.sh does on a laptop. run.py serves its live feed (head camera | third-person view, MJPEG) on port 8080,
and Modal exposes it through a tunnel. The links are printed and stored in the Modal Dict `mujoco-live`.
Results go to the Modal volume aalto-sim-out under mujoco/<tag>/ (eval.json in Aalto's format, episode logs, mp4s,
the policy's decision log).

    bash sim/mujoco/get_assets.sh && bash policy/get_urdf.sh          # once: G1/Dex3 MJCF + meshes, G1 URDF
    .venv/bin/modal run --detach sim/mujoco/modal_mujoco.py::batch             # the default batch (RUNS below)
    .venv/bin/modal run --detach sim/mujoco/modal_mujoco.py::batch --runs "v16-x v1.6 sort_fixed 1000 2 aalto"
    .venv/bin/modal run --detach sim/mujoco/modal_mujoco.py::stress --n 200    # random variants (dr.py), see below
    .venv/bin/python sim/mujoco/modal_mujoco.py links                          # print the live links again
    .venv/bin/modal volume get aalto-sim-out mujoco/<tag> artifacts/eval/mujoco/   # results

v1.6 calls Gemini Decision 1: GEMINI_API_KEY is read from this repo's .env on this computer and passed as a Modal
secret (never stored in the image or the volume), as modal_pipeline/sim/modal_sim.py does.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path("/opt/bot")   # in the container: /root/
BOT = "/opt/bot"
RUNS = """v16-fixed v1.6 sort_fixed 1000 6 aalto
v15off-fixed v1.5 sort_fixed 1000 6 aalto V15_SIDES=off
v16-fixed-geo v1.6 sort_fixed 1000 6 measured
v16-lang v1.6 sort_language 2000 3 aalto"""

IGN = ["**/__pycache__", "**/*.pyc", "**/*.md"]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libegl1", "libgl1", "libglvnd0", "libosmesa6", "ffmpeg")
    .pip_install("numpy==2.2.6", "scipy==1.15.2", "opencv-python-headless==4.10.0.84", "pyyaml", "msgpack",
                 "websockets>=12", "pin==3.3.1", "mujoco==4.0.1", "imageio[ffmpeg]", "pillow", "pyzmq")
    .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "NVIDIA_DRIVER_CAPABILITIES": "all",
          "PYTHONPATH": f"{BOT}/third_party/aaltonomous-humanoid"})
    .add_local_dir(ROOT / "third_party" / "aaltonomous-humanoid", f"{BOT}/third_party/aaltonomous-humanoid",
                   ignore=IGN + [".git", "**/.git"])
    .add_local_dir(ROOT / "policy", f"{BOT}/policy",
                   ignore=IGN + ["weights", "weights/**", "tests", "tests/**", "adk", "adk/**"])
    .add_local_dir(ROOT / "training" / "instruction_parser", f"{BOT}/training/instruction_parser",
                   ignore=IGN + ["**/*.jsonl", "data", "data/**"])
    .add_local_dir(ROOT / "artifacts" / "urdf", f"{BOT}/artifacts/urdf")
    .add_local_dir(ROOT / "artifacts" / "mujoco" / "g1", f"{BOT}/artifacts/mujoco/g1")
    .add_local_dir(ROOT / "sim" / "mujoco", f"{BOT}/sim/mujoco", ignore=IGN + ["tests", "tests/**"])
)
app = modal.App("bot-icelli-mujoco", image=image)
out_vol = modal.Volume.from_name("aalto-sim-out", create_if_missing=True)
links = modal.Dict.from_name("mujoco-live", create_if_missing=True)


@app.function(gpu="L4", cpu=8, memory=16384, timeout=4 * 3600, volumes={"/out": out_vol})
def run_config(line: str, rtf: float = 0.4, colors: str = "venue"):
    import subprocess
    tag, policy, task, seed, trials, geo, *extra = line.split()
    out = Path(f"/out/mujoco/{tag}")
    out.mkdir(parents=True, exist_ok=True)
    os.makedirs(f"{BOT}/artifacts/eval", exist_ok=True)
    if not os.path.exists(f"{BOT}/artifacts/eval/mujoco"):
        os.symlink("/out/mujoco", f"{BOT}/artifacts/eval/mujoco")
    gl = os.environ["MUJOCO_GL"]
    probe = "import mujoco; m=mujoco.MjModel.from_xml_string('<mujoco/>'); mujoco.Renderer(m,48,64).render()"
    if subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode != 0:
        gl = "osmesa"                                   # no EGL on this GPU node: CPU rendering (slower sim, same results)
    env = dict(os.environ, MUJOCO_GL=gl, PYOPENGL_PLATFORM=gl, V15_DLOG=str(out / f"decisions_{policy}.jsonl"))
    env.update(dict(kv.split("=", 1) for kv in extra))
    scene = ["--scene", f"{BOT}/artifacts/mujoco/scene_measured.yaml"] if geo == "measured" else []
    if scene:                                           # serve.py --scene needs the file: build.py writes it
        subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0,'{BOT}/sim/mujoco'); import build as B; "
                        "B.scene_yaml(B.load_cfg())"], env=env, check=True)
    slog = open(out / "server.log", "w")
    server = subprocess.Popen([sys.executable, f"{BOT}/sim/mujoco/serve.py", *scene, "--", "--policy", policy,
                               "--port", "8000"], env=env, stdout=slog, stderr=subprocess.STDOUT, cwd=BOT)
    for _ in range(240):
        time.sleep(0.5)
        if "listening" in (out / "server.log").read_text():
            break
    with modal.forward(8080) as tunnel:
        links[tag] = {"url": tunnel.url, "started": time.time(), "line": line, "gl": gl}
        print(f"[{tag}] live: {tunnel.url}  (rendering: {gl})", flush=True)
        rc = subprocess.run([sys.executable, f"{BOT}/sim/mujoco/run.py", "--tag", tag, "--task", task, "--seed", seed,
                             "--trials", trials, "--rtf", str(rtf), "--colors", colors, "--video", "--live", "8080"],
                            env=env, cwd=BOT).returncode
        time.sleep(20)                                  # leave the last frame and the results up for a moment
    links[tag] = {**links[tag], "url": None, "done": time.time(), "rc": rc}
    server.terminate()
    slog.close()
    out_vol.commit()
    return rc


@app.local_entrypoint()
def batch(runs: str = RUNS, rtf: float = 0.4, colors: str = "venue"):
    key = ""
    env_file = ROOT / ".env"
    if env_file.exists():
        key = next((ln.split("=", 1)[1].strip().strip("'\"") for ln in env_file.read_text().splitlines()
                    if ln.startswith("GEMINI_API_KEY=")), "")
    fn = run_config.with_options(secrets=[modal.Secret.from_dict({"GEMINI_API_KEY": key})]) if key else run_config
    lines = [ln for ln in runs.strip().splitlines() if ln.strip()]
    for ln in lines:
        links.pop(ln.split()[0], None)
    calls = [fn.spawn(ln, rtf, colors) for ln in lines]
    print(f"started {len(calls)} runs; live links (also: python sim/mujoco/modal_mujoco.py links):", flush=True)
    seen = set()
    for _ in range(180):                                 # up to 6 min for the containers to start
        for ln in lines:
            tag = ln.split()[0]
            v = links.get(tag)
            if tag not in seen and v and v.get("url"):
                seen.add(tag)
                print(f"  {tag:16s} {v['url']}", flush=True)
        if len(seen) == len(lines):
            break
        time.sleep(2)



# ------------------------------------------------------------------------------------------------ stress test
# Hundreds of single episodes, each in its own random variant of the scene (dr.py): random layouts, both tasks.
#   .venv/bin/modal run --detach sim/mujoco/modal_mujoco.py::stress --n 200          # 25 containers at once
#   .venv/bin/python sim/mujoco/stress_report.py <run>                                # after: per-factor report
def _gemini_key():
    if not modal.is_local():
        return ""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    return next((ln.split("=", 1)[1].strip().strip("'\"") for ln in env_file.read_text().splitlines()
                 if ln.startswith("GEMINI_API_KEY=")), "")


_KEY = _gemini_key()


@app.cls(gpu=["L4", "A10G", "L40S", "A100-40GB", "T4"], cpu=8, memory=16384, timeout=30 * 60, volumes={"/out": out_vol}, max_containers=25,
         secrets=[modal.Secret.from_dict({"GEMINI_API_KEY": _KEY})] if _KEY else [])
class Stress:
    @modal.enter()
    def start(self):
        import subprocess
        os.makedirs(f"{BOT}/artifacts/eval", exist_ok=True)
        if not os.path.exists(f"{BOT}/artifacts/eval/mujoco"):
            os.symlink("/out/mujoco", f"{BOT}/artifacts/eval/mujoco")
        probe = "import mujoco; m=mujoco.MjModel.from_xml_string('<mujoco/>'); mujoco.Renderer(m,48,64).render()"
        self.gl = "egl" if subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode == 0 else "osmesa"
        self.tunnel = modal.forward(8080)
        self.url = self.tunnel.__enter__().url
        self.cid = os.environ.get("MODAL_TASK_ID", str(os.getpid()))
        links[f"stress:{self.cid}"] = {"url": self.url, "started": time.time(), "gl": self.gl}

    @modal.exit()
    def stop(self):
        links.pop(f"stress:{self.cid}", None)
        self.tunnel.__exit__(None, None, None)

    @modal.method()
    def episode(self, run: str, spec: dict):
        """One episode: a fresh policy server (its own decision log), run.py --dr. -> trial dict + log stats."""
        import json
        import subprocess
        tag = f"{run}/{spec['id']:03d}"
        out = Path(f"/out/mujoco/{tag}")
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, MUJOCO_GL=self.gl, PYOPENGL_PLATFORM=self.gl,
                   V15_DLOG=str(out / f"decisions_{spec['policy']}.jsonl"))
        env.update(spec.get("server_env") or {})
        links[f"stress:{self.cid}"] = {"url": self.url, "episode": spec["id"], "gl": self.gl}
        slog = open(out / "server.log", "w")
        server = subprocess.Popen([sys.executable, f"{BOT}/sim/mujoco/serve.py", "--", "--policy", spec["policy"],
                                   "--port", "8000"], env=env, stdout=slog, stderr=subprocess.STDOUT, cwd=BOT)
        try:
            for _ in range(240):
                time.sleep(0.5)
                if "listening" in (out / "server.log").read_text():
                    break
            rc = subprocess.run([sys.executable, f"{BOT}/sim/mujoco/run.py", "--tag", tag, "--task", spec["task"],
                                 "--seed", str(spec["seed"]), "--trials", "1", "--dr", str(spec["dr"]),
                                 "--rtf", str(spec.get("rtf", 0.4)), "--video", "--live", "8080"],
                                env=env, cwd=BOT, timeout=25 * 60).returncode
        finally:
            server.terminate()
            slog.close()
        res = {"id": spec["id"], "spec": spec, "rc": rc, "gl": self.gl}
        try:
            res["trial"] = json.loads((out / "eval.json").read_text())["trials"][0]
        except Exception as e:
            res["error"] = repr(e)
        res["log"] = _log_stats(out / f"decisions_{spec['policy']}.jsonl")
        (out / "result.json").write_text(json.dumps(res, default=str))
        out_vol.commit()
        return res


def _log_stats(path):
    """Counts from the policy's decision log: Decision calls answered / missing, grasps tried / empty."""
    import json
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


@app.function(timeout=6 * 3600, volumes={"/out": out_vol})
def stress_run(run: str, specs: list):
    """Runs on Modal (so the batch survives the laptop): fans the episodes out over Stress containers."""
    import json
    done = 0
    os.makedirs(f"/out/mujoco/{run}", exist_ok=True)
    with open(f"/out/mujoco/{run}/all.jsonl", "a") as f:
        for res in Stress().episode.map([run] * len(specs), specs, order_outputs=False, return_exceptions=True):
            if isinstance(res, Exception):
                res = {"error": repr(res)}
            f.write(json.dumps(res, default=str) + "\n")
            f.flush()
            done += 1
            if done % 10 == 0:
                out_vol.commit()
                print(f"{done}/{len(specs)} episodes", flush=True)
    out_vol.commit()
    return done


@app.local_entrypoint()
def stress(n: int = 200, policy: str = "v1.6", seed0: int = 5000, language: float = 0.4, rtf: float = 0.4,
           run: str = ""):
    import random
    run = run or f"stress-{time.strftime('%m%d-%H%M')}"
    rnd = random.Random(seed0)
    specs = [{"id": i, "seed": seed0 + i, "dr": seed0 + i, "policy": policy, "rtf": rtf,
              "task": "sort_language" if rnd.random() < language else "sort_fixed"} for i in range(n)]
    if not _KEY and policy == "v1.6":
        print("WARNING: no GEMINI_API_KEY in .env: v1.6 runs as v1.5 (offline fallback)")
    out_vol_dir = f"/mujoco/{run}"
    call = stress_run.spawn(run, specs)
    print(f"started {run}: {n} episodes ({policy}), call {call.object_id}; results in aalto-sim-out{out_vol_dir}/\n"
          f"live links: .venv/bin/python sim/mujoco/modal_mujoco.py links")

if __name__ == "__main__" and sys.argv[1:] == ["links"]:
    for k, v in modal.Dict.from_name("mujoco-live").items():
        print(f"{k:16s} {v.get('url') or ('done rc=%s' % v.get('rc'))}")
