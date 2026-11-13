#!/usr/bin/env bash
# Plumbing tests for our policy server, using Aalto's own tools. Run from the repo root (make check / make mock).
#   policy/check.sh replay   synthetic replay: reply shapes + command rate >= 27 Hz (same threshold as the sim gate)
#   policy/check.sh mock     full episodes on Aalto's mock backend: runner + safety filter, logs in artifacts/runs/
set -euo pipefail

MODE="${1:-replay}"
PY="${PY:-.venv/bin/python}"
PORT="${PORT:-8000}"
POLICY="${POLICY:-hold}"
LOG_DIR="artifacts/logs"
mkdir -p "$LOG_DIR"
export PYTHONPATH="${PYTHONPATH:-$PWD/third_party/aaltonomous-humanoid}"

"$PY" policy/server.py --policy "$POLICY" --port "$PORT" >"$LOG_DIR/check_server.log" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# Wait (up to 30 s) for the server to listen.
for _ in $(seq 1 60); do
  if "$PY" -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(s.connect_ex(('127.0.0.1', $PORT)))"; then
    break
  fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo "policy server exited early. Last lines of $LOG_DIR/check_server.log:"; tail -20 "$LOG_DIR/check_server.log"; exit 1
  fi
  sleep 0.5
done

case "$MODE" in
  replay) "$PY" -m aaltonomous.deploy.replay --synthetic 100 --policy "ws://localhost:$PORT" ;;
  mock)   "$PY" -m aaltonomous.deploy.runner --backend mock --policy "ws://localhost:$PORT" \
            --team "${TEAM:-bot-icelli}" --episodes "${EPISODES:-2}" --out artifacts/runs ;;
  *)      echo "usage: $0 [replay|mock]"; exit 2 ;;
esac
echo "check ($MODE, policy=$POLICY): PASS"
