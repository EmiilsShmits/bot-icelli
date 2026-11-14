"""Offline checks (no sim): a fake scene service built from random layouts.

    PYTHONPATH=/root/aaltonomous-humanoid:/root python -m decision_oracle.test_offline [--layouts 20] [--decision IMG]

1. DefaultChooser + budget 0 picks exactly what Aalto's OraclePolicy picks (object, arm, plan length).
2. Every enumerated option (budget 8 s) is a plan that passed the planner's checks with 0 dry-run clips.
3. --decision IMG: one live Decision 1 call on the first layout, with IMG as the head image (prints the record).
"""
from __future__ import annotations

import argparse
import collections
import json
import time

import numpy as np

from aaltonomous.interface import tasks
from aaltonomous.scene.scene import Scene
from aaltonomous.sim.oracle import OraclePolicy

from .chooser import DecisionChooser
from .policy import DecisionOraclePolicy


class FakeClient:
    def __init__(self, scene, layout):
        self.objs = []
        n = collections.Counter()
        for o in layout:
            k = n[(o["color"], o["shape"])]
            n[(o["color"], o["shape"])] += 1
            p = scene.mat_to_pelvis(np.array([o["x"], o["y"], 0.0]))
            p[2] = scene.counter_z + scene.object_height(o["shape"]) / 2
            yaw = float(o.get("yaw", 0.0))
            self.objs.append({"name": f"obj_{o['color']}_{o['shape']}_{k}", "active": True, "pos": p.tolist(),
                              "shape": o["shape"], "color": o["color"], "speed": 0.0,
                              "quat_xyzw": [0, 0, np.sin(yaw / 2), np.cos(yaw / 2)]})

    def state(self):
        return {"objects": self.objs}


def setup(pol):
    pol.arm_cmd, pol.hand_cmd = pol.home.copy(), pol.post["open"].copy()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--layouts", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=float, default=8.0)
    ap.add_argument("--decision", default=None, help="image (jpg) for one live Decision 1 call")
    a = ap.parse_args(argv)
    scene = Scene.load()
    same = diff = none_both = 0
    n_opt, bad, t_enum, kinds = [], 0, [], collections.Counter()
    for i in range(a.layouts):
        rng = np.random.default_rng(a.seed + i)
        layout = tasks.sample_layout(rng, **scene.layout_kwargs())
        fc = FakeClient(scene, layout)
        ref = OraclePolicy(fc, threaded=False, prefetch=False, log=None)
        setup(ref)
        r = ref._plan_next(ref.arm_cmd, ref.hand_cmd, commit=False)
        mine = DecisionOraclePolicy(fc, chooser="default", threaded=False, prefetch=False, log=None)
        setup(mine)
        m = mine._plan_next(mine.arm_cmd, mine.hand_cmd, commit=False)
        if r[0] == "none" and m[0] == "none":
            none_both += 1
        elif r[0] == m[0] == "plan" and r[1].obj == m[1].obj and r[1].side == m[1].side and len(r[1].arm) == len(m[1].arm):
            same += 1
        else:
            diff += 1
            print(f"layout {i}: aalto {r[0]} {getattr(r[1], 'obj', None)} {getattr(r[1], 'side', None)}  "
                  f"mine {m[0]} {getattr(m[1], 'obj', None)} {getattr(m[1], 'side', None)}")
        # enumeration
        setup(mine)
        mine._update_drop_offsets()
        dets = mine.perception.detect()
        t = time.monotonic()
        opts, info = mine.enum.feasible_options(dets, mine.arm_cmd, mine.hand_cmd, budget_s=a.budget)
        t_enum.append(time.monotonic() - t)
        n_opt.append(len(opts))
        for o in opts:
            kinds[(o.shape, o.arm, o.grasp[:4], o.route)] += 1
            if not o.plan.ok or (o.plan.safety_clips or 0) != 0:
                bad += 1
        print(f"layout {i}: {len(dets)} objects, {len(opts)} options in {t_enum[-1]:.1f} s "
              f"(default {info['t_default_s']} s, budget hit {info['budget_hit']}), "
              f"objects with options {len({o.obj for o in opts})}, no direct {info['no_direct']}", flush=True)
        if a.decision and i == 0 and opts:
            ch = DecisionChooser()
            with open(a.decision, "rb") as f:
                img = f.read()
            ctx = {"dets": dets, "mapping_text": "red -> left, yellow -> center, blue -> right", "time_left": 100,
                   "attempts": {}, "retry_objs": [], "drop_choices": mine.enum.drop_choices, "jpeg": img}
            o, d, rec = ch.choose(opts, ctx)
            print(json.dumps({"chosen": o.to_json(), "drop": d, **rec}, indent=1, default=str)[:4000])
    print(f"\nsame choice as Aalto: {same}/{a.layouts} (both none {none_both}, different {diff})")
    print(f"options per look: mean {np.mean(n_opt):.1f}  min {min(n_opt)}  max {max(n_opt)};  "
          f"enumeration s: mean {np.mean(t_enum):.1f} max {max(t_enum):.1f}")
    print(f"options that failed a check: {bad}")
    for k, v in sorted(kinds.items()):
        print(f"  {k}: {v}")
    return 0 if diff == 0 and bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
