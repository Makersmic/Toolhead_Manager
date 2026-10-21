#!/usr/bin/env python3
"""Moonraker trusted_clients from the installer (1.5.4).

  rhino_trust.py ensure --conf ~/printer_data/config/moonraker.conf --backup-dir DIR [--moonraker URL] [--dry]

Adds what this Rhino needs to trusted_clients, only if [authorization] exists and the entry isn't covered yet:
127.0.0.0/8 (the Portal's own reads), this Rhino's LAN range(s), and 100.64.0.0/10 when Tailscale is up.
Prints one line per finding for install.sh. Exit 0 always unless the change itself failed (exit 1)."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rhino import trust                     # noqa: E402
from rhino.errors import Fail                # noqa: E402
from rhino.moonraker import Moonraker        # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ensure"])
    ap.add_argument("--conf", required=True)
    ap.add_argument("--backup-dir", required=True)
    ap.add_argument("--moonraker", default="http://127.0.0.1:7125")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.conf):
        print(f"note {a.conf} not found - trusted_clients left alone")
        return 0
    text = open(a.conf).read()
    info = trust.read(text)
    if not info["configured"]:
        print("ok   Moonraker has no [authorization]: it trusts every address, nothing to add")
        return 0
    if info["force_logins"]:
        print("note Moonraker has force_logins on: trusted_clients is ignored, so Mainsail and Studio need it off")
    want = [] if trust.covers(info["entries"], "127.0.0.1") else [(trust.LOOPBACK, "the Portal on this Rhino")]
    for net, why in trust.local_networks():
        sample = net.split("/")[0]
        if not trust.covers(info["entries"], sample) and net not in info["entries"]:
            want.append((net, why))
    if not want:
        print("ok   trusted_clients already covers this Rhino's networks")
        return 0
    for net, why in want:
        print(f"{'would add' if a.dry else 'add '} trusted_clients {net}  ({why})")
    if a.dry:
        return 0
    try:
        new = trust.add(text, [n for n, _ in want])
        trust.apply(a.conf, new, a.backup_dir, Moonraker(a.moonraker, timeout=5))
    except Fail as e:
        print(f"FAIL {e}")
        return 1
    print("ok   Moonraker restarted with the new trusted_clients")
    return 0


if __name__ == "__main__":
    sys.exit(main())
