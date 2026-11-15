# Junction submission: drafts (Sun 15 Nov ~07:45, Samer + Claude)

The Junction project page closes **Sun 10:00**. Fields: project name, punchline (≤ 200 characters), description
(≤ 5000), challenge, demo URL, source code, video, other links, presentation, tech challenges (Samer: Best use of Modal
+ Best use of Gemini API). Everything below is a draft: edit freely. Each number has a source (list at the end).

## Check before submitting
- **Challenge:** on the form, "Robot Teleoperation" is **Rokoko's** mocap-glove challenge. Our robot work is **Aalto's
  "Aaltonomous Humanoid"**. Its judging: real-world result 40 %, generality 25 %, originality 20 %, presentation 15 %.
  Pick Aalto's unless the team chose Rokoko on purpose.
- **The real-robot claim:** at 06:55 the G1 picked the yellow cube and dropped it into a box, autonomously. The
  instruction it got said yellow → centre box. It landed in the robot's right box (the left one in the phone video),
  because the boxes stood ~11 cm away from where the default layout puts them (`docs/research/real-run-0655.md`).
  Say "picked a block and placed it in a box", not "sorted it correctly" (unless Aalto counted it as correct).
- **Source link:** the repo is `github.com/EmiilsShmits/bot-icelli`. Check it is public, or the judges can't open it.

## Project name
**bot-icelli**, or longer: *bot-icelli: a humanoid that sorts on its own*

## Punchline (≤ 200 characters)
<!-- punchline-a -->
A Unitree G1 humanoid that sorts blocks on its own: Gemini reads the task, our vision and planner move the hands, and Isaac Sim runs on Modal took it from simulation to the real robot.
<!-- /punchline-a -->

Alternative:
<!-- punchline-b -->
From simulation to a real humanoid in 48 hours: a G1 that looks, understands the instruction with Gemini, and picks and places blocks by itself.
<!-- /punchline-b -->

## Description (≤ 5000 characters)
<!-- description -->
**The problem.** A humanoid now costs around €50,000, but teaching it a task can cost far more. End-to-end Vision-Language-Action models need expensive teleoperation data, retraining whenever the task or room changes, and when they fail you are debugging a black box.

**Our thesis.** Robotics should work like software: modular, inspectable and continuously improvable. Models decide *what* to do; small, readable skills decide *how* to move; every step leaves a log you can read.

**What we built.** Bot-icelli is the brain for Aalto's Unitree G1 humanoid. From its head camera and a free-text instruction ("put the purple blocks in the left box…"), it sorts blocks into three boxes on its own.
- **Gemini understands.** It reads the instruction, names each object's colour and shape, and assigns each one a box. In our agent version (Google ADK), Gemini chooses every action by calling our skills as tools, with Gemini Robotics-ER locating objects and bins.
- **Python skills act at 30 Hz.** Object and box detection from depth, inverse kinematics, face-aligned grasps, hand-overs between arms, smooth motion and gravity compensation.
- **Every step is checkable.** A grasp check reads the fingers and retries a miss; the robot calibrates its camera every episode from its own arms.
- **Safe by design.** The model only picks moves the planner has already verified, and a small on-board Gemma model takes over if the network drops.

**Why modular paid off.** Each real-robot problem was found in the logs and fixed in one module, with no retraining: arm sag, a stuck finger joint, centimetres of aim error, boxes 11 cm off their expected place, and an elbow pushing into the robot's own body that no simulator showed. On the real G1, it picked up a block and placed it in a box fully autonomously.

**Modal.** Our robot lab: from our laptops we ran Aalto's Isaac simulator and official evaluator on cloud GPUs, many evaluations in parallel, in a scene re-rendered to look like the real venue. We also fine-tuned a π0.5 VLA and a Gemma 3 1B instruction parser on H100s. Result: over 90 % of objects sorted in venue-style simulation, with zero safety violations.

**Our vision.** Describe a task to Gemini, execute it safely with inspectable skills, learn from failures in the cloud, and redeploy improved skills in minutes.

**Built with:** Gemini API, Gemini Robotics-ER, Google ADK, Gemma 3, Modal, Isaac Sim, Unitree G1, π0.5, Pinocchio, OpenCV.
<!-- /description -->

## Best use of Modal (tech challenge)
Judged on: effective use of Modal 40 %, technical ambition 25 %, impact 20 %, demo 15 % (a live app the judges can use).
<!-- modal -->
Modal was our robot lab in the cloud. We had no robot to practise on, and a laptop can't run Aalto's Isaac simulator, so everything heavy ran on Modal:
- **Simulation at scale.** Aalto's Isaac Sim and their official evaluator on L40S GPUs. Each candidate policy was scored with the same code the organisers use, many runs in parallel, on scene variants we built: the real venue's look and colours, a leaning robot, a moved camera, the shape lid. 23 of our 84 logged experiments ran there, plus all of Marcus's pipeline runs.
- **Data generation.** Aalto's scripted oracle, run in Isaac on Modal, recorded demonstrations straight into LeRobot v3 datasets in a Modal Volume, with the same features as Aalto's real-robot data, so the two merge.
- **Training.** π0.5 vision-language-action fine-tuning on H100s. Our Gemma 3 1B instruction parser was retrained on a Modal H100 overnight.
- **Inference and evaluation.** VLA checkpoints and our Gemini agent served next to the simulator, scored by the evaluator; results and head-camera videos in Volumes.
- **One CLI.** `modal run sim/modal_sim.py --action eval-policy|eval-model|eval-adk|datagen|baseline …`: the whole team launched runs from Windows laptops.
<!-- /modal -->
If the simulator demo page gets deployed on Modal before 10:00, add one line about it here: it is the "demo" criterion.

