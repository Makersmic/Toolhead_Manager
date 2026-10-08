"""Motion tests: run Rhino's macros with the simulator following the machine position, and check
where the bed and head actually go - not just which commands were sent.

    python3 dev/test_motion.py            # flows + the full sweep (about a minute)
    python3 dev/test_motion.py --quick    # flows only

Part 1 walks the everyday flows (home, paper test, print, cancel, swap, Set Z zero, CNC, knife,
laser pause/resume) and checks positions against the real limits in printer.cfg.

Part 2 is a sweep: every macro, and every button of the window it opens, from seven machine states
(homed in the middle, near the bed, parked, in the far corner, at the origin, and not homed with and
without a saved park height) with each of the five toolheads, idle and printing. It checks rules
that must always hold:
  R1  no move Klipper would refuse: past position_min/max, a gcode state that was never saved, or
      (starting homed) an axis that has stopped being homed
  R2  Z is never homed with a non-print tool mounted (the probe is on the print heads)
  R3  the bed never rises toward a non-print tool, except where that is the point
      (Set Z zero's Bed up buttons, returning to the cut on resume, the knife's own test cut)
  R4  the nozzle heater is never switched on with a non-print tool mounted
  R5  the saved park height stays true: when X/Y are homed with Z unhomed, Klipper's safe_z_home
      lowers the bed 10 mm blind, so the saved height must go up by the same amount
Jobs only run homed, so the not-homed states are tried idle, with the macros a person can run
(no leading underscore) and their buttons.
Known findings that are waiting on a decision are listed in KNOWN with a note; they are reported
but don't fail the run. Anything new fails it.
"""
import collections
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from klippersim import Sim, KlipperError  # noqa: E402

ROOT = os.path.dirname(HERE)
QUICK = "--quick" in sys.argv
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


BASE = Sim(ROOT, motion=True).load()
LIM_MIN, LIM_MAX = BASE.objects["toolhead"]["axis_minimum"], BASE.objects["toolhead"]["axis_maximum"]
TOOLS = {1: ("BlockOne", "PLA"), 2: ("SwitchFly", "PLA"), 3: ("LightSaber", "PLYWOOD"),
         4: ("HotJoe", "SOFT_WOOD"), 5: ("DragKnife", "VINYL")}
PRINT_HEADS = {1, 2}
SAFE_Z = 150.0          # bed clear of every tool's lowest point (measured on the machine) - deliberately not read from the config
PARK_X = BASE.macro_vars["VARIABLES"]["tool_swap_park_x"]
PARK_Y = BASE.macro_vars["VARIABLES"]["tool_swap_park_y"]


def sim(slot, x=288.0, y=203.0, z=20.0, homed="xyz", job="standby", **save):
    s = BASE.clone()
    name, mat = TOOLS.get(slot, ("", ""))
    s.macro_vars["SWAP_TOOL"]["current_tool"] = slot
    s.save_vars.update(current_tool=slot, set_material_toolhead=name, set_material_material=mat,
                       set_material_nozzle_size=0.4, set_material_extruder_index=0)
    s.save_vars.update(save)
    s.objects["print_stats"]["state"] = job
    s.heats = []

    def heat(p, rest):
        if float(p.get("S", 0) or 0) > 0:
            s.heats.append(tuple(s.stack))
    s.extra_cmds = {"M104": heat, "M109": heat}
    return s.place(x, y, z, homed=homed)


known_flow = []


def known(cond, msg, note):
    """A flow check that fails today because of a finding waiting on a decision."""
    if cond:
        print("NOTE  now passes - make it an ok() check again: " + msg)
    else:
        print(f"KNOWN {msg}: {note}")
        known_flow.append(msg)


def pos(s):
    p = s.objects["toolhead"]["position"]
    return (round(p["x"], 3), round(p["y"], 3), round(p["z"], 3))


def gpos(s):
    p = s.objects["gcode_move"]["gcode_position"]
    return (round(p["x"], 3), round(p["y"], 3), round(p["z"], 3))


