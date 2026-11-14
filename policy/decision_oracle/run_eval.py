"""Run Aalto's sim evaluation (aaltonomous.sim.evaluate) with the decision oracle in place of Aalto's oracle.

    # on the sim machine (bare metal), from Aalto's clone, env `isaac`, venue look sourced:
    source /root/venue_look/venue_env.sh
    PYTHONPATH=/root/aaltonomous-humanoid:/root python -m decision_oracle.run_eval --chooser decision \
        --task sort_fixed --trials 6 --seed 1000 --out /root/runs_do

--chooser aalto     Aalto's untouched OraclePolicy (the baseline)
          default   our library with the oracle's own rule (should behave like aalto)
          decision  Gemini Decision 1 picks among the feasible options (2 s timeout, default on failure)
          random    uniform over the feasible options (seeded): explores movements
          prefer_face  the oracle's object, but a face grasp whenever one is planned (stock claw last)
          memory    prefer_face + never repeat an (arm, grasp) that failed on this object; retries counted per object
--grasp-check on    abort a pick at the end of the lift when the fingers show an empty hand (any chooser)
Every other argument goes to aaltonomous.sim.evaluate unchanged (--policy oracle is implied). The per-look log is
written to --dlog (default: <out>/decisions_<chooser>_<task>_<time>.jsonl).
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--chooser", default="decision", choices=["aalto", "default", "decision", "random", "prefer_face", "memory"])
    ap.add_argument("--perception", default="privileged", choices=["privileged", "camera"],
                    help="camera = head RGB-D only (the scene service is then used for logging the truth, nothing else)")
    ap.add_argument("--labels", default="off", choices=["off", "log", "fuse"],
                    help="camera only: Decision 1 crop labels (log = record, fuse = may fix a close shape call)")
    ap.add_argument("--grasp-check", default="off", choices=["off", "log", "on"],
                    help="finger-angle check at the end of the lift: log = record only, on = abort an empty-handed pick")
    ap.add_argument("--max-tries", type=int, default=4, help="memory chooser: failed picks per object before giving up")
    ap.add_argument("--dlog", default=None)
    ap.add_argument("--look-budget", type=float, default=3.0, help="s of alternatives in a blocking look")
    ap.add_argument("--budget", type=float, default=None, help="s of alternatives in a prefetch look (chooser default)")
    a, rest = ap.parse_known_args(argv)

    import aaltonomous.sim.evaluate as E
    import aaltonomous.sim.oracle as O

    out = "runs/eval"
    if "--out" in rest:
        out = rest[rest.index("--out") + 1]
    task = rest[rest.index("--task") + 1] if "--task" in rest else "sort_fixed"
    if "--team" not in rest:
        rest += ["--team", f"do_{a.chooser}" + ("_cam" if a.perception == "camera" else "")]
    rest = ["--policy", "oracle"] + [x for x in rest]

    if a.chooser != "aalto":
        from .chooser import make
        from .policy import DecisionOraclePolicy

        dlog = a.dlog or os.path.join(out, f"decisions_{a.chooser}{'_cam' if a.perception == 'camera' else ''}_{task}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
        os.makedirs(os.path.dirname(dlog) or ".", exist_ok=True)
        print(f"[run_eval] chooser={a.chooser} dlog={dlog}", flush=True)
        ch = make(a.chooser)
        if a.budget is not None:
            ch.budget_s = a.budget

        def factory(client, **kw):
            return DecisionOraclePolicy(client, chooser=ch, dlog=dlog, look_budget_s=a.look_budget, perception=a.perception, labels=a.labels,
                                        grasp_check=a.grasp_check, max_tries=a.max_tries, **kw)

        O.OraclePolicy = factory   # evaluate() imports it from the module at call time

    class SeededClient(E.LocalClient):
        def reset(self, task, instruction, seed):
            self.policy.episode_seed, self.policy.task = seed, task
            super().reset(task, instruction, seed)

    E.LocalClient = SeededClient
    return E.main(rest)


if __name__ == "__main__":
    sys.exit(main())
