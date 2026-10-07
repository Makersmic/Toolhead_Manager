"""Maintenance tests: schedule math, meters from a simulated machine, the portal API, the boot
reminder file and the Klipper reminder macros.  Run: python3 dev/test_maint.py  (needs flask, jinja2)"""
import json, os, shutil, sys, tempfile, datetime
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_server as demo
CFG = demo.make_config()
sys.path.insert(0, CFG)
from rhino.portal import create_app, security
from rhino.maint import schedule, meters
from klippersim import Sim

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

DAY = 86400
T0 = datetime.datetime(2026, 1, 1, 9, 0).timestamp()
defs = meters.meter_defs()

# ---------------------------------------------------------------- schedule math (pure)
task = {"created": T0, "start": {"at": T0, "meters": {"machine.prod_h": 0.0}}, "last": None,
        "rules": [{"kind": "time", "every": 1, "unit": "months", "lead": 7, "lead_unit": "days"},
                  {"kind": "meter", "meter": "prod_h", "scope": "machine", "every": 100, "lead": 10}]}
val = {"v": 50.0}
st = schedule.task_status(task, T0 + 10 * DAY, lambda r: val["v"], lambda r: 5.0, defs)
ok(st["state"] == "ok" and abs(st["fraction"] - 0.5) < 0.01, f"half the hours used -> ok ({st['state']}, {st['fraction']:.2f})")
ok("50 h left" in st["rules"][1]["text"] and "10 days" in st["rules"][1]["text"], f"meter text with rate: {st['rules'][1]['text']}")
val["v"] = 92.0
ok(schedule.task_status(task, T0 + 10 * DAY, lambda r: val["v"], lambda r: None, defs)["state"] == "due_soon", "inside the early alarm (8 h left, lead 10 h) -> due soon")
val["v"] = 20.0
ok(schedule.task_status(task, T0 + 26 * DAY, lambda r: val["v"], lambda r: None, defs)["state"] == "due_soon", "7-day early alarm on the 1-month rule")
st = schedule.task_status(task, T0 + 32 * DAY, lambda r: val["v"], lambda r: None, defs)
ok(st["state"] == "overdue" and st["next"]["kind"] == "time", "whichever comes first: the month passed -> overdue")
ok(schedule.add_interval(datetime.datetime(2026, 1, 31).timestamp(), 1, "months") == datetime.datetime(2026, 2, 28).timestamp(), "31 Jan + 1 month = 28 Feb")
cal = {"created": T0, "anchor": "calendar", "first_due": "2026-02-01", "last": {"at": datetime.datetime(2026, 2, 10).timestamp(), "meters": {}},
       "rules": [{"kind": "time", "every": 1, "unit": "months"}]}
r = schedule.task_status(cal, datetime.datetime(2026, 2, 12).timestamp(), None, None, defs)["next"]
ok(datetime.datetime.fromtimestamp(r["due_ts"]).date() == datetime.date(2026, 3, 1), "fixed calendar: done late on 10 Feb, next is still 1 Mar")
ev = {"created": T0, "start": {"at": T0, "meters": {"machine.shutdowns": 2.0}}, "rules": [{"kind": "meter", "meter": "shutdowns", "scope": "machine", "every": 1, "event": True}]}
ok(schedule.task_status(ev, T0, lambda r: 2.0, lambda r: None, defs)["state"] == "ok", "event rule quiet until the event")
ok(schedule.task_status(ev, T0, lambda r: 3.0, lambda r: None, defs)["state"] == "overdue", "event rule due right after an emergency stop")
one = {"created": T0, "rules": [{"kind": "date", "on": "2026-03-01", "lead": 7}]}
ok(schedule.task_status(one, datetime.datetime(2026, 2, 25).timestamp(), None, None, defs)["state"] == "due_soon", "one-off date with 7-day alarm")
one["last"] = {"at": datetime.datetime(2026, 3, 2).timestamp()}
ok(schedule.task_status(one, datetime.datetime(2026, 3, 3).timestamp(), None, None, defs)["state"] == "done", "one-off done stays done")
ok(schedule.describe({"kind": "meter", "meter": "prod_h", "scope": "machine", "every": 200}, defs) == "every 200 production hours", "wording: every 200 production hours")

# ---------------------------------------------------------------- portal + simulated machine
fake = demo.start_fake()
S = demo.STATE
clock = {"t": T0}
app = create_app(CFG, f"http://127.0.0.1:{fake.server_port}")
mon, maint = app.config["MONITOR"], app.config["MAINT"]
maint.now = lambda: clock["t"]
col = mon.listeners[0]
c = app.test_client()
H = {security.HEADER: security.TOKEN}
J = lambda r: r.get_json()
def tick(seconds=5, n=1):
    for _ in range(n):
        clock["t"] += seconds
        mon.tick(clock["t"])

