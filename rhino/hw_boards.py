"""Add hardware wizard, step 2: what each board pin can do, and second boards ([mcu name]).

Data, not code, like hw_catalog:
  MCUS        chip family -> pin syntax, ADC pins (from Klipper's src/stm32/*adc.c, src/rp2040/adc.c),
              5 V tolerance rule
  PRESETS     known boards: generated pin uses from Klipper's board configs (hw_boards_data.py) plus
              hand-written extras (the Octopus silk labels in presets.BOARD_HEADERS, the plain Pico)
  generic_*   a board we have no table for: any pin the chip has is accepted, with warnings only

A pin reference is "PA1" on the main board and "<board>:PA1" / "<board>:gpio5" on a second board.
canon() makes the one spelling everything compares with. Nothing here reads or writes files."""
import re

from . import hw_catalog, presets
from .errors import Fail
from .hw_boards_data import BOARDS as _GENERATED


def _pins(prefix, nums):
    return {f"{prefix}{n}" for n in nums}


# ----------------------------------------------------------------------------- chips
# adc: None = unknown (generic board, any family member) -> ADC use is allowed with a warning.
# five_v: "yes" = 5 V tolerant in digital mode, "no" = never, "check" = look it up.
MCUS = {
    "stm32f446": {"label": "STM32F446", "family": "stm32",
                  "adc": _pins("PA", range(8)) | {"PB0", "PB1"} | _pins("PC", range(6)) | _pins("PF", range(3, 11))},
    "stm32g0b1": {"label": "STM32G0B1", "family": "stm32",
                  "adc": _pins("PA", range(8)) | {"PB0", "PB1", "PB2", "PB10", "PB11", "PB12", "PC4", "PC5"}},
    "rp2040":    {"label": "RP2040", "family": "rp2040", "adc": _pins("gpio", range(26, 30))},
    "stm32":     {"label": "Other STM32", "family": "stm32", "adc": None},
}
FAMILIES = {
    "stm32":  {"re": re.compile(r"^P[A-K][0-9]{1,2}$", re.I), "example": "PB1", "case": "upper"},
    "rp2040": {"re": re.compile(r"^gpio[0-9]{1,2}$", re.I), "example": "gpio5", "case": "lower"},
}
# STM32: digital pins are FT (5 V tolerant) except the DAC pins and the backup-domain pins (TT / TC).
_STM32_NOT_FT = {"PA4", "PA5", "PC13", "PC14", "PC15"}

# ----------------------------------------------------------------------------- boards
# use: heater / fan (a MOSFET header: switches supply voltage), thermistor (ADC header with a pull-up),
# endstop, probe, servo, rgb, driver (stepper socket), spi, gpio, led (on-board LED).
_PICO = {f"gpio{n}": {"use": "gpio", "header": f"GP{n}", "where": "Pico pinout"} for n in list(range(23)) + [26, 27, 28]}
_PICO["gpio25"] = {"use": "led", "header": "on-board LED", "where": "Pico pinout"}
PRESETS = {bid: dict(b) for bid, b in _GENERATED.items()}
PRESETS["rpi_pico"] = {"label": "Raspberry Pi Pico", "mcu": "rp2040", "source": "Raspberry Pi Pico pinout", "pins": _PICO}
PRESETS["generic_stm32"] = {"label": "Other board (STM32)", "mcu": "stm32", "source": "", "pins": {}, "generic": True}
PRESETS["generic_rp2040"] = {"label": "Other board (RP2040)", "mcu": "rp2040", "source": "", "pins": {}, "generic": True}

MAIN_PRESET = "octopus_v1_1"          # the Rhino's own board (printer.cfg serial: stm32f446)
# the main board's silk labels and spares we already know beat the generated ones
for _p, _h in presets.BOARD_HEADERS.items():
    _d = PRESETS[MAIN_PRESET]["pins"].setdefault(_p, {"use": "gpio", "header": "", "where": "presets.BOARD_HEADERS"})
    _d["header"] = _h
    if _h.startswith(("FAN", "HE", "Heated bed")):
        _d["use"] = "fan" if _h.startswith("FAN") else "heater"
    elif _h.startswith(("T", "TB")) and _p.startswith("PF"):
        _d["use"] = "thermistor"

BOARD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,15}$")
CANBUS_UUID_RE = re.compile(r"^[0-9a-f]{12}$")
MAX_BOARDS = 4
_REF = re.compile(r"^(?:([A-Za-z][A-Za-z0-9_]*):)?([A-Za-z0-9]+)$")


