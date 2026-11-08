"""Your macros (1.9.13): store, validation, refused steps, revisions, delete and undelete, export and import, backup.
Run: python3 dev/test_user_macros.py  (needs flask)"""
import io, json, os, shutil, sys, tempfile, zipfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-macros-test-")
CFG = ROOT + "/printer_data/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT
from rhino.portal import create_app, security
from rhino import user_macros as UM
from rhino import backup as B

app = create_app(CFG, "http://127.0.0.1:9")
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
FILE = CFG + "/myrhino/user_macros.json"
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


PARK = {"name": "Park the head", "toolheads": [], "steps": [
    {"kind": "home", "axes": "all", "onlyIfNeeded": True},
    {"kind": "moveBy", "dx": None, "dy": None, "dz": 10, "speed": 10},
    {"kind": "moveTo", "x": 275, "y": 350, "z": None, "speed": 100}]}


def post(path, body, hdr=HDR):
    return c.post(path, json=body, headers=hdr)


# ---- create, read, list
r = post("/api/user-macros", PARK)
m = r.get_json().get("macro") or {}
ok(r.status_code == 200 and m.get("id", "").startswith("m_") and m.get("rev") == 1, "a macro is saved, with an id and revision 1")
ok(os.path.isfile(FILE) and json.load(open(FILE))["schema"] == 1, "it's in myrhino/user_macros.json (inside the config folder, so it's backed up)")
ok(c.get("/api/user-macros").get_json()["macros"][0]["name"] == "Park the head", "it's listed")
r = post("/api/user-macros", PARK, hdr={})
ok(r.status_code == 400 and "Reload the page" in r.get_json()["error"], "a write without the Portal's token is refused")

# ---- every step kind is accepted with good values, and stored cleaned
ALL = {"name": "Every step", "toolheads": ["BlockOne"], "notes": "test", "steps": [
    {"kind": "home", "axes": "xy"}, {"kind": "moveTo", "x": 10, "speed": 50}, {"kind": "moveBy", "dz": -2.5, "speed": 5},
    {"kind": "temp", "heater": "hotend", "target": 210, "wait": True}, {"kind": "temp", "heater": "bed", "target": 60},
    {"kind": "heatMaterial", "material": "PLA", "wait": True}, {"kind": "fan", "percent": 50}, {"kind": "wait", "seconds": 5},
    {"kind": "macro", "name": "clean_nozzle"}, {"kind": "message", "text": "  Done  "}, {"kind": "gcode", "line": " G1 X1 "}]}
r = post("/api/user-macros", ALL)
s = (r.get_json().get("macro") or {}).get("steps", [])
ok(r.status_code == 200 and len(s) == 11, "every kind of step is accepted")
ok(s and s[0]["onlyIfNeeded"] is False and s[1]["y"] is None and s[5]["wait"] is True, "missing optional fields get their defaults")
ok(s and s[8]["name"] == "CLEAN_NOZZLE" and s[9]["text"] == "Done" and s[10]["line"] == "G1 X1", "names upper-cased, text and lines trimmed")

# ---- refused
BAD = [
    ({"kind": "teleport"}, "unknown step"),
    ({"kind": "home", "axes": "q"}, "home all, XY or Z"),
    ({"kind": "moveTo", "speed": 10}, "at least one axis"),
    ({"kind": "moveTo", "x": 5000, "speed": 10}, "from -2000 to 2000"),
    ({"kind": "moveTo", "x": 5, "speed": 0}, "speed"),
    ({"kind": "moveTo", "x": True, "speed": 10}, "must be a number"),
    ({"kind": "temp", "heater": "bed", "target": 140}, "from 0 to 130"),
    ({"kind": "temp", "heater": "hotend", "target": 400}, "from 0 to 300"),
    ({"kind": "temp", "heater": "chamber", "target": 40}, "hotend or bed"),
    ({"kind": "fan", "percent": 120}, "from 0 to 100"),
    ({"kind": "wait", "seconds": 99999}, "from 0 to 3600"),
    ({"kind": "macro", "name": "_TOOL_SAFE_OFF"}, "internal ones"),
    ({"kind": "macro", "name": "SAVE_CONFIG"}, "can't be run from a macro button"),
    ({"kind": "macro", "name": "FIRMWARE_RESTART"}, "can't be run from a macro button"),
    ({"kind": "gcode", "line": "M112"}, "M112 can't be run"),
    ({"kind": "gcode", "line": "G1 X1\nM112"}, "one line of G-code"),
    ({"kind": "gcode", "line": "set_kinematic_position z=0"}, "SET_KINEMATIC_POSITION can't be run"),
    ({"kind": "gcode", "line": "FORCE_MOVE STEPPER=stepper_z DISTANCE=5 VELOCITY=5"}, "FORCE_MOVE can't be run"),
    ({"kind": "message", "text": 'say "hi"'}, "without quotes"),
    ({"kind": "message", "text": "x" * 121}, "up to 120"),
    ({"kind": "fan", "percent": 10, "extra": 1}, "unknown field extra"),
    ({"kind": "heatMaterial", "wait": True}, "pick a material"),
]
for step, why in BAD:
    r = post("/api/user-macros", {"name": "Bad", "steps": [step]})
    err = (r.get_json() or {}).get("error", "")
    ok(r.status_code == 400 and why in err, f"refused: {json.dumps(step)[:60]} ({err[:70]})")
