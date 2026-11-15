"""v1.7: v1.6 (policies/oracle_v16.py) with fixes for what the real robot did on Sun 15 Nov (the wrist camera pushed
into the table). Everything else is v1.6: perception, Decision 1 labels and instruction, motions, task 3.

What changes from v1.6:
  * lean fallback (decision_oracle/camera.py, `CameraPerception.lean_fallback`): with V16_CALIB=lean the arm fit runs
    once per episode and lifts a grasp 4-9 cm on Aalto's real frames. When it fails or is past the limits
    (V16_LEAN_MAX_MOVE / V16_LEAN_MAX_DEG, 35 cm / 35 deg since 07f533c), v1.6 goes to lean.py's calibration-camera
    mapping (V16_LEAN_FALLBACK) or the uncorrected frame. v1.7 first reuses the camera's pose relative to the arms from
    the last believed arm fit of an earlier episode, with this episode's table fit, so the correction stays
    arm-based. First episode of a server process, nothing kept yet: as v1.6.
    Real frames: eval/analysis/real_depth/lean_fallback.py.

  * higher drop (V17_DROP=high, OFF by default: an experiment, not part of the model. Paired MuJoCo runs on Verda,
    e-091 / e-092: it sorts fewer objects than v1.6 because planning takes about twice as long; findings in
    decision_oracle/README.md Status): the block is released higher and further inside the box. v1.6 releases with the block's bottom ~3 cm above the real 7 cm rim, 5 cm inside the two
    nearest walls; the real hand has landed 3-9 cm low and 4-6 cm short. With "high":
      - pick, lift and the start of the carry are v1.6's (grasp.carry_height stays 0.16). Lifting to 22 cm at the
        pick took the block through the other hand, which waits in front of the chest (MuJoCo, seed 1001: cylinder
        stripped out of the grasp and off the table);
      - the carry ends V17_CARRY_H (0.22 m) above the table over the box instead of at carry height, so the arm
        climbs on the way to the box (`install_climb`);
      - release 6 cm higher (grasp.drop_above_rim 0.10: bottom ~9 cm above the real rim) and 8 cm inside the walls
        (grasp.drop_inset 0.08).
    Sorting tasks only: task 3 keeps v1.6's values and its own release (lowered to LID_GAP above the lid,
    decision_oracle/insert.py), so a block still goes into its hole from just above it. Put-downs on the table
    (relocation, relay) are v1.6's.

Env: as v1.6, plus V17_LEAN_KEEP (on | off, default on; off = v1.6's behaviour), V17_DROP (off | high, default off),
V17_CARRY_H / V17_DROP_ABOVE_RIM / V17_DROP_INSET (m; single values of "high"). With V17_DROP=high the last two win
over AALTO_CFG_OVERRIDES.
"""
from __future__ import annotations

import logging
import os

import numpy as np

from policies.oracle_v16 import OracleV16

log = logging.getLogger("bot-icelli.v1.7")


def _on(name, default="on"):
    return os.environ.get(name, default).lower() not in ("0", "off", "false", "no")


DROP_HIGH = {"drop_above_rim": 0.10, "drop_inset": 0.08}     # config.yaml grasp.* keys, m
DROP_ENV = {"drop_above_rim": "V17_DROP_ABOVE_RIM", "drop_inset": "V17_DROP_INSET"}
OVER_BIN_H = 0.22                # m above the table: where the carry ends over a box (V17_CARRY_H)
NO_DIP = 0.01                    # m: counted as "level" when the carry dips less than this below the lift height


def drop_settings():
    """grasp.* values of V17_DROP=high (single values from the environment), {} when it is off."""
    if not _on("V17_DROP", "off"):
        return {}
    return {k: float(os.environ[DROP_ENV[k]]) if os.environ.get(DROP_ENV[k]) else v for k, v in DROP_HIGH.items()}


def over_bin(pl, p):
    """Is pelvis-frame point p above the inside of one of the planner's bins (any height)?"""
    pm = np.asarray(pl.scene.pelvis_to_mat(np.asarray(p, float)), float)
    for name in pl.scene.bin_names:
        lo, hi = pl.scene.bin_inner_box(name)
        if np.all(pm[:2] >= lo[:2] - 1e-6) and np.all(pm[:2] <= hi[:2] + 1e-6):
            return True
    return False


