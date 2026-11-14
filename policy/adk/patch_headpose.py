"""Patch Marcus's agent (adk_agents/robot_sorter) so its head-camera fit is judged by how far the camera itself moved.

His headpose.plausible() is a copy of our old v1.2 check: it rejects a fit whose bin-fit shift (dxy) exceeds 6 cm.
In the venue look (camera ~10 deg lower than calibration.yaml, as in Aalto's real footage) the fit is right but
reports a shift of about -8 cm, because the plane fit tilts the pose about the pelvis origin and the bin fit moves it
back: the camera itself moved only ~2 cm (bot-icelli eval/RESULTS.md e-034). The agent then keeps the calibration
pose and places every object ~20 cm too far. Same fix as camera_move_ok in policy/policies/classical_v14.py.

    python patch_headpose.py <path to adk_agents/robot_sorter>

Prints what it did; leaves the files alone (and says so) if Marcus's code has already changed there.
"""
import sys
from pathlib import Path

d = Path(sys.argv[1])
hp, rb = d / "headpose.py", d / "robot.py"
h, r = hp.read_text(encoding="utf-8"), rb.read_text(encoding="utf-8")

OLD_DEF = '''def plausible(fit, max_tilt_deg=15.0, max_shift_m=0.06, max_yaw_deg=6.0):
    """Accept only corrections a mis-mounted / mis-calibrated head camera can need (real one: ~10° tilt)."""
    return (fit.ok and fit.tilt_deg <= max_tilt_deg and max(abs(fit.dxy[0]), abs(fit.dxy[1])) <= max_shift_m
            and abs(fit.dyaw_deg) <= max_yaw_deg)'''
NEW_DEF = '''def plausible(fit, T0=None, max_tilt_deg=15.0, max_shift_m=0.06, max_yaw_deg=6.0):
    """Accept only corrections a mis-mounted / mis-calibrated head camera can need (real one: ~10° tilt).
    bot-icelli patch: with T0 (the calibration pose) the limit applies to how far the camera itself moved. The bin
    fit's shift (dxy) reads ~8 cm in the venue look while the camera moved ~2 cm (bot-icelli e-034)."""
    if not (fit.ok and fit.tilt_deg <= max_tilt_deg and abs(fit.dyaw_deg) <= max_yaw_deg):
        return False
    if T0 is not None:
        import numpy as _np
        move = _np.asarray(fit.T, float)[:3, 3] - _np.asarray(T0, float)[:3, 3]
        return float(_np.linalg.norm(move)) <= max_shift_m
    return max(abs(fit.dxy[0]), abs(fit.dxy[1])) <= max_shift_m'''
OLD_CALL = "used = bool(plausible(fit))"
NEW_CALL = "used = bool(plausible(fit, self.head_T0))"

if OLD_DEF in h and r.count(OLD_CALL) == 1:
    hp.write_text(h.replace(OLD_DEF, NEW_DEF), encoding="utf-8")
    rb.write_text(r.replace(OLD_CALL, NEW_CALL), encoding="utf-8")
    print("patched: head-camera fit judged by the camera's own move (headpose.plausible + robot.fit_head_camera)")
else:
    print("NOT patched: Marcus's headpose.py / robot.py differ from 1a51d7b here; check his fit check by hand")
