"""Tests for tool controls, tool macros and the restart banner.
Run: python3 dev/test_extras.py   (needs flask, jinja2)"""
import json, os, shutil, subprocess, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from klippersim import Sim, KlipperError

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, contains=None):
    try: fn()
    except KlipperError as e: return contains is None or contains.lower() in str(e).lower()
    return False

# PC0 described as a MOSFET output, the others as logic pins
with open(os.path.join(CFG, "myrhino", "umbilical.json"), "w") as f:
    json.dump({"pins": ["PE0", "PE1", "PE2", "PE3", "PF4", "PB0", {"pin": "PB1", "type": "logic"},
                        {"pin": "PC0", "type": "mosfet", "label": "FAN4 header"}, {"pin": "PC1", "type": "logic"}]}, f)

fake = demo.start_fake()
S = demo.STATE
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
mon = app.config["MONITOR"]
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json()

vac = {"name": "needle_vacuum", "role": "switch", "pin": "PC1", "invert": True, "make_macros": True, "mounted_only": True, "purpose": "Vacuum relay"}
fan = {"name": "needle_fan", "role": "fan", "pin": "PC0", "max_power": 0.8, "make_macros": True}
lid = {"name": "needle_lid", "role": "input", "pin": "PB1", "pullup": True, "invert": True, "on_press": {"action": "pause"}, "on_release": {"action": "message", "message": "lid closed"}}
purge = {"name": "needle_purge", "purpose": "Run the needle in the air", "mounted_only": True,
         "body": "NEEDLE_VACUUM_ON\nM3 S300\nG4 P500\nM5\n{% if params.PARK|default(0)|int %}\n  G1 X0 Y0 F6000\n{% endif %}"}

# ---------------------------------------------------------------- preview
r = c.post("/api/preview/control", json={"draft": {"name": "Needle"}, "item": vac}, headers=H)
ok(r.status_code == 200 and "[output_pin needle_vacuum]" in J(r)["text"] and "pin: !PC1" in J(r)["text"] and "NEEDLE_VACUUM_ON" in J(r)["text"],
   "control preview shows the section and its macros")
r = c.post("/api/preview/control", json={"draft": {"name": "Needle"}, "item": {**lid, "pin": "PC0"}}, headers=H)
ok(r.status_code == 400 and "MOSFET" in J(r)["error"], "an input on a MOSFET pin is refused (pin type from umbilical.json)")
r = c.post("/api/preview/control", json={"draft": {"name": "Needle"}, "item": {**vac, "name": "spindle_speed"}}, headers=H)
ok(r.status_code == 400 and "already used" in J(r)["error"], "control name already used in the config refused")
r = c.post("/api/preview/control", json={"draft": {"name": "Needle"}, "item": {**vac, "pin": "PE0"}}, headers=H)
ok(r.status_code == 400 and "stepper_z" in J(r)["error"], "control on a pin the config uses refused")
r = c.post("/api/preview/control", json={"draft": {"name": "Needle", "controls": [vac]}, "item": {**fan, "pin": "PC1"}}, headers=H)
ok(r.status_code == 400 and "already used by this tool" in J(r)["error"], "two controls on one pin refused")
r = c.post("/api/preview/macro", json={"draft": {"name": "Needle", "controls": [vac]}, "item": purge}, headers=H)
ok(r.status_code == 200 and J(r)["text"].startswith("[gcode_macro NEEDLE_PURGE]") and "description: Run the needle in the air" in J(r)["text"]
   and not J(r)["warnings"], "macro preview: upper-cased name, description, no warnings (it calls a control macro)")
r = c.post("/api/preview/macro", json={"draft": {"name": "Needle"}, "item": {**purge, "body": "{% if x %}\nG1 X1"}}, headers=H)
ok(r.status_code == 400 and "template error" in J(r)["error"], "Jinja error caught before saving")
r = c.post("/api/preview/macro", json={"draft": {"name": "Needle", "controls": [vac]}, "item": {**purge, "name": "needle_vacuum_on"}}, headers=H)
ok(r.status_code == 400, "macro name clashing with a control's macro refused")
r = c.post("/api/preview/macro", json={"draft": {"name": "Needle"}, "item": {"name": "zz_test", "body": "G1 X1 ; move\nSAVE_CONFIG\nTYPO_CMD"}}, headers=H)
w = " ".join(J(r)["warnings"])
ok(r.status_code == 200 and "comment" in w and "SAVE_CONFIG" in w and "TYPO_CMD" in w, "warnings: cut-off comment, risky command, unknown command")
for bad in ("G28", "M3", "SET_PIN", "LEDOFF", "PAUSE"):
    rr = c.post("/api/preview/macro", json={"draft": {"name": "Needle"}, "item": {"name": bad, "body": "G1 X1"}}, headers=H)
    ok(rr.status_code == 400, f"macro name {bad} refused")

