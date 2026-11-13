# Progress

_Update at the end of every session. Newest state at the top; keep it short._

## Now
- **Done:** project context scaffolding (CLAUDE.md, docs/); all 38 challenges saved to `docs/challenges/` with an overview table; sponsor codes moved to `.env.challenges`; hardware + API research in `docs/research/` (Aalto G1 robot/sim, all credits and APIs, Rokoko gloves, Jetson)
- **Also done:** repo structure for knowledge base + code (see `README.md`, `AGENTS.md`); Aalto starter repo linked as a submodule; placeholder policy server passes Aalto's plumbing test (`make check`)
- **In progress:** working on the Aalto humanoid, mostly in sim. Team split: fine-tuning (Emīls, Tiya), simulation (Marcus, Samer)
- **Next:** agree on the open items at the top of `docs/DECISIONS.md` (brief, approach, handoffs, storage, workflow, owners)
- **Blockers:** open team decisions (see `docs/DECISIONS.md`). Open questions for mentors are listed at the end of `docs/research/aalto-humanoid.md` (real-G1 teleop access, Coil Pro/suit for wrist tracking)

## Mocks & shortcuts in the demo
_Anything hardcoded or faked, so nobody is surprised at demo time._

## Gotchas
- Challenge pages contain shared API keys and promo codes. They live in `.env.challenges` only; the docs reference them by variable name.
- Oxylabs credits require buying a $500/month plan with a 100% first-month discount. If we use it, cancel the subscription after the event.
- `make mock` needs the G1 URDF that Aalto's setup script clones (not present on laptops yet); `make check` works without it.
- Aalto sim needs an **RTX-class GPU** (not A100/H100: no RT cores, cameras won't render), on-demand, with a persistent volume. The first start compiles shaders (5-10 min). It runs at ~0.7x real time.
- Aalto finals PC may have **no network**: any LLM call in the policy needs an offline fallback.
- Hardware desk (Fri 21:15): all Rokoko gloves and the one suit are checked out; no Jetson listed. 3D printers are free.
- Qualia environment closes 7 days after the event; download anything we want to keep.

## Log
- 2026-11-13 — Set up project context structure.
- 2026-11-13 — Wrote team skills summary from LinkedIn to `docs/TEAM.md`.
- 2026-11-13 — Pulled full text of all 19 main and 19 tech challenges from hackjunction.app into `docs/challenges/`.
- 2026-11-13 — Research: Aalto humanoid repo docs, all hackerpacks + hardware desk, Rokoko gloves, Jetson → `docs/research/`.
- 2026-11-13 — Set up repo structure (AGENTS.md, work-area folders, registries, runbooks, Aalto submodule, placeholder policy server).
- 2026-11-13 — Trimmed docs to facts only; team decisions moved to an open list in `docs/DECISIONS.md`.
