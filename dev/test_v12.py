"""Tests for 1.2: Admin lists, tool categories, shared umbilical outputs, system hardware, custom status
codes and the Task Library / Task Books.  Run: python3 dev/test_v12.py  (needs flask, jinja2)"""
import datetime, json, os, shutil, subprocess, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from klippersim import Sim

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

fake = demo.start_fake()
S = demo.STATE
clock = {"t": datetime.datetime(2026, 3, 1, 9, 0).timestamp()}
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
maint = app.config["MAINT"]
maint.now = lambda: clock["t"]
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json()
def post(url, body=None): return c.post(url, json=body or {}, headers=H)

# ---------------------------------------------------------------- admin lists: categories and sub-types
o = J(c.get("/api/options"))
ok([x["value"] for x in o["categories"]] == ["additive", "subtractive", "passive"], "step 1 offers Additive / Subtractive / Passive")
cats = {k["value"]: k["category"] for k in o["kinds"]}
ok(cats["PRINT_HEAD"] == "additive" and cats["HOT_WIRE"] == "subtractive" and cats["PASSIVE"] == "passive", "every sub-type sits under a category")
lst = J(c.get("/api/lists"))
kinds = lst["kinds"] + [{"label": "Foam knife", "category": "subtractive", "behaviour": "POWERED", "cap": 0.6, "max_on_s": 120,
                         "checklist": ["Blade sharp"], "materials": {"FOAM": {"power": 0.4, "feed_rate": 500}}}]
r = post("/api/lists", {"kinds": kinds})
ok(r.status_code == 200 and any(k["id"] == "FOAM_KNIFE" for k in J(r)["kinds"]), "a new sub-type can be added on the Admin screen")
ok(post("/api/lists", {"kinds": lst["kinds"] + [{"label": "Bad", "category": "passive", "behaviour": "POWERED"}]}).status_code == 400,
   "a passive sub-type cannot be powered")
ok(post("/api/lists", {"kinds": [k for k in lst["kinds"] if k["id"] != "NEEDLE"]}).status_code == 400, "built-in sub-types cannot be deleted")
ok(post("/api/lists", {"materials": {"additive": "PLA, petg, Wood fill", "subtractive": [], "passive": []}}).status_code == 200 and
   J(c.get("/api/lists"))["materials"]["additive"] == ["PLA", "PETG", "WOOD_FILL"], "material names are cleaned (upper case, _)")
ok(post("/api/lists", {"nozzles": "0.4, 0.6, 9"}).status_code == 400, "nozzle sizes are range-checked")

# ---------------------------------------------------------------- the 21 contacts + shared outputs
cts = {x["contact"]: x for x in o["contacts"]}
ok(len(cts) == 21 and cts[18]["output"] == "SPINDLE_SPEED" and cts[16]["output"] == "SERVO_LASER" and cts[11]["output"] == "Spindle_power",
   "contacts map to the outputs that drive them (18 SPINDLE_SPEED, 16 SERVO_LASER, 11 Spindle_power)")
ok(cts[20].get("warning") and "PD12" in cts[20]["warning"], "contact 20 (PD12 on the pin map) is flagged: nothing in printer.cfg uses it")
r = post("/api/tools", {"name": "Router", "kind": "FOAM_KNIFE", "outputs": [
    {"role": "power", "source": "contact:18"}, {"role": "switch", "source": "contact:11"}, {"role": "switch", "source": "pin:PB1"}],
    "contacts": [12, 13]})
ok(r.status_code == 200, f"tool with a PWM signal and two switch outputs (shared 11 + new pin): {J(r).get('error', '')}")
t = J(c.get("/api/tools/Router"))["tool"]
ok(t["power_pin"] == "SPINDLE_SPEED" and t["enable_pin"] == "Spindle_power" and t["also_on"] == ["Router_EN2"] and t["category"] == "subtractive",
   "outputs become power_pin / enable_pin / also_on")
ok(t["contacts"] == [11, 12, 13, 18], f"contacts the tool uses: outputs + ticked ones ({t['contacts']})")
ok(t["power_cap"] == 0.6 and t["max_on_s"] == 120 and "FOAM" in t["materials"], "the new sub-type's starting values are used")
cfg = open(os.path.join(CFG, "myrhino", "custom_tools.cfg")).read()
ok("[output_pin Router_EN2]" in cfg and "pin: PB1" in cfg, "a new switch output is created")
ok(post("/api/tools", {"name": "Two", "kind": "NEEDLE", "outputs": [{"role": "switch", "source": "contact:11"}]}).status_code == 400,
   "a powered tool needs exactly one main power output")
ok(post("/api/tools", {"name": "Two", "kind": "NEEDLE", "outputs": [{"role": "power", "source": "contact:20"}]}).status_code == 400,
   "a contact nothing drives cannot be chosen")
