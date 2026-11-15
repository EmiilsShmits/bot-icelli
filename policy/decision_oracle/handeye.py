"""Head camera position and turn from the robot's own hands (hand-eye calibration from one depth frame).

The bin-wall fit in camera.py assumes the bins stand exactly where scene.yaml says. If they don't (the robot stands a
bit further from the table, a bin was placed 2 cm off), it moves the camera instead, and every object it sees is off
by the same amount: MuJoCo stress runs, sim/mujoco (bins shifted only: 33 % sorted vs 63 % nominal).

The arms are a reference that cannot move: the joint encoders give where the wrists and Dex3 hands are (forward
kinematics on the G1 URDF), and the head camera sees them in depth at the start of every episode. Matching the two
gives the camera's x, y and yaw relative to the arms, which is what a grasp needs. Tilt, roll and height still come
from the table plane (camera.fit_head_pose step 1); after this, the bins can be located instead of assumed.

    he = HandEye()                                            # loads hand_model.npz + the URDF (Pinocchio)
    res = he.fit(P_opt, T1, arm_q, hand_q, table_z)          # P_opt: optical-frame points (n, 3), T1: plane-fitted pose
    if res["ok"]: T = res["T"]

Only `obs` is used (head depth, arm_q, hand_q). The surface model (hand_model.npz, built from Unitree's STL meshes
with `python -m decision_oracle.handeye --build`) holds points + normals of the wrist, palm and finger links in their
link frames.
"""
from __future__ import annotations

import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL = HERE / "hand_model.npz"
LINK_KEYS = ("elbow", "wrist", "hand")       # links whose surfaces are used (both arms)


def _urdf_path():
    try:
        from aaltonomous.interface.safety import DEFAULT_URDF
        if Path(DEFAULT_URDF).exists():
            return str(DEFAULT_URDF)
    except Exception:
        pass
    for p in (HERE.parents[1] / "artifacts" / "urdf" / "g1_body29_hand14.urdf",):
        if p.exists():
            return str(p)
    raise FileNotFoundError("G1 URDF not found (bash policy/get_urdf.sh)")


def _joint_names():
    import yaml
    import aaltonomous.interface as I
    spec = yaml.safe_load(open(Path(I.__file__).parent / "joint_spec.yaml"))
    return [j["name"] for j in spec["arm"]] + [j["name"] for j in spec["hand"]]