def moves(s, start=0, kinds=("move", "restore", "offset_move", "z_hop", "safe_z_xy", "z_tilt")):
    return [m for m in s.moves[start:] if m["kind"] in kinds]


def zs(s, start=0):
    return [m["to"]["z"] for m in moves(s, start)]


def run(s, script):
    try:
        s.run_script(script)
        return None
    except KlipperError as e:
        return str(e)


# =============================================================== Part 1: everyday flows
print("== limits from printer.cfg ==")
ok(LIM_MAX == {"x": 576.0, "y": 406.0, "z": 400.0} and LIM_MIN == {"x": 0.0, "y": 0.0, "z": -10.0},
   f"travel limits read from printer.cfg: X0-576 Y0-406 Z-10-400 ({LIM_MIN}, {LIM_MAX})")

ok(BASE.macro_vars["_RHINO_PARK"]["safe_z"] == SAFE_Z, f"_RHINO_PARK safe_z is the measured {SAFE_Z:g} mm")

print("== homing ==")
s = sim(1, homed="")
s.run_script("G28")
ok(pos(s) == (287.5, 203.0, 10.0) and s._homed() == "xyz", f"G28 with BlockOne: X/Y home, probe at 287.5,203, ends 10 mm up {pos(s)}")
ok([m["kind"] for m in s.moves][:3] == ["blind_z_hop", "home_x", "home_y"], "...after safe_z_home's 10 mm lift (bed moves away from the head)")
s.run_script("Z_TILT_ADJUST")
ok(pos(s)[2] == 20.0 and all(LIM_MIN["x"] <= m["to"]["x"] <= LIM_MAX["x"] for m in moves(s)), "Z_TILT_ADJUST probes at 20 mm, all points inside X/Y travel")
s = sim(1, homed="xy")
ok(run(s, "G1 Z5") and "home" in run(s, "G1 Z5").lower(), "a Z move with Z not homed is refused, like Klipper")
s = sim(1)
ok("out of range" in (run(s, "G1 X577") or "").lower() and pos(s)[0] == 288.0, "X577 is refused (position_max 576) and nothing moves")

print("== paper test (NOZZLE_HEIGHT_CALIBRATE) ==")
s = sim(1, homed="")
s.run_script("NOZZLE_HEIGHT_CALIBRATE")
ok(pos(s) == (307.5, 208.0, 5.0) and gpos(s) == pos(s), f"homes, clears the offset, waits 5 mm above the probe point {pos(s)}")
n = len(s.moves)
s.press("Down 1"); s.press("Down 1"); s.press("Down 1"); s.press("Down 0.1")
ok(abs(pos(s)[2] - 1.9) < 1e-6, f"Down 1 x3 + Down 0.1 = Z 1.9 ({pos(s)[2]})")
s.press("Save")
ok(abs(s.save_vars.get("rhino_zcal_blockone", 99) - 1.8) < 1e-6, "Save stores the touch height less the paper")
ok(min(zs(s)) > LIM_MIN["z"], "never below Z's travel limit")
s = sim(1, z=-9.9)
s.run_script("NOZZLE_HEIGHT_CALIBRATE")
for _ in range(15):
    s.press("Down 1")
ok(pos(s)[2] >= LIM_MIN["z"], f"pressing Down 1 fifteen times from the bottom stops at position_min ({pos(s)[2]})")

