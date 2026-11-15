# Decisions

## Open: to agree as a team
_Add to this list freely. When the team agrees, move the item into the log below._
- [ ] Our brief: focus, priorities, stacked tech challenges (`docs/BRIEF.md`)
- [ ] Approach / methods for the sim side and the training side
- [ ] How sim and training hand work to each other (dataset format, checkpoint format)
- [ ] Where datasets and weights live (e.g. Hugging Face, Verda volume, IronShard)
- [ ] Git workflow: branches, reviews, who merges
- [ ] Who owns the submission (`policy/`) and the hand-in
- [ ] Owners for `data/` and `eval/`
- [ ] v1.6: turn the near-body push on by default (`V16_NEAR=push`)? The e-054 / e-055 gains were measured with it on; alone it was 2/2 in full runs, but both pushed triangles fell over (`policy/decision_oracle/README.md`)

## Log
_Append-only. One entry per agreed choice. Format:_

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

## 2026-11-13 — Repo is both knowledge base and code, with one folder per work area
- Decision: `docs/` is the knowledge base. Each work area (`sim/`, `data/`, `training/`, `policy/`, `eval/`) is a folder whose `README.md` has the same sections: Purpose, Owner, Inputs → Outputs, How to run, Status, Gotchas.
- Why: the team works in two halves (sim and fine-tuning). Separate folders avoid stepping on each other, and the fixed sections keep context findable.
- Alternatives considered: one Python package with modules; GitHub Issues for status.

## 2026-11-13 — AGENTS.md is the shared context file for every AI tool
- Decision: project context and rules live in `AGENTS.md`. `CLAUDE.md` only imports it (`@AGENTS.md`).
- Why: not everyone uses Claude. Codex, Cursor and Copilot read AGENTS.md directly; Claude Code reads it through the import. One file can't drift.
- Alternatives considered: one context file per tool.

## 2026-11-13 — Aalto starter repo as a pinned git submodule
- Decision: `third_party/aaltonomous-humanoid` is a git submodule pinned at `36daf5b`. We never edit it. `make update-aalto` pulls their updates.
- Why: we use their tools (protocol, replay, runner, evaluator) unchanged, and the submodule records which version we tested against.
- Alternatives considered: copying their code (would go stale); pip install (their repo has no packaging).
