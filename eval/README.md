# eval/: scoring policies in sim

**Purpose:** _to be agreed._
**Owner:** _TBD_

## How to run (Aalto's evaluator)
1. On the sim machine, start the sim (see `docs/runbooks/verda-sim-setup.md`).
2. Start a policy server on :8000 (`make serve`, or `docker run -d --gpus all -p 8000:8000 <image>`).
3. `make eval TASK=sort_fixed TRIALS=20`. This runs `aalto eval` inside the sim container; **untested so far**. Exit 0 = gate passed, 2 = failed.

## Status
- **Now:** —
- **Next:** —
- **Blockers:** —

## Facts from Aalto's rules
- **The sim gate** (required to reach the finals):
  - no abort, watchdog, crash or lost connection
  - **0 clipped steps**
  - **≥ 27 Hz command rate**, on the sim clock *and* by the policy's own latency (`policy_hz_rt`)
- **Finalist selection:** organisers score on a **held-out** sim variant (different textures, lighting, object poses, camera jitter; secret seeds).
- **Points per object:**
  - `sort_fixed`: +1 correct bin
  - `sort_language`: +2 correct bin
  - −1 wrong bin or knocked off
  - 0 left on the counter
