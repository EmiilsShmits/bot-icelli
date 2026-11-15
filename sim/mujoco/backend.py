"""MuJoCo backend for Aalto's AaltoEnv (same duck-typed contract as aaltonomous/interface/backends.py MockBackend):
reset_scene(layout, instruction), joints(), command(arm_q, hand_q), advance(dt), images(), close(), plus state() for
scoring. The scene comes from build.py (Unitree G1 + Dex3, measured venue geometry).

    python sim/mujoco/backend.py --snapshot artifacts/mujoco/snap --seed 1000     # head + overview PNGs of a layout
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B                                              # noqa: E402
from aaltonomous.sim.aalto_task import layout as LAY           # noqa: E402

H, W = 480, 640


class MujocoClock:
    """Sim clock for AaltoEnv, like Aalto's SimClock for Isaac (interface/backends.py): AaltoEnv paces its 30 Hz
    ticks and counts rates, time limit and watchdog in SIM seconds. The physics here only moves in advance(), so
    wait_until() runs the sim at a fixed real-time factor `rtf` (Isaac runs at ~0.5-0.65 with cameras): a tick of
    1/30 s sim time takes (1/30)/rtf s of wall time. If the Mac is slower than that, the sim just runs slower (as Isaac
    does under load); the policy is never starved by the laptop."""

    def __init__(self, data, rtf):
        self.data, self.rtf = data, float(rtf)
        self.anchor = None                               # (wall, sim) at the last re-anchor

    def now(self):
        return float(self.data.time)

    def reset(self):
        self.anchor = None

    def wait_until(self, t):
        import time
        wall = time.monotonic()
        if self.anchor is None:
            self.anchor = (wall, self.now())
        w0, s0 = self.anchor
        target = w0 + (t - s0) / self.rtf
        if target > wall:
            time.sleep(target - wall)
        elif wall - target > 0.25:                       # sim behind (slow Mac): re-anchor, no catch-up burst
            self.anchor = (wall, t)


def _qmul(a, b):
    """Hamilton product of two xyzw quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def tip_triangles(sc, poses, active):
    """Active triangular prisms lie on the face opposite the apex (ridge up), then the layout yaw; dropped from 2.4 cm.
    Same as the Isaac variant (modal_pipeline/sim/scene_variant.py TIP_TRIANGLES)."""
    roll = np.array([np.sin(np.pi / 4), 0.0, 0.0, np.cos(np.pi / 4)])
    out = dict(poses)
    for n in active:
        if LAY.parse_name(n)[1] == "triangle":
            p, q = poses[n]
            p = np.array(p, float)
            p[2] += 0.024 - sc.object_height("triangle") / 2
            out[n] = (p, _qmul(q, roll))
    return out


