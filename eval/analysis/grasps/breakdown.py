"""Held rate of grasp attempts (attempts.jsonl) by factor."""
import json, re, sys, collections
import numpy as np
R = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "eval/analysis/grasps/attempts.jsonl")]
def kind(g):
    if g.startswith("ridge"): return "ridge"
    if g == "stock": return "stock"
    m = re.match(r"face\d(p\d+)?", g)
    return ("face+turn" if m and m.group(1) else "face") if m else g
for r in R:
    r["kind"] = kind(r["grasp"])
    r["xb"] = "x<0.22" if r["x"] < 0.22 else ("0.22-0.28" if r["x"] < 0.28 else "x>=0.28")
    r["cb"] = "cross>3cm" if r["cross"] > 0.03 else "own side"
    r["try"] = "1st" if r["attempt"] == 1 else ("2nd" if r["attempt"] == 2 else "3rd+")
def table(keys, rows=R, min_n=5):
    c = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        k = tuple(r[x] for x in keys); c[k][0] += 1; c[k][1] += bool(r["held"])
    print(f"\n## held by {' x '.join(keys)}")
    for k, (n, h) in sorted(c.items(), key=lambda kv: (str(kv[0]))):
        if n >= min_n: print(f"  {' / '.join(map(str, k)):38s} {h:4d}/{n:<4d} {100 * h / n:5.1f} %")
print(f"attempts {len(R)}, held {sum(bool(r['held']) for r in R)} ({100 * np.mean([bool(r['held']) for r in R]):.0f} %)")
table(["run"])
table(["shape"])
table(["shape", "kind"])
table(["shape", "arm"])
table(["shape", "xb"])
table(["shape", "cb"])
table(["shape", "try"])
# objects: tried, ever held, sorted
objs = collections.defaultdict(list)
for r in R: objs[(r["run"], r["ep"], r["obj"])].append(r)
c = collections.defaultdict(lambda: [0, 0, 0, 0])
for k, rs in objs.items():
    sh = rs[0]["shape"]; c[sh][0] += 1; c[sh][1] += any(r["held"] for r in rs); c[sh][2] += bool(rs[0].get("sorted")); c[sh][3] += len(rs)
print("\n## objects: tried / ever held / sorted / attempts per object")
for sh, (n, h, s, a) in sorted(c.items()): print(f"  {sh:9s} {n:4d}  held {h:4d} ({100*h/n:.0f} %)  sorted {s:4d} ({100*s/n:.0f} %)  {a/n:.1f} tries")
held_not_sorted = [r for k, rs in objs.items() for r in rs[:1] if any(x["held"] for x in rs) and rs[0].get("sorted") is False]
print(f"\nheld at some point but not sorted: {len(held_not_sorted)} objects, by shape {collections.Counter(r['shape'] for r in held_not_sorted)}")
mism = [r for r in R if r.get("true_shape") and r["true_shape"] != r["shape"]]
print(f"attempts whose detected shape differs from the true one: {len(mism)} {collections.Counter((r['true_shape'], r['shape']) for r in mism).most_common(5)}")
