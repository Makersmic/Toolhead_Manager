"""Validate a tool's extra controls (pins with a job) and macros.

A control is described the way a person thinks about it ("switch it on and off", "signal comes from
the tool"); the guide's answers are stored as-is and sections.py turns them into the one Klipper
section that does that. Every name is checked against the live config AND the rest of the registry,
because Klipper refuses to start on a duplicate macro or object name.
"""
import re

from . import builders, sections
from .errors import Fail
from .presets import (COMMAND_RE, CONTROL_LIMITS, CONTROL_NAME_RE, CONTROL_ROLES, GCODE_WORD_RE, INPUT_ACTIONS,
                      KLIPPER_COMMANDS, MACRO_NAME_RE, MAX_CONTROLS, MAX_MACRO_LEN, MAX_MACRO_LINES, MAX_MACROS,
                      RISKY_COMMANDS)

try:                                     # Flask always brings Jinja2; the console path may not have it
    import jinja2
    _JENV = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])   # Klipper's delimiters
except ImportError:                      # pragma: no cover
    jinja2 = _JENV = None

_FIRST_WORD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def _flag(v):
    return v in (True, 1, "1", "true", "True", "on", "yes")


# ----------------------------------------------------------------------------- who owns which name
def taken_names(ctx, exclude_tool=None, exclude_hw=None):
    """-> (macros {UPPER: owner}, objects {lower: owner}) for everything except `exclude_tool`'s extras
    (or the system hardware item `exclude_hw`)."""
    macros = {n: "your Klipper config" for n in ctx.macro_names}
    macros.update({n: "a Klipper command" for n in KLIPPER_COMMANDS})
    macros.update({"CUSTOM_TOOLS": "the tool registry", "_RHINO_CONTROLS_OFF": "the tool registry"})
    objects = {n: owner for n, owner in ctx.object_names.items()}
    for n, hw in ctx.reg.get("hardware", {}).items():
        if n == exclude_hw:
            continue
        objects[n] = "system hardware"
        for mn, *_ in sections.control_macros("", None, hw):
            macros[mn] = f"system hardware {n}"
    for n, t in ctx.reg["tools"].items():
        for o in t.get("new_switch_pins", {}):
            objects[o.lower()] = f"toolhead {n}"
        for key in ("power_pin", "enable_pin"):
            if t.get(key) and t.get("owns_" + key):
                objects[t[key].lower()] = f"toolhead {n}"
        if n == exclude_tool:
            continue
        for c in t.get("controls", []):
            objects[c["name"]] = f"control of toolhead {n}"
            for mn, *_ in sections.control_macros(n, t["slot"], c):
                macros[mn] = f"control {c['name']} of toolhead {n}"
        for m in t.get("macros", []):
            macros[m["name"]] = f"toolhead {n}"
    return macros, objects


# ----------------------------------------------------------------------------- macros
def macro_name(raw, taken, mine):
    name = (raw or "").strip().upper()
    if not MACRO_NAME_RE.match(name):
        raise Fail("Macro name must start with a letter and use only letters, digits and _ (2 to 40 characters)")
    if GCODE_WORD_RE.match(name):
        raise Fail(f"{name} looks like a G-code word (G1, M3, T0...) - choose a descriptive name")
    if name in taken:
        case = (f" Klipper ignores letter case, so {raw.strip()} and {name} are the same name."
                if raw.strip() != name else "")
        raise Fail(f"A macro or command named {name} already exists ({taken[name]}).{case}")
    if name in mine:
        raise Fail(f"This tool already has a macro named {name}")
    return name


def macro_warnings(body, known):
    """Things that are legal but probably not meant: risky commands, unknown commands, cut-off comments."""
    out = []
    for i, ln in enumerate(body.splitlines(), 1):
        t = ln.strip()
        if not t or t[0] in "#;{":
            continue
        m = _FIRST_WORD.match(t)
        word = m.group(1).upper() if m else ""
        if word in RISKY_COMMANDS:
            out.append(f"Line {i}: {word} {RISKY_COMMANDS[word]}.")
        elif word and not re.fullmatch(r"[GMT][0-9]+", word) and word not in known:
            out.append(f"Line {i}: {word} is not a macro in your config or a Klipper command the portal knows - "
                       f"check the spelling (ignore this if a Klipper module provides it).")
        for mark in (" #", " ;", "\t#", "\t;"):
            if mark in ln and "{#" not in ln:
                out.append(f"Line {i}: Klipper treats everything after '{mark.strip()}' as a comment, so the rest "
                           f"of that line is dropped.")
                break
    return out


