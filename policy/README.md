# policy/: the submission

**Purpose:** the Docker image we hand in: a websocket policy server (Aalto protocol, port 8000). It currently holds a placeholder only.
**Owner:** _TBD_

## Inputs → Outputs
- **In:** _to be agreed_ (weights must be inside the image; `policy/weights/` is git-ignored).
- **Out:** a linux/amd64 image pushed to GHCR/Docker Hub, **pinned by digest**, submitted through the form on Discord.

## Files
| File | What |
|---|---|
| `server.py` | Entrypoint. Picks a policy by name (`--policy` or `POLICY` env) and serves it on :8000 |
| `policies/hold.py` | Placeholder that holds the start pose. Passes the plumbing checks; scores 0 |
| `policies/classical_v1.py` | **v1:** Aalto's classical baseline + instruction parsing + colour ranges that see the real orange/yellow/purple objects + speed guard |
| `policies/classical_v11.py` | **v1.1:** v1 + a hand-over for far cross-body objects (the arm on the object's side puts it down near the middle; the bin-side arm finishes) + a retry budget that actually limits retries. Being compared with v1 in the sim |
| `instruction.py` | Instruction → colour → bin, using Emīls's rule parser (`training/instruction_parser/rule_parser.py`) |
| `guard.py` | Shadow copy of Aalto's safety filter with slightly lower caps: what we send never gets clipped |
| `get_urdf.sh` | Downloads the G1 URDF that the IK and safety filter need (to `artifacts/urdf/` and where Aalto's code looks) |
| `tests/test_v1.py` | Unit tests. Parser, guard and colours run anywhere (Windows too); the v1.1 planner tests need Pinocchio and skip without it (run them on the sim machine in the `isaac` env) |
| `check.sh` | Runs Aalto's replay / mock tests against our server (`make check`, `make mock`) |
| `Dockerfile` | Submission image (CUDA 12.8 base). The build context allowlist is in `/.dockerignore` |
| `requirements.txt` | Image dependencies (keep them small) |
| `requirements-dev.txt` | Local test dependencies |
| `decision_oracle/` | **Not part of the submission.** Sim-only exploration: Aalto's oracle as motion functions with a Gemini Decision 1 chooser and camera-only perception. See its [README](decision_oracle/README.md) |

## How to run
```bash
make setup          # once
make check          # Aalto's replay test: shapes + >= 27 Hz
make serve          # run the server on :8000
make docker-build && make docker-check GPUS=none    # build + test the image (Docker running; slow on Apple silicon)
```
Hand-in: [`../docs/runbooks/submit.md`](../docs/runbooks/submit.md).

### v1
```bash
python -m unittest discover -s policy/tests -v       # parser, guard, colour ranges (no Pinocchio needed)
bash policy/get_urdf.sh                              # once: the G1 URDF
make check POLICY=v1                                 # Linux/macOS: needs pin (Pinocchio) from requirements
make docker-build POLICY=v1 IMAGE=ghcr.io/<owner>/bot-icelli-policy:v1
make docker-build POLICY=v1.1 IMAGE=bot-icelli/policy:v1.1     # v1.1; the tuning knobs are env vars (see the file's docstring)
```

## Status
- **Now (Sat 14 Nov, Samer + Claude):** v1 written; unit tests pass (instruction mapping on 200 training-template instructions + real colour names, guard, colour ranges on sim and real colours).
  - **Image built** on the Linux sim machine: `make docker-build POLICY=v1 IMAGE=bot-icelli/policy:v1`, **1.46 GB**; the build-time load check passes (Pinocchio, URDF, config, parser).
  - **Aalto's replay test passes** against the image (`aaltonomous.deploy.replay --synthetic 100 --container bot-icelli/policy:v1`): 100 calls, 0 errors, latency p50 5.5 ms / max 18 ms, server up in 0.55 s.
  - **Sim eval running** (baseline vs v1, same seeds): see `eval/README.md` and `eval/RESULTS.md`.
  - **v1.1** (Sat 14 Nov ~16:40): the baseline's first sim trials left 6 of 15 objects on the table; 3 of the 6 were cross-body grasps at the edge of the arm's reach, and one object was retried 4 times. v1.1 hands those objects over instead and caps retries. All 14 tests pass on the sim machine (incl. 3 planner tests); image `bot-icelli/policy:v1.1` built (1.46 GB). Sim comparison with v1 running.
- **Before:** placeholder `hold` policy; `make check` passes (100 calls, 0 errors, p50 latency ~4 ms)
- **Next:** —
- **Blockers:** —

## Gotchas
- `make mock` needs the G1 URDF from Unitree's `xr_teleoperate`, which Aalto's setup script clones into `third_party/aaltonomous-humanoid/third_party/`. Without it the safety filter can't start. Works on the sim machine; not set up on laptops yet.
- `make docker-build` works on the x86 Verda machine (Docker and buildx come with the `24.04.cuda13.0.docker` image); about 1 min. Not tried on a laptop.
- **Slow models:** think in a background thread and keep returning hold targets or chunks. Held ticks the runner inserts don't count toward 27 Hz.