s = Sim(CFG).load(); s.macro_vars["SWAP_TOOL"]["current_tool"] = 6
s.run_script("SET_TOOL_POWER POWER=0.5")
ok(s.pins["Spindle_power"] == 1 and s.pins["Router_EN2"] == 1, "power on switches every switch output on")
s.run_script("M5"); ok(s.pins["Spindle_power"] == 0 and s.pins["Router_EN2"] == 0, "M5 switches them off")
s.run_script("SET_TOOL_POWER POWER=0.5"); s.run_script("_TOOL_SAFE_OFF")
ok(s.pins["Router_EN2"] == 0, "_TOOL_SAFE_OFF switches them off")
r = post("/api/tools/Router/edit", {"contacts": [12, 13, 21]})
ok(r.status_code == 200 and not J(r)["restart_needed"] and J(c.get("/api/tools/Router"))["tool"]["contacts"] == [11, 12, 13, 18, 21],
   "editing the ticked contacts is portal-only (no restart)")

# ---------------------------------------------------------------- system hardware
light = {"name": "enclosure_light", "role": "switch", "pin": "PD15", "category": "lighting", "purpose": "Enclosure LED strip",
         "make_macros": True, "safe_off": False}
r = post("/api/preview/hardware", {"item": light})
ok(r.status_code == 200 and "[output_pin enclosure_light]" in J(r)["text"] and "ENCLOSURE_LIGHT_ON" in J(r)["text"]
   and "not mounted" not in J(r)["text"], "hardware preview: section and macros, no mounted-tool guard")
ok(post("/api/preview/hardware", {"item": {**light, "pin": "PB0"}}).status_code == 400, "a pin on the umbilical is refused for system hardware")
ok(post("/api/preview/hardware", {"item": {**light, "pin": "PA8"}}).status_code == 400, "a pin the config uses is refused")
ok(post("/api/preview/hardware", {"item": {**light, "pin": "PB1"}}).status_code == 400, "a pin a tool uses is refused")
ok(post("/api/preview/hardware", {"item": {**light, "category": "nope"}}).status_code == 400, "a category is required")
r = post("/api/hardware", light); ok(r.status_code == 200 and J(r)["restart_pending"], "system hardware added (restart queued)")
vac = {"name": "dust_vacuum", "role": "switch", "pin": "PB10", "category": "air", "purpose": "Shop vacuum relay", "make_macros": True, "safe_off": True}
ok(post("/api/hardware", vac).status_code == 200, "a second piece of hardware")
ok(post("/api/hardware", {**vac, "name": "enclosure_light"}).status_code == 400, "duplicate names refused")
hw = {x["name"]: x for x in J(c.get("/api/state"))["pins"]["hardware"]}
ok(set(hw) == {"enclosure_light", "dust_vacuum"} and hw["dust_vacuum"]["header"] == "HE2", "Pins & outputs lists it with the board header")
s = Sim(CFG).load()
s.run_script("ENCLOSURE_LIGHT_ON"); ok(s.pins["enclosure_light"] == 1, "its macro works whatever tool is mounted")
s.run_script("DUST_VACUUM_ON"); s.run_script("_TOOL_SAFE_OFF")
ok(s.pins["dust_vacuum"] == 0 and s.pins["enclosure_light"] == 1, "safe-off switches only the hardware marked for it")
r = post("/api/tools", {"name": "Sander", "kind": "POWERED", "outputs": [{"role": "power", "source": "pin:PC1"}, {"role": "switch", "source": "output:dust_vacuum"}]})
ok(r.status_code == 200, f"a tool can switch system hardware on with it (vacuum with the sander): {J(r).get('error', '')}")
ok(c.delete("/api/hardware/dust_vacuum", headers=H).status_code == 400, "hardware a tool switches cannot be removed")
r = post("/api/hardware", {**light, "original": "enclosure_light", "name": "case_light"})
ok(r.status_code == 200 and "case_light" in {x["name"] for x in J(c.get("/api/state"))["pins"]["hardware"]}, "rename hardware")
lint = subprocess.run([sys.executable, os.path.join(HERE, "lint_rhino.py"), CFG], capture_output=True, text=True)
ok(lint.returncode == 0, "generated config passes the lint " + (lint.stdout[-300:] if lint.returncode else ""))

