## Full results (method × test set)

Exact = all 10 slots right. CW = confidently wrong (valid answer, ≥1 wrong slot). Inv = refused/malformed. DS = distractor safety (`other` correct). T3 = refusal rate on invalid instructions. Latency = warm, batch 1, on T2a.

| Method | T1 exact | T2a exact | T2a CW | T2a inv | T2b exact | T2b CW | T2b inv | T2b DS | T3 refusal | p50 / p95 s | peak VRAM GB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rule` | 100.0 | 86.7 | 3.2 | 10.0 | 60.1 | 6.6 | 33.3 | 65.7 | 81.7 | 0.000 / 0.000 | – |
| `ft:/root/ckpt/s1b-full:B` | 100.0 | 94.7 | 0.9 | 4.4 | 90.6 | 8.0 | 1.4 | 97.7 | 58.3 | 0.407 / 0.416 | 2.7 |
| `ft:/root/ckpt/s270m-full:B` | 100.0 | 91.7 | 3.2 | 5.0 | 82.2 | 14.1 | 3.8 | 94.8 | 53.3 | 0.273 / 0.285 | 0.9 |
| `ft:/root/ckpt/s270m-prog:B` | 86.8 | 83.5 | 6.5 | 10.0 | 55.9 | 41.8 | 2.3 | 96.2 | 56.7 | 0.271 / 0.281 | 0.9 |
| `ft:/root/ckpt/sE2B-lora:B` | 100.0 | 93.5 | 1.5 | 5.0 | 96.7 | 2.3 | 0.9 | 99.1 | 75.0 | 0.563 / 0.573 | 11.3 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:A` | 96.5 | 73.2 | 15.9 | 10.9 | 54.9 | 36.6 | 8.5 | 87.3 | 46.7 | 0.563 / 0.588 | 5.1 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:B` | 23.3 | 14.5 | 52.5 | 33.0 | 1.4 | 66.2 | 32.4 | 61.0 | 73.3 | 0.092 / 0.108 | 4.6 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:C` | 92.7 | 77.6 | 22.4 | 0.0 | 48.8 | 51.2 | 0.0 | 97.2 | 0.0 | 0.126 / 0.127 | 5.0 |
| `hf:google/gemma-3-1b-it:A` | 11.5 | 17.1 | 67.3 | 15.6 | 4.7 | 81.2 | 14.1 | 81.2 | 40.0 | 0.912 / 0.917 | 3.7 |
| `hf:google/gemma-3-1b-it:B` | 1.7 | 1.2 | 38.6 | 60.2 | 0.5 | 58.7 | 40.8 | 15.5 | 68.3 | 0.142 / 0.167 | 3.2 |
| `hf:google/gemma-3-1b-it:C` | 18.4 | 7.4 | 92.6 | 0.0 | 7.0 | 93.0 | 0.0 | 95.3 | 0.0 | 0.152 / 0.154 | 3.6 |
| `hf:google/gemma-3-270m-it:A` | 15.3 | 13.3 | 47.2 | 39.5 | 2.8 | 67.1 | 30.0 | 66.2 | 38.3 | 0.686 / 0.751 | 1.3 |
| `hf:google/gemma-3-270m-it:B` | 16.7 | 16.5 | 83.5 | 0.0 | 1.9 | 98.1 | 0.0 | 95.8 | 10.0 | 0.098 / 0.106 | 1.1 |
| `hf:google/gemma-3-270m-it:C` | 17.0 | 5.3 | 94.7 | 0.0 | 2.3 | 97.7 | 0.0 | 95.8 | 0.0 | 0.147 / 0.160 | 1.3 |
| `hf:google/gemma-4-12B-it:A` | 100.0 | 92.0 | 2.9 | 5.0 | 88.3 | 11.3 | 0.5 | 88.3 | 75.0 | 2.330 / 2.333 | 28.8 |
| `hf:google/gemma-4-12B-it:C` | 100.0 | 93.8 | 6.2 | 0.0 | 94.8 | 5.2 | 0.0 | 94.8 | 0.0 | 0.723 / 0.739 | 28.6 |
| `hf:google/gemma-4-31B-it:A` | 100.0 | 87.9 | 0.6 | 11.5 | 96.2 | 1.9 | 1.9 | 96.2 | 100.0 | 4.322 / 4.325 | 74.2 |
| `hf:google/gemma-4-31B-it:B` | 100.0 | 85.0 | 2.4 | 12.7 | 81.2 | 16.9 | 1.9 | 91.1 | 95.0 | 0.729 / 0.729 | 71.1 |
| `hf:google/gemma-4-31B-it:C` | 100.0 | 92.9 | 7.1 | 0.0 | 98.1 | 1.9 | 0.0 | 98.1 | 0.0 | 1.606 / 1.717 | 73.7 |
| `hf:google/gemma-4-E2B-it:A` | 100.0 | 89.1 | 10.3 | 0.6 | 78.9 | 21.1 | 0.0 | 84.5 | 25.0 | 1.262 / 1.270 | 12.6 |
| `hf:google/gemma-4-E2B-it:B` | 21.2 | 12.7 | 67.3 | 20.1 | 9.9 | 54.5 | 35.7 | 56.8 | 36.7 | 0.195 / 0.212 | 11.9 |
| `hf:google/gemma-4-E2B-it:C` | 100.0 | 85.5 | 14.5 | 0.0 | 62.0 | 38.0 | 0.0 | 79.8 | 0.0 | 0.212 / 0.214 | 12.5 |
| `hf:google/gemma-4-E4B-it:A` | 100.0 | 88.8 | 7.4 | 3.8 | 79.8 | 20.2 | 0.0 | 83.1 | 48.3 | 1.586 / 1.593 | 19.8 |
| `hf:google/gemma-4-E4B-it:B` | 53.1 | 37.5 | 56.0 | 6.5 | 31.0 | 62.4 | 6.6 | 81.7 | 60.0 | 0.248 / 0.257 | 18.7 |
| `hf:google/gemma-4-E4B-it:C` | 100.0 | 91.2 | 8.8 | 0.0 | 80.3 | 19.7 | 0.0 | 84.0 | 0.0 | 0.317 / 0.325 | 19.6 |

