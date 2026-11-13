# sim/: Isaac simulation

**Purpose:** run Aalto's Isaac Sim scene, make it closer to reality, and produce what the training side needs: synthetic demos and a reliable way to score policies.
**Owner:** Marcus, Samer

## Inputs → Outputs
- **In:** Aalto sim image (`aalto-sim:v1`, link at kickoff / Discord); real-robot drops (for real2sim comparison).
- **Out:**
  - synthetic demo datasets, registered in [`../data/DATASETS.md`](../data/DATASETS.md)
  - domain-randomisation configs (`sim/configs/`)
  - sim scores in [`../eval/RESULTS.md`](../eval/RESULTS.md)

## How to run
- **Machine setup:** [`../docs/runbooks/verda-sim-setup.md`](../docs/runbooks/verda-sim-setup.md). You need an RTX-class GPU with ≥ 24 GB (not A100/H100), on-demand, plus a persistent volume.
- **Inside the container:**
  - `aalto sim`: first start takes 5–10 min
  - `aalto check`: expect 8 PASS
  - `aalto baseline`
  - `AALTO_DR=train aalto sim`: domain randomisation
- **Aalto's references:**
  - `third_party/aaltonomous-humanoid/aaltonomous/sim/README.md`
  - `…/cloud/QUICKSTART.md`

## First tasks (proposed)
1. Get the sim running on Verda and run `aalto baseline`. Record the time and cost per episode.
2. **Synthetic demos:** script the oracle/classical planner with domain randomisation on, and record the runs as LeRobot v3.0 with the same keys as the real drops. Privileged object poses are fine for *generating* data, but not inside the submission.
3. **Real2sim:** compare the sim camera images with Drop 0 and Drop 1 (lighting, textures, depth noise), then tune the DR ranges.

## Status
- **Now:** —
- **Next:** task 1
- **Blockers:** Verda credits claimed? Sim image download link (Discord)

## Gotchas
- The sim runs at ~0.7× real time, so a 120 s episode takes ~220 s of wall time. Run **one sim per machine**, or the 27 Hz gate fails.
- The first start compiles shaders (5–10 min). Keep the `aalto-kitcache` volume.
- Stop the sim with `aalto stop`, never `pkill -f sim_main`.
