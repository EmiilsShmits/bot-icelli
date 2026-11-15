"""Start our policy server (policy/server.py) with an optional scene.yaml for the POLICY's own geometry (bins, walls),
without patching Aalto's code: Scene.load() then defaults to that file. Test tooling only; the submission image is
unchanged (it ships Aalto's scene.yaml).

    PYTHONPATH=third_party/aaltonomous-humanoid .venv/bin/python sim/mujoco/serve.py \
        --scene artifacts/mujoco/scene_measured.yaml -- --policy v1.6 --port 8000
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=None, help="scene.yaml the policy should assume (default: Aalto's)")
    a, rest = ap.parse_known_args()
    if a.scene:
        from aaltonomous.scene.scene import Scene
        orig, path = Scene.load.__func__, str(Path(a.scene).resolve())
        Scene.load = classmethod(lambda cls, p=None: orig(cls, p or path))
        print(f"[serve] policy geometry: {path}", flush=True)
    sys.argv = [str(ROOT / "policy" / "server.py")] + [x for x in rest if x != "--"]
    sys.path.insert(0, str(ROOT / "policy"))
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
