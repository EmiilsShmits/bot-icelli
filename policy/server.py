"""bot-icelli policy server: the entrypoint of our submission image.

Run locally:  make serve        (= python policy/server.py --policy hold --port 8000)
In Docker:    the CMD of policy/Dockerfile. Pick the policy at build time with --build-arg POLICY=<name>.

Add a policy:
  1. Write a class in policy/policies/<name>.py that subclasses aaltonomous.deploy.policy_server.Policy
     and implements reset(instruction, task, seed) and act(obs) -> {"arm_q_target", "hand_q_target"}.
  2. Register it in POLICIES below.
  3. Run `make check` (must PASS) before merging.

Rules every policy must follow (see AGENTS.md): absolute joint targets, changes of at most
1 rad/s for arms and 3 rad/s for hands per tick (0 clips allowed), >= 27 commands/s, and only `obs` as input.
"""
from __future__ import annotations

import argparse
import logging
import os

from aaltonomous.deploy.policy_server import serve

from policies.hold import HoldChunkPolicy

# name -> factory. Model-based policies load their weights from policy/weights/ (baked into the image).
POLICIES = {
    "hold": HoldChunkPolicy,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", default=os.environ.get("POLICY", "hold"), choices=sorted(POLICIES))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    policy = POLICIES[args.policy]()
    logging.getLogger("bot-icelli").info("serving policy %r on :%d", args.policy, args.port)
    serve(policy, port=args.port)


if __name__ == "__main__":
    main()
