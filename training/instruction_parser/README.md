# training/instruction_parser

## Purpose
Test whether a small Gemma, running offline inside the policy image, can turn an unseen rung-2 `sort_language` instruction into a per-object target better than a rule-based parser. That instruction is the ×1.5 finals episode.

The output has 10 slots: 9 known colour+shape types plus `other`. Each slot is `left`, `center`, `right` or `leave`, or the whole answer is `invalid`.

- Plan: [`EXPERIMENT.md`](EXPERIMENT.md)
- Results: [`RESULTS.md`](RESULTS.md)

## Owner
Emīls + Tiya.

## Inputs → Outputs
- **Inputs:**
  - Aalto's 8 templates (`third_party/.../interface/tasks.py`)
  - Hand-written test sets in `data/`
  - Gemma / Qwen weights from Hugging Face (`HF_TOKEN` in `.env`)
- **Outputs:**
  - `results/<method>/<testset>.{preds.jsonl,summary.json}`
  - `results/tables.md`, `RESULTS.md`
  - Fine-tuned checkpoints in `artifacts/instruction_parser/` (git-ignored)
  - Training data in `artifacts/instruction_parser/data_train/`

| File | What |
|---|---|
| `spec.py` | Rule interpreter: structured spec → 10-slot label. All labels come from here |
| `build_t1.py`, `freeze.py` | Build T1 and freeze the hand-written T2a / T2b / T3 (SHA-256 in `results/testset_hashes.txt`) |
| `data/` | Frozen test sets: `t1`, `t2a`, `t2b`, `t3`. `*.src.jsonl` + `make_*.py` are the hand-written sources. **Never train on these or use them as few-shot examples** |
| `rule_parser.py` | Rule-based baseline (tuned on T1 + its own scratch examples only) |
| `prompts.py` | Exact prompts for formats A (JSON), B (fixed order), C (per-slot scoring) and for the fine-tuned student |
| `llm.py`, `eval.py` | HF model runners and the evaluation harness |
| `gen_train.py`, `teacher.py`, `overlap.py`, `finetune.py` | Phase 3: programmatic data, teacher paraphrases with round-trip filter, n-gram dedupe vs T2, fine-tuning |
| `fitcheck.py` | Phase 4: load time, VRAM, size, GPU/CPU latency |
| `run_phase2.sh`, `run_phase3.sh`, `remote_setup.sh`, `download.py` | What ran on the two Verda machines |
| `watchdog.py` | Laptop-side cost backstop: deletes `gemma-parser-exp-*` instances past an age or spend limit |
| `make_report.py`, `hybrid.py` | Tables for RESULTS.md; post-hoc combinations with the rule parser |
| `run_phase2b.sh`, `run_phase3b.sh`, `run_phase4q.sh`, `run_phase4r.sh` | Extra runs added during the night (Gemma 4 12B, E2B LoRA student, re-queued fit checks) |
| `results/logs/` | Machine logs from both Verda machines and the watchdog log |
| `gen_templates.py`, `run_v16g_retrain.sh`, `modal_retrain.py` | v1.6g (Sun 15 Nov): the 1B student trained again with the 14 Nov recipe (the 14 Nov checkpoint was on one laptop only), on a Modal H100 |
| `compare_v16g.py` | v1.6g: the test sets through the policy's own instruction code (`policy/instruction_gemma.py`, `instruction_d1.py`, the rules' mapping), inside the image on the CPU |

## How to run
```bash
cd training/instruction_parser
python3 spec.py check data/t2a.jsonl              # validate a test set
python3 eval.py rule data/t2a.jsonl data/t2b.jsonl data/t3.jsonl --device cpu   # no deps needed
python3 make_report.py rule > results/tables.md
```
Gemini Decision 1 (online, needs `GEMINI_API_KEY` in `.env`, no extra packages):
```bash
python3 eval.py gemini-decision data/t1.jsonl data/t2a.jsonl data/t2b.jsonl data/t3.jsonl --batch 8 --latency 20 --device cpu
python3 compare_gemini.py      # Gemini vs Gemma vs rule parser, plus fallback chains
```
LLM methods need a GPU machine with `requirements.txt` installed (see `remote_setup.sh`):
```bash
python eval.py hf:google/gemma-4-E2B-it:C data/t2a.jsonl --latency 30
python eval.py ft:/path/to/checkpoint:B data/t2a.jsonl
```

## Status
- **Now:** the overnight run of 14 Nov 2026 is done; see the top of `RESULTS.md`.
  - The best in-image candidate is the fine-tuned Gemma 3 1B (`artifacts/instruction_parser/ckpt/s1b-full`). It gets T2a 94.7% and T2b 90.6%, against the rule parser's 86.7% and 60.1%.
  - Both Verda machines were deleted. Nothing is committed.
- **Next:**
  - Fill the training-data gaps listed in RESULTS "What we'd do next", retrain, and test on a fresh T2c.
  - Ask Aalto the open questions (distractors, orange/purple).
  - Team decision on whether and where to plug the parser into `policy/` (out of scope here).
- **Blockers:** Aalto's answers on distractor scoring and real object colours.

## Gotchas
- **Test sets are frozen.** Changing a line changes its hash. Add new items to a new file instead.
- **`other` convention:** `leave` unless the instruction explicitly talks about unknown objects. A red star counts as `other`. Both are unconfirmed with Aalto.
- **Real-table colours:** orange → red and purple → blue in `t2a` `real_colour_names` (unconfirmed with Aalto).
- **transformers 5.x:** `TrainingArguments` no longer takes `warmup_ratio`; we use `warmup_steps`.
- **Gemma 4 loading:** Gemma 4 E2B/E4B are `Gemma4ForConditionalGeneration` (multimodal). `llm.load_model` tries `AutoModelForCausalLM` first, then `AutoModelForImageTextToText`.
- **Verda SSH launches** with `nohup … &` can keep the ssh session open. Close stdin (`< /dev/null`) on both sides.
