# Sim failure analysis: what goes wrong, grasp by grasp

**Snapshot:** Sat 14 Nov 2026, 17:45 Helsinki time, Samer + Claude. Data: [`data/2026-11-14_1745/`](data/2026-11-14_1745/). Every number below is printed by `python eval/analysis/numbers.py eval/analysis/data/2026-11-14_1745`. Method, columns and limits: [`README.md`](README.md).

**FACT** = measured in these runs. **OPINION (Samer + Claude)** = what we would build next.

## Read this first (FACT)
- **The oracle trap.** `aalto.sh eval --container IMAGE` without `--policy` runs **Aalto's privileged oracle**, not the image: Aalto's `evaluate.py` checks `--policy` (default `"oracle"`) before `--container`. Our runs labelled v1 / v1.1 / v1.2 that started before Sat 15:19 UTC were the oracle (e-010; fixed in 9b0e59c). Always pass `--policy ws://localhost:PORT` with `--container`; [`traced_eval.py`](traced_eval.py) adds it by itself.
- **First real image runs:**
  - **v1.2, nominal sim:** 12/15 sorted on seeds 1000–1003. On the same 4 seeds the baseline sorts 10/15 and the oracle 13/15. Only 4 of its 10 episodes were done at the snapshot; the run is still going.
  - **Update 17:55, not in the snapshot yet:** v1.2's 5th episode (seed 1004) sorted **0/5**. 8 of its 11 grasps were empty, on three cylinders, a triangle and a cube close to the robot; the baseline sorted 2/5 there. After 5 episodes **v1.2 is level with the baseline: 12/20 each** on seeds 1000–1004 (oracle 17/20). The lead after 4 episodes was noise.
  - **v1.1, one video episode (seed 1001):** 4/5 sorted.

## The runs (FACT)
| Label | Folder | What actually ran | Sim | Seeds | Sorted |
|---|---|---|---|---|---|
| **baseline** | `baseline_sort_fixed_nominal_…` (e-008) | Aalto's classical baseline, camera only (a valid submission) | nominal | 1000–1009 | 26/40 (65 %) |
| **baseline DR** | `baseline_sort_fixed_train_…` (e-011) | the same baseline | `AALTO_DR=train`: randomised lighting, colours, friction, camera ±1 cm / ±1° (closest to the held-out variant) | 1000–1009 | 11/40 (28 %) |
| **oracle** | `ORACLE-not-v1_sort_fixed_nominal_…` (e-010) | Aalto's oracle: exact object poses from the sim, not a submission | nominal | 1000–1009 | 32/40 (80 %) |
| **v1.2** | `bot-icelli_policy_v1.2_sort_fixed_nominal_…` | our image `bot-icelli/policy:v1.2` | nominal | 1000–1003 (4 of 10, running) | 12/15 (80 %) |
| v1.1 video | `v1.1-seed1001_…` | our image v1.1 | nominal | 1001 | 4/5 |
| oracle video | `ORACLE-not-v1.1-seed1001_…` | the oracle (mislabelled run) | nominal | 1001 | 4/5 |

The tables cover 36 episodes, 145 objects and 215 grasps. They also hold 309 events from the policies' own logs, e.g. each `execute <colour> <arm> → <bin>` with its planned grasp point, drop point, IK error and motion time.

## What the data shows (FACT)
### 1. The second object dropped into a bin often doesn't count
- **Aalto's rule** (`scene.py` `rule_text`): an object counts as in a bin only if its centre is inside the inner walls **and below the 6 cm rim**.
- **The baseline drops every object at the same point of each bin.** That point is the inner corner nearest the robot (`grasp.drop_inset` 0.05 in the classical config): pelvis (0.45, 0.00) for the centre bin and (0.45, ±0.21) for the side bins.
- **First object into a bin:** 24 of 24 scored.
- **Object released over a bin that already held one:** 2 of 8 scored.
  - 5 came to rest on top of the first object, centre 6.4–7.7 cm above the counter. That is above the rim, so it counts as "left on the counter".
  - 1 bounced off it and off the table (−1; seed 1005).
- That is 6 of the baseline's 14 lost objects, and 7 of its points.
- **The oracle** sometimes uses a second spot, 3 cm further in x and in y. It lost 1 of 7 such drops.
  - In the right bin that second spot is only 2 cm from the inner wall next to the centre bin, and the cube came to rest on the walls (seed 1009).
  - One more oracle object slipped out of the hand over a bin and ended above the rim (seed 1005).
- v1.2 lost 1 of 1 such drops.
- The oracle video shows it (seed 1001, the red cube at ~51 s).

### 2. Grasps that close on nothing
- **Empty grasps:**
  - baseline 34/69 (49 %)
  - baseline DR 38/54 (70 %)
  - oracle 19/56 (34 %)
  - v1.2 2/21 (10 %). On the same 4 seeds the baseline had 9/24. Its 5th episode (seed 1004, after the snapshot) had 8 empty of 11, so this is not a stable difference yet.
