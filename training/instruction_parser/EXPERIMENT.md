# Experiment: can a small Gemma parse rung-2 instructions?

**Status:** plan, written 2026-11-14 for an unattended overnight run on **two Verda GPUs**. Results go in `RESULTS.md` next to this file.
**Background:** [`docs/research/llm-vlm-uses.md`](../../docs/research/llm-vlm-uses.md), option 1.

## The question

**Problem:**
- In `sort_language`, the instruction defines where each object goes.
- The real-robot finals include one episode with an **unseen instruction, weighted ×1.5**.
- Aalto's 8 training templates are in `third_party/aaltonomous-humanoid/aaltonomous/interface/tasks.py`. Its docstring says the held-out finals templates are deliberately *not* in that file.
- Aalto's "Difficulty knobs" (`STARTER_PATHS.md`) list possible harder finals settings, with finals values "not announced":
  - **instructions** with "colour + shape, negation, held-out paraphrases"
  - **layouts** with a **"distractor object"**

**Idea:** a small Gemma runs offline inside our policy image. It reads the instruction once in `reset()` and outputs, for every object type, which bin it goes in or whether to leave it.

**We want to know:**
1. Does a small Gemma parse **unseen instructions** more accurately than a rule-based parser? Check both:
   - colour-only paraphrases
   - the harder kinds: shape, negation, distractors
2. Which size and method is best: prompted, scored, or fine-tuned (teacher → student)?
3. How often is it **confidently wrong**: a valid-looking answer that's incorrect? That's the dangerous case, because a validity check can't catch it.
4. Does it keep **unknown objects** (distractors) on the table unless the instruction says otherwise?
5. Does it fit the submission?
   - load time well inside the 120 s server start-up
   - small VRAM next to a VLA (≤ 32 GB total)
   - latency under 1 s
   - weights size within the 40 GB image limit
6. Is it Gemma specifically, or would any small LLM do? Compare against one non-Gemma model of similar size.

## Facts from Aalto's code (don't change these)
- Colours: `red`, `yellow`, `blue`. Shapes: `cube`, `cylinder`, `triangle` (`SHAPES` in `tasks.py`). That's **9 known object types**.
- Bins: `left`, `center`, `right`, named only by position.
- Today's code generates colour-only instructions where each colour gets a different bin (a permutation), and no distractors.
- The rung-1 instruction is fixed: red → left, yellow → center, blue → right.

## Output format (the parser's answer)
**10 slots:** the 9 known types plus `other`. Each slot gets one of `left`, `center`, `right` or `leave`:

```json
{"red cube": "left", "red cylinder": "left", "red triangle": "left",
 "yellow cube": "center", "...": "...",
 "other": "leave"}
```

**How the slots are filled:**
- A colour-only instruction gives all three shapes of that colour the same bin.
- `other` means **any object that isn't one of the 9 known types**, i.e. a distractor, whatever its colour or shape.
  - It defaults to `leave` unless the instruction explicitly says otherwise.
  - **Never assume a specific distractor colour or shape** (e.g. "black"). The robust rule is "pick only what the instruction names".
- If the instruction is contradictory, unrelated or impossible to follow, the parser returns **`invalid`**, so the policy can use a fallback.

**Assumption to confirm with Aalto:** a known colour on an unknown shape (e.g. a red star) counts as `other`, not as "a red object". Record it in `RESULTS.md` as an open question.

## Ground rules
- **Work only in `training/instruction_parser/`**, plus the doc updates listed in Phase 5.
  - Don't edit `third_party/`, `policy/` or anything else.
  - Other sessions share this checkout, so **don't commit, switch branches or push**. Leave everything uncommitted for a human to review.
- **Secrets:** read keys from `.env` without printing them. Never write tokens into repo files or logs.
  - On the Verda machines, pass `HF_TOKEN` as an environment variable on the command line rather than saving it.
  - `HF_TOKEN` is in `.env`. Gemma 3 access (270M / 1B / 4B / 27B) was checked on 2026-11-14 and works.
