# Dataset registry

Empty log, one row per dataset. The columns are a starting point; change them as the team needs.

| ID | Source | Episodes (ok / total) | Filter / how made (script + commit) | Location | Made by | Notes |
|---|---|---|---|---|---|---|
| ds-001 | Aalto drop 1: [`zupermiez/g1_pick_cube`](https://huggingface.co/datasets/zupermiez/g1_pick_cube) (Sat 14 Nov 01:54) | ? / 20 (no labels) | raw, unfiltered | Hugging Face (public); local copy in `artifacts/datasets/g1_pick_cube/` | Aalto | 11,720 frames, 479 MB. `pick up cube.`; Quest 3 teleop; no depth. Arms over 1 rad/s in 19/20 episodes; ep 13 and 16 spike to 21–28 rad/s; ep 19 doesn't move. Aalto: a significant part is "suboptimal" |
| ds-002 | Aalto drop 2: [`zupermiez/g1_junction_drop_2`](https://huggingface.co/datasets/zupermiez/g1_junction_drop_2) (Sat 14 Nov 11:37) | ? / 48 (no labels) | raw, unfiltered | Hugging Face (public); local copy in `artifacts/datasets/g1_junction_drop_2/` | Aalto | 14,548 frames, 472 MB. Single-object "Put the {orange/purple} {cube/triangular prism} into the {left/center/right} box.": orange cube → right (16), purple cube → center (14), orange cube → left (13), orange triangular prism → right (5); no yellow, no cylinders; no depth. Arms over 1 rad/s in 48/48 episodes (needs ×3 slow-down) |

**Both drops differ from the format in Aalto's repo docs:** camera keys are `observation.images.cam_high` / `cam_left_wrist` / `cam_right_wrist` (docs: `head_rgb`, `*_wrist_rgb`), there is **no head depth**, no GR00T copy and no `meta/aalto_episodes.jsonl` with success labels. Same as the docs: LeRobot v3.0, 30 Hz, 640×480, `observation.state` and `action` = 28 values in the documented joint order.
