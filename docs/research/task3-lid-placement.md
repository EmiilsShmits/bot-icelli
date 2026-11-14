# Task 3 (`insert_shapes`): where the lid box should go

Written Sun 15 Nov ~00:15 by Samer + Claude. Aalto (Sat evening, to Samer): no other team has tried task 3; they will
move the boxes for task 3 to where we ask. Our test had found the lid "not fully reachable".

**Task (Aalto's `RULES_AND_SCORING.md`):** "Put each object through the hole of the same shape in the lid." +3 through
the matching hole, −1 forced/jammed on the lid or dropped beside it. Default lid: on the **left** bin, centre
(0.505, +0.26) in the pelvis frame.

**The lid** (`lid_shape_holes_200mm.stl`, from Aalto via Samer): 200 × 200 mm, 4 mm plate, 12 mm rim. Three 60 mm
openings for the 45 mm blocks (7.5 mm clearance each side), centres in the lid's own frame (mm, from its centre):
square (−48, −35), circle (+48, −35), triangle (0, +39).

## Finding (`eval/analysis/reach_task3.py`, Aalto's own IK)
Top-down IK of the grasp point (= block centre) at release heights 0.12 / 0.14 / 0.16 m (pelvis frame; the lid top is at
~0.07–0.09 m), palm down within 25°, 6 mm tolerance, 2 cm grid, each arm.

- **Default placement: at least one hole is out of reach in every lid orientation.** The arm reaches ~0.50 m forward at
  that height; the default lid's far holes sit at x = 0.54–0.55 m.
- **With blocks anywhere in the usual band, no placement works:** a lid box near enough to reach is also within 7.5 cm
  of some block, and the hand (fingertips 5–7 cm from the block centre when closing) would hit the box.
- **With the blocks in the right half of the band, this works:**

| | Value |
|---|---|
| Lid box centre | pelvis (0.39, +0.15): 39 cm in front of the pelvis, 15 cm to the robot's **left**. Mat frame: x 0.60, y 0.25 |
| Box spans | pelvis x 0.285–0.495, y +0.045 – +0.255 |
| Lid orientation | **triangle hole nearest the robot**; square and circle in the back row, **square on the right** (towards the robot's centre line), circle on the left |
| Hole centres | triangle (0.351, +0.150), square (0.425, +0.102), circle (0.425, +0.198) |
| Blocks | right half of the usual band: x 0.26–0.33, **y −0.17 to −0.03** (mat x 0.28–0.42, y 0.12–0.19), ≥ 8 cm apart (3 blocks fit) |
| Other bins | centre and left bins **removed** (they overlap the lid box); the right bin may stay |

Evidence for that placement:
- **Reach:** every hole ≥ 8 cm inside the left arm's reach at all three release heights. The right arm also reaches the
  square and the triangle.
- **Wrist turn over each hole (left arm):** square −75…+75°, circle −60…+90°, triangle −90…+75°. The square repeats
  every 90° and the triangle every 120°, so any grasp can be lined up with its hole.
- **Camera:** all three holes are ≥ 90 px inside the head camera's image, with the calibration pose and with the
  ~10° further-down pose seen in Aalto's real footage, so the policy can check the lid's position from depth.
- The lid turned 90° (square near, circle far, both on the inner side; triangle outside) works almost as well.

**Not checked:** collisions of the hand with the box walls or rim while lowering. Above the lid the hand comes from
straight above, and the release height leaves ≥ 3 cm under the block. Nothing has been inserted in a sim yet: Aalto's
sim has no lid or `insert_shapes` scorer.

## Message for Aalto (Samer)
> Task 3 placement request from bot-icelli. From the default left bin, at least one hole is out of the G1's reach in any
> lid orientation (the arm reaches ~50 cm forward at that height). Could you set it up like this for task 3:
> 1. Lid box centre 39 cm in front of the robot's pelvis and 15 cm to its left. On the printed mat that is x = 60 cm
>    from the mat's corner on the robot's right (along the near edge), y = 25 cm in from the near edge.
> 2. Lid turned so the triangle hole is closest to the robot; the square and circle holes in the back row, square on
>    the right (towards the robot's middle), circle on the left.
> 3. Blocks in the right half of the usual area: 26–33 cm in front of the pelvis, 3–17 cm to the robot's right
>    (mat x 28–42 cm, y 12–19 cm), at least 8 cm apart.
> 4. The centre and left bins taken away (they would overlap the lid box); the right bin can stay.
> There every hole is at least 8 cm inside the arm's reach, the wrist can turn ±75° over each hole to line up the
> square and the triangle, and all three holes are in the head camera's view.

## Reproduce
`docker run --rm -v $PWD/eval/analysis/reach_task3.py:/r.py -v /tmp/out:/out bot-icelli/policy:v1.4 python3 /r.py /out/reach_task3.json`
(~5 min on `samer-v1-sim`; any image with Aalto's classical package and Pinocchio works).
