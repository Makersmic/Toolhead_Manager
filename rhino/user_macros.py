"""Your macros (1.9.13): short routines built from a list of steps in Rhino Studio. Design: docs/phase-macro-builder.md.

    myrhino/user_macros.json           {"schema": 1, "macros": [...]}
    myrhino/user_macros.history.json   revisions and deleted macros (rhino/versioned_store.py)

A macro: {id, name, toolheads: [] (empty = any), steps: [...], notes, created, updated, rev}, up to 30 steps.

The Portal only stores macros. It never runs one and never writes them into Klipper's config (Mike, Nov 7: Studio-only).
Studio turns the steps into G-code when you press the button and sends it through the console's own check and confirm.
This file still refuses anything a step must never hold, so a bad file can't reach the console even by hand:
- unknown step kinds or fields, numbers out of range, text with line breaks or control characters;
- calling an internal macro (a leading _) or one of the never-from-a-button commands below, in a macro step or the
  advanced G-code line.
"""
import re

from .errors import Fail
from .versioned_store import VersionedStore

MAX_MACROS = 100
MAX_STEPS = 30
_NAME = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")          # toolhead keys
_MACRO = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")    # a Klipper macro name, not an internal one
_TEXT = re.compile(r"^[^\x00-\x1f\"\\]{0,120}$")        # one line, no quotes: it goes inside RESPOND MSG="..."
_LINE = re.compile(r"^[^\x00-\x1f]{1,200}$")
# Never from a macro button, whatever the step (decisions.md, Oct 25 draft; Nov 7): stop, restarts, config writes,
# and position overrides that skip homing.
NEVER = ("M112", "SAVE_CONFIG", "FIRMWARE_RESTART", "RESTART", "SET_KINEMATIC_POSITION", "FORCE_MOVE", "SET_STEPPER_ENABLE")
_NEVER = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(NEVER) + r")(?![A-Za-z0-9_])", re.I)


def _num(v, lo, hi, what, blank=False):
    if v is None and blank:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
        raise Fail(f"{what} must be a number from {lo} to {hi}")
    return float(v) if isinstance(v, float) else v


def _bool(v, what):
    if not isinstance(v, bool):
        raise Fail(f"{what} must be yes or no")
    return v


def _only(step, keys, where):
    extra = set(step) - set(keys) - {"kind"}
    if extra:
        raise Fail(f"{where}: unknown field {sorted(extra)[0]}")


def _never(text, where):
    m = _NEVER.search(text)
    if m:
        raise Fail(f"{where}: {m.group(1).upper()} can't be run from a macro button")


def clean_step(st, where):
    if not isinstance(st, dict) or not isinstance(st.get("kind"), str):
        raise Fail(f"{where}: not a step")
    k = st["kind"]
    if k == "home":
        _only(st, ("axes", "onlyIfNeeded"), where)
        if st.get("axes") not in ("all", "xy", "z"):
            raise Fail(f"{where}: home all, XY or Z")
        return {"kind": k, "axes": st["axes"], "onlyIfNeeded": _bool(st.get("onlyIfNeeded", False), f"{where}: only if needed")}
    if k in ("moveTo", "moveBy"):
        axes = ("x", "y", "z") if k == "moveTo" else ("dx", "dy", "dz")
        _only(st, axes + ("speed",), where)
        lo, hi = (-2000, 2000) if k == "moveTo" else (-1000, 1000)
        out = {"kind": k, **{a: _num(st.get(a), lo, hi, f"{where}: {a.upper()}", blank=True) for a in axes}}
        if all(out[a] is None for a in axes):
            raise Fail(f"{where}: give at least one axis")
        out["speed"] = _num(st.get("speed"), 1, 500, f"{where}: speed (mm/s)")
        return out
    if k == "temp":
        _only(st, ("heater", "target", "wait"), where)
        if st.get("heater") not in ("hotend", "bed"):
            raise Fail(f"{where}: hotend or bed")
        top = 300 if st["heater"] == "hotend" else 130
        return {"kind": k, "heater": st["heater"], "target": _num(st.get("target"), 0, top, f"{where}: temperature"),
                "wait": _bool(st.get("wait", False), f"{where}: wait")}
    if k == "heatMaterial":
        _only(st, ("wait",), where)
        return {"kind": k, "wait": _bool(st.get("wait", True), f"{where}: wait")}
    if k == "fan":
        _only(st, ("percent",), where)
        return {"kind": k, "percent": _num(st.get("percent"), 0, 100, f"{where}: fan")}
    if k == "wait":
        _only(st, ("seconds",), where)
        return {"kind": k, "seconds": _num(st.get("seconds"), 0, 3600, f"{where}: seconds")}
    if k == "macro":
        _only(st, ("name",), where)
        n = st.get("name")
        if not isinstance(n, str) or not _MACRO.match(n):
            raise Fail(f"{where}: a Klipper macro's name (internal ones, starting with _, can't be called)")
        _never(n, where)
        return {"kind": k, "name": n.upper()}
    if k == "message":
        _only(st, ("text",), where)
        t = st.get("text")
        if not isinstance(t, str) or not _TEXT.match(t) or not t.strip():
            raise Fail(f"{where}: a message is one line of up to 120 characters, without quotes")
        return {"kind": k, "text": t.strip()}
    if k == "gcode":
        _only(st, ("line",), where)
        line = st.get("line")
        if not isinstance(line, str) or not _LINE.match(line) or not line.strip():
            raise Fail(f"{where}: one line of G-code, up to 200 characters")
        _never(line, where)
        return {"kind": k, "line": line.strip()}
    raise Fail(f"{where}: unknown step {k!r}")


def clean(raw, where="Macro"):
    if not isinstance(raw, dict):
        raise Fail(f"{where}: not a macro")
    extra = set(raw) - {"name", "toolheads", "steps", "notes", "id", "created", "updated", "rev"}
    if extra:
        raise Fail(f"{where}: unknown field {sorted(extra)[0]}")
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME.match(name.strip()):
        raise Fail(f"{where}: a name of 1 to 60 characters")
    name = name.strip()
    tools = raw.get("toolheads", [])
    if not isinstance(tools, list) or len(tools) > 20 or not all(isinstance(t, str) and _TOKEN.match(t) for t in tools):
        raise Fail(f"{name}: toolheads must be a list of toolhead names")
    steps = raw.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise Fail(f"{name}: 1 to {MAX_STEPS} steps")
    notes = raw.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 2000:
        raise Fail(f"{name}: notes must be text, up to 2000 characters")
    return {"name": name, "toolheads": sorted(set(tools)), "steps": [clean_step(s, f"{name}, step {i + 1}") for i, s in enumerate(steps)],
            "notes": notes}


class UserMacros(VersionedStore):
    NAME, KEY, PREFIX, NOUN, NOUNS, EXPORT_KEY = "user_macros", "macros", "m_", "macro", "macros", "rhino_user_macros"
    MAX = MAX_MACROS
    LIST_KEYS = ("id", "name", "toolheads", "steps", "notes", "created", "updated", "rev")
    DELETED_KEYS = ("id", "name", "deleted_at")
    EXPORT_FIELDS = ("name", "toolheads", "steps", "notes")

    def clean(self, raw):
        return clean(raw)
