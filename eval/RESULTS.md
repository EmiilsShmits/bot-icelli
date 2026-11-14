# Eval scoreboard

Empty log, one row per scored sim run. The columns are a starting point; change them as the team needs.

| ID | Date | Who | Policy (git sha / image digest) | Model (m-…) | Task | DR | Trials | Mean score | % sorted | Clips | Hz (sim / rt) | Gate | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e-001 | 2026-11-14 | Emīls | Aalto `oracle` baseline (Aalto 36daf5b) | — | sort_fixed | nominal | 3 | +3.67 ± 0.94 | 92 % (11/12) | 0 | 30.0 / 89.4 | PASS | Verda RTX 6000 Ada, 10 vCPU, bare metal. RTF 0.31. Uses privileged object poses, so not a valid submission. Logs: `artifacts/eval/oracle_sort_fixed_nominal_20261114_005442/` (local, git-ignored) |
| e-002 | 2026-11-14 | Emīls | Aalto `oracle` baseline (Aalto 36daf5b) + venue look (`sim/venue_look/`: camera offset, 7.5 cm bin walls) | — | sort_fixed | nominal | 2 | +3.50 ± 0.50 | 88 % (7/8) | 0 | 30.0 / 116 | PASS | Verda RTX PRO 6000 (spot), 30 vCPU, bare metal. RTF 0.41 during the run. Checks that the oracle still sorts with the venue geometry. Logs: `artifacts/eval/oracle_sort_fixed_nominal_20261114_101945/` (local, git-ignored) |
| e-003 | 2026-11-14 | Emīls | Aalto `oracle` baseline (Aalto 36daf5b) + venue look with scattered layouts (`venue.yaml` `scene.layout`: 3–6 objects, mat x 0.30–0.60, y 0.04–0.20, min spacing 6.5 cm) | — | sort_fixed | nominal | 3 | +3.33 ± 0.47 | 71 % (10/14) | 0 | 30.0 / 111 | PASS | Verda RTX PRO 6000 (spot). RTF 0.40. All 4 misses stayed on the table, in the trials with 5 and 6 objects; the 3-object trial was 3/3. Lower than e-002 (88 %), which used Aalto's layout band. Logs: `artifacts/eval/oracle_sort_fixed_nominal_20261114_104230/` (local, git-ignored) |
