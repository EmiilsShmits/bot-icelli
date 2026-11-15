# eval/analysis/real_depth: our perception on Aalto's first real depth frames (drop 3)

**Purpose:** check on real head depth what was only ever run on sim depth: the head-camera fit, the two arm-based calibration modes, where the real boxes stand, and whether the rung 3 lid holes are in reach. Since Sun ~02:50 also: the box and lid finder (`policy/decision_oracle/boxes_v16.py`) on these frames and on rendered depth of the real lid.
**Owner:** Emīls (with Claude, Sun 15 Nov ~02:30)

## Inputs → Outputs
- **In:** `artifacts/datasets/g1_junction_drop_3/` (drop 3, `data/DATASETS.md` ds-003), Aalto's calibration and `scene.yaml`, `policy/decision_oracle/camera.py` + `handeye.py` as they are in the working tree.
- **In, for the lid:** Aalto's `lid_shape_holes_200mm.stl`, in the repo as `sim/task3/lid_shape_holes_200mm.stl`.
- **Out:** printed tables; frames in `artifacts/real_frames/drop3/` (git-ignored).

## How to run (repo root)
```bash
# 1. first frame of each episode (needs pandas, pyarrow, av, opencv-python: not in .venv, use any scratch env)
python eval/analysis/real_depth/extract.py artifacts/datasets/g1_junction_drop_3 artifacts/real_frames/drop3
# 2. bin-wall fit, V16_CALIB=hands and V16_CALIB=lean on all 15 frames (.venv)
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/calib_modes.py artifacts/real_frames/drop3
# 2b. the lean fallback over 15 episodes in one process (.venv)
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lean_fallback.py artifacts/real_frames/drop3
# 3. top-down height map of the real table, 5 cm grid (scratch env or .venv)
python eval/analysis/real_depth/table_map.py artifacts/real_frames/drop3 artifacts/real_frames/drop3 3 7 13
# 4. rung 3: which lid holes a held object reaches when the boxes stand d cm closer (.venv, Aalto's IK)
PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python eval/analysis/real_depth/lid_reach.py artifacts/urdf/g1_body29_hand14.urdf
# 5. the same for the real lid on the middle box, sim geometry and the leaning real robot (frames where the arm fit works)
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lid_reach_center.py \
    artifacts/urdf/g1_body29_hand14.urdf artifacts/real_frames/drop3 0 13
# 6. the box finder on the real frames, or on saved sim frames (.venv); an output folder adds a top-down picture per frame
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/boxes_frames.py artifacts/real_frames/drop3
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/boxes_frames.py artifacts/monitor/sim_frames - quiet
# 7. the lid finder on rendered depth of the real lid: every turn, lip down and up, boxes as now and 7 cm closer
#    (.venv with mujoco: sim/mujoco/requirements.txt)
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lid_render.py \
    sim/task3/lid_shape_holes_200mm.stl artifacts/real_frames/drop3/depth_ep03_start.npy
# 8. the arm fit's precision and V16_ARM_SHIFT: every 3rd depth frame of each episode (scratch env, 100 MB), then (.venv)
python eval/analysis/real_depth/extract_mid.py artifacts/datasets/g1_junction_drop_3 artifacts/real_frames/drop3
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/arm_shift.py \
    artifacts/real_frames/drop3 artifacts/real_frames/drop3/drop3_mid.npz
# the same checks as unit tests
.venv/bin/python -m unittest policy/tests/test_boxes_v16.py -v
```

## Results (Sun 15 Nov ~02:30, 15 frames = frame 0 of each drop-3 episode)
**Where the real boxes stand** (`table_map.py`; table plane by RANSAC, noise 1.7 mm rms):
- camera 48.4–48.5 cm above the table; the table is tilted 14.3–15.5° against the calibration (drops 1 and 2: 7.9° and 12.2°);
- near wall of the box row 31–32 cm in front of the point straight below the camera (sim: 34.6 cm);
- gaps between the boxes 2–3 cm (`scene.yaml`: 5 cm); walls 7.3 cm at their highest.

