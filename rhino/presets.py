"""Tool kinds, starting values and limits. Change defaults here - nothing else hard-codes them.

Starting values are placeholders to be tuned on the real machine (EDIT in the portal)."""
import re

FIRST_CUSTOM_SLOT = 6  # built-in tools occupy slots 1-5

# kind -> tool type the Klipper macros dispatch on
KINDS = {"HOT_WIRE": "POWERED", "NEEDLE": "POWERED", "POWERED": "POWERED",
         "PASSIVE": "PASSIVE", "PRINT_HEAD": "DEPOSITION"}
KIND_LABELS = {"HOT_WIRE": "Hot wire foam cutter", "NEEDLE": "Needle / vibrating knife",
               "POWERED": "Other powered tool", "PASSIVE": "Passive tool (pen, blade, probe)",
               "PRINT_HEAD": "3D-print head (clone of an existing one)"}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,23}$")
MAT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
PIN_RE = re.compile(r"^[A-Za-z]{1,2}[0-9]{1,2}$")
# Text that ends up inside a Klipper config value. No # ; * (Klipper treats them as comments)
# and no quotes or braces (they would break the value or the Jinja that reads it).
SAFE_TEXT = re.compile(r"^[A-Za-z0-9 _.,:!?()/+-]*$")
SAFE_TEXT_HELP = "letters, digits, spaces and _ . , : ! ? ( ) / + -"

POWER_PRESETS = {
    "HOT_WIRE": {"cap": 0.5, "max_on_s": 600,
                 "materials": {"FOAM_EPS": {"power": 0.40, "feed_rate": 300},
                               "FOAM_XPS": {"power": 0.50, "feed_rate": 250}},
                 "checklist": ["Wire installed, taut and clear of the stock",
                               "Foam is clamped flat and cannot shift",
                               "Ventilation running - foam fumes",
                               "Fire extinguisher or water nearby and you stay present"]},
    "NEEDLE": {"cap": 1.0, "max_on_s": 900,
               "materials": {"FOAM": {"power": 0.60, "feed_rate": 600},
                             "FABRIC": {"power": 0.40, "feed_rate": 500}},
               "checklist": ["Needle or blade is firmly seated", "Material is clamped flat",
                             "Hands and cables clear of the cutting path"]},
    "POWERED": {"cap": 1.0, "max_on_s": 300,
                "materials": {"DEFAULT": {"power": 0.50, "feed_rate": 600}},
                "checklist": ["Tool is securely mounted and its cable is clear of the gantry",
                              "Work is clamped and the area is clear"]},
}
PASSIVE_PRESET = {"materials": {"DEFAULT": {"feed_rate": 800}},
                  "checklist": ["Tool is securely mounted", "Work is clamped and the area is clear"]}

# fields every material carries (the dispatch macros read these)
MATERIAL_COMMON = {"bed_temp": 0, "z_offset": 0.0, "square_corner_velocity": 5.0,
                   "stepper_x_current": 0.7, "stepper_y_current": 0.7, "stepper_z_current": 0.8}
ACCEL = {"POWERED": 800.0, "PASSIVE": 1000.0}

# fields kept in the JSON registry but never written to the Klipper config
PORTAL_ONLY_FIELDS = ("notes", "outputs", "contacts", "category")
# fields written to the Klipper config as their OWN sections (not inside variable_toolheads)
SECTION_FIELDS = ("macros", "controls")
EPHEMERAL_FIELDS = ("slot", "new_pin", "new_pin_cycle", "new_enable_pin", "new_switch_pins")
SCHEMA_VERSION = 1

# Pins that physically reach the tool umbilical connector (override in myrhino/umbilical.json).
# A pin only offered to new tools if it is ALSO not claimed anywhere in the Klipper config.
DEFAULT_UMBILICAL = ["PE0", "PE1", "PE2", "PE3", "PF4", "PB0", "PB1", "PC0", "PC1"]

