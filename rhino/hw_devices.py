"""Add hardware wizard, steps 3 and 5: the writers for catalog devices that the six old roles don't cover.

A device lives in the registry under "devices" (the six role-based items stay under "hardware", unchanged):

    {"device": "heater", "label": ..., "pins": {"pin": "PB10", "sensor": "PF5"},
     "flags": {"pin": "^"}, "sensor_type": "thermistor", "settings": {...},
     "scope": "machine" | "category" | "tools", "scope_values": [...], "scope_slots": [...],
     "follows": "manual", "expose": [...], "safe_off": bool, "purpose": "...", "notes": "..."}

clean() validates one; lines() / off_lines() / macros() only render (the preview, the generated file and the
tests all call them, so the preview is what gets written). Nothing here changes an existing macro: the
interlock "must be closed to start" check, filament sensors off without a print head, and job hooks are
macro changes waiting for Mike's review (docs/proposal-macro-hooks.md)."""
import re

from . import builders, hw_boards, hw_catalog, sections
from .errors import Fail
from .presets import BUILTIN_CATEGORY, CATEGORIES, CONTROL_NAME_RE, KLIPPER_COMMANDS

MAX_DEVICES = 40
THERMISTORS = hw_catalog.SENSOR_TYPES["thermistor"]["kinds"]
COLOR_ORDERS = ["GRB", "RGB", "GRBW", "RGBW", "BRG"]
GCODE_FOLLOW = {"M7": "Mist (M7 on, M9 off)", "M8": "Flood or air (M8 on, M9 off)"}
# follows rules the writers can do today; "output" and "job" come with job hooks (macro review first)
FOLLOWS_BUILT = {"manual", "heater", "motors", "temperature", "gcode"}


# ----------------------------------------------------------------------------- settings, as data
# key: (kind, default, lo, hi) for numbers; ("choice", default, options) for choices; ("bool", default).
def _n(default, lo, hi):
    return ("num", default, lo, hi)


# Every fan: how many wires, the speed-signal pulses per turn, the PWM cycle and (4-wire) an inverted signal.
FAN_WIRING = {"wires": ("choice", "2", ["2", "3", "4"]), "tach_ppr": _n(2, 1, 12), "cycle": _n(0.01, 0.00005, 0.5),
              "signal_inverted": ("bool", False)}
FAN_DEVICES = {"fan", "hotend_fan", "controller_fan", "temperature_fan", "exhaust"}

