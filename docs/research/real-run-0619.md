# Real robot, Sun 15 Nov 06:19: what the joint log and head camera show

Run `botticelli_20261115_061937` (Aalto's export: container log, `episode_000.npz` at 30 Hz, head-camera video):
Marcus's image `maroberg/robot-sorter:gemini-er-3` (ADK agent on gemini-robotics-er-2-preview), sort_fixed,
interrupted at 105 s. Analysed Sun ~06:50 by Samer + Claude (scripts in the session scratchpad: FK of `arm_q_cmd` vs
`arm_q` with Aalto's `ArmKinematics`, frames from the video around each grasp).

## What happened
| Pick | Arm | Video | Joint log |
|---|---|---|---|
| blue cube (0.279, −0.077) | right | hand came down about a finger-width to the **robot's right** of the cube, onto its edge; cube stays | all 7 finger joints reached the closed command: empty |
| yellow cylinder (0.316, 0.001) | left | hand just to the **robot's left** of the cylinder; lifts empty; cylinder ends ~3 cm closer to the robot | thumb + index reached the command: empty. Agent said "holding" |
| orange cube (0.259, 0.078) | left | hand over the cube, cube between the finger pads, slips out on the lift, ends ~3 cm closer | thumb + index reached the command: empty. Agent said "holding" |

- **Arm sag (no gravity feed-forward in that image):** at each grasp the measured arm was **11–15 mm lower and
  7–10 mm short** of the commanded pose (FK of `arm_q` vs `arm_q_cmd`, same model).
- **The left hand's `middle_0` joint is stuck** near −0.10…−0.27 rad whatever it is commanded (−0.05 open … −1.0
  closed); every other finger joint of both hands tracks its command within 0.01–0.02 rad. A grasp check over all 7
  joints (ours, Marcus's finger reading) therefore always says "holding" on the left hand: false positives, no retries.
- The pinch is thumb vs **index** (Aalto's `grasp.point_in_palm` sits 15 mm towards the index finger), so the stuck
  middle finger is not part of the grip.
- Marcus's self-calibration measured a small lean that session: upper body +2.9° pitch, table 27 mm lower than
  `scene.yaml`. So the 21° lean of e-083 is not what the robot showed here.

## What went into our image (Sun ~07:10)
- Grasp check on the pinch joints only (thumb_1, thumb_2, index_0, index_1; `GRASP_JOINTS`), threshold 0.03 rad
  (`GRASP_EMPTY_ERR`): empty hands read 0.01–0.02 on the robot, held objects 0.018–0.10 in the sim.
- `ARM_ERR="right=0,-0.025,0"`: the right hand aims 2.5 cm to the robot's left (video here; the real-footage analysis
  of Sat measured −2.9 cm for the right hand).
- `AALTO_CFG_OVERRIDES`: grasp lower on the block (`height_frac` 0.35), hold the closed hand 0.5 s (the real fingers
  take ~0.5 s), release 7 cm inside the box's near wall (was 5 cm).
- Gravity feed-forward is on in our image (if Aalto's runner applies `arm_tau_ff`, the sag above goes away).
