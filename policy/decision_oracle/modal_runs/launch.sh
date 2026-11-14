#!/bin/bash
# Start one v1.5 run (POLICY=v1.6 for another policy) on Modal (Aalto's Isaac sim + evaluator, our venue look by default), detached.
# Modal limits how fast apps are created, so launch runs one after another; this retries on that limit.
#   policy/decision_oracle/modal_runs/launch.sh TAG TASK SEED [more modal_sim.py args]
#   e.g. launch.sh v15off-fixed-1000 sort_fixed 1000 --server-env "V15_SIDES=off"
#        launch.sh v15tip-fixed-1000 sort_fixed 1000 --variant "--tip triangles"
#        launch.sh v15-nominal-1000 sort_fixed 1000 --look none
# Each run = 2 trials (seeds SEED, SEED+1), results in the Modal volume aalto-sim-out/TAG.
set -u
TAG=$1 TASK=$2 SEED=$3; shift 3
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
MODAL=${MODAL:-modal}
cd "$ROOT/modal_pipeline"
for try in 1 2 3 4 5 6; do
  out=$("$MODAL" run --detach sim/modal_sim.py --action eval-policy --policy "${POLICY:-v1.5}" --eval-task "$TASK" --trials 2 \
        --seed "$SEED" --tag "$TAG" --background "$@" 2>&1)
  if echo "$out" | grep -q "started eval-policy"; then echo "[$TAG] started"; exit 0; fi
  echo "[$TAG] try $try: $(echo "$out" | grep -m1 -iE 'error' | cut -c1-120)"; sleep 30
done
exit 1