## Best use of Gemini API (tech challenge)
They ask: what problem, how Gemini is integrated, what is innovative, why Gemini matters.
<!-- gemini -->
**Problem.** A humanoid must turn a free-text instruction and one camera image into the right action for every block. The real venue breaks the simple tools: under its lights, orange, yellow and purple drift out of fixed colour ranges, and the instructions name colours, shapes, negations and distractors.

**How Gemini is integrated.**
1. **Inside the policy that runs on the robot:**
   - Gemini names each newly seen object's colour and shape from a crop of the head-camera image, and confirms blobs our colour ranges missed (kept only when it is sure of both).
   - It turns the instruction into a target box for every object.
   - It runs in a background thread, so the 30 Hz control loop never waits, and falls back to a fine-tuned Gemma 3 1B inside the image and then to rules.
2. **As the robot's planner:** an agent built with Google's ADK.
   - Gemini looks at the camera and calls our motion skills as tools (look, pick-and-place, hand-over, check plan…), about 6 calls per episode.
   - 10 of 12 objects sorted in simulation; a Gemini Robotics-ER version of it ran on the real G1.
3. **As a judge and a teacher:**
   - We tested Gemini models as grasp monitors ("is the block in the hand?") against our finger-angle rule.
   - Gemini helped generate the tricky instruction paraphrases our small Gemma parser learned from.

**Why Gemini.** It does the parts that need understanding (language, and objects that look different from the training data) and leaves positions and joint targets to a geometric planner. So every move it asks for is one the planner has already checked.
<!-- /gemini -->

## Video (unlisted YouTube)
Ready clips, no audio, in `artifacts/video/` (git-ignored, on Samer's laptop):
- `phone_yellow_pick.mp4`: phone video 0:09–0:19.5 (the G1 picks the yellow block and drops it in a box).
- `robot_view_yellow_pick.mp4`: the same pick through the robot's head camera, episode time 10.5–22.5 s.

| Time | Shot | Source |
|---|---|---|
| 0:00–0:10 | The G1 picks the yellow block and drops it into a box | `phone_yellow_pick.mp4` |
| 0:10–0:22 | The same moment from the robot's own eyes: "this is all it sees" | `robot_view_yellow_pick.mp4` |
| 0:22–0:45 | How it works, 4 cards over sim footage: See → Understand (Gemini) → Move → Check | sim video from Samer |
| 0:45–1:10 | Isaac on Modal: several runs side by side, "84 experiments, venue look, leaning robot" | `aalto-sim-out` videos |
| 1:10–1:35 | Sim to real: sag 15 mm → 2 mm, a stuck finger, boxes moved 11 cm → measured | slides / joint-log plot |
| 1:35–1:50 | Team and what's next | |

The second half of the phone video (two misses) is left out.

## Presentation (slide outline)
1. **bot-icelli:** a humanoid that sorts on its own (photo from the phone video).
2. **The challenge:** G1 with Dex3 hands, 3 boxes, a free-text instruction, only the head camera; sim first, then the real robot.
3. **Our system:** See → Understand (Gemini) → Plan and move → Check, with offline fallbacks.
4. **Self-calibration:** the robot finds its own arms in depth → camera pose and lean; the box finder.
5. **Gemini:** labels and instructions in the policy; the ADK agent; Gemma 1B as the offline layer.
6. **Modal:** Isaac at scale, data generation, π0.5 and Gemma training (numbers above).
7. **Real robot:** the pick and place, and what the logs taught us → the fixes in the next image.
8. **Results and next steps.**

## Sources for the numbers
- 92 % (11/12) in Isaac with Aalto's randomisation, 0 clips: `eval/RESULTS.md` e-072 (`final-v16`).
- Triangles 21/24 vs 12/24: e-081. Objects sorted 36/49 → 43/49 with it: e-082.
- 84 experiments, 23 tagged Modal: rows of `eval/RESULTS.md`.
- Gemma 1B 94.7 % vs rules 86.7 % (T2a): `training/instruction_parser/README.md`.
- ADK agent 10/12, π0.5 4/12, 125 demonstrations: `modal_pipeline/TEAM_HANDOVER.md` §5.
- Real robot (sag 11–15 mm → 1–3 mm, stuck finger, aim 2 cm, boxes 11 cm, the pick): `docs/research/real-run-0619.md`,
  `docs/research/real-run-0655.md`.
- Grasp monitor study: `docs/research/model-monitor-oracle.md`.
