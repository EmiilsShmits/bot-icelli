# Camera-from-the-arms calibrations compared (Sun 15 Nov, ~03:30)

There are three ways in the team to handle "the robot leans and the bins are not where `scene.yaml` says". All three
use the robot's own arms as the reference.

| | **v1.6 `V16_CALIB=lean`** (ours, `policy/decision_oracle/handeye.py`) | **Marcus `selfcal.py`** (his repo 75f39af, ADK agent) | **Samer `policy/lean.py`** (origin/main, off by default) |
|---|---|---|---|
| Camera pose | 6-DOF point-to-plane ICP of head depth onto the arm + hand surface (URDF meshes, FK), 45 starts, best kept | trimmed ICP (Kabsch) from 13 starts, arms with or without hands (better one kept); mount check: ≤ 3 cm, pitch ≤ 15°, pan/roll ≤ 4° | none: assumes `calibration.yaml` is right relative to the arms |
| Frames | one, at the first look of the episode | several still moments, fused with the table/bin fit and priors in a GTSAM factor graph | one |
| What is changed | the planners' IK model moves by one rigid transform base = T_table · inv(T_arm) (tilt, yaw, x, y, z); deadband 4 mm / 0.5° | waist pitch/roll set in the IK model from the table tilt; scene shifted per axis when > 15 mm (yaw not applied) | IK targets mapped into the arm frame when the table fit tilts ≥ 5° |
| Dependencies | Pinocchio, SciPy, `hand_model.npz` (in policy/) | GTSAM + the URDF meshes (not in his image yet) | none |
| In which policy | v1.6 (opt-in) | ADK agent (tools `measure_scene`, `calibrate`) | v1.x and the ADK agent (patch) |

## Real robot, Aalto drop 3 (head depth), 15 still moments of 12 episodes (`cmp_real.py`)

No ground truth. Ours with the 7.5 cm cut (`camera.fit_head_pose` now uses it).

| | ours | Marcus (`camera_from_arms`, one frame each) |
|---|---|---|
| fits accepted | 15/15 (0/15 → 1/15 with the old 1.5 cm cut: objects and bin walls counted as misses) | 14/15 |
| camera vs calibration, median (pitch / pan / roll, offset) | 0.3° / 0.8° / 1.1°, 20 mm | 1.9° / 2.0° / 0.1°, 20 mm |
| spread over frames (std) | pitch 2.0°, offset 13 mm | pitch 2.2°, offset 6 mm |
| table tilt in the arm frame | **14.3°** (rising away from the robot) | **12.7°** |
| the two methods per frame | median 2.8° and 21 mm apart | |

Both say the same about the real setup: the camera sits within ~2° and ~2 cm of `calibration.yaml` relative to the
arms, and the table rises 13–14° away from the robot in the arm frame (the torso leans). Single real frames scatter
by ~2°, about 1.5–2 cm at the objects: **fusing several still moments, as Marcus does, is worth taking over.**

## MuJoCo, ground truth known (`cmp_sim.py`, 12 frames)

| | ours | Marcus (one frame) |
|---|---|---|
| venue-look camera (9° and 2.9 cm off calibration), nominal + shifted bins | 0.11°, 1.1 mm | 3.3°, 26 mm (his 3 cm mount check rules out the true pose) |
| leaning robot (camera 1–3° off) | 0.10–0.14°, ≤ 1.5 mm | 0.12–2.8°, 0.7–17.5 mm |

Reach error with each mapping (`t_lean.py`-style check, same scenes): ours ~1 mm in every mode; Samer's `lean.py`
turned on 26–29 mm with a leaning robot and 85 mm in the venue look (its auto gate switches on at ≥ 5° tilt there),
which matches his own Modal result (7/12 with it, 12/12 without).

## Episodes (MuJoCo, paired, e-078 / e-079)

`V16_CALIB=lean` vs today's fit: nominal 75 % = 75 % (identical), shifted bins 22 % → 58 %, leaning robot 49 % → 56 %,
all randomised 21 % → 49 %.

## Caveats

- MuJoCo hands are exactly the URDF meshes, which suits a fit that uses the hands (ours always does; Marcus's picks).
- Marcus's full pipeline (several frames + GTSAM + priors) was not run here, only its single-frame arm fit.
- None of it has run on the real robot.

Scripts (scratch paths as arguments): `extract_d3.py` (needs PyAV), `cmp_real.py`, `cmp_sim.py`.
