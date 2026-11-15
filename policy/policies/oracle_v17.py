"""v1.7: v1.6 (policies/oracle_v16.py) with fixes for what the real robot did on Sun 15 Nov (the wrist camera pushed
into the table). Everything else is v1.6: perception, Decision 1 labels and instruction, motions, task 3.

What changes from v1.6:
  * lean fallback (decision_oracle/camera.py, `CameraPerception.lean_fallback`): with V16_CALIB=lean the arm fit runs
    once per episode and lifts a grasp 4-9 cm on Aalto's real frames. When it fails or is past the limits
    (V16_LEAN_MAX_MOVE / V16_LEAN_MAX_DEG, 35 cm / 35 deg since 07f533c), v1.6 goes to lean.py's calibration-camera
    mapping (V16_LEAN_FALLBACK) or the uncorrected frame. v1.7 first reuses the camera's pose relative to the arms from
    the last believed arm fit of an earlier episode, with this episode's table fit, so the correction stays
    arm-based. First episode of a server process, nothing kept yet: as v1.6.
    Real frames: eval/analysis/real_depth/lean_fallback.py.

Env: as v1.6, plus V17_LEAN_KEEP (on | off, default on; off = v1.6's behaviour).
"""
from __future__ import annotations

import logging
import os

from policies.oracle_v16 import OracleV16

log = logging.getLogger("bot-icelli.v1.7")


def _on(name, default="on"):
    return os.environ.get(name, default).lower() not in ("0", "off", "false", "no")


class OracleV17(OracleV16):
    name = "bot-icelli-v1.7"

    def __init__(self):
        super().__init__()
        cam = getattr(self.pol, "cam", None)
        self.lean_keep = bool(_on("V17_LEAN_KEEP") and cam is not None and getattr(cam, "lean", None) is not None)
        if self.lean_keep:
            cam.lean_fallback = True
        log.info("v1.7 ready: lean fallback %s", "on" if self.lean_keep else "off (V17_LEAN_KEEP=off, or V16_CALIB is not lean)")
