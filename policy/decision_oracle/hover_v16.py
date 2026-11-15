"""EXPERIMENTAL, OFF BY DEFAULT, DO NOT TURN ON: in Isaac this lowers the score (13/14 -> 9/14, Verda, 3 seeds): the
measurement reads 1-2 cm where the true error is 0 and corrected picks can take much longer. It only works in MuJoCo.
Findings: docs/research/hover-check-preliminary.md.

V16_HOVER: look at the hand over the block before it goes down, and move the rest of the pick by what is seen.

Why: on the real robot the hand has come down a few cm beside the block. The camera-to-arms fit runs once per episode
at the start pose (camera.py, V16_CALIB=lean); what it leaves is a per-arm error (the fit follows the left arm), its
own noise from one frame, and the arm hanging below its target. All three show when the hand is where it works.
The block and the hand are then seen by the same camera, so the camera-to-arms pose itself drops out.

How: every pick's path already stops over the block (the end of `to_pregrasp`, grasp point >= 13.5 cm above the
table). There the policy holds until the arm is still (V16_HOVER_WAIT s, at most 3x that), takes the head depth frame
and the measured joints, and in a thread
  1. measures real hand minus model hand at the MEASURED joints (handeye.arm_shifts, that arm only);
  2. adds how far the measured joints are from the commanded ones (the arm hanging off its target), and takes off
     what the planner already corrected (lean.ERR: ARM_ERR + V16_ARM_SHIFT). The result is `off`: where the real
     hand is minus where the plan believes it is (table frame);
  3. moves the grasp point of every remaining tick by -off with the palm's orientation kept (damped least squares
     on Aalto's kinematics, own model: the planners' is busy prefetching), through the release; over the retreat and
     the way home the shift fades out, so the path ends where the plan ended (the prefetched next plan stays valid);
  4. slows the moved path down wherever a joint would go faster than the planner's speed (the plan runs at the
     cap already, so any change tips it over), joins the hover pose to it with Aalto's go_to and runs Aalto's
     safety filter over the lot.
act() only holds meanwhile. Anything that fails (no depth, hand not found, shift over the limit, a clipped step,
thread late) continues the plan as it was. Sorting picks and relays only; task 3 keeps its own path.

Env: V16_HOVER off | log | on (default off; log = measure and write the log line, change nothing),
V16_HOVER_WAIT s (0.5), V16_HOVER_MAX m (0.06: larger = not believed), V16_HOVER_MAX_TURN deg (12: the most the palm may turn when a joint is on its limit),
V16_HOVER_HANG off | on (off: only what the camera sees counts; on adds measured-minus-commanded joints, which in
Isaac is a steady 2-3 cm sag that Aalto's grasp heights are tuned with: correcting it there empties the hand),
V16_HOVER_MAX_DOWN m (0.015: the most the
hand is sent below its plan), V16_HOVER_MIN m (0.004: smaller = left alone, a sim).
"""
from __future__ import annotations

import os
import threading
import time

import numpy as np

KEEP = ("descend", "close", "lift", "carry", "open")      # phases that get the full shift
JOB_TIMEOUT_S = 2.5                                         # wall seconds for the thread before the plan goes on as it was


