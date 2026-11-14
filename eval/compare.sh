#!/bin/bash
# bot-icelli: Aalto's classical baseline vs our policy image on the same seeds, in the Aalto Isaac sim on this machine.
# Needs the sim running (bash ~/aaltonomous-humanoid/aaltonomous/cloud/aalto.sh sim) and the image built
# (cd ~/bot-icelli && make docker-build POLICY=v1 IMAGE=bot-icelli/policy:v1). Run it in tmux:
#   tmux new -d -s eval 'bash ~/compare.sh; exec bash'
# Results: one folder per run under $OUT (eval.json + episode logs); table: python3 ~/summarize.py
# Env: TASKS ("sort_fixed sort_language"), POLICIES ("baseline v1"; or an image tag), TRIALS (10), SEED (1000),
#      IMAGE (bot-icelli/policy:v1), OUT (~/runs/eval), PORT (8000). 2nd sim: AALTO_INSTANCE=b PORT=8001.
set -o pipefail
TRIALS=${TRIALS:-10}; SEED=${SEED:-1000}; OUT=${OUT:-$HOME/runs/eval}; PORT=${PORT:-8000}
TASKS=${TASKS:-"sort_fixed sort_language"}; POLICIES=${POLICIES:-"baseline v1"}; IMAGE=${IMAGE:-bot-icelli/policy:v1}
SFX=${AALTO_INSTANCE:+_$AALTO_INSTANCE}
exec > >(tee -a ~/compare$SFX.log) 2>&1
W="bash $HOME/aaltonomous-humanoid/aaltonomous/cloud/aalto.sh"
for task in $TASKS; do
  for pol in $POLICIES; do
    echo "=== $(date +%H:%M:%S) $pol / $task / trials $TRIALS from seed $SEED / port $PORT ${AALTO_INSTANCE:+/ sim $AALTO_INSTANCE}"
    if [ "$pol" = baseline ]; then
      # env -u: with the venue look, the baseline must not read the venue geometry (our image can't either)
      env -u AALTO_SCENE -u AALTO_LOOK PORT=$PORT $W py -m aaltonomous.baselines.classical.policy_server \
        > ~/baseline_server$SFX.log 2>&1 &
      sp=$!
      $W eval --policy ws://localhost:$PORT --team baseline --task $task --trials $TRIALS --seed $SEED --out "$OUT"
      rc=$?
      kill $sp 2>/dev/null; wait $sp 2>/dev/null
    else
      img=$IMAGE; [ "$pol" = v1 ] || img=$pol
      # --policy is required: Aalto's evaluate.py checks `--policy == oracle` (its default) BEFORE --container, so
      # --container alone runs the privileged oracle and never starts the image (our runs before Sat 15:19 UTC).
      $W eval --policy ws://localhost:$PORT --container "$img" --host-port $PORT --team "${pol//[:\/]/_}" --task $task --trials $TRIALS --seed $SEED --out "$OUT"
      rc=$?
    fi
    echo "=== $(date +%H:%M:%S) $pol / $task: exit $rc (0 = sim gate passed, 2 = gate failed, else crashed)"
  done
done
python3 ~/summarize.py "$OUT"
