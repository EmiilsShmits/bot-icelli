# Dataset registry

Empty log, one row per dataset. The columns are a starting point; change them as the team needs.

| ID | Source | Episodes (ok / total) | Filter / how made (script + commit) | Location | Made by | Notes |
|---|---|---|---|---|---|---|
| ds-001 | Aalto real drop: HF `zupermiez/g1_pick_cube` (Sat 14 Nov 01:54) | ? / 20 (no labels) | raw | Hugging Face | Aalto | `pick up cube.`; Quest 3 teleop; no depth. Arms over 1 rad/s in 19/20 episodes; ep 13 and 16 spike to 21–28 rad/s; ep 19 doesn't move |
| ds-002 | Aalto real drop: HF `zupermiez/g1_junction_drop_2` (Sat 14 Nov 11:37) | ? / 48 (no labels) | raw | Hugging Face | Aalto | Single-object "Put the {orange/purple} {cube/triangular prism} into the {left/center/right} box."; no depth. Arms over 1 rad/s in 48/48 episodes (needs ×3 slow-down) |