# a machine with past jobs: the first sync imports them as the starting reading
S["jobs"] += [{"job_id": "000001", "filename": "old.gcode", "status": "completed", "start_time": T0 - 9000, "end_time": T0 - 5400,
               "print_duration": 3600, "total_duration": 3600, "filament_used": 2500.0}]
S.update(current_tool=1, print_state="standby")
tick()
m = maint.meters.data["machine"]
ok(m["jobs"] == 1 and abs(m["prod_h"] - 1.0) < 1e-6 and abs(m["filament_m"] - 2.5) < 1e-6 and maint.meters.data["imported_jobs"] == 1,
   "first run imports Moonraker's past jobs as the machine's starting reading")
ok(maint.meters.value("tool", "prod_h", "BlockOne") == 0, "...but not per tool (unknown which tool ran them)")

# an hour of idle time, nozzle hot for half of it
S["extruder_target"] = 210.0
tick(5, 360)
S["extruder_target"] = 0.0
tick(5, 360)
ok(abs(maint.meters.value("machine", "up_h") - 1.0) < 0.01, f"up hours counted ({maint.meters.value('machine', 'up_h'):.3f})")
ok(abs(maint.meters.value("tool", "active_h", "BlockOne") - 0.5) < 0.01, "BlockOne working hours = time the nozzle heater was on")
ok(abs(maint.meters.value("tool", "mounted_h", "BlockOne") - 1.0) < 0.01, "BlockOne mounted hours")

# a 2 h job with a 30 min pause
S.update(print_state="printing", filename="part.gcode", progress=0.1)
tick(5, 720)
S["print_state"] = "paused"; tick(5, 360)
S["print_state"] = "printing"; tick(5, 720)
S["jobs"].append({"job_id": "000002", "filename": "part.gcode", "status": "completed", "start_time": clock["t"] - 9000,
                  "end_time": clock["t"], "print_duration": 7200, "total_duration": 9000, "filament_used": 12000.0})
S["print_state"] = "complete"; tick()
ok(abs(maint.meters.value("machine", "prod_h") - 3.0) < 0.02, f"production hours: +2 h for the job, the 30 min pause not counted ({maint.meters.value('machine', 'prod_h'):.3f})")
ok(maint.meters.value("machine", "jobs") == 2 and maint.meters.value("tool", "jobs", "BlockOne") == 1, "job counted once, for the machine and the mounted tool")
ok(abs(maint.meters.value("tool", "filament_m", "BlockOne") - 12.0) < 1e-6, "filament from the job history goes to the print head")
tick(5, 3); ok(maint.meters.value("machine", "jobs") == 2, "the same job is never counted twice")

# swaps, restart, shutdown
S["current_tool"] = 3; tick()
ok(maint.meters.value("machine", "swaps") == 1 and maint.meters.value("tool", "mounts", "LightSaber") == 1, "swap to LightSaber counted")
S["current_tool"] = 0; tick(); S["current_tool"] = 3; tick()
ok(maint.meters.value("machine", "swaps") == 1, "a restart (slot 0 then the same tool again) is not a swap")
S["laser"] = 0.5; tick(5, 72); S["laser"] = 0.0
ok(abs(maint.meters.value("tool", "active_h", "LightSaber") - 0.1) < 0.005, "LightSaber working hours = laser on")
S["klippy"] = "shutdown"; tick(); tick()
ok(maint.meters.value("machine", "shutdowns") == 1, "emergency stop / shutdown counted once")
S["klippy"] = "ready"; tick()

# job that ran while the portal was down
S["jobs"].append({"job_id": "000003", "filename": "night.gcode", "status": "completed", "start_time": col.online_since - 7200,
                  "end_time": col.online_since - 3600, "print_duration": 3600, "total_duration": 3600, "filament_used": 0})
before = maint.meters.value("machine", "prod_h")
col.last_history = 0; tick()
ok(abs(maint.meters.value("machine", "prod_h") - before - 1.0) < 0.01, "a job the portal missed is filled in from Moonraker's history")

# ---------------------------------------------------------------- tasks via the API
r = c.post("/api/maint/tasks", json={"title": "Tension belts", "asset": "machine:motion_xy", "type": "adjust",
           "rules": [{"kind": "meter", "meter": "prod_h", "scope": "machine", "every": 5, "lead": 1}]}, headers=H)
