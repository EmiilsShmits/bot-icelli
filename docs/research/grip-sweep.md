# Grip sweep: does any grasp setting fix cylinders or standing prisms? (Sat 14 Nov, ~00:20)

**Answer (FACT): no setting is clearly better than the default.** Cylinders already hold 95 %; standing triangular
prisms fail with every setting tried (10–25 %). Nothing from this sweep goes into the final image.

Run by the overnight grip-sweep session on Modal (9 GPUs), written up afterwards from its result files
(`junction2026/sim_out/gs1/*.json`, `gs1dr/base_dr.json` on Samer's laptop; raw runs on the Modal volume
`aalto-sim-out`, folders `gs1/<setting>`, `gs1dr/base_dr`). Table: `python docs/research/grip_sweep_table.py
<gs1 dir> <gs1dr dir> --base base`.

## Method
- Marcus's grasp bench (`sim/modal_sim.py --action grasp-bench`, his repo): one standing object per case, the
  oracle-based grasp, **one grasp per object** (`BENCH_TRIES=1`), 20 cases per shape (positions and turns spread over
  the object band), Aalto's nominal look (`gs1`) and `AALTO_DR=train` (`gs1dr`, default setting only).
- A case counts as held if the grasp lifted the object and it ended in a bin. 95 % intervals are Wilson intervals.

## Results (20 grasps per row)
| Setting | Cylinder held | Standing triangle held |
|---|---|---|
| `base` (default) | **19/20 = 95 %** (76–99) | **2/20 = 10 %** (3–30) |
| `closeslow` | 20/20 | 3/20 |
| `h40` (grasp lower) | 19/20 | 5/20 = 25 % (11–47) |
| `h60` (grasp higher) | 20/20 | 5/20 = 25 % (11–47) |
| `palmx` | 19/20 | 2/20 |
| `prenarrow` | 20/20 | 4/20 |
| `prewide` | 17/20 (worse: 3 missed) | 2/20 |
| `slow2` | 19/20 | 4/20 |
| `thumb` | 19/20 | 4/20 |
| `base` with `AALTO_DR=train` | 16/20 = 80 % | 3/20 = 15 % |

- Triangle misses are almost all "closed on nothing" (15–18 per setting); no setting changed that.
- The best triangle rows (`h40`, `h60`: 5/20) overlap the default's interval; against `base` they held 5 cases it
  missed and missed 2 it held: not evidence of a real gain.

## What it means (OPINION, Claude)
- Don't change grip defaults in the final image: no measured gain, and every change is untested on the real hand.
- Standing prisms need a different grasp, not a tuned one: the face-aligned grasp (Emīls's `upgrades.py`, Tiya's
  `pick_triangle`), or a push / topple to a lying prism, which the ridge grasp handles.