# ---------------------------------------------------------------- Task Library + Task Books
lib = J(c.get("/api/maint/tasklib"))
books = {b["name"]: b for b in lib["books"]}
ok("3D print head" in books and "Rhino motion system and frame" in books and len(lib["templates"]) > 20, "starter Task Books and library tasks seeded")
ok(lib["suggested"]["LightSaber"] == "b_laser" and lib["suggested"]["Router"] == "b_powered", "a book is suggested per tool")
r = post("/api/maint/books/b_printhead/assign", {"asset": "tool:BlockOne"})
ok(r.status_code == 200 and J(r)["added"] == 5, "assigning a book adds all its tasks")
ok(post("/api/maint/books/b_printhead/assign", {"asset": "tool:BlockOne"}).status_code == 200 and
   sum(1 for t in J(c.get("/api/maint"))["tasks"] if t["asset"] == "tool:BlockOne") == 5, "assigning twice adds nothing twice")
ok(post("/api/maint/books/b_printhead/assign", {"asset": "machine:frame"}).status_code == 400, "a book with tool meters cannot go on the machine")
r = post("/api/maint/books/b_rhino/assign", {"asset": "machine"})
ov = J(c.get("/api/maint"))
ok(r.status_code == 200 and any(t["asset"] == "machine:motion_xy" and t["title"].startswith("Check and tension") for t in ov["tasks"]),
   "the machine book puts each task in its own area")
tpl = next(x for x in lib["templates"] if x["id"] == "tool:nozzle_clean")
r = post("/api/maint/templates/tool:nozzle_clean", {**tpl, "title": "Clean and inspect the nozzle", "steps": "Heat\nBrush\nLook"})
ok(r.status_code == 200 and J(r)["updated_tasks"] == 1, "editing a library task...")
t = next(x for x in J(c.get("/api/maint"))["tasks"] if (x.get("link") or {}).get("template") == "tool:nozzle_clean")
ok(t["title"] == "Clean and inspect the nozzle" and t["steps"] == ["Heat", "Brush", "Look"] and t["link_info"]["book_name"] == "3D print head",
   "...updates the linked task on the tool")
r = post(f"/api/maint/tasks/{t['id']}", {"title": "changed here", "enabled": True})
ok(J(r).get("linked") and next(x for x in J(c.get("/api/maint"))["tasks"] if x["id"] == t["id"])["title"] == "Clean and inspect the nozzle",
   "a linked task's definition is the library's (only its own settings change)")
r = post("/api/maint/books", {"name": "Wide nozzle care", "templates": ["tool:nozzle_clean", "tool:nozzle_replace"]})
wide = J(r)["id"]; ok(r.status_code == 200, "a new Task Book")
ok(post("/api/maint/books", {"name": "wide nozzle care", "templates": ["tool:nozzle_clean"]}).status_code == 400, "book names are unique")
post(f"/api/maint/books/{wide}/assign", {"asset": "tool:SwitchFly"})
post(f"/api/maint/books/{wide}", {"name": "Wide nozzle care", "templates": ["tool:nozzle_clean", "tool:nozzle_replace", "tool:hotend_check"]})
sf = [x for x in J(c.get("/api/maint"))["tasks"] if x["asset"] == "tool:SwitchFly" and not x.get("archived")]
ok(len(sf) == 3, "adding a task to an assigned book adds it to the tool")
post(f"/api/maint/books/{wide}", {"name": "Wide nozzle care", "templates": ["tool:nozzle_clean"]})
sf = [x for x in J(c.get("/api/maint"))["tasks"] if x["asset"] == "tool:SwitchFly" and not x.get("archived")]
ok(len(sf) == 1, "taking a task out of the book archives it on the tool")
post(f"/api/maint/books/{wide}/assign", {"asset": "tool:SwitchFly", "on": False})
ok(not [x for x in J(c.get("/api/maint"))["tasks"] if x["asset"] == "tool:SwitchFly" and not x.get("archived")], "unassigning the book archives its tasks")
r = post(f"/api/maint/tasks/{t['id']}", {"detach": True})
ok(J(r).get("detached") and not next(x for x in J(c.get("/api/maint"))["tasks"] if x["id"] == t["id"]).get("link"), "detach a task to customise it")
r = post("/api/maint/templates", {"title": "Wipe the enclosure window", "type": "clean", "rules": [{"kind": "time", "every": 2, "unit": "weeks"}], "area": "frame"})
uid = J(r)["id"]; ok(r.status_code == 200, "a library task of your own")
ok(post(f"/api/maint/templates/{uid}/assign", {"asset": "hw:case_light"}).status_code == 200 and
   any(x["asset"] == "hw:case_light" for x in J(c.get("/api/maint"))["tasks"]), "a library task can go on system hardware")
r = c.delete(f"/api/maint/templates/{uid}", headers=H)
ok(J(r)["detached"] == 1 and any(x["asset"] == "hw:case_light" and not x.get("link") for x in J(c.get("/api/maint"))["tasks"]),
   "deleting a library task keeps its tasks, unlinked")

