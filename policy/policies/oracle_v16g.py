"""v1.6g: v1.6 (policies/oracle_v16.py) with the fine-tuned Gemma 3 1B instruction parser inside the image as the
offline middle layer: Gemini Decision 1 -> Gemma 1B (CPU) -> rule parser.

What changes from v1.6 (the instruction only; colour / shape labels, motions and sides are v1.6's):
  * reset() still sets the rule parser's mapping at once and now starts two background jobs: the Decision call
    (instruction_d1.py, as v1.6) and one Gemma generate (instruction_gemma.py). act() never waits for either.
  * first look (planning thread): Decision's answer if every slot is >= 0.6 confident within 2.5 s of reset (Gemma is
    then cancelled); else Gemma's if it gave 10 valid slots within V16G_GEMMA_DEADLINE (default 5 s after reset); else
    the rules' mapping stays. Aalto's fixed instruction skips both (it maps exactly), as in v1.6.
  * the weights (policy/weights/gemma-parser-1b, 2.0 GB) load at server start and must answer one self-test; without
    them, without torch, or on a wrong self-test answer Gemma is off and v1.6g runs exactly as v1.6. The image build
    fails instead (policy/Dockerfile), so a v1.6g image always has a working parser.
Offline (no key, no network): Gemma 1B -> rule parser, the measured offline chain in
training/instruction_parser/RESULTS.md.

Env: as v1.6, plus V16G_GEMMA (on | off, default on), GEMMA_PARSER_DIR, V16G_GEMMA_DEADLINE, V16G_GEMMA_THREADS,
V16G_GEMMA_DTYPE (instruction_gemma.py).
"""
from __future__ import annotations

import logging
import os

from guard import Guard
from instruction_gemma import GemmaInstruction, InstructionChain
from policies.oracle_v16 import OracleV16

log = logging.getLogger("bot-icelli.v1.6g")


def _on(name, default="on"):
    return os.environ.get(name, default).lower() not in ("0", "off", "false", "no")


def make_inner(gemma):
    """V16OraclePolicy with the Decision -> Gemma chain as its instruction stage (subclassed here, not in
    decision_oracle/, so v1.6's files stay as they are)."""
    from decision_oracle.upgrades_v16 import V16OraclePolicy, _str_keys

    class V16GOraclePolicy(V16OraclePolicy):
        def __init__(self, client, **kw):
            super().__init__(client, **kw)
            decision = self.instr                       # DecisionInstruction, or None with V16_INSTRUCTION=rules
            self.instr = InstructionChain(decision, gemma)
            self.log(f"[v1.6g] instruction: {'Decision 1 -> ' if self.instr.decision else ''}"
                     f"{'Gemma 1B -> ' if self.instr.gemma else ''}rule parser")

        def _apply_instruction(self):
            """v1.6's, with the answering stage ("decision" / "gemma") as the mapping source."""
            from instruction_d1 import slots_to_mapping
            try:
                slots, rec = self.instr.result()
                if slots is not None:
                    m = slots_to_mapping(slots)
                    rec["agrees_with_rules"] = m == self.mapping
                    rec["rules_mapping"] = _str_keys(self.mapping)
                    if m != self.mapping:
                        self.log(f"[v1.6g] instruction: {rec['source']} {m} replaces rules {self.mapping}")
                    self.mapping = m
                    self.planner.mapping = m
                    self.relay.mapping = m
                    self.mapping_source = rec["source"]
            except Exception as e:                      # the rule parser's mapping stays
                rec = {"used": False, "why": f"error {e!r}"}
            self._w({"type": "instruction", "t": round(self._t, 2), "mapping": self.mapping,
                     "mapping_source": self.mapping_source, **rec})

    return V16GOraclePolicy


class OracleV16G(OracleV16):
    name = "bot-icelli-v1.6g"

    def __init__(self):
        # Load Gemma first (~10 s on the CPU, before the server listens), so no import or load runs during an episode.
        self.gemma = GemmaInstruction() if _on("V16G_GEMMA") else None
        # Same arguments as OracleV16.__init__.
        self.pol = make_inner(self.gemma)(None, sides=os.environ.get("V15_SIDES", "off"), perception="camera",
                                          grasp_check="on", dlog=os.environ.get("V15_DLOG") or None, threaded=True,
                                          labels=os.environ.get("V16_LABELS", "fuse"),
                                          instruction=os.environ.get("V16_INSTRUCTION", "d1"),
                                          time_limit=float(os.environ.get("AALTO_TIME_LIMIT", 120.0)),
                                          log=lambda m: log.info(m))
        self.guard = Guard(float(os.environ.get("GUARD_ARM_VEL", 0.98)), float(os.environ.get("GUARD_HAND_VEL", 2.7)))
        self.action_horizon = int(self.pol.cfg["motion"]["chunk"])
        self.mapping, self.mapping_source = {}, ""
        self._pending_reset, self._stale_since = None, None
        chain = self.pol.instr
        log.info("v1.6g ready: sides=%s labels=%s instruction=%s time_limit=%.0f s", self.pol.sides,
                 "on" if self.pol.labeler is not None else "off (v1.5 perception)",
                 " -> ".join([s for s, on in (("Decision 1", chain.decision), ("Gemma 1B", chain.gemma)) if on]
                             + ["rules"]), self.pol.time_limit)
