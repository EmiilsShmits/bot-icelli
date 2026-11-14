# data/: datasets

**Purpose:** _to be agreed._
**Owner:** _TBD_

## Inputs → Outputs
- **In:** _to be agreed._
- **Out:** _to be agreed._

## How to run
- **Health report for a real-data drop** (speed-cap violations, spikes, how much to slow it down, grip signal):
  ```bash
  pip install -r data/requirements.txt
  python data/tools/drop_health.py zupermiez/g1_junction_drop_2    # downloads the joint data (~5 MB) to artifacts/drops/
  ```
  Findings so far: [`../docs/research/real-data-findings.md`](../docs/research/real-data-findings.md).

## Status
- **Now:** `tools/drop_health.py` checks Aalto's drops. Both drops so far break the speed caps (retime before training) and have no success labels.
- **Next:** —
- **Blockers:** —

## Facts about Aalto's real-robot data
- **Release schedule:** published on Hugging Face during the event, with links on the Junction Discord.
  - **Drop 0** (Fri evening): teleop demos
  - **Drop 1** (Sat): venue lighting, empty-scene RGB-D, real depth noise
- **Format:** LeRobot v3.0 (with head depth), plus a GR00T copy (LeRobot v2.1, RGB only).
  - `observation.state` = 28 (arm_q 14 + hand_q 14)
  - `action` = 28 commanded absolute targets at 30 Hz
  - 3 RGB cameras + head depth
  - `task` = the instruction
- **Raw:** successful, failed and messy episodes together. Labels, notes and warnings are in `meta/aalto_episodes.jsonl`.
- **Public G1 Dex3 datasets:** listed in `docs/research/aalto-humanoid.md` §8. No public colour-sorting set exists.
- **Format details:** `third_party/aaltonomous-humanoid/aaltonomous/data/DATA_CARD.md`.
