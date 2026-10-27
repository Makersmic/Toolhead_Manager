"""Real Klipper reads our config: the shipped one, and one full of what the Portal generates.

    python3 dev/test_real_klipper.py            (SKIPs when it can't find Klipper or an ARM compiler)
    KLIPPER_DIR=~/klipper python3 dev/test_real_klipper.py

Our other macro tests use klippersim, which is not Klipper. This one runs Klipper itself in its batch mode
(klippy.py -i/-o/-d: it reads printer.cfg, builds every object, then runs a G-code file against a pretend
Octopus, no hardware and no serial port). It catches what only Klipper notices: an option Klipper doesn't know,
a pin used twice, a section our writers get wrong, a macro whose Jinja breaks when it actually runs.

  A  the shipped config parses, then every macro runs once with no arguments
  B  the same, after the Portal has written a second board, one of each wizard device and job hooks

A macro refusing ("Must home axis first", its own action_raise_error) is fine; a template error, an unknown
command, an internal error or a shutdown fails the test. One run with no arguments only walks one path through
each macro, so this complements test_macros.py rather than replacing it.

Needs: a Klipper checkout (KLIPPER_DIR, default ~/klipper or ../klipper), arm-none-eabi-gcc and make (to build an
STM32F446 data dictionary in a temp folder; your Klipper build is not touched), Python with cffi, greenlet, jinja2,
markupsafe and pyserial, and flask for part B. Mainsail's client.cfg is used from MAINSAIL_CFG or
~/mainsail-config/client.cfg when present, otherwise a small stand-in. gcode_shell_command (a KIAUH extra, not in
Klipper) is used from the checkout when installed there, otherwise a stand-in that does nothing.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def skip(why):
    print(f"SKIP real Klipper test: {why}")
    sys.exit(0)


def find_klipper():
    for d in (os.environ.get("KLIPPER_DIR"), os.path.expanduser("~/klipper"), os.path.join(os.path.dirname(REPO), "klipper")):
        if d and os.path.isfile(os.path.join(d, "klippy", "klippy.py")):
            return d
    return None


KLIPPER = find_klipper()
if not KLIPPER:
    skip("no Klipper checkout (set KLIPPER_DIR)")
for tool in ("make", "arm-none-eabi-gcc", "gcc"):
    if not shutil.which(tool):
        skip(f"{tool} is not installed (apt install gcc-arm-none-eabi libnewlib-arm-none-eabi)")
try:
    import cffi, greenlet, jinja2, serial  # noqa: F401  (klippy's own needs)
except ImportError as e:
    skip(f"Klipper's Python packages are missing ({e.name})")

WORK = tempfile.mkdtemp(prefix="rhino-realk-")

# ---------------------------------------------------------------- a data dictionary for the Octopus v1.1 (STM32F446)
# Same choices as the board's Klipper docs: 12 MHz crystal, 32 KiB bootloader, USB on PA11/PA12.
OUT = os.path.join(WORK, "fw") + "/"
os.makedirs(OUT)
kconfig = os.path.join(WORK, "fw.config")
with open(kconfig, "w") as f:
    f.write("CONFIG_LOW_LEVEL_OPTIONS=y\nCONFIG_MACH_STM32=y\nCONFIG_MACH_STM32F446=y\n"
            "CONFIG_STM32_FLASH_START_8000=y\nCONFIG_STM32_CLOCK_REF_12M=y\nCONFIG_STM32_USB_PA11_PA12=y\n")
mk = ["make", "-C", KLIPPER, f"OUT={OUT}", f"KCONFIG_CONFIG={kconfig}"]
r = subprocess.run(mk + ["olddefconfig"], capture_output=True, text=True)
r = r if r.returncode else subprocess.run(mk + [f"-j{os.cpu_count() or 2}"], capture_output=True, text=True)
DICT = os.path.join(OUT, "klipper.dict")
ok(r.returncode == 0 and os.path.isfile(DICT), "built an STM32F446 data dictionary" + ("" if r.returncode == 0 else ": " + r.stderr[-300:]))
if not os.path.isfile(DICT):
    sys.exit(1)
version = subprocess.run(["git", "-C", KLIPPER, "describe", "--always", "--tags"], capture_output=True, text=True).stdout.strip()
print(f"     Klipper {version or '(unknown version)'} from {KLIPPER}")

# ---------------------------------------------------------------- klippy, plus the KIAUH extra our config uses
KLIPPY = os.path.join(WORK, "klippy")
shutil.copytree(os.path.join(KLIPPER, "klippy"), KLIPPY, ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.o"))
SHELL_STUB = '''# Stand-in for KIAUH's gcode_shell_command: the same options, runs nothing.
class ShellCommand:
    def __init__(self, config):
        self.name = config.get_name().split()[-1]
        config.get("command"); config.getfloat("timeout", 2.0, above=0.); config.getboolean("verbose", True)
        config.get_printer().lookup_object("gcode").register_mux_command(
            "RUN_SHELL_COMMAND", "CMD", self.name, self.cmd)
    def cmd(self, gcmd):
        gcmd.respond_info("shell command %s (not run in this test)" % self.name)
def load_config_prefix(config):
    return ShellCommand(config)
'''
# Batch mode stops at the first G-code error; this copy (only this copy) logs it and goes on, so one run can
# try every macro. Nothing else in Klipper is changed.
gpy = os.path.join(KLIPPY, "gcode.py")
src_g = open(gpy).read()
STOP = "        if self.is_fileinput:\n            self.printer.request_exit('error_exit')\n"
ok(STOP in src_g, "this Klipper's batch mode can be told to go on after an error")
open(gpy, "w").write(src_g.replace(STOP, ""))
extra = os.path.join(KLIPPY, "extras", "gcode_shell_command.py")
if not os.path.isfile(extra):
    with open(extra, "w") as f:
        f.write(SHELL_STUB)
    print("     gcode_shell_command: stand-in (not installed in this Klipper)")

MAINSAIL_STUB = """# Stand-in for Mainsail's client.cfg: the sections it adds that our config relies on.
[virtual_sdcard]
path: ~/printer_data/gcodes
on_error_gcode: CANCEL_PRINT
[pause_resume]
[display_status]
[respond]
[gcode_macro CANCEL_PRINT]
rename_existing: CANCEL_PRINT_BASE
gcode:
  CANCEL_PRINT_BASE
