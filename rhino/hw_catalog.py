"""Add hardware wizard: the catalog (step 1 of docs/hardware-coverage.md).

Everything the wizard can add is DATA here, not code: menu groups, devices, the pin kinds each device
needs, switch/sensor types and what they write, input purposes, scopes, "follows" rules and where an
item shows. Later steps read these tables; adding a device type means adding a row.

Status per device:
  ready    - Tool Manager can already write it (it maps onto an existing CONTROL_ROLES role)
  planned  - in the catalog so the wizard can show it, but its writer comes in a later build step;
             the wizard lists it as "coming" and the Portal refuses to save it until then.

Nothing here talks to Klipper or touches a file. check() verifies the tables agree with each other and
with presets.CONTROL_ROLES; dev/test_hw_catalog.py runs it."""
from . import presets

# ----------------------------------------------------------------------------- limits (decisions.md, 2026-10-26)
HEATER_MAX_TEMP = 120.0          # heater_generic cap (Mike)
TEMP_FAN_SHUTDOWN_MARGIN = 10.0  # temperature_fan max_temp default: target + this (Klipper shuts down above max_temp)
RUN_ON_DEFAULT = 10.0            # seconds a "follows another output" item keeps running after its leader stops
CONTROLLER_FAN_IDLE = 30         # controller_fan idle_timeout default (s)

# ----------------------------------------------------------------------------- menu groups, in menu order
GROUPS = [
    ("power", "Power and switching"),
    ("spindle", "Spindles"),
    ("air", "Coolant, air and dust"),
    ("fans", "Fans"),
    ("heat", "Heat and temperature"),
    ("lights", "Lights"),
    ("sensors", "Switches and sensors"),
    ("motion", "Movement"),
    ("measure", "Measuring"),
    ("boards", "Boards"),
    ("advanced", "Advanced"),
]

# ----------------------------------------------------------------------------- pin kinds
# What a device needs from a pin. The pin picker (step 2) shows only free pins that can do the kind.
PIN_KINDS = {
    "digital_in":  {"label": "Digital input", "help": "Switches, buttons, interlocks. Pull-up and invert are set from the sensor type."},
    "digital_out": {"label": "Digital output", "help": "Relays and plain on/off loads."},
    "pwm_out":     {"label": "PWM output", "help": "Fans, dimmers, laser and spindle speed. A MOSFET header drives a load; a logic pin drives a driver board."},
    "adc":         {"label": "Analog input (ADC)", "help": "Thermistors, analog pressure, pots. Only ADC-capable pins (on the Octopus: the T and TB headers)."},
    "spi_cs":      {"label": "SPI chip select", "help": "One free pin for CS, plus the SPI bus."},
    "i2c":         {"label": "I2C bus", "help": "A bus and an address; no single pin."},
    "data":        {"label": "One data line", "help": "Neopixel data. 5 V strips may need a level shifter."},
    "clock":       {"label": "Clock line", "help": "Dotstar clock, paired with a data line."},
    "step":        {"label": "Step", "help": "Stepper driver step pin."},
    "dir":         {"label": "Direction", "help": "Stepper driver direction pin."},
    "enable":      {"label": "Enable", "help": "Stepper driver enable pin."},
    "tach":        {"label": "Tach input", "help": "3- and 4-wire fan speed signal; needs a pull-up."},
}