ok(r.status_code == 200, f"create task: {J(r)}")
belts = J(r)["id"]
ok(c.post("/api/maint/tasks", json={"title": "x"}, headers=H).status_code == 400, "task without asset/rules refused")
ok(c.post("/api/maint/tasks", json={"title": "Bad \"quote\"", "asset": "machine:frame", "rules": [{"kind": "time", "every": 1, "unit": "days"}]}, headers=H).status_code == 400,
   "title with quotes refused (it goes into a Klipper prompt)")
ok(c.post("/api/maint/tasks", json={"title": "Tool meter on machine", "asset": "machine:frame", "rules": [{"kind": "meter", "meter": "active_h", "scope": "tool", "every": 5}]}, headers=H).status_code == 400,
   "a tool meter needs a tool task")
ok(c.post("/api/maint/tasks", json={"title": "No token", "asset": "machine:frame", "rules": [{"kind": "time", "every": 1, "unit": "days"}]}).status_code == 400, "write without token refused")
r = c.post("/api/maint/tasks", json={"title": "Clean the lens", "asset": "tool:LightSaber", "type": "clean",
           "rules": [{"kind": "meter", "meter": "active_h", "scope": "tool", "every": 0.2, "lead": 0.05}], "parts": "Lens tissue\nIPA"}, headers=H)
lens = J(r)["id"]
ov = J(c.get("/api/maint"))
t = {x["id"]: x for x in ov["tasks"]}
ok(t[belts]["status"]["state"] == "ok" and t[lens]["status"]["state"] == "ok", "new tasks start counting from now")
S["print_state"] = "printing"; S["laser"] = 0.5
tick(5, 2160)          # 3 h of laser job
S["laser"] = 0.0; S["print_state"] = "complete"; tick()
ov = J(c.get("/api/maint")); t = {x["id"]: x for x in ov["tasks"]}
ok(t[lens]["status"]["state"] == "overdue", "lens task overdue after 3 h of laser")
ok(t[belts]["status"]["state"] == "ok" and abs(t[belts]["status"]["next"]["remaining"] - 2.0) < 0.05,
   f"belts: 3 of 5 production hours used ({t[belts]['status']['next']['text']})")
ok(ov["counts"]["overdue"] == 1, "overdue count for the nav badge")

# boot reminder file + the Klipper prompt it drives
txt = open(os.path.join(CFG, "myrhino", "maintenance_status.cfg")).read()
ok("Clean the lens" in txt and "'overdue'" in txt, "maintenance_status.cfg lists the overdue task")
sim = Sim(CFG).load(); sim.macro_vars["SWAP_TOOL"]["current_tool"] = 3
sim.run_script("_PM_BOOT_REMINDER")
ok(sim.prompt and any("OVERDUE - LightSaber: Clean the lens" in x for x in sim.prompt["text"]), "Klipper shows the reminder after start-up")
sim.prompt = None; sim.run_script("_PM_BOOT_REMINDER"); ok(sim.prompt is None, "...only once per start")
sim2 = Sim(CFG).load(); sim2.save_vars["current_tool"] = 3; sim2.fire_delayed("_RESTORE_TOOL_PROMPT")
ok(sim2.prompt and "which toolhead" in sim2.prompt["title"], "restore question comes first")
sim2.press("Yes"); ok(sim2.prompt and sim2.prompt["title"] == "Maintenance due", "maintenance reminder follows the restore answer")
sim3 = Sim(CFG).load(); sim3.save_vars["current_tool"] = 3; sim3.fire_delayed("_RESTORE_TOOL_PROMPT"); sim3.press("Dismiss")
ok(sim3.prompt and sim3.prompt["title"] == "Maintenance due", "...also after Dismiss")
sim4 = Sim(CFG).load(); sim4.objects["print_stats"]["state"] = "printing"
sim4.run_script("PM_STATUS"); ok(sim4.shell_calls[-1] == ("rhino_toolgen", "pm-status"), "PM_STATUS asks the portal files (console)")

