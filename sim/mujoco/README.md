# sim/mujoco: the venue table in MuJoCo, with the measured geometry

## Purpose
A second simulator, independent of Aalto's Isaac sim, for testing our policy server end to end on a laptop. You can
watch it live.
- **Robot:** Unitree's official G1 + Dex3 model (MJCF from `unitreerobotics/xr_teleoperate` at the commit our URDF uses).
- **Scene:** the table, bins and camera as measured at the venue (Sat 14 Nov), Aalto's objects, and our venue-look
  colours.
- **Loop:** our policy server runs unchanged over the WebSocket on port 8000. The episode loop, safety filter, gate and
  scorer are Aalto's (`run_episode`, `SafetyFilter`, `gate_ok`, `aalto_task.layout.evaluate`).

## Owner
Emīls (+ Claude).

## Inputs → Outputs
- **Inputs:**
  - `venue_measured.yaml`: every number, tagged measured / aalto / venue / guess;
  - `artifacts/mujoco/g1/`, fetched by `get_assets.sh`;
  - a policy server on `ws://localhost:8000`.
- **Outputs:** `artifacts/eval/mujoco/<tag>/`. The `eval.json` is in Aalto's format, so this works:
  `V15_RUNS=artifacts/eval/mujoco python3 policy/decision_oracle/modal_runs/summarize.py <tag>`. Next to it: the
  episode logs, one mp4 per episode (head camera | third-person view, 10 fps) and the policy's decision log.
- **Generated:** `artifacts/mujoco/scene_measured.yaml`, which is Aalto's `scene.yaml` plus the measured bins and the
  venue layout region. The scorer uses it, and so does the policy when `--scene` is given.

## How to run (from the repo root, macOS or Linux)
```bash
bash policy/get_urdf.sh && bash sim/mujoco/get_assets.sh        # G1 URDF (policy IK) + G1/Dex3 MJCF + meshes (~30 MB)
.venv/bin/pip install -r sim/mujoco/requirements.txt
PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python -m unittest sim/mujoco/tests/test_mujoco_scene.py -v
```
Watch one episode live, with two terminals:
```bash
# 1: the policy (v1.6 reads GEMINI_API_KEY; without it v1.6 = v1.5 perception + rule parser)
set -a; . ./.env; set +a
PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python sim/mujoco/serve.py -- --policy v1.6 --port 8000
# 2: the sim, with MuJoCo's window (macOS needs mjpython for the window)
PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/mjpython sim/mujoco/run.py --viewer --seed 1000 --trials 1
```
Batches, one policy server per configuration: `bash sim/mujoco/batch.sh` (edit `RUNS` at the top).

**On Modal, with a live feed** (one L4 container per configuration, all in parallel; this Mac is too slow for
batches):
```bash
.venv/bin/modal run --detach sim/mujoco/modal_mujoco.py                     # default batch, prints one live link per run
.venv/bin/modal run --detach sim/mujoco/modal_mujoco.py --runs "v16-x v1.6 sort_fixed 1000 2 aalto"
.venv/bin/python sim/mujoco/modal_mujoco.py links                           # the live links again
.venv/bin/modal volume get aalto-sim-out mujoco/<tag> artifacts/eval/mujoco/  # results
```
- **Live link:** an MJPEG page (head camera | third-person view, ~10 fps) with the status and the score of each
  finished episode. It is a Modal tunnel: anyone with the link can watch until the run ends.
- **Gemini key:** v1.6 reads `GEMINI_API_KEY` from `.env` on this computer, passed as a Modal secret and never
  stored.
- **GPUs:** on Sun 15 Nov ~00:30, Modal took 5–18 min to start each L4 container, so 25 at once was not realistic.

**Stress test on Verda (what we used):** random variants of the scene (`dr.py`: colours, lights, camera pose,
table distance, bins, friction, mass, lying prisms), random layouts, both tasks.
- **Where:** `/root/mj/` on two RTX PRO 6000 machines (sim-5, sim-6), with a venv holding `requirements.txt` plus the
  policy requirements, and `MUJOCO_GL=egl`.
