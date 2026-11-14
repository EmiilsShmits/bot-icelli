# v1.5 (decision oracle as a policy server) vs Marcus's ADK agent

Written Sat 14 Nov ~20:30 by Emīls + Claude; venue-look side-by-side added ~21:30. Sources: our `eval/RESULTS.md` (e-004, e-028…e-040), Marcus's repo
github.com/marcusoberg/junction2026 at 1a51d7b (Sat 19:39: `adk_agents/`, `sim/modal_sim.py`, `sim_out/*/eval.json`),
and the same-seed numbers Samer collected in `docs/CONTEXT.md`. Scores marked "own scene" were measured in different
scenes and cannot be compared directly.

## What each one is

| | Marcus's ADK agent (`adk_agents/robot_sorter`) | v1.5 (`policy/policies/oracle_v15.py` + `decision_oracle/upgrades_v15.py`) |
|---|---|---|
| Motions | Aalto's oracle planner, cut into skills (`agent/skills`) | Aalto's oracle planner, called through `decision_oracle/motions.py` |
| Perception | Head RGB-D only. Head-camera pose fit and top-face shape (`classify_top`) taken from bot-icelli | Head RGB-D only (`decision_oracle/camera.py`): pose fit from depth, shape and yaw from the top face, ridge direction for lying blocks |
| Who decides the next move | **Gemini 4 Hydrogen** through Google ADK, calling tools: `look`, `view_camera`, `pick_and_place`, `pick`/`place`, `choose_arm`, `check_plan`, `hand_over`, `place_on_counter`, `go_home`, `done`, … About 6 calls per episode | Rules, no API: failure memory per object, face grasp first, a search over every planner-checked option |
| Other model calls | Gemini Decisions API: colour / shape label per object in `look`; decides the unclear band of the grasp check; picks the next object while the arm carries | None. Optional `V15_TIP_CHECK=d1\|hydrogen` (off: it did not beat the geometry, see the README) |
| Time per decision | 3–4 s, the robot holds still meanwhile (README of `adk_agents/`; `ROBOT_AGENT_THINKING=low`) | Planning < 1 s in a background thread |
| If the network fails | Holds still and asks again (back-off 0.5 → 5 s, `serve.py`). No automatic switch to the rule mode (`ROBOT_AGENT_MODEL=bench` exists as a separate mode) | Nothing changes |
| Instruction | The model reads the sentence itself: any wording | Emīls's rule parser (`policy/instruction.py` + colour × shape keys) |
| Arms | Parked out to the sides between moves; moves bringing the arms within 12 cm are refused; the other arm is moved aside when in the way; `arms.py` orders arms by bin reach, then shoulder distance | `V15_SIDES=strict`: each arm grasps and drops only on its own half, cross-side objects handed over on the centre line; `off`: either arm anywhere |
| Triangles | Face grips, every grip angle tried before giving up | Face grasp first; lying triangles: pinch across the end faces along the ridge (held 4/9 vs stock claw 0/14, e-032) |
| Grasp check | Finger tracking error after the lift (0.010 rad), Gemini decides the unclear band | Finger angles at the end of the lift (`grasp_check`) |
| Real colours (orange / yellow / purple) | Any saturated colour + Gemini labels; run in the sim with real colours (`--colors real/venue`) | HSV classes cover them (orange in "red", purple in "blue"), parser maps the words; **not yet run in the sim with real colours** |
| Submission image | **None.** `submission/Dockerfile` packs π0.5 only. An image would need internet during the run and the Gemini key inside the image | `bot-icelli/policy:v1.5` built on sim-3 (1.46 GB), Aalto's replay test: 100 calls, 0 errors, p50 4.9 ms |

Both pass the gate in every run (0 clipped steps, ~30 Hz).

## Scores

**Same seeds, same scene (Aalto's look, sort_fixed, seeds 1000–1004)**, from `docs/CONTEXT.md`:

| Policy | Nominal | `AALTO_DR=train` |
|---|---|---|
| Marcus's agent (1a51d7b, `sim_out/s2`) | 16/20 | **18/20** |
| Aalto's oracle, exact poses (not a submission) | 17/20 | 17/20 |
| Aalto's baseline | 12/20 | 10/20 |
| v1.3 | 13/20 | 14/20 |
| v1.4 | | 15/20 (seeds 1000–1009: 29/40, e-035) |
| **v1.5** | not run | sides off **17/20** (Sat ~20:45; seeds 1005–1009 and strict sides running on `samer-v1-sim`, `eval/v15_lane.sh`) |

**Same seeds, same scene (our venue look, nominal, Modal, Sat ~21:30)**: the first run of both side by side.
The agent is Marcus's 1a51d7b with one fix (item 3 below: the head-camera fit is accepted by how far the camera
moves), so it uses the venue look's 9.8° fit in every episode.

