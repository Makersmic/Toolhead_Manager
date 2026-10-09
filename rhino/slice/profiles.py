"""Kiri:Moto machine profiles built from the Rhino's own tool data.

Nothing here is typed in twice: the laser's power scale comes from VARIABLES.laser_s_max, each
material's power and feed from that tool's materials table, and the work area is checked against
the travel limits in printer.cfg. Change those and the profile follows on the next page load.

Read-only: this never writes a Klipper file.
"""
import json
import os

from .. import __version__
from ..klipper_cfg import ConfigTree
from ..errors import Fail

SETTINGS_FILE = os.path.join("myrhino", "slicer.json")

# Same area as the Orca profile (bed_shape 550 x 375): the X endstop sits at 550, so nothing may
# be placed past it even though Klipper's position_max is 576.
DEFAULT_WORK_AREA = {"x": 550.0, "y": 375.0}

DEFAULTS = {
    "enabled": False,          # the Slice tab only appears when this is true
    "kiri_port": 8090,         # Kiri:Moto runs on the same machine as the portal, on this port
    "work_area": {},           # per tool: {"LightSaber": {"x": 550, "y": 375}}
}

# Tool types this prototype makes profiles for, and the Kiri:Moto mode each one uses.
KIRI_MODE = {"LASER": "LASER"}


def settings_path(paths):
    return os.path.join(paths.cfg, SETTINGS_FILE)


