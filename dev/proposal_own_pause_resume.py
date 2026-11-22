#!/usr/bin/env python3
"""The Rhino writes its own PAUSE, RESUME and CANCEL_PRINT (docs/proposal-own-pause-resume.md).

    python3 dev/proposal_own_pause_resume.py            print what would change (changes nothing)
    python3 dev/proposal_own_pause_resume.py --apply    make the change (it refuses to run twice)

1. pause_resume.cfg is new: docs/pause_resume.cfg.draft moves to the config root (the draft is removed).
2. printer.cfg's first line: [include client_mainsail.cfg] becomes [include pause_resume.cfg].
3. client_macros.cfg loses the note about Mainsail's sections and the _CLIENT_VARIABLE hook table.
4. myrhino/positions.cfg's start-up step stops copying the park spot into _CLIENT_VARIABLE.
5. client_mainsail.cfg is deleted. Undo (rhino.sh option 4) brings it back with the rest of the old config folder.
Wording changes are made separately by hand. If any anchor isn't exactly as expected, the script stops and changes nothing."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
DRAFT, NEW, OLD = P("docs", "pause_resume.cfg.draft"), P("pause_resume.cfg"), P("client_mainsail.cfg")
PRINTER, MACROS, POSITIONS = P("printer.cfg"), P("client_macros.cfg"), P("myrhino", "positions.cfg")
INC_OLD, INC_NEW = "[include client_mainsail.cfg]", "[include pause_resume.cfg]"

MACROS_FROM = "# NOTE: [pause_resume], [display_status], and [respond] are commented"
MACROS_TO = "[gcode_macro _RHINO_CANCEL]"
MACROS_NEW = """# ---------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------
# CANCEL_PRINT (pause_resume.cfg) calls _RHINO_CANCEL after the heaters and the fan are off, and before Klipper's own
# cancel. PAUSE calls _RHINO_PAUSE_HOOK and RESUME calls _RHINO_RESUME_HOOK (both in tools/tool_power.cfg).

"""
POS_OLD = """# At start-up: Mainsail's own pause/cancel park reads _CLIENT_VARIABLE, so give it the park spot
# from above, then check every position against the travel limits (errors show in the console).
[delayed_gcode _RHINO_POSITIONS_APPLY]
initial_duration: 0.5
gcode:
  {% set p = printer["gcode_macro RHINO_POSITIONS"] %}
  SET_GCODE_VARIABLE MACRO=_CLIENT_VARIABLE VARIABLE=custom_park_x VALUE={p.park_x}
  SET_GCODE_VARIABLE MACRO=_CLIENT_VARIABLE VARIABLE=custom_park_y VALUE={p.park_y}
  RHINO_POSITIONS QUIET=1
"""
POS_NEW = """# At start-up: check every position against the travel limits (errors show in the console). Pause and cancel read
# the park spot above directly, so nothing is copied anywhere.
[delayed_gcode _RHINO_POSITIONS_APPLY]
initial_duration: 0.5
gcode:
  RHINO_POSITIONS QUIET=1
"""


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def plan():
    """-> {path: new text or None to delete}. Exits, changing nothing, if anything isn't as expected."""
    if os.path.exists(NEW):
        sys.exit("STOP: pause_resume.cfg is already there (already applied). Nothing changed.")
    for p in (DRAFT, OLD):
        if not os.path.isfile(p):
            sys.exit(f"STOP: {os.path.relpath(p, ROOT)} isn't there. Nothing changed.")
    lines = read(PRINTER).split("\n")
    if lines[0] != INC_OLD or sum(l.strip() in (INC_OLD, INC_NEW) for l in lines) != 1:
        sys.exit(f"STOP: printer.cfg's first line isn't {INC_OLD}, or it's included more than once. Nothing changed.")
    macros = read(MACROS)
    if macros.count(MACROS_FROM) != 1 or macros.count(MACROS_TO) != 1 or macros.index(MACROS_FROM) > macros.index(MACROS_TO) \
            or "[gcode_macro _CLIENT_VARIABLE]" not in macros[macros.index(MACROS_FROM):macros.index(MACROS_TO)]:
        sys.exit("STOP: client_macros.cfg isn't as expected (the Mainsail note and _CLIENT_VARIABLE, then _RHINO_CANCEL). Nothing changed.")
    pos = read(POSITIONS)
    if pos.count(POS_OLD) != 1:
        sys.exit("STOP: myrhino/positions.cfg's start-up step isn't as expected. Nothing changed.")
    a, b = macros.index(MACROS_FROM), macros.index(MACROS_TO)
    return {
        NEW: read(DRAFT),
        PRINTER: "\n".join([INC_NEW] + lines[1:]),
        MACROS: macros[:a] + MACROS_NEW + macros[b:],
        POSITIONS: pos.replace(POS_OLD, POS_NEW),
        DRAFT: None,
        OLD: None,
    }


def main():
    changes = plan()
    for path, text in changes.items():
        rel = os.path.relpath(path, ROOT)
        print(("delete " if text is None else "write  ") + rel)
    if "--apply" not in sys.argv:
        print("Dry run: nothing changed. Add --apply to write it.")
        return
    for path, text in changes.items():
        if text is None:
            os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
    print("Applied.")


if __name__ == "__main__":
    main()
