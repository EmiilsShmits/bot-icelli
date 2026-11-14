#!/bin/bash
# Swap what a running compare.sh does next: wait until <log> shows the start of a run we no longer want, then kill
# that tmux session (compare.sh, its evaluator and baseline server), remove a submission container left on <port>,
# and start <new command> in a fresh tmux session with the same name. The skipped run loses at most ~1 trial.
#   bash ~/replan.sh ~/compare.log eval "baseline / sort_language" 8000 "POLICIES=bot-icelli/policy:v1.1 bash ~/compare.sh"
# While it waits, this process's own command line contains "compare.sh", so queue.sh keeps waiting too.
log=$1; sess=$2; re=$3; port=$4; cmd=$5
until grep -qE "^=== .*$re" "$log"; do sleep 5; done
echo "$(date +%H:%M:%S) replan $sess: '$re' started; switching to: $cmd"
tmux kill-session -t "$sess"
sleep 3
docker ps -q --filter "publish=$port" | xargs -r docker rm -f
tmux new -d -s "$sess" "$cmd; exec bash"