- **New Python packages:** list them in `training/instruction_parser/requirements.txt`.
- **Weights and big data:** keep them on the machines or in `artifacts/instruction_parser/` (git-ignored). Small test sets (JSONL, under 1 MB) may live in the folder.
- **Cost:** follow the limits in the prompt that started this run. **The only safe end state is every experiment instance deleted.**

## Phase 0: local, free, before creating any machine
1. **Write a small rule interpreter.** It turns a structured spec (a list of rules) into the 10-slot answer. Phase 3 uses it to label generated data, so the labels are correct by construction.
2. **Write the test sets first and freeze them.** Save them as JSONL and record a SHA-256 of each file in `RESULTS.md`. Never use them for training or as few-shot examples.
   - **T1, in-distribution:** every one of Aalto's 8 templates × all 6 bin permutations × all 6 colour orders (288 items), labelled in the 10-slot format.
   - **T2a, unseen colour-only paraphrases (headline test 1):** at least 300, written by hand, as varied as a human organiser might phrase them.
     - The 6 colour → bin permutations should appear roughly equally often. Each item is tagged with a category.
     - Keep word-for-word overlap with the 8 templates low, and report the overlap.
     - Categories:
       - bin named first ("The left bin is for red…")
       - synonyms for bins: middle, centre, central, leftmost, rightmost, "the one in the middle"
       - colour variants: Red, RED, reddish, "the red ones", "anything red", "red-coloured items"
       - passive voice ("red objects should be placed…")
       - terse ("red→left, yellow→middle, blue→right"; "red left / blue right / yellow centre")
       - by elimination ("red left, blue right, yellow goes in the remaining bin"; "…the rest in the middle")
       - split across several sentences, with filler or politeness ("Hi robot, please…")
       - all lower case, no punctuation, typos ("yelow", "centre bin")
       - reordered clauses, and colours mentioned in a different order than the bins
       - long and chatty versus very short
     - **Separate small category (about 20 items, reported on its own):** real-object colour names.
       - The team saw orange / yellow / purple objects on the real table, while Aalto's docs say red / yellow / blue (`docs/PROGRESS.md`).
       - Label "orange" as red and "purple" as blue, and record this as an assumption that's unconfirmed with Aalto.
   - **T2b, harder unseen instructions (headline test 2):** at least 200, written by hand, each tagged with a category.
     - **colour + shape:** "red cubes go left, red cylinders in the middle, everything else blue goes right…"; also shape-only rules ("all triangles to the right bin").
     - **negation and exclusion:** "everything except blue goes in the left bin", "don't put anything red in the center bin", "no cylinders on the right".
     - **leave on the table:** "leave the yellow ones where they are", "don't touch the triangles".
     - **generic distractors:**
       - Examples: "ignore anything that isn't one of the blocks", "leave unfamiliar objects alone", "only sort the red, yellow and blue pieces".
       - **Never a specific distractor colour as the only cue.**
       - Include instructions that don't mention distractors at all, where `other` must still come out as `leave`.
     - **mixed:** these combined with the T2a styles (terse, typos, chatty).
     - Every item must define all 10 slots unambiguously; drop it if you're unsure of the right answer.
   - **T3, invalid:** about 60 items where the right answer is `invalid`.
     - contradictions ("red goes left. Red goes right.")
     - bins that don't exist ("the top bin", "the green bin")
     - unrelated text, an empty string
     - instructions that leave the destination of a known colour undefined, with no rule that covers it
     - These test the fallback logic and aren't part of accuracy.
3. **Write a rule-based parser** that's as good as we can make it in about an hour (regex or keyword proximity, with basic shape and "except" handling).
   - It returns the 10 slots or `invalid`.
   - Don't tune it on T2a or T2b. Tune it on T1 and your own scratch examples.
4. **Write the evaluation harness:** `eval.py <method> <testset>` writes per-item predictions plus a summary.
   - **Exact accuracy:** all 10 slots correct.
   - **Per-slot accuracy.**
   - **Invalid rate.**
   - **Confidently-wrong rate:** a valid answer with at least one wrong slot.
   - **Distractor safety:** the share of items where `other` is correct. When the instruction says nothing about distractors, `other` must be `leave`.
   - **Refusal rate on T3.**
   - **Per-category accuracy.**
   - **Latency:** p50 / p95, warm.