print("== printing ==")
s = sim(1, job="printing", rhino_zcal_blockone=-1.3)
s.run_script('START_JOB TOOLHEAD="BlockOne" MATERIAL="PLA" NOZZLE_SIZE=0.4 EXTRUDER=0')
s.press("Proceed"); s.press("Bypass")
pl = [m for m in s.moves if "PRIME_LINE" in m["stack"]]
low = [m for m in pl if m["to"]["z"] < m["frm"]["z"] + 1e-9 and abs(m["to"]["z"] - m["frm"]["z"]) < 1e-9 and m["frm"]["z"] < 0]
length = sum(abs(m["to"]["y"] - m["frm"]["y"]) + abs(m["to"]["x"] - m["frm"]["x"]) for m in low)
ok(pl and all(0 <= m["to"]["x"] <= 550 for m in pl), "prime line stays on the 550 mm bed")
ok(abs(length - 120) < 1e-6, f"prime line is 120 mm long ({length})")
ok(low and all(abs(m["to"]["z"] - (0.2 - 1.3)) < 1e-6 for m in low), "...drawn at 0.2 mm with the paper-test offset (machine Z -1.1)")
ok(abs(pl[-1]["to"]["z"] - (2 - 1.3)) < 1e-6, f"...then lifts 2 mm clear of the line (M6) (machine Z {pl[-1]['to']['z']})")
ok(abs(s.objects["gcode_move"]["homing_origin"]["z"] + 1.3) < 1e-9, "the paper-test offset is still applied after the file is released (M1)")
s.run_script("G1 X100 Y100 Z0.2 F3000")
ok(pos(s) == (100.0, 100.0, -1.1), f"file move G1 X100 Y100 Z0.2 lands at machine {pos(s)}: the first layer uses the paper test")
n = len(s.moves)
s.run_script("END_PRINT")
ok(pos(s)[2] >= SAFE_Z and min(zs(s, n)) >= -1.1, f"END_PRINT: bed only goes down, ends parked at Z{pos(s)[2]}")
ok(gpos(s) == pos(s), "...and no offset is left for the next job (G-code position = machine position)")

print("== G28 guard (M2) ==")
for slot in (3, 4, 5):
    s = sim(slot, homed="")
    err = run(s, "G28") or ""
    ok("only homed with a print head" in err and not s.moves, f"G28 with {TOOLS[slot][0]} mounted is refused before anything moves")
    err = run(s, "G28 Z") or ""
    ok("only homed with a print head" in err, f"...so is G28 Z")
    ok(run(s, "G28 X Y") is None and s._homed() == "xy" and not any(m["kind"] == "home_z" for m in s.moves), "...G28 X Y homes only X and Y")
s = sim(0, homed="")
ok("confirmed print head" in (run(s, "G28") or "") and not s.moves, "after a restart, before the tool question is answered: G28 refused")
ok(run(s, "G28 X") is None and s._homed() == "x", "...G28 X still works")
s = sim(3, homed="")
ok("only homed with a print head" in (run(s, "HOME") or ""), "the old HOME macro goes through the guard too")
s = sim(1, homed="")
ok(run(s, "G28") is None and s._homed() == "xyz", "with BlockOne: G28 homes everything as before")

print("== saved park height stays true (M4) ==")
s = sim(3, x=300, y=200, z=152.5, homed="", rhino_z_safe=1, rhino_park_z=152.5)
s.run_script("SWAP_TOOL TOOL=1")
hop = [m for m in s.moves if m["kind"] == "blind_z_hop"]
ok(len(hop) == 1 and abs(s.save_vars["rhino_park_z"] - 162.5) < 1e-9, "swap after a restart: X/Y homing lowers the bed 10 mm, and the saved park height becomes 162.5")
s = sim(3, x=300, y=200, z=395.0, homed="", rhino_z_safe=1, rhino_park_z=395.0)
ok("bottom of its travel" in (run(s, "G28 X Y") or "") and not s.moves, "parked within 10 mm of the bottom: X/Y homing refused (it would lower the bed past the end)")
s = sim(4, x=300, y=200, z=0.0, homed="", rhino_z_safe=1, rhino_park_z=152.5)
run(s, "SET_Z_ZERO"); s.press("Yes")
ok(abs(s.save_vars["rhino_park_z"] - 152.5) < 1e-9, "Bed position - Yes: Z set first, so the park height is unchanged")

