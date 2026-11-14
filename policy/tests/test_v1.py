"""Unit tests for the v1 policy parts that run without Pinocchio: instruction mapping, speed guard, colour ranges.

    python -m unittest discover -s policy/tests -v        # from the repo root

The full policy (IK, planner) needs Pinocchio + the G1 URDF; test that on Linux with `make check POLICY=v1`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

from aaltonomous.interface import tasks  # noqa: E402
from guard import Guard  # noqa: E402
from instruction import mapping_for  # noqa: E402

ARM_STEP, HAND_STEP = 0.98 / 30 + 1e-9, 2.7 / 30 + 1e-9


class TestInstruction(unittest.TestCase):
    def test_fixed_task(self):
        self.assertEqual(mapping_for("anything", "sort_fixed"), (tasks.FIXED_MAPPING, "fixed"))

    def test_training_templates(self):
        for seed in range(200):
            text, truth = tasks.make_instruction("sort_language", np.random.default_rng(seed))
            mapping, source = mapping_for(text, "sort_language")
            self.assertEqual(mapping, truth, f"{text!r} -> {mapping} [{source}]")

    def test_real_colour_names(self):
        text = "Put the purple objects in the left box, the orange ones in the middle box and the yellow ones on the right."
        self.assertEqual(mapping_for(text, "sort_language")[0], {"blue": "left", "red": "center", "yellow": "right"})

    def test_unreadable_falls_back_to_fixed(self):
        mapping, source = mapping_for("", "sort_language")
        self.assertEqual(mapping, tasks.FIXED_MAPPING)
        self.assertTrue(source.startswith("default"), source)


class TestGuard(unittest.TestCase):
    def obs(self):
        return {"arm_q": np.zeros(14), "hand_q": np.zeros(14)}

    def test_speed_capped_per_tick(self):
        g = Guard()
        arm, hand = g(np.full((10, 14), 1.0), np.full((10, 14), 1.0), self.obs())  # a 1 rad jump in one tick
        prev_a, prev_h = np.zeros(14), np.clip(np.zeros(14), g.filter.hand_lo, g.filter.hand_hi)
        for a, h in zip(arm, hand):
            self.assertLessEqual(np.abs(a - prev_a).max(), ARM_STEP)
            self.assertLessEqual(np.abs(h - prev_h).max(), HAND_STEP)
            prev_a, prev_h = a, h

    def test_nan_holds_last_command(self):
        g = Guard()
        bad = np.full((3, 14), np.nan)
        arm, hand = g(bad, bad, self.obs())
        self.assertTrue(np.all(np.isfinite(arm)) and np.all(np.isfinite(hand)))
        self.assertTrue(np.allclose(arm, 0.0))

    def test_single_tick_and_shape(self):
        arm, hand = Guard()(np.zeros(14), np.zeros((4, 14)), self.obs())
        self.assertEqual(arm.shape, (4, 14))
        self.assertEqual(hand.shape, (4, 14))


class TestColours(unittest.TestCase):
    """The widened ranges must see the sim colours AND the real ones measured in Aalto's head-camera video."""

    @classmethod
    def setUpClass(cls):
        from aaltonomous.baselines.classical.config import load_config
        from aaltonomous.baselines.classical.perception import Perception
        from aaltonomous.interface.calibration import Calibration
        from aaltonomous.scene.scene import Scene
        from policies.classical_v1 import HSV_V1
        cfg = load_config(overrides={"perception.hsv": HSV_V1})
        cls.perc = Perception(cfg, Scene.load(), Calibration.load())

    def classes(self, rgb):
        img = np.zeros((40, 40, 3), np.uint8)
        img[:] = rgb
        return sorted(c for c, m in self.perc.masks(img).items() if m[20, 20])

    def test_sim_colours(self):  # scene.yaml objects.colors
        self.assertEqual(self.classes((200, 30, 30)), ["red"])
        self.assertEqual(self.classes((235, 200, 20)), ["yellow"])
        self.assertEqual(self.classes((30, 70, 200)), ["blue"])

    def test_real_colours(self):  # median RGB of the objects in drop-2 head-camera frames
        self.assertEqual(self.classes((203, 103, 26)), ["red"])      # orange triangle
        self.assertEqual(self.classes((252, 156, 98)), ["red"])      # orange cube, brighter frame
        self.assertEqual(self.classes((210, 251, 174)), ["yellow"])  # pale yellow cylinder
        self.assertEqual(self.classes((185, 196, 129)), ["yellow"])  # yellow cube in shade
        self.assertEqual(self.classes((99, 147, 244)), ["blue"])     # purple cube (reads blue to this camera)

    def test_not_objects(self):
        self.assertEqual(self.classes((1, 20, 34)), [])      # black Dex3 hand
        self.assertEqual(self.classes((160, 157, 162)), [])  # plywood table
        self.assertEqual(self.classes((248, 253, 252)), [])  # glare
        self.assertEqual(self.classes((130, 127, 118)), [])  # cardboard inside a box


if __name__ == "__main__":
    unittest.main()
