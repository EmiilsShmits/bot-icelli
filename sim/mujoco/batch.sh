#!/usr/bin/env bash
# Run several policy configurations in the MuJoCo venue scene, one after another (one policy server at a time).
# Each line of RUNS: TAG POLICY TASK SEED TRIALS GEOMETRY(aalto|measured) [EXTRA ENV for the server...]
# Run from the repo root:  bash sim/mujoco/batch.sh            (the GEMINI key is read from .env)
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/third_party/aaltonomous-humanoid"
set -a; [ -f .env ] && . ./.env >/dev/null 2>&1; set +a
PY=.venv/bin/python
RUNS="${RUNS:-v16-fixed v1.6 sort_fixed 1000 6 aalto
v15off-fixed v1.5 sort_fixed 1000 6 aalto V15_SIDES=off
v16-fixed-geo v1.6 sort_fixed 1000 6 measured
v16-lang v1.6 sort_language 2000 3 aalto}"
while read -r TAG POLICY TASK SEED TRIALS GEO EXTRA; do
  [ -z "$TAG" ] && continue
  OUT=artifacts/eval/mujoco/$TAG; mkdir -p "$OUT"
  SCENE=""; [ "$GEO" = measured ] && SCENE="--scene artifacts/mujoco/scene_measured.yaml"
  env $EXTRA V15_DLOG="$OUT/decisions_$POLICY.jsonl" $PY sim/mujoco/serve.py $SCENE -- --policy "$POLICY" --port 8000 \
      > "$OUT/server.log" 2>&1 &
  SERVER=$!
  for _ in $(seq 1 120); do grep -q "listening" "$OUT/server.log" 2>/dev/null && break; sleep 1; done
  echo "== $TAG ($POLICY, $TASK $SEED x$TRIALS, policy geometry $GEO)"
  $PY sim/mujoco/run.py --tag "$TAG" --task "$TASK" --seed "$SEED" --trials "$TRIALS" --video 2>&1 \
      | grep -E "^trial|^->|objects|gate"
  kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null
done <<< "$RUNS"
echo "batch done"
