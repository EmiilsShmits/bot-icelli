# Hover check and per-arm correction: preliminary findings

**Status (Sun 15 Nov ~08:20, Emīls + Claude): experimental, off by default, not in any image, not run on the robot.**
**Do not turn it on.** In Isaac the hover check as built lowers the score (13/14 → 9/14). This note records what was
tried and what it showed, so nobody has to find it again. Nothing here is a team decision.

## Question
Why does the hand still land beside the block on the real robot with `V16_CALIB=lean`, and can the policy check where
its hand is before it goes down?

For what happened in the real runs, read Samer's analyses from Aalto's logs first:
[`real-run-0619.md`](real-run-0619.md), [`real-run-0655.md`](real-run-0655.md). They found per-arm aim errors
(now `ARM_ERR` in the image: left 2 cm, right 3 cm) and elbows hitting the body. That is the measured truth; this note
is about a camera-based check that did not get that far.

## What was built (all behind switches, default off)
| Switch | What it does | Code |
|---|---|---|
| `V16_ARM_SHIFT=on` | After the two-arm camera fit, measures each hand against its own model in the same depth frame and moves that arm's IK targets by the result for the episode | `handeye.HandEye.arm_shifts`, `camera._arm_shift`, `lean.set_fit_err` |
| `V16_HOVER=on` / `log` | Stops over the block, measures the hand against its model in one head-depth frame, moves the rest of the pick by the error (`log` only measures) | `decision_oracle/hover_v16.py` |
| `V16_HOVER_HANG=on` | Also corrects measured-minus-commanded joints (the hanging arm) | same |

Tests: `policy/tests/test_hover.py`, `policy/tests/test_arm_shift.py` (synthetic clouds only).

## Findings
### 1. Real frames (Aalto's drop 3, 15 episodes): the two arms do not agree with one camera pose
- The two-arm fit follows the left arm. The right hand reads 0.7–3.2 cm off its model when it reaches out, different
  per episode; the left 0.3 cm (`eval/analysis/real_depth/README.md`).
- **Caveat:** those numbers come from the same hand-against-model measurement that reads wrong values in Isaac
  (finding 3). They agree in direction with the `ARM_ERR` values found on the robot, but they are not confirmed.

### 2. MuJoCo (Mac, 3 seeds × 3 objects): works, but MuJoCo is the easy case
- Unchanged sim with the check on: 9/9, nothing moved.
- Right hand sent 3 cm aside on purpose (`ARM_ERR="right=0,0.03,0"`): 6/9 without the check, 9/9 with it. 0 clipped steps.
- In MuJoCo the arm reaches its command exactly and the measurement read 0.1–0.2 cm every time. Isaac differs on both.

### 3. Isaac on Verda (venue look, sort_fixed, seeds 1000–1002, 14 objects, rules parser, `LEAN_MAP=off`)
Runs were stopped after 3 of 5 seeds. One run per setting, no repeats: differences of 1–2 objects are noise.

| Setting | Sorted | Empty grasps | Hover picks moved |
|---|---|---|---|
| Control (v1.6 as is) | **13/14** | 2 | – |
| `V16_HOVER=on` | 9/14 | 4 | 6 of 15 (true error: 0) |
| `V16_HOVER=on` + `V16_ARM_SHIFT=on` | 7/14 | 5 | 6 of 18 |
| `V16_HOVER=on` + `V16_HOVER_HANG=on` | 4/9 (2 seeds) | 11 | 19 of 19 |
| Right hand sent 3 cm aside, check off | 9/14 | 15 | – |
| Right hand sent 3 cm aside, `V16_HOVER=on` | 9/14 | 6 | 10 of 20 |

Gate: every finished episode passed, 0 clipped steps. Command rates are not comparable (the control ran alone on its
machine at 92–96 Hz; every other run shared a machine with a second sim, 67–78 Hz with or without the check).

Why it is worse there:
- **The measurement is not reliable at the hover pose.** In Isaac the true error is 0, yet 6 of 15 measurements read
  0.9–2.2 cm and moved the pick by that much. On two dumped frames, with a known shift applied, about half the results were more
  than 1 cm from the truth. A wide search start (7 cm) reads 3–5 cm where the truth is 0; a 4 cm start reads
  0.8–0.9 cm. Assigning depth points to the nearest link of the whole arm did not fix it. **Cause not found.**
- **Corrected paths get much longer.** Offline scan of picks moved by 1–3 cm: usually +2 to +10 s, worst +36 s.
  In Isaac one episode stood still for ~80 s after a corrected pick and ran out of time. Likely the same thing; not confirmed.
- **The hanging arm must not be corrected in Isaac.** At the hover pose the arm sits a steady 2–3 cm from its command
  (1–3 cm low; the same after 0.2 s and after 2 s, so it is sag, not lag). Aalto's grasps are tuned with it: correcting
  it lifts the grasp and the hand comes up empty (4/9). That term is now off by default. On the real robot with gravity
  feed-forward the arm is 1–3 mm from its command (`real-run-0655.md`), so the term would do little there.
- **No gain on the injected error** (9/14 with and without), unlike MuJoCo.

### 4. Cost
- ~0.7 s hold per pick. MuJoCo on the Mac: `policy_hz_rt` 76.8 → 56.9 Hz.

## What this means
- `ARM_ERR` per arm, set from robot logs, is the correction that has evidence behind it. Keep using that.
- The idea (look at the hand before going down) is not disproved, but this version is not usable. Before anyone
  turns it on it needs: a measurement that reads 0 in Isaac at hover poses, a cap on how much longer a corrected
  pick may take, and a paired Isaac run that does not lose to the control.

## Reproduce
- MuJoCo: `sim/mujoco/serve.py` + `sim/mujoco/run.py` with the env switches above.
- Isaac on a Verda sim machine: copy `policy/` and `training/instruction_parser/{rule_parser,spec,prompts}.py` to
  `~/hover/`, then `bash eval/hover_lane.sh TAG PORT a|b SEED TRIALS [ENV=VAL ...]` (header of the script).
- `V16_HOVER_DUMP=<dir>` saves the depth frame and joints of every hover look for offline checks.
