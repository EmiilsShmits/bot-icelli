"""Phase 3 step 2: fine-tune a small Gemma to output the fixed-order answer (format B).

  python3 finetune.py --model google/gemma-3-270m-it --train data_train/train.jsonl --out /root/ckpt/student-270m \
      --epochs 2 --lr 1e-4 --bs 32
Full fine-tuning (default) or --lora. Loss only on the answer tokens.
"""
from __future__ import annotations

import argparse
import json
import random
import time

from prompts import ft_messages
from spec import fixed_order


def chat(tok, msgs, gen):
    try:
        return tok.apply_chat_template(msgs, add_generation_prompt=gen, tokenize=False, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, add_generation_prompt=gen, tokenize=False)


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/gemma-3-270m-it")
    ap.add_argument("--train", default="data_train/train.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--max-len", type=int, default=256)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    rows = [json.loads(l) for l in open(a.train)]
    random.Random(0).shuffle(rows)

    feats = []
    for r in rows:
        msgs = ft_messages(r["text"])
        prompt = chat(tok, msgs, True)
        full = chat(tok, msgs + [{"role": "assistant", "content": fixed_order(r["label"])}], False)
        if not full.startswith(prompt):
            raise SystemExit("chat template: full text does not start with prompt")
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        f_ids = tok(full, add_special_tokens=False)["input_ids"][: a.max_len]
        labels = [-100] * len(p_ids) + f_ids[len(p_ids):]
        feats.append({"input_ids": f_ids, "labels": labels[: len(f_ids)]})
    print(f"{len(feats)} examples; example:\n{full}", flush=True)

    def collate(batch):
        m = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), m), tok.pad_token_id)
        lab = torch.full((len(batch), m), -100)
        att = torch.zeros((len(batch), m), dtype=torch.long)
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            ids[i, :n] = torch.tensor(b["input_ids"])
            lab[i, :n] = torch.tensor(b["labels"])
            att[i, :n] = 1
        return {"input_ids": ids, "labels": lab, "attention_mask": att}

    try:
        model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, attn_implementation="eager")
    except (ValueError, KeyError) as e:
        print(f"AutoModelForCausalLM failed ({str(e)[:120]}); trying AutoModelForImageTextToText", flush=True)
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=torch.bfloat16, attn_implementation="eager")
    if a.lora:
        from peft import LoraConfig, get_peft_model
        # language-model projections only (skip vision / audio towers of multimodal Gemma 4)
        tm = r"^(?!.*(vision|audio)).*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$"
        model = get_peft_model(model, LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05, target_modules=tm,
                                                 task_type="CAUSAL_LM"))
        model.print_trainable_parameters()
    args = TrainingArguments(output_dir=a.out + "_tmp", per_device_train_batch_size=a.bs, num_train_epochs=a.epochs,
                             learning_rate=a.lr, lr_scheduler_type="cosine", bf16=True,
                             warmup_steps=max(1, int(0.03 * a.epochs * len(feats) / a.bs)),
                             logging_steps=25, save_strategy="no", report_to=[], remove_unused_columns=False,
                             dataloader_num_workers=2, weight_decay=0.0)
    t0 = time.time()
    Trainer(model=model, args=args, train_dataset=feats, data_collator=collate).train()
    if a.lora:
        model = model.merge_and_unload()
    model.save_pretrained(a.out, safe_serialization=True)
    tok.save_pretrained(a.out)
    print(f"saved {a.out} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