- **Unsorted objects never held at all:**
  - baseline 8 of 14
  - baseline DR 10 of 29, plus 15 never attempted
  - oracle 4 of 8
- **Not an aiming problem in the nominal sim.** The planned grasp point is as close to the object for empty grasps as for held ones: first attempts, x/y, median.
  - baseline: 0.6 cm when empty, 0.9 cm when held
  - oracle: 0.4 cm for both, still a third empty
  - grasp height is always the same, z = 0.03 m
- **With randomisation the aim gets worse:** 1.4 cm when empty, 1.1 cm when held, worst 5.4 cm. This includes up to 0.5 cm by which DR places each object off its layout card; the start positions don't show that.

### 3. Retrying the same grasp works less often than the first try
- **Held, first attempt vs second attempt on the same object:**
  - baseline 58 % vs 37 %
  - baseline DR 40 % vs 20 %
  - oracle 72 % vs 46 %
- **Each miss pushes the object.** Baseline seed 1002: the left arm tried the far-side red cylinder 4 times, all empty. Each plan was 1 cm closer to the robot (x 0.26 → 0.22 m).

### 4. Shapes
| | baseline | baseline DR | oracle | v1.2 (4 seeds, no triangles) |
|---|---|---|---|---|
| Held on the first grasp: cube | 73 % | 62 % | 73 % | 7/7 |
| Held on the first grasp: cylinder | **53 %** | 31 % | **89 %** | 6/8 |
| Held on the first grasp: triangle | 50 % | 25 % | 40 % | – |
| Sorted: cube / cylinder / triangle | 7/11, 13/19, 6/10 | 5/11, 5/19, 1/10 | 9/11, 16/19, 7/10 | 6/7, 6/8, – |

Most slips in the carry are cylinders.