## Per-category exact accuracy, T2A (%)

| Method | bin_first | bin_synonyms | colour_variants | elimination | length_extremes | multi_sentence | noisy | passive | real_colour_names | reordered | terse |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rule` | 87.1 | 100.0 | 96.8 | 97.1 | 71.9 | 96.8 | 62.5 | 100.0 | 95.2 | 59.4 | 90.6 |
| `ft:/root/ckpt/s1b-full:B` | 100.0 | 100.0 | 96.8 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 61.9 | 75.0 | 96.9 |
| `ft:/root/ckpt/s270m-full:B` | 100.0 | 100.0 | 96.8 | 97.1 | 100.0 | 100.0 | 90.6 | 100.0 | 47.6 | 65.6 | 96.9 |
| `ft:/root/ckpt/s270m-prog:B` | 87.1 | 93.5 | 96.8 | 88.6 | 100.0 | 100.0 | 65.6 | 100.0 | 9.5 | 56.2 | 96.9 |
| `ft:/root/ckpt/sE2B-lora:B` | 100.0 | 100.0 | 96.8 | 97.1 | 100.0 | 100.0 | 93.8 | 100.0 | 57.1 | 71.9 | 100.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:A` | 67.7 | 77.4 | 100.0 | 31.4 | 75.0 | 96.8 | 96.9 | 100.0 | 0.0 | 68.8 | 71.9 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:B` | 16.1 | 12.9 | 35.5 | 2.9 | 12.5 | 12.9 | 9.4 | 12.9 | 14.3 | 15.6 | 15.6 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:C` | 67.7 | 93.5 | 93.5 | 54.3 | 87.5 | 87.1 | 96.9 | 87.1 | 19.0 | 68.8 | 81.2 |
| `hf:google/gemma-3-1b-it:A` | 22.6 | 3.2 | 16.1 | 8.6 | 25.0 | 51.6 | 12.5 | 16.1 | 0.0 | 6.2 | 21.9 |
| `hf:google/gemma-3-1b-it:B` | 0.0 | 0.0 | 3.2 | 0.0 | 0.0 | 6.5 | 0.0 | 3.2 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-3-1b-it:C` | 0.0 | 0.0 | 3.2 | 2.9 | 0.0 | 12.9 | 21.9 | 3.2 | 14.3 | 0.0 | 25.0 |
| `hf:google/gemma-3-270m-it:A` | 19.4 | 12.9 | 22.6 | 5.7 | 25.0 | 16.1 | 9.4 | 19.4 | 0.0 | 9.4 | 3.1 |
| `hf:google/gemma-3-270m-it:B` | 16.1 | 16.1 | 16.1 | 17.1 | 18.8 | 16.1 | 18.8 | 16.1 | 14.3 | 15.6 | 15.6 |
| `hf:google/gemma-3-270m-it:C` | 0.0 | 0.0 | 3.2 | 0.0 | 0.0 | 9.7 | 18.8 | 0.0 | 14.3 | 0.0 | 15.6 |
| `hf:google/gemma-4-12B-it:A` | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 84.4 | 100.0 | 0.0 | 96.9 | 100.0 |
| `hf:google/gemma-4-12B-it:C` | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 |
| `hf:google/gemma-4-31B-it:A` | 100.0 | 100.0 | 96.8 | 88.6 | 100.0 | 100.0 | 53.1 | 100.0 | 0.0 | 100.0 | 100.0 |
| `hf:google/gemma-4-31B-it:B` | 100.0 | 96.8 | 93.5 | 85.7 | 100.0 | 100.0 | 46.9 | 100.0 | 0.0 | 84.4 | 100.0 |
| `hf:google/gemma-4-31B-it:C` | 100.0 | 100.0 | 100.0 | 91.4 | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 |
| `hf:google/gemma-4-E2B-it:A` | 100.0 | 100.0 | 100.0 | 74.3 | 96.9 | 100.0 | 100.0 | 100.0 | 0.0 | 84.4 | 96.9 |
| `hf:google/gemma-4-E2B-it:B` | 22.6 | 9.7 | 29.0 | 2.9 | 18.8 | 9.7 | 6.2 | 25.8 | 0.0 | 0.0 | 12.5 |
| `hf:google/gemma-4-E2B-it:C` | 100.0 | 100.0 | 100.0 | 71.4 | 90.6 | 77.4 | 100.0 | 100.0 | 0.0 | 78.1 | 96.9 |
| `hf:google/gemma-4-E4B-it:A` | 100.0 | 100.0 | 93.5 | 82.9 | 100.0 | 100.0 | 93.8 | 100.0 | 0.0 | 81.2 | 96.9 |
| `hf:google/gemma-4-E4B-it:B` | 38.7 | 32.3 | 58.1 | 25.7 | 34.4 | 58.1 | 25.0 | 58.1 | 0.0 | 37.5 | 34.4 |
| `hf:google/gemma-4-E4B-it:C` | 100.0 | 100.0 | 100.0 | 91.4 | 100.0 | 100.0 | 96.9 | 100.0 | 0.0 | 87.5 | 96.9 |

## Per-category exact accuracy, T2B (%)

| Method | colour_shape | distractor_generic | distractor_silent | leave | mixed | negation | shape_only |
|---|---|---|---|---|---|---|---|
| `rule` | 58.1 | 62.1 | 76.7 | 61.3 | 53.3 | 38.7 | 71.0 |
| `ft:/root/ckpt/s1b-full:B` | 87.1 | 89.7 | 93.3 | 87.1 | 90.0 | 90.3 | 96.8 |
| `ft:/root/ckpt/s270m-full:B` | 83.9 | 82.8 | 63.3 | 83.9 | 90.0 | 77.4 | 93.5 |
| `ft:/root/ckpt/s270m-prog:B` | 32.3 | 55.2 | 46.7 | 58.1 | 63.3 | 58.1 | 77.4 |
| `ft:/root/ckpt/sE2B-lora:B` | 96.8 | 100.0 | 93.3 | 96.8 | 96.7 | 93.5 | 100.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:A` | 29.0 | 69.0 | 50.0 | 41.9 | 56.7 | 67.7 | 71.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:B` | 0.0 | 0.0 | 3.3 | 6.5 | 0.0 | 0.0 | 0.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:C` | 22.6 | 69.0 | 50.0 | 45.2 | 56.7 | 54.8 | 45.2 |
| `hf:google/gemma-3-1b-it:A` | 0.0 | 10.3 | 20.0 | 0.0 | 0.0 | 3.2 | 0.0 |
| `hf:google/gemma-3-1b-it:B` | 0.0 | 0.0 | 0.0 | 3.2 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-3-1b-it:C` | 6.5 | 10.3 | 13.3 | 0.0 | 10.0 | 9.7 | 0.0 |
| `hf:google/gemma-3-270m-it:A` | 3.2 | 0.0 | 6.7 | 0.0 | 3.3 | 6.5 | 0.0 |
| `hf:google/gemma-3-270m-it:B` | 0.0 | 0.0 | 6.7 | 0.0 | 3.3 | 3.2 | 0.0 |
| `hf:google/gemma-3-270m-it:C` | 3.2 | 0.0 | 6.7 | 0.0 | 3.3 | 3.2 | 0.0 |
| `hf:google/gemma-4-12B-it:A` | 100.0 | 96.6 | 53.3 | 93.5 | 93.3 | 83.9 | 96.8 |
| `hf:google/gemma-4-12B-it:C` | 100.0 | 100.0 | 76.7 | 100.0 | 96.7 | 93.5 | 96.8 |
| `hf:google/gemma-4-31B-it:A` | 100.0 | 100.0 | 86.7 | 96.8 | 93.3 | 100.0 | 96.8 |
| `hf:google/gemma-4-31B-it:B` | 80.6 | 93.1 | 63.3 | 90.3 | 76.7 | 87.1 | 77.4 |
| `hf:google/gemma-4-31B-it:C` | 100.0 | 100.0 | 86.7 | 100.0 | 100.0 | 100.0 | 100.0 |
| `hf:google/gemma-4-E2B-it:A` | 96.8 | 89.7 | 46.7 | 83.9 | 76.7 | 74.2 | 83.9 |
| `hf:google/gemma-4-E2B-it:B` | 0.0 | 17.2 | 13.3 | 12.9 | 10.0 | 6.5 | 9.7 |
| `hf:google/gemma-4-E2B-it:C` | 58.1 | 93.1 | 33.3 | 87.1 | 70.0 | 58.1 | 35.5 |
| `hf:google/gemma-4-E4B-it:A` | 93.5 | 100.0 | 40.0 | 93.5 | 76.7 | 67.7 | 87.1 |
| `hf:google/gemma-4-E4B-it:B` | 16.1 | 41.4 | 26.7 | 29.0 | 40.0 | 41.9 | 22.6 |
| `hf:google/gemma-4-E4B-it:C` | 93.5 | 100.0 | 40.0 | 93.5 | 76.7 | 67.7 | 90.3 |

## T3 refusal per category (%)

| Method | contradiction | nonexistent_bin | undefined | unrelated |
|---|---|---|---|---|
| `rule` | 73.3 | 60.0 | 93.3 | 100.0 |
| `ft:/root/ckpt/s1b-full:B` | 20.0 | 73.3 | 53.3 | 86.7 |
| `ft:/root/ckpt/s270m-full:B` | 20.0 | 73.3 | 33.3 | 86.7 |
| `ft:/root/ckpt/s270m-prog:B` | 26.7 | 73.3 | 33.3 | 93.3 |
| `ft:/root/ckpt/sE2B-lora:B` | 60.0 | 86.7 | 53.3 | 100.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:A` | 6.7 | 93.3 | 6.7 | 80.0 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:B` | 53.3 | 86.7 | 60.0 | 93.3 |
| `hf:Qwen/Qwen2.5-1.5B-Instruct:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-3-1b-it:A` | 0.0 | 100.0 | 0.0 | 60.0 |
| `hf:google/gemma-3-1b-it:B` | 46.7 | 86.7 | 53.3 | 86.7 |
| `hf:google/gemma-3-1b-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-3-270m-it:A` | 26.7 | 53.3 | 33.3 | 40.0 |
| `hf:google/gemma-3-270m-it:B` | 0.0 | 0.0 | 0.0 | 40.0 |
| `hf:google/gemma-3-270m-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-4-12B-it:A` | 100.0 | 100.0 | 0.0 | 100.0 |
| `hf:google/gemma-4-12B-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-4-31B-it:A` | 100.0 | 100.0 | 100.0 | 100.0 |
| `hf:google/gemma-4-31B-it:B` | 100.0 | 100.0 | 80.0 | 100.0 |
| `hf:google/gemma-4-31B-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-4-E2B-it:A` | 20.0 | 26.7 | 0.0 | 53.3 |
| `hf:google/gemma-4-E2B-it:B` | 33.3 | 40.0 | 20.0 | 53.3 |
| `hf:google/gemma-4-E2B-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |
| `hf:google/gemma-4-E4B-it:A` | 53.3 | 86.7 | 0.0 | 53.3 |
| `hf:google/gemma-4-E4B-it:B` | 73.3 | 86.7 | 6.7 | 73.3 |
| `hf:google/gemma-4-E4B-it:C` | 0.0 | 0.0 | 0.0 | 0.0 |

