#!/usr/bin/env python3
"""The macro change for the filament-change hook slot (docs/proposal-filament-change-hook.md).

    python3 dev/proposal_filament_hooks.py            print the unified diff (changes nothing)
    python3 dev/proposal_filament_hooks.py --apply    write it (DONE Nov 23, Mike's OK: a second run is refused)

Adds one call line to _FC_FINISH, after PURGE and before RESTORE_GCODE_STATE. Stops and changes nothing unless the
anchor is found exactly once inside that macro."""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_macro_hooks import patched  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = "guided/filament_change.cfg"
CHANGES = [(FILE, "_FC_FINISH", "after", "  PURGE TOOLHEAD=",
            ["  # job hooks (docs/proposal-filament-change-hook.md): after the purge, hot, at the swap spot, before the head goes back",
             "  _RHINO_HOOKS SLOT=after_filament_change TOOL={TOOLHEAD}"])]


def main(apply=False):
    path = os.path.join(ROOT, FILE)
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    if "SLOT=after_filament_change" in old:
        raise SystemExit("Already applied: running it again would add the call twice.")
    new = patched(old, CHANGES)
    sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{FILE}", f"b/{FILE}", n=2))
    if apply:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)


if __name__ == "__main__":
    main("--apply" in sys.argv)
