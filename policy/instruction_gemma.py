"""Instruction -> 10 slots with the fine-tuned Gemma 3 1B student, offline on the CPU (v1.6g), and the v1.6g chain
Gemini Decision 1 -> Gemma 1B -> rule parser.

    g = GemmaInstruction()                    # weights from policy/weights/gemma-parser-1b (or GEMMA_PARSER_DIR); loads
                                              # them now (server start) and answers one self-test; off without them
    g.start(instruction)                      # reset(): one generate() in a background thread, returns at once
    slots, rec = g.result()                   # planning thread: waits until `deadline_s` after start(); never raises

    chain = InstructionChain(DecisionInstruction(), g)     # what policies/oracle_v16g.py uses
    chain.start(instruction)
    slots, rec = chain.result()               # rec["source"]: "decision" | "gemma" | None (the rules' mapping stays)

The student (training/instruction_parser, RESULTS.md and training/MODELS.md `ck-parser-1b`): Gemma 3 1B-it, full
fine-tune on 23,089 examples (programmatic + Aalto's templates + Gemma 4 31B paraphrases), prompt `prompts.FT_PREFIX`,
answer format B (the 10 slot values in `spec.SLOTS` order). Offline, as evaluated there: T2a 94.7 % exact / 0.9 %
confidently wrong, T2b 90.6 % / 8.0 % (rule parser 86.7 % / 3.2 % and 60.1 % / 6.6 %).

An answer that is not 10 valid slot values, or says `invalid`, counts as no answer: the next stage (the rule parser's
mapping, already set in reset()) stays. Prompt and parsing are the training code's own (`prompts.ft_messages`,
`spec.from_fixed_order`), so the image answers exactly as the evaluated student.

Env: GEMMA_PARSER_DIR (weights folder), V16G_GEMMA_DEADLINE (s after start(), default 5), V16G_GEMMA_THREADS (torch
CPU threads, default min(8, CPUs - 2)), V16G_GEMMA_DTYPE (float32 | bfloat16, default float32: bfloat16 is slow on
CPUs without native bf16).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

import instruction  # noqa: F401  (puts training/instruction_parser on sys.path)
from spec import INVALID, SLOTS, VALUES, from_fixed_order

log = logging.getLogger("bot-icelli.instruction_gemma")

DEFAULT_DIR = Path(__file__).resolve().parent / "weights" / "gemma-parser-1b"
MAX_NEW_TOKENS = 40                       # as training/instruction_parser/llm.py for format B
WORDS = set(VALUES) | {"centre", "middle"}  # what spec.from_fixed_order accepts as a slot value

# Self-test at load: Aalto's fixed instruction must come back as its fixed mapping (training data: T1 is 100 %).
SELF_TEST = ("Put the red objects in the left bin, the yellow objects in the center bin and the blue objects in the "
             "right bin.")
SELF_TEST_BINS = {"red": "left", "yellow": "center", "blue": "right"}


def _threads():
    try:
        n = len(os.sched_getaffinity(0))
    except AttributeError:                # Windows / macOS
        n = os.cpu_count() or 2
    return int(os.environ.get("V16G_GEMMA_THREADS") or max(1, min(8, n - 2)))


def _ft_messages(text):
    from prompts import ft_messages       # training/instruction_parser/prompts.py: the exact training prompt
    return ft_messages(text)


class GemmaInstruction:
    def __init__(self, path=None, deadline_s=None, threads=None, dtype=None, generate=None, self_test=True):
        """generate: optional fake (text -> raw answer text), for tests; then no weights are loaded."""
        self.deadline_s = float(os.environ.get("V16G_GEMMA_DEADLINE", 5.0)) if deadline_s is None else deadline_s
        self.path = Path(path or os.environ.get("GEMMA_PARSER_DIR") or DEFAULT_DIR)
        self.threads = threads or _threads()
        self.dtype = dtype or os.environ.get("V16G_GEMMA_DTYPE", "float32")
        self._fake = generate
        self.tok = self.model = None
        self.enabled, self.why_off = False, ""
        self.load_s = self.self_test_s = None
        self._job = None                  # (future, cancel event, t_start)
        self._lock = threading.Lock()
        self.pool = None
        if generate is not None:
            self.enabled = True
        elif not (self.path / "config.json").exists():
            self.why_off = f"no weights in {self.path}"
        else:
            try:
                self._load()
                self.enabled = True
            except Exception as e:        # missing torch / transformers, broken weights: the rules stay
                self.why_off = f"load failed: {type(e).__name__}: {str(e)[:120]}"
                log.exception("Gemma parser: load failed")
        if self.enabled:
            self.pool = ThreadPoolExecutor(1, thread_name_prefix="gemma-parser")
            if self_test and generate is None:
                self._self_test()
        if self.enabled:
            log.info("Gemma parser on: %s, %d CPU threads, %s, load %.1f s, self-test %.2f s, deadline %.1f s",
                     self.path, self.threads, self.dtype, self.load_s or 0, self.self_test_s or 0, self.deadline_s)
        else:
            log.warning("Gemma parser off (%s): Decision 1 -> rule parser only", self.why_off)

    # ------------------------------------------------------------------ model
    def _load(self):
        t = time.monotonic()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch.set_num_threads(self.threads)
        self.tok = AutoTokenizer.from_pretrained(self.path)
        self.model = AutoModelForCausalLM.from_pretrained(self.path, dtype=getattr(torch, self.dtype))
        self.model.eval()
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.load_s = round(time.monotonic() - t, 2)

    def _self_test(self):
        t = time.monotonic()
        try:
            slots, info = self._call(SELF_TEST, threading.Event())
        except Exception as e:
            slots, info = None, {"why": f"{type(e).__name__}: {str(e)[:120]}"}
        self.self_test_s = round(time.monotonic() - t, 2)
        want = {s: SELF_TEST_BINS.get(s.split()[0], "leave") for s in SLOTS}
        if slots != want:
            self.enabled = False
            self.why_off = f"self-test failed: {info.get('raw', info.get('why'))!r}"
            log.error("Gemma parser: %s", self.why_off)

    def _generate(self, text, cancel):
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        torch.set_num_threads(self.threads)          # per thread: the pool thread runs the ops
        msgs = _ft_messages(text)
        try:
            prompt = self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False,
                                                  enable_thinking=False)
        except TypeError:
            prompt = self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False)
        n0, tok = enc["input_ids"].shape[1], self.tok

        class Stop(StoppingCriteria):               # cancel, or 10 complete slot words (saves the end-of-turn step)
            def __call__(self, input_ids, scores, **kw):
                done = cancel.is_set()
                if not done:
                    w = tok.decode(input_ids[0, n0:], skip_special_tokens=True).lower().replace(",", " ").split()
                    done = w[:1] == [INVALID] or (len(w) >= len(SLOTS) and all(x in WORDS for x in w[:len(SLOTS)]))
                return torch.full((input_ids.shape[0],), done, dtype=torch.bool, device=input_ids.device)

        with torch.inference_mode():
            out = self.model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, temperature=None,
                                      top_p=None, top_k=None, pad_token_id=self.tok.pad_token_id,
                                      stopping_criteria=StoppingCriteriaList([Stop()]))
        return self.tok.decode(out[0, n0:], skip_special_tokens=True)

    def _call(self, text, cancel):
        t = time.monotonic()
        raw = self._fake(text) if self._fake is not None else self._generate(text, cancel)
        info = {"raw": " ".join(str(raw).split())[:120], "latency_s": round(time.monotonic() - t, 2)}
        if cancel.is_set():
            return None, {**info, "why": "cancelled"}
        pred = from_fixed_order(str(raw))
        if pred is None:
            return None, {**info, "why": "malformed answer"}
        if pred == INVALID:
            return None, {**info, "why": "model says invalid"}
        return pred, info

    # ------------------------------------------------------------------ episode
    def start(self, text):
        """reset(): never blocks. A previous episode's generate() that is still running is cancelled, not waited for."""
        with self._lock:
            if self._job is not None:
                self._job[1].set()
            self._job = None
            if not self.enabled or not (text or "").strip():
                return
            cancel = threading.Event()
            self._job = (self.pool.submit(self._call, text, cancel), cancel, time.monotonic())

    def cancel(self):
        """The answer is not needed (Decision answered): stop generating at the next token, freeing the CPU."""
        with self._lock:
            if self._job is not None:
                self._job[1].set()

    def result(self):
        """-> (slots or None, record). Waits at most until deadline_s after start(); never raises."""
        with self._lock:
            job = self._job
        if job is None:
            return None, {"used": False, "why": f"off ({self.why_off})" if not self.enabled else "no call"}
        fut, cancel, t0 = job
        try:
            slots, info = fut.result(timeout=max(0.0, self.deadline_s - (time.monotonic() - t0)))
        except FutureTimeout:
            cancel.set()
            return None, {"used": False, "why": "deadline", "waited_s": round(time.monotonic() - t0, 2)}
        except Exception as e:            # a generate() error
            return None, {"used": False, "why": f"{type(e).__name__}: {str(e)[:80]}",
                          "waited_s": round(time.monotonic() - t0, 2)}
        return slots, {"used": slots is not None, **info}