## Format C: accuracy vs confidence threshold (low-confidence answers go to the fallback)


`hf:Qwen/Qwen2.5-1.5B-Instruct:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 77.6 | 22.4 | 100.0 | 48.8 | 51.2 | 0.0 |
| 0.5 | 85.3 | 72.9 | 12.4 | 70.4 | 42.3 | 28.2 | 40.0 |
| 1.0 | 74.3 | 67.3 | 7.1 | 46.0 | 32.4 | 13.6 | 71.7 |
| 2.0 | 55.5 | 53.7 | 1.8 | 22.1 | 17.4 | 4.7 | 90.0 |
| 3.0 | 39.2 | 38.6 | 0.6 | 6.6 | 5.6 | 0.9 | 96.7 |
| 5.0 | 10.6 | 10.6 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| 8.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |

`hf:google/gemma-3-1b-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 7.4 | 92.6 | 100.0 | 7.0 | 93.0 | 0.0 |
| 0.5 | 20.4 | 5.0 | 15.3 | 61.5 | 5.6 | 55.9 | 56.7 |
| 1.0 | 17.1 | 4.7 | 12.4 | 50.2 | 4.7 | 45.5 | 66.7 |
| 2.0 | 9.7 | 2.9 | 6.8 | 35.7 | 4.2 | 31.5 | 81.7 |
| 3.0 | 7.4 | 2.7 | 4.7 | 28.2 | 3.8 | 24.4 | 90.0 |
| 5.0 | 2.9 | 0.9 | 2.1 | 15.0 | 2.3 | 12.7 | 96.7 |
| 8.0 | 0.3 | 0.3 | 0.0 | 4.2 | 1.4 | 2.8 | 98.3 |