SETTINGS = {
    "fan": {**FAN_WIRING, "max_power": _n(1.0, 0.1, 1.0), "kick_start": _n(0.5, 0.0, 5.0), "off_below": _n(0.0, 0.0, 0.9)},
    "hotend_fan": {**FAN_WIRING, "heater": ("choice", "extruder", ["extruder"]), "heater_temp": _n(50.0, 20.0, 300.0),
                   "fan_speed": _n(1.0, 0.1, 1.0), "kick_start": _n(0.5, 0.0, 5.0)},
    "controller_fan": {**FAN_WIRING, "fan_speed": _n(1.0, 0.1, 1.0), "idle_timeout": _n(hw_catalog.CONTROLLER_FAN_IDLE, 0, 3600),
                       "kick_start": _n(0.5, 0.0, 5.0)},
    "temperature_fan": {**FAN_WIRING, "target_temp": _n(40.0, 0.0, 100.0), "min_speed": _n(0.3, 0.0, 1.0), "max_speed": _n(1.0, 0.1, 1.0),
                        "kick_start": _n(0.5, 0.0, 5.0), "thermistor": ("choice", "Generic 3950", THERMISTORS),
                        "pullup_resistor": _n(4700, 100, 100000)},
    "heater": {"max_temp": _n(hw_catalog.HEATER_MAX_TEMP, 30.0, hw_catalog.HEATER_MAX_TEMP), "max_power": _n(1.0, 0.1, 1.0),
               "pwm_cycle_time": _n(0.3, 0.01, 1.0), "max_delta": _n(2.0, 0.5, 10.0),
               "thermistor": ("choice", "Generic 3950", THERMISTORS), "pullup_resistor": _n(4700, 100, 100000)},
    "temp_sensor": {"source": ("choice", "thermistor", ["thermistor", "host", "mcu"]),
                    "thermistor": ("choice", "Generic 3950", THERMISTORS), "pullup_resistor": _n(4700, 100, 100000)},
    "interlock": {"must_close_laser": ("bool", True), "must_close_spindle": ("bool", True)},
    "flame": {"required_for_laser": ("bool", False)},
    "pressure": {"must_be_ok": ("bool", False)},
    "vfd_fault": {},
    "spindle_relay": {"active_low": ("bool", False)},
    "spindle_pwm": {"cycle_time": _n(0.001, 0.00005, 0.1), "dir_active_low": ("bool", False), "enable_active_low": ("bool", False)},
    "pwm_tool": {"cycle_time": _n(0.001, 0.00005, 0.1)},
    "coolant": {"active_low": ("bool", False), "gcode": ("choice", "M8", list(GCODE_FOLLOW))},
    "air_assist": {"active_low": ("bool", False), "gcode": ("choice", "M8", list(GCODE_FOLLOW))},
    "dust": {"active_low": ("bool", False)},
    "vacuum_table": {"active_low": ("bool", False)},
    "fixed_output": {},
    "exhaust": {**FAN_WIRING, "max_power": _n(1.0, 0.1, 1.0), "kick_start": _n(0.5, 0.0, 5.0)},
    "led": {"cycle": _n(0.01, 0.00005, 0.5)},
    "neopixel": {"chain_count": _n(1, 1, 1024), "color_order": ("choice", "GRB", COLOR_ORDERS)},
    "dotstar": {"chain_count": _n(1, 1, 1024)},
    "runout": {"event_delay": _n(3.0, 0.5, 60.0)},
    "jam": {"detection_length": _n(7.0, 1.0, 100.0), "extruder": ("choice", "extruder", ["extruder"])},
    "manual_stepper": {"microsteps": ("choice", "16", ["1", "2", "4", "8", "16", "32", "64", "128", "256"]),
                       "rotation_distance": _n(40.0, 0.01, 1000.0), "velocity": _n(5.0, 0.1, 500.0),
                       "accel": _n(0.0, 0.0, 10000.0), "enable_active_low": ("bool", True)},
}
WRITERS = set(SETTINGS)          # the devices this module can write (the catalog shows these as ready)

# devices that can have generated ON / OFF (or SET) macros; the catalog's expose list is only the default
MACRO_DEVICES = {"spindle_relay", "coolant", "air_assist", "dust", "vacuum_table", "spindle_pwm", "pwm_tool", "exhaust", "fan",
                 "heater", "led", "neopixel", "dotstar"}
_SENSOR_INPUT_DEVICES = {"interlock", "flame", "pressure", "vfd_fault", "runout", "jam"}
_KLIPPER_RUNS_IT = {"controller_fan", "temperature_fan", "hotend_fan", "fixed_output", "runout", "jam"}   # nothing to switch off
_INPUT_ACTION = {"interlock": "pause", "flame": "estop", "pressure": "pause", "vfd_fault": "estop"}
_EXPECTED_SENSORS = {"interlock", "flame", "pressure", "vfd_fault", "runout", "jam", "manual_stepper"}


def _clean_settings(did, raw, ctx):
    out, spec = {}, dict(SETTINGS[did])
    if did == "jam":
        extruders = [h for h in ctx.heaters if h.startswith("extruder")] or ["extruder"]
        spec["extruder"] = ("choice", extruders[0], extruders)
    if did == "hotend_fan":
        heaters = list(ctx.heaters) or ["extruder"]
        spec["heater"] = ("choice", heaters[0], heaters)
    for key, s in spec.items():
        v = raw.get(key, s[1])
        if s[0] == "num":
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise Fail(f"{key.replace('_', ' ')}: a number")
            if not s[2] <= v <= s[3]:
                raise Fail(f"{key.replace('_', ' ')}: {s[2]:g} to {s[3]:g}")
            if isinstance(s[1], int) and float(v).is_integer():
                v = int(v)
        elif s[0] == "choice":
            if str(v) not in s[2]:
                raise Fail(f"{key.replace('_', ' ')}: one of {', '.join(s[2])}")
            v = str(v)
        else:
            v = v is True or str(v).lower() in ("1", "true", "yes", "on")
        out[key] = v
    if did == "temperature_fan" and out["min_speed"] > out["max_speed"]:
        raise Fail("The minimum speed can't be above the maximum")
    return out


# ----------------------------------------------------------------------------- validation
def taken(ctx, exclude=None):
    """-> (macros, objects) like extras.taken_names, plus every device and what it generates."""
    from . import extras
    return extras.taken_names(ctx, exclude_device=exclude)


