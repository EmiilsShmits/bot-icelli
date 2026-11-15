"""Where the three boxes really stand, and the shape lid with its holes, from one head depth image.

Nothing here assumes scene.yaml's box positions, gaps or wall height: they are measured. Input is the depth points
and a LEVELLED camera pose T (table flat at counter height, z up), from any of camera.py's fits.

    find_boxes(P, T, scene)          -> the row's direction, near wall, depth, wall height, each box's centre and size
    find_lid(P, T, scene, boxes)     -> which box carries a lid, the lid's pose and the centre of each hole
    enable(cam)                      -> opt-in hook (V16_BOXES=find): the drops follow the boxes found

How the boxes are found (top-down, 2 mm cells, only points at wall height, above any object standing in a box):
1. the near wall: the front-most wall cell of every column lies on one line across all three boxes (RANSAC);
2. the wall height: the top of the points on that line;
3. the far edge: the last row behind the near wall with wall points;
4. the sides: the walls run the whole depth and the near wall stops at every gap, so along the row each box is an
   interval with a wall at both ends, wall in front, and nothing in the gap to its neighbour. Three equal boxes at an
   even pitch are fitted first, then each box's two edges on their own (the real ones are 24.0 and 23.9 cm apart).
Works for thin walls (sim), thick taped cardboard flaps (venue) and a box covered by a lid.

How the lid is found: its plate is a flat patch at one height on a box; a hole is where the camera sees THROUGH that
plane (the ray to a lower point crosses it). Plate cells (+1) and see-through cells (-1) are matched against the
known lid (4 turns x lip up / down x +-10 deg x +-2.5 cm).

Tested on Aalto's real depth (drop 3) and on rendered depth of the real lid: eval/analysis/real_depth/README.md.
"""
from __future__ import annotations

import os

import numpy as np

RES = 0.002                 # top-down cell (m)
BAND_LO = 0.053             # lowest "wall" height: above an object standing in a box (4.5 cm + 3 mm floor + margin)
BAND_HI = 0.095             # first pass only; hands and arms are higher
X0, X1, Y0, Y1 = 0.10, 0.95, -0.60, 0.60     # work area in T's frame (x forward, y left)
V0, V1 = -0.03, 0.33        # across the row, from the near wall (m)
U0, U1 = -0.60, 0.60        # along the row


# ---------------------------------------------------------------------------------------------- helpers
def _grid(a, b, a0, b0, na, nb, res=RES):
    """Boolean occupancy (na, nb) of points (a, b); cell (0, 0) starts at (a0, b0)."""
    i = np.floor((a - a0) / res).astype(int)
    j = np.floor((b - b0) / res).astype(int)
    ok = (i >= 0) & (i < na) & (j >= 0) & (j < nb)
    G = np.zeros((na, nb), bool)
    G[i[ok], j[ok]] = True
    return G


def _mean(cs, k1, k2):
    """Mean of the array behind cumulative sum `cs` over cells [k1, k2); index arrays allowed."""
    n = len(cs) - 1
    a, b = np.clip(k1, 0, n), np.clip(k2, 0, n)
    return (cs[b] - cs[a]) / np.maximum(np.asarray(k2) - np.asarray(k1), 1)


def _near_line(x, y, rng):
    """The near wall of the row as a line x = m * y + c through the front-most wall cell of every column."""
    import cv2
    G = _grid(x, y, X0, Y0, int(round((X1 - X0) / RES)), int(round((Y1 - Y0) / RES)))
    G &= cv2.boxFilter(G.astype(np.float32), -1, (3, 3), normalize=False, borderType=cv2.BORDER_CONSTANT) >= 3
    cols = np.flatnonzero(G.any(0))
    if len(cols) < 100:
        return None
    fx = X0 + (G[:, cols].argmax(0) + 0.5) * RES
    fy = Y0 + (cols + 0.5) * RES
    best = None
    for _ in range(500):
        i, j = rng.integers(len(cols), size=2)
        if abs(fy[i] - fy[j]) < 0.05:
            continue
        m = (fx[i] - fx[j]) / (fy[i] - fy[j])
        if abs(m) > 0.27:                                    # the row lies within 15 deg of the frame's y axis
            continue
        inl = np.abs(fx - (m * fy + fx[i] - m * fy[i])) < 0.005
        if best is None or inl.sum() > best.sum():
            best = inl
    if best is None or best.sum() < 100:
        return None
    for tol in (0.005, 0.004):
        m, c = np.polyfit(fy[best], fx[best], 1)
        best = np.abs(fx - (m * fy + c)) < tol
        if best.sum() < 100:
            return None
    m, c = np.polyfit(fy[best], fx[best], 1)
    return float(m), float(c), int(best.sum()), float(np.ptp(fy[best]))


