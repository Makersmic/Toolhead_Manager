#!/usr/bin/env python3
"""The macro change for a per-head input shaper (docs/proposal-per-head-shaping.md).

    python3 dev/proposal_per_head_shaping.py            print the diff (changes nothing)
    python3 dev/proposal_per_head_shaping.py --apply    NOT YET APPLIED: it waits for Mike's OK (a second run is refused)

Adds one block to _RHINO_APPLY_TUNING in tools/3dp_macros.cfg, just before the loop that reports out-of-range values. Stops and
changes nothing unless the anchor is found exactly once inside that macro."""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_macro_hooks import patched  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = "tools/3dp_macros.cfg"
BLOCK = [
    "  # Input shaping for this head (docs/proposal-per-head-shaping.md): the pick Studio's Input shaping wizard stored, else leave it as it is",
    '  {% set sh = sv.get(("rhino_shaper_" ~ tool)|lower) %}',
    '  {% set sp = sh.split(",") if sh is string else [] %}',
    '  {% set sh_ok = sp|length == 4 and sp[0] in ["zv","mzv","zvd","ei","2hump_ei","3hump_ei"] and sp[2] in ["zv","mzv","zvd","ei","2hump_ei","3hump_ei"]',
    "                 and sp[1]|float > 10 and sp[1]|float < 200 and sp[3]|float > 10 and sp[3]|float < 200 %}",
    '  {% if sh_ok and "input_shaper" in printer.configfile.settings %}',
    "    SET_INPUT_SHAPER SHAPER_TYPE_X={sp[0]} SHAPER_FREQ_X={sp[1]} SHAPER_TYPE_Y={sp[2]} SHAPER_FREQ_Y={sp[3]}",
    '    RESPOND MSG="Input shaper for {tool}: X {sp[0]} {sp[1]} Hz, Y {sp[2]} {sp[3]} Hz (tuned)"',
    "  {% elif sh is string %}",
    '    RESPOND TYPE=error MSG="rhino_shaper_{tool} = {sh} isn\'t valid, so the shaper stays as Klipper loaded it. Run the Input shaping wizard again."',
    "  {% endif %}",
]
CHANGES = [(FILE, "_RHINO_APPLY_TUNING", "before", '  {% for name, v, good in [("rhino_rd_"', BLOCK)]


def main(apply=False):
    path = os.path.join(ROOT, FILE)
    old = open(path, encoding="utf-8").read()
    if "rhino_shaper_" in old:
        raise SystemExit("Already applied: running it again would add the block twice.")
    new = patched(old, CHANGES)
    sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{FILE}", f"b/{FILE}", n=2))
    if apply:
        open(path, "w", encoding="utf-8").write(new)


if __name__ == "__main__":
    main("--apply" in sys.argv)