def object_names(name, d):
    out = [name]
    if d["device"] == "spindle_pwm":
        out += [f"{name}_{p}" for p in ("direction", "enable") if d["pins"].get(p)]
    return out


def _scope(ctx, raw):
    scope = raw.get("scope") or "machine"
    if scope not in hw_catalog.SCOPES:
        raise Fail("Choose who it's for: the whole machine, a tool category or named tools")
    vals = [str(v) for v in (raw.get("scope_values") or [])]
    tools = ctx.all_tools
    if scope == "machine":
        return scope, [], []
    if scope == "category":
        if not vals or any(v not in CATEGORIES for v in vals):
            raise Fail(f"Choose a category: {', '.join(CATEGORIES.values())}")
        names = [n for n, t in tools.items() if (t.get("category") or BUILTIN_CATEGORY.get(t.get("type"))) in vals]
    else:
        bad = [v for v in vals if v not in tools]
        if not vals or bad:
            raise Fail(f"Choose the tools it's for{': no tool called ' + bad[0] if bad else ''}")
        names = vals
    slots = sorted(_slot_of(ctx, n) for n in names)
    return scope, vals, slots


def _slot_of(ctx, name):
    for s, n in ctx.builtin_map.items():
        if n == name:
            return int(s)
    return int(ctx.all_tools[name]["slot"])


def refresh_scope_slots(ctx):
    """Tools change category or come and go: recompute every device's mounted-tool slots before a save."""
    for d in ctx.reg.get("devices", {}).values():
        if d.get("scope", "machine") != "machine":
            try:
                d["scope_slots"] = _scope(ctx, d)[2]
            except Fail:
                d["scope_slots"] = []


def _pin(ctx, did, pname, kind, raw_ref, held, sensor_type, isolated, warnings):
    ref = ctx.resolve(str(raw_ref or "")) if ctx.resolve else ""
    if not ref:
        raise Fail(f"{pname}: {raw_ref!r} isn't a pin on the main board or an added board (like PB1 or ebb:PA1)")
    on_umb = set(ctx.umbilical) | {c["pin"] for c in ctx.contacts if c["pin"]}
    if ref in on_umb:
        raise Fail(f"{pname}: {ref} is wired to the tool connector; system hardware needs a board pin")
    used = ctx.claimed.get(ref) or held.get(ref)
    if used:
        raise Fail(f"{pname}: {ref} is already used by {used}")
    c = hw_boards.caps(ref, ctx.boards)
    ok, w = hw_boards.check_kind(kind, c)
    if not ok:
        raise Fail(f"{pname}: {w[0]}")
    warnings += w
    if sensor_type and kind == "digital_in":
        warnings += hw_boards.check_sensor(sensor_type, c, isolated)
    return ref


