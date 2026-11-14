"""Speed and limit guard: every target we send first goes through a copy of Aalto's own SafetyFilter with slightly
lower caps, so the runner's filter never has to clip (the sim gate allows 0 clipped steps).

Same idea as `modal_pipeline/submission/server.py` (make_shadow_filter). For the classical planner it is a safety
net (its plans are already pre-checked); for a learned policy it is what keeps the gate green.
"""
from __future__ import annotations

import logging

import numpy as np

from aaltonomous.interface.safety import JointSpec, SafetyConfig, SafetyFilter

log = logging.getLogger("bot-icelli.guard")
DT = 1.0 / 30.0


class Guard:
    def __init__(self, arm_vel: float = 0.98, hand_vel: float = 2.7):
        logging.getLogger("aaltonomous.safety").setLevel(logging.ERROR)  # shaping here is routine, not an event
        cfg = SafetyConfig(arm_max_vel=arm_vel, hand_max_vel=hand_vel, max_clipped_steps=10 ** 9)
        try:
            self.filter = SafetyFilter(JointSpec(), cfg)
        except Exception as e:  # no Pinocchio / URDF: limits and speed still enforced, workspace box not
            log.error("workspace check unavailable (%s: %s): guard runs without it", type(e).__name__, e)
            cfg.workspace = False
            self.filter = SafetyFilter(JointSpec(), cfg)
        self.reset()

    def reset(self):
        self.started = False
        self.ticks = 0
        self.shaped = 0

    def __call__(self, arm, hand, obs):
        """(k,14) or (14,) arm / hand targets -> the same targets, shaped to respect limits and speed caps."""
        arm = np.atleast_2d(np.asarray(arm, float))
        hand = np.atleast_2d(np.asarray(hand, float))
        k = max(len(arm), len(hand))
        if len(arm) != k:
            arm = np.repeat(arm[-1:], k, 0)
        if len(hand) != k:
            hand = np.repeat(hand[-1:], k, 0)
        f = self.filter
        if not self.started:  # the runner's filter starts from the measured pose, so does ours
            f.reset(np.asarray(obs["arm_q"], float), np.asarray(obs["hand_q"], float), 0.0)
            self.started = True
        out_a, out_h = [], []
        for a, h in zip(arm, hand):
            r = f.filter({"arm_q_target": a, "hand_q_target": h}, self.ticks * DT)
            self.ticks += 1
            self.shaped += bool(r.clipped)
            out_a.append(r.arm_q_cmd)
            out_h.append(r.hand_q_cmd)
        f.events.clear()
        return np.stack(out_a), np.stack(out_h)