5. Run the rule parser on all test sets locally. **Only then create the Verda machines.**

## Phase 1: two Verda machines
- **API:** base `https://api.verda.com/v1`. Get a token with `POST /oauth2/token` (client_credentials) using `VERDA_CLIENT_ID` / `VERDA_CLIENT_SECRET` from `.env`.
  - Useful endpoints: `/balance`, `/instance-availability`, `/instance-types`, `/images`, `/ssh-keys`, `/instances`, `/volumes`.
  - **Working curl examples** (token, SSH key, create instance) are in `docs/runbooks/verda-sim-setup.md` §1. The full schema is at `$API/openapi.json`; look up the instance delete action there.
  - If `api.verda.com` fails, use Verda's old name `https://api.datacrunch.io/v1`: same credentials, same endpoints. That was needed on Sat 14 Nov.
  - A 503 response means no capacity.
- **Record the balance** before creating anything.
- **SSH key:** generate a new ed25519 key at `~/.ssh/verda_bot_icelli` (no passphrase; it only protects temporary machines) and register it with `POST /ssh-keys`. Reuse it if it already exists.
- **Create two on-demand instances:**
  - Hostnames: `gemma-parser-exp-1` and `gemma-parser-exp-2`.
  - **Types:** this test is text only, so it doesn't need an RTX card for rendering. At 03:30 Sat the RTX 6000 Ada was sold out.
    - **exp-1:** `1RTXPRO6000.30V` (96 GB, Blackwell, the same generation as the finals RTX 5090, so the speed numbers are closer to the finals). Only FIN-03 had it.
    - **exp-2:** `1A100.22V` (80 GB; 27B fits in bf16; good for fine-tuning). All FIN locations had it.
    - If either is unavailable, use any GPU with ≥ 40 GB that keeps within the prompt's limits.
    - Verda's API listed them at $2.808/h and $2.374/h. The running sim machine bills at about 0.9× its list price, so roughly €4.7/h for both.
  - Image: Ubuntu 24.04 + CUDA (e.g. `24.04.cuda13.0.docker`). Check that the image is offered for each type.
  - Disk: about 150 GB, since the 27B weights alone are ~55 GB.
  - **Never touch any other instance on the account.** `bot-icelli-sim` is the team's sim machine.
- **Backstop:** on each machine, run `sudo shutdown -h +<minutes until the hard deadline>`.
  - It's not certain that a shut-down Verda instance stops billing, so this doesn't replace deleting it.
- **Software:** set up a Python venv on each machine, install `torch`, `transformers`, `accelerate`, `peft`, `trl`, `datasets` and `bitsandbytes`, and copy `training/instruction_parser/` across.
- Run long jobs in `tmux` or with `nohup`, and keep the logs.
- **Split the work so both GPUs are busy:**
  - **exp-1 (RTX PRO 6000):** Phase 2 (prompted models), then Phase 4 (fit checks).
  - **exp-2 (A100):** Phase 3 (teacher data, then fine-tuning). It starts as soon as the machine is up.
- **Memory note:** Gemma 27B in bf16 (~55 GB) fits both cards, but **not** a 48 GB card. If you end up on a smaller GPU, run 27B in 8-bit (~28 GB) or use Gemma 12B, and record which one you used.

