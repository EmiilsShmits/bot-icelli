#!/usr/bin/env bash
# Phase 4 on exp-1: fit checks. Usage: bash run_phase4.sh METHOD [METHOD...]; one process per (method, device), page cache dropped first.
cd /root/ip
export HF_HUB_OFFLINE=1
PY=/root/venv/bin/python
for m in "$@"; do
  for dev in cuda cpu; do
    sync; echo 3 > /proc/sys/vm/drop_caches
    if [ $dev = cpu ]; then $PY fitcheck.py $m --device cpu --threads 8 --n 10 2>&1 | grep -E '^\{|Traceback|Error' | tail -3
    else $PY fitcheck.py $m --device cuda --n 30 2>&1 | grep -E '^\{|Traceback|Error' | tail -3; fi
  done
done
echo PHASE4_DONE $(date +%T)
