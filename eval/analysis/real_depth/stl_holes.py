"""Lid STL -> holes: kind, centre, inscribed / circumscribed radius, pointing direction of the triangle.
Usage: stl_holes.py <file.stl> [z of the face to read, default lowest] [scale to mm, default 1]"""
import sys, struct, numpy as np
p = sys.argv[1]
raw = open(p, "rb").read()
if raw[:5] == b"solid" and b"facet" in raw[:400]:
    vals = [float(x) for line in raw.decode("ascii", "ignore").splitlines() if line.strip().startswith("vertex") for x in line.split()[1:4]]
    tri = np.array(vals, float).reshape(-1, 3, 3)
else:
    n = struct.unpack("<I", raw[80:84])[0]
    a = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
    tri = a["v"].astype(float)
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
tri = tri * scale
lo, hi = tri.reshape(-1, 3).min(0), tri.reshape(-1, 3).max(0)
print("size (mm)", np.round(hi - lo, 2), "min", np.round(lo, 2), "z levels", np.unique(np.round(tri[:, :, 2].reshape(-1), 2))[:8])
ZL = float(sys.argv[2]) * scale if len(sys.argv) > 2 and sys.argv[2] != "-" else lo[2]
nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
face = (np.abs(nrm[:, 2]) > 0.99) & (np.abs(tri[:, :, 2] - ZL).max(1) < 1e-3)
key = lambda v: (round(float(v[0]), 2), round(float(v[1]), 2))
edges = {}
for t in tri[face]:
    ks = [key(v) for v in t]
    for i in range(3):
        e = tuple(sorted((ks[i], ks[(i + 1) % 3]))); edges[e] = edges.get(e, 0) + 1
adj = {}
for (a_, b_), c in edges.items():
    if c == 1:
        adj.setdefault(a_, []).append(b_); adj.setdefault(b_, []).append(a_)
seen, loops = set(), []
for start in adj:
    if start in seen: continue
    loop, cur, prev = [start], start, None; seen.add(start)
    while True:
        nxt = [q for q in adj[cur] if q != prev and q not in seen]
        if not nxt: break
        prev, cur = cur, nxt[0]; seen.add(cur); loop.append(cur)
    loops.append(np.array(loop))
def area_centroid(P):
    x, y = P[:, 0], P[:, 1]; x1, y1 = np.roll(x, -1), np.roll(y, -1); cr = x * y1 - x1 * y; A = cr.sum() / 2
    return abs(A), np.array([((x + x1) * cr).sum(), ((y + y1) * cr).sum()]) / (6 * A)
def seg_dist(c, P):
    A_, B_ = P, np.roll(P, -1, axis=0); d = B_ - A_
    t = np.clip(((c - A_) * d).sum(1) / np.maximum((d * d).sum(1), 1e-12), 0, 1)
    return np.linalg.norm(A_ + t[:, None] * d - c, axis=1)
centre = (lo[:2] + hi[:2]) / 2
for L in sorted(loops, key=lambda L: -area_centroid(L)[0])[1:]:
    A, c = area_centroid(L)
    r_in, r_out = seg_dist(c, L).min(), np.linalg.norm(L - c, axis=1).max()
    ratio = A / (np.pi * r_in ** 2)
    kind = "circle" if r_out - r_in < 0.3 else ("square" if abs(A / (2 * r_in) ** 2 - 1) < 0.06 else "triangle")
    extra = ""
    if kind == "triangle":
        far = L[np.argmax(np.linalg.norm(L - c, axis=1))] - c          # one tip; the three tips are 120 deg apart
        tips = sorted({int(round(np.degrees(np.arctan2(q[1], q[0])) / 10.0)) * 10 for q in (L - c)[np.linalg.norm(L - c, axis=1) > r_out - 0.6]})
        extra = f" tips at angles {tips} deg (0 = +x, 90 = +y)"
    print(f"  {kind:8s} centre from lid centre ({c[0] - centre[0]:+6.1f}, {c[1] - centre[1]:+6.1f}) mm | inscribed radius {r_in:5.2f} | farthest point {r_out:5.2f} | extent {np.round(L.max(0) - L.min(0), 1)}{extra}")
