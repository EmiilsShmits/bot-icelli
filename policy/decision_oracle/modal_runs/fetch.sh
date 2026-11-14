#!/bin/bash
# Fetch one Modal run into artifacts/eval/v15/TAG (git-ignored) and make H.264 copies of its episode videos
# (Aalto's recorder writes mp4v, which most players and chat apps do not show) in artifacts/eval/v15/videos/.
#   policy/decision_oracle/modal_runs/fetch.sh TAG
# Needs ffmpeg on PATH, or the Python package imageio-ffmpeg.
set -eu
TAG=$1
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
MODAL=${MODAL:-modal}
OUT="${V15_RUNS:-$ROOT/artifacts/eval/v15}"   # V15_RUNS: another folder
mkdir -p "$OUT/videos"; rm -rf "$OUT/$TAG.part"; mkdir -p "$OUT/$TAG.part"
"$MODAL" volume get aalto-sim-out "$TAG" "$OUT/$TAG.part" >/dev/null
rm -rf "$OUT/$TAG"; mv "$OUT/$TAG.part" "$OUT/$TAG"
FF=$(command -v ffmpeg || python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)
find "$OUT/$TAG" -name "episode_*.mp4" | while IFS= read -r f; do
  dst="$OUT/videos/${TAG}_$(basename "$f")"
  if [ -n "$FF" ]; then
    "$FF" -y -loglevel error -i "$f" -c:v libx264 -pix_fmt yuv420p -crf 26 -movflags +faststart "$dst" < /dev/null
  else
    cp "$f" "$dst"; echo "no ffmpeg: copied as mp4v"
  fi
  echo "video: $dst"
done
V15_RUNS="$OUT" python3 "$(dirname "$0")/summarize.py" "$TAG"
