"""Bed mesh (1.6.0): myrhino/bed_mesh.cfg and the mesh step of a print start, in simulated Klipper.
Run from anywhere:  python3 dev/test_mesh.py   (needs: pip install jinja2)

The simulator is not real Klipper: BED_MESH_* are modelled (dev/klippersim.py), probing is not."""
import ast, os, re, shutil, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from klippersim import Sim, KlipperError

ROOT = os.path.dirname(HERE)
fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, contains=None):
    try: fn()
    except KlipperError as e: return contains is None or contains.lower() in str(e).lower()
    return False
def cmds(s, start=0): return [str(x[1]) for x in s.log[start:] if x[0] == "cmd"]
def words(s, start=0): return [c.split()[0] for c in cmds(s, start)]

BASE = Sim(ROOT).load()
MBASE = Sim(ROOT, motion=True).load()
def fresh(slot, motion=False, **save):
    s = (MBASE if motion else BASE).clone()
    s.macro_vars["SWAP_TOOL"]["current_tool"] = slot
    s.save_vars.update(save)
    return s
def mesh(s): return s.objects["bed_mesh"]
def meta(s): return s.save_vars.get("mesh_meta", {})

print("== set up ==")
ok("bed_mesh" in BASE.config_sections and "bed_mesh" in BASE.objects, "printer.cfg has a [bed_mesh] section (BM1: check its area on the machine)")
cfg = BASE.config_sections["bed_mesh"]
mn = [float(v) for v in cfg["mesh_min"].split(",")]; mx = [float(v) for v in cfg["mesh_max"].split(",")]
pr = BASE.config_sections["probe"]; ox, oy = float(pr["x_offset"]), float(pr["y_offset"])
lo, hi = BASE.objects["toolhead"]["axis_minimum"], BASE.objects["toolhead"]["axis_maximum"]
ok(lo["x"] <= mn[0] - ox and mx[0] - ox <= hi["x"] and lo["y"] <= mn[1] - oy and mx[1] - oy <= hi["y"],
   f"every probe point can be reached by the nozzle (probe {mn}-{mx} less offset {ox},{oy})")
ok(len([int(v) for v in cfg["probe_count"].split(",")]) == 2 and max(int(v) for v in cfg["probe_count"].split(",")) <= 6,
   "probe_count fits Klipper's default lagrange interpolation (6 or fewer per axis)")

print("== RHINO_MESH_CALIBRATE ==")
for slot, name in ((3, "LightSaber"), (4, "HotJoe"), (5, "DragKnife")):
    s = fresh(slot)
    ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=bed-60 BED=60"), "print head") and "BED_MESH_CALIBRATE" not in words(s),
       f"refused with {name} mounted (the probe is on the print heads), nothing probed")
s = fresh(0)
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=bed-60"), "no toolhead confirmed"), "refused with no tool confirmed")
s = fresh(1); s.objects["print_stats"]["state"] = "printing"
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=bed-60"), "job"), "refused during a job")
for bad in ('"my mesh"', "bed/60", "x" * 33, ""):
    s = fresh(1)
    ok(raises(lambda: s.run_script(f"RHINO_MESH_CALIBRATE PROFILE={bad} BED=60"), "PROFILE must"), f"bad name refused: {bad[:12]!r}")
s = fresh(1)
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=adaptive-1 BED=60"), "adaptive"), "adaptive-* names are Klipper's, refused")
s = fresh(1)
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=hot BED=150"), "130"), "bed above heater_bed max_temp refused")
s = fresh(1)
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=hot BED=60 SOAK=90"), "SOAK"), "soak over an hour refused")

s = fresh(1, motion=True).place(288, 203, 20, homed="xy")
s.mesh_points = [[0.05, 0.0, -0.02, 0.0, 0.03], [0.0, 0.01, 0.0, -0.01, 0.0], [-0.04, 0.0, 0.02, 0.0, 0.06]]
s.run_script("RHINO_MESH_CALIBRATE PROFILE=bed-60 BED=60 SOAK=5 WHEN=1761000000")
w = words(s)
ok(w.index("G28") < w.index("M190") < w.index("G4") < w.index("Z_TILT_ADJUST") < w.index("BED_MESH_CALIBRATE"),
   "Z not homed: homes, heats the bed, soaks, levels the gantry, then probes")
