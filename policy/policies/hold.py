"""Placeholder policy: hold the start pose. It does nothing useful, but it passes the plumbing checks.

It exists so `main` always has a working submission while the real model is trained.
It returns 10-tick chunks, so the command rate stays at 30 Hz with almost no compute.
"""
from __future__ import annotations

import numpy as np

from aaltonomous.deploy.policy_server import Policy


class HoldChunkPolicy(Policy):
    name = "bot-icelli-hold"
    action_horizon = 10

    def reset(self, instruction, task=None, seed=None):
        self.instruction = instruction
        self.home = None

    def act(self, obs):
        if self.home is None:
            self.home = (np.asarray(obs["arm_q"], np.float32), np.asarray(obs["hand_q"], np.float32))
        k = self.action_horizon
        return {
            "arm_q_target": np.repeat(self.home[0][None], k, 0),
            "hand_q_target": np.repeat(self.home[1][None], k, 0),
        }
