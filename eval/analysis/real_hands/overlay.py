"""Before/after picture: the FK hand model over two real head frames, through Aalto's calibration and turned 2.1 deg yaw / 2.3 deg down.
Run from the repo root: PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python eval/analysis/real_hands/overlay.py artifacts/eval/realcheck/hands_before_after.jpg"""
import json, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, "policy")
from aaltonomous.interface.calibration import Calibration
from decision_oracle.handeye import HandEye
cal = Calibration.load(); he = HandEye(); T = cal._T("head")
poses = json.load(open("artifacts/real_frames/poses.json"))
keys = ["g1_junction_drop_2:2002", "g1_pick_cube:4434"]
M = Image.new("RGB", (1280, 960))
for r, key in enumerate(keys):
    ds, idx = key.rsplit(":", 1); q = poses[key]
    P, N = he.cloud(q[:14], q[14:]); vis = np.einsum("ij,ij->i", N, T[:3, 3] - P) > 0
    uvz = cal.project("head", P[vis])
    for c, (du, dv, lab) in enumerate([(0, 0, "Aalto calibration"), (22, -24, "rotated 2.1 deg yaw, 2.3 deg down")]):
        im = Image.open(f"artifacts/real_frames/{ds}_head_{int(idx):06d}.jpg").convert("RGB"); d = ImageDraw.Draw(im)
        for u, v, z in uvz[::3]:
            if z > 0: d.point((u + du, v + dv), fill=(0, 255, 0))
        d.rectangle((0, 0, 330, 22), fill=(0, 0, 0)); d.text((6, 5), f"{key}: {lab}", fill=(255, 255, 255))
        M.paste(im, (c * 640, r * 480))
M.save(sys.argv[1], quality=85)