# ---------------------------------------------------------------- status codes
ml = J(c.get("/api/maint/lists"))
custom = ml["statuses"]["custom"]
ok([x["label"] for x in custom][:1] == ["Pending - Waiting on parts"], "default custom status: Pending - Waiting on parts")
r = post("/api/maint/tasks", {"title": "Replace the Y belt", "asset": "machine:motion_xy", "type": "replace",
                              "rules": [{"kind": "time", "every": 10, "unit": "days", "lead": 2}]})
belt = J(r)["id"]
clock["t"] += 11 * 86400
st = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}[belt]["status"]
ok(st["state"] == "overdue", "task overdue")
ok(post(f"/api/maint/tasks/{belt}/status", {"status": "s_parts"}).status_code == 400, "Waiting on parts needs a note")
r = post(f"/api/maint/tasks/{belt}/status", {"status": "s_parts", "note": "GT2 belt ordered"})
ov = J(c.get("/api/maint")); st = {x["id"]: x for x in ov["tasks"]}[belt]["status"]
ok(r.status_code == 200 and st["hold"]["label"] == "Pending - Waiting on parts" and st["state"] == "overdue", "status set; it keeps ageing (clock rule: none)")
ok(ov["counts"]["overdue"] == 0 and ov["counts"]["held"] == 1, "a status in its own group leaves the overdue count")
maint.write_boot_cfg(force=True)
ok("Replace the Y belt" not in open(os.path.join(CFG, "myrhino", "maintenance_status.cfg")).read(), "...and the boot reminder (boot prompt rule off)")
h = J(c.get("/api/maint/history"))["records"][0]
ok(h["action"] == "status" and h["status"] == "Pending - Waiting on parts" and h["notes"] == "GT2 belt ordered", "status change is in the work log")
# a status of your own with a paused clock and an expiry
custom = J(c.get("/api/maint/lists"))["statuses"]["custom"]
mine = {"label": "Waiting for the weekend", "color": "pink", "list": "upcoming", "boot_prompt": False, "note_required": False,
        "clock": "pause", "expiry": "days", "expiry_days": 4, "log_option": True}
r = post("/api/maint/statuses", {"custom": custom + [mine]})
ok(r.status_code == 200, "a custom status with rules can be added")
wid = next(x["id"] for x in J(r)["statuses"] if x["label"] == "Waiting for the weekend")
ok(post("/api/maint/statuses", {"custom": custom + [{**mine, "label": "Overdue"}]}).status_code == 400, "a status cannot reuse a built-in name")
ok(post("/api/maint/statuses", {"custom": [x for x in custom if x["id"] != "s_parts"]}).status_code == 400, "a status in use cannot be deleted")
r = post("/api/maint/tasks", {"title": "Lube the Z screws", "asset": "machine:motion_z", "type": "lubricate",
                              "rules": [{"kind": "time", "every": 10, "unit": "days", "lead": 2}]})
z = J(r)["id"]
clock["t"] += 9 * 86400
r = post(f"/api/maint/tasks/{z}/done", {"action": wid, "notes": "do it Saturday"})
ok(r.status_code == 200, "a custom status can be chosen in the Log work list")
clock["t"] += 3 * 86400            # 12 days after creation: would be overdue, but the clock is paused
st = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}[z]["status"]
ok(st["state"] == "due_soon" and st["hold"]["clock"] == "pause", f"paused clock: still where it was when set ({st['state']})")
clock["t"] += 2 * 86400            # 4 days after setting it: expires
st = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}[z]["status"]
ok(not st.get("hold") and st["state"] == "due_soon", f"the status ends by itself after 4 days and the paused days are credited ({st['next']['text']})")
ok(J(c.get("/api/maint/history"))["records"][0]["action"] == "status_cleared", "its end is logged")
r = post(f"/api/maint/tasks/{belt}/done", {"action": "done", "notes": "belt fitted"})
st = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}[belt]["status"]
ok(r.status_code == 200 and not st.get("hold") and st["state"] == "ok", "logging it done clears the status and restarts the schedule")
ok(post(f"/api/maint/tasks/{belt}/done", {"action": "nonsense"}).status_code == 400, "unknown log action refused")
r = post("/api/maint/lists", {"types": [{"id": "inspect", "label": "Look over"}, {"label": "Wash"}] +
                              [{"id": k, "label": v} for k, v in ml["types"].items() if k != "inspect"]})
ok(r.status_code == 200 and J(r)["types"]["inspect"] == "Look over" and "wash" in J(r)["types"], "kinds of work can be renamed and added")
ok(post("/api/maint/lists", {"types": [{"id": "inspect", "label": "Inspect"}]}).status_code == 400, "a kind of work tasks use cannot be removed")

fake.shutdown()
shutil.rmtree(os.path.dirname(os.path.dirname(CFG)), ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