- **Load:** 24 `stress_worker.py` processes per machine share one queue, with one atomic claim per episode. The sim
  clock sleeps most of the time, so 24 episodes load a 30-core machine only lightly.
```bash
# on each machine (MACHINE = 0 or 1), from /root/mj with .env holding GEMINI_API_KEY:
.venv/bin/python sim/mujoco/stress_worker.py --run stress-v16-a --n 200 --worker W --machine MACHINE --machines 2
# on the laptop: results and report
rsync -a root@<ip>:/root/mj/artifacts/eval/mujoco/stress-v16-a/ artifacts/eval/mujoco/stress-v16-a-<host>/
python3 sim/mujoco/stress_report.py stress-v16-a
```
- **Live grid:** forward the workers' live ports (`ssh -L 18180:localhost:8180 …`; the worker W serves on 8180+W),
  serve `sim/mujoco/` with `python3 -m http.server 18100` (`live_grid.html` shows the ports 18180, 18181, 18280, 18281), then open
  http://localhost:18100/live_grid.html.

**Standing-triangle grasp bench** (`tri_bench.py`): one standing prism per case, Aalto's planner with a forced arm and
finger angle, played open-loop without rendering (about 1 s per pick on the M1). Findings in
`eval/analysis/grasps/README.md` §4.
```bash
PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python sim/mujoco/tri_bench.py --point 0.083,-0.084,0.015 \
  --noise-mm 4 --noise-deg 4 --out artifacts/mujoco/tri_bench/n083.json
```

**Shape putting with the real lid** (`insert_demo.py`, rung 3): Aalto's `lid_shape_holes_200mm.stl` lying lip down on the
middle box, the boxes 7 cm closer and 2.7 cm apart; one block per case, seen by the head camera only (v1.6 camera
fit with `--calib hands` by default, object detection, `boxes_v16.py` for the lid's holes), picked by Aalto's oracle
planner, carried over its hole while the wrist turns it to the hole's angle, lowered to 1.2 cm above the plate and let
go. Played open-loop (no policy server), checked against Aalto's safety filter (0 clips). Results and one video per
case in `artifacts/eval/mujoco/<tag>/`.
```bash
PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python sim/mujoco/insert_demo.py --video --tag insert-demo \
  --spots 0.20:0.12,0.22:-0.12,0.18:0.05 --yaws 10,-30,40
```

Useful options:
- `run.py`:
  - `--task sort_language`;
  - `--colors sim|real_camera`: Aalto's saturated colours, or the colours as the real head camera recorded them
    (orange washed towards peach);
  - `--video`.
- `serve.py --scene artifacts/mujoco/scene_measured.yaml`: the policy assumes the measured bins. Without it, it
  assumes Aalto's `scene.yaml`, as the submission image does.
- `python sim/mujoco/backend.py --snapshot artifacts/mujoco/snap --seed 1000`: one head frame and one overview PNG.

## What it models
- **Robot:**
  - pelvis fixed at 0.79 m; legs and waist locked;
  - 28 arm and hand joints under PD position control, Unitree's controller gains: arm kp 80 / kd 3, wrist 40 / 1.5,
    Dex3 1.5 / 0.2;
  - gravity compensation on the arms;
  - the hands collide with the world but not with the robot (the safety filter keeps the arms apart).
- **Head camera:**
  - pose from Aalto's `calibration.yaml` (URDF `d435_link`), turned like the venue look (9° down, 1° roll, 2.5 cm
    left), with the lens 48 cm above the table (measured);
  - 640×480, fy 604.3;
  - depth in mm (table plane within 2 mm in the test);
  - the robot's head shell is hidden from it.
- **Scene:**
  - table near edge 10 cm in front of the pelvis (guess: "the robot leans against the table");
  - bins: near edge 30 cm from the table edge (measured), 21 cm (Aalto), 5 cm apart and 7 cm tall (measured).
    That puts them at Aalto's published 40 cm from the torso.
  - objects: 4.5 cm, 0.05 kg, friction 1.2, as in Aalto's Isaac scene.