def clean(ctx, raw, held):
    """-> (name, item, warnings). held: {pin: owner} for pins the registry already uses (minus this item)."""
    did = raw.get("device")
    if did not in hw_catalog.DEVICES:
        raise Fail("Choose what it is")
    if did not in WRITERS:
        raise Fail(f"{hw_catalog.DEVICES[did]['label']}: not built yet")
    cat = hw_catalog.DEVICES[did]
    original = (raw.get("original") or "").strip().lower() or None
    name = (raw.get("name") or "").strip().lower()
    if not CONTROL_NAME_RE.match(name):
        raise Fail("Name: lower-case letters, digits and _, 2 to 32 characters, starting with a letter")
    macros_taken, objects_taken = taken(ctx, exclude=original)
    if name in objects_taken:
        raise Fail(f"The name {name} is already used by {objects_taken[name]}")
    if name in {n.lower() for n in ctx.all_tools}:
        raise Fail(f"{name} is the name of a toolhead")
    warnings = []

    sensor_type, isolated = None, bool(raw.get("isolated"))
    if did in _EXPECTED_SENSORS and any(k == "digital_in" for _, k, _ in cat["pins"]):
        sensor_type = raw.get("sensor_type") or "mech_nc"
        if sensor_type not in hw_catalog.SENSOR_TYPES or hw_catalog.SENSOR_TYPES[sensor_type]["pin_kind"] != "digital_in":
            raise Fail("Choose the switch or sensor type")

    settings = _clean_settings(did, raw, ctx)
    pins, flags, given = {}, {}, raw.get("pins") or {}
    for pname, kind, required in cat["pins"]:
        if did == "temp_sensor" and pname == "sensor":
            required = settings["source"] == "thermistor"
        when = cat["pin_when"].get(pname)
        if when and any(str(settings.get(k)) not in v for k, v in when.items()):
            continue                         # e.g. a tach pin on a 2-wire fan: not asked, never written
        if not given.get(pname):
            if required:
                raise Fail(f"Choose a pin for {pname}")
            continue
        if did == "temp_sensor" and settings["source"] != "thermistor":
            continue
        pins[pname] = _pin(ctx, did, pname, kind, given[pname], {**held, **{p: f"{name} ({k})" for k, p in pins.items()}},
                           sensor_type, isolated, warnings)
        if kind == "digital_in" and sensor_type:
            s = hw_catalog.SENSOR_TYPES[sensor_type]
            flags[pname] = ("^" if s.get("pullup") else "") + ("!" if s.get("invert") else "")
    if did == "led" and not pins:
        raise Fail("Choose at least one colour pin")
    for pname, key in (("pin", "active_low"), ("direction", "dir_active_low"), ("enable", "enable_active_low")):
        if pname in pins and settings.get(key):
            flags[pname] = "!"
    if did in FAN_DEVICES:
        if settings["wires"] == "4" and "pin" in pins:   # its speed input is meant to be a logic pin
            warnings = [w for w in warnings if "3.3 V logic pin" not in w]
        warnings += _fan_rules(ctx, settings, pins, flags)

    follows = raw.get("follows") or next((f for f in cat["follows"] if f in FOLLOWS_BUILT), cat["follows"][0])
    if follows not in cat["follows"]:
        raise Fail(f"{cat['label']} can't follow {hw_catalog.FOLLOWS.get(follows, follows)}")
    if follows not in FOLLOWS_BUILT:
        raise Fail(f"Following {hw_catalog.FOLLOWS[follows].lower()} comes with job hooks, which aren't built yet. "
                   f"Choose another rule for now.")
    scope, scope_values, scope_slots = _scope(ctx, raw)
    allowed = set(cat["expose"]) | ({"macros"} if did in MACRO_DEVICES else set()) | {"control", "dashboard"} & set(cat["expose"])
    expose = [e for e in (raw.get("expose") if raw.get("expose") is not None else cat["expose"]) if e in allowed]

    live = cat["live"]
    safe_off = True if live else bool(raw.get("safe_off", did not in ("led", "neopixel", "dotstar", "fixed_output")))
    if did in _KLIPPER_RUNS_IT:
        safe_off = False
    item = {"device": did, "label": cat["label"], "pins": pins, "flags": flags, "settings": settings,
            "scope": scope, "scope_values": scope_values, "scope_slots": scope_slots, "follows": follows,
            "expose": expose, "safe_off": safe_off, "purpose": builders.text(raw.get("purpose"), f"{name} purpose", 80),
            "notes": builders.notes(raw.get("notes"))}
    if sensor_type:
        item["sensor_type"] = sensor_type
        item["isolated"] = isolated

    if follows == "gcode":
        if any(m in ctx.macro_names for m in ("M7", "M8", "M9")):
            raise Fail("M7 / M8 / M9 are already defined in your config. Choose another rule, or remove those macros.")
    for mn, *_ in macros_of(name, item):
        if mn in macros_taken or mn in KLIPPER_COMMANDS:
            raise Fail(f"{name} would make a macro {mn}, but that name is used by {macros_taken.get(mn, 'Klipper')}")
    for o in object_names(name, item)[1:]:
        if o in objects_taken:
            raise Fail(f"{name} would add {o}, but that name is used by {objects_taken[o]}")

    if did == "heater":
        warnings.append(f"Capped at {settings['max_temp']:g} C: Klipper shuts down above it. Turned off by Turn off "
                        f"heaters, at the end of a job, on cancel and on a tool swap.")
    if did == "temperature_fan":
        warnings.append(f"Klipper shuts down if it passes {settings['target_temp'] + hw_catalog.TEMP_FAN_SHUTDOWN_MARGIN:g} C "
                        f"(target + {hw_catalog.TEMP_FAN_SHUTDOWN_MARGIN:g}).")
    if did in ("flame", "vfd_fault"):
        warnings.append("An emergency stop here is not a hardware E-stop: it waits in Klipper's queue. "
                        "A real E-stop must cut motor and spindle/laser power.")
    if did == "interlock":
        tools = [w for w, on in (("laser", settings["must_close_laser"]), ("spindle", settings["must_close_spindle"])) if on]
        warnings.append("Opening it pauses a running job." + (f" While it's open, {' and '.join(tools)} jobs won't start or "
                        f"resume." if tools else ""))
    if did in ("runout", "jam"):
        warnings.append("It's switched on only while a print head is mounted, so laser and CNC jobs never pause for it.")
    if did == "manual_stepper":
        warnings.append("Set up its driver (current, microsteps on a TMC) in your own config: the wizard writes the "
                        "motor, not the driver.")
    return name, item, warnings