# ---------------------------------------------------------------------------------------------- boxes
def find_boxes(P, T, scene, rng=None):
    """P: optical-frame points (n, 3) with valid depth; T: levelled pose (frame <- optical). -> dict:

    ok, why; yaw_deg (row vs the frame's y axis); near (m, near wall at y = 0); depth; wall (height above the table);
    gaps [left-center, center-right] (m); frame {o, e1, e2} (near-wall point, forward and leftward unit vectors);
    boxes {left | center | right: {center (frame xy), size (along the row, across), edges_found {left, right},
    far_seen (False: far wall not in view, the box is taken as square), fill, near, far}}.
    Names go by position: the box furthest to the robot's left is "left"."""
    rng = rng or np.random.default_rng(0)
    res = {"ok": False, "why": "", "boxes": {}}
    zc = scene.counter_z
    Q = np.asarray(P, np.float64) @ T[:3, :3].T + T[:3, 3]
    x, y, h = Q[:, 0], Q[:, 1], Q[:, 2] - zc
    area = (x > X0) & (x < X1) & (y > Y0) & (y < Y1) & (h > 0.03) & (h < 0.12)
    x, y, h = x[area], y[area], h[area]
    hi = (h > BAND_LO) & (h < BAND_HI)
    if hi.sum() < 400:
        res["why"] = "too few points at wall height"
        return res
    line = _near_line(x[hi], y[hi], rng)
    if line is None:
        res["why"] = "no near wall line"
        return res
    m, c, n_line, span = line
    s = float(np.hypot(1.0, m))
    e1, e2, o = np.array([1.0, -m]) / s, np.array([m, 1.0]) / s, np.array([c, 0.0])   # forward, left, origin
    v = (x - o[0]) * e1[0] + (y - o[1]) * e1[1]
    u = (x - o[0]) * e2[0] + (y - o[1]) * e2[1]
    res.update(yaw_deg=float(np.degrees(np.arctan(m))), near=c, line_cols=n_line, line_span=span,
               frame={"o": o, "e1": e1, "e2": e2})
    if span < 0.25:
        res["why"] = f"near wall line too short ({span * 100:.0f} cm)"
        return res

    on = np.abs(v) < 0.008                                   # 2. wall height: the top of the near wall
    if on.sum() < 100:
        res["why"] = "too few points on the near wall"
        return res
    wall = float(np.percentile(h[on], 95))
    res["wall"] = wall
    band = (h > max(BAND_LO, wall - 0.022)) & (h < wall + 0.014)
    nv, nu = int(round((V1 - V0) / RES)), int(round((U1 - U0) / RES))
    G = _grid(v[band], u[band], V0, U0, nv, nu)
    row = lambda vv: int(round((vv - V0) / RES))
    col = lambda uu: int(round((uu - U0) / RES))

    size0 = np.asarray(scene.cfg["bins"]["outer_size"], float)          # the boxes' outer size: a prior, +-2.5 cm
    F = np.convolve(G.sum(1).astype(float), np.ones(3) / 3, mode="same")     # 3. far edge, roughly (refined per box)
    a, b = row(0.13), row(0.30)
    depth = float(size0[1])
    if F[a:b].max() >= 25:                                   # at least 5 cm of far wall in some row
        d_ = V0 + (a + int(np.flatnonzero(F[a:b] >= 0.4 * F[a:b].max()).max()) + 1) * RES
        if abs(d_ - size0[1]) < 0.04:
            depth = float(d_)

    S = G[row(0.02):row(depth - 0.03)].mean(0)               # 4. side walls: share of the depth with wall points
    N = G[row(-0.008):row(0.012)].any(0).astype(float)       #    near wall present in this column
    cS, cN, cM = (np.r_[0.0, np.cumsum(q)] for q in (S, N, np.maximum(S, N)))
    w = 3                                                    # cells on each side of an edge

    def edge(k, inward):
        """Wall just inside cell boundary k and nothing just outside: 0 .. 2."""
        ins, outs = ((k, k + w), (k - w, k)) if inward > 0 else ((k - w, k), (k, k + w))
        return (_mean(cS, *ins) - _mean(cS, *outs)) + (_mean(cN, *ins) - _mean(cN, *outs))

    names = sorted(scene.cfg["bins"]["centers"], key=lambda n: -scene.mat_to_pelvis(
        np.r_[scene.cfg["bins"]["centers"][n], 0.0])[1])     # left to right as the robot sees them
    if len(names) != 3:
        res["why"] = "scene does not have three bins"
        return res
    mid = scene.mat_to_pelvis(np.r_[scene.cfg["bins"]["centers"][names[1]], 0.0])[:2]
    uc = float((mid - o) @ e2)
    c0 = np.arange(col(uc - 0.15), col(uc + 0.15) + 1)       # centre of the middle box, in cells
    best = (-np.inf, 0, 0, 0)
    w_lo, w_hi = int(round((size0[0] - 0.025) / RES)), int(round((size0[0] + 0.025) / RES))
    for p in range(w_lo + 1, w_hi + 46):                     # pitch = width + gap; gap 0.2 .. 9 cm
        for wd in range(max(w_lo, p - 45), min(p, w_hi + 1)):
            sc = np.zeros(len(c0))
            for i in (-1, 0, 1):
                lft = c0 + i * p - wd // 2
                sc += edge(lft, +1) + edge(lft + wd, -1) + 1.5 * _mean(cN, lft, lft + wd)
            for i in (-1, 0):
                g0 = c0 + i * p - wd // 2 + wd
                sc -= 4.0 * _mean(cM, g0, g0 + p - wd)
            k = int(np.argmax(sc))
            if sc[k] > best[0]:
                best = (float(sc[k]), int(c0[k]), p, wd)
    score, k0, p, wd = best
    res.update(score=score, pitch=p * RES, width=wd * RES)

    low = _grid(v, u, V0, U0, nv, nu)                       # every point above 3 cm: the far wall, even cut off by
    spans = []                                               # the top of the image below its rim
    for i in (1, 0, -1):                                     # left, center, right: u grows to the left
        l0 = k0 + i * p - wd // 2
        cand = np.arange(-8, 9)
        el, er = edge(l0 + cand, +1), edge(l0 + wd + cand, -1)
        dl, dr = int(cand[np.argmax(el)]), int(cand[np.argmax(er)])
        fl, fr_ = bool(el.max() > 0.5), bool(er.max() > 0.5)
        if fl and not fr_:                                   # one edge out of view: keep the fitted width
            dr = dl
        elif fr_ and not fl:
            dl = dr
        elif not fl and not fr_:
            dl = dr = 0
        spans.append((l0 + dl, l0 + wd + dr, fl, fr_, float(el.max()), float(er.max())))
    depths = []
    for name, (lft, rgt, fl, fr_, sl, sr) in zip(names, spans):
        c0_, c1_ = max(lft, 0), max(min(rgt, nu), 1)
        occ = G[:, c0_:c1_]
        frac = occ.mean(1) if occ.size else np.zeros(nv)
        nr = np.flatnonzero(frac[row(-0.016):row(0.016)] >= 0.35)       # this box's own near wall
        v_near = V0 + (row(-0.016) + nr.min()) * RES if len(nr) else 0.0
        lo_ = low[:, min(c0_ + 5, nu - 1):max(c1_ - 5, 1)]              # its far wall: a row filled across the box
        fl_ = lo_.mean(1) if lo_.size else np.zeros(nv)
        r0, r1 = row(v_near + size0[1] - 0.04), row(v_near + size0[1] + 0.04)
        fr = np.flatnonzero(fl_[r0:r1] >= 0.3)
        far_seen = len(fr) > 0
        v_far = V0 + (r0 + fr.max() + 1) * RES if far_seen else v_near + (rgt - lft) * RES
        if far_seen:
            depths.append(v_far - v_near)
        uu = U0 + (lft + rgt) / 2 * RES
        inner = G[row(v_near + 0.03):row(v_far - 0.03), min(c0_ + 15, nu - 1):max(c1_ - 15, 1)]
        res["boxes"][name] = {
            "center": o + e1 * (v_near + v_far) / 2 + e2 * uu,
            "size": (float((rgt - lft) * RES), float(v_far - v_near)),
            "edges_found": {"right": fl, "left": fr_}, "edge_score": (round(sl, 2), round(sr, 2)),
            "far_seen": far_seen, "near": float(v_near), "far": float(v_far),
            "u": (U0 + lft * RES, U0 + rgt * RES), "fill": float(inner.mean()) if inner.size else 0.0}
    res["depth"] = float(np.median(depths)) if depths else depth
    b_ = res["boxes"]
    res["gaps"] = [float(b_[names[0]]["u"][0] - b_[names[1]]["u"][1]), float(b_[names[1]]["u"][0] - b_[names[2]]["u"][1])]
    found = [b_[n]["edges_found"] for n in names]
    if not (found[1]["left"] and found[1]["right"]):
        res["why"] = "the middle box's side walls were not found"
    elif not (found[0]["right"] and found[2]["left"]):       # the side boxes' inner walls (outer ones may be out of view)
        res["why"] = "a side box's inner wall was not found"
    elif min(res["gaps"]) < -0.004:
        res["why"] = "boxes overlap"
    else:
        res["ok"], res["why"] = True, "boxes measured"
    return res