ok("M190 S60.0" in cmds(s) and "G4 P300000" in cmds(s), "bed to 60°C and a 5 minute soak")
bm = [m for m in s.moves if m["kind"] == "bed_mesh"]
ok(len(bm) > 0 and all(lo[a] <= m["to"][a] <= hi[a] for m in bm for a in "xyz") and not s.motion_errors,
   f"probe moves all inside travel ({len(bm)} moves)")
xs = sorted({round(m["to"]["x"], 3) for m in bm}); ys = sorted({round(m["to"]["y"], 3) for m in bm})
ok(xs[0] == mn[0] - ox and xs[-1] == mx[0] - ox and ys[0] == mn[1] - oy and ys[-1] == mx[1] - oy,
   f"the nozzle goes to the probe points less the probe offset (X {xs[0]}-{xs[-1]}, Y {ys[0]}-{ys[-1]})")
ok(mesh(s)["profile_name"] == "bed-60" and "bed-60" in mesh(s)["profiles"], "the new mesh is saved as bed-60 and loaded")
ok(meta(s).get("bed-60") == {"bed": 60.0, "tool": "BlockOne", "when": 1761000000}, f"recorded: bed 60, BlockOne, time ({meta(s).get('bed-60')})")
ok(isinstance(ast.literal_eval(repr(meta(s))), dict), "mesh_meta is a plain literal (variables.save can hold it)")

s = fresh(2); s.objects["toolhead"]["homed_axes"] = "xyz"
s.run_script("RHINO_MESH_CALIBRATE PROFILE=cold BED=0 TILT=0")
w = words(s)
ok("G28" not in w and "M190" not in w and "G4" not in w and "Z_TILT_ADJUST" not in w and "M140" in w,
   "already homed, cold bed, TILT=0: bed off, no soak, no levelling, just probes")
ok(meta(s)["cold"]["bed"] == 0.0 and meta(s)["cold"]["tool"] == "SwitchFly", "a cold mesh is recorded at 0°C with SwitchFly")

print("== records follow the meshes ==")
s = fresh(1); s.objects["toolhead"]["homed_axes"] = "xyz"
s.save_vars["mesh_meta"] = {"gone": {"bed": 80.0, "tool": "BlockOne", "when": 1}}
s.run_script("RHINO_MESH_CALIBRATE PROFILE=bed-60 BED=60 SOAK=0")
ok("gone" not in meta(s), "a record for a mesh Klipper no longer has is dropped")
s.run_script("RHINO_MESH_REMOVE PROFILE=bed-60")
ok("bed-60" not in mesh(s)["profiles"] and "bed-60" not in meta(s), "RHINO_MESH_REMOVE removes the mesh and its record")
ok(raises(lambda: s.run_script("RHINO_MESH_REMOVE PROFILE=nothing"), "no mesh called"), "removing a mesh that isn't there says so")
s = fresh(1).seed_meshes([60]); s.objects["print_stats"]["state"] = "paused"
ok(raises(lambda: s.run_script("RHINO_MESH_REMOVE PROFILE=bed-60"), "job") and "bed-60" in mesh(s)["profiles"], "not during a job")

print("== print start: the mesh for the bed temperature ==")
def start(slot=1, material="PETG", meshes=(), extra=None, motion=False):
    s = fresh(slot, motion=motion)
    if meshes: s.seed_meshes(meshes)
    if extra: extra(s)
    s.objects["print_stats"]["state"] = "printing"
    s.run_script(f'START_JOB TOOLHEAD="BlockOne" MATERIAL="{material}" NOZZLE_SIZE=0.4 EXTRUDER=0')
    s.press("Proceed")
    return s
s = start(meshes=[0])
bed = s.save_vars.get("set_material_bed_temp")
ok(isinstance(bed, (int, float)) and bed >= 40, f"PETG heats the bed ({bed}°C), so the cold mesh does not count")

s = start(meshes=[int(bed)])
w = words(s)
ok(f"BED_MESH_PROFILE" in w and f"LOAD=bed-{int(bed)}" in " ".join(cmds(s)), f"a saved mesh made at {int(bed)}°C is loaded")
ok(not s.prompt and w.index("BED_MESH_PROFILE") < w.index("PRIME_LINE") < w.index("RESUME_BASE") and not s.objects["pause_resume"]["is_paused"],
   "...no question: load, prime, then the file runs (as before 1.6.0)")

def near(s):
    s.seed_meshes([int(bed) - 4, int(bed) + 3])
