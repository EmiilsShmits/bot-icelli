# Aalto humanoid (Väiski): hardware, sim, interface

Source: challenge repo `aaltonomous-humanoid` (docs dated 2026-11-11 to 13, commit a2d1dee), read 2026-11-13.
Challenge text: [`../challenges/main/aalto-university--aaltonomous-humanoid.md`](../challenges/main/aalto-university--aaltonomous-humanoid.md).
The repo docs are the source of truth and change during the event (versioned, changelog on the Junction Discord).

## In one screen

- **Robot:** Unitree G1, 29 DoF, with two **Dex3-1 three-finger hands** (7 DoF each). It is seated behind an 80 cm counter. Legs and waist are held stiff; it never walks. **Only the arms (2×7) and hands (2×7) move: 28 joints.**
- **Sensors:** head RealSense D435i (RGB + aligned depth, 640×480), one RGB UVC camera on each wrist. No force or tactile sensing.
- **Control:** absolute joint-position targets at **30 Hz**, sent as single steps or chunks `(k, 14)`. Every target goes through a safety filter.
- **Task:** sort 3–5 coloured 45 mm objects (cube / cylinder / triangular prism; red / yellow / blue) into 3 fixed orange bins (left / center / right) within 120 s.
- **You never touch the robot.** You submit a Docker policy server, the organisers run it in sim, and the top teams run on the real robot on Sunday.
- **Sim:** Isaac Sim 6.2 + Isaac Lab 3.0 (`unitree_sim_isaaclab`). It needs an **RTX-class GPU with ≥ 24 GB** (A100 / H100 won't render the cameras). It runs at ~0.7× real time.
- **Real data:** about 20 teleop demos per rung, raw and in LeRobot format. They were recorded with **Meta Quest hand tracking through Unitree `xr_teleoperate`**. That matters for a Rokoko-gloves idea (see the end of this file).

## 0. Official challenge page: facts only
Source: https://hackjunction.app/participate/45/challenges/320 (full text in [`../challenges/main/aalto-university--aaltonomous-humanoid.md`](../challenges/main/aalto-university--aaltonomous-humanoid.md); re-checked 2026-11-13 23:29, unchanged).

**Task**
- **Robot:** Väiski, a G1 with legs and waist held stiff; two 7-DoF arms, two Dex3 three-finger hands.
- **Objects:** 3–5 printed cubes / cylinders / triangular prisms, ~4.5 cm, red / yellow / blue, at random positions and angles.
- **Boxes:** 3 identical orange boxes, 21 cm wide, fixed, in a row (left / centre / right), 5 cm apart, 40 cm from the torso, no markings.
- **Time limit:** every object into the right box within **2 minutes**, with no human control.
- **Modes:**
  1. Fixed sorting: red → left, yellow → centre, blue → right.
  2. Sort by instruction. Page example: "Sort the objects: red into right, blue into left, yellow into center." Expect unseen phrasings.
  3. Stretch: each object through the matching hole in a lid on one box.
- **Policy I/O:** sees the head camera (colour + depth), both wrist cameras, joint states and the instruction. Sends target positions for all arm and finger joints, 30 times a second.

**How it works**
- **Build in sim first:** ready-made Isaac Sim of the robot and the exact scene; GPU from Verda.
- **Real-robot datasets:** published on Hugging Face during the event, with links on the Junction Discord.
- **Submission:** a Docker image running a small policy server. Aalto's runner sends its commands to the sim or the robot through their safety filter.
- **Finalists:** organisers evaluate submissions in sim on a scene version teams can't train on. Finalists run on the real robot on Sunday; the best real-robot score wins.
- **Safety check** required for real-robot time: no crashes or safety stops, no commands over the joint and speed limits, ≥ 27 commands per second.

**Judging criteria**
| Criterion | Weight | Meaning |
|---|---|---|
| Real-world result | 40% | How well it works on the real robot |
| Generality | 25% | Holds up when things change |
| Originality | 20% | Freshness of idea and approach |
| Presentation | 15% | Clarity of what you built and why it matters |

**Prizes**
- Winning team: €2,000 + a visit to the Aalto robotics lab.
- Top ~5 teams (chosen by sim performance) run live on the real Unitree G1.

**What they'd love to see** (from the page)
- works when reality doesn't match the sim exactly
- general ideas beyond one exact setup
- doing a lot with very little real-world data

**Approaches they name:** CV + classic programming, VLM/LLM planner calling own skills, imitation learning / VLA fine-tuning (LeRobot, π0, GR00T), RL in Isaac Lab, real2sim. They expect combinations to work best.

**What they provide**
- the real G1 at the venue
- a sim Docker image (Isaac Sim + Isaac Lab + the scene)
- Verda GPU compute
- real-robot datasets
- starter code: interface, safety filter, classical baseline, policy-server and Dockerfile templates, sim evaluator
- researchers as mentors, plus ~30 Aalto Robotics Club volunteers

**People and safety**
- **Mentors:** Erkka Lehtonen and Viktor Solianoi, on site. Questions go to the Junction Discord.
- **Safety:** teams never control the robot directly; Aalto's runner executes the image through their safety filter with staff at the e-stop.

**Not on the page**
- **Internet / network at the finals:** not mentioned. Aalto's repo docs say they provide no network (`FAQ.md`, `SUBMISSION.md`).
- **The page header** showed "Status: Closed" and a countdown "T -12:32:15" at Fri 23:29 (≈ Sat 12:01). What either refers to is not stated. Ask.

## 1. Robot hardware

| Part | Detail |
|---|---|
| Body | Unitree G1 29-DoF, "debug mode", fixed base, stiff lower body |
| Arms | 7 DoF each: shoulder pitch / roll / yaw, elbow, wrist roll / pitch / yaw. DDS `rt/lowcmd` motors 15–28 |
| Hands | Dex3-1, 7 DoF each: thumb 0–2 plus two fingers with 2 joints each. DDS `rt/dex3/left/cmd`, `rt/dex3/right/cmd` |
| Head camera | RealSense D435i colour + aligned depth (mm, 0 = invalid), 640×480, pitched ~48° down. Intrinsics fx = fy = 615 (provisional) |
| Wrist cameras | UVC RGB 640×480 on each wrist, each looking at its own Dex3. Poses not calibrated yet (placeholders in sim) |
| Reach | ~0.40 m from the waist comfortably, ~0.55 m with a straight arm. The bin centres are further than that, so release in the near part of each bin |
| Finals PC | One machine with an **RTX 5090 (32 GB)**, wired to the robot. **No guaranteed network** |

### Dex3 conventions (easy to get wrong)
- Each hand has its own joint order. **Left:** thumb 0–2, **middle** 0–1, **index** 0–1. **Right:** thumb 0–2, **index** 0–1, **middle** 0–1.
- The hands are mirrored: **left fingers close with negative angles, right fingers with positive** ones.
- **Zero = open hand**, which sits on a hard joint limit. Sending 0 to open is fine.
- The index and middle fingertips are ~57 mm apart, so a 45 mm object can wedge between them. Pinch the thumb against the fingers instead. Example postures are in `baselines/classical/config.yaml`.
- Arm q = 0 puts the hands just above the counter. A negative elbow value raises the forearm. **Home pose:** shoulder roll +0.35 (left) / −0.35 (right), elbow −0.5, everything else 0, hands open.
- The full joint table with limits is in repo `aaltonomous/interface/joint_spec.yaml` and `INTERFACE.md` §4. It comes from the URDF `xr_teleoperate/assets/g1/g1_body29_hand14.urdf`.

## 2. Interface (same in mock, sim and on the real robot)

```python
from aaltonomous.interface.env import AaltoEnv
env = AaltoEnv(backend="mock" | "sim", task="sort_fixed" | "sort_language", seed=0, time_limit=120.0)
obs = env.reset(); obs, info = env.step(action)   # blocks to keep 30 Hz
```

**Observations**

| Key | Shape |
|---|---|
| `head_rgb`, `left_wrist_rgb`, `right_wrist_rgb` | (480, 640, 3) uint8 RGB. An all-zero image means no frame yet |
| `head_depth` | (480, 640) uint16, in mm |
| `arm_q`, `arm_dq` | (14,) rad, rad/s |
| `hand_q` | (14,) rad |
| `instruction` | str |
| `t` | seconds since the episode started |

**Actions:** `arm_q_target` and `hand_q_target` are both **required** every time, as `(14,)` or `(k, 14)` absolute radians. `done` (bool) is optional. There is no torque control.

**Timing rules**
- 30 Hz. A `(k, 14)` chunk runs k ticks. The runner prefetches the next action while the current tick runs.
- If you answer late, the robot holds the last target. You get up to 30 s per call, then the episode ends.
- If your server returns errors: after 0.2 s the robot holds, and after **1.0 s it safe-stops and the episode ends**.
- **Slow models** (VLMs take 10–20 s per call) must think in a background thread and keep returning "hold" targets or chunks.

## 3. Safety filter (every tick, in sim and on the real robot)

| Stage | Limit |
|---|---|
| Position | URDF limits shrunk by 0.05 rad (arms) / 0.02 rad (hands) |
| **Velocity** | Each command may change by at most **1.0 rad/s (arms)** and **3.0 rad/s (hands)** relative to the last command |
| Workspace box | Wrist and palm must stay inside x 0.00–0.80, y −0.70–0.70, z −0.25–0.60 m (pelvis frame) |
| Counter keep-out | Wrist and palm may not enter z < 0.03 m over the table |
| Abort | More than 30 clipped steps ends the episode (points kept) |
| Not checked | Self-collision and fingertips vs table. Staff stop the run if this happens |

Offline check: `SafetyFilter.from_files()` then `filter(action, t)` returns whether it clipped and why. Finals limits will not get looser than these.

## 4. Scene

- **Pelvis frame:** x forward, y left, z up. The counter surface is at z = +0.01 m.
- **Objects:** 9 types (3 colours × 3 shapes), 45 mm, matte PLA, ~50 g. 3–5 per episode, at most 2 of each colour. Centres at x 0.26–0.33, y −0.17–0.17, yaw ±45°, at least 8 cm apart.
- **Bins:** 0.21 × 0.21 m, 6 cm walls. Centres: left (0.505, +0.26), center (0.505, 0), right (0.505, −0.26).
- **Mat:** 0.90 × 0.50 m printed mat with a 5 cm grid. The texture is the same in sim and on the real counter.

## 5. Tasks and scoring

| Rung | Task | Points per object |
|---|---|---|
| 1 | `sort_fixed`: red → left, yellow → center, blue → right | +1 correct bin, −1 wrong bin, −1 knocked off, 0 left on the counter |
| 2 | `sort_language`: an instruction defines the mapping; 8 training templates plus **unseen paraphrases** at eval | +2 correct, −1 wrong or knocked off |
| 3 (stretch) | `insert_shapes`: through the matching hole in a lid (sim only) | +3 matching hole, −1 jammed or dropped |

- **Finalist selection:** mean sim score on a **held-out sim variant** (different textures, lighting and camera jitter; secret seeds).
- **Sim gate**, which you must pass to reach the finals:
  - no abort, watchdog, crash or lost connection
  - **0 clipped steps**
  - **≥ 27 Hz command rate**, measured both on the sim clock and on the policy's own wall-clock latency (`policy_hz_rt`)
- **Finals:** 3 real-robot episodes:
  - `sort_fixed`
  - `sort_language` with a known template
  - `sort_language` with an unseen instruction (weight ×1.5)

  Ranking = real-robot score. Sim score breaks ties.
- **Allowed:** any method and any public model or data, external APIs at your own risk.
- **Not allowed:** privileged sim state in the submission, hard-coded layouts, tuning on the held-out variant.

**Difficulty knobs** (`STARTER_PATHS.md`; Aalto: "Finals values are not announced"):

| Knob | Easier | Harder | Now (code) |
|---|---|---|---|
| Objects per episode | 3 | 5 | 3–5 |
| Instruction | colour only | colour + shape, negation, held-out paraphrases | colour only, 8 training templates; held-out templates exist |
| Layout | spread out, yaw ±15° | min spacing, yaw ±45°, **distractor object** | yaw ±45°, ≥ 8 cm spacing, no distractors |
| Time limit | 180 s | 90 s | 120 s |
| Hole clearance (rung 3) | +15 mm | +3 mm | +10 mm |
| Shapes with holes (rung 3) | circle only | all three | all three |

- Known object types: 3 colours (red, yellow, blue) × 3 shapes (cube, cylinder, triangle) (`interface/tasks.py`).
- Aalto doesn't say what a distractor looks like. A policy that only picks objects the instruction names doesn't need to know.

## 6. Submission contract

| Item | Requirement |
|---|---|
| Image | linux/amd64, CUDA **≥ 12.8** (RTX 5090 is Blackwell). Template: `aaltonomous/docker/submission.Dockerfile` |
| Server | Websocket + msgpack (openpi-style), port **8000**. Subclass `Policy` from `aaltonomous.deploy.policy_server` and call `serve()` |
| Startup | Listening within **120 s**, weights **inside** the image, no downloads |
| Limits | ≤ **32 GB VRAM**, ≤ **40 GB** image |
| Hand-in | Push to GHCR / Docker Hub, **pin the digest**, submit through the web form (link on Discord). The last image before the Sunday deadline is the one that runs in the finals |

Local test ladder:
1. `deploy.replay --synthetic 100`, which also checks ≥ 27 Hz
2. `deploy.runner --backend mock`, which needs no GPU
3. `sim.evaluate` in Isaac on a cloud RTX box, which exits 0 when the gate passes

## 7. Sim and compute

| Need | Detail |
|---|---|
| GPU | **RTX-class, ≥ 24 GB**: RTX Pro 6000 / L40S / A6000 / RTX 4090 / 5090. **Not A100 / H100** (no RT cores, so no camera images). Those are fine for training |
| Host | Driver ≥ 580.65.06, Ubuntu 22.04/24.04 x86_64, ≥ 8 CPU cores (physics runs on the CPU), ≥ 32 GB RAM, ≥ 80 GB disk. **On-demand, not spot**, with a persistent volume for checkpoints |
| Start | Docker image `aalto-sim:v1` (~30 GB), then `aalto sim`, `aalto check`, `aalto snap`, `aalto baseline`. The first start compiles shaders, which takes **5–10 min** |
| Speed | ~0.7× real time with one sim, so a 120 s episode takes ~220 s of wall time. One sim per instance, or you'll fail the 27 Hz gate |
| Ports | Head camera 55555, wrists 55556/7, head RGB-D 55560, scene service 55580. Robot state and commands go over **DDS domain 1, the same topics as the real G1** |
| Domain randomisation | `AALTO_DR=train aalto sim` (lights, colours, mass/friction, camera jitter, depth noise) |
| Privileged state | The scene service gives object poses: fine for training, RL rewards and data generation, **not allowed in a submission** |

## 8. Data drops

- **Drop 0 (Fri evening):** real teleop demos, ~20 successful per rung plus a few deliberately messy ones. Failed episodes are included too: it's **raw**, and you choose what to train on from `meta/aalto_episodes.jsonl`, which holds success labels, notes and warnings.
- **Drop 1 (Sat):** venue lighting, empty-scene RGB-D, real depth noise on the objects.
- **Two formats of the same episodes:**
  - LeRobot **v3.0**, with head depth
  - **GR00T** copy (LeRobot v2.1 + `modality.json`), RGB only
- `observation.state` = 28 values (`arm_q` + `hand_q`). `action` = 28 commanded absolute targets at 30 Hz.
- **Public G1 Dex3 data for pretraining:** `unitreerobotics/G1_Stack_Block`, `G1_Dex3_PickGum_Dataset`, `datamentorshf/G1_Dex3_BlockStacking_Dataset`. There is no public colour-sorting set.

## 9. Baseline and starter routes

- **Classical baseline:** HSV colour blobs plus head depth give a pose. Pinocchio IK plans a top-down grasp, which is carried to the bin. Planning runs in a background thread; motion comes in 10-tick chunks.
  - Sim (nominal scene): **76–82 % of objects sorted** in the evaluator. Earlier runs through the runner: 0/24.
  - It fails mostly on triangles (the pinch slips) and on the 120 s limit. Rung 1 only.
  - It's also the reference submission image (CPU only, 1.5 GB).
- **Five routes, all allowed, hybrids encouraged:**
  1. Classical: better grasps, Grounding DINO / SAM 2, cuRobo
  2. VLM planner over your own skills, which fits rung 2. Watch the latency, and you need an offline fallback
  3. IL / VLA: ACT, Diffusion Policy, SmolVLA, π0 / π0.5 (openpi), GR00T. Fine-tuning needs 80 GB GPUs; inference fits the 5090
  4. RL in Isaac Lab, then distil to a vision policy
  5. Real2sim: re-texture, depth-noise models, friction / PD fitting

## 10. What this means for a Rokoko-gloves idea

- **The demos are hand-tracking teleop already.** They were recorded with `xr_teleoperate`'s `teleop_safe.py --arm=G1_29 --ee=dex3 --input-mode=hand`, with speed caps of 0.9 rad/s on the arms and 3 rad/s on the fingers so the demos stay inside the safety filter.
  - That tool already retargets human hand keypoints to G1 arm IK and Dex3 joints, and publishes `rt/lowcmd` + `rt/dex3/*/cmd`.
  - A Rokoko glove stream could replace the Quest hand-tracking input. This is our inference: check the xr_teleoperate input layer.
- **The sim takes commands over DDS on the same topics as the robot** (domain 1). So a glove teleop tool that publishes those topics should drive the Isaac sim as well. The recorder `aaltonomous/data/record_demos.py` turns sessions into LeRobot data with `to_lerobot.py`.
- **More demos = the scarce resource.** The challenge says "sim is free, reality is scarce". Gloves + sim give us our own in-domain demos for rung 1 and rung 2 on top of the ~20 per rung they ship.
- **Two catches:**
  1. Dex3 has 3 fingers, so 5-finger glove data has to be retargeted down: thumb + index + middle.
  2. Gloves only track fingers. **Wrist and arm position need a Coil Pro or the Smartsuit** (Rokoko brings both), or a camera.
- **Real robot:** in the Aalto challenge, teams never get DDS or SSH access to Väiski. The Rokoko challenge separately offers "access to a Unitree G1 … in coordination with" the Aalto team. Live glove teleop of the real robot therefore depends on the organisers: ask both teams.
- **Sim teleop runs at ~0.7× real time.** The operator will feel lag unless the sim is paced differently for teleop. Untested.

## Open questions for mentors

1. Can a Rokoko team teleoperate the real G1 (Väiski or another unit), and when?
2. Is there a Coil Pro or Smartsuit we can borrow for wrist position? The hardware desk shows the gloves and the suit all checked out.
3. Does `xr_teleoperate` take a custom hand-keypoint input, or do we write our own glove → IK → DDS bridge?
4. Aalto and Rokoko are both **main** challenges, and we can enter only one. Which one fits a "gloves → demos → policy" project better? Rokoko judges teleop; Aalto judges only the autonomous policy.
5. **Distractors** (for Aalto):
   - If the finals use a distractor object, how is it scored if it ends up in a bin or knocked off?
   - Does a known colour on an unknown shape (e.g. a red star) count as "a red object"?
6. **Finals instructions** (for Aalto): will the finals use the "harder" instruction knob (colour + shape, negation), or only colour-only paraphrases?
7. **Tech challenges** (for the Junction organisers): can one submission enter several tech challenges at once (e.g. Gemma + Gemini + Nemotron)?