# ----------------------------------------------------------------------------- switch and sensor types
# What the user picks instead of pull-ups and '!' flags. pullup -> '^', invert -> '!' in the written pin.
# refuse_direct: never wire straight to an MCU pin; the wizard asks the user to confirm an opto/divider is fitted.
SENSOR_TYPES = {
    "mech_nc":   {"label": "Mechanical, normally closed", "wires": 2, "pin_kind": "digital_in", "pullup": True, "invert": False,
                  "recommended": True, "note": "A broken wire reads as triggered, so it fails safe."},
    "mech_no":   {"label": "Mechanical, normally open", "wires": 2, "pin_kind": "digital_in", "pullup": True, "invert": True,
                  "note": "A broken wire is invisible: it just reads as not pressed."},
    "optical":   {"label": "Optical (slotted)", "wires": 3, "pin_kind": "digital_in", "pullup": False, "invert": False,
                  "ask_polarity": True, "warn": "Check the pin is 5 V tolerant if the sensor runs on 5 V."},
    "npn_no":    {"label": "Inductive / capacitive NPN, normally open", "wires": 3, "pin_kind": "digital_in", "pullup": True, "invert": True,
                  "warn": "These run on 6-36 V. Check the signal isn't at supply voltage before connecting."},
    "npn_nc":    {"label": "Inductive / capacitive NPN, normally closed", "wires": 3, "pin_kind": "digital_in", "pullup": True, "invert": False,
                  "warn": "These run on 6-36 V. Check the signal isn't at supply voltage before connecting."},
    "pnp":       {"label": "Inductive / capacitive PNP", "wires": 3, "pin_kind": "digital_in", "pullup": False, "invert": False,
                  "refuse_direct": True, "warn": "Outputs supply voltage. Needs an optocoupler or divider; confirm one is fitted."},
    "hall":      {"label": "Hall effect (open collector)", "wires": 3, "pin_kind": "digital_in", "pullup": True, "invert": True},
    "thermistor": {"label": "Thermistor", "wires": 2, "pin_kind": "adc",
                   "kinds": ["Generic 3950", "ATC Semitec 104GT-2", "ATC Semitec 104NT-4-R025H42G", "EPCOS 100K B57560G104F", "PT1000"]},
    "max31865":  {"label": "PT100 / PT1000 amplifier (MAX31865)", "pin_kind": "spi_cs", "asks": ["rtd_nominal_r", "rtd_reference_r", "rtd_num_of_wires"]},
    "thermocouple": {"label": "Thermocouple amplifier", "pin_kind": "spi_cs", "kinds": ["MAX31855", "MAX6675", "MAX31856"]},
    "i2c_temp":  {"label": "I2C temperature sensor", "pin_kind": "i2c", "kinds": ["BME280", "HTU21D", "SHT3X", "AHT10", "LM75"]},
    "ds18b20":   {"label": "DS18B20 (1-wire)", "pin_kind": None, "needs_host_mcu": True,
                  "warn": "Needs the host computer set up as a Klipper MCU; the wizard asks first."},
    "host_temp": {"label": "Host computer temperature", "pin_kind": None},
    "mcu_temp":  {"label": "Control board temperature", "pin_kind": None},
}

# ----------------------------------------------------------------------------- scope, follows, input purposes, exposure
SCOPES = {
    "machine": "Whole machine",
    "category": "A tool category (Additive / Subtractive / Passive)",
    "tools": "Named tools",
}
FOLLOWS = {
    "manual": "Nothing (manual)",
    "heater": "A heater (on above a temperature)",
    "motors": "The motors",
    "temperature": "A temperature (holds it)",
    "output": "Another output (with a run-on delay)",
    "job": "The job (job hooks)",
    "gcode": "G-code (M7 / M8 / M9)",
}
# purpose -> default action and extra rules (doc section 4). must_close_default: decisions.md 2026-10-26.
INPUT_PURPOSES = {
    "button":     {"label": "Button or pedal", "action": "command"},
    "interlock":  {"label": "Door or lid interlock", "action": "pause", "must_close_to_start": True,
                   "must_close_default_for": ["laser", "spindle"]},
    "flame":      {"label": "Flame sensor", "action": "estop", "can_require_for": ["laser"]},
    "pressure":   {"label": "Pressure or flow switch", "action": "pause", "optional_must_be_ok": True},
    "vfd_fault":  {"label": "VFD fault", "action": "estop"},
    "runout":     {"label": "Filament runout", "action": "pause", "print_head_only": True},
    "jam":        {"label": "Filament jam", "action": "pause", "print_head_only": True},
}
EXPOSE = {
    "control": "Control tab",
    "dashboard": "Dashboard",
    "care": "Care (count running hours)",
    "macros": "ON / OFF macros",
    "hooks": "Job hooks",
}
HOOK_SLOTS = ["before_start", "after_start", "before_end", "after_end", "on_cancel", "on_pause", "on_resume"]

# ----------------------------------------------------------------------------- devices
# pins: [(name, pin_kind, required)]. role: the existing CONTROL_ROLES key that writes it today (status ready).
# live: dangerous when on (spindle, laser, heater) -> behind the PadLock in the Control tab.
def _d(group, label, section, pins=(), *, role=None, status="planned", follows=("manual",), expose=("control",),
       sensor=False, purpose=None, live=False, hardware_only=False, help=""):
    return {"group": group, "label": label, "section": section, "pins": [list(p) for p in pins], "role": role,
            "status": status if role is None else "ready", "follows": list(follows), "expose": list(expose),
            "sensor": sensor, "purpose": purpose, "live": live, "hardware_only": hardware_only, "help": help}


