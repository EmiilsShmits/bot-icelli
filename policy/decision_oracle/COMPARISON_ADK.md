# v1.5 (decision oracle as a policy server) vs Marcus's ADK agent

Written Sat 14 Nov ~20:30 by Emīls + Claude. Sources: our `eval/RESULTS.md` (e-004, e-028…e-033), Marcus's repo
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
| v1.4 | | 12/15 after 4 seeds |
| **v1.5** | not run | **running** on `samer-v1-sim` (seeds 1000–1009, strict and sides off, `eval/v15_lane.sh`) |

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
  Aalto's oracle there. The two have not yet been run in the same scene; Samer's v1.5 lane on `samer-v1-sim` is
  the first such comparison.
- **Opinion (Emīls + Claude, not a team decision):** v1.5 is the safer submission. It needs no network and no key in
  the image, the image is built, and it scores at the oracle's level. The ADK agent is the stronger pitch story
  (Gemini looks at the scene and calls skills, any instruction wording), but at the finals a failed or slow call
  costs the episode and an image would carry the API key. If its 18/20 in Aalto's randomised look holds up against
  v1.5 on the same seeds, ideas worth taking into v1.5 without a model: the arms-aside parking and 12 cm clearance,
  trying every grip angle on triangles, choosing the next object while carrying.

## Open

- v1.5 on Aalto's look with randomisation (running, Samer) and with real colours (not run).
- Marcus's agent in our venue look with its current version (only the older `t2-venue-*`, which also used
  randomisation).
- Whether the finals sim uses Aalto's look, our venue-like look, or something else (Aalto: held-out variant).
