"""Planner config overrides from the environment, for every stack that builds its config with Aalto's `load_config`
(the classical baseline and v1.x, Aalto's oracle and so v1.5/v1.6 via `ClassicalPolicy`, Marcus's agent via
`agent/skills/context.py`). Lets one image be tuned on the day without a rebuild, e.g. a per-arm grasp offset measured
on the real robot, or grip values from the grasp sweep:

    AALTO_CFG_OVERRIDES='{"grasp.arm_xy_offset": {"left": [0.0, 0.01], "right": [0.0, -0.01]}, "grasp.height_frac": 0.45}'
    ARM_XY_OFFSET='left=0.0,0.01;right=0.0,-0.01'          # shorthand for grasp.arm_xy_offset (metres, pelvis x/y)

Keys are config.yaml's dotted keys (same as Aalto's ORACLE_OVERRIDES). These win over every other override.
`grasp.arm_xy_offset` shifts each arm's grasp point (Aalto's planner.py; also Marcus's skills planner).
"""
from __future__ import annotations

import json
import logging
import os
import sys

log = logging.getLogger("bot-icelli.cfg")


def env_overrides():
    out = {}
    raw = os.environ.get("AALTO_CFG_OVERRIDES", "").strip()
    if raw:
        out.update(json.loads(raw))
    arm = os.environ.get("ARM_XY_OFFSET", "").strip()
    if arm:
        off = {}
        for part in filter(None, (p.strip() for p in arm.split(";"))):
            side, _, xy = part.partition("=")
            dx, dy = (float(v) for v in xy.split(","))
            off[side.strip()] = [dx, dy]
        out["grasp.arm_xy_offset"] = {**out.get("grasp.arm_xy_offset", {}), **off}
    return out


def install():
    """Wrap aaltonomous.baselines.classical.config.load_config so the env overrides apply last, also in modules that
    imported load_config by name already. No-op without overrides."""
    extra = env_overrides()
    if not extra:
        return {}
    from aaltonomous.baselines.classical import config as C
    orig = C.load_config
    if getattr(orig, "_bot_icelli", False):
        return extra

    def load_config(path=None, overrides=None, profile=None):
        merged = dict(overrides or {})
        merged.update(extra)
        return orig(path, merged, profile)

    load_config._bot_icelli = True
    C.load_config = load_config
    for m in list(sys.modules.values()):
        if getattr(m, "load_config", None) is orig:
            m.load_config = load_config
    log.info("planner config overrides from the environment: %s", extra)
    return extra
