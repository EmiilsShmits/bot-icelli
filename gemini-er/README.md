# gemini-er/: the ADK agent with Gemini Robotics-ER in control

**Purpose:** a Google ADK agent in which the Gemini Robotics-ER model (`gemini-robotics-er-2-preview`) controls the
robot in real time through general tools, in the Isaac sim and on the real robot. Yes/no checks (is the hand above the
bin, is the object in the bin) go to the Gemini Decisions API (`gemini-decision-1`).
**Owner:** Marcus
**Source:** a copy of branch `gemini-er` of Marcus's repo
[github.com/marcusoberg/junction2026](https://github.com/marcusoberg/junction2026) (commit 9524855, Sun 15 Nov),
without its git history and without `sim_out/` (run outputs and videos, 4 GB: read them there).
`modal_pipeline/` is an older copy of the same repo (commit 4521b47) with the team's changes; this folder does not
replace it and nothing here was merged into it.

What is new against `modal_pipeline/adk_agents/` (all in `adk_agents/robot_sorter/`):
- `er.py`, `tools.py`, `agent.py`: Robotics-ER as the controlling model, and as a tool that finds the blocks.
- `bins.py`: the three bins are measured from the head camera (ER draws a box around each bin, the depth image gives
  the near wall, the width and the rim height) instead of read from `scene.yaml`.
- A firm grip for the real hands (`ROBOT_GRIP=firm`), and a check of the table in the depth image for an object that
  was never lifted (the real hands' finger sensors cannot tell).
- `localik.py` and the tools `find_bins`, `grab`, `drop_in`, `move_hand`, `grip`: the hand is moved by local inverse
  kinematics (least joint movement from the present pose), a second way to pick and release that does not use the
  organisers' planner.

Everything found wrong or unclear in Aalto's material: [`ORGANIZER_ISSUES.md`](ORGANIZER_ISSUES.md).
The agent's own README: [`adk_agents/README.md`](adk_agents/README.md).

## Inputs → Outputs
- **In:** Aalto's repo (`../third_party/aaltonomous-humanoid`, found automatically by `sim/modal_sim.py`); a Gemini
  API key in `adk_agents/robot_sorter/.env` (copy `.env.example`; never commit `.env`); a Modal workspace for the sim.
- **Out:** submission images in Marcus's private Docker Hub repo `maroberg/robot-sorter`:
  - `gemini-er-6`: for the real robot.
  - `gemini-er-6-sim`: the same with two settings that are right for the Isaac sim only (`submission/adk-sim.Dockerfile`).

## How to run
From this folder, with the `modal` CLI logged in and the key in `adk_agents/robot_sorter/.env`:
```bash
modal run --detach sim/modal_sim.py --action eval-adk --trials 1 --seed 1001 --tag er-1
modal run --detach sim/modal_sim.py --action sweep --tag s1 --sweep "nominal:sort_fixed:1001"
#   scenes for the sweep: nominal-real (firm grip, finger sensors ignored: the real robot's code path),
#   nominal-localik / nominal-real-localik (only the local-IK tools), see SCENES in sim/modal_sim.py
```
Build the image (needs Aalto's repo as `aaltonomous-humanoid/` inside this folder; Docker does not follow a link out
of the build folder, so copy or clone it there; it is git-ignored):
```bash
docker buildx build --platform linux/amd64 -f submission/adk.Dockerfile -t <registry>/<name>:<tag> --load .
```
`ROBOT_TOOLS_OFF=<tool>,<tool>` withholds tools from the model (e.g.
`pick_and_place,pick,place,hand_over,check_plan,choose_arm` leaves only the local-IK way).

## Status
- **Now:** Isaac sim on Modal, seed 1001, one episode each, 0 clipped steps in all: all tools 5/5 objects sorted;
  the real robot's code path with only the local-IK tools 5/5; only the local-IK tools with the sim grip 5/5 (3/5
  before a missed grip was remembered). An episode with the local-IK tools takes about 105–110 s, against 101 s.
- **Not tested on the real robot:** the firm grip, the measured bins and the local-IK tools.
- **Next / open:** no check that the hand is empty after a release; an object may stick in the opened hand after the
  firm grip.

## Gotchas
- The image contains `adk_agents/robot_sorter/.env`, i.e. the Gemini API key. Keep the image private.
- The agent needs the network for every decision; there is no offline fallback (a choice, against the working rule in
  `AGENTS.md`).
- The policy sends no `arm_tau_ff`: the gravity compensation is expected from Aalto's runner, so it is not applied twice.
- `sim_out/` is not in this copy and is git-ignored here.
