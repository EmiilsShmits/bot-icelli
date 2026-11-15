"""Per object: geometry shape vs Decision shape over time, from a decisions_v1.6.jsonl: python labels_dump.py file [seed]"""
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
want = int(sys.argv[2]) if len(sys.argv) > 2 else None
for r in rows:
    if want is not None and r.get("seed") != want:
        continue
    if r.get("type") == "labels":
        s = " | ".join(f"{x['obj']} geom={x.get('shape_geom')} d1={(x.get('d1') or {}).get('shape')} -> {x.get('shape')}" for x in r["rows"])
        print(f"{r['seed']} t={r['t']:6.2f} LABELS {s}")
    elif r.get("type") == "exec":
        print(f"{r['seed']} t={r.get('t', 0):6.2f} EXEC {json.dumps({k: r.get(k) for k in ('obj', 'side', 'bin', 'target_bin', 'shape', 'grasp')})}")
    elif r.get("type") == "grasp_check":
        print(f"{r['seed']} t={r.get('t', 0):6.2f} GRASP {json.dumps({k: v for k, v in r.items() if k not in ('seed', 'type')})[:200]}")
    elif r.get("type") == "fail":
        print(f"{r['seed']} t={r.get('t', 0):6.2f} FAIL {json.dumps({k: v for k, v in r.items() if k not in ('seed', 'type')})[:200]}")
