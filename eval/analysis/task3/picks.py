"""Every task-3 pick: seed, t, colour, arm, target, planned IK max_err, grasp check, and the shape labels just before
it (geometry, Decision 1, final). python picks.py <downloaded Modal tag folder: policy.log + runs/decisions_v1.6.jsonl>"""
import json, os, re, sys
d = sys.argv[1]
seed, rows = None, []
labels = {}
dlog = os.path.join(d, "runs", "decisions_v1.6.jsonl")
if not os.path.exists(dlog):
    dlog = os.path.join(d, "decisions.jsonl")
for l in open(dlog, encoding="utf-8"):
    r = json.loads(l)
    if r.get("type") == "labels":
        labels.setdefault(r["seed"], []).append((r["t"], {x.get("color"): (x.get("shape_geom"), (x.get("d1") or {}).get("shape"), x.get("shape")) for x in r["rows"]}))
out = []
for line in open(os.path.join(d, "policy.log"), encoding="utf-8", errors="replace"):
    m = re.search(r"reset task=\S+ seed=(\d+)", line)
    if m:
        seed = int(m.group(1)); continue
    m = re.search(r"\[classical t=\s*([\d.]+)\] execute (\w+)\s+(\w+)\s+arm -> (.*?) bin .*max_err=([\d.]+)mm max_tilt=(\d+)deg", line)
    if m:
        t, col, arm, tgt, err, tilt = float(m.group(1)), m.group(2), m.group(3), m.group(4), float(m.group(5)), int(m.group(6))
        lab = None
        for lt, lr in labels.get(seed, []):
            if lt <= t + 0.5:
                lab = lr.get(col)
        out.append([seed, t, col, arm, tgt, err, tilt, lab, ""])
        continue
    m = re.search(r"\[classical t=\s*([\d.]+)\] grasp check: (.*)", line)
    if m and out:
        out[-1][8] = m.group(2)[:40]
for o in out:
    s, t, col, arm, tgt, err, tilt, lab, gc = o
    print(f"{s} t={t:6.1f} {col:6} {arm:5} -> {tgt:24} err={err:3.1f}mm tilt={tilt:2d} labels(geom,d1,final)={lab} {gc}")
