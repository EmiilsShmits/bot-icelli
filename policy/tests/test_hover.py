"""V16_HOVER (decision_oracle/hover_v16.py): the hand is measured over the block and the rest of the pick is moved.

    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python -m unittest policy.tests.test_hover -v
"""
from __future__ import annotations

import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

ENV = {"GEMINI_API_KEY": "", "DECISION_KEY_FILE": "/nonexistent", "V16_LABELS": "off", "V16_INSTRUCTION": "rules"}
OFF = np.array([-0.012, -0.031, -0.008])          # the real hand is short, to the robot's right and low (m)


def build(**env):
    import server
    with mock.patch.dict(os.environ, {**ENV, **env}):
        return server.POLICIES["v1.6"]().pol


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.pol = build(V16_HOVER="on")
        except Exception as e:                    # no URDF / Pinocchio on this machine
            raise unittest.SkipTest(f"planner unavailable: {e!r}")
        from aaltonomous.baselines.classical.perception import Detection
        pol = cls.pol
        pol.prefetch = False
        pol._update_drop_offsets()
        d = Detection("red", np.array([0.30, -0.10, pol.scene.counter_z + pol.planner.height]), 400, 400, "depth")
        d.shape, d.name = "cube", "red_0"
        cls.plan = pol.planner.plan(d, pol.home, pol.post["open"], bin_name="right", relocate=False)
        assert cls.plan.ok, cls.plan.reason
        cls.ph = {n: (s, e) for n, s, e in cls.plan.phases}
        cls.cut = cls.ph["to_pregrasp"][1]

    def start(self, pol=None, option=True):
        """The policy at home with this plan started, as after a look."""
        pol = pol or self.pol
        pol.reset({"instruction": "", "mapping": {}})
        pol.prefetch = False
        pol.arm_cmd, pol.hand_cmd = pol.home.copy(), pol.post["open"].copy()
        plan = types.SimpleNamespace(**vars(self.plan))
        plan.summary = lambda: "test plan"
        if option:
            plan.option = types.SimpleNamespace(obj="red_0", route="direct", bin="right", shape="triangle",
                                                arm=plan.side, grasp="claw", drop=0, det=None, to_json=lambda: {})
        pol._truth_name = lambda o: None
        return plan, [pol._start(plan, 0.0)]

    def run_out(self, pol, acts, t=0.0, limit=4000):
        """Feed act() until the plan is done; the measured joints follow the commands. -> every commanded arm tick."""
        while pol.state == "executing" and len(acts) < limit:
            if not (pol.queue_a is not None and len(pol.queue_a)) and not pol.hover.pending() and pol._gc is None:
                break
            t += len(acts[-1]["arm_q_target"]) / 30.0
            acts.append(pol.act({"arm_q": pol.arm_cmd.copy(), "hand_q": pol.hand_cmd.copy(), "t": t,
                                 "head_depth": np.zeros((480, 640), np.uint16), "head_rgb": None}))
            time.sleep(0.002)
        return np.vstack([a["arm_q_target"] for a in acts])


