"""Every grasp attempt in MuJoCo stress runs, from the policy's decision logs: one row per executed plan.

    python3 eval/analysis/grasps/attempts.py artifacts/eval/mujoco/lean-v16-a:none artifacts/eval/mujoco/calib-v16-a:none,camera:bins
        # run[:modes[:calib]] ... -> eval/analysis/grasps/attempts.jsonl (or $ATTEMPTS_OUT) and a summary
Fields: shape, arm, grasp (stock / faceN[pXX] / ridge...), route, x, y (pelvis, m, from the look before the plan),
yaw_deg, cross (object on the other arm's side, m past the centre line), held (grasp check), err (m, grasp check),
attempt (n-th try on this object), sorted (the object's final outcome, matched to the true layout by position).
"""
import glob, json, os, sys
import numpy as np

rows = []
for arg in sys.argv[1:]:
    parts = arg.split(":")
    run, modes = parts[0], (parts[1].split(",") if len(parts) > 1 else None)
    calib = parts[2] if len(parts) > 2 else None
    for ep in sorted(glob.glob(f"{run}/[0-9]*/result.json")):
        r = json.load(open(ep)); s = r["spec"]
        if modes and s["mode"] not in modes: continue
        if calib and s.get("calib", "bins") != calib: continue
        d = os.path.dirname(ep)
        try:
            ev = json.load(open(f"{d}/eval.json"))["trials"][0]
        except Exception:
            continue
        # true objects: layout (mat) -> pelvis xy (origin 0.14, -0.45), outcome by name order
        lay = ev["layout"]; outs = {o["name"]: o["outcome"] for o in ev["outcomes"]}
        truth = []
        for o in lay:
            nm = [n for n in outs if n.startswith(f"obj_{o['color']}_{o['shape']}_")]
            truth.append((0.14 + o["y"], -0.45 + o["x"], o["shape"], o["color"], nm))
        last_xy, tries, pending = {}, {}, None
        for ln in open(f"{d}/decisions_v1.6.jsonl"):
            e = json.loads(ln); t = e.get("type")
            if t == "look":
                for dd in e.get("dets", []):
                    last_xy[dd["obj"]] = (dd["xy"][0], dd["xy"][1], dd.get("yaw_deg"))
            elif t == "exec":
                o = e["option"]; ob = o["obj"]
                tries[ob] = tries.get(ob, 0) + 1
                x, y, yaw = last_xy.get(ob, (np.nan, np.nan, None))
                side = 1.0 if o["arm"] == "left" else -1.0          # left arm works at +y
                pending = dict(run=os.path.basename(run), ep=os.path.basename(d), mode=s["mode"], calib=s.get("calib", "bins"),
                               task=s["task"], obj=ob, color=o.get("color"), shape=o.get("shape"), arm=o["arm"],
                               grasp=o["grasp"], route=o.get("route"), finger_deg=o.get("finger_deg"), face_deg=o.get("face_deg"),
                               x=x, y=y, yaw_deg=yaw, cross=float(-side * y), attempt=tries[ob], held=None, err=None, t=e["t"])
                rows.append(pending)
            elif t == "grasp_check" and pending is not None and e["obj"] == pending["obj"]:
                pending["held"], pending["err"] = (not e["empty"]), e["err"]
        # final outcome per detected object: nearest true object to its first seen position
        for rw in rows:
            if rw["ep"] != os.path.basename(d) or rw["run"] != os.path.basename(run) or "sorted" in rw: continue
            if not np.isfinite(rw["x"]): rw["sorted"] = None; continue
            dist = [np.hypot(rw["x"] - tx, rw["y"] - ty) for tx, ty, *_ in truth]
            k = int(np.argmin(dist)); tx, ty, tsh, tcol, nm = truth[k]
            rw["true_shape"] = tsh
            rw["sorted"] = (outs.get(nm[0]) == "correct") if nm and dist[k] < 0.05 else None
os.makedirs("eval/analysis/grasps", exist_ok=True)
with open(os.environ.get("ATTEMPTS_OUT", "eval/analysis/grasps/attempts.jsonl"), "w") as f:
    for rw in rows: f.write(json.dumps(rw) + "\n")
print(len(rows), "attempts,", sum(r["held"] is not None for r in rows), "with a grasp check")