# ---------------------------------------------------------------- add with controls + macros
good = {"name": "Needle", "kind": "NEEDLE", "power_pin": "SPINDLE_SPEED", "controls": [vac, fan, lid], "macros": [purge]}
r = c.post("/api/tools", json=good, headers=H)
ok(r.status_code == 200, f"tool with 3 controls and a macro added: {J(r).get('error', '')}")
prev = J(c.post("/api/preview/control", json={"tool": "Needle", "item": {**vac, "original": "needle_vacuum"}, "controls": [vac, fan, lid]}, headers=H))
cfg = open(os.path.join(CFG, "myrhino", "custom_tools.cfg")).read()
ok(prev["text"].split("\n# also switched off")[0].strip() in cfg, "preview text is exactly what was written")
ok(J(c.get("/api/options"))["free_pins"] == [], "control pins are taken from the free list")
d = J(c.get("/api/tools/Needle"))["tool"]
ok([x["name"] for x in d["control_macros"]] == ["NEEDLE_VACUUM_ON", "NEEDLE_VACUUM_OFF", "NEEDLE_FAN_SET", "NEEDLE_FAN_OFF"], "generated macros listed for the editor")
lint = subprocess.run([sys.executable, os.path.join(HERE, "lint_rhino.py"), CFG], capture_output=True, text=True)
ok(lint.returncode == 0, "generated config passes the lint " + (lint.stdout[-300:] if lint.returncode else ""))

# ---------------------------------------------------------------- in (simulated) Klipper
def sim(slot):
    s = Sim(CFG).load(); s.macro_vars["SWAP_TOOL"]["current_tool"] = slot; return s
s = sim(1)
ok(s.pins.get("needle_vacuum") == 0, "control output_pin loads, off")
ok(raises(lambda: s.run_script("NEEDLE_VACUUM_ON"), "not mounted"), "control macro refused when the tool is not mounted")
ok(raises(lambda: s.run_script("NEEDLE_PURGE"), "not mounted"), "tool macro refused when the tool is not mounted")
s = sim(6); s.run_script("NEEDLE_VACUUM_ON"); ok(s.pins["needle_vacuum"] == 1, "NEEDLE_VACUUM_ON switches it on")
s.run_script("NEEDLE_FAN_SET SPEED=0.5"); ok(s.fans["needle_fan"] == 0.5, "NEEDLE_FAN_SET drives the fan")
s.run_script("_TOOL_SAFE_OFF"); ok(s.pins["needle_vacuum"] == 0 and s.fans["needle_fan"] == 0, "_TOOL_SAFE_OFF switches the controls off")
s = sim(6); s.run_script("NEEDLE_VACUUM_ON"); s.run_script("SWAP_TOOL TOOL=1"); ok(s.pins["needle_vacuum"] == 0, "a tool swap switches the controls off")
s = sim(6); s.run_script("NEEDLE_VACUUM_ON"); s.objects["print_stats"]["state"] = "printing"; s.run_script("CANCEL_PRINT"); ok(s.pins["needle_vacuum"] == 0, "cancel switches the controls off")
s = sim(6); s.run_script("NEEDLE_PURGE"); ok(s.pins["needle_vacuum"] == 1, "tool macro runs when mounted")
s = sim(6); s.objects["print_stats"]["state"] = "printing"
s.run_script(s.render("needle_lid", s.config_sections["gcode_button needle_lid"]["press_gcode"]))
ok(any("pausing" in str(x) for x in s.log), "lid switch pauses a running job")
ok(s.config_sections["gcode_button needle_lid"]["pin"] == "^!PB1", "switch-to-ground wiring: pull-up and invert")

