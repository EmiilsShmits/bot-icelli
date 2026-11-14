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
| `policies/oracle_v15.py` | **v1.5:** a different base. Aalto's oracle motions (face grasps, relay, drop spots inside a bin) on the head camera only, with Emīls's upgrades from `decision_oracle/` (failure memory, grasp check, an option search over every object) + same-side arms (each arm stays on its half of the table; cross-side objects are handed over on the centre line) + a grasp for triangles lying on their side (fingers along the ridge, across the two triangular end faces) + colour × shape instructions. Offline, no API calls |
| `policies/oracle_v16.py` | **v1.6:** v1.5 + Gemini Decision 1 (online, `GEMINI_API_KEY`). It names each new object's colour and shape from a crop, finds saturated blobs no HSV range took (kept only if Decision is sure of a colour and a shape), and reads the instruction (`instruction_d1.py`). The depth geometry keeps the final say on "lying". `V15_SIDES` defaults to `off`. No key, error, deadline (2.5 s) or low confidence: exactly v1.5. act() never waits for a call |
| `instruction_d1.py` | v1.6 instruction stage: one Decision call started at reset() (10 slots: 9 colour × shape types + `other`), used at the first look if every slot is ≥ 0.6 confident, else the rule parser's mapping stays. Prompt fixes vs `training/instruction_parser/gemini_decision.py`: orange = red and purple = blue, no "invalid?" veto |
| `policies/oracle_v16g.py` | **v1.6g:** v1.6 with the fine-tuned Gemma 3 1B instruction parser inside the image as the offline middle layer: Decision 1 → Gemma 1B (CPU) → rule parser. Everything else is v1.6. Without the weights or torch it runs exactly as v1.6, but `make docker-build POLICY=v1.6g` fails then, so a v1.6g image always has a working parser |
| `instruction_gemma.py` | v1.6g's Gemma stage (`GemmaInstruction`: weights from `weights/gemma-parser-1b/`, loaded at server start with one self-test answer; one generate per episode in a background thread, deadline `V16G_GEMMA_DEADLINE` = 5 s after reset; the training prompt and answer parser themselves) and `InstructionChain` (Decision → Gemma → none, same interface as `instruction_d1`) |
| `requirements-gemma.txt` | v1.6g only: CPU-only torch + transformers, installed by the Dockerfile when `POLICY=v1.6g` |
| `tools/replay_instruction.py` | Aalto's synthetic replay test with a non-fixed instruction, so v1.6 / v1.6g's background instruction work runs while act() is timed |
| `policies/look.py` | **look:** never moves (holds the measured pose, ends after `LOOK_SECONDS`=30). Logs v1.4's head-camera fit, the objects it sees with the calibration and the fitted camera, a hand check (tilted camera or leaning robot; not validated yet), depth quality and finger angles. For the first run on the real robot: `docs/runbooks/real-robot.md` |
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