def install_climb(pl, floor_above_rim, over_h=OVER_BIN_H):
    """Wrap pl._cartesian (Aalto's _OraclePlanner; this instance only) so that a carry to a box ends `over_h` above
    the table instead of at carry height: the lift at the pick stays as low as v1.6's and the arm climbs on the way.

    The planner builds lift -> carry -> lower from points at carry height (planner.py, _plan_side). Here:
      carry   to a point over a box: the end point is raised to max(over_h, release height + 2 cm). One IK and a
              direct joint-space move, as Aalto's oracle, accepted if it never dips below the floor v1.6 has
              (`floor_above_rim` = v1.6's grasp.drop_above_rim; with the raised value from the config the floor would
              be above the start). No such move: v1.6's carry to the unraised point. An (arm, point) whose raised
              IK failed is not tried again in the episode. Planning must stay as cheap as v1.6's: a first version
              with extra joint-space searches took 2.6x the planning time and sorted 56 % instead of 83 %
              (MuJoCo on Verda, v17-drop-a), with the same success per pick.
      lower   starts from the raised point when the carry was raised.
    Everything else passes through. Off until `pl._v17_climb["on"]` is set (per episode: sorting only)."""
    st = getattr(pl, "_v17_climb", None)
    if st is not None:
        st.update(floor=float(floor_above_rim), over=float(over_h))
        return st
    from aaltonomous.baselines.classical.planner import Planner
    st = pl._v17_climb = {"on": False, "floor": float(floor_above_rim), "over": float(over_h), "unreach": set(),
                          "level": 0, "raised": 0, "plain": 0}             # counts: which carry was planned
    inner = pl._cartesian

    def cartesian(side, p0, p1, q0, name, plan):
        if not st["on"]:
            return inner(side, p0, p1, q0, name, plan)
        if name == "carry":
            plan.__dict__.pop("_v17_over", None)
            sc, g = pl.scene, pl.cfg["grasp"]
            rim = sc.counter_z + float(sc.cfg["bins"]["wall_height"]) + pl.height / 2
            floor = rim + st["floor"]
            z = max(sc.counter_z + st["over"], rim + float(g["drop_above_rim"]) + 0.02)
            key = (side, round(float(p1[0]), 3), round(float(p1[1]), 3))
            if z > float(p1[2]) + 1e-6 and key not in st["unreach"] and over_bin(pl, p1):
                reason, ik, wp = plan.reason, dict(plan.ik), dict(plan.waypoints)
                q0a = np.asarray(q0, float)
                q_to, ok = pl._ik(side, np.r_[np.asarray(p1, float)[:2], z], q0a, "carry", plan)       # one IK, as v1.6's carry
                if ok:
                    low = min(pl.kin.grasp_pose(side, q0a + f * (q_to - q0a))[0][2] for f in np.linspace(0, 1, 15))
                    if low >= floor:
                        plan._v17_over = z
                        st["level" if low >= float(p0[2]) - NO_DIP else "raised"] += 1
                        return [q_to]
                else:
                    st["unreach"].add(key)             # this arm cannot hold the block that high there: not tried again
                plan.reason, plan.ik, plan.waypoints = reason, ik, wp
            st["plain"] += 1
            reason = plan.reason
            qs = pl._joint_carry(side, q0, p0, p1, floor, "carry", plan)                # v1.6's carry, v1.6's floor
            if qs is not None:
                return qs
            plan.reason = reason
            return Planner._cartesian(pl, side, p0, p1, q0, name, plan)                 # the stock straight-line carry
        if name == "lower" and getattr(plan, "_v17_over", None) is not None:
            p0 = np.r_[np.asarray(p0, float)[:2], plan._v17_over]
        return inner(side, p0, p1, q0, name, plan)

    pl._cartesian = cartesian
    return st


class OracleV17(OracleV16):
    name = "bot-icelli-v1.7"

    def __init__(self):
        super().__init__()
        cam = getattr(self.pol, "cam", None)
        self.lean_keep = bool(_on("V17_LEAN_KEEP") and cam is not None and getattr(cam, "lean", None) is not None)
        if self.lean_keep:
            cam.lean_fallback = True
        g = self.pol.cfg["grasp"]
        self._drop0 = {k: g.get(k) for k in DROP_HIGH}          # v1.6's values (task 3 keeps them)
        self._drop_high = drop_settings()
        self._sort_planner = self.pol.planner                   # task 3 swaps pol.planner for its own (insert.py)
        self._climb = None
        if self._drop_high:
            self._climb = install_climb(self._sort_planner, self._drop0["drop_above_rim"],
                                        float(os.environ.get("V17_CARRY_H") or OVER_BIN_H))
        log.info("v1.7 ready: lean fallback %s; drop %s",
                 "on" if self.lean_keep else "off (V17_LEAN_KEEP=off, or V16_CALIB is not lean)",
                 f"high {self._drop_high}, carry ends {self._climb['over']:.2f} m over the box" if self._drop_high
                 else "as v1.6")

    def _set_drop(self, high):
        """The planner reads grasp.* at plan time, so the values are switched per episode: high for sorting, v1.6's
        for task 3 (its planners copy the config when the first task-3 episode starts)."""
        g = self.pol.cfg["grasp"]
        want = {**self._drop0, **(self._drop_high if high else {})}
        if self._climb is not None:
            self._climb["on"] = bool(high)
            self._climb["unreach"].clear()                     # the lean correction moves the arm frame per episode
        if any(g.get(k) != v for k, v in want.items()):
            g.update(want)
            for pl in (self._sort_planner, self.pol.planner, getattr(self.pol, "relay", None)):
                if pl is not None:
                    pl.__dict__.pop("_reach", None)            # _OraclePlanner._reaches_bin is cached per bin
            log.info("drop settings: %s", {k: g[k] for k in want})

    def _apply_reset(self):
        if self._drop_high and self._pending_reset is not None:
            from decision_oracle import insert
            info, task, _ = self._pending_reset
            self._set_drop(not insert.is_insert(task, (info or {}).get("instruction")))
        super()._apply_reset()
