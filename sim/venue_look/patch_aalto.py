"""Add a switchable "look" to Aalto's sim scene, without changing the default.

Run ON THE SIM MACHINE against a clone of Aalto's repo (never against our submodule):
    python sim/venue_look/patch_aalto.py /root/aaltonomous-humanoid

It edits two files in that clone (idempotent; fails loudly if Aalto's code changed):
  aaltonomous/sim/aalto_task/scene_cfg.py   reads $AALTO_LOOK (a yaml, see venue.yaml): colours, materials,
                                            table texture, bin liners, backdrop, lights. Appearance only.
  aaltonomous/scene/scene.py                reads $AALTO_SCENE (a scene yaml) instead of scene.yaml: geometry.
With neither variable set the sim is exactly Aalto's nominal scene.
"""
import sys
from pathlib import Path

MARK = "# [bot-icelli look]"


def sub(s, old, new, count=1):
    assert s.count(old) == count, f"expected {count}x, found {s.count(old)}x:\n{old}"
    return s.replace(old, new)


def patch_scene_py(p):
    s = p.read_text()
    if MARK in s:
        return False
    s = sub(s, "from dataclasses import dataclass\n", "import os\nfrom dataclasses import dataclass\n")
    s = sub(s, 'with open(path or HERE / "scene.yaml") as f:',
            f'with open(path or os.environ.get("AALTO_SCENE") or HERE / "scene.yaml") as f:  {MARK}')
    p.write_text(s)
    return True


LOOK_HELPERS = f'''

{MARK} AALTO_LOOK=<yaml> overrides appearance only (see bot-icelli sim/venue_look/venue.yaml). Unset = nominal.
def _load_look():
    ref = os.environ.get("AALTO_LOOK", "")
    if not ref or ref == "off":
        return {{}}
    with open(ref) as f:
        d = yaml.safe_load(f) or {{}}
    d["_dir"] = str(Path(ref).resolve().parent)
    print(f"[aalto] look: {{d.get('name', ref)}} ({{ref}})")
    return d


LOOK = _load_look()


def _look(key, default=None):
    """_look("counter.rgb") -> value from the look yaml, or default."""
    d = LOOK
    for k in key.split("."):
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return default if d is None else d


def _lin(v):
    """Look colours are sRGB 0-255 (as sampled from photos); USD diffuse colours are linear 0-1."""
    out = []
    for x in v:
        c = float(x) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def _look_rgb(key, default):
    """Look colour (sRGB 0-255 -> linear), or Aalto's default: the 0-1 tuple the nominal scene already uses."""
    v = _look(key)
    return _lin(v) if v is not None else tuple(default)
'''


