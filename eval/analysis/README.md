# eval/analysis/: what happened in each sim episode, grasp by grasp

**Purpose:** turn Aalto sim evaluation runs into tables of grasps, objects and policy decisions, so we can see what fails and decide which tools to build. **Results:** [`FINDINGS.md`](FINDINGS.md). **Owner:** Samer + Claude.

## Files
| File | What it is | Runs where |
|---|---|---|
| [`FINDINGS.md`](FINDINGS.md) | What fails and what to build next: facts and opinions kept apart | – |
| [`data/<snapshot>/`](data/) | The tables below for one set of runs (~300 KB, CSV / JSONL) | – |
| [`trace.py`](trace.py) | Run folders (+ policy logs) → the tables | where Aalto's sim is installed (needs Pinocchio + the G1 URDF), e.g. the Verda sim machine |
| [`traced_eval.py`](traced_eval.py) | Aalto's evaluator plus object positions 5×/s, the container's log, video; also adds the missing `--policy` (see below) | the sim machine |
| [`numbers.py`](numbers.py) | Every number in FINDINGS.md from a data folder | anywhere with pandas |

## How to run
```bash
# 1. New runs, on the sim machine (same arguments as `aalto.sh eval`; 2nd sim: AALTO_INSTANCE=b and --host-port 8001)
cd ~/aaltonomous-humanoid
bash aaltonomous/cloud/aalto.sh py ~/bot-icelli/eval/analysis/traced_eval.py --container bot-icelli/policy:v1.2 \
    --team v1.2 --task sort_fixed --trials 10 --seed 1000 --out ~/runs/traced --video
# 2. Tables, on the sim machine (also works on plain `aalto.sh eval` folders; --logs are optional policy logs)
PYTHONPATH=$PWD ~/miniforge3/envs/isaac/bin/python ~/bot-icelli/eval/analysis/trace.py \
    --runs ~/runs/traced/*/ --logs "$HOME/policy_logs/*.log" --out ~/analysis/out
# 3. Copy ~/analysis/out to eval/analysis/data/<YYYY-MM-DD_HHMM>/ and commit it; then, anywhere:
python eval/analysis/numbers.py eval/analysis/data/<YYYY-MM-DD_HHMM>
```

**Trap (FACT):** `aalto.sh eval --container IMAGE` **without** `--policy` silently runs Aalto's privileged oracle, not the image. Aalto's `evaluate.py` checks `--policy` (default `"oracle"`) before `--container`. Always pass `--policy ws://localhost:<host-port>` too. `trace.py` labels such runs `oracle` in `policy_actual`, whatever the folder is called.

## What trace.py reconstructs, and how
Nothing here needs the camera. It works from the evaluator's 30 Hz joint log (`episode_NNN.npz`), the episode summary (`episode_NNN.jsonl`: layout, mapping, outcomes, final poses), the policy's own log lines, and the robot's kinematics.
- **A grasp attempt:** a hand's command reaching Aalto's `closed` finger posture (`config.yaml` `hand`) for at least 4 ticks.
- **Held or empty:**
  - Measure: the largest per-joint median of |hand_q − hand_q_cmd| over ticks 15–36 after closing (thumb0 excluded).
  - An empty hand reaches the command; a held object stops a finger short.
  - Thresholds: empty < 0.004 rad, held > 0.008 rad, "unclear" in between.
  - Measured on 215 grasps: 94 empty ≤ 0.0036, 115 held ≥ 0.0081 (median 0.037), 6 between. Emīls found the same independently (e-013).
- **Slipped:** held at the lift, empty in the last 9 ticks before the hand opens.
- **Where it was released:** forward kinematics of the grasp point at opening, tested against the bins' inner footprints.
- **Where the object ended:** Aalto's own rule, from its final pose: inside a bin's inner walls **and below the 6 cm rim**, or not.
- **Which object a grasp was for:**
  - The object of the layout nearest to the planned grasp point (from the policy log, else the hand's position).
  - Prefer the colour the policy said it was picking, unless another object is 4 cm closer.
  - After a hand-over, the object is looked for where it was put down.
- **Which policy really ran (`policy_actual`):** the oracle if the trials carry its fields; otherwise the policy server's name from its log (`classical-rung1` = Aalto's baseline, `bot-icelli-v1.2` = our image).
- **Policy log matching:** the log that started within 90 s of the run and has episodes of the run's seeds. Takes Aalto's baseline log, our container's log (`container.log` from `traced_eval.py`, or a copy), or, for the oracle, its messages saved in `eval.json`.