| Policy | sort_fixed 1000–1005 | sort_language 2000–2005 | Both |
|---|---|---|---|
| Marcus's agent + camera fix (e-038, e-039) | 20/27 (triangles 1/5) | 23/28 (1 in a wrong bin) | 43/55 |
| **v1.5, sides off** (e-030, e-040) | **23/27** | **24/28** | **47/55** |
| v1.5, strict (e-029, e-031) | 20/27 | 22/28 | 42/55 |

Sim time per episode is about the same (agent 37–117 s, v1.5 42–117 s): the agent is quicker on easy seeds and
20–40 s slower on seeds with many retries, 3 of which ended 5–6 s before the 120 s limit. Its 127 Gemini calls took
2.3 s median, up to 18 s (wall clock), which in this sim (RTF 0.32) is only about 10 % of an episode's sim time. On
the real robot, at real time, each wait costs its full length.

### Where each loses objects (venue look, the 12 episodes above)

From v1.5's decision logs (`runs/decisions_v1.5.jsonl`) and the agent's `policy.log` (every tool call and result).
v1.5 sides off lost 8 of 55, the agent 12 of 55. Small sample (9 triangles in all); the seed 1003 wrong bin is
inferred from the logs, not checked on video.

**Both: triangles.** v1.5 sorted 2 of 9, the agent 3 of 9 (7 of v1.5's 8 losses, 6 of the agent's 12). The hand
closes on nothing: v1.5's grasp check found it empty on 8 of 10 face grasps on standing triangles and 4 of 4 stock
claws. The failing triangles lie close to the robot (x 0.20–0.24 m), where only the plain pinch can be planned. A
miss often tips the triangle over; lying blocks then failed 6 of 7 times with the stock claw (seed 2002: three in a
row).

**v1.5 only:**
- Empty stock-claw grasps on cylinders: 12 of 32. Seed 2005 spent five on cylinders and reached 117 s with a
  cylinder and a triangle left.
- Knocked neighbours. Seed 1002: reaching for a red cylinder, the left arm pushed a blue triangle 6 cm away toward
  the robot and out of the head camera's view; the episode ended with it on the table. Seed 1003: a blue triangle
  ended in the red bin, apparently carried by the left arm's move.
- A lying cylinder read as a cube (seed 1003; sorted anyway): the shared `classify_top` problem below.

**ADK agent only:**
- Repeats failed picks: 31 of 82 pick tries missed (38 %); 17 times it tried the same object again straight after
  a miss, 6 of those with identical arguments (seed 1003: the same right-arm pick on one triangle three times).
  v1.5's failure memory moves to another arm / grasp after a miss (item 2 below).
- Leaves triangles with no plannable grasp: 3 times the tool returned "only the plain pinch can be planned from
  here, and it does not hold a triangular prism", and the model moved on.