s = start(extra=near)
ok(f"LOAD=bed-{int(bed) + 3}" in " ".join(cmds(s)), f"two within 5°C: the closer one ({int(bed) + 3}°C) is used")
def tie(s):
    s.seed_meshes([int(bed)])
    s.objects["bed_mesh"]["profiles"]["newer"] = {"points": [[0.0]], "mesh_params": {}}
    s.save_vars["mesh_meta"]["newer"] = {"bed": float(int(bed)), "tool": "BlockOne", "when": 99}
s = start(extra=tie)
ok("LOAD=newer" in " ".join(cmds(s)), "same temperature: the newest is used")
def adaptive(s):
    s.objects["bed_mesh"]["profiles"]["adaptive-AB12"] = {"points": [[0.0]], "mesh_params": {}}
    s.save_vars["mesh_meta"] = {"adaptive-AB12": {"bed": float(int(bed)), "tool": "BlockOne", "when": 5}}
s = start(extra=adaptive)
ok(s.prompt and "LOAD=adaptive" not in " ".join(cmds(s)), "an adaptive (one-print) mesh is never picked for a print")

print("== print start: no mesh for this temperature ==")
s = start(meshes=[int(bed) + 30])
w = words(s)
ok(s.prompt and "No bed mesh" in s.prompt["title"] and s.objects["pause_resume"]["is_paused"], "asks, with the file held")
ok("BED_MESH_CALIBRATE" not in w and "PRIME_LINE" not in w and "RESUME_BASE" not in w, "...nothing probed, primed or released yet")
b = s.buttons()
ok(any("Probe a new mesh" in x for x in b) and any(f"bed-{int(bed) + 30}" in x for x in b) and any("without" in x for x in b)
   and any("Cancel job" in x for x in b), f"buttons: probe now, use the closest, print without, cancel ({b})")

s2 = start(meshes=[int(bed) + 30]); n = len(s2.log); s2.objects["toolhead"]["homed_axes"] = "xyz"; s2.press("Probe")
w = words(s2, n)
ok(w.index("BED_MESH_CALIBRATE") < w.index("PRIME_LINE") < w.index("RESUME_BASE") and not s2.prompt,
   "Probe: closes the question, probes, primes, then the file runs")
p = f"bed-{int(bed)}"
ok(mesh(s2)["profile_name"] == p and meta(s2).get(p, {}).get("bed") == float(bed) and meta(s2)[p]["when"] == 0,
   f"...saved as {p} with its bed temperature (time unknown: Studio stamps it)")
s2 = start(meshes=[int(bed) + 30]); n = len(s2.log); s2.press("Use")
ok(f"BED_MESH_PROFILE LOAD=bed-{int(bed) + 30}" in cmds(s2, n) and "PRIME_LINE" in words(s2, n), "Use the closest: loads it and goes on")
def loaded(s):
    s.seed_meshes([int(bed) + 30]); s.objects["bed_mesh"]["profile_name"] = f"bed-{int(bed) + 30}"
s2 = start(extra=loaded); n = len(s2.log); s2.press("without")
ok("BED_MESH_CLEAR" in words(s2, n) and mesh(s2)["profile_name"] == "" and "PRIME_LINE" in words(s2, n),
   "Print without: a mesh left loaded is switched off, then it goes on")
s2 = start(meshes=[int(bed) + 30]); n = len(s2.log); s2.press("Cancel job")
w = words(s2, n)
ok("CANCEL_PRINT" in w and "BED_MESH_CALIBRATE" not in w and "PRIME_LINE" not in w and not s2.prompt, "Cancel job: cancels, nothing probed or primed")
s2 = start()
ok(s2.prompt and not any(x.startswith("Use") for x in s2.buttons()), "no saved meshes at all: no 'Use' button")
def plain(s):
    s.objects["bed_mesh"]["profiles"]["default"] = {"points": [[0.0]], "mesh_params": {}}
s2 = start(extra=plain)
ok(any("default (temperature not recorded)" in x for x in s2.buttons()), "a mesh made outside Rhino (no record) is offered, marked as such")

print("== print start: cold bed (PLA, bed bypassed) ==")
s = start(material="PLA", meshes=[0, 60]); n = len(s.log); s.press("Bypass")
ok("BED_MESH_PROFILE LOAD=bed-cold" in cmds(s, n), "the cold mesh is used for a cold bed")
s = start(material="PLA", meshes=[60]); n = len(s.log); s.press("Bypass")
ok(s.prompt and "cold bed" in s.prompt["title"], "no cold mesh: asks ('No bed mesh for a cold bed')")