class InstructionChain:
    """Decision 1 (online) -> Gemma 1B (offline) -> no answer (the caller keeps the rule parser's mapping).

    Same interface as instruction_d1.DecisionInstruction (enabled / start / result), so v1.6's reset() and first look
    drive it unchanged. Both stages start together in reset(); result() takes Decision's answer if it has one within
    its deadline (and cancels Gemma), else Gemma's within its own deadline. A stage that is off is skipped."""

    def __init__(self, decision=None, gemma=None):
        self.decision = decision if decision is not None and decision.enabled else None
        self.gemma = gemma if gemma is not None and gemma.enabled else None
        self.enabled = self.decision is not None or self.gemma is not None
        self.why_off = "; ".join(w for w in (
            "" if self.decision is not None else "Decision off (no key)",
            "" if self.gemma is not None else f"Gemma off ({getattr(gemma, 'why_off', '') or 'not loaded'})") if w)

    def start(self, text):
        for stage in (self.decision, self.gemma):
            if stage is not None:
                stage.start(text)

    def result(self):
        rec = {}
        if self.decision is not None:
            slots, rec["decision"] = self.decision.result()
            if slots is not None:
                if self.gemma is not None:
                    self.gemma.cancel()
                return slots, {"used": True, "source": "decision", **rec}
        if self.gemma is not None:
            slots, rec["gemma"] = self.gemma.result()
            if slots is not None:
                return slots, {"used": True, "source": "gemma", **rec}
        return None, {"used": False, "source": None, "why": self.why_off or "no stage answered", **rec}
