#!/usr/bin/env bash
# Fetch Unitree's official G1 + Dex3 MuJoCo model (MJCF + STL meshes) from xr_teleoperate, at the same commit as the
# URDF that Aalto's IK uses (policy/get_urdf.sh). About 54 MB into artifacts/mujoco/g1/ (git-ignored).
# Run from the repo root: bash sim/mujoco/get_assets.sh
set -euo pipefail
REV=817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b
BASE="https://raw.githubusercontent.com/unitreerobotics/xr_teleoperate/$REV/assets/g1"
OUT=artifacts/mujoco/g1
mkdir -p "$OUT/meshes"
[ -s "$OUT/g1_body29_hand14.xml" ] || curl -fsSL "$BASE/g1_body29_hand14.xml" -o "$OUT/g1_body29_hand14.xml"
# mesh list from the MJCF itself
for f in $(grep -o 'file="[^"]*"' "$OUT/g1_body29_hand14.xml" | sed 's/file="//; s/"$//' | sort -u); do
  [ -s "$OUT/meshes/$f" ] || curl -fsSL "$BASE/meshes/$f" -o "$OUT/meshes/$f"
done
echo "ok: $OUT ($(ls "$OUT/meshes" | wc -l | tr -d ' ') meshes)"