# Output channels the built-in tools already use. Shown in the pin picker so sharing is a
# conscious choice (e.g. SERVO_LASER is both the laser intensity and the SwitchFly path servo).
SHARED_CHANNELS = {"Umbilical_LED": "umbilical LED strip data line (not a power output!)","SERVO_LASER": "LightSaber laser intensity / SwitchFly path servo",
                   "LASER_INITIALIZE": "LightSaber laser power rail",
                   "Spindle_power": "HotJoe spindle relay",
                   "SPINDLE_SPEED": "HotJoe spindle ESC (idles at 0.3 = neutral)"}

DEPOSITION_KEY_RE = re.compile(r"^[A-Za-z0-9]+_[0-9]+_[0-9]+(_T[0-9]+)?$")  # PLA_0_4, PETG_0_8_T2

LIMITS = {"cap": (0.05, 1.0), "min": (0.0, 1.0), "idle": (0.0, 1.0), "max_on_s": (1, 3600),
          "s_max": (1, 1000000), "feed_rate": (1, 100000), "z_offset": (-50.0, 50.0),
          "power": (0.0, 1.0), "cycle": (0.00005, 0.1), "nozzle": (0.1, 2.0)}
# per-material numeric fields users may edit, by tool type: key -> (low, high)
_COMMON_MAT = {"z_offset": (-50.0, 50.0), "accel": (50.0, 20000.0),
               "square_corner_velocity": (0.0, 50.0), "stepper_x_current": (0.1, 3.0),
               "stepper_y_current": (0.1, 3.0), "stepper_z_current": (0.1, 3.0), "bed_temp": (0, 130)}
MATERIAL_FIELDS = {"POWERED": {**_COMMON_MAT, "power": (0.0, 1.0), "feed_rate": (1, 100000)},
                   "PASSIVE": {**_COMMON_MAT, "feed_rate": (1, 100000)},
                   "DEPOSITION": {**_COMMON_MAT, "extruder_temp": (0, 300), "fan_speed": (0.0, 1.0),
                                  "extruder_current": (0.1, 3.0)}}
MAX_CHECKLIST_ITEMS, MAX_CHECKLIST_LEN, MAX_NOTES_LEN = 12, 120, 1000


# ----------------------------------------------------------------------------- macros + controls
MACRO_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
GCODE_WORD_RE = re.compile(r"^[GMT][0-9]+$")          # G1, M3, T0: never usable as a macro name
CONTROL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MAX_MACROS, MAX_MACRO_LEN, MAX_MACRO_LINES, MAX_CONTROLS = 30, 8000, 300, 12
# Klipper's own commands (core + the modules this config uses). A macro with one of these names would
# replace the command - Klipper refuses that unless rename_existing is used, so the portal refuses it.
KLIPPER_COMMANDS = set("""
SET_PIN SET_SERVO SET_FAN_SPEED SET_LED SET_HEATER_TEMPERATURE TEMPERATURE_WAIT SET_GCODE_OFFSET
SET_VELOCITY_LIMIT SET_PRESSURE_ADVANCE SET_TMC_CURRENT SET_TMC_FIELD SET_STEPPER_ENABLE SAVE_VARIABLE
SET_GCODE_VARIABLE UPDATE_DELAYED_GCODE RESPOND RESTART FIRMWARE_RESTART STATUS HELP ECHO GET_POSITION
SAVE_GCODE_STATE RESTORE_GCODE_STATE SAVE_CONFIG QUERY_ENDSTOPS QUERY_PROBE PROBE PROBE_CALIBRATE
Z_TILT_ADJUST BED_MESH_CALIBRATE BED_MESH_CLEAR BED_MESH_PROFILE BED_MESH_OUTPUT SET_KINEMATIC_POSITION
FORCE_MOVE MANUAL_STEPPER SET_IDLE_TIMEOUT SDCARD_PRINT_FILE SDCARD_RESET_FILE PAUSE RESUME CANCEL_PRINT
CLEAR_PAUSE EXCLUDE_OBJECT RUN_SHELL_COMMAND SET_LASER_POWER EMERGENCY_STOP TURN_OFF_HEATERS
SET_DISPLAY_TEXT SET_EXTRUDER_ROTATION_DISTANCE SYNC_EXTRUDER_MOTION ACTIVATE_EXTRUDER DUMP_TMC
INIT_TMC TUNING_TOWER PID_CALIBRATE ACCELEROMETER_QUERY SHAPER_CALIBRATE TEST_RESONANCES SET_INPUT_SHAPER
SET_FILAMENT_SENSOR QUERY_FILAMENT_SENSOR SET_RETRACTION GET_RETRACTION QUERY_BUTTON QUERY_ADC
""".split())
# Commands that are legal in a macro but surprising in a tool macro - the portal warns, it does not refuse.
RISKY_COMMANDS = {"FIRMWARE_RESTART": "restarts Klipper (stops any job)", "RESTART": "restarts Klipper (stops any job)",
                  "SAVE_CONFIG": "rewrites printer.cfg and restarts Klipper", "M112": "emergency stop",
                  "SET_KINEMATIC_POSITION": "tells Klipper the head is somewhere it may not be",
                  "FORCE_MOVE": "moves a stepper with no limits"}
