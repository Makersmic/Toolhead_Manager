#!/usr/bin/env python3
"""The macro change for job hooks, interlocks and filament sensors (docs/proposal-macro-hooks.md).

    python3 dev/proposal_macro_hooks.py            print the unified diff (changes nothing)
    python3 dev/proposal_macro_hooks.py --apply    write it into the config files (only after Mike's OK)

Every insertion names its file, its macro and an anchor line inside that macro; if an anchor isn't found exactly
once the script stops and changes nothing. Adds calls only: no existing line is edited or removed."""
import difflib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = "# job hooks / interlocks (docs/proposal-macro-hooks.md)"

# (file, macro, where, anchor, lines). where: "before" / "after" the anchor line, or "end" of the macro.
CHANGES = [
    ("myrhino/TOOLHEAD_DISPATCH.cfg", "START_JOB", "before", "  # Secure verification cleared, proceed with job movements safely",
     ["  " + NOTE + ": checks first, then the before-start hook. Nothing has moved yet.",
      "  _RHINO_INTERLOCKS TOOL={requested_toolhead}",
      "  _RHINO_HOOKS SLOT=before_start TOOL={requested_toolhead}", ""]),
    ("guided/laser_workflow.cfg", "LASER_JOB_SETUP", "before", "  SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file",
     ["  " + NOTE, "  _RHINO_INTERLOCKS", "  _RHINO_HOOKS SLOT=before_start"]),
    ("guided/cnc_workflow.cfg", "CNC_JOB_SETUP", "before", "  SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file",
     ["  " + NOTE, "  _RHINO_INTERLOCKS", "  _RHINO_HOOKS SLOT=before_start"]),
    ("guided/dragknife_workflow.cfg", "DRAGKNIFE_JOB_SETUP", "before", "  SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file",
     ["  " + NOTE, "  _RHINO_INTERLOCKS", "  _RHINO_HOOKS SLOT=before_start"]),
    ("guided/generic_workflow.cfg", "TOOL_JOB_SETUP", "before", "  SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file",
     ["  " + NOTE, "  _RHINO_INTERLOCKS", "  _RHINO_HOOKS SLOT=before_start"]),
    ("guided/laser_workflow.cfg", "_LASER_TEST_FIRE", "after", "gcode:",
     ["  " + NOTE + ": no test fire with the lid open", "  _RHINO_INTERLOCKS"]),
    ("myrhino/TOOLHEAD_DISPATCH.cfg", "_START_JOB_FILE", "after", "    M117 Job already running",
     ["    {% if printer.print_stats.state == \"printing\" %}", "      " + NOTE, "      _RHINO_INTERLOCKS",
      "      _RHINO_HOOKS SLOT=after_start", "    {% endif %}"]),
    ("myrhino/TOOLHEAD_DISPATCH.cfg", "_START_JOB_FILE", "before", "    SDCARD_PRINT_FILE FILENAME=",
     ["    " + NOTE + ": last gate before the file runs (a lid opened during setup is caught here)",
      "    _RHINO_INTERLOCKS", "    _RHINO_HOOKS SLOT=after_start"]),
    ("myrhino/TOOLHEAD_DISPATCH.cfg", "END_PRINT", "after", "  {% set tool_type = _th.get(TOOLHEAD, {}).get(\"type\", \"DEPOSITION\") %}",
     ["  " + NOTE, "  _RHINO_HOOKS SLOT=before_end TOOL={TOOLHEAD}"]),
    ("myrhino/TOOLHEAD_DISPATCH.cfg", "END_PRINT", "before", "  # 👉 DESIGNER AUTOMATED BACKUP TRIGGER (ADDED HERE)",
     ["  " + NOTE + ": after the Rhino's end sequence, before the backup", "  _RHINO_HOOKS SLOT=after_end TOOL={TOOLHEAD}",
      "  # ===================================================================="]),
    ("client_macros.cfg", "_RHINO_CANCEL", "end", None,
     ["    " + NOTE + ": last, so a failing hook can't stop the Rhino's own cancel (tool power is already off)",
      "    _RHINO_HOOKS SLOT=on_cancel"]),
    ("tools/tool_power.cfg", "_RHINO_PAUSE_HOOK", "end", None,
     ["  " + NOTE, "  _RHINO_HOOKS SLOT=on_pause"]),
    ("tools/tool_power.cfg", "_RHINO_RESUME_HOOK", "end", None,
     ["  " + NOTE + ": print heads resume here (non-print tools were refused above)", "  _RHINO_INTERLOCKS",
      "  _RHINO_HOOKS SLOT=on_resume"]),
    ("tools/tool_power.cfg", "TOOL_RESUME", "before", "    # 1. Travel above the paused spot at the current (lifted) height.",
     ["    " + NOTE + ": lid closed and hooks back on BEFORE the spindle or laser comes back", "    _RHINO_INTERLOCKS",
      "    _RHINO_HOOKS SLOT=on_resume", ""]),
    ("toolchanger.cfg", "CONFIRM_TOOL_INSTALL", "end", None,
     ["  " + NOTE + ": filament sensors only with a print head", "  _RHINO_FILAMENT_SENSORS"]),
    ("toolchanger.cfg", "RESTORE_TOOL", "end", None,
     ["  " + NOTE + ": filament sensors only with a print head", "  _RHINO_FILAMENT_SENSORS"]),
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
    lines = text.split("\n")
    for _f, macro, where, anchor, new in file_changes:
        i, j = _block(lines, macro)
        if where == "end":
            at = j
        else:
            hits = [k for k in range(i, j) if lines[k].startswith(anchor)]
            if len(hits) != 1:
                raise SystemExit(f"{macro}: anchor {anchor!r} found {len(hits)} times")
            at = hits[0] + (1 if where == "after" else 0)
        lines[at:at] = new
    return "\n".join(lines)


def main(apply=False):
    by_file = {}
    for ch in CHANGES:
        by_file.setdefault(ch[0], []).append(ch)
    out = {}
    for f, chs in by_file.items():
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            old = fh.read()
        out[f] = (old, patched(old, chs))
    for f, (old, new) in out.items():
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{f}", f"b/{f}", n=2))
    if apply:
        for f, (_old, new) in out.items():
            with open(os.path.join(ROOT, f), "w", encoding="utf-8") as fh:
                fh.write(new)


if __name__ == "__main__":
    main("--apply" in sys.argv)
