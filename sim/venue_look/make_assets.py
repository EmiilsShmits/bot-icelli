"""Generate the venue-look assets next to this file.

    python make_assets.py                                              # plywood.png (table-top texture, 1 px = 1 mm)
                                                                       # + venue_bg_<i>.jpg (surroundings)
    python make_assets.py <aalto>/aaltonomous/scene/scene.yaml         # also scene_venue.yaml

plywood.png: procedural varnished wood in the tone of the real table top (see BASE below).
scene_venue.yaml: Aalto's scene.yaml with the `scene:` section of venue.yaml merged in (bin wall height, where
objects start). Geometry affects scoring and the oracle, so every process must use the same file (AALTO_SCENE for
the sim AND for every client: check, eval, baseline). `source venue_env.sh` sets it.
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
N_BACKGROUNDS = 6                                 # made-up venue halls for the surroundings (venue_bg_<i>.jpg)
BASE = np.array([190, 168, 162], float)          # sRGB table tone: pale pinkish wood, so that it reads
                                                 # about (150,134,135) under the cool lamp, as in the real head camera


def plywood(w=1100, h=600, seed=0):
    """(h, w, 3) uint8. Grain runs along the long axis (the robot's left-right)."""
    import cv2
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    # wide, slowly wandering growth bands + fine grain lines
    warp = 0.03 * np.sin(2 * np.pi * (1.3 * x + 0.2)) + 0.015 * np.sin(2 * np.pi * (3.1 * x + 0.7))
    bands = 0.5 + 0.5 * np.sin(2 * np.pi * 7 * (y + warp))
    bands2 = 0.5 + 0.5 * np.sin(2 * np.pi * 23 * (y + 0.6 * warp) + 1.0)
    fine = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=40, sigmaY=0.8)
    fine /= np.abs(fine).max()
    blotch = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=120, sigmaY=80)
    blotch /= np.abs(blotch).max()
    v = 1.0 + 0.035 * (bands - 0.5) + 0.02 * (bands2 - 0.5) + 0.05 * fine + 0.04 * blotch
    img = BASE[None, None, :] * v[..., None]
    img[..., 2] *= 1.0 - 0.03 * (bands - 0.5)[..., ]          # darker bands are a little redder
    img = np.clip(img, 0, 255).astype(np.uint8)
    # a few zinc screw heads, like the real top
    for _ in range(9):
        c = (int(rng.uniform(40, w - 40)), int(rng.uniform(40, h - 40)))
        cv2.circle(img, c, 6, (150, 150, 155), -1, cv2.LINE_AA)
        cv2.circle(img, c, 6, (110, 108, 105), 1, cv2.LINE_AA)
    return img


