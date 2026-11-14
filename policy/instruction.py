"""Instruction -> which bin each colour goes to (v1).

v1 reads the instruction with Emīls's rule parser (`training/instruction_parser/rule_parser.py`): offline and
instant, 100 % on Aalto's 8 training templates and 86.7 % on unseen colour-only paraphrases
(`training/instruction_parser/RESULTS.md`). The Gemma / Gemini stages come in v2.

The parser answers for 9 object types (colour x shape) plus unknown objects. v1's perception does not tell shapes
apart yet, so the answer is folded to one bin per colour (the most common answer over the 3 shapes).

    mapping, source = mapping_for("Purple goes left, orange in the middle, yellow right.", "sort_language")
    # -> ({"blue": "left", "red": "center", "yellow": "right"}, "rules")

Colour names follow Aalto's sim: "red" = the warm class (red in sim, orange on the real table) and "blue" = the cool
class (blue in sim, purple on the real table); the parser already maps orange -> red and purple -> blue. A colour
whose objects should stay on the table is left out of the mapping; the classical planner then skips those objects.
"""
from __future__ import annotations

import collections
import logging
import os
import sys
from pathlib import Path

from aaltonomous.interface.tasks import FIXED_INSTRUCTION, FIXED_MAPPING

log = logging.getLogger("bot-icelli.instruction")

_HERE = Path(__file__).resolve().parent
for _d in (os.environ.get("INSTRUCTION_PARSER_DIR", ""), str(_HERE.parent / "training" / "instruction_parser")):
    if _d and (Path(_d) / "rule_parser.py").exists():
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
import rule_parser  # noqa: E402  (needs spec.py from the same folder)
from spec import COLORS, SHAPES  # noqa: E402

BINS = ("left", "center", "right")
ALIASES = {"orange": "red", "purple": "blue"}   # real object colours -> the camera classes (module doc)


def fold_to_colours(slots: dict) -> tuple[dict, bool]:
    """10-slot parser answer -> ({colour: bin}, shape_rules_dropped). Colours to leave on the table are omitted."""
    out, dropped = {}, False
    for c in COLORS:
        vals = [slots[f"{c} {s}"] for s in SHAPES]
        dropped |= len(set(vals)) > 1
        best = collections.Counter(vals).most_common(1)[0][0]
        if best in BINS:
            out[c] = best
    return out, dropped


def mapping_for(instruction: str, task: str | None = None) -> tuple[dict, str]:
    """Returns ({colour: bin}, where the answer came from). Never raises."""
    # Always read the text, even for sort_fixed: on the real robot rung 1 is yellow -> left, purple -> center,
    # orange -> right (Aalto, Discord Sat 15:07), not the sim's red -> left, yellow -> center, blue -> right.
    text = (instruction or "").strip()
    if text == FIXED_INSTRUCTION:
        # A sim whose scene was recoloured (modal_pipeline/sim/scene_variant.py --colors real/venue) also rewrites
        # Aalto's FIXED_MAPPING with the real names; the camera classes are red / yellow / blue, so fold them.
        fixed = {ALIASES.get(c, c): b for c, b in FIXED_MAPPING.items()}
        if set(fixed) <= set(COLORS):
            return fixed, "fixed"
    try:
        slots = rule_parser.parse(text)
    except Exception:  # a parser bug must never stop the robot
        log.exception("rule parser crashed on %r", text)
        slots = None
    if not isinstance(slots, dict):
        return dict(FIXED_MAPPING), "default (parser refused)"
    mapping, dropped = fold_to_colours(slots)
    return mapping, "rules" + (" (shape rules folded to colours)" if dropped else "")
