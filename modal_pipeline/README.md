# modal_pipeline/: sim data → π0.5 training → sim evaluation, all on Modal

**Purpose:** an end-to-end pipeline that runs entirely on Modal (no machine to keep alive): Aalto's Isaac sim,
recording oracle demonstrations, fine-tuning π0.5 (LeRobot 0.7.0), and scoring checkpoints with Aalto's evaluator.
**Owner:** Marcus

Full write-up of what was done, what was learned and what is open: [`TEAM_HANDOVER.md`](TEAM_HANDOVER.md).
Everything found wrong or unclear in Aalto's material: [`ORGANIZER_ISSUES.md`](ORGANIZER_ISSUES.md).

## Inputs → Outputs
- **In:** Aalto's repo (`../third_party/aaltonomous-humanoid`, found automatically), a Modal workspace with the
  secret `huggingface` (`HF_TOKEN` with access to `google/paligemma-3b-pt-224`).
- **Out (Modal volumes, nothing large in git):**
  - `aalto-data`: raw oracle recordings (`sim_raw/`) and LeRobot v3.0 datasets (`raw/`, `train/`), same feature
    names as Aalto's real drops, so they merge.
  - `aalto-runs`: checkpoints.
  - `aalto-sim-out`: evaluator results and head-camera videos.

## How to run
From this folder, with the `modal` CLI logged in:

```bash
modal run sim/modal_sim.py --action baseline --trials 3                 # Aalto's oracle in the sim
modal run --detach sim/modal_sim.py --action datagen --name sim_fixed_v4 --shards 8 --episodes 16 --seed 400000 --dr mix --background
modal run training/modal_pi05.py --action prepare --src sim_fixed_v4 --name sim_fixed_v4
modal run --detach training/modal_pi05.py --action train --mode full --dataset sim_fixed_v4 --run my-run --steps 6000 --save-freq 1000 --gpu B200 --workers 40 --background
modal run --detach sim/modal_sim.py --action eval-model --ckpt my-run/checkpoints/003000 --trials 3 --tag my-eval --background
mkdir -p sim_out && modal volume get aalto-sim-out my-eval sim_out      # scores (eval.json) + videos
modal run training/openloop_check.py --ckpt my-run/checkpoints/003000 --dataset sim_fixed_v4
```

Every script's docstring lists its other options. More commands and what each file does: `TEAM_HANDOVER.md` §2 and §4.

## Status
- **Now (Sat 14 Nov, 14:20):**
  - Sim on Modal: 9/9 scene checks, oracle baseline 11/12. Over 125 recorded oracle episodes: cubes 97 %,
    cylinders 91 %, triangular prisms 35 %.
  - Datasets: `sim_fixed_v2` (125 episodes, 57 min); `sim_fixed_v3` (about 126 more) recording.
  - Best checkpoint so far in the sim (rung 1, 3 episodes): 3 of 12 objects, mean score +0.33, gate PASS
    (`pi05-sim-v2` step 5,000). Whole-model fine-tune `pi05-sim-v2-full` is training (6,000 steps, done about 15:35).
  - `submission/` is a π0.5 policy server (background inference, local copy of the safety filter so the runner
    never clips) plus a Dockerfile that has **never been built**.
  - `agent/AI_STUDIO_PROMPT.md`: prompt for designing a Gemini agent that calls skills split out of the oracle.
- **Next:** merge v2 + v3 and keep training; per-object prompts; decide whether `submission/` or `../policy/` is
  the image we ship.
- **Blockers:** none. Grasps still miss by a centimetre or two and red objects land in the centre bin.

## Gotchas
- Use `--detach` **and** `--background` for anything long; without `--background` the job is cancelled when the
  laptop that started it sleeps.
- The sim needs an L40S (RT cores). It is CPU-bound (GPU at 11 %), 0.3× real time on Modal.
- Training: use the B200. `--mode full` (whole model) 1.46 s/step; `--mode expert --no-grad-ckpt` 0.58 s/step.
- `--mode expert` freezes the language model, and this π0.5 reads joint angles as text in the prompt, so prefer
  `--mode full` once the action head has converged.
- The dataset must be cut with `--mode segments` (default): successful pick-and-places joined back to back, no
  waiting at home. One episode per pick-and-place taught the model to stand still.
- `modal volume get` fails if the destination folder does not exist.
- The workspace limit is 10 GPUs; extra jobs queue.
- `training/openloop_check.py` and `submission/Dockerfile` need the G1 URDF inside Aalto's repo
  (`third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf` there, fetched by Aalto's setup script).
- `submission/Dockerfile` expects Aalto's repo as `aaltonomous-humanoid/` next to `submission/` in the build
  context; in this repo copy or link `../third_party/aaltonomous-humanoid` there first.
