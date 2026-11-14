"""Unit tests for v1.6 (policies/oracle_v16.py, decision_oracle/upgrades_v16.py + labels_v16.py, instruction_d1.py).
No network: every Decision answer here is a fake.

    python -m unittest policy/tests/test_v16.py -v        # from the repo root

The camera test needs OpenCV + Pinocchio and the saved venue-look sim frames (artifacts/monitor/sim_frames/, git-ignored).
"""
from __future__ import annotations

import sys
import time
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

from aaltonomous.scene.scene import resolve_bin  # noqa: E402

import instruction_d1 as I  # noqa: E402
from spec import SLOTS  # noqa: E402

try:
    import cv2
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False
FRAMES = sorted((ROOT / "artifacts" / "monitor" / "sim_frames").glob("f_*.npz"))


def answer(slots, conf=0.95, low=None):
    """Fake createDecision response for a 10-slot answer (low: one slot name answered with confidence 0.3)."""
    return {"answers": {I._qname(s): {"choice": v, "confidence": 0.3 if s == low else conf} for s, v in slots.items()}}


def slots_for(colour_bins, other="leave", **overrides):
    out = {s: colour_bins[s.split()[0]] for s in SLOTS if s != "other"}
    out["other"] = other
    out.update({k.replace("_", " "): v for k, v in overrides.items()})
    return out


CB = {"red": "left", "yellow": "center", "blue": "right"}


class TestInstructionD1(unittest.TestCase):
    def test_body_has_no_invalid_question_and_names_real_colours(self):
        b = I.build_body("Purple goes left.")
        self.assertEqual(set(b["questions"]), {I._qname(s) for s in SLOTS})
        self.assertIn("orange", b["input"])
        self.assertIn("purple", b["input"])
        self.assertTrue(b["input"].endswith("Instruction: Purple goes left."))

    def test_mapping_colour_only(self):
        self.assertEqual(I.slots_to_mapping(slots_for(CB)), CB)

    def test_mapping_shape_keys_tipped_and_other(self):
        s = slots_for(CB, other="right", red_triangle="center", blue_cube="leave")
        m = I.slots_to_mapping(s)
        self.assertEqual(resolve_bin(m, "red", "triangle"), "center")
        self.assertEqual(resolve_bin(m, "red", "tipped"), "center")      # a lying triangle follows the triangle
        self.assertEqual(resolve_bin(m, "red", "cube"), "left")
        self.assertIsNone(resolve_bin(m, "blue", "cube"))                # leave: stays on the table
        self.assertEqual(resolve_bin(m, "other", "cube"), "right")       # unknown objects get the `other` bin

    def test_same_keys_as_v15_rule_mapping(self):
        from policies.oracle_v15 import mapping_with_shapes
        import rule_parser
        text = "Triangles go in the left bin, everything else in the right bin."
        self.assertEqual(I.slots_to_mapping(rule_parser.parse(text)), mapping_with_shapes(text)[0])

    def test_confident_answer_is_used(self):
        d = I.DecisionInstruction(call=lambda body: answer(slots_for(CB)))
        d.start("Red left, yellow middle, blue right.")
        slots, rec = d.result()
        self.assertEqual(slots, slots_for(CB))
        self.assertTrue(rec["used"])

    def test_low_confidence_falls_back(self):
        d = I.DecisionInstruction(call=lambda body: answer(slots_for(CB), low="blue cube"))
        d.start("x")
        slots, rec = d.result()
        self.assertIsNone(slots)
        self.assertFalse(rec["used"])
        self.assertIn("low confidence", rec["why"])

    def test_error_and_bad_response_fall_back(self):
        def boom(body):
            raise ConnectionError("no network")
        for call in (boom, lambda body: {"answers": {}}):
            d = I.DecisionInstruction(call=call)
            d.start("x")
            slots, rec = d.result()
            self.assertIsNone(slots)
            self.assertFalse(rec["used"])

    def test_start_never_blocks_and_deadline_holds(self):
        def slow(body):
            time.sleep(1.0)
            return answer(slots_for(CB))
        d = I.DecisionInstruction(deadline_s=0.3, call=slow)
        t = time.monotonic()
        d.start("x")
        self.assertLess(time.monotonic() - t, 0.05)
        slots, rec = d.result()
        self.assertLess(time.monotonic() - t, 0.6)
        self.assertIsNone(slots)
        self.assertEqual(rec["why"], "deadline")

    def test_no_key_is_off(self):
        d = I.DecisionInstruction(key="")
        self.assertFalse(d.enabled)
        d.start("x")
        self.assertEqual(d.result()[0], None)


