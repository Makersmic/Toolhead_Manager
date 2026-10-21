"""Simulated-Klipper tests for this config tree + the custom-tool flow end to end.
Run from anywhere:  python3 dev/test_macros.py   (needs: pip install jinja2)"""
import os, shutil, subprocess, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from klippersim import Sim, KlipperError

FIXED = os.path.dirname(HERE)                      # the config tree this file lives in
fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, contains=None):
    try: fn()
    except KlipperError as e: return contains is None or contains.lower() in str(e).lower()
    return False
def fresh(slot, root=FIXED, mesh=True):
    # mesh: saved meshes at every bed temperature, so job starts run as they did before 1.6.0
    s = Sim(root).load(); s.macro_vars["SWAP_TOOL"]["current_tool"] = slot
    return s.seed_meshes() if mesh else s

# ---------------------------------------------------------------- the 10 original bugs
s = fresh(4)
try: s.run_script("M5"); ok(True, "bug1: M5 with HotJoe mounted no longer errors")
except KlipperError as e: ok(False, f"bug1: M5 with HotJoe -> {e}")
for slot, name, mat in ((3, "LightSaber", "PLYWOOD"), (5, "DragKnife", "VINYL"), (4, "HotJoe", "SOFT_WOOD")):
    s = fresh(slot); s.save_vars.update(set_material_toolhead=name, set_material_material=mat)
    try: s.run_script("SET_STEPPER_PARAMETERS"); ok(True, f"bug2: SET_STEPPER_PARAMETERS {name}/{mat}")
    except KlipperError as e: ok(False, f"bug2: {name}: {e}")
s = fresh(1); s.save_vars.update(set_material_toolhead="BlockOne", set_material_material="PLA", set_material_nozzle_size=0.4)
ok(not raises(lambda: s.run_script("PRIME_LINE"), "missing toolheads"), "bug3: PRIME_LINE no longer needs toolheads in variables.save")
s = fresh(1); s.objects["output_pin Umbilical_LED"] = {"value": 1.0}
try: s.run_script("LEDOFF"); ok(True, "bug4: LEDOFF default pin works")
except KlipperError as e: ok(False, f"bug4: {e}")
s = fresh(3); before = s.pins["SERVO_LASER"]
raises(lambda: s.run_script("SET_SERVO_ANGLE ANGLE=90"))
ok(s.pins["SERVO_LASER"] == before, "bug5: servo macro cannot drive the laser channel while LightSaber mounted")
s = fresh(3); s.pins["LASER_INITIALIZE"] = 1.0; s.pins["SERVO_LASER"] = 0.5; s.run_script("EMERGENCY_STOP")
ok(s.pins["LASER_INITIALIZE"] == 0 and s.pins["SERVO_LASER"] == 0, "bug6: EMERGENCY_STOP turns the laser off")
s = fresh(4); s.pins["Spindle_power"] = 1.0; s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT")
ok(s.pins["Spindle_power"] == 0, "bug7: CANCEL_PRINT turns the spindle off")
s = Sim(FIXED).load(); s.save_vars["current_tool"] = 3
s.fire_delayed("_RESTORE_TOOL_PROMPT")
ok(s.prompt and any("LightSaber" in t for t in s.prompt["text"]) and s.macro_vars["SWAP_TOOL"]["current_tool"] == 0, "bug8: after restart the saved tool is OFFERED, not silently assumed")
s.press("yes") if any("yes" in b.lower() for b in s.buttons()) else s.press(s.buttons()[0])
ok(s.macro_vars["SWAP_TOOL"]["current_tool"] == 3, "bug8: confirming restores SWAP_TOOL.current_tool")
s = fresh(1); s.save_vars.update(set_material_toolhead="SwitchFly", set_material_extruder_index=1)
s.macro_vars["SWAP_TOOL"]["pending_tool"] = 1
s.run_script("CONFIRM_TOOL_INSTALL")
out = s.render("G1", s.macros["G1"]["gcode"], {"E": "10", "F": "300"}, "E10 F300")
ok("E-10" not in out, "bug9: stale SwitchFly state no longer inverts E after a swap to BlockOne")

# ---------------------------------------------------------------- M3 / M4 / M5 dispatch (built-ins)
s = fresh(3); s.run_script("M3 S500")
ok(s.log and any("SET_LASER_POWER" in str(x) for x in s.log), "M3 on LightSaber routes to SET_LASER_POWER")
s = fresh(5); s.pins["Spindle_power"] = 1.0
ok(raises(lambda: s.run_script("M3 S500"), "no power output"), "M3 on DragKnife is rejected")
ok(s.pins["Spindle_power"] == 0, "...and everything was switched off BEFORE the rejection fired")
s = fresh(4); s.run_script("M5"); s.run_script("M3"); ok(True, "M3/M5 on HotJoe run")