**The boxes measured by the box finder** (`boxes_frames.py`, Sun ~02:50; `find_boxes` after the bin-wall camera fit; median and range over the 15 frames):

| | Real (drop 3) | `scene.yaml` |
|---|---|---|
| Found | 15/15 frames | |
| Wall height (top of the near wall) | 7.1 cm (7.0–7.2) | 6 cm |
| Box width | 21.2–21.4 cm (the side boxes' outer walls are out of view: the middle box's width is used for them) | 21 cm |
| Box depth | 20.8 cm (20.6–21.0); the middle box 21.8 | 21 cm |
| Gap left–centre, centre–right | 2.8 cm (1.8–3.0), 2.6 cm (2.2–3.0) | 5 cm, 5 cm |
| Centre to centre | 24.0 and 23.9 cm | 26 cm |
| Near wall from the point below the camera | 32.3 cm (31.6–32.6) | |
| Row direction against the camera fit's frame | +0.2° (−0.1…+0.7) | |

- Against where the bin-wall fit leaves `scene.yaml`'s boxes: left +0.1 cm, **middle +2.1 cm, right +4.2 cm** (towards the robot's left). The fit lines up the left box and the 26 cm spacing puts the other two too far right. Every drop into the middle and right box aims that far off centre today.
- The boxes are taped cardboard. The middle one has flaps folded in on three sides: its opening is about 14 × 16 cm (read off the height map), not 20 × 20. The lid's lip ring is 19.2 cm across, so it cannot sit in that box as it is now. The side boxes have thin walls.
- The far walls' rims are above the top edge of the image; only the lower part of each far wall is seen. After a 7 cm move they come into view.
- **Sim check** (115 saved venue-look frames, boxes where `scene.yaml` says): found on 107; on those, every centre within 3 mm, gaps 4.8 cm (true 5.0), width 21.2 (true 21.0). On the other 8 an arm is over the boxes: the finder says "not found" (once with a wrong width, also reported as not found).
- The lid check on all 15 real frames and the sim frames: "no lid" every time (the most covered box: 0.22–0.31 real, up to 0.41 sim; a lid needs 0.5).

**Calibration modes on real depth** (`calib_modes.py`):

| Mode | Works on | Numbers |
|---|---|---|
| Bin-wall fit (default, v1.2–v1.6) | 15/15 | shift −9.2…−9.4 cm with a search of ±10 cm; wall score 0.37–0.46 (needs 0.35); camera ends 3.5–4.1 cm from the calibration (v1.4 and the ADK image accept ≤ 6 cm) |
| `V16_CALIB=hands` | 3/15 | 8 frames: "arm fit too far from the calibration" (6.4–6.9 cm, limit 6); the rest: too few points on the arm model |
| `V16_CALIB=lean` | 2/15 | arm fit 23–28 % of points within 5 mm on the 13 failures (needs ~30 %); where it works: lean 15.1° and 15.6°, base moved 119 and 130 mm (limit 150) |

**v1.7's lean fallback** (`lean_fallback.py`, Sun ~06:30; `--v16` runs it without the fallback; same frames, through `CameraPerception` as the policy runs it, 15 episodes in one process):
- The base lifts a grasp 35 cm in front of the pelvis by 3.7–7.5 cm (14 frames 3.7–6.0, ep14 7.5) and one 45 cm out by 5.9–9.1 cm. Without it the hand aims that far below where it should.
- With the limits of 07f533c (35 cm / 35°) all 15 arm fits are used as they are, v1.6 and v1.7 alike. With the old 15 cm / 20° limits ep14 (20.9°, 148 mm) was dropped and that episode ran uncorrected.
- An arm fit that fails outright after a good episode (simulated): v1.7 keeps the earlier arm fit with the new table fit (lift 4.8 cm); v1.6 goes to `lean.py`'s mapping. In the first episode of a process both do.

