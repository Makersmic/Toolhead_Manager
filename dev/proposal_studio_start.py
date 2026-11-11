#!/usr/bin/env python3
"""The macro change for Studio's start wizard (docs/proposal-studio-start.md, approved by Mike Nov 10 2026).

    python3 dev/proposal_studio_start.py                print the unified diff (changes nothing)
    python3 dev/proposal_studio_start.py --apply        write it into the config files (refused once applied)
    python3 dev/proposal_studio_start.py --to DIR       write the changed files into a copy of the config at DIR (tests)

What it adds:
- SET_Z_ZERO remembers which tool its zero was set for (variable_zeroed). SWAP_TOOL clears it at the start of every
  swap; a Klipper restart clears it on its own.
- LASER_JOB_SETUP / DRAGKNIFE_JOB_SETUP FROM=STUDIO: the same checks, then straight to the start, refused unless the
  zero was set for the mounted tool. Without FROM=STUDIO nothing changes: the prompts are the same lines.
- _LASER_TEST_FIRE QUIET=1 and _DK_TEST_CUT QUIET=1: the same pulse / cut, no prompt after it. The knife's quiet test
  cut is refused without a zero for the DragKnife.
- _DK_XY_ZERO: the knife's X/Y work zero (machine origin, G54), moved out of _DK_SAVE_Z so Studio's wizard can run it
  as SET_Z_ZERO's next step, before the test cut.

Every edit names its file, its macro and an anchor line inside that macro; an anchor found other than exactly once stops
the script with nothing written."""
import difflib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = "# Studio start wizard (docs/proposal-studio-start.md)"
TM = ['  {% set _tm = {} %}',
      '  {% set _ = _tm.update(printer["gcode_macro VARIABLES"].tool_mapping) %}',
      '  {% set _ = _tm.update(printer["gcode_macro CUSTOM_TOOLS"].tool_mapping) %}']

# (file, macro, op, anchor, lines). op: "before" / "after" the anchor line, "end" of the macro, "replace" the anchor
# line and the lines after it that equal lines[...] (anchor is a list there), "macro_after" a new macro after this one.
CHANGES = [
    # ---- the zero flag
    ("toolchanger.cfg", "SET_Z_ZERO", "after", "variable_next: ''",
     ["variable_zeroed: ''      " + NOTE + ": the tool this Z zero was set for; cleared by SWAP_TOOL and restarts"]),
    ("toolchanger.cfg", "_Z_ZERO_SAVE", "after", '  {% set nxt = printer["gcode_macro SET_Z_ZERO"].next %}',
     TM + ['  {% set name = _tm.get(printer["gcode_macro SWAP_TOOL"].current_tool|int, "") %}']),
    ("toolchanger.cfg", "_Z_ZERO_SAVE", "after", "  SET_GCODE_OFFSET Z={'%.3f' % z}",
     ["  " + NOTE + ": a job started from Studio checks this", "  SET_GCODE_VARIABLE MACRO=SET_Z_ZERO VARIABLE=zeroed VALUE=\"'{name}'\""]),
    ("toolchanger.cfg", "SWAP_TOOL", "after", "      SET_GCODE_VARIABLE MACRO=SWAP_TOOL VARIABLE=pending_tool VALUE={new_tool}",
     ["      " + NOTE + ": a new tool needs a new Z zero", "      SET_GCODE_VARIABLE MACRO=SET_Z_ZERO VARIABLE=zeroed VALUE=\"''\""]),

    # ---- laser
    ("guided/laser_workflow.cfg", "LASER_JOB_SETUP", "before", "  # job hooks / interlocks (docs/proposal-macro-hooks.md)",
     ["  " + NOTE + ": FROM=STUDIO skips the prompts below, so it needs this tool's Z zero first",
      '  {% set studio = params.FROM|default("")|upper == "STUDIO" %}',
      '  {% if studio and printer["gcode_macro SET_Z_ZERO"].zeroed != "LightSaber" %}',
      '    { action_raise_error("LASER_JOB_SETUP FROM=STUDIO: set the Z zero for the LightSaber first (SET_Z_ZERO). A tool change or a Klipper restart clears it.") }',
      "  {% endif %}"]),
    ("guided/laser_workflow.cfg", "LASER_JOB_SETUP", "before", '  RESPOND TYPE=command MSG="action:prompt_begin Laser setup"',
     ["  {% if studio %}",
      "    " + NOTE + ": Studio's wizard showed the checklist, set the zero and test-fired; start (it refuses another tool)",
      "    _LASER_START",
      "  {% else %}"]),
    ("guided/laser_workflow.cfg", "LASER_JOB_SETUP", "end", None, ["  {% endif %}"]),
    ("guided/laser_workflow.cfg", "_LASER_TEST_FIRE", "after", "  DEACTIVATE_LASER",
     ["  " + NOTE + ": QUIET=1 is the same pulse with no prompt after it (Studio asks on screen)",
      "  {% if params.QUIET|default(0)|int == 1 %}",
      "  M117 Test fire done",
      "  {% else %}"]),
    ("guided/laser_workflow.cfg", "_LASER_TEST_FIRE", "end", None, ["  {% endif %}"]),

    # ---- drag knife
    ("guided/dragknife_workflow.cfg", "DRAGKNIFE_JOB_SETUP", "before", "  # Map file target pointer payload",
     ["  " + NOTE + ": FROM=STUDIO skips the prompts below, so it needs this tool's Z zero first",
      '  {% set studio = params.FROM|default("")|upper == "STUDIO" %}',
      '  {% if studio and printer["gcode_macro SET_Z_ZERO"].zeroed != "DragKnife" %}',
      '    { action_raise_error("DRAGKNIFE_JOB_SETUP FROM=STUDIO: set the Z zero for the DragKnife first (SET_Z_ZERO). A tool change or a Klipper restart clears it.") }',
      "  {% endif %}"]),
    ("guided/dragknife_workflow.cfg", "DRAGKNIFE_JOB_SETUP", "before", '  RESPOND TYPE=command MSG="action:prompt_begin Drag knife setup"',
     ["  {% if studio %}",
      "    " + NOTE + ": Studio's wizard showed the checklist, set the zero and ran the test cut; X/Y zero, then start",
      "    _DK_XY_ZERO",
      "    _DK_START",
      "  {% else %}"]),
    ("guided/dragknife_workflow.cfg", "DRAGKNIFE_JOB_SETUP", "end", None, ["  {% endif %}"]),
    ("guided/dragknife_workflow.cfg", "_DK_SAVE_Z", "replace",
     ["  SAVE_VARIABLE VARIABLE=cnc_g54_x VALUE=0.0", "  SAVE_VARIABLE VARIABLE=cnc_g54_y VALUE=0.0", "  G54",
      "  M117 G54 Material Surface Set"],
     ["  _DK_XY_ZERO               " + NOTE + ": the same four lines, shared"]),
    ("guided/dragknife_workflow.cfg", "_DK_SAVE_Z", "macro_after", None,
     ["", "[gcode_macro _DK_XY_ZERO]",
      "description: The drag knife's X/Y work zero is the machine origin - save it and apply G54. Runs after SET_Z_ZERO.",
      "gcode:",
      "  SAVE_VARIABLE VARIABLE=cnc_g54_x VALUE=0.0",
      "  SAVE_VARIABLE VARIABLE=cnc_g54_y VALUE=0.0",
      "  G54",
      "  M117 G54 Material Surface Set"]),
    ("guided/dragknife_workflow.cfg", "_DK_TEST_CUT", "after", "gcode:",
     ["  " + NOTE + ": QUIET=1 is the same cut with no prompt after it, and only after a Z zero for the DragKnife",
      "  {% set quiet = params.QUIET|default(0)|int == 1 %}",
      '  {% if quiet and printer["gcode_macro SET_Z_ZERO"].zeroed != "DragKnife" %}',
      '    { action_raise_error("_DK_TEST_CUT QUIET=1: set the Z zero for the DragKnife first (SET_Z_ZERO NEXT=_DK_XY_ZERO).") }',
      "  {% endif %}"]),
    ("guided/dragknife_workflow.cfg", "_DK_TEST_CUT", "before", "  # Prompt evaluation window panel", ["  {% if not quiet %}"]),
    ("guided/dragknife_workflow.cfg", "_DK_TEST_CUT", "end", None, ["  {% endif %}"]),
]