ok("G28 X" not in json.dumps(UM.NEVER) and "M112" in UM.NEVER, "the never-list names stop, restarts and position overrides")
r = post("/api/user-macros", {"name": "Long", "steps": [{"kind": "wait", "seconds": 1}] * 31})
ok(r.status_code == 400 and "1 to 30 steps" in r.get_json()["error"], "at most 30 steps")
r = post("/api/user-macros", {"name": "Odd", "steps": [{"kind": "wait", "seconds": 1}], "toolheads": ["a b"]})
ok(r.status_code == 400, "toolhead names are checked")

# ---- save with rev, history, revert, delete, undelete
mid = m["id"]
r = post(f"/api/user-macros/{mid}", {"macro": dict(PARK, name="Park"), "rev": 1})
ok(r.status_code == 200 and r.get_json()["macro"]["rev"] == 2, "saved with the revision it started from")
r = post(f"/api/user-macros/{mid}", {"macro": PARK, "rev": 1})
ok(r.status_code == 400 and "changed on another device" in r.get_json()["error"], "a stale revision is refused")
ok(c.get(f"/api/user-macros/{mid}/history").get_json()["revisions"][0]["rev"] == 1, "the old revision is kept")
r = post(f"/api/user-macros/{mid}/revert", {"to": 1})
ok(r.status_code == 200 and r.get_json()["macro"]["name"] == "Park the head" and r.get_json()["macro"]["rev"] == 3, "revert saves the old one as newest")
ok(c.delete(f"/api/user-macros/{mid}", headers=HDR).status_code == 200 and all(x["id"] != mid for x in c.get("/api/user-macros").get_json()["macros"]), "deleted")
ok(any(x["id"] == mid for x in c.get("/api/user-macros").get_json()["deleted"]), "and listed as deleted, for undo")
ok(post(f"/api/user-macros/{mid}/undelete", {}).status_code == 200, "brought back")

# ---- export, import
ex = c.get("/api/user-macros-export").get_json()
ok(ex.get("rhino_user_macros") == 1 and len(ex["macros"]) == 2 and "id" not in ex["macros"][0], "export holds every macro without ids")
r = post("/api/user-macros-import", ex)
names = [x["name"] for x in c.get("/api/user-macros").get_json()["macros"]]
ok(r.status_code == 200 and "Park the head (2)" in names, "import adds copies, a clashing name gets (2)")
bad = dict(ex, macros=ex["macros"] + [{"name": "Evil", "steps": [{"kind": "gcode", "line": "SAVE_CONFIG"}]}])
n = len(names)
r = post("/api/user-macros-import", bad)
ok(r.status_code == 400 and len(c.get("/api/user-macros").get_json()["macros"]) == n, "a file with one bad macro imports nothing")
ok(post("/api/user-macros-import", {"rhino_slice_profiles": 1, "profiles": []}).status_code == 400, "a slice profiles export isn't taken as macros")

# ---- an unreadable file is never overwritten
open(FILE, "w").write("{broken")
r = post("/api/user-macros", PARK)
ok(r.status_code == 400 and "can't be read" in r.get_json()["error"] and open(FILE).read() == "{broken", "an unreadable file is kept as it is, saves refused")
ok(c.get("/api/user-macros").get_json()["ok"] is False, "and the list says why")
os.remove(FILE)

# ---- backup: a restorable item of its own
ok(B.ITEMS["macros"]["files"] == ["config/myrhino/user_macros.json", "config/myrhino/user_macros.history.json"], "macros restore on their own from a backup")

# ---- nothing here talks to Klipper
src = "".join(open(os.path.join(REPO, *p)).read() for p in (("rhino", "user_macros.py"), ("rhino", "portal", "macro_routes.py"), ("rhino", "portal", "store_routes.py"), ("rhino", "versioned_store.py")))
ok("moonraker" not in src.lower() and "gcode/script" not in src and "printer.gcode" not in src, "the Portal never runs a macro or calls Moonraker")

shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
