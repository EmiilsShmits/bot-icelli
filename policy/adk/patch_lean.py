"""Patch Marcus's agent (adk_agents/robot_sorter/robot.py) so its head-camera fit also sets bot-icelli's arm-frame
mapping (policy/lean.py): on the real robot, where the fit says the robot leans (>= 5 deg), IK targets are mapped from
the fitted table frame into the arm frame (docs/research/hand-offset-real-data.md). In Aalto's sims the fit tilts
~1-2 deg and nothing changes. runtime.install() (patch_smooth.py) installs the ArmKinematics patch itself.

    python patch_lean.py <path to adk_agents/robot_sorter>
"""
import sys
from pathlib import Path

f = Path(sys.argv[1]) / "robot.py"
t = f.read_text(encoding="utf-8")
OK = '            self.pose_fit = {"used": used, "summary": fit.summary()}\n'
BAD = '            self.pose_fit = {"used": False, "summary": f"fit failed: {e!r}"}\n'
ADD_OK = ("            try:  # bot-icelli: real robot (fit tilted >= 5 deg): aim the arms in the arm frame (lean.py)\n"
          "                import lean\n"
          "                lean.set_fit(self.head_T0, np.asarray(fit.T, float) if used else None, fit.tilt_deg, self.log)\n"
          "            except ImportError:\n"
          "                pass\n")
ADD_BAD = ("            try:  # bot-icelli: no fit, no mapping\n"
           "                import lean\n"
           "                lean.off()\n"
           "            except ImportError:\n"
           "                pass\n")
if "import lean" in t:
    print("lean mapping: already in robot.py")
elif t.count(OK) == 1 and t.count(BAD) == 1:
    f.write_text(t.replace(OK, OK + ADD_OK).replace(BAD, BAD + ADD_BAD), encoding="utf-8")
    print("patched: head-camera fit sets the arm-frame mapping (robot.fit_head_camera)")
else:
    print("NOT patched: robot.fit_head_camera changed; call lean.set_fit(T0, fit.T, fit.tilt_deg) there by hand")
