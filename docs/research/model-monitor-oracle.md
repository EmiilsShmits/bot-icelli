# Models that monitor and help the oracle planner

Measured Sat 14 Nov (Emīls + Claude) on saved sim data; no sim run was started for this. The question: after "Decision 1 as chooser" showed no gain (`policy/decision_oracle/README.md`), can a vision/language model **watch** the planner and tell it what happened? Everything under "What to build" is a proposal, **not a team decision**.

## Summary
- **The best monitor is a rule, and it is already in `upgrades.py`.** Closed fingers stall on a held block. From `obs["hand_q"]` alone this told held from empty on **146 of 147** logged picks, 1.5 s after the hand starts closing. The one miss was a block that was carried and then dropped beside the bin.
- **Gemini Decision 1 works as a monitor when it gets two images, before and after.** "Is the block gone from the table?" 31/31; "is it in the hand?" 24/25; "did another block move?" 15/15. With one image it is weak: 19/32 and 20/25. Half-size images keep the accuracy (30/31, 23/25) and halve the latency (0.7 s median).
- **No model predicts a failed pick better than two rules read off the logs.** Triangle + stock claw, or another block within 7 cm: right on 74 of 98 picks (always saying "fine": 50). Decision 1 from the pick's description: 61 of 98; with our measured success rates pasted into the prompt: 69 of 98.
- **New from the logs: crowding.** A pick with another block closer than 7 cm ended in the bin 6 of 25 times; with 10 cm or more of free space 46 of 77.
- **"Never repeat a failed (arm, grasp)" rarely has anything to switch to.** 45 of 56 retries repeated a failed pair, but the planner offered an untried pair in only 6 of those 45. Repeats still worked 10 of 20 times on cylinders and 4 of 8 on cubes; on triangles 1 of 14.
- **A large model reading the logs offline is cheap and was right.** Gemini 4 Hydrogen got the pick table (98 lines) and returned 6 findings in 114 s. All its counts match ours, including the finger signal, the triangle grasp and the repeated retries.
- **Build first:** a Decision 1 before/after check at each look, as a second opinion next to the finger rule (details below). It is the one role where Decision 1 measured well and where the rule has a known gap (dropped beside the bin, real fingers untested).

## Data
- **Picks:** 147 executed picks from 4 logged runs in the venue-look sim (Decision chooser on sort_fixed and sort_language, camera mode on 2 and on 6 seeds). Per pick: the `exec` / `outcome` records of `decisions_*.jsonl` joined with `hand_q` and `hand_q_cmd` per tick from `episode_*.npz`. 69 ended in the bin, 78 did not.
- **Frames:** 113 head RGB-D frames with true poses, captured every 4 s during the Decision sort_fixed run (3 episodes, 15 picks). The episode files hold no images, so these frames are the only pictures. Lined up with the picks through the episode file times; the finger rule and the true poses then agree on every test frame.
- **Test sets cut from the frames:** 25 "hand closed for 1.5 s or more" frames (11 holding a block), 32 "hand open again" frames (11 with the block in its bin), 15 before/after pairs (one per pick), all 113 frames for scene questions (22 with both arms at home, as at a look).
- **Models:** `gemini-decision-1` (Decisions API, yes/no and choice questions), `gemini-robotics-er-2-preview` and `gemini-4-hydrogen` (generateContent with a JSON schema, thinking off). All three exist on our key. The model tests on plan critique use the first 3 runs (98 picks); the fourth run arrived later and is in the rule numbers only.
- **Where:** `artifacts/monitor/` in the main checkout (git-ignored): `sim_frames/`, `sim_runs/`, `probe_results.json` (every model answer), `probe_report.txt`.

## Results per role
"Rule" is the cheap alternative that needs no model. Counts are right answers out of test items.

