# policy/adk/: Marcus's agent as a submission image

**Purpose:** package Marcus's Gemini-driven ADK agent ([github.com/marcusoberg/junction2026](https://github.com/marcusoberg/junction2026),
`adk_agents/robot_sorter` + `agent/`) as an image Aalto can run, for the real-robot pre-submission (Sat 14 Nov,
23:59) and the final submission. His repo had no such image (its `submission/Dockerfile` packs π0.5).
**Owner:** Samer (packaging). The agent itself is Marcus's.

## Inputs → Outputs
- **In:** his repo at `MARCUS_REF` (sparse clone, no `sim_out/`), Aalto's package from our submodule, the G1 URDF
  (`artifacts/urdf/`, `policy/get_urdf.sh`), a Gemini key in `~/adk_key.env` on the build machine (`GEMINI_API_KEY=`).
- **Out:** `bot-icelli/adk:<TAG>` (1.64 GB, Python 3.12, CPU only), server on :8000 at start (`python -m robot_sorter.serve`).

## How to run (on `samer-v1-sim`)
```bash
grep '^GEMINI_API_KEY=' .env | ssh <sim machine> 'umask 077; cat > ~/adk_key.env'      # from a laptop's bot-icelli/.env
MARCUS_REF=main TAG=presubmit-adk-1 bash ~/bot-icelli/policy/adk/build.sh                # ~1 min once cached
TAG=presubmit-adk-1 RUNS="sort_fixed:1000" bash ~/bot-icelli/eval/adk_lane.sh           # sim episode + video, sim c
docker tag bot-icelli/adk:presubmit-adk-1 ghcr.io/samer-cyber/bot-icelli-policy:presubmit-adk-1
docker push ghcr.io/samer-cyber/bot-icelli-policy:presubmit-adk-1                       # prints the digest
```

## Status
- **Now (Sat ~21:25):** the image builds from his 1a51d7b; without a key it starts in 1 s and passes Aalto's replay
  test (100 calls, 0 errors, p50 5.7 ms). Waiting for a key for the sim episode.
- **Next:** a sim episode with the key (gate, video, score table for the form), then push and pre-submit.

## Gotchas
- **The image carries the Gemini key** (`/app/adk_agents/robot_sorter/.env`): Samer's decision, Sat ~21:15. Anyone who
  pulls the public image can read it. Cap the key's spending and replace it after the finals.
- **Needs internet on the robot PC.** If a Gemini call fails the agent holds still and retries (back-off 0.5 → 5 s);
  it has no automatic fallback to rules.
- **`patch_headpose.py` changes his code in the image:** his head-camera fit check (a copy of our old v1.2 one)
  rejects the right fit when the camera is ~10° lower than calibration (as in Aalto's real footage). The patch
  judges the camera's own move instead (as `camera_move_ok` in `policy/policies/classical_v14.py`). Marcus should
  merge the same fix; the build prints "NOT patched" once his code there changes.