[gcode_macro PAUSE]
rename_existing: PAUSE_BASE
gcode:
  PAUSE_BASE
[gcode_macro RESUME]
rename_existing: RESUME_BASE
gcode:
  RESUME_BASE
"""
mainsail = next((p for p in (os.environ.get("MAINSAIL_CFG"), os.path.expanduser("~/mainsail-config/client.cfg"))
                 if p and os.path.isfile(p)), None)

# Never run these: they stop Klipper on purpose, restart it, or only exist to drive real hardware for a long time.
NEVER = {"M112", "EMERGENCY_STOP", "FIRMWARE_RESTART", "RESTART", "SAVE_CONFIG", "SHUTDOWN", "RESTART_FOR_TOOLS"}
# A macro refusing on purpose (action_raise_error, "Must home axis first") is a gcode.CommandError: fine.
BAD = re.compile(r"Error evaluating '[^']*': (?!gcode\.CommandError)|Unknown command|Internal error|"
                 r"Transition to shutdown|Unhandled exception|not a valid config section|Option '.*' is not valid")
# Macros that break when run bare because their caller always hands them something: arguments, or a saved
# variable written one step earlier. Run with nothing, they hit a Jinja UndefinedError. Any macro NOT listed here
# that does this fails the test, so a real typo can't hide among them; check it, then add it with the reason.
NEEDS_CALLER = {
    "CONFIRM_TOOLHEAD": "TOOLHEAD=, MATERIAL= ... from START_JOB",
    "SET_TOOLHEAD": "TOOLHEAD=, MATERIAL= ... from START_JOB / the job wizards",
    "START_SEQUENCE": "PreCheck reads the set_material_* variables START_JOB saves first",
    "_TOOL_Z_DONE": "cnc_g54_z, saved by _Z_ZERO_SAVE just before it calls NEXT=_TOOL_Z_DONE",
    "_JOB_PATH_MATERIALS": "NOZZLE_SIZE= from START_JOB", "_SWITCHFLY_PICK": "PATH= from its prompt button",
    "_NOZZLE_Z_PROMPT": "Z= from NOZZLE_HEIGHT_CALIBRATE", "_NOZZLE_Z_MOVE": "D= from its prompt buttons",
    "_TOOLGEN": "KEYS= from the tool macros", "_RESTORE_TOOL_CONFIRM": "SLOT= from RESTORE_TOOL's buttons",
    "_Z_ZERO_MOVE": "D= from its prompt buttons", "_FC_HEAT": "TEMP= from FILAMENT_CHANGE",
    "_FC_RETRACT_PROMPT": "TEMP=", "_FC_RETRACT": "TEMP=", "_FC_LOAD_PROMPT": "TEMP=", "_FC_LOAD": "TEMP=",
    "_START_TOOL_SWAP_CONFIRM": "TOOL= from START_TOOL_SWAP", "_LASER_SET_PASSES": "DELTA= from its buttons",
    "_RHINO_MESH_RECORD": "BED= from RHINO_MESH_CALIBRATE",
}
MARK = "@@"
MARK_CFG = '''
[gcode_macro _REALK_MARK]
gcode:
  {action_respond_info("@@ " ~ params.N)}
'''


def stage(cfg_src, home):
    """Copy a config folder into home/printer_data/config the way the installer lays it out."""
    cfg = os.path.join(home, "printer_data", "config")
    for d in ("gcodes", "logs"):
        os.makedirs(os.path.join(home, "printer_data", d), exist_ok=True)
    shutil.copytree(cfg_src, cfg, ignore=shutil.ignore_patterns("dev", "docs", "manual", ".git", ".github", "slicer",
                                                                "__pycache__", "node_modules"))
    for p in glob.glob(os.path.join(cfg, "**", "*.cfg"), recursive=True):
        s = open(p).read()
        if "/home/pi" in s:
            open(p, "w").write(s.replace("/home/pi", home))
    with open(os.path.join(cfg, "printer.cfg"), "a") as f:
        f.write("\n[include _realk_mark.cfg]\n")
    open(os.path.join(cfg, "_realk_mark.cfg"), "w").write(MARK_CFG)
    if mainsail:
        shutil.copy(mainsail, os.path.join(cfg, "mainsail.cfg"))
    else:
        open(os.path.join(cfg, "mainsail.cfg"), "w").write(MAINSAIL_STUB)
    return cfg


def run(cfg, home, gcode, dicts):
    gfile = os.path.join(home, "in.gcode")
    log = os.path.join(home, "klippy.log")
    open(gfile, "w").write(gcode)
    if os.path.exists(log):
        os.remove(log)   # klippy appends to its log; each run reads only its own
    args = [sys.executable, os.path.join(KLIPPY, "klippy.py"), os.path.join(cfg, "printer.cfg"),
            "-i", gfile, "-o", os.path.join(home, "out.serial"), "-l", log]
    for name, path in dicts.items():
        args += ["-d", path if name == "mcu" else f"{name}={path}"]
    env = dict(os.environ, HOME=home)
    p = subprocess.run(args, capture_output=True, text=True, env=env, timeout=600)
    text = open(log).read() if os.path.isfile(log) else p.stderr
    # Klipper prints the whole config into the log first; what happened comes after it (from the first marker
    # when there is one: a macro's own text can contain a ===== line).
    i = text.find("\n@@ ")
    after = text[i:] if i >= 0 else text.rsplit("=======================", 1)[-1]
    return p.returncode, after, text


def macro_names(text):
    """gcode_macro names from Klipper's own config dump."""
    names = re.findall(r"^\[gcode_macro ([^\]\s]+)\]", text, re.M)
    return [n for n in dict.fromkeys(names) if n.upper() not in NEVER and n != "_REALK_MARK"]


