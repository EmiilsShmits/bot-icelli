# sim/: simulation

**Purpose:** _to be agreed._
**Owner:** Marcus, Samer

## Inputs → Outputs
- **In:** _to be agreed._
- **Out:** _to be agreed._

## How to run
- **Machine setup:** [`../docs/runbooks/verda-sim-setup.md`](../docs/runbooks/verda-sim-setup.md). On a fresh Verda machine, [`install_bare_metal.sh`](install_bare_metal.sh) does the whole bare-metal install with our fixes and starts the sim (11 min on an RTX PRO 6000).
- **Inside the sim container:**
  - `aalto sim`
  - `aalto check`: expect 9 PASS (Aalto's quickstart says 8)
  - `aalto baseline`
  - `AALTO_DR=train aalto sim`: domain randomisation
- **Venue look** (sim that resembles the real table): [`venue_look/README.md`](venue_look/README.md). Recreate it from scratch: [`docs/runbooks/venue-sim.md`](../docs/runbooks/venue-sim.md).
- **Aalto's references:**
  - `third_party/aaltonomous-humanoid/aaltonomous/sim/README.md`
  - `…/cloud/QUICKSTART.md`

## Status
- **Now:** Aalto sim runs bare-metal on Verda (`bot-icelli-sim`, Emīls's account). Set up on an RTX 6000 Ada, hibernated, and **resumed Sat 14 Nov at noon from the kept disk (volume `bot-icelli-os`) on a spot RTX PRO 6000** (30 vCPU, €1.28/h); a backup copy of the disk exists (`bot-icelli-os-backup`). It bills until hibernated again, and Verda can take a spot machine away at any time. 9/9 scene checks; oracle baseline 92 % with Aalto's scene, 88 % with the venue look and 71 % with the venue look plus scattered layouts (gate PASS in all three). How: `docs/runbooks/verda-sim-setup.md`. The switchable venue look in `venue_look/` is fitted to Aalto's real head-camera video (camera angle, bins, lighting). The wrist cameras are an estimate of the real mount (direction fitted to real frames, position and lens guessed); details and remaining differences in `venue_look/README.md`.
- **Second machine (Sat 14 Nov 15:45, Samer's account):** `samer-v1-sim`, spot RTX PRO 6000 in FIN-03, €1.28/h, set up from scratch with `install_bare_metal.sh` in 11 min (9/9 checks after the start-up fix). Runs the v1 evals (`eval/README.md`). No disk copy: Verda clones only shut-down machines, and the script reinstalls in 11 min.
- **Next:** —
- **Blockers:** sim speed is 0.52× real time on the RTX PRO 6000 machine and 0.31× on the RTX 6000 Ada one (Aalto quotes ~0.7×).

## Facts and gotchas (from Aalto's docs)
- **GPU:** needs an RTX-class GPU with ≥ 24 GB (RTX Pro 6000 / L40S / A6000 / 4090 / 5090). **A100/H100 can't render the cameras.** Use on-demand instances with a persistent volume.
- **Speed:** Aalto quotes ~0.7× real time (a 120 s episode takes ~220 s of wall time); we measured 0.31× on a 10-vCPU RTX 6000 Ada machine and 0.52× on a 30-vCPU RTX PRO 6000 machine. More than one sim per machine slows it further and can fail the 27 Hz gate.
- **First start** compiles shaders (5–10 min). Keep the `aalto-kitcache` volume.
- **Privileged object poses** (scene service) are allowed for training and data generation, **not** inside a submission.
- **Stopping:** use `aalto stop`, never `pkill -f sim_main`.