`hf:google/gemma-3-270m-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 5.3 | 94.7 | 100.0 | 2.3 | 97.7 | 0.0 |
| 0.5 | 87.0 | 5.0 | 82.0 | 83.1 | 2.3 | 80.8 | 5.0 |
| 1.0 | 81.7 | 5.0 | 76.7 | 70.4 | 1.9 | 68.5 | 18.3 |
| 2.0 | 69.0 | 4.4 | 64.6 | 54.0 | 1.9 | 52.1 | 33.3 |
| 3.0 | 50.7 | 3.5 | 47.2 | 36.2 | 1.4 | 34.7 | 48.3 |
| 5.0 | 15.0 | 0.9 | 14.2 | 11.7 | 0.9 | 10.8 | 90.0 |
| 8.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |

`hf:google/gemma-4-12B-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 93.8 | 6.2 | 100.0 | 94.8 | 5.2 | 0.0 |
| 0.5 | 100.0 | 93.8 | 6.2 | 100.0 | 94.8 | 5.2 | 1.7 |
| 1.0 | 99.7 | 93.5 | 6.2 | 100.0 | 94.8 | 5.2 | 3.3 |
| 2.0 | 97.6 | 91.7 | 5.9 | 98.6 | 94.4 | 4.2 | 10.0 |
| 3.0 | 93.5 | 87.6 | 5.9 | 95.3 | 91.5 | 3.8 | 21.7 |
| 5.0 | 92.9 | 87.0 | 5.9 | 83.1 | 82.2 | 0.9 | 26.7 |
| 8.0 | 85.5 | 81.4 | 4.1 | 74.2 | 74.2 | 0.0 | 51.7 |

