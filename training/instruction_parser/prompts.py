"""Exact prompts used for the prompted (Phase 2) and fine-tuned (Phase 3) models.

Few-shot examples are T1-style (Aalto's training templates), never from T2a / T2b / T3.
"""
from __future__ import annotations

import json

from spec import INVALID, SLOTS, fixed_order, interpret

TASK = (
    "You turn a robot sorting instruction into a fixed answer.\n"
    "Objects: colours red, yellow, blue x shapes cube, cylinder, triangle (9 known types). "
    "Any other object (unknown colour or shape) is 'other'.\n"
    "Bins: left, center, right (named by position only; middle/centre = center).\n"
    "For each of the 10 slots give where it goes: left, center, right, or leave (stays on the table).\n"
    "Rules: a colour-only rule applies to all three shapes of that colour. 'other' is leave unless the "
    "instruction explicitly says what to do with unknown/other objects. 'Everything' means the known blocks. "
    "If the instruction is contradictory, names a bin that doesn't exist, is unrelated, or leaves a known "
    "object without a destination, the answer is invalid.\n"
)
SLOT_LIST = ", ".join(SLOTS)

FORMAT = {
    "A": TASK + "Answer with one JSON object with exactly these 10 keys: " + SLOT_LIST
    + '. If invalid, answer {"invalid": true}. Output only the JSON.',
    "B": TASK + "Answer with exactly 10 words, the values for these slots in this order: " + SLOT_LIST
    + ". If invalid, answer the single word invalid. Output nothing else.",
    "C": TASK + "Answer with 10 lines 'slot: value' in this order: " + SLOT_LIST + ".",
}

FEW_SHOT_SPECS = [  # T1 templates 0, 4, 2 with three different permutations
    ("Put the blue objects in the left bin, the red objects in the center bin and the yellow objects in the right bin.",
     {"mapping": {"blue": "left", "red": "center", "yellow": "right"}}),
    ("The left bin is for yellow objects, the center bin for blue, the right bin for red.",
     {"mapping": {"yellow": "left", "blue": "center", "red": "right"}}),
    ("Sort the objects: red into right, blue into center, yellow into left.",
     {"mapping": {"red": "right", "blue": "center", "yellow": "left"}}),
]


def render_answer(label, fmt: str) -> str:
    if fmt == "A":
        return json.dumps({"invalid": True}) if label == INVALID else json.dumps(label)
    if fmt == "B":
        return fixed_order(label)
    if fmt == "C":
        return "\n".join(f"{s}: {label[s]}" for s in SLOTS)
    raise ValueError(fmt)


def messages(instruction: str, fmt: str, shots: int = 3):
    """Chat messages. The task text goes into the first user turn (Gemma 3 has no system role)."""
    msgs = []
    first = True
    for text, spec in FEW_SHOT_SPECS[:shots]:
        u = f"Instruction: {text}"
        if first:
            u = FORMAT[fmt] + "\n\n" + u
            first = False
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": render_answer(interpret(spec), fmt)}]
    u = f"Instruction: {instruction}"
    if first:
        u = FORMAT[fmt] + "\n\n" + u
    msgs.append({"role": "user", "content": u})
    return msgs


# Fine-tuned student: short prompt, no few-shot, format B answer.
FT_PREFIX = "Sort instruction -> 10 slots (" + SLOT_LIST + "):\n"


def ft_messages(instruction: str):
    return [{"role": "user", "content": FT_PREFIX + instruction}]


if __name__ == "__main__":
    for f in "ABC":
        print(f"===== format {f} =====")
        for m in messages("<INSTRUCTION>", f):
            print(f"[{m['role']}]\n{m['content']}\n")
    print("===== fine-tuned student =====")
    print(ft_messages("<INSTRUCTION>")[0]["content"])
