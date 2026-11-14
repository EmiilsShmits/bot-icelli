#!/bin/bash
# bot-icelli: v1.5 (Emils: Aalto's oracle motions on the head camera, offline) in AALTO'S look with AALTO_DR=train on
# sim c, sort_fixed seeds 1000-1009: the test closest to the finalist sim, same seeds as v1.3 (e-027: 26/40), v1.4
# (sim b, running) and Marcus's agent (seeds 1000-1004: 18/20). Emils ran v1.5 only in the venue look (e-029..e-032).
#   1) updates ~/bot-icelli to origin/main (local edits stashed, not lost), builds bot-icelli/policy:v1.5 and
#      bot-icelli/policy:v1.5-off (= v1.5 + ENV V15_SIDES=off, Emils's best venue run e-030: 23/27);
#   2) starts sim c WITHOUT the venue look and with AALTO_DR=train, checks it;
#   3) runs RUNS (default: v1.5-off) through compare.sh on port 8002, then stops sim c.
#   tmux new -d -s v15 'bash ~/v15_lane.sh; exec bash'      log: ~/v15_lane.log
set -o pipefail
exec > >(tee -a ~/v15_lane.log) 2>&1
echo "=== $(date +%H:%M:%S) v15 lane"
while pgrep -f "venue_lane[.]sh" >/dev/null; do sleep 10; done

cd ~/bot-icelli || exit 1
timeout 60 git fetch -q origin || { echo "git fetch FAILED"; exit 1; }
if [ -n "$(git status --porcelain)" ]; then git stash push -u -q -m "machine-local before v1.5 build $(date +%F_%H%M)" && echo "local edits stashed: $(git stash list | head -1)"; fi
git merge -q --ff-only origin/main || { echo "merge FAILED"; exit 1; }
git log --oneline -1
make docker-build POLICY=v1.5 IMAGE=bot-icelli/policy:v1.5 > ~/v15_build.log 2>&1 || { echo "build FAILED (tail ~/v15_build.log)"; tail -15 ~/v15_build.log; exit 1; }
printf 'FROM bot-icelli/policy:v1.5\nENV V15_SIDES=off\n' | docker build -q -t bot-icelli/policy:v1.5-off - >/dev/null || { echo "v1.5-off build FAILED"; exit 1; }
for t in v1.5 v1.5-off; do echo "image bot-icelli/policy:$t $(docker image inspect bot-icelli/policy:$t --format '{{.Id}}' | cut -c1-19) V15_SIDES=$(docker image inspect bot-icelli/policy:$t --format '{{range .Config.Env}}{{println .}}{{end}}' | grep V15_SIDES | cut -d= -f2)"; done

C="AALTO_INSTANCE=c AALTO_DDS_DOMAIN=9 AALTO_CAM_PORT_BASE=57555 AALTO_SCENE_PORT=57580 AALTO_RGBD_PORT=57560 AALTO_TELEIMAGER_REQ_PORT=62000"
export $C
unset AALTO_LOOK AALTO_SCENE AALTO_LOOK_BG
A=$HOME/aaltonomous-humanoid
cd "$A" || exit 1
W="bash aaltonomous/cloud/aalto.sh"

stop_c() {   # only sim c (instance c); never `aalto.sh stop`, which stops whichever sim it finds first
  for p in $(pgrep -f "^python .*aalto_sim_main.py"); do
    tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q "^AALTO_INSTANCE=c$" && kill -INT "$p" && echo "SIGINT sim c $p"
  done
  sleep 20
  for p in $(pgrep -f "^python .*aalto_sim_main.py"); do
    tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q "^AALTO_INSTANCE=c$" && kill -9 "$p" && echo "killed sim c $p"
  done
  for p in $(pgrep -f image_server_process); do
    tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -q teleimager_aalto_c && kill "$p" && echo "stopped camera server c $p"
  done
  tmux kill-session -t simc 2>/dev/null
}
trap stop_c EXIT

tmux kill-session -t simc 2>/dev/null
tmux new -d -s simc "$C AALTO_DR=train TASK=Aalto-Sort-G129-Dex3-Joint bash aaltonomous/sim/run_sim.sh 2>&1 | tee /tmp/aalto_sim_c.log; exec bash"
for _ in $(seq 150); do $W status 2>/dev/null | grep -q "scene service: OK" && break; sleep 5; done
$W status | tail -1
sleep 12
$W check 2>&1 | grep -aE "FAIL|PASS / " | tail -6
grep -aiE "look:|AALTO_DR|randomi" /tmp/aalto_sim_c.log | tail -4

for pol in ${RUNS:-bot-icelli/policy:v1.5-off}; do
  PORT=8002 TASKS=sort_fixed POLICIES="$pol" TRIALS=${TRIALS:-10} SEED=${SEED:-1000} bash "$HOME/compare.sh"
done
echo "=== $(date +%H:%M:%S) v15 lane done"