def _block(lines, macro):
    head = f"[gcode_macro {macro}]"
    starts = [i for i, l in enumerate(lines) if l.strip() == head]
    if len(starts) != 1:
        raise SystemExit(f"{macro}: found {len(starts)} definitions")
    i = starts[0]
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("[")), len(lines))
    while j > i and (not lines[j - 1].strip() or lines[j - 1].startswith("#")):   # blanks and the next macro's header comments
        j -= 1
    return i, j


def patched(text, file_changes):
    if NOTE in text:
        raise SystemExit("already applied (the note is in the file): nothing to do")
    lines = text.split("\n")
    for _f, macro, op, anchor, new in file_changes:
        i, j = _block(lines, macro)
        if op == "end":
            lines[j:j] = new
            continue
        if op == "macro_after":
            lines[j:j] = new
            continue
        first = anchor[0] if op == "replace" else anchor
        hits = [k for k in range(i, j) if lines[k].rstrip() == first.rstrip()]
        if len(hits) != 1:
            raise SystemExit(f"{macro}: anchor {first!r} found {len(hits)} times")
        at = hits[0]
        if op == "replace":
            if [l.rstrip() for l in lines[at:at + len(anchor)]] != [a.rstrip() for a in anchor]:
                raise SystemExit(f"{macro}: the lines to replace aren't all there")
            lines[at:at + len(anchor)] = new
        else:
            lines[at + (1 if op == "after" else 0):at + (1 if op == "after" else 0)] = new
    return "\n".join(lines)


def changed(root=ROOT):
    by_file = {}
    for ch in CHANGES:
        by_file.setdefault(ch[0], []).append(ch)
    out = {}
    for f, chs in by_file.items():
        with open(os.path.join(root, f), encoding="utf-8") as fh:
            old = fh.read()
        out[f] = (old, patched(old, chs))
    return out


def main(argv):
    to = argv[argv.index("--to") + 1] if "--to" in argv else None
    out = changed(ROOT if not to else to)
    if to or "--apply" in argv:
        for f, (_old, new) in out.items():
            with open(os.path.join(to or ROOT, f), "w", encoding="utf-8") as fh:
                fh.write(new)
        return
    for f, (old, new) in out.items():
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{f}", f"b/{f}", n=2))


if __name__ == "__main__":
    main(sys.argv[1:])
