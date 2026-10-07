"""Changes that are saved but not yet live (Klipper loads them at its next restart).

Kept in rhino_data/restart_pending as JSON so the portal banner can say WHAT is waiting, and
shared by the portal and the console commands (both mark it; a restart from either clears it).

    {"since": 1727800000.0, "changes": ["added Needle", "edited FoamWire: power_cap"],
     "auto_restart": false, "note": ""}

An empty file (written by older versions) still counts as "something is waiting".
"""
import json
import os
import time

MAX_CHANGES = 30


def _read(paths):
    p = paths.restart_flag
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read().strip()
        d = json.loads(text) if text else {}
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    d.setdefault("since", os.path.getmtime(p))
    d.setdefault("changes", [])
    d.setdefault("auto_restart", False)
    d.setdefault("note", "")
    return d


def _write(paths, d):
    os.makedirs(paths.state_dir, exist_ok=True)
    tmp = paths.restart_flag + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, paths.restart_flag)


def get(paths):
    """The pending record, or None when nothing is waiting."""
    return _read(paths)


def mark(paths, change):
    d = _read(paths) or {"since": time.time(), "changes": [], "auto_restart": False, "note": ""}
    if change and change not in d["changes"]:
        d["changes"] = (d["changes"] + [change])[-MAX_CHANGES:]
    d["note"] = ""
    _write(paths, d)
    return d


def set_auto_restart(paths, on):
    d = _read(paths)
    if d is None:
        return None
    d["auto_restart"], d["note"] = bool(on), ""
    _write(paths, d)
    return d


def set_note(paths, note, auto_restart=None):
    d = _read(paths)
    if d is None:
        return None
    d["note"] = note
    if auto_restart is not None:
        d["auto_restart"] = auto_restart
    _write(paths, d)
    return d


def clear(paths):
    try:
        os.remove(paths.restart_flag)
    except FileNotFoundError:
        pass
