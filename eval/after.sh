#!/bin/bash
# Start a run once another one has finished, without stopping anything: waits for a line matching <pattern> to be
# appended to <log> (only lines after the log's current end count), then runs <command> in a new tmux session.
#   tmux new -d -s after_b "bash ~/after.sh ~/compare_b.log 'policy:v1.3 / sort_fixed: exit' eval_b14 '<command>'; exec bash"
log=$1; pattern=$2; sess=$3; cmd=$4
start=$(wc -l < "$log" 2>/dev/null || echo 0)
echo "$(date +%H:%M:%S) waiting for '$pattern' in $log (after line $start), then: $cmd"
until tail -n +$((start + 1)) "$log" 2>/dev/null | grep -qF -- "$pattern"; do sleep 10; done
echo "$(date +%H:%M:%S) '$pattern' seen: starting tmux $sess"
tmux new -d -s "$sess" "$cmd; exec bash"
