"""Gravity feed-forward torque for the real robot: every action gets `arm_tau_ff`, the torque that holds the arms up
at the commanded pose.

Why (Aalto's PR #4 to aaltonomous-humanoid, "Action key arm_tau_ff", said merged by erkka Sun 15 Nov 04:18): on the
robot, G1_29_ArmController clips each target to ±0.12 rad of the measured angle at kp 80, so the PD holds at most
~9.6 Nm. An arm stretched ~0.5 m forward needs ~10 Nm at the shoulder and sinks 15-18 cm (shoulder pitch 0.28 rad
below its command). The teleop app that recorded Aalto's demos sends gravity compensation; with the new key a policy
can too. Our pre-submission sent none, and on Aalto's video every grasp landed beside its block.

What it does: `install()` wraps `aaltonomous.deploy.policy_server.handle`, which Aalto's `serve()` calls for every
message, so it covers every policy served that way (policy/server.py and Marcus's agent, via runtime.install()). For
each action it computes the gravity torque of the 14 arm joints at each row of `arm_q_target` (with the hand at
`hand_q_target`) on the URDF and joint order of Aalto's `ArmKinematics`: fixed base at the pelvis, legs and waist at 0.
`arm_tau_ff` gets exactly the shape of `arm_q_target` ((14,) or (k, 14)), as the runner requires.

Safety: the runner clamps `arm_tau_ff` to ±15 Nm (shoulder, elbow) / ±2.5 Nm (wrist) and the URDF effort, and sends 0
on safe stop, abort and episode end; we clamp to the same bounds first. The Isaac sim and the mock ignore the key, and
runners without PR #4 drop it (msgpack), so sim scores cannot change. If anything fails here the action goes out
without the key.

Env:
  GRAVITY_FF            on | off (default on)
  GRAVITY_FF_SCALE      factor on the torque (default 1.0)
  GRAVITY_FF_PITCH_DEG  gravity turned about the pelvis y axis, deg, for a robot pitched towards the table (default 0;
                        drop 3's depth suggests ~15°, untested)
"""
from __future__ import annotations

import logging
import os

import numpy as np

log = logging.getLogger("bot-icelli.gravity_ff")

N = 14
LIMIT_ARM, LIMIT_WRIST = 15.0, 2.5           # Nm, the runner's clamp (INTERFACE.md, PR #4)


class GravityFF:
    def __init__(self, scale=1.0, pitch_deg=0.0, urdf=None):
        import pinocchio as pin
        from aaltonomous.interface.safety import DEFAULT_URDF, JointSpec
        self.pin = pin
        spec = JointSpec()
        self.model = pin.buildModelFromUrdf(str(urdf or DEFAULT_URDF))
        self.data = self.model.createData()
        self.q0 = pin.neutral(self.model)
        ids = [self.model.getJointId(n) for n in spec.arm_names]
        self.arm_iq = np.array([self.model.joints[j].idx_q for j in ids])
        self.arm_iv = np.array([self.model.joints[j].idx_v for j in ids])
        self.hand_iq = np.array([self.model.joints[self.model.getJointId(n)].idx_q for n in spec.hand_names])
        self.names = list(spec.arm_names)
        lim = np.array([LIMIT_WRIST if "wrist" in n else LIMIT_ARM for n in self.names])
        effort = np.asarray(self.model.effortLimit, float)[self.arm_iv]
        self.limit = np.where(effort > 0, np.minimum(lim, effort), lim)
        self.scale = float(scale)
        a = np.radians(float(pitch_deg))
        self.model.gravity = pin.Motion(9.81 * np.array([np.sin(a), 0.0, -np.cos(a)]), np.zeros(3))

    def torque(self, arm_q, hand_q=None):
        """(14,) gravity torque (Nm) of the arm joints at arm_q, clamped to the runner's bounds."""
        q = self.q0.copy()
        q[self.arm_iq] = np.asarray(arm_q, float)
        if hand_q is not None:
            q[self.hand_iq] = np.asarray(hand_q, float)
        tau = self.pin.computeGeneralizedGravity(self.model, self.data, q)[self.arm_iv] * self.scale
        return np.clip(tau, -self.limit, self.limit)

    def for_action(self, action):
        """arm_tau_ff for an action dict: the shape of its arm_q_target."""
        arm = np.asarray(action["arm_q_target"], float)
        rows = arm.reshape(-1, N)
        hand = action.get("hand_q_target")
        hand = None if hand is None else np.asarray(hand, float).reshape(-1, N)
        out = np.vstack([self.torque(r, None if hand is None else hand[min(i, len(hand) - 1)])
                         for i, r in enumerate(rows)])
        return out.reshape(arm.shape)


def install():
    """Wrap Aalto's policy_server.handle so every action carries arm_tau_ff. No-op if off or already installed."""
    if os.environ.get("GRAVITY_FF", "on").strip().lower() == "off":
        log.info("gravity feed-forward off (GRAVITY_FF=off)")
        return None
    from aaltonomous.deploy import policy_server as ps
    if getattr(ps.handle, "_gravity_ff", None) is not None:
        return ps.handle._gravity_ff
    try:
        g = GravityFF(scale=float(os.environ.get("GRAVITY_FF_SCALE", "1.0") or 1.0),
                      pitch_deg=float(os.environ.get("GRAVITY_FF_PITCH_DEG", "0") or 0.0))
    except Exception as e:                   # no Pinocchio / URDF: serve without it
        log.warning("gravity feed-forward not installed: %r", e)
        return None
    orig = ps.handle
    state = {"logged": False, "failed": 0}

    def handle(policy, msg):
        out = orig(policy, msg)
        if isinstance(out, dict) and out.get("type") == "action" and isinstance(out.get("action"), dict):
            act = out["action"]
            try:
                if act.get("arm_q_target") is not None and act.get("arm_tau_ff") is None:
                    tau = g.for_action(act)
                    out = {**out, "action": {**act, "arm_tau_ff": tau}}
                    if not state["logged"]:
                        state["logged"] = True
                        t0 = tau.reshape(-1, N)[0]
                        log.info("gravity feed-forward: first action |tau| max %.1f Nm (%s), rows %d",
                                 float(np.abs(t0).max()), g.names[int(np.abs(t0).argmax())], tau.reshape(-1, N).shape[0])
            except Exception as e:           # never let it break an action
                state["failed"] += 1
                if state["failed"] <= 3:
                    log.warning("gravity feed-forward skipped for one action: %r", e)
        return out

    handle._gravity_ff = g
    ps.handle = handle
    log.info("gravity feed-forward on: arm_tau_ff on every action (scale %.2f, gravity pitched %.1f deg)",
             g.scale, float(os.environ.get("GRAVITY_FF_PITCH_DEG", "0") or 0.0))
    return g