HOMED = "SET_KINEMATIC_POSITION X=250 Y=200 Z=50\n"   # axes count as homed, so macros get past their homing checks


def sweep(label, cfg, home, dicts, extra_gcode=""):
    code, after, full = run(cfg, home, "G4 P1\n", dicts)
    bad = [ln for ln in after.splitlines() if BAD.search(ln)]
    if code and not bad:   # e.g. "pin PA8 used multiple times in config": the last error line says why
        bad = [ln for ln in full.splitlines() if re.search(r"error|Error|multiple times", ln) and "action_" not in ln][-1:]
    ok(code == 0 and not bad, f"{label}: real Klipper reads the config" + ("" if not bad else ": " + bad[0].strip()[:200]))
    if code or bad:
        print(after[-1500:])
        return
    names = macro_names(full)
    ok(len(names) > 50, f"{label}: {len(names)} macros found")
    # Each macro once, with a marker before it so a failure names its macro. Batch mode can't home (Klipper's
    # endstop code needs a serial port): a macro that homes shuts Klipper down, so the next run starts after it.
    broken, internal, homes, restarts, crashed = {}, {}, [], [], False
    todo, first = list(names), True
    while todo:
        g = (extra_gcode if first else "") + HOMED + "".join(f"_REALK_MARK N={n}\n{n}\n" for n in todo) + "_REALK_MARK N=END\n"
        first = False
        code, after, _ = run(cfg, home, g, dicts)
        crashed |= code != 0
        current, down = "(setup lines)", None
        for ln in after.splitlines():
            m = re.match(r"@@ (\S+)", ln)
            if m:
                current = m.group(1)
                continue
            if "Transition to shutdown" in ln or ln.startswith("Restarting printer"):
                down = current
                break
            if not BAD.search(ln):
                continue
            if "jinja2.exceptions.UndefinedError" in ln and current in NEEDS_CALLER:
                internal.setdefault(current, NEEDS_CALLER[current])
            else:
                broken.setdefault(current, ln.strip()[:220])
        if current == "END":
            break
        if down is None or down not in todo:
            broken.setdefault(current, "the run stopped here without reaching the end")
            break
        if "Transition to shutdown" not in after:
            # Batch mode restarted Klipper (none of these macros restart on purpose; NEVER skips the ones that
            # do). The input after a restart is cut, so carry on from the next macro in a fresh run.
            restarts.append(down)
        elif "must be a cdata pointer, not NoneType" in after and "home" in after.split("Transition to shutdown")[0][-4000:]:
            homes.append(down)
            if broken.get(down, "").startswith("Internal error"):
                del broken[down]
        else:
            broken.setdefault(down, "Klipper shut down: " + after.split("Transition to shutdown", 1)[1].splitlines()[0][:160])
        todo = todo[todo.index(down) + 1:]
    ok(not crashed, f"{label}: Klipper exited cleanly after every run")
    ok(not broken, f"{label}: every macro runs without a template error, unknown command or shutdown"
       + "".join(f"\n       {k}: {v}" for k, v in broken.items()))
    if homes:
        print(f"     note: {len(homes)} macros home an axis, which batch mode can't do (checked up to there): " + ", ".join(homes))
    if restarts:
        print(f"     note: batch mode restarted Klipper after (checked up to there): " + ", ".join(restarts))
    if internal:
        print(f"     note: {len(internal)} macros need what their caller passes (NEEDS_CALLER): " + ", ".join(internal))


