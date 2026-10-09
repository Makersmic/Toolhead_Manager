"""Slice tab prototype tests (Kiri:Moto in the portal). Run: python3 dev/test_slice.py  (needs flask, jinja2)

Part 1  the LightSaber profile is built from variables.cfg / printer.cfg, never typed in twice
Part 2  a laser file really exported by Kiri:Moto with that profile (dev/fixtures/kiri_lightsaber_cube.gcode)
        runs through the simulated Klipper macros: with LightSaber mounted it cuts at the right power and
        ends with the laser off and the bed parked; with another tool mounted it is refused before the
        laser can switch on
Part 3  the portal: off by default (no tab, no extra security rule, nothing changes); when on, it opens
        on the mounted tool and only lets this machine's Kiri:Moto be framed
"""
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def copy_config():
    root = tempfile.mkdtemp(prefix="rhino-slice-test-")
    cfg = os.path.join(root, "printer_data", "config")
    shutil.copytree(ROOT, cfg, ignore=shutil.ignore_patterns("__pycache__", "registry_backups", ".git", "maintenance"))
    return cfg


def write_settings(cfg, data):
    p = os.path.join(cfg, "myrhino", "slicer.json")
    if data is None:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


from rhino.paths import resolve  # noqa: E402
from rhino.slice import profiles  # noqa: E402

# =============================================================================== part 1
print("== profile built from the config ==")
CFG = copy_config()
P = resolve(CFG)
ok(profiles.load_settings(P)["enabled"] is False, "no myrhino/slicer.json: slicing is off")
write_settings(CFG, "{not json")
ok(profiles.load_settings(P)["enabled"] is False, "a broken slicer.json: slicing is off (no crash)")
write_settings(CFG, {"enabled": "yes"})
ok(profiles.load_settings(P)["enabled"] is False, "only a real true turns it on")
write_settings(CFG, None)

r = profiles.build(P)
ok(sorted(r["profiles"]) == ["LightSaber"] and not r["problems"], "one profile, for LightSaber (the only laser tool), no problems")
ls = r["profiles"]["LightSaber"]
dev = ls["device"]
ok(ls["mode"] == "LASER" and dev["deviceName"] == "Rhino LightSaber" and ls["slot"] == 3, "Kiri:Moto Laser mode, 'Rhino LightSaber', slot 3")
ok(dev["laserMaxPower"] == 1000.0, "power scale = variable_laser_s_max (1000), the same scale the M3 macro divides by")
ok((dev["bedWidth"], dev["bedDepth"]) == (550.0, 375.0), "work area 550 x 375, the same as the Orca profile (X endstop at 550)")
ok(dev["gcodeLaserOn"] == ["M3 S{power}"] and dev["gcodeLaserOff"] == ["M5"], "cuts switch the laser with M3 S / M5")
pre = "\n".join(dev["gcodePre"])
ok(dev["gcodePre"][0] == "; RHINO_TOOL=LightSaber", "the file starts with the tool stamp the portal will check")
ok("ACTIVATE_LASER" in pre and "LASER_JOB_SETUP" not in [l.split(";")[0].strip() for l in dev["gcodePre"]],
   "start code powers the rails and does not call LASER_JOB_SETUP (it refuses to run mid-job)")
ok(not any(l.split(";")[0].strip().startswith(("START_JOB", "G28")) for l in dev["gcodePre"]),
   "no START_JOB / G28 (its Z homing is refused with the laser mounted)")
ok([l.split(";")[0].strip() for l in dev["gcodePost"]] == ["M5", "DEACTIVATE_LASER", "_RHINO_PARK"],
   "end code: laser off, rails off, bed to the safe park height")
pr = ls["processes"]
ok(sorted(pr) == ["LightSaber ACRYLIC", "LightSaber LEATHER", "LightSaber PLYWOOD"], "one setting per material in variables.cfg")
ok((pr["LightSaber PLYWOOD"]["ctOutPower"], pr["LightSaber PLYWOOD"]["ctOutSpeed"]) == (80.0, 600.0),
   "plywood: 80% power (laser_power 0.8), F600 (feed_rate 600)")
