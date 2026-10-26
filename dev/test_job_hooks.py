"""Job hooks (Add hardware wizard, step 4). Run: python3 dev/test_job_hooks.py   (needs flask)

Storage, validation and the generated _RHINO_HOOKS text. The macros don't call it yet (job_hooks.LIVE is False):
that change waits for review (docs/proposal-macro-hooks.md), so these tests also check nothing reaches a .cfg."""
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
ok(st["ok"] and st["rev"] == 0 and st["hooks"] == {} and st["live"] is False, "empty to start; not live")
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
ok("_RHINO_HOOKS" not in open(GEN).read(), "nothing reaches a .cfg while hooks aren't live")
ok(not r.get("restart_needed"), "no restart while hooks aren't live")

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

# ---------------------------------------------------------------- the proposed macro change still applies, and only adds
import io, contextlib, proposal_macro_hooks as P
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        P.main(apply=False)
    applied = True
except SystemExit as e:
    applied = False; print("   ", e)
d = buf.getvalue().splitlines()
ok(applied, "docs/proposal-macro-hooks.md: every anchor is found once (the macros haven't drifted)")
ok(d and not [l for l in d if l.startswith("-") and not l.startswith("---")], "the proposed change only adds lines")
ok(sum(1 for l in d if l.strip() in ("+  _RHINO_HOOKS SLOT=before_start", "+  _RHINO_HOOKS SLOT=before_start TOOL={requested_toolhead}")) == 5,
   "before_start: START_JOB and the four *_JOB_SETUP macros")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
fake.shutdown()
sys.exit(1 if fails else 0)
