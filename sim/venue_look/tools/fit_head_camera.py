"""How far the real head camera is from Aalto's calibration: fit the camera pose to the middle bin's corners.

    python fit_head_camera.py                                  # print the fits for the corners below
    python fit_head_camera.py <real_head.jpg> <overlay.jpg>    # also draw Aalto's scene over the image with the fit

Aalto's scene (bins from scene.yaml) is projected through the head camera of calibration.yaml; the fit changes the
camera rotation (degrees: pitch + = further down, roll, yaw), its position (m, pelvis frame) and the bin wall height
until the middle bin's corners land on the pixels clicked in a real frame (OBS). For another frame: open it in an
image viewer, read off the six corners and replace OBS. AALTO_DIR = an aaltonomous-humanoid checkout
(default: our submodule).
"""
import os, sys
import numpy as np, cv2, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
AALTO = os.environ.get("AALTO_DIR", os.path.join(HERE, "../../../third_party/aaltonomous-humanoid"))
cal = yaml.safe_load(open(f"{AALTO}/aaltonomous/interface/calibration.yaml"))["cameras"]["head"]
sc = yaml.safe_load(open(f"{AALTO}/aaltonomous/scene/scene.yaml"))
K = cal["intrinsics"]
T0 = np.array(cal["T_pelvis_optical"], float)
O = np.array(sc["counter"]["mat_origin_in_pelvis"], float)
b = sc["bins"]; BW, BD = b["outer_size"]; CX, CY = b["centers"]["center"]

# Middle bin in g1_pick_cube (drop 1), frame 0. Key = (rim "top" or wall foot "bot", mat-x side, mat-y side);
# mat x points to the robot's left (= image left), mat y away from the robot. Value = pixel (u, v) in the 640x480 image.
OBS = {
    ("top", +1, -1): (280, 172),   # near rim corner, image left
    ("top", -1, -1): (515, 172),   # near rim corner, image right
    ("top", +1, +1): (285, 32),    # far rim corner, image left
    ("top", -1, +1): (478, 24),    # far rim corner, image right
    ("bot", +1, -1): (285, 228),   # foot of the near wall, image left
    ("bot", -1, -1): (500, 226),   # foot of the near wall, image right
}


def mat_to_pelvis(p):
    p = np.asarray(p, float)
    return O + np.array([p[1], p[0], p[2]])


def rot(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    if axis == "x": return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y": return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def camera(pitch=0, roll=0, yaw=0, d=(0, 0, 0)):
    """Aalto's head camera, rotated about its own optical axes (x right, y down, z forward) and moved by d."""
    T = T0.copy()
    T[:3, :3] = T0[:3, :3] @ rot("x", -pitch) @ rot("z", roll) @ rot("y", yaw)
    T[:3, 3] = T0[:3, 3] + np.asarray(d, float)
    return T


def project(T, pts_pelvis):
    P = np.asarray(pts_pelvis, float)
    Pc = (P - T[:3, 3]) @ T[:3, :3]
    return np.stack([K["fx"] * Pc[:, 0] / Pc[:, 2] + K["cx"], K["fy"] * Pc[:, 1] / Pc[:, 2] + K["cy"]], 1), Pc[:, 2]


def bins(wall_h=None):
    """name -> (4 floor corners, 4 rim corners) in the pelvis frame."""
    h = wall_h or b["wall_height"]; out = {}
    for name, (cx, cy) in b["centers"].items():
        fp = [(cx - BW / 2, cy - BD / 2), (cx + BW / 2, cy - BD / 2), (cx + BW / 2, cy + BD / 2), (cx - BW / 2, cy + BD / 2)]
        out[name] = ([mat_to_pelvis([x, y, 0]) for x, y in fp], [mat_to_pelvis([x, y, h]) for x, y in fp])
    return out


def draw(img, T, wall_h=None):
    def poly(pts, c, closed=True, t=1):
        uv, z = project(T, pts)
        if (z > 0.02).all(): cv2.polylines(img, [np.round(uv).astype(np.int32)], closed, c, t, cv2.LINE_AA)
    for bot, top in bins(wall_h).values():
        poly(bot, (0, 200, 255)); poly(top, (0, 255, 0), t=2)
        for p, q in zip(bot, top): poly([p, q], (0, 200, 255), False)
    return img


def model(p, names):
    q = dict(pitch=0, yaw=0, roll=0, dx=0, dy=0, dz=0, h=b["wall_height"]); q.update(dict(zip(names, p)))
    T = camera(q["pitch"], q["roll"], q["yaw"], (q["dx"], q["dy"], q["dz"]))
    pts = [mat_to_pelvis([CX + sx * BW / 2, CY + sy * BD / 2, q["h"] if lvl == "top" else 0.0]) for (lvl, sx, sy) in OBS]
    return project(T, pts)[0].ravel()


def fit(names, iters=60):
    """Gauss-Newton on the free parameters in `names`; the rest stay at Aalto's values."""
    p = np.zeros(len(names))
    if "h" in names: p[names.index("h")] = b["wall_height"]
    y = np.array(list(OBS.values()), float).ravel()
    for _ in range(iters):
        r = model(p, names) - y
        J = np.stack([(model(p + e, names) - model(p - e, names)) / 2e-4 for e in np.eye(len(p)) * 1e-4], 1)
        step = np.linalg.lstsq(J, -r, rcond=None)[0]; p = p + step
        if np.abs(step).max() < 1e-7: break
    r = model(p, names) - y
    return p, float(np.sqrt((r ** 2).mean()))


if __name__ == "__main__":
    for names in (["pitch"], ["pitch", "yaw", "roll"], ["pitch", "yaw", "roll", "h"], ["pitch", "dy", "roll", "h"]):
        p, rms = fit(names)
        print("  ".join(f"{n} {v:+.3f}" for n, v in zip(names, p)), f" | error {rms:.1f} px")
    if len(sys.argv) > 2:       # venue.yaml uses the last fit: pitch, sideways shift dy, roll, wall height
        q = dict(zip(names, p))
        img = draw(cv2.imread(sys.argv[1]), camera(q["pitch"], q["roll"], 0, (0, q["dy"], 0)), q["h"])
        cv2.imwrite(sys.argv[2], img); print(sys.argv[2])
