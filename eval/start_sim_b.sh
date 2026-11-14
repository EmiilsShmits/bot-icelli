#!/bin/bash
# A 2nd Aalto sim on the same machine (own DDS domain and ports: AALTO_INSTANCE=b), inside tmux "simb", pid in
# ~/sim_b.pid. Extra settings pass through, e.g.  AALTO_DR=train bash ~/start_sim_b.sh
# Clients of this sim need AALTO_INSTANCE=b too:  AALTO_INSTANCE=b PORT=8001 bash ~/compare.sh
# Stop it with  kill -INT $(cat ~/sim_b.pid)  — never `aalto.sh stop`, which stops whichever sim it finds first.
cd ~/aaltonomous-humanoid || exit 1
for p in $(pgrep -f image_server_process); do   # a camera server left over from an earlier sim b
  tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q teleimager_aalto_b && kill "$p" && echo "stopped old camera server $p"
done
rm -f ~/sim_b.pid
tmux kill-session -t simb 2>/dev/null
tmux new -d -s simb "AALTO_INSTANCE=b AALTO_DR=${AALTO_DR:-} TASK=Aalto-Sort-G129-Dex3-Joint bash aaltonomous/sim/run_sim.sh 2>&1 | tee /tmp/aalto_sim_b.log; exec bash"
for _ in $(seq 30); do
  for p in $(pgrep -f "^python .*aalto_sim_main.py"); do
    tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q "^AALTO_INSTANCE=b" && echo "$p" > ~/sim_b.pid
  done
  [ -s ~/sim_b.pid ] && break
  sleep 1
done
echo "sim b pid: $(cat ~/sim_b.pid 2>/dev/null)  (AALTO_DR=${AALTO_DR:-off})"
for _ in $(seq 120); do
  if AALTO_INSTANCE=b bash aaltonomous/cloud/aalto.sh status 2>/dev/null | grep -q "scene service: OK"; then echo "sim b ready"; exit 0; fi
  sleep 5
done
echo "sim b not ready after 10 min: see /tmp/aalto_sim_b.log"; exit 1