**How precise the arm fit is, and the per-arm correction** (`arm_shift.py`, Sun ~07:05; `V16_ARM_SHIFT`, `policy/decision_oracle/README.md`):
- **Unconfirmed (Sun ~08:20):** the same hand-against-model measurement reads 0.9–2.2 cm in Isaac where the true error is 0 (`docs/research/hover-check-preliminary.md`). The real-frame numbers below point the same way as the `ARM_ERR` values found on the robot, but they have not been checked against anything else.
- The camera is bolted to the head, so the fitted camera-to-arms pose should be the same in all 15 episodes. Over the 15 episodes it varies by 0.4–0.7 cm (one standard deviation per axis, at the work area). 13 episodes are within 0.9 cm of the mean at the centre of the work area; ep01 and ep14 are 1.3 and 2.2 cm off (up to 4 cm at its corners). The fitted rotation ranges over 0.5–6.9°.
- The fit follows the left arm: the left hand ends within 0.4 cm of its model in every episode, the right hand up to 3.6 cm from it (median 1.1 cm), mostly towards the robot's right. Fitting each arm alone does not work: the right arm alone fails or turns the camera 7–17°.
- Later in the episodes, on frames where an arm is still and reaching 29 cm or more forward (measured joint angles, so the controller is not part of this): left hand 0.3 cm from its model (90 frames, 4 episodes); right hand 1.2 cm (107 frames), per episode 1.1, 3.2, 0.9, 1.1, 0.7, 0.9, 1.4 cm. With the shift measured at frame 0 taken off: 1.0, 1.2, 0.5, 0.6, 0.6, 0.7, 0.3 cm. A fixed right-arm offset taken from the other episodes barely helps (1.8 → 1.6 cm, in a first pass with a slightly different choice of points): the error changes from episode to episode.
- Measuring the hand again 0.2–0.5 s later in nearly the same place gives the same shift to 0.1 cm (90 % under 0.3). Repeatable is not the same as right: see the first bullet.
- Teleop's own tracking in these episodes (commanded minus measured joints, as hand position): median 0.4 cm. How well our gravity feed-forward holds the arm on the robot is not known.
- 73 of the 107 right-hand frames are from ep00. The arms start from teleop's pose, not the policy's home pose.

**If the boxes are glued ~7 cm closer to the robot** (Aalto, told to the team Sun ~02:00; assumed: along the table, from the drop-3 layout):
- the bin-wall fit's shift goes from −9.3 cm to about −2.3 cm: inside the search range;
- the camera then ends ~9.8 cm from the calibration: **v1.4 and the ADK image would reject the fit** (limit 6 cm, `camera_move_ok`);
- the near wall comes to ~25 cm in front of the camera's foot point, where the far objects of drop 3 lie now (5–25 cm).

**Rung 3, the lid in Aalto's sim** (`lid_reach.py`: `scene.yaml`, lid on the LEFT box, upright robot, left arm, top-down): a held object reaches the triangle hole once the boxes are ≥ 3 cm closer, the circle hole at ≥ 7 cm, the square hole at 10 cm (one finger direction) to 12 cm. At 7 cm: triangle and circle yes, square no.

**Rung 3, the real lid** (`lid_shape_holes_200mm.stl`, given to the team Sun ~02:10; Aalto: it goes on the MIDDLE box):
- plate 200 × 200 × 4 mm with an 8 mm lip (ring 185.6–191.6 mm);
- holes, centres in mm from the lid centre: square 60 × 60 (rounded corners) at (−48, −35), circle ⌀ 60 at (+48, −35), triangle at (0, +39.3) with one tip towards +y, inscribed radius 21.6 (object: 15), rounded tips 33 from its centre (object: 27.5–30);
- so a 45 mm cube or cylinder has 7.5 mm of room per side, a triangle about 3–6 mm; a centred cube may be turned ±25°, a centred triangle about ±20° (computed from the outlines, not tried);
- not the lid of Aalto's sim (210 mm, holes +10 mm, other positions, on the left box);
- how it is turned on the box is not known.

