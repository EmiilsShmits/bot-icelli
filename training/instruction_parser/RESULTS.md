# Results: can a small Gemma parse rung-2 instructions?

**Verdict: promising, not yet "viable" by the proposed bar.** A *fine-tuned* small Gemma clearly beats the rule parser on unseen instructions. No in-image candidate reaches T2a ≥ 98% or T3 refusal ≥ 90%. **Recommended:** Gemma 3 1B fine-tuned on our teacher + programmatic data (format B, fixed order); it fits easily. Gemma 4 E2B + LoRA is the most accurate, if ~10 GB of VRAM next to the VLA is acceptable.

**T2a (339 unseen colour-only paraphrases), exact / confidently wrong:** 1B student **94.7% / 0.9%** · E2B-LoRA student 93.5% / 1.5% · rule parser 86.7% / 3.2% · non-Gemma Qwen2.5-1.5B (prompted, best format) 77.6% / 22.4%. Without the 21 orange/purple items: 1B student 96.9% / 0.3%.

**T2b (213 harder unseen instructions):** E2B-LoRA **96.7% / 2.3%** · 1B student **90.6% / 8.0%** · rule 60.1% / 6.6% · Qwen 54.9% / 36.6%. Distractor safety: E2B-LoRA 99.1%, 1B 97.7%, rule 65.7%. T3 refusal: E2B-LoRA 75%, 1B 58%, rule 82%.

**Fit (1B student, RTX PRO 6000):** 0.14 s p50 on GPU, 1.6 s on 8 CPU threads, 2.0 GB VRAM, 9.5 s from cold disk to first answer, 2.0 GB of weights. E2B-LoRA (A100): 0.56 s, 10.2 GB VRAM, 45 s cold load, 10.2 GB.

**Cost:** Verda balance €197.86 → €189.54 at 05:51 (**€8.32**). It read €189.01 right after the deletions and then rose; Verda seems to refund unused prepaid time. Both `gemma-parser-exp-*` instances and their OS volumes were deleted at 05:38 / 05:47 (lifetimes 1 h 38 min / 1 h 47 min). Confirmed with `GET /instances` (0 instances) and `GET /volumes` (no `gemma-parser-exp-*` left; trash empty).

---

Run: Sat 14 Nov 2026, 03:50–05:50 EET, unattended. Plan: [`EXPERIMENT.md`](EXPERIMENT.md). Everything here is uncommitted, for a human to review.

## What ran
| Machine | GPU | Did |
|---|---|---|
| laptop | – | Phase 0: rule interpreter, test sets (two helper agents wrote T2a / T2b / T3 by hand, blind to the parsers), rule parser, eval harness, programmatic training data |
| `gemma-parser-exp-1` (`1RTXPRO6000.30V`, FIN-03, €2.53/h) | RTX PRO 6000 Blackwell 96 GB | Phase 2: 6 prompted models × formats A/B/C, plus Gemma 4 12B (A/C, added). Phase 4: fit checks |
| `gemma-parser-exp-2` (`1A100.22V`, FIN-01, €2.14/h) | A100 80 GB | Phase 3: teacher paraphrases (Gemma 4 31B), fine-tuning of three students, their eval, fit checks for E2B-LoRA |

- **Models:** Gemma 4 exists (E2B, E4B, 12B, 26B-A4B, 31B, released Mar–Jun 2026), so it is used where it has a size:
  - Gemma 3 270M-it and 1B-it, because Gemma 4 has nothing that small
  - Gemma 4 E2B-it and E4B-it
  - Gemma 4 12B-it (extra mid point)
  - Gemma 4 31B-it as the upper bound, in bf16 (fits the 96 GB card)
  - **Non-Gemma:** Qwen2.5-1.5B-Instruct
  - All downloads worked; no gate problems.