class TestPath(Base):
    def test_moved_path(self):
        h, plan, side = self.pol.hover, self.plan, self.plan.side
        c = np.array([0.012, 0.031, 0.008])
        W = h.weights(plan, self.cut)
        A0 = plan.arm[self.cut:]
        A1, why = h.shift_path(side, A0, W, c)
        self.assertIsNotNone(A1, why)
        self.assertEqual(W[0], 1.0)
        self.assertEqual(W[-1], 0.0)
        self.assertTrue(np.all(np.diff(W) <= 1e-12))                      # 1 ... then down to 0, never back up
        rel = self.ph["open"][1] - self.cut                               # full shift through the release
        self.assertTrue(np.all(W[:rel] == 1.0))
        for i in list(range(0, rel, 7)) + [rel - 1]:
            moved = h.grasp_point(side, A1[i]) - h.grasp_point(side, A0[i])
            np.testing.assert_allclose(moved, c, atol=5e-4)
            h.kin._fk(A0[i]); R0 = h.kin.data.oMf[h.kin.palm[side]].rotation.copy()
            h.kin._fk(A1[i]); R1 = h.kin.data.oMf[h.kin.palm[side]].rotation
            ang = np.degrees(np.arccos(np.clip((np.trace(R0.T @ R1) - 1) / 2, -1, 1)))
            self.assertLess(ang, 0.5)                                     # the palm keeps its orientation
        np.testing.assert_array_equal(A1[-1], A0[-1])                     # ends where the plan ended
        other = slice(7, 14) if side == "left" else slice(0, 7)
        np.testing.assert_array_equal(A1[:, other], A0[:, other])         # the other arm is not touched

    def test_correct_is_safe_and_bounded(self):
        h, plan, pol = self.pol.hover, self.plan, self.pol
        a0, h0 = plan.arm[self.cut - 1], plan.hand[self.cut - 1]
        r = h.correct(plan, self.cut, plan.side, OFF, a0, h0)
        self.assertIn("arm", r, r)
        np.testing.assert_allclose(r["shift"], -OFF)
        full = np.vstack([a0[None], r["arm"]])
        self.assertLessEqual(np.abs(np.diff(full, axis=0)).max() * 30.0, 1.0 + 1e-6)      # arm speed cap, rad/s
        self.assertEqual(pol.planner.dry_run_safety(a0, h0, r["arm"], r["hand"]), 0)
        self.assertNotIn("arm", h.correct(plan, self.cut, plan.side, np.array([0.0, 0.002, 0.0]), a0, h0))   # tiny
        self.assertNotIn("arm", h.correct(plan, self.cut, plan.side, np.array([0.0, 0.09, 0.0]), a0, h0))    # absurd
        np.testing.assert_array_equal(r["arm"][-1], plan.arm[-1])
        self.assertEqual(r["at"](0), 0)
        self.assertGreaterEqual(r["at"](len(plan.arm) - self.cut - 1), len(plan.arm) - self.cut - 1)
        r = h.correct(plan, self.cut, plan.side, np.array([0.0, 0.0, 0.04]), a0, h0)      # "hand is 4 cm high"
        self.assertAlmostEqual(r["shift"][2], -h.max_down)                # never sent more than 1.5 cm lower
        self.assertIn("cut", r["note"])

    def test_joint_on_its_limit(self):
        """Most plans have a joint on its limit over the block (MuJoCo seed 1000: 'tick 0: 9.2 mm short'): the palm
        turns a few degrees instead and the grasp still moves by the full amount."""
        from aaltonomous.baselines.classical.perception import Detection
        pol, h = self.pol, self.pol.hover
        d = Detection("yellow", np.array([0.28, -0.06, pol.scene.counter_z + pol.planner.height]), 400, 400, "depth")
        d.shape, d.name = "cylinder", "yellow_0"
        plan = pol.planner.plan(d, pol.home, pol.post["open"], bin_name="center", relocate=False)
        self.assertTrue(plan.ok, plan.reason)
        side = plan.side
        ph = {n: (s, e) for n, s, e in plan.phases}
        cut = ph["to_pregrasp"][1]
        sl = h.kin.sl(side)
        q = plan.arm[cut][sl]
        self.assertLess(np.minimum(q - h.kin.lo[sl], h.kin.hi[sl] - q).min(), 0.01)       # a joint is on its limit
        off = np.array([0.002, -0.03 if side == "right" else 0.03, 0.0])
        a0, h0 = plan.arm[cut - 1], plan.hand[cut - 1]
        r = h.correct(plan, cut, side, off, a0, h0)
        self.assertIn("arm", r, r)
        self.assertLessEqual(h.turn_deg, h.max_turn)
        self.assertGreater(h.turn_deg, 0.5)                                               # it did have to turn
        A1, _ = h.shift_path(side, plan.arm[cut:], h.weights(plan, cut), -off, strict=ph["lift"][1] - cut)
        for i in range(0, ph["lift"][1] - cut, 5):                                        # down to the block and up
            moved = h.grasp_point(side, A1[i]) - h.grasp_point(side, plan.arm[cut + i])
            self.assertLess(np.linalg.norm(moved + off), 0.0046)
        full = np.vstack([a0[None], r["arm"]])
        self.assertLessEqual(np.abs(np.diff(full, axis=0)).max() * 30.0, 1.0 + 1e-6)
        self.assertEqual(pol.planner.dry_run_safety(a0, h0, r["arm"], r["hand"]), 0)
        h.max_turn = 0.5                                                                  # not allowed to turn: refused
        self.addCleanup(lambda: setattr(h, "max_turn", 12.0))
        self.assertNotIn("arm", h.correct(plan, cut, side, off, a0, h0))


