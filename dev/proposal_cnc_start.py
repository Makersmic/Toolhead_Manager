#!/usr/bin/env python3
"""The macro change for Studio's CNC start wizard (docs/proposal-cnc-start.md). Applied Nov 11 2026 (1.9.27).

    python3 dev/proposal_cnc_start.py                print the unified diff (changes nothing)
    python3 dev/proposal_cnc_start.py --apply        write it into guided/cnc_workflow.cfg (DONE Nov 11 2026; refused once applied)
    python3 dev/proposal_cnc_start.py --to DIR       write the changed file into a copy of the config at DIR (tests)

The same pattern as the laser and knife (dev/proposal_studio_start.py, 1.9.25):
- CNC_JOB_SETUP FROM=STUDIO: the same checks, then straight to _CNC_START. Refused unless SET_Z_ZERO's zero is for the
  HotJoe and the spindle is running (relay on, throttle above the ESC's 0.3 stop): a job must never start on a stopped
  spindle. variable_studio_start tells Studio this config has it.
- _CNC_SAVE_XY QUIET=1: X/Y zero only, without going on to the Z zero (Studio does that as its own step).
- _CNC_WARMUP QUIET=1: the lid check first, then the same lift and ramp, without the Ready prompt; refused without a
  Z zero for the HotJoe (it lifts relative to the zero).
- _CNC_ADJUST_SPEED QUIET=1: the same ±5 %, without the Ready prompt.
Without FROM=STUDIO / QUIET=1 nothing changes.
"""
import difflib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = "# Studio CNC start wizard (docs/proposal-cnc-start.md)"
F = "guided/cnc_workflow.cfg"
Q = "params.QUIET|default(0)|int == 1"

CHANGES = [
    ("CNC_JOB_SETUP", "after", "variable_duty: 0.6",
     ["variable_studio_start: 1   " + NOTE + ": this config takes FROM=STUDIO"]),
    ("CNC_JOB_SETUP", "before", "  # Map file target pointer payload",
     ["  " + NOTE + ": FROM=STUDIO skips the prompts below, so it needs the zero and a running spindle first",
      '  {% set studio = params.FROM|default("")|upper == "STUDIO" %}',
      '  {% if studio and printer["gcode_macro SET_Z_ZERO"].zeroed != "HotJoe" %}',
      '    { action_raise_error("CNC_JOB_SETUP FROM=STUDIO: set the Z zero for the HotJoe first (SET_Z_ZERO). A tool change or a Klipper restart clears it.") }',
      "  {% endif %}",
      '  {% if studio and (printer["output_pin Spindle_power"].value|float < 0.5 or printer["output_pin SPINDLE_SPEED"].value|float <= 0.31) %}',
      '    { action_raise_error("CNC_JOB_SETUP FROM=STUDIO: the spindle isn\'t running. Warm it up first (_CNC_WARMUP).") }',
      "  {% endif %}"]),
    ("CNC_JOB_SETUP", "before", '  RESPOND TYPE=command MSG="action:prompt_begin CNC setup"',
     ["  {% if studio %}",
      "    " + NOTE + ": Studio's wizard showed the checklist, set the zeros and warmed the spindle up",
      "    _CNC_START",
      "  {% else %}"]),
    ("CNC_JOB_SETUP", "end", None, ["  {% endif %}"]),
    ("_CNC_SAVE_XY", "replace", ["  _CNC_ZERO_Z_CHOOSE"],
     ["  {% if not " + Q + " %}   " + NOTE + ": QUIET=1 stops here (Studio sets Z as its own step)",
      "  _CNC_ZERO_Z_CHOOSE",
      "  {% endif %}"]),
    ("_CNC_WARMUP", "after", "gcode:",
     ["  " + NOTE + ": QUIET=1 checks the lid first and leaves out the Ready prompt; it needs the HotJoe's Z zero",
      "  {% set quiet = " + Q + " %}",
      '  {% if quiet and printer["gcode_macro SET_Z_ZERO"].zeroed != "HotJoe" %}',
      '    { action_raise_error("_CNC_WARMUP QUIET=1: set the Z zero for the HotJoe first (SET_Z_ZERO).") }',
      "  {% endif %}",
      "  {% if quiet %}",
      "  _RHINO_INTERLOCKS",
      "  {% endif %}"]),
    ("_CNC_WARMUP", "replace", ["  _CNC_READY"], ["  {% if not quiet %}", "  _CNC_READY", "  {% endif %}"]),
    ("_CNC_ADJUST_SPEED", "replace", ["  _CNC_READY"],
     ["  {% if not " + Q + " %}   " + NOTE + ": QUIET=1 leaves out the Ready prompt", "  _CNC_READY", "  {% endif %}"]),
]


def _block(lines, macro):
    head = f"[gcode_macro {macro}]"
    starts = [i for i, l in enumerate(lines) if l.strip() == head]
    if len(starts) != 1:
        raise SystemExit(f"{macro}: found {len(starts)} definitions")
    i = starts[0]
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("[")), len(lines))
    while j > i and (not lines[j - 1].strip() or lines[j - 1].startswith("#")):
        j -= 1
    return i, j


def patched(text):
    if NOTE in text:
        raise SystemExit("already applied (the note is in the file): nothing to do")
    lines = text.split("\n")
    for macro, op, anchor, new in CHANGES:
        i, j = _block(lines, macro)
        if op == "end":
            lines[j:j] = new
            continue
        first = anchor[0] if op == "replace" else anchor
        hits = [k for k in range(i, j) if lines[k].rstrip() == first.rstrip()]
        if len(hits) != 1:
            raise SystemExit(f"{macro}: anchor {first!r} found {len(hits)} times")
        at = hits[0]
        if op == "replace":
            lines[at:at + len(anchor)] = new
        else:
            k = at + (1 if op == "after" else 0)
            lines[k:k] = new
    return "\n".join(lines)


def main(argv):
    to = argv[argv.index("--to") + 1] if "--to" in argv else None
    path = os.path.join(to or ROOT, F)
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    new = patched(old)
    if to or "--apply" in argv:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        return
    sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{F}", f"b/{F}", n=2))


if __name__ == "__main__":
    main(sys.argv[1:])