# ----------------------------------------------------------------------------- references
def canon_pin(pin, family):
    f = FAMILIES[family]
    if not f["re"].match(pin or ""):
        return ""
    return pin.lower() if f["case"] == "lower" else pin.upper()


def split_ref(ref):
    """'!ebb:PA1' -> ('ebb', 'PA1'); '^PA1' and 'mcu:PA1' -> ('', 'PA1'). Flags are dropped. ('', '') if not a ref."""
    m = _REF.match(re.sub(r"[!^~]", "", (ref or "").strip()))
    if not m:
        return "", ""
    board = (m.group(1) or "").lower()
    return ("" if board == "mcu" else board), m.group(2)


def canon(ref, boards):
    """A pin reference in its one spelling, or '' if it isn't a pin on the main board or an added board.
    boards: {name: {"preset": id}} (the registry's second boards and any [mcu name] in the config)."""
    board, pin = split_ref(ref)
    if not board:
        p = canon_pin(pin, MCUS[PRESETS[MAIN_PRESET]["mcu"]]["family"])
        return p
    if board not in boards:
        return ""
    fams = [family_of(boards[board])] if (boards[board] or {}).get("preset") else list(FAMILIES)
    p = next((q for q in (canon_pin(pin, f) for f in fams) if q), "")
    return f"{board}:{p}" if p else ""


def family_of(board):
    preset = PRESETS.get((board or {}).get("preset"))
    if preset:
        return MCUS[preset["mcu"]]["family"]
    return (board or {}).get("family") or "stm32"


# ----------------------------------------------------------------------------- capabilities
def caps(ref, boards):
    """What one pin can do. ref must already be canon()."""
    board, pin = ref.split(":", 1) if ":" in ref else ("", ref)
    preset_id = boards[board]["preset"] if board else MAIN_PRESET
    preset = PRESETS.get(preset_id) or PRESETS["generic_rp2040" if pin.startswith("gpio") else "generic_stm32"]
    mcu = MCUS[preset["mcu"]]
    known = preset["pins"].get(pin)
    use = known["use"] if known else "gpio"
    if mcu["family"] == "rp2040":
        five_v = "no"
    elif pin in _STM32_NOT_FT:
        five_v = "no"
    else:
        five_v = "yes"
    return {"pin": ref, "board": board or "main", "header": (known or {}).get("header", ""), "use": use,
            "known": bool(known),
            "mosfet": use in ("heater", "fan"),
            "adc": None if mcu["adc"] is None else pin in mcu["adc"],
            "pwm": True,                # Klipper runs software PWM on any output pin
            "five_v": five_v}


def check_kind(kind, c):
    """-> (ok, [warnings]) for using pin caps c as hw_catalog pin kind `kind`."""
    w, where = [], c["header"] or c["pin"]
    if kind not in hw_catalog.PIN_KINDS or kind == "i2c":
        return False, [f"{kind} is not chosen by pin"]
    if not c["known"]:
        w.append(f"{c['pin']} isn't a header we have a table for. Check your board's pinout before wiring.")
    if c["mosfet"]:
        if kind in ("digital_in", "tach", "adc", "data", "clock", "spi_cs", "step", "dir", "enable"):
            return False, [f"{where} is a MOSFET power output: it switches supply voltage and can't carry a signal."]
        w.append(f"{where} switches supply voltage (12 or 24 V) through the load. Use it for a fan, heater, "
                 f"solenoid or relay coil rated for that voltage, never for a logic input.")
    elif kind in ("digital_out", "pwm_out"):
        w.append(f"{where} is a 3.3 V logic pin: it drives a relay module or driver board, not a load directly.")
    if kind == "adc":
        if c["adc"] is False:
            return False, [f"{c['pin']} can't read an analog value on this chip."]
        if c["adc"] is None:
            w.append(f"We don't know this board's analog pins. Check {c['pin']} is an ADC pin.")
        if c["use"] == "thermistor":
            w.append(f"{where} has a pull-up resistor for a thermistor.")
    if kind in ("step", "dir", "enable") and c["use"] != "driver":
        w.append(f"{c['pin']} isn't on a driver socket: it needs an external stepper driver.")
    if c["use"] == "driver" and kind not in ("step", "dir", "enable"):
        w.append(f"{c['pin']} goes to a stepper driver socket. Only use it if that socket is empty.")
    if c["use"] in ("spi", "led"):
        w.append(f"{c['pin']} is wired to something on the board ({c['use']}).")
    return True, w


