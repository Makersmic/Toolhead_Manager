"""Studio's start wizard on the machine side (docs/proposal-studio-start.md): the zero flag, FROM=STUDIO, QUIET=1.

    python3 dev/test_studio_start.py          (needs jinja2)

Runs in the simulated Klipper. Until dev/proposal_studio_start.py --apply has run, it tests a patched copy of the
config, so the change is proven before it's applied; afterwards it tests the config itself. Either way it also checks
that the prompt chain without FROM=STUDIO shows the same lines as before."""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from klippersim import KlipperError, Sim          # noqa: E402
import proposal_studio_start as P                  # noqa: E402

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


applied = P.NOTE in open(os.path.join(REPO, "guided", "laser_workflow.cfg")).read()
if applied:
    NEW, OLD = REPO, None
    print("(testing the applied config)")
else:
    tmp = tempfile.mkdtemp(prefix="rhino-studio-start-")
    NEW = os.path.join(tmp, "config")
    shutil.copytree(REPO, NEW, ignore=shutil.ignore_patterns(".git", "manual", "node_modules", "__pycache__", "studio", "vendor"))
    P.main(["--to", NEW])
    OLD = REPO
    print("(testing a patched copy: the change isn't applied yet)")
    ok(True, "every anchor of the change is found exactly once")


def sim(slot, root=NEW, z=150.0):
    s = Sim(root).load()
    s.macro_vars["SWAP_TOOL"]["current_tool"] = slot
    s.objects["toolhead"]["position"]["z"] = z
    s.objects["gcode_move"]["gcode_position"]["z"] = z
    s.objects["toolhead"]["homed_axes"] = "xyz"
    return s.seed_meshes()


def cmds(s):
    return [str(x[1]) for x in s.log if x[0] == "cmd"]


def zero(s, nxt=""):
    s.run_script("SET_Z_ZERO" + (f" NEXT={nxt}" if nxt else ""))
    s.press("SET")


zeroed = lambda s: s.macro_vars["SET_Z_ZERO"]["zeroed"]
rails = lambda s: s.pins.get("LASER_INITIALIZE", 0.0)

# ---------------------------------------------------------------- the zero flag
s = sim(3)
ok(zeroed(s) == "", "after a restart no tool has a zero")
s.run_script("SET_Z_ZERO"); s.press("Cancel") if any("Cancel" in b for b in s.buttons()) else None
ok(zeroed(s) == "", "a cancelled Set Z zero leaves no zero")
zero(s)
ok(zeroed(s) == "LightSaber", "SET records the zero for the mounted tool")
s.run_script("SWAP_TOOL TOOL=5")
ok(zeroed(s) == "", "a tool swap clears it at once")

# ---------------------------------------------------------------- laser
s = sim(3)
ok(raises(lambda: s.run_script("LASER_JOB_SETUP FILE=cut.gcode FROM=STUDIO"), "set the Z zero for the LightSaber"),
   "laser FROM=STUDIO before a zero: refused")
ok("SDCARD_PRINT_FILE" not in " ".join(cmds(s)) and rails(s) == 0.0, "...nothing started, rails off")
zero(s)
s.log.clear()
s.run_script("_LASER_TEST_FIRE QUIET=1")
ok(not s.prompt and "SET_LASER_POWER POWER=0.05" in cmds(s) and rails(s) == 0.0 and s.pins.get("SERVO_LASER", 0.0) == 0.0,
   "test fire QUIET=1: the same 5% pulse, no prompt, rails and level off after")
ok(cmds(s).index("_RHINO_INTERLOCKS") < cmds(s).index("ACTIVATE_LASER"), "...the lid check still runs before it fires")
s.log.clear()
s.run_script("LASER_JOB_SETUP FILE=cut.gcode FROM=STUDIO")
c = cmds(s)
ok(not s.prompt, "laser FROM=STUDIO after the zero: no prompt chain")
ok("_RHINO_INTERLOCKS" in c and "_RHINO_HOOKS SLOT=before_start" in c and "SET_GCODE_OFFSET X=0 Y=0" in c,
   "...the same checks and X/Y reset run")
order = [x for x in c if x in ('SDCARD_PRINT_FILE FILENAME="cut.gcode"', "ACTIVATE_LASER")]
ok(order == ['SDCARD_PRINT_FILE FILENAME="cut.gcode"', "ACTIVATE_LASER"] and rails(s) == 1.0,
   "...the file starts, then the rails come on (after it loaded)")
