# bot-icelli: Junction 2026 · Aaltonomous Humanoid

We're teaching **Väiski**, Aalto's Unitree G1 humanoid with three-finger Dex3 hands, to sort coloured blocks into three bins **on its own**. We build mostly in simulation (Isaac Sim) with a handful of real-robot demos. We hand in a Docker policy server; the top ~5 teams run it on the real robot on Sunday.

> **New here? Read in this order:**
> 1. this file
> 2. [`docs/research/aalto-humanoid.md`](docs/research/aalto-humanoid.md): the robot, sim and official rules
> 3. [`docs/PLAN.md`](docs/PLAN.md)
> 4. the README of the folder you'll work in
>
> Using an AI coding tool? It should read [`AGENTS.md`](AGENTS.md) (Claude Code does this automatically through `CLAUDE.md`).

## Who does what

| Area | Folder | People |
|---|---|---|
| Model fine-tuning | [`training/`](training/) | Emīls, Tiya |
| Simulation | [`sim/`](sim/) | Marcus, Samer |
| Datasets (real + synthetic) | [`data/`](data/) | shared |
| The submission (policy server + Docker) | [`policy/`](policy/) | shared, one integrator merges |
| Scoring in sim | [`eval/`](eval/) | shared |
| Knowledge base | [`docs/`](docs/) | everyone |

## How it fits together

```
 Aalto real demos (Hugging Face drops) ─┐
 our sim-generated demos (sim/) ────────┴─> data/  ─ LeRobot dataset ─>  training/  ─ checkpoint ─>  policy/  ─ Docker image ─>  eval/  ─>  submit
                                          DATASETS.md                    MODELS.md                    server + Dockerfile         RESULTS.md
```

Each arrow is a fixed format (see [`AGENTS.md`](AGENTS.md#how-the-parts-connect-contracts)). That lets the sim half and the training half work in parallel without waiting on each other.

## Quickstart (laptop, no GPU needed)

```bash
git clone --recurse-submodules https://github.com/EmiilsShmits/bot-icelli.git
cd bot-icelli
make setup      # submodule + .venv (needs Python ≥ 3.10; override with: make setup PYTHON=/path/to/python3.12)
make check      # starts our policy server and runs Aalto's plumbing test: should end with PASS
```

GPU work (the Isaac sim and training) runs on a Verda cloud machine; see [`docs/runbooks/verda-sim-setup.md`](docs/runbooks/verda-sim-setup.md).
To submit, see [`docs/runbooks/submit.md`](docs/runbooks/submit.md).

## Repo layout

```
AGENTS.md            rules + map for humans and AI tools (single source of rules)
CLAUDE.md            loads AGENTS.md for Claude Code
CONTRIBUTING.md      branches, commits, logging experiments, adding a new area
Makefile             every common command (make help)
.env.example         names of the keys we use (copy to .env, never commit .env)
docs/                knowledge base: BRIEF, PLAN, PROGRESS, DECISIONS, TEAM, runbooks/, research/, challenges/
sim/  data/  training/  policy/  eval/      the work areas, each with its own README
third_party/aaltonomous-humanoid/          Aalto's starter repo (git submodule, pinned, never edited)
artifacts/           local datasets / checkpoints / logs (git-ignored)
```

## Big files and secrets
- **Never commit** datasets, weights or run logs. Use private Hugging Face repos plus the Verda persistent volume (`/data`). Local copies go in `artifacts/`.
- **Never commit** keys. Put them in `.env` (template: `.env.example`) and share values in private team chat.

## Links
- Aalto starter repo: https://github.com/zupermiez/aaltonomous-humanoid (participant docs in `aaltonomous/docs/participants/`)
- Challenge page: https://hackjunction.app/participate/45/challenges/320
- Data drops, sim updates, the submission form: the Aalto channel on the Junction Discord
