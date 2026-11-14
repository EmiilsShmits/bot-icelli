cd /root/ip; export HF_HUB_OFFLINE=1; PY=/root/venv/bin/python
while ! grep -q DOWNLOADS_DONE /root/dl2.log; do sleep 10; done
while ! grep -q PHASE4_DONE /root/logs/phase4a.log; do sleep 10; done
for f in C A; do echo "=== gemma-4-12B $f $(date +%T)"
$PY eval.py hf:google/gemma-4-12B-it:$f data/t2a.jsonl --batch 16 --latency 30 2>&1 | grep -E "^\{|Traceback" | tail -3
$PY eval.py hf:google/gemma-4-12B-it:$f data/t2b.jsonl data/t3.jsonl data/t1.jsonl --batch 16 2>&1 | grep -E "^\{|Traceback" | tail -5; done
echo PHASE2B_DONE $(date +%T)
