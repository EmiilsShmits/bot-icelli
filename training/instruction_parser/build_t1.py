"""T1 (in-distribution): Aalto's 8 templates x 6 bin permutations x 6 colour orders = 288 items."""
from __future__ import annotations

import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../third_party/aaltonomous-humanoid"))
sys.path.insert(0, HERE)

from spec import interpret  # noqa: E402

try:
    from aaltonomous.interface.tasks import TEMPLATES, COLORS, BINS
except Exception:  # numpy missing etc.: parse the file instead of importing it
    src = open(os.path.join(HERE, "../../third_party/aaltonomous-humanoid/aaltonomous/interface/tasks.py")).read()
    ns: dict = {}
    start = src.index("COLORS = ")
    exec(src[start: src.index("def bin_phrase")], ns)
    TEMPLATES, COLORS, BINS = ns["TEMPLATES"], ns["COLORS"], ns["BINS"]


def main(out=os.path.join(HERE, "data/t1.jsonl")):
    rows = []
    for ti, t in enumerate(TEMPLATES):
        for bins in itertools.permutations(BINS):
            for colors in itertools.permutations(COLORS):
                w = {f"c{i}": c for i, c in enumerate(colors)}
                w.update({f"C{i}": c.capitalize() for i, c in enumerate(colors)})
                w.update({f"b{i}": b for i, b in enumerate(bins)})
                spec = {"mapping": dict(zip(colors, bins))}
                rows.append({"id": f"t1-{len(rows) + 1:03d}", "text": t.format(**w), "category": f"template_{ti}",
                             "spec": spec, "label": interpret(spec)})
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} items to {out}")


if __name__ == "__main__":
    main()
