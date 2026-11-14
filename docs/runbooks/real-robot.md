# Runbook: a session on the real robot

**Owner:** Samer (Aalto contact). Written Sat 14 Nov ~20:05 by Samer + Claude. Nothing here has been tried on the
robot yet; update this file after the first session.

The goal of a first session is to learn the few facts the simulator can't tell us, with as little risk as possible:
first a run in which the robot doesn't move at all, then one supervised episode.

**Images (public on GHCR, linux/amd64, 1.46 GB, server up in < 1 s, no internet or API key needed):**
| Use | Image |
|---|---|
| Run 1: look only, never moves | `ghcr.io/samer-cyber/bot-icelli-policy@sha256:f4f871b526254bc8a173f0613a27bf963b0522a50d30ed290abf261d78993aed` (tag `look`) |
| Run 2+: our candidate v1.4 | `ghcr.io/samer-cyber/bot-icelli-policy@sha256:cd8311e9f64ea25703d9c70a645b44091dc5a00d8b5f75dc54f29720f6fd7f8d` (tag `v1.4`) |
| Fallback: v1.3 (no grasp check, no head-fit fix) | `ghcr.io/samer-cyber/bot-icelli-policy@sha256:60ef1b8980de11f9448da5de27234bf3d9f3b3be682f1914a2c0532c2ed504c4` (tag `v1.3`) |

## 0. Before: message to Aalto (erkka, Aalto channel / DM)
erkka offered real-robot deployments (through a Wendy agent) to teams that show readiness, and asked for material.
A draft (edit freely):

> Hi erkka, Samer from bot-icelli. Could we get a short slot (15–20 min) on the real robot?
> Our image is public: `ghcr.io/samer-cyber/bot-icelli-policy@sha256:cd8311e9…` (linux/amd64, CUDA 12.8 base,
> 1.46 GB, server up in under 1 s, no internet or keys). It never sends a command faster than 0.98 rad/s (arms) /
> 2.7 rad/s (fingers), below your filter's 1.0 / 3.0, and holds still while it plans.
> Plan: (1) 2 min with a look-only build (tag `look`) that never moves the robot and logs what our camera sees;
> (2) one sort_fixed episode with 3 objects, e-stop ready; (3) if all is well, one 5-object and one language episode.
> What we've done in sim, if useful: [link to the repo's `docs/CONTEXT.md`]; things we found in the starter repo:
> [link to `modal_pipeline/ORGANIZER_ISSUES.md`].
> Questions: (a) how does the robot stand during the runs (on its feet, on the gantry, seated)? Is the torso upright?
> (b) the table height relative to the waist joint, and the bins' wall height and positions: or may we measure them?
> (c) will the head camera's calibration file change for the finals? (d) does Wendy start the image like
> `docker run --gpus all -p 8000:8000 <image>` on the x86 PC with the RTX 5090? (e) could we get the policy's log and
> the run recording afterwards?

## 1. Bring
- Laptop with this repo. A tape measure (≥ 1 m). A phone with a spirit-level / inclinometer app (most phones have one
  in the measuring app). Someone to note numbers.

## 2. Measure the real setup (10 min, before anything runs)
Our code assumes the values in the third column (Aalto's `scene.yaml` / `calibration.yaml`, plus our estimates from
their footage). Write down what you find; a difference of more than ~2 cm or ~3° matters.

| # | What | How | Our code assumes | Why it matters |
|---|---|---|---|---|
| 1 | **Torso angle** (forward lean and sideways tilt) | phone level flat on the chest plate; again on the back of the head if there is a flat spot | upright, 0° | **The key question.** Aalto's footage shows the camera looking ~10° further down than its calibration. If the torso is upright, the camera is tilted on its mount and v1.4's camera fit is right. If the torso leans ~10°, the robot leans and v1.4 would put its hands several cm off (§7) |
| 2 | Table height vs the pelvis | tape: floor → table top, and floor → the hip joints (the pelvis) | table top 1 cm above the pelvis (table 80 cm, pelvis 79 cm, robot standing) | every grasp and drop height |
| 3 | Bins | tape, measured from the floor point below the pelvis (between the feet): distance to each bin's near wall, sideways position of each bin's centre, inside size, wall height, gaps | near walls 40 cm ahead; centre bin straight ahead, side bins ±26 cm; 21 cm inside; walls 6 cm (Aalto), 7.5 cm (our estimate from footage); gaps 5 cm | drop points; the far half of each bin is out of reach |
| 4 | Objects | ruler (and kitchen scale if there is one); how triangles lie (on a face or on a side) | 4.5 cm, ~50 g | grip |
| 5 | Where objects are placed | tape from the floor point below the pelvis | 26–35 cm ahead | **closer than ~27 cm is our weak zone** in sim (most of our losses) |
| 6 | Start pose | photo; are both hands visible to the head camera? | arms down, elbows bent, hands near the table edge in view | collisions, objects hidden behind the hands |
| 7 | Light | photo from just behind the robot's head | — | glare on the table can hide colours |
| 8 | Clearance | anything within ~60 cm the arms could hit (cables, bin backs, people) | — | safety |