## Tables (one row per …)
**`episodes.csv`** (episode):
- `run`, `policy_actual`, `seed`, `task`, `variant` (nominal / train …)
- `n_objects`, `n_correct`, `score`, `max_score`, `end_reason` (done / time_limit / safe_stop)
- `sim_s`, `wall_s`, `rtf`, `hold_frac` / `policy_wait_frac` (share of ticks the runner held or waited for the policy), `clipped_steps`, `command_hz`, `policy_hz_rt`
- counts: `picks`, `empty_grasps`, `slips`, `into_target_bin`, `never_attempted`, `far_cross_body_objects`
- `instruction`, `true_mapping`, `policy_mapping` (what our policy read), `policy_log`, `policy_log_file`

**`objects.csv`** (object of the layout; positions in the pelvis frame, m):
- `name` (Aalto's `obj_<colour>_<shape>_<k>`), `color`, `shape`, `x`, `y`, `yaw_deg` (start)
- `target_bin`, `bin_arm`: the arm on the bin's side
- `far_cross_body`: more than 8 cm past the robot's centre line on the far side for that arm
- `outcome`: Aalto's, correct / counter / off / wrong
- `final_where`:
  - `bin:<b>`
  - `above_rim:<b>`: over the bin's floor but above the rim, e.g. on top of another object; scores 0
  - `raised`: above the rim elsewhere, e.g. on bin walls
  - `counter`, `off`
- `moved_m`, `final_x/y/z`
- `attempts`, `attempt_results` (`|`-separated), `arms_used`, `first_attempt`
- **`loss_reason`** (empty if it scored): `never_attempted`, `never_held`, `slipped_in_carry`, `resting_above_rim`, `bounced_out_of_bin`, `off_the_counter`, `wrong_bin`, `handed_over_then_lost`, `released_outside_target_bin`, `in_hand_at_episode_end`, `unclear`
- From `traced_eval.py` runs only: `first_moved_t`, `max_z`

**`picks.csv`** (grasp attempt):
- `arm`, `t_close`, `t_open`, `hold_s`
- `object`, `object_dist_m`: planned grasp point to the object's start position (x, y), `object_color`, `shape`, `far_cross_body`
- `grasp_x/y/z`, `release_x/y/z`: FK of the grasp point at closing / opening
- `released_at`, `earlier_releases_same_bin`
- `finger_err_lift`, `finger_err_end`
- `result`: `empty_grasp`, `slipped_in_carry`, `released_in_target_bin`, `released_in_other_bin`, `released_on_counter`, `handed_over`, `unclear`
- `object_outcome`, `object_final_where`: how that object ended
- From the policy log: `planned_color`, `planned_bin`, `planned_grasp`, `planned_drop`, `ik_err_mm`, `plan_s` (planned motion time), `t_planned`

**`policy_events.csv`** (line of the policy's own log):
- `kind`:
  - `reset`, with the mapping our policy read and its source
  - `execute` (a planned pick-and-place: colour, arm, bin, grasp, drop, IK, tilt, time)
  - `home`, `done` ("nothing left to sort (N detections)"), `skip` (planner refusal), `note`, `warning`, `error`

**`events.jsonl`** (episode): one time-ordered list per episode: start, policy events, `grasp_closed`, `released`, `object_moved` (traced runs), end.

**`summary.md`**: per-run tables: sorted by shape / side / distance, grasp results, loss reasons, releases by how full the bin was.

## Limits (FACT)
- **Without `traced_eval.py` there are no object positions during the episode.** The object a grasp was for is matched from start positions, so a few attributions can be wrong, mostly after an object was pushed. Final positions and outcomes are exact (Aalto's).
- **Seed matching to policy logs** assumes one policy server per run; a server reused for several runs is fine as long as seeds differ.
- **Physics is not deterministic** (Aalto: ±10 % between runs). Compare on the same seeds and watch the counts, not just the percentages.
- The geometry comes from Aalto's nominal `scene.yaml` (and `AALTO_SCENE` if set). `AALTO_DR=train` doesn't move the bins or the robot, so the bin geometry still holds.
- **Start positions in DR runs can be up to ~5 mm and 5° off.** The episode summary's layout is the layout card, and DR places each object that far off it (`aaltonomous/sim/dr/train.yaml`, `pose`). `object_dist_m` and `moved_m` include that.
