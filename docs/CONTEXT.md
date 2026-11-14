# Team context: read this first

**Last updated:** Sat 14 Nov 2026, ~19:10 Helsinki time, by Samer + Claude. If you change something this file describes, update it in the same commit.

**Every statement here is one of three kinds:**
- **FACT**: measured by us, or said by the organisers. Each one names its source and time. Numbers come from `eval/RESULTS.md` and the linked files; check there before you build on one.
- **OPINION (Samer + Claude)**: what Samer and Claude recommend. A proposal to argue with, not a team decision. Decisions go in [`DECISIONS.md`](DECISIONS.md).
- **OPEN**: nobody knows yet.

**AI agents:** treat FACT as true unless a newer source says otherwise (then point out the conflict). Never present an OPINION as decided. Ask a human about OPEN items that affect judging.

## 1. The situation in five lines
1. **FACT:** we hand Aalto one Docker image. Finalists are picked from a sim run on a held-out variant; the finals run on the real robot on Sunday. Aalto posts the hand-in form, team IDs and deadlines on Discord "this evening" (erkka, Sat 15:07).
2. **FACT:** Junction's project page closes Sun 15 Nov 10:00 (official schedule).
3. **FACT:** our candidates are v1 … v1.4 in `policy/`, all built on Aalto's classical baseline. Their images are built and pass Aalto's replay test. In the nominal sim v1.2 and v1.3 sort 26/40, the same as the baseline; runs with randomisation and in the venue look are going (§4.3).
4. **FACT (Samer, Sat ~17:00):** Samer + Claude do the final integration and build the final image from what the team produces.
5. **OPINION (Samer + Claude):** v2 = Gemini Decision 1 reads the instruction (with offline fallbacks) + the best "hands" we can measure (v1.x vs Emīls's `policy/decision_oracle` in camera mode). Gemini does not drive the robot.

## 2. Deadlines, submission, network (FACT)
| What | Fact | Source |
|---|---|---|
| Junction project page | closes Sun 15 Nov 10:00 | official schedule |
| Aalto image deadline | not announced yet; form, team IDs and deadlines come "this evening" on Discord | erkka, Sat 15:07 |
| Finalist selection | sim run on a held-out variant: other textures, lighting, object poses, camera jitter, secret seeds | Aalto brief |
| Internet during the finalist sim run | yes | Samer, Sat ~17:00 |
| Internet on the finals PC | yes, but a failed or slow call still counts as a failure, with no rerun | Aalto to Samer, Sat ~12:50 |
| Finals PC | RTX 5090 on ethernet; tell Aalto early if the image is big | erkka, Sat 09:47 |
| Image contract | linux/amd64, CUDA ≥ 12.8, server on :8000 within 120 s, ≤ 32 GB VRAM, ≤ 40 GB image, weights inside | Aalto docs |
| Sim gate | 0 clipped steps; ≥ 27 commands/s on the sim clock and by the policy's own latency; no abort, crash or lost connection | Aalto docs |
| Real-robot test before the finals | no answer, so assume none. A few exceptional teams may deploy through a Wendy agent (DM erkka) | erkka, Sat 14:39 |

How to hand in: [`runbooks/submit.md`](runbooks/submit.md). Hard rules for code: `AGENTS.md`.

## 3. The task on the real robot (FACT, organisers)
- **Objects:** 4.5 cm cubes, triangular prisms and cylinders in **orange, yellow, purple** (the sim uses red, yellow, blue). Prisms may lie on a face or on a side; count, colours and placement are random. (erkka, Sat 15:07)
- **Real rung 1 (sort_fixed): yellow → left, purple → center, orange → right.** The sim's rung 1 is red → left, yellow → center, blue → right. So always read `obs["instruction"]`. (erkka, Sat 15:07)
- **Instructions** may name colour, shape or both. Colour comes first; shape only if several teams handle colour. No negation. (erkka, Sat 01:00 and 15:07)
- **Episode:** 120 s, arms at home, hands open, head depth available. (erkka, Sat 15:07)
- **Scoring:** sort_fixed +1 / −1 per object; sort_language +2 / −1; knocked off the table −1; left on the table 0. (Aalto docs)
- **Layout:** the values in Aalto's INTERFACE.md are a plan until measured at the venue. (erkka, Sat 15:07)

## 4. What we measured (FACT)
### 4.1 Aalto's real-robot data
- **Colours in the robot's head camera** (OpenCV hue 0–180): orange objects 11–13, yellow 34–46, purple ~110 (reads as blue), orange boxes 4–7. Aalto's stock baseline misses orange and most yellow. ([`research/aalto-discord-notes.md`](research/aalto-discord-notes.md))
- **The real head camera looks ~10° further down than `calibration.yaml`** (7.9° and 12.2° in the two datasets), and the bin walls are ~7.5 cm, not 6. Emīls's fit can't tell a tilted camera from a leaning torso. ([`../sim/venue_look/README.md`](../sim/venue_look/README.md))
- **Aalto's demos break the speed caps:** arms 2–4 rad/s (cap 1), fingers up to 25 rad/s (cap 3). Retime before training on them. ([`research/real-data-findings.md`](research/real-data-findings.md))
- At the same joint angles, the real hand sits 4–6 cm closer to the robot than the sim hand. (venue look README)

### 4.2 Reading the instruction (Emīls, [`../training/instruction_parser/RESULTS.md`](../training/instruction_parser/RESULTS.md))
| Method | Aalto's templates | unseen wording (T2a): exact / confidently wrong | hard wording (T2b): exact / confidently wrong |
|---|---|---|---|
| Rule parser (in v1) | 100 % | 86.7 % / 3.2 % | 60.1 % / 6.6 % |
| Gemma 3 1B, fine-tuned, offline | 100 % | 94.7 % / 0.9 % | 90.6 % / 8.0 % |
| Gemini Decision 1 (API) | 100 % | 91.7 % / **0.0 %** | 93.9 % / 0.9 % |
| Gemini → Gemma 1B → rules | 100 % | **98.5 %** / 0.6 % | **98.1 %** / 1.9 % |

- **"Gemini" in our docs means Gemini Decision 1** (`gemini-decision-1`, Google's Decisions API). It answers multiple-choice questions with a confidence instead of writing text; the parser asks "where does a red cube go? left / center / right / leave" for each object type, plus "is this instruction invalid?".
- It **refused all 21 orange/purple test items**, because its prompt says the colours are red, yellow and blue. That needs fixing now that Aalto confirmed the real names.
- Speed: median 0.44 s, p95 0.84 s, worst 3.05 s (900 calls from Helsinki); about $0.11 per 900 calls. With a camera image attached, as in decision_oracle: median ~0.63 s, worst ~1.3 s.
- Gemma 3 1B student: 0.14 s on the GPU (1.6 s on 8 CPU threads), 2.0 GB VRAM, 2.0 GB of weights, 9.5 s from a cold disk to the first answer.

### 4.3 Sim scores ([`../eval/RESULTS.md`](../eval/RESULTS.md))
| Run | Policy | Sim / task / trials | Objects sorted | Notes |
|---|---|---|---|---|
| e-008 | Aalto's classical baseline, camera only (a valid submission) | nominal, sort_fixed, 10 | 26/40 (65 %), gate PASS | **far cross-body objects 2/9**, the rest 24/31 |
| e-010 | **Aalto's oracle**, launched as "v1" by mistake (`--container` without `--policy` runs the oracle) | nominal, sort_fixed, 10 (same seeds as e-008) | 32/40 (80 %) | **not v1**. Useful as the exact-pose reference on the baseline's seeds |
| e-011 | Aalto's classical baseline | `AALTO_DR=train`, sort_fixed, 10 | 11/40 (28 %), gate FAIL | 2 safe-stops right after time-limit episodes (blocking `reset()`, fixed in our versions) |
| e-023 | **v1.2**, the real image | nominal, sort_fixed, same seeds as e-008 | 26/40 (65 %), gate PASS | **the same as the baseline**; seed 1004 0/5 |
| e-024 | **v1.3** (+ free drop spot per bin) | nominal, sort_fixed, same seeds | 26/40 (65 %), gate PASS | the same again. No lost object rests on another one any more (baseline 5 of 14), but **13 of its 14 lost objects end closer than 27.5 cm to the pelvis**; 6 episodes end early with objects still seen but given up |
| e-025 | **Aalto's oracle**, launched as "v1.2" on sim B by an old `compare.sh` | `AALTO_DR=train`, sort_fixed, same seeds | 32/40 (80 %), gate PASS | **the same as nominal (e-010)**: randomisation hurts camera-based perception, not the physics |
| running | v1.3 with randomisation; then v1.4 | `AALTO_DR=train`, sort_fixed, same seeds | 11/15 after 4 seeds (baseline 9/15, oracle 13/15 on those) | the finalist-like test |
| running | v1.3, the baseline, then v1.4 in the venue look (sim C) | venue look, sort_fixed, seeds 1000–1005 | — | same seeds as e-004 … e-022 |
| e-001 | Aalto's oracle (exact object poses from the sim: **not a valid submission**) | nominal, sort_fixed, 3 | 11/12 (92 %) | no triangles in those layouts |
| e-004 | Aalto's oracle | venue look, sort_fixed, 6 | 22/27 (82 %) | triangles 2/5 |
| e-005 | oracle + Gemini Decision 1 choosing the next move | same seeds as e-004 | 23/27 (85 %) | one object more is noise |
| e-006 | decision_oracle with **camera-only** perception | venue look, 2 seeds | 6/9 | same per seed as with exact poses |
| e-007 | Aalto's oracle | venue look, sort_language, 6 | 20/28 (71 %) | |
| e-009 | oracle + Gemini Decision 1 choosing | same seeds as e-007 | 21/28 (75 %) | noise again |

Other measurements:
- Aalto's own numbers for their classical baseline: 76–82 % in their nominal sim (seeds 0–7). (`third_party/…/baselines/classical/README.md`)
- Aalto's oracle over 125 recorded episodes (Marcus): cubes 97 %, cylinders 91 %, **triangles 35 %**. Best π0.5 checkpoint: 3 of 12 objects. ([`../modal_pipeline/TEAM_HANDOVER.md`](../modal_pipeline/TEAM_HANDOVER.md))
- **Triangles with the stock claw grasp hold in 1 of 15 picks**; face-aligned grasps held 5/5 cubes and 1/1 triangle. (Emīls, e-005/e-006)
- Camera-only perception (Emīls): 2.5 mm median position error, shape right on 153 of 162 objects, head-pose re-fit 9.79° ± 0.02° on venue-look frames.
- Grasp check signal (Emīls, 40db2e6): after closing, an empty hand reaches the commanded finger angles within 0.000–0.010 rad; a held block stops the fingers 0.021–0.100 rad short. Measured in sim since: right on all 11 aborts (e-013) and on 146 of 147 logged picks ([`research/model-monitor-oracle.md`](research/model-monitor-oracle.md)). The trace of 215 grasps in `eval/analysis/` shows the same split.
- **What fails, grasp by grasp** (Samer + Claude, [`../eval/analysis/FINDINGS.md`](../eval/analysis/FINDINGS.md); baseline, baseline with `AALTO_DR=train` and the oracle on the same 10 seeds):
  - **Second object into the same bin:** Aalto counts an object only if its centre is below the bin's 6 cm rim. The baseline drops every object at one fixed point per bin, so the next one lands on the first. Only 2 of 8 such drops scored: 6 of the baseline's 14 lost objects.
  - **Empty grasps:** baseline 49 % of grasps, 70 % with DR, the oracle 34 %. In the nominal sim the planned grasp point is as close to the object for empty grasps as for held ones.
  - **Second tries hold less than first tries:** 37 % vs 58 % (baseline).
  - **Cylinders, first grasp held:** baseline 53 %, oracle 89 %.
- **Emīls's decision_oracle with camera-only perception + upgrades, venue look** (e-019, e-022): sort_fixed 21/27, sort_language 26/28 (Aalto's oracle with exact poses: 22/27, 20/28). Runs in-process inside Aalto's evaluator, not as a policy server.
- **Marcus's ADK agent** (Gemini 4 Hydrogen calling oracle-based skills, camera perception; Modal, from `sim_out/` in his repo): nominal sort_fixed seeds 1000–1004: 14/20 and 17/20 in two runs (Aalto's baseline 16/20, his rule-based skill policy 16/20 on the same seeds there); sort_language seeds 1000–1002: 6/11 and 9/11. **With real colours and `--dr wide`** (`sim/scene_variant.py`): 7/21, 8/19 and 8/20, with 3–4 objects in a wrong bin per run (−1 each). Every move waits 3–4 s for the model.
- **v1.2's head-camera re-fit rejected its own correct fit in the venue look** (Sat ~19:00, sim C): tilt 9.8°, reported "shift −8.3 cm" > the 6 cm limit, but the camera itself moved only 1.9 cm (the plane fit tilts the pose about the pelvis origin, the bin fit moves it back). v1.2/v1.3 then perceive the venue look with a camera ~10° off: on one frame v1.3 finds 11 "objects" (bins among them, at wrong heights), v1.4 (fixed) exactly the 6 objects. In the nominal and randomised sims all 25 logged fits were accepted, so this only bites in the venue look, and on the real robot if its camera is really tilted.
- Sim speed: one sim on the RTX PRO 6000 machine runs at 0.52× real time, two or three on one machine at 0.17–0.48×. Scores pace on the sim clock, so speed doesn't change results.

