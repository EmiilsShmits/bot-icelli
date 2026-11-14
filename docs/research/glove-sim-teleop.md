# Controlling the Aalto sim with Rokoko gloves: research

**Question:** how could we drive the simulated G1 with Rokoko gloves + Coil Pro, and record what we do as training demos? Where do we start?

**Short answer:** most of the pieces exist in Aalto's starter code: commanding the sim, the safety filter, arm IK, a demo recorder that already works with the sim, and conversion to LeRobot. The missing parts are viewing the sim live and the glove → joint-target bridge.

**Start by running the sim on its own, then drive it from a script, then by keyboard, and only then add the gloves.**

Researched 2026-11-14 from the Aalto repo (pinned `36daf5b`, plus the reverted commit `3c11147`) and Unitree's `unitree_sim_isaaclab` README. Nothing here is tested yet.

## 1. What already exists

### How the sim takes commands
The Aalto sim (task `Aalto-Sort-G129-Dex3-Joint`, built on Unitree's `unitree_sim_isaaclab`) listens on **DDS domain 1**, on the same topics as the real G1:
- `rt/lowcmd`: arms, motors 15–28
- `rt/dex3/left/cmd`, `rt/dex3/right/cmd`: hands

Unitree's README says the sim "can be integrated with xr_teleoperate for teleoperation-based data collection", because the topics match the real robot.

There are two ways to command it from Python:

| | **A. Through `AaltoEnv`** | **B. Publish DDS directly** |
|---|---|---|
| How | `env = AaltoEnv(backend="sim")`, then `env.step({"arm_q_target", "hand_q_target"})` at 30 Hz | Publish to `rt/lowcmd` + `rt/dex3/*/cmd` (what xr_teleoperate and Aalto's own teleop do) |
| Safety filter | **Yes**: same limits as the submission. More than 30 clipped steps ends the episode | **No**: we must limit speed ourselves (Aalto's teleop capped 0.9 rad/s arms, 3 rad/s fingers) |
| Timing | Paces 30 Hz on the **sim clock** (`interface/env.py`) | Our own timing |
| Returns obs | Yes: all cameras + joints each step | No: read separately |
| Code | `aaltonomous/interface/env.py`. Its sim backend already uses xr_teleoperate's `G1_29_ArmController` internally (`interface/backends.py`) | Aalto's `teleop_safe.py` is **not in the public repo** |

### Recording demos
- **Aalto's recorder works with the sim:** `aaltonomous/data/record_demos.py --backend sim` passively records DDS commands + cameras at 30 Hz while something else drives the robot. That's how Drop 0 was made, on the real robot. It has keys for start / stop / success / fail / discard, and layout cards for consistent resets.
- **Conversion:** `aaltonomous/data/to_lerobot.py` converts the recordings to **LeRobot v3.0 + a GR00T copy**, the same format as Aalto's demos.
- **Alternative:** Aalto's runner (`deploy/runner.py --backend sim --log-images`) logs every tick, cameras included, if teleop is wrapped as a "policy".

### Moving the arm from a hand position (IK)
- **Aalto's baseline:** `baselines/classical/kinematics.py`, `ArmKinematics.solve(side, target, arm_q_seed)`. Pinocchio IK: target pose → 7 arm joints.
- **xr_teleoperate's arm IK:** takes a wrist pose (SE(3)).

### Moving the fingers
- **Simple:** blend between Aalto's postures in `baselines/classical/config.yaml` (`hand.open`, `closed`, `release`; left-hand order) based on how curled the glove fingers are.
- **Full:** xr_teleoperate's `unitree_dex3.yml` maps a 25-point human hand onto Dex3's 7 joints (thumb, index, middle). See [`rokoko.md`](rokoko.md) §4.

### Seeing the sim (needed for teleop)
The sim runs **headless** by default. Options:

| Option | What you see | Status |
|---|---|---|
| Camera streams over ZMQ (head 55555, wrists 55556/7) through an SSH tunnel, shown by a small viewer on the laptop | The robot's own camera views | Available. Aalto's docs suggest it for headless viewing |
| WebRTC camera streams in the browser (ports 60001–60003) | Same, in a browser | Supported by Unitree's image server, but **disabled** in Aalto's config (`sim/teleimager_aalto.yaml`: `enable_webrtc: false`) |
| **Full Isaac Sim window over VNC** | Free 3D view of the whole scene | Aalto added a Verda VNC setup (commit `3c11147`, Fri 21:51), then **reverted it** minutes later. It may come back; ask Aalto |
| `aalto snap` | Still images | Not usable for live teleop |

### The gloves
- **Rokoko SDK:** runs on macOS 14+ (Apple silicon), Linux and Windows. Streams hand joints at 83 Hz; the Coil Pro adds wrist position. Details in [`rokoko.md`](rokoko.md).

## 2. Where each part runs
- **Sim:** a cloud RTX machine (Verda), ≥ 24 GB, not A100/H100. A Mac or the Jetson can't run Isaac Sim.
- **Gloves + Rokoko SDK:** a laptop at the venue (USB, or Wi-Fi via a local router).
- **The bridge** (glove data → IK / finger mapping → commands): best run **on the sim machine**, next to the sim. The laptop only sends small glove packets (e.g. through an SSH tunnel), and the video comes back the other way.
  - DDS across the internet is impractical, because its discovery relies on the local network *(general knowledge, verify)*.

## 3. A step-by-step path (proposal, not agreed)

| Step | What | Done when |
|---|---|---|
| **0. Run the sim on its own** | Verda RTX machine → `aalto sim`, `aalto check`, `aalto snap`, `aalto baseline` ([runbook](../runbooks/verda-sim-setup.md)). Then view the head camera live on a laptop through an SSH tunnel | Baseline score table printed; live camera view on the laptop |
| **1. Drive it from a script** | Small Python script with `AaltoEnv(backend="sim")`: move one arm slowly, open and close a hand | Arm moves, 0 clipped steps |
| **2. Keyboard teleop + recording** (no gloves yet) | Keys move a wrist target → IK → `env.step`. Record with `record_demos.py --backend sim`, convert with `to_lerobot.py` | One full human-driven episode saved as a LeRobot dataset |
| **3. Gloves for the fingers** | Rokoko SDK on the laptop → finger curl → Dex3 (posture blending first). Wrist still on keyboard | Glove closes the robot hand in sim |
| **4. Coil Pro for the wrist** | Coil Pro wrist pose → map Coil frame to the robot's frame → IK → arm follows the hand | Pick-and-place of one block by glove |
| **5. Record demos, test value** | Record episodes; train with and without them; compare in sim (see [`rokoko.md`](rokoko.md) §6) | Two rows in `eval/RESULTS.md` |

Steps 0–2 need no gloves and are useful for the sim and data work anyway: running the sim, controlling it, and recording datasets.

## 4. Risks and unknowns
- **Sim runs at ~0.7× real time.** `AaltoEnv` paces on the sim clock, so the robot lags behind a real-time hand. The same hand speed is also larger per sim second, which means more speed-limit clips. Teleop has to be slow, or the bridge has to rate-limit.
- **Network delay** between the laptop and the Verda machine: glove data out, video back.
- **Safety filter clips** (option A): more than 30 clipped steps ends the episode. Demos recorded with clips teach the model bad motion.
- **No live view** until we set one up (tunnel + viewer, or VNC if Aalto restores it).
- **Frame mapping:** Coil Pro coordinates ↔ robot pelvis frame (origin, scale, heading) need calibrating.
- **Coil Pro interference** from metal tables and laptops near it.
- **Aalto's `teleop_safe.py`** (what they used for Drop 0) isn't public. Ask whether they can share it.

## 5. Open questions
1. Will Aalto restore the Verda VNC setup (full sim view)?
2. Does anyone on the team have an RTX laptop with ≥ 24 GB VRAM, to run the sim locally? If not, Verda only.
3. Can Aalto share `teleop_safe.py`, or its speed-limiting settings?
4. Rokoko SDK licence: form submitted and accepted?
