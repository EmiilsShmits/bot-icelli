# AGENTS.md: context and rules for anyone working in this repo

This file is for AI coding tools (Codex, Cursor, Copilot, Claude Code, Gemini CLI, …) and for humans. It is the single source of project rules.
Keep it short. Details live in `docs/` and in each folder's `README.md`.

## Project
- **Junction 2026 hackathon** (Fri 13 – Sun 15 Nov 2026), team bot-icelli.
- **Challenge:** Aaltonomous Humanoid (Aalto University). A Unitree G1 with Dex3 three-finger hands must sort coloured blocks into 3 bins on its own.
- **How it's scored:** we hand in a Docker image with a policy server. It's scored in Isaac Sim, and the top ~5 teams run on the real robot on Sunday.
- **Official rules (robot, sim, scoring, submission):** [`docs/research/aalto-humanoid.md`](docs/research/aalto-humanoid.md) and Aalto's `third_party/aaltonomous-humanoid/aaltonomous/docs/participants/`.
- **Our brief** (to be agreed): [`docs/BRIEF.md`](docs/BRIEF.md). **Plan:** [`docs/PLAN.md`](docs/PLAN.md).
- **Team split:**
  - Emīls + Tiya: model fine-tuning (`training/`)
  - Marcus + Samer: simulation (`sim/`)
  - Shared: `data/`, `policy/`, `eval/`

## Map: read the relevant file before acting
| Path | What | Owner |
|---|---|---|
| `docs/BRIEF.md` | Our agreed brief: focus, stacked tech challenges, priorities. **Blank until the team agrees** | all |
| `docs/PLAN.md` | Approach, milestones, demo/pitch | all |
| `docs/PROGRESS.md` | Team-level status + log | all |
| `docs/DECISIONS.md` | Append-only log of non-obvious choices | all |
| `docs/TEAM.md` | Who's who, skills, hardware | all |
| `docs/runbooks/` | Step-by-step how-tos (Verda + sim setup, submitting) | all |
| `docs/research/` | Research notes (robot, APIs/credits, Rokoko, Jetson) | all |
| `sim/` | Isaac sim setup, domain randomisation, synthetic demos, real2sim | Marcus, Samer |
| `data/` | Download, convert, filter and version datasets. Registry: `data/DATASETS.md` | shared |
| `training/` | Fine-tuning configs + scripts. Registry: `training/MODELS.md` | Emīls, Tiya |
| `policy/` | **The submission:** policy server + Dockerfile | shared (one integrator merges) |
| `eval/` | Score any policy in sim. Scoreboard: `eval/RESULTS.md` | shared |
| `third_party/aaltonomous-humanoid/` | Aalto's starter repo (git submodule, pinned). **Never edit it.** Their docs: `aaltonomous/docs/participants/` | Aalto |
| `artifacts/` | Local datasets, checkpoints, run logs. Git-ignored | — |

Every work folder has a `README.md` with the same sections:
- Purpose
- Owner
- Inputs → Outputs
- How to run
- Status (Now / Next / Blockers)
- Gotchas

**Read it before working in that folder, and update its Status when you change something.**

## How the parts connect (contracts)
```
Aalto real demos ─┐
sim-generated demos ─┴─> data/ ──(LeRobot v3.0 dataset)──> training/ ──(checkpoint)──> policy/ ──(Docker image)──> eval/ ──> submit
```
1. **Dataset:**
   - LeRobot v3.0, with the same keys as Aalto's drops: `observation.state` = 28 values (arm_q 14 + hand_q 14), `action` = 28 absolute joint targets at 30 Hz.
   - Register every dataset in `data/DATASETS.md`.
2. **Checkpoint:**
   - Weights + a config (model type, normalisation stats, action horizon, cameras used), stored on a private Hugging Face repo.
   - Register every checkpoint in `training/MODELS.md`.
3. **Policy:**
   - Aalto's websocket protocol on port 8000; the image is pinned by digest.
   - Log every scored run in `eval/RESULTS.md`, failures included.

## Hard rules (from the challenge; breaking them gets us disqualified or stuck at the gate)
- **Velocity caps:** every target must change by at most **1.0 rad/s (arms)** and **3.0 rad/s (hands)**. The sim gate allows **0 clipped steps**.
- **Command rate:** ≥ **27 commands/s** from our policy. Slow models must think in a background thread and keep returning hold targets or action chunks.
- **Inputs:** a submission sees only `obs`. No privileged sim state (object poses), and no hard-coded layouts.
- **Image:** CUDA ≥ 12.8, linux/amd64, weights inside the image, server up within 120 s, ≤ 32 GB VRAM, ≤ 40 GB image.
- **No network at the finals is guaranteed**, so any LLM/API call needs an offline fallback.

## Working rules
- **Demo beats completeness.** Judge every task by "does this raise the real-robot score or the pitch?"
- **`main` always runs.** `make check` must pass before anything merges into `policy/`.
- **Requirements come from Aalto's docs** (digest: `docs/research/aalto-humanoid.md`) and, once agreed, `docs/BRIEF.md`. If something that affects judging is unclear, ask rather than guess.
- **Record decisions** in `docs/DECISIONS.md`: anything non-obvious (method, dataset, scope cut, architecture).
- **No silent new dependencies or services.** Add them to that folder's `requirements.txt` and mention them in the PR or commit.
- **Secrets** live only in a local `.env` (see `.env.example`). Never put keys or promo codes in code or docs.
- **Big files never go in git:** datasets, weights, run logs. Use private Hugging Face repos plus the Verda persistent volume, and keep local copies in `artifacts/`.
- **Commits:** prefix with the area (`sim: …`, `data: …`, `train: …`, `policy: …`, `eval: …`, `docs: …`). Small and often. AI tools commit only when a human asks.

## Commands (run from the repo root; `make help` lists them all)
```bash
make setup          # init submodule + .venv with policy deps (needs Python ≥ 3.10)
make serve          # run our policy server on :8000
make check          # plumbing test: Aalto's synthetic replay against our server (shapes + ≥ 27 Hz)
make mock           # full episodes on Aalto's mock backend (no GPU)
make docker-build   # build the submission image (linux/amd64)
make docker-check   # replay test against the built image (also checks startup < 120 s)
make eval           # score in Isaac sim; run on the Verda sim machine (see docs/runbooks/)
make update-aalto   # pull the latest Aalto starter repo into the submodule
```

## Code conventions
- **Python 3.10+** (the Aalto code and LeRobot need it). Each folder has its own `requirements.txt`, because the sim (Isaac env), training (LeRobot/torch) and the submission image need different environments.
- **Import Aalto code as `aaltonomous.*`.** `make` targets set `PYTHONPATH=third_party/aaltonomous-humanoid`.
- **Configs go in YAML** in the folder's `configs/`. No magic numbers in scripts.
- **IDs:** datasets `ds-NNN-short-name`, checkpoints `m-NNN-short-name`, eval runs `ev-NNN`. Number them in order in the registries.