- **Software:** torch 2.11 + cu128, transformers 5.23, driver 580.178.04, image `24.04.cuda13.0`. Exact prompts are in [`results/prompts.txt`](results/prompts.txt) (3 few-shot examples, T1-style only).
- **Training data:** 23,089 examples, in `artifacts/instruction_parser/data_train/train.jsonl`.
  - **Programmatic:** 16,000 from `gen_train.py`, ~41% colour-only, 7% invalid.
  - **Aalto templates:** 1,200 examples rendered from the 8 training templates (added after the programmatic-only student rejected one template style; see below). This makes T1 in-distribution for the students, as its name says.
  - **Teacher:** 5,889 paraphrases from Gemma 4 31B. 1,500 seeds × 5 gave 7,500 candidates; 6,108 (81%) survived the round-trip parse and 5,889 remained after near-duplicate removal against T2.
  - **Overlap with T2a + T2b:** max trigram Jaccard per training example, mean 0.10 for programmatic and 0.14 for teacher data; 18 teacher items removed at > 0.6 (`results/overlap_prog.txt`, `results/logs/exp-2/phase3.log`).
- **Students** (prompt `prompts.FT_PREFIX`, answer format B):

| Student | Method |
|---|---|
| `s270m-prog` | Gemma 3 270M, full FT, programmatic data only (ablation) |
| `s270m-full` | Gemma 3 270M, full FT, 3 epochs, lr 1e-4 |
| `s1b-full` | Gemma 3 1B, full FT, 2 epochs, lr 3e-5 |
| `sE2B-lora` | Gemma 4 E2B, LoRA r=32 on language-model projections, 1 epoch, lr 2e-4, merged |

## Test sets (frozen; SHA-256 in [`results/testset_hashes.txt`](results/testset_hashes.txt))
| Set | Items | sha256 (first 16) | Notes |
|---|---|---|---|
| T1 | 288 | `31c3186d047c98b3` | 8 Aalto templates × 6 bin perms × 6 colour orders |
| T2a | 339 | `421d678b8b120077` | 318 main items in 10 categories, 48–55 per colour→bin permutation, plus 21 `real_colour_names` (orange = red, purple = blue) |
| T2b | 213 | `34c91941c1046c70` | colour_shape, shape_only, negation, leave, distractor_generic (9 send `other` to a bin), distractor_silent, mixed; 29–31 each |
| T3 | 60 | `e8b57f4d432de940` | contradiction, nonexistent_bin, unrelated, undefined; 15 each |

- **Overlap with Aalto's templates** (trigram containment after masking colour/bin words): T2a mean 14.7%, 1.8% of items over 50%; T2b mean 12.0% (`results/template_overlap.txt`).
- **Hand-written sources:** `data/*.src.jsonl` and `data/make_*.py`.

## Headline results (selected; full table in [`results/tables.md`](results/tables.md))
Exact = all 10 slots right. CW = confidently wrong (a valid answer with ≥ 1 wrong slot). DS = distractor safety (`other` correct). Latency is warm, batch 1, from the eval run (students on the A100, prompted models on the RTX PRO 6000); see the fit table for like-for-like numbers.

