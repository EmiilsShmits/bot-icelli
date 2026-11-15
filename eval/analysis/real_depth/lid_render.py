"""The lid finder (policy/decision_oracle/boxes_v16.py) on rendered depth of Aalto's real lid.

There is no real frame with the lid yet, so this renders one: the camera pose and the three boxes are taken from a
real drop-3 depth frame (measured by find_boxes), the boxes are rebuilt in MuJoCo with thin walls, moved `closer` cm
towards the robot, and the lid's own STL is laid on a box in every turn, lip down and lip up. Depth gets noise
(1.7 mm rms, as measured on the real table) and holes at depth edges. Then find_boxes + find_lid run on it and the
hole centres are compared with where the STL's holes really are.

Usage (repo root, .venv with mujoco: sim/mujoco/requirements.txt):
    PYTHONPATH=third_party/aaltonomous-humanoid:policy .venv/bin/python eval/analysis/real_depth/lid_render.py \
        artifacts/real_frames/lid/lid_shape_holes_200mm.stl artifacts/real_frames/drop3/depth_ep03_start.npy [out dir]
"""
import copy
import struct
import sys

import mujoco
import numpy as np

from aaltonomous.interface.calibration import Calibration
from aaltonomous.scene.scene import Scene
from decision_oracle import boxes_v16 as B
from decision_oracle import camera as C
LEVELLED = getattr(C, "fit_head_pose_levelled", C.fit_head_pose)   # levelled table-frame fit (older camera.py: fit_head_pose)

FOCAL = 604.5                    # the renderer's camera: the real focal length, principal point at the image centre
STL_HOLES = {"cube": (-0.048, -0.035), "cylinder": (0.048, -0.035), "triangle": (0.0, 0.0393)}   # stl_holes.py, m
PLATE = 0.004


def stl_bounds(path):
    with open(path, "rb") as f:
        raw = f.read()
    n = struct.unpack("<I", raw[80:84])[0]
    a = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n, offset=84)
    v = a["v"].reshape(-1, 3).astype(float) * 0.001
    return v.min(0), v.max(0)


def rz(a):
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])


def quat(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, float).reshape(-1))
    return q


def scene_xml(stl, T, zc, boxes, wall, lid_R, lid_p, thick=0.005):
    R = T[:3, :3]
    g = [f'<geom type="plane" size="3 3 0.1" pos="0 0 {zc}"/>']
    for b in boxes:
        (cx, cy), (w, d), yaw = b["center"], b["size"], b["yaw"]
        for dx, dy, sx, sy in ((d / 2 - thick / 2, 0, thick / 2, w / 2), (-d / 2 + thick / 2, 0, thick / 2, w / 2),
                               (0, w / 2 - thick / 2, d / 2, thick / 2), (0, -w / 2 + thick / 2, d / 2, thick / 2)):
            p = np.array([cx, cy, 0]) + rz(yaw) @ np.array([dx, dy, 0])
            g.append(f'<geom type="box" size="{sx} {sy} {wall / 2}" pos="{p[0]} {p[1]} {zc + wall / 2}" euler="0 0 {yaw}"/>')
    q = quat(lid_R)
    return f"""<mujoco>
  <compiler angle="radian"/>
  <visual><global offwidth="640" offheight="480"/><map znear="0.05" zfar="5"/></visual>
  <statistic extent="1" center="0.4 0 0"/>
  <asset><mesh name="lid" file="{stl}" scale="0.001 0.001 0.001"/></asset>
  <worldbody>
    {' '.join(g)}
    <body name="lid" pos="{lid_p[0]} {lid_p[1]} {lid_p[2]}" quat="{q[0]} {q[1]} {q[2]} {q[3]}">
      <geom name="lid" type="mesh" mesh="lid" contype="0" conaffinity="0"/></body>
    <camera name="head" pos="{T[0, 3]} {T[1, 3]} {T[2, 3]}" fovy="{np.degrees(2 * np.arctan(240 / FOCAL))}"
            xyaxes="{R[0, 0]} {R[1, 0]} {R[2, 0]} {-R[0, 1]} {-R[1, 1]} {-R[2, 1]}"/>
  </worldbody>
</mujoco>"""


