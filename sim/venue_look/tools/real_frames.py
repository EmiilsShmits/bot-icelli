"""Take frames out of one of Aalto's real datasets: the three camera images and the joint angles at that moment.

    python real_frames.py <dataset_dir> <out_dir> --frames 0 150      # these frames
    python real_frames.py <dataset_dir> <out_dir> --n 30              # 30 frames spread over the dataset

Writes <out_dir>/<dataset>_<camera>_<frame>.jpg (camera = head, left_wrist, right_wrist) and adds
"<dataset>:<frame>" -> 28 joint values to <out_dir>/poses.json (the input of pose_from_real.py and the fits).
<dataset_dir> is a LeRobot v3 folder with one data file and one video per camera (true for both drops so far).
"""
import argparse, glob, json, os
import cv2, numpy as np
import pyarrow.parquet as pq

CAMS = {"head": "cam_high", "left_wrist": "cam_left_wrist", "right_wrist": "cam_right_wrist"}
ap = argparse.ArgumentParser()
ap.add_argument("dataset"); ap.add_argument("out")
ap.add_argument("--frames", type=int, nargs="*"); ap.add_argument("--n", type=int, default=0)
a = ap.parse_args()
ds = os.path.basename(os.path.normpath(a.dataset))
data = sorted(glob.glob(f"{a.dataset}/data/*/*.parquet"))
assert len(data) == 1, f"expected one data file, found {len(data)}"
state = np.stack(pq.read_table(data[0], columns=["observation.state"]).to_pandas()["observation.state"].values)
frames = list(a.frames or []) + ([int(v) for v in np.linspace(0, len(state) - 30, a.n)] if a.n else [])
assert frames, "give --frames or --n"
os.makedirs(a.out, exist_ok=True)
pj = f"{a.out}/poses.json"
poses = json.load(open(pj)) if os.path.exists(pj) else {}
for name, key in CAMS.items():
    vids = sorted(glob.glob(f"{a.dataset}/videos/observation.images.{key}/*/*.mp4"))
    assert len(vids) == 1, f"expected one {key} video, found {len(vids)}"
    cap = cv2.VideoCapture(vids[0])
    for f in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, img = cap.read()
        assert ok, f"{key}: no frame {f}"
        cv2.imwrite(f"{a.out}/{ds}_{name}_{f:06d}.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
for f in frames:
    poses[f"{ds}:{f}"] = [round(float(v), 5) for v in state[f]]
json.dump(poses, open(pj, "w"))
print(f"{len(frames)} frames of {ds} -> {a.out} ({len(poses)} poses in poses.json)")
