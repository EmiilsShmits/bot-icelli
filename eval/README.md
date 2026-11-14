# eval/: scoring policies in sim

**Purpose:** _to be agreed._
**Owner:** _TBD_

## How to run: baseline vs our image on a bare-metal sim machine (what we use)
1. Machine and sim: `docs/runbooks/verda-sim-setup.md` (one script: `sim/install_bare_metal.sh`).
2. Build our image on the machine: `git clone --recurse-submodules https://github.com/EmiilsShmits/bot-icelli.git && cd bot-icelli && make docker-build POLICY=v1 IMAGE=bot-icelli/policy:v1`
3. Copy the scripts over and start them in tmux, so they keep running when SSH drops:
   ```bash
   scp eval/compare.sh eval/summarize.py eval/queue.sh root@<ip>:~/
   ssh root@<ip> "tmux new -d -s eval 'bash ~/compare.sh; exec bash'"    # Aalto's baseline vs v1, sort_fixed + sort_language, seeds 1000-1009
   ssh root@<ip> "tmux new -d -s queue 'bash ~/queue.sh; exec bash'"     # afterwards: the same with AALTO_DR=train, then with the venue look
   ```
   - `compare.sh` runs Aalto's evaluator (`aalto.sh eval`): the baseline as a local policy server, our policy as the real submission image (`--container`). Options as env vars: `TRIALS`, `SEED`, `TASKS`, `POLICIES` (`baseline`, `v1` or any image tag), `IMAGE`.
   - `queue.sh` waits for a running `compare.sh`, then restarts the sim per phase (`PHASES="dr venue"`).
4. Results: one folder per run in `~/runs/eval/` (`eval.json` + per-episode logs). Table of all runs: `ssh root@<ip> python3 ~/summarize.py` (add `--trials` for one row per trial). Watch live: `ssh -t root@<ip> tmux attach -t eval` (detach: Ctrl-b d).

**Two sims on one machine:** one sim uses ~15 of the RTX PRO 6000 machine's 30 cores, and a 10-trial run takes ~20–30 min. `eval/start_sim_b.sh` starts a second sim with its own ports (`AALTO_DR=train bash ~/start_sim_b.sh`, inside tmux `simb`); point a second comparison at it with `AALTO_INSTANCE=b PORT=8001 bash ~/compare.sh`. Stop it with `kill -INT $(cat ~/sim_b.pid)`, never `aalto.sh stop` (that stops whichever sim it finds first). `queue.sh` stops sim b before its own phases.

**Three lanes on one machine (Sat 14 Nov evening):** sim A = Aalto's nominal scene, sim B = `AALTO_DR=train` (closest to the held-out variant that picks finalists), sim C = Emīls's venue look (closest to the real robot). `eval/venue_lane.sh` starts sim C (instance c, its own ports) in the venue look, installs the look on first use (patches Aalto's clone on the machine: with `AALTO_LOOK` / `AALTO_SCENE` unset the other sims are unaffected), runs `compare.sh` on port 8002 with 6 trials from seed 1000 (the seeds of Emīls's venue runs e-004…e-022), prefixes those run folders `VENUE-` (Aalto names folders by randomisation, not by look) and stops sim C at the end: `RUNS="bot-icelli/policy:v1.4 baseline" tmux new -d -s venue 'bash ~/venue_lane.sh; exec bash'`. `eval/after.sh` starts a run when another one has finished, without stopping anything. Three sims slow each other (RTF ~0.17–0.25): a 10-trial run then takes ~60–80 min.

**Never `--container` without `--policy`:** Aalto's `evaluate.py` checks `--policy` (default `oracle`) first, so `--container IMAGE` alone silently runs the privileged oracle instead of the image. That happened to our first "v1" run (e-010). `compare.sh` passes both since 9b0e59c.

**What failed, and why:** [`analysis/`](analysis/) turns run folders into grasp-by-grasp tables. Results: [`analysis/FINDINGS.md`](analysis/FINDINGS.md). `analysis/traced_eval.py` can replace `aalto.sh eval` to also record object positions, the container's log and video. It has not been run end-to-end yet: test it on one trial first.

**Docker-path sim (Aalto's image):** start a policy server on :8000 (`make serve`, or `docker run -d --gpus all -p 8000:8000 <image>`), then `make eval TASK=sort_fixed TRIALS=20` (runs `aalto eval` inside the sim container; untested). Exit 0 = gate passed, 2 = failed.

## Status
- **Now (Sat 14 Nov ~19:40, Samer + Claude):** on Samer's Verda machine (`samer-v1-sim`, spot RTX PRO 6000, FIN-03). Done: v1.2 and v1.3 nominal both 26/40, the same as the baseline (e-023, e-024); the oracle with `AALTO_DR=train` 32/40, the same as nominal (e-025). Running in three lanes (see above): sim A v1.1 nominal, then v1.3 and the baseline on sort_language; sim B v1.3 with randomisation (11/15 after 4 seeds; baseline 9/15 there), then v1.4; sim C the venue look: v1.3, the baseline, then v1.4.
- **Next:** v1.4 nominal on sim A (not queued yet: sim A's queue was set up by another session). The old `queue.sh` (tmux `queue`) still waits to run a venue phase on sim A once every `compare.sh` is done; sim C covers that now.
- **Blockers:** —

## Facts from Aalto's rules
- **The sim gate** (required to reach the finals):
  - no abort, watchdog, crash or lost connection
  - **0 clipped steps**
  - **≥ 27 Hz command rate**, on the sim clock *and* by the policy's own latency (`policy_hz_rt`)
- **Finalist selection:** organisers score on a **held-out** sim variant (different textures, lighting, object poses, camera jitter; secret seeds).
- **Points per object:**
  - `sort_fixed`: +1 correct bin
  - `sort_language`: +2 correct bin
  - −1 wrong bin or knocked off
  - 0 left on the counter