### 5. Where the object sits
- **Far cross-body** (more than 8 cm past the robot's centre line on the far side for the arm that serves its bin):
  - sorted: baseline 2/9, baseline DR 1/9, oracle 6/9
  - near side: 24/31, 10/31, 26/31
  - the baseline's far cross-body grasps were empty 10 of 17 times
- **Hand-overs in v1.1 / v1.2:** 5 so far, and 3 of the 5 objects were then sorted. Both failures are the same object: seed 1001's red cube, handed over by the right arm. Watch it in the v1.1 video at ~68 s.
- **Close to the robot** (pelvis x < 0.30 m): baseline 9/18 vs 17/22 further out; oracle 12/18 vs 20/22.

### 6. Randomisation adds failures of its own (baseline DR)
- **15 objects were never attempted:**
  - 9 are in two episodes that safe-stopped in the first 4 s (seeds 1005, 1009). The cause is the baseline's blocking `reset()` right after an episode cut by the time limit; our versions are fixed (80d7c9a).
  - 5 are in the two episodes cut by the 120 s limit (seeds 1004, 1008).
  - 1 is in seed 1000. The baseline said "nothing left to sort" at 57 s while a blue cylinder was still on the counter: an object it didn't recognise.
- **Grasps miss much more often:** 70 % empty.
- **Two more episodes ran out of time** (seeds 1001 and 1002). After many empty grasps the policy stopped at 111 s and 118 s with "not enough time for red / yellow (10 s)".

### 7. Planning is not the bottleneck
- All 215 executed plans passed IK (max error 6.0 mm) with 0 safety clips.
- No log has a planner refusal (`skip`).
- A planned pick-and-place takes 9.8 s (median; 8.3–11.4 s). The baseline doesn't notice an empty hand, so every empty grasp costs a full trip to the bin and back.
- Sim seconds per sorted object: baseline 28, baseline DR 71, oracle 19, v1.2 19.

### 8. The grip signal is clean (for opinion 2)
- After the fingers close, an empty hand reaches the commanded finger angles. A held object stops at least one finger short.
- The measure is the largest per-joint median of |hand_q − hand_q_cmd| over the lift. Over all 215 grasps:
  - 94 empty grasps measured at most 0.0036 rad
  - 115 held grasps at least 0.0081 rad (median 0.037)
  - 6 fell in between
- It matches Emīls's independent check: the grasp check in `policy/decision_oracle/upgrades.py` was right on all 11 aborts (e-013) and on 146 of 147 logged picks ([`docs/research/model-monitor-oracle.md`](../../docs/research/model-monitor-oracle.md)).

## What to build or change (OPINION, Samer + Claude), most gain per hour first
1. **A free drop spot in each bin.**
   - Count what the policy has already put into each bin this episode, and release the next object at a different spot: 2–3 spots per bin, all inside reach.
   - Keep each spot at least ~4 cm from every inner wall: the objects are 4.5 cm wide, and the oracle's second spot, 2 cm from a wall, put a cube on the wall.
   - The side bins' far half is out of reach (`scene.yaml` notes), so spread along the near, inner part.
   - Where: override `Planner.bin_xy` (Aalto's `baselines/classical/planner.py`, which places the drop point) in our v1.x.
   - In these runs it would have saved up to 6 of 40 objects (7 points) for the baseline. It is cheap and testable offline.
2. **Grasp check right after closing, then retry at once.**
   - On an empty hand: abort the carry, open, look again, re-plan. Saves ~10 s per miss, which is half the baseline's grasps.
   - Emīls has it for the oracle (`upgrades.py`): 22 → 15 sim s per sorted object (e-013). Port it to the v1.x executor.
3. **Never repeat a grasp that just failed.** Change the finger direction (face-aligned for cubes and triangles), the height, or the arm. Emīls's memory chooser does this for the oracle; Tiya's `pick_triangle` tool plans face-aligned triangle grasps but isn't wired to perception and the executor yet.
4. **Cylinders: copy what the oracle does.** Its first grasp holds 89 % against the baseline's 53 %, and aim doesn't explain it (see 2). Compare the two in `picks.csv` (`planned_grasp`, `arm`, `shape`) and in `policy/decision_oracle`.
5. **Hand-overs:** find out why seed 1001's red cube is lost after its hand-over (v1.1 video, ~68 s).
6. **Randomisation:** run v1.2 with `AALTO_DR=train`. The held-out variant looks like this, and the baseline drops from 65 % to 28 % there. Check colour recognition there too (the missed blue cylinder in seed 1000).
7. **Objects near the robot** (x < 0.30 m): a different approach or a nudge outwards.
8. **Trace every new run** with [`trace.py`](trace.py) and [`numbers.py`](numbers.py). Plain run folders work, plus the policy's log. [`traced_eval.py`](traced_eval.py) would add object positions 5 times a second, the container's log and video. It has not been run end-to-end yet: test it on one trial first.

## Episodes worth looking at
| Run / seed | What happens |
|---|---|
| baseline 1001, 1002, 1009 | the second object into a bin lands on the first and doesn't count (5 objects) |
| baseline 1005 | a blue cylinder bounces off the bin's first object and off the table (−1) |
| baseline 1002, t 32–68 s | the far-side red cylinder, 4 empty grasps in a row, pushed closer each time |
| baseline 1004 | 10 grasps, 8 empty, 2 of 5 sorted |
| baseline DR 1007 | 8 grasps, all empty, 0 of 3 sorted |
| oracle 1006 | exact poses, still 6 empty grasps, 1 of 4 sorted (two triangles, never held) |
| v1.1 video, seed 1001 | 4 of 5; two hand-overs, the red cube is lost after its hand-over (~68 s) |
| oracle video, seed 1001 | 4 of 5; the blue cylinder slips twice, the red cube lands on the other red cube (~51 s) |

The videos are on Samer's laptop and the sim machine (`~/video/out/`). The repo ignores `*.mp4`. Real v1.2 videos for seeds 1001 and 1002, and v1.1 for 1002, are recording.

## Limits (FACT)
- **No object positions during these runs.**
  - The object a grasp aimed at is matched from start positions and the policy log, so a few grasps may be attributed to the wrong object.
  - Where each object ended is exact: it comes from Aalto's end-of-episode poses and outcomes.
  - New runs through `traced_eval.py` would record positions 5 times a second (not run end-to-end yet).
- **Physics is not deterministic.** The same seed can end differently; Aalto expects ±10 % between runs. Small differences (one object in 15) are noise.
- sort_fixed only, so far. sort_language doubles every point, so the same failures cost twice as much there.

## Marcus's agent, standing blue cylinder missed twice (e-042, seed 1000, Sat ~22:30, Samer + Claude)
Measured with `grasp_geometry.py` (forward kinematics on the recorded joint angles) against the sim's true spawn
positions (`layout` in eval.json, mat → pelvis: x = 0.14 + y_mat, y = −0.45 + x_mat):
- **Perception was not the problem:** the agent's object positions were within 2–3 mm of the truth for all three.
- **The arm was not the problem either:** when the fingers started closing on the cylinder (miss 1), the grasp point
  was 0.5 cm from its centre (commanded 0.2 cm; tracking error < 1°), the same as the two grasps that held (red cube
  0.5 cm, yellow cylinder 0.5 cm), with the fingertips at the same distances.
- **The grasp itself lost it:** the fingers closed fully on nothing and the cylinder ended 1.6 cm closer to the robot,
  i.e. the closing fingers pushed the round object out before the thumb held it. Standing cylinders fail this way
  often (Emīls: claw grasp on cylinders 45/77).
- **The model's retry made it worse:** Gemini asked for a 1.5 cm offset toward the robot, so miss 2 closed 1.8 cm short
  of the (already pushed) cylinder, which then tipped over. The tipped cylinder was picked up on the next try.
- To fix: the grip on round objects (closing order, a grip that cages the cylinder, grasp height), tested with
  Marcus's grasp bench; and don't let the model add offsets when the estimate is this accurate.