### 4.4 Submission candidates (`policy/`)
| Version | Adds | Status |
|---|---|---|
| v1 | Aalto's classical baseline + reads the instruction (rule parser, orange/purple names) + real-colour HSV ranges + speed guard (0.98 / 2.7 rad/s) | image 1.46 GB; Aalto's replay test: 100 calls, 0 errors, 5.5 ms median, server up in 0.55 s |
| v1.1 | far cross-body objects are first moved by the near arm, then finished by the bin-side arm; at most 3 tries per object | image built; nominal run going |
| v1.2 | v1.1 + re-fits the head-camera pose from depth at each episode's first look (Emīls's fit): corrects ~1° in the nominal sim, ~2° with randomisation. **Rejects the ~10° fit of the venue look** (see §4.3) | nominal 26/40 = baseline (e-023) |
| v1.3 | v1.2 + a free drop spot per bin (`eval/analysis/FINDINGS.md` §1) | nominal 26/40 = baseline (e-024); stacking gone. Running with randomisation and in the venue look |
| v1.4 | v1.3 + grasp check at the end of the lift (empty: skip the carry, go home, look again) + a retry with another arm / finger direction + the head-fit check fixed | image `cd8311e9f64e`, 26 tests, replay test passes. Queued with randomisation and in the venue look; not yet in the nominal sim |
| all three | `reset()` never blocks (a blocked reset made Aalto's baseline fail the gate once on our loaded machine) | 80d7c9a |

`policy/decision_oracle/` (Emīls) is **exploration, not in the image**: Aalto's oracle split into motion functions, choosers (Aalto's rule, Gemini Decision 1, random, prefer-face, memory), camera-only perception and a grasp check. It runs inside Aalto's evaluator, not yet as a policy server.