## Phase 2 (exp-1): prompted models, no training
**Models** (check Hugging Face for the newest Gemma generation and use it if it's newer than Gemma 3):
- **Gemma, small, instruction-tuned:** about 270M, 1B and 4B (the in-image candidates).
- **Gemma, large:** 27B, as an upper bound.
- **One ungated non-Gemma small model** of similar size, e.g. Qwen 0.5B–3B instruct, as a comparison.
- If a Gemma download fails, record it as a blocker and continue with the rest. **Don't use a mirror to get around the gate.**

**Three ways to get the answer out**, run for each model:
- **A. JSON:** the prompt asks for the 10-slot JSON with greedy decoding, then a validity check.
- **B. Fixed order:** the prompt asks for the 10 answers in a fixed slot order, e.g. `left left left center center center right right right leave`.
- **C. Scoring:** for each slot, compute the model's log-likelihood of each of the 4 options and pick the best.
  - The result is always valid. The smallest top-1 vs top-2 gap across the slots is a confidence value.
  - Report how accuracy changes as the confidence threshold rises, with low-confidence answers going to the fallback.

Use a short system prompt with at most 3 few-shot examples. Take them from T1-style templates, never from T2a, T2b or T3. Record the exact prompts.

## Phase 3 (exp-2): teacher → student fine-tune
1. **Training data, labelled by construction:**
   - **(a) Programmatic:**
     - Sample random structured specs: colour-only permutations, colour + shape, exclusions, "leave" rules, distractor clauses.
     - Write them out with a larger grammar of templates and synonyms written by you, without copying T2 sentences.
     - Label them with the rule interpreter.
   - **(b) Teacher paraphrases:** the large Gemma rewrites instructions *given the spec*.
     - Keep only paraphrases that a second pass parses back to the same 10 slots (round-trip filter).
     - Aim for about 10–30k examples in total, with roughly 40% colour-only and 60% harder kinds.
     - Report n-gram overlap with T2a and T2b, and remove near-duplicates.
2. **Fine-tune** the smallest Gemma (about 270M) to output the fixed-order answer (format B), using full fine-tuning or LoRA. Then fine-tune 1B if time allows.
3. **Evaluate** on T1, T2a, T2b and T3. T2a and T2b are the honest tests of generalisation.

## Phase 4 (exp-1, after Phase 2): does it fit the submission?
For the best one or two candidates, including the fine-tuned student when it's ready, measure:
- load time from disk to first answer
- peak VRAM
- weights size on disk
- warm latency p50 / p95 on the GPU
- warm latency p50 / p95 on **CPU only**, so we know if it can stay off the GPU and leave it to the VLA

Note: the finals GPU is an RTX 5090 (32 GB), so latency here is an approximation.

## Phase 5: wrap up (always runs, even after errors)
1. **Copy results back** into `training/instruction_parser/results/`: predictions, summaries, logs and exact prompts.
   - Copy a fine-tuned checkpoint under 2 GB to `artifacts/instruction_parser/`.
2. **Delete both `gemma-parser-exp-*` instances** and their OS volumes through the API. Leave `bot-icelli-sim` and any other instance alone.
3. **Confirm deletion:** `GET /instances` shows no `gemma-parser-exp-*`, and `GET /volumes` has nothing left over from this run.
4. **Record** the balance after deletion and the total spend.
5. **Write `RESULTS.md`**, starting with a summary of at most 6 lines for someone who just woke up:
   - **Verdict:** viable / not viable / unclear, and the recommended model + method.
   - **Headline numbers:** on T2a and on T2b, the exact accuracy and confidently-wrong rate for the best Gemma vs the rule parser vs the non-Gemma model. Also distractor safety, T3 refusal rate, and latency, VRAM, load time and size.
   - **Cost:** balance before → after; both instances deleted (yes/no).
   - Then:
     - the full results table (method × test set)
     - per-category accuracy on T2a and T2b
     - 10 worst failures with the model's output
     - open questions for Aalto (the red-star assumption, how distractors are scored)
     - what we'd do next
6. **Update the docs:**
   - Add `README.md` to this folder with the standard sections: Purpose, Owner (Emīls + Tiya), Inputs → Outputs, How to run, Status, Gotchas.
   - Add a row to `training/MODELS.md` for any fine-tuned checkpoint.
   - Add one line to `docs/PROGRESS.md`.

**Suggested "viable" bar** (a proposal, not a team decision):
- **T2a:** exact accuracy ≥ 98%, confidently wrong ≤ 1%, and clearly better than the rule parser.
- **T2b:** exact accuracy ≥ 90%; distractor safety ≥ 99%.
- **T3:** refusal ≥ 90%.
- **Fit:** latency < 1 s, VRAM ≤ 4 GB, load time ≤ 30 s.

## Not in scope
- Wiring the parser into `policy/`. Where it plugs in is a team decision.
- Seeing distractors on camera, and adding distractors to the sim. That's perception and sim-team work; this test is text only.
- The VLA, the sim, or `bot-icelli-sim`.
