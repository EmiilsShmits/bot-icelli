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
| `check.sh` | Runs Aalto's replay / mock tests against our server (`make check`, `make mock`) |
| `Dockerfile` | Submission image (CUDA 12.8 base). The build context allowlist is in `/.dockerignore` |
| `requirements.txt` | Image dependencies (keep them small) |
| `requirements-dev.txt` | Local test dependencies |

## How to run
```bash
make setup          # once
make check          # Aalto's replay test: shapes + >= 27 Hz
make serve          # run the server on :8000
make docker-build && make docker-check GPUS=none    # build + test the image (Docker running; slow on Apple silicon)
```
Hand-in: [`../docs/runbooks/submit.md`](../docs/runbooks/submit.md).

## Status
- **Now:** placeholder `hold` policy; `make check` passes (100 calls, 0 errors, p50 latency ~4 ms)
- **Next:** —
- **Blockers:** —

## Gotchas
- `make mock` needs the G1 URDF from Unitree's `xr_teleoperate`, which Aalto's setup script clones into `third_party/aaltonomous-humanoid/third_party/`. Without it the safety filter can't start. Works on the sim machine; not set up on laptops yet.
- `make docker-build` is untested so far (Docker wasn't running). It targets linux/amd64; building on the x86 Verda machine is faster.
- **Slow models:** think in a background thread and keep returning hold targets or chunks. Held ticks the runner inserts don't count toward 27 Hz.
