"""Record a video of every scored episode: head camera on top, left and right wrist cameras below.

Wraps the other entry points of this folder; everything after the module name is passed on unchanged:
    python -m decision_oracle.video upgrades --perception camera --labels fuse --task sort_language --trials 2 --seed 2000
    python -m decision_oracle.video run_eval --chooser aalto --task sort_language --trials 1 --seed 2005

Writes episode_NNN.mp4 (H.264, 30 fps, 640x720) next to each episode's .jsonl/.npz in the run folder, with the
episode time and the instruction written on it. Aalto's own --video (runner.Recorder) records the head camera only.
Sim-only exploration tool, like the rest of this folder.
"""
import importlib
import shutil
import subprocess
import sys

import numpy as np
from aaltonomous.deploy import runner as R

W, H = 640, 480                     # head camera tile; the wrist tiles are half size, side by side below it


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class TiledRecorder(R.Recorder):
    """Aalto's Recorder (npz + jsonl as before) plus a tiled three-camera video."""

    def __init__(self, path, images=False, video=False):
        super().__init__(path, images=images, video=False)
        self.raw, self.writer, self.n = path.with_suffix(".raw.mp4"), None, 0

    def add(self, row, obs):
        super().add(row, obs)
        import cv2
        f = self._frame(obs, cv2)
        if self.writer is None:
            self.writer = cv2.VideoWriter(str(self.raw), cv2.VideoWriter_fourcc(*"mp4v"), R.HZ, (f.shape[1], f.shape[0]))
        self.writer.write(f)
        self.n += 1

    def _frame(self, obs, cv2):
        def tile(key, w, h, label):
            im = obs.get(key)
            out = np.zeros((h, w, 3), np.uint8) if im is None else cv2.resize(
                np.ascontiguousarray(np.asarray(im)[..., :3][..., ::-1]), (w, h))
            cv2.putText(out, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            return out
        f = np.vstack([tile("head_rgb", W, H, "head"),
                       np.hstack([tile("left_wrist_rgb", W // 2, H // 2, "left wrist"),
                                  tile("right_wrist_rgb", W // 2, H // 2, "right wrist")])])
        ins = str(obs.get("instruction") or "")
        lines = [f"{self.path.name}  t={self.n / R.HZ:5.1f} s"] + [ins[k:k + 78] for k in range(0, min(len(ins), 156), 78)]
        for i, line in enumerate(lines):     # bottom of the head tile, one 18 px row per line
            y = H - 8 - 18 * (len(lines) - 1 - i)
            cv2.rectangle(f, (0, y - 14), (W, y + 5), (0, 0, 0), -1)
            cv2.putText(f, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        return f

    def save(self, events, summary):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            out, exe = self.path.with_suffix(".mp4"), _ffmpeg()
            ok = exe and subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(self.raw), "-c:v", "libx264",
                                         "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", str(out)]
                                        ).returncode == 0
            if ok:
                self.raw.unlink()
            else:                    # no H.264 encoder: keep the mp4v file under the final name
                self.raw.replace(out)
        super().save(events, summary)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        raise SystemExit("usage: python -m decision_oracle.video <upgrades|run_eval> [their arguments]")
    R.Recorder = TiledRecorder       # aaltonomous.sim.evaluate imports Recorder from runner at call time
    mod = importlib.import_module(f"decision_oracle.{argv[0]}")
    return mod.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
