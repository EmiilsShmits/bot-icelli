# What Aalto's drop 3 says about the real Dex3 hand (grasp check, tactile)

Written Sun 15 Nov ~00:35 by Samer + Claude. Data: Hugging Face `zupermiez/g1_junction_drop_3` (published Sat 14 Nov
22:07 UTC): 15 teleoperated episodes, 4,823 frames at 30 Hz. Besides joint states (`observation.state`, 28), commands
(`action`, 28) and the three cameras, it has **head depth** (`observation.images.head_depth`: HEVC video, `gray12le`,
millimetres) and **tactile** (`observation.tactile`: 216 = 2 hands × 9 pads × 12 points, raw counts, idle ≈ 30,000).
Note: the hand joint order differs between hands in this data (left: thumb 0–2, middle 0–1, index 0–1; right:
thumb 0–2, index 0–1, middle 0–1).

## Finding: the finger-angle grasp check doesn't transfer to the real hand
All our grasp checks decide "hand empty vs holding" from how far the fingers lag their command after closing:
- v1.4 at 0.006 rad;
- Marcus's agent at 0.010 rad (Gemini decides a band around it);
- v1.5/v1.6 from the finger angles at the end of the lift.

In sim an empty hand reads 0.0001–0.0036 rad and a held block 0.0117–0.0752 (e-028). On the real hand, at moments
when the command has been steady for ⅓ s and the tactile pads read nothing:

| Hand | Finger error p10 / p50 / p90 (rad) | Notes |
|---|---|---|
| left | 0.037 / 0.046 / 0.069 | |
| right | 0.039 / 0.086 / 0.202 | episodes 0–5, right hand closed fully on nothing: 0.12–0.26 |

So **with nothing in the hand the real fingers already lag by more than every threshold we use**. On the real robot
these checks will always report "holding":
- **Harmless:** no false aborts. It behaves like v1.3, with no check.
- **The loss:** no recovery after a real miss.

A real threshold can't be read off this data: the teleoperator closes to a fist, not to our `closed` posture, and the
empty-hand error alone already reaches 0.26 rad, which overlaps any plausible "holding" value.

## Tactile would settle it, but the policy can't see it
- Contact is unmistakable in the pads: the left-hand grasps in episodes 10–11 reach 9,000–22,000 counts above idle,
  while with no contact the hand stays at or below ~4,600 (mostly pad s3, then s1/s5).
- **But Aalto's interface does not put tactile in `obs`**: their docs say "Not in obs. Only joint positions
  (`hand_q`) tell you what the fingers did." (`docs/participants/FAQ.md`, `INTERFACE.md`).

**Ask Aalto:** could the finals pass `observation.tactile` (the 216 values) in `obs`? Then a tactile grasp check is a
few lines: holding = active hand's pads > ~6,000 counts above idle after the lift.

## Also in drop 3: real head depth
Real depth makes the hand-position check possible on real frames. `policy/policies/look.py` `hand_check()` compares
the measured depth at the projected hand points, so it can tell a tilted camera from a leaning torso or an arm offset.
Forwarded to the hand-offset analysis (side session), which writes `docs/research/hand-offset-real-data.md`.
