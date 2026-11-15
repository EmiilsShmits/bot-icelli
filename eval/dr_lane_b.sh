#!/bin/bash
# bot-icelli: start sim b (instance b, AALTO_DR=train, Aalto's look) if it isn't up, then run POLICIES through
# compare.sh on it (port 8001). Leaves sim b running.
#   POLICIES="bot-icelli/policy:v1.6-smooth bot-icelli/policy:v1.6-nosmooth" TRIALS=5 bash ~/bot-icelli/eval/dr_lane_b.sh
set -o pipefail
exec > >(tee -a ~/dr_lane_b.log) 2>&1
echo "=== $(date +%H:%M:%S) dr lane b: ${POLICIES:?set POLICIES}"
export AALTO_INSTANCE=b
unset AALTO_LOOK AALTO_SCENE AALTO_LOOK_BG
cd ~/aaltonomous-humanoid || exit 1
W="bash aaltonomous/cloud/aalto.sh"
if ! $W status 2>/dev/null | grep -q "scene service: OK"; then
  tmux kill-session -t simb 2>/dev/null
  tmux new -d -s simb "AALTO_INSTANCE=b AALTO_DR=train TASK=Aalto-Sort-G129-Dex3-Joint bash aaltonomous/sim/run_sim.sh 2>&1 | tee /tmp/aalto_sim_b.log; exec bash"
  for _ in $(seq 150); do $W status 2>/dev/null | grep -q "scene service: OK" && break; sleep 5; done
  sleep 12
fi
$W status | tail -1
$W check 2>&1 | grep -aE "FAIL|PASS / " | tail -4
PORT=8001 TASKS=${TASKS:-sort_fixed} TRIALS=${TRIALS:-5} SEED=${SEED:-1000} bash ~/compare.sh
echo "=== $(date +%H:%M:%S) dr lane b done"
