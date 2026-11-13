# training/: model fine-tuning

**Purpose:** _to be agreed._
**Owner:** Emīls, Tiya

## Inputs → Outputs
- **In:** _to be agreed._
- **Out:** _to be agreed._

## How to run
_Nothing yet._

## Status
- **Now:** —
- **Next:** —
- **Blockers:** —

## Facts from Aalto's docs
- **Method options** they list (any method is allowed): `third_party/aaltonomous-humanoid/aaltonomous/docs/participants/STARTER_PATHS.md`.
- **Real demos:**
  - ~20 per rung, **raw** (failed and messy episodes included; labels in `meta/aalto_episodes.jsonl`)
  - LeRobot v3.0, plus a GR00T-format copy (RGB only)
- **Fine-tuning compute:** large VLAs (π0 / π0.5, GR00T) need 80 GB GPUs to fine-tune. Inference must fit the 32 GB RTX 5090 at the finals.
- **What a submitted policy must output:** absolute joint targets at 30 Hz, changing by at most 1 rad/s (arms) / 3 rad/s (hands), with ≥ 27 commands/s (chunks count per tick).
- **Compute credits:** see `docs/research/apis-and-credits.md`.