print("== cancel ==")
s = sim(1, x=200, y=150, z=0.3, job="printing")
n = len(s.moves)
s.run_script("CANCEL_PRINT")
z = zs(s, n)
ok(all(b >= a - 1e-9 for a, b in zip([0.3] + z, z)), "cancel never moves the bed up")
ok(pos(s) == (551.0, 381.0, SAFE_Z), f"cancel ends at X551 Y381 with the bed at the park height {pos(s)}")
s = sim(4, x=200, y=150, z=37.0, job="printing")
s.run_script("SET_GCODE_OFFSET X=150 Y=100 Z=35")
s.run_script("CANCEL_PRINT")
ok(pos(s) == (551.0, 381.0, SAFE_Z) and gpos(s) == pos(s), "CNC cancel with work offsets: same park spot, offsets cleared")

print("== tool swap ==")
s = sim(1, z=20.0)
s.run_script("SWAP_TOOL TOOL=3")
first_xy = next((m for m in moves(s) if (m["to"]["x"], m["to"]["y"]) != (m["frm"]["x"], m["frm"]["y"])), None)
ok(first_xy and first_xy["frm"]["z"] >= SAFE_Z, f"swap: the bed is at the safe height before the head moves ({first_xy and first_xy['frm']['z']})")
ok(all(b >= a - 1e-9 for a, b in zip([20.0] + zs(s), zs(s))), "...the bed never rises during the swap")
ok(pos(s)[:2] == (PARK_X, PARK_Y) and not any(m["kind"] == "home_z" for m in s.moves), f"...head at the swap spot X{PARK_X} Y{PARK_Y}, Z never homed")
s.fire_delayed("TRIGGER_PHYSICAL_SWAP_PROMPT")
before = pos(s)
s.run_script("CONFIRM_TOOL_INSTALL")
ok(pos(s) == before and s.macro_vars["SWAP_TOOL"]["current_tool"] == 3, "confirm: LightSaber recorded, nothing moves")

print("== Set Z zero ==")
s = sim(3, z=150.0)
s.run_script("SET_Z_ZERO")
for _ in range(5):
    s.press("Bed up 10")
s.press("Bed up 1 mm"); s.press("Bed up 0.1")
ok(abs(pos(s)[2] - 98.9) < 1e-6, f"Bed up 10 x5, 1, 0.1 from Z150 = Z98.9 ({pos(s)[2]})")
n = len(s.moves)
s.press("SET")
ok(len(moves(s, n)) == 0 and abs(gpos(s)[2]) < 1e-6, "SET: nothing moves, the G-code Z here is now 0")
s.run_script("G90\nG1 Z5")
ok(abs(pos(s)[2] - 103.9) < 1e-6, "G1 Z5 afterwards: the bed drops 5 mm (tool 5 mm above the surface)")
s = sim(4, z=372.0)
s.run_script("SET_Z_ZERO")
s.press("Bed down 10"); s.press("Bed down 10")
ok(pos(s)[2] == 380.0, f"Bed down stops at Z380 ({pos(s)[2]})")
s = sim(4, z=-5.0)
s.run_script("SET_Z_ZERO")
s.press("Bed up 10")
ok(pos(s)[2] == LIM_MIN["z"], f"Bed up stops at position_min ({pos(s)[2]})")

print("== Z back after a restart (bed was parked) ==")
s = sim(4, x=300, y=200, z=0.0, homed="", rhino_z_safe=1, rhino_park_z=152.5)
run(s, "SET_Z_ZERO")
s.press("Yes")
ok(pos(s) == (550.0, 0.0, 152.5) and s._homed() == "xyz", f"Yes: Z taken as 152.5, X/Y homed {pos(s)}")
ok(not any(m["kind"] == "blind_z_hop" for m in s.moves), "...Z is set before X/Y homing, so safe_z_home doesn't lift the bed blind")

print("== CNC (HotJoe) ==")
s = sim(4, x=210.0, y=120.0, z=150.0, set_material_feed_rate=800)
s.run_script("SET_WORK_ZERO")
s.place(z=35.5)
s.run_script("_CNC_ZERO_Z_CHOOSE"); s.press("SET")
s.run_script("G90\nG1 X0 Y0 Z2\nG1 Z-1")
ok(pos(s) == (210.0, 120.0, 34.5), f"after zeroing at X210 Y120, Z at 35.5: G1 X0 Y0 Z-1 cuts at machine {pos(s)}")
s.run_script("G1 X50 Y30")
ok(pos(s)[:2] == (260.0, 150.0), "file X/Y are measured from the work zero")
s.save_vars.update(set_material_toolhead="HotJoe", set_material_material="SOFT_WOOD")
s.run_script("END_PRINT")
ok(gpos(s) == pos(s) and pos(s)[2] >= SAFE_Z, "END_PRINT: work offsets cleared, bed parked")

