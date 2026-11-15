# policy/decision_oracle: Aalto's oracle as motion functions + a Gemini Decision 1 chooser

**Purpose:** make Aalto's scripted oracle more general by splitting its hidden choices into motion functions that take parameters. Gemini Decision 1 (or a random chooser) then picks those parameters from options the planner has already checked. We run both in the Aalto Isaac sim to find out which movements work.

Two perception modes:
- `--perception privileged` (default): exact object poses from the sim, as Aalto's oracle. Exploration and data generation only, **not a submission**.
- `--perception camera`: head RGB-D only (`camera.py`). The sim's poses are then read **only to log the truth** next to what the camera saw; nothing in the plan uses them.
**Owner:** Emīls (built with Claude, Sat 14 Nov)

## Summary (read this first)
- **What it is.** Aalto's oracle decides everything inside one function. Here the same planner is called through motion functions with explicit parameters (object, arm, grasp, route, drop spot, retry). At every look we list the options the planner has checked, and a *chooser* picks one. Choosers: Aalto's own rule, Gemini Decision 1, random, and "prefer a face grasp".
- **What Decision 1 sees.** The head-camera image, a short text describing the scene, and one multiple-choice question per parameter with only feasible answers. It never produces positions or joint targets; the planner does that. With `--perception camera` the object positions come from the head RGB-D image, not from the sim.
- **Result so far.** Decision 1 as chooser is no better than Aalto's rule (23/27 against 22/27 on the same seeds; its confidence sits near 0.5). The useful output is the per-movement log: it shows **where the oracle fails**: triangles picked with the stock claw grasp hold in 1 of 15 picks.
- **Camera-only perception works in sim.** 2.5 mm median position error against true poses and the same score as exact poses on the two seeds tried. Not tested on real depth.
- **Not a submission by itself.** It runs in-process inside Aalto's evaluator and imports Aalto's planner. **v1.5 (`policy/policies/oracle_v15.py`) packs the camera + upgrades into a policy server**, using `upgrades_v15.py` from here: sort_fixed 23/27 with either arm anywhere (e-030), 20/27 with same-side arms (e-029), sort_language 22/28 (e-031).
- **Oracle upgrades (Sat ~17:00): written, not yet measured in sim.** `upgrades.py` (a separate file; the original code is unchanged) adds a per-object failure memory, face grasps first and a finger-angle grasp check (section below). The offline test passes; the sim runs are queued.
- **Still running (Sat ~17:00):** camera mode on all 6 seeds (in progress), then the memory chooser + grasp check (2-seed smoke test, sort_fixed, sort_language, sort_fixed with camera), camera on sort_language, the random chooser, camera + Decision. Rows get added to `eval/RESULTS.md` as they finish.

## Inputs → Outputs
- **In:** a running Aalto sim (scene service :55580, head RGB-D :55560) and `GEMINI_API_KEY` (env var, or the file `/root/.decision_key` on the sim machine) for the Decision chooser.
- **Out:** Aalto's `eval.json` per run (scores, outcomes, safety, rates) plus our `decisions.jsonl`: one line per look (feasible options, planner reasons, Decision questions/answers/latency/fallback, chosen option), per executed pick, and per pick outcome seen at the next look.

