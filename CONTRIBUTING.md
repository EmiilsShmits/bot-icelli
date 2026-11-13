# Contributing

How we keep the repo usable as a shared knowledge base. **Git workflow** (branches, reviews, who merges) is still to be agreed; see the open decisions in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Keeping context current (for humans and AI tools alike)
- **Changed how something works or how to run it?** Update that folder's `README.md` (How to run, Status).
- **The team agreed on something non-obvious?** Add an entry to [`docs/DECISIONS.md`](docs/DECISIONS.md).
- **Ending a work block?** Update your folder's Status. Add one line to [`docs/PROGRESS.md`](docs/PROGRESS.md) if it matters to the whole team.
- **A rule everyone should follow?** Put it in [`AGENTS.md`](AGENTS.md), not in a tool-specific file.

## Logging work
`data/DATASETS.md`, `training/MODELS.md` and `eval/RESULTS.md` are empty tables to log datasets, checkpoints and sim scores. Adjust the columns as needed.

## Adding a new work area (e.g. `teleop/`)
1. Create the folder with a `README.md` using the standard sections (copy one from another folder):
   - Purpose
   - Owner
   - Inputs → Outputs
   - How to run
   - Status
   - Gotchas
2. Add a row to the map in `AGENTS.md` and the "Who does what" table in `README.md`.

## Never commit
- **Keys:** use a local `.env` (copy `.env.example`). Sponsor promo codes are in `.env.challenges`, which is also git-ignored.
- **Datasets, weights, run logs:** `.gitignore` blocks the common file types, but check `git status` before you commit.
- **New packages:** go in that folder's `requirements.txt`. Mention new services to the team.