def check_jinja(name, section_text):
    """Parse the section as Klipper will, then compile its gcode template. Raises Fail with the line."""
    try:
        cp = sections.parse_like_klipper(section_text)
        sec = next(s for s in cp.sections() if s.startswith("gcode_macro "))
        gcode = cp.get(sec, "gcode")
    except Exception as e:
        raise Fail(f"{name}: the generated config would not parse ({e})")
    if _JENV is None:
        return
    try:
        _JENV.parse(gcode)
    except jinja2.TemplateSyntaxError as e:
        raise Fail(f"{name}: template error on line {e.lineno} of the generated gcode: {e.message}")


def clean_macro(ctx, tool_name, slot, raw, taken, mine, known):
    """-> (macro dict, warnings)."""
    name = macro_name(raw.get("name"), taken, mine)
    purpose = builders.text(raw.get("purpose"), f"{name} purpose", 120)
    body = str(raw.get("body") or "").replace("\r\n", "\n").replace("\t", "    ").strip("\n")
    if not body.strip():
        raise Fail(f"{name}: the macro has no commands")
    if len(body) > MAX_MACRO_LEN or len(body.splitlines()) > MAX_MACRO_LINES:
        raise Fail(f"{name}: the macro is too long (max {MAX_MACRO_LINES} lines / {MAX_MACRO_LEN} characters)")
    m = {"name": name, "purpose": purpose, "body": body, "mounted_only": _flag(raw.get("mounted_only"))}
    check_jinja(name, "\n".join(sections.macro_section(name, purpose, body, slot if m["mounted_only"] else None, tool_name)))
    return m, macro_warnings(body, known)


# ----------------------------------------------------------------------------- controls
def _num(raw, key, default, label):
    return builders.num(raw, key, *CONTROL_LIMITS[key], default=default, label=label)


