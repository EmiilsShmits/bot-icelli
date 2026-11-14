
### t2a.jsonl (339 items)

| Parser | Exact | Wrong | Refused |
|---|---|---|---|
| rule parser | 294/339 (86.7%) | 11 | 34 |
| Decision as first tested | 311/339 (91.7%) | 0 | 28 |
| Decision v1.6 prompt | 338/339 (99.7%) | 0 | 1 |
| v1.6 chain (Decision, else rules) | 339/339 (100.0%) | 0 | 0 |

v1.6 Decision latency p50 0.31 s, p95 0.48 s, max 0.67 s

Per category, exact (rules / first Decision / v1.6 chain):
  bin_first: 27 / 31 / 31 of 31
  bin_synonyms: 31 / 31 / 31 of 31
  colour_variants: 30 / 31 / 31 of 31
  elimination: 34 / 33 / 35 of 35
  length_extremes: 23 / 32 / 32 of 32
  multi_sentence: 30 / 31 / 31 of 31
  noisy: 20 / 31 / 32 of 32
  passive: 31 / 31 / 31 of 31
  real_colour_names: 20 / 0 / 21 of 21
  reordered: 19 / 29 / 32 of 32
  terse: 29 / 31 / 32 of 32

### t2b.jsonl (213 items)

| Parser | Exact | Wrong | Refused |
|---|---|---|---|
| rule parser | 128/213 (60.1%) | 14 | 71 |
| Decision as first tested | 200/213 (93.9%) | 2 | 11 |
| Decision v1.6 prompt | 212/213 (99.5%) | 1 | 0 |
| v1.6 chain (Decision, else rules) | 212/213 (99.5%) | 1 | 0 |

v1.6 Decision latency p50 0.24 s, p95 1.06 s, max 7.25 s

Per category, exact (rules / first Decision / v1.6 chain):
  colour_shape: 18 / 31 / 31 of 31
  distractor_generic: 18 / 29 / 29 of 29
  distractor_silent: 23 / 28 / 29 of 30
  leave: 19 / 23 / 31 of 31
  mixed: 16 / 27 / 30 of 30
  negation: 12 / 31 / 31 of 31
  shape_only: 22 / 31 / 31 of 31
  MISS t2b-163 [decision] 'First put all the cubes in the left bin, then put whatever is left in the right ' -> {'other': 'right'}

### t1.jsonl (288 items)

| Parser | Exact | Wrong | Refused |
|---|---|---|---|
| rule parser | 288/288 (100.0%) | 0 | 0 |
| Decision as first tested | 288/288 (100.0%) | 0 | 0 |
| Decision v1.6 prompt | 288/288 (100.0%) | 0 | 0 |
| v1.6 chain (Decision, else rules) | 288/288 (100.0%) | 0 | 0 |

v1.6 Decision latency p50 0.75 s, p95 1.10 s, max 1.45 s

Per category, exact (rules / first Decision / v1.6 chain):
  template_0: 36 / 36 / 36 of 36
  template_1: 36 / 36 / 36 of 36
  template_2: 36 / 36 / 36 of 36
  template_3: 36 / 36 / 36 of 36
  template_4: 36 / 36 / 36 of 36
  template_5: 36 / 36 / 36 of 36
  template_6: 36 / 36 / 36 of 36
  template_7: 36 / 36 / 36 of 36