ok((pr["LightSaber ACRYLIC"]["ctOutPower"], pr["LightSaber ACRYLIC"]["ctOutSpeed"]) == (90.0, 400.0), "acrylic: 90%, F400")
ok(all(p["ctOriginCenter"] is False and p["ctOriginBounds"] is False for p in pr.values()),
   "origin = the bed's corner (machine X/Y), not Kiri's default centre-of-part")
ok(ls["process"] == "LightSaber PLYWOOD", "opens on plywood")

write_settings(CFG, {"enabled": True, "work_area": {"LightSaber": {"x": 600, "y": "big"}}})
r2 = profiles.build(P)
d2 = r2["profiles"]["LightSaber"]["device"]
ok(d2["bedWidth"] == 576.0 and any("past the travel limit 576" in p for p in r2["problems"]),
   "a work area past printer.cfg's travel is cut back to it, and said so")
ok(d2["bedDepth"] == 375.0 and any("not a number" in p for p in r2["problems"]), "a work area that is not a number is reported")
write_settings(CFG, None)

# =============================================================================== part 2
print("== the exported laser file, run through the simulated macros ==")
from klippersim import Sim, KlipperError  # noqa: E402

GCODE = open(os.path.join(HERE, "fixtures", "kiri_lightsaber_cube.gcode")).read().splitlines()
ok(GCODE[0] == "; RHINO_TOOL=LightSaber" and any(l.startswith("M3 S800") for l in GCODE),
   "fixture is a real Kiri:Moto export with the Rhino profile (stamp, S800 = 80% of 1000)")
BASE = Sim(ROOT, motion=True).load()
TOOLS = {1: ("BlockOne", "PLA"), 3: ("LightSaber", "PLYWOOD")}


def sim(slot):
    s = BASE.clone()
    name, mat = TOOLS[slot]
    s.macro_vars["SWAP_TOOL"]["current_tool"] = slot
    s.save_vars.update(current_tool=slot, set_material_toolhead=name, set_material_material=mat)
    s.objects["print_stats"]["state"] = "printing"
    s.place(275.0, 187.5, 40.0, homed="xyz")       # focus set by eye: Z0 is machine Z40 here
    s.run_script("SET_GCODE_OFFSET Z=40")
    return s


s = sim(3)
seen, err = [], None
try:
    for line in GCODE:
        s.run_line(line)
        seen.append((line, s.pins.get("SERVO_LASER", 0.0), s.pins.get("LASER_INITIALIZE", 0.0)))
except KlipperError as e:
    err = e
ok(err is None, f"LightSaber mounted: the whole file runs with no Klipper error ({err})")
cut = [p for l, p, _ in seen if l.startswith("G1")]
ok(cut and all(abs(p - 0.8) < 1e-9 for p in cut), "every cutting move runs at 0.8 (80%) laser power")
travel = [p for l, p, _ in seen if l.startswith("G0")]
ok(travel and all(p == 0.0 for p in travel), "the laser is off on every travel move (G0)")
ok(all(rail == 1.0 for l, _, rail in seen if l.startswith(("G0", "G1"))), "the rails are powered for the whole job")
ok(s.pins.get("SERVO_LASER") == 0.0 and s.pins.get("LASER_INITIALIZE") == 0.0, "after the file: laser and rails both off")
xy = [m["to"] for m in s.moves if m["to"] and m["to"].get("x") is not None]
ok(all(0 <= m["x"] <= 550 and 0 <= m["y"] <= 375 for m in xy), "every X/Y move stays inside the 550 x 375 work area")
zs = [m["to"]["z"] for m in s.moves if m["to"] and m["to"].get("z") is not None]
ok(min(zs) >= 40.0, "the bed never comes closer than the focus height during the job")
ok(s.objects["toolhead"]["position"]["z"] >= 150.0, "ends with the bed lowered to the safe park height (150)")

s = sim(1)
err = None
try:
    for line in GCODE:
        s.run_line(line)
except KlipperError as e:
    err = e
