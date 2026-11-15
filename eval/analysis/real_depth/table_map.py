"""Top-down map of the real table from one drop-3 depth frame: table plane by RANSAC, then points by height.
Frame: origin = point on the table straight below the camera, x = forward (camera axis on the table), y = left.
Usage: bins_real.py <frames dir> <out dir> ep [ep ...]"""
import sys, numpy as np, cv2
src, out, eps = sys.argv[1], sys.argv[2], [int(e) for e in sys.argv[3:]]
FX, FY, CX, CY = 604.827, 604.298, 325.042, 250.927      # head camera intrinsics from Aalto's calibration.yaml
u, v = np.meshgrid(np.arange(640), np.arange(480))
rng = np.random.default_rng(0)
for ep in eps:
    d = np.load(f"{src}/depth_ep{ep:02d}_start.npy").astype(np.float64) / 1000.0
    ok = (d > 0.15) & (d < 1.6)
    P = np.stack([(u - CX) * d / FX, (v - CY) * d / FY, d], -1)[ok]
    best = None
    for _ in range(400):
        a, b, c = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
        if nn < 1e-9: continue
        n /= nn; off = n @ a
        cnt = int((np.abs(P @ n - off) < 0.004).sum())
        if best is None or cnt > best[0]: best = (cnt, n, off)
    cnt, n, off = best
    inl = np.abs(P @ n - off) < 0.004
    c0 = P[inl].mean(0)                                         # refine: least squares on the inliers
    n = np.linalg.svd(P[inl][::7] - c0, full_matrices=False)[2][-1]; n /= np.linalg.norm(n)
    off = n @ c0
    if off > 0: n, off = -n, -off                               # n points from the table to the camera
    h = P @ n - off                                             # height above the table
    cam_h = -off
    res = (P[inl] @ n - off)
    z = n; fwd = np.array([0, 0, 1.0]) - z * z[2]; fwd /= np.linalg.norm(fwd); left = np.cross(z, fwd)
    X, Y = P @ fwd, P @ left
    print(f"ep{ep:02d}: table inliers {100 * inl.mean():.0f}% of valid, plane noise rms {1000 * res.std():.1f} mm, camera {100 * cam_h:.1f} cm above the table, "
          f"optical axis {np.degrees(np.arccos(np.clip(-(z[2]), -1, 1))):.1f} deg from straight down")
    # top-down map, 2 mm cells: x 0..0.9 forward, y -0.5..0.5
    R = 0.002; W_, H_ = int(1.0 / R), int(0.9 / R)
    img = np.zeros((H_, W_, 3), np.uint8)
    def put(mask, col):
        xi = ((X[mask]) / R).astype(int); yi = ((0.5 - Y[mask]) / R).astype(int)
        g = (xi >= 0) & (xi < H_) & (yi >= 0) & (yi < W_)
        img[H_ - 1 - xi[g], yi[g]] = col
    put(np.abs(h) < 0.006, (70, 70, 70))                        # table / bin floors
    put((h > 0.015) & (h < 0.05), (0, 200, 255))                # objects (and low hand parts)
    put((h >= 0.05) & (h < 0.09), (0, 80, 255))                 # bin rims
    put(h >= 0.09, (255, 120, 0))                               # hands / arms
    for k in range(0, 19):                                      # 5 cm grid, labels every 10 cm
        xx = H_ - 1 - int(k * 0.05 / R)
        cv2.line(img, (0, xx), (W_ - 1, xx), (40, 90, 40) if k % 2 else (60, 160, 60), 1)
        if k % 2 == 0: cv2.putText(img, f"x {k * 5}", (2, xx - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 220, 60), 1)
    for k in range(0, 21):
        yy = int(k * 0.05 / R)
        cv2.line(img, (yy, 0), (yy, H_ - 1), (40, 90, 40) if k % 2 else (60, 160, 60), 1)
        if k % 2 == 0: cv2.putText(img, f"{50 - k * 5}", (yy + 2, H_ - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 220, 60), 1)
    cv2.imwrite(f"{out}/top_ep{ep:02d}.png", img)
    # rim statistics: per 1 cm lateral band, nearest and farthest rim point; rim height
    rim = (h >= 0.045) & (h < 0.095) & (X > 0.3)
    print(f"   rim points {rim.sum()}, rim height (95th pct of 4.5-9.5 cm band) {100 * np.percentile(h[rim], 95):.1f} cm, median {100 * np.median(h[rim]):.1f} cm")
    ys = np.arange(-0.40, 0.40, 0.01)
    occ = np.array([((Y[rim] >= y) & (Y[rim] < y + 0.01)).sum() for y in ys])
    near = [np.percentile(X[rim][(Y[rim] >= y) & (Y[rim] < y + 0.01)], 2) if o > 30 else np.nan for y, o in zip(ys, occ)]
    print("   lateral y (cm): rim-point count per 1 cm band")
    print("   " + " ".join(f"{int(100 * y):+d}:{o}" for y, o in zip(ys, occ) if abs(y) < 0.36))
    print("   near wall x (cm) per band: " + " ".join(f"{int(100 * y):+d}:{100 * x:.0f}" for y, x in zip(ys, near) if not np.isnan(x)))
