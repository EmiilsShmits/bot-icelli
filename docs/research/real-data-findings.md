# Aalto's real-robot data drops: what's in them (checked Sat 14 Nov)

**Question:** what can we actually learn from Aalto's real demos, and can we train on them as they are?
**Short answer:** not as they are. Every episode commands the arms faster than the safety filter allows, so a policy that imitates them gets clipped (the sim gate allows 0 clips). The data is still very useful for perception, calibration and checking grasps on the real hand.

Checked on Sat 14 Nov ~12:15 from the two Hugging Face datasets. Reproduce with `python data/tools/drop_health.py <repo id>` (joint data only, ~5 MB, no videos).

## 1. What the drops contain

| | `zupermiez/g1_pick_cube` (Sat 01:54) | `zupermiez/g1_junction_drop_2` (Sat 11:37) |
|---|---|---|
| Episodes / frames | 20 / 11,720, median 16.7 s | 48 / 14,548, median 8.3 s |
| Tasks | `pick up cube.` | `Put the orange cube into the right box.` (16), `Put the purple cube into the center box.` (14), `Put the orange cube into the left box.` (13), `Put the orange triangular prism into the right box.` (5) |
| Cameras | `cam_high` (head), `cam_left_wrist`, `cam_right_wrist`: RGB 640×480 | same; **no head depth** |
| Labels | **none**: no `meta/aalto_episodes.jsonl` (no success label, notes or warnings) | none |
| Teleop | Meta Quest 3 | Meta Quest 3 |

- **The format differs from Aalto's `DATA_CARD.md`:** the camera keys are `cam_high` / `cam_*_wrist` (not `head_rgb` / `*_wrist_rgb`), there's no depth and no sidecar. `observation.state` and `action` are 28 values in the interface order (left arm 7, right arm 7, left hand 7, right hand 7).
- **The task text uses the real colour names and "box":** "orange", "purple", "box". The sim and Aalto's templates say "red", "blue", "bin".
- **Every drop-2 episode is one object** ("Put the X into the Y box"). That's the same shape as a planner handing a sub-task to a skill.
- The pick-cube README calls itself "data drop 1"; that's not the repo's "Drop 1" (venue lighting + depth capture, still expected).

## 2. Speed: the demos break the safety filter's caps

| | drop 2 | pick cube |
|---|---|---|
| Episodes with arm commands over 1 rad/s | **48 / 48** | 19 / 20 (the 20th doesn't move) |
| Ticks over the arm cap | 2,768 of 14,548 (19 %) | 1,126 of 11,720 (10 %) |
| Typical max arm speed (5-tick median filter) | 2–4 rad/s (median 2.97) | 2–4 rad/s |
| Spikes (> 5 rad/s in one tick) | 5 episodes, up to 11 rad/s | 4 episodes; ep 13 and 16 reach 21–28 rad/s (the "spasms") |
| Typical max finger speed | 12–25 rad/s (cap 3) | 13–26 rad/s |
| Slow-down needed to pass the filter | ×3.1 arms only, ×6.0 with fingers | ×3.2 / ×5.3 |
| Median episode at legal speed | 8.3 s → **27 s** (arms) / 50 s (arms + fingers) | 16.7 s → 58 s / 101 s |

- The over-cap ticks are spread over the shoulder-pitch, elbow and all wrist joints, so it's the operator's speed, not one broken joint.
- Aalto's `RECORDING.md` says demos are made with teleop caps of 0.9 rad/s (arms) and 3 rad/s (fingers). These drops clearly weren't. Worth asking.

**What it means:**
1. **A policy imitating these actions commands > 1 rad/s.** The filter clips those steps, and the sim gate allows 0. Retime (slow down) and median-filter the demos before training, or keep a speed guard on the policy's output. The guard alone shifts the timing the model learned, so retime as well.
2. **Human-style motion at legal speed is too slow for 4–5 objects in 120 s:** about 27 s per object for the arms alone. Time-optimal planned motion (the classical planner moves at ~0.97 rad/s) and using both arms at once matter more than copying the human.
3. **Train motion mostly on legal-speed sim demos** (oracle/scripted, glove teleop through `AaltoEnv`). Use the real episodes for what only they have: real images and the real hand's behaviour.

## 3. Grip: the real fingers show when they're holding something

- In the most-closed 20 % of each drop-2 episode, the commanded finger angles are a median **0.36 rad** (summed over the 6 finger joints of the busy hand) more closed than the measured ones. Elsewhere the gap is ~0.02.
- Sustained over 1 s, the largest gap per episode is **0.42–1.69 rad**, in every episode.
- So `hand_q` (in `obs`) probably tells us whether a grasp is holding an object on the real Dex3 (soft gains kp 1.5 / kd 0.2: blocked fingers stall). That makes **grasp verification and retry** possible without tactile sensing.
- **Caveat:** part of the gap may be lag from the very fast finger commands. Check against a hand closing on air (sim, plus any real "miss" episodes) before trusting a threshold.

## 4. What else the real data is good for

| Use | How | Why it matters |
|---|---|---|
| **Colour model for the real objects** | Label orange / yellow / purple pixels in `cam_high` frames (by hand, or have a VLM point at the objects), fit thresholds or a small classifier | The baseline's HSV ranges were tuned on the sim's red / blue (see `aalto-discord-notes.md`) |
| **Head-camera calibration check** | Project the palm position (FK from `arm_q` with the URDF + `calibration.yaml`) onto `cam_high` frames and measure the offset to the hand in the image | Aalto's head extrinsics are still provisional (URDF, not checked with the AprilTag). A 1–2 cm error makes 45 mm objects miss |
| **System ID for the sim** | Compare commanded vs measured arm angles (0.15–0.4 rad apart at teleop speed) and fit the sim's PD gains / delay | Physics fidelity (Aalto's "real2sim" route) |
| **Human grasps for triangles** | Drop-2 episodes 16–20 are triangular prisms: read the hand posture and wrist angles at grasp time | Triangles are the baseline's main miss |
| **Sub-task phrasing for a VLA skill** | Instructions in the form "Put the {colour} {shape} into the {position} box." | If π0.5 becomes a per-object skill, the planner should call it with this exact phrasing |
