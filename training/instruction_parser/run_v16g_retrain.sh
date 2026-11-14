#!/usr/bin/env bash
# v1.6g: re-train the Gemma 3 1B student on a fresh Verda GPU machine (as root, this folder copied to /root/ip), because
# the 14 Nov checkpoint (s1b-full) was kept on one laptop only. Same recipe as run_phase3.sh (RESULTS.md "Students"):
# programmatic data + Aalto template renders + Gemma 4 31B paraphrases (round-trip filtered, de-duplicated against
# T2a/T2b) -> full fine-tune of Gemma 3 1B-it, format B, 2 epochs, lr 3e-5, bs 32 -> eval on T1/T2a/T2b/T3.
# Models download without a token: google/gemma-4-31B-it is not gated; unsloth/gemma-3-1b-it is an ungated copy of
# google/gemma-3-1b-it. Versions: torch 2.11 + cu128, transformers 5.23.0, as on 14 Nov.
#   bash run_v16g_retrain.sh > /root/logs/retrain.log 2>&1          # a Verda machine set up with remote_setup.sh
#   modal run --detach modal_retrain.py                               # what ran for v1.6g (Verda had no free GPU)
set -euo pipefail
cd "${IP_DIR:-/root/ip}"
PY=${PY:-/root/venv/bin/python}
CKPT=${CKPT:-/root/ckpt}
LOGS=${LOGS:-/root/logs}
mkdir -p data_train "$CKPT" "$LOGS"
echo "data start $(date +%T)"
# Both are stdlib-only and deterministic; gen_templates.py needs Aalto's tasks.py, so make them on the laptop and copy
# data_train/ along (the machine gets only this folder).
[ -s data_train/prog_raw.jsonl ] || $PY gen_train.py --n 16000 --seed 0 --out data_train/prog_raw.jsonl
[ -s data_train/templates.jsonl ] || $PY gen_templates.py --n 1200 --out data_train/templates.jsonl
cat data_train/prog_raw.jsonl data_train/templates.jsonl > data_train/prog.jsonl
$PY overlap.py dedupe data_train/prog.jsonl data_train/prog_dedup.jsonl data/t2a.jsonl data/t2b.jsonl
echo "teacher start $(date +%T)"
$PY teacher.py --model google/gemma-4-31B-it --seeds data_train/prog_dedup.jsonl --n-seeds 1500 --k 5 --batch 12 \
   --out data_train/teacher.jsonl > "$LOGS/teacher.log" 2>&1
echo "teacher done $(date +%T)"; tail -2 "$LOGS/teacher.log"
$PY overlap.py dedupe data_train/teacher.jsonl data_train/teacher_dedup.jsonl data/t2a.jsonl data/t2b.jsonl
cat data_train/prog_dedup.jsonl data_train/teacher_dedup.jsonl > data_train/train.jsonl
wc -l data_train/train.jsonl
echo "ft 1b start $(date +%T)"
$PY finetune.py --model unsloth/gemma-3-1b-it --train data_train/train.jsonl --out "$CKPT/s1b-full" --epochs 2 \
   --lr 3e-5 --bs 32 > "$LOGS/ft_s1b_full.log" 2>&1
tail -2 "$LOGS/ft_s1b_full.log"
$PY eval.py ft:$CKPT/s1b-full:B data/t2a.jsonl --latency 30 --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
$PY eval.py ft:$CKPT/s1b-full:B data/t2b.jsonl data/t3.jsonl data/t1.jsonl data/t2c.jsonl --batch 64 2>&1 \
   | grep -E '^\{|Traceback|Error' | cut -c1-400
echo "RETRAIN_DONE $(date +%T)"
