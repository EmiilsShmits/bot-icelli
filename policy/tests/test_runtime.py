"""Unit tests for policy/cfg_overrides.py and policy/runtime.py (runtime patches of Aalto's planner).

    python -m unittest policy/tests/test_runtime.py -v        # from the repo root; needs numpy, scipy, pyyaml
"""
from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]


class TestCfgOverrides(unittest.TestCase):
    def setUp(self):
        for k in ("AALTO_CFG_OVERRIDES", "ARM_XY_OFFSET"):
            os.environ.pop(k, None)
        from aaltonomous.baselines.classical import config as C
        importlib.reload(C)                         # undo any earlier install
        self.C = C

    def tearDown(self):
        for k in ("AALTO_CFG_OVERRIDES", "ARM_XY_OFFSET"):
            os.environ.pop(k, None)
        importlib.reload(self.C)

    def test_no_env_is_a_noop(self):
        import cfg_overrides
        orig = self.C.load_config
        self.assertEqual(cfg_overrides.install(), {})
        self.assertIs(self.C.load_config, orig)

    def test_env_overrides_win_and_reach_modules_that_imported_by_name(self):
        import cfg_overrides
        os.environ["ARM_XY_OFFSET"] = "left=0.0,0.01; right=0.005,-0.01"
        os.environ["AALTO_CFG_OVERRIDES"] = '{"grasp.height_frac": 0.42}'
        holder = types.ModuleType("holder_of_load_config")
        holder.load_config = self.C.load_config     # like `from .config import load_config`
        sys.modules[holder.__name__] = holder
        try:
            extra = cfg_overrides.install()
            self.assertEqual(extra["grasp.arm_xy_offset"], {"left": [0.0, 0.01], "right": [0.005, -0.01]})
            cfg = holder.load_config(None, {"grasp.height_frac": 0.6})
            self.assertAlmostEqual(cfg["grasp"]["height_frac"], 0.42)         # env wins over caller overrides
            self.assertEqual(cfg["grasp"]["arm_xy_offset"]["right"], [0.005, -0.01])
            self.assertIs(self.C.load_config, holder.load_config)
            cfg_overrides.install()                                            # idempotent
            self.assertTrue(getattr(self.C.load_config, "_bot_icelli", False))
        finally:
            sys.modules.pop(holder.__name__, None)


if __name__ == "__main__":
    unittest.main()
