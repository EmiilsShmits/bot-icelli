"""Rule interpreter: structured spec -> 10-slot answer (EXPERIMENT.md, Phase 0 step 1).

Labels for every test set and every generated training example come from here, so they are
correct by construction (as long as the spec says what the sentence means).

Spec format (JSON):
  {"mapping": {"red": "left", "yellow": "center", "blue": "right"}}          # colour-only shorthand
  {"rules": [{"colors": ["red"], "shapes": null, "to": "left"}, ...],          # general form
   "other": "leave"}                                                            # optional, default "leave"
  {"invalid": true, "reason": "..."}                                            # instruction can't be followed

Rules are applied in order; a later rule overrides an earlier one for the slots it matches.
  colors / shapes: list of known colours / shapes, or null (= any known one).
  to: "left" | "center" | "right" | "leave".
"mapping" and "rules" may be combined (mapping is applied first).
Every one of the 9 known slots must end up defined, otherwise the spec is rejected.

Conventions (assumptions, recorded in RESULTS.md):
  - `other` = any object that is not one of the 9 known colour+shape types (a distractor). It is
    "leave" unless the instruction explicitly talks about unknown / other / extra objects.
    Words like "everything" / "all objects" refer to the known blocks only.
  - A known colour on an unknown shape (a red star) counts as `other`.
"""
from __future__ import annotations

import json
import sys

COLORS = ("red", "yellow", "blue")
SHAPES = ("cube", "cylinder", "triangle")
BINS = ("left", "center", "right")
VALUES = BINS + ("leave",)
SLOTS = tuple(f"{c} {s}" for c in COLORS for s in SHAPES) + ("other",)
INVALID = "invalid"


class SpecError(ValueError):
    pass


def interpret(spec: dict):
    """Returns a dict slot -> value for all 10 SLOTS, or the string "invalid"."""
    if spec.get("invalid"):
        return INVALID
    out = {}
    for color, dest in (spec.get("mapping") or {}).items():
        if color not in COLORS or dest not in VALUES:
            raise SpecError(f"bad mapping entry {color!r}: {dest!r}")
        for s in SHAPES:
            out[f"{color} {s}"] = dest
    for r in spec.get("rules") or []:
        extra = set(r) - {"colors", "shapes", "to"}
        if extra:
            raise SpecError(f"unknown rule keys {extra}")
        cols = r.get("colors") or COLORS
        shps = r.get("shapes") or SHAPES
        if r.get("to") not in VALUES:
            raise SpecError(f"bad destination {r.get('to')!r}")
        for c in cols:
            if c not in COLORS:
                raise SpecError(f"unknown colour {c!r}")
            for s in shps:
                if s not in SHAPES:
                    raise SpecError(f"unknown shape {s!r}")
                out[f"{c} {s}"] = r["to"]
    missing = [s for s in SLOTS[:-1] if s not in out]
    if missing:
        raise SpecError(f"undefined slots: {missing}")
    other = spec.get("other", "leave")
    if other not in VALUES:
        raise SpecError(f"bad other {other!r}")
    out["other"] = other
    return {s: out[s] for s in SLOTS}


def fixed_order(label) -> str:
    """Format B: the 10 values in SLOTS order, space separated (or 'invalid')."""
    if label == INVALID:
        return INVALID
    return " ".join(label[s] for s in SLOTS)


def from_fixed_order(text: str):
    """Inverse of fixed_order; returns None if the text isn't a valid answer."""
    toks = text.strip().lower().replace(",", " ").split()
    if toks[:1] == [INVALID]:
        return INVALID
    toks = ["center" if t in ("centre", "middle") else t for t in toks]
    if len(toks) < len(SLOTS) or any(t not in VALUES for t in toks[: len(SLOTS)]):
        return None
    return dict(zip(SLOTS, toks[: len(SLOTS)]))


def is_valid_label(label) -> bool:
    return label == INVALID or (isinstance(label, dict) and set(label) == set(SLOTS)
                                and all(v in VALUES for v in label.values()))


def check_file(path: str) -> int:
    """Validate a test-set JSONL: every line needs id, text, category, spec; fills in label."""
    n = bad = 0
    ids = set()
    rows = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            n += 1
            try:
                row = json.loads(line)
                for k in ("id", "text", "category", "spec"):
                    if k not in row:
                        raise SpecError(f"missing key {k}")
                if row["id"] in ids:
                    raise SpecError(f"duplicate id {row['id']}")
                ids.add(row["id"])
                row["label"] = interpret(row["spec"])
                rows.append(row)
            except (SpecError, json.JSONDecodeError) as e:
                bad += 1
                print(f"{path}:{i}: {e}")
    print(f"{path}: {n} items, {bad} bad")
    return bad


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(1 if sum(check_file(p) for p in sys.argv[2:]) else 0)
    print("usage: python3 spec.py check FILE.jsonl ...")
