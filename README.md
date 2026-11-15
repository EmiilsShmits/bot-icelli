# bot-icelli: Junction 2026 · Aaltonomous Humanoid

We're working on Aalto's challenge: make **Väiski**, a Unitree G1 humanoid with three-finger Dex3 hands, sort coloured blocks into three bins **on its own**. Development happens mostly in simulation (Isaac Sim). The organisers score submitted Docker policy servers in sim, and the top ~5 teams run on the real robot on Sunday.

> **New here? Read in this order:**
> 1. this file
> 2. [`docs/research/aalto-challenge-overview.md`](docs/research/aalto-challenge-overview.md): the challenge in plain language (details: [`aalto-humanoid.md`](docs/research/aalto-humanoid.md))
> 3. [`docs/DECISIONS.md`](docs/DECISIONS.md): what's agreed and what's still open
> 4. the README of the folder you'll work in
>
> Using an AI coding tool? It should read [`AGENTS.md`](AGENTS.md) (Claude Code does this automatically through `CLAUDE.md`).

## Who does what

| Area | Folder | People |
|---|---|---|
| Model fine-tuning | [`training/`](training/) | Emīls, Tiya |
| Simulation | [`sim/`](sim/) | Marcus, Samer |
| Sim data → training → sim eval on Modal | [`modal_pipeline/`](modal_pipeline/) | Marcus |
| ADK agent with Gemini Robotics-ER in control | [`gemini-er/`](gemini-er/) | Marcus |
| Datasets | [`data/`](data/) | TBD |
| The submission (policy server + Docker) | [`policy/`](policy/) | TBD |
| Scoring in sim | [`eval/`](eval/) | TBD |
| Knowledge base | [`docs/`](docs/) | everyone |

## The pipeline the challenge implies

```
real-robot demos (Aalto drops) + anything we generate in sim  →  data/
data/      →  training/   (fine-tune a policy)
training/  →  policy/     (server + Docker image)
policy/    →  eval/       (score in sim)  →  submit
```

How the areas hand work to each other (formats, storage) is still to be agreed; see [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Quickstart (laptop, no GPU needed)

```bash
git clone --recurse-submodules https://github.com/EmiilsShmits/bot-icelli.git
cd bot-icelli
make setup      # submodule + .venv (needs Python ≥ 3.10; override with: make setup PYTHON=/path/to/python3.12)
make check      # starts the placeholder policy server and runs Aalto's plumbing test: should end with PASS
```

- GPU work (the Isaac sim) runs on a cloud RTX machine: [`docs/runbooks/verda-sim-setup.md`](docs/runbooks/verda-sim-setup.md).
- Submitting: [`docs/runbooks/submit.md`](docs/runbooks/submit.md).

## Repo layout

```
AGENTS.md            context + rules for humans and AI tools
CLAUDE.md            loads AGENTS.md for Claude Code
CONTRIBUTING.md      how to keep the knowledge base current
Makefile             common commands (make help)
.env.example         names of the keys we use (copy to .env, never commit .env)
docs/                knowledge base: BRIEF, PLAN, PROGRESS, DECISIONS, TEAM, runbooks/, research/, challenges/
sim/  data/  training/  policy/  eval/      work areas, each with its own README
third_party/aaltonomous-humanoid/          Aalto's starter repo (git submodule, pinned, never edited)
artifacts/           local datasets / checkpoints / logs (git-ignored)
```

## Never commit
- **Keys:** put them in `.env` (template: `.env.example`).
- **Datasets, weights, run logs:** GitHub caps files at 100 MB. Where they live instead is still to be agreed.

## Links
- Aalto starter repo: https://github.com/zupermiez/aaltonomous-humanoid (participant docs in `aaltonomous/docs/participants/`)
- Challenge page: https://hackjunction.app/participate/45/challenges/320
- Data drops, sim updates, the submission form: the Aalto channel on the Junction Discord