# ---------------------------------------------------------------- edit + remove
r = c.post("/api/tools/Needle/edit", json={"controls": [vac, fan], "macros": []}, headers=H)
ok(r.status_code == 200 and "controls" in J(r)["changes"] and "macros" in J(r)["changes"], "edit replaces the controls and macros")
ok("gcode_button needle_lid" not in open(os.path.join(CFG, "myrhino", "custom_tools.cfg")).read(), "removed control is gone from the cfg")
ok(J(c.get("/api/options"))["free_pins"] == ["PB1"], "its pin is free again")

# ---------------------------------------------------------------- banner: waiting changes, job timer, auto-restart
st = J(c.get("/api/state"))
ok(st["restart_pending"] and st["pending"]["changes"][:2] == ["added Needle", "edited Needle: controls, macros"], f"banner lists what is waiting: {st['pending']['changes']}")
S.update(print_state="printing", filename="part.gcode", progress=0.5, print_duration=1800.0, total_duration=1900.0, estimated_time=3600.0)
mon.tick(1000.0)
st = J(c.get("/api/state")); job = st["printer"]["job"]
ok(st["printer"]["restart_blocked"] and job["timing"]["method"] == "slicer" and abs(job["timing"]["remaining"] - 1800) < 1,
   "slicer estimate: 30 min left")
S.update(estimated_time=0.0, print_duration=0.0, progress=0.25, total_duration=600.0, filename="cut.nc")
mon.tick(1005.0)
job = J(c.get("/api/state"))["printer"]["job"]
ok(job["timing"]["method"] == "file" and abs(job["timing"]["remaining"] - 1800) < 1, "laser/CNC file: estimate from progress (10 min for 25%)")
S["print_state"] = "paused"; mon.tick(1010.0); mon.tick(1015.0); mon.tick(1020.0)
job = J(c.get("/api/state"))["printer"]["job"]
ok(job["paused_s"] == 10.0 and job["paused_since"] == 1010.0, f"pause time tracked for the banner ({job['paused_s']}, {job['paused_since']})")
ok(c.post("/api/restart", headers=H).status_code == 400 and S["restarts"] == 0, "restart refused during the job")
r = c.post("/api/tools/Needle/edit", json={"notes": "edited mid-job"}, headers=H)
ok(r.status_code == 200 and not J(r)["restart_needed"] and "edited Needle: notes" not in J(c.get("/api/state"))["pending"]["changes"],
   "a notes-only edit needs no restart (notes never reach Klipper)")
r = c.post("/api/tools/Needle/edit", json={"cap": 0.9}, headers=H)
ok(r.status_code == 200 and "edited Needle: power_cap" in J(c.get("/api/state"))["pending"]["changes"], "editing during a job is saved and queued")
ok(c.post("/api/restart/auto", json={"on": True}, headers=H).status_code == 200, "auto-restart armed")
S["print_state"] = "printing"; mon.tick(1025.0)
S["print_state"] = "complete"; mon.tick(1030.0)
ok(S["restarts"] == 0 and J(c.get("/api/state"))["pending"]["restart_at"] == 1060.0, "job finished: restart scheduled 30 s later")
mon.tick(1045.0); ok(S["restarts"] == 0, "...not yet")
mon.tick(1061.0); ok(S["restarts"] == 1 and not J(c.get("/api/state"))["restart_pending"], "auto-restart happened and cleared the banner")
# error end: no automatic restart
c.post("/api/tools/Needle/edit", json={"cap": 0.8}, headers=H); c.post("/api/restart/auto", json={"on": True}, headers=H)
S["print_state"] = "printing"; mon.tick(1100.0); S["print_state"] = "error"; mon.tick(1105.0); mon.tick(1200.0)
p = J(c.get("/api/state"))["pending"]
ok(S["restarts"] == 1 and p and "error" in p["note"] and not p["auto_restart"], "a job ending in error is not followed by an automatic restart")
# a restart from anywhere else clears the banner
import time as _t
S["print_state"] = "standby"; S["klippy"] = "startup"; mon.tick(_t.time() + 5); S["klippy"] = "ready"; mon.tick(_t.time() + 10)
ok(not J(c.get("/api/state"))["restart_pending"], "a Klipper restart from Mainsail or the console also clears the banner")

fake.shutdown()
shutil.rmtree(os.path.dirname(os.path.dirname(CFG)), ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
