# Progress

_Update at the end of every session. Newest state at the top; keep it short._

## Now
- **Deadline (Aalto, Sat ~12:50): Sun 10:00 for everything:** the sim evaluation that picks the finalists and the finals image. The finals PC will have internet. No answer yet on a real-robot test run before the finals (assume no).
- **Done:** project context scaffolding (CLAUDE.md, docs/); all 38 challenges saved to `docs/challenges/` with an overview table; sponsor codes moved to `.env.challenges`; hardware + API research in `docs/research/` (Aalto G1 robot/sim, all credits and APIs, Rokoko gloves, Jetson)
- **Also done:** repo structure for knowledge base + code (see `README.md`, `AGENTS.md`); Aalto starter repo linked as a submodule; placeholder policy server passes Aalto's plumbing test (`make check`)
- **Sim runs (Sat 14 Nov):** Aalto sim installed bare-metal on Emīls's Verda RTX 6000 Ada (`bot-icelli-sim`, $1.59/h). 9/9 scene checks pass; oracle baseline scores 92 % on sort_fixed, gate PASS (`eval/RESULTS.md` e-001). Setup + fixes in `docs/runbooks/verda-sim-setup.md`. **Machine hibernated Sat 14 Nov 03:48** (disk with the install kept, ~€0.05/h; resume steps in the runbook).
- **Venue look (Sat 14 Nov):** `sim/venue_look/` makes the sim resemble the real table (plywood, orange/yellow/purple objects, taped cardboard bins, black curtains). Switchable; default sim unchanged. **Open question for organisers:** the real objects are orange/yellow/purple, the docs say red/yellow/blue. Which is which?
- **LLM ideas (Sat 14 Nov):**
  - `docs/research/llm-vlm-uses.md` covers where an LLM/VLM could help: mainly an offline rung-2 instruction parser that could also fit the Gemma prize.
  - Its overnight test plan is `training/instruction_parser/EXPERIMENT.md`.
  - Aalto's "difficulty knobs" (possible harder finals: colour + shape, negation, a distractor object) are now in `docs/research/aalto-humanoid.md` §5.
- **Strategy proposal (Sat 14 Nov 12:30, Samer + Claude):** [`STRATEGY.md`](STRATEGY.md). **Not agreed yet: read it and discuss.** It proposes getting a valid submission in today, a classical core with π0.5 as an optional skill, and Verda + Gemma as tech challenges. Evidence:
  - [`research/real-data-findings.md`](research/real-data-findings.md): the drops break the speed caps; the real hand shows grip
  - [`research/aalto-discord-notes.md`](research/aalto-discord-notes.md): organiser answers; the real colours are orange / yellow / purple
- **In progress:** working on the Aalto humanoid, mostly in sim. Team split: fine-tuning (Emīls, Tiya), simulation (Marcus, Samer)
- **Next:** agree on the open items at the top of `docs/DECISIONS.md` (brief, approach, handoffs, storage, workflow, owners)
- **Blockers:** open team decisions (see `docs/DECISIONS.md`). Open questions for mentors are listed at the end of `docs/research/aalto-humanoid.md` (real-G1 teleop access, Coil Pro/suit for wrist tracking)

## Mocks & shortcuts in the demo
_Anything hardcoded or faked, so nobody is surprised at demo time._

## Gotchas
- **Aalto's real demos break the speed caps:** arms at 2–4 rad/s (cap 1), fingers up to 25 rad/s (cap 3), in every drop-2 episode. Retime them before training (`data/tools/drop_health.py`, `docs/research/real-data-findings.md`).
- **The real objects are orange / yellow / purple** (Aalto, Discord Sat 11:41) and the bins are orange. Measured in the robot's camera, the baseline's HSV ranges miss the orange objects and most of the yellow ones (purple reads as blue and is fine). Image: `docs/research/img/colour-check.jpg`.
- Challenge pages contain shared API keys and promo codes. They live in `.env.challenges` only; the docs reference them by variable name.
- Verda credits and API keys are personal (€200 per member). They need a payment card on the account (Verda: not charged, removable). It's unconfirmed whether usage beyond the €200 would be charged, so stop machines when idle.
- Oxylabs credits require buying a $500/month plan with a 100% first-month discount. If we use it, cancel the subscription after the event.
- `make mock` needs the G1 URDF that Aalto's setup script clones (not present on laptops yet); `make check` works without it.
- Aalto sim needs an **RTX-class GPU** (not A100/H100: no RT cores, cameras won't render), on-demand, with a persistent volume. The first start compiles shaders (Aalto: 5-10 min; ours took 11.5 min). Aalto quotes ~0.7x real time; **we measured 0.31x on a 10-vCPU RTX 6000 Ada** (sim process at ~5 cores, GPU at 8 %), so more CPU cores may help. Cause not confirmed.
- Aalto's bare-metal install has broken package pins (Isaac Sim, Isaac Lab/rerun) and one failing camera-view self-test on their side. Workarounds in `docs/runbooks/verda-sim-setup.md` §2b.
- `verda.com` showed a "suspended domain" page on Sat 14 Nov; the API worked at `api.datacrunch.io/v1`.
- Aalto finals PC **will have internet** (Aalto to Samer, Sat ~12:50), but a failed or slow call counts as a failure: any LLM call in the policy needs an offline fallback and must never block `act()`.
- Hardware desk (Fri 21:15): all Rokoko gloves and the one suit are checked out; no Jetson listed. 3D printers are free.
- Qualia environment closes 7 days after the event; download anything we want to keep.

## Log
- 2026-11-13 — Set up project context structure.
- 2026-11-13 — Wrote team skills summary from LinkedIn to `docs/TEAM.md`.
- 2026-11-13 — Pulled full text of all 19 main and 19 tech challenges from hackjunction.app into `docs/challenges/`.
- 2026-11-13 — Research: Aalto humanoid repo docs, all hackerpacks + hardware desk, Rokoko gloves, Jetson → `docs/research/`.
- 2026-11-13 — Set up repo structure (AGENTS.md, work-area folders, registries, runbooks, Aalto submodule, placeholder policy server).
- 2026-11-13 — Trimmed docs to facts only; team decisions moved to an open list in `docs/DECISIONS.md`.
- 2026-11-14 — Verda sim machine up; Aalto sim installed bare-metal (3 install workarounds), 9/9 scene checks, oracle baseline 92 % / gate PASS. Camera snapshots in `artifacts/sim-snap/` (local).
- 2026-11-14 — Built `sim/venue_look/` from a phone photo of the real table; 9/9 scene checks pass with it.
- 2026-11-14 — Research notes on Nemotron uses, LLM/VLM uses, Gemma prize and credits; Aalto difficulty knobs added; Gemma instruction-parser experiment planned for overnight.
- 2026-11-14 — Strategy proposal (`docs/STRATEGY.md`), real-data health check (`data/tools/drop_health.py`, `docs/research/real-data-findings.md`), Aalto Discord digest (`docs/research/aalto-discord-notes.md`).
- 2026-11-14 — Aalto answers: one deadline Sun 10:00, finals PC has internet. Real object colours measured in the robot's head camera (baseline misses orange and most yellow); strategy timeline and Gemini role updated.
