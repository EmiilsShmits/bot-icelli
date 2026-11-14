"""v1.2 = v1.1 + the head-camera pose re-fitted from the depth image at the first look of every episode.

Aalto's `calibration.yaml` head pose is a URDF default. Measured with `policy/headpose.py` (Emīls's fit: table
plane + bin walls) on live frames, Sat 14 Nov:
  - nominal sim: 0.9° tilt, ~1 cm shift: the sim renders with the principal point at the image centre while the
    calibration's sits 10.9 px lower (~1°), so the stock deprojection is slightly off even in Aalto's own sim;
  - AALTO_DR=train: ~2° tilt, ~2.5 cm shift, ~1° yaw (Aalto's ±1 cm / ±1° camera jitter on top), the kind of
    error the held-out sim variant that picks the finalists also has;
  - venue-look sim (and the real robot, from Aalto's footage): ~10° tilt, which moves objects by several cm.
The fit is used only if `headpose.plausible()` accepts it (≤ 15° tilt, ≤ 6 cm shift, ≤ 6° yaw); otherwise the
calibration stays as it is. Every episode starts again from `calibration.yaml` and fits once (up to 3 tries).
"""
from __future__ import annotations

import copy
import logging

import numpy as np

from headpose import CAM, fit_head_pose, plausible
from policies.classical_v11 import ClassicalV11, PolicyV11

log = logging.getLogger("bot-icelli.v1.2")
MAX_FIT_TRIES = 3


class PolicyV12(PolicyV11):
    def reset(self, info=None):
        super().reset(info)
        if getattr(self, "_cal0", None) is not None:   # back to calibration.yaml; refit at the first look
            self.cal.cams[CAM].T_pelvis_optical = self._cal0.cams[CAM].T_pelvis_optical.copy()
        self.head_fit, self._fit_tries = None, 0

    def _look(self, obs):
        if self.head_fit is None and self._fit_tries < MAX_FIT_TRIES and obs.get("head_depth") is not None:
            self._fit_tries += 1
            depth = np.asarray(obs["head_depth"])
            if depth.ndim == 2 and depth.any():
                fit = fit_head_pose(depth, self._cal0, self.scene)
                if plausible(fit):
                    self.cal.cams[CAM].T_pelvis_optical = fit.T
                    self.head_fit = fit
                    self.log(f"[v1.2] head pose fitted: {fit.summary()}")
                else:
                    self.log(f"[v1.2] head pose fit not used (try {self._fit_tries}): {fit.summary()}")
        return super()._look(obs)


class ClassicalV12(ClassicalV11):
    name = "bot-icelli-v1.2"

    def __init__(self):
        super().__init__()
        pol = self.pol
        pol.__class__ = PolicyV12
        pol._cal0 = copy.deepcopy(pol.cal)       # pristine calibration.yaml: every fit starts from it
        pol.head_fit, pol._fit_tries = None, 0
