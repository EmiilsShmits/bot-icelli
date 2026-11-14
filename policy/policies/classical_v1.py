"""v1 submission policy: Aalto's classical baseline + instruction parsing + colours for the real objects + guard.

Changes against Aalto's reference image (`aaltonomous/baselines/classical/policy_server.py`):
  1. Reads the instruction (`policy/instruction.py`) instead of always sorting red -> left, yellow -> center,
     blue -> right (the stock baseline scores 0 expected points per object in the instruction rounds).
  2. Wider HSV ranges, measured on Aalto's real head-camera frames (`docs/research/aalto-discord-notes.md`): the
     real orange objects (hue 11-13) and the pale yellow ones (hue 34-46) fall outside the stock ranges.
  3. Every target passes our shadow safety filter (`policy/guard.py`).
  4. reset() never blocks (see reset()): Aalto's reference waits for a planning thread left over from the last
     episode, which on a loaded machine got its next episode safe-stopped at step 0 (sim-gate FAIL).
Perception, IK planner, grasps and timing are Aalto's code, unchanged.

Env: AALTO_TIME_LIMIT (s, default 120), AALTO_ARM_VEL (planner speed), AALTO_PROFILE (config profile, default sim),
GUARD_ARM_VEL / GUARD_HAND_VEL (guard caps, default 0.98 / 2.7; the runner allows 1.0 / 3.0).
"""
from __future__ import annotations

import logging
import os
import time

import numpy as np

from aaltonomous.baselines.classical.policy import ClassicalPolicy
from aaltonomous.deploy.policy_server import Policy

from guard import Guard
from instruction import mapping_for

log = logging.getLogger("bot-icelli.v1")

# OpenCV HSV (H 0-180, S/V 0-255). Each class covers the sim colour AND the real one.
#   red    sim red (H ~0-5) + real orange objects (H 11-13). The orange bins match too (sim H ~12, real H 4-7):
#          they are removed by their 3D position (perception keep-mask + in_bin rejection), as in the baseline.
#   yellow sim yellow (H ~26-30) + real pale yellow (H 34-46, S 72-88).
#   blue   sim blue (H ~120) + real purple (H ~110 in the robot camera; margin to 165 in case the finals camera
#          sees it more violet). V >= 90 keeps the black Dex3 hands (V ~34) out.
HSV_V1 = {
    "red": [[[0, 70, 70], [17, 255, 255]], [[165, 70, 70], [180, 255, 255]]],
    "yellow": [[[18, 50, 90], [55, 255, 255]]],
    "blue": [[[90, 60, 90], [165, 255, 255]]],
}


class ClassicalV1(Policy):
    name = "bot-icelli-v1"

    def __init__(self):
        overrides = {"perception.hsv": HSV_V1}
        if os.environ.get("AALTO_ARM_VEL"):
            overrides["motion.arm_max_vel"] = float(os.environ["AALTO_ARM_VEL"])
        self.pol = ClassicalPolicy(threaded=True, require_confirm=False,
                                   time_limit=float(os.environ.get("AALTO_TIME_LIMIT", 120.0)),
                                   overrides=overrides, log=lambda m: log.info(m))
        self.guard = Guard(float(os.environ.get("GUARD_ARM_VEL", 0.98)), float(os.environ.get("GUARD_HAND_VEL", 2.7)))
        self.action_horizon = int(self.pol.cfg["motion"]["chunk"])
        self.mapping, self.mapping_source = {}, ""
        self._pending_reset, self._stale_since = None, None
        self._tools = None

    def get_tools(self, observation):
        """Return model-callable skill tools bound to this tick's measured state.

        Construction is lazy so the normal 30 Hz policy path pays no extra IK-model
        startup cost unless a higher-level planner asks for the skills. The returned
        functions capture joint state internally; a model cannot provide stale state.
        """
        if self._tools is None:
            from tools.triangle_pick import TrianglePickTool

            self._tools = {"pick_triangle": TrianglePickTool(self.pol.planner)}
        return {name: tool.bind(observation) for name, tool in self._tools.items()}

    def reset(self, instruction, task=None, seed=None):
        # Never block here. The runner starts the episode clock right after reset(), and 3 s of sim time without a
        # command is a safe stop = sim-gate FAIL. Seen with Aalto's baseline (Sat 14 Nov, eval/RESULTS.md): an episode
        # ended mid-plan, its reset() waited ~14 s for that planning thread on a loaded machine, and the next episode
        # was stopped at step 0. The planner is not thread-safe, so a new episode must not start planning while the
        # old thread runs: if it still runs, act() holds the arms until it is done, then applies this reset.
        if self.guard.shaped:
            log.info("previous episode: guard shaped %d of %d ticks", self.guard.shaped, self.guard.ticks)
        self.mapping, self.mapping_source = mapping_for(instruction, task)
        self._pending_reset = {"instruction": instruction, "mapping": self.mapping}
        self.guard.reset()
        if self._planning():
            self._stale_since = time.monotonic()
            log.warning("previous episode's planning thread still running: holding until it finishes")
        else:
            self._apply_reset()
        log.info("reset task=%s seed=%s mapping=%s [%s] instruction=%r", task, seed, self.mapping,
                 self.mapping_source, instruction)

    def _planning(self):
        job = self.pol._job
        return job is not None and job["result"] is None

    def _apply_reset(self):
        self.pol.reset(self._pending_reset)
        self._pending_reset = None
        if self._stale_since is not None:
            log.info("old planning thread done after %.1f s: episode starts", time.monotonic() - self._stale_since)
            self._stale_since = None

    def _hold(self, obs):
        """Hold the measured pose (clamped into the joint limits, as Aalto's first act() does)."""
        sp, k = self.pol.spec, max(1, int(self.pol.cfg["motion"].get("hold_ticks", 1)))
        a = np.clip(np.asarray(obs["arm_q"], float), sp.arm_lower, sp.arm_upper)
        h = np.clip(np.asarray(obs["hand_q"], float), sp.hand_lower, sp.hand_upper)
        return {"arm_q_target": np.repeat(a[None], k, 0), "hand_q_target": np.repeat(h[None], k, 0), "done": False}

    def act(self, obs):
        if self._pending_reset is not None:
            if self._planning():
                a = self._hold(obs)
            else:
                self._apply_reset()
                a = self.pol.act(obs)
        else:
            a = self.pol.act(obs)
        arm, hand = self.guard(a["arm_q_target"], a["hand_q_target"], obs)
        return {"arm_q_target": arm.astype(np.float64), "hand_q_target": hand.astype(np.float64),
                "done": bool(a.get("done", False))}