## 3. Run 1: look only (2 min, the robot never moves)
- Image tag `look`. Aalto starts it like any submission. It answers every tick with "hold where you are", looks at
  the table every 5 s and ends the episode after 30 s.
- Put 3–5 objects on the table first (anywhere, also one close to the robot).
- Read the policy's log (`docker logs <container>`): every line we need starts with `[look`.

| Line | Good | Stop and tell Claude if |
|---|---|---|
| `camera fit: tilt …; camera moved …; v1.4 USES it` | tilt 8–12° (as in Aalto's footage), camera moved a few cm, USES | "does NOT use it", or tilt > 15° |
| `objects with the fitted camera: …` | exactly the objects on the table, right colours, tops 4–5 cm, positions within ~2 cm of your tape | bins or hands listed as objects; tops at 7–9 cm (camera pose wrong); objects missing |
| `hand check …` / `verdict: …` | "TILTED CAMERA" | "LEANING ROBOT". This check is not validated yet (Sat ~20:00): trust the phone level (§2 row 1) over it |
| `depth: … % valid pixels` | > 80 % | < 50 % (real depth holes would hurt grasping) |
| `finger angles …` | the open hand, near Aalto's `open` posture | — |

## 4. Run 2: one supervised episode with v1.4
- 3 objects, one of each colour, 30–35 cm in front of the robot, not touching. e-stop held by Aalto.
- Instruction: the real rung-1 wording (yellow → left, purple → centre, orange → right) or whatever Aalto uses.
- Watch: does the hand come down on the object or beside it? If it misses by a steady offset in one direction,
  note how far and which way: our config has a per-arm correction (`grasp.arm_xy_offset`).
- In the log, every pick prints `grasp check: held (finger error X rad …)` or `hand empty (…)`. In sim an empty hand
  reads 0.0001–0.0036 rad, a held object ≥ 0.008; the threshold is 0.006. Note the real values.
- **Stop it if:** a hand heads into the table or a bin wall; the two arms come close to each other (Aalto's planner
  doesn't check arm against arm, `modal_pipeline/ORGANIZER_ISSUES.md` A12); anything moves jerkily.

## 5. If there's more time
- 5 objects including a triangle on its side; one object 25 cm from the robot (our weak zone).
- A language episode: an instruction like "put the purple ones in the left bin, the orange ones in the middle and the
  yellow ones on the right".

## 6. Bring back
- Every run's policy log (`docker logs`), the run recording if Aalto records one, photos (setup from the side, from
  behind the head), and your measurements: write them into `docs/research/real-robot-measurements.md`.

## 7. What we'd change, depending on what you find
| Finding | Then |
|---|---|
| Torso upright, `look` says v1.4 USES the fit, objects right | hand in v1.4 as it is |
| Torso leans ~10° | the camera fit fixes what the robot sees but not where its arms go: rotate the arm model by the same angle (not built yet, ~1 h). Until then v1.4 may miss grasps by several cm |
| Steady reach offset (e.g. always 2 cm short) | set `grasp.arm_xy_offset` for that arm in v1.x, rebuild (~5 min) |
| Real empty hand reads > 0.006 rad | the grasp check treats empty hands as held: harmless, it then behaves like v1.3 |
| Real held object reads < 0.006 rad | the check would drop held objects: raise `V14_EMPTY_RAD` or hand in v1.3 |
| Bins or table not where `scene.yaml` says | move them in our copy of the scene values, rebuild |
| Colours missed | widen the colour ranges in `policy/policies/classical_v1.py` from the photos |