def _fan_rules(ctx, s, pins, flags):
    """Electrical rules for 2/3/4-wire fans. Sets the tach pull-up and the signal inversion; returns warnings."""
    w, wires = [], s["wires"]
    if "tach" in pins:
        flags["tach"] = "^"                  # the speed signal is open collector: Klipper needs the pull-up
    if wires == "4":
        c = hw_boards.caps(pins["pin"], ctx.boards)
        if c["mosfet"]:
            raise Fail(f"{c['header'] or pins['pin']} is a MOSFET power output. A 4-wire fan's PWM wire needs a logic pin; "
                       f"its power comes from an always-on fan port, or from a MOSFET header chosen as its power pin.")
        if s["signal_inverted"]:
            flags["pin"] = "!"
        w.append("4-wire: power on the fan's red and black wires (an always-on port, or the power pin here), the "
                 "speed signal on its blue wire. Most fans read the PWM fine at Klipper's 10 ms; some run at full speed "
                 "until the signal is inverted (a transistor in between).")
        if "power" not in pins:
            w.append("With no power pin, many 4-wire fans keep turning slowly at 0% speed.")
    elif s["signal_inverted"]:
        raise Fail("Only a 4-wire fan's speed signal can be inverted")
    if wires == "3" and "tach" in pins:
        w.append("3-wire: the speed reading is only right at full speed. Below that the PWM cuts the fan's own power, "
                 "and its speed signal with it.")
    if s["cycle"] < 0.01:
        w.append("Klipper recommends a PWM cycle of 10 ms or more for fans (software PWM).")
    return w


def _fan_lines(d):
    """The options every fan section shares: cycle, speed signal, power (enable) pin."""
    s, out = d["settings"], []
    if s["cycle"] != 0.01:
        out.append(f"cycle_time: {s['cycle']:g}")
    if d["pins"].get("tach"):
        out.append(f"tachometer_pin: {_p(d, 'tach')}")
        if s["tach_ppr"] != 2:
            out.append(f"tachometer_ppr: {s['tach_ppr']:g}")
    if d["pins"].get("power"):
        out.append(f"enable_pin: {d['pins']['power']}")
    return out


# ----------------------------------------------------------------------------- rendering
def _p(d, pname):
    return d["flags"].get(pname, "") + d["pins"][pname]


def _thermistor(d):
    s = d["settings"]
    out = [f"sensor_type: {s['thermistor']}", f"sensor_pin: {d['pins']['sensor']}"]
    if s.get("pullup_resistor", 4700) != 4700:
        out.append(f"pullup_resistor: {s['pullup_resistor']:g}")
    return out


