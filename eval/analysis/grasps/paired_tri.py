"""Paired V16_TRI off vs mid (MuJoCo run with --calibs V16_TRI=off,V16_TRI=mid): per seed pair, objects sorted, and
triangle grasps held per attempt.   python3 eval/analysis/grasps/paired_tri.py artifacts/eval/mujoco/tri-v16-b"""
import glob, json, os, subprocess, sys, collections

run = sys.argv[1]
ep = {}
for f in glob.glob(f"{run}/[0-9]*/result.json"):
    r = json.load(open(f)); d = os.path.dirname(f)
    if r.get("rc") != 0 or not os.path.exists(f"{d}/eval.json"):
        continue
    t = json.load(open(f"{d}/eval.json"))["trials"][0]
    outs = [o["outcome"] for o in t["outcomes"]]
    tri = [o["outcome"] for o, l in zip(t["outcomes"], t["layout"]) if l["shape"] == "triangle"]
    ep[r["spec"]["id"]] = (r["spec"], sum(o == "correct" for o in outs), len(outs), sum(o == "correct" for o in tri), len(tri))
pairs = collections.defaultdict(dict)
for sp, c, n, tc, tn in ep.values():
    pairs[sp["seed"]][sp["calib"].split("=")[1]] = (c, n, tc, tn)
full = {s: v for s, v in pairs.items() if "off" in v and "mid" in v}
tot = {k: [0, 0, 0, 0] for k in ("off", "mid")}
better = worse = 0
for s, v in sorted(full.items()):
    for k in tot:
        tot[k] = [a + b for a, b in zip(tot[k], v[k])]
    better += v["mid"][0] > v["off"][0]; worse += v["mid"][0] < v["off"][0]
print(f"{len(full)} complete pairs ({len(ep)} episodes)")
for k, (c, n, tc, tn) in tot.items():
    print(f"  {k}: sorted {c}/{n} ({100*c/max(n,1):.0f} %), triangles {tc}/{tn} ({100*tc/max(tn,1):.0f} %)")
print(f"  per pair: mid better {better}, worse {worse}, same {len(full) - better - worse}")
out = f"/tmp/attempts_{os.path.basename(run)}.jsonl"
for k in ("off", "mid"):
    env = dict(os.environ, ATTEMPTS_OUT=out)
    subprocess.run([sys.executable, "eval/analysis/grasps/attempts.py", f"{run}:none:V16_TRI={k}"], env=env,
                   stdout=subprocess.DEVNULL, check=True)
    R = [json.loads(l) for l in open(out)]
    T = [r for r in R if r["shape"] == "triangle" and r.get("true_shape") == "triangle" and r["held"] is not None]
    C = collections.defaultdict(lambda: [0, 0])
    for r in R:
        if r["held"] is not None and r.get("true_shape") == r["shape"]:
            C[r["shape"]][0] += r["held"]; C[r["shape"]][1] += 1
    print(f"  {k}: held per attempt " + ", ".join(f"{s} {a}/{b}" for s, (a, b) in sorted(C.items())))
