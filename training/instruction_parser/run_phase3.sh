#!/usr/bin/env bash
# Phase 3 on exp-2: teacher paraphrases (Gemma 4 31B) -> combined data -> fine-tune students -> eval.
cd /root/ip
export HF_HUB_OFFLINE=1
PY=/root/venv/bin/python
NSEEDS=${NSEEDS:-1500}
while pgrep -f "finetune.py.*s270m-prog" >/dev/null; do sleep 10; done
echo "teacher start $(date +%T)"
$PY teacher.py --model google/gemma-4-31B-it --seeds data_train/prog_dedup.jsonl --n-seeds $NSEEDS --k 5 --batch 12 \
   --out data_train/teacher.jsonl > /root/logs/teacher.log 2>&1 &
TP=$!
$PY eval.py ft:/root/ckpt/s270m-prog:B data/t2a.jsonl --latency 30 --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
$PY eval.py ft:/root/ckpt/s270m-prog:B data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
wait $TP
echo "teacher done $(date +%T)"; tail -2 /root/logs/teacher.log
$PY overlap.py dedupe data_train/teacher.jsonl data_train/teacher_dedup.jsonl data/t2a.jsonl data/t2b.jsonl
cat data_train/prog_dedup.jsonl data_train/teacher_dedup.jsonl > data_train/train.jsonl
wc -l data_train/train.jsonl
echo "ft 270m start $(date +%T)"
$PY finetune.py --model google/gemma-3-270m-it --train data_train/train.jsonl --out /root/ckpt/s270m-full --epochs 3 --lr 1e-4 --bs 32 > /root/logs/ft_s270m_full.log 2>&1
$PY eval.py ft:/root/ckpt/s270m-full:B data/t2a.jsonl --latency 30 --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
$PY eval.py ft:/root/ckpt/s270m-full:B data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
echo "ft 1b start $(date +%T)"
$PY finetune.py --model google/gemma-3-1b-it --train data_train/train.jsonl --out /root/ckpt/s1b-full --epochs 2 --lr 3e-5 --bs 32 > /root/logs/ft_s1b_full.log 2>&1
$PY eval.py ft:/root/ckpt/s1b-full:B data/t2a.jsonl --latency 30 --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
$PY eval.py ft:/root/ckpt/s1b-full:B data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch 64 2>&1 | grep -E '^\{|Traceback|Error' | cut -c1-400
echo PHASE3_DONE $(date +%T)
