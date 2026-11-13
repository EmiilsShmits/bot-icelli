# training/: model fine-tuning

**Purpose:** train the policy that maps `obs` (cameras, joints, instruction) to joint targets.
**Owner:** Emīls, Tiya

## Inputs → Outputs
- **In:** datasets from [`../data/DATASETS.md`](../data/DATASETS.md).
- **Out:** checkpoints on private Hugging Face repos, each with a row in [`MODELS.md`](MODELS.md). `policy/` turns them into the submission.

## The checkpoint contract
A checkpoint is the weights plus a config that `policy/` can load without guessing. The config holds:
- model type
- normalisation stats
- action horizon (chunk length)
- cameras used
- the dataset IDs it was trained on

## Candidate methods (from Aalto's starter paths)
| Method | Why | Cost |
|---|---|---|
| ACT / Diffusion Policy (LeRobot) | Small and fast; works with ~20–100 demos | Trains on one GPU |
| SmolVLA (LeRobot) | Reads the instruction, which rung 2 needs | Moderate |
| π0 / π0.5 (openpi), GR00T | Strongest priors; Aalto ships a GR00T-format copy | Fine-tuning needs 80 GB GPUs; inference fits the 32 GB finals GPU |

**Constraints the model must meet:**
- Return action **chunks** (`(k, 14)`), so the command rate stays ≥ 27 Hz.
- Each step must stay within **1 rad/s (arms) / 3 rad/s (hands)**. The sim gate allows 0 clips.

## How to run
- Training configs go in `training/configs/`, scripts in `training/` as they're written.
- Compute: Verda (€200 per team) and Modal ($100 per person).

## Status
- **Now:** —
- **Next:** pick the first method; get a training run going on Drop 0 as soon as it lands
- **Blockers:** Drop 0 (Fri evening); GPU access

## Gotchas
- The demos are scarce (~20 per rung) and **raw**. Filter them before training.
- The sim-to-real visual gap is the main risk. Use domain-randomised sim data and Drop 1 images.
