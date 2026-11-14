"""Scene variants for the Isaac sim, to test a policy on more than the nominal scene.

Run INSIDE the sim container before `aalto sim` (sim/modal_sim.py --variant "..." does this). It edits the
container's copy of the organisers' files in place; the checkout on the laptop is never touched, and the sim, the
evaluator and the scoring all read the same edited files, so they stay consistent with each other.

    python scene_variant.py --colors real --dr wide --placement wide --instructions shape

  --colors real        the foam blocks the organisers announced on Discord (14 Nov): yellow, purple, orange, with
                       their real sort_fixed mapping yellow -> left, purple -> center, orange -> right.
                       (orange objects in front of orange bins: on purpose, that is the real setup.)
  --colors pastel      washed-out shades of the same three (worn foam, strong light)
  --colors venue       the three colours as the robot's head camera recorded the real blocks (data drop 2), from
                       Marcus's repo (1a51d7b). With AALTO_DR=train this is his "venue" scene (colours only: not
                       our venue look, which also lowers the camera). With "--dr wide" orange and yellow can be
                       truly indistinguishable.
  --dr wide            writes sim/dr/wide.yaml: the organisers' training randomisation with wider object shades
                       (hue / saturation / brightness), lighting, camera noise and camera pose error. Then start
                       the sim with AALTO_DR=wide (modal_sim.py: --dr wide).
  --placement wide     objects anywhere between the robot and the bins (not only the nominal 7 cm strip), any yaw
  --instructions shape sort_language instructions that name shapes, or colour and shape together, as the
                       organisers said the finals may ("colour, shape or both"). These sentences are ours.

  --tip triangles      every triangular prism lies on a rectangular face (ridge up, any yaw) instead of standing on
                       a triangular one, as a prism looks after it fell over (tests the v1.5 ridge grasp).
  --task3 request      rung 3 as we asked Aalto to set it up (docs/research/task3-lid-placement.md): the real lid
                       (bot-icelli sim/task3/lid_shape_holes_200mm.stl, plate on top, triangle hole nearest the robot,
                       square on its right) on the left bin moved to 39 cm in front of the pelvis and 15 cm left, the
                       centre bin taken away, 3 blocks in the right half of the band. Start the sim with
                       TASK=Aalto-Insert-G129-Dex3-Joint (modal_sim.py --task) and score with --eval-task insert_shapes.

  --lean DEG           the robot leans DEG forward against the table: its fixed base is pitched about the pelvis, so the
                       head camera (mounted on the pelvis link) and both arms tilt together and the table stays level.
                       That is what Aalto's real footage shows (docs/research/hand-offset-real-data.md: 5-10 deg).
  --cam-mount DEG      the head camera also looks DEG further down on its mount (real fit: ~2.4).
                       Both edit only the sim's scene_cfg.py: calibration.yaml and scene.yaml stay nominal, so a policy
                       sees what it would see on the real robot. Use with --look none (the venue look tilts the camera
                       10 deg on its mount, which is the other explanation of the real footage).

What a variant does NOT change: object size, the bins, the counter, the camera (except --lean / --cam-mount).
Without --tip, prisms always stand on a triangular face (the sim has no lying prisms).
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = next((p for p in (Path("/opt/aalto"), ROOT.parent / "aaltonomous-humanoid") if (p / "aaltonomous").is_dir()), None)

COLORS = {
    "real": {"yellow": [235, 200, 20], "purple": [125, 70, 175], "orange": [245, 135, 25]},
    "pastel": {"yellow": [240, 220, 110], "purple": [165, 130, 200], "orange": [245, 170, 100]},
    # As the robot's own head camera sees the real blocks (OpenCV hue / saturation on data drop 2): orange 11-13 /
    # 150-220, yellow 34-46 / 72-88 (a pale green-yellow), purple ~110 / 140-150 (looks blue). Marcus's values.
    "venue": {"yellow": [194, 217, 150], "purple": [82, 119, 191], "orange": [230, 129, 62]},
}
FIXED = {"yellow": "left", "purple": "center", "orange": "right"}      # Discord, 14 Nov 15:07

DR_WIDE = """# Wider than train.yaml where it matters for telling objects apart; written by sim/scene_variant.py.
name: wide
lighting:
  key_intensity_scale: [0.5, 1.6]
  key_pos_jitter: [0.5, 0.5, 0.3]
  key_rgb_jitter: 0.12
  dome_intensity_scale: [0.4, 1.6]
  dome_rgb_jitter: 0.08
