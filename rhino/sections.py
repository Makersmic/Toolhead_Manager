"""Klipper text for a tool's extra controls and macros - rendering only, no validation.

The portal preview, the generated custom_tools.cfg and the tests all call these functions, so what
the preview shows is byte-for-byte what is written. Input is assumed already validated (extras.py).
"""
import configparser


def macro_section(name, purpose, body, guard_slot=None, guard_tool="", owner=""):
    """[gcode_macro NAME] text. guard_slot: refuse to run unless that slot is mounted."""
    lines = [f"[gcode_macro {name}]"]
    if owner:
        lines.append(f"# {owner}")
    if purpose:
        lines.append(f"description: {purpose}")
    lines.append("gcode:")
    if guard_slot is not None:
        lines += [f'  {{% if printer["gcode_macro SWAP_TOOL"].current_tool|int != {int(guard_slot)} %}}',
                  f'    {{ action_raise_error("{name}: {guard_tool} is not mounted (slot {int(guard_slot)}). Swap tools first.") }}',
                  "  {% endif %}"]
    for ln in body.replace("\t", "    ").splitlines():
        if ln.strip():
            lines.append("  " + ln.rstrip())
    return lines


def pin_spec(c):
    """'^!PC1' - Klipper wants the pull-up mark before the invert mark."""
    return ("^" if c.get("pullup") else "") + ("!" if c.get("invert") else "") + c["pin"]


def control_section(tool_name, c, owner=None):
    """The one Klipper section a control (or a piece of system hardware) becomes."""
    role, n = c["role"], c["name"]
    head = (f"# {owner}" if owner else f"# control of toolhead {tool_name}") + (f": {c['purpose']}" if c.get("purpose") else "")
    if role in ("switch", "level"):
        keep_on = c.get("on_shutdown") == "on"
        lines = [f"[output_pin {n}]", head, f"pin: {pin_spec(c)}"]
        if role == "level":
            lines += ["pwm: True", f"cycle_time: {c['cycle']:g}"]
        lines += [f"value: {1 if role == 'switch' and c.get('start_on') else 0}",
                  f"shutdown_value: {1 if keep_on else 0}"]
        return lines
    if role == "fan":
        return [f"[fan_generic {n}]", head, f"pin: {pin_spec(c)}", f"max_power: {c['max_power']:g}",
                f"cycle_time: {c['cycle']:g}", f"kick_start_time: {c['kick_start']:g}",
                f"shutdown_speed: {1 if c.get('on_shutdown') == 'on' else 0}"]
    if role == "heater_fan":
        return [f"[heater_fan {n}]", head, f"pin: {pin_spec(c)}", f"heater: {c['heater']}",
                f"heater_temp: {c['heater_temp']:g}", f"max_power: {c['max_power']:g}"]
    if role == "servo":
        return [f"[servo {n}]", head, f"pin: {pin_spec(c)}", f"maximum_servo_angle: {c['max_angle']:g}",
                f"minimum_pulse_width: {c['min_pulse']:g}", f"maximum_pulse_width: {c['max_pulse']:g}"]
    if role == "input":
        lines = [f"[gcode_button {n}]", head, f"pin: {pin_spec(c)}", "press_gcode:"]
        lines += ["  " + l for l in _input_action(n, c.get("on_press", {}), "triggered")]
        lines.append("release_gcode:")
        lines += ["  " + l for l in _input_action(n, c.get("on_release", {}), "released")]
        return lines
    raise ValueError(role)


def _input_action(name, a, verb):
    kind = a.get("action", "none")
    msg = a.get("message") or f"{name} {verb}"
    if kind == "message":
        return [f'RESPOND MSG="{name}: {msg}"']
    if kind == "pause":
        return ['{% if printer.print_stats.state == "printing" %}',
                f'  RESPOND TYPE=error MSG="{name} {verb} - pausing the job"', "  PAUSE", "{% endif %}"]
    if kind == "estop":
        return ["M112"]
    if kind == "command":
        return [a["command"]]
    return ["{% if false %}{% endif %}"]     # gcode_button needs a template; this one does nothing


def control_off_lines(c):
    """Commands that make one control safe (used by _RHINO_CONTROLS_OFF and NAME_OFF)."""
    role, n = c["role"], c["name"]
    if role in ("switch", "level"):
        return [f"SET_PIN PIN={n} VALUE=0"]
    if role == "fan":
        return [f"SET_FAN_SPEED FAN={n} SPEED=0"]
    if role == "servo":
        return [f"SET_SERVO SERVO={n} WIDTH=0"]
    return []


