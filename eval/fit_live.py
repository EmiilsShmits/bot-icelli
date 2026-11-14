"""Grab head RGB-D frames from a running sim and run our head-pose fit (policy/headpose.py) on them.

    cd ~/aaltonomous-humanoid && bash aaltonomous/cloud/aalto.sh py ~/bot-icelli/eval/fit_live.py [--port 55560] [--n 3]

Nominal sim: the correction should be ~0. AALTO_DR=train: up to ~1 deg / 1 cm (Aalto's camera jitter).
Venue look: ~10 deg tilt. Frames during an episode may show the arms; the fit tolerates some.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "policy"))

from aaltonomous.interface.calibration import Calibration  # noqa: E402
from aaltonomous.interface.head_rgbd import HeadRGBDClient  # noqa: E402
from aaltonomous.scene.scene import Scene  # noqa: E402
from headpose import fit_head_pose, plausible  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=55560)
ap.add_argument("--n", type=int, default=3)
a = ap.parse_args()
cal, scene = Calibration.load(), Scene.load()
cli = HeadRGBDClient(a.host, a.port)
done = 0
t_end = time.time() + 60
while done < a.n and time.time() < t_end:
    f = cli.get()
    if f is None:
        time.sleep(0.1)
        continue
    depth = f[1]
    t0 = time.perf_counter()
    fit = fit_head_pose(depth, cal, scene)
    print(f"frame {done}: {fit.summary()}  ok={fit.ok} plausible={plausible(fit)}  "
          f"{(time.perf_counter() - t0) * 1000:.0f} ms", flush=True)
    done += 1
    time.sleep(2.0)
cli.close()
