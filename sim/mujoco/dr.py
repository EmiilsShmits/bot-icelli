"""Domain randomisation for the MuJoCo venue scene: one random variant of venue_measured.yaml per episode, drawn
from a seed (same seed -> same variant). Ranges cover what we do not know about the venue (or know only roughly):

    colours    object colour set (venue look / Aalto's sim / as the real head camera recorded them) x brightness and
               per-channel tint; table tone
    lights     key and fill strength, key direction, ambient
    camera     head camera pitch +-2 deg, roll +-1, yaw +-1.5, sideways +-1 cm, height above the table +-1.5 cm
    table      robot -> table edge 6-14 cm (not measured; moves the bins with it)
    bins       wall height 6-8 cm, each bin +-1.5 cm in x and y
    objects    friction 0.7-1.4, mass 30-80 g
    tip        30 % of episodes: triangular prisms lie on a face (ridge up)

The policy is not told: it assumes Aalto's scene.yaml and calibration, as in the submission image.

mode: "all" (everything above), "camera" (only the camera pose), "bins" (only the table distance and the bins),
"none" (the nominal measured scene). The random draws are the same in every mode, so one seed gives the same camera
error in "all" and "camera" and the same bin shift in "all" and "bins" (paired controls).

    python sim/mujoco/dr.py 5000        # print the variant of seed 5000
"""
from __future__ import annotations

import copy
import json
import sys

import numpy as np

COLOR_SETS = ("venue", "sim", "real_camera")


MODES = ("all", "camera", "bins", "none", "lean")


def sample(cfg, seed, mode="all"):
    """-> (cfg variant, colours {name: rgb}, tip, params dict for the report)."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not in {MODES}")
    c_all, cols_all, tip_all, p_all = _sample_all(cfg, seed)
    if mode == "all":
        return c_all, cols_all, tip_all, dict(p_all, mode=mode)
    c = copy.deepcopy(cfg)
    cols = dict(cfg["objects"]["colors"]["venue"])
    p = {k: 0.0 for k in p_all}
    p.update(colors="venue", brightness=1.0, key_light=1.0, ambient=0.3, tip=False,
             table_edge_cm=round(100 * cfg["table"]["robot_to_table_edge"], 1),
             bin_wall_cm=round(100 * cfg["bins"]["wall_height"], 1), friction=cfg["objects"]["friction"],
             mass_g=round(1000 * cfg["objects"]["mass"]), mode=mode)
    if mode == "camera":
        c["camera"] = c_all["camera"]
        p.update({k: p_all[k] for k in p_all if k.startswith("cam_")})
    elif mode == "lean":
        # What Aalto's real head frames say (docs/CONTEXT.md 4.1): the camera sits ~2 deg below its calibration on
        # the mount and the torso leans 6-10 deg towards the table (7.9 and 12.2 deg of total tilt in the two drops).
        # The venue look puts all of it (9 deg) in the camera instead. Same total view tilt range here.
        r = np.random.default_rng([int(seed), 0x1EA])
        lean = float(r.uniform(5.0, 11.0))
        c["robot"]["lean_deg"] = lean
        c["camera"]["pitch_down_deg"] = float(r.uniform(1.0, 3.0))
        c["camera"]["yaw_deg"] = float(r.uniform(-2.5, -1.5))
        c["camera"]["shift_y"] = 0.0
        p.update(lean_deg=round(lean, 2), cam_pitch_deg=round(c["camera"]["pitch_down_deg"] - cfg["camera"]["pitch_down_deg"], 2))
    elif mode == "bins":
        c["table"]["robot_to_table_edge"] = c_all["table"]["robot_to_table_edge"]
        c["bins"]["jitter"] = c_all["bins"]["jitter"]
        p.update(table_edge_cm=p_all["table_edge_cm"], bin_jitter_cm=p_all["bin_jitter_cm"])
    return c, cols, False, p


def _sample_all(cfg, seed):
    r = np.random.default_rng([int(seed), 0xD12])
    u = lambda lo, hi: float(r.uniform(lo, hi))
    c = copy.deepcopy(cfg)
    cset = str(r.choice(COLOR_SETS, p=[0.4, 0.2, 0.4]))
    bright = u(0.85, 1.15)
    cols = {}
    for name, rgb in cfg["objects"]["colors"][cset].items():
        tint = r.uniform(-12, 12, 3)
        cols[name] = [int(np.clip(v * bright + t, 0, 255)) for v, t in zip(rgb, tint)]
    c["table"]["rgb"] = [int(np.clip(v + r.uniform(-15, 15), 0, 255)) for v in cfg["table"]["rgb"]]
    c["lights"] = {"key_scale": u(0.5, 1.5), "fill_scale": u(0.5, 2.0), "ambient": u(0.15, 0.45),
                   "key_dir": [u(-0.7, -0.1), u(0.0, 0.6), -1.0]}
    cam = c["camera"]
    cam["pitch_down_deg"] += u(-2, 2)
    cam["roll_deg"] += u(-1, 1)
    cam["yaw_deg"] += u(-1.5, 1.5)
    cam["shift_y"] += u(-0.01, 0.01)
    cam["above_table"] += u(-0.015, 0.015)
    c["table"]["robot_to_table_edge"] = u(0.06, 0.14)
    c["bins"]["wall_height"] = u(0.06, 0.08)
    c["bins"]["jitter"] = {n: [u(-0.015, 0.015), u(-0.015, 0.015)] for n in ("left", "center", "right")}
    c["objects"]["friction"] = u(0.7, 1.4)
    c["objects"]["mass"] = u(0.03, 0.08)
    tip = bool(r.random() < 0.3)
    params = {"colors": cset, "brightness": round(bright, 3), "key_light": round(c["lights"]["key_scale"], 2),
              "ambient": round(c["lights"]["ambient"], 2),
              "cam_pitch_deg": round(cam["pitch_down_deg"] - cfg["camera"]["pitch_down_deg"], 2),
              "cam_roll_deg": round(cam["roll_deg"] - cfg["camera"]["roll_deg"], 2),
              "cam_yaw_deg": round(cam["yaw_deg"] - cfg["camera"]["yaw_deg"], 2),
              "cam_shift_cm": round(100 * (cam["shift_y"] - cfg["camera"]["shift_y"]), 2),
              "cam_height_cm": round(100 * (cam["above_table"] - cfg["camera"]["above_table"]), 2),
              "table_edge_cm": round(100 * c["table"]["robot_to_table_edge"], 1),
              "bin_wall_cm": round(100 * c["bins"]["wall_height"], 1),
              "bin_jitter_cm": round(100 * max(abs(v) for xy in c["bins"]["jitter"].values() for v in xy), 2),
              "friction": round(c["objects"]["friction"], 2), "mass_g": round(1000 * c["objects"]["mass"]),
              "tip": tip}
    return c, cols, tip, params


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import build as B
    print(json.dumps(sample(B.load_cfg(), int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "all")[3], indent=1))