def control_macros(tool_name, slot, c):
    """[(name, purpose, body, guard_slot)] for the 'make on/off macros' option.
    System hardware passes tool_name "" and slot None: no mounted-tool guard, purpose names the item."""
    if not c.get("make_macros"):
        return []
    role, n, up = c["role"], c["name"], c["name"].upper()
    guard = slot if c.get("mounted_only") and slot is not None else None
    tool_name = tool_name or (c.get("purpose") or n)
    off = (f"{up}_OFF", f"{tool_name}: {n} off", "\n".join(control_off_lines(c)), None)
    if role == "switch":
        return [(f"{up}_ON", f"{tool_name}: {n} on", f"SET_PIN PIN={n} VALUE=1", guard), off]
    if role == "level":
        body = ("{% set v = [[params.VALUE|default(1)|float, 0.0]|max, 1.0]|min %}\n"
                f"SET_PIN PIN={n} VALUE={{\"%.4f\"|format(v * {c['max_power']:g})}}")
        return [(f"{up}_SET", f"{tool_name}: {n} level VALUE=0..1 (1 = {c['max_power'] * 100:g}%)", body, guard), off]
    if role == "fan":
        body = ("{% set v = [[params.SPEED|default(1)|float, 0.0]|max, 1.0]|min %}\n"
                f"SET_FAN_SPEED FAN={n} SPEED={{v}}")
        return [(f"{up}_SET", f"{tool_name}: {n} speed SPEED=0..1", body, guard), off]
    if role == "servo":
        body = (f"{{% set a = [[params.ANGLE|default(0)|float, 0.0]|max, {c['max_angle']:g}]|min %}}\n"
                f"SET_SERVO SERVO={n} ANGLE={{a}}")
        return [(f"{up}_ANGLE", f"{tool_name}: move {n} ANGLE=0..{c['max_angle']:g}", body, guard),
                (f"{up}_OFF", f"{tool_name}: {n} stop holding", "\n".join(control_off_lines(c)), None)]
    return []


def tool_lines(name, tool):
    """Every extra section for one tool: controls, their macros, then the user's macros."""
    out = []
    for c in tool.get("controls", []):
        out += control_section(name, c) + [""]
        for mn, purpose, body, guard in control_macros(name, tool["slot"], c):
            out += macro_section(mn, purpose, body, guard, name, owner=f"made by control {c['name']} of {name}") + [""]
    for m in tool.get("macros", []):
        out += macro_section(m["name"], m.get("purpose", ""), m["body"],
                             tool["slot"] if m.get("mounted_only") else None, name, owner=f"macro of toolhead {name}") + [""]
    return out


def hardware_lines(reg):
    """System hardware: board pins that are not on the umbilical (enclosure fans, lights, pumps...)."""
    hw = reg.get("hardware", {})
    if not hw:
        return []
    out = ["# ---- system hardware (not on the tool connector) ----", ""]
    for n, c in sorted(hw.items()):
        out += control_section(n, c, owner=f"system hardware ({c.get('category_label') or c.get('category', '')})") + [""]
        for mn, purpose, body, guard in control_macros("", None, c):
            out += macro_section(mn, purpose, body, None, owner=f"made by system hardware {n}") + [""]
    return out


def safe_off_lines(reg):
    """_RHINO_CONTROLS_OFF: called by _TOOL_SAFE_OFF (end of job, cancel, swap, emergency stop)."""
    body = []
    for n, t in sorted(reg["tools"].items()):
        for c in t.get("controls", []):
            if c.get("safe_off"):
                body += [f"# {n}: {c['name']}"] + control_off_lines(c)
    for n, c in sorted(reg.get("hardware", {}).items()):
        if c.get("safe_off"):
            body += [f"# system hardware: {n}"] + control_off_lines(c)
    body = body or ["{% if false %}{% endif %}"]
    return (["[gcode_macro _RHINO_CONTROLS_OFF]",
             "description: Switch off every tool control marked 'off when made safe' (generated; called by _TOOL_SAFE_OFF)",
             "gcode:"] + ["  " + l for l in body] + [""])


def parse_like_klipper(text):
    """Parse config text exactly the way Klipper's configfile does (for previews and round-trips)."""
    cp = configparser.RawConfigParser(strict=False, inline_comment_prefixes=(";", "#"))
    cp.optionxform = str
    cp.read_string(text)
    return cp