# ---------------------------------------------------------------- custom tools end to end
ROOT = tempfile.mkdtemp(prefix="rhino-test-")
shutil.copytree(FIXED, ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
CFG = ROOT + "/printer_data/config"
def toolgen(*a):
    r = subprocess.run([sys.executable, CFG + "/scripts/rhino_toolgen.py", "--config-dir", CFG, *a], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()
rc, out = toolgen("add", "NAME=FoamWire", "KIND=HOT_WIRE", "PIN=PB1", "NEW_ENABLE_PIN=PC0")
ok(rc == 0, f"toolgen add FoamWire: {out}")
rc, out = toolgen("add", "NAME=Needle", "KIND=NEEDLE", "POWER_PIN=SPINDLE_SPEED")
ok(rc == 0, f"toolgen add Needle on shared SPINDLE_SPEED: {out}")
rc, out = toolgen("add", "NAME=Pen", "KIND=PASSIVE"); ok(rc == 0, "toolgen add Pen")
rc, out = toolgen("add", "NAME=Wide", "KIND=PRINT_HEAD", "BASE=BlockOne", "NOZZLES=0.6"); ok(rc == 0, "toolgen add Wide")
rc, out = toolgen("add", "NAME=Bad", "KIND=HOT_WIRE", "PIN=PE0"); ok(rc == 1 and "stepper_z" in out, "toolgen refuses a pin the config uses")

def cs(slot):
    s = Sim(CFG).load(); s.macro_vars["SWAP_TOOL"]["current_tool"] = slot; return s
s = cs(6)
ok(s.pins.get("FoamWire_PWR") == 0 and s.pins.get("FoamWire_EN") == 0, "generated [output_pin] sections load (power + enable)")
s.run_script("M3 S500")   # S500 / s_max 1000 = 50% of cap 0.5 -> 0.25
ok(abs(s.pins["FoamWire_PWR"] - 0.25) < 1e-6 and s.pins["FoamWire_EN"] == 1, f"M3 S500 -> duty {s.pins['FoamWire_PWR']} (cap-scaled), enable on")
ok(s.macro_vars["TOOL_POWER_STATE"]["active"] == 1, "watchdog state armed")
s.run_script("M3 S5000"); ok(s.pins["FoamWire_PWR"] <= 0.5 + 1e-9, "S above s_max never exceeds the power cap")
s.run_script("M5"); ok(s.pins["FoamWire_PWR"] == 0 and s.pins["FoamWire_EN"] == 0 and s.macro_vars["TOOL_POWER_STATE"]["active"] == 0, "M5 turns it off and disarms")

# watchdog: no job -> cut after max_on_s (600) ; job running -> no time limit ; pause -> cut, resume -> restored
s.run_script("M3 S1000"); s.objects["print_stats"]["state"] = "standby"
for _ in range(119): s.fire_delayed("TOOL_POWER_WATCHDOG")
ok(s.pins["FoamWire_PWR"] > 0, "119 ticks (595 s) idle: still on")
for _ in range(2): s.fire_delayed("TOOL_POWER_WATCHDOG")
ok(s.pins["FoamWire_PWR"] == 0 and s.errors(), "after max_on_s with no job: cut off + error shown")
s = cs(6); s.run_script("M3 S1000"); s.objects["print_stats"]["state"] = "printing"
for _ in range(400): s.fire_delayed("TOOL_POWER_WATCHDOG")
ok(s.pins["FoamWire_PWR"] > 0, "while a job is printing there is no time limit (job supervises the tool)")
s.objects["print_stats"]["state"] = "paused"; s.run_script("TOOL_POWER_PAUSE")
ok(s.pins["FoamWire_PWR"] == 0 and s.macro_vars["TOOL_POWER_STATE"]["suspended"] == 1, "pause cuts power")
s.objects["print_stats"]["state"] = "printing"; s.run_script("TOOL_POWER_RESTORE")
ok(s.pins["FoamWire_PWR"] > 0 and s.macro_vars["TOOL_POWER_STATE"]["suspended"] == 0, "resume restores the same level")
s.objects["print_stats"]["state"] = "paused"; s.fire_delayed("TOOL_POWER_WATCHDOG")
ok(s.pins["FoamWire_PWR"] == 0, "tick also cuts power during a pause even if the hook did not fire")
s.objects["print_stats"]["state"] = "printing"; s.fire_delayed("TOOL_POWER_WATCHDOG")
ok(s.pins["FoamWire_PWR"] > 0, "tick restores power after resume if the hook did not fire")

# Mainsail integration: the real mainsail.cfg (dev/fixtures) is loaded, our hooks go through _CLIENT_VARIABLE
s = cs(6)
ok("PAUSE_BASE" in s.macros and "rename_existing" in s.macros["PAUSE"], "real Mainsail PAUSE/RESUME/CANCEL_PRINT loaded")
cv = s.macro_vars["_CLIENT_VARIABLE"]
ok(cv["user_pause_macro"] == "_RHINO_PAUSE_HOOK" and cv["user_resume_macro"] == "_RHINO_RESUME_HOOK"
   and cv["user_cancel_macro"] == "_RHINO_CANCEL", "Rhino hooks wired into Mainsail's _CLIENT_VARIABLE")
import glob as _g
_dups = [f for f in _g.glob(os.path.join(FIXED, "**", "*.cfg"), recursive=True)
         if "fixtures" not in f and any(l.strip().upper() in ("[GCODE_MACRO CANCEL_PRINT]", "[GCODE_MACRO PAUSE]", "[GCODE_MACRO RESUME]")
                                        for l in open(f, encoding="utf-8"))]
ok(not _dups, f"no config file re-defines Mainsail's PAUSE/RESUME/CANCEL_PRINT ({_dups})")

def idx(sim, text, start=0):
    for i, e in enumerate(sim.log[start:], start):
        if e[0] == "cmd" and text in e[1]: return i
    return -1

# ---- PAUSE / TOOL_RESUME for non-print tools (real Mainsail PAUSE/RESUME/CANCEL_PRINT) ----
def paused_job(slot, setup):
    s = cs(slot); s.objects["print_stats"]["state"] = "printing"
    s.objects["gcode_move"]["gcode_position"] = {"x": 120.0, "y": 80.0, "z": 3.0}
    s.objects["toolhead"]["position"]["z"] = 3.0
    s.run_script(setup); s.before = dict(s.pins); n = len(s.log); s.run_script("PAUSE"); return s, n

# custom powered tool
s, n = paused_job(6, "M3 S1000"); lvl = s.before["FoamWire_PWR"]
lift, off, park = idx(s, "G1 Z10", n), idx(s, "FoamWire_PWR VALUE=0", n), idx(s, "G1 X", n)
ok(s.pins["FoamWire_PWR"] == 0 and 0 <= lift < off < park, "PAUSE (custom tool): lift 10 mm, tool off, then Mainsail parks")
ok(s.prompt and "Resume job" in s.buttons() and "Cancel job" in s.buttons(), "pause pop-up offers Resume job / Cancel job")
s.objects["extruder"]["can_extrude"] = True; s.prompt = None
ok(raises(lambda: s.run_script("RESUME"), "TOOL_RESUME"), "Mainsail RESUME is stopped for a non-print-tool job (even with a warm extruder)")
ok(s.objects["print_stats"]["state"] == "paused" and "Resume job" in s.buttons(), "...nothing moved, and the pop-up is shown again")
n = len(s.log); s.press("Resume job")
xy, z2, rb, on = idx(s, "G1 X120.0 Y80.0", n), idx(s, "G1 Z5.0", n), idx(s, "RESUME_BASE", n), idx(s, "SET_TOOL_POWER", n)
ok(0 <= xy < z2 < rb < on, "TOOL_RESUME: over the spot, down to +2 mm, slow return, then power")
ok(abs(s.pins["FoamWire_PWR"] - lvl) < 1e-9 and s.objects["print_stats"]["state"] == "printing", "custom tool back at its pre-pause level, job running")
ok(s.macro_vars["_RHINO_PAUSE_HOOK"]["tool_pause"] == 0, "pause memory cleared after resume")

# built-in laser: was left ON during the park move before
s, n = paused_job(3, "SET_LASER_POWER POWER=0.6")
off, park = idx(s, "SERVO_LASER VALUE=0", n), idx(s, "G1 X", n)
ok(s.pins["SERVO_LASER"] == 0 and 0 <= off < park, "PAUSE (LightSaber): laser off before the park move")
s.run_script("RESUME"); ok(s.objects["print_stats"]["state"] == "paused" and s.pins["SERVO_LASER"] == 0, "Mainsail RESUME (cold extruder) leaves the laser job paused and dark")
n = len(s.log); s.run_script("TOOL_RESUME")
ok(abs(s.pins["SERVO_LASER"] - 0.6) < 1e-9 and idx(s, "SET_LASER_POWER", n) > idx(s, "RESUME_BASE", n), "TOOL_RESUME: laser back to 0.6 after the return move")

# CNC spindle: lifted out of the cut while spinning, stopped, spun up again BEFORE re-entering the cut
s, n = paused_job(4, "Spindle_ACTIVATE\nSET_PIN PIN=SPINDLE_SPEED VALUE=0.55")
ok(s.pins["Spindle_power"] == 0 and abs(s.pins["SPINDLE_SPEED"] - 0.3) < 1e-9 and idx(s, "G1 Z10", n) < idx(s, "Spindle_DEACTIVATE", n),
   "PAUSE (HotJoe): lifted while spinning, then spindle stopped")
n = len(s.log); s.run_script("TOOL_RESUME")
ok(abs(s.pins["SPINDLE_SPEED"] - 0.55) < 1e-9 and s.pins["Spindle_power"] == 1 and idx(s, "Spindle_ACTIVATE", n) < idx(s, "G1 Z5.0", n),
   "TOOL_RESUME (HotJoe): spindle back to 55 % before going down into the cut")

# safety refusals
s, n = paused_job(6, "M3 S1000"); s.macro_vars["SWAP_TOOL"]["current_tool"] = 7
ok(raises(lambda: s.run_script("TOOL_RESUME"), "recorded as mounted") and s.objects["print_stats"]["state"] == "paused", "TOOL_RESUME refuses if a different tool is mounted")
s = cs(6); ok(raises(lambda: s.run_script("TOOL_RESUME"), "nothing is paused"), "TOOL_RESUME with nothing paused is refused")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"; s.objects["extruder"]["can_extrude"] = True
s.run_script("PAUSE"); ok(s.prompt is None, "print-head pause: no Rhino pop-up (Mainsail as usual)")
s.run_script("TOOL_RESUME"); ok(s.objects["print_stats"]["state"] == "printing", "TOOL_RESUME on a print job hands over to Mainsail RESUME")
s, n = paused_job(3, "SET_LASER_POWER POWER=0.6"); s.press("Cancel job")
ok(s.pins["SERVO_LASER"] == 0 and s.macro_vars["_RHINO_PAUSE_HOOK"]["tool_pause"] == 0 and s.objects["print_stats"]["state"] == "cancelled",
   "Cancel job from the pop-up: laser off, pause forgotten, job cancelled")
s, n = paused_job(6, "M3 S1000"); s.run_script("PAUSE")
ok(s.macro_vars["_RHINO_PAUSE_HOOK"]["px"] == 120.0, "pressing PAUSE twice keeps the original paused spot")

# Mainsail CANCEL_PRINT runs the Rhino cancel (tool off, lift, home XY) and its own clean-up
s = cs(6); s.run_script("M3 S1000"); s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT")
ok(s.pins["FoamWire_PWR"] == 0 and idx(s, "_RHINO_CANCEL") >= 0 and idx(s, "SET_PAUSE_AT_LAYER") >= 0
   and idx(s, "CANCEL_PRINT_BASE") > idx(s, "_RHINO_CANCEL"), "CANCEL_PRINT: Mainsail clean-up + Rhino cancel, before CANCEL_PRINT_BASE")

# shared channel: Needle drives SPINDLE_SPEED, idle must be 0.3 (ESC neutral), not 0
s = cs(7); ok(s.pins["SPINDLE_SPEED"] == 0.3, "SPINDLE_SPEED starts at neutral")
s.run_script("M3 S600"); ok(s.pins["SPINDLE_SPEED"] > 0.3, "Needle on shared ESC channel drives it")
s.run_script("M5"); ok(abs(s.pins["SPINDLE_SPEED"] - 0.3) < 1e-9, "M5 returns the shared ESC channel to neutral 0.3 (not 0)")
s = cs(4); s.run_script("_TOOL_SAFE_OFF"); ok(abs(s.pins["SPINDLE_SPEED"] - 0.3) < 1e-9, "safe-off with HotJoe mounted keeps ESC neutral")

# SWAP_TOOL cuts tool power
s = cs(6); s.run_script("M3 S1000"); s.run_script("SWAP_TOOL TOOL=7")
ok(s.pins["FoamWire_PWR"] == 0 and s.macro_vars["TOOL_POWER_STATE"]["active"] == 0, "SWAP_TOOL switches the custom tool off first")
s = cs(6); s.run_script("M3 S1000"); s.run_script("EMERGENCY_STOP"); ok(s.pins["FoamWire_PWR"] == 0, "EMERGENCY_STOP cuts custom tools")
s = cs(6); s.run_script("M3 S1000"); s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT"); ok(s.pins["FoamWire_PWR"] == 0, "CANCEL_PRINT cuts custom tools")
s = cs(6); s.save_vars.update(set_material_toolhead="FoamWire", set_material_material="FOAM_EPS"); s.run_script("M3 S1000"); s.run_script("END_PRINT")
ok(s.pins["FoamWire_PWR"] == 0, "END_PRINT cuts custom tools")
s = cs(7); ok(raises(lambda: s.run_script("SET_TOOL_POWER POWER=1")) is False, "SET_TOOL_POWER works for Needle")
s = cs(8); s.pins["Spindle_power"] = 1.0
ok(raises(lambda: s.run_script("M3 S10"), "no power output"), "M3 on a print-head clone is rejected")

# SET_TOOLHEAD / SET_STEPPER_PARAMETERS for custom types
s = cs(6); s.run_script("SET_TOOLHEAD TOOLHEAD=FoamWire MATERIAL=FOAM_EPS")
ok(s.save_vars.get("set_material_toolhead") == "FoamWire" and abs(s.save_vars["set_material_power"] - 0.4) < 1e-9, "SET_TOOLHEAD dispatches POWERED tools")
s.run_script("SET_STEPPER_PARAMETERS"); ok(True, "SET_STEPPER_PARAMETERS works for POWERED")
s = cs(9); s.run_script("SET_TOOLHEAD TOOLHEAD=Pen MATERIAL=DEFAULT"); ok(s.save_vars.get("set_material_toolhead") == "Pen", "SET_TOOLHEAD dispatches PASSIVE tools")
s = cs(8); s.save_vars.update(set_material_extruder_index=0); s.run_script("SET_TOOLHEAD TOOLHEAD=Wide MATERIAL=PLA NOZZLE_SIZE=0.6 EXTRUDER=0")
ok(s.save_vars.get("set_material_toolhead") == "Wide", "SET_TOOLHEAD dispatches a cloned print head at 0.6 mm")

# ---------------------------------------------------------------- console macros
s = cs(6)
s.run_script("ADD_TOOLHEAD NAME=Hot2 KIND=HOT_WIRE PIN=PC1 CAP=0.3")
ok(s.shell_calls and s.shell_calls[-1][0] == "rhino_toolgen" and s.shell_calls[-1][1].startswith("add NAME=Hot2 KIND=HOT_WIRE")
   and "PIN=PC1" in s.shell_calls[-1][1] and "CAP=0.3" in s.shell_calls[-1][1], f"ADD_TOOLHEAD forwards params: {s.shell_calls[-1] if getattr(s,'shell_calls',None) else None}")
ok(s.prompt and "Restart now" in s.buttons(), "...and offers a restart")
s.run_script("ADD_TOOLHEAD NAME=X KIND=PASSIVE EVIL=rm")
ok("EVIL" not in s.shell_calls[-1][1], "unlisted parameters are not forwarded")
s.run_script("ADD_TOOLHEAD ACTION=remove NAME=Pen2 KIND=PASSIVE")
ok(s.shell_calls[-1][1].startswith("add "), "a user cannot override ACTION")
s.objects["print_stats"]["state"] = "printing"
ok(raises(lambda: s.run_script("ADD_TOOLHEAD NAME=Q KIND=PASSIVE"), "blocked while a job"), "registry changes refused during a job")
ok(raises(lambda: s.run_script("RESTART_FOR_TOOLS"), "blocked while a job"), "restart refused during a job")
s.objects["print_stats"]["state"] = "standby"
n = len(s.shell_calls); s.run_script("REMOVE_TOOLHEAD NAME=Pen")
ok(len(s.shell_calls) == n and any("Remove Pen" in b for b in s.buttons()), "REMOVE_TOOLHEAD asks first")
ok(raises(lambda: s.run_script("REMOVE_TOOLHEAD NAME=FoamWire"), "mounted"), "cannot remove the mounted tool")
s.run_script("REMOVE_TOOLHEAD NAME=Pen"); s.press("Remove Pen"); ok(s.shell_calls[-1][1] == "remove NAME=Pen", "confirm -> remove forwarded")
ok(raises(lambda: s.run_script("REMOVE_TOOLHEAD NAME=BlockOne"), "not a custom"), "built-ins cannot be removed")
s.run_script("TOOLS_MENU"); ok(s.prompt is not None, "TOOLS_MENU renders")
s.run_script("LIST_TOOLHEADS"); ok(s.shell_calls[-1][1].startswith("list"), "LIST_TOOLHEADS")

# ---------------------------------------------------------------- guided job setup for custom tools
s = cs(6); s.save_vars.update(set_material_toolhead="FoamWire", set_material_material="FOAM_EPS")
s.run_script("TOOL_JOB_SETUP FILE=cut.gcode")
ok(any("Ventilation" in t for t in s.prompt["text"]), "checklist shown")
s.press("All checked"); ok("Continue" not in s.buttons(), "cannot continue before both zeros are set")
s.objects["toolhead"]["position"].update(x=210.0, y=120.0, z=35.5)
s.press("X/Y zero"); s.press("Z zero"); ok("Set Z zero" in s.prompt["title"], "Z zero opens the SET_Z_ZERO window"); s.press("SET")
ok(s.offsets["X"] == 210.0 and s.offsets["Y"] == 120.0 and s.offsets["Z"] == 35.5 and not getattr(s, "moved", False), "zero uses position, no MOVE=1")
ok("Continue" in s.buttons(), "Continue appears once both are set")
s.press("Continue"); s.pins["FoamWire_PWR"] = 0
s.press("Test pulse"); ok(s.pins["FoamWire_PWR"] == 0, "test pulse ends with power off"); ok("Start - tool power ON" in s.buttons(), "back at the start choices")
s.press("tool power ON"); ok(s.pins["FoamWire_PWR"] > 0, "start (tool power ON) switches the tool on")
ok(any("SDCARD_PRINT_FILE" in str(x) or "cut.gcode" in str(x) for x in s.log), "job file started")
s = cs(6); ok(raises(lambda: s.run_script("TOOL_JOB_SETUP"), "choose a material"), "setup demands a selected material")
s = cs(3); ok(raises(lambda: s.run_script("TOOL_JOB_SETUP"), "LASER_JOB_SETUP"), "setup points built-in tools to their own workflow")
s = cs(6); s.save_vars.update(set_material_toolhead="FoamWire", set_material_material="FOAM_EPS"); s.objects["toolhead"]["homed_axes"] = "xy"
ok(raises(lambda: s.run_script("TOOL_JOB_SETUP"), "Home"), "setup demands homing")
s = cs(6); s.save_vars.update(set_material_toolhead="FoamWire", set_material_material="FOAM_EPS"); s.run_script("TOOL_JOB_SETUP"); s.press("All checked")
s.press("Cancel"); ok(s.pins["FoamWire_PWR"] == 0 and s.offsets == {"X": 0.0, "Y": 0.0, "Z": 0.0}, "cancel clears offsets and power")

# ---------------------------------------------------------------- safe park height / no Z homing with non-print tools
def cmds(s): return [str(x[1]) for x in s.log if x[0] == "cmd"]
def homes(s): return [c for c in cmds(s) if c.split()[0].upper() == "G28"]
# 1.4.5: CANCEL_PRINT never homes X/Y with a laser mounted (homing Y with the LightSaber on crashes it)
def cancel(slot, homed):
    s = fresh(slot); s.objects["toolhead"]["homed_axes"] = homed; s.objects["print_stats"]["state"] = "printing"
    s.run_script("CANCEL_PRINT"); return s
s = cancel(3, "xyz")
ok(not homes(s) and any(c.startswith("G1 X") for c in cmds(s)) and s.pins["LASER_INITIALIZE"] == 0
   and idx(s, "CANCEL_PRINT_BASE") > idx(s, "_RHINO_CANCEL"), "cancel with LightSaber: no G28, parks X/Y, rail off, Mainsail clean-up runs")
s = cancel(3, "z")
ok(not homes(s) and not any(c.startswith("G1 X") for c in cmds(s)) and idx(s, "CANCEL_PRINT_BASE") >= 0,
   "cancel with LightSaber and X/Y not homed: no homing, no move, cancel still finishes")
s = cancel(1, "xyz")
ok(any(c.startswith("G28 X Y") for c in homes(s)), "cancel with BlockOne still homes X/Y as before")
s = cancel(4, "xyz")
ok(any(c.startswith("G28 X Y") for c in homes(s)), "cancel with HotJoe still homes X/Y as before")
s = fresh(3); s.objects["toolhead"]["homed_axes"] = ""; s.save_vars["rhino_z_safe"] = 0
s.run_script("SWAP_TOOL TOOL=1")
ok(s.prompt and "clear" in s.prompt["title"].lower() and not homes(s), "swap after a restart with the bed not parked: asks before any homing")
ok(s.macro_vars["SWAP_TOOL"]["pending_tool"] == -1, "...and nothing is started until confirmed")
s.press("It is clear")
ok(homes(s) == ["G28 X Y"], "confirmed: homes X/Y only, never Z")
ok(s.macro_vars["SWAP_TOOL"]["pending_tool"] == 1, "...and the swap continues")
s = fresh(3); s.objects["toolhead"]["homed_axes"] = ""; s.save_vars["rhino_z_safe"] = 1
s.run_script("SWAP_TOOL TOOL=1")
ok(homes(s) == ["G28 X Y"] and s.macro_vars["SWAP_TOOL"]["pending_tool"] == 1, "bed parked before the restart: swap homes X/Y by itself")
s = fresh(3); s.objects["toolhead"]["position"]["z"] = 20.0; s.objects["gcode_move"]["gcode_position"]["z"] = 20.0
s.run_script("SWAP_TOOL TOOL=1")
ok("G1 Z150.0 F1200" in cmds(s) and not homes(s), "homed swap lowers the bed to the safe height, no homing")
ok(s.save_vars.get("rhino_z_safe") == 1, "...and records the bed as parked")
s = fresh(4); s.objects["toolhead"]["position"]["z"] = 200.0; s.objects["gcode_move"]["gcode_position"]["z"] = 200.0
s.run_script("_RHINO_PARK"); ok("G1 Z200.0 F1200" in cmds(s), "park never raises the bed toward the tool")
s = fresh(4); s.objects["toolhead"]["position"]["z"] = 12.0; s.objects["gcode_move"]["gcode_position"]["z"] = 2.0
s.run_script("_RHINO_PARK"); ok("G1 Z140.0 F1200" in cmds(s), "park height ignores work offsets (machine Z 150)")
s = fresh(1); s.objects["toolhead"]["position"]["z"] = 0.3; s.objects["gcode_move"]["gcode_position"]["z"] = 0.3
s.save_vars.update(set_material_toolhead="BlockOne", set_material_material="PLA")
s.run_script("END_PRINT"); ok(any(c.startswith("G1 Z150") for c in cmds(s)) and "G1 Z10 F600" not in cmds(s), "END_PRINT parks at the safe height")
s = fresh(4); s.objects["toolhead"]["position"]["z"] = 3.0; s.objects["gcode_move"]["gcode_position"]["z"] = 3.0; s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT")
ok(any(c.startswith("G1 Z150") for c in cmds(s)), "cancel parks at the safe height")
s = fresh(1); s.objects["toolhead"]["position"]["z"] = 20.0; s.save_vars["rhino_z_safe"] = 1
s.run_delayed_body("_RHINO_PARK_WATCH"); ok(s.save_vars["rhino_z_safe"] == 0, "watcher: bed raised below the safe height -> not parked")
s.objects["toolhead"]["position"]["z"] = 150.0; s.run_delayed_body("_RHINO_PARK_WATCH"); ok(s.save_vars["rhino_z_safe"] == 1, "watcher: bed at the safe height -> parked")
s.objects["toolhead"]["homed_axes"] = ""; s.save_vars["rhino_z_safe"] = 1; s.run_delayed_body("_RHINO_PARK_WATCH")
ok(s.save_vars["rhino_z_safe"] == 1, "watcher leaves the record alone while Z is not homed")
s = fresh(1); s.save_vars["rhino_z_safe"] = 1; s.macro_vars["_START_JOB_FILE"]["file"] = "a.gcode"; s.run_script("_START_JOB_FILE")
ok(s.save_vars["rhino_z_safe"] == 0, "starting a job clears the parked record")
for slot, script in ((4, "_CNC_ZERO_XY"), (5, "_DK_ZERO_Z"), (3, "LASERHOME"), (4, "SET_Z_ZERO")):
    s = fresh(slot); s.objects["toolhead"]["homed_axes"] = "xy"
    ok(raises(lambda: s.run_script(script), "Z is not homed") and not homes(s), f"{script}: never homes Z with a non-print tool")
    s = fresh(slot); s.objects["toolhead"]["homed_axes"] = "z"
    try: s.run_script(script)
    except KlipperError: pass
    ok(homes(s) == ["G28 X Y"], f"{script}: Z homed -> parks, then homes X/Y only")
s = fresh(1); s.objects["toolhead"]["homed_axes"] = "xyz"
s.save_vars.update(set_material_toolhead="BlockOne", set_material_material="PLA", set_material_nozzle_size=0.4)
s.objects["extruder"]["temperature"] = 210.0
try: s.run_script("PURGE")
except KlipperError: pass
ok(any("PURGE" == c.split()[0] for c in cmds(s)) and not homes(s), "print head: homed check now works (no needless G28 every time)")


# ---------------------------------------------------------------- SET_Z_ZERO: Z0 by eye for laser / CNC / knife / added tools
def zsim(slot, z=150.0, homed="xyz"):
    s = fresh(slot); s.objects["toolhead"]["position"]["z"] = z; s.objects["gcode_move"]["gcode_position"]["z"] = z
    s.objects["toolhead"]["homed_axes"] = homed
    def skp(p, rest):
        s.objects["toolhead"]["position"]["z"] = float(p["Z"]); s.objects["toolhead"]["homed_axes"] = "xyz"
    s.extra_cmds = {"SET_KINEMATIC_POSITION": skp}; return s
s = zsim(4); s.run_script("SET_Z_ZERO")
ok(s.prompt and "Set Z zero" in s.prompt["title"] and not homes(s), "SET_Z_ZERO (HotJoe, Z homed): opens the window, no homing")
ok(all(any(b.startswith(f"Bed {d} {n}") for b in s.buttons()) for d in ("up", "down") for n in ("10", "1", "0.1")), "...with Bed up/down 10, 1 and 0.1")
s.press("Bed up 10"); ok("G1 Z-10.000 F600" in cmds(s) and "G91" in cmds(s), "Bed up 10 = relative move 10 mm toward the tool")
s.objects["toolhead"]["position"]["z"] = 37.25; s.press("SET")
ok(abs(s.save_vars["cnc_g54_z"] - 37.25) < 1e-9 and "SET_GCODE_OFFSET Z=37.250" in cmds(s), "SET: the bed height becomes Z0 (saved and applied, no move)")
ok(not any(c.startswith("SET_KINEMATIC_POSITION") for c in cmds(s)), "SET never redefines machine Z")
s = zsim(4, z=290.0); s.run_script("SET_Z_ZERO"); s.press("Bed down 10"); ok("G1 Z0.000 F600" in cmds(s), "never lowers the bed past Z290")
s = zsim(4, z=285.0); s.run_script("SET_Z_ZERO"); s.press("Bed down 10"); ok("G1 Z5.000 F600" in cmds(s), "...stops exactly at Z290")
s = zsim(4, z=-9.95); s.run_script("SET_Z_ZERO"); s.press("Bed up 1 mm"); ok("G1 Z-0.050 F300" in cmds(s), "never raises the bed past position_min")
s = zsim(4, z=292.0); s.run_script("SET_Z_ZERO"); s.press("Bed down 0.1"); ok("G1 Z0.000 F300" in cmds(s), "below the Z290 limit, Bed down does not move the bed UP")
s = zsim(1); ok(raises(lambda: s.run_script("SET_Z_ZERO"), "NOZZLE_HEIGHT_CALIBRATE"), "print head: refused, points to the paper test")
s = zsim(4); s.objects["print_stats"]["state"] = "printing"; ok(raises(lambda: s.run_script("SET_Z_ZERO"), "job"), "refused during a job")
s = zsim(3); s.run_script("SET_Z_ZERO"); ok(any("Focus dot ON" in b for b in s.buttons()), "LightSaber: focus-dot buttons in the window")
s.press("Focus dot ON"); ok(s.pins["SERVO_LASER"] == 0.01, "...focus dot at 1%")
s.press("SET"); ok(s.pins["SERVO_LASER"] == 0 and s.pins["LASER_INITIALIZE"] == 0, "SET switches the dot and the laser rail off")
s = zsim(4); s.run_script("SET_Z_ZERO"); ok(not any("Focus dot" in b for b in s.buttons()), "no laser buttons for other tools")
s = zsim(5); s.run_script("_DK_ZERO_Z"); s.objects["toolhead"]["position"]["z"] = 42.0; s.press("SET")
ok(idx(s, "_DK_TEST_CUT") > idx(s, "SET_GCODE_OFFSET Z=42.000"), "drag knife: SET then runs the test cut (NEXT)")
s = zsim(4); s.save_vars.update(set_material_toolhead="HotJoe", set_material_material="SOFT_WOOD"); s.run_script("_CNC_ZERO_Z_CHOOSE")
ok(s.prompt and "Set Z zero" in s.prompt["title"], "CNC: the Z step is the SET_Z_ZERO window (no touch plate / G38.2)")
s = zsim(3); s.run_script("_LASER_FOCUS"); ok(s.prompt and "Set Z zero" in s.prompt["title"], "laser: focus step is the SET_Z_ZERO window")
# Z not homed after a restart
s = zsim(4, z=0.0, homed=""); s.save_vars.update(rhino_z_safe=1, rhino_park_z=152.5)
ok(raises(lambda: s.run_script("SET_Z_ZERO"), "Bed position") and s.prompt and "Bed position" in s.prompt["title"] and not homes(s), "Z unhomed, bed was parked: asks first, does not move")
s.press("Yes"); ok("SET_KINEMATIC_POSITION Z=152.5 SET_HOMED=Z" in cmds(s) and homes(s) == ["G28 X Y"], "Yes: Z taken from the park height, X/Y homed")
ok(s.prompt and "Set Z zero" in s.prompt["title"], "...and the Set Z zero window opens")
s = zsim(4, z=0.0, homed=""); s.save_vars.update(rhino_z_safe=1, rhino_park_z=152.5); raises(lambda: s.run_script("SET_Z_ZERO"))
s.press("No"); ok(not any(c.startswith("SET_KINEMATIC_POSITION") for c in cmds(s)) and not homes(s), "No: nothing is set or moved")
s = zsim(4, z=0.0, homed=""); s.save_vars.update(rhino_z_safe=0, rhino_park_z=152.5)
ok(raises(lambda: s.run_script("SET_Z_ZERO"), "not left parked") and not s.prompt, "bed not left parked (a job was running): no restore offered")
s = zsim(4, z=0.0, homed="")
ok(raises(lambda: s.run_script("SET_Z_ZERO"), "not left parked"), "no park height ever saved: no restore offered")
s = zsim(4, z=0.0, homed=""); s.save_vars.update(rhino_z_safe=1, rhino_park_z=150.0); raises(lambda: s.run_script("_CNC_ZERO_XY"))
s.press("Yes"); ok(s.prompt and "X/Y" in s.prompt["title"], "restore from the CNC wizard carries on with the same step")
s = zsim(4, z=150.0); s.save_vars["rhino_z_safe"] = 0; s.run_delayed_body("_RHINO_PARK_WATCH")
ok(s.save_vars["rhino_z_safe"] == 1 and abs(s.save_vars["rhino_park_z"] - 150.0) < 1e-9, "watcher records the exact park height")
s.objects["toolhead"]["position"]["z"] = 210.0; s.run_delayed_body("_RHINO_PARK_WATCH"); ok(abs(s.save_vars["rhino_park_z"] - 210.0) < 1e-9, "...and follows the bed while parked")
s = zsim(4, z=200.0); s.run_script("_RHINO_PARK"); ok(s.save_vars.get("rhino_park_z") is not None and s.save_vars["rhino_z_safe"] == 1, "_RHINO_PARK saves the park height")
s = zsim(4, z=150.0); s.run_script("G54"); ok(not any("MOVE=1" in c for c in cmds(s)), "G54 applies the work offset without moving the tool")

s = zsim(3); s.run_script("SET_LASER TOOLHEAD=LightSaber MATERIAL=PLYWOOD"); ok(not any(c.startswith("SET_GCODE_OFFSET Z") for c in cmds(s)), "choosing a laser material leaves the Z zero alone")
s = zsim(5); s.run_script("SET_DRAG_KNIFE TOOLHEAD=DragKnife MATERIAL=VINYL"); ok(not any(c.startswith("SET_GCODE_OFFSET Z") for c in cmds(s)), "...and a knife material")
s = zsim(4); s.run_script("SET_SPINDLE TOOLHEAD=HotJoe MATERIAL=SOFT_WOOD"); ok(not any(c.startswith("SET_GCODE_OFFSET Z") for c in cmds(s)), "...and a spindle material")

s = zsim(4); s.run_script("SET_Z_ZERO"); s.save_vars["rhino_z_safe"] = 1; s.press("Bed up 10 mm"); ok(s.save_vars["rhino_z_safe"] == 0, "leaving the park height clears the parked record at once")
s = zsim(4); s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT")
ok(idx(s, "SET_GCODE_OFFSET X=0 Y=0 Z=0") < idx(s, "G28 X Y"), "cancel clears CNC/knife work offsets before homing and the park move")
s = zsim(4); s.save_vars.update(set_material_toolhead="HotJoe", set_material_material="SOFT_WOOD"); s.run_script("END_PRINT")
ok("SET_GCODE_OFFSET X=0 Y=0 Z=0" in cmds(s), "END_PRINT clears X/Y work offsets for every tool (CNC too)")
s = zsim(1); s.run_script("SET_PRINT TOOLHEAD=BlockOne MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0"); ok("SET_GCODE_OFFSET X=0 Y=0" in cmds(s), "a print never inherits a CNC X/Y work zero")
s = zsim(3); s.run_script("LASER_JOB_SETUP FILE=a.gcode"); ok("SET_GCODE_OFFSET X=0 Y=0" in cmds(s), "laser setup drops any X/Y work zero (files use machine X/Y)")

# ---------------------------------------------------------------- 1.4.1: the laser's rails are powered for the job
def laser_flow(s, file="cut.gcode"):
    s.run_script(f"LASER_JOB_SETUP FILE={file}" if file else "LASER_JOB_SETUP")
    for b in ("All checked - set focus", "SET - Z zero here", "Yes - continue"):
        s.press(b)
rails = lambda s: s.pins.get("LASER_INITIALIZE", 0.0)
s = zsim(3); laser_flow(s)
ok(rails(s) == 0.0 and s.pins.get("SERVO_LASER", 0.0) == 0.0, "1.4.1: through focus and test fire the rails end off (as before)")
s.press("Start the cut")
c = cmds(s)
ok(rails(s) == 1.0 and s.pins.get("SERVO_LASER", 0.0) == 0.0, "1.4.1: Start the cut powers the rails, level still 0")
order = [e[1] for e in s.log if e[0] == "cmd" and e[1] in ('SDCARD_PRINT_FILE FILENAME="cut.gcode"', "ACTIVATE_LASER", "DEACTIVATE_LASER")]
ok(order[-2:] == ['SDCARD_PRINT_FILE FILENAME="cut.gcode"', "ACTIVATE_LASER"], "...after the file is loaded, so a load failure leaves them off")
s.objects["print_stats"]["state"] = "printing"; s.run_script("M3 S800")
ok(rails(s) == 1.0 and abs(s.pins["SERVO_LASER"] - 0.8) < 1e-9, "1.4.1: the file's M3 S800 now fires at 80% (in 1.4.0 the rails were off)")
s.run_script("PAUSE"); ok(rails(s) == 1.0 and s.pins["SERVO_LASER"] == 0.0, "pause drops the level, keeps the rails for the resume")
s.run_script("TOOL_RESUME"); ok(abs(s.pins["SERVO_LASER"] - 0.8) < 1e-9, "TOOL_RESUME puts the level back")
s.run_script("CANCEL_PRINT"); ok(rails(s) == 0.0 and s.pins["SERVO_LASER"] == 0.0, "cancel: rails and level off")
s = zsim(3); laser_flow(s); s.press("Start the cut"); s.save_vars.update(set_material_toolhead="LightSaber")
s.objects["print_stats"]["state"] = "printing"; s.run_script("M3 S800\nEND_PRINT")
ok(rails(s) == 0.0 and s.pins["SERVO_LASER"] == 0.0, "END_PRINT: rails and level off")
s = zsim(3); laser_flow(s); s.press("Start the cut"); s.run_script("EMERGENCY_STOP")
ok(rails(s) == 0.0, "EMERGENCY_STOP: rails off")
s = zsim(3); laser_flow(s, file=None); s.press("Start the cut")
ok(rails(s) == 0.0 and "SDCARD_PRINT_FILE" not in " ".join(cmds(s)), "no FILE given: nothing starts and the rails stay off")
s = zsim(3); laser_flow(s)
def bad_file(p, rest): raise KlipperError("Unable to open file")
s.extra_cmds["SDCARD_PRINT_FILE"] = bad_file
ok(raises(lambda: s.press("Start the cut"), "unable to open") and rails(s) == 0.0, "file fails to load: Klipper stops there, rails stay off")
s = zsim(1); s.run_script("SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE=\"'cut.gcode'\"")
ok(raises(lambda: s.run_script("_LASER_START"), "not LightSaber") and rails(s) == 0.0
   and "SDCARD_PRINT_FILE" not in " ".join(cmds(s)), "_LASER_START typed with BlockOne mounted: refused before the file starts")

# ---------------------------------------------------------------- first start: nothing recorded yet
s = Sim(FIXED).load(); s.save_vars.pop("current_tool", None)
s.fire_delayed("_RESTORE_TOOL_PROMPT")
ok(s.prompt and "which toolhead" in s.prompt["title"].lower() and any("BlockOne" in b for b in s.buttons()), "first start with no recorded tool: asks, listing every tool")
s.press("BlockOne")
ok(s.macro_vars["SWAP_TOOL"]["current_tool"] == 1 and s.save_vars.get("current_tool") == 1, "...choosing one arms the gates and records it for the next restart")

# ---------------------------------------------------------------- job start: the confirm question must not park the head
s = fresh(1); s.objects["print_stats"]["state"] = "printing"
s.run_script("CONFIRM_TOOLHEAD TOOLHEAD=BlockOne MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0")
c = [str(x[1]).split()[0].upper() for x in s.log if x[0] == "cmd"]
ok("PAUSE_BASE" in c and "_TOOLHEAD_PARK_PAUSE_CANCEL" not in c and "PAUSE" not in c, "start question holds the file without Mainsail's park move")

# ---------------------------------------------------------------- nozzle height (paper test)
s = fresh(1); s.run_script("NOZZLE_HEIGHT_CALIBRATE")
c = cmds(s)
ok(c.index("G28") < c.index("SET_GCODE_OFFSET Z=0") and "G1 X307.5 Y208.0 F6000" in c and s.prompt and "BlockOne" in s.prompt["title"],
   "paper test: homes with the print head, clears the offset, goes to the middle, opens the window")
ok(any("Down 0.1" in b for b in s.buttons()) and any("Save" in b for b in s.buttons()), "...with Down/Up steps and Save")
s.objects["toolhead"]["position"]["z"] = 5.0; s.press("Down 1")
ok("G1 Z4.000 F300" in cmds(s) and any("Z 4.00" in t for t in s.prompt["text"]), "Down 1 moves the nozzle 1 mm closer and shows the new height")
s.objects["toolhead"]["position"]["z"] = -9.98; s.press("Down 1")
ok("G1 Z-9.950 F300" in cmds(s), "never below Z's travel limit")
s.objects["toolhead"]["position"]["z"] = -1.24; s.press("Save")
ok(abs(s.save_vars.get("rhino_zcal_blockone", 99) - (-1.34)) < 1e-6 and "SET_GCODE_OFFSET Z=-1.340" in cmds(s), "Save stores where the nozzle touches (paper allowed for) for that head")
s = fresh(3); ok(raises(lambda: s.run_script("NOZZLE_HEIGHT_CALIBRATE"), "print heads") and "G28" not in cmds(s), "refused (and no homing) with the laser mounted")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"; ok(raises(lambda: s.run_script("NOZZLE_HEIGHT_CALIBRATE"), "job"), "refused during a job")
s = fresh(1); s.save_vars.update(rhino_zcal_blockone=-1.34, rhino_zfine_blockone_pla_0_4=0.05)
s.run_script("_RHINO_APPLY_Z TOOLHEAD=BlockOne KEY=PLA_0_4"); ok("SET_GCODE_OFFSET Z=-1.290" in cmds(s), "prints use the paper test plus the material fine-tune")
s = fresh(1); s.run_script("_RHINO_APPLY_Z TOOLHEAD=BlockOne KEY=PLA_0_4")
ok(any(c.startswith("SET_GCODE_OFFSET Z=-0.425") for c in cmds(s)), "no paper test yet: the old material offset is used (with a warning)")
s = fresh(1); s.save_vars.update(rhino_zcal_blockone=-1.34)
s.run_script("SET_PRINT TOOLHEAD=BlockOne MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0"); ok("SET_GCODE_OFFSET Z=-1.340" in cmds(s), "SET_PRINT applies the head's paper test")

# ---------------------------------------------------------------- job start: nothing runs past an open question
s = fresh(1); s.objects["print_stats"]["state"] = "printing"; s.save_vars["rhino_zcal_blockone"] = -1.3
s.run_script('START_JOB TOOLHEAD="BlockOne" MATERIAL="PLA" NOZZLE_SIZE=0.4 EXTRUDER=0')
ok(s.objects["pause_resume"]["is_paused"] and "Proceed" in " ".join(s.buttons()), "file held at the confirm question")
s.press("Proceed")
c = cmds(s)
ok(s.prompt and "PLA" in s.prompt["title"] and s.objects["pause_resume"]["is_paused"] and "PRIME_LINE" not in [x.split()[0] for x in c],
   "PLA question open: file still held, no prime line yet, nothing heating")
ok("RESUME_BASE" not in [x.split()[0] for x in c], "...and the file was not released early")
n = len(s.log); s.press("Bypass")
c2 = [str(x[1]).split()[0] for x in s.log[n:] if x[0] == "cmd"]
ok(c2.index("PRIME_LINE") < c2.index("RESUME_BASE") and not s.objects["pause_resume"]["is_paused"], "answer: prompt closed, prime line, then the file runs")
ok(any("prompt_end" in str(x[1]) for x in s.log[n:n + 3]), "the question closes as soon as it is answered")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"
s.run_script('START_JOB TOOLHEAD="BlockOne" MATERIAL="PETG" NOZZLE_SIZE=0.4 EXTRUDER=0'); s.press("Proceed")
c = [str(x[1]).split()[0] for x in s.log if x[0] == "cmd"]
ok("PRIME_LINE" in c and c.index("PRIME_LINE") < c.index("RESUME_BASE"), "non-PLA: no question, heats, primes, then the file runs")
s = fresh(1); s.run_script("PREHEAT")
ok(s.prompt and "PLA" in s.prompt["title"] and not s.objects["pause_resume"]["is_paused"], "PREHEAT on its own only asks and heats")
n = len(s.log); s.press("Heat"); ok("PRIME_LINE" not in [str(x[1]).split()[0] for x in s.log[n:]], "...and does not prime or start anything")

# ---------------------------------------------------------------- park position: 20 mm in from X/Y max minus 5
s = fresh(1); s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT")
c = cmds(s); ok(c.index("G28 X Y") < c.index("G1 X551.0 Y381.0 F6000"), "cancel ends at the park position X551 Y381")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"; s.run_script("PAUSE")
ok(any(x.startswith("G1 X551.0 Y381.0") for x in cmds(s)) and not any("X571" in x for x in cmds(s)), "pause parks there too, never at X571")

# ---------------------------------------------------------------- 1.4.6 A: SwitchFly per-path materials
def sf(saved=None, printing=False):
    s = fresh(2); s.save_vars.update(set_material_toolhead="SwitchFly", set_material_nozzle_size=0.4)
    if saved: s.save_vars.update(saved)
    s.objects["toolhead"]["homed_axes"] = "xyz"; s.objects["extruder"]["temperature"] = 230.0
    if printing: s.objects["print_stats"]["state"] = "printing"
    return s
def purge_key(s):
    return next((c.split('MATERIAL_KEY="')[1].rstrip('"') for c in cmds(s) if c.startswith("PURGE ")), None)
# SWITCH_T0/T1: the bug (default PLA_0_4 is not a SwitchFly key) is gone, nothing falls back to PLA
s = sf({"switchfly_material_t0": "PETG"}); s.run_script("SWITCH_T0")
ok(purge_key(s) == "PETG_0_4_T0" and s.save_vars["set_material_extruder_index"] == 0, "SWITCH_T0 with no MATERIAL uses path 1's saved material (PETG), not PLA")
s = sf(); s.run_script("SWITCH_T0 MATERIAL=pla")
ok(purge_key(s) == "PLA_0_4_T0" and s.save_vars["switchfly_material_t0"] == "PLA" and s.save_vars["set_material_material"] == "PLA",
   "SWITCH_T0 MATERIAL=pla: short name (any case) builds PLA_0_4_T0 and is remembered for path 1")
s = sf(); s.run_script("SWITCH_T1 MATERIAL=ABS_0_4_T1")
ok(purge_key(s) == "ABS_0_4_T1" and s.save_vars["set_material_extruder_index"] == 1 and s.save_vars["switchfly_material_t1"] == "ABS",
   "SWITCH_T1 accepts a full key, records path 2 for the E-reversal")
s = sf({"switchfly_material_t1": "PLA", "set_material_nozzle_size": 0.8}); s.run_script("SWITCH_T1")
ok(purge_key(s) == "PLA_0_8_T1", "the key follows the saved nozzle size (0.8)")
s = sf(); n = len(s.log)
ok(raises(lambda: s.run_script("SWITCH_T0 MATERIAL=NYLON"), "no NYLON") and not any(c.startswith(("G1", "PURGE", "SET_SERVO")) for c in cmds(s)),
   "unknown material: clear error, nothing moves, no PLA fallback")
s = sf(); ok(raises(lambda: s.run_script("SWITCH_T0 MATERIAL=PLA_0_4_T1"), "Choose one of: PLA, ABS, ASA, PETG"), "path 2's key on path 1 is refused, with the choices listed")
s = sf(); s.run_script("SWITCH_T1")
ok(s.prompt and "Path 2 (T1)" in s.prompt["title"] and set(s.buttons()) >= {"PLA", "ABS", "ASA", "PETG", "Cancel"}
   and not any(c.startswith(("G1", "PURGE")) for c in cmds(s)), "by hand with nothing saved: asks, nothing moves")
s.press("PETG"); ok(purge_key(s) == "PETG_0_4_T1" and s.save_vars["switchfly_material_t1"] == "PETG", "...answering switches with that material")
s = sf(); s.run_script("SWITCH_T1"); s.press("Cancel"); ok(s.prompt is None and not any(c.startswith("PURGE") for c in cmds(s)), "...Cancel closes it, nothing done")
s = sf(printing=True); ok(raises(lambda: s.run_script("SWITCH_T0"), "no material known"), "in a job with nothing saved: error, not a question or PLA")

# START_JOB: the file's MATERIAL fills its path; the other path is asked, holding the file
def sf_job(line, saved=None):
    s = sf(saved, printing=True); s.run_script(line); return s
s = sf_job('START_JOB TOOLHEAD="SwitchFly" MATERIAL="PLA" NOZZLE_SIZE=0.4 EXTRUDER=0', {"switchfly_material_t1": "PETG"})
ok(s.objects["pause_resume"]["is_paused"] and s.prompt and "Path 2 (T1)" in s.prompt["title"], "Orca SwitchFly file: held, path 2 asked")
ok(s.buttons()[0] == "Same as last time (PETG)" and {"PLA", "ABS", "ASA", "PETG"} <= set(s.buttons()), "...'Same as last time' first, then the table's materials")
ok(any("Path 1 (T0): PLA" in t for t in s.prompt["text"]), "...showing path 1 from the file")
s.press("Same as last time")
ok("Confirm" in s.prompt["title"] and any("Path 1 (T0): PLA" in t for t in s.prompt["text"]) and any("Path 2 (T1): PETG" in t for t in s.prompt["text"]),
   "CONFIRM_TOOLHEAD shows both paths")
ok(s.objects["pause_resume"]["is_paused"], "...file still held")
s.press("Proceed")
sv = s.save_vars
ok(sv["switchfly_material_t0"] == "PLA" and sv["switchfly_material_t1"] == "PETG" and sv["set_material_material"] == "PLA"
   and sv["set_material_extruder_index"] == 0, "Proceed: both paths saved for next time, the file's path is the active one")
ok(s.prompt and "PLA" in s.prompt["title"] and s.objects["pause_resume"]["is_paused"], "...then the usual PLA bed question, file still held")
s = sf_job("START_JOB TOOLHEAD=SwitchFly NOZZLE_SIZE=0.4 EXTRUDER=1")
ok(s.prompt and "Path 1 (T0)" in s.prompt["title"] and not any("Same as last time" in b for b in s.buttons()), "no materials, none saved: path 1 asked, no 'Same as last time'")
s.press("ASA"); ok("Path 2 (T1)" in s.prompt["title"] and any("Path 1 (T0): ASA" in t for t in s.prompt["text"]), "...then path 2, showing path 1's answer")
s.press("PETG"); s.press("Proceed")
ok(s.save_vars["set_material_material"] == "PETG" and s.save_vars["set_material_extruder_index"] == 1 and s.save_vars["switchfly_material_t0"] == "ASA",
   "EXTRUDER=1 job: path 2's material is the active one")
s = sf_job("START_JOB TOOLHEAD=SwitchFly MATERIAL_T0=PLA MATERIAL_T1=petg NOZZLE_SIZE=0.4 EXTRUDER=0")
ok(s.prompt and "Confirm" in s.prompt["title"], "MATERIAL_T0 and MATERIAL_T1 given: straight to the confirm question")
s = sf_job("START_JOB TOOLHEAD=SwitchFly MATERIAL_T0=PLA MATERIAL_T1=PLA NOZZLE_SIZE=0.8 EXTRUDER=0"); s.press("Proceed")
ok(s.save_vars["set_material_nozzle_size"] == 0.8, "0.8 mm nozzle job")
s = sf(printing=True)
ok(raises(lambda: s.run_script("START_JOB TOOLHEAD=SwitchFly MATERIAL_T1=NYLON NOZZLE_SIZE=0.4 EXTRUDER=0"), "no NYLON") and not homes(s),
   "unknown path material: stopped before homing")
s = sf(printing=True)
ok(raises(lambda: s.run_script("START_JOB TOOLHEAD=SwitchFly MATERIAL=PLA MATERIAL_T0=PETG NOZZLE_SIZE=0.4 EXTRUDER=0"), "different materials"),
   "MATERIAL and MATERIAL_T0 disagreeing: refused")
s = sf_job("START_JOB TOOLHEAD=SwitchFly MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0"); s.press("Cancel")
ok(s.objects["print_stats"]["state"] == "cancelled", "Cancel at the path question cancels the job")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"
s.run_script('START_JOB TOOLHEAD="BlockOne" MATERIAL="PLA" NOZZLE_SIZE=0.4 EXTRUDER=0')
ok("Confirm" in s.prompt["title"] and any(t == "Material: PLA" for t in s.prompt["text"]), "BlockOne job start unchanged")
# SET_PRINT / SET_TOOLHEAD by hand
s = sf(); before = dict(s.save_vars)
ok(raises(lambda: s.run_script("SET_PRINT TOOLHEAD=SwitchFly MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0 MATERIAL_T1=NYLON"), "no NYLON")
   and s.save_vars == before, "SET_PRINT checks both paths before saving anything")
s = sf({"switchfly_material_t1": "ABS"}); s.run_script("SET_TOOLHEAD TOOLHEAD=SwitchFly MATERIAL=PETG NOZZLE_SIZE=0.4 EXTRUDER=0")
ok(s.save_vars["switchfly_material_t0"] == "PETG" and s.save_vars["switchfly_material_t1"] == "ABS", "SET_TOOLHEAD by hand: sets its path, leaves the other path's saved material")
s = sf(); ok(raises(lambda: s.run_script("SET_PRINT TOOLHEAD=SwitchFly NOZZLE_SIZE=0.4 EXTRUDER=1 MATERIAL_T0=PLA"), "name the material for path 2"),
             "SET_PRINT with no material for the printing path: error, no PLA default")

# ---------------------------------------------------------------- 1.4.6 B: END_PRINT safe-off for every tool
def endjob(slot, name, mat, extra=None):
    s = fresh(slot); s.save_vars.update(set_material_toolhead=name, set_material_material=mat, set_material_nozzle_size=0.4)
    s.macros["_RHINO_CONTROLS_OFF"]["gcode"] = "SET_PIN PIN=dust_vacuum VALUE=0"; s.pins["dust_vacuum"] = 1.0   # a control ticked "switch off when made safe"
    s.macro_vars["TOOL_POWER_STATE"]["active"] = 1
    for k, v in (extra or {}).items(): s.pins[k] = v
    s.run_script("END_PRINT"); return s
for slot, name, mat in ((1, "BlockOne", "PLA"), (2, "SwitchFly", "PLA"), (3, "LightSaber", "PLYWOOD"), (4, "HotJoe", "SOFT_WOOD"), (5, "DragKnife", "VINYL")):
    s = endjob(slot, name, mat, {"Spindle_power": 1.0, "LASER_INITIALIZE": 1.0})
    ok(s.pins["Spindle_power"] == 0 and s.pins["LASER_INITIALIZE"] == 0 and abs(s.pins["SPINDLE_SPEED"] - 0.3) < 1e-9
       and s.macro_vars["TOOL_POWER_STATE"]["active"] == 0, f"END_PRINT {name}: every tool output safe, watchdog stood down")
    ok(s.pins["dust_vacuum"] == 1.0, f"END_PRINT {name}: controls ticked 'switch off when made safe' keep running")
    c = cmds(s); ok(c.index("_TOOL_SAFE_OFF KEEP_CONTROLS=1") < c.index("SET_GCODE_OFFSET X=0 Y=0 Z=0") < c.index("_RHINO_PARK"), f"END_PRINT {name}: after the tool's own shutdown, before the park")
s = endjob(2, "SwitchFly", "PLA", {"SERVO_LASER": 0.075}); ok(s.pins["SERVO_LASER"] == 0.075, "END_PRINT SwitchFly: path servo left alone")
s = endjob(3, "LightSaber", "PLYWOOD", {"SERVO_LASER": 0.6}); ok(s.pins["SERVO_LASER"] == 0, "END_PRINT LightSaber: laser level 0")
for script in ("CANCEL_PRINT", "EMERGENCY_STOP", "SWAP_TOOL TOOL=5"):
    s = fresh(1); s.macros["_RHINO_CONTROLS_OFF"]["gcode"] = "SET_PIN PIN=dust_vacuum VALUE=0"; s.pins["dust_vacuum"] = 1.0
    if script == "CANCEL_PRINT": s.objects["print_stats"]["state"] = "printing"
    s.run_script(script)
    ok(s.pins["dust_vacuum"] == 0, f"{script.split()[0]} still switches ticked controls off")
s = cs(6); s.macros["_RHINO_CONTROLS_OFF"]["gcode"] = "SET_PIN PIN=FoamWire_EN VALUE=0"
s.save_vars.update(set_material_toolhead="FoamWire", set_material_material="FOAM_EPS"); s.run_script("M3 S1000"); s.run_script("END_PRINT")
ok(s.pins["FoamWire_PWR"] == 0 and "_TOOL_SAFE_OFF KEEP_CONTROLS=1" not in cmds(s), "END_PRINT added POWERED tool: full _TOOL_SAFE_OFF, unchanged")

# ---------------------------------------------------------------- 1.4.7: the material record follows the mounted tool
P0 = 0.0005 / 0.02                     # servo duty for path 1 (0 degrees)
P1 = 0.0025 / 0.02                     # servo duty for path 2 (180 degrees)
def confirm_swap(to_slot, from_slot=1, rec=None, servo=None):
    s = fresh(from_slot); s.save_vars.update(rec or {}); s.objects["extruder"]["temperature"] = 25.0
    if servo is not None: s.pins["SERVO_LASER"] = servo
    s.macro_vars["SWAP_TOOL"]["pending_tool"] = to_slot; s.run_script("CONFIRM_TOOL_INSTALL"); return s
def e_out(s, e="10"):
    return s.render("G1", s.macros["G1"]["gcode"], {"E": e, "F": "300"}, f"E{e} F300")
# Swap to SwitchFly with its selector left on path 2 and a BlockOne record at path 1
s = confirm_swap(2, rec={"set_material_toolhead": "BlockOne", "set_material_extruder_index": 0}, servo=P1)
ok(s.save_vars["set_material_toolhead"] == "SwitchFly" and s.save_vars["set_material_extruder_index"] == 0
   and abs(s.pins["SERVO_LASER"] - P0) < 1e-9, "swap to SwitchFly: record says SwitchFly path 1 AND the selector is turned to path 1")
ok("E-10" not in e_out(s), "...so G1 E10 feeds forward on the path the servo really selects")
s = confirm_swap(2, rec={"set_material_toolhead": "SwitchFly", "set_material_extruder_index": 1}, servo=P1)
ok(s.save_vars["set_material_extruder_index"] == 0 and abs(s.pins["SERVO_LASER"] - P0) < 1e-9,
   "swap SwitchFly back on (record path 2): record and selector both reset to path 1, never out of step")
s = confirm_swap(2); c = cmds(s)
ok(not any(x.split()[0].upper() in ("G1", "G0", "G28", "M104", "M109", "PURGE") for x in c if x.strip()),
   "swap to SwitchFly: only the selector servo moves - no axis, no extrusion, no heat")
# Swap to BlockOne after SwitchFly path 2 (bug9 again, through the new macro) and to a laser
s = confirm_swap(1, from_slot=2, rec={"set_material_toolhead": "SwitchFly", "set_material_extruder_index": 1}, servo=P1)
ok(s.save_vars["set_material_toolhead"] == "BlockOne" and s.save_vars["set_material_extruder_index"] == 0
   and abs(s.pins["SERVO_LASER"] - P1) < 1e-9 and "E-10" not in e_out(s), "swap to BlockOne: record re-pointed, E forward, the (unmounted) selector servo not driven")
s = confirm_swap(3, from_slot=2, rec={"set_material_toolhead": "SwitchFly", "set_material_extruder_index": 1}, servo=0.0)
ok(s.save_vars["set_material_toolhead"] == "LightSaber" and s.pins["SERVO_LASER"] == 0.0, "swap to LightSaber: record re-pointed, laser channel untouched")
# After a restart
def restore(slot, rec, servo=P1):
    s = Sim(FIXED).load(); s.save_vars.update(rec); s.pins["SERVO_LASER"] = servo
    s.run_script(f"_RESTORE_TOOL_CONFIRM SLOT={slot}"); return s
s = restore(2, {"current_tool": 2, "set_material_toolhead": "SwitchFly", "set_material_extruder_index": 1})
ok(s.save_vars["set_material_extruder_index"] == 1 and abs(s.pins["SERVO_LASER"] - P1) < 1e-9 and "E-10" in e_out(s),
   "restart, 'Yes - SwitchFly': record already right, nothing moves, path 2 still reverses E")
s = restore(1, {"set_material_toolhead": "SwitchFly", "set_material_extruder_index": 1})
ok(s.save_vars["set_material_toolhead"] == "BlockOne" and s.save_vars["set_material_extruder_index"] == 0 and "E-10" not in e_out(s),
   "restart, BlockOne picked while the record said SwitchFly path 2: re-pointed, E forward")
s = restore(2, {"set_material_toolhead": "BlockOne", "set_material_extruder_index": 0})
ok(s.save_vars["set_material_toolhead"] == "SwitchFly" and abs(s.pins["SERVO_LASER"] - P0) < 1e-9,
   "restart, SwitchFly picked while the record said BlockOne: selector turned to path 1 to match")

shutil.rmtree(ROOT, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