def as_bins(found, scene):
    """find_boxes result -> what CameraPerception._apply_bins takes: centres and shifts against scene.yaml."""
    cen, shift = {}, {}
    for n, b in found["boxes"].items():
        nom = scene.mat_to_pelvis(np.r_[scene.cfg["bins"]["centers"][n], 0.0])[:2]
        cen[n] = np.asarray(b["center"], float)
        shift[n] = (float(cen[n][0] - nom[0]), float(cen[n][1] - nom[1]))
    return {"centers": cen, "shift": shift, "why": f"boxes measured (wall {found['wall'] * 100:.1f} cm, gaps "
            + " / ".join(f"{g * 100:.1f}" for g in found["gaps"]) + " cm)"}


# ---------------------------------------------------------------------------------------------- lid
def _round_square(half, r, n=8):
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        a = np.linspace(0, np.pi / 2, n) + k * np.pi / 2
        pts.append(np.c_[sx * (half - r) + r * np.cos(a), sy * (half - r) + r * np.sin(a)])
    return np.vstack(pts)


def _round_triangle(inradius, rho, tip_deg=90.0, n=10):
    pts = []
    for k in range(3):
        d = np.radians(tip_deg + 120.0 * k)
        ctr = 2.0 * (inradius - rho) * np.array([np.cos(d), np.sin(d)])
        a = d + np.linspace(-np.pi / 3, np.pi / 3, n)
        pts.append(ctr + rho * np.c_[np.cos(a), np.sin(a)])
    return np.vstack(pts)


