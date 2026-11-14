"""Rule-based baseline parser (EXPERIMENT.md Phase 0 step 3).

Keyword proximity per clause, with basic shape, "except", "leave", "the rest" and distractor handling.
Tuned only on T1 and the scratch examples at the bottom of this file, never on T2a / T2b / T3.

parse(text) -> 10-slot dict (spec.SLOTS) or "invalid".
"""
from __future__ import annotations

import difflib
import re

from spec import BINS, COLORS, INVALID, SHAPES, SLOTS

COLOR_WORDS = {
    "red": "red", "reds": "red", "reddish": "red", "crimson": "red", "scarlet": "red", "orange": "red",
    "yellow": "yellow", "yellows": "yellow", "yellowish": "yellow", "golden": "yellow", "gold": "yellow",
    "blue": "blue", "blues": "blue", "bluish": "blue", "blueish": "blue", "navy": "blue", "purple": "blue",
}
SHAPE_WORDS = {
    "cube": "cube", "cubes": "cube", "square": "cube", "squares": "cube", "cubic": "cube", "boxy": "cube",
    "cylinder": "cylinder", "cylinders": "cylinder", "cylindrical": "cylinder", "round": "cylinder",
    "circle": "cylinder", "circles": "cylinder", "circular": "cylinder", "disc": "cylinder", "discs": "cylinder",
    "triangle": "triangle", "triangles": "triangle", "triangular": "triangle", "prism": "triangle",
    "prisms": "triangle", "pyramid": "triangle", "pyramids": "triangle",
}
BIN_WORDS = {
    "left": "left", "leftmost": "left", "lefthand": "left",
    "right": "right", "rightmost": "right", "righthand": "right",
    "center": "center", "centre": "center", "middle": "center", "central": "center", "mid": "center",
    "centered": "center", "centred": "center",
}
NEG = {"not", "dont", "don't", "never", "no", "nothing", "shouldn't", "shouldnt", "mustn't", "avoid", "neither", "nor"}
EXCEPT = {"except", "excluding", "besides", "but"}
LEAVE = {"leave", "ignore", "skip", "untouched", "alone", "touch", "stay", "remain", "ignored", "skipped"}
REST = {"rest", "remaining", "else", "others", "leftover", "leftovers", "last", "third"}
ALL = {"everything", "all", "every", "each", "anything", "any"}
DISTRACTOR = {"unknown", "unfamiliar", "foreign", "extra", "distractor", "distractors", "unrecognised",
              "unrecognized", "random", "strange", "weird", "odd", "unexpected", "non-block", "anything"}
BAD_BIN = {"top", "bottom", "upper", "lower", "fourth", "back", "front", "green", "black", "white",
           "behind", "above", "below", "second", "first", "pink"}
VOCAB = sorted(set(COLOR_WORDS) | set(SHAPE_WORDS) | set(BIN_WORDS) | {"except", "remaining", "leave"})


def _norm_token(t: str) -> str:
    if t in COLOR_WORDS or t in SHAPE_WORDS or t in BIN_WORDS or len(t) < 4:
        return t
    m = difflib.get_close_matches(t, VOCAB, n=1, cutoff=0.8)
    return m[0] if m else t


def _tokens(clause: str):
    clause = clause.replace("left-hand", "lefthand").replace("right-hand", "righthand")
    clause = re.sub(r"\b(l)\s*[:=]", " left ", clause)
    clause = re.sub(r"\b(c|m)\s*[:=]", " center ", clause)
    clause = re.sub(r"\b(r)\s*[:=]", " right ", clause)
    return [_norm_token(t) for t in re.findall(r"[a-z']+", clause)]


def _split(text: str):
    t = text.lower().replace("→", " to ").replace("->", " to ").replace("=>", " to ")
    parts = re.split(r"[.;!?\n/|]+|,|\band then\b|\bthen\b|\bwhile\b|\bwhereas\b|\band\b(?=\s+(?:the\s+)?(?:%s)\b)"
                     % "|".join(list(COLOR_WORDS) + list(SHAPE_WORDS) + ["leave", "ignore", "don't", "do not", "put", "place", "move"]), t)
    return [p.strip() for p in parts if p and p.strip()]


def _slots(colors=None, shapes=None):
    return {f"{c} {s}" for c in (colors or COLORS) for s in (shapes or SHAPES)}


def _entities(toks):
    """Sequence of (pos, kind, value): kind in sel, bin. A selector is (colors|None, shapes|None)."""
    ents = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in COLOR_WORDS:
            cols = [COLOR_WORDS[t]]
            shp = None
            j = i + 1
            while j < len(toks) and toks[j] in ("and", "or", "coloured", "colored", "-") and j + 1 < len(toks) \
                    and toks[j + 1] in COLOR_WORDS and False:
                j += 2
            # attach a shape that directly follows ("red cubes", "red-coloured cylinders")
            k = i + 1
            while k < len(toks) and toks[k] in ("coloured", "colored", "ish"):
                k += 1
            if k < len(toks) and toks[k] in SHAPE_WORDS:
                shp = [SHAPE_WORDS[toks[k]]]
                i = k
            ents.append((i, "sel", (cols, shp)))
        elif t in SHAPE_WORDS:
            ents.append((i, "sel", (None, [SHAPE_WORDS[t]])))
        elif t in BIN_WORDS:
            ents.append((i, "bin", BIN_WORDS[t]))
        i += 1
    return ents