## 5. Machines and money (FACT)
- **Samer's Verda account:** `samer-v1-sim`, spot RTX PRO 6000 (96 GB, 30 vCPU) in FIN-03, €1.28/h, billing until deleted. Verda can take a spot machine back at any time; [`../sim/install_bare_metal.sh`](../sim/install_bare_metal.sh) rebuilds one in ~11 min. Runs there live in tmux; the scripts are in `eval/` (`compare.sh`, `summarize.py`, `queue.sh`, `replan.sh`). Its IP is in Samer's local `.env` (`VERDA_SIM_HOST`), not in the repo.
- **Emīls's Verda account:** `bot-icelli-sim` (venue look, decision_oracle runs).
- **Marcus:** Modal workspace (sim on L40S, π0.5 training on B200), `modal_pipeline/`.
- Every member has €200 of Verda credits on their own account; a machine bills to whoever created it.
- **This repo is public.** Keys go only in a local `.env`, never in code, logs or a public image.

## 6. Recommendations (OPINION, Samer + Claude)
### 6.1 Getting to the final image
- Always have a working image handed in: v1.x as soon as Aalto's form opens.
- A new version replaces it only if, on the same sim seeds, it passes the gate and scores higher on both tasks, ideally also with `AALTO_DR=train`, the closest thing we have to the held-out variant. `eval/compare.sh` runs that side-by-side.
- One submission path: each version is an entry in `policy/server.py` (v1, v1.1, v1.2, v2 …), never a separate server.
- Samer + Claude integrate. Everyone else hands over a working piece with a test and a sim number.

