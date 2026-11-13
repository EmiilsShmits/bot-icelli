# eval/: scoring policies in sim

**Purpose:** score any policy the same way the organisers will, and keep one scoreboard both halves trust.
**Owner:** shared. Whoever runs an eval logs it.

## Inputs → Outputs
- **In:** a running policy server (`make serve` or a built image) plus the Isaac sim on the Verda machine.
- **Out:** a row in [`RESULTS.md`](RESULTS.md) per run, plus the raw logs in `/data/eval/<ev-id>/` on Verda.

## How to run
1. On the Verda sim machine, start the sim (see `sim/README.md`).
2. Start the policy:
   - from code: `make serve`
   - from the image: `docker run -d --gpus all -p 8000:8000 <image>`
3. `make eval TASK=sort_fixed TRIALS=20`. This runs `aalto eval` inside the sim container. Exit 0 = gate passed, 2 = failed.
4. Also run `TASK=sort_language`. **Run with the default gate settings.**

## What counts (the sim gate)
To pass:
- no abort, watchdog, crash or lost connection
- **0 clipped steps**
- **≥ 27 Hz command rate**, on the sim clock *and* by the policy's own latency (`policy_hz_rt`)

Organisers score on a **held-out** variant with different textures, lighting and camera jitter, so also test with `AALTO_DR=train`.

## Status
- **Now:** —
- **Next:** run Aalto's baseline once and log it as `ev-001` (our reference point)
- **Blockers:** sim machine

## Gotchas
- `make eval` is untested until the sim machine exists.