# snooze, complete, history
r = c.post(f"/api/maint/tasks/{lens}/snooze", json={"days": 2}, headers=H)
ov = J(c.get("/api/maint")); t = {x["id"]: x for x in ov["tasks"]}
ok(t[lens]["status"]["snoozed"] and ov["counts"]["overdue"] == 0 and ov["counts"]["snoozed"] == 1, "snoozed task leaves the overdue count")
maint.write_boot_cfg(force=True)
ok("Clean the lens" not in open(os.path.join(CFG, "myrhino", "maintenance_status.cfg")).read(), "snoozed task is not in the boot reminder")
r = c.post(f"/api/maint/tasks/{lens}/done", json={"action": "done", "notes": "lens was smoky"}, headers=H)
ov = J(c.get("/api/maint")); t = {x["id"]: x for x in ov["tasks"]}
ok(r.status_code == 200 and t[lens]["status"]["state"] == "ok" and not t[lens].get("snooze_until"), "done resets the count and the snooze")
h = J(c.get("/api/maint/history"))["records"]
ok(h[0]["title"] == "Clean the lens" and h[0]["action"] == "done" and h[0]["was"] == "overdue" and "tool.active_h" in h[0]["readings"],
   "history records the completion with its readings")
r = c.post(f"/api/maint/tasks/{belts}/done", json={"action": "skipped", "date": "2025-12-01"}, headers=H)
ok(r.status_code == 200, "skip with a back-dated date accepted")
ok(c.post(f"/api/maint/tasks/{belts}/done", json={"date": "2099-01-01"}, headers=H).status_code == 400, "future completion date refused")

# meters: adjust
r = c.post("/api/maint/meters", json={"scope": "machine", "meter": "prod_h", "value": 1500, "note": "hours before tracking"}, headers=H)
ok(r.status_code == 200 and maint.meters.value("machine", "prod_h") == 1500, "meter reading can be set (machine had hours before tracking)")
ok(c.post("/api/maint/meters", json={"scope": "machine", "meter": "prod_h", "value": -1}, headers=H).status_code == 400, "negative reading refused")

# library
lib = J(c.get("/api/maint/library"))["templates"]
keys = {(x["key"], x["asset"]) for x in lib}
ok(("tool:laser_lens", "tool:LightSaber") in keys and ("tool:nozzle_clean", "tool:BlockOne") in keys and ("machine:umbilical", "machine:umbilical") in keys,
   "library offers tasks per tool type and machine area")
ok(("tool:laser_lens", "tool:BlockOne") not in keys, "...and not laser tasks for a print head")
r = c.post("/api/maint/library", json={"picks": [{"key": "tool:nozzle_clean", "asset": "tool:BlockOne"}, {"key": "machine:estop", "asset": "machine:other"}]}, headers=H)
ok(r.status_code == 200 and J(r)["added"] == 2, "add from library")
lib = {(x["key"], x["asset"]): x for x in J(c.get("/api/maint/library"))["templates"]}
ok(lib[("tool:nozzle_clean", "tool:BlockOne")]["added"], "library marks what is already added")

from rhino.maint import library as _lib
from rhino.presets import SAFE_TEXT as _SAFE
ok(all(_SAFE.match(t["title"]) and len(t["title"]) <= 80 for t in _lib.MACHINE + _lib.TOOLS), "every starter task title is valid")
r = c.post("/api/maint/library", json={"picks": [{"key": x["key"], "asset": x["asset"]} for x in J(c.get("/api/maint/library"))["templates"] if not x["added"]]}, headers=H)
ok(r.status_code == 200 and J(r)["added"] > 20, f"every starter task can be added ({J(r).get('added')})")

# tool rename / remove follow into maintenance
r = c.post("/api/tools", json={"name": "Needle", "kind": "NEEDLE", "power_pin": "SPINDLE_SPEED"}, headers=H)
r = c.post("/api/maint/tasks", json={"title": "Replace needle", "asset": "tool:Needle", "rules": [{"kind": "meter", "meter": "active_h", "scope": "tool", "every": 20}]}, headers=H)
nid = J(r)["id"]
c.post("/api/tools/Needle/rename", json={"new_name": "Stabber"}, headers=H)
t = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}
ok(t[nid]["asset"] == "tool:Stabber", "renaming a tool moves its maintenance tasks")
c.delete("/api/tools/Stabber", headers=H)
t = {x["id"]: x for x in J(c.get("/api/maint"))["tasks"]}
ok(t[nid].get("archived") and t[nid]["status"] is None, "removing a tool archives its tasks (history kept)")

# console
from rhino import cli
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cli.main(["--config-dir", CFG, "pm-status"])
ok("rhino: Maintenance:" in buf.getvalue(), f"console pm-status: {buf.getvalue().strip().splitlines()[0]}")

# persistence
maint.meters.save(force=True)
again = meters.MeterStore(os.path.join(CFG, "myrhino", "maintenance", "meters.json"))
ok(again.value("machine", "prod_h") == 1500 and not again.data.get("new"), "meters survive a portal restart")

fake.shutdown()
shutil.rmtree(os.path.dirname(os.path.dirname(CFG)), ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
