"""Every 3rd depth frame of each drop-3 episode + the joint state of that frame and its neighbours' speed."""
import sys, av, numpy as np, pandas as pd
d, out = sys.argv[1], sys.argv[2]
e = pd.read_parquet(f"{d}/meta/episodes/chunk-000/file-000.parquet")
df = pd.read_parquet(f"{d}/data/chunk-000/file-000.parquet", columns=["observation.state", "action", "episode_index", "frame_index", "timestamp"])
k = "videos/observation.images.head_depth"
print(e[[c for c in e.columns if "head_depth" in c or c in ("episode_index", "length")]].to_string())
D, S, A, EP, FR, SP = [], [], [], [], [], []
for fi in sorted(e[f"{k}/file_index"].unique()):
    sub = e[e[f"{k}/file_index"] == fi]
    c = av.open(f"{d}/{k}/chunk-000/file-{fi:03d}.mp4"); st = c.streams.video[0]
    frames = [(float(fr.pts * st.time_base), fr.to_ndarray()) for fr in c.decode(st)]
    ts = np.array([t for t, _ in frames])
    for _, r in sub.iterrows():
        ep = int(r.episode_index)
        g = df[df.episode_index == ep].sort_values("frame_index")
        X = np.stack(g["observation.state"].to_numpy()).astype(float); Act = np.stack(g["action"].to_numpy()).astype(float)
        t0 = r[f"{k}/from_timestamp"]
        for i in range(0, len(g), 3):
            j = int(np.argmin(np.abs(ts - (t0 + i / 30.0))))
            if abs(ts[j] - (t0 + i / 30.0)) > 0.02: continue
            lo, hi = max(0, i - 3), min(len(g) - 1, i + 3)
            SP.append(np.abs(X[hi, :14] - X[lo, :14]).reshape(2, 7).max(1) / ((hi - lo) / 30.0))   # rad/s per arm
            D.append(frames[j][1].astype(np.uint16)); S.append(X[i]); A.append(Act[i]); EP.append(ep); FR.append(i)
        print("ep", ep, "frames", len(g), flush=True)
np.savez_compressed(f"{out}/drop3_mid.npz", depth=np.stack(D), state=np.stack(S), action=np.stack(A), ep=np.array(EP), fr=np.array(FR), speed=np.stack(SP))
print("saved", len(D))
