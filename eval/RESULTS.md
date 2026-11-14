# Eval scoreboard

Empty log, one row per scored sim run. The columns are a starting point; change them as the team needs.

| ID | Date | Who | Policy (git sha / image digest) | Model (m-…) | Task | DR | Trials | Mean score | % sorted | Clips | Hz (sim / rt) | Gate | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e-001 | 2026-11-14 | Emīls | Aalto `oracle` baseline (Aalto 36daf5b) | — | sort_fixed | nominal | 3 | +3.67 ± 0.94 | 92 % (11/12) | 0 | 30.0 / 89.4 | PASS | Verda RTX 6000 Ada, 10 vCPU, bare metal. RTF 0.31. Uses privileged object poses, so not a valid submission. Logs: `artifacts/eval/oracle_sort_fixed_nominal_20261114_005442/` (local, git-ignored) |
