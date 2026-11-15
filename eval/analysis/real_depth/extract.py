"""First frame of every episode of a real drop that has head depth (drop 3): depth, head image, joint angles.

Writes into <out dir>:
    depth_epNN_start.npy   (480, 640) uint16, millimetres, 0 = invalid (same as obs["head_depth"])
    head_epNN_start.png    head camera image of the same moment
    state0.npy             (episodes, 28) observation.state at frame 0: 14 arm joints, then 14 hand joints
    sheet_K.jpg            start / middle / end of each episode, 5 episodes per sheet

Usage (needs numpy, pandas, pyarrow, av, opencv-python; not in the policy image):
    python eval/analysis/real_depth/extract.py artifacts/datasets/g1_junction_drop_3 artifacts/real_frames/drop3
"""
import os
import sys

import av
import cv2
import numpy as np
import pandas as pd

d, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
e = pd.read_parquet(f"{d}/meta/episodes/chunk-000/file-000.parquet")


def grab(path, times):
    """Frames nearest to the given timestamps (s) of one video file -> {time: frame}."""
    c = av.open(path)
    st = c.streams.video[0]
    want, res, i = sorted(times), {}, 0
    for fr in c.decode(st):
        t = float(fr.pts * st.time_base)
        while i < len(want) and t >= want[i] - 1e-3:
            res[want[i]] = fr
            i += 1
        if i >= len(want):
            break
    return res


# joint angles at frame 0
df = pd.read_parquet(f"{d}/data/chunk-000/file-000.parquet", columns=["observation.state", "episode_index", "frame_index"])
f0 = df[df.frame_index == 0].sort_values("episode_index")
np.save(f"{out}/state0.npy", np.stack(f0["observation.state"].to_numpy()).astype(np.float64))

# head camera: start, 45 %, end of each episode
k = "videos/observation.images.cam_high"
times = []
for _, r in e.iterrows():
    a, b = r[f"{k}/from_timestamp"], r[f"{k}/to_timestamp"]
    times += [a + 0.02, a + 0.45 * (b - a), b - 0.1]
res = grab(f"{d}/{k}/chunk-000/file-000.mp4", times)
tiles = []
for j, t in enumerate(times):
    img = res[t].to_ndarray(format="bgr24")
    if j % 3 == 0:
        cv2.imwrite(f"{out}/head_ep{j // 3:02d}_start.png", img)
    img = img.copy()
    cv2.putText(img, f"ep{j // 3} {['start', 'mid', 'end'][j % 3]}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    tiles.append(img)
for s in range(0, len(tiles), 15):
    sheet = np.vstack([np.hstack(tiles[q:q + 3]) for q in range(s, min(s + 15, len(tiles)), 3)])
    cv2.imwrite(f"{out}/sheet_{s // 15}.jpg", cv2.resize(sheet, None, fx=0.5, fy=0.5), [cv2.IMWRITE_JPEG_QUALITY, 80])

# head depth (lossless HEVC, gray12le = millimetres): first frame of each episode
k = "videos/observation.images.head_depth"
for fi in sorted(e[f"{k}/file_index"].unique()):
    sub = e[e[f"{k}/file_index"] == fi]
    times = [r[f"{k}/from_timestamp"] + 0.02 for _, r in sub.iterrows()]
    res = grab(f"{d}/{k}/chunk-000/file-{fi:03d}.mp4", times)
    for (_, r), t in zip(sub.iterrows(), times):
        a = res[t].to_ndarray()
        ep = int(r.episode_index)
        np.save(f"{out}/depth_ep{ep:02d}_start.npy", a)
        v = a[a > 0]
        print(f"ep{ep:02d}: valid {100 * (a > 0).mean():.1f} %, median {np.median(v):.0f} mm")
