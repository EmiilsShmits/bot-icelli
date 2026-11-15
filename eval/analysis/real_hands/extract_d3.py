"""Drop 3: pick still moments (arms not moving), decode head depth + colour there, save with the joint angles."""
import json, os, sys
import numpy as np, pandas as pd, av
R = sys.argv[1]; OUT = sys.argv[2]
info = json.load(open(f"{R}/meta/info.json"))
print(info["features"]["observation.state"]["names"][0][14:21])
d = pd.read_parquet(f"{R}/data/chunk-000/file-000.parquet")
ep = pd.read_parquet(f"{R}/meta/episodes/chunk-000/file-000.parquet")
S = np.stack(d["observation.state"].to_numpy()).astype(float)
epi, fi = d["episode_index"].to_numpy(), d["frame_index"].to_numpy()
picks = []
for e in sorted(set(epi)):
    rows = np.flatnonzero(epi == e)
    q = S[rows, :14]
    still = [k for k in range(10, len(rows) - 10) if np.abs(q[k - 9:k + 10] - q[k]).max() < 0.015]
    chosen = []
    for k in still:                                  # spread: at least 40 frames and 0.1 rad apart
        if all(abs(k - c) > 40 and np.abs(q[k] - q[c]).max() > 0.1 for c in chosen):
            chosen.append(k)
    chosen = ([0] if np.abs(q[:10] - q[0]).max() < 0.015 else []) + chosen
    for k in chosen[:3]:
        picks.append((int(e), int(fi[rows[k]]), S[rows[k]]))
print(len(picks), "still moments")

def decode(key, e, want, fmt):
    r = ep[ep["episode_index"] == e].iloc[0]
    f = f"{R}/videos/{key}/chunk-{int(r[f'videos/{key}/chunk_index']):03d}/file-{int(r[f'videos/{key}/file_index']):03d}.mp4"
    first = int(round(float(r[f"videos/{key}/from_timestamp"]) * 30))
    need = {first + i: i for i in want}
    out = {}
    c = av.open(f); s = c.streams.video[0]; tb = float(s.time_base)
    c.seek(int(max(0, (min(need) - 5) / 30) / tb), stream=s, any_frame=False, backward=True)
    for fr in c.decode(s):
        n = int(round(float(fr.pts * tb) * 30))
        if n in need:
            out[need[n]] = fr.to_ndarray(format=fmt)
        if n > max(need):
            break
    c.close()
    return out

os.makedirs(OUT, exist_ok=True)
by = {}
for e, f, s in picks:
    by.setdefault(e, []).append((f, s))
n = 0
for e, lst in by.items():
    want = [f for f, _ in lst]
    D = decode("observation.images.head_depth", e, want, "gray16le")
    C = decode("observation.images.cam_high", e, want, "rgb24")
    for f, s in lst:
        if f in D:
            np.savez_compressed(f"{OUT}/e{e:02d}_f{f:04d}.npz", depth=D[f].astype(np.uint16), rgb=C.get(f), state=s)
            n += 1
print("saved", n)
