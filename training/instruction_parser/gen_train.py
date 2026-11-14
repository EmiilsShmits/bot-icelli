"""Phase 3 (a): programmatic training data, labelled by construction with spec.interpret.

Grammar + synonyms written for this script (not copied from T2a / T2b, which the author never read).
  python3 gen_train.py --n 14000 --out data_train/prog.jsonl --seed 0
Each line: {"text", "spec", "label", "kind"}.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re

from spec import BINS, COLORS, INVALID, SHAPES, interpret

R = random.Random(0)

COL = {
    "red": ["red", "red", "red", "Red", "RED", "reddish"],
    "yellow": ["yellow", "yellow", "yellow", "Yellow", "YELLOW", "yellowish"],
    "blue": ["blue", "blue", "blue", "Blue", "BLUE", "bluish"],
}
SHP_PL = {"cube": ["cubes", "cubes", "square blocks", "cube-shaped pieces", "boxes"],
          "cylinder": ["cylinders", "cylinders", "round pieces", "cylindrical blocks", "tubes"],
          "triangle": ["triangles", "triangles", "triangular pieces", "triangle blocks", "prisms"]}
SHP_SG = {"cube": ["cube", "square block"], "cylinder": ["cylinder", "round piece"],
          "triangle": ["triangle", "triangular piece"]}
BIN = {
    "left": ["the left bin", "left", "the left-hand bin", "the leftmost bin", "the bin on the left", "the left box",
             "the left one", "the far-left bin", "the left container", "the bin to the left"],
    "center": ["the center bin", "the middle bin", "the centre bin", "middle", "the central bin", "the bin in the middle",
               "the middle one", "center", "centre", "the middle container", "the one in between"],
    "right": ["the right bin", "right", "the right-hand bin", "the rightmost bin", "the bin on the right", "the right box",
              "the right one", "the far-right bin", "the right container", "the bin to the right"],
}
BIN_TERSE = {"left": ["left", "L", "left"], "center": ["middle", "center", "centre", "mid"], "right": ["right", "R", "right"]}


def pick(xs):
    return R.choice(xs)


def col_phrase(c):
    w = pick(COL[c])
    return pick([f"{w}", f"the {w} ones", f"{w} objects", f"{w} blocks", f"{w} pieces", f"anything {w}",
                 f"all {w} items", f"{w}-coloured objects", f"the {w} things", f"every {w} block", f"{w} stuff"])


def cs_phrase(c, s):
    w = pick(COL[c])
    return pick([f"{w} {pick(SHP_PL[s])}", f"the {w} {pick(SHP_PL[s])}", f"any {w} {pick(SHP_SG[s])}",
                 f"every {w} {pick(SHP_SG[s])}"])


def shape_phrase(s):
    return pick([pick(SHP_PL[s]), f"all the {pick(SHP_PL[s])}", f"the {pick(SHP_PL[s])}", f"every {pick(SHP_SG[s])}",
                 f"any {pick(SHP_SG[s])}"])


def sel_phrase(sel):
    c, s = sel
    if c and s:
        return cs_phrase(c, s)
    if c:
        return col_phrase(c)
    return shape_phrase(s)


def assign(sel, b, terse=False):
    S = sel_phrase(sel)
    if b == "leave":
        return pick([f"leave {S} on the table", f"don't touch {S}", f"{S} stay where they are", f"ignore {S}",
                     f"{S}: leave", f"do not move {S}", f"{S} remain on the table", f"leave {S} alone",
                     f"{S} should not be picked up", f"skip {S}"])
    if terse:
        return pick([f"{S} {pick(BIN_TERSE[b])}", f"{S}→{pick(BIN_TERSE[b])}", f"{S}: {pick(BIN_TERSE[b])}",
                     f"{S} -> {pick(BIN_TERSE[b])}", f"{pick(BIN_TERSE[b])}: {S}", f"{S} = {pick(BIN_TERSE[b])}"])
    B = pick(BIN[b])
    return pick([f"{S} go in {B}", f"{S} into {B}", f"put {S} in {B}", f"{B} gets {S}", f"{B} is for {S}",
                 f"{S} should be placed in {B}", f"send {S} to {B}", f"toss {S} into {B}", f"{S} belong in {B}",
                 f"{B} takes {S}", f"I want {S} in {B}", f"{S} are to be put in {B}", f"place {S} into {B}",
                 f"{S} need to end up in {B}", f"carry {S} over to {B}", f"{B}: {S}", f"{S} to {B}",
                 f"for {B}, {S}", f"drop {S} in {B}", f"{S} should go to {B}"])


def rest_clause(b):
    if b == "leave":
        return pick(["leave the rest on the table", "don't touch anything else", "everything else stays put",
                     "the others stay where they are"])
    B = pick(BIN[b])
    return pick([f"the rest go in {B}", f"everything else to {B}", f"anything left over goes in {B}",
                 f"remaining ones in {B}", f"all the others into {B}", f"whatever is left goes to {B}"])


def remaining_bin_clause(sel):
    return pick([f"{sel_phrase(sel)} go in the remaining bin", f"{sel_phrase(sel)} take the last bin",
                 f"{sel_phrase(sel)} into the other bin", f"the leftover bin is for {sel_phrase(sel)}",
                 f"{sel_phrase(sel)} get whichever bin is free"])


DISTR_LEAVE = ["ignore anything that isn't a red, yellow or blue block", "leave unknown objects alone",
               "don't touch anything unfamiliar", "only sort the coloured blocks", "if you see something that isn't one of the blocks, leave it",
               "anything else on the table that isn't one of our blocks stays there", "do not pick up objects you don't recognise",
               "only the cubes, cylinders and triangles count; leave other things", "ignore distractors",
               "unknown items stay on the table"]
DISTR_BIN = ["anything that isn't one of the known blocks goes in {B}", "put unfamiliar objects in {B}",
             "any object you don't recognise goes to {B}", "stray objects that aren't our blocks: {B}",
             "if something isn't a red, yellow or blue block, put it in {B}"]
EXCEPT = ["everything except {X} goes in {B}", "all but {X} → {B}", "put everything other than {X} in {B}",
          "apart from {X}, everything goes to {B}", "{B} gets everything that isn't {X}",
          "except for {X}, put all objects in {B}"]
UNRELATED = ["What time is it?", "The weather is nice today.", "Please stand by.", "Hello!", "", " ",
             "asdf qwerty", "Can you dance?", "Wave at the audience.", "Pick up the cup and bring it to me.",
             "Turn off the lights.", "Tell me a joke."]
PREFIX = ["", "", "", "", "Please ", "Hi robot, ", "Okay, ", "Alright: ", "Robot, ", "Task: ", "Listen up. ",
          "Here's the plan: ", "Hey! "]
SUFFIX = ["", "", "", "", " Thanks.", " Thank you!", " Go.", " Good luck!", " Cheers."]
JOIN = [", ", "; ", ". ", " and ", "\n", " / ", ", then ", " — "]


def typo(w):
    if len(w) < 4 or not w.isalpha():
        return w
    i = R.randrange(1, len(w) - 1)
    op = R.random()
    if op < 0.33:
        return w[:i] + w[i + 1:]
    if op < 0.66:
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return w[:i] + w[i] + w[i:]


def finalize(clauses, terse=False):
    R.shuffle(clauses) if R.random() < 0.3 else None
    j = pick(JOIN) if not terse else pick([", ", " / ", "; ", "\n"])
    text = j.join(clauses)
    pre = pick(PREFIX)
    if text and (not pre or pre.endswith((". ", ": ", "! "))):
        text = text[0].upper() + text[1:]
    if not terse and not text.endswith((".", "!", "?")):
        text += "."
    text = pre + text + pick(SUFFIX)
    r = R.random()
    if r < 0.15:
        text = text.lower()
    elif r < 0.2:
        text = re.sub(r"[.,;!]", "", text.lower())
    if R.random() < 0.15:
        ws = text.split(" ")
        k = R.randrange(len(ws))
        ws[k] = typo(ws[k])
        text = " ".join(ws)
    return text


def colour_base(clauses, rules, terse, use_rest=True):
    perm = R.sample(BINS, 3)
    cols = list(COLORS)
    R.shuffle(cols)
    mapping = dict(zip(cols, perm))
    mode = R.random()
    if use_rest and mode < 0.15:
        clauses += [assign((cols[0], None), mapping[cols[0]], terse), assign((cols[1], None), mapping[cols[1]], terse),
                    rest_clause(mapping[cols[2]])]
        rules.append({"colors": None, "shapes": None, "to": mapping[cols[2]]})
        rules += [{"colors": [c], "shapes": None, "to": mapping[c]} for c in cols[:2]]
    elif use_rest and mode < 0.25:
        clauses += [assign((cols[0], None), mapping[cols[0]], terse), assign((cols[1], None), mapping[cols[1]], terse),
                    remaining_bin_clause((cols[2], None))]
        rules += [{"colors": [c], "shapes": None, "to": mapping[c]} for c in cols]
    else:
        clauses += [assign((c, None), mapping[c], terse) for c in cols]
        rules += [{"colors": [c], "shapes": None, "to": mapping[c]} for c in cols]
    return mapping


def sample(kind):
    terse = R.random() < 0.2
    clauses, rules = [], []
    other = "leave"
    if kind == "colour_only":
        colour_base(clauses, rules, terse)
    elif kind == "colour_shape":
        mapping = colour_base(clauses, rules, terse, use_rest=False)
        for _ in range(R.choice([1, 1, 2])):
            c, s = pick(COLORS), pick(SHAPES)
            b = pick([x for x in BINS + ("leave",) if x != mapping[c]])
            clauses.append(assign((c, s), b, terse))
            rules.append({"colors": [c], "shapes": [s], "to": b})
    elif kind == "shape_only":
        shp = list(SHAPES)
        R.shuffle(shp)
        dest = {s: pick(BINS) for s in shp} if R.random() < 0.4 else dict(zip(shp, R.sample(BINS, 3)))
        clauses += [assign((None, s), dest[s], terse) for s in shp]
        rules += [{"colors": None, "shapes": [s], "to": dest[s]} for s in shp]
        if R.random() < 0.4:
            c, s = pick(COLORS), pick(SHAPES)
            b = pick([x for x in BINS + ("leave",) if x != dest[s]])
            clauses.append(assign((c, s), b, terse))
            rules.append({"colors": [c], "shapes": [s], "to": b})
    elif kind == "exclusion":
        b1, b2 = R.sample(BINS + ("leave",) if R.random() < 0.2 else BINS, 2)
        x = (pick(COLORS), None) if R.random() < 0.6 else (None, pick(SHAPES))
        X = sel_phrase(x)
        B = "the table" if b1 == "leave" else pick(BIN[b1])
        ex = pick(EXCEPT).format(X=X, B=B) if b1 != "leave" else pick(
            [f"leave everything except {X} on the table", f"only {X} get moved"])
        clauses += [ex, assign(x, b2, terse)]
        rules += [{"colors": None, "shapes": None, "to": b1},
                  {"colors": [x[0]] if x[0] else None, "shapes": [x[1]] if x[1] else None, "to": b2}]
    elif kind == "leave":
        if R.random() < 0.5:
            cols = list(COLORS)
            R.shuffle(cols)
            bins = R.sample(BINS, 2)
            if R.random() < 0.5:
                clauses += [assign((cols[0], None), bins[0], terse), assign((cols[1], None), bins[1], terse),
                            assign((cols[2], None), "leave", terse)]
            else:
                clauses.append(pick(["only sort the {a} and {b} blocks", "just move {a} and {b}",
                                     "only {a} and {b} matter"]).format(a=cols[0], b=cols[1]))
                clauses += [assign((cols[0], None), bins[0], terse), assign((cols[1], None), bins[1], terse)]
            rules += [{"colors": None, "shapes": None, "to": "leave"},
                      {"colors": [cols[0]], "shapes": None, "to": bins[0]},
                      {"colors": [cols[1]], "shapes": None, "to": bins[1]}]
        else:
            colour_base(clauses, rules, terse, use_rest=False)
            s = pick(SHAPES)
            clauses.append(pick([f"but leave all {pick(SHP_PL[s])} on the table",
                                 f"{pick(SHP_PL[s])} stay where they are, whatever their colour",
                                 f"except {pick(SHP_PL[s])}, which you should not touch",
                                 f"don't touch any {pick(SHP_SG[s])}"]))
            rules.append({"colors": None, "shapes": [s], "to": "leave"})
    elif kind == "negation":
        mapping = colour_base(clauses, rules, terse, use_rest=False)
        c = pick(COLORS)
        wrong = pick([b for b in BINS if b != mapping[c]])
        clauses.insert(R.randrange(len(clauses) + 1), pick([
            f"don't put {col_phrase(c)} in {pick(BIN[wrong])}", f"{col_phrase(c)} must not go in {pick(BIN[wrong])}",
            f"never {col_phrase(c)} in {pick(BIN[wrong])}", f"no {pick(COL[c])} in {pick(BIN[wrong])}"]))
    if R.random() < 0.3:
        if R.random() < 0.2:
            other = pick(BINS)
            clauses.append(pick(DISTR_BIN).format(B=pick(BIN[other])))
        else:
            clauses.append(pick(DISTR_LEAVE))
    spec = {"rules": rules, "other": other}
    return finalize(clauses, terse), spec


def sample_invalid():
    k = R.random()
    cols = list(COLORS)
    R.shuffle(cols)
    if k < 0.3:  # contradiction
        b1, b2 = R.sample(BINS, 2)
        perm = dict(zip(cols, R.sample(BINS, 3)))
        clauses = [assign((c, None), perm[c]) for c in cols]
        clauses.append(assign((cols[0], None), b2 if perm[cols[0]] != b2 else b1))
        text = finalize(clauses)
    elif k < 0.55:  # nonexistent bin
        bad = pick(["the top bin", "the bottom bin", "the green bin", "the fourth bin", "the bin behind you",
                    "the upper bin", "the blue bin", "the red bin", "the back bin", "the kitchen"])
        perm = dict(zip(cols, R.sample(BINS, 3)))
        clauses = [assign((c, None), perm[c]) for c in cols[:2]] + [f"{col_phrase(cols[2])} go in {bad}"]
        text = finalize(clauses)
    elif k < 0.75:
        text = pick(UNRELATED)
    else:  # undefined: a colour without destination
        perm = dict(zip(cols, R.sample(BINS, 3)))
        text = finalize([assign((c, None), perm[c]) for c in cols[:2]])
    return text, {"invalid": True}


KINDS = [("colour_only", 0.40), ("colour_shape", 0.13), ("shape_only", 0.10), ("exclusion", 0.10),
         ("leave", 0.12), ("negation", 0.07), ("invalid", 0.08)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=14000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="data_train/prog.jsonl")
    a = ap.parse_args()
    R.seed(a.seed)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    seen = set()
    rows = []
    while len(rows) < a.n:
        kind = R.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
        text, spec = sample_invalid() if kind == "invalid" else sample(kind)
        if text in seen:
            continue
        seen.add(text)
        rows.append({"text": text, "spec": spec, "label": interpret(spec), "kind": kind})
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from collections import Counter
    print(len(rows), Counter(r["kind"] for r in rows))


if __name__ == "__main__":
    main()