DEVICES = {
    # power and switching
    "relay":        _d("power", "Relay or contactor", "output_pin", [("pin", "digital_out", True)], role="switch",
                       follows=("manual", "output", "job", "gcode"), expose=("control", "macros", "hooks", "care"),
                       help="Relay, solenoid, pump, light, valve: anything simply on or off."),
    "dimmer":       _d("power", "Dimmer or PWM level", "output_pin", [("pin", "pwm_out", True)], role="level",
                       follows=("manual", "output", "job"), expose=("control", "macros", "hooks")),
    "pwm_tool":     _d("power", "Move-synced power (laser-style)", "pwm_tool", [("pin", "pwm_out", True)], live=True,
                       help="Power that changes in step with moves."),
    "fixed_output": _d("power", "Fixed at boot", "static_digital_output", [("pins", "digital_out", True)], expose=(),
                       help="Set once at start-up; no control."),
    # spindles
    "spindle_relay": _d("spindle", "Spindle on a relay", "output_pin", [("pin", "digital_out", True)], live=True,
                        follows=("manual", "job"), expose=("control", "care", "hooks")),
    "spindle_pwm":  _d("spindle", "Spindle speed (PWM, or PWM to 0-10 V for a VFD)", "pwm_tool",
                       [("pin", "pwm_out", True), ("direction", "digital_out", False), ("enable", "digital_out", False)], live=True,
                       follows=("manual", "job"), expose=("control", "care", "hooks")),
    "vfd_fault":    _d("spindle", "VFD fault input", "gcode_button", [("pin", "digital_in", True)], sensor=True, purpose="vfd_fault",
                       expose=("dashboard",)),
    # coolant, air and dust
    "coolant":      _d("air", "Mist or flood coolant", "output_pin", [("pin", "digital_out", True)],
                       follows=("manual", "gcode", "job", "output"), expose=("control", "hooks")),
    "air_assist":   _d("air", "Air assist", "output_pin", [("pin", "digital_out", True)],
                       follows=("output", "job", "gcode", "manual"), expose=("control", "hooks")),
    "dust":         _d("air", "Dust collector or vacuum", "output_pin", [("pin", "digital_out", True)],
                       follows=("output", "job", "manual"), expose=("control", "hooks", "care")),
    "vacuum_table": _d("air", "Vacuum table", "output_pin", [("pin", "digital_out", True)],
                       follows=("job", "manual"), expose=("control", "hooks")),
    "exhaust":      _d("air", "Exhaust fan", "fan_generic", [("pin", "pwm_out", True)],
                       follows=("job", "output", "manual"), expose=("control", "hooks")),
    # fans
    "fan":          _d("fans", "Fan by speed", "fan_generic", [("pin", "pwm_out", True), ("tach", "tach", False)], role="fan",
                       expose=("control", "macros")),
    "hotend_fan":   _d("fans", "Hotend fan (on while a heater is hot)", "heater_fan", [("pin", "pwm_out", True)], role="heater_fan",
                       follows=("heater",), expose=()),
    "controller_fan": _d("fans", "Electronics / driver fan (on while the motors are on)", "controller_fan", [("pin", "pwm_out", True)],
                         follows=("motors",), expose=(), hardware_only=True),
    "temperature_fan": _d("fans", "Fan that holds a temperature", "temperature_fan",
                          [("pin", "pwm_out", True), ("sensor", "adc", True)], follows=("temperature",), expose=("dashboard",)),
    # heat and temperature
    "heater":       _d("heat", "Chamber / enclosure / generic heater", "heater_generic",
                       [("pin", "pwm_out", True), ("sensor", "adc", True)], live=True, expose=("control", "dashboard"),
                       hardware_only=True, help="Capped at 120 C. Turned off by idle timeout and Turn off heaters."),
    "temp_sensor":  _d("heat", "Temperature readout", "temperature_sensor", [("sensor", "adc", False)], expose=("dashboard",)),
    "thermistor_def": _d("heat", "Custom thermistor or analog sensor", "thermistor", expose=()),
    # lights
    "led":          _d("lights", "Plain LED (1-4 channels)", "led", [("red", "pwm_out", False), ("green", "pwm_out", False),
                                                                   ("blue", "pwm_out", False), ("white", "pwm_out", False)]),
    "neopixel":     _d("lights", "Addressable strip (Neopixel)", "neopixel", [("pin", "data", True)]),
    "dotstar":      _d("lights", "Addressable strip (Dotstar)", "dotstar", [("data", "data", True), ("clock", "clock", True)]),
    "led_chip":     _d("lights", "I2C LED chip (PCA9533 / PCA9632)", "pca9632", [("bus", "i2c", True)]),
    # switches and sensors
    "button":       _d("sensors", "Button or pedal", "gcode_button", [("pin", "digital_in", True)], role="input", sensor=True,
                       purpose="button", expose=("control",)),
    "interlock":    _d("sensors", "Door or lid interlock", "gcode_button", [("pin", "digital_in", True)], sensor=True,
                       purpose="interlock", expose=("dashboard",)),
    "flame":        _d("sensors", "Flame sensor", "gcode_button", [("pin", "digital_in", True)], sensor=True, purpose="flame",
                       expose=("dashboard",)),
    "pressure":     _d("sensors", "Pressure or flow switch", "gcode_button", [("pin", "digital_in", True)], sensor=True,
                       purpose="pressure", expose=("dashboard",)),
    "runout":       _d("sensors", "Filament runout", "filament_switch_sensor", [("pin", "digital_in", True)], sensor=True,
                       purpose="runout", expose=("dashboard",)),
    "jam":          _d("sensors", "Filament jam (motion)", "filament_motion_sensor", [("pin", "digital_in", True)], sensor=True,
                       purpose="jam", expose=("dashboard",)),
    "width_hall":   _d("sensors", "Filament width (hall)", "hall_filament_width_sensor", [("adc1", "adc", True), ("adc2", "adc", True)]),
    "width_tsl":    _d("sensors", "Filament width (TSL1401CL)", "tsl1401cl_filament_width_sensor", [("sensor", "adc", True)]),
    # movement
    "servo":        _d("motion", "Servo", "servo", [("pin", "pwm_out", True)], role="servo", expose=("control", "macros")),
    "manual_stepper": _d("motion", "Extra motor (gate, feeder, rotary)", "manual_stepper",
                         [("step", "step", True), ("dir", "dir", True), ("enable", "enable", True), ("endstop", "digital_in", False)]),
    # measuring
    "accelerometer": _d("measure", "Accelerometer (for input shaping)", "adxl345", [("cs", "spi_cs", True)], expose=(),
                        help="Also adds resonance_tester. Chips: ADXL345, LIS2DW, LIS3DH, MPU9250, ICM20948, BMI160."),
    "angle":        _d("measure", "Angle sensor", "angle", [("cs", "spi_cs", True)], expose=()),
    "load_cell":    _d("measure", "Load cell", "load_cell", expose=("dashboard",)),
    "analog_in":    _d("measure", "Analog input", "adc_scaled", [("vref", "adc", True), ("vssa", "adc", True)], expose=()),
    # boards (decisions.md 2026-10-26: second board is in this job, step 2)
    "board":        _d("boards", "Second control board", "mcu", expose=(), hardware_only=True,
                       help="Adds [mcu <name>]; its pins then appear in every pin picker."),
    # advanced
    "multi_pin":    _d("advanced", "Several pins as one (multi_pin)", "multi_pin", expose=()),
    "pin_override": _d("advanced", "Share a pin (duplicate_pin_override)", "duplicate_pin_override", expose=()),
    "expander":     _d("advanced", "GPIO expander (SX1509)", "sx1509", [("bus", "i2c", True)], expose=()),
    "adc_chip":     _d("advanced", "ADC chip (ADS1x1x)", "ads1x1x", [("bus", "i2c", True)], expose=()),
    "digipot":      _d("advanced", "Digital potentiometer", "mcp4451", expose=(),
                       help="AD5206, MCP4451, MCP4728, MCP4018."),
    "sercom":       _d("advanced", "SAMD SERCOM bus", "samd_sercom", expose=()),
}

