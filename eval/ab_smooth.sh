#!/bin/bash
# bot-icelli: A/B of policy/smooth_motion.py on samer-v1-sim. One v1.6 image, smoothing on (default) vs off
# (SMOOTH_MOTION=0, a derived image), same seeds in all three sims at once:
#   sim A Aalto's nominal scene, seeds 1000-1004;  sim B AALTO_DR=train, 1000-1004;  sim C the venue look, 1000-1005.
# (5 seeds on A and B: eval/venue_lane.sh labels every 6-trial seed-1000 run as a venue run.)
#   tmux new -d -s ab 'bash ~/bot-icelli/eval/ab_smooth.sh; exec bash'      log: ~/ab_smooth.log
# Then: python3 ~/summarize.py | grep v1.6-   and   eval/analysis/motion_smoothness.py ~/runs/eval/*v1.6-*smooth*/
set -o pipefail
exec > >(tee -a ~/ab_smooth.log) 2>&1
echo "=== $(date +%H:%M:%S) ab_smooth"
cd ~/bot-icelli || exit 1
make docker-build POLICY=v1.6 IMAGE=bot-icelli/policy:v1.6-smooth > ~/ab_build.log 2>&1 || { echo "build FAILED"; tail -20 ~/ab_build.log; exit 1; }
printf 'FROM bot-icelli/policy:v1.6-smooth\nENV SMOOTH_MOTION=0\n' | docker build -q -t bot-icelli/policy:v1.6-nosmooth - >/dev/null || exit 1
for t in v1.6-smooth v1.6-nosmooth; do
  echo "$t $(docker image inspect bot-icelli/policy:$t --format '{{.Id}}' | cut -c1-19): $(docker run --rm bot-icelli/policy:$t \
    python3 -c "import sys; sys.path[:0]=['/app/policy','/app']; import smooth_motion as s; s.install(); from aaltonomous.baselines.classical import planner as p; print(p.time_scale.__name__, s._cfg())" 2>&1 | tail -1)"
done
P="bot-icelli/policy:v1.6-smooth bot-icelli/policy:v1.6-nosmooth"
tmux new -d -s ab_a "TASKS=sort_fixed POLICIES='$P' TRIALS=5 SEED=1000 bash ~/compare.sh; exec bash"
tmux new -d -s ab_b "AALTO_INSTANCE=b PORT=8001 TASKS=sort_fixed POLICIES='$P' TRIALS=5 SEED=1000 bash ~/compare.sh; exec bash"
tmux new -d -s ab_c "RUNS='$P' TRIALS=6 SEED=1000 bash ~/venue_lane.sh; exec bash"
echo "=== $(date +%H:%M:%S) started ab_a (nominal), ab_b (DR), ab_c (venue)"