# What a control can be, in the words the guide uses. Each maps to one Klipper section type.
CONTROL_ROLES = {
    "switch": {"label": "Switch it on and off", "section": "output_pin",
               "help": "Relay, solenoid, vacuum pump, light, valve - anything that is simply on or off."},
    "level": {"label": "Set a level (power, brightness, speed)", "section": "output_pin",
              "help": "A driver board, LED dimmer or heater that takes a PWM level from 0 to 100%."},
    "fan": {"label": "Run it like a fan", "section": "fan_generic",
            "help": "A fan or blower you set by speed %, with a kick-start to get it spinning."},
    "heater_fan": {"label": "Run it automatically while a heater is hot", "section": "heater_fan",
                   "help": "Hotend or heat-break cooling: Klipper turns it on above a temperature by itself."},
    "servo": {"label": "Move it to an angle (hobby servo)", "section": "servo",
              "help": "A servo that swings a gate, lifts a pen or flips a deflector."},
    "input": {"label": "Signal comes FROM the tool (button, switch, sensor)", "section": "gcode_button",
              "help": "Lid switch, limit switch, foot pedal, sensor: Rhino reacts when it changes."},
}
INPUT_ACTIONS = {"none": "Do nothing", "message": "Show a message", "pause": "Pause the job",
                 "estop": "Emergency stop (M112)", "command": "Run a command or macro"}
CONTROL_CYCLE = {"switch": None, "level": 0.01, "fan": 0.01}
CONTROL_LIMITS = {"cycle": (0.00005, 0.5), "max_power": (0.05, 1.0), "heater_temp": (20.0, 300.0),
                  "min_pulse": (0.0001, 0.003), "max_pulse": (0.0005, 0.004), "max_angle": (10.0, 360.0),
                  "kick_start": (0.0, 5.0)}
COMMAND_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*( [A-Za-z0-9_]+=[A-Za-z0-9_.-]+)*$")


# ----------------------------------------------------------------------------- tool categories
# The three answers to "what kind of tool is it?". Each sub-type (editable on the Admin screen) picks
# one of the behaviours, which decides what Klipper config the tool gets.
CATEGORIES = {"additive": "Additive", "subtractive": "Subtractive", "passive": "Passive"}
CATEGORY_HELP = {"additive": "Adds material: print heads, paste or glue dispensers.",
                 "subtractive": "Removes or cuts material: lasers, spindles, hot wires, knives.",
                 "passive": "Does not make or cut anything: pens, probes, cameras, holders."}
BEHAVIOURS = {"PRINT_HEAD": "3D-print head (copies an existing extruder and heater)",
              "POWERED": "Powered (a PWM power output with a cap and a watchdog)",
              "PASSIVE": "Unpowered (offsets and feed rate only)"}
BEHAVIOUR_TYPE = {"PRINT_HEAD": "DEPOSITION", "POWERED": "POWERED", "PASSIVE": "PASSIVE"}
CATEGORY_BEHAVIOURS = {"additive": ("PRINT_HEAD", "POWERED"), "subtractive": ("POWERED", "PASSIVE"),
                       "passive": ("PASSIVE",)}