def real_lid():
    """Aalto's printed lid (lid_shape_holes_200mm.stl), SEEN FROM ABOVE WITH THE LIP DOWN: metres, lid centre = 0,
    a to the right and b away when the triangle hole is on the far side. Lip up is the mirror image (a -> -a)."""
    t = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    return {"size": 0.200, "thickness": 0.004, "holes": [
        ("cube", np.array([0.048, -0.035]), _round_square(0.030, 0.007)),
        ("cylinder", np.array([-0.048, -0.035]), 0.030 * np.c_[np.cos(t), np.sin(t)]),
        ("triangle", np.array([0.0, 0.0393]), _round_triangle(0.02157, 0.0101))]}


def scene_lid(scene):
    """The lid of Aalto's sim (scene.lid_holes()), same form; a = pelvis x, b = pelvis y at turn 0."""
    b = scene.cfg["bins"]
    ctr = np.asarray(b["centers"][scene.cfg["lid"]["bin"]], float)
    holes = [(hh["shape"], (hh["center"] - ctr)[::-1], (hh["poly"] - hh["center"])[:, ::-1]) for hh in scene.lid_holes()]
    return {"size": float(min(b["outer_size"])), "thickness": float(scene.cfg["lid"]["thickness"]), "holes": holes}


def _lid_pose(model, turn, lip_up, yaw):
    """-> (R 2x2, hole centres {shape: local xy}, hole outlines [local (n, 2)]) for the lid centred at the origin."""
    ang = np.radians(90.0 * turn) + yaw
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    mir = np.array([-1.0, 1.0]) if lip_up else np.ones(2)
    cen = {k: R @ (ctr * mir) for k, ctr, _ in model["holes"]}
    polys = [((ctr + poly) * mir) @ R.T for _, ctr, poly in model["holes"]]
    return R, cen, polys


