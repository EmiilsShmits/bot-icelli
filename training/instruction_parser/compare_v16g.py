"""v1.6g instruction stage on the frozen test sets, through the policy's own code (policy/instruction_gemma.py,
policy/instruction_d1.py, policies/oracle_v15.mapping_with_shapes), one instruction at a time on the CPU, as in an
episode.

    # in the v1.6g image (torch + weights inside), test sets mounted:
    docker run --rm -v $PWD/training/instruction_parser:/ip bot-icelli/policy:v1.6g \
        python3 /ip/compare_v16g.py /ip/data/t2a.jsonl /ip/data/t2b.jsonl --out /ip/results/v16g
    # add --env-file <file with GEMINI_API_KEY=...> to measure the online chain Decision -> Gemma -> rules too

Per set it prints:
  * each stage alone, 10 slots (the RESULTS.md metric): exact / wrong (answered, >= 1 slot wrong = confidently wrong)
    / no answer, for the rule parser, Gemma 1B (+ latency) and, with a key, Decision 1;
  * the chains as the policy runs them, judged on the mapping the planner gets (instruction_d1.slots_to_mapping of
    the label): offline = Gemma within its deadline, else the rules' mapping (mapping_with_shapes: what reset() sets;
    Aalto's fixed mapping when the rule parser refuses too); online = Decision within 2.5 s, else the offline chain.
Gemma runs without a deadline here so every answer is seen; the chains then drop answers slower than
V16G_GEMMA_DEADLINE (default 5 s), as the policy would.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for root in (HERE.parents[1], Path("/app")):           # repo checkout, or inside the image
    if (root / "policy" / "instruction_gemma.py").exists():
        sys.path[:0] = [str(root / "policy"), str(root / "third_party" / "aaltonomous-humanoid"), str(root)]
        break

import instruction_d1 as D  # noqa: E402
import instruction_gemma as G  # noqa: E402
import rule_parser  # noqa: E402
from policies.oracle_v15 import mapping_with_shapes  # noqa: E402
from spec import INVALID, interpret  # noqa: E402


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else float("nan")


def judge(pred, label):
    """10-slot answer -> 'exact' | 'wrong' | 'none'."""
    if pred is None or pred == INVALID:
        return "none"
    return "exact" if pred == label else "wrong"


def line(name, outcomes, n, extra=""):
    ex, wr, no = (sum(o == k for o in outcomes) for k in ("exact", "wrong", "none"))
    return f"| {name} | {ex}/{n} ({100 * ex / n:.1f}%) | {wr} ({100 * wr / n:.1f}%) | {no} |{extra}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sets", nargs="+")
    ap.add_argument("--out", help="folder for per-item JSONL")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    gemma = G.GemmaInstruction(deadline_s=600.0)
    if not gemma.enabled:
        sys.exit(f"Gemma is off: {gemma.why_off}")
    policy_deadline = float(os.environ.get("V16G_GEMMA_DEADLINE", 5.0))
    decision = D.DecisionInstruction()                    # policy defaults: 2.5 s deadline, 2.0 s timeout, conf 0.6
    print(f"Gemma: {gemma.path}, {gemma.threads} threads, {gemma.dtype}, load {gemma.load_s} s, self-test "
          f"{gemma.self_test_s} s; policy deadline {policy_deadline} s; Decision {'on' if decision.enabled else 'off'}")

    for path in a.sets:
        rows = [json.loads(l) for l in open(path) if l.strip()][: a.limit]
        n, out = len(rows), []
        t_set = time.monotonic()
        for i, r in enumerate(rows):
            label = interpret(r["spec"])
            text = r["text"]
            try:
                rules = rule_parser.parse(text)
            except Exception:
                rules = None
            gemma.start(text)
            g_slots, g_rec = gemma.result()
            d_slots, d_rec = (None, {"used": False, "why": "off"})
            if decision.enabled:
                decision.start(text)
                d_slots, d_rec = decision.result()
            g_lat = g_rec.get("latency_s")
            g_in_time = g_slots if (g_lat is not None and g_lat <= policy_deadline) else None
            want = D.slots_to_mapping(label)
            rules_map, rules_src = mapping_with_shapes(text, "sort_language")
            off_slots = g_in_time
            off_map = D.slots_to_mapping(off_slots) if off_slots is not None else rules_map
            # docs/CONTEXT.md §6.2 idea, measured only (not in the policy): Gemma only where the rules agree or refuse
            rules_read = isinstance(rules, dict)
            agree_slots = off_slots if (off_slots is not None and (not rules_read or off_slots == rules)) else None
            agree_map = D.slots_to_mapping(agree_slots) if agree_slots is not None else rules_map
            on_slots = d_slots if d_slots is not None else off_slots
            on_map = D.slots_to_mapping(on_slots) if on_slots is not None else rules_map
            rec = {"id": r["id"], "category": r["category"], "text": text,
                   "rules": judge(rules, label), "gemma": judge(g_slots, label), "gemma_latency_s": g_lat,
                   "gemma_raw": g_rec.get("raw"), "gemma_why": g_rec.get("why"),
                   "decision": judge(d_slots, label) if decision.enabled else None,
                   "decision_latency_s": d_rec.get("latency_s"), "decision_why": d_rec.get("why"),
                   "offline_source": "gemma" if off_slots is not None else rules_src,
                   "offline_ok": off_map == want,
                   "agree_source": "gemma" if agree_slots is not None else rules_src, "agree_ok": agree_map == want,
                   "online_source": ("decision" if d_slots is not None else "gemma" if off_slots is not None
                                     else rules_src) if decision.enabled else None,
                   "online_ok": on_map == want if decision.enabled else None,
                   "rules_policy_ok": rules_map == want,
                   "fixed_default": rules_src.startswith("default")}
            out.append(rec)
            if (i + 1) % 25 == 0:
                print(f"  {Path(path).name}: {i + 1}/{n} ({time.monotonic() - t_set:.0f} s)", flush=True)
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            with open(Path(a.out) / (Path(path).stem + ".jsonl"), "w") as f:
                for rec in out:
                    f.write(json.dumps(rec) + "\n")

        lat = [o["gemma_latency_s"] for o in out if o["gemma_latency_s"] is not None]
        print(f"\n### {Path(path).name} ({n} items)\n")
        print("Each stage alone (10 slots; wrong = confidently wrong):\n")
        print("| Stage | Exact | Wrong | No answer |\n|---|---|---|---|")
        print(line("rule parser", [o["rules"] for o in out], n))
        print(line("Gemma 1B, image, CPU", [o["gemma"] for o in out], n))
        if decision.enabled:
            print(line("Decision 1 (v1.6 prompt)", [o["decision"] for o in out], n))
        print(f"\nGemma latency (CPU, {gemma.threads} threads, {gemma.dtype}): p50 {pct(lat, .5):.2f} s, "
              f"p95 {pct(lat, .95):.2f} s, max {max(lat):.2f} s; over the {policy_deadline:.0f} s deadline: "
              f"{sum(x > policy_deadline for x in lat)}")
        print("\nChains as the policy runs them (judged on the planner's mapping):\n")
        print("| Chain | Right mapping | Answered by |\n|---|---|---|")

        def chain_row(name, ok_key, src_key):
            ok = sum(bool(o[ok_key]) for o in out)
            srcs = {}
            for o in out:
                s = o[src_key]
                s = "rules" if s.startswith("rules") else ("fixed default" if s.startswith("default") else s)
                srcs[s] = srcs.get(s, 0) + 1
            return f"| {name} | {ok}/{n} ({100 * ok / n:.1f}%) | " + ", ".join(f"{k} {v}" for k, v in sorted(srcs.items())) + " |"
        print(f"| v1.5 / v1.6 offline: rules only | {sum(o['rules_policy_ok'] for o in out)}/{n} "
              f"({100 * sum(o['rules_policy_ok'] for o in out) / n:.1f}%) | rules, fixed default "
              f"{sum(o['fixed_default'] for o in out)} |")
        print(chain_row("v1.6g offline: Gemma -> rules", "offline_ok", "offline_source"))
        print(chain_row("(not built) offline, Gemma only where the rules agree or refuse", "agree_ok", "agree_source"))
        if decision.enabled:
            print(chain_row("v1.6g online: Decision -> Gemma -> rules", "online_ok", "online_source"))
        cats = sorted({o["category"] for o in out})
        print("\nPer category, right mapping (rules only / v1.6g offline" + (" / online" if decision.enabled else "")
              + "):")
        for c in cats:
            sel = [o for o in out if o["category"] == c]
            parts = [sum(o["rules_policy_ok"] for o in sel), sum(o["offline_ok"] for o in sel)]
            if decision.enabled:
                parts.append(sum(o["online_ok"] for o in sel))
            print(f"  {c}: {' / '.join(map(str, parts))} of {len(sel)}")
        misses = [o for o in out if not o["offline_ok"]]
        print(f"\nOffline misses ({len(misses)}):")
        for o in misses:
            print(f"  {o['id']} [{o['offline_source']}] {o['text'][:90]!r} gemma={o['gemma_raw']!r}")
        print(f"\n({Path(path).name}: {time.monotonic() - t_set:.0f} s)")


if __name__ == "__main__":
    main()