print("== no X/Y carry-over into the next print ==")
s = sim(4, x=210.0, y=120.0, z=150.0)
s.run_script("SET_WORK_ZERO")
s.macro_vars["SWAP_TOOL"]["current_tool"] = 1
s.run_script("SET_PRINT TOOLHEAD=BlockOne MATERIAL=PLA NOZZLE_SIZE=0.4 EXTRUDER=0")
s.run_script("G90\nG1 X10 Y10 Z5")
ok(pos(s)[:2] == (10.0, 10.0), f"print after a CNC zero: G1 X10 Y10 lands at machine X10 Y10 {pos(s)}")

print("== drag knife test cut ==")
s = sim(5, x=0.0, y=0.0, z=150.0, set_material_feed_rate=800)
s.run_script("_DK_ZERO_Z")
s.place(z=42.0)
n = len(s.moves)
s.press("SET")
cut = moves(s, n)
ok(abs(min(m["to"]["z"] for m in cut) - 41.7) < 1e-6, "test cut goes exactly 0.3 mm below the surface (machine Z 41.7)")
ok(abs(pos(s)[2] - 52.0) < 1e-6, f"...and ends 10 mm above it ({pos(s)[2]})")
ok(all(m["frm"]["z"] >= 42.0 - 1e-6 for m in cut if (m["to"]["x"], m["to"]["y"]) != (m["frm"]["x"], m["frm"]["y"]) and m["to"]["z"] >= 42.0),
   "travel moves are made above the surface")

print("== lifts stop at the end of Z travel (M5) ==")
s = sim(4, z=392.0, set_material_feed_rate=800)
ok(run(s, "_CNC_ABORT") is None and pos(s)[2] == LIM_MAX["z"], f"CNC cancel at Z392: lifts to Z400, not Z407 ({pos(s)[2]})")
s = sim(5, z=390.0)
ok(run(s, "_DK_ABORT") is None and pos(s)[2] == LIM_MAX["z"], "knife cancel at Z390: lifts to Z400")
s = sim(4, z=395.0)
s.save_vars.update(set_material_toolhead="HotJoe", set_material_material="SOFT_WOOD")
ok(run(s, "_CNC_WARMUP") is None and pos(s)[2] == LIM_MAX["z"], "CNC warm-up lift at Z395: stops at Z400")
s = sim(1, z=395.0, set_material_extruder_temp=210.0)
ok(run(s, "FILAMENT_CHANGE") is None and run(s, "_FC_HEAT TOOLHEAD=BlockOne MATERIAL=PLA TEMP=210") is None and pos(s)[2] == LIM_MAX["z"], "filament change at Z395: lifts to Z400 and parks")
s = sim(1, homed="xy", set_material_extruder_temp=210.0)
ok("home the printer first" in (run(s, "FILAMENT_CHANGE") or "") and not s.heats, "filament change with Z not homed: refused before heating")

print("== print-head-only commands (M3) ==")
for cmd in ("PURGE", "PREHEAT", "FILAMENT_CHANGE"):
    for slot in (3, 4, 5):
        s = sim(slot, homed="")
        err = run(s, cmd) or ""
        ok("is for print heads" in err and not s.heats and not s.moves, f"{cmd} with {TOOLS[slot][0]}: refused, no heat, no movement")
s = sim(1, set_material_extruder_temp=210.0)
s.objects["extruder"]["temperature"] = 25.0
ok(run(s, "PURGE") is None and s.heats, "PURGE with BlockOne: heats and purges as before")