# category of the built-in tools, by their type in variables.cfg
BUILTIN_CATEGORY = {"DEPOSITION": "additive", "LASER": "subtractive", "CNC": "subtractive",
                    "DRAG_KNIFE": "subtractive", "POWERED": "subtractive", "PASSIVE": "passive"}
KIND_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,23}$")

# ----------------------------------------------------------------------------- the 21-pin umbilical
# Contact -> board pin, as wired (Rhino literature, umbilical pin map). Override in myrhino/umbilical.json
# ("contacts": [{"contact": 1, "pin": "PA2", "label": "...", "kind": "switched"}]). kind:
#   switched  a board output that switches power to the tool     signal  a logic-level signal line
#   return    the - / ground side of a circuit                    supply  a + supply that is always on
#   stepper   a stepper motor coil                                spare   not wired at the board end
CONTACT_KINDS = ("switched", "signal", "return", "supply", "stepper", "spare")
DEFAULT_CONTACTS = [
    (1, "PA2", "Hotend heater +", "switched"), (2, "", "Hotend heater -", "return"),
    (3, "PF4", "Hotend thermistor", "signal"), (4, "", "Hotend thermistor", "return"),
    (5, "PE5", "Hotend fan +", "switched"), (6, "", "Hotend fan -", "return"),
    (7, "", "Stepper A1", "stepper"), (8, "", "Stepper A2", "stepper"),
    (9, "", "Stepper B1", "stepper"), (10, "", "Stepper B2", "stepper"),
    (11, "PA1", "24 V power activate +", "switched"), (12, "", "24 V power activate -", "return"),
    (13, "", "Probe -", "return"), (14, "", "Probe +", "supply"), (15, "PG10", "Probe signal", "signal"),
    (16, "PB0", "Laser PWM (5 V)", "signal"), (17, "", "Spare", "spare"),
    (18, "PB11", "PWM signal 24 V - (ESC signal to GND)", "signal"), (19, "", "Spare", "spare"),
    (20, "PD12", "12 V power activate +", "switched"), (21, "", "12 V power activate -", "return"),
]
# How a tool uses an output it drives
OUTPUT_ROLES = {"power": "Main power level (PWM)", "switch": "Switch on with the tool (on/off)"}
MAX_OUTPUTS = 6

# ----------------------------------------------------------------------------- system hardware
# Board headers of the BTT Octopus, used only to LABEL pins in the system-hardware pin picker.
BOARD_HEADERS = {
    "PA8": "FAN0", "PE5": "FAN1", "PD12": "FAN2", "PD13": "FAN3", "PD14": "FAN4", "PD15": "FAN5",
    "PA2": "HE0", "PA3": "HE1", "PB10": "HE2", "PB11": "HE3", "PA1": "Heated bed (HB)",
    "PF3": "TB", "PF4": "T0", "PF5": "T1", "PF6": "T2", "PF7": "T3",
    "PG6": "DIAG0 (X stop)", "PG9": "DIAG1 (Y stop)", "PG10": "DIAG2", "PG11": "DIAG3", "PG12": "DIAG4",
    "PG13": "DIAG5", "PG14": "DIAG6", "PG15": "DIAG7", "PB0": "RGB", "PB6": "BLTouch servo", "PB7": "BLTouch probe",
    "PC5": "Z probe", "PE11": "PS-ON", "PC0": "PWR-DET", "PB1": "spare GPIO", "PC1": "spare GPIO",
}
HW_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MAX_HARDWARE = 40
# Contacts the built-in tools use (Rhino literature tool pages; PWM signal on 18 as in the pin map and printer.cfg)
BUILTIN_CONTACTS = {"BlockOne": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15],
                    "SwitchFly": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18],
                    "LightSaber": [3, 4, 13, 14, 15, 16, 20, 21],
                    "HotJoe": [3, 4, 11, 12, 13, 14, 15, 18],
                    "DragKnife": [3, 4, 13, 14, 15]}
