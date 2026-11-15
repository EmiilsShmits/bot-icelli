"""Standing-triangle grasps: held rate by arm and by finger angle vs the nearest apex (mod 120 deg), from every
decision log under artifacts/eval (deduplicated). Isaac runs by default, MuJoCo runs with --mj.
Usage: python3 eval/analysis/grasps/tri_angle.py [--mj]"""
import json,glob,collections,sys
import hashlib; seen=set(); files=[]
for f in glob.glob("artifacts/eval/**/decisions_v1.*.jsonl",recursive=True):
    if ("mujoco" in f) != ("--mj" in sys.argv): continue
    h=hashlib.md5(open(f,"rb").read()).hexdigest()
    if h in seen: continue
    seen.add(h); files.append(f)
rows=[]
for f in files:
    yaw={}; pend=None
    for l in open(f):
        e=json.loads(l); t=e.get("type")
        if t=="look":
            for d in e.get("dets",[]): yaw[d["obj"]]=d.get("yaw_deg")
        elif t=="exec":
            o=e["option"]
            pend=dict(f=f,obj=o["obj"],shape=o.get("shape"),arm=o["arm"],grasp=o["grasp"],fd=o.get("finger_deg"),yaw=yaw.get(o["obj"]),held=None)
            rows.append(pend)
        elif t=="grasp_check" and pend and e["obj"]==pend["obj"] and pend["held"] is None:
            pend["held"]=not e["empty"]
T=[r for r in rows if r["shape"]=="triangle" and r["held"] is not None]
print(len(files),"files",len(T),"triangle attempts with a check")
for arm in ("left","right"):
    h=collections.defaultdict(lambda:[0,0]); g=collections.defaultdict(lambda:[0,0])
    for r in T:
        if r["arm"]!=arm: continue
        g[r["grasp"]][0]+=r["held"]; g[r["grasp"]][1]+=1
        if r["fd"] is None or r["yaw"] is None: continue
        p=(r["fd"]-r["yaw"]-90)%120; b=int(p//10*10); h[b][0]+=r["held"]; h[b][1]+=1
    print(arm,"  ".join("%d:%d/%d"%(b,*h[b]) for b in sorted(h)))
    print("   ",{k:"%d/%d"%tuple(v) for k,v in g.items()})