print("== spindle (CNC): never cut with a bed mesh ==")
s = fresh(4).seed_meshes([60]); s.objects["bed_mesh"]["profile_name"] = "bed-60"; s.objects["toolhead"]["homed_axes"] = "xyz"
s.run_script("SET_Z_ZERO")
ok(mesh(s)["profile_name"] == "" and "BED_MESH_CLEAR" in words(s), "SET_Z_ZERO with HotJoe switches the mesh off before the zero is set")
for slot, name in ((3, "LightSaber"), (5, "DragKnife")):
    s = fresh(slot).seed_meshes([60]); s.objects["bed_mesh"]["profile_name"] = "bed-60"; s.objects["toolhead"]["homed_axes"] = "xyz"
    s.run_script("SET_Z_ZERO")
    ok(mesh(s)["profile_name"] == "bed-60", f"{name} keeps the mesh (focus / blade depth stay even)")
s = fresh(4).seed_meshes([60]); s.objects["bed_mesh"]["profile_name"] = "bed-60"; s.pins["Spindle_power"] = 1.0
ok(raises(lambda: s.run_script("_CNC_START"), "cut depth") and s.pins["Spindle_power"] == 0 and "SDCARD_PRINT_FILE" not in words(s),
   "a mesh loaded again after SET_Z_ZERO: the spindle job stops, spindle off, file not started")
s = fresh(4).seed_meshes([60]); s.objects["bed_mesh"]["profile_name"] = "bed-60"; s.pins["Spindle_power"] = 1.0
ok(raises(lambda: s.run_script("_RHINO_JOB_GO"), "cut depth") and s.pins["Spindle_power"] == 0, "...and the same at the end of a START_JOB")
s = fresh(4)
ok(not raises(lambda: s.run_script("_RHINO_MESH_CNC_CHECK")), "no mesh loaded: the spindle check lets it run")
s = fresh(3).seed_meshes([60]); s.objects["bed_mesh"]["profile_name"] = "bed-60"
ok(not raises(lambda: s.run_script("_RHINO_MESH_CNC_CHECK")), "the laser with a mesh: allowed")

print("== a config without [bed_mesh] ==")
d = tempfile.mkdtemp(prefix="rhino-mesh-")
shutil.copytree(ROOT, d + "/c", ignore=shutil.ignore_patterns("__pycache__", "registry_backups", "node_modules", ".git"))
txt = open(d + "/c/printer.cfg").read()
txt = re.sub(r"^\[bed_mesh\]\n(?:[^\[\n].*\n)*", "", txt, flags=re.M)
open(d + "/c/printer.cfg", "w").write(txt)
NB = Sim(d + "/c").load(); shutil.rmtree(d, ignore_errors=True)
ok("bed_mesh" not in NB.config_sections and "bed_mesh" not in NB.objects, "(test copy has no [bed_mesh])")
s = NB.clone(); s.macro_vars["SWAP_TOOL"]["current_tool"] = 1; s.objects["print_stats"]["state"] = "printing"
s.run_script('START_JOB TOOLHEAD="BlockOne" MATERIAL="PETG" NOZZLE_SIZE=0.4 EXTRUDER=0'); s.press("Proceed")
w = words(s)
ok(not s.prompt and "PRIME_LINE" in w and w.index("PRIME_LINE") < w.index("RESUME_BASE"), "print start runs exactly as before: no question, primes, runs")
s = NB.clone(); s.macro_vars["SWAP_TOOL"]["current_tool"] = 1
ok(raises(lambda: s.run_script("RHINO_MESH_CALIBRATE PROFILE=x"), "not set up"), "RHINO_MESH_CALIBRATE says bed mesh is not set up")
s = NB.clone(); s.macro_vars["SWAP_TOOL"]["current_tool"] = 4; s.objects["toolhead"]["homed_axes"] = "xyz"
ok(not raises(lambda: s.run_script("SET_Z_ZERO")) and not raises(lambda: s.run_script("_RHINO_MESH_CNC_CHECK")), "spindle macros work without [bed_mesh]")

print()
print("ALL PASSED" if not fails else f"{len(fails)} FAILED:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
