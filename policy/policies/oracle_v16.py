"""v1.6 submission candidate: v1.5 (policies/oracle_v15.py) with Gemini Decision 1 for colour, shape and the
instruction, and v1.5's offline perception and rule parser as the fallback.

What changes from v1.5 (all in decision_oracle/upgrades_v16.py, labels_v16.py and policy/instruction_d1.py):
  * colour + shape: one Decision call per new object crop (parallel, 2.5 s deadline, planning thread only). Decision's
    colour and shape win when confident (>= 0.6); the depth geometry's "lying" (tipped) label always stands.
  * extra objects: saturated blobs at object height that no HSV range took are kept when Decision names their colour
    (a real block outside v1.5's ranges is otherwise never seen).
  * instruction: reset() still sets the rule parser's mapping at once and starts one Decision call in the background;
    the first look takes Decision's answer if all 10 slots are confident (>= 0.6), else the rules' mapping stays.
  * V15_SIDES defaults to "off" (47/55 vs strict 42/55 on the same venue episodes, eval/RESULTS.md e-030, e-040).
No key, no network, deadline or low confidence: v1.5 behaviour. act() never waits for any call.

Env: GEMINI_API_KEY (or DECISION_KEY_FILE / /root/.decision_key), V16_LABELS (fuse | log | off, default fuse),
V16_INSTRUCTION (d1 | rules, default d1), V15_SIDES (default off here), AALTO_TIME_LIMIT, V15_DLOG,
GUARD_ARM_VEL / GUARD_HAND_VEL (as v1.5).
"""
from __future__ import annotations

import logging
import os

from guard import Guard
from policies.oracle_v15 import OracleV15

log = logging.getLogger("bot-icelli.v1.6")


class OracleV16(OracleV15):
    name = "bot-icelli-v1.6"

    def __init__(self, inner_kw=None):
        """inner_kw: extra arguments for the inner policy (v1.7 passes planner `overrides`); None = v1.6 as it was."""
        from decision_oracle.upgrades_v16 import V16OraclePolicy
        self.pol = V16OraclePolicy(None, sides=os.environ.get("V15_SIDES", "off"), perception="camera",
                                   grasp_check="on", dlog=os.environ.get("V15_DLOG") or None, threaded=True,
                                   labels=os.environ.get("V16_LABELS", "fuse"),
                                   instruction=os.environ.get("V16_INSTRUCTION", "d1"),
                                   time_limit=float(os.environ.get("AALTO_TIME_LIMIT", 120.0)),
                                   log=lambda m: log.info(m), **(inner_kw or {}))
        self.guard = Guard(float(os.environ.get("GUARD_ARM_VEL", 0.98)), float(os.environ.get("GUARD_HAND_VEL", 2.7)))
        self.action_horizon = int(self.pol.cfg["motion"]["chunk"])
        self.mapping, self.mapping_source = {}, ""
        self._pending_reset, self._stale_since = None, None
        log.info("v1.6 ready: sides=%s labels=%s instruction=%s (key %s) time_limit=%.0f s", self.pol.sides,
                 "on" if self.pol.labeler is not None else "off (v1.5 perception)",
                 "decision" if self.pol.instr is not None and self.pol.instr.enabled else "rules only",
                 "found" if self.pol.labeler is not None else "missing", self.pol.time_limit)
