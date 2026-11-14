#!/usr/bin/env bash
# Phase 2 on exp-1: every model x format A/B/C on T1, T2a, T2b, T3. Latency (warm, batch 1) measured on T2a.
cd /root/ip
export HF_HUB_OFFLINE=1
PY=/root/venv/bin/python
MODELS=${MODELS:-"google/gemma-3-270m-it Qwen/Qwen2.5-1.5B-Instruct google/gemma-3-1b-it google/gemma-4-E2B-it google/gemma-4-E4B-it google/gemma-4-31B-it"}
for m in $MODELS; do
  bs=32; [[ $m == *31B* ]] && bs=16
  for f in B C A; do
    echo "=== $m $f $(date +%T)"
    $PY eval.py hf:$m:$f data/t2a.jsonl --batch $bs --latency 30 2>&1 | grep -E '^\{|Error|error|Traceback' | tail -5
    $PY eval.py hf:$m:$f data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch $bs 2>&1 | grep -E '^\{|Error|error|Traceback' | tail -8
  done
done
echo PHASE2_DONE $(date +%T)
