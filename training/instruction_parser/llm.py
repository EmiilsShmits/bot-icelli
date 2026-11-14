"""Hugging Face model runners for formats A (JSON), B (fixed order) and C (per-slot scoring)."""
from __future__ import annotations

import json
import re
import time

from prompts import ft_messages, messages
from spec import INVALID, SLOTS, VALUES, from_fixed_order

SYN = {"centre": "center", "middle": "center", "central": "center"}


def parse_json_answer(text: str):
    m = re.search(r"\{.*?\}", text, re.S)
    if not m:
        return INVALID if text.strip().lower().startswith(INVALID) else None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    if d.get("invalid") is True:
        return INVALID
    out = {}
    for k, v in d.items():
        k = " ".join(str(k).lower().split())
        v = SYN.get(str(v).lower().strip(), str(v).lower().strip())
        out[k] = v
    if set(out) != set(SLOTS) or any(v not in VALUES for v in out.values()):
        return None
    return {s: out[s] for s in SLOTS}


def load_model(model_id: str, device: str = "cuda", load_8bit: bool = False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    kw = {}
    if device == "cpu":
        kw["dtype"] = torch.float32
    else:
        kw["dtype"] = torch.bfloat16
        kw["device_map"] = device
    if load_8bit:
        from transformers import BitsAndBytesConfig
        kw["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    try:
        model = AutoModelForCausalLM.from_pretrained(model_id, **kw)
    except (ValueError, KeyError) as e:
        print(f"AutoModelForCausalLM failed ({str(e)[:120]}); trying AutoModelForImageTextToText")
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(model_id, **kw)
    model.eval()
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"
    return tok, model


class HFMethod:
    """method string: hf:<model>:<A|B|C>  or  ft:<checkpoint dir>:B"""

    def __init__(self, method: str, device: str = "cuda", load_8bit: bool = False, shots: int = 3):
        kind, rest = method.split(":", 1)
        self.model_id, self.fmt = rest.rsplit(":", 1)
        self.kind = kind
        self.device = device
        self.shots = shots
        t0 = time.time()
        self.tok, self.model = load_model(self.model_id, device, load_8bit)
        self.load_s = time.time() - t0
        self._cand = None

    def prompt(self, text: str) -> str:
        msgs = ft_messages(text) if self.kind == "ft" else messages(text, self.fmt, self.shots)
        kw = {}
        try:
            return self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False, **kw)
        except TypeError:
            return self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)

    def _encode(self, prompts):
        enc = self.tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False)
        return {k: v.to(self.model.device) for k, v in enc.items()}

    def _generate(self, prompts, max_new):
        import torch
        enc = self._encode(prompts)
        with torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=max_new, do_sample=False, temperature=None, top_p=None,
                                      top_k=None, pad_token_id=self.tok.pad_token_id)
        return self.tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)

    def _candidates(self):
        if self._cand is None:
            ids = []
            for v in VALUES:
                t = self.tok.encode(" " + v, add_special_tokens=False)
                ids.append(t[0])
            assert len(set(ids)) == len(ids), f"candidate first tokens collide: {ids}"
            self._cand = ids
        return self._cand

    def _score(self, prompts):
        import torch
        cand = self._candidates()
        answers = [""] * len(prompts)
        gaps = [[] for _ in prompts]
        for slot in SLOTS:
            full = [p + a + f"{slot}:" for p, a in zip(prompts, answers)]
            enc = self._encode(full)
            with torch.no_grad():
                try:
                    logits = self.model(**enc, logits_to_keep=1).logits[:, -1, :].float()
                except TypeError:
                    logits = self.model(**enc).logits[:, -1, :].float()
            lp = torch.log_softmax(logits, -1)[:, cand]
            top = torch.topk(lp, 2, dim=-1)
            for i in range(len(prompts)):
                v = VALUES[int(top.indices[i, 0])]
                gaps[i].append(float(top.values[i, 0] - top.values[i, 1]))
                answers[i] += f"{slot}: {v}\n"
        res = []
        for a, g in zip(answers, gaps):
            label = {ln.split(": ")[0]: ln.split(": ")[1] for ln in a.strip().split("\n")}
            res.append({"pred": label, "raw": a, "conf": min(g)})
        return res

    def predict_batch(self, texts):
        prompts = [self.prompt(t) for t in texts]
        if self.fmt == "C":
            return self._score(prompts)
        raws = self._generate(prompts, 200 if self.fmt == "A" else 40)
        res = []
        for r in raws:
            pred = parse_json_answer(r) if self.fmt == "A" else from_fixed_order(r)
            res.append({"pred": pred, "raw": r})
        return res
