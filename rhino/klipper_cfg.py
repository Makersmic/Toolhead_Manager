"""Read-only view of the Klipper config tree: which pins are taken, which tools are built in.

Follows [include] lines from printer.cfg the way Klipper does, so a stray .cfg that is not
included (an archive, a backup) never counts. The generated registry file is skipped on
purpose: the registry validates itself against everything *except* itself.
"""
import ast
import configparser
import glob
import json
import os
import re

from .errors import Fail
from .presets import CONTACT_KINDS, DEFAULT_CONTACTS, DEFAULT_UMBILICAL

_INCLUDE = re.compile(r"^\s*\[include\s+(.+?)\]\s*(?:[#;].*)?$")
_PIN = re.compile(r"^[A-Z]{1,2}[0-9]{1,2}$")
_SKIP_SECTIONS = ("gcode_macro", "delayed_gcode", "gcode_shell_command")
_EXTERNAL = ("mainsail", "klipper-toolchanger", "timelapse", "crowsnest")
# section types whose second word is an object name a new control must not reuse
_NAMED_OBJECTS = ("output_pin", "fan_generic", "heater_fan", "controller_fan", "temperature_fan", "servo",
                  "gcode_button", "led", "neopixel", "dotstar", "pwm_tool", "pwm_cycle_time", "heater_generic",
                  "temperature_sensor", "filament_switch_sensor", "filament_motion_sensor", "manual_stepper")
PIN_TYPES = {"logic": "Logic-level GPIO (3.3 V): any control, inputs too",
             "mosfet": "Switched power output (MOSFET): on/off, level and fans only - not inputs or servos",
             "": "Not described in umbilical.json"}


def _parser():
    cp = configparser.RawConfigParser(strict=False, inline_comment_prefixes=("#", ";"))
    cp.optionxform = str
    return cp


def _parse(path):
    cp = _parser()
    try:
        with open(path, encoding="utf-8") as f:
            cp.read_string(_strip_includes(f.read()), source=path)
    except (configparser.Error, UnicodeDecodeError, OSError):
        return None
    return cp


def _strip_includes(text):
    return "\n".join(l for l in text.splitlines() if not _INCLUDE.match(l))