`hf:google/gemma-4-31B-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 92.9 | 7.1 | 100.0 | 98.1 | 1.9 | 0.0 |
| 0.5 | 100.0 | 92.9 | 7.1 | 100.0 | 98.1 | 1.9 | 15.0 |
| 1.0 | 100.0 | 92.9 | 7.1 | 100.0 | 98.1 | 1.9 | 28.3 |
| 2.0 | 99.4 | 92.6 | 6.8 | 99.5 | 98.1 | 1.4 | 46.7 |
| 3.0 | 99.4 | 92.6 | 6.8 | 99.1 | 97.7 | 1.4 | 55.0 |
| 5.0 | 97.9 | 92.3 | 5.6 | 98.6 | 97.7 | 0.9 | 65.0 |
| 8.0 | 96.5 | 91.4 | 5.0 | 97.2 | 96.7 | 0.5 | 75.0 |

`hf:google/gemma-4-E2B-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 85.5 | 14.5 | 100.0 | 62.0 | 38.0 | 0.0 |
| 0.5 | 95.3 | 83.5 | 11.8 | 90.1 | 57.7 | 32.4 | 1.7 |
| 1.0 | 90.6 | 79.9 | 10.6 | 83.6 | 55.9 | 27.7 | 8.3 |
| 2.0 | 80.2 | 74.6 | 5.6 | 71.4 | 51.2 | 20.2 | 26.7 |
| 3.0 | 72.0 | 69.0 | 2.9 | 63.8 | 48.4 | 15.5 | 40.0 |
| 5.0 | 57.8 | 56.9 | 0.9 | 55.4 | 43.2 | 12.2 | 56.7 |
| 8.0 | 21.2 | 21.2 | 0.0 | 40.4 | 36.2 | 4.2 | 95.0 |

