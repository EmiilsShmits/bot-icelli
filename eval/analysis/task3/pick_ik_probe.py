"""Task-3 cylinder pick IK, offline: the planned error of each pick waypoint (grasp, pregrasp, descend, lift) with
LID_PICK_TOL off (the planner's 6 mm) and at 2 mm, over a grid of block positions, arms parked (insert.py's PARK).
Needs decision_oracle.test_insert / test_offline, which the image leaves out: mount the repo's policy/ (README)."""
import sys
import time

import numpy as np

sys.path.insert(0, "/app/policy")
from aaltonomous.baselines.classical.perception import Detection
from aaltonomous.interface import tasks
from aaltonomous.scene.scene import Scene

from decision_oracle import insert as I
from decision_oracle.test_insert import insert_layout
from decision_oracle.test_offline import FakeClient, setup
from decision_oracle.upgrades_v16 import V16OraclePolicy

scene = Scene.load()
lay = insert_layout(np.random.default_rng(0), scene)
fc = FakeClient(scene, lay)
pol = V16OraclePolicy(fc, sides="off", perception="privileged", threaded=False, prefetch=False, log=None,
                      labels="off", instruction="rules")
info = I.configure(pol, "insert_shapes", {"instruction": tasks.INSERT_INSTRUCTION})
pol.reset(info)
I.after_reset(pol)
setup(pol)
ik = pol.kin.cfg["ik"]
base_tol = ik["pos_tol"]
print("kin cfg is planner cfg:", pol.kin.cfg is pol.planner.cfg, "pos_tol", base_tol)
z = pol.scene.counter_z + pol.scene.object_height()


def plan_at(x, y, tol):
    import os
    d = Detection("yellow", np.array([x, y, z]), 1000, 1000, "probe", 0.0)
    d.shape = "cylinder"
    d.name = "probe"
    os.environ["LID_PICK_TOL"] = str(tol)
    try:
        t = time.monotonic()
        p = pol.planner.plan(d, pol.home, pol.post["open"], bin_name="hole_cylinder", relocate=False)
        dt = time.monotonic() - t
    finally:
        os.environ.pop("LID_PICK_TOL", None)
    assert ik["pos_tol"] == base_tol, ik["pos_tol"]
    if not p.ok:
        return f"FAIL ({p.reason[:50]}) {dt:.1f}s"
    w = {k: v for k, v in p.ik.items() if k in ("grasp", "pregrasp", "descend", "lift")}
    s = " ".join(f"{k}={1000 * v[1]:.1f}/{v[2]:.0f}d" for k, v in w.items())
    return f"{p.side:5} max={1000 * max(v[1] for v in p.ik.values()):.1f} {s} {dt:.1f}s"


for x, y in [(0.33, -0.16), (0.29, -0.03), (0.26, -0.03), (0.27, -0.09), (0.32, -0.03), (0.32, -0.16), (0.33, -0.08),
             (0.30, -0.12), (0.35, -0.05), (0.25, -0.15), (0.36, -0.14), (0.28, 0.0)]:
    print(f"({x:.2f},{y:+.2f}) default: {plan_at(x, y, 0)}")
    print(f"            LID_PICK_TOL=0.002: {plan_at(x, y, 0.002)}")
    sys.stdout.flush()