# Klipper sections the catalog may write (from Klipper's Config_Reference.md, checked Oct 2026).
KLIPPER_SECTIONS = {
    "output_pin", "pwm_tool", "static_digital_output", "multi_pin", "duplicate_pin_override", "fan_generic", "heater_fan",
    "controller_fan", "temperature_fan", "heater_generic", "temperature_sensor", "thermistor", "adc_temperature", "led",
    "neopixel", "dotstar", "pca9533", "pca9632", "gcode_button", "filament_switch_sensor", "filament_motion_sensor",
    "hall_filament_width_sensor", "tsl1401cl_filament_width_sensor", "servo", "manual_stepper", "adxl345", "lis2dw",
    "lis3dh", "mpu9250", "icm20948", "bmi160", "resonance_tester", "angle", "load_cell", "adc_scaled", "ads1x1x",
    "sx1509", "ad5206", "mcp4451", "mcp4728", "mcp4018", "samd_sercom", "mcu",
}


def check():
    """-> list of problems; empty means the tables agree with each other and with presets.CONTROL_ROLES."""
    out, groups = [], {g for g, _ in GROUPS}
    for did, d in DEVICES.items():
        if d["group"] not in groups:
            out.append(f"{did}: unknown group {d['group']}")
        if d["section"] not in KLIPPER_SECTIONS:
            out.append(f"{did}: {d['section']} is not a Klipper section the catalog may write")
        for name, kind, _req in d["pins"]:
            if kind not in PIN_KINDS:
                out.append(f"{did}: pin {name} has unknown kind {kind}")
        if d["role"] is not None:
            if d["role"] not in presets.CONTROL_ROLES:
                out.append(f"{did}: role {d['role']} is not in presets.CONTROL_ROLES")
            elif presets.CONTROL_ROLES[d["role"]]["section"] != d["section"]:
                out.append(f"{did}: role {d['role']} writes {presets.CONTROL_ROLES[d['role']]['section']}, not {d['section']}")
        for f in d["follows"]:
            if f not in FOLLOWS:
                out.append(f"{did}: unknown follows {f}")
        for e in d["expose"]:
            if e not in EXPOSE:
                out.append(f"{did}: unknown exposure {e}")
        if d["purpose"] is not None and d["purpose"] not in INPUT_PURPOSES:
            out.append(f"{did}: unknown purpose {d['purpose']}")
        if d["sensor"] and d["purpose"] is None:
            out.append(f"{did}: a sensor needs a purpose")
    for sid, s in SENSOR_TYPES.items():
        if s["pin_kind"] is not None and s["pin_kind"] not in PIN_KINDS:
            out.append(f"sensor {sid}: unknown pin kind {s['pin_kind']}")
    for p in INPUT_PURPOSES.values():
        if p["action"] not in presets.INPUT_ACTIONS:
            out.append(f"purpose {p['label']}: action {p['action']} is not in presets.INPUT_ACTIONS")
    covered = {d["role"] for d in DEVICES.values() if d["role"]}
    for role in presets.CONTROL_ROLES:
        if role not in covered:
            out.append(f"role {role} has no device in the catalog")
    return out