Reach with that lid on the middle box (`lid_reach_center.py`; L / R = which arm holds an object over the hole, all four turns of the lid):

| Boxes closer by | Sim geometry (upright) | Real geometry (drop-3 frames 0 and 13, torso leaning 15°) |
|---|---|---|
| 0 cm | only the holes on the near half | only the holes on the near half |
| 3–5 cm | the far holes with one arm, or not at all | the far holes mostly not |
| 7 cm | **all three holes, every turn, both arms** | **all three holes, every turn, at least one arm** |

**The lid finder on rendered depth** (`lid_render.py`, Sun ~02:50; no real frame with the lid exists). The scene: the camera pose and the boxes of real frame 3, rebuilt in MuJoCo with thin walls; the lid's STL laid on a box 0–4 mm off centre and up to 6° turned; depth with 1.7 mm noise (as on the real table), 70 % of the pixels at depth edges and 5 % of all pixels dropped:

| Lid on | Boxes | Poses (4 turns × lip down / up × turns of 0, +6, −4°) | Found in the right pose | Hole centres off by |
|---|---|---|---|---|
| middle box | as in drop 3 | 24 | 24 | ≤ 2.4 mm |
| middle box | 7 cm closer | 24 | 24 | ≤ 1.7 mm |
| left box | 7 cm closer | 8 | 8 | ≤ 2.4 mm |
| right box (half out of view) | 7 cm closer | 8 | 3; 4 times "no lid", once "square and round hole not told apart" | ≤ 2.3 mm |

- All 64: found in the right pose 59, **reported found in a wrong pose 0**. Hole centre error over the 59: median 1.2 mm, 95 % under 2.0 mm, largest 2.4 mm. Plate height within 0.1 mm.
- Which way the lid is turned is clear (score gap to the next turn 0.20–0.36). Lip down and lip up differ only by which of the two side holes is square: decided by the square hole's four corners (vote 0.42–0.88 of 1; under 0.35 the finder says it cannot tell).
- Room for a 45 mm cube or cylinder in its hole: 7.5 mm per side. A triangle: 3–6 mm.
- `find_lid` takes 0.15 s on a full-resolution frame.

## Gotchas
- `calib_modes.py` and `lid_reach_center.py` need `policy/decision_oracle/handeye.py` and the `V16_CALIB` camera.py (Sun ~03:30: in Emīls's working tree, not yet on GitHub). The box and lid finder and its scripts do not.
- **The head camera's intrinsics are in Aalto's `calibration.yaml`: fx 604.8, fy 604.3, cx 325.0, cy 250.9.** Until Sun ~02:50 `table_map.py` used round D435 numbers (615, 615, 320, 240); with the right ones the camera height reads 2 mm lower (48.4–48.5 cm), nothing else in the results moved. A renderer with other intrinsics than the points are computed with puts everything ~1 cm off: `lid_render.py` sets the calibration to the renderer's camera for that reason.
- The rendered lid is clean geometry plus noise. Real stereo depth can fill small holes with the plate's depth or leave them empty; then the finder reports a plate whose holes do not match, it does not guess. Check on the first real frame with the lid.
- The lid model is "seen from above with the lip down", read from the STL (plate at z 0–4 mm, lip 4–12 mm). If Aalto lays it lip up, the finder reports `lip_up` and the cube and cylinder holes swap sides.
- `state0.npy` assumes the dataset's `observation.state` order is the interface order (14 arm, then left hand 7, right hand 7). The arm fits converge (3 mm rms), which supports it; not checked joint by joint.
- Frame 0 of a teleop episode, not the finals' home pose: the arms are in view in the same way, but not at exactly the same angles.
- `calib_modes.py` sets the wall height to 7 cm; with `scene.yaml`'s 6 cm the wall band is thinner.
- The "7 cm closer" rows are arithmetic on the measured layout, not a measurement. Re-run steps 1–3 on the next drop.