# ---------------------------------------------------------------- A: the shipped config
homeA = os.path.join(WORK, "a")
cfgA = stage(REPO, homeA)
sweep("A shipped config", cfgA, homeA, {"mcu": DICT})

# ---------------------------------------------------------------- B: what the Portal writes
try:
    import flask  # noqa: F401
except ImportError:
    print("SKIP part B: flask is not installed")
    sys.exit(1 if fails else 0)

sys.path.insert(0, HERE)
import demo_server as demo  # noqa: E402

src = demo.make_config(os.path.join(WORK, "portal"))
sys.path.insert(0, src)
from rhino.portal import create_app, security  # noqa: E402

fake = demo.start_fake()
app = create_app(src, f"http://127.0.0.1:{fake.server_port}")
c = app.test_client()
H = {security.HEADER: security.TOKEN}


def post(path, body, what):
    r = c.post(path, json=body, headers=H)
    ok(r.status_code == 200, f"B: {what}" + ("" if r.status_code == 200 else f": {(r.get_json() or {}).get('error')}"))


used = set()


def pick(kind, mosfet=None, adc=None, board="aux"):
    for p in (c.get(f"/api/hardware/pins?kind={kind}").get_json() or {}).get("pins", []):
        if not p["pin"].startswith(board + ":") or p["pin"] in used or p["use"] == "driver" and kind not in ("step", "dir", "enable"):
            continue
        if (mosfet is not None and p["mosfet"] != mosfet) or (adc is not None and p["adc"] != adc):
            continue
        used.add(p["pin"])
        return p["pin"]
    raise SystemExit(f"no free {kind} pin on {board}")


# A second Octopus over CAN gives every device its own pins without touching the machine's.
post("/api/hardware/boards", {"name": "aux", "preset": "octopus_v1_1", "link": "can", "canbus_uuid": "aabbccddeeff"},
     "a second board (Octopus over CAN)")
