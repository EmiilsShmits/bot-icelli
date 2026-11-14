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
| `policies/classical_v12.py` | **v1.2:** v1.1 + the head-camera pose re-fitted from the depth image at the first look of every episode (`headpose.py`), used only within plausible limits |
| `policies/classical_v13.py` | **v1.3:** v1.2 + a free drop spot per bin. Aalto's planner drops every object at one point, so the second one lands on the first and doesn't count (`eval/analysis/FINDINGS.md` §1); the n-th drop now goes to spot n of 3, all ≥ 4 cm inside the walls |
| `policies/classical_v14.py` | **v1.4:** v1.3 + a grasp check at the end of the lift (empty hand: skip the carry, go home, look again; ported from Emīls's `upgrades.py`, threshold 0.006 rad from 215 logged grasps) + a retry that uses another arm / finger direction + a fix to v1.2's head-camera fit check (it rejected the correct 10° fit in the venue look; now judged by where the camera ends up) |
| `headpose.py` | Head-camera pose from one depth image (table plane + bin walls). Copied from Emīls's `decision_oracle/camera.py` (that folder stays out of the image); keep the two in sync |
| `instruction.py` | Instruction → colour → bin, using Emīls's rule parser (`training/instruction_parser/rule_parser.py`) |
| `tools/triangle_pick.py` | Agent-callable triangle grasp planner: face-aligned pick-and-place from a vision-supplied pelvis-frame pose; returns a safety-checked trajectory, never executes it |
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

### Triangle tool
`ClassicalV1.get_tools(obs)["pick_triangle"]` returns a model-callable function with the measured joint state bound
internally. The higher-level agent supplies a vision-confirmed triangle colour / pelvis-frame top centre / yaw and
target bin. A successful result contains a safety-checked pick-and-place joint trajectory; pass it through `Guard`
before execution. The tool is lazy-loaded and does not change `act()` behavior. The current camera detector is
shape-agnostic, so the caller must supply the triangle pose; the policy executor still needs to dispatch returned
trajectories.

## Status
- **Now (Sat 14 Nov, Samer + Claude):** v1 written; unit tests pass (instruction mapping on 200 training-template instructions + real colour names, guard, colour ranges on sim and real colours).
  - **Image built** on the Linux sim machine: `make docker-build POLICY=v1 IMAGE=bot-icelli/policy:v1`, **1.46 GB**; the build-time load check passes (Pinocchio, URDF, config, parser).
  - **Aalto's replay test passes** against the image (`aaltonomous.deploy.replay --synthetic 100 --container bot-icelli/policy:v1`): 100 calls, 0 errors, latency p50 5.5 ms / max 18 ms, server up in 0.55 s.
  - **Sim eval running** (baseline vs v1, same seeds): see `eval/README.md` and `eval/RESULTS.md`.
  - **v1.1** (Sat 14 Nov ~16:40): the baseline's first sim trials left 6 of 15 objects on the table; 3 of the 6 were cross-body grasps at the edge of the arm's reach, and one object was retried 4 times. v1.1 hands those objects over instead and caps retries. All 14 tests pass on the sim machine (incl. 3 planner tests); image `bot-icelli/policy:v1.1` built (1.46 GB). Sim comparison with v1 running.
  - **v1.2** (Sat 14 Nov ~17:00): v1.1 + head-camera pose fit (Emīls's). On live frames the fit corrects 0.9° / ~1 cm in Aalto's nominal sim (its renderer ignores the calibration's principal point, ~1°), ~2° / ~2.5 cm with `AALTO_DR=train` (camera jitter, as in the held-out variant), and ~10° in the venue look / on the real robot. 17 tests pass on the sim machine (synthetic tilts of 0/5/10° recovered within 0.3°); image `bot-icelli/policy:v1.2` (1.46 GB) passes the replay test (100 calls, 0 errors, p50 5.7 ms, up in 0.54 s). In the sim comparison next.
  - **Reset fix (all versions, Sat 14 Nov ~17:00):** Aalto's baseline failed the sim gate once under load (`safe_stop` at step 0): its `reset()` waited ~14 s for a planning thread left over from an episode cut off by the time limit, and the runner's watchdog stops the robot after 3 s of sim time without a command. Ours now returns at once and holds the arms in `act()` until that thread is done (`classical_v1.py`). 18 tests pass on the sim machine; images v1.1 `b93cf1bf1b73` and v1.2 `4a817cbfe5be` rebuilt with it (v1.2 replay test: 100 calls, 0 errors).
  - **First real sim numbers (Sat ~18:00):** v1.2 nominal is level with the baseline, 18/28 each after 7 of 10 seeds (`eval/RESULTS.md` once done). The earlier "v1 80 %" was Aalto's oracle (e-010).
  - **v1.3** (Sat 14 Nov ~18:00): v1.2 + a free drop spot per bin (`eval/analysis/FINDINGS.md` §1: the baseline's second drop into a bin scored 2 of 8). Spots per bin: Aalto's point, then 5 cm further along the bin, then 4.7 cm deeper (side bins) / ±5 cm (centre bin), all ≥ 4 cm inside the walls; falls back to Aalto's point if a spot can't be reached. 21 tests pass on the sim machine (all 3 spots of every bin plan from home); image `bot-icelli/policy:v1.3` (`60ef1b8980de`, 1.46 GB) passes the replay test (100 calls, 0 errors, p50 4.9 ms). Queued in the sim right after v1.2, same seeds.
  - **Sim results (Sat ~19:40, `eval/RESULTS.md`):** v1.2 and v1.3 both sort 26/40 in the nominal sim, the same as the baseline (e-023, e-024). v1.3's drop spots work (no lost object rests on another one; baseline 5 of 14) but 13 of its 14 lost objects end closer than 27.5 cm to the pelvis, where grasps keep failing.
  - **v1.4** (Sat 14 Nov ~19:30, Samer + Claude): v1.3 + grasp check after the lift + a retry with another arm / finger direction + the head-fit check fix. In the venue look v1.2/v1.3 rejected their own correct fit (tilt 9.8°, "shift −8.3 cm", but the camera itself moved only 1.9 cm: the plane fit tilts the pose about the pelvis origin and the bin fit moves it back), so they ran on a camera ~10° off: on a venue-look frame v1.3 finds 11 "objects" (bins among them, wrong heights), v1.4 exactly the 6 objects. In the nominal and randomised sims every fit was accepted before (25 of 25), so nothing changes there. 26 tests pass on the sim machine; image `bot-icelli/policy:v1.4` (`cd8311e9f64e`, 1.46 GB) passes the replay test (100 calls, 0 errors, p50 4.2 ms, up in 0.5 s). Queued in the sim with randomisation and in the venue look.
- **Triangle skill:** all policy versions expose a lazy `pick_triangle` tool through `ClassicalV1.get_tools(obs)`. It uses face-aligned grasp planning and returns an Aalto-planner-checked trajectory. A caller must provide triangle shape and pelvis-frame top centre/yaw; the normal submission detector is shape-agnostic and the policy executor does not yet dispatch skill trajectories.
- **Before:** placeholder `hold` policy; `make check` passes (100 calls, 0 errors, p50 latency ~4 ms)
- **Next:** connect shape/yaw perception and policy-executor dispatch, then run randomized Isaac trials to measure grasp success.
- **Blockers:** —

## Gotchas
- `make mock` needs the G1 URDF from Unitree's `xr_teleoperate`, which Aalto's setup script clones into `third_party/aaltonomous-humanoid/third_party/`. Without it the safety filter can't start. Works on the sim machine; not set up on laptops yet.
- `make docker-build` works on the x86 Verda machine (Docker and buildx come with the `24.04.cuda13.0.docker` image); about 1 min. Not tried on a laptop.
- **Slow models:** think in a background thread and keep returning hold targets or chunks. Held ticks the runner inserts don't count toward 27 Hz.