### 6.2 What v2 should look like
1. **Reader** (once per episode, in a background thread, never blocking `act()`): Gemini Decision 1 (2 s limit) → Gemma 3 1B inside the image → rule parser → fixed mapping. Gemini's answer is used as it comes (0 % confidently wrong on colour-only wording). Gemma's answer is used only when the rule parser agrees or can't read the sentence (Gemma is 8 % confidently wrong on hard wording). First fix the orange/purple refusal.
2. **Hands** (all offline): whichever measures best, v1.x or decision_oracle in camera mode. Worth adding to either: a free drop spot in each bin (the cheapest fix found, `eval/analysis/FINDINGS.md`), face grasps for triangles (prefer-face / memory chooser), the finger-angle grasp check with a retry, and the head-pose re-fit (already in v1.2).
3. **Pacemaker:** `act()` answers 30 times a second from the planned motion, or holds. It never waits on the network.

### 6.3 Where Gemini helps, and where it doesn't
- **Helps: reading the instruction** (measured, §4.2). A wrong reading sends every object to the wrong bin: with 4 objects that's −4 instead of +8.
- **Doesn't: choosing the next move.** Measured twice: 23/27 vs 22/27 and 21/28 vs 20/28. Keep it off in the scored image; fine in the pitch.
- **Untested, so not in the plan:** "Gemini 4 Hydrogen" and Gemini Robotics-ER 2. Measure them first, on Emīls's test sets or saved frames. (This updates `STRATEGY.md`, which still suggests Robotics-ER for live use.)
- **The Gemini key inside the image** can be read by anyone who has the image. Use a separate key with a spending cap, revoke it after the event, never push the image to a public registry, and ask Aalto whether they can pass the key as an environment variable instead.

