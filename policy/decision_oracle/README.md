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
- **Not a submission.** It runs in-process inside Aalto's evaluator and imports Aalto's planner. Nothing here is in the Docker image.
- **Still running (Sat evening):** sort_language with Decision, camera mode on all 6 seeds, the random chooser, camera + Decision, camera + prefer_face. Rows get added to `eval/RESULTS.md` as they finish.

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
| Retry / skip | retry up to 2× per **table position** (a pushed object counts as new) | `retry` / `skip`, asked when a picked object is back on the table |

## How it decides (never blocks `act()`)
- The look runs in Aalto's planning thread. That is the first look of an episode, or the prefetch while the previous pick executes. Meanwhile `act()` returns holds, as in Aalto's oracle.
- The oracle's own choice is planned first, so a default always exists. Then alternatives are planned until a budget runs out: 8 s in a prefetch, 3 s in a blocking look.
- Decision 1 gets one call per look: the head-camera JPEG, a short scene text, and one `choice` question per parameter. Each question's criteria are only the feasible values plus `default`; questions with a single feasible value are skipped. A timeout (2 s), an HTTP error or a missing answer falls back to the default. Answers are matched to an option in the order object → arm → grasp → route. A non-default drop spot means one more plan; if that plan fails, the default spot is kept.

## Camera perception (`--perception camera`)
1. **Head camera pose.** Aalto's `calibration.yaml` pose is a URDF default; the real camera and our venue-look sim point about 10° further down. `fit_head_pose` re-fits it from one depth image at the first look of an episode: the table plane gives tilt, roll and height; the bin walls (known 21 cm boxes) give x, y and yaw. No markers needed.
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
$P -m decision_oracle.test_camera <frames dir>                  # camera perception vs true poses on saved frames
python3 policy/decision_oracle/analyze.py <run_dir>=<decisions.jsonl>    # laptop, after copying the runs back
```
Don't pass `--no-cameras`: the Decision chooser needs the head image.

## Status
- **Now (Sat 14 Nov, evening):** the library, four choosers (default, Decision 1, random, prefer_face), camera perception, crop labels, logging and analysis all run in the venue-look sim. Gate PASS in every run so far (0 clips, 30 Hz). Results below; more runs are queued on the sim machine (sort_language with Decision, camera on 6 seeds, random chooser, camera + Decision, camera + prefer_face).
- **Next:**
  - Fix the triangle grasp: see "Which movements fail".
  - Grasp check from the finger angles in `obs["hand_q"]` (an empty hand closes further), so a miss is caught before the carry.
  - Placement check: Decision 1 "is it in the bin?" on the head camera.
  - Count retries per object, not per table position (camera names already survive small moves; a pushed object gets a new name).
  - Real-robot gaps for camera mode: real depth noise and holes, bins not exactly at `scene.yaml` positions, the real hand sitting 4–6 cm closer than the sim hand (`sim/venue_look/README.md`). None of these is tested.
  - Turn it into a policy server (it runs in-process inside Aalto's evaluator today).
- **Blockers:** none.

## Results (venue look, 3–6 scattered objects; sort_fixed uses seeds 1000–1005, sort_language 2000–2005)
| Run | Task | Perception | Chooser | Sorted | Cubes | Cylinders | Triangles | Gate |
|---|---|---|---|---|---|---|---|---|
| e-004 | sort_fixed | exact poses | Aalto's oracle | 22/27 (82 %) | 7/7 | 13/15 | 2/5 | PASS |
| e-005 | sort_fixed | exact poses | Decision 1 | 23/27 (85 %) | 7/7 | 14/15 | 2/5 | PASS |
| e-006 | sort_fixed | camera | oracle's rule (seeds 1002–1003 only) | 6/9 | 1/1 | 5/5 | 0/3 | PASS |
| e-007 | sort_language | exact poses | Aalto's oracle | 20/28 (71 %) | 13/16 | 6/8 | 1/4 | PASS |

Every run: 0 clipped steps, 30 commands/s in sim time, policy 110–135 Hz in real time. Sim time per sorted object: about 22 s. Full rows with logs: [`eval/RESULTS.md`](../../eval/RESULTS.md).

- **Decision 1 as chooser shows no measurable gain** (one object of 27). 46 calls, 0.64 s median, 1.27 s max, no fallbacks. It took a non-default option in 31 of 46 looks, with confidence around 0.5. Picks where it changed the object: 9/13 ok; drop spot: 6/12; grasp or arm: 0/3; same as the oracle: 8/13.
- **Camera perception costs nothing on the two seeds tried:** same score per seed as with exact poses. Against the truth: 2.5 mm median position error, shapes right except one cylinder seen as a cube after it was pushed, no false detections.
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