print("== nothing to cancel (M7) ==")
s = sim(1)
ok(run(s, "ABORT_TOOL_SWAP") is None and any("No tool swap is running" in str(x) for x in s.log), "ABORT_TOOL_SWAP with no swap: says so, no Klipper error")
ok(run(s, "_FC_ABORT") is None and any("No filament change is running" in str(x) for x in s.log), "filament-change Cancel with none running: says so")
s = sim(1, z=20.0)
s.run_script("SWAP_TOOL TOOL=3")
ok(run(s, "ABORT_TOOL_SWAP") is None and s.macro_vars["SWAP_TOOL"]["pending_tool"] == -1, "ABORT_TOOL_SWAP during a swap still cancels it")

print("== laser pause and resume ==")
s = sim(3, x=120.0, y=80.0, z=150.0, job="printing")
s.run_script("SET_GCODE_OFFSET Z=99")
s.run_script("G90\nG1 X120 Y80 Z3")
ok(pos(s) == (120.0, 80.0, 102.0), "laser job running at G-code Z3 (machine 102)")
s.run_script("SET_LASER_POWER POWER=0.6")
n = len(s.moves)
s.run_script("PAUSE")
p = moves(s, n)
ok(p and p[0]["to"]["z"] > 102.0 and p[0]["to"][ "x"] == 120.0, "pause: lifts first, before moving away")
ok(all(m["to"]["z"] >= 102.0 for m in p), "...the bed never rises toward the laser while pausing")
n = len(s.moves)
s.press("Resume job")
r = moves(s, n)
xy = [m for m in r if (m["to"]["x"], m["to"]["y"]) != (m["frm"]["x"], m["frm"]["y"])]
ok(pos(s) == (120.0, 80.0, 102.0), f"resume: back exactly where it paused {pos(s)}")
ok(all(m["to"]["z"] > 102.0 for m in xy), "...travelling above the work, then down to it")

print("== filament change mid-print ==")
s = sim(1, x=250.0, y=200.0, z=12.0, job="printing", set_material_extruder_temp=210.0)
s.objects["extruder"]["can_extrude"] = True
start = pos(s)
s.run_script("FILAMENT_CHANGE")
s.press("Heat and start")
ok(all(m["to"]["z"] >= 12.0 for m in moves(s)), "filament change only lowers the bed")

