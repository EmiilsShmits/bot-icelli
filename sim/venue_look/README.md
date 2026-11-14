# sim/venue_look: make the sim look like the real table

**Purpose:** a second, switchable look for Aalto's sim that resembles the real table at Junction, to shrink the visual gap between sim and the real robot (Aalto's "real2sim" route). The default sim is untouched.
**Owner:** Marcus, Samer (first version built by Emīls with Claude, Sat 14 Nov)

## What it changes
| | Aalto default | Venue look |
|---|---|---|
| Objects | red, yellow, blue | orange, yellow, purple |
| Table | white printed grid mat | varnished plywood, no mat |
| Bins | plain orange | orange outside and rim, cardboard inside; the **middle** box has wide orange tape folded over its opening. Same size and 5 cm gaps as Aalto's |
| Background | grey | black curtains, dark floor, less ambient light |

Source: one phone photo of the real table (Sat 14 Nov), colours sampled from it. Compare `artifacts/sim-snap/venue/head_camera.jpg` with `artifacts/sim-snap/nominal_seed4/head_camera.jpg` (local, git-ignored).

## Files
| File | What |
|---|---|
| `venue.yaml` | The look: colours, materials, lights. Edit this to tune |
| `patch_aalto.py` | Adds `AALTO_LOOK` and `AALTO_SCENE` support to a clone of Aalto's repo (two files). Idempotent |
| `start_venue.sh` | Starts the sim with the venue look (paths as on `bot-icelli-sim`) |
| `make_assets.py` | Generates `plywood.png`. Can also write a `scene_venue.yaml` with a measured bin gap |
| `plywood.png` | Table-top texture. Generated |

## How to run (on the sim machine, bare-metal install)
```bash
# once: copy this folder to the machine, then patch Aalto's clone (not our submodule)
scp -r sim/venue_look root@<ip>:/root/
python /root/venue_look/patch_aalto.py /root/aaltonomous-humanoid

# start the sim with the venue look
bash aaltonomous/cloud/aalto.sh stop
export AALTO_LOOK=/root/venue_look/venue.yaml          # appearance only; geometry stays Aalto's
bash aaltonomous/cloud/aalto.sh sim                    # or: bash /root/venue_look/start_venue.sh
bash aaltonomous/cloud/aalto.sh check                  # 9 PASS
```
- **Back to Aalto's default:** `aalto.sh stop`, unset `AALTO_LOOK`, `aalto.sh sim`.
- **Measured geometry (optional):** once someone measures the real bin gap, `python make_assets.py <aalto>/aaltonomous/scene/scene.yaml <gap in m>` writes `scene_venue.yaml`; export `AALTO_SCENE=<that file>` for the sim and every client.
- **With randomisation:** add `AALTO_DR=train`. Aalto's jitter is applied around the venue colours.

## Status
- **Now:** works on `bot-icelli-sim`: 9/9 scene checks pass. Appearance only; geometry is Aalto's. **The sim on that machine is currently running with the venue look.**
- **Next:** —
- **Blockers:** the colour mapping below is a guess.

## Gotchas
- **Colour names are a guess.** Aalto's instructions say red / yellow / blue; the real objects are orange / yellow / purple (and black). `venue.yaml` assumes "red" = orange and "blue" = purple. **Not confirmed by the organisers.**
- **The middle box's tape is visual only by default.** Objects fall through it in the sim. Its widths (2.5–4 cm per side) are rough estimates from the photo. `rim_tape_collide: true` in `venue.yaml` would make it a solid ledge, which shrinks the opening to about 14 × 15 cm; that setting is untested, and nobody has checked how stiff the real tape is. Aalto's randomisation (`AALTO_DR`) doesn't vary the tape colour.
- **Geometry is not from the photo.** A first version made the bins touch; that was a misreading (the real boxes are separated). Bin size (21 cm, measured by Aalto) and the 5 cm gaps are Aalto's values. The real gap and the bin height (Aalto's 6 cm is an unmeasured default; the real boxes look taller) still need a tape measure.
- **If you use `AALTO_SCENE`, it must be the same for the sim and every client** (`check`, `eval`, `baseline`, recording). Otherwise the scorer and the oracle use different bin positions from the sim.
- **Finalists are picked in a hidden sim variant** with other textures and lighting. Train on this look *in addition to* the default look and randomisation, not instead.
- **Colours in `venue.yaml` are sRGB (0–255)** as seen in a photo; the patch converts them to the linear values the renderer needs. Aalto's own `scene.yaml` colours are passed to the renderer unconverted.
- **Not matched:** the robot's white T-shirt and silver forearms, the real camera's exposure and noise, exact dimensions. Aalto's real data drops (recorded through the robot's cameras) are the better reference for those.
- The patch fails loudly if Aalto changes the code it edits. Re-check after `make update-aalto`.