`hf:google/gemma-4-E4B-it:C`

| threshold | T2a coverage | T2a exact (overall) | T2a CW | T2b coverage | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|---|---|
| 0.0 | 100.0 | 91.2 | 8.8 | 100.0 | 80.3 | 19.7 | 0.0 |
| 0.5 | 98.5 | 90.9 | 7.7 | 96.7 | 79.3 | 17.4 | 6.7 |
| 1.0 | 96.5 | 90.6 | 5.9 | 93.9 | 77.9 | 16.0 | 8.3 |
| 2.0 | 95.0 | 90.3 | 4.7 | 87.8 | 76.1 | 11.7 | 13.3 |
| 3.0 | 93.2 | 90.0 | 3.2 | 85.0 | 75.6 | 9.4 | 16.7 |
| 5.0 | 89.7 | 88.2 | 1.5 | 79.3 | 73.2 | 6.1 | 28.3 |
| 8.0 | 79.6 | 78.8 | 0.9 | 63.4 | 62.9 | 0.5 | 51.7 |

## Worst failures: `ft_--root--ckpt--sE2B-lora_B`

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-235 | noisy | rd left yllw right ble center | left left left right right right center center center leave | right right right left left left center center center leave |
| t2a-283 | reordered | Bins, from the right: red, then yellow, then blue. | right right right center center center left left left leave | right right right left left left center center center leave |
| t2a-179 | elimination | Red and blue to the left and right bins respectively; yellow takes the remaining one. | left left left center center center right right right leave | left left left right right right left right left leave |
| t2a-073 | colour_variants | Red, Yellow and Blue should end up in the Right, Left and Center bins respectively. | right right right left left left center center center leave | right right right right right right center center center leave |
| t2a-273 | reordered | Going left to right, the bins should hold red, blue and yellow. | left left left right right right center center center leave | left left left right right right left left left leave |
| t2b-083 | negation | Everything goes left except triangles and cylinders, which go right. | left right right left right right left right right leave | left right leave left right leave left right leave leave |
| t2b-213 | mixed | Everything goes in the left bin... oh, except the cylinders, those go in the right bin. | left right left left right left left right left leave | left leave left left leave left left leave left leave |
| t2b-084 | negation | Blocks that aren't yellow cylinders go in the middle bin. Yellow cylinders go in the right bin. | center center center center right center center center center leave | center center center right right right center center center leave |
| t2b-111 | leave | Leave the blue and yellow triangles alone. Everything else goes in the right bin. | right right right right right leave right right leave leave | right right right right right leave leave leave leave leave |
| t2b-027 | colour_shape | Yellow and blue cylinders go in the right bin. Red cylinders and every cube go in the left bin. All triangles go in the middle bin. | left left center left right center left right center leave | left left center right right center left right center leave |