def for_ui():
    """The whole catalog as JSON-safe data, menu-ordered, for Studio's wizard."""
    from .hw_devices import FOLLOWS_BUILT, MACRO_DEVICES, SETTINGS, WRITERS   # steps 3 and 5

    def settings(did):
        out = []
        for key, spec in SETTINGS.get(did, {}).items():
            row = {"key": key, "kind": spec[0], "default": spec[1]}
            if spec[0] == "num":
                row.update(min=spec[2], max=spec[3])
            elif spec[0] == "choice":
                row["options"] = list(spec[2])
            out.append(row)
        return out

    def row(did, d):
        r = dict(d, id=did, status="ready" if (d["role"] or did in WRITERS) else "planned")
        if did in WRITERS:            # a role device keeps the system hardware form; these use the wizard
            r.update(writer="wizard", settings=settings(did),
                     expose_allowed=sorted(set(d["expose"]) | ({"macros"} if did in MACRO_DEVICES else set())))
        elif d["role"]:
            r["writer"] = "form"
        return r
    groups = [{"id": g, "label": label, "devices": [row(did, d) for did, d in DEVICES.items() if d["group"] == g]}
              for g, label in GROUPS]
    return {"groups": groups, "pin_kinds": PIN_KINDS, "sensor_types": SENSOR_TYPES, "scopes": SCOPES,
            "follows": FOLLOWS, "follows_built": sorted(FOLLOWS_BUILT), "input_purposes": INPUT_PURPOSES, "expose": EXPOSE, "hook_slots": HOOK_SLOTS,
            "limits": {"heater_max_temp": HEATER_MAX_TEMP, "temp_fan_margin": TEMP_FAN_SHUTDOWN_MARGIN,
                       "run_on": RUN_ON_DEFAULT, "controller_fan_idle": CONTROLLER_FAN_IDLE}}
