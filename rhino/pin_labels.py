"""Pin labels (1.5.3): names for board pins, as Klipper pin aliases.

    [board_pins rhino]            generated into myrhino/custom_tools.cfg from custom_tools.json "labels"
    aliases:
        ENCLOSURE_LIGHT=PB5,
        DRYBOX_FAN=PA8

Any section can then say `pin: ENCLOSURE_LIGHT` (or `!ENCLOSURE_LIGHT`), and moving the light to another
pin is one change to the label. Klipper checks the aliases itself at the next restart; nothing here
restarts it. Aliases in your own [board_pins] sections (the EXP headers in printer.cfg, say) are shown
but never changed.

Two writes:
- save/remove a label: only the registry (and its generated file), the usual way (backup, round-trip check).
- use a label in a section: rewrites ONE `key: value` line in one of your config files, replacing the raw
  pin with the label (prefix like ! or ^ kept, comments kept). The file is copied to
  rhino_data/config_backups first, and re-read afterwards: if the section doesn't resolve to the same pin,
  the copy is put back.
"""
import datetime
import os
import re
import shutil

from .errors import Fail

ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
PIN_RE = re.compile(r"^[A-Z]{1,2}[0-9]{1,2}$")
MAX_LABELS = 60
KEEP_FILE_BACKUPS = 20


def clean_alias(raw):
    a = str(raw or "").strip().upper()
    if not ALIAS_RE.match(a):
        raise Fail("A label is 2-32 letters, digits and _, starting with a letter (like ENCLOSURE_LIGHT)")
    if PIN_RE.match(a):
        raise Fail(f"{a} looks like a pin name; pick a name that says what it is (like ENCLOSURE_LIGHT)")
    return a


def clean_pin(raw):
    p = str(raw or "").strip().upper()
    if not PIN_RE.match(p):
        raise Fail(f"{raw!r} isn't a board pin (like PB5)")
    return p


def check_label(ctx, tree, alias, pin, original=None):
    """Fail unless ALIAS=PIN can be added (or ORIGINAL changed to it). Returns warnings."""
    labels = ctx.reg.get("labels", {})
    warnings = []
    file_defs = {d["alias"]: d for d in tree.alias_defs}
    if alias in file_defs:
        d = file_defs[alias]
        raise Fail(f"{alias} is already an alias in {d['file']} [{d['section']}]")
    if alias != original and alias in labels:
        raise Fail(f"There's already a label called {alias}")
    if original and alias != original:
        users = uses_of(tree, original, ctx.reg)
        if users:
            raise Fail(f"{original} is used by {', '.join(u['where'] for u in users)} - a label in use can't be renamed")
    if not original and len(labels) >= MAX_LABELS:
        raise Fail(f"At most {MAX_LABELS} pin labels")
    # the pin: free, or used only through this very label
    mine = {u["where"] for u in uses_of(tree, original or alias, ctx.reg)}
    hw_users = [u for u in uses_of(tree, original or alias, ctx.reg) if u.get("hardware")]
    if hw_users and pin in set(ctx.umbilical) | {c["pin"] for c in ctx.contacts if c["pin"]}:
        raise Fail(f"{pin} is wired to the tool connector, and system hardware ({', '.join(u['hardware'] for u in hw_users)}) uses this label")
    owner = ctx.claimed.get(pin)
    if owner and owner not in mine:
        raise Fail(f"{pin} is already used by {owner}")
    from . import registry
    others_hw = {n: h for n, h in ctx.reg.get("hardware", {}).items() if h.get("pin_label") != (original or alias)}
    held = registry.pins_in_use({**ctx.reg, "hardware": others_hw, "labels": {a: q for a, q in labels.items() if a not in (alias, original)}})
    if pin in held:
        raise Fail(f"{pin} is kept for {held[pin]}")
    for a, q in list(labels.items()) + [(d["alias"], d["pin"]) for d in tree.alias_defs]:
        if q == pin and a not in (alias, original):
            warnings.append(f"{a} also names {pin}")
    if pin in ctx.umbilical:
        warnings.append(f"{pin} is wired to the tool connector")
    return warnings