## Worst failures: `ft_--root--ckpt--s1b-full_B`

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-073 | colour_variants | Red, Yellow and Blue should end up in the Right, Left and Center bins respectively. | right right right left left left center center center leave | right right right right right right center center center leave |
| t2a-339 | real_colour_names | Purple blocks to the left, orange blocks to the right, yellow to the middle. | right right right center center center left left left leave | left left left center center center left left left leave |
| t2b-045 | shape_only | Cubes go in the left bin, and so do cylinders. Triangles go in the middle bin. | left left center left left center left left center leave | left center center left center center left center center leave |
| t2b-083 | negation | Everything goes left except triangles and cylinders, which go right. | left right right left right right left right right leave | left right leave left right leave left right leave leave |
| t2b-107 | leave | Don't touch anything yellow or blue. Red blocks go in the middle bin. | center center center leave leave leave leave leave leave leave | center center center leave leave leave left left left leave |
| t2b-116 | leave | Yellow blocks stay where they are. Red blocks go in the centre bin, and so do blue blocks. | center center center leave leave leave center center center leave | center center center leave leave leave left left left leave |
| t2b-132 | distractor_generic | Sort only the red, yellow and blue cubes, cylinders and triangles; anything else stays where it is. Red cubes go right, all other blocks go left. | right left left left left left left left left leave | right left left left left left leave leave leave leave |
| t2b-201 | mixed | Please sort these: triangles in the right bin, but not the red ones, those go left. Everything that's not a triangle goes in the middle. | center center left center center right center center right leave | left left leave center center right center center right leave |
| t2b-004 | colour_shape | Every cube goes to the centre bin except the red cube, which goes left. For the cylinders and triangles, sort by colour: red and blue to the right bin, yellow to the left bin. | left right right center left left center right right leave | leave right right left left left center right right leave |
| t2b-022 | colour_shape | Sort the red blocks by shape - cubes left, cylinders centre, triangles right - and sort the yellow and blue blocks the opposite way round: cubes right, cylinders centre, triangles left. | left center right right center left right center left leave | left center right right center right right center right leave |

## Worst failures: `ft_--root--ckpt--s270m-full_B`

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-073 | colour_variants | Red, Yellow and Blue should end up in the Right, Left and Center bins respectively. | right right right left left left center center center leave | right right right center center center left left left leave |
| t2a-139 | terse | L=blue C=red R=yellow | center center center right right right left left left leave | right right right center center center left left left leave |
| t2a-243 | noisy | red objects middle bin yellow objects right bin blue objects left bin | center center center right right right left left left leave | center center center left left left right right right leave |
| t2a-272 | reordered | The yellow ones? Right bin. The blue? Middle. Red? Left. | left left left right right right center center center leave | left left left center center center right right right leave |
| t2a-280 | reordered | If it's yellow, center; if it's red, right; if it's blue, left. | right right right center center center left left left leave | center center center right right right left left left leave |
| t2a-327 | real_colour_names | orange left purple middle yelow right | left left left right right right center center center leave | left left left center center center right right right leave |
| t2a-328 | real_colour_names | Yellow on the right, orange on the left, and purple in the remaining bin. | left left left right right right center center center leave | center center center right right right left left left leave |
| t2a-166 | elimination | Blue on the right, red in the center; whatever bin is unused gets yellow. | center center center left left left right right right leave | center center center leave leave leave right right right leave |
| t2a-235 | noisy | rd left yllw right ble center | left left left right right right center center center leave | left left left left left left center center center leave |
| t2a-325 | real_colour_names | Purple objects should be placed in the center bin, orange objects in the left bin, yellow objects in the right bin. | left left left right right right center center center leave | center center center right right right center center center leave |

