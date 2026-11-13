# Decisions

_Append-only. One entry per non-obvious choice. Format:_

```
## YYYY-MM-DD — Decision title
- Decision:
- Why:
- Alternatives considered:
```

## 2026-11-13 — Use Claude Code for planning and building
- Decision: all planning, research and code live in this folder; context is kept in `CLAUDE.md` and `docs/`.
- Why: the plan sits next to the code and stays current; every session starts with the same context.
- Alternatives considered: Claude Project on claude.ai for planning (rejected: plan would drift from the code).

## 2026-11-13 — Rule out the Intel Physical AI challenge
- Decision: not entering Ignite Next × Intel.
- Why: we didn't get one of the 25 SO-101 robot stations, which the challenge requires.
- Alternatives considered: still the leading idea: Rokoko Smartgloves II + Aalto humanoid digital twin.

## 2026-11-13 — Repo is both knowledge base and code, organised by work area
- Decision:
  - one repo with `docs/` (knowledge base) plus one folder per work area: `sim/`, `data/`, `training/`, `policy/`, `eval/`
  - each folder has a README with fixed sections: Purpose, Owner, Inputs → Outputs, How to run, Status, Gotchas
  - the areas hand work over in three fixed formats (dataset, checkpoint, policy image), each logged in a registry: `data/DATASETS.md`, `training/MODELS.md`, `eval/RESULTS.md`
- Why: the team works in two halves (sim vs fine-tuning). Separate folders avoid merge conflicts, and the fixed formats let both halves work in parallel.
- Alternatives considered: one Python package with modules (harder to split ownership); GitHub Issues for status (too much overhead for 48 h; kept for bugs and blockers only).

## 2026-11-13 — AGENTS.md is the single source of rules for every AI tool
- Decision: project rules and the map live in `AGENTS.md`. `CLAUDE.md` only imports it (`@AGENTS.md`).
- Why: not everyone uses Claude. Codex, Cursor and Copilot read AGENTS.md directly; Claude Code reads it through the import; Gemini CLI can be configured to. One file means the rules can't drift.
- Alternatives considered: one context file per tool (would drift).

## 2026-11-13 — Aalto starter repo as a pinned git submodule
- Decision: `third_party/aaltonomous-humanoid` is a git submodule pinned at `36daf5b` (same content as `a2d1dee`). We never edit it. `make update-aalto` pulls their updates.
- Why: their package (`aaltonomous.*`) gives us the protocol, replay, runner and evaluator unchanged, and the submodule records exactly which version we tested against.
- Alternatives considered: copying their code (would silently go stale); pip install (their repo has no packaging).

## 2026-11-13 — Big files live outside git
- Decision: datasets, weights and run logs go on private Hugging Face repos plus the Verda volume `/data`, with local copies in `artifacts/`. `.gitignore` blocks the common weight and data file types.
- Why: GitHub caps files at 100 MB, and some drops may be licensed for participants only. Aalto's FAQ also recommends Hugging Face as a checkpoint backup.
- Alternatives considered: Git LFS (quota limits); IronShard (kept as an option if judges need big artifacts).