ok(err is not None and "Activation Denied" in str(err), "BlockOne mounted: the file is refused at ACTIVATE_LASER")
ok(s.pins.get("SERVO_LASER", 0.0) == 0.0 and s.pins.get("LASER_INITIALIZE", 0.0) == 0.0, "...before the laser could switch on")
ok(not [m for m in s.moves if m["to"] and m["to"].get("x") not in (None, 275.0)], "...and before any move")

# =============================================================================== part 3
print("== portal ==")
import http.server  # noqa: E402
import threading  # noqa: E402

STATE = {"tool": 3, "klippy": "ready"}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/server/info"):
            self._send(200, {"result": {"klippy_state": STATE["klippy"]}})
        elif self.path.startswith("/printer/objects/query"):
            self._send(200, {"result": {"status": {"print_stats": {"state": "standby"},
                                                   "gcode_macro SWAP_TOOL": {"current_tool": STATE["tool"]}}}})
        else:
            self._send(404, {})


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
sys.path.insert(0, CFG)
from rhino.portal import create_app  # noqa: E402

app = create_app(CFG, f"http://127.0.0.1:{srv.server_port}")
c = app.test_client()
BASE_CSP = None

r = c.get("/", base_url="http://rhino.local:5000")
BASE_CSP = r.headers["Content-Security-Policy"]
ok("frame-src" not in BASE_CSP and "frame-ancestors 'none'" in BASE_CSP, "off: the security policy is exactly as before (no frame-src)")
html = r.get_data(as_text=True)
ok('id="navSlice"' in html and 'class="nav-btn nav-top hidden" data-view="slice"' in html, "off: the Slice button is in the page but hidden")
ok(c.get("/api/slice/context").get_json() == {"ok": True, "enabled": False}, "off: the context says disabled and nothing else")

write_settings(CFG, {"enabled": True})
r = c.get("/", base_url="http://rhino.local:5000")
csp = r.headers["Content-Security-Policy"]
ok(csp == BASE_CSP + "; frame-src http://rhino.local:8090", "on: only Kiri:Moto on this host's port 8090 may be framed")
ok(c.get("/api/state").headers["Content-Security-Policy"] == BASE_CSP, "on: JSON replies keep the plain policy")
r = c.get("/", base_url="http://192.168.1.20:5000")
ok(r.headers["Content-Security-Policy"].endswith("frame-src http://192.168.1.20:8090"), "on: works with an IP address too")
r = c.get("/", headers={"Host": "evil.com;script-src *"})
ok("script-src *" not in r.headers["Content-Security-Policy"], "a junk Host header cannot add rules to the policy")

d = c.get("/api/slice/context").get_json()
ok(d["enabled"] and d["kiri_port"] == 8090 and d["mounted"] == {"slot": 3, "name": "LightSaber", "online": True},
   "LightSaber mounted: the context says so")
ok(d["profile"]["deviceName"] == "Rhino LightSaber" and d["why"] == "", "...and carries its profile")
STATE["tool"] = 1
d = c.get("/api/slice/context").get_json()
ok(d["profile"] is None and "only has a Kiri:Moto profile for laser tools" in d["why"],
   "BlockOne mounted: no profile, and the page explains why (prototype covers LightSaber only)")
STATE["tool"] = 0
d = c.get("/api/slice/context").get_json()
ok(d["profile"] is None and "No toolhead is recorded" in d["why"], "nothing mounted: says to answer the mounted-tool question")
STATE["klippy"] = "shutdown"
d = c.get("/api/slice/context").get_json()
ok(d["profile"] is None and "not reachable" in d["why"], "Klipper not ready: opens without a profile and says why")
write_settings(CFG, {"enabled": True, "kiri_port": 9123})
ok(c.get("/api/slice/context").get_json()["kiri_port"] == 9123, "the Kiri:Moto port can be changed in slicer.json")
write_settings(CFG, None)
ok(c.get("/api/slice/context").get_json() == {"ok": True, "enabled": False}, "deleting slicer.json turns it off again")

srv.shutdown()
shutil.rmtree(os.path.dirname(os.path.dirname(CFG)), ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} problems:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