def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# ------------------------------------------------------------------------------------------- model file
def _stl_triangles(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", 9), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)


def _sample_surface(tris, res, rng):
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    cr = np.cross(e1, e2)
    area = np.linalg.norm(cr, axis=1) / 2
    nrm = cr / np.maximum(2 * area[:, None], 1e-12)
    k = rng.poisson(area / (res * res) * 2)
    idx = np.repeat(np.arange(len(tris)), k)
    r1, r2 = rng.random(len(idx)), rng.random(len(idx))
    m = r1 + r2 > 1
    r1[m], r2[m] = 1 - r1[m], 1 - r2[m]
    p = tris[idx, 0] + r1[:, None] * e1[idx] + r2[:, None] * e2[idx]
    _, u = np.unique(np.round(p / res), axis=0, return_index=True)
    return p[u], nrm[idx][u]


def build_model(mesh_dir, out=MODEL, urdf=None, res=0.003):
    """Sample the visual meshes of the elbow, wrist and hand links (link frames, URDF visual origin applied)."""
    rng = np.random.default_rng(0)
    root = ET.parse(urdf or _urdf_path()).getroot()
    names, pts, nrms, link_of = [], [], [], []
    for L in root.findall("link"):
        nm = L.get("name")
        vis = L.find("visual")
        if vis is None or not any(k in nm for k in LINK_KEYS) or vis.find("geometry/mesh") is None:
            continue
        o = vis.find("origin")
        xyz = np.array([float(x) for x in (o.get("xyz", "0 0 0") if o is not None else "0 0 0").split()])
        rpy = np.array([float(x) for x in (o.get("rpy", "0 0 0") if o is not None else "0 0 0").split()])
        mesh = Path(mesh_dir) / vis.find("geometry/mesh").get("filename").split("/")[-1]
        p, n = _sample_surface(_stl_triangles(mesh), res, rng)
        R = _rpy(*rpy)
        names.append(nm)
        pts.append(p @ R.T + xyz)
        nrms.append(n @ R.T)
        link_of.append(np.full(len(p), len(names) - 1, np.int16))
    np.savez_compressed(out, names=np.array(names), pts=np.vstack(pts).astype(np.float32),
                        nrm=np.vstack(nrms).astype(np.float16), link=np.concatenate(link_of), res=res)
    return out


# ------------------------------------------------------------------------------------------- fit
class HandEye:
    def __init__(self, model=None, urdf=None):
        import pinocchio as pin
        z = np.load(model or os.environ.get("V16_HAND_MODEL", MODEL))
        self.names = [str(n) for n in z["names"]]
        self.pts, self.nrm, self.link = z["pts"].astype(float), z["nrm"].astype(float), z["link"]
        self.pin = pin
        self.model = pin.buildModelFromUrdf(urdf or _urdf_path())
        self.data = self.model.createData()
        self.fids = [self.model.getFrameId(n) for n in self.names]
        self.qidx = [self.model.joints[self.model.getJointId(n)].idx_q for n in _joint_names()]

    def cloud(self, arm_q, hand_q):
        """Surface points + normals of the arms in the pelvis frame for these joint angles."""
        pin = self.pin
        q = pin.neutral(self.model)
        q[self.qidx] = np.r_[np.asarray(arm_q, float), np.asarray(hand_q, float)]
        pin.forwardKinematics(self.model, self.data, q)
        pin.updateFramePlacements(self.model, self.data)
        P, N = np.empty_like(self.pts), np.empty_like(self.nrm)
        for i, f in enumerate(self.fids):
            M = self.data.oMf[f]
            m = self.link == i
            P[m] = self.pts[m] @ M.rotation.T + M.translation
            N[m] = self.nrm[m] @ M.rotation.T
        return P, N

    def fit(self, P_opt, T1, arm_q, hand_q, table_z, max_shift=0.06, max_yaw_deg=8.0):
        """Point-to-plane ICP of the depth points near the arms onto their surface model, over (yaw, dx, dy) of the
        camera about the pelvis z axis (tilt, roll, height stay from the table plane). -> dict (ok, T, why, ...)."""
        from scipy.spatial import cKDTree
        T1 = np.asarray(T1, float)
        M, N = self.cloud(arm_q, hand_q)
        vis = np.einsum("ij,ij->i", N, T1[:3, 3] - M) > 0          # faces turned to the camera
        M, N = M[vis], N[vis]
        res = {"ok": False, "T": T1, "n": 0, "rms_mm": None, "dxy": (0.0, 0.0), "dyaw_deg": 0.0, "dz_mm": None,
               "why": ""}
        if len(M) < 500:
            res["why"] = "arms not in view"
            return res
        tree = cKDTree(M)
        Q = np.asarray(P_opt, float) @ T1[:3, :3].T + T1[:3, 3]
        Q = Q[Q[:, 2] > table_z + 0.015]                            # off the table
        if len(Q) == 0:
            res["why"] = "no points above the table"
            return res
        d0, _ = tree.query(Q, distance_upper_bound=0.08)
        Q = Q[np.isfinite(d0)]
        if len(Q) < 400:
            res["why"] = f"too few points near the arms ({len(Q)})"
            return res
        R, t = np.eye(3), np.zeros(3)
        for th in (0.06, 0.04, 0.03, 0.02, 0.015, 0.012, 0.01, 0.008, 0.006, 0.006, 0.005, 0.005, 0.005, 0.005,
                   0.004, 0.004):
            X = Q @ R.T + t
            dd, ii = tree.query(X, distance_upper_bound=th)
            s = np.isfinite(dd)
            if s.sum() < 200:
                res["why"] = f"ICP lost the arms ({int(s.sum())} points)"
                return res
            x, m, n = X[s], M[ii[s]], N[ii[s]]
            J = np.c_[n[:, 0] * (-x[:, 1]) + n[:, 1] * x[:, 0], n[:, 0], n[:, 1]]
            r = np.einsum("ij,ij->i", n, m - x)
            sol = np.linalg.lstsq(J, r, rcond=None)[0]
            dR = _rz(sol[0])
            R, t = dR @ R, dR @ t + np.array([sol[1], sol[2], 0.0])
        X = Q @ R.T + t
        dd, ii = tree.query(X, distance_upper_bound=0.005)
        s = np.isfinite(dd)
        yaw = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
        res.update(n=int(s.sum()), frac=round(float(s.mean()), 3), rms_mm=round(float(np.sqrt(np.mean(dd[s] ** 2))) * 1000, 2),
                   dxy=(float(t[0]), float(t[1])), dyaw_deg=yaw,
                   dz_mm=round(float(np.median(M[ii[s], 2] - X[s, 2])) * 1000, 1))
        if res["n"] < 400 or res["frac"] < 0.3:
            res["why"] = f"weak arm fit ({res['n']} points, {res['frac']:.0%} within 5 mm)"
            return res
        if np.hypot(*t[:2]) > max_shift or abs(yaw) > max_yaw_deg:
            res["why"] = f"arm fit too far from the calibration ({np.hypot(*t[:2]) * 100:.1f} cm, {yaw:.1f} deg)"
            return res
        T = np.eye(4)
        T[:3, :3], T[:3, 3] = R @ T1[:3, :3], R @ T1[:3, 3] + t
        res.update(ok=True, T=T)
        return res

    def fit_pose(self, P_opt, T_init, arm_q, hand_q, off_table, max_rot_deg=20.0, max_shift=0.12):
        """The camera's full pose in the arm (pelvis) frame from the arms alone: 6-DOF point-to-plane ICP, no table.

        Where `fit` keeps the table-levelled tilt, this one answers "where is the camera relative to the arms",
        which is what IK needs when the torso leans (Aalto's real frames: the camera sits within ~2 deg of its
        calibration, the table looks 8-12 deg tilted). P_opt: optical-frame points; T_init: start pose (calibration);
        off_table: bool mask of P_opt points clear of the table (from the levelled fit). -> dict (ok, T, ...)."""
        from scipy.spatial import cKDTree
        T_init = np.asarray(T_init, float)
        M, N = self.cloud(arm_q, hand_q)
        vis = np.einsum("ij,ij->i", N, T_init[:3, 3] - M) > 0
        M, N = M[vis], N[vis]
        res = {"ok": False, "T": T_init, "n": 0, "rms_mm": None, "rot_deg": None, "shift_mm": None, "why": ""}
        if len(M) < 500:
            res["why"] = "arms not in view"
            return res
        tree = cKDTree(M)
        P = np.asarray(P_opt, float)[np.asarray(off_table, bool)]
        if len(P) < 400:
            res["why"] = f"too few points off the table ({len(P)})"
            return res
        def turned(pitch, yaw):             # about the camera: pitch about its own x axis, yaw about pelvis z
            T = T_init.copy()
            T[:3, :3] = _rz(np.radians(yaw)) @ T_init[:3, :3] @ _rx(np.radians(pitch))
            return T

        def icp(T, ths):
            c = T[:3, 3].copy()
            for th in ths:
                X = P @ T[:3, :3].T + T[:3, 3]
                dd, ii = tree.query(X, distance_upper_bound=th)
                s = np.isfinite(dd)
                if s.sum() < 200:
                    return None
                x, m, n = X[s], M[ii[s]], N[ii[s]]
                J = np.c_[np.cross(x - c, n), n]              # rotation about the camera keeps the steps small
                sol = np.linalg.lstsq(J, np.einsum("ij,ij->i", n, m - x), rcond=None)[0]
                dR = _rodrigues(sol[:3])
                T2 = np.eye(4)
                T2[:3, :3] = dR @ T[:3, :3]
                T2[:3, 3] = dR @ (T[:3, 3] - c) + c + sol[3:]
                T, c = T2, T2[:3, 3]
            return T

        def inliers(T):
            d, _ = tree.query(P @ T[:3, :3].T + T[:3, 3], distance_upper_bound=0.005)
            return int(np.isfinite(d).sum())
        # Multi-start: the venue look's camera is ~9 deg (and 3 cm) off the calibration, more than one ICP pulls in,
        # and from a wrong start it can settle on a pose that fits the hands almost as well. A short ICP from each
        # start, the one with the most points within 5 mm wins, then a long one.
        best = None
        for pitch in np.arange(-14.0, 14.1, 2.0):
            for yaw in (-4.0, 0.0, 4.0):
                T = icp(turned(pitch, yaw), (0.04, 0.02, 0.012, 0.008, 0.006))
                if T is not None:
                    k = inliers(T)
                    if best is None or k > best[0]:
                        best = (k, T)
        if best is None:
            res["why"] = "ICP lost the arms from every start"
            return res
        T = icp(best[1], (0.01, 0.008, 0.006, 0.005, 0.005, 0.004, 0.004, 0.004, 0.004, 0.004, 0.004, 0.003, 0.003,
                          0.003, 0.003, 0.003))
        if T is None:
            res["why"] = "ICP lost the arms"
            return res
        X = P @ T[:3, :3].T + T[:3, 3]
        dd, ii = tree.query(X, distance_upper_bound=0.005)
        s = np.isfinite(dd)
        dR = T[:3, :3] @ T_init[:3, :3].T
        rot = float(np.degrees(np.arccos(np.clip((np.trace(dR) - 1) / 2, -1, 1))))
        shift = float(np.linalg.norm(T[:3, 3] - T_init[:3, 3]))
        res.update(n=int(s.sum()), frac=round(float(s.mean()), 3),
                   rms_mm=round(float(np.sqrt(np.mean(dd[s] ** 2))) * 1000, 2) if s.any() else None,
                   rot_deg=round(rot, 2), shift_mm=round(shift * 1000, 1))
        if res["n"] < 400 or res["frac"] < 0.3:
            res["why"] = f"weak arm fit ({res['n']} points, {res['frac']:.0%} within 5 mm)"
            return res
        if rot > max_rot_deg or shift > max_shift:
            res["why"] = f"arm fit too far from the calibration ({rot:.1f} deg, {shift * 100:.1f} cm)"
            return res
        res.update(ok=True, T=T)
        return res

    def arm_shifts(self, P_opt, T, arm_q, hand_q, max_shift=0.04, min_pts=150, deadband=0.003,
                   sides=("left", "right")):
        """Each arm on its own after the joint fit: real hand minus model hand (m, arm frame), from the same frame.

        fit_pose gives one camera pose for both arms, and on Aalto's real frames (drop 3) the left arm decides it
        (more of it is in view): the left hand then sits 0.2 cm from its model, the right hand 1.3-1.8 cm (short, to
        the robot's right, low), different in every episode. The shift measured here at the start pose predicts the
        right hand's error when it reaches out to 0.5 cm (same episodes). Translation only, wrist and hand links,
        point-to-plane. P_opt: optical-frame points clear of the table; T: the believed camera pose (arm <- optical).
        -> {side: {"d": (3,) or None, "n": points, "why": ""}}; d is None when it cannot be trusted or is under
        `deadband` (a sim, where model and hand agree). max_shift over 4 cm also widens the search (hover_v16)."""
        from scipy.spatial import cKDTree
        T = np.asarray(T, float)
        M_all, N_all = self.cloud(arm_q, hand_q)
        X = np.asarray(P_opt, float) @ T[:3, :3].T + T[:3, 3]
        out = {}
        ths = ((0.07, 0.05) if max_shift > 0.04 else ()) + (0.04, 0.03, 0.02, 0.012, 0.008, 0.006, 0.005, 0.005, 0.004, 0.004)
        for side in sides:
            keep = [i for i, n in enumerate(self.names) if n.startswith(side) and ("hand" in n or "wrist" in n)]
            m = np.isin(self.link, keep)
            M, N = M_all[m], N_all[m]
            vis = np.einsum("ij,ij->i", N, T[:3, 3] - M) > 0
            M, N = M[vis], N[vis]
            res = out[side] = {"d": None, "n": 0, "why": ""}
            if len(M) < 200 or len(X) == 0:
                res["why"] = "hand not in view"
                continue
            tree, d, n = cKDTree(M), np.zeros(3), None
            for th in ths:
                dd, ii = tree.query(X + d, distance_upper_bound=th)
                s = np.isfinite(dd)
                if s.sum() < min_pts:
                    n = None
                    break
                n = N[ii[s]]
                d = d + np.linalg.lstsq(n, np.einsum("ij,ij->i", n, M[ii[s]] - (X[s] + d)), rcond=None)[0]
            res["n"] = int(s.sum())
            if n is None:
                res["why"] = f"too few points on the hand ({res['n']})"
                continue
            ev = np.linalg.eigvalsh(n.T @ n / len(n))
            if ev[0] < 0.03:                          # the surfaces seen all face one way: a slide along them is free
                res["why"] = f"hand seen from one side only ({ev[0]:.3f})"
                continue
            if np.linalg.norm(d) > max_shift:
                res["why"] = f"shift too large ({np.linalg.norm(d) * 100:.1f} cm)"
                continue
            if np.linalg.norm(d) < deadband:
                res["why"] = f"within {deadband * 1000:.0f} mm"
                continue
            res["d"] = -d                             # the points had to move by d to meet the model: real = model - d
        return out


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _rodrigues(w):
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def set_kin_base(kin, A):
    """Express an ArmKinematics (Aalto's IK/FK, Pinocchio) in another base frame: pelvis' = A @ pelvis.

    Every joint hanging off the root and every frame on the root is moved by A, so FK, Jacobians, IK targets and the
    top-down direction all live in the table-levelled frame the camera reports in. A = None or identity restores."""
    pin, m = kin.pin, kin.model
    if not hasattr(kin, "_base0"):
        kin._base0 = ([m.jointPlacements[j].copy() for j in range(m.njoints)],
                      [m.frames[i].placement.copy() for i in range(len(m.frames))])
    J0, F0 = kin._base0
    A = np.eye(4) if A is None else np.asarray(A, float)
    B = pin.SE3(A[:3, :3].copy(), A[:3, 3].copy())
    for j in range(1, m.njoints):
        m.jointPlacements[j] = B * J0[j] if m.parents[j] == 0 else J0[j]
    for i in range(len(m.frames)):
        f = m.frames[i]
        f.placement = B * F0[i] if f.parentJoint == 0 else F0[i]
        m.frames[i] = f
    kin.base = A


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--meshes", default=str(HERE.parents[1] / "artifacts" / "mujoco" / "g1" / "meshes"))
    a = ap.parse_args()
    if a.build:
        out = build_model(a.meshes)
        z = np.load(out)
        print(f"{out}: {len(z['pts'])} points, {len(z['names'])} links, {out.stat().st_size / 1e3:.0f} kB")
