# Runbook: recreate the venue-look sim

How to get, from nothing, Aalto's sim looking like the real table at Junction (the "venue look"), and how to check it against the real footage. Every command here was run on Sat 14 Nov on `bot-icelli-sim` (Verda spot RTX PRO 6000, Aalto's repo at commit 36daf5b).

- **What the look changes and what still differs from reality:** [`sim/venue_look/README.md`](../../sim/venue_look/README.md).
- **Time:** about 40 min for the machine and Aalto's sim (step 1), about 5 min for the look (steps 2–3).
- **Cost:** the machine bills while it exists (€1.28/h spot plus disks on Sat 14 Nov). Stop it when done: `verda-sim-setup.md`, "Stopping the machine".

`<ip>` below is your machine's address. Commands marked **laptop** run in this repo's root; the rest run on the machine as root.

## 1. A machine with Aalto's sim running
Follow [`verda-sim-setup.md`](verda-sim-setup.md): section 1 (machine) and section 2b (bare-metal install, including the two package-pin fixes). On an RTX PRO 6000 also apply the start-up fix in its Troubleshooting table ("Black images").

Done when this prints `9 PASS / 0 FAIL` with Aalto's default look:
```bash
cd /root/aaltonomous-humanoid
bash aaltonomous/cloud/aalto.sh sim
bash aaltonomous/cloud/aalto.sh check
```

## 2. Install the look
**laptop:**
```bash
scp -r sim/venue_look root@<ip>:/root/
```
On the machine:
```bash
bash /root/venue_look/redeploy.sh
```
`redeploy.sh` does all of this, and is safe to run again after any change:
1. stops the sim;
2. restores Aalto's three files and patches them (`patch_aalto.py`: adds the `AALTO_LOOK` and `AALTO_SCENE` switches to Aalto's clone);
3. generates `plywood.png`, the six `venue_bg_<i>.jpg` backgrounds and `scene_venue.yaml` (`make_assets.py`);
4. starts the sim with the look (`venue_env.sh` sets the two variables);
5. runs the scene checks and saves one image per camera to `/root/snap_venue`.