def clean_control(ctx, tool_name, raw, objects, mine_objects, pins_here, hardware=False):
    """-> (control dict, warnings). pins_here: pins this tool already uses (power, enable, earlier controls).
    hardware=True: system hardware - a board pin off the umbilical, no mounted-tool guard."""
    warnings = []
    name = (raw.get("name") or "").strip().lower()
    if not CONTROL_NAME_RE.match(name):
        raise Fail("Control name must start with a letter and use only lower-case letters, digits and _ (2 to 32 characters)")
    if name in objects:
        raise Fail(f"The name {name} is already used by {objects[name]}")
    if name in mine_objects:
        raise Fail(f"This tool already has a control named {name}")
    role = (raw.get("role") or "").strip()
    if role not in CONTROL_ROLES:
        raise Fail(f"{name}: choose what the control does")
    c = {"name": name, "role": role, "purpose": builders.text(raw.get("purpose"), f"{name} purpose", 80)}

    if hardware:
        pin = builders.board_pin_any(ctx, raw.get("pin"), f"{name} pin", exclude_hw=raw.get("original") or None)
    else:
        pin = builders.board_pin(ctx, raw.get("pin"), f"{name} pin", exclude_tool=tool_name)
    if pin in pins_here:
        raise Fail(f"{name}: {pin} is already used by this tool")
    ptype = ctx.umbilical_info.get(pin, {}).get("type", "") if not hardware else ""
    if hardware and role in ("input", "servo") and pin in HEATER_HEADERS:
        raise Fail(f"{name}: {pin} is a heater / fan MOSFET output on the board - it cannot read a signal or drive a servo")
    if ptype == "mosfet" and role in ("input", "servo"):
        raise Fail(f"{name}: {pin} is a switched power output (MOSFET) - it cannot read a signal or drive a servo. "
                   f"Use a logic-level pin.")
    if ptype == "" and role in ("input", "servo") and not hardware:
        warnings.append(f"{name}: make sure {pin} is a plain logic pin, not a MOSFET power output "
                        f"(describe it in myrhino/umbilical.json and the portal checks this for you).")
    c.update(pin=pin, invert=_flag(raw.get("invert")))

    if role == "input":
        c["pullup"] = _flag(raw.get("pullup"))
        for key in ("on_press", "on_release"):
            a = raw.get(key) or {}
            act = a.get("action", "message" if key == "on_press" else "none")
            if act not in INPUT_ACTIONS:
                raise Fail(f"{name}: unknown action {act!r}")
            clean = {"action": act}
            if act == "message":
                clean["message"] = builders.text(a.get("message"), f"{name} message", 80)
            if act == "command":
                cmd = " ".join(str(a.get("command") or "").split())
                if not COMMAND_RE.match(cmd):
                    raise Fail(f"{name}: the command must be a macro or command name, optionally with KEY=VALUE "
                               f"parameters (letters, digits, _ . -)")
                clean["command"] = cmd
            c[key] = clean
        if c["on_press"]["action"] == "estop" or c["on_release"]["action"] == "estop":
            warnings.append(f"{name}: an emergency stop needs a FIRMWARE_RESTART to recover. Make sure the switch "
                            f"cannot trigger by accident.")
        return c, warnings

    c["on_shutdown"] = "on" if raw.get("on_shutdown") == "on" else "off"
    if c["on_shutdown"] == "on":
        warnings.append(f"{name} stays ON if Klipper shuts down or loses the board. Only choose this for "
                        f"things that are safe left running (cooling).")
    if role == "switch":
        c["start_on"] = _flag(raw.get("start_on"))
    if role in ("level", "fan"):
        c["cycle"] = _num(raw, "cycle", 0.01, f"{name} PWM cycle time")
        c["max_power"] = _num(raw, "max_power", 1.0, f"{name} maximum")
    if role == "fan":
        c["kick_start"] = _num(raw, "kick_start", 0.1, f"{name} kick-start time")
    if role == "heater_fan":
        heater = (raw.get("heater") or "").strip()
        if heater not in ctx.heaters:
            raise Fail(f"{name}: choose the heater it follows ({', '.join(ctx.heaters) or 'no heaters found'})")
        c.update(heater=heater, heater_temp=_num(raw, "heater_temp", 50.0, f"{name} turn-on temperature"),
                 max_power=_num(raw, "max_power", 1.0, f"{name} speed"))
        return c, warnings                    # Klipper runs it by itself: no macros, no safe-off
    if role == "servo":
        c.update(max_angle=_num(raw, "max_angle", 180.0, f"{name} maximum angle"),
                 min_pulse=_num(raw, "min_pulse", 0.001, f"{name} minimum pulse"),
                 max_pulse=_num(raw, "max_pulse", 0.002, f"{name} maximum pulse"))
        if c["min_pulse"] >= c["max_pulse"]:
            raise Fail(f"{name}: the minimum pulse width must be shorter than the maximum")
    c.update(safe_off=_flag(raw.get("safe_off", not hardware)), make_macros=_flag(raw.get("make_macros")),
             mounted_only=False if hardware else _flag(raw.get("mounted_only")))
    return c, warnings


HEATER_HEADERS = {"PA8", "PE5", "PD12", "PD13", "PD14", "PD15", "PA2", "PA3", "PB10", "PB11", "PA1"}


def clean_hardware(ctx, raw, categories):
    """-> (name, item, warnings) for one piece of system hardware (validated like a tool control)."""
    original = (raw.get("original") or "").strip().lower() or None
    taken_m, taken_o = taken_names(ctx, exclude_hw=original)
    c, w = clean_control(ctx, "", raw, taken_o, set(), set(), hardware=True)
    cat = raw.get("category")
    if cat not in categories:
        raise Fail(f"{c['name']}: choose a category")
    c["category"] = cat
    c["notes"] = builders.notes(raw.get("notes"))
    for mn, *_ in sections.control_macros("", None, c):
        if mn in taken_m:
            raise Fail(f"'Make macros' would create {mn}, but that name is used by {taken_m[mn]}")
    return c["name"], c, w


def hardware_preview(ctx, raw, categories):
    name, c, w = clean_hardware(ctx, raw, categories)
    lines = sections.control_section(name, c, owner=f"system hardware ({c['category']})") + [""]
    for mn, purpose, body, guard in sections.control_macros("", None, c):
        lines += sections.macro_section(mn, purpose, body, None, owner=f"made by system hardware {name}") + [""]
    if c.get("safe_off"):
        lines += ["# also switched off by _TOOL_SAFE_OFF (end of job, cancel, tool swap, emergency stop):"]
        lines += ["#   " + l for l in sections.control_off_lines(c)]
    return {"text": "\n".join(lines).rstrip() + "\n", "warnings": w, "item": c}