- Stops early: seed 1003 ended at 93 s with 26 s left and 3 objects on the table, after `hand_over` failed ("no
  hand-over spot is free").
- Mixed up two touching objects (the wrong bin, seed 2002): a red triangle and a blue cube touched, the id `obj_3`
  moved to the cube between looks, and the "red" label from the first look stayed with the id, so the cube went to
  the red bin.
- Retries push episodes to the limit: 3 ended 3–6 s before 120 s. On the real robot each Gemini wait adds its full
  length.

**Largest gains:** for both, a grasp that holds triangles near the robot (or sliding them out to where face grasps
plan). For the agent, not repeating a failed (arm, grasp) pair and the ridge grasp for lying triangles (items 1–2
below). For v1.5, a clearance check against close neighbours on the approach.

**Own scenes** (not comparable with each other):

| Policy | Scene | Task | Sorted |
|---|---|---|---|
| Marcus's agent, `s2` | Aalto's look, nominal, seeds 2000–2004 | sort_fixed | 11/21 |
| Marcus's agent, `s2` | Aalto's look, nominal, seeds 1000–1004 | sort_language | 11/18 |
| Marcus's agent, earlier runs (`t1-*`, `var-*`) | real colours + `--dr wide` | both | 5/12 – 8/21, wrong-bin drops |
| Marcus's agent, `t2-venue-*` | real colours as the camera sees them (`--colors venue`) + `AALTO_DR=train` | both | 3/21, 4/20 |
| v1.5, sides off (e-030) | **our venue look** (camera 10° lower, 7.5 cm walls, scattered objects), seeds 1000–1005 | sort_fixed | **23/27** (Aalto's oracle there 22/27, v1.4 20/27, baseline 0/14 on 1000–1002) |
| v1.5, strict (e-029, e-031) | our venue look | sort_fixed / sort_language | 20/27 / 22/28 |

Note on names: Marcus's `venue` scene (`sim/modal_sim.py`, `SCENES["venue"] = ("--colors venue", "train")`) means
the real object colours plus Aalto's `train` randomisation. It is not our venue look (`sim/venue_look/`). His
`s1` sweep has some seeds recorded twice (a reused container kept an earlier result), so only `s2` is quoted above.

## Reading

- **Facts:** both drive the same oracle motions from the head camera. In Aalto's look with randomisation Marcus's
  agent sorts 18/20, one more than Aalto's oracle with exact poses. In our venue look v1.5 sorts 23/27, one more than
  Aalto's oracle there. Side by side in the venue look on the same 12 episodes (e-038…e-040): v1.5 sides off
  47/55, the agent with the camera fix 43/55. Within run-to-run spread, so about level; the agent's weakest shape
  there is triangles (1/5 on sort_fixed).
- **Opinion (Emīls + Claude, not a team decision):** v1.5 is the safer submission. It needs no network and no key in
  the image, the image is built, and it scores at the oracle's level. The ADK agent is the stronger pitch story
  (Gemini looks at the scene and calls skills, any instruction wording), but at the finals a failed or slow call
  costs the episode and an image would carry the API key. If its 18/20 in Aalto's randomised look holds up against
  v1.5 on the same seeds, ideas worth taking into v1.5 without a model: the arms-aside parking and 12 cm clearance,
  trying every grip angle on triangles, choosing the next object while carrying.

## What from v1.5 could go into the ADK agent (for Marcus)

Checked against his repo at 1a51d7b. Only what his agent does not already have; file names on his side are in
`adk_agents/robot_sorter/`.

1. **Grasp along the ridge for lying triangles (largest gain).** His `shape.py` returns `"tipped"` with no
   direction, and `look` only tells the model "lying on its side"; no tool has a grasp for it. v1.5 takes the ridge
   direction from the top-strip points (`ridge_yaw`, `classify_top_v15` in `upgrades_v15.py`: 0.8° median error,
   47 of 48 lying triangles found, offline on 115 frames) and pinches across the two triangular end faces
   (`SidedPlanner._plan_side_faces`: only yaw and yaw + 180°, within 95° of the finger reference). Held 4 of 9 lying
   triangles, the stock claw 0 of 14 (e-032, small sample). To port: return the ridge yaw from `shape.py`, and give
   the tools a "tipped" grasp that tries only those two faces. Passing it as a cube with that yaw is not the same:
   the cube grasp may choose the sloped faces, which squeeze the block up out of the fingers.
2. **Do not repeat a failed pick.** After a miss his tools only step to the next triangle grip angle
   (`robot.tries`, `TRIANGLE_GRIPS_DEG`); otherwise the model chooses again and may repeat the same arm and grasp.
   v1.5's failure memory (`upgrades.py` memory chooser) tries a different arm / grasp pair on an object after one
   fails. That is where the sort_language gain came from (e-015: second tries 8/11, against 5/11 without it). To
   port: list the failed (arm, grasp) pairs in each object's `look` entry, or have `pick_and_place` skip them unless
   the model names them.
3. **Head-camera fit in the venue look.** `headpose.py` copied our fit and added `plausible()`, which rejects
   shifts over 6 cm. In our venue look the fit reports about −8 cm while the camera moved about 2 cm, so the right
   fit is thrown away there, and probably on the real robot (camera about 10° lower). v1.5 uses the fit whenever it
   succeeds (part of its 23/27 there). To port: relax the shift limit, or use Samer's `camera_move_ok`
   (`policy/policies/classical_v14.py`). **Done in our copy** (`modal_pipeline/adk_agents/robot_sorter/headpose.py`
   `camera_move_ok`, used by `robot.py`; `ROBOT_HEADPOSE_CHECK=shift` restores the old limit) and used in e-038 and
   e-039; not yet in Marcus's repo. Samer's pre-submission image applies the same limit to Marcus's code at build
   time (`policy/adk/patch_headpose.py`), so e-038 and e-039 measure the logic that image runs.
4. **Evidence: do not let Decision 1 overrule "tipped".** His `decisions.py` lets Decision 1 call a block "other:
   lying on its side". On 59 crops the geometry called lying (`test_tipcheck.py`), Decision 1 caught 2 of 11 wrong
   "lying" labels and turned 3 really lying blocks into upright (Hydrogen: 5 of 11, flipped 4, 3.2 s). The
   geometry's "tipped" should win.

Not worth porting: same-side arms (his arm parking and 12 cm clearance cover collisions; the side rule cost v1.5
3 objects), the option search and the relay limit (his `check_plan`, `choose_arm` and `hand_over` tools cover them).

Shared problem, not a fix: lying cylinders are read as "cube" (19 times in the offline test), in `classify_top`,
which both use; a fix there helps both.

## Open

- v1.5 on Aalto's look with randomisation (running, Samer) and with real colours (not run).
- ~~Marcus's agent in our venue look with its current version~~: done, e-038 and e-039 (with the camera fix).
  Not run: the agent in the venue look without the fix, or with randomisation.
- Whether the finals sim uses Aalto's look, our venue-like look, or something else (Aalto: held-out variant).
