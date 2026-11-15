# Handoff: Samer's overnight Claude session → the next agent (Sun 15 Nov, ~01:05 Helsinki)

> **Update Sun ~04:45: gravity feed-forward (the likely main cause of the real-robot misses), the best system now.**
> - **Aalto's PR #4** (`arm_tau_ff`, erkka "merged" 04:18; still open on GitHub at 04:35): on the real robot the arm
>   controller holds ~9.6 Nm at most, so an outstretched arm **sinks 15–18 cm**. A policy may now send feed-forward
>   torque per arm joint; the teleop that recorded Aalto's demos sends gravity compensation. None of our images did.
>   **Done (3768226): `policy/gravity_ff.py`**, on by default, wraps Aalto's `policy_server.handle`, so every action of
>   every policy (ours and Marcus's agent, via `runtime.install()`) carries `arm_tau_ff` = gravity torque at each row
>   of `arm_q_target`, clamped to the runner's ±15 / ±2.5 Nm. Tests 7/7 in the image (arm straight out at 0.41 m: 8.5 Nm
>   at the shoulder); Aalto's PR #4 runner + mock against our v1.6 server: all replies accepted, torque recorded on
>   93/93 ticks, 0 clipped steps. Sim scores cannot change (the sim ignores it). **Not in any built image yet.**
> - **Best system now (OPINION, Samer + Claude):** v1.6 from main + gravity feed-forward (on) + Emīls's `V16_TRI=mid`
>   (standing triangles 21/24 vs 12/24 in Isaac, e-081; still off by default) + a camera correction for the leaning
>   robot (`V16_CALIB=lean`, `LEAN_MAP=auto` or Marcus's self-calibration: Samer's decision, open). Task 3 on the real
>   robot needs the lid on the middle box (Emīls's `V16_BOXES=lid` finder, not wired into `insert.py`) or stays off.
> - **Task-3 cylinders in sim:** two failure types remain: a missed grab that knocks the cylinder away or over, and a
>   cylinder jamming on the hole's rim (it hangs tilted or off-centre in the 2-finger pinch; Emīls measured blocks
>   13–15 mm off the grasp point in MuJoCo, the hole allows 7.5 mm). Aalto's episode files log no block poses, so
>   measuring the Isaac offset needs an instrumented run.

> **Update Sun ~03:50: the real-robot video of our pre-submission, the three image gates, task 3 settled.**
> - **Real robot (Aalto's pre-submission video, Samer has the file, recorded ~03:20):** almost certainly
>   `presubmit-adk-1` (between moves the arms go out to the side: Marcus's `_park`, `adk_agents/robot_sorter/tools.py`).
>   The robot hangs from the crane; its head camera is ~50 cm above the desk (Samer). The sim assumes 46.4 cm
>   (`calibration.yaml`: camera 47.4 cm above the pelvis, counter +1 cm). In 46 s it reaches for the purple cube with
>   its right hand twice. Both times the fingers come down on the table about a hand-width beside the cube, on the
>   side towards the robot's right hand, close on nothing, and the arm carries on as if holding it. The cube never moves
>   (frames at 17–18 s and 35–36 s). Samer: every team's run showed an offset. Matches the Saturday finding (§3b,
>   `docs/research/hand-offset-real-data.md`: torso leans 5–10°, right hand y −2.9 cm off the model) and Marcus's
>   drop-3 check (table tilted 12.3°, 6–8 cm further than `scene.yaml`). From this camera angle "beside" can't be split
>   into "to the right" vs "short".
>   **Every image we have aims the arms in the table-fitted camera frame, `final-v16` included: expect the same miss
>   on the real robot unless one of these goes in:** Marcus's self-calibration (75f39af: not in an image, needs gtsam
>   + meshes, never run on a robot), our lean mapping (`LEAN_MAP=auto`, off since 847df56 because it cost 5/12 in our
>   lean sim), or a per-arm correction measured on the robot. Team decision; Samer thinks Marcus has solved it.
> - **Gates on sim B (`AALTO_DR=train`, seeds 1000–1002, all PASS, 0 clips):** `final-v16` 11/12 (e-072),
>   `final-v16g` 10/12 with one wrong bin (e-070), `final-adk` 10/12 with one time-limit episode (e-071).
> - **Task 3 settled (e-073 … e-077):** release height, pinch height and a hold before release make no difference;
>   cubes (0/16) and triangles (1/24) lose points under every setting, so cylinders only stays. New `LID_PICK_TOL`
>   (on, 2 mm): the hand's way down to the block no longer drifts up to 6 mm off the planned grasp point (Aalto's
>   planner accepts 6 mm); +22 vs +13 on 9 seeds, within noise. **Images rebuilt from 2de82ce (~03:40, not pushed):**
>   `final-v16` `6a02fad81f37` (1.46 GB) and `final-v16g` `3308f1b4489e` (6.35 GB): key 53 bytes, replay test PASS
>   (0 errors, startup 0.5 s / 7.4 s). Their sorting code is the e-072 / e-070 code; only `insert.py` changed.
> - **No new pushes** from Emīls (bot-icelli, last 838a407 at 02:41) or Marcus (his repo, last 75f39af at 02:06), as
>   of 03:45.

