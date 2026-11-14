"""Phase 3 (b): teacher paraphrases with a large Gemma, kept only if they round-trip.

  python3 teacher.py --model google/gemma-4-31B-it --seeds data_train/prog.jsonl --n-seeds 3000 \
      --k 4 --out data_train/teacher.jsonl

1. For each seed (a programmatic example with its spec), the teacher writes k paraphrases given the
   exact 10-slot meaning.
2. Round-trip filter: the same model parses each paraphrase (format B, prompted, greedy). Only
   paraphrases whose parse equals the seed's label are kept.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time

from llm import load_model
from prompts import messages
from spec import INVALID, SLOTS, from_fixed_order

GEN_PROMPT = """You help build test data for a robot that sorts blocks into three identical bins named only by position (left, center, right).
Known objects: red, yellow and blue blocks, each a cube, cylinder or triangle. "other" means any object that is not one of these 9 types.

Here is an instruction and its exact meaning (where each object type must go; "leave" = stays on the table):
Instruction: {text}
Meaning:
{meaning}

Write {k} different instructions with EXACTLY this meaning, the way different human organisers might say them.
Vary the style a lot: short and terse, long and chatty, polite, passive voice, naming the bin first, using synonyms
(middle/centre, leftmost, the one on the right), grouping objects differently, "everything except", "the rest".
Do not change any destination, do not add rules, do not mention specific distractor colours or shapes.
{other_note}
Output exactly {k} lines, one instruction per line, no numbering, no quotes, nothing else."""


def meaning_text(label):
    lines = [f"- {s}: {label[s]}" for s in SLOTS]
    return "\n".join(lines)


def chat(tok, msgs):
    try:
        return tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)


def generate(tok, model, prompts, max_new, sample):
    import torch
    enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    kw = dict(do_sample=True, temperature=0.9, top_p=0.95) if sample else dict(do_sample=False, temperature=None,
                                                                                top_p=None, top_k=None)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new, pad_token_id=tok.pad_token_id, **kw)
    return tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/gemma-4-31B-it")
    ap.add_argument("--seeds", default="data_train/prog.jsonl")
    ap.add_argument("--n-seeds", type=int, default=3000)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--out", default="data_train/teacher.jsonl")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    seeds = [json.loads(l) for l in open(a.seeds)]
    seeds = [s for s in seeds if s["label"] != INVALID]
    rng.shuffle(seeds)
    seeds = seeds[: a.n_seeds]
    tok, model = load_model(a.model)
    t0 = time.time()
    cands = []
    for i in range(0, len(seeds), a.batch):
        chunk = seeds[i: i + a.batch]
        prompts = []
        for s in chunk:
            note = ("Every instruction must say what to do with unknown/other objects." if s["label"]["other"] != "leave"
                    else "Mention unknown objects at most generically (or not at all).")
            prompts.append(chat(tok, [{"role": "user", "content": GEN_PROMPT.format(
                text=s["text"], meaning=meaning_text(s["label"]), k=a.k, other_note=note)}]))
        outs = generate(tok, model, prompts, 90 * a.k, sample=True)
        for s, o in zip(chunk, outs):
            for line in o.strip().split("\n"):
                line = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line).strip().strip('"')
                if 8 <= len(line) <= 400:
                    cands.append({"text": line, "spec": s["spec"], "label": s["label"], "kind": "teacher_" + s["kind"]})
        print(f"gen {min(i + a.batch, len(seeds))}/{len(seeds)} seeds, {len(cands)} cands, {time.time() - t0:.0f}s", flush=True)
    kept = []
    for i in range(0, len(cands), a.batch * 2):
        chunk = cands[i: i + a.batch * 2]
        prompts = [chat(tok, messages(c["text"], "B")) for c in chunk]
        outs = generate(tok, model, prompts, 40, sample=False)
        for c, o in zip(chunk, outs):
            if from_fixed_order(o) == c["label"]:
                kept.append(c)
        print(f"roundtrip {min(i + 2 * a.batch, len(cands))}/{len(cands)} kept {len(kept)} {time.time() - t0:.0f}s", flush=True)
    seen = set()
    with open(a.out, "w") as f:
        for c in kept:
            if c["text"].lower() in seen:
                continue
            seen.add(c["text"].lower())
            f.write(json.dumps(c) + "\n")
    print(f"done: {len(cands)} candidates, {len(kept)} kept, {len(seen)} unique, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
