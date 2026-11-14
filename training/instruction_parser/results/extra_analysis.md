## T2a without the 21 `real_colour_names` items (318 items)

| Method | exact | CW | inv |
|---|---|---|---|
| `rule` | 86.2 | 3.5 | 10.4 |
| `ft_--root--ckpt--sE2B-lora_B` | 95.9 | 1.6 | 2.5 |
| `ft_--root--ckpt--s1b-full_B` | 96.9 | 0.3 | 2.8 |
| `ft_--root--ckpt--s270m-full_B` | 94.7 | 2.2 | 3.1 |
| `hf_google--gemma-4-E4B-it_C` | 97.2 | 2.8 | 0.0 |
| `hf_google--gemma-4-12B-it_C` | 100.0 | 0.0 | 0.0 |
| `hf_google--gemma-4-31B-it_C` | 99.1 | 0.9 | 0.0 |
| `hf_google--gemma-4-31B-it_A` | 93.7 | 0.6 | 5.7 |

## Veto variant: refuse if the LLM *or* the rule parser refuses, or if their answers differ

Same as `agree` in hybrid.md but the rule parser's refusals also count. Shows the T3 / coverage trade-off.

| Method | T2a exact | T2a CW | T2b exact | T2b CW | T3 refusal |
|---|---|---|---|---|---|
| `ft_--root--ckpt--sE2B-lora_B` | 84.1 | 0.0 | 58.7 | 0.5 | 93.3 |
| `ft_--root--ckpt--s1b-full_B` | 84.4 | 0.0 | 57.3 | 0.9 | 93.3 |
| `ft_--root--ckpt--s270m-full_B` | 82.3 | 0.0 | 51.2 | 0.5 | 90.0 |
| `hf_google--gemma-4-E4B-it_C` | 79.6 | 0.0 | 49.8 | 0.0 | 98.3 |
