"""v1.7 (policies/oracle_v17.py): v1.6 + the lean fallback. The fallback itself: test_v16.py TestLeanFallback.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python -m unittest policy.tests.test_v17 -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

ENV = {"GEMINI_API_KEY": "", "DECISION_KEY_FILE": "/nonexistent", "V16_LABELS": "off", "V16_INSTRUCTION": "rules"}


class TestV17(unittest.TestCase):
    def build(self, name, **env):
        import server
        with mock.patch.dict(os.environ, {**ENV, **env}):
            return server.POLICIES[name]()

    def test_registered_and_fallback_on(self):
        p = self.build("v1.7")
        self.assertEqual(p.name, "bot-icelli-v1.7")
        self.assertTrue(p.lean_keep)
        self.assertTrue(p.pol.cam.lean_fallback)

    def test_switches(self):
        self.assertFalse(self.build("v1.7", V17_LEAN_KEEP="off").pol.cam.lean_fallback)
        self.assertFalse(self.build("v1.7", V16_CALIB="bins").pol.cam.lean_fallback)

    def test_v16_keeps_its_behaviour(self):
        self.assertFalse(self.build("v1.6").pol.cam.lean_fallback)


if __name__ == "__main__":
    unittest.main()
