#!/bin/bash
# bot-icelli: a 3rd sim on this machine (instance c) in Emils's venue look (bot-icelli sim/venue_look), for
# real-robot-like runs next to sim A (Aalto's nominal scene) and sim B (AALTO_DR=train).
# Seeds 1000-1005, sort_fixed = the seeds of Emils's venue runs (e-004 oracle 22/27, e-012 camera 18/27,
# e-019 upgrades + camera 21/27), so the numbers compare directly. Stops sim c at the end.
#   tmux new -d -s venue 'bash ~/venue_lane.sh; exec bash'        log: ~/venue_lane.log, table: python3 ~/summarize.py
# Env: RUNS ("bot-icelli/policy:v1.3 baseline"), TRIALS (6), SEED (1000), AALTO_LOOK_BG (0 = fixed background)
set -o pipefail
exec > >(tee -a ~/venue_lane.log) 2>&1

label_venue_runs() {   # Aalto names a run folder by its randomisation ("nominal"), not by the look. This lane is the
  # only one on the machine that runs 6 trials from seed 1000 (sims A and B run 10): prefix those folders VENUE-.
  python3 - "$HOME/runs/eval" <<'PY'
import json, os, sys
root = sys.argv[1]
for n in sorted(os.listdir(root)):
    f = os.path.join(root, n, "eval.json")
    if n.startswith("VENUE-") or not os.path.isfile(f):
        continue
    try:
        s = json.load(open(f))["summary"]
    except Exception:
        continue
    if s.get("trials") == 6 and (s.get("seeds") or [None])[0] == 1000:
        os.rename(os.path.join(root, n), os.path.join(root, "VENUE-" + n))
        print(f"renamed {n} -> VENUE-{n} (sim c, venue look)")
PY
}
label_venue_runs
C="AALTO_INSTANCE=c AALTO_DDS_DOMAIN=9 AALTO_CAM_PORT_BASE=57555 AALTO_SCENE_PORT=57580 AALTO_RGBD_PORT=57560 AALTO_TELEIMAGER_REQ_PORT=62000"
export $C
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

# 1) Install the look once: copy it from the machine's bot-icelli clone, patch Aalto's clone (adds the AALTO_LOOK /
#    AALTO_SCENE switches only; with them unset the sim and clients read Aalto's nominal scene), generate the geometry.
if ! grep -q AALTO_SCENE "$A/aaltonomous/scene/scene.py" || [ ! -f /root/venue_look/scene_venue.yaml ]; then
  rm -rf /root/venue_look && cp -r "$HOME/bot-icelli/sim/venue_look" /root/venue_look
  ( source "$HOME/miniforge3/etc/profile.d/conda.sh" && conda activate isaac &&
    { grep -q AALTO_SCENE "$A/aaltonomous/scene/scene.py" || python /root/venue_look/patch_aalto.py "$A"; } &&
    cd /root/venue_look && python make_assets.py "$A/aaltonomous/scene/scene.yaml" | tail -4 ) || { echo "venue look install FAILED"; exit 1; }
fi
source /root/venue_look/venue_env.sh
export AALTO_LOOK_BG=${AALTO_LOOK_BG:-0}
echo "=== $(date +%H:%M:%S) look $AALTO_LOOK | scene $AALTO_SCENE | background $AALTO_LOOK_BG"

# 2) Start sim c with the look, check it, snapshot the cameras.
tmux kill-session -t simc 2>/dev/null
tmux new -d -s simc "$C AALTO_LOOK=$AALTO_LOOK AALTO_SCENE=$AALTO_SCENE AALTO_LOOK_BG=$AALTO_LOOK_BG TASK=Aalto-Sort-G129-Dex3-Joint bash aaltonomous/sim/run_sim.sh 2>&1 | tee /tmp/aalto_sim_c.log; exec bash"
for _ in $(seq 150); do $W status 2>/dev/null | grep -q "scene service: OK" && break; sleep 5; done
$W status | tail -1
sleep 12
$W check 2>&1 | grep -aE "FAIL|PASS / " | tail -6
grep -a "look:" /tmp/aalto_sim_c.log | tail -8
$W py -m aaltonomous.sim.scene_client random 1001 >/dev/null 2>&1; sleep 6
$W snap --out /root/snap_venue_c >/dev/null 2>&1; echo "snapshots: $(ls /root/snap_venue_c | tr '\n' ' ')"

# 3) The runs (compare.sh logs to ~/compare_c.log; folders in ~/runs/eval, labelled by the scene in eval.json).
for pol in ${RUNS:-bot-icelli/policy:v1.3 baseline}; do
  PORT=8002 TASKS=sort_fixed POLICIES="$pol" TRIALS=${TRIALS:-6} SEED=${SEED:-1000} bash "$HOME/compare.sh"
  label_venue_runs
done
echo "=== $(date +%H:%M:%S) venue lane done"