class MujocoBackend:
    name = "mujoco"
    has_success = False

    def __init__(self, cfg=None, colors="venue", viewer=False, overview=False, rtf=None, tip=False, **_):
        """viewer: open MuJoCo's live window (macOS: run under `mjpython`). overview: also render the third-person
        camera each tick (videos). rtf: run on a sim clock at this real-time factor (MujocoClock); None = wall time.
        tip: triangular prisms lie on a rectangular face (ridge up), as modal_pipeline/sim/scene_variant.py --tip."""
        self.tip = tip
        self.cfg = cfg or B.load_cfg()
        self.model, self.sc = B.build(self.cfg, colors)
        self.data = mujoco.MjData(self.model)
        self.clock = MujocoClock(self.data, rtf) if rtf else None
        m = self.model
        jid = lambda n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)
        self.arm_q_adr = np.array([m.jnt_qposadr[jid(n)] for n in B.ARM])
        self.arm_v_adr = np.array([m.jnt_dofadr[jid(n)] for n in B.ARM])
        self.hand_q_adr = np.array([m.jnt_qposadr[jid(n)] for n in B.HAND])
        self.act = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, n) for n in B.ARM + B.HAND])
        self.objects = LAY.object_names(self.sc)
        self.obj_adr = {n: m.jnt_qposadr[jid(n)] for n in self.objects}
        self.obj_vadr = {n: m.jnt_dofadr[jid(n)] for n in self.objects}
        self.cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "head_d435")
        self.rgb_r = mujoco.Renderer(m, H, W)
        self.depth_r = mujoco.Renderer(m, H, W)
        self.depth_r.enable_depth_rendering()
        self.head_opt = mujoco.MjvOption()
        self.head_opt.geomgroup[B.HEAD_GROUP] = 0     # the camera looks out of the head shell
        self.over_r = mujoco.Renderer(m, 480, 640) if overview else None
        self.last_overview = self.last_frame = None
        self.video, self.video_every, self._tick = None, 3, 0     # video: list of frames (head | overview) or None
        self.active = []
        self.pelvis_w = np.array([0.0, 0.0, self.cfg["robot"]["pelvis_height"]])
        self.viewer = None
        if viewer:
            from mujoco import viewer as mjviewer
            self.viewer = mjviewer.launch_passive(m, self.data)
            self.viewer.cam.lookat[:] = [0.35, 0.0, 0.85]
            self.viewer.cam.distance, self.viewer.cam.azimuth, self.viewer.cam.elevation = 1.6, 200, -35

    # ------------------------------------------------------------------ contract
    def reset_scene(self, layout, instruction=None):
        m, d = self.model, self.data
        mujoco.mj_resetData(m, d)
        home = np.array([LAY.ARM_HOME[n] for n in B.ARM])
        d.qpos[self.arm_q_adr] = home
        d.qpos[self.hand_q_adr] = 0.0
        d.ctrl[self.act] = np.r_[home, np.zeros(14)]
        poses, self.active = LAY.assign(self.sc, layout)
        if self.tip:
            poses = tip_triangles(self.sc, poses, self.active)
        for n, (p, q_xyzw) in poses.items():
            a = self.obj_adr[n]
            d.qpos[a:a + 3] = p + self.pelvis_w
            d.qpos[a + 3:a + 7] = [q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]]
        mujoco.mj_forward(m, d)
        self._step(0.5)                                # let the objects settle on the table
        d.time = 0.0
        if self.clock is not None:
            self.clock.reset()
        self._sync()

    def joints(self):
        d = self.data
        return (d.qpos[self.arm_q_adr].astype(np.float32).copy(), d.qvel[self.arm_v_adr].astype(np.float32).copy(),
                d.qpos[self.hand_q_adr].astype(np.float32).copy())

    def command(self, arm_q, hand_q):
        lo, hi = self.model.actuator_ctrlrange[self.act].T
        self.data.ctrl[self.act] = np.clip(np.r_[np.asarray(arm_q, float), np.asarray(hand_q, float)], lo, hi)

    def advance(self, dt):
        self._step(dt)
        self._tick += 1
        self._sync()

    def images(self):
        d = self.data
        self.rgb_r.update_scene(d, camera=self.cam, scene_option=self.head_opt)
        rgb = self.rgb_r.render().copy()
        self.depth_r.update_scene(d, camera=self.cam, scene_option=self.head_opt)
        z = self.depth_r.render()
        depth = np.where((z > 0.1) & (z < 10.0), np.round(z * 1000.0), 0).astype(np.uint16)
        if self.over_r is not None and self._tick % self.video_every == 0:
            self.over_r.update_scene(d, camera="overview")
            self.last_overview = self.over_r.render().copy()
            self.last_frame = np.hstack([rgb, self.last_overview])     # head | overview (videos, live feed)
            if self.video is not None:
                self.video.append(self.last_frame)
        blank = np.zeros((H, W, 3), np.uint8)
        return {"head_rgb": rgb, "head_depth": depth, "left_wrist_rgb": blank, "right_wrist_rgb": blank.copy()}

    def close(self):
        for r in (self.rgb_r, self.depth_r, self.over_r):
            if r is not None:
                r.close()
        if self.viewer is not None:
            self.viewer.close()

    # ------------------------------------------------------------------ extras
    def _step(self, dt):
        t_end = self.data.time + dt - 1e-9
        while self.data.time < t_end:
            mujoco.mj_step(self.model, self.data)

    def _sync(self):
        if self.viewer is not None and self.viewer.is_running():
            self.viewer.sync()

    def settle(self, seconds):
        self._step(seconds)
        self._sync()

    def state(self):
        """[{name, color, shape, active, pos (pelvis, m), speed}] for aalto_task.layout.evaluate."""
        out = []
        for n in self.objects:
            a, v = self.obj_adr[n], self.obj_vadr[n]
            c, s, _ = LAY.parse_name(n)
            out.append({"name": n, "color": c, "shape": s, "active": n in self.active,
                        "pos": (self.data.qpos[a:a + 3] - self.pelvis_w).tolist(),
                        "speed": float(np.linalg.norm(self.data.qvel[v:v + 3]))})
        return out


def main():
    import imageio.v2 as iio
    from aaltonomous.interface import tasks
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--colors", default="venue")
    a = ap.parse_args()
    be = MujocoBackend(colors=a.colors, overview=True)
    lay = tasks.sample_layout(np.random.default_rng(a.seed), **be.sc.layout_kwargs())
    be.reset_scene(lay)
    im = be.images()
    out = Path(a.snapshot)
    out.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(f"{out}_head.png", im["head_rgb"])
    iio.imwrite(f"{out}_overview.png", be.last_overview)
    dep = im["head_depth"].astype(float)
    print("layout", [(o["color"], o["shape"]) for o in lay], "depth mm min/med/max", dep[dep > 0].min(),
          np.median(dep[dep > 0]), dep.max())
    be.close()


if __name__ == "__main__":
    main()