textures:
  mat_scale: [0.75, 1.15]
  mat_rgb_jitter: 0.08
  mat_bias: [-0.04, 0.04]
  counter_rgb_jitter: 0.25
  bin_rgb_jitter: 0.10
objects:
  hue_jitter: 0.03                      # turns (0.03 = 11 deg)
  sat_scale: [0.6, 1.2]
  val_scale: [0.6, 1.2]
  mass_scale: [0.7, 1.5]
  friction_scale: [0.75, 1.1]
pose:
  xy_jitter: 0.005
  yaw_jitter_deg: 5
camera:
  rgb_noise_std: 4.0
  rgb_gain: [0.85, 1.15]
  depth_noise_mm: 1.5
  depth_noise_rel: 0.002
  depth_hole_frac: 0.02
  pose_jitter_m: 0.01
  pose_jitter_deg: 1.0
"""

SHAPE_INSTRUCTIONS = '''

# ---- added by sim/scene_variant.py --instructions shape: instructions by shape, or by colour and shape -------------
_SHAPE_WORD = {"cube": "cubes", "cylinder": "cylinders", "triangle": "triangular prisms"}
_SHAPE_TEMPLATES = (
    "Put the {s0} in the {b0} bin, the {s1} in the {b1} bin and the {s2} in the {b2} bin.",
    "Sort by shape: {s0} go to the {b0} bin, {s1} to the {b1} bin, {s2} to the {b2} bin.",
    "The {b0} bin is for {s0}, the {b1} bin for {s1} and the {b2} bin for {s2}. Colour does not matter.",
)
_MIXED_TEMPLATES = (
    "Put all {c0} objects in the {b0} bin. Of the others, the {s0} go in the {b1} bin and everything else in the {b2} bin.",
    "{C0} objects belong in the {b0} bin whatever their shape; other {s0} go to the {b1} bin; the rest go to the {b2} bin.",
)
_colour_instruction = make_instruction


def make_instruction(task, rng):
    if task != "sort_language":
        return _colour_instruction(task, rng)
    kind = int(rng.integers(3))
    if kind == 0:
        return _colour_instruction(task, rng)
    shapes, bins = [str(s) for s in rng.permutation(SHAPES)], [str(b) for b in rng.permutation(BINS)]
    words = {f"s{i}": _SHAPE_WORD[s] for i, s in enumerate(shapes)}
    words.update({f"b{i}": b for i, b in enumerate(bins)})
    if kind == 1:
        text = _SHAPE_TEMPLATES[int(rng.integers(len(_SHAPE_TEMPLATES)))].format(**words)
        return text, dict(zip(shapes, bins))
    colour = str(COLORS[int(rng.integers(len(COLORS)))])
    words.update(c0=colour, C0=colour.capitalize())
    text = _MIXED_TEMPLATES[int(rng.integers(len(_MIXED_TEMPLATES)))].format(**words)
    return text, {colour: bins[0], shapes[0]: bins[1], "default": bins[2]}      # most specific key wins (resolve_bin)
'''


TIP_TRIANGLES = '''

# ---- added by sim/scene_variant.py --tip triangles ----
_assign_standing = assign


def _qmul(a, b):
    """Hamilton product of two xyzw quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def assign(sc, layout):
    """Every active triangular prism lies on the rectangular face opposite its apex: roll +90 deg about the mesh x axis
    (apex up, ridge horizontal), then the layout yaw; dropped from 2.4 cm so it settles whatever the mesh origin."""
    poses, active = _assign_standing(sc, layout)
    roll = np.array([np.sin(np.pi / 4), 0.0, 0.0, np.cos(np.pi / 4)])
    for n in active:
        if parse_name(n)[1] == "triangle":
            p, q = poses[n]
            p = np.array(p, float)
            p[2] += 0.024 - sc.object_height("triangle") / 2
            poses[n] = (p, _qmul(q, roll))
    return poses, active