def load_settings(paths):
    """myrhino/slicer.json merged over the defaults. A missing or broken file means 'off'."""
    out = json.loads(json.dumps(DEFAULTS))
    try:
        with open(settings_path(paths), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        out["enabled"] = data.get("enabled") is True
        port = data.get("kiri_port", out["kiri_port"])
        if isinstance(port, int) and 1 <= port <= 65535:
            out["kiri_port"] = port
        if isinstance(data.get("work_area"), dict):
            out["work_area"] = data["work_area"]
    return out


def _variables(tree):
    """The whole [gcode_macro VARIABLES] section as {name: raw text}."""
    for _, cp in tree.files:
        if cp.has_section("gcode_macro VARIABLES"):
            return dict(cp.items("gcode_macro VARIABLES"))
    raise Fail("cannot find [gcode_macro VARIABLES] in the included config files")


def _travel(tree):
    """{'x': position_max, 'y': position_max} from printer.cfg (None if not found)."""
    out = {"x": None, "y": None}
    for _, cp in tree.files:
        for ax in ("x", "y"):
            sec = f"stepper_{ax}"
            if cp.has_section(sec) and cp.has_option(sec, "position_max"):
                try:
                    out[ax] = float(cp.get(sec, "position_max"))
                except ValueError:
                    pass
    return out


def _work_area(name, settings, travel, problems):
    wa = dict(DEFAULT_WORK_AREA)
    mine = (settings.get("work_area") or {}).get(name)
    if isinstance(mine, dict):
        for ax in ("x", "y"):
            try:
                wa[ax] = float(mine.get(ax, wa[ax]))
            except (TypeError, ValueError):
                problems.append(f"{name}: work area {ax.upper()} in {SETTINGS_FILE} is not a number - using {wa[ax]:g}")
    for ax in ("x", "y"):
        lim = travel.get(ax)
        if lim is not None and wa[ax] > lim:
            problems.append(f"{name}: work area {ax.upper()} {wa[ax]:g} is past the travel limit {lim:g} in printer.cfg"
                            f" - using {lim:g}")
            wa[ax] = lim
        if wa[ax] <= 0:
            problems.append(f"{name}: work area {ax.upper()} must be more than 0 - using {DEFAULT_WORK_AREA[ax]:g}")
            wa[ax] = DEFAULT_WORK_AREA[ax]
    return wa


def device_name(tool):
    return f"Rhino {tool}"


def laser_profile(name, tool, s_max, area):
    """One Kiri:Moto LASER device (in Kiri's own stored form) plus one process per material.

    G-code it produces, start to end:
      * a stamp line  ; RHINO_TOOL=<name>  - the portal reads this to refuse a job sliced for a
        tool that is not mounted (a later step of the prototype)
      * G21 / G90 and M5 - millimetres, absolute machine X/Y, laser off before the first move
      * ACTIVATE_LASER - powers the LightSaber rails; Klipper refuses it if another tool is mounted
      * per cut: M3 S<power> ... M5. S runs 0..laser_s_max, which is exactly how the M3 macro scales it
      * end: M5, DEACTIVATE_LASER, _RHINO_PARK (bed down to the safe height)
    The file has no Z moves: it cuts at Z0, the focus point set by LASER_JOB_SETUP / SET_Z_ZERO.
    It must NOT call LASER_JOB_SETUP (that refuses to run during a job) or START_JOB (its G28
    would try to home Z with the laser mounted, which the G28 macro refuses).
    """
    dname = device_name(name)
    pre = [
        f"; RHINO_TOOL={name}",
        f"; RHINO_PROFILE={dname} (made by the Rhino Tool Manager {__version__} from variables.cfg)",
        f"; Start this file with LASER_JOB_SETUP FILE=<this file> - it sets the focus and test-fires first.",
        "G21 ; millimetres",
        "G90 ; absolute X/Y - machine coordinates, same as the slicer bed",
        "M5 ; laser off before the first move",
        "ACTIVATE_LASER ; power the LightSaber rails (refused if another tool is mounted)",
    ]
    post = [
        "M5 ; laser off",
        "DEACTIVATE_LASER ; rails off",
        "_RHINO_PARK ; bed down to the safe park height",
    ]
    device = {
        "mode": "LASER",
        "internal": 0,                 # tells Kiri:Moto this is already in its stored form
        "noclone": True,               # edit the tool in the portal, not a copy in Kiri:Moto
        "deviceName": dname,
        "bedWidth": area["x"],
        "bedDepth": area["y"],
        "bedHeight": 2.5,
        "maxHeight": 100,
        "laserMaxPower": s_max,
        "gcodePre": pre,
        "gcodePost": post,
        "gcodeFExt": "gcode",
        "gcodeSpace": True,
        "gcodeLaserOn": ["M3 S{power}"],
        "gcodeLaserOff": ["M5"],
    }
    processes = {}
    for mat, m in sorted((tool.get("materials") or {}).items()):
        try:
            power = float(m.get("laser_power", 0.5))
            feed = float(m.get("feed_rate", 600))
        except (TypeError, ValueError):
            continue
        pname = f"{name} {mat}"
        processes[pname] = {
            "processName": pname,
            "ctOutPower": round(max(0.0, min(power, 1.0)) * 100, 1),   # percent of laserMaxPower
            "ctOutSpeed": feed,                                         # mm/min (Kiri writes it as F)
            # Kiri's default puts the origin at the middle of the part. The Rhino's laser files use
            # machine X/Y (LASER_JOB_SETUP clears any X/Y work zero), so keep the bed's own origin:
            # the part cuts where it sits on the slicer bed.
            "ctOriginCenter": False,
            "ctOriginBounds": False,
        }
    # Open on plywood (what LASER_JOB_SETUP also assumes when nothing is chosen), else the first material.
    first = f"{name} PLYWOOD" if f"{name} PLYWOOD" in processes else next(iter(processes), None)
    return {"tool": name, "mode": "LASER", "deviceName": dname, "device": device, "processes": processes,
            "process": first, "area": area, "s_max": s_max}


def build(paths, settings=None):
    """-> {"profiles": {tool name: profile}, "problems": [text]} for every tool this prototype covers."""
    settings = settings or load_settings(paths)
    tree = ConfigTree(paths)
    mapping, tools = tree.builtin_tools()
    raw = _variables(tree)
    try:
        s_max = float(str(raw.get("variable_laser_s_max", "1000")).strip())
    except ValueError:
        raise Fail("variable_laser_s_max in variables.cfg is not a number")
    travel = _travel(tree)
    profiles, problems = {}, []
    for slot, name in sorted(mapping.items()):
        t = tools.get(name) or {}
        if KIRI_MODE.get(t.get("type")) != "LASER":
            continue
        area = _work_area(name, settings, travel, problems)
        p = laser_profile(name, t, s_max, area)
        p["slot"] = slot
        if not p["processes"]:
            problems.append(f"{name}: no materials with laser_power and feed_rate in variables.cfg")
        profiles[name] = p
    return {"profiles": profiles, "problems": problems}