devices = [
    {"device": "controller_fan", "name": "driver_fan", "pins": {"pin": pick("pwm_out", mosfet=True)}},
    {"device": "fan", "name": "four_wire", "wires": "4", "cycle": 0.00004, "tach_ppr": 2,
     "pins": {"pin": pick("pwm_out", mosfet=False), "tach": pick("tach"), "power": pick("digital_out", mosfet=True)},
     "expose": ["control", "macros"]},
    {"device": "temperature_fan", "name": "chamber_exhaust", "target_temp": 45,
     "pins": {"pin": pick("pwm_out", mosfet=True), "sensor": pick("adc", adc=True)}},
    {"device": "heater", "name": "chamber", "max_temp": 80, "expose": ["control", "dashboard", "macros"],
     "pins": {"pin": pick("pwm_out", mosfet=True), "sensor": pick("adc", adc=True)}},
    {"device": "temp_sensor", "name": "pi_temp", "source": "host"},
    {"device": "interlock", "name": "lid", "sensor_type": "mech_nc", "pins": {"pin": pick("digital_in")}},
    {"device": "flame", "name": "flame", "sensor_type": "mech_no", "pins": {"pin": pick("digital_in")}},
    {"device": "spindle_pwm", "name": "router", "expose": ["control", "macros"],
     "pins": {"pin": pick("pwm_out", mosfet=False), "direction": pick("digital_out", mosfet=False),
              "enable": pick("digital_out", mosfet=False)}},
    {"device": "coolant", "name": "mist", "follows": "gcode", "gcode": "M7", "pins": {"pin": pick("digital_out", mosfet=False)}},
    {"device": "air_assist", "name": "air", "follows": "gcode", "gcode": "M8", "pins": {"pin": pick("digital_out", mosfet=False)}},
    {"device": "dust", "name": "dust", "expose": ["control", "macros"], "scope": "category", "scope_values": ["subtractive"],
     "pins": {"pin": pick("digital_out", mosfet=False)}},
    {"device": "led", "name": "case_light", "pins": {"white": pick("pwm_out", mosfet=True)}, "expose": ["control", "macros"]},
    {"device": "neopixel", "name": "strip", "chain_count": 30, "pins": {"pin": pick("data")}},
    {"device": "runout", "name": "runout", "sensor_type": "mech_no", "pins": {"pin": pick("digital_in")}},
    {"device": "manual_stepper", "name": "rotary", "rotation_distance": 360,
     "pins": {"step": pick("step"), "dir": pick("dir"), "enable": pick("enable")}},
]
for d in devices:
    post("/api/hardware/devices", d, f"wizard device {d['device']} '{d['name']}'")
st = c.get("/api/hooks").get_json() or {}
post("/api/hooks", {"rev": st.get("rev", 0), "hooks": {
    "machine": {"before_start": ["M117 Starting"], "after_end": ["SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0"],
                "on_pause": ["M118 Paused"]},
    "category:subtractive": {"after_start": ["DUST_ON"], "before_end": ["DUST_OFF"], "on_cancel": ["DUST_OFF"]},
    "tool:LightSaber": {"after_start": ["M8"], "after_end": ["M9"]},
}}, "job hooks for the machine, CNC tools and the LightSaber")
gen = open(os.path.join(src, "myrhino", "custom_tools.cfg")).read()
hooks = open(os.path.join(src, "myrhino", "job_hooks.cfg")).read()
ok("[mcu aux]" in gen and "cycle_time: 0.00004" in gen and "tachometer_pin" in gen, "B: the generated file has the board and a 4-wire fan")
ok("DUST_ON" in hooks and "_RHINO_INTERLOCKS" in hooks and "lid" in hooks, "B: job_hooks.cfg has the hooks and the lid interlock")
fake.shutdown()

homeB = os.path.join(WORK, "b")
cfgB = stage(src, homeB)
# The job hooks and interlocks by slot and tool, before the plain sweep runs every macro once.
calls = "".join(f"_REALK_MARK N=hooks:{s}:{t}\n_RHINO_HOOKS SLOT={s} TOOL={t}\n"
                for t in ("BlockOne", "LightSaber", "HotJoe")
                for s in ("before_start", "after_start", "before_end", "after_end", "on_cancel", "on_pause", "on_resume"))
calls += "".join(f"_REALK_MARK N=checks:{t}\n_RHINO_INTERLOCKS TOOL={t}\n_RHINO_FILAMENT_SENSORS TOOL={t}\n"
                 for t in ("BlockOne", "LightSaber", "HotJoe", "DragKnife"))
calls += "_REALK_MARK N=outputs\nM7\nM8\nM9\nFOUR_WIRE_SET SPEED=0.5\nCHAMBER_SET TARGET=40\n_RHINO_CONTROLS_OFF\n"
sweep("B Portal-written config", cfgB, homeB, {"mcu": DICT, "aux": DICT}, extra_gcode=calls)

if fails:
    print(f"\n{len(fails)} FAILED (work folder kept: {WORK})")
    sys.exit(1)
shutil.rmtree(WORK, ignore_errors=True)
print("\nall real-Klipper checks passed")