class TestMeasure(Base):
    def cloud(self, T, arm_q, hand_q, side, shift):
        he = self.pol.cam.lean
        M, N = he.cloud(arm_q, hand_q)
        vis = np.einsum("ij,ij->i", N, T[:3, 3] - M) > 0
        mine = np.array([he.names[i].startswith(side) for i in he.link])
        P = (M + np.where(mine[:, None], shift, 0.0))[vis][::3]
        Ti = np.linalg.inv(T)
        return P @ Ti[:3, :3].T + Ti[:3, 3]

    def test_sees_the_hand_and_the_hanging_arm(self):
        import lean
        from decision_oracle import camera as C
        h, plan, pol, side = self.pol.hover, self.plan, self.pol, self.plan.side
        T = np.asarray(pol.cam.cal0._T(C.CAM), float)
        fr = (np.eye(4), T, T)
        cmd, hand = plan.arm[self.cut - 1], plan.hand[self.cut - 1]
        seen = np.array([-0.010, -0.025, 0.004])
        r = h.measure(self.cloud(T, cmd, hand, side, seen), cmd, hand, cmd, side, fr)
        self.assertIsNotNone(r["off"], r)
        self.assertLess(np.linalg.norm(r["off"] - seen), 0.003, r)
        meas = cmd.copy()                                   # the real arm hangs below its target
        meas[h.kin.sl(side)][0] += 0.05
        hang = h.grasp_point(side, meas) - h.grasp_point(side, cmd)
        self.assertGreater(np.linalg.norm(hang), 0.008)
        r = h.measure(self.cloud(T, meas, hand, side, seen), meas, hand, cmd, side, fr)
        self.assertFalse(h.use_hang)                        # default: logged, not corrected (Isaac: it empties the hand)
        self.assertLess(np.linalg.norm(r["off"] - seen), 0.003, r)
        self.assertLess(np.linalg.norm(r["hang"] - hang), 1e-9)
        h.use_hang = True                                   # V16_HOVER_HANG=on
        self.addCleanup(lambda: setattr(h, "use_hang", False))
        r = h.measure(self.cloud(T, meas, hand, side, seen), meas, hand, cmd, side, fr)
        self.assertLess(np.linalg.norm(r["off"] - (seen + hang)), 0.003, r)
        h.use_hang = False
        lean.set_fit_err({side: seen})                      # the planner already corrects that much (V16_ARM_SHIFT)
        self.addCleanup(lambda: lean.set_fit_err(None))
        r = h.measure(self.cloud(T, cmd, hand, side, seen), cmd, hand, cmd, side, fr)
        self.assertLess(np.linalg.norm(r["off"]), 0.003, r)

    def test_no_arm_fit_no_measure(self):
        h = self.pol.hover
        self.pol.cam.fit = None
        r = h.measure_depth(np.zeros((480, 640), np.uint16), self.pol.home, self.pol.post["open"], self.pol.home, "right")
        self.assertIsNone(r["off"])


class TestFlow(Base):
    def flow(self, result, option=True, mode_="on"):
        pol = self.pol
        pol.hover.mode = mode_
        self.addCleanup(lambda: setattr(pol.hover, "mode", "on"))
        with mock.patch.object(pol.hover, "measure_depth", lambda *a, **k: dict(result)):
            plan, acts = self.start(option=option)
            self.assertIsNotNone(pol.hover.st)
            return plan, self.run_out(pol, acts)

    def test_corrected_pick(self):
        for option in (True, False):                       # with and without the grasp check's own cut at the lift
            plan, A = self.flow({"off": OFF, "why": "", "seen": OFF, "hang": np.zeros(3), "known": np.zeros(3)}, option)
            h, side = self.pol.hover, plan.side
            self.assertTrue(h.last["corrected"], h.last)
            np.testing.assert_array_equal(A[:self.cut], plan.arm[:self.cut])           # up to the hover: the plan
            self.assertLessEqual(np.abs(np.diff(A, axis=0)).max() * 30.0, 1.0 + 1e-6)  # no jump anywhere
            np.testing.assert_array_equal(A[-1], plan.arm[-1])                         # ends where the plan ended
            low = lambda X: min(h.grasp_point(side, q)[2] for q in X[::3])
            g = int(np.argmin([h.grasp_point(side, q)[2] for q in A]))                 # the grasp: lowest point
            g0 = int(np.argmin([h.grasp_point(side, q)[2] for q in plan.arm]))
            moved = h.grasp_point(side, A[g]) - h.grasp_point(side, plan.arm[g0])
            np.testing.assert_allclose(moved, -OFF, atol=1.5e-3)                       # the grasp is moved by -off
            self.assertGreater(len(A), len(plan.arm))                                  # the hold over the block
            self.assertEqual(self.pol.planner.dry_run_safety(plan.arm[0], plan.hand[0], A, np.repeat(plan.hand[:1], len(A), 0)), 0)
            self.assertAlmostEqual(low(A), low(plan.arm) - OFF[2], places=2)

    def test_log_mode_and_failures_keep_the_plan(self):
        for res, mode_ in (({"off": OFF, "why": ""}, "log"), ({"off": None, "why": "hand not measured"}, "on"),
                           ({"off": np.array([0.0, 0.09, 0.0]), "why": ""}, "on")):
            plan, A = self.flow(res, mode_=mode_)
            self.assertFalse(self.pol.hover.last["corrected"])
            moving = A[np.r_[True, np.abs(np.diff(A, axis=0)).max(1) > 0]]              # drop the hold ticks
            ref = plan.arm[np.r_[True, np.abs(np.diff(plan.arm, axis=0)).max(1) > 0]]
            np.testing.assert_array_equal(moving, ref)

    def test_off_by_default_and_needs_lean(self):
        self.assertIsNone(build().hover)
        self.assertIsNone(build(V16_HOVER="on", V16_CALIB="bins").hover)
        self.assertEqual(build(V16_HOVER="log").hover.mode, "log")


if __name__ == "__main__":
    unittest.main()
