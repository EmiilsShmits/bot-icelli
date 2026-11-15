# Team context: read this first

**Last updated:** Sun 15 Nov 2026, ~03:50 Helsinki time, by Samer + Claude (§4.1 our pre-submission on the real robot; §4.3 image gates and task 3; §4.4; §1–2 still as of Sat evening). If you change something this file describes, update it in the same commit.

**Every statement here is one of three kinds:**
- **FACT**: measured by us, or said by the organisers. Each one names its source and time. Numbers come from `eval/RESULTS.md` and the linked files; check there before you build on one.
- **OPINION (Samer + Claude)**: what Samer and Claude recommend. A proposal to argue with, not a team decision. Decisions go in [`DECISIONS.md`](DECISIONS.md).
- **OPEN**: nobody knows yet.

**AI agents:** treat FACT as true unless a newer source says otherwise (then point out the conflict). Never present an OPINION as decided. Ask a human about OPEN items that affect judging.

## 1. The situation in five lines
1. **FACT:** we hand Aalto one Docker image. Finalists are picked from a sim run on a held-out variant; the finals run on the real robot on Sunday. Aalto posts the hand-in form, team IDs and deadlines on Discord "this evening" (erkka, Sat 15:07).
2. **FACT:** Junction's project page closes Sun 15 Nov 10:00 (official schedule).
3. **FACT:** our candidates are v1 … v1.4 in `policy/`, all built on Aalto's classical baseline. Their images are built and pass Aalto's replay test. **v1.4 and v1.3 are public on GHCR** (§2). In the nominal sim v1.x sort 26–29/40 like the baseline; **with randomisation v1.3 keeps 26/40 and v1.4 sorts 29/40 while the baseline falls to 11/40**, and in the venue look v1.4 sorts 20/27 (§4.3). **v1.5 is a different base** (Aalto's oracle motions on the head camera + decision_oracle upgrades, `policy/policies/oracle_v15.py`): in the venue look 23/27 with either arm anywhere and 20/27 with same-side arms (e-030, e-029, Modal); **with randomisation in Aalto's look 33/40 with sides off (e-037), our best**; strict sides running. Strict v1.5 is on GHCR as the pre-submission backup: `ghcr.io/samer-cyber/bot-icelli-policy:presubmit-v15-1` (`sha256:be601037877f98b07b779394d8455443bc4eb87d420458874a70dca7dd057222`).
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

How to hand in: [`runbooks/submit.md`](runbooks/submit.md). Hard rules for code: `AGENTS.md`. A session on the real robot: [`runbooks/real-robot.md`](runbooks/real-robot.md) (what to tell Aalto, what to measure, a look-only first run). Fast sims on Modal (Marcus's pipeline, every seed at once) from a Windows laptop: [`runbooks/modal-windows.md`](runbooks/modal-windows.md).

**Our images (public, pushed Sat evening from `samer-v1-sim`):**
- v1.4 (candidate): `ghcr.io/samer-cyber/bot-icelli-policy@sha256:cd8311e9f64ea25703d9c70a645b44091dc5a00d8b5f75dc54f29720f6fd7f8d`
- v1.3 (fallback): `ghcr.io/samer-cyber/bot-icelli-policy@sha256:60ef1b8980de11f9448da5de27234bf3d9f3b3be682f1914a2c0532c2ed504c4`
- look (never moves, logs perception; first real-robot run): `ghcr.io/samer-cyber/bot-icelli-policy@sha256:f4f871b526254bc8a173f0613a27bf963b0522a50d30ed290abf261d78993aed`

## 3. The task on the real robot (FACT, organisers)
- **Objects:** 4.5 cm cubes, triangular prisms and cylinders in **orange, yellow, purple** (the sim uses red, yellow, blue). Prisms may lie on a face or on a side; count, colours and placement are random. (erkka, Sat 15:07)
- **Real rung 1 (sort_fixed): yellow → left, purple → center, orange → right.** The sim's rung 1 is red → left, yellow → center, blue → right. So always read `obs["instruction"]`. (erkka, Sat 15:07)
- **Instructions** may name colour, shape or both. Colour comes first; shape only if several teams handle colour. No negation. (erkka, Sat 01:00 and 15:07)
- **Episode:** 120 s, arms at home, hands open, head depth available. (erkka, Sat 15:07)
- **Scoring:** sort_fixed +1 / −1 per object; sort_language +2 / −1; knocked off the table −1; left on the table 0. (Aalto docs)
- **Layout:** the values in Aalto's INTERFACE.md are a plan until measured at the venue. (erkka, Sat 15:07)
- **The boxes will be glued closer to the robot** before the finals, by about 7 cm. (Aalto, said to Emīls, Sun ~02:00; the 7 cm is Emīls's recollection, not a published number)
- **Shape putting (rung 3) on the real robot uses a printed lid on the MIDDLE box**: `lid_shape_holes_200mm.stl` (in the repo as `sim/task3/lid_shape_holes_200mm.stl`), 200 × 200 × 4 mm with a square, a round and a triangular hole. (Aalto, file given to Emīls, Sun ~02:10.) Aalto's sim has another lid (210 mm, other hole places) on the LEFT box. The brief calls rung 3 a stretch, "real robot only as a bonus".
- **The real arms sag without feed-forward torque; a policy can now send it** (Aalto's PR #4 to aaltonomous-humanoid, "Action key `arm_tau_ff`"; erkka on Discord, Sun 04:18: "merged"; on GitHub still open at 04:35). On the robot the arm controller clips each target to ±0.12 rad of the measured angle at kp 80, so it holds ~9.6 Nm at most: an arm stretched ~0.5 m forward needs ~10 Nm at the shoulder and **sinks 15–18 cm**. The optional action key `arm_tau_ff` ((14,) or (k, 14) Nm, rows as `arm_q_target`) goes to the arm motors; the runner clamps it to ±15 Nm (shoulder, elbow) / ±2.5 Nm (wrist); the Isaac sim and the mock ignore it; old runners drop it. The teleop that recorded Aalto's demos sends gravity compensation. **Ours since 3768226** (`policy/gravity_ff.py`, on by default, every policy and the ADK image).

## 4. What we measured (FACT)
### 4.1 Aalto's real-robot data
- **Colours in the robot's head camera** (OpenCV hue 0–180): orange objects 11–13, yellow 34–46, purple ~110 (reads as blue), orange boxes 4–7. Aalto's stock baseline misses orange and most yellow. ([`research/aalto-discord-notes.md`](research/aalto-discord-notes.md))
- **The real head camera looks ~10° further down than `calibration.yaml`** (7.9° and 12.2° in the two datasets), and the bin walls are ~7.5 cm, not 6. Emīls's fit can't tell a tilted camera from a leaning torso. ([`../sim/venue_look/README.md`](../sim/venue_look/README.md))
- **Relative to the arms, the real head camera is within ~2° of `calibration.yaml`; the rest of the 10° is the torso leaning towards the table** (Emīls + Claude, Sun 15 Nov ~02:00, `eval/analysis/real_hands/`). We projected the Dex3 hand model (URDF forward kinematics from the recorded `observation.state`) into all 61 saved real head frames of both drops and scored how much of it lands on the black hand pixels.
  - Aalto's calibration as-is: 5.6 px mean distance, 60 % on the hand.
  - The venue look's camera, 9° further down on its mount: worse (9.2 px, 48 %).
  - Best single turn: 2.25° down, 2.25° yaw, 2° roll (3.1 px, 73 %). Each drop alone gives the same turn within 0.75° (pick_cube 2.5° down, drop 2 1.75° down), although their tables look tilted by 7.9° and 12.2°.
  - So the camera-to-arm geometry stays put, and the table's tilt changes with the robot's posture.
  - This explains the "hand sits 4–6 cm closer than in sim" note (the venue look put the tilt in the camera), and it fits the venue note that the robot leans against the table.
  - **Confirmed with real head depth (drop 3), Sun ~03:30:** two independent arm fits (ours and Marcus's `selfcal.py`) put the camera within ~2° and ~2 cm of its calibration, and the table rising 12.7–14.3° away from the robot in the arm frame. Single frames scatter by ~2°. Comparison of the three team methods: [`../eval/analysis/real_hands/COMPARISON.md`](../eval/analysis/real_hands/COMPARISON.md).
- **Aalto's demos break the speed caps:** arms 2–4 rad/s (cap 1), fingers up to 25 rad/s (cap 3). Retime before training on them. ([`research/real-data-findings.md`](research/real-data-findings.md))
- At the same joint angles, the real hand sits 4–6 cm closer to the robot than the sim hand. (venue look README) Explained by the item above: the venue look tilts the camera instead of the torso.
- **Tape-measured at the venue** (team, Sat 14 Nov):
  - head camera lens 48 cm straight above the table top (the URDF default puts it at 46.4 cm);
  - bins 7 cm tall (Aalto's `scene.yaml`: 6 cm), about 5 cm apart, near edge 30 cm from the table edge;
  - the robot leans against the table edge. Its distance to the table edge is not measured; 10 cm puts the bins at
    Aalto's published 40 cm from the torso.
  - Used by the MuJoCo scene ([`../sim/mujoco/venue_measured.yaml`](../sim/mujoco/venue_measured.yaml)).
- **Our pre-submission on the real robot misses its grasps** (Aalto's pre-submission video, Sun ~03:20; Samer +
  Claude, frames 17–18 s and 35–36 s): almost certainly `presubmit-adk-1` (Marcus's agent: arms parked out to the
  side between moves). The robot hangs from the crane, head camera ~50 cm above the desk (Samer; the sim assumes
  46.4 cm). It reaches for the purple cube with the right hand twice; both times the fingers land on the table about
  a hand-width beside the cube, on the side towards the robot's right hand, and close on nothing. The cube never
  moves. Samer: every team's run showed an offset. Fits the hand-offset analysis (torso leaning 5–10°, right hand y
  −2.9 cm; [`research/hand-offset-real-data.md`](research/hand-offset-real-data.md)) and Marcus's drop-3 check (table
  tilted 12.3°, 6–8 cm further than `scene.yaml`). Every image we have aims in the table-fitted camera frame.
- **The real boxes measured from head depth** (drop 3, 15 frames; Emīls + Claude, Sun 15 Nov ~02:50, [`../eval/analysis/real_depth/README.md`](../eval/analysis/real_depth/README.md)):
  - walls 7.1 cm, boxes 21.2 cm wide, gaps 2.8 and 2.6 cm, so **24 cm centre to centre** (`scene.yaml`: 5 cm gaps, 26 cm);
  - near wall 32.3 cm in front of the point below the camera;
  - after our bin-wall camera fit the middle box stands 2.1 cm and the right box 4.2 cm from where `scene.yaml` puts them: every policy that drops at `scene.yaml`'s bins aims that far off centre (still inside a 21 cm box);
  - the middle box is cardboard with flaps folded in, opening about 14 × 16 cm. The lid's lip ring (19.2 cm) does not fit it as it is.
- **Box and lid finder built, off by default** (`policy/decision_oracle/boxes_v16.py`, v1.6 `V16_BOXES=find|lid`; same time, same README):
  - boxes: real frames 15/15; venue-look sim frames 107/115, within 3 mm where found;
  - lid: the real STL rendered on the middle box with the real camera pose and noise, 48/48 poses with the right turn and side, hole centres within 2.4 mm;
  - not run in any episode; no real frame with the lid exists.
- **Shape putting works in MuJoCo, open-loop** (Emīls + Claude, Sun ~03:25, `sim/mujoco/insert_demo.py`): the real lid on the middle box, boxes 7 cm closer, head camera only. 19/27 blocks through the right hole (cubes 7/9, cylinders 9/9, prisms 3/9), 0 wrong holes. Every block still held at its hole went in; the failures were blocks slipping out of the hand while carried. Not run through the policy server. Separate from the team's `insert.py` (task 3, cylinders only).
- **If the boxes move 7 cm closer, v1.6's default camera fit (`V16_CALIB=bins`) puts every object 7.5 cm off** in MuJoCo: it lines the boxes up with `scene.yaml` and moves the camera to do so. `V16_CALIB=hands` and `V16_CALIB=lean` do not (4/4 blocks vs 0/4). The v1.2–v1.5 images and Marcus's agent were not checked; any fit that matches the boxes to `scene.yaml` has the same problem.

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
**Overnight Sat → Sun (Samer + Claude, e-056 … e-063):**
- **Smooth motion (W1, `policy/smooth_motion.py`) costs no score:** v1.6 with vs without, same seeds: venue look
  23/27 vs 23/27, `AALTO_DR=train` 19/20 vs 19/20, 0 clipped steps. Peak arm acceleration ~13 vs 25–58 rad/s²,
  largest one-tick speed change 0.39 vs 0.8–1.7 rad/s; episodes ~16 % longer. On by default.
- **Lean mapping (`policy/lean.py`) hurts in sim:** robot pitched 8° + camera 2.4° (the lean fitted to Aalto's real
  footage), v1.6 seeds 1000–1002: mapping off 12/12, on 7/12. Default switched to off (847df56).
- **Task 3:** the first run (e-063, 0/6 inserted, −1 per episode) was invalid: the sim starts with the arms near
  joint zero and in our lid placement the left hand got caught under the lid before every trial. Fixed for our
  Modal runs (`modal_pipeline/sim/eval_patches.py`); `insert.py` now parks both arms beside the lid. Since then
  (e-064 … e-077, Modal, Aalto's look): **cylinders go in ~2 times in 3** (21/32 over four release settings), **cubes
  0/16 and triangles 1/24**, which lose points under every setting, so `insert.py` tries cylinders only. Releasing
  12 mm inside the hole, a higher pinch or a 0.6 s hold change nothing beyond noise. `LID_PICK_TOL` (2 mm, on) keeps
  the hand's way down on the planned grasp point (Aalto's planner allows 6 mm): +22 vs +13 on 9 seeds, within noise.
- **Candidate image gates** (sim B, `AALTO_DR=train`, seeds 1000–1002, PASS, 0 clips): `final-v16` 11/12 (e-072),
  `final-v16g` 10/12 (one wrong bin, e-070), `final-adk` 10/12 (one time-limit episode, e-071).
- v1.6 with all the new code in Aalto's nominal look: 9/12 (e-060).

| Run | Policy | Sim / task / trials | Objects sorted | Notes |
|---|---|---|---|---|
| e-008 | Aalto's classical baseline, camera only (a valid submission) | nominal, sort_fixed, 10 | 26/40 (65 %), gate PASS | **far cross-body objects 2/9**, the rest 24/31 |
| e-010 | **Aalto's oracle**, launched as "v1" by mistake (`--container` without `--policy` runs the oracle) | nominal, sort_fixed, 10 (same seeds as e-008) | 32/40 (80 %) | **not v1**. Useful as the exact-pose reference on the baseline's seeds |
| e-011 | Aalto's classical baseline | `AALTO_DR=train`, sort_fixed, 10 | 11/40 (28 %), gate FAIL | 2 safe-stops right after time-limit episodes (blocking `reset()`, fixed in our versions) |
| e-023 | **v1.2**, the real image | nominal, sort_fixed, same seeds as e-008 | 26/40 (65 %), gate PASS | **the same as the baseline**; seed 1004 0/5 |
| e-024 | **v1.3** (+ free drop spot per bin) | nominal, sort_fixed, same seeds | 26/40 (65 %), gate PASS | the same again. No lost object rests on another one any more (baseline 5 of 14), but **13 of its 14 lost objects end closer than 27.5 cm to the pelvis**; 6 episodes end early with objects still seen but given up |
| e-025 | **Aalto's oracle**, launched as "v1.2" on sim B by an old `compare.sh` | `AALTO_DR=train`, sort_fixed, same seeds | 32/40 (80 %), gate PASS | **the same as nominal (e-010)**: randomisation hurts camera-based perception, not the physics |
| e-026 | **v1.1** | nominal, sort_fixed, same seeds | 29/40 (72 %), gate PASS | within run-to-run spread of the 26/40s |
| e-027 | **v1.3 with randomisation** | `AALTO_DR=train`, sort_fixed, same seeds | **26/40 (65 %), gate PASS** | **the same as nominal; the baseline falls to 11/40 with a gate FAIL (e-011)**: +15 objects on the test closest to the finalist variant. 12 of 14 lost objects end near the robot |
| e-028 | **v1.4 in the venue look** (sim C) | venue look, sort_fixed, seeds 1000–1005 | **20/27 (74 %), gate PASS** | same seeds as e-004 (oracle, exact poses 22/27), e-012 (camera 18/27), e-019 (decision_oracle camera + upgrades 21/27). v1.3 there: 0/9 in 2 episodes (head fit rejected) |
| e-029/e-030 | **v1.5** same-side arms / sides off (Modal) | venue look, sort_fixed, seeds 1000–1005 | 20/27 / **23/27 (85 %)**, gate PASS | same seeds as e-028 (v1.4 20/27) and e-004 (oracle, exact poses 22/27) |
| e-031, e-032 | v1.5 same-side arms (Modal) | venue look: sort_language 2000–2005; sort_fixed with every triangle lying | 22/28; 18/27, gate PASS | e-022 (decision_oracle inside Aalto's evaluator) 26/28; lying triangles held 4/9 with the ridge grasp, 0/14 with the stock claw |
| e-033 | Aalto's baseline in the venue look (sim C, stopped after 2½ episodes) | venue look, sort_fixed, seeds 1000–1002 | **0/14** | the stock colour ranges miss the real orange and most yellow; v1.4 20/27, v1.5 23/27 on the same seeds |
| e-034 | **`look` image, live** (sim C) | venue look, seed 1000 | never moves (0/3 by design), gate PASS | camera fit 9.8°, “v1.4 USES it”; objects right with the fitted camera (tops 4.4 cm); hand check “TILTED CAMERA” from t ≥ 10 s (1.3 vs 4.3 cm): the right answer for this look |
| e-035 | **v1.4 with randomisation** (sim B) | `AALTO_DR=train`, sort_fixed, seeds 1000–1009 | **29/40 (1 wrong bin), gate PASS** | v1.3 26/40 (e-027), baseline 11/40 + gate FAIL (e-011). Seeds 1000–1004: 15/20 (Marcus's agent 18/20, Aalto's oracle with exact poses 17/20) |
| e-036 | v1.3 on sort_language (sim A) | nominal, seeds 1000–1009 | 24/37, gate PASS | no wrong bins; seeds 1000–1004 11/18, the same as Marcus's agent |
| e-037 | **v1.5 sides off with randomisation** (sim C) | `AALTO_DR=train`, Aalto's look, seeds 1000–1009 | **33/40, gate PASS** | best camera-only result: v1.4 29/40, v1.3 26/40, baseline 11/40, Aalto's oracle with exact poses 32/40 (e-025); seeds 1000–1004 17/20 (Marcus's agent 18/20) |
| running | v1.5 strict with randomisation (sim B, 17/24 after 6 seeds); **Marcus's agent as a Docker image** in Aalto's nominal scene (sim C, `policy/adk/`, `eval/adk_lane.sh`), waiting for a Gemini key | | | for the real-robot pre-submission (Sat 23:59) |
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
- **Marcus's ADK agent** (Gemini 4 Hydrogen calling oracle-based skills, camera perception; Modal, from `sim_out/` in his repo, up to a20c8c4 Sat 19:26): nominal sort_fixed seeds 1000–1004: 14/20, 17/20, 16/20 (Aalto's baseline 16/20 on the same seeds there); a triangle-heavy nominal set (seeds 2000–2004): **18/21, triangles 7/10** (face grips, every grip angle tried). With real colours and `--dr wide`: 5/12 – 8/21 with wrong-bin drops; in his `venue` scene + `AALTO_DR=train`: 3/21 and 4/20 (6 in a wrong bin). **His `venue` scene is not our venue look:** it only recolours the blocks as the real head camera saw them (`sim/scene_variant.py --colors venue`); camera, bins and layout stay Aalto's. His agent has not been run in our venue look (camera 10° lower), where its copy of our old head-fit check (`adk_agents/robot_sorter/headpose.py` `plausible()`) would reject the correct fit (fix: `camera_move_ok` in `policy/policies/classical_v14.py`). Every move waits 3–4 s for the model. **Newest runs (his 1a51d7b, Sat 19:39, Aalto's look, `sim_out/s2/`): randomised (`AALTO_DR=train`) seeds 1000–1004 18/20**, nominal 1000–1004 16/20, triangle-heavy 2000–2004 11/21, sort_language 1000–1004 11/18 (variants mixed). Same seeds on `samer-v1-sim`: Aalto's oracle with exact poses 17/20 nominal and randomised; baseline 12/20 / 10/20; v1.3 13/20 / 14/20; v1.1 16/20 nominal; v1.4 randomised 12/15 after 4 seeds. So in Aalto's look his agent leads v1.x (it drives Aalto's oracle motions, like v1.5); with the real colours his agent fell to 3/21 and 4/20 (older version; v1.x was not run in that scene), and it has not been run in our venue look. It is driven by Gemini, so a submission would need internet during the run and a key inside the image (not on our public GHCR package); there is no image of it yet.
- **Grasp check in the venue look** (v1.4, e-028): 21 empty-hand aborts at 0.0001–0.0002 rad, 25 held objects at 0.0117–0.0752 rad; the 0.006 threshold separates all of them (0.012 would have dropped one held object).
- **v1.2's head-camera re-fit rejected its own correct fit in the venue look** (Sat ~19:00, sim C): tilt 9.8°, reported "shift −8.3 cm" > the 6 cm limit, but the camera itself moved only 1.9 cm (the plane fit tilts the pose about the pelvis origin, the bin fit moves it back). v1.2/v1.3 then perceive the venue look with a camera ~10° off: on one frame v1.3 finds 11 "objects" (bins among them, at wrong heights), v1.4 (fixed) exactly the 6 objects. In the nominal and randomised sims all 25 logged fits were accepted, so this only bites in the venue look, and on the real robot if its camera is really tilted.
- Sim speed: one sim on the RTX PRO 6000 machine runs at 0.52× real time, two or three on one machine at 0.17–0.48×. Scores pace on the sim clock, so speed doesn't change results.

### 4.4 Submission candidates (`policy/`)
| Version | Adds | Status |
|---|---|---|
| v1 | Aalto's classical baseline + reads the instruction (rule parser, orange/purple names) + real-colour HSV ranges + speed guard (0.98 / 2.7 rad/s) | image 1.46 GB; Aalto's replay test: 100 calls, 0 errors, 5.5 ms median, server up in 0.55 s |
| v1.1 | far cross-body objects are first moved by the near arm, then finished by the bin-side arm; at most 3 tries per object | nominal 29/40 (e-026) |
| v1.2 | v1.1 + re-fits the head-camera pose from depth at each episode's first look (Emīls's fit): corrects ~1° in the nominal sim, ~2° with randomisation. **Rejects the ~10° fit of the venue look** (see §4.3) | nominal 26/40 = baseline (e-023) |
| v1.3 | v1.2 + a free drop spot per bin (`eval/analysis/FINDINGS.md` §1) | nominal 26/40 (e-024), **randomised 26/40 (e-027)**; venue look 0/9 (head fit rejected). On GHCR (fallback) |
| v1.4 | v1.3 + grasp check at the end of the lift (empty: skip the carry, go home, look again) + a retry with another arm / finger direction + the head-fit check fixed | **venue look 20/27 (e-028)**; **randomised 29/40 (e-035)**; not yet in the nominal sim. On GHCR (candidate) |
| v1.5 | not built on v1.x: Aalto's oracle motions (face grasps, relay, drop spots) on the head camera + decision_oracle upgrades (failure memory, grasp check, option search) + same-side arms (`V15_SIDES=strict`, default) + a ridge grasp for lying triangles | venue look 20/27 strict, 23/27 sides off (e-029, e-030); sort_language 22/28 (e-031). Uses Aalto's `scene.yaml` bin walls (6 cm) for the camera fit; the venue look has 7.5 cm |
| v1.6 | v1.5 sides off + Gemini Decision 1 (API) for colour and shape of each object crop and for the instruction; v1.5's HSV, depth shape and rule parser stay as the offline fallback (no key / error / 2.5 s deadline / confidence < 0.6). v1.6 only: lying-prism grasp fix (hand 18 mm along the ridge, ridge plan on either arm before the stock claw) | venue look sort_fixed 23/27 (e-044), sort_language 25/28 (e-045): 48/55 vs v1.5 sides off 47/55; lying prisms 48/53 vs v1.5 46/53 (e-049); no key 8/9 (e-048). Real-colour sim (venue colours, sort_fixed 1000-1005): 17/27 with 5 in a wrong bin (e-046) → 22/27, 0 wrong after the colour wording fix (e-050) → 25/27 and 23/27 (e-054, e-055) with the red/yellow merge, the crowd check and the near-body push (push off by default). Not built as an image; an image with the key baked in must not go on our public GHCR package |
| look | never moves: logs v1.4's camera fit, the objects it sees and a hand check (`policy/policies/look.py`) | for the first real-robot run; image on GHCR. **Tested live in the venue look (e-034): every line right** |
| **final images** (Sun ~02:35) | built on `samer-v1-sim` from main (≥ 92b2999), **not pushed**: `bot-icelli/policy:final-v16` (1.46 GB: v1.6 + Emīls's 83d53a7 + smoothing on + lean off + task 3 cylinders only, arms parked), `:final-v16g` (6.35 GB, + retrained Gemma 1B), `bot-icelli/adk:final-adk` (Marcus 1855ff4 + smoothing). Gemini key inside all three (as `presubmit-adk-1`) | replay test PASS on all three; Decision 1 verified from inside final-v16 (0.26 s, right mapping). **Gates on sim B, same seeds: final-v16 11/12 (e-072), final-v16g 10/12 (e-070), final-adk 10/12 (e-071)**; e-065 was the first final-v16 build, whose key was broken (9/12). final-v16 and final-v16g rebuilt from 2de82ce (Sun ~03:40: + `LID_PICK_TOL`, task 3 only; replay PASS, key 53 bytes). None corrects the real-robot offset (§4.1) |
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
  - **Cause found (Sun 15 Nov, MuJoCo, `eval/analysis/grasps/README.md` §4):** Aalto's grasp point sits almost at the fingertips, so the closed thumb stops ~11 mm short of a standing prism and the index finger pushes it away instead of pinching. Lying prisms already have their own grasp (e-049).
  - **Fix built, on by default since 27b1de9 (Samer, Sun ~04:40):** `V16_TRI=mid` (`policy/decision_oracle/tri_v16.py`): midpoint grasp point and per-hand finger angles for standing triangles. MuJoCo paired run (e-080, 72 pairs): triangle grasps held 27 % → 57 % per attempt, objects sorted 83 % → 88 %, gate PASS. **Isaac agrees (e-081, 24 single-triangle cases, paired):** triangles sorted 12/24 → 21/24, grasps held 26 % → 62 % per attempt, 9 cases better and 0 worse. **Full episodes (e-082, 12 paired Isaac episodes):** gate PASS with it on, objects sorted 36/49 → 43/49 (part of it noise), triangles 3/10 → 5/10.
- **Far cross-body objects:** 2/9 in the baseline; v1.1 targets them.
- **Second object into a bin:** fixed in v1.3 (no lost object rests on another one, e-024).
- **Objects near the robot (pelvis x < ~0.28 m):** where v1.3 loses almost everything it loses (13 of 14, e-024). Failed grasps push objects towards the robot, where they sit at the bottom edge of the head camera's view and partly behind the hands at the home pose. v1.4's grasp check and new-grasp retry are the first step; a nudge outwards or a different approach for close objects is the next.
- **The head-pose re-fit (v1.2–v1.6) levels the camera on the table, and on the real robot that is probably wrong** (see 4.1: it is the torso that leans, not the camera).
  - Synthetic check with the real geometry (`eval/analysis/real_hands/lean_error.py`): with the torso leaning 8° and the camera exact on its mount, levelling moves every object ~7 cm (4°: 3.3 cm, 12°: 10 cm).
  - Aalto's calibration used as-is would be exact.
  - `V16_CALIB=hands` fixes only x, y and yaw after levelling, so it gives up above ~4° and falls back to the bin fit.
  - **Fix built (Sun ~03:00, Emīls + Claude): `V16_CALIB=lean`, the default since Sun ~05:30 (team decision, `docs/DECISIONS.md`)** (`policy/decision_oracle/README.md`). On Aalto's 15 drop-3 frames the arm fit succeeds 15/15 (lean 12–16°), 14 move the IK base, 1 is rejected as implausible (ep14, 20.9°) and keeps the bin-wall frame; a crashing or failed arm fit, or a missing `hand_model.npz`, falls back to the bin-wall fit.
    - The arms give the camera's full pose relative to them, and the planners' IK model is moved into the camera's levelled table frame.
    - MuJoCo with a leaning robot (new `dr.py` mode `lean`): reach error 35–65 mm → ~1 mm. Shifted bins: 9–35 mm → ~1 mm. Nominal unchanged.
    - Paired episodes (`eval/RESULTS.md` e-079): nominal 75 % = 75 %, shifted bins 22 % → 58 %, leaning 49 % → 56 %, all randomised 21 % → 49 %.
    - Untested on real depth of the black hands.
  - The venue look puts the tilt in the camera, so it can't show this. The MuJoCo scene now can (`--dr-mode lean`).
- **Real robot, none of it tested there:** camera ~10° off (v1.2 targets it), the hand sits 4–6 cm closer than in sim, real depth noise and holes, bins maybe not where `scene.yaml` says.
- **Infrastructure:** the spot machine can vanish (reinstall: 11 min).

## 7. Open questions (OPEN)
- **Aalto:** the image deadline and hand-in form (expected tonight); whether they can pass an API key as an environment variable; how distractors are scored.
- **Real camera: mostly answered (Sun ~02:00).** The hands in Aalto's frames say the camera is ~2° off its calibration and the torso leans (4.1). Still open: is the lean the same at the venue, and does the real waist pitch move (it is not in `obs`)?
- **Sim runs going (Sat ~20:20):** v1.5 (strict and sides off) with randomisation in Aalto's look, seeds 1000–1009: does it match Marcus's agent there (18/20 on 1000–1004) while keeping its venue-look lead over v1.4 (23/27 vs 20/27)? If so, v1.5 becomes the candidate.
- **Gemma inside the image:** size, and start-up within the 120 s limit, are untested.
- **Aalto, about the box move and the lid (Sun ~02:50):** the exact new distance and gaps; whether the object area moves too; how the lid is turned and which side is up; which box it sits on, given that the middle box's opening is smaller than the lid's lip; whether shape putting is scored in the finals.

## 8. Repo rules added today (FACT)
- **No AI co-author lines in commits or PRs** (`Co-Authored-By: Claude …`, "Generated with …", `Claude-Session:`): GitHub listed "Claude" as a contributor of this repo because of them. Guards: `.claude/settings.json`, `.githooks/commit-msg`, `make setup`, and the rule in `AGENTS.md` (c239100).
- Older commits still carry such lines. Samer may have the history cleaned (messages only; same files, authors and dates). If that happens, run `git pull --rebase` once; a plain `git pull` would bring the old commits back.
