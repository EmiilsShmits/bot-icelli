# AGENTS.md: context for anyone working in this repo

This file is for AI coding tools (Codex, Cursor, Copilot, Claude Code, Gemini CLI, …) and for humans. Keep it short and factual.
Details live in `docs/` and in each folder's `README.md`.

**Start here: [`docs/CONTEXT.md`](docs/CONTEXT.md)**, the current situation in one file. It separates **FACTS** (each with its source), **OPINIONS** (Samer + Claude's recommendations, not team decisions) and **OPEN** questions. Read it before starting work. Never present an opinion from it as decided, and update it when you change something it describes.

## Project
- **Junction 2026 hackathon** (Fri 13 – Sun 15 Nov 2026), team bot-icelli.
- **Working on:** Aaltonomous Humanoid (Aalto University), mostly in simulation. A Unitree G1 with Dex3 three-finger hands must sort coloured blocks into 3 bins on its own. Our brief is still to be agreed (`docs/BRIEF.md`).
- **Official rules** (robot, sim, scoring, submission):
  - our digest: [`docs/research/aalto-humanoid.md`](docs/research/aalto-humanoid.md)
  - Aalto's docs: `third_party/aaltonomous-humanoid/aaltonomous/docs/participants/`
- **Team split:**
  - Emīls + Tiya: model fine-tuning (`training/`)
  - Marcus + Samer: simulation (`sim/`)
- **Open team decisions:** listed at the top of [`docs/DECISIONS.md`](docs/DECISIONS.md). Don't treat them as settled.

## Map: read the relevant file before acting
| Path | What |
|---|---|
| `docs/CONTEXT.md` | **Read first.** Where we stand: facts (sourced) vs Samer + Claude's opinions vs open questions |
| `docs/BRIEF.md` | Our brief: focus, priorities, stacked tech challenges. **Blank until the team agrees** |
| `docs/PLAN.md` | Approach, milestones, demo/pitch. Not started |
| `docs/STRATEGY.md` | Strategy proposal (Sat 14 Nov): plan, architecture, who does what, tech challenges. **Not agreed yet** |
| `docs/PROGRESS.md` | Team-level status + log |
| `docs/DECISIONS.md` | Open decisions + append-only log of choices made |
| `docs/TEAM.md` | Who's who, skills, hardware |
| `docs/runbooks/` | Step-by-step how-tos (Verda + sim setup, recreating the venue-look sim, submitting) |
| `docs/research/` | Research notes (robot, APIs/credits, Rokoko, Jetson) |
| `sim/` | Simulation work (Marcus, Samer) |
| `modal_pipeline/` | Marcus's Modal pipeline: sim, oracle data recording, π0.5 training, sim evaluation, policy server. Start with its `TEAM_HANDOVER.md` |
| `training/` | Model fine-tuning work (Emīls, Tiya) |
| `data/` | Datasets: real drops and anything we generate |
| `policy/` | The submission: policy server + Dockerfile. Candidates v1, v1.1, v1.2 in `policy/policies/` (status in `policy/README.md`) |
| `policy/decision_oracle/` | Sim-only exploration, **not in the submission**: Aalto's oracle as motion functions, Gemini Decision 1 / rule choosers, camera-only perception. Has its own README with results |
| `eval/` | Scoring policies in sim |
| `third_party/aaltonomous-humanoid/` | Aalto's starter repo (git submodule, pinned). **Never edit it** |
| `artifacts/` | Local datasets, checkpoints, logs. Git-ignored |

Every work folder has a `README.md` with the same sections:
- Purpose
- Owner
- Inputs → Outputs
- How to run
- Status (Now / Next / Blockers)
- Gotchas

Read it before working there, and update its Status when you change something.

## Hard rules from the challenge (facts, not choices)
- **Velocity caps:** every target must change by at most **1.0 rad/s (arms)** and **3.0 rad/s (hands)**. The sim gate allows **0 clipped steps**.
- **Command rate:** ≥ **27 commands/s** from the policy. Slow models must think in a background thread and keep returning hold targets or action chunks.
- **Inputs:** the submission sees only `obs`. No privileged sim state (object poses), and no hard-coded layouts.
- **Image:** linux/amd64, CUDA ≥ 12.8, server on port 8000 within 120 s, weights inside the image, ≤ 32 GB VRAM, ≤ 40 GB image.
- **Deadlines:** Junction's project page closes **Sun 15 Nov 10:00** (official schedule). Aalto has **not** published a time for the Docker image: their brief says finalists are picked in sim on **Saturday**, and the final image is due Sunday at a time they'll post in the Aalto Discord channel. ("Sun 10:00 for the image" was our assumption, not Aalto's answer.) Until they announce it, submit a working image as early as possible on Saturday.
- **Network:** Aalto says the finals PC will have internet (Sat 14 Nov), but a failed or slow call counts as a failure with no rerun. Any API call needs an offline fallback and must never block `act()`.
- **Aalto's real demos:** LeRobot v3.0, 30 Hz, `observation.state` and `action` = 28 values each (14 arm + 14 hand joints, absolute radians), plus a GR00T-format copy.
  - The drops so far (HF `zupermiez/g1_pick_cube`, `zupermiez/g1_junction_drop_2`) differ from Aalto's data card: camera keys `cam_high` / `cam_*_wrist`, no head depth, no success labels.
  - **They break the speed caps** (arms 2–4 rad/s, fingers up to 25 rad/s). Retime before training on them: `docs/research/real-data-findings.md`.
- **Real objects:** orange, yellow, purple (the sim uses red, yellow, blue); the bins are orange too. Drop 2's instructions say "orange", "purple" and "box". **Real rung 1 (Aalto, Sat 15:07): yellow → left, purple → center, orange → right**, unlike the sim. Instructions may name colour, shape or both: always parse `obs["instruction"]`, never hardcode a mapping.
  - In the robot's head camera, orange reads as hue 11–13 (between the baseline's red and yellow ranges), yellow as 34–46 (outside its yellow range) and purple as ~110 (blue). The stock baseline misses orange and most yellow.

## Working rules
- **Demo beats completeness.** Judge every task by "does this help the real-robot result or the pitch?"
- **`main` should always run.**
- **If something that affects judging is unclear, ask** rather than guess.
- **Record decisions** in `docs/DECISIONS.md` once the team agrees on them.
- **No silent new dependencies or services.** Add them to that folder's `requirements.txt` and mention them.
- **Never commit secrets.** Keys go in a local `.env` (see `.env.example`).
- **Never commit datasets or weights.** GitHub caps files at 100 MB. Where they live instead is an open decision.
- **AI tools commit only when a human asks.**
- **No AI attribution in commits or PRs.** No `Co-Authored-By:` or "Generated with …" lines for Claude, Copilot, Codex, Cursor or Gemini: GitHub then lists the tool as a contributor of this repo. `.claude/settings.json` turns Claude Code's attribution off, and `.githooks/commit-msg` deletes such lines. Turn the hook on once per clone with `git config core.hooksPath .githooks` (`make setup` and every Claude Code session in this repo do it for you).

## Commands (run from the repo root; `make help` lists them all)
```bash
make setup          # init submodule + .venv with policy deps (needs Python ≥ 3.10)
make serve          # run the placeholder policy server on :8000
make check          # Aalto's synthetic replay test against our server (shapes + ≥ 27 Hz)
make mock           # full episodes on Aalto's mock backend (needs the G1 URDF; see policy/README.md)
make docker-build   # build the submission image (linux/amd64); works on the Verda sim machine (v1 image 1.46 GB)
make docker-check   # replay test against the built image
make eval           # score in Isaac sim on the Verda sim machine, untested so far
make update-aalto   # pull the latest Aalto starter repo into the submodule
```
