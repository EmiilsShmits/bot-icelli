#!/bin/bash
# bot-icelli: a working-tree v1.6 (copied to ~/hover/policy, parser files to ~/hover/training/instruction_parser)
# against an Isaac sim that already runs on this machine in the venue look. No image build, rules parser, no API.
# Used for the hover-check runs (docs/research/hover-check-preliminary.md).
#   hover_lane.sh TAG PORT INSTANCE(a|b) SEED TRIALS [ENV=VAL ...]     results: ~/hover/runs/TAG
#   e.g. tmux new -d -s hover 'bash ~/hover/hover_lane.sh i-hov 8011 a 1000 5 V16_HOVER=on; exec bash'
TAG=$1; PORT=$2; INST=$3; SEED=$4; TRIALS=$5; shift 5
A=$HOME/aaltonomous-humanoid; P=/root/miniforge3/envs/isaac/bin/python
OUT=$HOME/hover/runs/$TAG; rm -rf "$OUT"; mkdir -p "$OUT"
cd $HOME/hover || exit 1
env -u AALTO_SCENE -u AALTO_LOOK "$@" LEAN_MAP=off V16_LABELS=off V16_INSTRUCTION=rules GEMINI_API_KEY= DECISION_KEY_FILE=/nonexistent \
  V15_DLOG="$OUT/decisions.jsonl" PYTHONPATH=$A:$HOME/hover/policy $P policy/server.py --policy v1.6 --port $PORT > "$OUT/server.log" 2>&1 &
SP=$!
for _ in $(seq 1 180); do grep -q "listening" "$OUT/server.log" 2>/dev/null && break; sleep 1; done
source /root/venue_look/venue_env.sh
[ "$INST" = b ] && export AALTO_INSTANCE=b
cd $A
bash aaltonomous/cloud/aalto.sh eval --policy ws://localhost:$PORT --team "$TAG" --task sort_fixed --trials $TRIALS --seed $SEED --out "$OUT" > "$OUT/run.log" 2>&1
kill $SP 2>/dev/null
echo "done $TAG" >> "$OUT/run.log"