| Role | Test | Rule | Decision 1 | Robotics-ER 2 | Hydrogen | Worth a model? |
|---|---|---|---|---|---|---|
| 1. Grasp check: is the block in the hand? | 25 frames, hand closed | finger angles **25/25** (146/147 picks) | 1 image 20/25; **before + now 24/25** | 21/25; pair 21/25 | 22/25; pair 24/25 | No. The rule is better and instant |
| 2. Placement: did it reach the bin? | 32 frames, hand open again | "held until release" **32/32** (146/147 picks) | 1 image 19/32; **before + after 31/31** | 29/32; pair 31/31 | 28/32; pair 31/31 | **Yes, as a second opinion** (pair only) |
| 2b. Count the blocks in each bin | 113 frames | not built | left 86, center 64, right 110 of 113 | 86 / 64 / 111 | 92 / 64 / 110 of 112 | No. The near wall hides the bin floor |
| 3. What happened to the block? (in bin / same place / pushed / tipped) | 15 before/after pairs | not built (camera.py re-detects) | 11/15 | 12/15 | 12/15 | Marginal |
| 3b. Did another block move or fall? | 15 pairs (3 yes) | not built | **15/15** | 14/15 | 15/15 | **Yes**, same call as role 2 |
| 3c. Choose a different option after a failure | 56 retries in the logs | "never repeat": applicable in 6 of 45 repeats | chose "retry" 48 of 48 times, confidence 0.47–0.58 | not tested | not tested | No. Needs a sim comparison of rules |
| 4. Scene: is a block lying on its side? | 113 frames (65 yes) | camera.py ridge test 93/113; arms at home 20/22 | 72/113 (never a false alarm, misses 41 of 65) | 67/113 (says yes almost always) | **111/113**; arms at home 22/22 | Only Hydrogen, at 3 s |
| 4b. Scene: how many blocks on the table? | 113 frames | camera.py 94/113; arms at home **22/22** | 96/113; arms at home **22/22** | 90/113; 22/22 | 97/112; 21/21 | Usable as a cross-check on `camera.py` |
| 4c. Foreign objects, stacked blocks | none in the data | | | | | Untested |
| 5. Plan critique: will this pick fail? | 98 picks, text only | A or C **74/98**; A or B 66/98; always "fine" 50/98 | 61/98; with our success rates in the prompt 69/98 | 51/96; 67/98 | 68/98; 69/98 | No |
| 5b. Same, with the look image | 17 picks | A or B 13/17 | 12/17 | 6/17 | 11/17 | No |
| 6. Offline: read the logs, propose rule changes | pick table, 98 lines | our own analysis | cannot write text | not tested | 6 of 6 findings correct, 114 s | **Yes**, costs nothing at run time |

Rules for role 5: **A** = triangle (or tipped block) with the stock claw; **B** = this (arm, grasp) already failed on this object; **C** = another object within 7 cm.

### Latency (seconds, one call at a time)
| Model | Text only | 1 image (640 × 480) | 2 images | 2 images, half size |
|---|---|---|---|---|
| Decision 1, from the laptop on venue wifi | 0.33 median, 1.05 worst (196 calls) | 0.54 median, 3.0 at 99 %, **21.4 worst** (325) | 1.63 median, 4.4 worst (71) | 0.75 median, 4.6 worst (56) |
| Decision 1, from the sim machine (chooser runs) | | 0.64 median, 1.27 worst (92) | | |
| Robotics-ER 2 | 0.88 median, 12.1 worst | 1.57 median, 3.9 worst | 2.20 median, 3.6 worst | |
| Hydrogen | 2.59 median, 5.7 worst | 2.95 median, 25.3 worst | 3.30 median, 6.3 worst | |

- With a 2 s timeout, 6 % of Decision 1's one-image calls and 27 % of its full-size two-image calls from the laptop would have fallen back; with half-size pairs 1 of 56. Send half-size images.
- Failures seen in 1,797 calls: 2 dropped connections (Robotics-ER), 1 timeout at 30 s (Hydrogen), none in Decision 1's 663.

## What each role showed

### 1. Grasp check
- **Rule.** Sum of |`hand_q` − commanded angle| over the picking hand. Held: 0.063–0.303 rad during the carry. Empty: 0.008–0.020 rad. Threshold 0.03 rad.
  - 1.0 s after the close starts: 142/147 right (5 picks held the block for a moment and lost it). From 1.5 s on: 146/147.
  - The check in `upgrades.py` (largest single joint error below 0.012 rad = empty) also separates the 98 picks tested, measured 2 s after the close starts: held 0.016 or more, empty 0.0002 or less. The margin on the "held" side is thin (0.016 against 0.012).
  - Failed picks spend 6.3 s each between "close + 2 s" and the next pick: 488 s of the 1,631 s spent picking. That is the time an abort saves.
- **Models.** With one image all three miss real holds (the arm hides the block) and none raises a false alarm. Decision 1 needs the image from before the pick to reach 24/25.
- **Timeout or wrong answer:** irrelevant here, the rule decides.
- **Open:** the threshold is a sim value. The real hand shows a similar gap (`docs/research/real-data-findings.md` §3: 0.36 rad when closed on a block), but Aalto's drops contain no missed grasps to test against.

