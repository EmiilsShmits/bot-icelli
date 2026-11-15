"""How smooth are the arm commands in recorded episodes? (Aalto's evaluator writes episode_NNN.npz per trial: t,
arm_q, arm_q_cmd, ...). Large one-tick speed changes are what a real G1 feels as jolts.

    python motion_smoothness.py <run folder or glob> [...]     # e.g. ~/runs/eval/*v1.6*/

Per episode: max |speed| of the commands (rad/s), max and 99th-percentile |acceleration| (rad/s^2), 95th-percentile
|jerk| (rad/s^3), biggest one-tick speed change (rad/s), max tracking error (deg, actual vs commanded) and the sim
time of the episode.
"""
import glob
import os
import sys

import numpy as np


def episode_stats(f):
    z = np.load(f)
    if "arm_q_cmd" not in z.files or len(z["t"]) < 10:
        return None
    t, q = z["t"], z["arm_q_cmd"]
    dt = np.diff(t)
    dt[dt <= 0] = 1.0 / 30.0
    v = np.diff(q, axis=0) / dt[:, None]
    dv = np.abs(np.diff(v, axis=0))
    a = dv / dt[1:, None]
    j = np.abs(np.diff(a, axis=0)) / dt[2:, None]
    err = np.degrees(np.abs(z["arm_q"] - q).max(axis=1))
    return {"v_max": float(np.abs(v).max()), "a_max": float(a.max()), "a_p99": float(np.percentile(a.max(axis=1), 99)),
            "j_p95": float(np.percentile(j.max(axis=1), 95)), "dv_max": float(dv.max()), "track_deg": float(err.max()),
            "sim_s": float(t[-1] - t[0])}


def main(paths):
    print(f"{'run':58s} {'ep':>3s} {'v max':>6s} {'a max':>6s} {'a p99':>6s} {'j p95':>6s} {'dv max':>7s} {'track':>6s} {'sim s':>6s}")
    for pat in paths:
        for d in sorted(glob.glob(os.path.expanduser(pat))):
            for f in sorted(glob.glob(os.path.join(d, "episode_*.npz"))):
                s = episode_stats(f)
                if s:
                    print(f"{os.path.basename(os.path.normpath(d))[:58]:58s} {f[-7:-4]:>3s} {s['v_max']:6.2f} {s['a_max']:6.1f} "
                          f"{s['a_p99']:6.1f} {s['j_p95']:6.0f} {s['dv_max']:7.2f} {s['track_deg']:5.1f}d {s['sim_s']:6.1f}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["."])
