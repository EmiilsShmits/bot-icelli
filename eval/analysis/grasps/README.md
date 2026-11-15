# Grasp attempts: what fails (Sun 15 Nov, Emīls + Claude)

## Purpose
One row per executed grasp, taken from v1.6 decision logs: which shapes, arms, grasps and finger angles hold.

## Owner
Emīls

## Inputs → Outputs
- **Inputs:** decision logs (`decisions_v1.*.jsonl`) and `result.json` under `artifacts/eval/`.
- **Outputs:**
  - `attempts.jsonl`: MuJoCo stress runs, with the true shape and the outcome;
  - printed tables.

## How to run
```bash
python3 eval/analysis/grasps/attempts.py artifacts/eval/mujoco/lean-v16-a:none artifacts/eval/mujoco/calib-v16-a:none,camera:bins
python3 eval/analysis/grasps/breakdown.py      # held rate by shape, grasp kind, arm, distance, try
python3 eval/analysis/grasps/tri_angle.py      # standing triangles by arm x finger angle, Isaac logs
python3 eval/analysis/grasps/tri_angle.py --mj # the same for MuJoCo logs
python3 eval/analysis/grasps/paired_tri.py artifacts/eval/mujoco/tri-v16-b   # V16_TRI off vs mid, paired
python3 eval/analysis/grasps/isaac_tri.py artifacts/eval/isaac/tri16          # the same in Isaac (tri_sweep.py)
```

## Findings
**What fails is standing triangles. Cubes and cylinders are fine.**

Held per attempt, MuJoCo, nominal-accuracy v1.6 episodes (680 attempts):

| Shape | Held per attempt | Notes |
|---|---|---|
| Cube | 93 % | |
| Cylinder | 83 % | 72 % at pelvis x ≥ 0.28 |
| Standing triangle | 17 % | 2.2 tries per object |
| Knocked-over block | 17 % | |

