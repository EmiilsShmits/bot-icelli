#!/bin/bash
# Run ON THE SIM MACHINE after changing anything in this folder: re-apply the patch to Aalto's clone, regenerate
# the generated files, restart the sim with the venue look, run the scene checks and take a snapshot.
#   bash /root/venue_look/redeploy.sh
# Optional env: AALTO_DIR (default /root/aaltonomous-humanoid), AALTO_LOOK_BG=<0-5> (fixed background),
#               SEED=<n> (object layout), SNAP_DIR (default /root/snap_venue), CHECK=0 (skip the checks).
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
A="${AALTO_DIR:-/root/aaltonomous-humanoid}"
cd "$A"
bash aaltonomous/cloud/aalto.sh stop || true; sleep 3
# the patch refuses to patch twice, so start from Aalto's own three files
git checkout aaltonomous/scene/scene.py aaltonomous/sim/aalto_task/scene_cfg.py aaltonomous/sim/aalto_task/hooks.py
source ~/miniforge3/etc/profile.d/conda.sh; conda activate isaac
python "$D/patch_aalto.py" "$A"
(cd "$D" && python make_assets.py "$A/aaltonomous/scene/scene.yaml" | tail -8)
source "$D/venue_env.sh"
bash aaltonomous/cloud/aalto.sh sim | tail -1
sleep "${SETTLE:-12}"
if [ "${CHECK:-1}" != 0 ]; then bash aaltonomous/cloud/aalto.sh check 2>&1 | grep -aE "FAIL|PASS / " | tail -4; fi
if [ -n "$SEED" ]; then bash aaltonomous/cloud/aalto.sh py -m aaltonomous.sim.scene_client random "$SEED" >/dev/null 2>&1; sleep 6; fi
grep -a "look:" /tmp/aalto_sim.log | tail -6
bash aaltonomous/cloud/aalto.sh snap --out "${SNAP_DIR:-/root/snap_venue}" >/dev/null 2>&1
echo "snapshots in ${SNAP_DIR:-/root/snap_venue}"