### 6.4 Tiya's agent plan ([`implementation_plan.md`](implementation_plan.md))
- **Keep:** Gemini Decision 1 + the rule parser at reset, better grasps and re-grasp, the fallback chain, never blocking `act()`. Its claim that Gemini Decision 1 takes camera images is now confirmed by Emīls's runs (0.6 s median, not "~200 ms").
- **Skip for the submission:** Gemini choosing every cycle (no gain measured), `push_clear` (risks −1 knock-offs), the React workbench (it scores nothing; show real sim runs in the pitch instead), the π0.5 skill (3/12 objects).

### 6.5 Other calls
- **π0.5:** not in the scored path for now (best 3/12 objects). Marcus's Modal pipeline stays useful for data and the pitch.
- **Tech challenges:** Verda (our sims run there), Gemma (offline parser student), Gemini (Decision 1 parser, once v2 is in). Skip the rest unless there's spare time. Details: [`STRATEGY.md`](STRATEGY.md) §8.

### 6.6 Risks we see
- **Triangles:** the biggest loss in sim (stock claw 1/15).
- **Far cross-body objects:** 2/9 in the baseline; v1.1 targets them.
- **Second object into a bin:** fixed in v1.3 (no lost object rests on another one, e-024).
- **Objects near the robot (pelvis x < ~0.28 m):** where v1.3 loses almost everything it loses (13 of 14, e-024). Failed grasps push objects towards the robot, where they sit at the bottom edge of the head camera's view and partly behind the hands at the home pose. v1.4's grasp check and new-grasp retry are the first step; a nudge outwards or a different approach for close objects is the next.
- **The venue look is our best stand-in for the real robot, but it assumes the camera is tilted on its mount.** If the robot leans instead (the hand in Aalto's footage sits 4–6 cm lower in the head image than the venue look predicts, about the same angle), a camera re-fit alone would put the arms several cm off on the real robot, and the venue look can't show that. Check it on Aalto's real data (project the hands from the recorded joint angles through both camera poses) or on the robot.
- **Real robot, none of it tested there:** camera ~10° off (v1.2 targets it), the hand sits 4–6 cm closer than in sim, real depth noise and holes, bins maybe not where `scene.yaml` says.
- **Infrastructure:** the spot machine can vanish (reinstall: 11 min).

## 7. Open questions (OPEN)
- **Aalto:** the image deadline and hand-in form (expected tonight); whether they can pass an API key as an environment variable; how distractors are scored.
- **Real camera:** is the camera mounted tilted, or is the torso leaning? This decides whether the head-pose re-fit is right on the real robot. Comparing the hands' projected and seen positions in the head camera could tell.
- **Sim runs going (Sat ~19:10):** does v1.3 hold up with randomisation (11/15 after 4 seeds)? Does v1.4's grasp check pay off there and in the venue look? How does v1.4 in the venue look compare with decision_oracle in camera mode on the same seeds (21/27, e-019)?
- **Gemma inside the image:** size, and start-up within the 120 s limit, are untested.

## 8. Repo rules added today (FACT)
- **No AI co-author lines in commits or PRs** (`Co-Authored-By: Claude …`, "Generated with …", `Claude-Session:`): GitHub listed "Claude" as a contributor of this repo because of them. Guards: `.claude/settings.json`, `.githooks/commit-msg`, `make setup`, and the rule in `AGENTS.md` (c239100).
- Older commits still carry such lines. Samer may have the history cleaned (messages only; same files, authors and dates). If that happens, run `git pull --rebase` once; a plain `git pull` would bring the old commits back.
