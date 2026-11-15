# Real robot, Sun 15 Nov 06:55: our image `final-v16-real`, one block picked and placed

Run `bot-icelli_20261115_065556` (Aalto's export: container log, `episode_000.npz` at 30 Hz, head-camera video) and
Samer's phone video of the same run (`IMG_0726.MOV`, not in git). Image
`ghcr.io/samer-cyber/bot-icelli-policy@sha256:b998bb9f…` (`final-v16-real`, 709c393). Task sort_fixed, instruction
"red → left bin, yellow → center bin, blue → right bin". Interrupted at 47 s. Analysed Sun ~07:20 by Samer + Claude:
forward kinematics of `arm_q_cmd` vs `arm_q` with Aalto's `ArmKinematics`, hand joints, head-camera and phone frames.

## What happened
| t (s) | Pick | Arm | Result | Why |
|---|---|---|---|---|
| 10.9 | yellow cube (0.34, −0.07) | right | **picked, carried, released into a box**, but the robot's **right** box, not the centre one | grasp centred within ~1 cm. The drop went to `scene.yaml`'s centre (y 0), but the box row stood ~11 cm further to the robot's left than in the 06:19 run, so y 0 was the wall between the centre and right boxes |
| 22.5 | orange cube (0.30, +0.11) | left | missed. Grasp check "empty" (0.018 rad), retried | hand ~2 cm to the robot's left of the cube; a finger landed on the cube and tipped it |
| 31.3 | purple cube (0.33, +0.02) | right | missed. Grasp check "empty" (0.014 rad), retried | **the right elbow hit the robot's own body.** The plan (a reach across the midline) took the elbow to 9 cm from the midline beside the torso. The real elbow stopped at ~10 cm and the hand was pushed ~2 cm right (27 mm at the grasp point, shoulder roll error 0.094 rad), so a finger came down on the cube's top |
| 43.1 | orange again | left | **the crash at the end**, stopped by Aalto at 47 s ("interrupted") | the retry's alternative grasp planned the left elbow 2 cm from the midline. The real elbow stopped at ~11 cm against the body, and the arm kept pushing (shoulder roll error up to 0.55 rad, the head camera turned ~6°) |

- **Gravity feed-forward works:** at the grasps the measured arm is 1–3 mm from the commanded pose (06:19, without it: 11–15 mm low, 7–10 mm short).
- **Camera:**
  - Arm fit OK: lean 6.1°, base moved 32 mm.
  - The bin-outline fit was weak (0.29), so the calibration's x, y and yaw were kept, and with them the `scene.yaml` box positions.
  - Head-camera frames at t = 1 s: the box row is ~85 px (~11 cm) further to the robot's left than at 06:19, so the robot does not stand at the same place in every run.
- **Grip:**
  - The held yellow (foam) cube stopped the pinch joints only 0.03–0.05 rad short of the closed command: a weak squeeze.
  - Empty closes read 0.014–0.018 rad.
  - The grasp check (thumb + index, 0.03 rad) called every pick right, and both misses were retried.
- **Right hand:** its thumb's bending joints (thumb_1, thumb_2) moved 0.3–0.4 rad on every close in the joint log. The rotation joint (thumb_0) is never commanded and sat 0.04 rad off zero. If the thumb is mechanically stuck (the instructor says it has been for a while), the motors' encoders do not show it.
- **Finger speed:** the real fingers reach a 0.4 rad close in ~1–1.5 s (empty hand), much slower than the 0.16 s command ramp. With a 0.5 s close hold the lift started while the thumb was still closing.
- **The sims never show arm-against-body contact.** In a grid of normal IK solutions, 288 of 792 bring an elbow within 10 cm of the midline (mostly reaches across the body).

## What went into `final-v16-real3` (4ec4952): real2 plus
- **`selfcol.py`:** plans that bring an elbow within 13 cm of the midline beside the torso (pelvis x < 0.10 m) are refused like an IK failure, so the planner takes another grasp, the other arm, a hand-over, or skips the object. `SELFCOL=off` turns it off.
  - It refuses both real collisions and allows the two real poses that worked (`tests/test_selfcol.py`).
  - On the IK grid it refuses ~5 % of same-side reaches and ~65 % of cross-body ones.
- **`motion.close_hold_s` 1.2 s** (was 0.5): the fingers settle before the lift.
- **`ARM_ERR` right 3 cm** (was 3.5): the purple's extra 2 cm was the body push, not aim; the yellow pick needed 2.5–3.5 cm.

## What went into `final-v16-real2` (780e1e5; image 7998cb78ff06, replay test PASS)
- **`ARM_ERR="left=0,0.02,0;right=0,-0.035,0"`:** the left hand aims 2 cm to the robot's right; the right hand aims 3.5 cm to the robot's left (was 2.5 cm).
- **`V16_BOXES=find`:** the boxes are measured from head depth and the drops follow them (Emīls's `boxes_v16.py`).
  - Earlier checks: 15/15 real drop-3 frames, sim centres within 3 mm.
  - New test (`test_shifted_row_found_or_refused_never_mislabelled`): a row shifted 0–13 cm, with the left box cut off at 5 widths.
  - Result: every box within 1 cm, or "not found" (the `scene.yaml` boxes, as before). Never mislabelled.
- **Thumb closes 1.4 cm further:** `hand.closed` = [0, 0.2, 0.9, −1.0, −0.6, −1.0, −0.6], was [0, −0.1, 1.2, …].
  - The thumb tip passes between index and middle (±2.8 cm), so an empty hand still reaches the command and the grasp check still reads it empty.
  - The squeeze on a 4.5 cm block goes from ~0.7 cm to ~2.1 cm.
- **Sim check (e-085, e-086):** gate PASS, 0 clips, 11/12 (Aalto look; the same settings without the thumb and box finder: 12/12; the miss was a cube knocked across the table during another pick, not a failed grasp) and 13/14 (venue look). The box finder measured the boxes in all 6 episodes (within 0.3 cm of `scene.yaml`).
