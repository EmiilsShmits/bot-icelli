#!/bin/bash
# bot-icelli eval queue for ONE sim on the machine: waits for a running compare.sh to finish, then runs
#   phase 2: Aalto's training randomisation (AALTO_DR=train), close to the held-out variant used to pick finalists;
#   phase 3: Emīls's venue look (sim/venue_look: real colours, camera 10° lower, 7.5 cm walls, scattered objects).
# Each phase = compare.sh (baseline vs our image, same seeds, both tasks). Results: ~/runs/eval, log: ~/queue.log
#   scp eval/compare.sh eval/summarize.py eval/queue.sh root@<ip>:~/
#   ssh root@<ip> "tmux new -d -s queue 'bash ~/queue.sh; exec bash'"
# Env: PHASES ("dr venue"), plus everything compare.sh reads (TRIALS, SEED, TASKS, POLICIES, IMAGE).
set -o pipefail
exec > >(tee -a ~/queue.log) 2>&1
W="bash $HOME/aaltonomous-humanoid/aaltonomous/cloud/aalto.sh"
while pgrep -f "bash .*compare.sh" >/dev/null; do sleep 30; done   # every running compare.sh, 2nd sim's too
if [ -f ~/sim_b.pid ]; then   # a 2nd sim (AALTO_INSTANCE=b, started by hand) would confuse `aalto.sh stop`: stop it first
  kill -INT "$(cat ~/sim_b.pid)" 2>/dev/null
  for _ in $(seq 30); do kill -0 "$(cat ~/sim_b.pid)" 2>/dev/null || break; sleep 1; done
  kill -9 "$(cat ~/sim_b.pid)" 2>/dev/null; rm -f ~/sim_b.pid; echo "stopped sim b"
fi
for phase in ${PHASES:-dr venue}; do
  echo "=== $(date +%H:%M:%S) phase $phase"
  case $phase in
    dr)
      $W stop; sleep 5
      AALTO_DR=train $W sim && sleep 12
      $W check 2>&1 | grep -aE "FAIL|PASS / "
      bash ~/compare.sh ;;
    venue)
      rm -rf /root/venue_look && cp -r ~/bot-icelli/sim/venue_look /root/venue_look
      bash /root/venue_look/redeploy.sh
      ( source /root/venue_look/venue_env.sh && bash ~/compare.sh ) ;;
  esac
done
echo "=== $(date +%H:%M:%S) queue done"
python3 ~/summarize.py
