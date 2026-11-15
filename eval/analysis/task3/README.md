# eval/analysis/task3: task-3 (insert_shapes) runs, pick by pick

## Purpose
Shows what happens to each block in our task-3 Modal runs: the outcome per shape, each pick's planned IK error and
grasp check, and the shape labels the planner saw. These scripts produced the numbers in `eval/RESULTS.md`
e-073 … e-077 and the `LID_PICK_TOL` change in `policy/decision_oracle/insert.py`.

## Owner
Samer (with Claude, Sun 15 Nov ~03:00–04:00)

## Inputs → Outputs
- **In:** one Modal run per tag on the volume `aalto-sim-out`, which holds `policy.log`, `runs/decisions_v1.6.jsonl` and
  `runs/eval/<run>/eval.json` (+ `episode_NNN.mp4` head-camera videos).
- **Out:** printed tables. Nothing is written.

## How to run (repo root)
```bash
# download a tag (on Windows: modal.exe from the junction2026 venv, see docs/runbooks/modal-windows.md)
modal volume get aalto-sim-out t3-pt2-1003 sim_out/
python eval/analysis/task3/t3_collect.py sim_out t3-pt2-1003 t3-pt0-1003   # outcome per shape, per seed
python eval/analysis/task3/picks.py sim_out/t3-pt2-1003                     # each pick: IK error, grasp check, labels
python eval/analysis/task3/labels_dump.py sim_out/t3-pt2-1003/runs/decisions_v1.6.jsonl 1003   # labels over time
# offline IK probe, on the sim machine, in a v1.6 image with the repo's policy/ mounted over the image's copy
docker run --rm -v ~/bot-icelli/policy:/app/policy:ro -v ~/bot-icelli/eval/analysis/task3:/probe \
  --entrypoint bash bot-icelli/policy:final-v16 \
  -c "cd /app/policy && PYTHONPATH=/app:/app/policy python3 /probe/pick_ik_probe.py"
```
Tags run on Sun 15 Nov: `t3-v16-e`, `t3-v16-f`, `t3-gapp8-1003`, `t3-gapm12-{1000,1003}`, `t3-gapm12-h60-{1000,1003}`,
`t3-gapm12-h60-d06-{1000,1003}`, `t3-pt2-{1000,1003,1006}`, `t3-pt0-{1003,1006}` (settings in `eval/RESULTS.md`).

## Status
- **Now:** e-073 … e-077 done. Cylinders go in ~2 times in 3; cubes 0/16 and triangles 1/24 under every release
  setting, so `insert.py` tries cylinders only. Before `LID_PICK_TOL`, cylinder picks planned within 1.5 mm grasped
  18/18 and picks at 2.2–5.8 mm 6/12; the probe showed the 5–6 mm came from the straight descent, not the grasp IK.
- **Seen, not acted on:** a cylinder knocked over by a missed grab reads "cube" to the depth geometry while Decision 1
  still says "cylinder", so it is sent to the round hole lying down. Two such attempts so far: one went in, one ended
  on the lid (−1), so they are not filtered out.
- **Next:** the real robot (Aalto's lid on the middle box, boxes ~7 cm closer): see `docs/CONTEXT.md` §3–4.
- **Blockers:** —

## Gotchas
- `pick_ik_probe.py` sets `LID_PICK_TOL` in `os.environ` around each plan: `insert.settings()` is read at plan time.
- The image leaves out `decision_oracle/test_*.py`, so the probe needs the repo's `policy/` mounted (above).
- `t3_collect.py` reads the shape from the object's name (`obj_<colour>_<shape>_<n>`), as Aalto's evaluator names them.
