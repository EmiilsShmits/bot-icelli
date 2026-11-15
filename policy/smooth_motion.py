"""Smooth, jerk-limited arm motions for the real robot.

Aalto's planner (`aaltonomous/baselines/classical/planner.py` `time_scale`, used by the classical baseline, the oracle,
v1.x, v1.5/v1.6 and Marcus's agent) times every arm move as a piecewise-LINEAR joint path through its IK waypoints with
a trapezoidal speed profile. At each waypoint the joint velocity changes direction instantly, and the trapezoid
switches acceleration on and off instantly. In our recorded sim episodes (Sat 14 Nov, every policy incl. Aalto's
baseline) that gives arm accelerations of 15 rad/s^2 at the 99th percentile and up to 54 rad/s^2, while the oracle asks
for 8 and the classical config for 1.5. On a real G1 those steps are jolts; the one team that tested on the real robot
had "huge jerks".

`smooth_time_scale` keeps the same contract (samples at dt, excluding Qs[0], ending exactly at Qs[-1], no joint faster
than vmax) but
  * follows a monotone cubic (PCHIP) through the same waypoints, so the velocity is continuous and the path stays
    within each pair of neighbouring waypoints joint by joint (no overshoot past the planner's checked path);
  * caps the acceleration at SMOOTH_ARM_ACC (default 6 rad/s^2, below the oracle's 8);
  * limits jerk by smoothing the speed profile over SMOOTH_JERK_S (default 0.06 s);
  * checks the result and stretches it in time if the curve's own acceleration still exceeds the cap.

    import smooth_motion; smooth_motion.install()   # before the planner users are imported
Env: SMOOTH_MOTION (1; 0 = Aalto's original), SMOOTH_ARM_ACC (6.0), SMOOTH_JERK_S (0.06).

Measured on the 210 arm moves the v1.5 planner makes for 6 random layouts (offline self-test, Sun 15 Nov):
  original: peak acceleration p95 23 / max 29 rad/s^2, biggest one-tick speed change 0.96 rad/s, 270 s of motion;
  default:  p95 7.4 / max 7.8 rad/s^2, biggest one-tick speed change 0.26 rad/s, 338 s (x1.25);
  cap 4:    max 5.2 rad/s^2, 0.17 rad/s, x1.37;  cap 8: max 10.3 rad/s^2, 0.34 rad/s, x1.21.
"""
from __future__ import annotations

import logging
import os
import sys

import numpy as np

log = logging.getLogger("bot-icelli.smooth")
_ORIGINAL = None
_FINE = 8            # sub-steps per control tick for the speed profile


def _cfg():
    return (os.environ.get("SMOOTH_MOTION", "1") != "0",
            float(os.environ.get("SMOOTH_ARM_ACC", 6.0)),
            float(os.environ.get("SMOOTH_JERK_S", 0.06)))


def _speed_profile(S, vmax, amax, tj, h):
    """Distance s(t) from 0 to S on a fine grid of step h: trapezoid (vmax, amax), its speed then averaged over a
    window of tj (jerk <= amax / tj). Returns s at t = 0, h, 2h, ... (last value == S)."""
    ta = vmax / amax
    if amax * ta * ta > S:                                   # triangle: never reaches vmax
        ta = np.sqrt(S / amax)
        T, vpk = 2 * ta, amax * ta
    else:
        T, vpk = 2 * ta + (S - amax * ta * ta) / vmax, vmax
    n = max(2, int(np.ceil(T / h)))
    t = (np.arange(n) + 0.5) * (T / n)
    v = np.minimum.reduce([amax * t, np.full(n, vpk), amax * (T - t)])
    v = np.clip(v, 0.0, None)
    k = max(1, int(round(tj / (T / n))))
    if k > 1:
        v = np.convolve(v, np.ones(k) / k)                   # same area (distance), smooth corners
    s = np.r_[0.0, np.cumsum(v) * (T / n)]
    return s * (S / s[-1]), T / n


def smooth_time_scale(Qs, vmax, amax, dt):
    """Drop-in for planner.time_scale (same arguments and result shape), smooth and jerk-limited."""
    on, a_cap, tj = _cfg()
    if not on and _ORIGINAL is not None:
        return _ORIGINAL(Qs, vmax, amax, dt)
    Qs = np.asarray(Qs, float)
    seg = np.abs(np.diff(Qs, axis=0)).max(axis=1)
    if float(seg.sum()) < 1e-9:
        return np.empty((0, Qs.shape[1]))
    P = Qs[np.r_[True, seg > 1e-9]]                          # drop repeated waypoints
    seg = np.abs(np.diff(P, axis=0)).max(axis=1)
    u = np.r_[0.0, np.cumsum(seg)]                           # inf-norm arc length, as in the original
    S = float(u[-1])
    if len(P) == 2:
        def path(s):
            return P[0] + np.outer(s / S, P[1] - P[0])

        def dpath(s):
            return np.tile((P[1] - P[0]) / S, (len(s), 1))
    else:
        from scipy.interpolate import PchipInterpolator
        f = PchipInterpolator(u, P, axis=0)
        df = f.derivative()

        def path(s):
            return f(s)

        def dpath(s):
            return df(s)
    grid = np.linspace(0.0, S, max(200, 50 * len(P)))
    kmax = 1.01 * max(1.0, float(np.abs(dpath(grid)).max()))   # joint speed per unit arc length (+1 % margin)
    a = min(float(amax), a_cap)
    stretch, v_ok = 1.0, False
    for _ in range(8):
        # slowing a move down by `stretch` divides speeds by stretch and accelerations by stretch^2
        s_fine, h = _speed_profile(S, vmax / (kmax * stretch), a / (kmax * stretch ** 2), tj, dt / _FINE)
        T = h * (len(s_fine) - 1)
        n = max(1, int(np.ceil(T / dt)))
        tk = np.arange(1, n + 1) * dt
        sk = np.interp(np.minimum(tk, T), np.arange(len(s_fine)) * h, s_fine)
        out = path(sk)
        out[-1] = P[-1]
        vel = np.diff(np.vstack([P[:1], out]), axis=0) / dt
        acc = np.diff(np.vstack([np.zeros((1, P.shape[1])), vel, np.zeros((1, P.shape[1]))]), axis=0) / dt
        v_seen, a_seen = float(np.abs(vel).max()), float(np.abs(acc).max())
        v_ok, a_ok = v_seen <= vmax * 0.999, a_seen <= 1.3 * a_cap or n < 3
        if v_ok and a_ok:
            break
        # the curve's own bends (or tick rounding) went over a cap: slow the whole move down and retry
        stretch *= max(1.0 if v_ok else v_seen / (0.995 * vmax), 1.0 if a_ok else float(np.sqrt(a_seen / (1.3 * a_cap))))
    if not v_ok and _ORIGINAL is not None:                   # never above the caller's speed cap
        return _ORIGINAL(Qs, vmax, amax, dt)
    return out


def install():
    """Replace planner.time_scale with smooth_time_scale, also in modules that imported it by name already."""
    global _ORIGINAL
    from aaltonomous.baselines.classical import planner
    if planner.time_scale is smooth_time_scale:
        return
    _ORIGINAL = planner.time_scale
    planner.time_scale = smooth_time_scale
    for m in list(sys.modules.values()):
        if getattr(m, "time_scale", None) is _ORIGINAL:
            m.time_scale = smooth_time_scale
    on, a_cap, tj = _cfg()
    log.info("smooth arm motions %s: acceleration <= %.1f rad/s^2, jerk window %.2f s", "on" if on else "OFF", a_cap, tj)
