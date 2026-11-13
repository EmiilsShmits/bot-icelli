# sim/: simulation

**Purpose:** _to be agreed._
**Owner:** Marcus, Samer

## Inputs → Outputs
- **In:** _to be agreed._
- **Out:** _to be agreed._

## How to run
- **Machine setup:** [`../docs/runbooks/verda-sim-setup.md`](../docs/runbooks/verda-sim-setup.md).
- **Inside the sim container:**
  - `aalto sim`
  - `aalto check`: expect 8 PASS
  - `aalto baseline`
  - `AALTO_DR=train aalto sim`: domain randomisation
- **Aalto's references:**
  - `third_party/aaltonomous-humanoid/aaltonomous/sim/README.md`
  - `…/cloud/QUICKSTART.md`

## Status
- **Now:** —
- **Next:** —
- **Blockers:** —

## Facts and gotchas (from Aalto's docs)
- **GPU:** needs an RTX-class GPU with ≥ 24 GB (RTX Pro 6000 / L40S / A6000 / 4090 / 5090). **A100/H100 can't render the cameras.** Use on-demand instances with a persistent volume.
- **Speed:** the sim runs at ~0.7× real time, so a 120 s episode takes ~220 s of wall time. More than one sim per machine slows it further and can fail the 27 Hz gate.
- **First start** compiles shaders (5–10 min). Keep the `aalto-kitcache` volume.
- **Privileged object poses** (scene service) are allowed for training and data generation, **not** inside a submission.
- **Stopping:** use `aalto stop`, never `pkill -f sim_main`.
