"""Tuning results (1.9.16): saving per head and per material, ranges, stale revisions, clearing, history, backup item.
Run: python3 dev/test_tuning.py  (needs flask)"""
import json, os, shutil, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-tuning-test-")
CFG = ROOT + "/printer_data/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT
from rhino.portal import create_app, security
from rhino import backup as B

app = create_app(CFG, "http://127.0.0.1:9")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
FILE = CFG + "/myrhino/tuning.json"
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


def post(path, body, hdr=H):
    r = c.post(path, json=body, headers=hdr)
    return r.status_code, r.get_json() or {}


st = c.get("/api/tuning").get_json()
ok(st["ok"] and st["rev"] == 0 and st["runs"] == [], "empty to start")
code, r = post("/api/tuning/result", {"rev": 0, "tool": "BlockOne", "test": "extruder_calibration", "value": 4.3125})
ok(code == 200 and r["heads"]["BlockOne"]["rotation_distance"]["value"] == 4.3125 and r["rev"] == 1, "rotation distance kept for the head")
ok(os.path.isfile(FILE) and json.load(open(FILE))["schema"] == 1, "in myrhino/tuning.json (the config folder: backed up)")
code, r = post("/api/tuning/result", {"rev": 1, "tool": "BlockOne", "test": "pressure_advance", "value": 0.032, "nozzle": 0.4, "material": "PLA"})
m = r.get("materials", {}).get("BlockOne|0.4|PLA", {})
ok(code == 200 and m.get("pressure_advance", {}).get("value") == 0.032, "pressure advance kept per head, nozzle and material")
code, r = post("/api/tuning/result", {"rev": 2, "tool": "BlockOne", "test": "pressure_advance", "value": 0.03, "nozzle": 0.4, "material": "PLA"})
pa = r["materials"]["BlockOne|0.4|PLA"]["pressure_advance"]
ok(pa["value"] == 0.03 and pa["old"] == 0.032, "a new result keeps what it replaced, for old and new side by side")
ok([x["test"] for x in r["runs"]] == ["pressure_advance", "pressure_advance", "extruder_calibration"], "every run is listed, newest first")
code, r = post("/api/tuning/result", {"rev": 1, "tool": "BlockOne", "test": "pressure_advance", "value": 0.03, "nozzle": 0.4, "material": "PLA"})
ok(code == 400 and "another screen" in r.get("error", ""), "a stale revision is refused")
for body, why in [({"test": "nope", "tool": "BlockOne", "value": 1}, "Unknown tuning test"),
                  ({"test": "pressure_advance", "tool": "BlockOne", "value": 3, "nozzle": 0.4, "material": "PLA"}, "from 0 to 2"),
                  ({"test": "pressure_advance", "tool": "BlockOne", "value": 0.03, "material": "PLA"}, "nozzle"),
                  ({"test": "pressure_advance", "tool": "Block One", "value": 0.03, "nozzle": 0.4, "material": "PLA"}, "Which tool"),
                  ({"test": "extruder_calibration", "tool": "BlockOne", "value": True}, "rotation distance must be"),
                  ({"test": "extrusion_multiplier", "tool": "BlockOne", "value": 0.97, "nozzle": 0.4, "material": "PL A"}, "Which material")]:
    code, r = post("/api/tuning/result", {"rev": 3, **body})
    ok(code == 400 and why in r.get("error", ""), f"refused: {why}")
code, r = post("/api/tuning/result", {"rev": 3, "tool": "BlockOne", "test": "pressure_advance", "value": 0.03, "nozzle": 0.4, "material": "PLA"}, hdr={})
ok(code == 400 and "Reload the page" in r.get("error", ""), "a write without the token is refused")
code, r = post("/api/tuning/clear", {"rev": 3, "tool": "BlockOne", "test": "pressure_advance", "nozzle": 0.4, "material": "PLA"})
ok(code == 200 and "pressure_advance" not in r["materials"]["BlockOne|0.4|PLA"] and r["rev"] == 4, "a value can be forgotten (jobs go back to the default)")
h = json.load(open(CFG + "/myrhino/tuning.history.json"))
ok(len(h["revisions"]) == 3 and h["revisions"][0]["rev"] == 3, "older versions are kept")
# laser and drag knife (1.9.23): per tool and material with no nozzle ("stock"), and per tool
rev = c.get("/api/tuning").get_json()["rev"]
code, r = post("/api/tuning/result", {"rev": rev, "tool": "LightSaber", "test": "laser_cut_power", "value": 0.85, "material": "PLYWOOD"})
ok(code == 200 and r["materials"]["LightSaber|PLYWOOD"]["laser_cut_power"]["value"] == 0.85, "laser cut power kept per tool and material, no nozzle")
ok(r["runs"][0] == {"tool": "LightSaber", "test": "laser_cut_power", "value": 0.85, "time": r["runs"][0]["time"], "material": "PLYWOOD"}, "the run names the material, not a nozzle")
code, r = post("/api/tuning/result", {"rev": r["rev"], "tool": "LightSaber", "test": "laser_focus_height", "value": 6.5})
ok(code == 200 and r["heads"]["LightSaber"]["laser_focus_height"]["value"] == 6.5, "focus height kept once per laser")
code, r2 = post("/api/tuning/result", {"rev": r["rev"], "tool": "LightSaber", "test": "laser_focus_height", "value": 0.5})
ok(code == 400 and "from 1 to 30" in r2.get("error", ""), "a focus height under 1 mm is refused (the ramp never goes lower)")
code, r2 = post("/api/tuning/result", {"rev": r["rev"], "tool": "DragKnife", "test": "knife_depth", "value": 0.3})
ok(code == 400 and "material" in r2.get("error", ""), "a knife depth needs a material")
code, r = post("/api/tuning/result", {"rev": r["rev"], "tool": "DragKnife", "test": "knife_depth", "value": 0.3, "material": "VINYL"})
ok(code == 200 and r["materials"]["DragKnife|VINYL"]["knife_depth"]["value"] == 0.3, "knife depth kept per knife and material")
code, r = post("/api/tuning/clear", {"rev": r["rev"], "tool": "DragKnife", "test": "knife_depth", "material": "VINYL"})
ok(code == 200 and "knife_depth" not in r["materials"]["DragKnife|VINYL"], "a knife value can be forgotten")
open(FILE, "w").write("{broken")
code, r = post("/api/tuning/result", {"rev": 4, "tool": "BlockOne", "test": "extruder_calibration", "value": 4.3})
ok(code == 400 and "can't be read" in r["error"] and open(FILE).read() == "{broken", "an unreadable file is kept as it is")
ok(c.get("/api/tuning").get_json()["ok"] is False, "and the state says why")
ok(B.ITEMS["tuning"]["files"] == ["config/myrhino/tuning.json", "config/myrhino/tuning.history.json"], "tuning restores on its own from a backup")
src = open(os.path.join(REPO, "rhino", "tuning.py")).read() + open(os.path.join(REPO, "rhino", "portal", "tuning_routes.py")).read()
ok("moonraker" not in src.lower() and "gcode/script" not in src, "the Portal never sends anything to Klipper for tuning")

shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
