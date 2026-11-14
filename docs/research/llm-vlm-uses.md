# Where an LLM / VLM could help (any vendor)

Facts come from Aalto's [`RULES_AND_SCORING.md`](../../third_party/aaltonomous-humanoid/aaltonomous/docs/participants/RULES_AND_SCORING.md) and `aaltonomous/interface/tasks.py`. Everything under "Options" is an idea, **not a team decision**. Nemotron-specific notes are in [`nemotron-and-pi0.md`](nemotron-and-pi0.md).

## Facts that matter here

**Rungs:**
- **Rung 1 `sort_fixed`:** the instruction never changes (red → left, yellow → center, blue → right).
- **Rung 2 `sort_language`:** the instruction defines the mapping.
  - Bins are always named by position (`left`, `center`, `right`) and look identical.
  - The training wording comes from 8 templates (`TEMPLATES` in `aaltonomous/interface/tasks.py`).
  - Aalto: "Expect paraphrases you haven't seen."

**Real-robot finals:** 3 episodes.
1. `sort_fixed`
2. `sort_language` with a training template
3. `sort_language` with an **unseen instruction and layout, weighted ×1.5**. This is the highest-weighted episode.

**What the mapping really is:**
- **Today's code:** behind every rung-2 sentence, it's 3 colours → 3 bins, so there are only 6 possible answers.
- **Possible harder finals settings** (Aalto's "Difficulty knobs"; values not announced): colour + shape instructions, negation, and a **distractor object**. See [`aalto-humanoid.md`](aalto-humanoid.md) §5.

**Policy interface:** the instruction arrives once per episode, in `reset(instruction, task, seed)` and in `obs["instruction"]`.

**Constraints:**
- Aalto confirmed to the team on Sat 14 Nov that the finals machine will have internet (their repo docs had said no network). Failed calls get no rerun, so API calls need a timeout and an offline fallback.
- The submission is limited to ≤ 32 GB VRAM and a ≤ 40 GB image, and must answer at ≥ 27 commands/s.

## Options

### 1. Rung-2 instruction parser (offline, inside the image)
1. In `reset()`, a small local LLM reads the instruction once and outputs a target for each object type.
   - **Simple form,** for colour-only instructions: `{"red": "left", "blue": "center", "yellow": "right"}`.
   - **Robust form,** which also covers the harder knobs: 10 slots, one for each of the 9 known types (3 colours × 3 shapes) plus `other`. Each slot is `left`, `center`, `right` or `leave`.
   - `other` means any object that isn't one of the 9 known types, i.e. a distractor. It defaults to `leave`.
   - **Distractor rule:** pick only what the instruction names. Never assume what a distractor looks like (e.g. "black"); a robot tuned to one guess fails on anything else.
2. **Validate:**
   - every slot is filled with an allowed value, and the instruction isn't contradictory
   - if not, fall back to a rule-based parser built from the 8 templates
3. **Canonicalise:** rewrite the mapping into one fixed sentence format before the VLA or classical controller sees it.
   - The VLA then only ever sees one phrasing, so the unseen-wording problem moves to the LLM, which is good at it.

**Why it fits:**
- It targets the ×1.5 episode.
- It works with either a VLA or a classical controller.
- It runs once per episode, so the command rate isn't affected.
- It needs no network, so it also works as the fallback if an online parser fails.

**Size:** a 1–4B model (e.g. Gemma, Qwen, a small Nemotron) should fit next to the VLA within 32 GB and answer in under a second *(general knowledge, verify on the target GPU)*.

**Test cases to cover:**
- the bin named first ("The left bin is for red")
- synonyms ("crimson", "the middle one")
- exclusions ("everything except…")
- different word order
- colour + shape rules, "leave the yellow ones", generic distractor wording ("ignore anything that isn't a block")

**Overnight test (Sat 14 Nov):** the plan is in [`../../training/instruction_parser/EXPERIMENT.md`](../../training/instruction_parser/EXPERIMENT.md); results will go in `RESULTS.md` next to it.

**Distractors on camera:** the parser only decides what *should* be picked. Seeing and skipping distractors is perception work:
- **Classical route:** pick only objects that confidently match a known colour and shape.
- **VLA route:** add **random** distractors (shapes, colours, sizes) to the sim training scenes, so the model learns "pick what's named", not "avoid black".

Generate a few hundred paraphrases and measure accuracy, plus the fallback rate.

**Stackable prize:** a Gemma model would fit **Best Use of Gemma**; see "Prize tracks" below.

**Teacher-student variant:**
1. A large model (Claude or Gemini, development time only) generates thousands of tricky paraphrases with the correct mapping.
2. Fine-tune a **tiny Gemma** on them, so it answers in milliseconds offline in the image.
   - *(general knowledge, verify)* Google released Gemma 3 270M for task-specific fine-tuning. Check Hugging Face for newer versions.
3. Measure accuracy on a held-out set of paraphrases the student never saw.

This is a stronger prize story than prompting a model, with a measurable result.

### 2. Inside the VLA
π0.5 and GR00T are built on a VLM, so a VLA route already uses one. Option 1 makes its language job smaller.

### 3. Development-time helpers (any capable model, network is fine)
- **Demo quality review from episode videos:**
  - label each one success or fail, split it into phases, and flag fumbles and drops
  - drop or trim bad takes, since there are only ~20 real demos per rung
- **Paraphrase generation:** to test option 1 and to train the VLA on varied wording.
- **Failure analysis of sim eval runs:** classify why episodes failed, to guide the next training round.
- **Available credits:** Claude API ($20 per person), Gemini (one form per team; strong on video), Featherless, NVIDIA Build (Nemotron).

## Prize tracks and credits

From [`../challenges/tech/`](../challenges/tech/) and [`apis-and-credits.md`](apis-and-credits.md).

| Track | Prize | What it needs | Fit with option 1 |
|---|---|---|---|
| **Best Use of Gemma** (Google DeepMind) | €1,000 each for the top 3 teams, unranked | "Most innovative and impactful use" of Gemma open models, creative application, strong technical execution. No minimum requirements or write-up form listed | Runs offline **inside the submission**, so it's clearly part of the working solution and visible in the unseen-instruction finals episode |
| Best Use of Gemini API | €4,000 + $1,000 Google Cloud per member / €2,000 / €1,000 | Meaningful, innovative use of the Gemini API, with an explanation of why Gemini matters | An API. With finals internet confirmed it could be the main parser (e.g. the Gemini Decisions API), with Gemma or the rule parser as the offline fallback. Also fits development-time helpers (option 3) |
| Best Use of Nemotron (NVIDIA) | RTX 5080 for 2 teams | Nemotron 3.5 Super VL "in the working solution" plus a write-up | Too big for the image; see [`nemotron-and-pi0.md`](nemotron-and-pi0.md) |

**Credits:**
- **Gemma needs no credits.** It's open weights, downloaded from Hugging Face and run ourselves.
  - Hosted options while developing: Featherless ($50 per person), Modal ($100 per person), Verda (€200 per person), Google AI Studio (free in the browser).
- **Claude API:** $20 per person ($80 for the team).
  - The claim link is in `CLAUDE_CREDITS_URL` in `.env.challenges`.
  - There's no Anthropic prize track, so it's a development tool only (e.g. as the teacher above).
  - The API takes images, not video, so extract frames first.

**Open question:** can one Junction submission enter several tech challenges at once? Ask the organisers before planning around more than one.

## Where it doesn't help
- **Low-level control at 30 Hz.** Large models take seconds per call. The VLA or a classical controller does this.
- **Rung 1.** The instruction is fixed.
- **Checking each placement with a VLM during the episode.** Possible, but it adds time and risk inside the 120 s limit. A stretch idea only.