# =============================================================== Part 2: sweep
KNOWN = {
    # (rule, macro chain): note shown in the report - findings waiting on a decision. Empty since 1.3.8.
}
# Places where moving the bed up toward a non-print tool is the point
BED_UP_OK = {"_Z_ZERO_MOVE", "TOOL_RESUME", "_DK_TEST_CUT", "_LASER_TEST_FIRE", "_CNC_WARMUP"}
STATES = {
    "middle Z20": dict(x=288, y=203, z=20),
    "near the bed": dict(x=200, y=150, z=0.3),
    "parked": dict(x=551, y=381, z=150),
    "far corner Z380": dict(x=576, y=406, z=380),
    "origin Z5": dict(x=0, y=0, z=5),
    "not homed, parked": dict(x=300, y=200, z=152.5, homed="", rhino_z_safe=1, rhino_park_z=152.5),
    "not homed": dict(x=300, y=200, z=3, homed="", rhino_z_safe=0),
}
if not QUICK:
    print("== sweep: every macro and button, 7 machine states x 5 tools, idle and printing ==")
    macros = sorted(n for n, d in BASE.macros.items() if d.get("gcode", "").strip() and n not in ("G0", "G1"))
    found = collections.defaultdict(set)

    def fire_pending(s):
        for name in list(getattr(s, "pending_delayed", {}) or {}):
            s.pending_delayed.pop(name, None)
            if name in s.delayed and name not in ("TOOL_POWER_WATCHDOG", "_RHINO_PARK_WATCH"):
                try:
                    s.run_delayed_body(name)
                except KlipperError:
                    pass

    def attempt(slot, st, job, mac, button=None):
        s = sim(slot, job=job, **st)
        s.motion_strict = False
        s.started_homed = s._homed() == "xyz"
        s.start_park = s.save_vars.get("rhino_park_z") if s.save_vars.get("rhino_z_safe") == 1 else None
        for script, is_button in ((mac, False), (button, True)):
            if script is None:
                continue
            try:
                s.press(script) if is_button else s.run_script(script)
            except (KlipperError, AssertionError):
                pass
            except Exception:
                pass            # macro called without its required parameters: not a motion question
            fire_pending(s)
        return s

    def check(s, slot, where):
        tool = TOOLS[slot][0]
        for msg, stack in s.motion_errors:
            if msg.startswith("Must home") and not s.started_homed:
                continue        # refused before anything happened: Klipper's own safety net
            found[("R1", " > ".join(stack[-3:]))].add(f"{tool}, {where}: {msg}")
        for m in s.moves:
            chain = " > ".join(m["stack"][-3:])
            if slot not in PRINT_HEADS and m["kind"] == "home_z":
                found[("R2", chain)].add(f"{tool}, {where}")
            if (slot not in PRINT_HEADS and m["kind"] in ("move", "restore", "offset_move") and m["frm"]
                    and m["to"]["z"] < m["frm"]["z"] - 1e-6 and not BED_UP_OK & set(m["stack"])):
                found[("R3", chain)].add(f"{tool}, {where}: Z{m['frm']['z']:g} -> Z{m['to']['z']:g}")
        if s.start_park is not None and s.save_vars.get("rhino_z_safe") == 1 and "z" not in s._homed():
            hops = sum(m.get("dz", 0) for m in s.moves if m["kind"] == "blind_z_hop")
            if abs(s.save_vars.get("rhino_park_z", 0) - (s.start_park + hops)) > 1e-6:
                found[("R5", where.split(", ")[-1].split(" / ")[0])].add(f"{tool}, {where}: bed lowered {hops:g} mm, saved height {s.save_vars.get('rhino_park_z')}")
        if slot not in PRINT_HEADS:
            for stack in s.heats:
                found[("R4", " > ".join(stack[-3:]))].add(f"{tool}, {where}")

    runs = 0
    for slot in TOOLS:
        for stn, st in STATES.items():
            homed = st.get("homed", "xyz") == "xyz"
            for job in (("standby", "printing") if homed else ("standby",)):
                for mac in (macros if homed else [m for m in macros if not m.startswith("_")]):
                    s = attempt(slot, st, job, mac)
                    check(s, slot, f"{stn}, {job}, {mac}")
                    runs += 1
                    for lab in [b[0] for b in (s.prompt or {}).get("buttons", []) + (s.prompt or {}).get("footer", [])]:
                        s2 = attempt(slot, st, job, mac, lab)
                        check(s2, slot, f"{stn}, {job}, {mac} / {lab}")
                        runs += 1
    print(f"   {runs} runs")
    rules = {"R1": "a move Klipper would refuse", "R2": "Z homed with a non-print tool",
             "R3": "bed raised toward a non-print tool", "R4": "nozzle heated with a non-print tool",
             "R5": "saved park height no longer matches the bed"}
    known_seen = set()
    for key in sorted(found):
        rule, chain = key
        k = next((kk for kk in KNOWN if kk[0] == rule and (kk[1] == chain or chain.startswith(kk[1] + " >")
                                                          or chain.split(" > ")[0] == kk[1])), None)
        ex = sorted(found[key])[0]
        if k:
            known_seen.add(k)
            print(f"KNOWN {rule} {chain}: {KNOWN[k]}  (e.g. {ex})")
        else:
            ok(False, f"{rule} {rules[rule]}: {chain}  ({len(found[key])} cases, e.g. {ex})")
    for k in KNOWN:
        if k not in known_seen:
            print(f"NOTE  {k[0]} {k[1]} is listed as known but no longer happens - remove it from KNOWN")
    ok(True, f"sweep: {len(known_seen)} known findings waiting on a decision, nothing new")

if known_flow:
    print(f"\n{len(known_flow)} known flow finding(s) waiting on a decision")
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
