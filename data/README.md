# data/: datasets (real + synthetic)

**Purpose:** get every dataset into one format, record where it lives, and make clear what it's good for. This is the handoff between `sim/` and `training/`.
**Owner:** shared. Whoever makes a dataset registers it.

## Inputs → Outputs
- **In:**
  - Aalto real-robot drops (Hugging Face, links on Discord): Drop 0 (Fri evening, teleop demos), Drop 1 (Sat: venue lighting, empty-scene RGB-D, depth noise)
  - synthetic demos from `sim/`
  - public G1 Dex3 sets (see `docs/research/aalto-humanoid.md` §8)
- **Out:** LeRobot v3.0 datasets on private Hugging Face repos, each with a row in [`DATASETS.md`](DATASETS.md).

## The dataset contract
- **Format:** LeRobot v3.0, same keys as Aalto's drops.
  - `observation.state` = 28 values (`arm_q` 14 + `hand_q` 14)
  - `action` = 28 **absolute** joint targets at 30 Hz
  - images `observation.images.{head_rgb, head_depth, left_wrist_rgb, right_wrist_rgb}`
  - `task` = the instruction
- **Aalto also ships a GR00T copy** (LeRobot v2.1, RGB only). Use it as-is for GR00T fine-tuning.
- **The drops are raw**: they include failed and messy episodes. Filter on `success`, `notes` and `warnings` in `meta/aalto_episodes.jsonl`, and record the filter you used in `DATASETS.md`.

## How to run
- Download and convert scripts go here as they're written.
- Storage:
  - Verda volume `/data/datasets/<id>/`
  - Hugging Face `$HF_NAMESPACE/icelli-<id>` (private)
  - local copies in `artifacts/datasets/`

## Status
- **Now:** —
- **Next:** download Drop 0 when it's posted; register it as `ds-001-drop0-raw`
- **Blockers:** Hugging Face team account/org (needed for private repos)

## Gotchas
- Never commit data. Parquet, mp4 and npz files are git-ignored.
- Some drops may be licensed for Junction participants only, so keep the Hugging Face repos private.
