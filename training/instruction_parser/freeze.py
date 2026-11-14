"""Freeze the hand-written test sets: data/<name>.src.jsonl -> data/<name>.jsonl (with labels), print SHA-256."""
from __future__ import annotations

import hashlib
import json
import os
import sys

from spec import interpret

HERE = os.path.dirname(os.path.abspath(__file__))


def main(names):
    for n in names:
        src = os.path.join(HERE, "data", f"{n}.src.jsonl")
        dst = os.path.join(HERE, "data", f"{n}.jsonl")
        if os.path.exists(src):
            rows = [json.loads(l) for l in open(src) if l.strip()]
            with open(dst, "w") as f:
                for r in rows:
                    r["label"] = interpret(r["spec"])
                    f.write(json.dumps({k: r[k] for k in ("id", "text", "category", "spec", "label")}) + "\n")
        h = hashlib.sha256(open(dst, "rb").read()).hexdigest()
        print(f"{n}.jsonl  {sum(1 for _ in open(dst))} items  sha256 {h}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["t1", "t2a", "t2b", "t3"])
