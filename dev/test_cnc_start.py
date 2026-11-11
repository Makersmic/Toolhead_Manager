"""Studio's CNC start wizard on the machine side (docs/proposal-cnc-start.md): FROM=STUDIO and QUIET=1.

    python3 dev/test_cnc_start.py          (needs jinja2)

Simulated Klipper. Until dev/proposal_cnc_start.py --apply has run it tests a patched copy of the config, so the change
is proven before it's applied; afterwards the config itself. Also checks the prompt chain without FROM is unchanged."""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from klippersim import KlipperError, Sim          # noqa: E402
import proposal_cnc_start as P                     # noqa: E402

REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def raises(fn, contains=None):
    try:
        fn()
    except KlipperError as e:
        return contains is None or contains.lower() in str(e).lower()
    return False


applied = P.NOTE in open(os.path.join(REPO, P.F)).read()
if applied:
    NEW, OLD = REPO, None
    print("(testing the applied config)")
else:
    tmp = tempfile.mkdtemp(prefix="rhino-cnc-start-")
    NEW = os.path.join(tmp, "config")
    shutil.copytree(REPO, NEW, ignore=shutil.ignore_patterns(".git", "manual", "node_modules", "__pycache__", "studio", "vendor"))
    P.main(["--to", NEW])
    OLD = REPO
    print("(testing a patched copy: the change isn't applied yet)")
    ok(True, "every anchor of the change is found exactly once")


def sim(root=NEW, z=150.0):
    s = Sim(root).load()
    s.macro_vars["SWAP_TOOL"]["current_tool"] = 4
    s.objects["toolhead"]["position"]["z"] = z
    s.objects["gcode_move"]["gcode_position"]["z"] = z
    s.objects["toolhead"]["homed_axes"] = "xyz"
    s.save_vars.update(set_material_toolhead="HotJoe", set_material_material="SOFT_WOOD")
    return s.seed_meshes()


def cmds(s):
    return [str(x[1]) for x in s.log if x[0] == "cmd"]


def zero(s):
    s.run_script("SET_Z_ZERO")
    s.press("SET")


spinning = lambda s: s.pins.get("Spindle_power", 0) > 0.5 and s.pins.get("SPINDLE_SPEED", 0) > 0.31

s = sim()
ok(s.macro_vars["CNC_JOB_SETUP"].get("studio_start") == 1, "the config tells Studio it takes FROM=STUDIO")
ok(raises(lambda: s.run_script("CNC_JOB_SETUP FILE=p.gcode FROM=STUDIO"), "Z zero for the HotJoe"), "FROM=STUDIO before a zero: refused")
ok(raises(lambda: s.run_script("_CNC_WARMUP QUIET=1"), "Z zero") and not spinning(s), "quiet warm-up before a zero: refused, the spindle stays off")

s = sim(); s.objects["toolhead"]["position"]["x"] = 120.0; s.objects["toolhead"]["position"]["y"] = 80.0
s.run_script("_CNC_SAVE_XY QUIET=1")
c = cmds(s)
ok(s.save_vars.get("cnc_g54_x") == 120.0 and s.save_vars.get("cnc_g54_y") == 80.0 and "G54" in c, "X/Y zero QUIET=1: saved at the head and applied")
ok("_CNC_ZERO_Z_CHOOSE" not in c and not (s.prompt and "Set Z zero" in s.prompt["title"]), "...and it stops there (no Z window)")
zero(s)
ok(raises(lambda: s.run_script("CNC_JOB_SETUP FILE=p.gcode FROM=STUDIO"), "spindle isn't running"), "FROM=STUDIO with a zero but the spindle off: refused")
s.log.clear()
s.macro_vars["CNC_JOB_SETUP"]["duty"] = 0.6
s.run_script("_CNC_WARMUP QUIET=1")
c = cmds(s)
ok(spinning(s) and abs(s.pins["SPINDLE_SPEED"] - 0.6) < 1e-9 and not s.prompt, "quiet warm-up: ramps to the throttle set, no Ready prompt")
ok(c.index("_RHINO_INTERLOCKS") < next(i for i, x in enumerate(c) if x.lower().startswith("spindle_activate")), "...the lid is checked before the spindle starts")
s.run_script("_CNC_ADJUST_SPEED DELTA=0.05 QUIET=1")
ok(abs(s.pins["SPINDLE_SPEED"] - 0.65) < 1e-9 and not s.prompt, "throttle +5 % QUIET=1: no Ready prompt")
s.log.clear()
s.run_script("CNC_JOB_SETUP FILE=p.gcode FROM=STUDIO")
c = cmds(s)
ok(not s.prompt and "_RHINO_INTERLOCKS" in c and "_RHINO_HOOKS SLOT=before_start" in c and 'SDCARD_PRINT_FILE FILENAME="p.gcode"' in c,
   "FROM=STUDIO after the zero and warm-up: checks, hooks, the file starts")
s = sim(); zero(s); s.macro_vars["CNC_JOB_SETUP"]["duty"] = 0.6; s.run_script("_CNC_WARMUP QUIET=1")
s.run_script("SWAP_TOOL TOOL=1"); s.macro_vars["SWAP_TOOL"]["current_tool"] = 4; s.objects["print_stats"]["state"] = "standby"
ok(raises(lambda: s.run_script("CNC_JOB_SETUP FILE=p.gcode FROM=STUDIO"), "Z zero"), "a swap since the zero: refused again")

# ---------------------------------------------------------------- the prompt chain is unchanged
if OLD:
    def walk(root):
        s = sim(root)
        s.run_script("CNC_JOB_SETUP FILE=p.gcode")
        seen = [((s.prompt or {}).get("title"), tuple((s.prompt or {}).get("text", [])), tuple(s.buttons()))]
        for b in ("All checked - set X/Y zero", "Set X/Y zero here", "SET - Z zero here", "Throttle +5%"):
            s.press(b)
            seen.append(((s.prompt or {}).get("title"), tuple((s.prompt or {}).get("text", [])), tuple(s.buttons())))
        return seen, s.pins.get("SPINDLE_SPEED")
    a, b = walk(OLD), walk(NEW)
    ok(a == b and len(a[0]) == 5 and all(x[0] for x in a[0]), "the prompts without FROM=STUDIO: the same windows, lines and buttons as before")

print("\n" + ("ALL PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