### 2. Placement check
- **Rule.** "The fingers held something until the release" predicted "in the right bin" on 146/147 picks. No pick put a block in a wrong bin.
  - **The one miss matters:** camera mode took a cylinder for a cube, carried it with a face grasp and released it between the centre and left bins. The fingers said "held", the block ended on the table. Only a camera can catch this.
- **Models.** One image of the bins is not enough: the near wall and the hands hide most of each bin floor (every model got the centre bin count right in only 64 of 113 frames). The before/after question "is the block gone from the table?" avoids looking into the bins and all three models got 31/31.
- **Timeout or wrong answer:** no answer keeps the finger verdict. A wrong "still on the table" costs one extra look; a wrong "gone" leaves a block unsorted, which is what happens today without the check.
- **Not tested:** the dropped-beside-the-bin case itself (no frames from that run) and wrong-bin drops (none happened).

### 3. Failure diagnosis
- **What happened.** 72 of the 78 failed picks never held the block: the fingers closed on nothing (5 held it for a moment, 1 carried it and dropped it beside the bin). The block stays where it was or moves up to 6 cm (median about 1 cm; 21 of 47 moved less than 1 cm). The models separate "in the bin" from "still there" well but confuse "same place" with "pushed" at the 1 cm line: 11–12 of 15.
- **Other blocks disturbed.** Decision 1 15/15. In the frames a triangle pick knocked over the cylinder next to it twice. One of those cylinders was then picked from its side; the other failed twice and stayed on the table.
- **Choosing differently.** Counted on all 147 picks:
  - First attempts end in the bin 50/91, second 14/37, third 3/13.
  - 45 of 56 retries repeated an (arm, grasp) that had failed on that object; 15 of 45 worked (cylinders 10/20, cubes 4/8, triangles 1/14).
  - The look listed an untried (arm, grasp) for the object in only 6 of the 45 repeats. So the plain rule mostly decides between "repeat" and "skip", and skipping would have lost 15 sorted objects.
  - Repeats that failed again cost 358 s of 1,631 s. No episode ended with an untried object, so that time cost no points in these runs.
  - Decision 1 as chooser answered the retry question with "retry" 48 times of 48, at confidence 0.47–0.58. It adds nothing here.
- **What a rule should do instead:** stop repeating on triangles after one failure, keep one repeat for cubes and cylinders. `upgrades.py` already keeps the failure memory; its option search may list more alternatives than the 6 of 45 seen here.

### 4. Scene sanity
- **Tipped blocks.** Geometry (`camera.py`) recognises 47 of 67 tipped objects on these frames, 20/22 frames when the arms are at home. Decision 1 on the whole image never raises a false alarm but misses 41 of 65. Hydrogen is right on 111/113. A tipped block was picked 4 times and never held, so the answer only saves time.
- **Count on the table.** With the arms at home, `camera.py`, Decision 1 and Robotics-ER all count right on 22/22 frames. With an arm in view all drop to about 85 %. Decision 1's count is therefore a usable alarm for "camera.py lost or invented an object", but these frames contain no such case to prove it.
- **Crowding (from positions, no model).** Success by distance to the nearest other object: under 7 cm 6/25, 7–10 cm 17/45, 10 cm or more 46/77. First attempts without the triangle stock claw: 5/13, 13/23, 31/42. Most of the evidence is from the first 3 runs (5/21 against 32/49); the fourth had only 4 crowded picks (1/4 against 14/28).
- **Untested:** objects that are not ours, stacked blocks. The sim runs have neither.

### 5. Plan critique
- Rule A alone flags 29 picks, 26 of them failed. Rule C flags 25, 19 failed. A or C: 101/147 right.
- Zero-shot, Decision 1 calls most picks fine (mean answer 0.74 for picks that worked, 0.59 for picks that failed). Giving it our measured success rates turns it into the rule: 69/98, the same as Hydrogen.
- The image did not help (12/17, rule 13/17), on a small sample.

### 6. Offline help
- Input: one line per pick (shape, arm, grasp, attempt number, finger error, result), 4,300 tokens. Hydrogen with thinking on: 114 s, 31,000 thinking tokens.
- Its 6 findings, all with correct counts: empty grasps show in the finger error (48 of 48); triangle + stock claw fails (18 of 20); retries repeat a failed pair (17 of 26 fail); cubes do better with face grasps (16/21 against 7/16); cylinders do worse with the left arm (11/20 against 12/16); third and fourth attempts rarely work (2 of 9).
- It could not see what the table did not hold: that an untried pair is rarely on offer, and the crowding effect (no positions in that table).

## What to build, in order
All model calls belong in the planning thread. `act()` keeps returning holds or the queued plan, as now.