def _template(model, res, turn, lip_up, yaw, n):
    """(n, n) float32: +1 plate, -1 hole, 0 outside. Rows = local e1 (forward), columns = local e2 (left)."""
    import cv2
    R, _, polys = _lid_pose(model, turn, lip_up, yaw)
    px = lambda q: np.round((np.asarray(q)[:, ::-1] / res + n / 2 - 0.5) * 16).astype(np.int32)   # (col, row), 1/16 px
    hs = model["size"] / 2
    tpl = np.zeros((n, n), np.float32)
    cv2.fillPoly(tpl, [px(np.array([[hs, hs], [-hs, hs], [-hs, -hs], [hs, -hs]]) @ R.T)], 1.0, shift=4)
    cv2.fillPoly(tpl, [px(q) for q in polys], -1.0, shift=4)
    return tpl


def _observe(Q, cam, frame_o, e1, e2, z0, grad, thick, res, half):
    """Top-down image around frame_o: +1 plate (points on the lid plane), -1 seen through it, 0 unknown."""
    import cv2
    n = int(round(2 * half / res))
    d = Q[:, :2] - frame_o
    a, b = d @ e1, d @ e2
    plane = z0 + a * grad[0] + b * grad[1]
    near = (np.abs(a) < half) & (np.abs(b) < half)
    plate = _grid(a[near & (np.abs(Q[:, 2] - plane) < 0.0035)], b[near & (np.abs(Q[:, 2] - plane) < 0.0035)], -half, -half, n, n, res)
    low = Q[:, 2] < plane - 0.012                            # the ray to a point below the plate crosses its mid-plane
    ca, cb = (cam[:2] - frame_o) @ e1, (cam[:2] - frame_o) @ e2
    da, db, dz = a[low] - ca, b[low] - cb, Q[low, 2] - cam[2]
    den = dz - da * grad[0] - db * grad[1]
    t = (z0 - thick / 2 + ca * grad[0] + cb * grad[1] - cam[2]) / np.where(np.abs(den) < 1e-9, -1e-9, den)
    ok = (t > 0) & (t < 1)
    opened = _grid(ca + t[ok] * da[ok], cb + t[ok] * db[ok], -half, -half, n, n, res)
    k = np.ones((3, 3), np.uint8)
    plate = cv2.morphologyEx(plate.astype(np.uint8), cv2.MORPH_CLOSE, k).astype(bool)
    opened = cv2.morphologyEx(opened.astype(np.uint8), cv2.MORPH_CLOSE, k).astype(bool)
    obs = np.zeros((n, n), np.float32)
    obs[plate & ~opened] = 1.0
    obs[opened & ~plate] = -1.0
    return obs


