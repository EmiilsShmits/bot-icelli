# sim/venue_look: make the sim look like the real table

**Purpose:** a second, switchable look for Aalto's sim that resembles the real table at Junction, to shrink the visual gap between sim and the real robot (Aalto's "real2sim" route). The default sim is untouched.
**Owner:** Marcus, Samer (first version built by Emīls with Claude, Sat 14 Nov)

## What it changes
| | Aalto default | Venue look |
|---|---|---|
| Head camera | pose from `calibration.yaml` (a URDF default) | looks 9° further down, 1° roll, 2.5 cm to the robot's left: fitted to the real footage |
| Objects | red, yellow, blue; 3–4 in a band in front of the bins | orange, yellow, blue-violet; **3–6 scattered over the area where the real ones lie** (mat x 0.30–0.60, y 0.04–0.20, down to 6.5 cm apart) |
| Table | white printed grid mat | pale grey-pink glossy wood with a glare patch from the lamp, no mat; orange tape marks in front of the bins |
| Bins | plain orange, 6 cm walls | red-orange outside, grey cardboard inside, **7.5 cm walls**, orange paper folded over the rim of all three (wide on the middle box, slightly uneven). Same 21 cm size and 5 cm gaps as Aalto's |
| Lighting | bright, warm, lamp overhead | one cool lamp in front of the robot on its right, weak room light |
| Background | grey | no walls; all round, one of six made-up event halls (dark blue walls, purple / cyan / white lights, blurred people-sized shapes). A different hall each time the sim starts; it also tints the table and the reflections |
| Camera image | sharp | motion blur and slightly soft focus (applies to all cameras) |
| Robot arms | dark grey, near-black hands, big white wrist-camera bracket | silver wrists, **blue-grey hands** (the real black plastic reads grey on camera), a black cable on each forearm, a small camera board instead of the bracket |
| Wrist cameras | Unitree's placeholder: fisheye, looking sideways | at the base of the hand, looking along the fingers (about 35° down, 25° towards the thumb), plain 75° lens. **An estimate, see below** |

Sources: a phone photo of the real table (Sat 14 Nov) and the head-camera video in Aalto's two real datasets (`data/DATASETS.md`, d-001 and d-002). Sim next to real, head camera and both wrist cameras: `artifacts/sim-snap/venue_v3/head_sim_vs_real.jpg` and `artifacts/sim-snap/venue_v4/wrist_sim_vs_real.jpg`; hands before / now / real: `artifacts/sim-snap/venue_v6/hands_before_now_real.jpg` (local, git-ignored).

