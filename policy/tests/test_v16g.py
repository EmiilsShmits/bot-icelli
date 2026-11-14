"""Unit tests for v1.6g's instruction stage (policy/instruction_gemma.py, policies/oracle_v16g.py).
No network and no weights needed: Gemma and Decision answers here are fakes. With the real weights in
policy/weights/gemma-parser-1b (or GEMMA_PARSER_DIR) and torch installed, one more test runs the real student.

    python -m pytest policy/tests/test_v16g.py -v        # from the repo root
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "policy"), str(ROOT / "third_party" / "aaltonomous-humanoid")]

import instruction_d1 as D  # noqa: E402
import instruction_gemma as G  # noqa: E402
from spec import SLOTS, fixed_order  # noqa: E402

try:
    import cv2  # noqa: F401
    import pinocchio  # noqa: F401
    HAVE_PIN = True
except ImportError:
    HAVE_PIN = False
try:
    import torch  # noqa: F401
    import transformers  # noqa: F401
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False
WEIGHTS = Path(os.environ.get("GEMMA_PARSER_DIR") or G.DEFAULT_DIR)

CB = {"red": "left", "yellow": "center", "blue": "right"}
OTHER = {"red": "right", "yellow": "left", "blue": "center"}


def slots_for(colour_bins, other="leave"):
    out = {s: colour_bins[s.split()[0]] for s in SLOTS if s != "other"}
    out["other"] = other
    return out


def decision_answer(slots, conf=0.95):
    return {"answers": {D._qname(s): {"choice": v, "confidence": conf} for s, v in slots.items()}}


class TestGemmaStage(unittest.TestCase):
    def test_answer_is_parsed(self):
        g = G.GemmaInstruction(generate=lambda t: fixed_order(slots_for(CB)))
        g.start("Red left, yellow middle, blue right.")
        slots, rec = g.result()
        self.assertEqual(slots, slots_for(CB))
        self.assertTrue(rec["used"])

    def test_centre_and_middle_are_center(self):
        raw = fixed_order(slots_for(CB)).replace("center", "centre", 1)
        g = G.GemmaInstruction(generate=lambda t: raw)
        g.start("x")
        self.assertEqual(g.result()[0], slots_for(CB))

    def test_malformed_and_invalid_are_no_answer(self):
        for raw, why in (("left left left", "malformed answer"), ("banana " * 10, "malformed answer"),
                         ("invalid", "model says invalid")):
            g = G.GemmaInstruction(generate=lambda t, raw=raw: raw)
            g.start("x")
            slots, rec = g.result()
            self.assertIsNone(slots)
            self.assertFalse(rec["used"])
            self.assertEqual(rec["why"], why)

    def test_start_never_blocks_and_deadline_holds(self):
        def slow(text):
            time.sleep(1.0)
            return fixed_order(slots_for(CB))
        g = G.GemmaInstruction(deadline_s=0.3, generate=slow)
        t = time.monotonic()
        g.start("x")
        self.assertLess(time.monotonic() - t, 0.05)
        slots, rec = g.result()
        self.assertLess(time.monotonic() - t, 0.6)
        self.assertIsNone(slots)
        self.assertEqual(rec["why"], "deadline")

    def test_new_start_cancels_old_job(self):
        seen = []

        def slow(text):
            time.sleep(0.3)
            seen.append(text)
            return fixed_order(slots_for(CB if text == "new" else OTHER))
        g = G.GemmaInstruction(deadline_s=2.0, generate=slow)
        g.start("old")
        g.start("new")
        slots, rec = g.result()
        self.assertEqual(slots, slots_for(CB))           # the old answer never replaces the new one

    def test_generate_error_is_no_answer(self):
        def boom(text):
            raise RuntimeError("out of memory")
        g = G.GemmaInstruction(generate=boom)
        g.start("x")
        slots, rec = g.result()
        self.assertIsNone(slots)
        self.assertIn("RuntimeError", rec["why"])

    def test_no_weights_is_off(self):
        g = G.GemmaInstruction(path=ROOT / "artifacts" / "no-such-weights")
        self.assertFalse(g.enabled)
        self.assertIn("no weights", g.why_off)
        g.start("x")
        slots, rec = g.result()
        self.assertIsNone(slots)
        self.assertIn("off", rec["why"])


class TestChain(unittest.TestCase):
    def chain(self, decision=None, gemma=None, d_deadline=0.5, g_deadline=1.0):
        d = None if decision is None else D.DecisionInstruction(deadline_s=d_deadline, call=decision)
        g = None if gemma is None else G.GemmaInstruction(deadline_s=g_deadline, generate=gemma)
        return G.InstructionChain(d, g)

    def test_decision_first(self):
        c = self.chain(lambda b: decision_answer(slots_for(CB)), lambda t: fixed_order(slots_for(OTHER)))
        c.start("x")
        slots, rec = c.result()
        self.assertEqual((slots, rec["source"]), (slots_for(CB), "decision"))

    def test_gemma_when_decision_unsure_fails_or_late(self):
        def late(body):
            time.sleep(1.0)
            return decision_answer(slots_for(CB))

        def boom(body):
            raise ConnectionError("no network")
        for decision in (lambda b: decision_answer(slots_for(CB), conf=0.3), boom, late):
            c = self.chain(decision, lambda t: fixed_order(slots_for(OTHER)), d_deadline=0.3)
            c.start("x")
            slots, rec = c.result()
            self.assertEqual((slots, rec["source"]), (slots_for(OTHER), "gemma"))
            self.assertFalse(rec["decision"]["used"])

    def test_offline_is_gemma_then_rules(self):
        c = G.InstructionChain(D.DecisionInstruction(key=""), G.GemmaInstruction(generate=lambda t: "invalid"))
        self.assertIsNone(c.decision)
        c.start("x")
        slots, rec = c.result()
        self.assertIsNone(slots)                         # the caller keeps the rule parser's mapping
        self.assertIsNone(rec["source"])
        self.assertEqual(rec["gemma"]["why"], "model says invalid")

    def test_nothing_on(self):
        c = G.InstructionChain(D.DecisionInstruction(key=""), G.GemmaInstruction(path=ROOT / "no-such-weights"))
        self.assertFalse(c.enabled)
        c.start("x")
        self.assertIsNone(c.result()[0])

    def test_decision_answer_cancels_gemma(self):
        started, cancelled = threading.Event(), []
        g = G.GemmaInstruction(deadline_s=2.0, generate=lambda t: (started.set(), time.sleep(0.3),
                                                                 fixed_order(slots_for(OTHER)))[-1])
        c = G.InstructionChain(D.DecisionInstruction(call=lambda b: decision_answer(slots_for(CB))), g)
        c.start("x")
        self.assertEqual(c.result()[1]["source"], "decision")
        started.wait(1.0)
        cancelled.append(g._job[1].is_set())
        self.assertTrue(cancelled[0])


@unittest.skipUnless(HAVE_PIN, "needs OpenCV + Pinocchio")
class TestPolicyWiring(unittest.TestCase):
    def test_first_look_takes_gemma_when_offline(self):
        os.environ.pop("GEMINI_API_KEY", None)
        from policies.oracle_v16g import make_inner
        from instruction_d1 import slots_to_mapping
        gemma = G.GemmaInstruction(generate=lambda t: fixed_order(slots_for(OTHER)))
        pol = make_inner(gemma)(None, sides="off", perception="camera", grasp_check="on", threaded=True,
                                labels="off", instruction="d1", time_limit=120.0)
        if pol.instr.decision is not None:
            self.skipTest("a Gemini key is configured on this machine")
        text = "Red to the right, yellow to the left, blue in the middle."
        from policies.oracle_v15 import mapping_with_shapes
        pol.reset({"instruction": text, "mapping": mapping_with_shapes(text)[0]})
        self.assertTrue(pol._instr_pending)
        pol._apply_instruction()
        self.assertEqual(pol.mapping, slots_to_mapping(slots_for(OTHER)))
        self.assertEqual(pol.mapping_source, "gemma")


@unittest.skipUnless(HAVE_TORCH and (WEIGHTS / "config.json").exists(), "needs torch and the Gemma parser weights")
class TestRealStudent(unittest.TestCase):
    def test_loads_self_tests_and_reads_a_paraphrase(self):
        g = G.GemmaInstruction(path=WEIGHTS, deadline_s=60.0)
        self.assertTrue(g.enabled, g.why_off)
        g.start("Yellow blocks go in the left bin, red ones in the right bin and blue ones in the middle.")
        slots, rec = g.result()
        self.assertEqual(slots, slots_for({"red": "right", "yellow": "left", "blue": "center"}), rec)


if __name__ == "__main__":
    unittest.main()
