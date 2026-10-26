"""Job hooks (Add hardware wizard, step 4). Run: python3 dev/test_job_hooks.py   (needs flask)

Storage, validation and the generated _RHINO_HOOKS text. The macros don't call it yet (job_hooks.LIVE is False):
the macros call it since Mike approved the change (2026-10-26, docs/proposal-macro-hooks.md), so these tests also
check myrhino/job_hooks.cfg: always there, rewritten on hooks and hardware saves, every call site in place."""
import os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from rhino import job_hooks, sections, backup

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

GEN = os.path.join(CFG, "myrhino", "custom_tools.cfg")
fake = demo.start_fake()
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json() or {}

# hardware for hooks to switch: a second board, a dust collector and a chamber heater on it
c.post("/api/hardware/boards", json={"name": "aux", "preset": "octopus_v1_1", "link": "can", "canbus_uuid": "aabbccddeeff"}, headers=H)
r = c.post("/api/hardware/devices", json={"device": "dust", "name": "dust", "pins": {"pin": "aux:PG11"}, "expose": ["control", "macros"]}, headers=H)
ok(r.status_code == 200, f"dust collector added {J(r).get('error', '')}")
r = c.post("/api/hardware/devices", json={"device": "heater", "name": "chamber", "pins": {"pin": "aux:PA2", "sensor": "aux:PF4"}, "max_temp": 80}, headers=H)
ok(r.status_code == 200, f"chamber heater added {J(r).get('error', '')}")

st = J(c.get("/api/hooks"))
ok(st["ok"] and st["rev"] == 0 and st["hooks"] == {} and st["live"] is True, "empty to start; live")
ids = [s["id"] for s in st["scopes"]]
ok(ids[0] == "machine" and "category:subtractive" in ids and "tool:LightSaber" in ids, "scopes: machine, categories, each tool")
ok(st["slots"] == ["before_start", "after_start", "before_end", "after_end", "on_cancel", "on_pause", "on_resume"], "the seven slots")


def save(hooks, rev, preview=False):
    r = c.post("/api/preview/hooks" if preview else "/api/hooks", json={"rev": rev, "hooks": hooks}, headers=H)
    return r.status_code, J(r)


for hooks, why in [({"machine": {"before_start": ["G28"]}}, "moves an axis"),
                   ({"machine": {"before_start": ["G1 X10"]}}, "moves an axis"),
                   ({"machine": {"after_start": ["NOT_A_MACRO"]}}, "isn't a macro"),
                   ({"machine": {"after_start": ["M999"]}}, "isn't a G-code"),
                   ({"machine": {"after_start": ["SET_HEATER_TEMPERATURE HEATER=chamber TARGET=90"]}}, "80 C at most"),
                   ({"machine": {"after_start": ["M140 S200"]}}, "heater_bed goes to"),
                   ({"machine": {"after_start": ["SET_HEATER_TEMPERATURE HEATER=nope TARGET=10"]}}, "no heater"),
                   ({"tool:NoSuchTool": {"after_start": ["M117 hi"]}}, "Unknown scope"),
                   ({"machine": {"sometime": ["M117 hi"]}}, "Unknown slot"),
                   ({"machine": {"after_start": ["M117 hi; G28"]}}, "M117 / M118 text"),
                   ({"machine": {"after_start": ["SET_PIN PIN=dust VALUE={1}"]}}, "KEY=VALUE"),
                   ({"machine": {"after_start": ["M117 hi"] * 21}}, "at most 20")]:
    code, r = save(hooks, 0, preview=True)
    ok(code == 400 and why in r.get("error", ""), f"refused ({why}): {r.get('error', '')[:80]}")

code, r = save({"machine": {"after_start": ["G28"]}}, 0, preview=True)
ok(code == 200, "G28 is fine after the Rhino's start")

hooks = {"machine": {"before_start": ["DUST_ON", "SET_HEATER_TEMPERATURE HEATER=chamber TARGET=60"],
                     "after_end": ["SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0"]},
         "category:subtractive": {"after_start": ["RESPOND MSG=cutting"]},
         "tool:LightSaber": {"on_pause": ["M117 laser paused"]}}
code, r = save(hooks, 0)
ok(code == 200 and r.get("rev") == 1, f"hooks saved, revision 1 {r.get('error', '')}")
ok(any("dust" in w and "no end hook" in w for w in r["warnings"]), "warns: dust turned on, never turned off by an end hook")
ok(not any("chamber" in w for w in r["warnings"]), "no warning for the heater: an end hook turns it off")
m = r["macro"]
cancel = m.split("slot == 'on_cancel'")[1]
ok(cancel.split("\n")[1].strip() == "SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0" and "SET_PIN PIN=dust VALUE=0" in cancel,
   "on_cancel turns off everything a hook turned on, first")
ok("{% if cat == \"subtractive\" %}" in m and "{% if tool == \"LightSaber\" %}" in m, "category and tool hooks are guarded")
ok('"LightSaber": "subtractive"' in m, "the macro knows each tool's category")
try:
    sections.parse_like_klipper(m); parsed = True
except Exception:
    parsed = False