def patch_scene_cfg(p):
    s = p.read_text()
    if MARK in s:
        return False
    s = sub(s, "from pathlib import Path\n\nimport numpy as np\nimport yaml\n",
            "import os\nfrom pathlib import Path\n\nimport numpy as np\nimport yaml\n")
    s = sub(s, 'ENV = "/World/envs/env_.*"\n', 'ENV = "/World/envs/env_.*"\n' + LOOK_HELPERS)

    # object colours
    s = sub(s, "def _rgb(name):\n    return tuple(c / 255.0 for c in SC.colors[name])",
            "def _rgb(name):\n    return _look_rgb(f\"objects.colors.{name}\", tuple(c / 255.0 for c in SC.colors[name]))")
    s = sub(s, "visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=_rgb(color), roughness=0.7, metallic=0.0),",
            "visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=_rgb(color),\n"
            "                                                                roughness=float(_look(\"objects.roughness\", 0.7)),\n"
            "                                                                metallic=0.0),")

    # textured quad: roughness knob
    s = sub(s, "    texture: str = \"\"\n    uvs: tuple",
            "    texture: str = \"\"\n    roughness: float = 0.9\n    uvs: tuple")
    s = sub(s, 'sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)',
            'sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(cfg.roughness))')

    # static box: optional visual-only
    s = sub(s, "def _static_box(name, center_pelvis, size, rgb, roughness=0.8):",
            "def _static_box(name, center_pelvis, size, rgb, roughness=0.8, collide=True):")
    s = sub(s, "            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=True, contact_offset=0.005,\n"
               "                                                             rest_offset=0.0),\n"
               "            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=rgb, roughness=roughness, metallic=0.0),\n"
               "            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.8, dynamic_friction=0.6,\n"
               "                                                            restitution=0.0),\n",
            "            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=True, contact_offset=0.005,\n"
            "                                                             rest_offset=0.0) if collide else None,\n"
            "            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=rgb, roughness=roughness, metallic=0.0),\n"
            "            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.8, dynamic_friction=0.6,\n"
            "                                                            restitution=0.0) if collide else None,\n")

    # counter colour + gloss
    s = sub(s, 'return _static_box("Counter", centre, (size[1], size[0], COUNTER_THICKNESS), (0.55, 0.45, 0.35))',
            'return _static_box("Counter", centre, (size[1], size[0], COUNTER_THICKNESS),\n'
            '                       _look_rgb("counter.rgb", (0.55, 0.45, 0.35)), float(_look("counter.roughness", 0.8)))')

    # mat: other texture (optionally covering the whole counter top) or hidden
    s = sub(s, "    centre = SC.mat_to_pelvis([mat[0] / 2, mat[1] / 2, 0.0005])\n"
               "    return AssetBaseCfg(\n"
               "        prim_path=f\"{ENV}/Mat\",\n"
               "        init_state=AssetBaseCfg.InitialStateCfg(pos=_w(centre)),\n"
               "        spawn=TexturedQuadCfg(size=(float(mat[1]), float(mat[0])), texture=str(ASSETS / c[\"mat_texture\"]),\n",
            "    centre = SC.mat_to_pelvis([mat[0] / 2, mat[1] / 2, 0.0005])\n"
            "    texture = str(ASSETS / c[\"mat_texture\"])\n"
            "    if _look(\"table.texture\"):                      # look: e.g. bare plywood instead of the printed mat\n"
            "        texture = str(Path(LOOK[\"_dir\"]) / _look(\"table.texture\"))\n"
            "        if _look(\"table.cover_counter\", True):\n"
            "            mat = np.asarray(c[\"counter_size\"], float)\n"
            "    return AssetBaseCfg(\n"
            "        prim_path=f\"{ENV}/Mat\",\n"
            "        init_state=AssetBaseCfg.InitialStateCfg(pos=_w(centre)),\n"
            "        spawn=TexturedQuadCfg(size=(float(mat[1]), float(mat[0])), texture=texture,\n"
            "                              roughness=float(_look(\"table.roughness\", 0.9)),\n")

    # bins: colour + cardboard liner (visual only, stops below the rim so the rim keeps the bin colour)
    s = sub(s, "        rgb = tuple(c / 255.0 for c in SC.bin_rgb)\n",
            "        rgb = _look_rgb(\"bins.rgb\", tuple(c / 255.0 for c in SC.bin_rgb))\n")
    s = sub(s, "            out[f\"bin_{name}_{part}\"] = _static_box(f\"Bin_{name}_{part}\", SC.mat_to_pelvis(c), (s[1], s[0], s[2]), rgb)\n",
            "            out[f\"bin_{name}_{part}\"] = _static_box(f\"Bin_{name}_{part}\", SC.mat_to_pelvis(c), (s[1], s[0], s[2]), rgb,\n"
            "                                                    float(_look(\"bins.roughness\", 0.8)))\n"
            "        if _look(\"bins.liner_rgb\"):\n"
            "            e, rim = 0.001, float(_look(\"bins.liner_below_rim\", 0.008))\n"
            "            hl, lrgb = h - ft - rim, _lin(_look(\"bins.liner_rgb\"))\n"
            "            liners = {\n"
            "                \"floor\": ((cx, cy, ft + e / 2), (ox - 2 * t, oy - 2 * t, e)),\n"
            "                \"xlo\": ((cx - ox / 2 + t + e / 2, cy, ft + hl / 2), (e, oy - 2 * t, hl)),\n"
            "                \"xhi\": ((cx + ox / 2 - t - e / 2, cy, ft + hl / 2), (e, oy - 2 * t, hl)),\n"
            "                \"ylo\": ((cx, cy - oy / 2 + t + e / 2, ft + hl / 2), (ox - 2 * t - 2 * e, e, hl)),\n"
            "                \"yhi\": ((cx, cy + oy / 2 - t - e / 2, ft + hl / 2), (ox - 2 * t - 2 * e, e, hl)),\n"
            "            }\n"
            "            for part, (c, s) in liners.items():\n"
            "                out[f\"bin_{name}_liner_{part}\"] = _static_box(f\"BinLiner_{name}_{part}\", SC.mat_to_pelvis(c),\n"
            "                                                              (s[1], s[0], s[2]), lrgb, 0.9, collide=False)\n"
            "        tape = (_look(\"bins.rim_tape\") or {}).get(name)   # paper/tape folded over the opening, per bin\n"
            "        if tape:\n"
            "            e = 0.001\n"
            "            wn, wf, wl, wr = (float(tape.get(k, 0.0)) for k in (\"near\", \"far\", \"left\", \"right\"))\n"
            "            ys, yc = oy - wn - wf, cy + (wn - wf) / 2          # side strips fill the span between near and far\n"
            "            strips = {  # robot's view: near = low mat y, left = high mat x\n"
            "                \"near\": ((cx, cy - oy / 2 + wn / 2, h + e / 2), (ox, wn, e)),\n"
            "                \"far\": ((cx, cy + oy / 2 - wf / 2, h + e / 2), (ox, wf, e)),\n"
            "                \"left\": ((cx + ox / 2 - wl / 2, yc, h + e / 2), (wl, ys, e)),\n"
            "                \"right\": ((cx - ox / 2 + wr / 2, yc, h + e / 2), (wr, ys, e)),\n"
            "            }\n"
            "            for part, (c, s) in strips.items():\n"
            "                if min(s) > 0:\n"
            "                    out[f\"bin_{name}_tape_{part}\"] = _static_box(\n"
            "                        f\"BinTape_{name}_{part}\", SC.mat_to_pelvis(c), (s[1], s[0], s[2]),\n"
            "                        _look_rgb(\"bins.rim_tape_rgb\", rgb), float(_look(\"bins.roughness\", 0.8)),\n"
            "                        collide=bool(_look(\"bins.rim_tape_collide\", False)))\n")

    # lid colour
    s = sub(s, "visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.85, 0.85, 0.85), roughness=0.8)),",
            "visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=_look_rgb(\"lid.rgb\", (0.85, 0.85, 0.85)),\n"
            "                                                                     roughness=0.8)),")

    # floor, lights
    s = sub(s, "visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.35, 0.35, 0.38)))),",
            "visual_material=sim_utils.PreviewSurfaceCfg(\n"
            "                                          diffuse_color=_look_rgb(\"floor.rgb\", (0.35, 0.35, 0.38))))),")
    s = sub(s, "spawn=sim_utils.DomeLightCfg(color=(0.9, 0.9, 0.9), intensity=800.0)),",
            "spawn=sim_utils.DomeLightCfg(color=tuple(_look(\"lights.dome_color\", (0.9, 0.9, 0.9))),\n"
            "                                                                intensity=float(_look(\"lights.dome_intensity\", 800.0)))),")
    s = sub(s, "                                  init_state=AssetBaseCfg.InitialStateCfg(pos=(0.5, 0.0, 2.2)),\n"
               "                                  spawn=sim_utils.SphereLightCfg(color=(1.0, 0.97, 0.92), intensity=60000.0,\n"
               "                                                                 radius=0.15)),\n",
            "                                  init_state=AssetBaseCfg.InitialStateCfg(\n"
            "                                      pos=tuple(_look(\"lights.key_pos\", (0.5, 0.0, 2.2)))),\n"
            "                                  spawn=sim_utils.SphereLightCfg(\n"
            "                                      color=tuple(_look(\"lights.key_color\", (1.0, 0.97, 0.92))),\n"
            "                                      intensity=float(_look(\"lights.key_intensity\", 60000.0)),\n"
            "                                      radius=float(_look(\"lights.key_radius\", 0.15)))),\n")

    # backdrop walls (visual only): far side + both sides, e.g. black curtains
    s = sub(s, "def make_scene_cfg_class(name=\"AaltoSceneCfg\", lid=False):",
            "def backdrop_cfgs():\n"
            "    \"\"\"Look: visual-only walls behind the bins and on both sides (pelvis frame), e.g. black curtains.\"\"\"\n"
            "    if not _look(\"backdrop.rgb\"):\n"
            "        return {}\n"
            "    d, hgt, rgb = float(_look(\"backdrop.distance\", 1.5)), float(_look(\"backdrop.height\", 3.0)), _lin(_look(\"backdrop.rgb\"))\n"
            "    walls = {\"far\": ((d, 0.0, 0.5), (0.02, 2 * d, hgt)), \"left\": ((0.0, d, 0.5), (2 * d, 0.02, hgt)),\n"
            "             \"right\": ((0.0, -d, 0.5), (2 * d, 0.02, hgt))}\n"
            "    return {f\"backdrop_{k}\": _static_box(f\"Backdrop_{k}\", c, sz, rgb, 0.95, collide=False) for k, (c, sz) in walls.items()}\n"
            "\n\n"
            "def make_scene_cfg_class(name=\"AaltoSceneCfg\", lid=False):")
    s = sub(s, "    attrs = {**_fixed_cfgs(), **bin_cfgs(), **object_cfgs()}\n",
            "    attrs = {**_fixed_cfgs(), **bin_cfgs(), **object_cfgs(), **backdrop_cfgs()}\n")
    p.write_text(s)
    return True


if __name__ == "__main__":
    repo = Path(sys.argv[1])
    for rel, fn in (("aaltonomous/scene/scene.py", patch_scene_py),
                    ("aaltonomous/sim/aalto_task/scene_cfg.py", patch_scene_cfg)):
        print(("patched  " if fn(repo / rel) else "already  ") + rel)
