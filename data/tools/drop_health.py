"""Health report for an Aalto real-robot data drop (LeRobot v3.0): speed-cap violations, spikes, grip signal.

Why: Aalto's drops are raw. Before training on them, check whether their commanded actions would pass the safety
filter (1 rad/s arms, 3 rad/s hands, 0 clipped steps allowed at the sim gate) and how much they'd need slowing down.

Usage (from the repo root; needs numpy, pandas, pyarrow: `pip install -r data/requirements.txt`):
    python data/tools/drop_health.py zupermiez/g1_junction_drop_2          # downloads the joint data (~5 MB, no videos)
    python data/tools/drop_health.py artifacts/drops/g1_junction_drop_2    # or a local copy (same layout as on HF)
    python data/tools/drop_health.py zupermiez/g1_pick_cube --csv artifacts/drops/pick_cube_health.csv

Columns:
    arm_v / hand_v      max commanded speed (rad/s) of any arm / hand joint, after a 5-tick median filter
    arm_over / hand_over ticks whose command change exceeds the cap (raw data, what the filter would clip)
    spikes              ticks where an arm joint jumps > 5 rad/s (teleop glitches)
    stretch             uniform slow-down factor that brings every tick under 0.95 / 2.9 rad/s
    grip_gap            median of (|commanded| - |measured|) summed over the 6 finger joints of the busier hand,
                        over the most-closed 20 % of the episode. > 0 = the fingers are blocked (holding something)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

FPS = 30.0
ARM_CAP, HAND_CAP = 1.0, 3.0
REPO_ROOT = Path(__file__).resolve().parents[2]
# Finger joints without thumb_0, in observation.state order (14 arm values first, then left hand 7, right hand 7)
FINGERS = {"L": [15, 16, 17, 18, 19, 20], "R": [22, 23, 24, 25, 26, 27]}


def fetch(repo_id: str) -> Path:
    """Download meta/ and data/ parquet files of a public HF dataset (no videos) to artifacts/drops/<name>/."""
    out = REPO_ROOT / "artifacts" / "drops" / repo_id.split("/")[-1]
    with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{repo_id}") as r:
        files = [s["rfilename"] for s in json.load(r)["siblings"]]
    for f in files:
        if f.endswith(".parquet") or f.endswith(".json") or f == "README.md":
            dst = out / f
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(f"https://huggingface.co/datasets/{repo_id}/resolve/main/{f}", dst)
    return out


def medfilt(x: np.ndarray, k: int = 5) -> np.ndarray:
    p = k // 2
    xp = np.pad(x, ((p, p), (0, 0)), mode="edge")
    return np.stack([np.median(xp[i:i + k], axis=0) for i in range(len(x))])


def report(root: Path) -> pd.DataFrame:
    df = pd.concat([pd.read_parquet(p) for p in sorted((root / "data").rglob("*.parquet"))], ignore_index=True)
    tasks_df = pd.read_parquet(root / "meta" / "tasks.parquet")
    task_of = {int(row["task_index"]): str(txt) for txt, row in tasks_df.iterrows()} if "task_index" in tasks_df else {}
    st = np.stack(df["observation.state"].to_numpy()).astype(np.float64)
    ac = np.stack(df["action"].to_numpy()).astype(np.float64)
    ep = df["episode_index"].to_numpy()
    rows = []
    for e in np.unique(ep):
        m = ep == e
        a, s = ac[m], st[m]
        raw_v = np.abs(np.diff(a, axis=0)) * FPS
        filt_v = np.abs(np.diff(medfilt(a), axis=0)) * FPS
        arm_v, hand_v = filt_v[:, :14].max(), filt_v[:, 14:].max()
        hand = "L" if np.ptp(a[:, FINGERS["L"]], axis=0).sum() >= np.ptp(a[:, FINGERS["R"]], axis=0).sum() else "R"
        j = FINGERS[hand]
        closure = np.abs(a[:, j]).sum(1)
        gap = (np.abs(a[:, j]) - np.abs(s[:, j])).sum(1)
        closed = closure > np.percentile(closure, 80)
        rows.append(dict(
            ep=int(e), task=task_of.get(int(df["task_index"][m].iloc[0]), ""), sec=round(m.sum() / FPS, 1),
            arm_v=round(float(arm_v), 2), hand_v=round(float(hand_v), 2),
            arm_over=int((raw_v[:, :14] > ARM_CAP + 1e-6).any(1).sum()),
            hand_over=int((raw_v[:, 14:] > HAND_CAP + 1e-6).any(1).sum()),
            spikes=int((raw_v[:, :14] > 5.0).any(1).sum()),
            stretch=round(float(max(arm_v / 0.95, hand_v / 2.9, 1.0)), 1),
            stretch_arm_only=round(float(max(arm_v / 0.95, 1.0)), 1),
            grip_gap=round(float(np.median(gap[closed])), 2), hand=hand))
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="HF repo id (owner/name) or a local LeRobot v3.0 folder")
    ap.add_argument("--csv", help="also write the per-episode table here")
    args = ap.parse_args()
    root = Path(args.dataset)
    if not root.exists():
        root = fetch(args.dataset)
    r = report(root)
    pd.set_option("display.width", 220, "display.max_rows", 500, "display.max_colwidth", 55)
    print(r.to_string(index=False))
    n = len(r)
    print(f"\n{n} episodes, {r.sec.sum():.0f} s")
    print(f"episodes with arm commands over {ARM_CAP} rad/s: {(r.arm_over > 0).sum()}/{n}; "
          f"with spikes > 5 rad/s: {(r.spikes > 0).sum()}/{n}")
    print(f"median slow-down to pass the filter: x{r.stretch_arm_only.median():.1f} (arms only), "
          f"x{r.stretch.median():.1f} (arms + fingers); median episode {r.sec.median():.1f} s -> "
          f"{(r.sec * r.stretch_arm_only).median():.0f} s / {(r.sec * r.stretch).median():.0f} s")
    print(f"grip gap (closed phase), median: {r.grip_gap.median():.2f} rad")
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        r.to_csv(args.csv, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
