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

try:  # the planner tests need Pinocchio and the G1 URDF: they run on the sim machine, not on Windows laptops
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False


class TestInstruction(unittest.TestCase):
    def test_fixed_task(self):
        self.assertEqual(mapping_for(tasks.FIXED_INSTRUCTION, "sort_fixed"), (tasks.FIXED_MAPPING, "fixed"))

    def test_real_fixed_wording(self):  # Aalto: real rung 1 = yellow -> left, purple -> center, orange -> right
        text = "Put the yellow objects in the left bin, the purple objects in the center bin and the orange objects in the right bin."
        self.assertEqual(mapping_for(text, "sort_fixed")[0], {"yellow": "left", "blue": "center", "red": "right"})

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


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (sim machine or Docker build)")
class TestV11Planner(unittest.TestCase):
    """v1.1: far cross-body objects are handed over by the arm on their side; others are planned as before."""

    @classmethod
    def setUpClass(cls):
        from policies.classical_v11 import ClassicalV11
        cls.v = ClassicalV11()
        cls.v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")   # red -> left, yellow -> center, blue -> right

    def plan(self, color, x, y):
        from aaltonomous.baselines.classical.perception import Detection
        pol = self.v.pol
        det = Detection(color, np.array([x, y, pol.scene.counter_z + pol.planner.height]), 400, 400, "depth")
        return pol.planner.plan(det, pol.home, pol.post["open"])

    def test_far_cross_body_is_handed_over(self):
        for color, y, carrier in (("red", -0.155, "right"), ("blue", 0.165, "left")):
            p = self.plan(color, 0.29, y)
            self.assertTrue(p.ok, p.reason)
            self.assertEqual((p.target_bin, p.side), ("counter", carrier), p.reason)
            self.assertTrue(p.reason.startswith("hand-over"), p.reason)

    def test_near_and_same_side_go_straight_to_the_bin(self):
        for color, y, bin_name in (("red", -0.03, "left"), ("red", 0.15, "left"), ("blue", -0.15, "right"),
                                   ("yellow", -0.15, "center")):
            p = self.plan(color, 0.29, y)
            self.assertTrue(p.ok, p.reason)
            self.assertEqual(p.target_bin, bin_name, f"{color} at y={y}: {p.reason}")

    def test_handover_spots_near_the_middle(self):
        from aaltonomous.baselines.classical.perception import Detection
        from policies.classical_v11 import HANDOVER_Y
        pol = self.v.pol
        det = Detection("red", np.array([0.29, -0.155, 0.05]), 400, 400, "depth")
        spots = pol.planner.relocation_spots(det, "left")
        self.assertTrue(spots)
        self.assertLess(abs(spots[0][1] - HANDOVER_Y), 0.03, spots[0])


def plane_depth(extra_tilt_deg):
    """Synthetic head depth (mm) of an endless table at counter height, seen by a camera tilted extra_tilt_deg
    (about its optical x axis) away from calibration.yaml's pose."""
    from aaltonomous.interface.calibration import Calibration
    from aaltonomous.scene.scene import Scene
    cal, scene = Calibration.load(), Scene.load()
    c, T = cal.cams["head"], cal._T("head")
    a = np.radians(extra_tilt_deg)
    R = T[:3, :3] @ np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    v, u = np.mgrid[0:c.height, 0:c.width]
    ray = np.stack([(u - c.K[0, 2]) / c.K[0, 0], (v - c.K[1, 2]) / c.K[1, 1], np.ones(u.shape)], -1)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (scene.counter_z - T[2, 3]) / (ray @ R[2])     # optical depth (m) where the ray meets the table
    return np.where((s > 0.15) & (s < 1.5), s * 1000, 0).astype(np.uint16), cal, scene