Expected last lines:
```
9 PASS / 0 FAIL
[aalto] look: venue (/root/venue_look/venue.yaml)
[aalto] look: surroundings venue_bg_<i>.jpg
[aalto] look: robot arm, 28 prims changed
snapshots in /root/snap_venue
```
Options, as environment variables in front of the command: `AALTO_LOOK_BG=<0-5>` (fixed background instead of a random one), `SEED=<n>` (object layout), `AALTO_DIR=<path>` (Aalto's clone, if not `/root/aaltonomous-humanoid`).

## 3. Use it
Every shell that talks to the sim needs the two variables, or the scorer and the oracle use the wrong bin size:
```bash
source /root/venue_look/venue_env.sh
cd /root/aaltonomous-humanoid
bash aaltonomous/cloud/aalto.sh check                                          # 9 PASS
bash aaltonomous/cloud/aalto.sh snap --out /root/snap_venue                    # one image per camera
bash aaltonomous/cloud/aalto.sh py -m aaltonomous.sim.scene_client random 7    # new object layout, no restart
bash aaltonomous/cloud/aalto.sh baseline                                       # Aalto's oracle, 3 trials, score table
bash aaltonomous/cloud/aalto.sh eval --policy ws://localhost:8000 --task sort_fixed --trials 10   # our policy
```
- **See the images (laptop):** `scp -r root@<ip>:/root/snap_venue artifacts/sim-snap/`.
- **With Aalto's randomisation on top:** put `AALTO_DR=train` in front of `redeploy.sh`.
- **Back to Aalto's default look:** `aalto.sh stop`, open a new shell (or `unset AALTO_LOOK AALTO_SCENE`), `aalto.sh sim`. The patch can stay; it does nothing without the variables.
- **Oracle results so far:** 88 % with the look and Aalto's layouts, 71 % with the scattered layouts (`eval/RESULTS.md`, e-002 and e-003).

## 4. Compare with the real footage
The sim robot is put into the joint angles of a real frame, so the two sets of images show the same pose.

**laptop** (once; needs the real datasets in `artifacts/datasets/`, see `data/DATASETS.md`, and `pip install -r sim/venue_look/tools/requirements.txt`):
```bash
python sim/venue_look/tools/real_frames.py artifacts/datasets/g1_junction_drop_2 artifacts/real_frames --frames 0 150
scp artifacts/real_frames/poses.json root@<ip>:/root/
```
On the machine (sim running with the look):
```bash
source /root/venue_look/venue_env.sh && cd /root/aaltonomous-humanoid
bash aaltonomous/cloud/aalto.sh py /root/venue_look/tools/pose_from_real.py /root/poses.json g1_junction_drop_2:150
bash aaltonomous/cloud/aalto.sh snap --out /root/snap_pose
```
The first command should print `clipped 0` and joint errors below 0.1 rad. **laptop:**
```bash
scp -r root@<ip>:/root/snap_pose artifacts/sim-snap/
python sim/venue_look/tools/compare.py artifacts/sim-snap/snap_pose artifacts/real_frames g1_junction_drop_2:150 artifacts/sim-snap/compare.jpg
```
`compare.jpg` has the sim on top and the real frame below: left wrist, right wrist, head.

## 5. Change something
1. Edit `sim/venue_look/venue.yaml` (**laptop**). Every value has a comment saying what it is and where it came from. Colours are sRGB 0–255 as seen in an image.
2. `scp -r sim/venue_look root@<ip>:/root/`
3. `bash /root/venue_look/redeploy.sh` on the machine (about 1 min), then step 4 again to compare.

| To change | Where in `venue.yaml` |
|---|---|
| Head camera angle and position | `camera.head` |
| Wrist camera mount and lens | `camera.wrist` |
| Object, bin, table, tape colours | `objects`, `bins`, `table`, `counter` |
| Lamp, room light, backgrounds | `lights` (`backdrop.walls` brings back dark curtains) |
| Blur and focus | `render` |
| Wrist, hand, cable, camera-board look | `robot.arm` |
| Bin wall height, where and how many objects spawn | `scene` |

Code changes go in `patch_aalto.py` (what the sim does with those values) or `make_assets.py` (generated pictures). Never edit Aalto's files by hand: `redeploy.sh` restores them.

## 6. How the numbers were found (and how to redo them)
All from Aalto's two real datasets and one phone photo of the table. Details and the remaining errors are in the README.

| Value | Method | Redo it |
|---|---|---|
| Head camera: 9° further down, 1° roll, 2.5 cm sideways; bin walls 7.5 cm | Project Aalto's bins through the calibrated camera, fit the pose to the middle bin's six corners clicked in a real frame | **laptop:** `python sim/venue_look/tools/fit_head_camera.py <real_head.jpg> <overlay.jpg>`. Prints 7.9°, 4.7 cm, 1.0°, 7.1 cm for drop 1; `venue.yaml` uses the middle of the two drops |
| Wrist cameras: at the base of the hand, about 35° down, 25° towards the thumb | Robot model gives the wrist pose per frame; fit a camera on the wrist so the projected bins cover the orange in 60 real frames per hand. Position read off the head-camera video | See below |
| Colours of objects, bins, table, hands | Median pixel values in the real head and wrist frames | Read the pixels in any image viewer; write them into `venue.yaml` |
| Where objects lie | 67 object sightings in 24 real head frames, converted to table coordinates with the fitted camera | `scene.layout` in `venue.yaml` |
| Backgrounds | Made up by `make_assets.py` to resemble the hall (no real people or logos) | Edit `venue_background()` |

**Wrist-camera fit** (needs `pinocchio`, which the machine's `isaac` environment has; about 2 min per hand):
```bash
# laptop: 30 frames from each dataset, copied to the machine
for d in g1_pick_cube g1_junction_drop_2; do python sim/venue_look/tools/real_frames.py artifacts/datasets/$d artifacts/real_frames --n 30; done
scp -r artifacts/real_frames root@<ip>:/root/
# machine
source ~/miniforge3/etc/profile.d/conda.sh && conda activate isaac
cd /root/venue_look/tools
AALTO_DIR=/root/aaltonomous-humanoid python fit_wrist_camera.py left /root/real_frames \
  /root/aaltonomous-humanoid/third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf
```
It prints the 8 best candidates. Read them as a range: the direction is similar across them, the position and lens are not. Sat 14 Nov, left hand: pitch 30–40°, towards the thumb 17–44°, roll −11 to −17°, field of view 74–97°.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `patch_aalto.py` stops with `AssertionError: expected 1x, found 0x` and a piece of code | Aalto changed the code it edits (their repo moved on from 36daf5b). The message shows the piece it looked for; find its new form in Aalto's file and update `patch_aalto.py` |
| `check` fails only with the look | Run `redeploy.sh` again and read `/tmp/aalto_sim.log` for `[aalto] look:` lines and Python errors |
| Oracle or scoring behaves oddly (objects "missing" bins) | That shell has no `AALTO_SCENE`. `source /root/venue_look/venue_env.sh` |
| `[aalto] look: surroundings ... not found` | The backgrounds were not generated: run `redeploy.sh`, or `python make_assets.py <Aalto's scene.yaml>` in `/root/venue_look` |
| `pose_from_real.py` says "episode is over" or hangs | The sim is not running, or the shell lacks `venue_env.sh` |
| Black camera images on an RTX PRO 6000 | `verda-sim-setup.md`, Troubleshooting |
