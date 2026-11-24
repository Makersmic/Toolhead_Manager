"""Tuned heater values (1.9.48): rhino/tuned.py and the Portal's /api/tuned routes.
Run: python3 dev/test_tuned.py  (needs flask)"""
import atexit, json, os, re, shutil, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="rhino-tuned-test-")
atexit.register(shutil.rmtree, ROOT, True)
shutil.copytree(os.path.dirname(HERE), ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
CFG = ROOT + "/printer_data/config"
sys.path.insert(0, CFG)
from rhino import pending, sections, tuned
from rhino.errors import Fail
from rhino.paths import resolve
from rhino.portal import create_app, security

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, text=""):
    try:
        fn()
    except Fail as e:
        return text.lower() in str(e).lower()
    return False

paths = resolve(CFG)
HEAT = {"extruder", "heater_bed", "chamber"}
t = tuned.Tuned(paths, now=lambda: 1000)

# --- the repo's files
starter = open(os.path.join(os.path.dirname(HERE), "myrhino", "tuned.cfg")).read()
ok(starter == tuned.render({}, set()), "the starter tuned.cfg is what an empty render gives")
pc = open(os.path.join(os.path.dirname(HERE), "printer.cfg")).read()
inc = [l.strip() for l in pc.split("\n") if l.startswith("[include")]
ok("[include myrhino/tuned.cfg]" in inc and inc.index("[include myrhino/tuned.cfg]") > inc.index("[include tools/3dp.cfg]"), "printer.cfg includes tuned.cfg after tools/3dp.cfg")
inst = open(os.path.join(os.path.dirname(HERE), "install.sh")).read()
ok(inst.count("myrhino/tuned.cfg") >= 2 and "myrhino/tuned.json" in inst, "the installer keeps your tuned.cfg and tuned.json, and puts a starter in place")

# --- naming
for obj, key in (("extruder", "extruder"), ("heater_bed", "heater_bed"), ("heater_generic chamber", "chamber")):
    ok(tuned.heater_key(obj) == key, f"heater key: {obj}")
for bad in ("", None, "heater_generic ", "heater_generic a b", "heater_generic ../x", "fan", "extruder1", "heater_generic x\nY"):
    ok(raises(lambda b=bad: tuned.heater_key(b)), f"refused heater name: {bad!r}")

# --- set, render, override
r = t.set_pid({"rev": 0, "heater": "extruder", "kp": 31.2, "ki": 2.4, "kd": 101.5}, HEAT)
ok(r["rev"] == 1 and r["pid"]["extruder"]["kp"] == 31.2 and r["pid"]["extruder"]["previous"] is None and r["restart_needed"] is True, "keep a heater's PID")
cfg = open(t.cfg).read()
ok("[extruder]\ncontrol: pid\npid_Kp: 31.2\npid_Ki: 2.4\npid_Kd: 101.5" in cfg, "tuned.cfg carries the values")
ok(pending.get(paths) is not None and any("tuned PID for extruder" in c for c in pending.get(paths)["changes"]), "a Klipper restart is marked pending, not done")
base = open(os.path.join(CFG, "tools", "3dp.cfg")).read()
merged = sections.parse_like_klipper(base + "\n" + cfg)
ok(merged.get("extruder", "pid_Kp") == "31.2" and merged.get("extruder", "pid_Ki") == "2.4", "read after tools/3dp.cfg, the tuned value wins (Klipper's later-include rule)")
ok(merged.get("extruder", "rotation_distance").split()[0] == "4.487", "...and the rest of [extruder] is untouched")
r = t.set_pid({"rev": 1, "heater": "extruder", "kp": 33, "ki": 2.5, "kd": 110}, HEAT)
ok(r["pid"]["extruder"]["previous"] == {"kp": 31.2, "ki": 2.4, "kd": 101.5}, "the values before this tune are remembered")
ok(raises(lambda: t.set_pid({"rev": 1, "heater": "extruder", "kp": 1, "ki": 1, "kd": 1}, HEAT), "another screen"), "a stale revision is refused")
for bad in ({"kp": 0}, {"kp": -1}, {"kp": 1e9}, {"kp": "x"}, {"kp": True}, {"kp": float("nan")}, {"ki": None}):
    raw = {"rev": 2, "heater": "extruder", "kp": 1, "ki": 1, "kd": 1, **bad}
    ok(raises(lambda raw=raw: t.set_pid(raw, HEAT)), f"bad gain refused: {bad}")