### v1.6g (Gemma 3 1B parser inside the image)
```bash
# weights first (git-ignored, 2.0 GB): the student checkpoint folder (config.json, model.safetensors, tokenizer ...)
cp -r <checkpoint>/ policy/weights/gemma-parser-1b/      # training/instruction_parser/README.md says where it is
make docker-build POLICY=v1.6g IMAGE=bot-icelli/policy:v1.6g [GEMINI_KEY_FILE=...]   # fails without working weights
make docker-check IMAGE=bot-icelli/policy:v1.6g          # startup < 120 s (it loads the weights: ~10 s)
python policy/tools/replay_instruction.py --container bot-icelli/policy:v1.6g   # act() timing while Gemma generates
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
  - **Sim results (Sat ~19:10, `eval/RESULTS.md`):** v1.2 and v1.3 both sort 26/40 in the nominal sim, the same as the baseline (e-023, e-024). v1.3's drop spots work (no lost object rests on another one; baseline 5 of 14) but 13 of its 14 lost objects end closer than 27.5 cm to the pelvis, where grasps keep failing.
  - **v1.4** (Sat 14 Nov ~19:00, Samer + Claude): v1.3 + grasp check after the lift + a retry with another arm / finger direction + the head-fit check fix. In the venue look v1.2/v1.3 rejected their own correct fit (tilt 9.8°, "shift −8.3 cm", but the camera itself moved only 1.9 cm: the plane fit tilts the pose about the pelvis origin and the bin fit moves it back), so they ran on a camera ~10° off: on a venue-look frame v1.3 finds 11 "objects" (bins among them, wrong heights), v1.4 exactly the 6 objects. In the nominal and randomised sims every fit was accepted before (25 of 25), so nothing changes there. 26 tests pass on the sim machine; image `bot-icelli/policy:v1.4` (`cd8311e9f64e`, 1.46 GB) passes the replay test (100 calls, 0 errors, p50 4.2 ms, up in 0.5 s). Queued in the sim with randomisation and in the venue look.
  - **v1.5** (Sat 14 Nov ~20:00, Emīls + Claude): the decision oracle with camera perception (best without privileged state in the venue-look sim: sort_language 26/28 e-022, sort_fixed 21/27 e-019) as a policy server, plus same-side arms and the lying-triangle grasp (`decision_oracle/upgrades_v15.py`). 41 unit tests pass on the sim machine (incl. `tests/test_v15.py`); the offline self-test finds 0 of 40 options breaking the side rule. Image `bot-icelli/policy:v1.5` (`36db42368dde`, 1.46 GB) builds on sim-3 and passes the replay test (100 calls, 0 errors, p50 4.9 ms, up in 0.56 s). **Sim on Modal, venue look, gate PASS every run (0 clips, 30 Hz):** sort_fixed 20/27 with same-side arms (e-029) and **23/27 with `V15_SIDES=off` (e-030)**, against v1.4 20/27 (e-028) and Aalto's oracle with exact poses 22/27 (e-004); sort_language 22/28 strict (e-031; decision_oracle inside Aalto's evaluator 26/28, e-022); all triangles lying 18/27 (e-032; ridge grasp held 4/9 lying triangles, stock claw 0/14). The side rule costs objects on these seeds; Emīls + Claude's suggestion: run with `off` until the 3-relay change (`MAX_RELAYS_STRICT`) is measured (the code default is still `strict`). `V15_TIP_CHECK=d1|hydrogen` (default off) asks Gemini whether a block the camera calls lying really is; offline it did not beat the geometry (`decision_oracle/README.md`).
  - **v1.6** (Sat 14 Nov ~23:30, Emīls + Claude): v1.5 sides off + Gemini Decision 1 for colour, shape and the instruction (`policies/oracle_v16.py`, `instruction_d1.py`, `decision_oracle/upgrades_v16.py` + `labels_v16.py`); v1.5 is the offline fallback. Lying-prism grasp fix in v1.6 only (`V16_RIDGE_SHIFT`, `V16_RIDGE_FIRST`; v1.5 unchanged). 28 unit tests pass (`tests/test_v15.py`, `tests/test_v16.py`); `make check POLICY=v1.6` passes (100 calls, 0 errors). Modal, venue look, gate PASS every run: 48/55 on the e-030/e-040 episodes (v1.5 sides off 47/55), lying prisms 48/53 (v1.5 46/53), no key 8/9 (`eval/RESULTS.md` e-044…e-049). Image not built yet: `make docker-build POLICY=v1.6 GEMINI_KEY_FILE=...` bakes the key in, so keep that image off the public GHCR package.
  - **Sat ~20:05:** v1.4 in the venue look 20/27 (e-028); v1.3 with `AALTO_DR=train` 26/40, the baseline 11/40 (e-027). Public on GHCR: v1.4 `sha256:cd8311e9…`, v1.3 `sha256:60ef1b89…`, look `sha256:f4f871b5…` (full lines in `docs/CONTEXT.md` §2). 27 tests pass on the sim machine.
- **Triangle skill:** all policy versions expose a lazy `pick_triangle` tool through `ClassicalV1.get_tools(obs)`. It uses face-aligned grasp planning and returns an Aalto-planner-checked trajectory. A caller must provide triangle shape and pelvis-frame top centre/yaw; the normal submission detector is shape-agnostic and the policy executor does not yet dispatch skill trajectories.
- **Before:** placeholder `hold` policy; `make check` passes (100 calls, 0 errors, p50 latency ~4 ms)
- **Next:** connect shape/yaw perception and policy-executor dispatch, then run randomized Isaac trials to measure grasp success.
- **Blockers:** —

## Gotchas
- `make mock` needs the G1 URDF from Unitree's `xr_teleoperate`, which Aalto's setup script clones into `third_party/aaltonomous-humanoid/third_party/`. Without it the safety filter can't start. Works on the sim machine; not set up on laptops yet.
- `make docker-build` works on the x86 Verda machine (Docker and buildx come with the `24.04.cuda13.0.docker` image); about 1 min. Not tried on a laptop.
- **Slow models:** think in a background thread and keep returning hold targets or chunks. Held ticks the runner inserts don't count toward 27 Hz.
