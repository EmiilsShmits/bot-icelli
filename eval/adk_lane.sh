#!/bin/bash
# bot-icelli: Marcus's agent as a submission image (bot-icelli/adk:$TAG, policy/adk/) in Aalto's evaluator on sim c,
# Aalto's nominal scene, run the way Aalto runs submissions (`aalto eval --policy ws://localhost:PORT --container`),
# with the head-camera video (~/video/record_video.py) and the container's own log kept. For the pre-submission form.
#   TAG=presubmit-adk-1 tmux new -d -s adklane 'bash ~/adk_lane.sh; exec bash'
# Starts sim c if it isn't up, then waits for the image (build it with policy/adk/build.sh), then runs RUNS episodes:
# "task:seed task:seed ..." (default "sort_fixed:1000"). Leaves sim c running for more runs (stop: tmux kill-session -t simc
# after SIGINT to its python, as in eval/venue_lane.sh).
# Outputs: ~/runs/eval/bot-icelli_adk-<tag>_*/ (eval.json, episode_000.mp4), H.264 copies in ~/video/out/adk-*.mp4,
# the agent's log in ~/adk_sim_<task>_<seed>.log, this lane's log in ~/adk_lane.log.
set -o pipefail
exec > >(tee -a ~/adk_lane.log) 2>&1
TAG=${TAG:-presubmit-adk-1}; IMG=bot-icelli/adk:$TAG
echo "=== $(date +%H:%M:%S) adk lane: $IMG, runs ${RUNS:-sort_fixed:1000}"
while pgrep -f "v15_lane[.]sh|venue_lane[.]sh" >/dev/null; do sleep 10; done
(command -v ffmpeg >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q ffmpeg >/tmp/ffmpeg_install.log 2>&1) &
inst=$!

C="AALTO_INSTANCE=c AALTO_DDS_DOMAIN=9 AALTO_CAM_PORT_BASE=57555 AALTO_SCENE_PORT=57580 AALTO_RGBD_PORT=57560 AALTO_TELEIMAGER_REQ_PORT=62000"
export $C
unset AALTO_LOOK AALTO_SCENE AALTO_LOOK_BG AALTO_DR
A=$HOME/aaltonomous-humanoid
cd "$A" || exit 1
W="bash aaltonomous/cloud/aalto.sh"
if ! $W status 2>/dev/null | grep -q "scene service: OK"; then
  tmux kill-session -t simc 2>/dev/null
  tmux new -d -s simc "$C TASK=Aalto-Sort-G129-Dex3-Joint bash aaltonomous/sim/run_sim.sh 2>&1 | tee /tmp/aalto_sim_c.log; exec bash"
  for _ in $(seq 150); do $W status 2>/dev/null | grep -q "scene service: OK" && break; sleep 5; done
  sleep 12
fi
$W status | tail -1
$W check 2>&1 | grep -aE "FAIL|PASS / " | tail -4

for _ in $(seq 720); do docker image inspect "$IMG" >/dev/null 2>&1 && break; sleep 10; done
docker image inspect "$IMG" >/dev/null 2>&1 || { echo "no image $IMG after 2 h"; exit 1; }
echo "image $IMG $(docker image inspect "$IMG" --format '{{.Id}}' | cut -c1-19) $(docker image inspect "$IMG" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
wait "$inst" 2>/dev/null

for run in ${RUNS:-sort_fixed:1000}; do
  task=${run%%:*}; seed=${run##*:}; log=~/adk_sim_${task}_${seed}.log
  echo "=== $(date +%H:%M:%S) $task seed $seed"
  nohup bash -c "for _ in \$(seq 600); do c=\$(docker ps --filter ancestor=$IMG --format '{{.Names}}' | head -1); [ -n \"\$c\" ] && { docker logs -f \"\$c\"; exit 0; }; sleep 1; done" > "$log" 2>&1 &
  # --policy too: Aalto's evaluate checks --policy (default "oracle") before --container
  $W py ~/video/record_video.py --policy ws://localhost:8002 --container "$IMG" --host-port 8002 \
     --team "bot-icelli_adk-$TAG" --task "$task" --trials 1 --seed "$seed" --out "$HOME/runs/eval"
  echo "=== $(date +%H:%M:%S) $task seed $seed: exit $? (0 = sim gate passed, 2 = gate failed, else crashed)"
  d=$(ls -td "$HOME"/runs/eval/bot-icelli_adk-${TAG}_${task}_* 2>/dev/null | head -1)
  for f in "$d"/episode_*.mp4; do
    [ -f "$f" ] || continue
    out=~/video/out/adk-${TAG}-${task}-seed${seed}.mp4
    ffmpeg -loglevel error -y -i "$f" -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p "$out" && echo "video: $out ($(du -h "$out" | cut -f1))"
  done
  grep -aE "head camera pose fit|agent|Traceback|Error" "$log" | cut -c1-300 | tail -15
done
echo "=== $(date +%H:%M:%S) adk lane done"
