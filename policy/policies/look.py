"""look: a look-only policy for the first minutes on the real robot. It never moves: every answer holds the measured
pose. It runs v1.4's perception on the head camera every few seconds and logs what it finds, so a robot session can
start with zero risk and answer the questions that decide whether v1.4 suits that robot:

  - head-camera fit: how far the camera looks down compared with `calibration.yaml`, how far it moved, and whether
    v1.4 would use the fit;
  - objects found (colour, position, top height above the table) with the calibration camera and with the fitted
    one; real objects are 4.5 cm tall, so tops near 4.5 cm mean the geometry is right;
  - hand check (tilted camera or leaning robot?): the joint angles put the hands at known points (forward
    kinematics). With the right camera pose those points sit on the hands in the depth image. If the fitted camera
    matches the hands, the camera is tilted on its mount: what v1.4 assumes. If the calibration camera matches the
    hands while the fit still finds a tilt, the whole robot leans and v1.4 would put its hands several cm off.
    NOT YET VALIDATED in the sim (Sat 14 Nov ~20:00): it gives a verdict only when one pose lands within 4 cm;
    the phone-level measurement of the torso in docs/runbooks/real-robot.md is the primary answer;
  - depth quality (valid pixels) and the finger angles at rest.

It ends the episode after LOOK_SECONDS (default 30). Run it with POLICY=look (image tag `look`), read the policy's
log (`docker logs`). Everything is in lines starting with "[look".
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

from aaltonomous.deploy.policy_server import Policy

from headpose import CAM, fit_head_pose
from policies.classical_v14 import ClassicalV14, camera_move_ok

log = logging.getLogger("bot-icelli.look")

EVERY_S = 5.0                                   # one full look per this many seconds of episode time


def hand_check(depth, depth_scale, T, kin, arm_q, hand_q, K):
    """Project each hand's forward-kinematics points (palm, grasp point, finger links, fingertips) into the depth
    image with camera pose T (pelvis <- optical) and compare the depth measured there with the depth the joints
    predict. Right pose: the pixel lands on the hand (a few cm, the hand's thickness). A pose 10° off lands ~100 px
    away, on the table or a bin. Returns {side: (median |measured - predicted| in m or None, points in view)}."""
    h, w = depth.shape
    out = {}
    for side in ("left", "right"):
        hp = kin.hand_points(side, arm_q, hand_q)                  # (8, 3) pelvis frame
        cam = (hp - T[:3, 3]) @ T[:3, :3]                           # into the optical frame
        z = np.maximum(cam[:, 2], 1e-6)
        u = np.round(K[0, 0] * cam[:, 0] / z + K[0, 2]).astype(int)
        v = np.round(K[1, 1] * cam[:, 1] / z + K[1, 2]).astype(int)
        res = []
        for ui, vi, zi in zip(u, v, cam[:, 2]):
            if zi < 0.1 or not (2 <= ui < w - 2 and 2 <= vi < h - 2):
                continue
            win = depth[vi - 2:vi + 3, ui - 2:ui + 3].astype(float) * depth_scale
            win = win[win > 0.1]
            if len(win):
                res.append(abs(float(np.median(win)) - zi))
        out[side] = (float(np.median(res)) if res else None, len(res))
    return out


class LookPolicy(Policy):
    name = "bot-icelli-look"

    def __init__(self):
        self.v = ClassicalV14()                 # config, scene, calibration, perception, kinematics, guard
        self.pol = self.v.pol
        self.seconds = float(os.environ.get("LOOK_SECONDS", 30))
        self._job, self._last, self._n = None, -1e9, 0
        log.info("look: never moves; logs perception every %.0f s, ends after %.0f s", EVERY_S, self.seconds)

    def reset(self, instruction, task=None, seed=None):
        self.v.reset(instruction, task, seed)   # logs the colour -> bin mapping read from the instruction
        self._job, self._last, self._n = None, -1e9, 0

    def act(self, obs):
        t = float(obs.get("t", 0.0))
        idle = self._job is None or self._job["done"]
        if idle and t - self._last >= EVERY_S and t >= 0.5 and obs.get("head_depth") is not None:
            self._last, self._n = t, self._n + 1
            snap = {k: np.array(obs[k], copy=True) for k in ("head_rgb", "head_depth", "arm_q", "hand_q") if k in obs}
            snap["t"] = t
            self._job = {"done": False}
            threading.Thread(target=self._look, args=(snap, self._job, self._n), daemon=True).start()
        a = self.v._hold(obs)
        arm, hand = self.v.guard(a["arm_q_target"], a["hand_q_target"], obs)
        done = t >= self.seconds
        if done:
            arm, hand = arm[-1:], hand[-1:]
        return {"arm_q_target": arm.astype(np.float64), "hand_q_target": hand.astype(np.float64), "done": done}

    def _look(self, o, job, n):
        try:
            self._diagnose(o, n)
        except Exception as e:                  # never kill the control loop
            log.warning("[look #%d] failed: %r", n, e)
        finally:
            job["done"] = True

    def _diagnose(self, o, n):
        pol, say = self.pol, (lambda m: log.info("[look #%d t=%.1f] %s", n, o["t"], m))
        depth, rgb = np.asarray(o["head_depth"]), np.asarray(o["head_rgb"])
        arm_q, hand_q = np.asarray(o["arm_q"], float), np.asarray(o["hand_q"], float)
        cam = pol._cal0.cams[CAM]
        T0, K = pol._cal0._T(CAM).copy(), np.asarray(cam.K, float)

        valid = (depth > 150) & (depth < 2000)
        say(f"depth: {100 * valid.mean():.0f} % valid pixels, median {np.median(depth[valid]) / 1000:.2f} m"
            if valid.any() else "depth: NO valid pixels")

        fit = fit_head_pose(depth, pol._cal0, pol.scene)
        use = camera_move_ok(fit, T0)
        mv = np.asarray(fit.T, float)[:3, 3] - T0[:3, 3]
        say(f"camera fit: {fit.summary()}; camera moved ({', '.join(f'{100 * x:+.1f}' for x in mv)}) cm; "
            f"v1.4 {'USES it' if use else 'does NOT use it'}")

        zc = pol.scene.counter_z
        poses = [("calibration", T0)] + ([("fitted", np.asarray(fit.T, float))] if fit.ok else [])
        hands = {}
        for label, T in poses:
            pol.cal.cams[CAM].T_pelvis_optical = T                      # what the perception projects with
            dets = pol.perception.detect(rgb, depth)
            objs = "; ".join(f"{d.color} at ({100 * d.top[0]:.0f}, {100 * d.top[1]:+.0f}) cm, top "
                             f"{100 * (d.top[2] - zc):.1f} cm" for d in dets) or "none"
            say(f"objects with the {label} camera: {len(dets)}: {objs}")
            hands[label] = hand_check(depth, float(cam.depth_scale), T, pol.kin, arm_q, hand_q, K)
            hc = ", ".join(f"{s} hand " + ("not in view" if d is None else f"{100 * d:.1f} cm ({k}/8 points in view)")
                           for s, (d, k) in hands[label].items())
            say(f"hand check, {label} camera: depth measured where the joints put the hand, minus the depth they "
                f"predict (median): {hc}")
        pol.cal.cams[CAM].T_pelvis_optical = np.asarray(fit.T, float) if use else T0

        if len(hands) == 2:
            def score(h):
                ds = [d for d, k in h.values() if d is not None]
                return np.mean(ds) if ds else None
            c, f = score(hands["calibration"]), score(hands["fitted"])
            if c is None or f is None:
                say("verdict: hands not in view, the hand check can't decide (tilted camera or leaning robot)")
            elif min(c, f) > 0.04:
                say(f"verdict: inconclusive. Neither camera puts the joint-angle hands on the hands in the depth "
                    f"image ({100 * c:.1f} / {100 * f:.1f} cm): measure the torso angle with a phone level instead")
            elif fit.tilt_deg < 3:
                say(f"verdict: camera close to calibration.yaml (tilt {fit.tilt_deg:.1f} deg): nothing to decide")
            elif f + 0.02 < c:
                say(f"verdict: TILTED CAMERA. The fitted camera puts the hands where the joints say "
                    f"({100 * f:.1f} vs {100 * c:.1f} cm): v1.4's camera fit is right for this robot")
            elif c + 0.02 < f:
                say(f"verdict: LEANING ROBOT. The calibration camera matches the hands better ({100 * c:.1f} vs "
                    f"{100 * f:.1f} cm) although the table looks tilted by {fit.tilt_deg:.1f} deg: v1.4 would put "
                    f"its hands off. Tell Samer + Claude before running v1.4")
            else:
                say(f"verdict: unclear ({100 * c:.1f} vs {100 * f:.1f} cm); check the torso angle with a phone level")

        hq = ", ".join(f"{x:+.2f}" for x in hand_q)
        say(f"finger angles (left 0-6, right 7-13): {hq}")
