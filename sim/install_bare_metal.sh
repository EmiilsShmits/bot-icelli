#!/bin/bash
# Bare-metal install of Aalto's Isaac sim on a fresh Verda machine, as root:
# docs/runbooks/verda-sim-setup.md §2b as one script. Run it inside tmux; re-running resumes
# (each Aalto step leaves a marker in third_party/). Log: ~/setup.log
#   scp sim/install_bare_metal.sh root@<ip>:~/ && ssh root@<ip> "tmux new -d -s setup 'bash ~/install_bare_metal.sh; exec bash'"
set -eo pipefail
exec > >(tee -a ~/setup.log) 2>&1
trap 'echo "=== install_sim.sh exit $? at $(date +%H:%M:%S)"' EXIT
AALTO_REV=${AALTO_REV:-36daf5b44dad46b8f448a5124ded7faa9947be1e}   # = our submodule (Sat 14 Nov)
ISAACLAB_REV=e3f7d9ff1f5d7f8280de3ece9000b7117f66bcf4               # = ISAACLAB_REV in setup_instance.sh
echo "=== install_sim.sh start $(date +%H:%M:%S)"
cd ~
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends git curl unzip cmake build-essential \
  libturbojpeg libglu1-mesa libxt6 libvulkan1 libegl1 libgl1 libxrandr2 libxi6 libsm6 libice6 libxkbcommon0 libglib2.0-0t64
[ -d aaltonomous-humanoid/.git ] || git clone -q https://github.com/zupermiez/aaltonomous-humanoid.git
cd aaltonomous-humanoid
git -c advice.detachedHead=false checkout -q "$AALTO_REV"

# Aalto pins 5 packages newer than Isaac Sim 6.2 allows -> ResolutionImpossible at the isaacsim step
C=aaltonomous/cloud/isaac-constraints.txt
for p in click==8.5.1 urllib3==2.8.0 psutil==7.2.2 llvmlite==0.50.0 fsspec==2026.9.0; do
  sed -i "s/^${p//./\\.}\$/# $p  (conflicts with isaacsim 6.2)/" $C
done
grep -c "conflicts with isaacsim" $C

S=aaltonomous/cloud/setup_instance.sh
for s in prereq conda torch isaacsim; do bash $S $s; done

# Isaac Lab's rerun visualizer wants rerun-sdk>=0.29; Aalto pins 0.23.4. Install "all" minus that visualizer.
if [ ! -f third_party/.setup_done_isaaclab ]; then
  echo "=== isaaclab without the rerun visualizer"
  d=third_party/IsaacLab
  if [ ! -d $d/.git ] || [ "$(git -C $d rev-parse HEAD)" != $ISAACLAB_REV ]; then
    rm -rf $d; git init -q $d; git -C $d remote add origin https://github.com/isaac-sim/IsaacLab.git
    git -C $d fetch -q --depth 1 origin $ISAACLAB_REV
    git -C $d -c advice.detachedHead=false checkout -q FETCH_HEAD
  fi
  source ~/miniforge3/etc/profile.d/conda.sh && conda activate isaac
  ( export PIP_CONSTRAINT=$PWD/$C PIP_NO_CACHE_DIR=1 OMNI_KIT_ACCEPT_EULA=YES CYCLONEDDS_HOME=$PWD/third_party/cyclonedds/install
    cd $d && ./isaaclab.sh --install "mimic,teleop,newton,rl,visualizer[viser]" )
  conda deactivate
  touch third_party/.setup_done_isaaclab
fi
for s in cyclonedds repos assets aalto; do bash $S $s; done
bash $S verify || echo "!!! verify reported failures (known at 36daf5b: only test_cubes_and_bins_visible)"

# RTX PRO 6000: the renderer needs ~6 s to start, Isaac Sim stops waiting after 120 frames -> black images
F=~/miniforge3/envs/isaac/lib/python3.12/site-packages/isaacsim/exts/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py
# (Isaac Sim 6.2's line is `MAX_FRAMES = 240 if os.name == "nt" else 120`)
sed -i -E '/MAX_FRAMES[[:space:]]*=/ s/\b120\b/1500/' "$F"
grep -n "MAX_FRAMES" "$F" | head -3
echo "=== install done $(date +%H:%M:%S); starting the sim (first start compiles shaders, 5-10 min)"

set +e
bash aaltonomous/cloud/aalto.sh sim
for _ in $(seq 60); do bash aaltonomous/cloud/aalto.sh status | grep -q "scene service: OK" && break; sleep 10; done
bash aaltonomous/cloud/aalto.sh status
bash aaltonomous/cloud/aalto.sh check
echo "=== sim check done $(date +%H:%M:%S)"