- **Leaning robot** (`dr.py` mode `lean`, `robot.lean_deg` in the config): the whole robot pitches 5–11° about the pelvis towards the table, and the camera sits 1–3° below its calibration. That is what Aalto's real frames say (`docs/CONTEXT.md` 4.1). The other modes keep the venue look's 9° in the camera.
- **Not modelled:** wrist cameras (black; v1.6 does not use them). Randomisation and lying prisms: `dr.py`, `--tip`.

## Status
- **Now (Sun 15 Nov ~02:00):**
  - scene, backend, runner, randomisation (`dr.py`) and tests work (6/6 pass);
  - the head camera now uses Aalto's full intrinsics (principal point 5 / 11 px off centre). **Runs before this fix (e-052, e-053) saw the scene ~1° off from the policy's K, so they are slightly pessimistic.**
  - Verda runs: e-052 randomised 19 %, e-053 paired control (bins shift is what breaks v1.6), e-078 paired `V16_CALIB=bins` vs `hands`, e-079 `bins` vs `lean`, e-080 `V16_TRI=off` vs `mid` (`eval/RESULTS.md`).
  - **Shape putting (`insert_demo.py`, Sun 15 Nov ~03:25): 19/27 blocks through the right hole** (cubes 7/9, cylinders 9/9, prisms 3/9), score 54 of 81, 0 wrong holes. Every block still in the hand when it reached its hole went in (19/19); the 8 failures all slipped out of the hand during the carry (the grasp, not the insertion). Video: `artifacts/eval/mujoco/insert-demo/highlights.mp4`.
    - Perception from the head camera: holes within 1.7 mm, blocks within 1.4 mm, block angles within 0.2°.
    - Two corrections made it work, both measured here (spread ±2 mm, ±1–2°): the block sits 13 mm behind and 15 mm to the thumb side of the planner's grasp point, and it turns in the hand (prisms 12°, cubes 5°, mirrored between hands). Without them cubes went 1/4. Released blocks were within 5.5 mm and 2.8° of their hole.
    - **With the boxes 7 cm closer, v1.6's default camera fit (`V16_CALIB=bins`) puts everything 7.5 cm off** (it lines the boxes up with `scene.yaml`): 0/4, the arm reaches 7.5 cm beside every block. `V16_CALIB=hands` (camera within 0.3 mm) and `V16_CALIB=lean` (frame 7.5 cm off but the IK model moved with it) both give 4/4. This matters for rungs 1–2 as well, not only the lid.
    - Not done: no policy server, no episode loop with several blocks, MuJoCo's Dex3 grip only; the in-hand offsets are MuJoCo's and need checking on the real hand.
- **Next:**
  - analyse the leaning-scene losses in e-079 (`V16_CALIB=lean` 56 % there vs 75 % nominal);
  - measure the real robot-to-table distance.
- **Blockers:** none.

## Gotchas
- **Clock:** `run.py` runs on a sim clock at a real-time factor of 0.4 by default (`--rtf`), the way Aalto's Isaac
  sim runs (0.27–0.45 in our Modal runs). Rates, the time limit and the watchdog count sim seconds, as there.
  - Why: in wall time (`--rtf 0`) this M1 cannot step, render and run the policy at 30 Hz. v1.6 then fell to 17–21 Hz
    and ran out of time with objects left, which measured the laptop, not the policy.
  - Even at 0.6, the policy's ~150 ms per call on this busy Mac (75–120 ms on Modal) makes 2–5-tick holds. At 0.4
    it gets about the time per tick Isaac gave it.
  - The real robot runs at 1.0: there the finals PC has to be fast enough.
- **Layouts:** the same seed gives the same layout as the Isaac venue runs (same rng and venue layout region), so scores
  compare per seed.
- **Live feed:** `run.py --live 8080` serves the feed on a laptop too (open http://localhost:8080/).
- **Viewer:** `--viewer` needs `mjpython` on macOS, and it slows the loop a little.
- **Depth warning:** MuJoCo warns "ARB_clip_control unavailable" on macOS. Depth is still accurate to about 2 mm at
  table range (`test_depth_of_the_table`).