def det(color="red", shape="cube", d1=None, leftover=False, xy=None):
    d = types.SimpleNamespace(color=None if leftover else color, hsv_color=None if leftover else color, shape=shape,
                              yaw=0.0, d1=d1 or {}, top_xy=xy)
    return d


def d1(colour=None, cc=0.95, shape=None, sc=0.95):
    out = {}
    if colour:
        out.update(colour=colour, colour_conf=cc)
    if shape:
        out.update(shape=shape, shape_conf=sc)
    return out


@unittest.skipUnless(HAVE_PIN, "needs OpenCV + Pinocchio")
class TestFuse(unittest.TestCase):
    def setUp(self):
        from decision_oracle.labels_v16 import CropLabelerV16
        self.lab = CropLabelerV16.__new__(CropLabelerV16)    # no key, no thread pool: fuse() only
        self.lab.mode, self.lab.min_conf = "fuse", 0.6

    def test_confident_colour_wins(self):
        d = det("red", d1=d1("yellow"))
        self.lab.fuse(d)
        self.assertEqual((d.color, d.color_src), ("yellow", "d1"))

    def test_unsure_or_other_colour_keeps_hsv(self):
        for l in (d1("yellow", cc=0.4), d1("other", cc=0.99), {"error": "deadline"}):
            d = det("blue", d1=l)
            self.lab.fuse(d)
            self.assertEqual(d.color, "blue")
            self.assertFalse(getattr(d, "other", False))

    def test_leftover_blob(self):
        d = det(leftover=True, d1=d1("yellow", shape="cube"))
        self.lab.fuse(d)
        self.assertEqual((d.color, d.color_src), ("yellow", "d1"))
        d = det(leftover=True, d1=d1("other", cc=0.9))
        self.lab.fuse(d)
        self.assertEqual(d.color, "other")                 # sorted only if the instruction gives `other` a bin
        for l in (d1("yellow", cc=0.4), d1("other", cc=0.7), {"error": "deadline"},
                  d1("yellow"),                                       # no known shape: robot part / glare?
                  d1("yellow", cc=0.8, shape="cube"),                 # colour not sure enough for a new object
                  d1("blue", shape="other")):
            d = det(leftover=True, d1=l)
            self.lab.fuse(d)
            self.assertTrue(d.other)                       # nobody knows its colour: dropped

    def test_tipped_stands(self):
        d = det(shape="tipped", d1=d1("red", shape="triangle"))
        self.lab.fuse(d)
        self.assertEqual(d.shape, "tipped")

    def test_shape_override_refits_yaw(self):
        a = np.radians(20)
        g = np.stack(np.meshgrid(np.linspace(-0.0225, 0.0225, 15), np.linspace(-0.0225, 0.0225, 15)), -1).reshape(-1, 2)
        xy = g @ np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
        d = det(shape="cylinder", d1=d1("red", shape="cube"), xy=xy)
        self.lab.fuse(d)
        self.assertEqual((d.shape, d.shape_geom, d.shape_src), ("cube", "cylinder", "d1"))
        self.assertAlmostEqual(np.degrees(d.yaw) % 90, 20, delta=2)

    def test_unsure_or_other_shape_keeps_geometry(self):
        for l in (d1("red", shape="cube", sc=0.4), d1("red", shape="other")):
            d = det(shape="triangle", d1=l)
            self.lab.fuse(d)
            self.assertEqual(d.shape, "triangle")