def lines(name, d):
    """The Klipper sections for one device (no trailing blank line)."""
    did, s = d["device"], d["settings"]
    head = f"# hardware ({d['label']})" + (f": {d['purpose']}" if d.get("purpose") else "")
    if did == "controller_fan":
        out = [f"[controller_fan {name}]", head, f"pin: {_p(d, 'pin')}", f"fan_speed: {s['fan_speed']:g}",
               f"idle_timeout: {s['idle_timeout']:g}", f"kick_start_time: {s['kick_start']:g}"] + _fan_lines(d)
    elif did == "hotend_fan":
        out = [f"[heater_fan {name}]", head, f"pin: {_p(d, 'pin')}", f"heater: {s['heater']}",
               f"heater_temp: {s['heater_temp']:g}", f"fan_speed: {s['fan_speed']:g}",
               f"kick_start_time: {s['kick_start']:g}"] + _fan_lines(d)
    elif did == "fan":
        out = [f"[fan_generic {name}]", head, f"pin: {_p(d, 'pin')}", f"max_power: {s['max_power']:g}",
               f"kick_start_time: {s['kick_start']:g}", "shutdown_speed: 0"] + _fan_lines(d)
        if s["off_below"]:
            out.append(f"off_below: {s['off_below']:g}")
    elif did == "temperature_fan":
        out = [f"[temperature_fan {name}]", head, f"pin: {_p(d, 'pin')}"] + _thermistor(d) + [
               "control: watermark", f"target_temp: {s['target_temp']:g}", "min_temp: 0",
               f"max_temp: {s['target_temp'] + hw_catalog.TEMP_FAN_SHUTDOWN_MARGIN:g}",
               f"min_speed: {s['min_speed']:g}", f"max_speed: {s['max_speed']:g}", f"kick_start_time: {s['kick_start']:g}",
               "shutdown_speed: 1"] + _fan_lines(d)
    elif did == "heater":
        out = [f"[heater_generic {name}]", head, f"heater_pin: {_p(d, 'pin')}"] + _thermistor(d) + [
               "control: watermark", f"max_delta: {s['max_delta']:g}", "min_temp: 0", f"max_temp: {s['max_temp']:g}",
               f"max_power: {s['max_power']:g}", f"pwm_cycle_time: {s['pwm_cycle_time']:g}"]
    elif did == "temp_sensor":
        out = [f"[temperature_sensor {name}]", head]
        if s["source"] == "thermistor":
            out += _thermistor(d)
        elif s["source"] == "host":
            out.append("sensor_type: temperature_host")
        else:
            out.append("sensor_type: temperature_mcu")
    elif did in _INPUT_ACTION:
        out = [f"[gcode_button {name}]", head, f"pin: {_p(d, 'pin')}", "press_gcode:"]
        out += ["  " + l for l in sections._input_action(name, {"action": _INPUT_ACTION[did]}, "triggered")]
        out += ["release_gcode:", "  " + f'RESPOND MSG="{name}: back to normal"']
    elif did in ("spindle_relay", "coolant", "air_assist", "dust", "vacuum_table"):
        out = [f"[output_pin {name}]", head, f"pin: {_p(d, 'pin')}", "value: 0", "shutdown_value: 0"]
    elif did in ("spindle_pwm", "pwm_tool"):
        out = [f"[pwm_tool {name}]", head, f"pin: {_p(d, 'pin')}", f"cycle_time: {s['cycle_time']:g}",
               "value: 0", "shutdown_value: 0"]
        for extra in ("direction", "enable"):
            if d["pins"].get(extra):
                out += ["", f"[output_pin {name}_{extra}]", f"# {extra} of {name}", f"pin: {_p(d, extra)}",
                        "value: 0", "shutdown_value: 0"]
    elif did == "fixed_output":
        out = [f"[static_digital_output {name}]", head, f"pins: {d['pins']['pins']}"]
    elif did == "exhaust":
        out = [f"[fan_generic {name}]", head, f"pin: {_p(d, 'pin')}", f"max_power: {s['max_power']:g}",
               f"kick_start_time: {s['kick_start']:g}", "shutdown_speed: 0"] + _fan_lines(d)
    elif did == "led":
        out = [f"[led {name}]", head] + [f"{c}_pin: {_p(d, c)}" for c in ("red", "green", "blue", "white") if c in d["pins"]]
        out.append(f"cycle_time: {s['cycle']:g}")
    elif did == "neopixel":
        out = [f"[neopixel {name}]", head, f"pin: {d['pins']['pin']}", f"chain_count: {s['chain_count']:g}",
               f"color_order: {s['color_order']}"]
    elif did == "dotstar":
        out = [f"[dotstar {name}]", head, f"data_pin: {d['pins']['data']}", f"clock_pin: {d['pins']['clock']}",
               f"chain_count: {s['chain_count']:g}"]
    elif did == "runout":
        out = [f"[filament_switch_sensor {name}]", head, f"switch_pin: {_p(d, 'pin')}", "pause_on_runout: True",
               f"event_delay: {s['event_delay']:g}"]
    elif did == "jam":
        out = [f"[filament_motion_sensor {name}]", head, f"switch_pin: {_p(d, 'pin')}",
               f"detection_length: {s['detection_length']:g}", f"extruder: {s['extruder']}", "pause_on_runout: True"]
    elif did == "manual_stepper":
        out = [f"[manual_stepper {name}]", head, f"step_pin: {d['pins']['step']}", f"dir_pin: {d['pins']['dir']}",
               f"enable_pin: {'!' if s['enable_active_low'] else ''}{d['pins']['enable']}", f"microsteps: {s['microsteps']}",
               f"rotation_distance: {s['rotation_distance']:g}", f"velocity: {s['velocity']:g}", f"accel: {s['accel']:g}"]
        if d["pins"].get("endstop"):
            out.append(f"endstop_pin: {_p(d, 'endstop')}")
    else:
        raise ValueError(did)
    return out