def _match(obs, model, res, hyps, yaws, max_shift):
    """Best (score, turn, lip_up, yaw, shift e1, shift e2) per (turn, lip_up); score = correlation / template cells."""
    import cv2
    n = obs.shape[0] - 2 * int(round(max_shift / res))
    out = {}
    for turn, lip_up in hyps:
        for yaw in yaws:
            tpl = _template(model, res, turn, lip_up, yaw, n)
            r = cv2.matchTemplate(obs, tpl, cv2.TM_CCORR)
            _, mx, _, loc = cv2.minMaxLoc(r)
            sc = mx / float(np.abs(tpl).sum())
            if (turn, lip_up) not in out or sc > out[(turn, lip_up)][0]:
                mid = (r.shape[0] - 1) / 2
                dr, dc = loc[1] - mid, loc[0] - mid
                if 0 < loc[1] < r.shape[0] - 1:              # sub-cell: parabola through the peak and its neighbours
                    q = r[loc[1] - 1:loc[1] + 2, loc[0]]
                    dr += float(np.clip((q[0] - q[2]) / (2 * (q[0] - 2 * q[1] + q[2]) - 1e-9), -0.5, 0.5))
                if 0 < loc[0] < r.shape[1] - 1:
                    q = r[loc[1], loc[0] - 1:loc[0] + 2]
                    dc += float(np.clip((q[0] - q[2]) / (2 * (q[0] - 2 * q[1] + q[2]) - 1e-9), -0.5, 0.5))
                out[(turn, lip_up)] = (sc, turn, lip_up, float(yaw), dr * res, dc * res)
    return out


def _side_vote(obs, model, res, turn, lip_up, yaw, s1, s2):
    """Is the square hole where this pose says, and the round one where it says? -1 .. 1.
    Lip up and lip down differ only by which of the two holes is square, i.e. by the four corners a square hole has
    and a round one does not: +1 = the cube hole's corners are open and the cylinder hole's are plate."""
    import cv2
    holes = {k: (ctr, poly) for k, ctr, poly in model["holes"]}
    if "cube" not in holes or "cylinder" not in holes:
        return 1.0
    R, cen, _ = _lid_pose(model, turn, lip_up, yaw)
    half = float(np.abs(holes["cube"][1]).max()) - 0.0015
    rad = max(float(np.linalg.norm(holes["cylinder"][1], axis=1).max()), half * 0.9) + 0.0015
    n = obs.shape[0]
    sq = np.array([[half, half], [-half, half], [-half, -half], [half, -half]]) @ R.T
    vote = 0.0
    for k, sign in (("cube", -1.0), ("cylinder", 1.0)):
        c = cen[k] + [s1, s2]
        px = lambda q: np.round((np.asarray(q)[:, ::-1] / res + n / 2 - 0.5) * 16).astype(np.int32)
        m = np.zeros((n, n), np.uint8)
        cv2.fillPoly(m, [px(sq + c)], 1, shift=4)
        cv2.circle(m, tuple(int(q) for q in px(c[None])[0]), int(round(rad / res * 16)), 0, -1, shift=4)
        vote += sign * float(obs[m > 0].mean()) if m.any() else 0.0
    return vote / 2.0


