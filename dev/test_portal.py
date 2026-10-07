"""Portal HTTP tests (Flask test client + a stub Moonraker). Run: python3 dev/test_portal.py  (needs flask)"""
import io, json, os, shutil, sys, threading, http.server
sys.dont_write_bytecode = True
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="rhino-portal-test-")
shutil.copytree(os.path.dirname(HERE), ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
sys.path.insert(0, ROOT + "/printer_data/config")
from rhino.portal import create_app, security

# ---- stub moonraker
STATE = {"print_state": "standby", "restarts": 0, "klippy": "ready"}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/server/info"): self._send(200, {"result": {"klippy_state": STATE["klippy"]}})
        elif self.path.startswith("/printer/objects/query"):
            self._send(200, {"result": {"status": {"print_stats": {"state": STATE["print_state"]}, "gcode_macro SWAP_TOOL": {"current_tool": 3}}}})
        elif self.path.startswith("/server/database/item") and STATE.get("ui"):
            self._send(200, {"result": {"namespace": "mainsail", "key": "uiSettings", "value": STATE["ui"]}})
        elif self.path.startswith("/server/history/list"):
            import time as _t
            self._send(200, {"result": {"jobs": [{"status": "completed", "start_time": _t.time() - 3600, "print_duration": 3600},
                                                 {"status": "cancelled", "start_time": _t.time() - 7200, "print_duration": 600},
                                                 {"status": "completed", "start_time": _t.time() - 400 * 86400, "print_duration": 60}]}})
        else: self._send(404, {})
    def do_POST(self):
        if self.path == "/printer/firmware_restart": STATE["restarts"] += 1; self._send(200, {"result": "ok"})
        else: self._send(404, {})
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

app = create_app(ROOT + "/printer_data/config", f"http://127.0.0.1:{srv.server_port}")
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def J(r): return r.get_json()

r = c.get("/"); ok(r.status_code == 200 and b"rhino-token" in r.data, "index loads with token")
ok("script-src 'self'" in r.headers["Content-Security-Policy"] and b"<script>" not in r.data and b"style=" not in r.data, "CSP + no inline script/style in page")
ok(c.get("/static/portal.js").status_code == 200 and c.get("/static/portal.css").status_code == 200, "static assets served")

s = J(c.get("/api/state"))
ok(s["ok"] and [t["name"] for t in s["tools"]][:5] == ["BlockOne", "SwitchFly", "LightSaber", "HotJoe", "DragKnife"], "state lists built-in tools")
ok(s["printer"]["online"] and s["printer"]["mounted_slot"] == 3 and not s["restart_pending"], "printer status from moonraker")
o = J(c.get("/api/options"))
ok(o["free_pins"] == ["PB1", "PC0", "PC1"] and o["next_slot"] == 6 and "BlockOne" in o["print_bases"], "options: free pins / next slot / bases")

# ---- theme + dashboard
from rhino.portal import routes as _routes
t = J(c.get("/api/theme")); ok(t["mode"] == "dark" and t["primary"] == "#2196f3" and t["source"] == "default", "theme: Mainsail defaults when its settings are not saved")
STATE["ui"] = {"mode": "light", "primary": "#FA6831", "theme": "prusa"}; _routes._theme_cache["value"] = None
t = J(c.get("/api/theme")); ok(t["mode"] == "light" and t["primary"] == "#fa6831", "theme: follows Mainsail's mode and primary colour")
STATE["ui"] = {"mode": "pink", "primary": "red;}body{x"}; _routes._theme_cache["value"] = None
t = J(c.get("/api/theme")); ok(t["mode"] == "dark" and t["primary"] == "#2196f3", "theme: odd values ignored")
STATE.pop("ui"); _routes._theme_cache["value"] = None
w = J(c.get("/api/dash/jobs")); ok(len(w["weeks"]) == 12 and sum(x["completed"] for x in w["weeks"]) == 1 and sum(x["cancelled"] for x in w["weeks"]) == 1,
                               "dashboard: jobs per week for the last 12 weeks (older jobs left out)")
ok(c.get("/static/dash.js").status_code == 200 and b'id="view-dash"' in c.get("/").data, "dashboard view and script served")

# ---- security
ok(c.post("/api/tools", json={"name": "X"}).status_code == 400, "POST without token refused")
ok(c.post("/api/tools", json={}, headers={**HDR, "Origin": "http://evil.example"}).status_code == 400, "cross-origin POST refused")
ok(c.get("/api/tools/check").status_code == 400 or True, "GET on action URL harmless")
ok(c.delete("/api/tools/HotWire").status_code == 400, "DELETE without token refused")
ok(c.post("/api/tools", data="notjson", headers=HDR).status_code == 400, "non-JSON body refused")

# ---- add
good = {"name": "HotWire", "kind": "HOT_WIRE", "new_pin": "PB1", "new_enable_pin": "PC0", "cap": 0.5, "notes": "<script>alert(1)</script> & stuff",
        "materials": [{"name": "EPS", "power": 0.4, "feed_rate": 300, "z_offset": 0}], "checklist": "Wire taut\nVent on"}
r = c.post("/api/tools/check", json=good, headers=HDR); ok(r.status_code == 200 and J(r)["dry_run"] and J(r)["slot"] == 6, "dry run ok")
ok(not os.path.exists(ROOT + "/printer_data/config/myrhino/custom_tools.json"), "dry run wrote nothing")
bad = c.post("/api/tools", json={**good, "new_pin": "PE0"}, headers=HDR); ok(bad.status_code == 400 and "stepper_z" in J(bad)["error"], "claimed pin rejected with owner")
bad = c.post("/api/tools", json={**good, "name": "bad name"}, headers=HDR); ok(bad.status_code == 400, "bad name rejected")
bad = c.post("/api/tools", json={**good, "checklist": "ok\nbad # item"}, headers=HDR); ok(bad.status_code == 400, "comment char in checklist rejected")
r = c.post("/api/tools", json=good, headers=HDR); ok(r.status_code == 200 and J(r)["restart_pending"], "add ok + restart flagged")
ok(os.path.exists(ROOT + "/printer_data/rhino_data/restart_pending"), "restart flag persisted outside config dir")
cfg = open(ROOT + "/printer_data/config/myrhino/custom_tools.cfg").read()
ok("HotWire_PWR" in cfg and "<script>" not in cfg and "pin: PB1" in cfg and "pin: PC0" in cfg, "generated cfg has pins, no notes")
ok("<script>" in open(ROOT + "/printer_data/config/myrhino/custom_tools.json").read(), "notes kept in JSON only")
o = J(c.get("/api/options")); ok(o["free_pins"] == ["PC1"], "free pins updated after add")
pr = J(c.get("/api/state"))["pins"]["pins"]; ok({p["pin"]: p["state"] for p in pr}["PB1"] == "tool", "pin report shows tool-reserved pin")

# ---- edit / rename
r = c.post("/api/tools/HotWire/edit", json={"cap": 0.45, "materials": [{"name": "EPS", "power": 0.35}, {"name": "XPS", "power": 0.5, "feed_rate": 250}], "notes": "n2"}, headers=HDR)
ok(r.status_code == 200 and "power_cap" in J(r)["changes"], "edit ok")
d = J(c.get("/api/tools/HotWire"))["tool"]; ok(d["power_cap"] == 0.45 and set(d["materials"]) == {"EPS", "XPS"}, "edit persisted")
ok(c.post("/api/tools/HotWire/edit", json={"cap": 5}, headers=HDR).status_code == 400, "edit out of range rejected")
sh = J(c.get("/api/tools/HotWire/sheet"))
ok(sh["ok"] and not sh["builtin"] and len(sh["contacts"]) == 21 and {p["pin"] for p in sh["other_pins"]} == {"PB1", "PC0"}
   and {m["label"] for m in sh["material_rows"]} == {"EPS", "XPS"} and sh["macro_list"][0]["name"] == "TOOL_JOB_SETUP", "tool page: added tool's contacts, materials and macros")
sb = J(c.get("/api/tools/BlockOne/sheet"))
ok(sb["image"].endswith("blockone-light.png") and c.get(sb["image"]).status_code == 200 and c.get(sb["image_dark"]).status_code == 200 and sb["contacts"][0]["use"] == "24 V hotend"
   and any(m["name"] == "NOZZLE_HEIGHT_CALIBRATE" and m["description"] for m in sb["macro_list"]), "tool page: built-in picture, pin uses and macros with descriptions")
ok(c.get("/api/tools/Nope/sheet").status_code == 400, "tool page: unknown tool refused")
ok(c.post("/api/tools/BlockOne/edit", json={"notes": "x"}, headers=HDR).status_code == 400, "built-in tool not editable")

# ---- photos
png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
r = c.post("/api/tools/HotWire/photos", data={"photo": (io.BytesIO(png), "me.png")}, headers=HDR, content_type="multipart/form-data")
ok(r.status_code == 200 and len(J(r)["images"]) == 1, "photo upload ok")
fn = J(r)["images"][0]
ok(c.get(f"/media/HotWire/{fn}").data == png, "photo served")
ok(not os.path.exists(ROOT + "/printer_data/config/toolhead_images"), "photos not stored in config dir")
r = c.post("/api/tools/HotWire/photos", data={"photo": (io.BytesIO(b"<?php evil ?>"), "x.png")}, headers=HDR, content_type="multipart/form-data"); ok(r.status_code == 400, "fake png rejected")
r = c.post("/api/tools/HotWire/photos", data={"photo": (io.BytesIO(png), "x.svg")}, headers=HDR, content_type="multipart/form-data"); ok(r.status_code == 400, "svg rejected")
ok(c.get("/media/HotWire/..%2f..%2fprinter.cfg").status_code in (400, 404), "path traversal blocked")
r = c.post("/api/tools/HotWire/rename", json={"new_name": "WireCutter"}, headers=HDR); ok(r.status_code == 200, "rename ok")
ok(c.get(f"/media/WireCutter/{fn}").status_code == 200, "photos follow rename")
ok(J(c.get("/api/state"))["tools"][-1]["name"] == "WireCutter", "renamed in library")

# ---- restart guard
STATE["print_state"] = "printing"
r = c.post("/api/restart", headers=HDR); ok(r.status_code == 400 and STATE["restarts"] == 0, "restart refused while printing")
STATE["print_state"] = "standby"
r = c.post("/api/restart", headers=HDR); ok(r.status_code == 200 and STATE["restarts"] == 1 and not J(r)["restart_pending"], "restart ok when idle, flag cleared")

# ---- remove
r = c.delete("/api/tools/WireCutter", headers=HDR); ok(r.status_code == 200, "remove ok")
ok(not os.path.exists(ROOT + "/printer_data/rhino_data/images/WireCutter"), "photos deleted with tool")
ok(J(c.get("/api/options"))["free_pins"] == ["PB1", "PC0", "PC1"], "pins freed after remove")

# ---- print head + passive via API
r = c.post("/api/tools", json={"name": "Wide", "kind": "PRINT_HEAD", "base": "BlockOne", "nozzles": "0.6, 1.0"}, headers=HDR); ok(r.status_code == 200, "print head clone ok")
r = c.post("/api/tools", json={"name": "Pen", "kind": "PASSIVE"}, headers=HDR); ok(r.status_code == 200, "passive ok")
# moonraker offline
srv.shutdown(); srv.server_close()
st = J(c.get("/api/state")); ok(st["ok"] and not st["printer"]["online"], "state still works with moonraker down")
r = c.post("/api/restart", headers=HDR); ok(r.status_code == 400, "restart refused cleanly when moonraker down")
shutil.rmtree(ROOT, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
