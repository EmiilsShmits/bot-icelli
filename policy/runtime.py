"""bot-icelli runtime patches for Aalto's planner, installed before any policy is built (policy/server.py, and the
agent image's serve.py via policy/adk/patch_smooth.py):

  * smooth_motion: smooth, jerk-limited arm motions (SMOOTH_MOTION=0 turns them off);
  * cfg_overrides: planner config from the environment (AALTO_CFG_OVERRIDES, ARM_XY_OFFSET);
  * lean: IK targets mapped from the head-camera fit's table frame into the arm frame when the fit says the robot
    leans. Off by default since Sun 15 Nov (it cost 5 of 12 objects in the lean sim); LEAN_MAP=auto turns it on.
    Needs a set_fit() call per episode from the camera fit.
  * gravity_ff: every action carries `arm_tau_ff`, the gravity torque at the commanded arm pose (Aalto's PR #4: on
    the real robot an outstretched arm sags 15-18 cm without it). The sim ignores it. GRAVITY_FF=off turns it off.
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
    try:                      # separate: it only needs Pinocchio and Aalto's policy server
        import gravity_ff
        gravity_ff.install()
    except Exception as e:
        log.warning("gravity feed-forward not installed: %r", e)