class ConfigTree:
    """Parsed config. Build one per request - it is cheap and always current."""

    def __init__(self, paths, skip_generated=True):
        self.paths = paths
        self.files = []              # [(relative path, ConfigParser)]
        self.missing_includes = []   # include targets that matched nothing
        self._seen = set()
        skip = {os.path.abspath(paths.registry_cfg)} if skip_generated else set()
        self._walk(paths.printer_cfg, skip)
        self.aliases = self._aliases()
        self.macro_names, self.object_names, self.heaters = set(), {}, []
        self.claimed_pins, self.output_pins = self._scan()

    # ---- include graph -------------------------------------------------------------
    def _walk(self, path, skip):
        path = os.path.abspath(path)
        if path in self._seen or path in skip:
            return
        self._seen.add(path)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return
        base = os.path.dirname(path)
        for line in text.splitlines():
            m = _INCLUDE.match(line)
            if not m:
                continue
            pattern = m.group(1).strip()
            hits = sorted(glob.glob(os.path.join(base, pattern)))
            if not hits and not any(x in pattern for x in _EXTERNAL):
                self.missing_includes.append(pattern)
            for h in hits:
                self._walk(h, skip)
        cp = _parse(path)
        if cp is not None:
            self.files.append((os.path.relpath(path, self.paths.cfg), cp))

    # ---- pins ----------------------------------------------------------------------
    def _aliases(self):
        out = {}
        for _, cp in self.files:
            if cp.has_section("board_pins"):
                for line in cp.get("board_pins", "aliases", fallback="").replace("\n", ",").split(","):
                    if "=" in line:
                        a, p = (x.strip() for x in line.split("=", 1))
                        out[a.upper()] = p.upper()
        return out

    def resolve(self, pin):
        """'!EXP1_3' -> 'PE8'; returns '' if it is not a plain board pin."""
        pin = re.sub(r"^[!^~]+", "", (pin or "").strip()).upper()
        pin = self.aliases.get(pin, pin)
        return pin if _PIN.match(pin) else ""

    def _scan(self):
        claimed, outs = {}, {}
        for rel, cp in self.files:
            for sec in cp.sections():
                kind, _, rest = sec.partition(" ")
                rest = rest.strip()
                if kind == "gcode_macro" and rest:
                    self.macro_names.add(rest.upper())
                if kind in _NAMED_OBJECTS and rest:
                    self.object_names.setdefault(rest.lower(), f"{rel} [{sec}]")
                is_extruder = kind == "extruder" or (kind.startswith("extruder") and kind[8:].isdigit())
                if (is_extruder and not rest) or kind == "heater_bed":
                    self.heaters.append(kind)
                elif kind == "heater_generic" and rest:
                    self.heaters.append(rest)
                if sec.split(" ")[0] in _SKIP_SECTIONS or sec == "board_pins":
                    continue
                opts = dict(cp.items(sec))
                for key, val in opts.items():
                    if key == "pin" or key.endswith("_pin"):
                        pins = [val]
                    elif key.endswith("_pins"):
                        pins = val.split(",")
                    else:
                        continue
                    for raw in pins:
                        tok = raw.strip().split()[0] if raw.strip() else ""
                        p = self.resolve(tok)
                        if p:
                            claimed.setdefault(p, f"{rel} [{sec}]")
                if sec.startswith("output_pin "):
                    name = sec[len("output_pin "):].strip()
                    outs[name] = {"pwm": opts.get("pwm", "False").strip().lower() in ("true", "1", "yes"),
                                  "value": _num(opts.get("value", "0")),
                                  "cycle_time": _num(opts.get("cycle_time", "")),
                                  "pin": self.resolve(opts.get("pin", "")), "file": rel}
        return claimed, outs

    def umbilical_pins(self):
        """Pins wired to the tool connector. Edit myrhino/umbilical.json to change them."""
        return list(self.umbilical_info())

    def umbilical_info(self):
        """{pin: {"type": "logic"|"mosfet"|"", "label": str}} in connector order.

        umbilical.json "pins" may list plain names ("PB1") or objects
        ({"pin": "PB1", "type": "mosfet", "label": "FAN2 header, 24 V"}). The type lets the controls guide
        offer only pins that can do the job; a plain name means "not described" and is offered for anything."""
        p = self.paths.umbilical_json
        if not os.path.exists(p):
            return {x: {"type": "", "label": ""} for x in DEFAULT_UMBILICAL}
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            out = {}
            for item in (data["pins"] if isinstance(data, dict) else data):
                if isinstance(item, dict):
                    pin, typ, label = str(item["pin"]).upper(), str(item.get("type", "")).lower(), str(item.get("label", ""))
                else:
                    pin, typ, label = str(item).upper(), "", ""
                if not _PIN.match(pin) or typ not in PIN_TYPES:
                    raise ValueError(pin)
                out[pin] = {"type": typ, "label": label[:60]}
            return out
        except (OSError, ValueError, KeyError, TypeError):
            raise Fail(f"{p} is unreadable - expected \"pins\": a list of pin names like \"PB1\" or objects like "
                       f"{{\"pin\": \"PB1\", \"type\": \"logic\"}} (type is logic or mosfet)")

    def contacts(self):
        """The 21-pin connector: [{"contact", "pin", "label", "kind", "output", "pwm", "used_by"}] in order.

        Comes from umbilical.json "contacts" (if given) or the Rhino pin map. "output" is the [output_pin]
        in the config that drives the contact's board pin, so a tool can share it by contact number."""
        rows = [{"contact": c, "pin": p, "label": l, "kind": k} for c, p, l, k in DEFAULT_CONTACTS]
        path = self.paths.umbilical_json
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("contacts"):
                    rows = []
                    for item in data["contacts"]:
                        pin = str(item.get("pin") or "").upper()
                        kind = str(item.get("kind") or ("signal" if pin else "spare")).lower()
                        if (pin and not _PIN.match(pin)) or kind not in CONTACT_KINDS:
                            raise ValueError(item)
                        rows.append({"contact": int(item["contact"]), "pin": pin, "label": str(item.get("label", ""))[:60], "kind": kind})
            except (OSError, ValueError, KeyError, TypeError):
                raise Fail(f"{path}: \"contacts\" must be a list like {{\"contact\": 1, \"pin\": \"PA2\", \"label\": \"Hotend heater +\", "
                           f"\"kind\": \"switched\"}} (kind: {', '.join(CONTACT_KINDS)})")
        by_pin = {o["pin"]: (n, o) for n, o in self.output_pins.items() if o.get("pin")}
        for r in rows:
            n, o = by_pin.get(r["pin"], (None, None))
            r["output"], r["pwm"] = (n or ""), bool(o and o["pwm"])
            r["used_by"] = self.claimed_pins.get(r["pin"], "") if r["pin"] else ""
        return sorted(rows, key=lambda r: r["contact"])

    # ---- built-in tools ------------------------------------------------------------
    def builtin_tools(self):
        """-> (tool_mapping {slot:int -> name}, toolheads {name -> dict}) from [gcode_macro VARIABLES]."""
        for _, cp in self.files:
            if cp.has_section("gcode_macro VARIABLES"):
                sec = dict(cp.items("gcode_macro VARIABLES"))
                try:
                    mapping = ast.literal_eval(sec["variable_tool_mapping"].strip())
                    tools = ast.literal_eval(sec["variable_toolheads"].strip())
                    return {int(k): v for k, v in mapping.items()}, tools
                except (KeyError, ValueError, SyntaxError) as e:
                    raise Fail(f"cannot parse the tool tables in variables.cfg: {e}")
        raise Fail("cannot find [gcode_macro VARIABLES] in the included config files")


def _num(s):
    try:
        return float(str(s).strip())
    except ValueError:
        return None