| Method | T1 | T2a exact | T2a CW | T2b exact | T2b CW | T2b DS | T3 refusal | VRAM GB |
|---|---|---|---|---|---|---|---|---|
| rule parser | 100 | 86.7 | 3.2 | 60.1 | 6.6 | 65.7 | 81.7 | – |
| **student Gemma 3 1B (FT)** | 100 | **94.7** | **0.9** | 90.6 | 8.0 | 97.7 | 58.3 | 2.0 |
| student Gemma 3 270M (FT) | 100 | 91.7 | 3.2 | 82.2 | 14.1 | 94.8 | 53.3 | 0.55 |
| student Gemma 3 270M, programmatic data only | 86.8 | 83.5 | 6.5 | 55.9 | 41.8 | 96.2 | 56.7 | 0.55 |
| **student Gemma 4 E2B (LoRA)** | 100 | 93.5 | 1.5 | **96.7** | **2.3** | **99.1** | 75.0 | 10.2 |
| Gemma 4 E2B prompted, A (JSON) | 100 | 89.1 | 10.3 | 78.9 | 21.1 | 84.5 | 25.0 | 10.3 |
| Gemma 4 E4B prompted, C (scoring) | 100 | 91.2 | 8.8 | 80.3 | 19.7 | 84.0 | 0 (C can't refuse) | 16.0 |
| Gemma 4 12B prompted, C | 100 | 93.8 | 6.2 | 94.8 | 5.2 | 94.8 | 0 | 28.6 |
| Gemma 4 31B prompted, A (upper bound) | 100 | 87.9 | 0.6 | 96.2 | 1.9 | 96.2 | **100** | 74 |
| Gemma 4 31B prompted, C (upper bound) | 100 | 92.9 | 7.1 | **98.1** | 1.9 | 98.1 | 0 | 74 |
| Gemma 3 1B prompted, best (A) | 11.5 | 17.1 | 67.3 | 4.7 | 81.2 | 81.2 | 40.0 | 3.7 |
| Gemma 3 270M prompted, best (B) | 16.7 | 16.5 | 83.5 | 1.9 | 98.1 | 95.8 | 10.0 | 1.1 |
| Qwen2.5-1.5B prompted, A | 96.5 | 73.2 | 15.9 | 54.9 | 36.6 | 87.3 | 46.7 | 5.1 |
| Qwen2.5-1.5B prompted, C | 92.7 | 77.6 | 22.4 | 48.8 | 51.2 | 97.2 | 0 | 5.0 |

**Answers to the plan's questions:**
1. **Better than rules on unseen instructions?** Yes, once fine-tuned:
   - T2a: +8 points (1B) with a third of the rule parser's confidently-wrong rate.
   - T2b: +30 to +37 points.
   - Prompted small Gemmas (270M / 1B) are useless (≤ 17% exact). Prompted Gemma 4 E2B/E4B are near the rule parser on T2a and well above it on T2b, but are confidently wrong 9–21% of the time.
2. **Best size and method:**
   - **Fine-tuning (teacher → student) beats prompting at every size.** The teacher data matters: the programmatic-only 270M student scores 55.9% on T2b vs 82.2% with the teacher paraphrases.
   - Among prompted formats, B (fixed order) is the worst for small models: they lose track of the slot order. A (JSON) and C (scoring) are much better. B works well once fine-tuned.
3. **Confidently wrong:**
   - Low for the 1B student on T2a (0.9%), higher on T2b (8.0%).
   - The E2B-LoRA student is at 1.5% / 2.3%.
   - Prompted models are mostly 5–20%. The rule parser is 3–7%, but only because it refuses a lot.
   - A rule-parser veto drives it to ≤ 1% at a big coverage cost (see "Hybrids").
4. **Unknown objects (distractors):**
   - The students learned the convention: DS 97.7–99.1% on T2b.
   - Prompted Gemma 4 models send distractors into a bin when the instruction says "everything"/"all the rest" (distractor_silent: E4B-C 40%).
   - Forcing `other` = `leave` unless the rule parser sees an explicit distractor rule fixes most of it: E4B-C goes from 80.3 → 93.0 on T2b.
5. **Fit:** the 270M and 1B students meet every fit bar (latency < 1 s on GPU, VRAM ≤ 4 GB, load ≤ 30 s). E2B-LoRA meets latency and load but needs 10 GB of VRAM. See the next table.
6. **Gemma specifically?** Not shown.
   - Prompted, Qwen2.5-1.5B beats Gemma 3 1B/270M by a wide margin but loses to Gemma 4 E2B/E4B.
   - We fine-tuned only Gemma, so "fine-tuned Gemma vs fine-tuned other model" is untested.
   - The evidence says the fine-tuning and teacher data do the work. The Gemma angle is the prize story (Gemma 4 31B teacher → Gemma student), not a measured advantage.

## Phase 4: fit checks
One process per row, page cache dropped first, 30 warm queries (10 on CPU), batch 1, T2a instructions. CPU = 8 threads.

| Candidate | Device | Cold load → first answer s | Latency p50 / p95 s | Peak VRAM GB | Weights on disk GB |
|---|---|---|---|---|---|
| **student 1B** | RTX PRO 6000 | 9.5 | **0.138 / 0.139** | 2.0 | 2.0 |
| student 1B | CPU | 8.4 | 1.60 / 1.61 | – | 2.0 |
| student 270M | RTX PRO 6000 | 8.6 | 0.096 / 0.096 | 0.55 | 0.54 |
| student 270M | CPU | 6.2 | 0.55 / 0.56 | – | 0.54 |
| student E2B-LoRA | A100 (exp-1 was busy; its checkpoint is 10 GB) | 45.1 | 0.56 / 0.57 | 10.2 | 10.2 |
| student E2B-LoRA | CPU (A100 box) | 21.8 | 4.67 / 4.69 | – | 10.2 |
| Gemma 4 E2B prompted A | RTX PRO 6000 | 25.2 | 1.25 / 1.26 | 10.3 | 10.2 |
| Gemma 4 E2B prompted A | CPU | 29.1 | 20.8 / 21.1 | – | 10.2 |
| Gemma 4 E4B prompted C | RTX PRO 6000 | 34.8 | 0.32 / 0.33 | 16.0 | 16.0 |
| Gemma 4 E4B prompted C | CPU | 44.6 | 33.5 / 33.9 | – | 16.0 |

- The parser runs once per episode in `reset()`. **The 270M / 1B students could stay entirely on the CPU** (0.6–1.6 s) and leave the GPU to the VLA.
- The finals GPU is an RTX 5090. These numbers come from a Blackwell RTX PRO 6000 / A100 and are approximate.
- Raw data: [`results/fitcheck.jsonl`](results/fitcheck.jsonl).

## Hybrids with the rule parser (post-hoc, on the same test sets: treat as hypotheses)
Full table: [`results/hybrid.md`](results/hybrid.md) and [`results/extra_analysis.md`](results/extra_analysis.md).

| Combination | Effect |
|---|---|
| `other` from the rule parser (else `leave`) on prompted Gemma 4 | T2b E2B-A 78.9 → 88.7, E4B-C 80.3 → 93.0, 12B-C 94.8 → 96.7 (distractor safety → 96–98%). Students: no gain; they already learned it |
| `agree`: accept only if LLM and rule parser agree, or the rule parser refuses | 1B student: T2a CW 0.9 → **0.0**, T2b CW 8.0 → 6.1, at −1 to −4 points exact |
| `veto`: refuse if either refuses or they differ | T3 refusal → 90–93%, CW ≤ 1%, but T2a exact drops to ~84% and T2b to ~57%. Too conservative |

**Format C confidence threshold** (Gemma 4 E4B, refusing below the top-1 vs top-2 log-prob gap):
- **T2a:**
  - threshold 0: coverage 100%, exact 91.2%, CW 8.8%
  - threshold 5: coverage 90%, exact 88.2%, CW 1.5%
  - threshold 8: coverage 80%, CW 0.9%
- **T2b:** threshold 8 gives CW 0.5% at 63% coverage.
- **T3:** refusal rises only to 52% at threshold 8.
- **Verdict:** confidence filtering works for CW but is a poor detector of invalid instructions.

## Per-category accuracy (exact %, selected; all methods in [`results/tables.md`](results/tables.md))
**T2a**
| Method | bin_first | bin_syn | colour_var | elimination | length | multi_sent | noisy | passive | real_colour | reordered | terse |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 87.1 | 100 | 96.8 | 97.1 | 71.9 | 96.8 | 62.5 | 100 | 95.2 | 59.4 | 90.6 |
| student 1B | 100 | 100 | 96.8 | 100 | 100 | 100 | 100 | 100 | 61.9 | 75.0 | 96.9 |
| student E2B-LoRA | 100 | 100 | 96.8 | 97.1 | 100 | 100 | 93.8 | 100 | 57.1 | 71.9 | 100 |
| Gemma 4 E4B C | 100 | 100 | 100 | 91.4 | 100 | 100 | 96.9 | 100 | 0.0 | 87.5 | 96.9 |
| Gemma 4 31B C | 100 | 100 | 100 | 91.4 | 100 | 100 | 100 | 100 | 0.0 | 100 | 100 |

**T2b**
| Method | colour_shape | distr_generic | distr_silent | leave | mixed | negation | shape_only |
|---|---|---|---|---|---|---|---|
| rule | 58.1 | 62.1 | 76.7 | 61.3 | 53.3 | 38.7 | 71.0 |
| student 1B | 87.1 | 89.7 | 93.3 | 87.1 | 90.0 | 90.3 | 96.8 |
| student E2B-LoRA | 96.8 | 100 | 93.3 | 96.8 | 96.7 | 93.5 | 100 |
| Gemma 4 E4B C | see tables.md (distractor_silent 40.0) | | | | | | |

**T3 refusal per category:**

| Method | contradiction | nonexistent bin | undefined | unrelated |
|---|---|---|---|---|
| rule | 73 | 60 | 93 | 100 |
| 1B student | 20 | 73 | 53 | 87 |
| E2B-LoRA | 60 | 87 | 53 | 100 |

The students rarely notice contradictions. Our training data had only ~2% contradiction examples.

**Main weaknesses of the students:**
- **`real_colour_names`:** the "orange = red, purple = blue" mapping was never in the training data. Prompted models refuse these entirely (0%), which is *consistent with the prompt*, since orange is not a known colour.
- **`reordered` items that give only an order:** "Bins from left to right: yellow, blue, red".
- **Contradictions in T3.**

## 10 worst failures: recommended student (Gemma 3 1B FT)
Format: 10 slots in the order red cube/cyl/tri, yellow cube/cyl/tri, blue cube/cyl/tri, other.

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-073 | colour_variants | Red, Yellow and Blue should end up in the Right, Left and Center bins respectively. | right×3 left×3 center×3 leave | right×3 **right×3** center×3 leave |
| t2a-339 | real_colour_names | Purple blocks to the left, orange blocks to the right, yellow to the middle. | right×3 center×3 left×3 leave | **left×3** center×3 left×3 leave |
| t2b-045 | shape_only | Cubes go in the left bin, and so do cylinders. Triangles go in the middle bin. | left left center (×3) leave | left **center** center (×3) leave |
| t2b-083 | negation | Everything goes left except triangles and cylinders, which go right. | left right right (×3) leave | left right **leave** (×3) leave |
| t2b-107 | leave | Don't touch anything yellow or blue. Red blocks go in the middle bin. | center×3 leave×3 leave×3 leave | center×3 leave×3 **left×3** leave |
| t2b-116 | leave | Yellow blocks stay where they are. Red blocks go in the centre bin, and so do blue blocks. | center×3 leave×3 center×3 leave | center×3 leave×3 **left×3** leave |
| t2b-132 | distractor_generic | Sort only the red, yellow and blue cubes, cylinders and triangles; anything else stays where it is. Red cubes go right, all other blocks go left. | right left left, left×3, left×3, leave | right left left, left×3, **leave×3**, leave |
| t2b-201 | mixed | Please sort these: triangles in the right bin, but not the red ones, those go left. Everything that's not a triangle goes in the middle. | center center left / center center right / center center right / leave | **left left leave** / center center right / center center right / leave |
| t2b-004 | colour_shape | Every cube goes to the centre bin except the red cube, which goes left. For the cylinders and triangles, sort by colour: red and blue to the right bin, yellow to the left bin. | left right right / center left left / center right right / leave | **leave** right right / **left** left left / center right right / leave |
| t2b-022 | colour_shape | Sort the red blocks by shape - cubes left, cylinders centre, triangles right - and sort the yellow and blue blocks the opposite way round: cubes right, cylinders centre, triangles left. | left center right / right center left / right center left / leave | left center right / right center **right** / right center **right** / leave |

- **Pattern:** "and so do X" / "the opposite way round" / "respectively" constructions, and order-only phrasing. These were rare in the training grammar and the teacher data.
- **The E2B-LoRA list** (in `results/tables.md`) has the same flavour plus the mangled "rd left yllw right ble center".

## Follow-up: Gemini Decision 1 (Sat 14 Nov, ~11:00, online)

Aalto confirmed internet at the finals, so we tested Google's **Gemini Decisions API** (`gemini-decision-1`, launched 11 Nov) on the same frozen test sets.

**Setup:**
- One `createDecision` call per instruction: 10 `choice` questions (9 known types + `other`, each left / center / right / leave) plus one yes/no question "is the instruction invalid?".
- Same task text as the prompted models (`prompts.TASK`), no few-shot examples, no tuning.
- Code: [`gemini_decision.py`](gemini_decision.py) and [`compare_gemini.py`](compare_gemini.py). Needs `GEMINI_API_KEY` in `.env`.

**Results** ([`results/gemini_compare.md`](results/gemini_compare.md)). Exact = all 10 slots right; CW = confidently wrong. Chains try each parser in order, and a refusal passes the instruction to the next one.

| Method | T1 exact | T2a exact / CW | T2a w/o orange-purple exact / CW | T2b exact / CW | T3 refusal |
|---|---|---|---|---|---|
| rule parser | 100.0% | 86.7% / 3.2% | 86.2% / 3.5% | 60.1% / 6.6% | 81.7% |
| Gemma 3 1B (fine-tuned) | 100.0% | 94.7% / 0.9% | 96.9% / 0.3% | 90.6% / 8.0% | 58.3% |
| Gemma 4 E2B (LoRA) | 100.0% | 93.5% / 1.5% | 95.9% / 1.6% | 96.7% / 2.3% | 75.0% |
| **Gemini Decision 1** | 100.0% | 91.7% / **0.0%** | **97.8% / 0.0%** | 93.9% / **0.9%** | **100.0%** |
| **Gemini → Gemma 1B → rule** | 100.0% | **98.5%** / 0.6% | **99.4% / 0.0%** | **98.1%** / 1.9% | 53.3% |
| Gemma 1B → rule (offline only) | 100.0% | 96.5% / 0.9% | 97.2% / 0.3% | 92.0% / 8.0% | 53.3% |

**What it means:**
- **Gemini almost never guesses wrong. When unsure, it refuses.**
  - It was confidently wrong on 0 of 339 colour-only and 2 of 213 harder instructions, and it refused all 60 invalid ones.
  - Most of its misses are refusals, which a fallback can catch. That's the safe failure mode.
- **Its misses have two causes:**
  - **All 21 orange/purple items:** the task text says the colours are red, yellow and blue, so it refuses. Fix once Aalto confirms what the colours are called.
  - **8 of 31 "leave" instructions** ("only sort the red blocks", "don't touch the triangles"): the yes/no "invalid" question vetoed answers whose slot choices were all ≥ 0.98 confident. Our wording ("leaves some known object without any destination") reads "leave it on the table" as no destination.
  - That's a fixable prompt bug. **But we found it on the test set**, so a re-run after fixing it needs new test items to be a fair number.
- **The two remaining confident errors** ("anything remaining goes in the left bin") are a convention question: does "anything remaining" include unknown objects? Our labels say no.
- **The best chain is Gemini first, then the offline Gemma 1B, then the rule parser.** 98.5% / 98.1% exact, and 0.0% confidently wrong on colour-only wording without the orange/purple items.
  - T3 refusal drops in the chain because Gemma answers what Gemini refused. That matters little at the finals, where the instruction will be valid.

**Speed and cost:**
- From a laptop in Helsinki: p50 0.44 s, p95 0.84 s, max 3.05 s over 900 calls. A 2 s timeout before falling back to Gemma looks reasonable.
- 900 calls used 1.05 M input tokens, about **$0.11**.

## Follow-up: Decision 1 with the two prompt fixes, in v1.6 (Sat 14 Nov, evening)

The v1.6 policy (`policy/instruction_d1.py`) calls Decision with the two fixes named above:
- the task text says orange = red and purple = blue;
- no yes/no "invalid?" question (finals instructions are valid).

It uses the answer only if all 10 slots come back with confidence ≥ 0.6; otherwise the rule parser's answer stays (the "v1.6 chain").

T2a and T2b had already been looked at, so a fresh hand-written set came first: **T2c**, 40 items in [`data/t2c.jsonl`](data/t2c.jsonl), written before any run. It covers orange/purple names, Aalto's real rung 1, "leave" / "only" / "don't touch" wording, shape rules, paraphrases and one `other` rule. Script: [`compare_v16.py`](compare_v16.py). Full output for T1/T2a/T2b: [`results/compare_v16_t2ab.md`](results/compare_v16_t2ab.md).

| Set | Rule parser | Decision as first tested | Decision, v1.6 prompt | v1.6 chain |
|---|---|---|---|---|
| **T2c (fresh, 40)** | 80.0% (1 wrong) | 42.5% (3 wrong) | **100.0% (0 wrong)** | **100.0%** |
| T1 (Aalto templates, 288) | 100.0% | 100.0% | 100.0% | 100.0% |
| T2a (339, seen before) | 86.7% (11 wrong) | 91.7% | 99.7% (0 wrong, 1 refused) | 100.0% |
| T2b (213, seen before) | 60.1% (14 wrong) | 93.9% | 99.5% (1 wrong) | 99.5% |

- **Latency** from a laptop in Helsinki: p50 0.3 to 0.75 s and p95 under 1.1 s per set; one call took 7.25 s (T2b). In v1.6 the call starts at reset() and is waited for at most 2.5 s, at the first look.
- **The one wrong answer:** T2b-163, "First put all the cubes in the left bin, then put whatever is left in the right…". Decision sends unknown objects (`other`) right too. That is the open "anything remaining" convention (question 4 below), not a parsing error.
- **Caveats:**
  - 40 items is small: one miss would be 2.5 points.
  - T2c was written by the same people (Emīls + Claude) as the earlier sets.

## Open questions for Aalto
1. **Distractors:** is a known colour on an unknown shape (a red star) a "red object" or a distractor? We assumed a distractor (`other`).
2. **Distractor scoring:** how are distractors scored? Is moving one a penalty, and is leaving it on the table required? Do finals instructions ever say what to do with them?
3. **Real-table colours:** the team saw orange / yellow / purple objects on the real table, but the docs say red / yellow / blue. Will finals instructions say "orange" or "red"? We labelled orange = red and purple = blue (unconfirmed).
4. **"Everything":** in an instruction like "put everything in the left bin", does "everything" include a distractor? We assumed no.
5. **Invalid instructions:** can a finals instruction be invalid or contradictory at all? If not, T3 refusal matters much less and format C becomes attractive.

## What we'd do next
1. **Fix the known data gaps and retrain the 1B student** (~10 min on an A100):
   - add "respectively", "and so do", "the opposite way round", order-only ("left to right: …") and contradiction examples
   - add orange/purple synonyms if Aalto confirms
   - **re-test on a fresh hand-written T2c**, since T2a/T2b have now been looked at
2. **Ship as `rule parser ∧ student` (the `agree` variant):**
   - accept the student's answer when the rule parser agrees or refuses
   - on disagreement, fall back to the rule parser's answer or to rung-1 behaviour
   - with the 1B student this gave 0% confidently wrong on T2a
3. **Try Gemma 4 12B 4-bit, or the Gemma 4 E2B student on the CPU, as the "big" option:**
   - 12B scored 100% on the 318 main T2a items when prompted with format C, but needs 28 GB in bf16
   - the E2B student is 4.7 s on CPU, which may be acceptable once per `reset()` if the episode clock allows it
4. **Prize story (Best Use of Gemma):** Gemma 4 31B teacher → Gemma 3 1B student, offline in the image, beating rules by 8 / 30 points on unseen instructions.
5. **Fine-tune Qwen2.5-1.5B** on the same data to settle question 6 (is it Gemma specifically?).

## Deviations, problems and fixes during the run
- **Extra runs beyond the plan:**
  - **Gemma 4 12B:** prompted A/C, as a mid-size point.
  - **Gemma 4 E2B LoRA student.**
  - **Aalto template examples in the training data:** the programmatic-only 270M student refused 13% of T1 ("{C0} goes to the {b0} bin, {c1} to the {b1} bin…" → `invalid`).
  - All three used machine time that was already paid for. No extra machines.
- **Fixes during the run:**
  - **transformers 5.x:** `TrainingArguments` no longer takes `warmup_ratio`; `finetune.py` now uses `warmup_steps`. The first 270M run crashed and was rerun.
  - **E2B LoRA:** the first attempt failed because E2B wasn't downloaded on exp-2. It was downloaded and rerun.
  - **`fitcheck.py`:** the first run crashed on an incomplete-snapshot check after measuring. The fix reads the HF cache directory. E2B-A, E4B-C and the 270M student were rerun.
- **Fit checks:** the E2B-LoRA fit check ran on the A100, because its 10 GB merged checkpoint was on exp-2.
- **Checkpoints:**
  - **Not kept:** the E2B-LoRA checkpoint (10 GB) was **not** copied back (over the plan's 2 GB limit) and was deleted with exp-2. Reproduce with `run_phase3b.sh` (~8 min on an A100).
  - **Kept** in `artifacts/instruction_parser/ckpt/` (see `training/MODELS.md`): `s270m-full` (0.54 GB) and `s1b-full` (1.9 GB).
- **Delete action:** Verda's `delete` action returns `"action":"discontinue"`. The OS volumes were passed with `delete_permanently: true` and disappeared from `/volumes` and `/volumes/trash` within seconds.
- **Left on the account:**
  - The registered SSH key `gemma-parser-exp` (free) is still there; delete it if you like.
  - `bot-icelli-os` (a detached volume that existed before this run) was not touched.
- **Cost guard:** a laptop-side watchdog (`watchdog.py`, log in `results/logs/watchdog.log`) was ready to delete at 5 h 45 min or €33 of spend. It never had to act.
