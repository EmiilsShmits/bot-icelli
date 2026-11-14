# Aalto Discord: organiser answers that matter

Facts from the Aalto challenge channel on the Junction Discord, with what each means for us. **Newest first; add new answers at the top.** Copied by Samer on Sat 14 Nov ~12:00.

| When | Who | What they said | What it means for us |
|---|---|---|---|
| Sat 11:41 | erkka (Aalto) | The sim's object colours are wrong (red, blue, yellow). "We will use the ones we have (purple, yellow, orange). Feel free to edit the simulation how you see fit." "You need to make your sim really accurate to our setup if you want to have any chance of having the sim2real work." | **Perception and the instruction parser must handle the real colours (orange, purple) and the sim ones (red, blue).** The held-out sim variant is probably still Aalto's sim. See the colour check below. Still unconfirmed: in rung 1's fixed sentence ("red → left … blue → right"), does red mean orange and blue mean purple? |
| Sat 11:37 | erkka | Drop 2 is out: `zupermiez/g1_junction_drop_2` | Single-object demos; they break the speed caps. See [`real-data-findings.md`](real-data-findings.md) |
| Sat 09:47 | erkka | Finals: "we will connect a pc with rtx5090 to the robot via ethernet so bigger models can also fit. Please notify us well in advance if you plan to do something like this so we can start downloads early" | If our image grows (e.g. π0.5 weights), tell Aalto early |
| Sat 01:54 | erkka | First dataset `zupermiez/g1_pick_cube`: "a significant part of the data is 'suboptimal'. You will have to work on it yourself. Starting from the labels themselves. Better datasets coming tomorrow." | Don't trust the labels; curate. The drops have no success labels at all |
| Sat 01:00 | erkka | Answers to team The Larp Interns: (1) oracle not re-measured on the sim clock (~84 % before, triangles the main miss); (2) Dex3 gains kp 1.5 / kd 0.2, fixed and the same for every team; (3) pad friction not measured: the pads are rubber, the sim's 1.2 / 1.0 is "on the grippy side, so expect a bit less grip on the real robot"; (4) finals instructions: "colour comes first. If several teams handle colour, we may also test shape-based instructions. **No negation.**" | Tune grasps with **lower friction** in randomisation. **Shape-based instructions are likely** if we're good at colour, so parse shapes and estimate shape in perception. Negation is off the list |
| Sat 00:25–00:45 | erkka | Little data overnight: teleop only works over Wi-Fi from the VR goggles, and the venue Wi-Fi is unusable. "the whole challenge is anyway to try to make do with little real world data" | Aalto has a data-collection problem. A **wired** teleop (Rokoko Smartgloves II stream over USB; the Coil Pro has no radio) would solve it. That's an angle for a Rokoko project |
| Fri 21:40 | erkka | "no need to wait for the docker image btw you can build everything based on the repo" | Bare-metal install is fine (what we did) |
| Fri 21:40 | erkka | Asked whether the robot will have internet: "yes it can have" | **Contradicts the repo docs** ("we provide no network"). Confirm before relying on any API at runtime; keep an offline fallback regardless |
| Fri 19:42 | erkka | Challenge summary: 3 levels; Docker server at 30 Hz; sim evaluation → finalists → real robot on Sunday; "External APIs at your own risk; no guaranteed internet in the finals"; "Organisers reserve the right to change rules and details during the event" | — |

## Colour check (from Emīls's photo samples in `sim/venue_look/venue.yaml`)

OpenCV hue (0–180) of the real colours vs the classical baseline's HSV ranges (`baselines/classical/config.yaml`):

| Thing | sRGB sample | Hue | Baseline range | Result |
|---|---|---|---|---|
| Orange object ("red"?) | 240, 145, 45 | ~15 | red: 0–8 and 170–180 | **Falls between red and yellow: not detected** |
| Yellow object | 240, 216, 42 | ~26 | yellow: 18–35 | OK |
| Purple object ("blue"?) | 163, 135, 230 | ~129 | blue: 100–130 | **At the upper edge**: partly detected |
| Orange bins | 238, 125, 70 | ~10 | (masked by 3D position) | Close to the orange objects' hue: keep the bin mask |

These come from a phone photo, not the robot's camera, so the exact values will differ. The point stands: **the stock baseline would likely miss the orange objects on the real robot.** Re-fit the thresholds on `cam_high` frames from the drops (and Drop 1 when it lands), and keep them working on the sim colours too.

## Other teams seen in the channel
- **The Larp Interns** (Oliver): measuring oracle scores, asking about Dex3 gains and pad friction. They're doing careful real2sim; treat them as strong.
- **yo_mama:** asked how the finals computer connects to the robot.
- **Mr.OREO:** asked about internet on the robot.