'''


TASK3_LID = [Path("/opt/task3/lid_shape_holes_200mm.stl"),
             ROOT.parent.parent / "sim" / "task3" / "lid_shape_holes_200mm.stl"]


def write_task3_lid(src, dst):
    """Aalto's lid STL (binary, mm, a tray: 4 mm plate at z 0-4 with a 12 mm rim) -> the sim's lid_shapes.stl (mm, mat
    axes around the lid centre, bottom at z = 0): turned 180 deg about x, so the plate is on top (z 8-12 mm, the rim
    hangs down) and the triangle hole (lid +v) is nearest the robot (mat -y); square (lid -u) on the robot's right."""
    import struct

    import numpy as np
    b = Path(src).read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    t = np.frombuffer(b, dtype=dt, count=n, offset=84)
    v, nr = t["v"].astype(np.float64), t["n"].astype(np.float64)
    out = np.zeros(n, dtype=dt)
    out["v"] = np.stack([v[..., 0], -v[..., 1], v[..., 2].max() - v[..., 2]], axis=-1)   # a rotation: winding kept
    out["n"] = np.stack([nr[:, 0], -nr[:, 1], -nr[:, 2]], axis=-1)
    Path(dst).write_bytes(b"bot-icelli task3 lid".ljust(80, b" ") + struct.pack("<I", n) + out.tobytes())
    return float(v[..., 2].max())


def task3_scene(s):
    """scene.yaml text -> rung 3 as requested: lid on the left bin at mat (0.60, 0.25) = pelvis (0.39, +0.15), centre
    bin out of the way, 3 blocks in mat x 0.28-0.42, y 0.12-0.19 (pelvis x 0.26-0.33, y -0.17..-0.03)."""
    for pat, value in ((r"(\n    left:\s+)\[[^\]]*\]", "[0.60, 0.25]"), (r"(\n    center:\s+)\[[^\]]*\]", "[0.45, 3.0]"),
                       (r"(\n  region_x: )\[[^\]]*\]", "[0.28, 0.42]"), (r"(\n  region_y: )\[[^\]]*\]", "[0.12, 0.19]"),
                       (r"(\n  n_cubes: )\[[^\]]*\]", "[3, 3]"), (r"(\n  thickness: )[0-9.]+", "0.012")):
        s, n = re.subn(pat, lambda m: m.group(1) + value, s, count=1)
        assert n == 1, f"task3: {pat} not found in scene.yaml"
    return s


def lean_scene_cfg(path, lean_deg, cam_deg):
    """--lean / --cam-mount: pitch the robot's fixed base forward by lean_deg about the pelvis (+y, Isaac Lab xyzw
    quaternion via the file's own rotmat_to_quat_xyzw) and tilt the head camera cam_deg further down on its mount
    (about the optical x axis, as the venue look's camera.head.pitch_down_deg). Idempotent."""
    import math
    src = path.read_text()
    if "added by sim/scene_variant.py --lean" in src:
        return
    robot = "init_rot=(0.0, 0.0, 0.0, 1.0))"
    assert src.count(robot) == 1, f"{path.name}: robot init_rot not found"
    cam = '    T = np.asarray(cal["T_pelvis_optical"], float)\n'
    assert src.count(cam) == 1, f"{path.name}: head camera pose line not found"
    anchor = "def head_camera_cfg():\n"
    assert src.count(anchor) == 1, f"{path.name}: head_camera_cfg not found"
    src = src.replace(robot, "init_rot=_LEAN_Q)").replace(cam, cam + "    T = T.copy()\n    T[:3, :3] = T[:3, :3] @ _CAM_MOUNT_R\n")
    t, c = math.radians(lean_deg), math.radians(cam_deg)
    # Before head_camera_cfg: the module builds the scene classes at import time (make_scene_cfg_class() near the
    # end), so the constants must exist by then; rotmat_to_quat_xyzw is defined above this point.
    block = (f"# ---- added by sim/scene_variant.py --lean {lean_deg} --cam-mount {cam_deg} ----\n"
             f"_LEAN_R = np.array([[{math.cos(t)!r}, 0.0, {math.sin(t)!r}], [0.0, 1.0, 0.0], "
             f"[{-math.sin(t)!r}, 0.0, {math.cos(t)!r}]])   # about +y: forward (+x) tips down\n"
             f"_LEAN_Q = rotmat_to_quat_xyzw(_LEAN_R)\n"
             f"_CAM_MOUNT_R = np.array([[1.0, 0.0, 0.0], [0.0, {math.cos(c)!r}, {math.sin(c)!r}], "
             f"[0.0, {-math.sin(c)!r}, {math.cos(c)!r}]])   # about optical x by -cam_deg: view tips down\n\n\n")
    src = src.replace(anchor, block + anchor)
    path.write_text(src)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colors", choices=sorted(COLORS), default=None)
    ap.add_argument("--dr", choices=["wide"], default=None)
    ap.add_argument("--placement", choices=["wide"], default=None)
    ap.add_argument("--instructions", choices=["shape"], default=None)
    ap.add_argument("--tip", choices=["triangles"], default=None)
    ap.add_argument("--task3", choices=["request"], default=None)
    ap.add_argument("--lean", type=float, default=None, help="robot pitched forward this many degrees vs the table")
    ap.add_argument("--cam-mount", type=float, default=0.0, help="head camera this many degrees further down on its mount")
    a = ap.parse_args()
    pkg = REPO / "aaltonomous"
    scene, tasks = pkg / "scene" / "scene.yaml", pkg / "interface" / "tasks.py"
    s, t = scene.read_text(), tasks.read_text()
    if a.colors:
        cols = COLORS[a.colors]
        block = "".join(f"    {name}: {rgb}\n" for name, rgb in cols.items())
        s, n = re.subn(r"(  colors:[^\n]*\n)(?:    \w+: \[[^\n]*\n)+", lambda m: m.group(1) + block, s, count=1)
        assert n == 1, "objects.colors block not found in scene.yaml"
        names = list(cols)
        sentence = ("Put the {0} objects in the {1} bin, the {2} objects in the {3} bin and the {4} objects in the "
                    "{5} bin.").format(names[0], FIXED[names[0]], names[1], FIXED[names[1]], names[2], FIXED[names[2]])
        t += (f"\n\n# ---- added by sim/scene_variant.py --colors {a.colors} ----\n"
              f"COLORS = {tuple(names)!r}\nFIXED_MAPPING = {dict(FIXED)!r}\nFIXED_INSTRUCTION = {sentence!r}\n")
    if a.placement == "wide":
        for key, value in (("region_x", "[0.24, 0.66]"), ("region_y", "[0.12, 0.23]"), ("yaw_range_deg", "[-90, 90]")):
            s, n = re.subn(rf"(\n  {key}: )\[[^\]]*\]", lambda m: m.group(1) + value, s, count=1)
            assert n == 1, f"layout.{key} not found in scene.yaml"
    if a.instructions == "shape":
        t += SHAPE_INSTRUCTIONS
    if a.dr == "wide":
        (pkg / "sim" / "dr" / "wide.yaml").write_text(DR_WIDE)
    if a.tip == "triangles":
        lay = pkg / "sim" / "aalto_task" / "layout.py"
        if "--tip triangles" not in lay.read_text():
            lay.write_text(lay.read_text() + TIP_TRIANGLES)
    if a.task3:
        s = task3_scene(s)
        src = next((p for p in TASK3_LID if p.exists()), None)
        assert src is not None, f"task3: lid STL not found in {TASK3_LID}"
        h = write_task3_lid(src, pkg / "scene" / "assets" / "lid_shapes.stl")
        print(f"task3: lid {src.name} ({h:.0f} mm high) on the left bin at mat (0.60, 0.25)")
    if a.lean is not None or a.cam_mount:
        lean_scene_cfg(pkg / "sim" / "aalto_task" / "scene_cfg.py", a.lean or 0.0, a.cam_mount or 0.0)
        print(f"lean: robot pitched {a.lean or 0.0:.1f} deg forward vs the table, head camera {a.cam_mount:.1f} deg "
              f"further down on its mount (sim only; calibration.yaml unchanged)")
    scene.write_text(s)
    tasks.write_text(t)
    print(f"scene variant applied in {REPO}: colors={a.colors} dr={a.dr} placement={a.placement} "
          f"instructions={a.instructions} tip={a.tip} task3={a.task3} lean={a.lean} cam_mount={a.cam_mount}")


if __name__ == "__main__":
    main()
