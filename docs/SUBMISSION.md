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
**What we built.** A Unitree G1 humanoid with three-finger Dex3 hands that clears a table on its own. It looks with its head RGB-D camera, reads a free-text instruction ("put the purple blocks in the left box…"), and picks and places each block into one of three boxes. No teleoperation, no markers, no object positions from the simulator: one Docker image that Aalto runs on the real robot.

**How it works.**
- **Seeing.** The head depth image gives the table plane, each block's position, and its shape from the top face (cube, cylinder, triangle). Colours come from HSV ranges tuned on the real camera's footage. The robot calibrates itself every episode: it finds its own arms in the depth image and fits them to a hand model. That gives the camera pose and how far the body leans (6° in our last real run), without markers. The three boxes are measured from depth too, so the drops follow the boxes when they move.
- **Understanding, with Gemini.** Gemini names each new object's colour and shape from an image crop, rescues blobs our colour ranges miss, and turns the instruction into a target box for every object. It runs in a background thread, so the 30 Hz control loop never waits. If the network fails, a fine-tuned Gemma 3 1B inside the image takes over (94.7 % on unseen instructions, against 86.7 % for rules), then a rule parser.
- **Moving.** Aalto's inverse-kinematics planner, extended with:
  - face-aligned grasps, and our own grasp for standing triangles (21 of 24 picked in Isaac, against 12 of 24);
  - hand-overs between the arms, and retries that remember what failed;
  - jerk-limited smooth paths inside the speed limits (0 safety clips);
  - gravity feed-forward torque, so the arm lands where it is told. On the real robot the arm sagged 11–15 mm without it and is 1–3 mm off with it.
- **Checking.** A held block stops the thumb and index joints, and a grasp check reads exactly that. On the real robot it caught every miss and retried.
- **Two more brains, explored in parallel.**
  - An agent built with Google's ADK: Gemini looks at the camera and calls our motion skills as tools (10 of 12 objects sorted in sim).
  - A π0.5 vision-language-action model, fine-tuned on 125 demonstrations we recorded in simulation (still learning: 4 of 12).

**Sim to real.** We logged 84 experiments, almost all in Aalto's Isaac simulator on cloud GPUs. They covered a "venue look" re-rendered to match the real hall, a leaning robot, a shifted camera and the shape-lid task. Our final system sorts 11 of 12 objects in Isaac with Aalto's scene randomisation.

On the real G1 it picked a block from the table and placed it in a box, fully autonomously. Between real runs we went through every joint log and camera frame, and fixed each problem we found in the next image:
- the arm sag;
- a stuck finger joint on the left hand (the grasp check now reads only the pinch joints);
- a 2 cm aim error per arm;
- boxes standing 11 cm from their default place;
- an elbow pushing into the robot's own body on reaches across it, which the simulator never shows (such plans are now refused).

**What we learned.** Simulation gets you most of the way. The last centimetres are calibration, and the robot's own logs are the best sensor for it.

**Team.** Emīls Šmits, Marcus Öberg, Samer Haddadin, Tiya Kumar.
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