1. **Decision 1 before/after check at every look** (new; the Decision 1 role that measured well).
   - **What:** one call with two half-size images (the head image when the pick started, the head image now) and two yes/no questions: "is the block gone from the table?" and "did any other block move or fall over?".
   - **Hook:** `UpgradedOraclePolicy._settle_last_pick()` in `upgrades.py`. It already runs at each look in the planning thread, with the arm at home, and decides whether the last pick failed. Keep a reference to `self._rgb` in `_start()` (no copy, no encoding in `act()`); encode and call in the planning thread, started before the option search so the two overlap.
   - **Use of the answer:** "not gone" while the fingers said "held" → record the failure (`_fail(o, "decision")`), which covers the dropped-beside-the-bin case. "Another block moved" → in camera mode drop the prefetched plan and detect again, because the prefetch reuses the previous look's positions.
   - **Timeout:** 2 s; from the sim machine no call took longer than 1.3 s. **Fallback:** no answer or a probability between 0.35 and 0.65 → today's behaviour (finger rule + re-detection). Decision 1's mean answers were 0.84 / 0.18, so the unsure band is rarely hit.
   - **Before trusting it:** log-only for one sim run (answer next to the true outcome), then switch it on.
2. **Offline review after each batch of runs** (no code in the policy). `python monitor_rules.py --table RUN=LOG …` prints the prompt and the pick table; paste both into Hydrogen. The table now has the distance to the nearest other object, so the model can see crowding (it was not in the table Hydrogen read here).
3. **Rules for the chooser, to be compared in sim** (not models): free-standing objects first (`MemoryChooser.choose`, the line that orders objects: add "nearest other object under 7 cm" after the failure count); one repeat for cubes and cylinders, none for triangles. Needs the same seeds as e-004 / e-007.
4. **Save the head image at every look** into the decision log folder (about 30 KB as JPEG). Then every pick has a before image, and roles 2, 3 and 5 can be re-measured on hundreds of picks without `capture.py`.

**Not worth building:** a single-image grasp or placement check with Decision 1; a model as plan critic; counting blocks inside the bins; Decision 1 for tipped blocks (geometry or Hydrogen do it).

## What could not be tested, and the capture it needs
| Question | Why not | Capture needed |
|---|---|---|
| Does the finger threshold hold on the real Dex3? | Aalto's drops have no missed grasps | Real episodes with deliberate misses (hand closing on air next to a block), `hand_q` recorded |
| Does the before/after check catch a block dropped beside the bin or in a wrong bin? | 1 such pick in 147, no frames of it | `capture.py` during a run with a drop offset that misses the bin on purpose, about 20 picks |
| Does choosing a different (arm, grasp) after a failure sort more objects? | Outcomes of choices that were not made are unknown | Sim runs: memory chooser against the default on the same seeds (queued by the decision-oracle session) |
| Does "free-standing objects first" help? | Same | One sim run with that order on seeds 1000–1005 and 2000–2005 |
| Foreign objects, stacked blocks | None in the sim data | Sim frames with a distractor object, or real frames labelled by hand |
| Plan critique with the image | Only 17 picks have a look image | Item 4 above |
| Anything on real images | All frames are venue-look sim | Real head frames with known outcomes |

## How to reproduce
```bash
D=artifacts/monitor            # main checkout; sim_runs copied with scp -p so the episode file times survive
python policy/decision_oracle/monitor_rules.py $D/sim_runs/<run>=$D/sim_runs/decisions_<run>.jsonl …   # rules, numpy only
PYTHONPATH=third_party/aaltonomous-humanoid python policy/decision_oracle/monitor_probe.py \
    --frames $D/sim_frames --run $D/sim_runs/do_decision_sort_fixed_nominal_20261114_133911 \
    --log $D/sim_runs/decisions_decision_sort_fixed_20261114_133911.jsonl --more <RUN=LOG …> \
    --scene $D/sim_code/scene_venue.yaml --env-file .env --out $D/probe_results.json \
    --roles grasp,grasp_pair,place,place_pair,census,sanity,diagnose,critique,critique_exp,critique_img
```
Answers are cached in `probe_results.json`, so a second call only prints the tables. `--scale 0.5` sends half-size images.

## Limits of these numbers
- Sim only, venue look. Sim depth and sim fingers are cleaner than the real ones.
- The frame tests come from one run of 3 episodes and 15 picks; differences of one or two items mean nothing.
- The model tests were run from a laptop on venue wifi; latency from the finals PC is unknown.
- Accuracy here is per frame or per pick. None of it shows yet how many more objects get sorted.
