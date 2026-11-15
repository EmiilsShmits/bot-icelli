"""Aalto's synthetic replay test (aaltonomous.deploy.replay) with an instruction other than Aalto's fixed one.

The stock test always sends the fixed instruction, which v1.6 / v1.6g map at once without starting Decision or Gemma.
This sends a paraphrase instead, so the background instruction work (v1.6g: one Gemma generate on the CPU) runs while
act() is being timed. Same pass rule as the stock test: valid replies, >= 27 commands/s, no errors; with --container
also startup <= 120 s.

    python policy/tools/replay_instruction.py --policy ws://localhost:8000                # a running server
    python policy/tools/replay_instruction.py --container bot-icelli/policy:v1.6g --gpus none --steps 600
"""
from __future__ import annotations

import argparse
import sys

from aaltonomous.deploy import replay as R
from aaltonomous.deploy.runner import Container

DEFAULT = "Purple blocks go in the left bin, orange ones in the right bin and yellow ones in the middle."


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instruction", default=DEFAULT)
    ap.add_argument("--steps", type=int, default=600, help="act() calls (600 keep act() busy for the whole generate)")
    ap.add_argument("--policy", default="ws://localhost:8000")
    ap.add_argument("--container")
    ap.add_argument("--host-port", type=int, default=8000)
    ap.add_argument("--gpus", default="all", help='docker --gpus value; "none" for a CPU-only host')
    a = ap.parse_args(argv)
    obs = R.load_obs(None, a.steps, synthetic=True)
    for o in obs:
        o["instruction"] = a.instruction
    cm = Container(a.container, a.host_port, gpus=None if a.gpus.lower() == "none" else a.gpus) if a.container else None
    try:
        url = a.policy
        if cm:
            cm.prepare().__enter__()
            url = f"ws://localhost:{a.host_port}"
        try:
            res = R.replay(url, obs, alive=cm.alive if cm else None)
        except ConnectionError as e:
            print(cm.logs(tail=40) if cm else "", file=sys.stderr)
            res = {"pass": False, "error": str(e)}
        if cm:
            res["startup_s"] = res.get("connect_s")
            res["pass"] = res["pass"] and res["startup_s"] is not None and res["startup_s"] <= 120
            print(cm.logs(tail=25), file=sys.stderr)
    finally:
        if cm:
            cm.__exit__()
    print({"instruction": a.instruction, **res})
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
