"""bot-icelli runtime patches for Aalto's planner, installed before any policy is built (policy/server.py, and the
agent image's serve.py via policy/adk/patch_smooth.py):

  * smooth_motion: smooth, jerk-limited arm motions (SMOOTH_MOTION=0 turns them off);
  * cfg_overrides: planner config from the environment (AALTO_CFG_OVERRIDES, ARM_XY_OFFSET);
  * lean: IK targets mapped from the head-camera fit's table frame into the arm frame when the fit says the robot
    leans (real robot only; LEAN_MAP=off turns it off). Needs a set_fit() call per episode from the camera fit.
"""
from __future__ import annotations

import logging

log = logging.getLogger("bot-icelli.runtime")


def install():
    try:
        import cfg_overrides
        import lean
        import smooth_motion
        cfg_overrides.install()
        smooth_motion.install()
        lean.install()
    except ImportError as e:  # `hold` on a machine without the planner's dependencies
        log.warning("runtime patches not installed: %s", e)
