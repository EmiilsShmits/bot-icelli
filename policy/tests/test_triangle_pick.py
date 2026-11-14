"""Behavioral checks for the triangle planning tool's inputs and output contract."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

from tools.triangle_pick import TrianglePickTool, triangle_midpoint_shift  # noqa: E402
from policies.classical_v1 import ClassicalV1  # noqa: E402


class PlannerVariantStub(SimpleNamespace):
    """Stand-in for a policy-specific Planner subclass (e.g. v1.1's hand-over planner)."""

    def plan(self, det, arm_q, hand_q, bin_name=None, obstacles=(), relocate=True):
        self.calls.append((det, bin_name, relocate))
        return SimpleNamespace(
            ok=True, arm=np.zeros((2, 14)), hand=np.zeros((2, 14)), duration=2 / 30,
            safety_clips=0, side="left", target_bin=bin_name, waypoints={"grasp": det.top.copy()},
        )


class TestTrianglePickTool(unittest.TestCase):
    def setUp(self):
        scene = SimpleNamespace(cfg={"bins": {"centers": {"left": [0, 0], "center": [0, 0], "right": [0, 0]}}})
        self.calls = []
        self.base = PlannerVariantStub(
            cfg={}, scene=scene, post={}, home=np.zeros(14), kin=object(), safety=object(),
            spec=SimpleNamespace(arm_lower=np.full(14, -2), arm_upper=np.full(14, 2),
                                 hand_lower=np.full(14, -2), hand_upper=np.full(14, 2)),
            mapping={}, dt=1 / 30, calls=self.calls,
        )
        with patch("tools.triangle_pick.ArmKinematics"):
            self.tool = TrianglePickTool(self.base)
        self.planner = self.tool.planner
        self.planner.scene = scene
        self.planner.spec = self.base.spec
        self.obs = {"arm_q": np.zeros(14), "hand_q": np.zeros(14)}
        self.bound = self.tool.bind(self.obs)

    def test_valid_pose_returns_planned_joint_chunks(self):
        self.assertIsInstance(self.tool.planner, PlannerVariantStub)
        result = self.tool(self.obs, "red", [0.3, 0.1, 0.45], 0.4, "left")
        self.assertTrue(result["ok"])
        self.assertEqual(result["skill"], "pick_triangle")
        self.assertEqual(np.asarray(result["arm_q_target"]).shape, (2, 14))
        det, bin_name, relocate = self.calls[0]
        self.assertEqual(det.shape, "triangle")
        self.assertEqual(det.yaw, 0.4)
        self.assertEqual(bin_name, "left")
        self.assertTrue(relocate)

    def test_invalid_pose_refuses_without_planning(self):
        result = self.tool(self.obs, "red", [0.3, 0.1, 0.45], None, "left")
        self.assertFalse(result["ok"])
        self.assertEqual(self.calls, [])

    def test_out_of_limit_measured_state_refuses(self):
        obs = {"arm_q": np.full(14, 3.0), "hand_q": np.zeros(14)}
        result = self.tool(obs, "red", [0.3, 0.1, 0.45], 0.4, "left")
        self.assertFalse(result["ok"])
        self.assertIn("joint limits", result["reason"])
        self.assertEqual(self.calls, [])

    def test_malformed_tool_arguments_refuse_cleanly(self):
        result = self.tool(self.obs, [], [0.3, 0.1, 0.45], 0.4, "left")
        self.assertFalse(result["ok"])
        self.assertEqual(self.calls, [])

    def test_planner_rejection_returns_no_trajectory(self):
        self.tool.planner.plan = lambda *args, **kwargs: SimpleNamespace(
            ok=False, arm=None, hand=None, reason="IK unreachable",
        )
        result = self.tool(self.obs, "red", [0.3, 0.1, 0.45], 0.4, "left")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "IK unreachable")
        self.assertNotIn("arm_q_target", result)

    def test_triangle_contact_point_uses_support_face(self):
        self.assertAlmostEqual(triangle_midpoint_shift(0), 0.0075, places=6)
        self.assertAlmostEqual(triangle_midpoint_shift(np.pi / 3), -0.0075, places=6)

    def test_bound_agent_tool_hides_measured_joint_state(self):
        self.assertEqual(self.bound.__name__, "pick_triangle")
        result = self.bound("red", [0.3, 0.1, 0.45], 0.4, "left")
        self.assertTrue(result["ok"])

    def test_classical_policy_registers_tool_lazily(self):
        policy = ClassicalV1.__new__(ClassicalV1)
        policy.pol = SimpleNamespace(planner="policy planner")
        policy._tools = None
        with patch("tools.triangle_pick.TrianglePickTool", return_value="triangle skill") as constructor:
            tool = SimpleNamespace(bind=lambda observation: ("bound skill", observation))
            constructor.return_value = tool
            tools = policy.get_tools(self.obs)
            self.assertEqual(tools, {"pick_triangle": ("bound skill", self.obs)})
            self.assertEqual(policy.get_tools(self.obs), tools)
        constructor.assert_called_once_with("policy planner")


if __name__ == "__main__":
    unittest.main()
