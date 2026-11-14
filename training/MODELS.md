# Checkpoint registry

Empty log, one row per checkpoint. The columns are a starting point; change them as the team needs.

| ID | Method / base model | Datasets (ds-…) | Config (file + commit) | GPU / time | Location | Best eval (ev-…) | Notes |
|---|---|---|---|---|---|---|---|
| ck-parser-1b | Gemma 3 1B-it, full fine-tune, format B (10-slot fixed order), 2 ep, lr 3e-5, bs 32 | `artifacts/instruction_parser/data_train/train.jsonl` (23,089: programmatic + 1,200 Aalto templates + 5,889 Gemma 4 31B paraphrases) | `training/instruction_parser/finetune.py` via `run_phase3.sh` (uncommitted, 14 Nov) | A100 80 GB, ~6 min | `artifacts/instruction_parser/ckpt/s1b-full` (1.9 GB, local only) | T2a 94.7% / CW 0.9%; T2b 90.6% / CW 8.0%; T3 refusal 58% (`training/instruction_parser/RESULTS.md`) | Recommended parser candidate. 0.14 s GPU, 1.6 s CPU, 2.0 GB VRAM |
| ck-parser-270m | Gemma 3 270M-it, full fine-tune, format B, 3 ep, lr 1e-4, bs 32 | same as above | same | A100 80 GB, ~5 min | `artifacts/instruction_parser/ckpt/s270m-full` (0.54 GB, local only) | T2a 91.7% / CW 3.2%; T2b 82.2% / CW 14.1% | Smallest; 0.10 s GPU, 0.55 s CPU, 0.55 GB VRAM |
| ck-parser-e2b-lora | Gemma 4 E2B-it + LoRA r=32 (merged), format B, 1 ep, lr 2e-4, bs 16 | same as above | `finetune.py --lora` via `run_phase3b.sh` | A100 80 GB, ~8 min | **not kept** (10 GB, deleted with the machine; rerun to reproduce) | T2a 93.5% / CW 1.5%; T2b 96.7% / CW 2.3%; T3 75% | Most accurate in-image candidate, but 10.2 GB VRAM |
