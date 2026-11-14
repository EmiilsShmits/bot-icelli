"""Post-hoc combinations of an LLM method with the rule parser, computed from saved predictions (no GPU).

Variants (all evaluated on the same frozen test sets, so they are hypotheses to confirm on fresh data):
  llm              the LLM answer as is
  other_leave      LLM answer, but `other` forced to "leave" unless the rule parser found an explicit
                   distractor destination
  rule_first       rule parser if it returns a valid answer, else the LLM
  agree            accept only if LLM and rule parser agree; LLM-only when the rule parser refuses;
                   refuse (fallback) when both answer and disagree

  python3 hybrid.py results/hf_google--gemma-4-E4B-it_C [more dirs] > results/hybrid.md
"""
from __future__ import annotations

import json
import os
import sys

import rule_parser
from spec import INVALID

HERE = os.path.dirname(os.path.abspath(__file__))


def valid(x):
    return x not in (None, INVALID)


def variants(pred, text):
    r = rule_parser.parse(text)
    out = {"llm": pred}
    if valid(pred):
        o = dict(pred)
        o["other"] = r["other"] if valid(r) else "leave"
        out["other_leave"] = o
    else:
        out["other_leave"] = pred
    out["rule_first"] = r if valid(r) else pred
    if valid(r) and valid(pred):
        out["agree"] = pred if pred == r else INVALID
    elif valid(pred):
        out["agree"] = pred
    else:
        out["agree"] = INVALID if r == INVALID else r
    return out


def score(rows, key):
    v = [r for r in rows if r["label"] != INVALID]
    inv = [r for r in rows if r["label"] == INVALID]
    res = {}
    if v:
        res["exact"] = sum(r["var"][key] == r["label"] for r in v) / len(v)
        res["cw"] = sum(valid(r["var"][key]) and r["var"][key] != r["label"] for r in v) / len(v)
        res["ds"] = sum(valid(r["var"][key]) and r["var"][key]["other"] == r["label"]["other"] for r in v) / len(v)
    if inv:
        res["refusal"] = sum(not valid(r["var"][key]) for r in inv) / len(inv)
    return res


def main(dirs):
    print("| Method | Variant | T2a exact | T2a CW | T2b exact | T2b CW | T2b DS | T3 refusal |")
    print("|---|---|---|---|---|---|---|---|")
    for d in dirs:
        data = {}
        for t in ("t2a", "t2b", "t3"):
            f = os.path.join(d, f"{t}.preds.jsonl")
            if not os.path.exists(f):
                continue
            rows = [json.loads(l) for l in open(f)]
            for r in rows:
                r["var"] = variants(r["pred"], r["text"])
            data[t] = rows
        for key in ("llm", "other_leave", "rule_first", "agree"):
            s = {t: score(rows, key) for t, rows in data.items()}
            f = lambda t, k: "–" if k not in s.get(t, {}) else f"{100 * s[t][k]:.1f}"
            print(f"| `{os.path.basename(d)}` | {key} | {f('t2a', 'exact')} | {f('t2a', 'cw')} | {f('t2b', 'exact')} | "
                  f"{f('t2b', 'cw')} | {f('t2b', 'ds')} | {f('t3', 'refusal')} |")


if __name__ == "__main__":
    main(sys.argv[1:])
