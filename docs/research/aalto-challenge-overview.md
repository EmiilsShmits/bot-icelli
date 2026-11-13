# Aalto challenge: plain-language overview

A short explainer for anyone new to the challenge. Facts only.
- Details and numbers: [`aalto-humanoid.md`](aalto-humanoid.md)
- Full challenge text: [`../challenges/main/aalto-university--aaltonomous-humanoid.md`](../challenges/main/aalto-university--aaltonomous-humanoid.md)
- Aalto's own docs: `third_party/aaltonomous-humanoid/aaltonomous/docs/participants/`

## In one sentence
Build the "brain" that makes Aalto's humanoid robot **Väiski** sort small coloured blocks into three boxes **completely on its own**. Almost all development happens in a simulator; the best teams run on the real robot on Sunday.

## The setup
- **Robot:** a Unitree G1 humanoid behind a counter. Legs and waist are locked; only **two 7-joint arms** and **two 3-finger Dex3 hands** move (28 joints).
- **Objects:** 3–5 printed blocks, ~4.5 cm: cubes, cylinders, triangular prisms, in red, yellow, blue. Placed randomly, rotated up to ±45°.
- **Boxes:** three identical orange boxes in a row behind the objects (left, centre, right), told apart only by position.
- **Time limit:** 2 minutes per round ("episode").

## What our program does
Our program ("policy") runs as a small server in a Docker container. **30 times a second** it receives:
- the head camera (colour + depth) and two wrist cameras
- the current joint angles
- a text instruction

It answers with target angles for all 28 joints. Aalto's software passes them to the robot through a **safety filter**.

## The tasks ("rungs" = difficulty levels)
| Rung | Task ID | What | Points per object |
|---|---|---|---|
| 1 | `sort_fixed` | Always: red → left, yellow → centre, blue → right | +1 correct, −1 wrong box or knocked off |
| 2 | `sort_language` | A text instruction sets the rule, in phrasings we haven't seen | +2 correct, −1 wrong or knocked off |
| 3 (stretch) | `insert_shapes` | Push each block through the matching hole in a lid (sim only; real robot only as a bonus) | +3 / −1 |

## How the winner is chosen
1. **Fri–Sat:** teams build and test in Aalto's Isaac Sim simulation of the exact scene.
2. **Submit** a Docker image. The last one before the Sunday deadline counts; the exact time is TBA.
3. **Organisers score every image in sim** on a version of the scene we can't train on (different textures, lighting, positions). Only images that pass the safety check qualify.
4. **The top ~5 run on the real robot on Sunday:**
   - rung 1
   - rung 2 with a known instruction
   - rung 2 with an unseen instruction, weighted ×1.5

   **The real-robot score decides the winner**; the sim score breaks ties.

**Judging:**
- real-world result 40%
- generality 25%
- originality 20%
- presentation 15%

**Prize:** €2,000 + a visit to the Aalto robotics lab.

## The rules that bite
- **Speed limits:** each command may change by at most 1 rad/s (arms) / 3 rad/s (hands). **A single violation fails the sim check.**
- **At least 27 commands per second.** Slow AI models must think in the background while the robot keeps getting commands.
- **Only camera and joint inputs** inside the submission. No true object positions from the simulator.
- **Image limits:** starts within 2 minutes, weights inside it, fits a 32 GB RTX 5090.
- **Nobody touches the real robot.** Aalto runs our image, with staff at the emergency stop.
- **No guaranteed internet at the finals** (Aalto's repo docs; the challenge page doesn't mention it). External API calls are allowed at our own risk, so they need a fallback.

## What Aalto gives us
- **Simulator:** a Docker image (Isaac Sim + Isaac Lab + the scene). Needs a rented RTX-class GPU ≥ 24 GB (not A100/H100); runs at ~0.7× real speed.
- **Starter code** (`third_party/aaltonomous-humanoid`):
  - robot interface, safety filter, policy-server template
  - scoring tool
  - a classical baseline that sorts ~80% of objects in an easy sim scene (rung 1 only)
- **Real-robot demos** (Hugging Face, links on Discord):
  - **Drop 0** (Fri evening): ~20 human-teleoperated demos per rung (rungs 1 and 2), raw, failures included
  - **Drop 1** (Sat): venue lighting and depth-noise reference data
- **Mentors:** Erkka Lehtonen and Viktor Solianoi, plus ~30 Aalto Robotics Club volunteers. Questions go to the Junction Discord.

## Approaches they name (any mix allowed)
- classical: camera → find blocks → compute arm motion
- an AI planner calling our own pick/place skills
- imitation learning / fine-tuning a robot model (π0, GR00T, ACT)
- reinforcement learning in the simulator
- making the simulator match reality

**What they'd love to see:**
- works when reality differs from the sim
- general ideas
- doing a lot with very little real data