class TestHeadPose(unittest.TestCase):
    """policy/headpose.py (Emīls's fit): the table-plane part on synthetic depth, and the acceptance limits."""

    def test_tilt_recovered(self):
        from headpose import fit_head_pose, plausible
        for tilt in (0.0, 5.0, -10.0):
            depth, cal, scene = plane_depth(tilt)
            fit = fit_head_pose(depth, cal, scene)
            self.assertTrue(fit.ok, fit.why)
            self.assertAlmostEqual(fit.tilt_deg, abs(tilt), delta=0.3, msg=fit.summary())
            self.assertTrue(plausible(fit), fit.summary())

    def test_plausible_limits(self):
        from headpose import PoseFit, plausible
        T = np.eye(4)
        self.assertTrue(plausible(PoseFit(T, True, tilt_deg=10.0, dxy=(0.02, -0.01), dyaw_deg=1.0)))
        self.assertFalse(plausible(PoseFit(T, False)))
        self.assertFalse(plausible(PoseFit(T, True, tilt_deg=20.0)))
        self.assertFalse(plausible(PoseFit(T, True, dxy=(0.08, 0.0))))
        self.assertFalse(plausible(PoseFit(T, True, dyaw_deg=7.0)))


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (sim machine or Docker build)")
class TestResetNeverBlocks(unittest.TestCase):
    """A planning thread left over from the last episode must not delay reset() (watchdog: 3 s of sim time)."""

    def test_stale_planning_thread(self):
        import time
        from policies.classical_v1 import ClassicalV1
        v = ClassicalV1()
        v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")
        job = {"obs": None, "result": None}
        v.pol._job = job                                        # the old episode's look, still planning
        t0 = time.monotonic()
        v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")
        self.assertLess(time.monotonic() - t0, 0.5)             # returns at once
        obs = {"arm_q": v.pol.home.copy(), "hand_q": v.pol.post["open"].copy(), "t": 0.0}
        a = v.act(obs)                                          # holds while the old thread runs
        self.assertEqual(a["arm_q_target"].shape[1], 14)
        self.assertTrue(np.allclose(a["arm_q_target"], a["arm_q_target"][0]))
        self.assertIsNotNone(v._pending_reset)
        job["result"] = ("none", None, 0)                       # old thread done
        v.act(obs)                                              # reset applied, Aalto's policy takes over
        self.assertIsNone(v._pending_reset)
        self.assertIsNone(v.pol._job)


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (sim machine or Docker build)")
class TestV12(unittest.TestCase):
    def test_fit_used_then_reset(self):
        from policies.classical_v12 import ClassicalV12
        v = ClassicalV12()
        v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")
        pol = v.pol
        T0 = pol.cal._T("head").copy()
        pol.arm_cmd, pol.hand_cmd = pol.home.copy(), pol.post["open"].copy()
        pol._look({"head_rgb": np.zeros((480, 640, 3), np.uint8), "head_depth": plane_depth(-8.0)[0]})
        self.assertIsNotNone(pol.head_fit)
        self.assertAlmostEqual(pol.head_fit.tilt_deg, 8.0, delta=0.3)
        self.assertFalse(np.allclose(pol.cal._T("head"), T0))          # perception now uses the fitted pose
        v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")
        self.assertTrue(np.allclose(pol.cal._T("head"), T0))           # next episode starts from calibration.yaml
        self.assertIsNone(pol.head_fit)


@unittest.skipUnless(HAVE_PIN, "needs pinocchio + the G1 URDF (sim machine or Docker build)")
class TestV13DropSpots(unittest.TestCase):
    """v1.3: the n-th drop into a bin goes to a different spot, inside the walls, so objects don't stack."""

    @classmethod
    def setUpClass(cls):
        from policies.classical_v13 import ClassicalV13
        cls.v = ClassicalV13()
        cls.v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")   # red -> left, yellow -> center, blue -> right

    def det(self, color, y):
        from aaltonomous.baselines.classical.perception import Detection
        pol = self.v.pol
        return Detection(color, np.array([0.29, y, pol.scene.counter_z + pol.planner.height]), 400, 400, "depth")

    def test_spots_inside_the_walls_and_apart(self):
        from policies.classical_v13 import MIN_WALL
        pl = self.v.pol.planner
        for name in ("left", "center", "right"):
            for side in ("left", "right"):
                spots = pl.drop_spots(name, side)
                self.assertEqual(len(spots), 3, (name, side))
                lo, hi = pl._inner_box(name)
                for p in spots:
                    self.assertTrue(np.all(p >= lo + MIN_WALL - 1e-6) and np.all(p <= hi - MIN_WALL + 1e-6), (name, p))
                for i in range(3):
                    for j in range(i):
                        self.assertGreaterEqual(np.linalg.norm(spots[i] - spots[j]), 0.045, (name, side))

    def test_next_drop_goes_elsewhere(self):
        pol, seen = self.v.pol, {}
        for color, y, b in (("red", 0.15, "left"), ("yellow", -0.10, "center"), ("blue", -0.15, "right")):
            got = []
            for n in range(3):
                pol.planner.drop_count = {b: n}
                p = pol.planner.plan(self.det(color, y), pol.home, pol.post["open"])
                self.assertTrue(p.ok, p.reason)
                got.append(tuple(np.round(p.waypoints["drop"][:2], 3)))
            seen[b] = got
            self.assertEqual(len(set(got)), 3, f"{b}: drop points for counts 0, 1, 2 = {got}")
        print("\n  v1.3 drop points (counts 0, 1, 2):", seen)
        pol.planner.drop_count = {}

    def test_count_per_episode(self):
        pol = self.v.pol
        p = pol.planner.plan(self.det("red", 0.15), pol.home, pol.post["open"])
        pol._start(p, 0.0)
        self.assertEqual(pol.planner.drop_count, {"left": 1})
        h = pol.planner.plan(self.det("red", -0.155), pol.home, pol.post["open"])   # far cross-body: hand-over
        self.assertEqual(h.target_bin, "counter", h.reason)
        pol._start(h, 0.0)
        self.assertEqual(pol.planner.drop_count, {"left": 1})                        # a hand-over isn't a drop
        self.v.reset(tasks.FIXED_INSTRUCTION, "sort_fixed")
        self.assertEqual(pol.planner.drop_count, {})


if __name__ == "__main__":
    unittest.main()
