"""Patch Marcus's agent (adk_agents/robot_sorter/serve.py) to install bot-icelli's runtime patches (policy/runtime.py):
smooth, jerk-limited arm motions (policy/smooth_motion.py) and planner config overrides from the environment
(policy/cfg_overrides.py: AALTO_CFG_OVERRIDES, ARM_XY_OFFSET).

`runtime.install()` must run before `agent/skills/planner.py` and `agent/skills/context.py` are imported, because they
copy Aalto's `time_scale` / `load_config` in by name. serve.py imports them through `.robot`, so the call goes right
after the zmq block, before any other import. The image ships the three modules in /app (on PYTHONPATH).

    python patch_smooth.py <path to adk_agents/robot_sorter>
"""
import sys
from pathlib import Path

f = Path(sys.argv[1]) / "serve.py"
t = f.read_text(encoding="utf-8")
ANCHOR = 'sys.modules["zmq"] = None\n'
LINE = ("import runtime  # noqa: E402  bot-icelli: smooth arm motions + planner config from the environment\n"
        "runtime.install()\n")
if LINE in t:
    print("runtime patches: already in serve.py")
elif t.count(ANCHOR) == 1:
    f.write_text(t.replace(ANCHOR, ANCHOR + LINE), encoding="utf-8")
    print("patched: smooth arm motions + planner config overrides (serve.py)")
else:
    print("NOT patched: serve.py changed; add `import runtime; runtime.install()` before its imports by hand")