In Isaac (the grader's sim), standing triangles hold 37/111 (33 %), in every v1.6 Isaac log we have. Samer's Isaac grip sweep (`docs/research/grip-sweep.md`) got 10–25 % with every setting it tried; the misses were "closed on nothing".

What the earlier fixes covered:
- lying prisms: the ridge grasp, e-049, 48/53;
- triangles near the body: push, e-051;
- the face grasp before the claw.

None of these changes how a *standing* triangle is pinched.

### 1. In MuJoCo the right finger angle depends on the hand (FACT, MuJoCo only)
A triangle has no parallel faces, so the pinch angle matters. Aalto's oracle uses one angle for both hands: fingers at 105° from the apex (`TRI_PHI_DEG`). Our extra angles are 75° and 90°. The Dex3 hands are mirror images, though. Measured as finger direction vs the nearest apex (mod 120°), standing triangles held:

| Angle vs apex | Left hand | Right hand |
|---|---|---|
| 40–50° (the mirror of 75°) | 0/3 | **10/10** |
| 70–80° | **30/30** | 0/16 |
| 90–100° | 0/36 | 0/29 |
| 100–110° (Aalto's 105°) | 0/99 | 11/50 |

In MuJoCo the working angle is 75° for the left hand and its mirror (−75° ≡ 45°) for the right. The angle we use first (105°) almost never holds there.

### 2. MuJoCo is not a good judge of triangle grips (FACT)
Aalto's 105° on the left hand:
- MuJoCo: 16/304 (5 %);
- Isaac: 20/47 (43 %).

75° on the left hand:
- MuJoCo: 70/111;
- Isaac: 3/10.

The contact models differ. Don't tune triangle grasps in MuJoCo, and don't read MuJoCo triangle misses as policy failures. Cubes and cylinders agree between the two sims.

### 4. Why standing prisms slip: the thumb never reaches them (FACT, MuJoCo bench)
Bench: `sim/mujoco/tri_bench.py`, raw results in `artifacts/mujoco/tri_bench/`.
- One standing prism per case, about 1 s each, no rendering.
- Aalto's planner with a forced arm and finger angle, played open-loop.
- Records which hand links touch the prism, how it moves during the close, and whether it lifts.

Renders: `triangle_close.png` (hand open at grasp height | closed | after the lift).

- **Aalto's oracle puts the object centre almost at the fingertips.** It sets `grasp.point_in_palm` x = 0.099 m; the closed fingertips are at 0.101 and the thumb tip at 0.065. The midpoint, the classical planner's `auto`, would be about 0.083.
- **The closed hand doesn't pinch.** With the planned closed hand on an unmoved prism:
  - the index finger overlaps it by 14–17 mm;
  - the thumb stops 11 mm short;
  - the middle finger stops 13 mm short (by design: the 15 mm sideways shift pinches thumb against one finger).
- **So the grasp relies on the index finger pushing the object 11 mm along the table into the thumb.** A cube slides back flat on its face and gets caught. A standing prism is pushed on a slanted face or a corner, so it turns and slides sideways. The thumb then closes on nothing, which matches "closed on nothing" in Samer's Isaac sweep.
- **Mirrored hands, exactly:** the right hand at 45° has the same finger gaps as the left at 75°. The pinch is thumb against the *index* finger, so which side of the hand the prism's corner sits on depends on the hand.

Held per planned pick, both arms, angles 0–105° (left-hand terms; right mirrored):

| Bench | Aalto x 0.099 | x 0.091 | **x 0.087** | **x 0.083** | x 0.079 |
|---|---|---|---|---|---|
| Exact pose, 2 spots, 6 yaws | 14/102 | 35/106 | – | **51/98** | – |
| 4 mm / 4° perception noise, 4 spots from 0.19 to 0.31 m, 5 yaws | 27/162 (17 %) | – | 66/162 (41 %) | **76/161 (47 %)** | 74/159 (47 %) |

- With noise, Aalto's point gives 17 %, the same as the stress runs: the bench reproduces the field failure.
- At x 0.083 with noise, by angle (left-hand terms):

  | Angle | Held | Rate |
  |---|---|---|
  | 30° | 16/21 | 76 % |
  | 90° | 14/21 | 67 % |
  | 15° | 11/18 | 61 % |
  | 75° | 13/23 | 57 % |
  | 105° (Aalto's) | 3/21 | 14 % |
  | 45° | 4/16 | 25 % |
  | 60° (fingers flat on a face) | 4/18 | 22 % |

### 5. What to build (OPINION, Claude)
- **For standing triangles only:**
  - grasp point x 0.083 instead of 0.099, swapping `kin.offset[side]` around the plan the way `_plan_face` swaps `kin.hint`;
  - finger angles tried in the order 30°, 90°, 15°, 75° from the apex for the left hand, mirrored (120° − angle) for the right.

  Cubes and cylinders keep Aalto's point: they hold 93 % and 83 % with it.
- **Expected gain (MuJoCo):** about 17 % → 60–75 % held per attempt on standing triangles.
- **Before it goes in the image, check it in Isaac:**
  - Isaac's contact model gave Aalto's 105° far more holds than MuJoCo (43 % vs 5 % on the left hand).
  - The geometry (thumb 11 mm short) is the same in every simulator and on the real hand, since it comes from the URDF; how far a pushed prism slides before the thumb catches it is what the physics changes.
  - Put it behind a v1.6 flag, default off, until an Isaac run agrees.

### 6. Built and measured in MuJoCo (FACT): `V16_TRI=mid`, off by default
`policy/decision_oracle/tri_v16.py`. Paired MuJoCo run e-080: the same 72 seeds with the flag off and on, nominal scene, both tasks.

| | off | mid |
|---|---|---|
| Triangle grasps held per attempt | 42/153 (27 %) | **65/114 (57 %)** |
| Triangles sorted | 60/87 | **68/87** |
| All objects sorted | 259/312 (83 %) | **273/312 (88 %)** |
| Gate | PASS, 0 clips | PASS, 0 clips |

- Per pair: mid better 18, worse 9, same 45 (sign test p = 0.12).
- Rerun the table: `python3 eval/analysis/grasps/paired_tri.py artifacts/eval/mujoco/tri-v16-b`.

### 7. Isaac agrees (FACT): e-081
`policy/decision_oracle/tri_sweep.py` on Modal, Aalto's Isaac sim, venue look.
- One standing triangle per episode, full v1.6 policy (camera, planner, chooser, retries; rule-based instruction, no API calls).
- 24 cases: 4 columns × 3 rows over the object area, 2 turns each, both arms, the same cases with the flag off and on.

| | off | mid |
|---|---|---|
| Triangles sorted | 12/24 | **21/24** |
| Grasps held per attempt | 12/47 (26 %) | **21/34 (62 %)** |
| Left hand, held | 4/23 | **10/12** |
| Right hand, held | 8/24 | **11/22** |
| Tries per case | 2.0 | 1.4 |

- Per case: mid better 9, worse 0, same 15 (sign test p = 0.004).
- Two of the 3 misses with the flag on (cases 22–23, pelvis 0.31 m, +0.15 m) were never seen by the camera, with the flag off too: a perception gap at the far-left-front corner, not a grasp result.
- So the gain is not a MuJoCo artefact.
- By angle, with the flag on:
  - left hand: 30° held 6/6, 15° 2/2, 90° 2/4;
  - right hand: 90° (the mirror of the left's 30°) 6/13, 30° 3/6, 105° 2/2.

  The right hand still needs ~2 tries per triangle. Its angle order is a mirror of the left's MuJoCo order, not measured in Isaac: worth a per-angle check for the right hand.

### 8. Full episodes in Isaac (FACT): e-082
v1.6 with `V16_TRI=off` vs `mid`, the same 12 episodes each (sort_fixed + sort_language, seeds 1000–1005), venue look.

| | off | mid |
|---|---|---|
| Objects sorted | 36/49 (73 %) | **43/49 (88 %)** |
| Triangles sorted | 3/10 | 5/10 |
| Triangle grasps held | 4/16 | 6/17 |
| Gate | PASS, 0 clips, 30 Hz | PASS, 0 clips, 30 Hz |

- Per episode: mid better 5, worse 1, same 6.
- Cubes and cylinders also did better with mid, though their grasps are the same: part of the 36 → 43 is run-to-run noise.
- These layouts have few triangles (10 in 12 episodes), so this run mainly shows the fix is safe in full episodes; e-081 measures the grasp.

### 3b. Earlier idea (superseded by 4–5)
- **Mirror the triangle angle for the right hand in Isaac.** Try 105 / 75 for the left hand and −105 / −75 for the right, one standing prism per case, about 20 grasps per arm and angle (Marcus's grasp bench, as in the grip sweep).
  - The Isaac logs have too few right-hand triangle grasps at mirrored angles to say: 40–50° 0/5, 10–20° 3/9.
  - If mirroring helps, the change is one sign in `motions.face_options` for `side == "right"`.
- **Knocked-over blocks (17 %)** come from failed triangle picks, so they go down if triangles hold.
- **Far cylinders** (x ≥ 0.28 m, 72 %): next in line, not looked at yet.

## Status
- **Now:** `V16_TRI=mid` built (off by default), measured in MuJoCo (§6) and Isaac (§7): both agree.
- **Next:** team decision on turning it on in the v1.6 image (full episodes pass the gate with it on, e-082); the right hand's angle order.
- **Blockers:** none.

## Gotchas
- `attempts.py` matches a detection to the true object by its first seen position (< 5 cm). A block knocked over after a miss shows up as "tipped".
- `tri_angle.py` trusts the policy's shape label, and uses the yaw from the last look before each grasp.