s = sim(3); zero(s); s.macro_vars["SWAP_TOOL"]["current_tool"] = 4
ok(raises(lambda: s.run_script("LASER_JOB_SETUP FILE=cut.gcode FROM=STUDIO")), "a zero for another tool than the one mounted: refused")
s = sim(5); zero(s)
ok(raises(lambda: s.run_script("LASER_JOB_SETUP FILE=cut.gcode FROM=STUDIO"), "LightSaber"), "a DragKnife zero doesn't start a laser job")
s = sim(3); zero(s); s.objects["print_stats"]["state"] = "printing"
ok(raises(lambda: s.run_script("LASER_JOB_SETUP FILE=cut.gcode FROM=STUDIO"), "BEFORE the job"), "refused while a job runs")

# ---------------------------------------------------------------- drag knife
s = sim(5)
ok(raises(lambda: s.run_script("DRAGKNIFE_JOB_SETUP FILE=k.gcode FROM=STUDIO"), "set the Z zero for the DragKnife"),
   "knife FROM=STUDIO before a zero: refused")
ok(raises(lambda: s.run_script("_DK_TEST_CUT QUIET=1"), "Z zero"), "knife quiet test cut before a zero: refused, nothing moves")
ok(not any(x.startswith("G1 Z-") for x in cmds(s)), "...no plunge")
s.log.clear()
zero(s, "_DK_XY_ZERO")
c = cmds(s)
ok("G54" in c and "SAVE_VARIABLE VARIABLE=cnc_g54_x VALUE=0.0" in c and "_DK_TEST_CUT" not in c,
   "Set Z zero NEXT=_DK_XY_ZERO: X/Y work zero applied, no test cut yet")
s.log.clear()
s.run_script("_DK_TEST_CUT QUIET=1")
c = cmds(s)
ok(not s.prompt and "G1 Z-0.3 F200" in c and any(x.startswith("_RHINO_LIFT") for x in c), "knife test cut QUIET=1: the same cut and lift, no prompt")
s.log.clear()
s.run_script("DRAGKNIFE_JOB_SETUP FILE=k.gcode FROM=STUDIO")
c = cmds(s)
ok(not s.prompt and "_RHINO_INTERLOCKS" in c and "G54" in c and 'SDCARD_PRINT_FILE FILENAME="k.gcode"' in c,
   "knife FROM=STUDIO after the zero: checks, X/Y zero, the file starts")
ok(c.index("G54") < c.index('SDCARD_PRINT_FILE FILENAME="k.gcode"'), "...X/Y zero before the file")
s = sim(5); zero(s); s.run_script("SWAP_TOOL TOOL=3")
s.macro_vars["SWAP_TOOL"]["current_tool"] = 5; s.objects["print_stats"]["state"] = "standby"   # the simulated swap's job state
ok(raises(lambda: s.run_script("DRAGKNIFE_JOB_SETUP FILE=k.gcode FROM=STUDIO"), "Z zero"), "a swap since the zero: refused again")

# ---------------------------------------------------------------- the prompt chain is unchanged
s = sim(5); s.run_script("_DK_ZERO_Z"); s.press("SET")
ok(s.prompt and "Check the test cut" in s.prompt["title"] and "G54" in cmds(s), "knife prompt chain: SET still runs X/Y zero and the test cut, which asks")
if OLD:
    def walk(root, slot, script, presses):
        s = sim(slot, root)
        s.run_script(script)
        seen = [((s.prompt or {}).get("title"), tuple((s.prompt or {}).get("text", [])), tuple(s.buttons()))]
        for b in presses:
            s.press(b)
            seen.append(((s.prompt or {}).get("title"), tuple((s.prompt or {}).get("text", [])), tuple(s.buttons())))
        return seen
    for slot, script, presses, what in (
            (3, "LASER_JOB_SETUP FILE=cut.gcode", ["All checked - set focus", "SET - Z zero here", "Yes - continue"], "laser"),
            (5, "DRAGKNIFE_JOB_SETUP FILE=k.gcode", ["All checked - set Z zero", "SET - Z zero here", "Cut looks good"], "drag knife")):
        a, b = walk(OLD, slot, script, presses), walk(NEW, slot, script, presses)
        ok(a == b and len(a) == 4 and all(x[0] for x in a), f"{what} prompts without FROM=STUDIO: the same titles, lines and buttons as before")

print("\n" + ("ALL PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
