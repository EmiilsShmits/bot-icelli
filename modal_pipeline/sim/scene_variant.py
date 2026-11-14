"""Scene variants for the Isaac sim, to test a policy on more than the nominal scene.

Run INSIDE the sim container before `aalto sim` (sim/modal_sim.py --variant "..." does this). It edits the
container's copy of the organisers' files in place; the checkout on the laptop is never touched, and the sim, the
evaluator and the scoring all read the same edited files, so they stay consistent with each other.

    python scene_variant.py --colors real --dr wide --placement wide --instructions shape

  --colors real        the foam blocks the organisers announced on Discord (14 Nov): yellow, purple, orange, with
                       their real sort_fixed mapping yellow -> left, purple -> center, orange -> right.
                       (orange objects in front of orange bins: on purpose, that is the real setup.)
  --colors pastel      washed-out shades of the same three (worn foam, strong light)
  --dr wide            writes sim/dr/wide.yaml: the organisers' training randomisation with wider object shades
                       (hue / saturation / brightness), lighting, camera noise and camera pose error. Then start
                       the sim with AALTO_DR=wide (modal_sim.py: --dr wide).
  --placement wide     objects anywhere between the robot and the bins (not only the nominal 7 cm strip), any yaw
  --instructions shape sort_language instructions that name shapes, or colour and shape together, as the
                       organisers said the finals may ("colour, shape or both"). These sentences are ours.

  --tip triangles      every triangular prism lies on a rectangular face (ridge up, any yaw) instead of standing on
                       a triangular one, as a prism looks after it fell over (tests the v1.5 ridge grasp).

What a variant does NOT change: object size, the bins, the counter, the camera. Without --tip, prisms always stand
on a triangular face (the sim has no lying prisms).
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = next((p for p in (Path("/opt/aalto"), ROOT.parent / "aaltonomous-humanoid") if (p / "aaltonomous").is_dir()), None)

COLORS = {
    "real": {"yellow": [235, 200, 20], "purple": [125, 70, 175], "orange": [245, 135, 25]},
    "pastel": {"yellow": [240, 220, 110], "purple": [165, 130, 200], "orange": [245, 170, 100]},
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colors", choices=sorted(COLORS), default=None)
    ap.add_argument("--dr", choices=["wide"], default=None)
    ap.add_argument("--placement", choices=["wide"], default=None)
    ap.add_argument("--instructions", choices=["shape"], default=None)
    ap.add_argument("--tip", choices=["triangles"], default=None)
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
    scene.write_text(s)
    tasks.write_text(t)
    print(f"scene variant applied in {REPO}: colors={a.colors} dr={a.dr} placement={a.placement} "
          f"instructions={a.instructions} tip={a.tip}")


if __name__ == "__main__":
    main()
