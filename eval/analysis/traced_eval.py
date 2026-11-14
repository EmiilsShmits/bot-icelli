"""`aaltonomous.sim.evaluate` plus everything failure analysis needs (eval/analysis/README.md).

Same arguments as `aalto.sh eval`, plus:
  --video          head-camera mp4 per episode (episode_NNN.mp4)
  --pose-hz HZ     every object's position from the sim's scene service, HZ times a second (default 5, 0 = off)
                   -> episode_NNN.poses.jsonl. Read by this evaluator only, never by the policy (privileged state).
It also
  - saves the policy container's own log as container.log in the run folder: Aalto's evaluator deletes the
    container at the end, and its log with it;
  - avoids a trap in Aalto's evaluate.py: it tests --policy (default "oracle") BEFORE --container, so
    `--container IMAGE` alone silently runs Aalto's privileged ORACLE instead of the image. With --container and
    no --policy, this wrapper adds --policy ws://localhost:<host-port>.

    cd ~/aaltonomous-humanoid
    bash aaltonomous/cloud/aalto.sh py ~/bot-icelli/eval/analysis/traced_eval.py --container bot-icelli/policy:v1.2 \
        --team v1.2 --task sort_fixed --trials 10 --seed 1000 --out ~/runs/traced --video
    # on a 2nd sim: AALTO_INSTANCE=b in front, and --host-port 8001
Then: eval/analysis/trace.py --runs ~/runs/traced/*/ --out ...
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import aaltonomous.deploy.runner as R


def take(argv, flag, has_value=False, default=None):
    if flag not in argv:
        return default, argv
    i = argv.index(flag)
    if has_value:
        return argv[i + 1], argv[:i] + argv[i + 2:]
    return True, argv[:i] + argv[i + 1:]


def main(argv):
    video, argv = take(argv, "--video", default=False)
    pose_hz, argv = take(argv, "--pose-hz", True, "5")
    pose_hz = float(pose_hz)
    if "--container" in argv and "--policy" not in argv:
        port = argv[argv.index("--host-port") + 1] if "--host-port" in argv else "8000"
        argv = ["--policy", f"ws://localhost:{port}"] + argv
        print(f"[traced_eval] --container without --policy would run Aalto's oracle: added --policy ws://localhost:{port}")
    host = argv[argv.index("--host") + 1] if "--host" in argv else "127.0.0.1"
    run = {"dir": None}

    _init, _add, _save = R.Recorder.__init__, R.Recorder.add, R.Recorder.save

    def poll(rec):
        from aaltonomous.sim.scene_client import SceneClient
        sc = SceneClient(host)
        with open(rec.path.with_suffix(".poses.jsonl"), "w") as f:
            while not rec._stop.wait(1.0 / pose_hz):
                if rec._t is None:          # before the episode's first tick the scene still shows the previous one
                    continue
                try:
                    objs = sc.state()["objects"]
                except Exception:           # a slow scene service must never break the evaluation
                    continue
                f.write(json.dumps({"t": round(rec._t, 3), "objects": {
                    o["name"]: [round(float(v), 4) for v in o["pos"]] for o in objs if o.get("active", True)}}) + "\n")

    def init(self, path, images=False, video_=False):
        _init(self, path, images=images, video=bool(video_ or video))
        run["dir"] = Path(path).parent
        self._t, self._stop, self._thr = None, threading.Event(), None
        if pose_hz > 0:
            self._thr = threading.Thread(target=poll, args=(self,), daemon=True)
            self._thr.start()

    def add(self, row, obs):
        self._t = float(row.get("t", 0.0))
        _add(self, row, obs)

    def save(self, events, summary):
        if self._thr is not None:
            self._stop.set()
            self._thr.join(timeout=2.0)
        _save(self, events, summary)

    R.Recorder.__init__, R.Recorder.add, R.Recorder.save = init, add, save

    _exit = R.Container.__exit__

    def exit_(self, *exc):
        try:
            if self.started and run["dir"] is not None:
                r = R._docker("logs", "--timestamps", self.name, check=False)
                (run["dir"] / "container.log").write_text((r.stdout or "") + (r.stderr or ""))
        except Exception as e:  # noqa: BLE001
            print(f"[traced_eval] could not save the container log: {e}")
        return _exit(self, *exc)

    R.Container.__exit__ = exit_

    from aaltonomous.sim import evaluate
    return evaluate.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