def parse(text: str):
    if not text or not text.strip():
        return INVALID
    assigned = {}  # slot -> (priority, value)
    conflict = False
    other = "leave"
    rest_bin = None          # "the rest go to X"
    remaining_sels = []      # selectors sent to "the remaining bin"
    pending = []             # selectors waiting for a bin from the next clause
    bad = False
    neg_pairs = set()

    def put(slots, value, prio):
        nonlocal conflict
        for s in slots:
            if s in assigned:
                p, v = assigned[s]
                if prio < p:
                    continue
                if prio == p and v != value:
                    conflict = True
            assigned[s] = (prio, value)

    for clause in _split(text):
        toks = _tokens(clause)
        tset = set(toks)
        ents = _entities(toks)
        sels = [e for e in ents if e[1] == "sel"]
        bins = [e for e in ents if e[1] == "bin"]
        is_leave = bool(tset & LEAVE) or "where they are" in clause or "on the table" in clause \
            or "don't move" in clause or "do not move" in clause
        is_neg = bool(tset & NEG) or "do not" in clause
        is_rest = bool(tset & REST) or "everything else" in clause or "all other" in clause \
            or "the other" in clause
        is_distr = ("isn't" in clause or "is not" in clause or "aren't" in clause or "are not" in clause
                    or "not one of" in clause or "anything other" in clause or "any other object" in clause
                    or bool(tset & (DISTRACTOR - {"anything"})))
        exc_idx = next((i for i, t in enumerate(toks) if t in EXCEPT or (t == "other" and i + 1 < len(toks)
                        and toks[i + 1] == "than")), None)
        mentions_bin_noun = bool(tset & {"bin", "bins", "box", "boxes", "basket", "container"})

        if is_distr and not sels or (is_distr and ("isn't" in clause or "not one of" in clause or "unknown" in tset)):
            # sentence about distractors
            if bins and not is_neg:
                other = bins[0][2]
            else:
                other = "leave"
            continue

        if is_leave and not bins:
            targets = sels or pending
            for _, _, (c, s) in targets:
                put(_slots(c, s), "leave", 2 if (c and s) else 1)
            if not targets and is_rest:
                rest_bin = "leave"
            pending = []
            continue

        if is_neg and bins and not is_leave and exc_idx is None:
            for _, _, (c, s) in sels:
                for b in bins:
                    neg_pairs.add((tuple(c or ()), tuple(s or ()), b[2]))
            continue

        if mentions_bin_noun and not bins and not is_rest and (tset & BAD_BIN):
            bad = True
            continue

        if exc_idx is not None and bins:
            before = [e for e in sels if e[0] < exc_idx]
            after = [e for e in sels if e[0] > exc_idx]
            base = set()
            if before:
                for _, _, (c, s) in before:
                    base |= _slots(c, s)
            else:
                base = _slots()
            excl = set()
            for _, _, (c, s) in after:
                excl |= _slots(c, s)
            dest = "leave" if is_leave else bins[0][2]
            put(base - excl, dest, 0.5)
            pending = []
            continue

        if not sels and bins and is_rest:
            rest_bin = bins[0][2]
            continue
        if not sels and is_rest and is_leave:
            rest_bin = "leave"
            continue
        if not sels and bins and (tset & ALL) and not pending:
            put(_slots(), bins[0][2], 0)
            continue
        if sels and not bins and is_rest and ("bin" in tset or "one" in tset or "spot" in tset):
            remaining_sels.extend(sels)
            continue
        if sels and not bins:
            pending.extend(sels)
            continue
        if pending and bins:
            sels = pending + sels
            pending = []
        if not sels:
            continue

        # pair selectors with bins
        if len(bins) == 1:
            pairs = [(s, bins[0]) for s in sels]
        elif len(sels) == len(bins):
            pairs = list(zip(sels, bins))
        else:
            pairs = []
            for s in sels:
                nearest = min(bins, key=lambda b: (abs(b[0] - s[0]), b[0] < s[0]))
                pairs.append((s, nearest))
        for (_, _, (c, s)), (_, _, b) in pairs:
            prio = 2 if (c and s) else 1
            put(_slots(c, s), b, prio)

    if pending:
        if rest_bin is None:
            remaining_sels.extend(pending)
    if remaining_sels:
        used = {v for p, v in assigned.values() if v in BINS}
        free = [b for b in BINS if b not in used]
        if len(free) == 1:
            for _, _, (c, s) in remaining_sels:
                put(_slots(c, s), free[0], 1)
    if rest_bin is not None:
        for s in _slots():
            if s not in assigned:
                assigned[s] = (0, rest_bin)
    if conflict or bad or len(assigned) < 9:
        return INVALID
    out = {s: assigned[s][1] for s in SLOTS[:-1]}
    out["other"] = other
    return out


SCRATCH = [  # (text, expected colour mapping or full check) – own examples, not from any test set
    ("red left, yellow middle, blue right", {"red": "left", "yellow": "center", "blue": "right"}),
    ("Blue on the left please; red in the centre and yellow on the right.", {"blue": "left", "red": "center", "yellow": "right"}),
    ("left: yellow / middle: red / right: blue", {"yellow": "left", "red": "center", "blue": "right"}),
    ("red to the right bin, blue to the left one, the rest in the middle", {"red": "right", "blue": "left", "yellow": "center"}),
    ("Everything except red goes in the left bin. Red goes right.", {"red": "right", "yellow": "left", "blue": "left"}),
    ("red left blue right and leave the yellow ones", {"red": "left", "blue": "right", "yellow": "leave"}),
]


if __name__ == "__main__":
    import json
    import sys
    ok = 0
    for text, exp in SCRATCH:
        got = parse(text)
        good = got != INVALID and all(got[f"{c} cube"] == b for c, b in exp.items())
        ok += good
        if not good:
            print("FAIL", text, "->", got if got == INVALID else {c: got[f"{c} cube"] for c in COLORS})
    print(f"scratch {ok}/{len(SCRATCH)}")
    if len(sys.argv) > 1:
        print(json.dumps(parse(sys.argv[1]), indent=1))