ok(raises(lambda: t.set_pid({"rev": 2, "heater": "heater_generic dryer", "kp": 1, "ki": 1, "kd": 1}, HEAT), "no heater called dryer"), "a heater Klipper doesn't have is refused")
ok(raises(lambda: t.set_pid("x", HEAT)), "not an object is refused")
r = t.set_pid({"rev": 2, "heater": "heater_generic chamber", "kp": 17.4, "ki": 0.9, "kd": 220}, HEAT)
ok("[heater_generic chamber]" in open(t.cfg).read(), "a chamber heater gets its own section")
# a heater that was removed from the config is left out of the file (an incomplete heater section would stop Klipper)
tuned_cfg = tuned.render(r["pid"], {"extruder", "heater_bed"})
ok("[heater_generic chamber]" not in tuned_cfg and "Klipper has no such heater" in tuned_cfg, "a kept value for a vanished heater isn't written")
sections.parse_like_klipper(tuned_cfg)

# --- clear
r = t.clear({"rev": 3, "heater": "heater_generic chamber"}, HEAT)
ok("heater_generic chamber" not in r["pid"] and "[heater_generic chamber]" not in open(t.cfg).read(), "clear forgets a heater (it goes back to its own config)")
ok(raises(lambda: t.clear({"rev": 4, "heater": "heater_generic chamber"}, HEAT), "nothing is kept"), "clearing what isn't kept is refused")
ok(raises(lambda: t.clear({"rev": 9, "heater": "extruder"}, HEAT), "another screen"), "clear with a stale revision is refused")

# --- files
ok(not [f for f in os.listdir(os.path.dirname(t.cfg)) if f.startswith(".tuned")], "no temp files left behind")
open(t.file, "w").write("not json")
ok(raises(lambda: t.state(), "can't be read"), "an unreadable tuned.json is never overwritten")
ok(open(t.file).read() == "not json", "...and is kept as it is")
os.remove(t.file)
t.set_pid({"rev": 0, "heater": "heater_bed", "kp": 54, "ki": 0.9, "kd": 220}, HEAT)

# --- the Portal
app = create_app(CFG, moonraker_url="http://127.0.0.1:9")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
r = c.get("/api/tuned"); ok(r.json["ok"] and "heater_bed" in r.json["pid"], "GET /api/tuned")
rev = r.json["rev"]
r = c.post("/api/tuned/pid", json={"rev": rev, "heater": "extruder", "kp": 30, "ki": 2, "kd": 100}); ok(r.status_code == 400 and "out of date" in r.json["error"], "a write without the token is refused")
r = c.post("/api/tuned/pid", json={"rev": rev, "heater": "extruder", "kp": 30, "ki": 2, "kd": 100}, headers=H); ok(r.json["ok"] and r.json["pid"]["extruder"]["kd"] == 100, "keep over the Portal")
r = c.post("/api/tuned/pid", json={"rev": rev + 1, "heater": "heater_generic chamber", "kp": 1, "ki": 1, "kd": 1}, headers=H); ok(r.status_code == 400 and "no heater called chamber" in r.json["error"], "the base Rhino has no chamber heater: refused")
r = c.post("/api/tuned/clear", json={"rev": rev + 1, "heater": "extruder"}, headers=H); ok(r.json["ok"] and "extruder" not in r.json["pid"], "clear over the Portal")
ok("pid_Kp: 54" in open(t.cfg).read(), "the bed's values are still in tuned.cfg")

# --- the curve data route
RES = os.path.join(ROOT, "res"); os.makedirs(RES)
os.environ["RHINO_RESONANCE_DIR"] = RES
open(os.path.join(RES, "calibration_data_x_rhino_x.csv"), "w").write("freq,psd_x,psd_y,psd_z,psd_xyz\n5,1,1,1,3\n")
r = c.get("/api/resonance-data?axis=x&name=rhino_x"); ok(r.status_code == 200 and r.data.startswith(b"freq,psd_x"), "the curve data of a run is served")
for q in ("axis=z&name=rhino_x", "axis=x&name=../etc/passwd", "axis=x&name=a/b", "axis=x&name=", "axis=x&name=nothere"):
    r = c.get("/api/resonance-data?" + q); ok(r.status_code == 400, f"curve data refused: {q}")
os.symlink("/etc/passwd", os.path.join(RES, "calibration_data_y_linked.csv"))
r = c.get("/api/resonance-data?axis=y&name=linked"); ok(r.status_code == 400, "a link is never followed")
ok(c.post("/api/tuned/shaper", json={"rev": 1}).status_code == 400, "the shaper route needs the token")

# --- tuning.json knows the material tower's two values
from rhino import tuning
ok(tuning.TESTS["print_temperature"][2:] == (160.0, 290.0) and tuning.TESTS["retraction_length"][0] == "material", "the material tower's temperature and retraction can be recorded")

print(f"\n{len(fails)} failed" if fails else "\nALL PASSED")
sys.exit(1 if fails else 0)