@unittest.skipUnless(HAVE_PIN and FRAMES, "needs OpenCV + Pinocchio + artifacts/monitor/sim_frames")
class TestAnyColourCamera(unittest.TestCase):
    def test_same_as_v15_and_finds_an_unknown_colour(self):
        from aaltonomous.interface.calibration import Calibration
        from decision_oracle.camera import HSV
        from decision_oracle.test_tipcheck import venue_scene
        from decision_oracle.upgrades_v15 import RidgeCamera
        from decision_oracle.upgrades_v16 import AnyColourCamera
        scene, cal = venue_scene(str(ROOT / "sim" / "venue_look" / "venue.yaml")), Calibration.load()
        z = np.load(FRAMES[0])
        v15 = RidgeCamera(scene, cal).detect(z["rgb"], z["depth"])
        v16 = AnyColourCamera(scene, cal).detect(z["rgb"], z["depth"])
        self.assertEqual([(d.color, d.shape) for d in v15], [(d.color, d.shape) for d in v16])   # nothing extra
        d = v15[0]
        x, y, w, h = d.bbox
        hsv = cv2.cvtColor(np.ascontiguousarray(z["rgb"]), cv2.COLOR_RGB2HSV)
        m = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in HSV[d.color]:
            m |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        m[:y], m[y + h:], m[:, :x], m[:, x + w:] = 0, 0, 0, 0
        hsv[m > 0, 0] = 70                                  # that object turns green: no HSV class covers it
        rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        self.assertEqual(len(RidgeCamera(scene, cal).detect(rgb, z["depth"])), len(v15) - 1)
        cam = AnyColourCamera(scene, cal)
        lo = [e for e in cam.detect(rgb, z["depth"]) if getattr(e, "leftover", False)]
        self.assertEqual(len(lo), 1)
        self.assertLess(np.linalg.norm(lo[0].top[:2] - d.top[:2]), 0.02)
        self.assertIsNone(lo[0].color)
        cam.leftovers = False                               # no key: exactly v1.5
        self.assertEqual(len(cam.detect(rgb, z["depth"])), len(v15) - 1)


@unittest.skipUnless(HAVE_PIN, "needs OpenCV + Pinocchio")
class TestRidgeFixV16Only(unittest.TestCase):
    """The lying-prism grasp fix (hand 18 mm along the ridge, ridge plan on either arm first) is on in v1.6 only."""

    def test_v16_on_v15_unchanged(self):
        import copy
        from aaltonomous.interface import tasks
        from decision_oracle.test_offline import FakeClient, setup
        from decision_oracle.test_tipcheck import venue_scene
        from decision_oracle.upgrades_v15 import V15OraclePolicy
        from decision_oracle.upgrades_v16 import V16OraclePolicy
        try:
            scene = venue_scene(str(ROOT / "sim" / "venue_look" / "venue.yaml"))
            layout = tasks.sample_layout(np.random.default_rng(0), **scene.layout_kwargs())
            pols = {"v15": V15OraclePolicy(FakeClient(scene, layout), scene=scene, sides="off", threaded=False,
                                           prefetch=False, log=None),
                    "v16": V16OraclePolicy(FakeClient(scene, layout), scene=scene, sides="off", threaded=False,
                                           prefetch=False, log=None, instruction="rules", labels="off")}
        except Exception as e:  # no URDF on laptops
            self.skipTest(f"planner unavailable: {e!r}")
        self.assertEqual(pols["v15"].planner.ridge_shift["right"], (0.0, 0.0))
        self.assertFalse(pols["v15"].planner.ridge_first)
        self.assertEqual(pols["v16"].planner.ridge_shift["right"], (18.0, 0.0))
        self.assertTrue(pols["v16"].planner.ridge_first and pols["v16"].relay.ridge_first)
        got = {}
        for k, pol in pols.items():        # near the body, ridge +40 deg, centre bin: only the right hand lines up
            setup(pol)
            pol._update_drop_offsets()
            d = copy.copy(pol.perception.detect()[0])
            d.top = np.array([0.21, 0.07, d.top[2]])
            d.shape, d.yaw, d.name = "tipped", np.radians(40.0), "t"
            p = pol.planner.plan(d, pol.arm_cmd, pol.hand_cmd, bin_name="center", relocate=False)
            got[k] = (p.side, "ridge" in str(p.reason))
        self.assertEqual(got["v15"], ("left", False))          # stock claw: never holds a lying prism
        self.assertEqual(got["v16"], ("right", True))


class TestDecisionLog(unittest.TestCase):
    def test_shape_mapping_keys_can_be_logged(self):
        import json
        from decision_oracle.upgrades_v16 import _jsonable
        rec = {"type": "instruction", "mapping": {"red": "left", ("red", "triangle"): "center"}, "rows": [{"a": 1}]}
        out = json.loads(json.dumps(_jsonable(rec)))
        self.assertEqual(out["mapping"], {"red": "left", "red triangle": "center"})
        self.assertEqual(out["rows"], [{"a": 1}])


if __name__ == "__main__":
    unittest.main()