def _f(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


def mode():
    m = os.environ.get("V16_HOVER", "off").strip().lower()
    return m if m in ("on", "log") else "off"


def _skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


class Hover:
    def __init__(self, pol, mode_="on"):
        from aaltonomous.baselines.classical.kinematics import ArmKinematics
        self.pol, self.mode = pol, mode_
        self.kin = ArmKinematics(pol.cfg)                   # own model: moved with the planners' (cam.kins)
        self.wait, self.max_shift = _f("V16_HOVER_WAIT", 0.5), _f("V16_HOVER_MAX", 0.06)
        self.max_down, self.min_shift = _f("V16_HOVER_MAX_DOWN", 0.015), _f("V16_HOVER_MIN", 0.004)
        self.max_turn, self.turn_deg = _f("V16_HOVER_MAX_TURN", 12.0), 0.0      # deg the palm may turn to reach
        self.use_hang = os.environ.get("V16_HOVER_HANG", "off").lower() in ("1", "on", "true", "yes")
        self.st, self.last = None, None

    def reset(self):
        self.st = None

    # ------------------------------------------------------------------ hooks (V16OraclePolicy._start / act)
    def arm(self, plan):
        """After the policy's _start: cut the queue at the end of `to_pregrasp`; the rest waits for the look."""
        pol, self.st = self.pol, None
        if plan is None or plan.arm is None or getattr(pol, "_insert", None) is not None:
            return
        ph = {n: (s, e) for n, s, e in plan.phases}
        if "to_pregrasp" not in ph or "descend" not in ph or pol.queue_a is None:
            return
        gc = pol._gc if getattr(pol, "_gc", None) is not None and pol._gc.get("plan") is plan else None
        end = len(plan.arm) - (len(gc["rest_a"]) if gc is not None else 0)      # where the queue ends in the plan
        done, cut = end - len(pol.queue_a), ph["to_pregrasp"][1]
        if not done < cut < end:
            return
        self.st = {"plan": plan, "side": plan.side, "cut": cut, "end": end, "stage": "move", "t0": None,
                   "prev": None, "job": None, "wall": None}
        pol.queue_a, pol.queue_h = plan.arm[done:cut], plan.hand[done:cut]

    def pending(self):
        pol = self.pol
        return self.st is not None and pol.state == "executing" and (pol.queue_a is None or not len(pol.queue_a))

    def step(self, obs):
        """The queue ended over the block: hold, look, then hand out the rest (moved or as planned)."""
        pol, st = self.pol, self.st
        t = float(obs.get("t", pol._t))
        q = np.asarray(obs["arm_q"], float)
        if st["stage"] == "move":
            st.update(stage="settle", t0=t, wall=time.monotonic())
        if st["stage"] == "settle":
            sl = self.kin.sl(st["side"])
            still = False
            if st["prev"] is not None and t > st["prev"][0]:
                still = float(np.abs(q[sl] - st["prev"][1][sl]).max()) / (t - st["prev"][0]) < 0.08     # rad/s
            st["prev"] = (t, q.copy())
            waited = t - st["t0"]
            if not ((waited >= self.wait and still) or waited >= 3 * self.wait
                    or time.monotonic() - st["wall"] > 8.0):
                return pol._hold()
            depth = obs.get("head_depth")
            if depth is None:
                return self._finish(None, "no head depth")
            job = {"result": None}
            args = (job, np.array(depth), q.copy(), np.asarray(obs["hand_q"], float).copy(), pol.arm_cmd.copy(),
                    pol.hand_cmd.copy(), st)
            threading.Thread(target=self._job, args=args, daemon=True).start()
            st.update(stage="busy", job=job, wall=time.monotonic(), waited=waited)
            return pol._hold()
        res = st["job"]["result"]
        if res is None:
            if time.monotonic() - st["wall"] < JOB_TIMEOUT_S:
                return pol._hold()
            return self._finish(None, "look took too long")
        return self._finish(res, res.get("why", ""))

    # ------------------------------------------------------------------ the look (thread)
    def _job(self, job, depth, arm_q, hand_q, arm_cmd, hand_cmd, st):
        try:
            dump = os.environ.get("V16_HOVER_DUMP")              # debugging: keep the frame the look used
            if dump:
                fr = self.frames()[0]
                os.makedirs(dump, exist_ok=True)
                np.savez_compressed(os.path.join(dump, "hover_%s_%.2f.npz" % (st["side"], self.pol._t)), depth=depth,
                                    arm_q=arm_q, hand_q=hand_q, arm_cmd=arm_cmd, side=st["side"],
                                    **({"A": fr[0], "T_arm": fr[1], "T_table": fr[2]} if fr else {}))
            res = self.measure_depth(depth, arm_q, hand_q, arm_cmd, st["side"])
            if res.get("off") is not None and self.mode == "on":
                res.update(self.correct(st["plan"], st["cut"], st["side"], res["off"], arm_cmd, hand_cmd))
        except Exception as e:                  # never lose the pick to the check
            res = {"off": None, "why": f"error {e!r}"}
        job["result"] = res

    def frames(self):
        """(A = table <- arm frame, T_arm = arm <- optical, T_table) of this episode's camera fit, or a reason."""
        cam = self.pol.cam
        fit = getattr(cam, "fit", None)
        if cam is None or getattr(cam, "lean", None) is None or fit is None or not fit.ok:
            return None, "no arm-based camera fit (V16_CALIB=lean)"
        try:
            import lean
            if lean.active():
                return None, "lean.py's mapping is on (no arm fit this episode)"
        except ImportError:
            pass
        base = (fit.arm_pose or {}).get("base", "")
        if fit.base is None and not base.startswith("same frame (within"):
            return None, f"no arm fit this episode ({base})"
        A = np.eye(4) if fit.base is None else np.asarray(fit.base, float)
        T = np.asarray(fit.T, float)
        return (A, np.linalg.inv(A) @ T, T), ""

    def measure_depth(self, depth, arm_q, hand_q, arm_cmd, side):
        from . import camera as C
        pol = self.pol
        fr, why = self.frames()
        if fr is None:
            return {"off": None, "why": why}
        P = C._points(pol.cam.cal0, depth, step=3).reshape(-1, 3)
        d = depth[::3, ::3].reshape(-1)
        P = P[(d > 150) & (d < 1300)]
        z = P @ fr[2][2, :3] + fr[2][2, 3]
        return self.measure(P[z > pol.scene.counter_z + 0.075], arm_q, hand_q, arm_cmd, side, fr)

    def measure(self, P_off, arm_q, hand_q, arm_cmd, side, fr=None):
        """off = where the real hand is minus where the plan believes it is (m, table frame), from optical-frame
        points clear of the table and the measured joints. -> dict (off or None, why, parts for the log)."""
        if fr is None:
            fr, why = self.frames()
            if fr is None:
                return {"off": None, "why": why}
        A, T_arm, _ = fr
        he = self.pol.cam.lean
        r = he.arm_shifts(P_off, T_arm, arm_q, hand_q, max_shift=self.max_shift, deadband=0.0, sides=(side,))[side]
        if r["d"] is None:
            return {"off": None, "why": f"hand not measured ({r['why']})", "n": r["n"]}
        seen = A[:3, :3] @ r["d"]                                   # real hand - model at the measured joints
        hang = self.grasp_point(side, arm_q) - self.grasp_point(side, arm_cmd)      # measured - commanded joints
        try:
            import lean
            known = np.asarray(lean.ERR[side], float)               # already corrected by the planner
        except ImportError:
            known = np.zeros(3)
        off = seen - known + (hang if self.use_hang else 0.0)      # the hanging arm: logged, added only on request
        return {"off": off, "why": "", "n": r["n"], "seen": seen, "hang": hang, "known": known}

    def grasp_point(self, side, arm_q):
        """The model's grasp point (table frame when the base is set), without lean.py's corrections."""
        k = self.kin
        k._fk(np.asarray(arm_q, float))
        M = k.data.oMf[k.palm[side]]
        return M.translation + M.rotation @ k.offset[side]

    # ------------------------------------------------------------------ the rest of the plan, moved
    def correct(self, plan, cut, side, off, arm_cmd, hand_cmd):
        n = float(np.linalg.norm(off))
        if n < self.min_shift:
            return {"why": f"within {self.min_shift * 1000:.0f} mm"}
        if n > self.max_shift:
            return {"why": f"{n * 100:.1f} cm is over the limit ({self.max_shift * 100:.0f} cm): not believed"}
        c = -np.asarray(off, float)
        note = ""
        if c[2] < -self.max_down:
            note = f"down move cut from {-c[2] * 100:.1f} to {self.max_down * 100:.1f} cm"
            c[2] = -self.max_down
        A0, H0 = plan.arm[cut:], plan.hand[cut:]
        W = self.weights(plan, cut)
        held = [e for name, s_, e in plan.phases if name in ("descend", "close", "lift")]
        A1, err = self.shift_path(side, A0, W, c, strict=(max(held) - cut) if held else None)
        if A1 is None:
            return {"why": f"moved path not reachable ({err})"}
        A1, H1, at = retime(A1, H0, 0.98 * float(self.pol.cfg["motion"]["arm_max_vel"]))
        ba, bh = self.pol.planner.go_to(arm_cmd, hand_cmd, A1[0], H1[0])
        if len(ba):
            arm, hand = np.vstack([ba, A1]), np.vstack([bh, H1])
        else:
            arm, hand = A1, H1
        clips = self.pol.planner.dry_run_safety(arm_cmd, hand_cmd, arm, hand)
        if clips:
            return {"why": f"moved path would be clipped ({clips} steps)"}
        return {"arm": arm, "hand": hand, "n_bridge": len(ba), "at": at, "shift": c, "note": note}

    def weights(self, plan, cut):
        """1 through the release, then a smooth fade to 0 at the plan's last tick (ticks cut..end)."""
        n = len(plan.arm) - cut
        last = max([e for name, s, e in plan.phases if name in KEEP] or [cut]) - cut
        last = int(np.clip(last, 0, n - 1))
        W = np.ones(n)
        m = n - last
        W[last:] = 0.5 * (1 + np.cos(np.pi * np.arange(m) / max(1, m - 1)))
        W[-1] = 0.0
        return W

    def shift_path(self, side, Q, W, c, tol=0.003, strict=None, loose=0.025):
        """Q (n, 14) arm targets -> the same with the grasp point of `side` moved by W[k] * c. The palm keeps its
        orientation where the joints allow it; with a joint on its limit (most plans have one) the palm may turn a
        little instead, up to `max_turn` degrees. The first `strict` ticks (down to the block and up again) must land
        within `tol`; the carry and the release after them within `loose`. Returns (Q', "") or (None, why)."""
        tols = np.full(len(Q), max(tol, 0.15 * float(np.linalg.norm(c))))      # 3 mm, or 15 % of a big move
        if strict is not None:
            tols[max(0, strict):] = loose
        why = ""
        for w_rot in (0.3, 0.04):                      # 1 rad of palm turn counts as 30 cm, then as 4 cm
            out, turn, why = self._shift_path(side, Q, W, c, tols, w_rot)
            if out is not None and turn <= self.max_turn:
                self.turn_deg = turn
                return out, ""
            if out is not None:
                why = f"palm would turn {turn:.0f} deg"
        return None, why

    def _shift_path(self, side, Q, W, c, tols, w_rot):
        k, pin = self.kin, self.kin.pin
        sl, fid = k.sl(side), k.palm[side]
        iv = k.arm_iv[sl]
        out, dq, turn = np.array(Q, float), np.zeros(7), 0.0
        for i in range(len(out)):
            if W[i] <= 0:
                dq = np.zeros(7)
                continue
            q0 = out[i].copy()
            lo, hi = np.minimum(k.lo[sl], q0[sl]), np.maximum(k.hi[sl], q0[sl])
            k._fk(q0)
            M0 = k.data.oMf[fid]
            R0 = M0.rotation.copy()
            target = M0.translation + R0 @ k.offset[side] + W[i] * c
            x, arm = np.clip(q0[sl] + dq, lo, hi), q0.copy()
            for it in range(9):
                arm[sl] = x
                qf = k._fk(arm)
                M = k.data.oMf[fid]
                R = M.rotation
                r = R @ k.offset[side]
                e_p = target - (M.translation + r)
                e_w = 0.5 * (np.cross(R[:, 0], R0[:, 0]) + np.cross(R[:, 1], R0[:, 1]) + np.cross(R[:, 2], R0[:, 2]))
                if it == 8 or (np.linalg.norm(e_p) < 2e-4 and np.linalg.norm(e_w) < 2e-3):
                    break
                J6 = pin.computeFrameJacobian(k.model, k.data, qf, fid, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)[:, iv]
                J = np.vstack([J6[:3] - _skew(r) @ J6[3:], w_rot * J6[3:]])
                x = _bounded_step(J, np.r_[e_p, w_rot * e_w], x, lo, hi)
            if np.linalg.norm(e_p) > tols[i]:
                return None, 0.0, f"tick {i}: {np.linalg.norm(e_p) * 1000:.1f} mm short"
            turn = max(turn, float(np.degrees(np.arcsin(min(1.0, np.linalg.norm(e_w))))))
            dq = x - q0[sl]
            out[i, sl] = x
        return out, turn, ""

    # ------------------------------------------------------------------ back to the queue
    def _finish(self, res, why=""):
        pol, st = self.pol, self.st
        self.st = None
        plan, cut, end = st["plan"], st["cut"], st["end"]
        a, h = plan.arm[cut:end], plan.hand[cut:end]
        gc = pol._gc if getattr(pol, "_gc", None) is not None and pol._gc.get("plan") is plan else None
        used = bool(res) and res.get("arm") is not None
        if used:
            # the same point of the pick in the moved, re-timed path (the whole of it when nothing waits after)
            k = res["n_bridge"] + res["at"](end - cut) if end < len(plan.arm) else len(res["arm"])
            a, h = res["arm"][:k], res["hand"][:k]
            if gc is not None:
                gc["rest_a"], gc["rest_h"] = res["arm"][k:], res["hand"][k:]
        cm = lambda v: None if v is None else [round(100 * float(x), 1) for x in v]
        rec = {"type": "hover", "t": round(pol._t, 2), "decision": getattr(plan, "decision_id", None),
               "arm": st["side"], "mode": self.mode, "corrected": used, "why": why or (res or {}).get("note", ""),
               "waited_s": round(st.get("waited") or 0.0, 2)}
        for key in ("off", "seen", "hang", "known", "shift"):
            rec[key + "_cm"] = cm((res or {}).get(key))
        self.last = rec
        try:
            pol._w(rec)
        except Exception:
            pass
        off = (res or {}).get("off")
        pol.log("[hover] %s hand: %s%s" % (
            st["side"],
            "not measured" if off is None else "off by (%+.1f, %+.1f, %+.1f) cm (seen %s, hanging %s%s, already corrected %s)" % (
                *(100 * off), rec["seen_cm"], rec["hang_cm"], "" if self.use_hang else " not counted", rec["known_cm"]),
            "; rest of the pick moved by %s cm%s" % (rec["shift_cm"], (", " + res["note"]) if res.get("note") else "")
            if used else "; pick goes on as planned" + (f" ({why})" if why else "")))
        pol._enqueue(a, h)
        return pol._pop() if len(a) else pol._hold()


def _bounded_step(J, e, x, lo, hi, lam=1e-5):
    """One damped least-squares step x -> x + dx with J dx = e, inside [lo, hi]: a joint that would leave its range
    stops on the limit and the others take over (up to three rounds)."""
    x, e, free = x.copy(), e.copy(), np.ones(len(x), bool)
    for _ in range(3):
        if not free.any():
            break
        Jf = J[:, free]
        d = np.linalg.solve(Jf.T @ Jf + lam * np.eye(Jf.shape[1]), Jf.T @ e)
        new = x[free] + d
        hit = (new < lo[free]) | (new > hi[free])
        if not hit.any():
            x[free] = new
            break
        idx = np.flatnonzero(free)[hit]
        bound = np.clip(new[hit], lo[idx], hi[idx])
        e = e - J[:, idx] @ (bound - x[idx])
        x[idx] = bound
        free[idx] = False
    return x


def retime(A, H, vmax, hz=30.0, win=9):
    """Stretch time wherever an arm joint moves faster than vmax (rad/s); the path itself is unchanged.
    A (n, 14) arm ticks, H (n, 14) hand ticks -> (A', H', at) with at(i) = the tick of A' where A[i] is reached."""
    A, H = np.asarray(A, float), np.asarray(H, float)
    n = len(A)
    if n < 2:
        return A, H, (lambda i: int(i))
    s = np.maximum(1.0, np.abs(np.diff(A, axis=0)).max(1) * hz / vmax)          # ticks each step needs
    if s.max() > 1.0:                           # widen and round off the slow stretches: no sudden speed change
        pad = np.pad(s, win // 2, mode="edge")
        s = np.array([pad[i:i + win].max() for i in range(len(s))])
        pad = np.pad(s, win // 2, mode="edge")
        s = np.array([pad[i:i + win].mean() for i in range(len(s))])
    cum = np.r_[0.0, np.cumsum(s)]
    m = int(np.ceil(cum[-1] - 1e-9)) + 1
    x = np.interp(np.minimum(np.arange(m), cum[-1]), cum, np.arange(n))         # original (fractional) tick
    i0 = np.minimum(np.floor(x).astype(int), n - 2)
    f = (x - i0)[:, None]
    return ((1 - f) * A[i0] + f * A[i0 + 1], (1 - f) * H[i0] + f * H[i0 + 1],
            lambda i: int(np.ceil(cum[int(np.clip(i, 0, n - 1))] - 1e-9)))


def make(pol):
    """The check for this policy, or None (off, or no arm-based calibration to measure against)."""
    m = mode()
    if m == "off" or getattr(pol, "cam", None) is None or getattr(pol.cam, "lean", None) is None:
        return None
    return Hover(pol, m)
