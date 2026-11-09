#!/usr/bin/env python3
"""The Rhino keeps its own PAUSE, RESUME and CANCEL_PRINT (docs/proposal-own-client-macros.md).

    python3 dev/proposal_own_client_macros.py            print what would change (changes nothing)
    python3 dev/proposal_own_client_macros.py --apply    make the change (DONE in 1.9.19; it refuses to run twice)

1. client_mainsail.cfg: a pinned copy of mainsail-config's client.cfg (GPL-3.0, (C) Alex Zellner). The copy is
   dev/fixtures/mainsail.cfg, byte for byte the machine's mainsail.cfg on Nov 9 2026
   (md5 0b6bf780f4dba4d0ca7294dd0f6b5d40), under a short Rhino header. No macro line is changed.
2. printer.cfg's first line: [include mainsail.cfg] becomes [include client_mainsail.cfg].
If either anchor isn't exactly as expected, the script stops and changes nothing."""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "dev", "fixtures", "mainsail.cfg")
PINNED = os.path.join(ROOT, "client_mainsail.cfg")
PRINTER = os.path.join(ROOT, "printer.cfg")
MD5 = "0b6bf780f4dba4d0ca7294dd0f6b5d40"
OLD, NEW = "[include mainsail.cfg]", "[include client_mainsail.cfg]"
# install.sh and the tests find the upstream text by this line: everything after it is the upstream file, unchanged.
BELOW = "# ---- mainsail-config client.cfg below, unchanged ----"
HEADER = f"""# Rhino: Mainsail's client macros, kept with the Rhino so Klipper doesn't need Mainsail installed.
#
# This is mainsail-config's client.cfg (https://github.com/mainsail-crew/mainsail-config), GPL-3.0,
# Copyright (C) 2022 Alex Zellner, copied unchanged: the same file the Rhino ran as mainsail.cfg until 1.9.19
# (md5 {MD5}). printer.cfg includes this file instead of mainsail.cfg; never include both.
#
# Don't edit it. The Rhino's own pause, resume and cancel steps are in client_macros.cfg (_CLIENT_VARIABLE and
# its hooks). Why and how: docs/proposal-own-client-macros.md.
{BELOW}
"""


def plan():
    body = open(SOURCE, "rb").read()
    if hashlib.md5(body).hexdigest() != MD5:
        sys.exit(f"STOP: {SOURCE} isn't the machine's copy (md5 {MD5}). Nothing changed.")
    if os.path.exists(PINNED):
        sys.exit("STOP: client_mainsail.cfg is already there (applied in 1.9.19). Nothing changed.")
    lines = open(PRINTER, encoding="utf-8").read().split("\n")
    if lines[0] != OLD or sum(l.strip() in (OLD, NEW) for l in lines) != 1:
        sys.exit(f"STOP: printer.cfg's first line isn't {OLD}, or it's included more than once. Nothing changed.")
    return HEADER.encode() + body, "\n".join([NEW] + lines[1:])


def main():
    pinned, printer = plan()
    print(f"new  client_mainsail.cfg  ({len(pinned)} bytes: Rhino header + the machine's mainsail.cfg, unchanged)")
    print(f"edit printer.cfg line 1:  {OLD}  ->  {NEW}")
    if "--apply" not in sys.argv:
        print("Dry run: nothing changed. Add --apply to write it.")
        return
    open(PINNED, "wb").write(pinned)
    open(PRINTER, "w", encoding="utf-8").write(printer)
    print("Applied.")


if __name__ == "__main__":
    main()