def find_lid(P, T, scene, boxes, model=None, only=None):
    """Which box carries the lid, and where its holes are. P: optical points at FULL image resolution.

    -> {ok, why, box, z (plate top above the table, m), center (frame xy), yaw_deg (on top of the turn), turn (0..3:
        quarter turns of the lid's b axis from the row's forward direction), lip_up, score (0..1), turn_margin (score
        gap to the best other turn), side_vote (-1..1: how clearly the square and the round hole are told apart, which
        is what separates lip down from lip up), tilt_deg, holes {cube | cylinder | triangle: {center (frame xy),
        axis_deg}}}
    axis_deg: direction in the frame (from +x towards +y) of the lid's b axis: a cube must be square to it, and the
    triangle hole has one tip pointing along it."""
    model = model or real_lid()
    res = {"ok": False, "why": "", "holes": {}}
    if not boxes.get("boxes"):
        res["why"] = "no boxes"
        return res
    zc = scene.counter_z
    Q = np.asarray(P, np.float64) @ T[:3, :3].T + T[:3, 3]
    Q[:, 2] -= zc
    cam = np.r_[T[:2, 3], T[2, 3] - zc]
    e1, e2, wall = boxes["frame"]["e1"], boxes["frame"]["e2"], boxes["wall"]
    half_l = model["size"] / 2
    cands = []
    for name, bx in boxes["boxes"].items():                  # a lid = one flat patch over most of the box
        if only is not None and name != only:
            continue
        d = Q[:, :2] - bx["center"]
        a, b = d @ e1, d @ e2
        inside = (np.abs(a) < half_l + 0.01) & (np.abs(b) < half_l + 0.01) & (Q[:, 2] > wall - 0.015) & (Q[:, 2] < wall + 0.03)
        if inside.sum() < 500:
            continue
        hh, ed = np.histogram(Q[inside, 2], bins=np.arange(wall - 0.015, wall + 0.0301, 0.002))
        z0 = ed[hh.argmax()] + 0.001
        on = inside & (np.abs(Q[:, 2] - z0) < 0.004)
        cover = _grid(a[on], b[on], -half_l, -half_l, 50, 50, 0.004).mean()
        cands.append((float(cover), name, float(np.median(Q[on, 2])), on, a, b))
    cands.sort(key=lambda q: -q[0])
    if not cands or cands[0][0] < 0.5:
        res["why"] = "no lid: no box is covered by a flat plate" + (f" (most covered {cands[0][1]}: {cands[0][0]:.2f})" if cands else "")
        return res
    cover, name, z0, on, a, b = cands[0]
    A = np.c_[a[on], b[on], np.ones(on.sum())]               # the plate's own plane (it may sit a little tilted)
    for _ in range(2):
        g = np.linalg.lstsq(A, Q[on, 2], rcond=None)[0]
        keep = np.abs(A @ g - Q[on, 2]) < 0.003
        A, on = A[keep], np.flatnonzero(on)[keep]
        on_mask = np.zeros(len(Q), bool)
        on_mask[on] = True
        on = on_mask
    g = np.linalg.lstsq(A, Q[on, 2], rcond=None)[0]
    grad, z0 = g[:2], float(g[2])
    tilt = float(np.degrees(np.arctan(np.hypot(*grad))))
    res.update(box=name, z=z0, cover=cover, tilt_deg=tilt)
    if tilt > 6.0:
        res["why"] = f"the plate on the {name} box is tilted {tilt:.1f} deg: not a lid lying flat"
        return res
    ctr = np.asarray(boxes["boxes"][name]["center"], float)
    hyps = [(k, s) for k in range(4) for s in (False, True)]
    shift = 0.026
    obs = _observe(Q, cam, ctr, e1, e2, z0, grad, model["thickness"], RES, 0.13 + shift)
    coarse = _match(obs, model, RES, hyps, np.radians(np.arange(-10.0, 10.1, 2.0)), shift)
    rank = sorted(coarse.values(), key=lambda q: -q[0])
    best = rank[0]
    others = [q[0] for q in rank if q[1] != best[1]]
    turn_margin = float(best[0] - max(others)) if others else 1.0
    fine_res = 0.001
    c2 = ctr + e1 * best[4] + e2 * best[5]
    z2 = z0 + grad @ np.array([best[4], best[5]])
    obs2 = _observe(Q, cam, c2, e1, e2, z2, grad, model["thickness"], fine_res, 0.13 + 0.006)
    yaws = best[3] + np.radians(np.arange(-1.5, 1.51, 0.25))
    turn, lip_up = best[1], best[2]
    sc, _, _, yaw, s1, s2 = _match(obs2, model, fine_res, [(turn, lip_up)], yaws, 0.006)[(turn, lip_up)]
    vote = _side_vote(obs2, model, fine_res, turn, lip_up, yaw, s1, s2)
    if vote < 0:                                             # the corners say the other side is up
        lip_up = not lip_up
        sc, _, _, yaw, s1, s2 = _match(obs2, model, fine_res, [(turn, lip_up)], yaws, 0.006)[(turn, lip_up)]
        vote = _side_vote(obs2, model, fine_res, turn, lip_up, yaw, s1, s2)
    centre = c2 + e1 * s1 + e2 * s2
    row_ang = np.arctan2(e1[1], e1[0])
    _, cen, _ = _lid_pose(model, turn, lip_up, yaw)
    axis = float(np.degrees(row_ang + np.radians(90.0 * turn) + yaw + np.pi / 2))     # lid b axis in the frame
    axis = (axis + 180.0) % 360.0 - 180.0
    for k, pc in cen.items():
        res["holes"][k] = {"center": centre + e1 * pc[0] + e2 * pc[1], "axis_deg": axis}
    res.update(center=centre, yaw_deg=float(np.degrees(yaw)), turn=int(turn), lip_up=bool(lip_up), score=float(sc),
               turn_margin=turn_margin, side_vote=float(vote))
    if sc < 0.45:
        res["why"] = f"a plate lies on the {name} box but the holes do not match the lid ({sc:.2f})"
    elif turn_margin < 0.05:
        res["why"] = f"lid on the {name} box, but which way it is turned is not clear (margin {turn_margin:.2f})"
    elif vote < 0.35:
        res["why"] = f"lid on the {name} box, but the square and the round hole are not told apart ({vote:.2f})"
    else:
        res["ok"], res["why"] = True, f"lid on the {name} box"
    return res


