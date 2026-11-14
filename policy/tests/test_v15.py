"""Unit tests for v1.5 (policies/oracle_v15.py, decision_oracle/upgrades_v15.py).

    python -m unittest policy/tests/test_v15.py -v        # from the repo root

The mapping tests need only the instruction parser. The rest needs Pinocchio + OpenCV (the oracle planner and the
camera code import them); the planner test also needs the G1 URDF, so it runs on the sim machine. Fuller offline
check there: `python -m decision_oracle.upgrades_v15 --selftest 6` (side rule on every option, ridge grasp plans).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

from aaltonomous.interface import tasks  # noqa: E402

try:
    import cv2  # noqa: F401
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False


def _mapping(text, task="sort_language"):
    # oracle_v15 imports the policy server base class only; the policy itself is built lazily
    from policies.oracle_v15 import mapping_with_shapes
    return mapping_with_shapes(text, task)


class TestMapping(unittest.TestCase):
    def test_fixed(self):
        m, src = _mapping(tasks.FIXED_INSTRUCTION, "sort_fixed")
        self.assertEqual(m, dict(tasks.FIXED_MAPPING))

    def test_colour_only_has_no_shape_keys(self):
        m, _ = _mapping("Put the blue objects in the left bin, the red ones in the middle and the yellow ones right.")
        self.assertEqual({k: v for k, v in m.items() if isinstance(k, str)}, {"blue": "left", "red": "center",
                                                                            "yellow": "right"})
        self.assertFalse([k for k in m if not isinstance(k, str)])

    def test_shape_keys_win_and_tipped_follows_triangle(self):
        from aaltonomous.scene.scene import resolve_bin
        m, src = _mapping("Triangles go in the left bin, everything else in the right bin.")
        self.assertEqual(resolve_bin(m, "red", "triangle"), "left")
        self.assertEqual(resolve_bin(m, "red", "tipped"), "left")       # a triangle lying on its side
        self.assertEqual(resolve_bin(m, "blue", "cube"), "right")


@unittest.skipUnless(HAVE_PIN, "needs Pinocchio + OpenCV")
class TestV15Parts(unittest.TestCase):
    def test_side_rule(self):
        from decision_oracle.upgrades_v15 import SIDE_BAND, arm_allowed
        self.assertTrue(arm_allowed("left", 0.10) and not arm_allowed("left", -0.10))
        self.assertTrue(arm_allowed("right", -0.10) and not arm_allowed("right", 0.10))
        for arm in ("left", "right"):                         # the centre line is shared (relay points sit there)
            self.assertTrue(arm_allowed(arm, 0.0) and arm_allowed(arm, SIDE_BAND * 0.9))
            self.assertTrue(arm_allowed(arm, -SIDE_BAND * 0.9))

    def test_ridge_yaw_on_a_lying_prism_strip(self):
        from decision_oracle.upgrades_v15 import classify_top_v15
        for deg in (-80, -30, 0, 45, 89):
            a = np.radians(deg)
            u, v = np.meshgrid(np.linspace(-0.0225, 0.0225, 40), np.linspace(-0.0035, 0.0035, 5))
            pts = np.c_[u.ravel() * np.cos(a) - v.ravel() * np.sin(a), u.ravel() * np.sin(a) + v.ravel() * np.cos(a)]
            shape, yaw, centre, f = classify_top_v15(pts)
            self.assertEqual(shape, "tipped")
            err = abs((yaw - a + np.pi / 2) % np.pi - np.pi / 2)
            self.assertLess(np.degrees(err), 2.0, f"ridge at {deg} deg read as {np.degrees(yaw):.1f}")
            self.assertLess(np.linalg.norm(centre), 1e-3)

    def test_standing_shapes_unchanged(self):
        from decision_oracle import camera
        from decision_oracle.upgrades_v15 import classify_top_v15
        s = np.linspace(-0.0225, 0.0225, 30)
        cube = np.array([[x, y] for x in s for y in s])
        self.assertEqual(classify_top_v15(cube)[:2], camera.classify_top(cube)[:2])

    def test_planner_side_rule(self):
        try:
            from aaltonomous.scene.scene import Scene
            from decision_oracle.test_offline import FakeClient, setup
            from decision_oracle.upgrades_v15 import V15OraclePolicy, arm_allowed
            scene = Scene.load()
            rng = np.random.default_rng(3)
            fc = FakeClient(scene, tasks.sample_layout(rng, **scene.layout_kwargs()))
            pol = V15OraclePolicy(fc, threaded=False, prefetch=False, log=None)
        except Exception as e:  # no URDF on laptops
            self.skipTest(f"planner unavailable: {e!r}")
        setup(pol)
        pol._update_drop_offsets()
        opts, _ = pol.enum.feasible_options(pol.perception.detect(), pol.arm_cmd, pol.hand_cmd, budget_s=4.0)
        for o in opts:
            self.assertTrue(arm_allowed(o.arm, o.det.top[1]), f"{o.arm} arm for an object at y {o.det.top[1]:+.3f}")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_PIN, "needs Pinocchio + OpenCV")
class TestRidgeShift(unittest.TestCase):
    def test_parse(self):
        from decision_oracle.upgrades_v15 import _ridge_shift
        self.assertEqual(_ridge_shift(""), {"left": (0.0, 0.0), "right": (0.0, 0.0)})
        self.assertEqual(_ridge_shift("18,0"), {"left": (18.0, 0.0), "right": (18.0, 0.0)})
        self.assertEqual(_ridge_shift("right:18,-6"), {"left": (0.0, 0.0), "right": (18.0, -6.0)})

    def test_palm_z_is_mirrored(self):
        from decision_oracle.upgrades_v15 import palm_z_dir
        f = np.array([1.0, 0.0, 0.0])                       # fingers forward: palm +z points to the body's midline
        self.assertTrue(np.allclose(palm_z_dir("left", f), [0, -1, 0]))
        self.assertTrue(np.allclose(palm_z_dir("right", f), [0, 1, 0]))

    def test_shift_moves_the_closed_pinch_onto_the_prism(self):
        """With the hand 18 mm further along the ridge the closed thumb and fingertips straddle the prism's centre
        (thumb short of the near end face by < 22.5 mm, fingers short of the far one): both arms, mirrored."""
        try:
            import copy
            from aaltonomous.baselines.classical.config import hand_postures
            from aaltonomous.scene.scene import Scene
            from decision_oracle import upgrades_v15 as U
            from decision_oracle.test_offline import FakeClient, setup
            scene = Scene.load()
            fc = FakeClient(scene, tasks.sample_layout(np.random.default_rng(0), **scene.layout_kwargs()))
            pol = U.V15OraclePolicy(fc, sides="off", threaded=False, prefetch=False, log=None)
        except Exception as e:  # no URDF on laptops
            self.skipTest(f"planner unavailable: {e!r}")
        setup(pol)
        pol._update_drop_offsets()
        det0 = pol.perception.detect()[0]
        closed = hand_postures(pol.cfg, pol.spec)["closed"]
        try:
            for shift, inside in (((0.0, 0.0), False), ((18.0, 0.0), True)):
                pol.planner.ridge_shift = {"left": shift, "right": shift}
                for side, y in (("left", 0.08), ("right", -0.08)):
                    d = copy.copy(det0)
                    d.top = np.array([0.26, y, det0.top[2]])
                    d.shape, d.yaw, d.name = "tipped", 0.1 if side == "left" else -0.1, "t"
                    p = pol.planner._plan_side_faces(d, side, side, pol.arm_cmd, pol.hand_cmd)
                    self.assertTrue(p.ok and "ridge" in p.reason, p.reason)
                    a = np.radians(float(p.reason.split("(")[1].split(" deg")[0]))
                    e = next(e for n, s, e in p.phases if n == "descend")
                    pol.kin._fk(p.arm[e - 1], closed)
                    u = [(t[:2] - d.top[:2]) @ [np.cos(a), np.sin(a)] for t in pol.kin._tips(side)]
                    thumb_in = -0.0225 < u[2] < 0
                    self.assertEqual(thumb_in, inside, f"{side} shift {shift}: thumb at {u[2] * 1000:.0f} mm")
                    self.assertTrue(0 < u[0] < 0.0225 or not inside)
        finally:
            del pol.planner.ridge_shift
