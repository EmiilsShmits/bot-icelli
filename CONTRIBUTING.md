# Contributing

Four people, 48 hours, one repo. These rules keep `main` working and the knowledge base current.

## Branches and merging
- **Your own area** (`sim/`, `training/`, `data/`, `eval/`): push straight to `main` in small commits. Pull often (`git pull --rebase`).
- **Shared code** (`policy/`, the Makefile, root files, `docs/BRIEF.md`, `docs/PLAN.md`):
  1. Branch `area/short-name` (e.g. `policy/act-loader`).
  2. Open a pull request.
  3. Get one teammate to look at it.
  4. `make check` must pass.
- **Never** force-push `main`.
- **Updating Aalto's starter code:** run `make update-aalto` and commit the new submodule pointer with a note on what changed (their changelog is on Discord).

## Commit messages
`<area>: <what changed>`, for example:
- `sim: add lighting randomisation config`
- `train: ACT baseline on ds-001`
- `docs: record decision on action chunk size`

## Logging work: the three registries
Log every run, including failures. The registries are how the two halves of the team stay in sync.

| You made… | Add a row to | ID format |
|---|---|---|
| a dataset (downloaded, converted, filtered, generated) | [`data/DATASETS.md`](data/DATASETS.md) | `ds-NNN-short-name` |
| a checkpoint | [`training/MODELS.md`](training/MODELS.md) | `m-NNN-short-name` |
| a scored sim run | [`eval/RESULTS.md`](eval/RESULTS.md) | `ev-NNN` |

## Keeping context current (for humans and AI tools alike)
- **Changed how something works or how to run it?** Update that folder's `README.md` (How to run, Status).
- **Made a non-obvious choice?** Add an entry to [`docs/DECISIONS.md`](docs/DECISIONS.md).
- **Ending a work block?** Update your folder's Status. Add one line to [`docs/PROGRESS.md`](docs/PROGRESS.md) if it matters to the whole team.
- **New rule that everyone should follow?** Put it in [`AGENTS.md`](AGENTS.md), not in a tool-specific file.

## Dependencies
- Each folder has its own `requirements.txt`. Add new packages there and say why in the commit.
- **New services** (a new API, cloud or tracker): mention them in team chat and add a line to `docs/DECISIONS.md`.

## Adding a new work area (e.g. `teleop/` for Rokoko gloves)
1. Create the folder with a `README.md` using the standard sections (copy one from another folder):
   - Purpose
   - Owner
   - Inputs → Outputs
   - How to run
   - Status
   - Gotchas
2. Add a row to the map in `AGENTS.md` and the "Who does what" table in `README.md`.
3. If it produces data or models, use the existing registries rather than inventing new ones.

## Secrets and big files
- **Keys:** local `.env` only (copy `.env.example`).
- **Sponsor promo codes:** `.env.challenges` (also git-ignored).
- **Datasets and weights:** go on Hugging Face (private) or `/data` on Verda, never in git. `.gitignore` blocks the common weight/data file types, but check `git status` before you commit.