> **Update Sun ~03:00: teammates' latest work vs `final-v16`, and task 3.**
> - **Emīls** (838a407): latest main in the venue look + real colours 22/27 with push on (e-068); `LEAN_MAP=auto`
>   there 0/27; crowd check on 13/18 vs off 11/18 (e-069). Confirms `final-v16`'s defaults (lean off, crowd on);
>   push on/off is within noise (e-066 push off 24/27). **Tiya** (8a45b81): triangles no longer abort on an "empty"
>   finger reading (already in `final-v16`); her wrist-camera triangle check is only in our copy of Marcus's agent
>   (`modal_pipeline/adk_agents/`), not in `final-adk`. **Marcus**: 1855ff4 (= `final-adk`) scored 19/20 in Aalto's
>   nominal look (his run, seeds 1000–1004; 1000–1002: 11/12 vs v1.6's 9/12 in e-060); his 75f39af self-calibration
>   (camera against the robot's own arms, GTSAM) measured on Aalto's real drop 3: table rises 12.3° away from the
>   robot, bins 6–8 cm further than `scene.yaml`, arm-vs-model error 15 mm → 4 mm. Not in any image (needs gtsam +
>   meshes), ~20 s per episode, no sim gain, not run on the robot.
> - **Task-3 videos** (head camera, Modal runs of `final-v16`'s code): `artifacts/task3_videos/` (git-ignored, on
>   Samer's laptop). `t3-v16-f_*` = cylinders only (`final-v16`'s default), `t3-v16-e_*` = all shapes. More runs:
>   `modal.exe volume get aalto-sim-out <tag> <dir>`, files `runs/eval/*/episode_NNN.mp4`.
> - **Task-3 failure modes** (videos): the cylinder hangs tilted in the 2-finger pinch and jams on the rim; the cube
>   arrives turned ~25° (the square hole allows ~19°); the triangle arrives lying on its side. Tests running:
>   release 12 mm down into the hole (`LID_GAP=-0.012`), with and without a higher pinch (`LID_GRASP_H=0.6`).

> **Update Sun ~02:30: final candidate images are built on `samer-v1-sim` (main 14e39ce), NOT pushed** (pushing
> to the public GHCR package publishes the Gemini key inside; Samer's call, as for `presubmit-adk-1`):
> - `bot-icelli/policy:final-v16` (v1.6 + Emīls's 83d53a7 + smoothing + lean off + task-3 park), `:final-v16g`
>   (+ retrained Gemma 1B), `bot-icelli/adk:final-adk` (Marcus 1855ff4; his 75f39af "self-calibration" is newer and
>   untested by us). Aalto's replay test passes on all three.
> - **Two image bugs found and fixed tonight:** (1) `.dockerignore` lacked `decision_oracle/near_v16.py`,
>   `crowd_v16.py` and `insert.py` (v1.5/v1.6 import insert at every reset: such an image crashes at the first
>   episode); (2) the Gemini key went in as the whole `GEMINI_API_KEY= <key>` line (the .env has a space after `=`),
>   so every Decision 1 call got HTTP 400 and v1.6 silently ran its offline fallback. Now verified from inside the
>   image: one instruction call 0.26 s, right mapping. The A/B images (e-056…e-059) had no key at all.
> - Gate runs on sim B (`AALTO_DR=train`, seeds 1000–1002, `~/dr_lane_b.log`): old final-v16 (= offline fallback),
>   then `final-v16g` + `final-adk` (tmux `gate_next`), then the fixed `final-v16` (tmux `gate_next2`).
> - Push recipe (on the sim machine, logged in to ghcr.io): `docker tag bot-icelli/policy:final-v16
>   ghcr.io/samer-cyber/bot-icelli-policy:final-v16 && docker push ghcr.io/samer-cyber/bot-icelli-policy:final-v16`,
>   then pin the printed `sha256:` digest in Aalto's form (`docs/runbooks/submit.md`).

> **Update Sun ~02:10 (same next session). Results of §0 items 1–4 are in `eval/RESULTS.md` e-056 … e-063 (Emīls took e-050 … e-055 meanwhile):**
> - **Smoothing A/B (e-056 … e-059): keep it on.** Same score with and without (venue 23/27 vs 23/27, randomised
>   19/20 vs 19/20, 0 clips), peak arm acceleration ~13 vs 25–58 rad/s², largest one-tick speed change 0.39 vs
>   0.8–1.7 rad/s; episodes ~16 % longer.
> - **Lean mapping (e-061/e-062): ship it off.** In the lean look (robot pitched 8°, camera +2.4°) `LEAN_MAP=off`
>   sorted 12/12, `auto` 7/12 (same seeds). `policy/lean.py` default is now `off` (tests updated, 5/5 in the image).
> - **Regression (e-060):** v1.6 with the new code, Aalto's nominal look, 9/12; misses are ordinary empty grasps.
> - **Task 3 (e-063) was not a valid test:** the sim starts with both arms near the joint-zero pose and the
>   evaluator's homing lifts them; in the task-3 scene the left hand's zero pose is under the lid plate, so it stayed
>   caught all episode. `modal_pipeline/sim/eval_patches.py` (installed by `modal_sim.py`'s eval command) now
>   resets the scene when the homing fails (probe `t3-probe-b`: 0.40 → 0.01 rad from home). `insert.py` also parks
>   both arms beside the lid between moves (at home the left hand hangs over the triangle hole). Rerun: `t3-v16-e`.
> - Gemma retrain (sim machine, `/root/v16g`): teacher done ~00:05 UTC, then fine-tune + eval (`RETRAIN_DONE` in
>   `/root/v16g/logs/retrain.log`).

> **Update Sun ~01:55 (next session, "Sim venue look and LLM instruction parsing"):** everything below marked
> uncommitted is now committed (75ed976 Modal + lean variant + task-3 lid, 49f78b3 policy, plus a docs commit).
> - The queued Modal runs `t3-v16-a` and `reg-v16-all-nominal` had failed in 6–18 s: Windows-built images lose
>   the executable bit, so `aalto sim` → "Permission denied". Fixed in `modal_sim.py` (chmod at container start),
>   relaunched as `t3-v16-b` and `reg-v16-b`.
> - The side sessions (hand offset, grip sweep, Gemma) had all stopped. The lean look was never built, so I added
>   `scene_variant.py --lean DEG --cam-mount DEG` and started `lean-v16-auto` (LEAN_MAP=auto LEAN_OFFSETS=off) vs
>   `lean-v16-off` (--lean 8 --cam-mount 2.4, --look none, seeds 1000–1002).
> - Grip sweep results: `docs/research/grip-sweep.md` (no setting beats the default).
> - The Gemma retrain runs on the sim machine's GPU (`/root/v16g`, tmux `v16g_train`), not on Modal.

Written by the Claude session that ran the overnight plan (plan file `C:\Users\hadad\.claude\plans\clever-soaring-sky.md`;
full transcript `C:\Users\hadad\.claude\projects\D--Samer-Hackathons-JUNCTION-2026\5ab08843-2b95-4a2a-9a93-be385fced8bf.jsonl`).
**Nothing below is committed yet** unless marked. Read `AGENTS.md` and `docs/CONTEXT.md` first as usual.

## 0. Do these next, in this order
1. **Smoothing A/B** (running on the sim machine, §2): when `tmux ab_c` and `tmux ab_b` finish, compare
   `v1.6-smooth` vs `v1.6-nosmooth` (score, gate, episode time), run `eval/analysis/motion_smoothness.py` on both, add
   RESULTS rows, then commit the W1 files (§3a). Smooth so far: venue 19/23 (seeds 1000–1004), randomised 14/15
   (1000–1003), 0 clipped commands everywhere.
2. **Task 3 sim results** (Modal tag `t3-v16-a`, queued behind the grip sweep's GPUs, §2): fetch, read the outcomes
   (`inserted` / `forced` / `dropped` / `counter`) and the head-camera videos, iterate on `policy/decision_oracle/insert.py`.
3. **Regression run** (Modal tag `reg-v16-all-nominal`): v1.6 with smoothing + lean + insert code on normal sorting,
   nominal scene, seeds 1000–1002. Must score like before (no change expected: lean stays off there).
4. **Lean fix validation**: the hand-offset session was asked to build a "lean" sim look (§2). Run v1.6 in it with
   `LEAN_MAP=auto` vs `LEAN_MAP=off`. This decides whether the final image ships with the arm-frame mapping on.
5. **Commit + push** (coordinate with the other sessions' files, §3), `git pull` on the sim machine, **rebuild the final
   candidates**, gate-check, push to GHCR, anonymous pull test, team picks, Samer submits **before 10:00 Helsinki**
   (our assumption; Aalto's exact time is whatever they posted on Discord).

## 1. Where things stand (context)
- Challenge: Aalto humanoid (G1 + Dex3 sorts blocks; rung 3 = insert shapes through a lid). Final Docker image runs on
  the **real robot** on Sunday. Judges: real-robot success matters most; they prefer AI / fine-tuned methods; "the one
  team that tested on the real robot had huge jerks"; every team built a better sim; **nobody else does task 3** and
  Aalto will put the task-3 lid box wherever we ask.
- Pre-submission (done Sat): `ghcr.io/samer-cyber/bot-icelli-policy:presubmit-adk-1`
  (sha256:d94198bd994e5ef42004cc5d64108922c1b232ab07521edab5c4c98288006cdf, Marcus's ADK agent + our camera fix; it
  **contains the Gemini key** by Samer's decision: cap spending, rotate the key after the finals) and backup
  `presubmit-v15-1` (sha256:be601037877f98b07b779394d8455443bc4eb87d420458874a70dca7dd057222).
- Final candidates: **Marcus's ADK agent** (`policy/adk/build.sh`) or **v1.6 / v1.6g** (`policy/server.py`). Not decided.
- Best sim numbers so far: v1.6 venue look 48/55 (e-044/e-045), v1.5 sides off randomised 33/40, Marcus's agent DR
  18/20, agent + camera fix venue 20/27 and 23/28 (Emīls).

## 2. Running right now and how to check
- **Sim machine** (`samer-v1-sim`, host in `.env` as `VERDA_SIM_HOST`, never print it; `ssh root@<host>`):
  - `tmux ab_c`: sim C (venue look, port 8002), `v1.6-smooth` then `v1.6-nosmooth`, 6 trials, seeds 1000–1005.
  - `tmux ab_b`: sim B (`AALTO_DR=train`, port 8001, `eval/dr_lane_b.sh`), same two images, 5 trials, 1000–1004.
  - Results: `~/runs/eval/*v1.6-*smooth*/` (`python3 ~/summarize.py | grep v1.6-` for the table), logs `~/ab_smooth.log`,
    `~/dr_lane_b.log`. Then `python3 eval/analysis/motion_smoothness.py ~/runs/eval/*v1.6-*smooth*/` (in a policy image
    if numpy is missing: earlier we ran it with `docker run ... bot-icelli/policy:v1.6-smooth python3 ...`).
  - **Sim A** (pid 185881, venue look, started 19:50) is idle: its old `queue` finished (summary tables printed). It eats
    ~13 cores; all 3 sims run at 0.2× real time. Stopping it frees CPU, but **kill it by PID only**
    (`kill -INT 185881`): `aalto.sh stop` may take the other sims down. It was started by another session: ask Samer.
  - `/tmp/t3/` on the machine: copies of insert.py, lean.py and tests used for the offline runs (scratch).
- **Modal** (works now; CLI `D:\Samer\Hackathons\JUNCTION 2026\junction2026\.venv\Scripts\modal.exe`, run from
  `bot-icelli\modal_pipeline`):
  - `t3-v16-a`: call `fc-01M7E435F5SFV58AA6X034J0BT` (app `ap-c7m6F9qHFIS0jxcjWDBCe7`): task 3, v1.6 + insert code,
    `--task Aalto-Insert-G129-Dex3-Joint --eval-task insert_shapes --look none --variant "--task3 request" --trials 2 --seed 1000`.
  - `reg-v16-all-nominal`: call `fc-01M7E4ETVCA9QJKRW7FJZTAM4M`: v1.6 sort_fixed, `--look none`, 3 trials from 1000.
  - **Both were queued with no container at 01:00**: the grip-sweep session holds 9 GPUs (apps `ap-CroG3yqEuKpe48xlsnhe9t`
    with 8 containers, `ap-7AdrunCPKOj6gjdvILK3nM` with 1), apparently the workspace's GPU limit. The Gemma session also
    has `bot-icelli-v16g-retrain` running. Check a call:
    `..\..\junction2026\.venv\Scripts\python.exe -c "import modal; print(modal.FunctionCall.from_id('fc-...').get(timeout=0))"`
    (TimeoutError = still running). Outputs when done: `mkdir sim_out; modal.exe volume get aalto-sim-out t3-v16-a sim_out`
    (eval JSON, `episode_NNN.mp4` videos, `/tmp/policy.log` with `[insert]` lines). `modal.exe container list` shows what holds GPUs.
  - `bot-icelli\modal_pipeline\aaltonomous-humanoid` is a **directory junction** to Marcus's clean LF clone
    (`junction2026\aaltonomous-humanoid`, same commit 36daf5b as our submodule), so Modal builds from Windows work.
    Git-ignored locally via `.git/info/exclude` only.
- **Side sessions** (all share the bot-icelli folder; told "commit nothing, switch no branch"):
  - `local_ff853a84-d10d-419c-8016-ab46f7bf35f5` "Real hand offset from Aalto's real data": delivered
    `docs/research/hand-offset-real-data.md` + `eval/analysis/hand_offset.py` + 2 images. **Follow-up queued (01:00):
    build a "lean" look** (robot upper body pitched ~8° vs the table, camera ~2.4° down on its mount; only
    `sim/venue_look/` and, if simple, `modal_sim.py --look lean`), report a Modal boot whose hand/table geometry matches the
    real footage and a how-to.
  - `local_fdce102c-cf2f-483b-8b25-6b07dd01d654` "Grip sweep for cylinders and prisms on Modal": running (9 GPUs). So far
    `docs/research/grip_sweep_table.py`. Its recommended values go in via `AALTO_CFG_OVERRIDES` (§3a).
  - `local_66babc89-e9fe-466f-a180-432942e5c67f` "Fine-tuned Gemma parser in the v1.6 image": v1.6g (Gemini → Gemma 1B →
    rules), files in §3c, retraining on Modal.

## 3. Uncommitted work in the bot-icelli folder, by owner
### 3a. This session (Claude, overnight plan)
**W1 smooth motion + config overrides** (unit tests 8/8 pass locally: `python -m unittest policy/tests/test_runtime.py policy/tests/test_smooth_motion.py`):
- `policy/smooth_motion.py`: runtime replacement of Aalto's `planner.time_scale` (piecewise-linear joint paths with
  instant direction changes at every waypoint → 15–54 rad/s² spikes: the likely "huge jerks"). PCHIP path through the
  same waypoints, trapezoid speed profile convolved with a box window (jerk limit), accel cap, same vmax. Measured on
  real plans: accel p95 23 → 7.4 rad/s², biggest one-tick Δv 0.96 → 0.26 rad/s, motions ×1.25 longer.
  Env: `SMOOTH_MOTION` (1/0), `SMOOTH_ARM_ACC` (6.0), `SMOOTH_JERK_S` (0.06).
- `policy/cfg_overrides.py`: planner config from env for every stack using Aalto's `load_config` (v1.x, oracle-based
  v1.5/v1.6, Marcus's skills): `AALTO_CFG_OVERRIDES='{"grasp.height_frac": 0.45, ...}'` (dotted keys, win over all
  others), `ARM_XY_OFFSET='left=dx,dy;right=dx,dy'` (→ `grasp.arm_xy_offset`, metres, pelvis frame).
- `policy/runtime.py`: `install()` = cfg_overrides + smooth_motion + lean. Called in `policy/server.py` `main()` before
  the policy is built (server.py is **also edited by the Gemma session**: its `_v16g` entry), and in Marcus's agent via
  `policy/adk/patch_smooth.py` (inserts `import runtime; runtime.install()` after the zmq line of `robot_sorter/serve.py`).
- `policy/adk/build.sh` + `policy/adk/Dockerfile`: copy `smooth_motion.py cfg_overrides.py runtime.py lean.py` to
  `/app`, run `patch_smooth.py` and `patch_lean.py` (also earlier: `ALLOW_NO_KEY`, base `nvidia/cuda:12.8.0-base-ubuntu24.04`).
- `policy/tests/test_smooth_motion.py`, `policy/tests/test_runtime.py`, `eval/analysis/motion_smoothness.py`,
  `eval/ab_smooth.sh` (builds `v1.6-smooth` + derived `v1.6-nosmooth` with `ENV SMOOTH_MOTION=0`), `eval/dr_lane_b.sh`.

**Lean fix = arm-frame mapping** (unit tests 4/4 pass in the policy image, §8):
- Finding (hand-offset session, `docs/research/hand-offset-real-data.md`): on the real robot **the robot leans 5–10°
  forward vs the table; the head camera is within ~2.4° of calibration.yaml**. Every policy we have (v1.4–v1.6 and
  Marcus's agent) fits the camera to the table (8–12° "tilt") and aims the arms in that fitted frame → on the real robot
  the hand would land **6–9 cm short and low**. Fix: keep the fit for perception and clearance checks, map IK targets
  into the arm frame: `p_arm = M p_fit − offset[side]`, `M = T0 @ inv(T_fit)`; per-arm offsets left (+1.5, −0.8, +1.1) cm,
  right (+1.0, −2.9, +1.1) cm.
- `policy/lean.py`: class-level runtime patch of Aalto's `ArmKinematics` (`solve` maps target + palm-down axis + finger
  hint into the arm frame; `grasp_pose` / `hand_points` map back, except inside `solve`). Off until `set_fit()` sees a
  fit tilted ≥ 5°: Aalto's sims fit ~1–2° → **no change in their sims**. Env: `LEAN_MAP` auto|on|off, `LEAN_OFFSETS`
  on|off, `LEAN_MIN_TILT` (5).
- Hooks: `policy/decision_oracle/camera.py` `ensure_pose()` calls `lean.set_fit(cal0._T(CAM), fit.T, fit.tilt_deg)`
  (v1.5/v1.6/v1.6g); `policy/adk/patch_lean.py` inserts the same into Marcus's `robot.fit_head_camera` (tested on his
  latest `1855ff4` robot.py: patches and parses).
- **Caveat:** our current **venue look tilts the camera on its mount ~10°**, so `LEAN_MAP=auto` turns the mapping ON
  there, which is wrong for that sim. Evaluate new images in the venue look with `LEAN_MAP=off` (or use the lean look).
  Not yet run in any full sim. Shipping it on (auto) is a team decision (§6).

**Task 3 (`insert_shapes`)**:
- `policy/decision_oracle/insert.py` (+ hook in `policy/policies/oracle_v15.py::_apply_reset`: `insert.configure()` before
  `pol.reset()`, `insert.after_reset()` after; applies to v1.5, v1.6, v1.6g). On for task `insert_shapes` (Aalto's runner
  sends it with every reset) or an instruction mentioning a hole / lid / inserting.
  - The lid's three holes become the planner's "bins" (`InsertPlanner`, subclass of Aalto's `_OraclePlanner`): face grasp
    for square and triangle, carry above the hole, **wrist turns** so the block lines up (square mod 90°, triangle mod
    120°), lower until the block bottom is `LID_GAP` above the lid, open, lift. Rejects plans with wrist > 8° off or block
    centre > 4 mm off the hole. Lying triangles and stock-claw grasps of square/triangle are skipped (a failed insert = −1).
  - Clearance against the lid box + remaining bins (`_LidAware`), task-3 relay points clear of the lid, relay keeps shape/yaw.
  - Lid pose: requested placement, refined at the first look from head depth (`find_lid`: top plane → centre, turn,
    height); detections on/in the lid box are dropped.
  - Hole layout (pelvis frame, lid as requested, from Aalto's STL): triangle (−0.039, 0) apex towards the robot, square
    (+0.035, −0.048), circle (+0.035, +0.048) from the lid centre (0.39, +0.15).
  - Env: `LID_CENTER` ("0.39,0.15"), `LID_YAW_DEG` (0), `LID_LAYOUT` request|mirror, `LID_TOP` (0.075), `LID_REFINE` on|off,
    `LID_GAP` (0.008), `LID_BINS` ("right").
- `policy/decision_oracle/test_insert.py`: **PASS** in the policy image: `find_lid` within 2 mm / 0.2° / 0 mm height on
  synthetic depth (lid moved up to 5 cm, turned up to 10°); 18/18 blocks in 6 layouts get a direct plan, all by the
  **left arm** (it reaches the right half of the band), wrist error ≤ 1.8°, drop error ≤ 1.6 mm.
- Sim: `sim/task3/lid_shape_holes_200mm.stl` (Aalto's lid, from Samer), `modal_pipeline/sim/scene_variant.py --task3 request`
  (lid on the left bin moved to mat (0.60, 0.25) = pelvis (0.39, +0.15), STL turned 180° about x so the plate is on top
  and the triangle hole faces the robot, centre bin moved away, 3 blocks in mat x 0.28–0.42, y 0.12–0.19, lid thickness
  0.012), `modal_sim.py` adds `sim/task3` to the image. Checked locally: holes where expected, normals consistent.
  Aalto's own sim already has the Insert task + scorer (`TASK=Aalto-Insert-G129-Dex3-Joint`, `evaluate.py --task insert_shapes`).
- Not done for task 3: the full sim result (queued), tuning, venue appearance, lid placement error tests, and **task 3 in
  Marcus's agent image** (needs a dispatcher in `serve.py`: delegate task `insert_shapes` to our `OracleV16`, plus our
  policy code in that image).

**Docs:** `docs/research/real-hand-drop3.md` (drop 3: real Dex3 empty-hand finger error 0.04–0.26 rad exceeds every
grasp-check threshold, so "holding" is always read on the real robot; tactile contact 9,000–22,000 vs ≤ ~4,600 idle;
ask Aalto to put `observation.tactile` in `obs`). This file `docs/HANDOFF.md`.

### 3b. Hand-offset session
`eval/analysis/hand_offset.py`, `docs/research/hand-offset-real-data.md`, `docs/research/img/hand-offset-*.{jpg,png}`;
probably also the edits to `docs/research/README.md` and `eval/analysis/README.md`.

### 3c. Gemma session (v1.6g)
`policy/instruction_gemma.py`, `policy/policies/oracle_v16g.py`, `policy/requirements-gemma.txt`, `policy/tests/test_v16g.py`,
`policy/tools/replay_instruction.py`, `training/instruction_parser/{compare_v16g.py,gen_templates.py,modal_retrain.py,run_v16g_retrain.sh}`;
probably the edits to `.dockerignore`, `Makefile`, `policy/Dockerfile`, `policy/README.md`, `training/instruction_parser/README.md`,
and the `_v16g` part of `policy/server.py`.

### 3d. Grip-sweep session
`docs/research/grip_sweep_table.py` (results doc pending).

## 4. Facts established this session (beyond the repo)
- Sim machine: 30 cores; 3 sims at once → real-time factor 0.2 (CPU-bound, physics on CPU); GPU (RTX PRO 6000, 98 GB) not the limit.
- Modal: our `modal_pipeline` image builds from the cache in ~1 min; the GPU limit (~9–10 concurrent L40S) is shared by all sessions.
- Marcus's repo: newest is `1855ff4` (grasp options with failure memory, ridge grip, camera-fit acceptance by camera
  movement): with it `patch_headpose.py` prints "NOT patched" (fine, his own fix replaces it); `patch_lean.py` patches.
- Task 3 reach (committed earlier, `docs/research/task3-lid-placement.md`): default lid unreachable; the requested
  placement works. **Samer still has to send that message to Aalto** (text is in the doc).

## 5. Remaining plan (after §0)
- Apply the grip sweep's best values (cylinders / standing prisms) via `AALTO_CFG_OVERRIDES` defaults in the final image.
- Final image build, on the sim machine after `git pull`:
  - v1.6 / v1.6g: `make docker-build POLICY=v1.6 IMAGE=bot-icelli/policy:final-v16` (v1.6g per the Gemma session's
    instructions), gate check with `compare.sh` (nominal, 0 clips), tag + push `ghcr.io/samer-cyber/bot-icelli-policy:<tag>`,
    anonymous manifest check (HTTP 200 + digest), as for the pre-submission.
  - Marcus's agent: `MARCUS_REF=1855ff4 TAG=final-adk bash ~/bot-icelli/policy/adk/build.sh` (needs `~/adk_key.env` with
    `GEMINI_API_KEY=`; check its "patched:" lines), same checks.
- Optional, lower value now: reach-check image (W2b: hands hover 5 cm above mat grid points so staff can read the real
  offset); Aalto would have to run it before the finals.
- Not doing: a new simulator (MuJoCo menagerie G1 exists; judges said every team built a better sim).

## 6. Decisions for Samer / the team
1. Final image: Marcus's agent or v1.6/v1.6g (task 3 only exists in our v1.x stack so far).
2. **Decided by the sim (Sun ~02:00): off** (e-061/e-062, default changed in 847df56). Was: ship the lean mapping `auto` (on for the real robot) or off. Evidence: 109 real frames, 43 episodes; the lean model
   fits to 2.3 cm, the mounted-tilt model (what all our policies assume) to 6.4 cm. Not yet tested in a sim.
3. Attempt task 3 on the real robot (+3 per block, −1 per block left on/beside the lid).
4. Stop idle sim A (pid 185881) to speed up the A/B.
5. Messages to Aalto: task-3 placement (doc text); tactile in `obs`; if there is robot time, run the `look` image (logs
   the camera fit, i.e. the lean, and a depth hand check); forward any real-robot feedback/video to the agents.

## 7. Rules that still apply
- Never commit secrets; keys only in local `.env` (and `~/adk_key.env` on the machine). Never print or commit the sim
  machine's IP. No `Co-Authored-By`/"Generated with" lines (the repo hook strips them). Never edit `third_party/`
  (patch at runtime, or edit the sim machine's own clone `/root/aaltonomous-humanoid`).
- Don't kill other sessions' runs without Samer's OK. Side sessions share this folder: touch only your own files.
- The Gemini key in the public pre-submission image was Samer's decision; using the `.env` key for test runs is approved.
- AI tools commit only when a human asks (Samer has allowed commits/pushes of team docs and this work in bot-icelli).

## 8. Command cookbook
```bash
# sim machine (Git Bash, from bot-icelli)
H=$(grep -m1 '^VERDA_SIM_HOST=' .env | cut -d= -f2- | tr -d "\"'\r "); case "$H" in *@*) ;; *) H="root@$H";; esac
ssh -o BatchMode=yes -o ConnectTimeout=40 "$H" 'tmux capture-pane -p -t ab_c -S -300 | grep -aE "^trial|^=== "'
# offline tests in the policy image (copy the files to /tmp/t3 on the machine first)
docker run --rm -v /tmp/t3/insert.py:/app/policy/decision_oracle/insert.py -v /tmp/t3/test_insert.py:/app/policy/decision_oracle/test_insert.py \
  -v /tmp/t3/test_offline.py:/app/policy/decision_oracle/test_offline.py -w /app/policy bot-icelli/policy:v1.6-smooth \
  python3 -m decision_oracle.test_insert --layouts 6 --budget 4
docker run --rm -v /tmp/t3/lean.py:/app/policy/lean.py -v /tmp/t3/test_lean.py:/app/policy/tests/test_lean.py -w /app/policy \
  bot-icelli/policy:v1.6-smooth sh -c "touch tests/__init__.py; python3 -m unittest tests.test_lean -v"
```
```powershell
# Modal (PowerShell or Git Bash), from bot-icelli\modal_pipeline
..\..\junction2026\.venv\Scripts\modal.exe run --detach sim/modal_sim.py --action eval-policy --policy v1.6 `
  --task Aalto-Insert-G129-Dex3-Joint --eval-task insert_shapes --look none --variant "--task3 request" `
  --trials 2 --seed 1000 --tag t3-v16-b --background
#   --server-env "LEAN_MAP=off LID_GAP=0.01"   settings for the policy;  --look venue for the venue look (set LEAN_MAP=off there)
..\..\junction2026\.venv\Scripts\modal.exe volume get aalto-sim-out t3-v16-a sim_out
```