## Files
| File | What |
|---|---|
| `venue.yaml` | The look: camera offset, colours, materials, lights, tape marks, blur, robot arm, plus a `scene:` section with geometry changes (bin wall height, where objects spawn). Edit this to tune |
| `patch_aalto.py` | Adds `AALTO_LOOK` and `AALTO_SCENE` support to a clone of Aalto's repo (three files: `scene/scene.py`, `sim/aalto_task/scene_cfg.py`, `sim/aalto_task/hooks.py`). Idempotent |
| `venue_env.sh` | Sets `AALTO_LOOK` and `AALTO_SCENE`. Source it in every shell that starts the sim or a client |
| `redeploy.sh` | On the machine: re-patch, regenerate, restart the sim with the look, check, snapshot. Run after any change |
| `tools/real_frames.py` | Laptop: takes frames out of a real dataset (three camera images + joint angles → `poses.json`) |
| `tools/pose_from_real.py` | Machine: puts the sim robot into a recorded real joint pose (for like-for-like camera comparisons) |
| `tools/compare.py` | Laptop: tiles the sim snapshots over the real frame |
| `tools/fit_head_camera.py`, `tools/fit_wrist_camera.py` | The two camera fits described below |
| `tools/requirements.txt` | What the laptop tools need (numpy, opencv-python, pyarrow, pyyaml; `pin` for the wrist fit) |
| `start_venue.sh` | Starts the sim with the venue look (paths as on `bot-icelli-sim`) |
| `make_assets.py` | Generates `plywood.png`, the six `venue_bg_<i>.jpg` surroundings and `scene_venue.yaml` (Aalto's `scene.yaml` with the `scene:` section of `venue.yaml` merged in) |
| `plywood.png`, `venue_bg_<i>.jpg`, `scene_venue.yaml` | Generated; `scene_venue.yaml` exists only on the sim machine |

## How to run (on the sim machine, bare-metal install)
**Full step-by-step, from an empty machine to a comparison with the real footage: [`docs/runbooks/venue-sim.md`](../../docs/runbooks/venue-sim.md).** Short version:
```bash
# once: copy this folder to the machine, patch Aalto's clone (not our submodule), generate the geometry
scp -r sim/venue_look root@<ip>:/root/
python /root/venue_look/patch_aalto.py /root/aaltonomous-humanoid
(cd /root/venue_look && python make_assets.py /root/aaltonomous-humanoid/aaltonomous/scene/scene.yaml)

# start the sim with the venue look, then check it
cd /root/aaltonomous-humanoid
bash aaltonomous/cloud/aalto.sh stop
source /root/venue_look/venue_env.sh                   # needed in EVERY shell: sim, check, snap, baseline, eval
bash aaltonomous/cloud/aalto.sh sim
bash aaltonomous/cloud/aalto.sh check                  # 9 PASS
```
- **On Modal:** `modal_pipeline/sim/modal_sim.py` builds this folder into its image and uses the look for every action by default (`--look none` turns it off). See `modal_pipeline/README.md`.
- **Back to Aalto's default:** `aalto.sh stop`, `unset AALTO_LOOK AALTO_SCENE`, `aalto.sh sim`.
- **After any change in this folder:** copy it to the machine and run `bash /root/venue_look/redeploy.sh`; it does the steps above.
- **After editing `patch_aalto.py`, by hand:** on the machine, `git checkout aaltonomous/scene/scene.py aaltonomous/sim/aalto_task/scene_cfg.py aaltonomous/sim/aalto_task/hooks.py` in Aalto's clone, then run the patch again (it skips files it has already patched).
- **Other geometry or object spread:** edit the `scene:` section of `venue.yaml`, run `make_assets.py` again, restart the sim.
- **New object layout without a restart:** `aalto.sh py -m aaltonomous.sim.scene_client random <seed>`.
- **Fixed background:** `export AALTO_LOOK_BG=<0-5>` before starting the sim (or `lights.dome_texture_pick` in `venue.yaml`). Unset = a random one per start.
- **With randomisation:** add `AALTO_DR=train`. Aalto's jitter is applied around the venue colours and camera pose.

## How the camera offset was found
Projected Aalto's scene (bin corners from `scene.yaml`, camera from `calibration.yaml`) into the image and fitted the camera rotation, sideways shift and bin wall height to the middle bin's corners in one real frame per dataset.

| Dataset | Further down | Roll | Camera to the robot's left | Wall height | Fit error |
|---|---|---|---|---|---|
| `g1_pick_cube` (drop 1), frame 0 | 7.9° | 1.0° | 4.7 cm | 7.1 cm | 3.4 px |
| `g1_junction_drop_2` (drop 2), frame 0 | 12.2° | 1.1° | 0.7 cm | 7.9 cm | 5.2 px |

- The bin widths in the image already matched (235 px real, 238 px projected), so the distance to the bins is right; the difference is the viewing angle.
- `venue.yaml` uses the middle of the two (10° down), minus 1° because the renderer ignores the calibrated principal point.
- The fit can't tell a tilted camera from a leaning torso or a robot standing off-centre. The image is the same either way.

## How the wrist camera pose was found
Aalto's sim uses Unitree's sample wrist cameras (their calibration file is from another robot), and Aalto's `calibration.yaml` has no wrist mount. The real cameras are small bare circuit boards at the base of each hand; they are visible in the real head-camera video.

- **Direction:** fitted on 60 real frames per hand. For each frame the robot model gives the wrist pose from the recorded joint angles; the bins are projected through a candidate camera and should cover the orange paper in the real image. Both hands gave about 35° down (towards the middle finger) and 25° towards the thumb, mirror-symmetric.
- **Position and lens:** not pinned down by that fit. Position is read off the head-camera video (base of the hand, index-finger side). The 75° lens is a guess; the fit preferred anything from 75° to 100°.
- **Expect errors of 15–20° and a few cm.** A measured mount from Aalto would replace all of this (`camera.wrist` in `venue.yaml`).
- **Check used:** `tools/pose_from_real.py` puts the sim robot into a recorded real joint pose, so sim and real images can be compared like for like.

## What still differs from the real cameras
| # | Real | Sim (venue look) |
|---|---|---|
| 1 | **Wrist cameras:** fingers fill more than half the image, on both sides; behind them a real hall with people, tables and screens, and in some frames a black banner or curtain | Same general view (fingers in front, bins and table beyond), but the fingers are smaller and mostly on one side, and the direction is an estimate. The hall is made up, not a photo, nothing in it moves, and there is no black curtain or banner |
| 1b | With the robot in the same joint pose, the real hand is about 4–6 cm closer to the robot (lower in the head image) | Hand sits further forward. Cause not found: could be the head-camera fit, joint zero offsets or arm sag |
| 2 | The head view changes by about 4° and 4 cm between the two datasets, and shifts within one | One fixed pose. Aalto's `AALTO_DR=train` jitters it by only ±1° and ±1 cm |
| 3 | Gaps between bins vary from about 3 to 5 cm (hand-placed); paper rims are creased and torn | Even 5 cm gaps; rims only slightly uneven |
| 4 | Objects often touch each other | At least 6.5 cm between centres, so they come close but rarely touch |
| 5 | Arms start low, hands near the table edge; the wrist is a silver ball joint with a thin cable loop | Aalto's start pose (left forearm in front of the left bin); recoloured wrist links, a plain plate for the camera board and a simple cable arc |
| 5b | **Hands:** grey with a teal tint and washed out in the wrist cameras (about 30,50,65 in shade to 90,120,120 where lit); darker navy in the head camera (about 0,25,55 to 45,55,75) | One grey material for both (`robot.arm.hand_rgb`): about 30,40,65 in the wrist cameras, 45,60,90 from the head. A little too dark and blue on the wrists, too light from the head. The tint follows the background picked at start |
| 6 | Dark, contrasty image; bin interiors darker; people and coloured lights reflect in the table | Brighter and cleaner; only the lamp reflects |

## Status
- **Now:** works on `bot-icelli-sim` (spot RTX PRO 6000, resumed Sat 14 Nov): 9/9 scene checks pass with everything in the table above, including the new wrist cameras, backgrounds and grey hands. Aalto's oracle sorts 71 % (10/14) with the scattered layouts, 88 % (7/8) with Aalto's own layout band (`eval/RESULTS.md` e-003, e-002).
- **Also (Sat 14 Nov ~19:00, Samer + Claude):** running on `samer-v1-sim` as a third sim next to Aalto's nominal scene and `AALTO_DR=train` (`eval/venue_lane.sh`). Checked against a real head-camera frame: framing, bins with rim paper, table and the orange / yellow / purple objects match well; a bit cleaner than the real image, purple more saturated, hands lighter. It caught a bug: v1.2/v1.3's head-camera fit check rejected the correct 9.8° fit here (fixed in `policy/` v1.4).
- **Next:** the hand-position offset (row 1b); a randomisation file with a wider head-camera jitter (about ±3°, ±3 cm, row 2).
- **Blockers:** the red/blue colour mapping below is still a guess.

## Gotchas
- **The background changes between sim starts, not between episodes.** For runs that should be comparable, fix it with `AALTO_LOOK_BG`. The pictures are generated, so they hold no real people or logos.
- **The wrist cameras are an estimate, not a calibration.** Don't use them for geometry (pixel → 3-D). Aalto's `calibration.yaml` still has no wrist pose.
- **Blur and focus are renderer-wide.** The `render:` settings in `venue.yaml` change every camera, including the depth-aligned head RGB.
- **Tape marks, rim paper and the cable have no collision.** They only change the image.
- **Colour names are partly a guess.** Aalto confirmed on Discord (Sat 14 Nov) that the real objects are purple, yellow and orange and that the sim's red / blue / yellow are wrong. They did not say which real colour replaces "red" and which "blue"; `venue.yaml` assumes "red" = orange and "blue" = purple.
- **The rim paper is visual only by default.** Objects fall through it in the sim. Its widths (1.5–3.5 cm per side on the middle box, about 1 cm on the others) are rough estimates from images. `rim_tape_collide: true` in `venue.yaml` would make it a solid ledge, which shrinks the middle opening to about 14.5 × 16.5 cm; that setting is untested, and nobody has checked how stiff the real tape is. Aalto's randomisation (`AALTO_DR`) doesn't vary the tape colour.
- **Geometry: the bin wall height and the object spawn region differ from Aalto's.** Both are in the `scene:` section of `venue.yaml`. The spawn region covers where 67 real object sightings lie (24 frames); the oracle does worse in it (see Status). Bin size (21 cm, measured by Aalto) and the 5 cm gaps are Aalto's values. The 7.5 cm wall height comes from the camera fit above (Aalto's 6 cm is an unmeasured default); a tape measure would settle it. A first version made the bins touch; that was a misreading of the photo.
- **`calibration.yaml` is unchanged.** The look moves the sim camera, but Aalto's calibration file still describes the old pose. Code that turns head-camera pixels or depth into 3-D points with that file is off by about 10° in this look, as it would be on the real robot.
- **`AALTO_SCENE` must be the same for the sim and every client** (`check`, `eval`, `baseline`, recording). Otherwise the scorer and the oracle use a different bin size from the sim. `source venue_env.sh` in each shell does it.
- **Finalists are picked in a hidden sim variant** with other textures and lighting. Train on this look *in addition to* the default look and randomisation, not instead.
- **Colours in `venue.yaml` are sRGB (0–255)** as seen in an image; the patch converts them to the linear values the renderer needs. Aalto's own `scene.yaml` colours are passed to the renderer unconverted.
- The patch fails loudly if Aalto changes the code it edits. Re-check after `make update-aalto`.