ok(parsed, "_RHINO_HOOKS parses the way Klipper reads config")
HCFG = os.path.join(CFG, "myrhino", "job_hooks.cfg")
hc = open(HCFG).read()
ok("DUST_ON" in hc.split("slot == 'before_start'")[1].split("{% elif")[0] and "SET_PIN PIN=dust VALUE=0" in hc, "myrhino/job_hooks.cfg has the saved hooks")
ok("_RHINO_HOOKS" not in open(GEN).read(), "hooks live in their own file, not custom_tools.cfg")
ok(r.get("restart_needed") is True, "a hooks save that changes the file asks for a Klipper restart")

code, r = save({"machine": {"after_start": ["M117 hi"]}}, 0)
ok(code == 400 and "another device" in r["error"], "a stale revision is refused")
code, r = save({"machine": {"after_start": ["M117 hi"]}}, 1)
ok(code == 200 and r["rev"] == 2, "saving from the current revision works")
hist = J(c.get("/api/hooks/history"))["revisions"]
ok(len(hist) == 1 and hist[0]["rev"] == 1 and "category:subtractive" in hist[0]["hooks"], "the previous revision is kept")
ok("config/myrhino/job_hooks.json" in backup.ITEMS["tools"]["files"],
   "job hooks are in the backup")

with open(os.path.join(CFG, "myrhino", "job_hooks.json"), "w") as f:
    f.write("{not json")
r = c.post("/api/hooks", json={"rev": 2, "hooks": {}}, headers=H)
ok(r.status_code == 400 and "can't be read" in J(r)["error"], "an unreadable hooks file is never overwritten")

# ---------------------------------------------------------------- the approved macro change is in place
import re
cfg_text = ""
for root, _dirs, files in os.walk(CFG):
    for f in files:
        if f.endswith(".cfg") and "job_hooks" not in f:
            cfg_text += open(os.path.join(root, f), encoding="utf-8").read()
calls = re.findall(r"^\s*(_RHINO_HOOKS SLOT=\w+|_RHINO_INTERLOCKS|_RHINO_FILAMENT_SENSORS)\b", cfg_text, re.M)
count = {k: calls.count(k) for k in set(calls)}
want = {"_RHINO_HOOKS SLOT=before_start": 5, "_RHINO_HOOKS SLOT=after_start": 2, "_RHINO_HOOKS SLOT=before_end": 1,
        "_RHINO_HOOKS SLOT=after_end": 1, "_RHINO_HOOKS SLOT=on_cancel": 1, "_RHINO_HOOKS SLOT=on_pause": 1,
        "_RHINO_HOOKS SLOT=on_resume": 2, "_RHINO_INTERLOCKS": 10, "_RHINO_FILAMENT_SENSORS": 2}
ok(count == want, f"every call site is in place exactly once ({count})")
for macro in ("_RHINO_HOOKS", "_RHINO_INTERLOCKS", "_RHINO_FILAMENT_SENSORS"):
    ok(f"[gcode_macro {macro}]" in open(HCFG).read(), f"{macro} is defined")

# the shipped starter copy is exactly what an empty machine generates (so a fresh install has the macros)
REPO = os.path.dirname(HERE)
k = job_hooks.Known(set(), {}, {}, {})
from rhino import hw_devices
ok(open(os.path.join(REPO, "myrhino", "job_hooks.cfg")).read() ==
   job_hooks.render_file({}, k, hw_devices.interlock_macro({}, [], []), hw_devices.filament_macro({}, [])),
   "the repo's starter job_hooks.cfg matches an empty render")
ok("[include myrhino/job_hooks.cfg]" in open(os.path.join(REPO, "printer.cfg")).read(), "printer.cfg includes it")

# a hardware save rewrites the file: an interlock appears in _RHINO_INTERLOCKS at once
os.remove(os.path.join(CFG, "myrhino", "job_hooks.json"))        # (the test above left it unreadable on purpose)
r = c.post("/api/hardware/devices", json={"device": "interlock", "name": "lid", "pins": {"pin": "aux:PG12"}, "sensor_type": "mech_nc"}, headers=H)
ok(r.status_code == 200, f"lid interlock added {J(r).get('error', '')}")
il = open(HCFG).read().split("[gcode_macro _RHINO_INTERLOCKS]")[1].split("[gcode_macro")[0]
ok('printer["gcode_button lid"].state == "PRESSED"' in il and "'LightSaber'" in il and "'HotJoe'" in il,
   "the interlock refuses LightSaber and HotJoe jobs while open")
r = c.post("/api/hardware/devices", json={"device": "runout", "name": "runout", "pins": {"pin": "aux:PG13"}, "sensor_type": "mech_no"}, headers=H)
fs = open(HCFG).read().split("[gcode_macro _RHINO_FILAMENT_SENSORS]")[1]
ok("SET_FILAMENT_SENSOR SENSOR=runout ENABLE={on}" in fs and "'BlockOne'" in fs and "'LightSaber'" not in fs,
   "runout sensor: on only with a print head mounted")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
fake.shutdown()
sys.exit(1 if fails else 0)
