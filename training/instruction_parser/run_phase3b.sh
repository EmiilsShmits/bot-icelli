#!/usr/bin/env bash
# Phase 3b on exp-2 (after run_phase3.sh): LoRA fine-tune of Gemma 4 E2B on the same data, then eval.
cd /root/ip
export HF_HUB_OFFLINE=1
PY=/root/venv/bin/python
while ! grep -q PHASE3_DONE /root/logs/phase3.log; do sleep 20; done
echo "ft e2b-lora start $(date +%T)"
$PY finetune.py --model google/gemma-4-E2B-it --train data_train/train.jsonl --out /root/ckpt/sE2B-lora --epochs 1 --lr 2e-4 --bs 16 --lora > /root/logs/ft_sE2B_lora.log 2>&1
tail -3 /root/logs/ft_sE2B_lora.log
$PY eval.py ft:/root/ckpt/sE2B-lora:B data/t2a.jsonl --latency 30 --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
$PY eval.py ft:/root/ckpt/sE2B-lora:B data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
echo PHASE3B_DONE $(date +%T)