def venue_background(seed=0, w=2048, h=1024):
    """(h, w, 3) uint8 RGB, equirectangular (x = direction around the robot, y = straight up ... straight down).
    Not a photo: a made-up dark event hall in the style of the real wrist-camera footage - dark blue walls,
    purple / cyan / white light strips, bright screens, an over-exposed patch or two, and blurred people-sized
    shapes and tables along the horizon. Each seed gives a different hall."""
    import cv2
    rng = np.random.default_rng(1000 + seed)
    el = (0.5 - (np.arange(h) + 0.5) / h) * 180.0                     # elevation of each row, degrees
    px = w / 360.0                                                    # pixels per degree

    def row(e):
        return int(np.clip((0.5 - e / 180.0) * h, 0, h - 1))

    # walls and ceiling: dark blue-violet, a little lighter near the horizon; floor: dark warm grey
    wall = np.array([rng.uniform(55, 85), rng.uniform(62, 95), rng.uniform(120, 170)])
    ceil = np.array([26, 30, 52.0])
    floor = np.array([52, 48, 46.0])
    t = np.clip(el / 55.0, 0, 1)[:, None]
    img = np.where(el[:, None] >= 0, wall * (1 - t) + ceil * t, floor * (1 + np.clip(el[:, None] / 60.0, -0.6, 0)))
    img = np.repeat(img[:, None, :], w, 1).astype(np.float32)
    # large soft patches of coloured wash light on the walls
    for _ in range(int(rng.integers(8, 14))):
        col = np.array([[150, 60, 230], [60, 110, 255], [40, 200, 230], [230, 70, 160]][int(rng.integers(4))], float)
        c = (int(rng.uniform(0, w)), row(rng.uniform(2, 55)))
        m = np.zeros((h, w), np.float32)
        cv2.ellipse(m, c, (int(rng.uniform(12, 40) * px), int(rng.uniform(6, 18) * px)), 0, 0, 360, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 14 * px / 5.7)
        img += m[..., None] * col * rng.uniform(0.35, 0.8)
    # ceiling trusses: thin dark-grey lines
    for _ in range(int(rng.integers(4, 8))):
        y = row(rng.uniform(25, 70)); x0 = int(rng.uniform(0, w)); ln = int(rng.uniform(30, 120) * px)
        cv2.line(img, (x0, y), (x0 + ln, y + int(rng.uniform(-4, 4) * px)), (120, 124, 140), max(2, int(0.6 * px)), cv2.LINE_AA)
    # screens and windows: bright rectangles just above the horizon
    for _ in range(int(rng.integers(4, 8))):
        col = np.array([[70, 130, 255], [235, 240, 255], [150, 90, 255], [255, 250, 235]][int(rng.integers(4))], float)
        x0, e0 = int(rng.uniform(0, w)), rng.uniform(3, 28)
        ww, hh = int(rng.uniform(3, 14) * px), int(rng.uniform(2, 9) * px)
        cv2.rectangle(img, (x0, row(e0) - hh), (x0 + ww, row(e0)), tuple(float(v) for v in col * rng.uniform(0.8, 1.0)), -1)
    # one or two over-exposed areas (a bright doorway, a lamp shining into the lens)
    for _ in range(int(rng.integers(1, 3))):
        m = np.zeros((h, w), np.float32)
        cv2.ellipse(m, (int(rng.uniform(0, w)), row(rng.uniform(5, 45))), (int(rng.uniform(6, 16) * px), int(rng.uniform(5, 14) * px)),
                    0, 0, 360, 1.0, -1)
        img += cv2.GaussianBlur(m, (0, 0), 3 * px)[..., None] * np.array([255, 255, 255.0])
    # light strips: thin, saturated, horizontal or vertical
    for _ in range(int(rng.integers(18, 34))):
        col = [(225, 80, 255), (80, 225, 255), (235, 240, 255), (255, 120, 220), (255, 235, 170)][int(rng.integers(5))]
        x0, e0 = int(rng.uniform(0, w)), rng.uniform(4, 62)
        ln = int(rng.uniform(2, 12) * px)
        if rng.random() < 0.3:
            cv2.line(img, (x0, row(e0)), (x0, row(e0) + ln), col, max(2, int(0.7 * px)), cv2.LINE_AA)
        else:
            cv2.line(img, (x0, row(e0)), (x0 + ln, row(e0) + int(rng.uniform(-1.5, 1.5) * px)), col, max(2, int(0.7 * px)), cv2.LINE_AA)
    # a row of small warm lamps
    y = row(rng.uniform(4, 10)); x0 = int(rng.uniform(0, w))
    for k in range(int(rng.integers(8, 20))):
        cv2.circle(img, (x0 + int(k * 2.2 * px), y), max(1, int(0.4 * px)), (255, 225, 150), -1, cv2.LINE_AA)
    glow = cv2.GaussianBlur(np.clip(img - 150, 0, None), (0, 0), 1.6 * px)       # bloom around bright things
    img = img + 0.6 * glow
    # along the horizon: tables, chairs and people-sized shapes in muted colours
    clutter = np.zeros_like(img); mask = np.zeros((h, w), np.float32)
    for _ in range(int(rng.integers(70, 120))):
        col = np.array([[225, 222, 215], [40, 42, 50], [150, 120, 95], [90, 35, 40], [200, 185, 160], [60, 70, 110],
                        [120, 125, 130]][int(rng.integers(7))], float) * rng.uniform(0.6, 1.0)
        x0, wd = int(rng.uniform(0, w)), int(rng.uniform(1.0, 4.0) * px)
        if rng.random() < 0.3:                                        # table: wide and low
            y0, y1, wd = row(rng.uniform(-6, 0)), row(rng.uniform(-10, -6)), int(rng.uniform(5, 14) * px)
        else:                                                         # person: narrow, up to a bit above the horizon
            y0, y1 = row(rng.uniform(1, 12)), row(rng.uniform(-12, -4))
        cv2.rectangle(clutter, (x0, y0), (x0 + wd, y1), tuple(float(v) for v in col), -1)
        cv2.rectangle(mask, (x0, y0), (x0 + wd, y1), 1.0, -1)
    soft = 1.0 * px                                                   # they are far away and out of focus
    mask = cv2.GaussianBlur(mask, (0, 0), soft)[..., None]
    img = img * (1 - mask) + cv2.GaussianBlur(clutter, (0, 0), soft)
    k = int(6 * px)                                                   # make the left and right edges meet
    a = np.linspace(0, 1, k)[None, :, None]
    img[:, -k:] = img[:, -k:] * (1 - a) + img[:, :1] * a
    img = cv2.GaussianBlur(img, (0, 0), 0.35 * px)
    return np.clip(img, 0, 255).astype(np.uint8)


def scene_venue(src):
    """Aalto's scene.yaml + the `scene:` overrides from venue.yaml (geometry, so it also changes physics)."""
    import yaml
    sc = yaml.safe_load(open(src))
    over = (yaml.safe_load(open(HERE / "venue.yaml")) or {}).get("scene") or {}

    def merge(dst, src_, path=""):
        for k, v in src_.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v, f"{path}{k}.")
            else:
                notes.append(f"{path}{k}: {dst.get(k)} -> {v}")
                dst[k] = v
    notes = []
    merge(sc, over)
    out = HERE / "scene_venue.yaml"
    out.write_text("# GENERATED by make_assets.py: Aalto's scene.yaml + the `scene:` section of venue.yaml.\n"
                   + "".join(f"#   {n}\n" for n in notes) + yaml.safe_dump(sc, sort_keys=False))
    print("wrote", out, *notes, sep="\n  ")


if __name__ == "__main__":
    import cv2
    cv2.imwrite(str(HERE / "plywood.png"), plywood()[..., ::-1])
    print("wrote", HERE / "plywood.png")
    for i in range(N_BACKGROUNDS):
        cv2.imwrite(str(HERE / f"venue_bg_{i}.jpg"), venue_background(i)[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("wrote", N_BACKGROUNDS, "x venue_bg_<i>.jpg")
    if len(sys.argv) > 1:
        scene_venue(sys.argv[1])