## Files
| File | What |
|---|---|
| `motions.py` | The motion functions. `plan_direct(det, arm, grasp, bin, …, drop)`, `plan_relay`, `drop_ok`, `face_options`, `target_bin`; `OptionEnumerator.feasible_options()` lists only planner-checked options, the oracle's own choice first |
| `chooser.py` | `DefaultChooser` (Aalto's rule), `DecisionChooser` (one createDecision call per look, 2 s timeout, default on any failure), `RandomChooser` (seeded, explores), `PreferFaceChooser` (the oracle's object, but a face grasp whenever one is planned; no API) |
| `policy.py` | `DecisionOraclePolicy(OraclePolicy)`: replaces only `_plan_next`; keeps Aalto's look thread, prefetch and holds. Logs decisions and outcomes |
| `camera.py` | Camera perception: fits the head camera pose from the depth image (table plane + bin walls), finds objects by colour and height, gets shape and yaw from the top face outline |
| `labels.py` | Optional Decision 1 labels for single-object crops (colour, shape, "other"); geometry stays the fallback |
| `test_camera.py` | Scores camera perception against true poses on saved frames |
| `run_eval.py` | `aaltonomous.sim.evaluate` with our policy swapped in (`--chooser aalto|default|decision|random|prefer_face`, `--perception privileged|camera`, `--labels off|log|fuse`) |
| `analyze.py` | Tables per shape / arm / grasp / route / drop spot, latency, fallbacks, planner rejections |
| `upgrades.py` | **All oracle upgrades in one separate file**, as subclasses of the files above (which stay as first pushed): `MemoryChooser`, `MemoryEnumerator`, `TrackingCamera`, `UpgradedOraclePolicy`, plus its own runner, self-test and analysis. Delete this file and nothing else changes |
| `upgrades_v15.py` | **v1.5 upgrades**, again a separate file of subclasses: same-side arms (`SidedPlanner`: each arm grasps and drops only on its half of the table, cross-side objects go through the relay on the centre line), the ridge grasp for lying triangles (`RidgeCamera` gives the ridge direction, the planner pinches across the two triangular end faces), `TipChecker` (optional Gemini check of the camera's "lying" label: Decision 1 or Hydrogen on the crop; off by default), `V15Chooser`, `V15OraclePolicy`. Runs in the sim like `upgrades.py` (`--sides strict|off`) and is the core of the v1.5 policy server (`policy/policies/oracle_v15.py`) |
| `upgrades_v16.py` + `labels_v16.py` | **v1.6** (policy server `policy/policies/oracle_v16.py`), subclasses again: `AnyColourCamera` (v1.5's camera + saturated blobs at object height that no HSV range took; each detection keeps its top-face points), `CropLabelerV16` (Decision colour + shape win when ≥ 0.6 sure, "tipped" from depth always stands, a leftover blob needs colour ≥ 0.85 and a known shape), `V16OraclePolicy` (Decision instruction answer at the first look, `policy/instruction_d1.py`). No key: exactly v1.5 |
| `boxes_v16.py` | **The boxes and the shape lid measured from head depth** (opt-in `V16_BOXES=find|lid`, v1.6). `find_boxes`: near wall line, wall height, far edge, side walls and gaps → each box's centre and size, nothing taken from `scene.yaml` but the box size as a prior. `find_lid`: which box carries Aalto's printed lid, its turn, which side is up, and the centre of each hole. `enable(cam)` lets the drops follow the boxes found. Tests: `policy/tests/test_boxes_v16.py`; numbers: `eval/analysis/real_depth/README.md` |
| `tri_v16.py` | **Standing-triangle grasp** (opt-in `V16_TRI=mid`, v1.6). `TriPlanner` (on top of `CrowdPlanner`): a standing triangle is planned with the grasp point midway between the closed fingertips and the thumb (palm x 0.083 m instead of Aalto's 0.099), and this hand's finger angles first (left 30°, 90°, 15°, 75° from the apex; right mirrored), labelled `face<k>p<angle>`. Other shapes unchanged. Why and the MuJoCo numbers: `eval/analysis/grasps/README.md` §4 |
| `ridge_sweep.py`, `modal_runs/ridge_summary.py`, `viz_ridge.py` | Lying-prism grasp tests: one prism per sim episode with a forced arm and a hand shift (`V15_RIDGE_SHIFT`), traced through the pick; summary table per run and arm; offline pictures of the planned ridge grasp |
| `test_labels_real.py` | No sim: v1.5's HSV classes vs Decision crop labels on Aalto's real head frames (`artifacts/real_frames/`), against hand labels. `LABELER=v15|v16` picks the colour wording |
| `test_tipcheck.py` | Offline test of the lying-block handling on saved head frames with true poses: how often the camera's "tipped" is right, the ridge direction error, and what the Gemini check answers. `PYTHONPATH=third_party/aaltonomous-humanoid:policy python -m decision_oracle.test_tipcheck --frames artifacts/monitor/sim_frames --models d1,hydrogen` (needs `GEMINI_API_KEY`) |
| `COMPARISON_ADK.md` | **v1.5 vs Marcus's ADK agent** (Gemini calling oracle skills): how each decides, network and image, scores on the same seeds where they exist, what to take from each |
| `modal_runs/` | v1.5 on Modal: `launch.sh TAG TASK SEED [args]` (detached, retries Modal's app limit), `fetch.sh TAG` (results + H.264 videos into `artifacts/eval/v15/`), `summarize.py TAG… / --group PREFIX…` |
| `video.py` | Films every scored episode: head camera on top, both wrist cameras below, time and instruction on the frame (H.264). Wraps `upgrades` / `run_eval`: `python -m decision_oracle.video upgrades --perception camera ...` |
| `monitor_rules.py` | No sim, no API: joins the decision logs with the finger angles in `episode_*.npz`. Grasp check from `hand_q`, what retries repeated, rules that flag a pick before it runs; `--table` prints a pick table + prompt for a large model |
| `monitor_probe.py` | No sim: asks Decision 1, Robotics-ER 2 and Hydrogen monitoring questions on saved head frames with true poses (block in the hand? gone from the table? another block moved? tipped? counts) and scores them. Results: [`docs/research/model-monitor-oracle.md`](../../docs/research/model-monitor-oracle.md) |
| `test_offline.py` | No sim: fake scene service from random layouts; default chooser = Aalto's choice, every option passes the checks |

## The parameters (what Aalto's oracle hard-codes)
| Parameter | Aalto's rule | Options here |
|---|---|---|
| Object | nearest its bin first | every object with at least one checked plan |
| Arm | the bin's side (centre bin: the object's side), other arm on failure (`grasp.arm: by_y`) | left / right where planned |
| Grasp | fingers along a face nearest the hand's natural direction (`FACE_ALIGN`, triangles `TRI_PHI_DEG`=105), stock finger hints as fallback | `face<k>` (each face within 75°), `stock`, triangles also `face<k>p75` / `face<k>p90` |
| Route | direct; relay (put down near the centre, other arm finishes) only when no object has a direct plan | direct / relay |
| Bin | from the mapping (`scene.resolve_bin`) | fixed by the instruction |
| Drop spot | `DROP_OFFSETS` cycled by how many objects are already in the bin | the 5 offsets that pass a cheap IK check |
| Retry / skip | retry up to 2× per **table position** (a pushed object counts as new) | `retry` / `skip`, asked when a picked object is back on the table. `upgrades.py`: up to 4 failures per **object**, a different arm or grasp each time |

## How it decides (never blocks `act()`)
- The look runs in Aalto's planning thread. That is the first look of an episode, or the prefetch while the previous pick executes. Meanwhile `act()` returns holds, as in Aalto's oracle.
- The oracle's own choice is planned first, so a default always exists. Then alternatives are planned until a budget runs out: 8 s in a prefetch, 3 s in a blocking look.
- Decision 1 gets one call per look: the head-camera JPEG, a short scene text, and one `choice` question per parameter. Each question's criteria are only the feasible values plus `default`; questions with a single feasible value are skipped. A timeout (2 s), an HTTP error or a missing answer falls back to the default. Answers are matched to an option in the order object → arm → grasp → route. A non-default drop spot means one more plan; if that plan fails, the default spot is kept.

## Oracle upgrades (`upgrades.py`, run with `python -m decision_oracle.upgrades`)
Everything in this section lives in `upgrades.py` only. The original files are not modified, so `run_eval.py` behaves as before. Three changes to how the oracle picks, all rules (no API call):
1. **Failure memory.** Every failed pick is stored per object as (arm, grasp). The memory chooser never repeats a pair that failed on that object while another planner-checked option exists, and sorts objects that have not failed yet first. Retries are counted per object (4 failures, `--max-tries`), not per table position as in Aalto's code. In camera mode the object keeps its name after a failed pick if it is found within 10 cm of where it was.
2. **Face grasp first.** For cubes and triangles: Aalto's face grasp, then the alternative triangle angles (75°, 90°), then the stock claw. The option search spends its time budget on the object that will be picked.
3. **Grasp check from the finger angles.** At the end of the lift the policy compares the measured finger angles (`obs["hand_q"]`) with the commanded closed posture. A held block keeps the fingers 0.021–0.100 rad short of it; an empty hand reaches it (0.000–0.010 rad). Measured on 56 logged sim picks: 29 of 29 held and 27 of 27 empty told apart. Below 0.012 rad the pick is aborted: the hand opens, the arm goes straight home (a joint-space move, the reverse of the approach) and the robot looks again. This skips the empty carry to the bin and records the failure at once. The threshold is a sim value: real finger encoders need their own.

## Camera perception (`--perception camera`)
1. **Head camera pose.** Aalto's `calibration.yaml` pose is a URDF default; the real camera and our venue-look sim point about 10° further down. `fit_head_pose` re-fits it from one depth image at the first look of an episode: the table plane gives tilt, roll and height; the bin walls (known 21 cm boxes) give x, y and yaw. No markers needed.
   - **`V16_CALIB=hands` (v1.6 only, off by default, Sun 15 Nov):** x, y and yaw come from the robot's own arms instead of the bins (`handeye.py`).
     - How: the URDF forward kinematics of the recorded arm and hand joints give a surface model of the elbows, wrists and Dex3 hands (`hand_model.npz`, built from Unitree's meshes). Point-to-plane ICP fits it to the head depth points above the table.
     - Then `locate_bins` finds the three bins in that frame (the set, then each bin within ±2.5 cm) and writes their centres into `scene.cfg` for the episode.
     - Why: the bin-wall fit trusts `scene.yaml`, so a bin shifted 2 cm moves the camera estimate and every object with it. MuJoCo: bins-only shift 33 % vs nominal 63 % (e-053).
     - Accuracy in MuJoCo (6 seeds × 3 randomisation modes): object positions within 1.5–3.2 mm, bins found within 2.5–9 mm.
     - MuJoCo, paired (e-070): it triples the score when the bins are shifted (17 % → 56 %), but loses ~15 points in the nominal scene (69 % → 53 %): a ~2 mm bias. Superseded by `lean`.
   - **`V16_CALIB=lean` (v1.6 only, off by default, Sun 15 Nov): perception as `bins`, IK moved into the camera's frame.**
     - **Why:** Aalto's real frames say the torso leans and the camera sits within ~2° of its calibration (`docs/CONTEXT.md` 4.1). The levelled fit then reports objects in a table frame that the arms are not in: ~5–6 cm off at a 6–7° lean in MuJoCo, mostly in height. The same mismatch appears when the bins or the robot-to-table distance differ from `scene.yaml` (1–3.5 cm).
     - **How:**
       - `HandEye.fit_pose` finds the camera's full pose relative to the arms: 6-DOF point-to-plane ICP over the depth points off the table, from 45 starts, best kept. It is never levelled.
       - Then base = T_table · inv(T_arm). `handeye.set_kin_base` moves the planners' Pinocchio model (`pl.kin` of the planner and the relay) by it, so FK, Jacobians, IK targets and "top-down" all live in the frame the camera reports in.
       - Deadband: if the base moves the work area < 4 mm and turns < 0.5°, the model is left alone, so the nominal sim is unchanged.
       - Reset restores the model each episode.
     - **Reach error in MuJoCo** (`eval/analysis/real_hands/`-style geometry check, 20 scenes): leaning robot 35–65 mm → 0.8–1.4 mm; shifted bins 9–35 mm → 0.8–1.1 mm; nominal unchanged (1.4–2.4 mm, deadband). Paired episodes (e-071): nominal 75 % = 75 % (identical), shifted bins 22 % → 58 %, leaning robot 49 % → 56 %, all randomised 21 % → 49 %.
     - **Not checked:** real head depth on the black Dex3 hands (the drops have no depth). If the arm fit fails, the policy logs it and keeps the levelled frame (today's behaviour).
   - **`V16_BOXES=find` (v1.6 only, off by default, Sun 15 Nov ~02:50): the boxes are measured, not assumed** (`boxes_v16.py`).
     - **Why:** every fit above takes the boxes' spacing from `scene.yaml` (26 cm centre to centre). On Aalto's real depth (drop 3) the boxes are 24 cm apart, so after the bin-wall fit the middle box stands 2.1 cm and the right box 4.2 cm from where the drops aim. Aalto also said they will glue the boxes ~7 cm closer to the robot.
     - **How:** after the camera fit, on the same depth image, seen from above at wall height: the near wall is one line across the three boxes (RANSAC), its top is the wall height, then the far edge, then along the row each box is an interval with a wall at both ends and nothing in the gap to its neighbour. Each box gets its own centre, written into `scene.cfg` for the episode (as `hands` does) and put back on reset.
     - **What it still takes from `scene.yaml`:** the box size (21 cm, ± 2.5 cm allowed) and that there are three boxes named by position. Not their place, spacing, gaps or wall height.
     - **Checked** (`eval/analysis/real_depth/README.md`):
       - real drop-3 frames 15/15: walls 7.1 cm, gaps 2.8 and 2.6 cm, boxes 21.2 cm wide, each centre the same within ± 4 mm over the frames;
       - venue-look sim frames: found on 107/115, within 3 mm of the sim's boxes where found. On the other 8 an arm is over the boxes; it says "not measured" and the bins stay as they were;
       - 0.3 s, once per episode, in the look thread.
     - **`V16_BOXES=lid`** also looks for the shape lid and keeps the result in `cam.lid`: the box it lies on, the plate height, its quarter turn, which side is up, and each hole's centre and direction. The plate is a flat patch at one height on a box; a hole is where the camera sees through that plane. Both are matched against the lid's outline (`real_lid()`, from Aalto's `lid_shape_holes_200mm.stl`; `scene_lid()` gives the sim's lid in the same form). On rendered depth of the real STL (MuJoCo, real camera pose, 1.7 mm noise, holes at depth edges): right turn and side in 59/64 poses and never a wrong one reported; hole centres within 2.4 mm (median 1.2). The 5 misses are lids on the right box, half out of view.
     - **Not checked:** no episode has run with either setting (no sim score). No real frame with the lid exists, and real stereo depth may fill small holes in, which the rendered depth does not show. Nothing uses `cam.lid` yet: there is no shape-putting movement.
2. **Objects.** Pixels with an object colour (HSV ranges covering sim red/yellow/blue and real orange/yellow/purple) that lie at object height above the table and outside the bins. One blob is one object; the highest 6 mm of it is the top face.
3. **Shape and yaw** from the top face's outline seen from above: how well a rectangle, a circle and a triangle fit. A ridge instead of a face means a block lying on its side (`tipped`): stock grasp only.
4. **Names** are kept across looks by position (same colour within 3 cm).
5. **Prefetch** (planning the next object while the arm moves) reuses the last look's detections, because the arm crosses the view. The next look re-detects and replans if the object moved more than 1 cm.
6. **Stale frames.** The first frames of a sim episode still show the previous scene, so the first look waits until 1.0 s; every look waits 0.4 s after the arm is home.
7. **Decision 1 crop labels** (`--labels log|fuse`): one call per new object, in parallel, 2.5 s deadline, cached per object. `fuse` lets a confident Decision label fix a shape that geometry found a close call. Geometry alone decides `tipped`.

## How to run (sim machine `bot-icelli-sim`, bare metal)
```bash
scp -r policy/decision_oracle root@<ip>:/root/        # from the laptop
# on the machine, in tmux; the sim already runs with the venue look
cd /root/aaltonomous-humanoid && source /root/venue_look/venue_env.sh
export PYTHONPATH=/root/aaltonomous-humanoid:/root
P=/root/miniforge3/envs/isaac/bin/python
$P -m decision_oracle.test_offline --layouts 8                  # no sim needed
$P -m decision_oracle.run_eval --chooser decision --task sort_fixed --trials 6 --seed 1000 --out /root/runs_do
$P -m decision_oracle.run_eval --chooser aalto    --task sort_fixed --trials 6 --seed 1000 --out /root/runs_do
$P -m decision_oracle.run_eval --chooser default --perception camera --labels fuse --task sort_fixed --trials 6 --seed 1000 --out /root/runs_do
$P -m decision_oracle.upgrades --task sort_fixed --trials 6 --seed 1000 --out /root/runs_do   # upgrades: memory chooser + grasp check
$P -m decision_oracle.upgrades --selftest 6                     # upgrades, no sim needed
$P -m decision_oracle.upgrades --analyze <decisions.jsonl>      # grasp check vs outcome, picks by try number
$P -m decision_oracle.test_camera <frames dir>                  # camera perception vs true poses on saved frames
python3 policy/decision_oracle/analyze.py <run_dir>=<decisions.jsonl>    # laptop, after copying the runs back
```
Don't pass `--no-cameras`: the Decision chooser needs the head image.

## Status
- **Standing-triangle grasp (Sun 15 Nov, Emīls + Claude): `tri_v16.py`, opt-in `V16_TRI=mid`, off by default.**
  - At Aalto's grasp point the closed thumb stops ~11 mm short of a standing prism and the index finger pushes it away (MuJoCo bench `sim/mujoco/tri_bench.py`: 17 % held with perception noise). Midpoint grasp point + per-hand angles: 47 % over all angles, 61–76 % at the angles now tried first.
  - Unit tests: `policy/tests/test_v16.py` `TestTriMid`. v1.5 is unchanged: the shared `motions.grasp_variants` only changes when a policy passes `tri_phis`, which only v1.6 with `V16_TRI=mid` does.
  - **MuJoCo paired run (e-072, 72 pairs):** triangle grasps held 27 % → 57 % per attempt, all objects sorted 83 % → 88 %, gate PASS.
  - **Next:** one Isaac run before turning it on in an image.
- **Box and lid finder (Sun 15 Nov, ~02:50, Emīls + Claude): `boxes_v16.py`, opt-in `V16_BOXES=find|lid`, off by default.**
  - Measures the three boxes from head depth instead of taking them from `scene.yaml`: real drop-3 frames 15/15, sim frames 107/115 (within 3 mm where found). Finds Aalto's printed lid and its holes on rendered depth within 2.4 mm. Details under "Camera perception" above.
  - **Next:** one sim run with `V16_BOXES=find` against the default (nominal and shifted bins); the first real frame with the lid; a shape-putting movement that uses `cam.lid`.
- **v1.6 (Sat 14 Nov, ~22:00, Emīls + Claude): Decision 1 for colour, shape and the instruction, v1.5 as the fallback.**
  - **Sim frames** (115 saved venue-look frames, no API): with the leftover pass on, the HSV detections are identical to v1.5's on every frame and no leftover blob appears. With one object per frame recoloured green (no HSV class), the new camera finds it in 19/19 frames; v1.5 misses all 19.
  - **Real head frames** (`test_labels_real.py`: 81 single-block crops from 31 drop-2 frames, hand-labelled; 83 crops of hands, arm or glare):
    - colour: HSV 79/81 right, Decision 74/81 right with 0 wrong (7 unsure), fused 79/81. The 2 HSV misses were part-hidden blocks;
    - Decision shape: 51/54 (3 lying prisms called cube; the depth "tipped" overrides those);
    - the first colour wording called pale real yellow "other" (67/81) and gave a known colour to 36 of the 83 non-block crops (mostly arm reflections as "blue"). The v1.6 wording halves that to 23, and the leftover rule (colour ≥ 0.85 plus a known shape) would keep 3 of 83. Those 3 would also have to pass the depth filters (object height, top-face size).
    - So on real frames HSV already gets the colours right. What Decision adds is a second opinion when HSV misses, plus the shape. The leftover pass is a guard for colours outside the ranges, which these frames did not contain.
  - **Orange called "yellow" in the real-colour sim (e-046), Sat ~23:30:** the sim lights the venue orange to a pale peach (crops saved with `V16_DUMP_CROPS`); the colour wording "pale, light … yellow" pulled it to yellow (5/5 orange crops, 4 of them ≥ 0.6). New wording (pale orange / peach / tan under red, not under yellow): 5/5 orange there, real frames 75/81 right with 0 wrong (was 74/81, 0 wrong). The re-run of e-046 with it is pending.
  - **Lying-prism grasp fix (v1.6 only, `upgrades_v15.SidedPlanner.ridge_shift` / `ridge_first`, set by `V16OraclePolicy`):** at Aalto's grasp point the closed thumb stops ~15 mm short of the prism's near end face, so the fingers must sweep it back (the right hand held 0/7). `ridge_sweep.py` (one lying prism per episode, arm forced, 12 picks per setting): ridge held 3/6 with no shift, **6/7 with the hand 18 mm further along the ridge** (right 3/4), worse with ±6 mm sideways. Plus a ridge plan on either arm before the stock claw (offline: 31 vs 28 ridge plans on 45 poses). Full v1.6 with lying prisms 48/53 vs v1.5 46/53 (e-049). Still failing: objects < 0.20 m in front of the pelvis, cross-body reaches, fingers > 50° from the hand's natural direction.
  - **Sim runs on Modal:** see `eval/RESULTS.md` (e-044…e-049).
- **Now (Sat 14 Nov, ~20:30): v1.5 measured on Modal** (e-029…e-032, gate PASS every run). Same-side arms cost objects (sort_fixed 20/27 strict, 23/27 off); the ridge grasp holds lying triangles 4/9 (stock claw 0/14). Strict mode now allows 3 relay tries per object (Aalto: 1), not yet run. Next: run that, lower the ridge grasp, sort_language with sides off.
- **Now (Sat 14 Nov, ~17:00):** the library, four choosers (default, Decision 1, random, prefer_face), camera perception, crop labels, logging and analysis are in place, plus the upgrades in `upgrades.py` (memory chooser, grasp check). Everything has run in the venue-look sim with gate PASS (0 clips, 30 Hz). **The upgrades in `upgrades.py` sort 26/28 on sort_language (e-015) against 20/28 for Aalto's oracle**, and 23/27 against 22/27 on sort_fixed (e-016; the same before the option-search fix, e-013); gate PASS every time. Grasp check off: same 23/27 (e-018). Camera + Decision 1: 21/27 (e-017). Upgrades with camera: 21/27 (e-019). Without the memory chooser: 23/27 (e-020). Camera on sort_language: 21/28 (e-021), one more than Aalto's oracle with exact poses. Upgrades with camera on sort_language: 26/28 (e-022). Next: triangle and tipped-block movements, randomisation, a policy server.
- **Next:**
  - More seeds for the upgrades on both tasks (the sort_language gain rests on 6 seeds). More options for objects that have only one: more carry routes, relay as a normal option, a nudge move (all 4 sort_fixed misses in e-016 are of this kind).
  - Placement check: Decision 1 "is it in the bin?" on the head camera.
  - Real-robot gaps for camera mode: real depth noise and holes, bins not exactly at `scene.yaml` positions, the real hand sitting 4–6 cm closer than the sim hand (`sim/venue_look/README.md`). None of these is tested.
  - Turn it into a policy server (it runs in-process inside Aalto's evaluator today).
- **Models as monitors (Sat 14 Nov, measured without the sim):** [`docs/research/model-monitor-oracle.md`](../../docs/research/model-monitor-oracle.md). The finger-angle rule tells held from empty on 146 of 147 logged picks; Decision 1 matches it only with a before/after image pair; no model predicts a failed pick better than "triangle + stock claw, or another block within 7 cm". Scripts: `monitor_rules.py`, `monitor_probe.py`.
- **Blockers:** none.

## Results (venue look, 3–6 scattered objects; sort_fixed uses seeds 1000–1005, sort_language 2000–2005)
| Run | Task | Perception | Chooser | Sorted | Cubes | Cylinders | Triangles | Gate |
|---|---|---|---|---|---|---|---|---|
| e-004 | sort_fixed | exact poses | Aalto's oracle | 22/27 (82 %) | 7/7 | 13/15 | 2/5 | PASS |
| e-005 | sort_fixed | exact poses | Decision 1 | 23/27 (85 %) | 7/7 | 14/15 | 2/5 | PASS |
| e-006 | sort_fixed | camera | oracle's rule (seeds 1002–1003 only) | 6/9 | 1/1 | 5/5 | 0/3 | PASS |
| e-007 | sort_language | exact poses | Aalto's oracle | 20/28 (71 %) | 13/16 | 6/8 | 1/4 | PASS |
| e-009 | sort_language | exact poses | Decision 1 | 21/28 (75 %) | 14/16 | 5/8 | 2/4 | PASS |
| e-012 | sort_fixed | camera | oracle's rule | 18/27 (67 %) | 6/7 | 10/15 | 2/5 | PASS |
| e-013 | sort_fixed | exact poses | upgrades: memory chooser + grasp check (before the option-search fix) | 23/27 (85 %) | 7/7 | 13/15 | 3/5 | PASS |
| e-014 | sort_fixed | exact poses | random | 21/27 (78 %) | 6/7 | 13/15 | 2/5 | PASS |
| e-015 | sort_language | exact poses | upgrades: memory chooser + grasp check | **26/28 (93 %)** | 16/16 | 7/8 | 3/4 | PASS |
| e-016 | sort_fixed | exact poses | upgrades: memory chooser + grasp check | 23/27 (85 %) | 7/7 | 14/15 | 2/5 | PASS |
| e-017 | sort_fixed | camera | Decision 1 (+ crop labels) | 21/27 (78 %) | 6/7 | 14/15 | 1/5 | PASS |
| e-018 | sort_fixed | exact poses | upgrades without the grasp check | 23/27 (85 %) | 7/7 | 15/15 | 1/5 | PASS |
| e-019 | sort_fixed | camera | upgrades: memory chooser + grasp check | 21/27 (78 %) | 7/7 | 13/15 | 1/5 | PASS |
| e-020 | sort_fixed | exact poses | upgrades without the memory chooser (oracle's choice + grasp check) | 23/27 (85 %) | 7/7 | 15/15 | 1/5 | PASS |
| e-021 | sort_language | camera | oracle's rule | 21/28 (75 %) | 11/16 | 7/8 | 3/4 | PASS |
| e-022 | sort_language | camera | upgrades: memory chooser + grasp check | **26/28 (93 %)** | 16/16 | 8/8 | 2/4 | PASS |
| e-029 | sort_fixed | camera | **v1.5 policy server**, same-side arms (Modal) | 20/27 (74 %) | | | | PASS |
| e-030 | sort_fixed | camera | v1.5, sides off (Modal) | **23/27 (85 %)** | | | | PASS |
| e-031 | sort_language | camera | v1.5, same-side arms (Modal) | 22/28 (79 %) | | | | PASS |
| e-032 | sort_fixed, triangles lying | camera | v1.5, same-side arms (Modal) | 18/27 (67 %) | | | | PASS |

Every run: 0 clipped steps, 30 commands/s in sim time, policy 110–135 Hz in real time. Sim time per sorted object: about 22 s (15 s with the grasp check, e-013). Full rows with logs: [`eval/RESULTS.md`](../../eval/RESULTS.md).

- **Is a block really lying? (offline, `test_tipcheck.py`, 115 saved sim frames).** The camera geometry called 59 detections "tipped": 48 really lying, 11 upright (mostly standing triangles seen at an angle). It found 47 of the 48 lying triangles on the table, with a ridge direction error of 0.8° median (1.3° at 90 %). Asking a model about the crop: **Decision 1** right 47/59, caught 2 of the 11 upright ones but called 3 really lying blocks upright, 0.59 s median; **Hydrogen** (`gemini-4-hydrogen`, JSON schema, thinking off) right 49/59, caught 5/11, flipped 4, 3.2 s median (6.2 s max). Neither beats the geometry, so the check is off in v1.5 (`V15_TIP_CHECK`). Lying cylinders are read as "cube" (19 times), which the model check does not see.
- **Decision 1 as chooser shows no measurable gain** (one object of 27). 46 calls, 0.64 s median, 1.27 s max, no fallbacks. It took a non-default option in 31 of 46 looks, with confidence around 0.5. Picks where it changed the object: 9/13 ok; drop spot: 6/12; grasp or arm: 0/3; same as the oracle: 8/13.
- **Upgrades with camera perception on sort_language: 26/28** (e-022), the same as with exact poses (e-015) and 6 more than Aalto's oracle with exact poses (e-007). The best result here without privileged state; the 2 misses are triangles. It still runs inside Aalto's evaluator, not as a policy server.
- **Oracle upgrades on sort_language: 26/28 against 20/28 for Aalto's oracle and 21/28 for Decision 1** (e-015 vs e-007, e-009, same seeds). The first gap larger than noise, but 4 of the 6 extra objects come from one seed (2005: 5/6 against 1/6), so it needs more seeds. The gain is in the retries: first try 16/28 as before, second try 8/11 and third 2/3 (Decision 1 run: 5/11 and 1/3), because a failed arm and grasp pair is not repeated and an empty hand is noticed at the lift. Cubes 16/16, triangles 3/4. 16 grasp-check aborts, all real misses.
- **Oracle upgrades on sort_fixed with the search fix: 23/27 again** (e-016; e-013 before the fix; Aalto's oracle 22/27). No gain on this task. All 4 misses are objects that had a single planner-checked option which does not hold: 3 triangles with only the stock claw, and a red cylinder that only the left arm with the stock claw could reach (empty hand 4 times out of 4). A chooser cannot fix these; the next step is more options (other grasps, carry routes, relay as a normal option). Grasp check over the three upgrade runs: 45 aborts, all real misses; 2 blocks were held at the lift and lost in the carry.
- **On sort_fixed no single upgrade matters:** all upgrades, no grasp check and no memory chooser each sort 23/27 (e-016, e-018, e-020), one more than Aalto's oracle. Triangles (1–3 of 5) are the limit, and no planner-checked grasp holds them; the gain on sort_language (e-015) has not been taken apart yet.
- **Grasp check on or off: 23/27 both times** (e-016, e-018). It does not add objects on these seeds; it saves time (one episode without it ran into the 120 s limit).
- **Upgrades with camera perception: 21/27** (e-019), 3 more than camera with the oracle's rule (e-012), same as camera + Decision 1. Retries go to blocks a failed pick knocked onto their side: 0 of 9 such picks held. Next for camera mode: stop retrying a tipped block with the stock claw, or nudge it upright.
- **Camera + Decision 1: 21/27** (e-017), against 18/27 for camera with the oracle's rule (e-012) and 22/27 with exact poses. Triangles 1/5.
- **Random chooser: 21/27** (e-014), one object below the oracle's rule. Which arm or drop spot is taken matters little; the grasp type on triangles does (stock claw 1/8, face grasp 1/3).
- **Oracle upgrades, on sort_fixed, first run: 23/27, no measurable gain** (e-013 vs 22/27 for Aalto's oracle and 23/27 for Decision 1 on the same seeds). What did work: the grasp check aborted 11 picks and all 11 were real misses (finger error 0.000–0.001 rad with an empty hand, 0.019–0.071 with a block); it missed 1 block that was held at the lift and lost in the carry. Retries on the same object: first try 17/25, second 5/6, third 1/1. Sim time per sorted object fell from about 22 s to 15 s, because an empty hand stops at the lift. No object went to a wrong bin. This run still had a flaw in the option search (one object's grasp variants used the whole time budget, another object never got a plan and stayed on the table); the fix is in `upgrades.py` and its runs are going.
- **Camera perception on all 6 seeds: 18/27 against 22/27 with exact poses** (e-012 vs e-004; the 2-seed smoke test e-006 had shown no difference). Localisation is not the cause: 2.4 mm median error over 180 object views, no false detections, and failed picks had the same position error as successful ones. The lost objects are grasp failures (cylinder stock claw 11/24 picks in this run) and blocks that a failed pick tipped over (0/3 picks; a lying cylinder is read as a cube). With 27 objects and picks that succeed about half the time, 4 objects is within run-to-run spread.
- **Camera perception on 115 saved sim frames** (arms often in view): 229 of 246 objects matched, 2.5 mm median error (4.4 mm at 90 %), colour 229/229, shape 153/162 by geometry, yaw error under 0.5° median. Head pose fit: 9.79° ± 0.02° tilt on every frame.
- **Decision 1 crop labels** on those frames: 37/37 upright blocks right on shape, 48/48 on colour, ~1 s per call; 0/11 on tipped blocks (it says "triangle"), which the geometry catches.

## Which movements fail (per executed pick, e-005 and e-006)
| Movement | Picks ok | Note |
|---|---|---|
| Cube, face grasp | 5/5 | |
| Cube, stock claw | 4/7 | works less often than the face grasp |
| Cylinder, stock claw | 18/27 | left arm 9/16, right arm 9/11 |
| Triangle, face grasp | 1/1 | |
| Triangle, stock claw | 1/15 | **the main failure.** Fingers end up at 45° to the robot, not on a face; the pinch slips and can tip the triangle over |
| Tipped block, stock claw | 0/1 | |
| Relay | not needed in these seeds | |

- **Why triangles get the stock claw:** Aalto's oracle tries the face grasp only on its first-choice arm and falls back to stock finger directions when that plan is rejected. Rejections for triangle face grasps in e-005: "no joint-space carry path above the bin rim" (24), the arm can't reach the bin (41, the other arm), IK failures (13). An alternative face angle (75° or 90° instead of 105°) had a valid plan 12 times and was never chosen. The `prefer_face` chooser tests exactly that.
- **All failed picks left the object on the table** (27 of 27); none went into a wrong bin or off the table.
- **A failed pick pushes the object** 1–3 cm, sometimes onto its side, and the retry uses the same grasp.

## Gotchas
- The submodule `third_party/aaltonomous-humanoid` must be at Aalto 36daf5b; `oracle.py` internals (`_OraclePlanner`, `_plan_relay`, `FACE_ALIGN`, …) are imported, so a newer Aalto commit may break this.
- Every shell that starts the sim, the evaluation or the offline test must `source /root/venue_look/venue_env.sh`, or the bin sizes disagree.
- Enumeration is CPU work in the policy process (GIL). Watch `policy_hz_rt` in the gate; Aalto's 1 ms switch interval keeps `act()` responsive.
- Decision 1's `choice` always spreads probability; the chosen value is the argmax, so low confidence still picks something. Its `default` criterion catches "unsure".
- The API key lives in `/root/.decision_key` on the sim machine (chmod 600). Never in code, logs or the repo.