def render(xml, rng, noise=0.0017):
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "lid")
    mid = m.geom_dataid[gid]
    V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
    W = d.geom_xpos[gid] + V @ d.geom_xmat[gid].reshape(3, 3).T          # the lid's vertices in the world
    r = mujoco.Renderer(m, 480, 640)
    r.enable_depth_rendering()
    r.update_scene(d, camera="head")
    z = r.render().astype(np.float64)
    r.close()
    gy, gx = np.gradient(z)
    edge = np.hypot(gx, gy) > 0.008                                      # real depth has holes at depth edges
    z = z + rng.normal(0, noise, z.shape) * (z / 0.6) ** 2
    bad = (edge & (rng.random(z.shape) < 0.7)) | (rng.random(z.shape) < 0.05) | (z > 1.6)
    out = np.round(z * 1000).astype(np.uint16)
    out[bad] = 0
    return out, W


def main():
    stl, frame = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    sc, cal = Scene.load(), Calibration.load()
    zc = sc.counter_z
    real = np.load(frame)
    fit = LEVELLED(real, cal, sc)
    T = fit.T
    fb = B.find_boxes(B.points(cal, real, 2), T, sc)
    assert fb["ok"], fb["why"]
    cal = copy.deepcopy(cal)                                             # from here on: the renderer's intrinsics
    cal.cams["head"].K = np.array([[FOCAL, 0, 319.5], [0, FOCAL, 239.5], [0, 0, 1.0]])
    e1, e2 = fb["frame"]["e1"], fb["frame"]["e2"]
    yaw_row = float(np.arctan2(e1[1], e1[0]))
    lo, hi = stl_bounds(stl)
    c_file = np.r_[(lo[:2] + hi[:2]) / 2, lo[2]]                         # centre of the plate's outer face (file z = 0)
    print(f"real frame: wall {fb['wall'] * 100:.1f} cm, boxes " + ", ".join(
        f"{n} ({b['center'][0] * 100:.1f}, {b['center'][1] * 100:.1f})" for n, b in fb["boxes"].items()))
    print(f"lid STL: {np.round((hi - lo) * 1000, 1)} mm\n")
    rng = np.random.default_rng(0)
    errs, n_ok, n_all, wrong, groups = [], 0, 0, 0, {}
    print("closer box    lip  turn yaw | found  turn lip yaw   | hole centre error mm (cube, cylinder, triangle) | plate z err mm | score, turn margin, side vote")
    for closer in (0.0, 0.07):
        for on in ("center",) if closer == 0.0 else ("center", "left", "right"):
            for lip_up in (False, True):
                for turn in range(4):
                    for dyaw in ((0.0,) if on != "center" else (0.0, 6.0, -4.0)):
                        boxes = [{"center": b["center"] - closer * e1, "size": b["size"], "yaw": yaw_row} for b in fb["boxes"].values()]
                        tgt = fb["boxes"][on]
                        off = rng.uniform(-0.004, 0.004, 2)              # the lid does not sit exactly centred
                        c_lid = tgt["center"] - closer * e1 + off
                        psi = yaw_row + np.radians(90.0 * turn + dyaw)
                        if lip_up:
                            R, top = rz(psi), fb["wall"] + PLATE
                            p = np.r_[c_lid, zc + fb["wall"]] - R @ c_file
                        else:
                            R, top = rz(psi) @ np.diag([-1.0, 1.0, -1.0]), fb["wall"] + PLATE
                            p = np.r_[c_lid, zc + top] - R @ c_file
                        depth, W = render(scene_xml(stl, T, zc, boxes, fb["wall"], R, p), rng)
                        assert abs(W[:, 2].min() - (zc + fb["wall"] - (0.0 if lip_up else 0.008))) < 1e-3, "lid not where it was put"
                        assert np.abs((W[:, :2].min(0) + W[:, :2].max(0)) / 2 - c_lid).max() < 1e-3, "lid not where it was put"
                        truth = {k: c_lid + rz(psi)[:2, :2] @ (np.array(q) * ([1, 1] if lip_up else [-1, 1])) for k, q in STL_HOLES.items()}
                        found = B.find_boxes(B.points(cal, depth, 2), T, sc)
                        lid = B.find_lid(B.points(cal, depth, 1), T, sc, found) if found["boxes"] else {"ok": False, "why": found["why"], "holes": {}}
                        n_all += 1
                        grp = groups.setdefault((closer, on), {"n": 0, "ok": 0, "err": [0.0], "why": []})
                        grp["n"] += 1
                        line = f"{closer * 100:4.0f}   {on:6s} {'up  ' if lip_up else 'down'} {turn}   {dyaw:+4.0f} | "
                        if lid.get("holes"):
                            e = [1000 * float(np.linalg.norm(lid["holes"][k]["center"] - truth[k])) for k in ("cube", "cylinder", "triangle")]
                            right = lid["box"] == on and lid["turn"] == turn and lid["lip_up"] == lip_up
                            n_ok += bool(lid["ok"] and right)
                            wrong += bool(lid["ok"] and not right)
                            if lid["ok"] and right:
                                errs.append(e)
                                grp["ok"] += 1
                                grp["err"].append(max(e))
                            else:
                                grp["why"].append(lid["why"])
                            line += (f"{'yes' if lid['ok'] else 'no '}    {lid['turn']}    {'up  ' if lid['lip_up'] else 'down'} {lid['yaw_deg']:+5.1f} | "
                                     f"{e[0]:5.1f} {e[1]:5.1f} {e[2]:5.1f}{'' if right else '  WRONG POSE'} | {1000 * (lid['z'] - top):+5.1f} | {lid['score']:.2f} {lid['turn_margin']:.2f} {lid['side_vote']:+.2f}"
                                     f"{'' if found['ok'] else '  (boxes: ' + found['why'] + ')'}{'' if lid['ok'] else '  ' + lid['why']}")
                        else:
                            line += f"no: {lid['why']}"
                            grp["why"].append(lid["why"].split(":")[0].split(" (")[0])
                        print(line)
                        if out:
                            np.save(f"{out}/lid_{int(closer * 100)}_{on}_{'up' if lip_up else 'down'}_{turn}_{int(dyaw)}.npy", depth)
    e = np.array(errs)
    print()
    for (closer, on), grp in groups.items():
        print(f"boxes {closer * 100:.0f} cm closer, lid on {on}: right pose {grp['ok']}/{grp['n']}, largest hole centre error "
              f"{max(grp['err']):.1f} mm" + ("; not found: " + "; ".join(sorted(set(grp["why"]))) if grp["why"] else ""))
    print(f"\nlid found in the right pose: {n_ok}/{n_all}; reported found in a WRONG pose: {wrong}")
    if len(e):
        print(f"hole centre error over those, mm: median {np.median(e):.1f}, 95th percentile {np.percentile(e, 95):.1f}, max {e.max():.1f}")
    # and without a lid: must say so
    depth, _ = render(scene_xml(stl, T, zc, [{"center": b["center"], "size": b["size"], "yaw": yaw_row} for b in fb["boxes"].values()],
                                fb["wall"], np.eye(3), np.array([5.0, 5.0, 0.0])), rng)
    found = B.find_boxes(B.points(cal, depth, 2), T, sc)
    print("no lid in the scene ->", B.find_lid(B.points(cal, depth, 1), T, sc, found)["why"])


if __name__ == "__main__":
    main()