def off_lines(name, d):
    """Commands that make one device safe (for _RHINO_CONTROLS_OFF and NAME_OFF)."""
    did = d["device"]
    if did in ("spindle_relay", "coolant", "air_assist", "dust", "vacuum_table", "spindle_pwm", "pwm_tool"):
        out = [f"SET_PIN PIN={name} VALUE=0"]
        if did == "spindle_pwm":
            out += [f"SET_PIN PIN={name}_{x} VALUE=0" for x in ("enable", "direction") if d["pins"].get(x)]
        return out
    if did == "heater":
        return [f"SET_HEATER_TEMPERATURE HEATER={name} TARGET=0"]
    if did in ("exhaust", "fan"):
        return [f"SET_FAN_SPEED FAN={name} SPEED=0"]
    if did in ("led", "neopixel", "dotstar"):
        return [f"SET_LED LED={name} RED=0 GREEN=0 BLUE=0" + (" WHITE=0" if did != "dotstar" else "")]
    if did == "manual_stepper":
        return [f"MANUAL_STEPPER STEPPER={name} ENABLE=0"]
    return []


def _guard(name, d):
    slots = d.get("scope_slots") or []
    if d.get("scope", "machine") == "machine":
        return []
    return [f'{{% if printer["gcode_macro SWAP_TOOL"].current_tool|int not in {slots} %}}',
            f'  {{ action_raise_error("{name} is only for {", ".join(d.get("scope_values") or []) or "other tools"}. Swap tools first.") }}',
            "{% endif %}"]


def macros_of(name, d):
    """[(macro name, description, body lines)] when the device is exposed as ON / OFF macros."""
    if "macros" not in d.get("expose", []):
        return []
    did, up, s = d["device"], name.upper(), d["settings"]
    off = (f"{up}_OFF", f"{d['label']}: {name} off", off_lines(name, d))
    if did in ("spindle_relay", "coolant", "air_assist", "dust", "vacuum_table"):
        return [(f"{up}_ON", f"{d['label']}: {name} on", _guard(name, d) + [f"SET_PIN PIN={name} VALUE=1"]), off]
    if did in ("spindle_pwm", "pwm_tool"):
        body = _guard(name, d) + ["{% set v = [[params.VALUE|default(1)|float, 0.0]|max, 1.0]|min %}",
                                  f"SET_PIN PIN={name} VALUE={{v}}"]
        return [(f"{up}_SET", f"{d['label']}: {name} level VALUE=0..1", body), off]
    if did in ("exhaust", "fan"):
        return [(f"{up}_SET", f"{d['label']}: {name} speed SPEED=0..1",
                 _guard(name, d) + ["{% set v = [[params.SPEED|default(1)|float, 0.0]|max, 1.0]|min %}",
                                    f"SET_FAN_SPEED FAN={name} SPEED={{v}}"]), off]
    if did == "heater":
        body = _guard(name, d) + [f"{{% set t = [[params.TEMP|default(0)|float, 0.0]|max, {s['max_temp']:g}]|min %}}",
                                  f"SET_HEATER_TEMPERATURE HEATER={name} TARGET={{t}}"]
        return [(f"{up}_SET", f"{d['label']}: {name} target TEMP=0..{s['max_temp']:g}", body), off]
    if did in ("led", "neopixel", "dotstar"):
        return [(f"{up}_ON", f"{d['label']}: {name} on (full white)",
                 [f"SET_LED LED={name} RED=1 GREEN=1 BLUE=1" + (" WHITE=1" if did != "dotstar" else "")]), off]
    return []


def gcode_lines(reg):
    """M7 / M8 / M9 for devices that follow G-code. Only written when some device asks (and the config has none)."""
    devs = {n: d for n, d in reg.get("devices", {}).items() if d.get("follows") == "gcode"}
    if not devs:
        return []
    out = ["# ---- coolant / air G-code (made by hardware that follows G-code) ----", ""]
    for code, what in (("M7", "mist"), ("M8", "flood or air")):
        on = [n for n, d in sorted(devs.items()) if d["settings"].get("gcode") == code]
        if on:
            out += sections.macro_section(code, f"Coolant {what} on (generated)", "\n".join(f"SET_PIN PIN={n} VALUE=1" for n in on),
                                          owner="hardware that follows G-code") + [""]
    out += sections.macro_section("M9", "Coolant / air off (generated)",
                                  "\n".join(f"SET_PIN PIN={n} VALUE=0" for n in sorted(devs)), owner="hardware that follows G-code") + [""]
    return out


