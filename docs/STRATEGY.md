# Strategy proposal: how we win the Aalto challenge

**Status: proposal, not agreed.** Written Sat 14 Nov ~12:30 by Samer with Claude, from Aalto's repo (`36daf5b`, unchanged since Fri 21:54), the Aalto Discord channel and the two real-data drops. Discuss it, then move what we agree into [`DECISIONS.md`](DECISIONS.md) and [`BRIEF.md`](BRIEF.md).
**Updated ~13:00** with Aalto's answers: **one deadline for everything, Sun 10:00**, and **the finals PC has internet**. Colours re-measured in the robot's own camera.
Evidence: [`research/real-data-findings.md`](research/real-data-findings.md) (what's in the drops) and [`research/aalto-discord-notes.md`](research/aalto-discord-notes.md) (organiser answers).

## TL;DR
1. **Get a valid v1 submitted tonight, before anything clever.** Baseline + a parser that knows orange/purple/box + colour detection for the real objects + our own speed guard, through Docker → GHCR → the form. Finalists are picked in sim from what's submitted by Sun 10:00; submitting v1 early lets Aalto's pre-check catch problems while there's time to fix them. Don't wait for the fine-tuning results to start this.
2. **Win on reliability.** Every point needs a physical pick on the real robot. A classical core (perception → IK → scripted grasps) is the default; π0.5 joins only as a plug-in skill if it beats the classical skill in sim with randomisation on (checkpoint tonight).
3. **Stand out by making every module work on the real setup.** Each part is fitted to or checked against Aalto's scarce real data: colours, camera calibration, grip detection, triangle grasps. The instruction goes through an offline fine-tuned Gemma with a measured accuracy. Both arms work at once, and every pick is checked and retried.
4. **Tech challenges:** Verda and Gemma (natural fit, little extra work), plus Gemini once v1 is in. The finals PC has internet, so Gemini Robotics-ER can label our data before the finals *and* give a live second opinion during them (with an offline fallback). Skip the rest.
5. **Rokoko as a second project** with its own main challenge: wired glove teleop of the G1 in the sim (no Wi-Fi, which is what broke Aalto's own data collection), recording demos in Aalto's format.

## 1. Where the points are

| Finals episode | Points per object | Share of the maximum |
|---|---|---|
| 1. `sort_fixed` | +1 | 1/6 |
| 2. `sort_language`, known template | +2 | 2/6 |
| 3. `sort_language`, unseen instruction + layout (×1.5) | +3 | 3/6 |

- **5/6 of the maximum needs the instruction followed *and* the object placed on the real robot.** A wrong bin costs −1 (−1.5 in episode 3) and loses the +2/+3. Knocking an object off costs −1.
- **Attempt anything we can classify:** an attempt pays off whenever P(right bin) > 1/3. Leave unknown objects (distractors) alone.
- **Judging is unclear.** The challenge page weights real-world result 40 %, generality 25 %, originality 20 %, presentation 15 %; the repo says ranking = real-robot score. Ask (§10). Either way it's reliability first, then generality and originality.
- **Finalists come from the held-out sim variant** (other textures, lighting, poses, camera jitter). Tune with `AALTO_DR=train` on, not only on the nominal scene and not only on the venue look.
- **Deadline:** Sun 10:00 for both the sim evaluation that picks finalists and the finals image (Aalto, Sat ~12:50). The last image submitted before then is the one that runs.
- **Gate:** 0 clipped steps, ≥ 27 Hz measured on *our own* wall-clock latency, no crash or watchdog.

## 2. What the data and Discord tell us (others may miss some of this)

1. **The real objects are orange / yellow / purple, and the bins are orange too.** Drop 2's own instructions say "orange cube", "purple cube", "box". Measured in the robot's own head camera: orange sits at hue 11–13, between the baseline's red (≤ 8) and yellow (≥ 18) ranges, and yellow looks pale green (34–46), outside its yellow range. Purple looks blue and is detected. **So the stock baseline would sort mostly the purple objects on the real robot.** Both the parser and perception must handle the real names and colours, and the sim ones. Image and numbers: [`research/aalto-discord-notes.md`](research/aalto-discord-notes.md).
2. **The real demos break the speed limits.** All 48 drop-2 episodes command the arms at 2–4 rad/s (cap 1) and the fingers at up to 25 rad/s (cap 3). At legal speed a median 8 s pick-and-place takes ~27 s. So: don't imitate raw real actions; retime them first. Copying human speed can't sort 4–5 objects in 120 s anyway.
3. **The real hand shows when it's holding something:** while closed, the measured fingers lag the command by 0.4–1.7 rad (sustained). That makes grasp checks from `hand_q` possible (to be confirmed against closing on air).
4. **Drop 2 is single-object sub-tasks** ("Put the orange cube into the right box."), the same shape as a planner → skill call.
5. **Organiser answers:** no negation in instructions; shape-based instructions possible "if several teams handle colour"; real pads are rubber with less grip than the sim; Dex3 gains are fixed for everyone; the finals PC is an RTX 5090 wired to the robot (tell them early about big images) and **will have internet** (confirmed to Samer, Sat ~12:50).
6. **Competition:** 13 teams on this challenge. At least one (The Larp Interns) is doing careful real2sim work. Assume 2–3 strong teams.

## 3. Architecture: one server, swappable parts

```
reset(instruction) ─► Instruction compiler (once per episode, < 1 s, offline)
                      fine-tuned Gemma + rule parser; both must agree, else the rule parser
                      ─► TaskSpec: {colour × shape → left | center | right | leave}, unknown objects → leave

act(obs) at 30 Hz, never blocks (planning runs in a background thread)
  Perception    head RGB-D → objects: colour class (sim AND real colours), shape, yaw, position, confidence
                bins masked by 3D position; anything not matching a known type = unknown
  Second opinion (optional, live) Gemini Robotics-ER on the head image + instruction, at episode start
                and after each place, in a background thread with a timeout: which object is which and where
                it goes. Our depth still decides the exact position; no answer in time → carry on without it
  Planner       next object per arm, both arms in parallel (lock on the centre bin), time budget
  Skills        pick: face-aligned grasp from the perceived yaw, triangle-specific grasp | place | relay
                [optional learned skill: π0.5 "Put the {colour} {shape} into the {position} box."]
  Checker       grasp: hand_q gap; place: re-detect from the head camera; retry or skip
  Speed guard   every chunk ≤ 0.95 rad/s arms / ≤ 2.9 rad/s hands, joint limits, workspace check
                → 0 clips whatever produced the chunk (also protects us from a VLA)
  Log           every decision (debugging + the "what the robot thinks" view for the pitch)
```

**Why not "π0.5 for low-level control + a big LLM planner live"?**
- **π0.5 as the only controller:** it learns from demos, and the real ones break the speed caps (§2). Sim-trained, it faces the sim-to-real visual gap, and when it fails on the real robot we can't debug it in an afternoon. Keep it, but as a skill behind the planner that must beat the classical skill on the same seeds.
- **A live LLM agent calling tools** (e.g. the oracle split into LangChain tools): every step would wait on the network (the finals PC has internet, but a failed or slow call costs the episode), VLM calls take 10–20 s (Aalto's estimate) inside a 120 s episode, and the oracle's tools use privileged object poses, which a submission may not use. **The safe version of the same idea:** the LLM compiles the instruction once into a checked TaskSpec, a deterministic executor runs it, and Gemini gives a live second opinion that the robot never waits for. A live agent loop is still a good *development* tool (debugging and evaluating in sim).

## 4. How we set ourselves apart (ranked by value for effort)

| # | What | Why it matters | Owner (proposal) |
|---|---|---|---|
| 1 | **Colour detection for the real objects**, fitted on `cam_high` frames from the drops (and Drop 1 when it lands), still working on the sim colours | Likely a silent failure for teams on the stock baseline: up to a third of the objects | Emīls |
| 2 | **Calibration checked against real data:** project the palm's FK onto drop head-camera frames, measure the offset, correct `xy_offset` / extrinsics | Aalto's head extrinsics are provisional; 1–2 cm of error makes a 45 mm grasp miss | Claude + Samer |
| 3 | **Grasps that hold:** perceived yaw + shape → face-aligned grasps (the oracle's `FACE_ALIGN` logic, fed with *perceived* yaw instead of privileged yaw), a triangle grasp (try thumb on one face, index + middle on the two faces of the opposite corner), lower friction in randomisation | Triangles are the baseline's main miss, and the real pads grip less than the sim | Marcus |
| 4 | **Check every grasp and place, then retry:** `hand_q` gap after closing, head-camera re-detection after placing | Turns a slip into a second try instead of a zero | Marcus |
| 5 | **Both arms at once** | The 120 s limit is one of the baseline's two main losses | Marcus |
| 6 | **Instruction compiler with a measured accuracy:** Gemma + rules on hundreds of unseen paraphrases, incl. orange/purple/box and shape rules; put the number in the pitch | Protects the ×1.5 episode; generality is 25 % | Emīls |
| 7 | **"What the robot thinks" view** (detections, parsed instruction, plan, checks) from sim runs and the finals logs | Presentation is 15 %, and it shows the generality | Tiya |
| 8 | **Optional learned skill** (π0.5) behind the same skill interface, decided at the checkpoint | Originality, if it really works | Marcus |

The pitch line: **"Sim is free, reality is scarce, so we spent our reality carefully: every part of the robot's brain is calibrated against Aalto's real data, and the language part runs offline on the robot."**

## 5. Plan and checkpoints

**Deadline: Sun 10:00** for everything (Aalto, Sat ~12:50).

| When | Goal | Done when |
|---|---|---|
| **Now → ~19:00** | **P0: submission v1.** Baseline + rule parser (orange/purple/red/blue, box/bin) + widened colour ranges + speed guard | `replay --synthetic` and `sim.evaluate` gate PASS on both tasks; image on GHCR; digest submitted through the form |
| ~19:00 → 02:00 | **P1: higher sim score with randomisation on.** Perceived yaw + face-aligned grasps, grasp check + retry, both arms, Gemma in the image, Gemini second opinion | Every change scored on the same ≥ 10 seeds with `AALTO_DR=train`, logged in `eval/RESULTS.md`; resubmit when better |
| **22:00** | **Checkpoint: π0.5 go / no-go** | It stays only if it beats the classical skill on the same seeds with randomisation on and 0 clips |
| 02:00 → 06:00 | The sim farm runs long evals overnight; fix the top failure each round | — |
| **06:00** | **Freeze features.** Real-data checks (calibration, Drop 1 colours), pitch + video | Only bug fixes after this |
| **~08:30** | **Final submission**, leaving time to react to Aalto's pre-check | The last good digest is written down in `eval/RESULTS.md` |

**Rule:** only submit an image that passed the full gate on ≥ 10 randomised seeds. The last image before the deadline is the one that runs in the finals.

## 6. Who does what (proposal)

| Person | Owns | First thing now |
|---|---|---|
| **Samer** | Integration and the submission (Docker → GHCR → form), eval farm, contact with Aalto | Ask Aalto the §10 questions; a Verda sim box with SSH access for Claude; the submission pipeline with the baseline |
| **Marcus** | Skills and motion: grasps, triangles, both arms; the π0.5 experiment | Keep π0.5 training in the background; start the face-aligned grasp with perceived yaw |
| **Emīls** | Perception, sim realism, language | Real-colour model from drop frames (sim colours must still work); Gemma compiler into the image |
| **Tiya** | The Rokoko project, the pitch, all write-ups | Gloves → sim with an input you can swap (glove / webcam / keyboard); Rokoko licence; collect pitch material |

Claude (through Samer) takes the rule parser, the speed guard, the Docker/GHCR pipeline, the calibration overlay and data tools.

## 7. Infrastructure

- **Sim farm on Verda:** 2–3 RTX boxes (RTX 6000 Ada or RTX PRO 6000), **≥ 16 vCPUs** (physics runs on the CPU: we measured 0.31× real time on 10 vCPUs, Aalto ~0.7×), one sim per box, a persistent volume each. Use each member's €200; hibernate when idle. One box per active developer plus one for long evals.
- **Eval loop:** one command per variant (`aalto eval --policy ws://localhost:8000 --task <task> --trials 10` with `AALTO_DR=train`) → a row in `eval/RESULTS.md` with the git sha. Always compare on the same seeds.
- **Training:** π0.5 on B200 (Modal or Verda). Checkpoints in a private Hugging Face repo, never in git.
- **Submission pipeline:** build on the x86 Verda box → `replay --synthetic` → `sim.evaluate` gate → push to GHCR (public package) → submit the digest. Tell Aalto early if the image grows past a few GB (π0.5).
- **One server in `policy/`** with the parts in §3 as separate modules, each testable on the mock backend.

## 8. Tech challenges

| Challenge | Verdict | Why | Extra work | Owner |
|---|---|---|---|---|
| **Verda** ($10k credits, then $2.5k) | **Enter** | "Teach a humanoid to move … in simulation, at scale" is their first example. Our sim and evals already run there; a sim farm is compute a laptop can't do | Document the process (runbooks exist) and post a summary link in their Discord | Samer |
| **Gemma** (3 × €1,000) | **Enter** | The only one of the three that runs offline inside the image. A fine-tuned compiler with measured accuracy is solid technical execution | Ship it in the image; publish the eval table | Emīls |
| **Gemini API** (€4k + $1k GCP per member, then €2k / €1k) | **Enter, once v1 is in** | Gemini Robotics-ER is made for robot spatial reasoning (pointing, boxes, success detection). Before the finals: label real and sim frames for our colour/shape detector and check eval episodes. During the finals (the PC has internet): a live second opinion on which object goes where, which the robot never waits for | ~½ day | Tiya |
| **Nemotron** (2 × RTX 5080) | **Skip unless someone has spare time** | Gemini covers the same role with a model made for robots and a bigger prize. Super VL doesn't fit the 32 GB finals GPU, so it could only be an API call or a development-time data engine | ~½ day | — |
| **Modal** | Only if π0.5 trains there | Free to enter if Modal really does the training | Write-up | Marcus |
| MLH ×6, Codex, CRACI, Cloudinary, Oxylabs, Context.dev, Aiven, Arduino, Atech | **Skip** | Each needs real integration and none helps the robot | — | — |

## 9. Rokoko as a second project (own main challenge)

- **What:** Rokoko Smartgloves II + Coil Pro → G1 + Dex3 teleop in the Isaac sim, and on Väiski only if Aalto and Rokoko set it up with their operator and e-stop. Demos are recorded in Aalto's LeRobot format.
- **Why it's strong:** Aalto's own teleop failed at the venue because the Quest needs Wi-Fi. The gloves stream over USB and the Coil Pro is a passive field source with no radio, so the rig works wired. Offer the recordings to Aalto and the other teams.
- **Path:** input abstraction (glove | webcam hand tracking | keyboard) → xr_teleoperate's Dex3 retargeting + arm IK → `AaltoEnv(backend="sim")` (safety filter on) → `record_demos.py --backend sim` → `to_lerobot.py`. Details: [`research/glove-sim-teleop.md`](research/glove-sim-teleop.md), [`research/rokoko.md`](research/rokoko.md).
- **Gloves aren't guaranteed** (120 min rental, SDK licence approval). Build and test with the webcam or keyboard input first, then script the glove session: triangles and recoveries.
- **Link to the Aalto project:** glove demos of hard cases can tune the triangle grasp (hand posture at grasp time) without training a big model.

## 10. Questions for Aalto (ask in person today)
1. ~~When is the submission for picking finalists due?~~ **Answered: one deadline for everything, Sun 10:00.**
2. Is the winner the real-robot score only (repo), or the 40/25/20/15 criteria on the challenge page?
3. Will the finals instructions say orange/purple or red/blue? In rung 1, is orange "red" and purple "blue"? What are the black shapes on the table for?
4. ~~Does the finals PC have internet?~~ **Answered: yes.**
5. Can you run one episode of our image on the real robot before the finals (a dry run) and give us the logs? *(Asked; no answer yet. Assume no.)*
6. When do the checked head extrinsics and wrist-camera mounts come? Is the real box taller than 6 cm, and is the tape on the centre box part of the finals scene?
7. Were drops 1–2 recorded without the 0.9 rad/s teleop cap? (We measure 2–4 rad/s on the arms and up to 25 rad/s on the fingers.) Is the Drop 1 venue capture (RGB-D, depth noise) still coming?
8. If we bring a wired Rokoko glove teleop (no Wi-Fi), could your operator use it to record real demos, shared with every team?
9. Are the finals objects the foam blocks seen in the drop videos (not printed PLA)?

## 11. Risks

| Risk | Mitigation |
|---|---|
| No valid submission at Sun 10:00 | P0 first; submit v1 tonight even if it's only the baseline plus fixes; final submission ~08:30, not 09:55 |
| Orange/yellow not detected on the real robot | Widened ranges fitted on real frames; test on venue-look sim and on drop frames |
| Calibration off on the real robot | FK overlay check on drop frames; ask for the AprilTag result; ask for a dry run |
| Grasps slip with real (less grippy) pads | Lower friction in randomisation; grasp check + retry |
| Gate fails on rate (real-time latency) | Planning in a background thread; watch `policy_hz_rt` in every eval |
| π0.5 eats the team's time | Hard go/no-go at 22:00 on the same seeds |
| Internet fails or Gemini is slow in the finals | The robot never waits for Gemini; our own detector and parser carry on alone |
| Sim farm cost | Hibernate idle boxes; each box on its owner's credits |