def uses_of(tree, alias, reg=None):
    """Sections whose pin lines use ALIAS (and system hardware the Portal made with it, given the registry)."""
    if not alias:
        return []
    out = [{**u, "where": f"{u['file']} [{u['section']}]"} for u in tree.pin_uses if u["alias"] == alias.upper()]
    for n, hw in sorted(((reg or {}).get("hardware") or {}).items()):
        if hw.get("pin_label") == alias.upper():
            out.append({"where": f"system hardware {n}", "hardware": n})
    return out


def report(ctx, tree):
    """What Board pins shows: the Rhino labels (editable) and aliases in your own files (read-only),
    each with what uses it; and the pin lines that use a raw pin (they could use a label)."""
    rows = []
    for a, p in sorted(ctx.reg.get("labels", {}).items()):
        rows.append({"alias": a, "pin": p, "editable": True, "source": "Rhino labels",
                     "used_by": [u["where"] for u in uses_of(tree, a, ctx.reg)]})
    for d in tree.alias_defs:
        if not PIN_RE.match(d["pin"]):
            continue                                  # <GND>, <5V> and the like
        rows.append({"alias": d["alias"], "pin": d["pin"], "editable": False, "source": f"{d['file']} [{d['section']}]",
                     "used_by": [u["where"] for u in uses_of(tree, d["alias"])]})
    raw = [{"file": u["file"], "section": u["section"], "key": u["key"], "value": u["value"], "pin": u["pin"]}
           for u in tree.pin_uses if u["pin"] and not u["alias"]]
    return {"labels": rows, "raw_pin_lines": raw}


# ----------------------------------------------------------------------------- rewriting one line
_HEADER = re.compile(r"^\[([^\]]+)\]\s*([#;].*)?$")


def rewrite_pin_line(text, section, key, old_value, new_value):
    """Replace OLD_VALUE with NEW_VALUE on the `key:` line of [section]. Exactly one match or Fail.
    Keeps indentation, the separator, prefixes are the caller's business, and trailing comments."""
    lines = text.split("\n")
    in_sec, hits = False, []
    want = " ".join(section.split()).lower()
    kre = re.compile(rf"^(\s*{re.escape(key)}\s*[:=]\s*)(\S+)(.*)$", re.I)
    for i, line in enumerate(lines):
        h = _HEADER.match(line.strip()) if line[:1] == "[" else None
        if h:
            in_sec = " ".join(h.group(1).split()).lower() == want
            continue
        if in_sec:
            m = kre.match(line)
            if m and m.group(2) == old_value:
                hits.append((i, m))
    if len(hits) != 1:
        raise Fail(f"Couldn't find exactly one '{key}: {old_value}' line in [{section}] ({len(hits)} found) - change it by hand")
    i, m = hits[0]
    lines[i] = m.group(1) + new_value + m.group(3)
    return "\n".join(lines)


def backup_file(paths, rel):
    """Copy a config file into rhino_data/config_backups before it's changed; keep the newest 20."""
    src = os.path.join(paths.cfg, rel)
    d = os.path.join(paths.state_dir, "config_backups")
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, rel.replace("/", "__") + datetime.datetime.now().strftime(".%Y%m%d-%H%M%S-%f.cfg"))
    shutil.copy2(src, dest)
    for old in sorted(os.listdir(d))[:-KEEP_FILE_BACKUPS]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return dest


def safe_rel(paths, rel):
    """A config file path inside the config folder (no .., no absolute paths), that exists."""
    full = os.path.abspath(os.path.join(paths.cfg, rel or ""))
    if not rel or os.path.isabs(rel) or not full.startswith(os.path.abspath(paths.cfg) + os.sep) or not os.path.isfile(full):
        raise Fail(f"{rel!r} isn't a file in the config folder")
    if os.path.abspath(full) in (os.path.abspath(paths.registry_cfg),):
        raise Fail("The generated file can't be edited this way")
    return full