def check_sensor(sensor_type, c, isolated=False):
    """Extra rules for a switch / sensor type. Raises Fail for a PNP sensor on a direct pin."""
    s = hw_catalog.SENSOR_TYPES[sensor_type]
    w = []
    if s.get("refuse_direct") and not isolated:
        raise Fail(f"This sensor ({s['label']}) outputs its supply voltage and would damage {c['pin']}. Fit an "
                   f"optocoupler or a divider, then confirm it here.")
    if sensor_type == "optical" and c["five_v"] != "yes":
        w.append(f"{c['pin']} isn't 5 V tolerant: run the sensor on 3.3 V, or add a divider.")
    if s.get("warn") and sensor_type != "optical":
        w.append(s["warn"])
    return w


# ----------------------------------------------------------------------------- second boards
def clean_board(raw, taken_names, existing):
    """-> (name, item) for one second board, or Fail. taken_names: object/mcu names already in use."""
    name = str(raw.get("name") or "").strip().lower()
    if not BOARD_NAME_RE.match(name) or name == "mcu":
        raise Fail("Board name: lower-case letters, digits and _, 2 to 16 characters, starting with a letter (not 'mcu')")
    if name in taken_names:
        raise Fail(f"{name} is already used by {taken_names[name]}")
    if len(existing) >= MAX_BOARDS and name not in existing:
        raise Fail(f"At most {MAX_BOARDS} extra boards")
    preset = str(raw.get("preset") or "")
    if preset not in PRESETS:
        raise Fail("Choose the board, or 'Other board' if it isn't listed")
    link = raw.get("link")
    item = {"preset": preset, "label": PRESETS[preset]["label"]}
    if link == "usb":
        serial = str(raw.get("serial") or "").strip()
        if not serial.startswith("/dev/serial/by-id/") or any(ch.isspace() for ch in serial):
            raise Fail("Choose the board's USB connection from the list (/dev/serial/by-id/...)")
        item.update(link="usb", serial=serial)
    elif link == "can":
        uuid = str(raw.get("canbus_uuid") or "").strip().lower()
        if not CANBUS_UUID_RE.match(uuid):
            raise Fail("CAN bus UUID: 12 hex digits (from the CAN query in Klipper)")
        item.update(link="can", canbus_uuid=uuid)
    else:
        raise Fail("Choose how the board connects: USB or CAN bus")
    for other, b in existing.items():
        if other != name and (b.get("serial") and b.get("serial") == item.get("serial")
                              or b.get("canbus_uuid") and b.get("canbus_uuid") == item.get("canbus_uuid")):
            raise Fail(f"That connection is already board {other}")
    return name, item


def board_lines(reg):
    """[mcu <name>] sections for the generated file."""
    out = []
    for name, b in sorted(reg.get("boards", {}).items()):
        out += [f"[mcu {name}]", f"# second board added in Rhino Studio ({b.get('label', b['preset'])})"]
        out.append(f"serial: {b['serial']}" if b["link"] == "usb" else f"canbus_uuid: {b['canbus_uuid']}")
        out.append("")
    return out


def presets_for_ui():
    return [{"id": bid, "label": p["label"], "mcu": MCUS[p["mcu"]]["label"], "generic": p.get("generic", False),
             "example": FAMILIES[MCUS[p["mcu"]]["family"]]["example"], "source": p["source"]}
            for bid, p in PRESETS.items()]


def check():
    """-> list of problems in the tables (dev/test_hw_boards.py)."""
    out = []
    for bid, p in PRESETS.items():
        if p["mcu"] not in MCUS:
            out.append(f"{bid}: unknown chip {p['mcu']}")
            continue
        fam = MCUS[p["mcu"]]["family"]
        for pin, d in p["pins"].items():
            if canon_pin(pin, fam) != pin:
                out.append(f"{bid}: {pin} isn't a {fam} pin in its one spelling")
            if d["use"] not in ("heater", "fan", "thermistor", "endstop", "probe", "servo", "rgb", "driver", "spi", "gpio", "led"):
                out.append(f"{bid}: {pin} has unknown use {d['use']}")
            if d["use"] == "thermistor" and MCUS[p["mcu"]]["adc"] is not None and pin not in MCUS[p["mcu"]]["adc"]:
                out.append(f"{bid}: thermistor header {pin} isn't an ADC pin")
    if MCUS[PRESETS[MAIN_PRESET]["mcu"]]["family"] != "stm32":
        out.append("the main board must be STM32 (bare pin names)")
    return out
