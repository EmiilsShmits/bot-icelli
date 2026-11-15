#!/bin/bash
# bot-icelli: build Marcus's ADK agent as a submission image, on the sim machine (x86, Docker).
#   MARCUS_REF=main TAG=presubmit-adk-1 bash ~/bot-icelli/policy/adk/build.sh
# 1) sparse clone of github.com/marcusoberg/junction2026 at MARCUS_REF (adk_agents/ and agent/ only, not sim_out/);
# 2) context = those + Aalto's package (our pinned submodule) + the G1 URDF + policy/adk/Dockerfile;
# 3) patch_headpose.py: his head-camera fit judged by the camera's own move (else the real ~10 deg tilt is ignored);
#    patch_smooth.py + policy/runtime.py: smooth, jerk-limited arm motions (SMOOTH_MOTION=0 turns it off) and
#    planner config overrides from the environment (AALTO_CFG_OVERRIDES, ARM_XY_OFFSET; policy/cfg_overrides.py);
#    patch_lean.py + policy/lean.py: the arm-frame mapping for a leaning robot (docs/research/hand-offset-real-data.md),
#    OFF by default since Sun 15 Nov (it cost 5 of 12 objects in the lean sim, eval/RESULTS.md e-062); LEAN_MAP=auto;
# 4) the Gemini key from ~/adk_key.env (GEMINI_API_KEY=..., copied in by hand, never committed) written as
#    adk_agents/robot_sorter/.env, which the agent reads at start. Samer's decision (Sat 14 Nov ~21:15): the image
#    carries that key, so anyone who pulls it can read it. The context copy is deleted after the build.
# Env: MARCUS_REF (main), TAG (presubmit-adk-1), ROBOT_AGENT_MODEL (gemini-4-hydrogen).
set -euo pipefail
REF=${MARCUS_REF:-main}; TAG=${TAG:-presubmit-adk-1}; MODEL=${ROBOT_AGENT_MODEL:-gemini-4-hydrogen}
BI=$HOME/bot-icelli; B=$HOME/adk_build; C=$B/ctx
URDF=$BI/artifacts/urdf/g1_body29_hand14.urdf
[ -f "$URDF" ] || (cd "$BI" && bash policy/get_urdf.sh)
KEY=$(grep -m1 '^GEMINI_API_KEY=' "$HOME/adk_key.env" 2>/dev/null | cut -d= -f2- | tr -d "\"' \r" || true)
if [ -z "$KEY" ]; then
  [ "${ALLOW_NO_KEY:-0}" = 1 ] || { echo "no GEMINI_API_KEY in ~/adk_key.env (ALLOW_NO_KEY=1 builds without one)"; exit 1; }
  echo "WARNING: no key, the agent will not move (packaging test only)"
fi

rm -rf "$B"; mkdir -p "$C"
git clone -q --filter=blob:none --no-checkout https://github.com/marcusoberg/junction2026 "$B/marcus"
git -C "$B/marcus" sparse-checkout set --no-cone /adk_agents/ /agent/
git -C "$B/marcus" checkout -q "$REF"
SHA=$(git -C "$B/marcus" rev-parse --short HEAD)
echo "Marcus's repo at $SHA ($(git -C "$B/marcus" log -1 --format=%cd --date=format:%H:%M) UTC): $(git -C "$B/marcus" log -1 --format=%s | cut -c1-90)"
cp -r "$B/marcus/adk_agents" "$B/marcus/agent" "$C/"
find "$C" \( -name __pycache__ -o -name .adk -o -name '.env' \) -prune -exec rm -rf {} +
cp -r "$BI/third_party/aaltonomous-humanoid/aaltonomous" "$C/aaltonomous"
cp "$URDF" "$C/"
cp "$BI/policy/adk/Dockerfile" "$C/"
python3 "$BI/policy/adk/patch_headpose.py" "$C/adk_agents/robot_sorter"
cp "$BI/policy/smooth_motion.py" "$BI/policy/cfg_overrides.py" "$BI/policy/runtime.py" "$BI/policy/lean.py" "$C/"
python3 "$BI/policy/adk/patch_smooth.py" "$C/adk_agents/robot_sorter"
python3 "$BI/policy/adk/patch_lean.py" "$C/adk_agents/robot_sorter"
umask 077
if [ -n "$KEY" ]; then
  printf 'GOOGLE_API_KEY=%s\nGOOGLE_GENAI_USE_ENTERPRISE=0\nROBOT_AGENT_MODEL=%s\n' "$KEY" "$MODEL" > "$C/adk_agents/robot_sorter/.env"
else
  printf 'GOOGLE_GENAI_USE_ENTERPRISE=0\nROBOT_AGENT_MODEL=%s\n' "$MODEL" > "$C/adk_agents/robot_sorter/.env"
fi
docker build -q --label "org.opencontainers.image.revision=marcus-$SHA" -t "bot-icelli/adk:$TAG" "$C" | cut -c1-19
rm -f "$C/adk_agents/robot_sorter/.env"
echo "built bot-icelli/adk:$TAG from Marcus's $SHA, model $MODEL"