def device_lines(reg):
    devs = reg.get("devices", {})
    if not devs:
        return []
    out = ["# ---- hardware added in Rhino Studio ----", ""]
    for n, d in sorted(devs.items()):
        out += lines(n, d) + [""]
        for mn, desc, body in macros_of(n, d):
            out += sections.macro_section(mn, desc, "\n".join(body), owner=f"made by hardware {n}") + [""]
    return out + gcode_lines(reg)


def pins_of(d):
    return list(d["pins"].values())


def sections_of(name, d):
    """Section headers a device must produce (round-trip check)."""
    return [l[1:-1] for l in lines(name, d) if l.startswith("[")] + [f"gcode_macro {m}" for m, *_ in macros_of(name, d)]


# ----------------------------------------------------------------------------- macro changes awaiting review
# These two macros are rendered for docs/proposal-macro-hooks.md and the Portal preview only. Nothing calls them and
# they are not written to any .cfg until Mike approves the macro change (then: regenerated on every registry save).
_MOUNTED = ["  {% set _map = {} %}",
            "  {% set _ = _map.update(printer['gcode_macro VARIABLES'].tool_mapping) %}",
            "  {% set _ = _map.update(printer['gcode_macro CUSTOM_TOOLS'].tool_mapping|default({})) %}",
            "  {% set tool = params.TOOL|default(_map.get(printer['gcode_macro SWAP_TOOL'].current_tool|int, '')) %}"]


def interlock_macro(reg, laser_tools, spindle_tools):
    """_RHINO_INTERLOCKS: refuse a job (or a laser test fire) while a required input is triggered.
    laser_tools / spindle_tools: tool names, from the tool types and kinds at generation time."""
    checks = []
    for n, d in sorted(reg.get("devices", {}).items()):
        s, st = d["settings"], f'printer["gcode_button {n}"].state == "PRESSED"'
        groups = []
        if d["device"] == "interlock":
            if s.get("must_close_laser"):
                groups.append(("laser", laser_tools, f"{n} is open. Close it before starting the laser."))
            if s.get("must_close_spindle"):
                groups.append(("spindle", spindle_tools, f"{n} is open. Close it before starting the spindle."))
        elif d["device"] == "flame" and s.get("required_for_laser"):
            groups.append(("laser", laser_tools, f"{n} reads a flame. Check the machine before starting the laser."))
        elif d["device"] == "pressure" and s.get("must_be_ok"):
            groups.append(("any", None, f"{n} isn't OK (no air or coolant pressure)."))
        for _, tools, msg in groups:
            cond = st if tools is None else f"tool in {sorted(tools)} and {st}"
            checks += [f"  {{% if {cond} %}}", f'    {{ action_raise_error("{msg}") }}', "  {% endif %}"]
    body = _MOUNTED + (checks or ["  {% if false %}{% endif %}"])
    return ("[gcode_macro _RHINO_INTERLOCKS]\n"
            "description: Refuse to start while a door / lid interlock is open or a required sensor is triggered (generated). "
            "TOOL defaults to the mounted tool.\ngcode:\n" + "\n".join(body) + "\n")


def filament_macro(reg, print_tools):
    """_RHINO_FILAMENT_SENSORS: filament sensors on only while a print head is mounted (a laser job never pauses for runout)."""
    sensors = [n for n, d in sorted(reg.get("devices", {}).items()) if d["device"] in ("runout", "jam")]
    body = _MOUNTED + [f"  {{% set on = 1 if tool in {sorted(print_tools)} else 0 %}}"]
    body += [f"  SET_FILAMENT_SENSOR SENSOR={n} ENABLE={{on}}" for n in sensors] or ["  {% if false %}{% endif %}"]
    return ("[gcode_macro _RHINO_FILAMENT_SENSORS]\n"
            "description: Filament sensors on only with a print head mounted (generated). TOOL defaults to the mounted tool.\n"
            "gcode:\n" + "\n".join(body) + "\n")
