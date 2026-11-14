#!/usr/bin/env bash
# Fetch the G1 URDF that Aalto's IK and safety filter need (Unitree xr_teleoperate, the commit Aalto's setup pins).
#   artifacts/urdf/                                                  -> copied into the Docker image
#   third_party/aaltonomous-humanoid/third_party/xr_teleoperate/...  -> where Aalto's code looks for it locally
#                                                                       (ignored by Aalto's .gitignore)
# Run from the repo root: bash policy/get_urdf.sh
set -euo pipefail
REV=817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b
URL="https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/$REV/assets/g1/g1_body29_hand14.urdf"
for d in artifacts/urdf third_party/aaltonomous-humanoid/third_party/xr_teleoperate/assets/g1; do
  mkdir -p "$d"
  if [ ! -s "$d/g1_body29_hand14.urdf" ]; then
    curl -fsSL "$URL" -o "$d/g1_body29_hand14.urdf"
  fi
  echo "ok: $d/g1_body29_hand14.urdf"
done