# ---------------------------------------------------------------------------------------------- hook
def points(cal, depth, step=1, max_range_mm=1600):
    """Optical-frame points of the valid pixels of a head depth image (mm)."""
    from .camera import _points
    P = _points(cal, depth, step).reshape(-1, 3)
    d = depth[::step, ::step].reshape(-1)
    return P[(d > 150) & (d < max_range_mm)]


def enable(cam, lid=False, log=None, max_move=0.20):
    """Opt-in (V16_BOXES=find, or =lid to look for the lid too): after each accepted camera fit, measure the boxes
    and let the drops follow them (scene.cfg bins centres, in mat coordinates). Never raises; if the boxes are not
    found, or found more than `max_move` from scene.yaml, the bins stay where they were. reset() puts scene.yaml's
    centres back. The result is kept in cam.boxes / cam.lid. Needs only CameraPerception.ensure_pose and .reset."""
    import copy
    log = log or cam.log
    inner, inner_reset = cam.ensure_pose, cam.reset
    centers = cam.scene.cfg["bins"]["centers"]
    bins0 = copy.deepcopy(centers)
    cam.boxes = cam.lid = None

    def reset(*a, **kw):
        out = inner_reset(*a, **kw)
        centers.clear()
        centers.update(copy.deepcopy(bins0))
        cam.boxes = cam.lid = None
        return out

    def ensure_pose(depth):
        before = cam.fit
        fit = inner(depth)
        if fit is None or fit is before or not fit.ok:
            return fit
        try:
            found = find_boxes(points(cam.cal0, depth, 2), fit.T, cam.scene)
            cam.boxes = found
            if not found["ok"]:
                log(f"[boxes] not measured: {found['why']}")
                return fit
            bins = as_bins(found, cam.scene)
            far = max(float(np.hypot(*s)) for s in bins["shift"].values())
            if far > max_move:
                log(f"[boxes] measured {far * 100:.0f} cm from scene.yaml: not used")
                return fit
            for n, xy in bins["centers"].items():
                m = cam.scene.pelvis_to_mat([float(xy[0]), float(xy[1]), 0.0])
                centers[n] = [float(m[0]), float(m[1])]
            log(f"[boxes] {bins['why']}; shift cm " + ", ".join(
                f"{n} ({dx * 100:+.1f}, {dy * 100:+.1f})" for n, (dx, dy) in bins["shift"].items()))
            if lid:
                cam.lid = find_lid(points(cam.cal0, depth, 1), fit.T, cam.scene, found)
                log(f"[boxes] lid: {cam.lid['why']}" + (
                    "; holes " + ", ".join(f"{k} ({q['center'][0] * 100:.1f}, {q['center'][1] * 100:.1f})"
                                           for k, q in cam.lid["holes"].items()) if cam.lid["ok"] else ""))
        except Exception as e:                               # never let this break perception
            log(f"[boxes] error: {e!r}")
        return fit

    cam.ensure_pose, cam.reset = ensure_pose, reset
    return cam


def mode():
    """V16_BOXES: off (default) | find | lid."""
    m = os.environ.get("V16_BOXES", "off").lower()
    return m if m in ("find", "lid") else "off"
