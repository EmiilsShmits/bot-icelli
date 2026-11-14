"""Tile the sim's three camera snapshots over the real images of one frame (left wrist, right wrist, head).

    python compare.py <sim_snap_dir> <real_dir> <dataset>:<frame> <out.jpg>

<sim_snap_dir> is what `aalto.sh snap --out` wrote (head_camera.jpg, left_wrist_camera.jpg, right_wrist_camera.jpg);
<real_dir> is the output folder of real_frames.py. Put the sim robot in the same pose first (pose_from_real.py).
"""
import sys
import cv2, numpy as np
snap, real, key, out = sys.argv[1:5]
ds, f = key.split(":")
def row(files, label):
    r = np.hstack([cv2.resize(cv2.imread(p), (640, 480)) for p in files])
    cv2.rectangle(r, (0, 0), (90, 34), (0, 0, 0), -1)
    cv2.putText(r, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return r
sim = row([f"{snap}/{c}_camera.jpg" for c in ("left_wrist", "right_wrist", "head")], "sim")
rl = row([f"{real}/{ds}_{c}_{int(f):06d}.jpg" for c in ("left_wrist", "right_wrist", "head")], "real")
cv2.imwrite(out, np.vstack([sim, rl]), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(out)