## Worst failures: `rule`

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-007 | bin_first | For the left bin, red. For the center bin, blue. For the right bin, yellow. | left left left right right right center center center leave | center center center left left left right right right leave |
| t2a-025 | bin_first | Into the left bin, all the blue pieces. Into the center bin, all the red pieces. Into the right bin, all the yellow pieces. | center center center right right right left left left leave | right right right left left left center center center leave |
| t2a-027 | bin_first | Left bin, red; center bin, blue; right bin, yellow. | left left left right right right center center center leave | center center center left left left right right right leave |
| t2a-255 | reordered | In the right bin, blue; in the middle bin, yellow; in the left bin, red. | left left left center center center right right right leave | right right right left left left center center center leave |
| t2b-132 | distractor_generic | Sort only the red, yellow and blue cubes, cylinders and triangles; anything else stays where it is. Red cubes go right, all other blocks go left. | right left left left left left left left left leave | right right right right right right right right right leave |
| t2a-003 | bin_first | Into the right bin go the red pieces; into the center bin, the blue; into the left bin, the yellow. | right right right left left left center center center leave | right right right center center center left left left leave |
| t2a-073 | colour_variants | Red, Yellow and Blue should end up in the Right, Left and Center bins respectively. | right right right left left left center center center leave | right right right right right right right right right leave |
| t2a-236 | noisy | yellow too the rite bin blue too the left bin red too the senter bin | center center center right right right left left left leave | left left left left left left left left left leave |
| t2b-206 | mixed | Right bin: blue cubes, blue cylinders. Left bin: blue triangles, all red. Centre bin: all yellow. | left left left center center center right right left leave | center center center center center center right left left leave |
| t2a-225 | noisy | yello goes left red goes rite blue goes middle | right right right left left left center center center leave | left left left left left left center center center leave |

## Worst failures: `hf_google--gemma-4-E4B-it_C`

| id | category | instruction | expected | got |
|---|---|---|---|---|
| t2a-329 | real_colour_names | From left to right: purple, yellow, orange. | right right right center center center left left left leave | leave leave leave leave leave leave leave leave leave leave |
| t2a-327 | real_colour_names | orange left purple middle yelow right | left left left right right right center center center leave | leave leave leave right leave leave leave leave leave leave |
| t2a-319 | real_colour_names | Orange blocks in the left bin, yellow in the center bin, purple in the right bin. | left left left center center center right right right leave | leave leave leave center center center leave leave leave left |
| t2a-320 | real_colour_names | The purple ones go on the left, the orange ones in the middle, the yellow ones on the right. | center center center right right right left left left leave | leave leave leave right right right leave leave leave left |
| t2a-321 | real_colour_names | orange → right, yellow → left, purple → center | right right right left left left center center center leave | leave leave leave left left left leave leave leave right |
| t2a-324 | real_colour_names | Anything orange goes in the right bin, anything purple in the left bin, and anything yellow in the middle. | right right right center center center left left left leave | leave leave leave center center center leave leave leave right |
| t2a-325 | real_colour_names | Purple objects should be placed in the center bin, orange objects in the left bin, yellow objects in the right bin. | left left left right right right center center center leave | leave leave leave right right right leave leave leave center |
| t2a-331 | real_colour_names | Orange in the rightmost bin, purple in the central bin, yellow in the leftmost bin. | right right right left left left center center center leave | leave leave leave left left left leave leave leave right |
| t2a-332 | real_colour_names | orange: center, yellow: left, purple: right | center center center left left left right right right leave | leave leave leave left left left leave leave leave center |
| t2a-333 | real_colour_names | Orange-coloured items go right, purple-coloured items go left, yellow-coloured items go in the middle. | right right right center center center left left left leave | leave leave leave center center center leave leave leave right |