# ----------------------------------------------------------------------------- whole tool
def apply(ctx, name, tool, macros=None, controls=None):
    """Validate and set tool['controls'] / tool['macros'] (each only if given). Returns warnings."""
    warnings = []
    taken_m, taken_o = taken_names(ctx, exclude_tool=name)
    if controls is None:
        controls = tool.get("controls", [])
        revalidate_controls = False
    else:
        revalidate_controls = True
    if len(controls) > MAX_CONTROLS:
        raise Fail(f"At most {MAX_CONTROLS} controls per tool")
    pins_here = {p for p in (tool.get("new_pin"), tool.get("new_enable_pin")) if p}
    clean_c, mine_o, ctl_macros = [], set(), {}
    for raw in controls:
        if revalidate_controls:
            c, w = clean_control(ctx, name, raw, taken_o, mine_o, pins_here)
            warnings += w
        else:
            c = raw
        clean_c.append(c)
        mine_o.add(c["name"])
        pins_here.add(c["pin"])
        for mn, *_ in sections.control_macros(name, tool["slot"], c):
            if mn in taken_m:
                raise Fail(f"Control {c['name']} would make a macro {mn}, but that name is used by {taken_m[mn]}. "
                           f"Rename the control or untick 'make on/off macros'.")
            if mn in ctl_macros:
                raise Fail(f"Two controls would both make a macro named {mn}")
            ctl_macros[mn] = c["name"]
    tool["controls"] = clean_c

    if macros is not None:
        if len(macros) > MAX_MACROS:
            raise Fail(f"At most {MAX_MACROS} macros per tool")
        mine = dict(ctl_macros)
        known = set(taken_m) | set(ctl_macros) | {(m.get("name") or "").strip().upper() for m in macros}
        clean_m = []
        for raw in macros:
            m, w = clean_macro(ctx, name, tool["slot"], raw, taken_m, mine, known)
            mine[m["name"]] = name
            clean_m.append(m)
            warnings += [f"{m['name']}: {x}" for x in w]
        tool["macros"] = clean_m
    else:
        for m in tool.get("macros", []):
            if m["name"] in ctl_macros:
                raise Fail(f"Control {ctl_macros[m['name']]} would make a macro {m['name']}, which this tool already has")
        tool.setdefault("macros", [])
    return warnings


def preview(ctx, name, tool, kind, raw):
    """Text that would be written for one macro or control, plus warnings - nothing is saved.
    Raises Fail on an invalid entry (the message is shown under the editor)."""
    taken_m, taken_o = taken_names(ctx, exclude_tool=name)
    original = (raw.get("original") or "").strip()
    if kind == "macro":
        mine = {m["name"]: name for m in tool.get("macros", []) if m["name"] != original.upper()}
        for c in tool.get("controls", []):
            mine.update({mn: name for mn, *_ in sections.control_macros(name, tool["slot"], c)})
        known = set(taken_m) | set(mine) | {(raw.get("name") or "").strip().upper()}
        m, w = clean_macro(ctx, name, tool["slot"], raw, taken_m, mine, known)
        text = sections.macro_section(m["name"], m["purpose"], m["body"],
                                      tool["slot"] if m["mounted_only"] else None, name, owner=f"macro of toolhead {name}")
        return {"text": "\n".join(text) + "\n", "warnings": w, "item": m}
    others = [c for c in tool.get("controls", []) if c["name"] != original.lower()]
    pins_here = {p for p in (tool.get("new_pin"), tool.get("new_enable_pin")) if p} | {c["pin"] for c in others}
    c, w = clean_control(ctx, name, raw, taken_o, {c["name"] for c in others}, pins_here)
    lines = sections.control_section(name, c) + [""]
    for mn, purpose, body, guard in sections.control_macros(name, tool["slot"], c):
        if mn in taken_m:
            raise Fail(f"'Make macros' would create {mn}, but that name is used by {taken_m[mn]}")
        lines += sections.macro_section(mn, purpose, body, guard, name, owner=f"made by control {c['name']} of {name}") + [""]
    if c.get("safe_off"):
        lines += ["# also switched off by _TOOL_SAFE_OFF (end of job, cancel, tool swap, emergency stop):"]
        lines += ["#   " + l for l in sections.control_off_lines(c)]
    return {"text": "\n".join(lines).rstrip() + "\n", "warnings": w, "item": c}
