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

STATE = {"tool": 3, "klippy": "ready", "print_state": "standby", "uploads": [], "scripts": [], "refuse": ""}


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
            self._send(200, {"result": {"status": {"print_stats": {"state": STATE["print_state"]},
                                                   "gcode_macro SWAP_TOOL": {"current_tool": STATE["tool"]}}}})
        else:
            self._send(404, {})

    def do_POST(self):
        import re as _re
        import urllib.parse as _up
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/server/files/upload":
            name = _re.search(rb'name="file"; filename="([^"]+)"', body).group(1).decode()
            data = body.split(b"Content-Type: application/octet-stream\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            root = _re.search(rb'name="root"\r\n\r\n(\w+)', body).group(1).decode()
            STATE["uploads"].append((name, data, root))
            self._send(201, {"result": {"item": {"path": name, "root": root}, "action": "create_file"}})
        elif self.path.startswith("/printer/gcode/script"):
            script = _up.parse_qs(_up.urlparse(self.path).query)["script"][0]
            if STATE["refuse"]:
                return self._send(400, {"error": {"code": 400, "message": STATE["refuse"]}})
            STATE["scripts"].append(script)
            self._send(200, {"result": "ok"})
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

# =============================================================================== part 4
print("== send to the Rhino, then start the laser setup ==")
from rhino.slice import jobs  # noqa: E402
from rhino.portal import security  # noqa: E402
HDR = {security.HEADER: security.TOKEN}
JOB = open(os.path.join(HERE, "fixtures", "kiri_lightsaber_cube.gcode")).read()

ok(jobs.read_stamp(JOB) == "LightSaber", "the stamp is read from the file")
ok(jobs.read_stamp("G1 X1\n" * 60 + "; RHINO_TOOL=LightSaber") == "", "...only from the first 50 lines")
ok(jobs.read_stamp("; RHINO_TOOL=Light Saber; rm") == "", "a stamp with odd characters is not trusted")
ok(jobs.safe_name("LightSaber", 'my "sign" ../x.gcode') == "LightSaber-my-sign-x.gcode", "file names are cleaned to letters, digits, - and _")
ok(jobs.safe_name("LightSaber", "") == "LightSaber-job.gcode", "...and never empty")

write_settings(CFG, {"enabled": True})
STATE.update(tool=3, klippy="ready", print_state="standby", uploads=[], scripts=[], refuse="")


def send(text=JOB, name="laser-002.gcode", hdr=HDR):
    return c.post("/api/slice/send", json={"name": name, "gcode": text}, headers=hdr)


def start(f, hdr=HDR):
    return c.post("/api/slice/start", json={"file": f}, headers=hdr)


r = send(hdr={})
ok(r.status_code == 400 and not STATE["uploads"], "no portal token: refused, nothing uploaded")
for setup, expect, what in (
        (dict(tool=1), "but BlockOne is mounted", "wrong tool mounted"),
        (dict(tool=0), "No toolhead is recorded", "no tool recorded as mounted"),
        (dict(print_state="printing"), "A job is printing", "a job running"),
        (dict(print_state="paused"), "A job is paused", "a job paused"),
        (dict(klippy="shutdown"), "Klipper is not ready", "Klipper not ready")):
    STATE.update(tool=3, klippy="ready", print_state="standby"); STATE.update(setup)
    r = send(); d = r.get_json()
    ok(r.status_code == 409 and any(expect in x for x in d["conflicts"]) and not STATE["uploads"],
       f"send refused (409) with {what}, and nothing uploaded")
STATE.update(tool=3, klippy="ready", print_state="standby")
r = send(text="G21\nG1 X10 Y10\nM3 S1000\n"); d = r.get_json()
ok(r.status_code == 409 and "not sliced with a Rhino profile" in d["conflicts"][0] and not STATE["uploads"],
   "a file with no Rhino stamp is refused")
r = send(text=JOB.replace("RHINO_TOOL=LightSaber", "RHINO_TOOL=HotJoe")); d = r.get_json()
ok(r.status_code == 409 and any("no Slice profile" in x for x in d["conflicts"]), "a file stamped for a tool with no profile is refused")
from rhino import pending  # noqa: E402
pending.mark(P, "added Needle")
r = send(); d = r.get_json()
ok(r.status_code == 409 and any("Restart Klipper first" in x for x in d["conflicts"]), "tool changes waiting for a Klipper restart: refused")
pending.clear(P)

d = c.get("/api/slice/check?tool=LightSaber").get_json()
ok(d["conflicts"] == [] and d["mounted"] == "LightSaber", "check: all clear with LightSaber mounted")
r = send(name='laser 002.gcode'); d = r.get_json()
ok(r.status_code == 200 and d["file"] == "LightSaber-laser-002.gcode" and d["setup"] == "LASER_JOB_SETUP", "all clear: sent as LightSaber-laser-002.gcode")
ok(len(STATE["uploads"]) == 1 and STATE["uploads"][0][0] == "LightSaber-laser-002.gcode" and STATE["uploads"][0][2] == "gcodes"
   and STATE["uploads"][0][1].decode() == JOB, "...uploaded to Moonraker's gcodes folder byte for byte")

r = start("LightSaber-other.gcode")
ok(r.status_code == 400 and not STATE["scripts"], "start: a file this portal did not send is refused")
r = start('LightSaber-laser-002.gcode\nG28')
ok(r.status_code == 400 and not STATE["scripts"], "start: nothing can be tacked on to the command")
STATE["tool"] = 1
r = start("LightSaber-laser-002.gcode"); d = r.get_json()
ok(r.status_code == 409 and "BlockOne is mounted" in d["conflicts"][0] and not STATE["scripts"],
   "start: tool swapped after sending - refused, nothing run")
STATE["tool"] = 3
r = start("LightSaber-laser-002.gcode", hdr={})
ok(r.status_code == 400 and not STATE["scripts"], "start: no portal token - refused")
r = start("LightSaber-laser-002.gcode"); d = r.get_json()
ok(r.status_code == 200 and STATE["scripts"] == ["LASER_JOB_SETUP FILE=LightSaber-laser-002.gcode"],
   "start: runs exactly LASER_JOB_SETUP FILE=LightSaber-laser-002.gcode")
STATE["refuse"] = "LASER_JOB_SETUP sets a work zero, which a running or paused job's RESUME would undo."
r = start("LightSaber-laser-002.gcode"); d = r.get_json()
ok(r.status_code == 400 and "RESUME would undo" in d["error"], "Klipper's own refusal is shown word for word")
STATE["refuse"] = ""
write_settings(CFG, None)
r = send(); ok(r.status_code == 400 and len(STATE["uploads"]) == 1, "slicing turned off: send refused")
ok(start("LightSaber-laser-002.gcode").status_code == 400, "...and start refused")

# =============================================================================== part 5
print("== Klipper's questions in the portal ==")
from rhino.slice import prompts  # noqa: E402

E = lambda m, t=1.0, typ="response": {"message": m, "time": t, "type": typ}
store = [E("// action:prompt_begin Old"), E("// action:prompt_show"),
         E("// action:prompt_begin Laser setup", 2.0), E("// action:prompt_text Glasses on"),
         E("// action:prompt_button_group_start"), E("// action:prompt_button Yes|_GO|primary"),
         E("// action:prompt_button No|_STOP|error"), E("// action:prompt_button_group_end"),
         E("// action:prompt_button Plain"), E("// action:prompt_footer_button Cancel|_CANCEL|bogus"),
         E("// action:prompt_show")]
q = prompts.current(store)
ok(q and q["title"] == "Laser setup" and q["items"][0] == {"text": "Glasses on"}, "reads the latest question: title and text")
ok([b["label"] for b in q["buttons"]] == ["Yes", "No", "Plain", "Cancel"] and len(q["items"][1]["group"]) == 2,
   "buttons in order, grouped as Klipper grouped them, footer last")
ok(q["buttons"][2]["command"] == "Plain" and q["buttons"][3]["color"] == "secondary",
   "a button with no command runs its label (as in Mainsail); an unknown colour falls back")
ok(prompts.current(store + [E("// action:prompt_end")]) is None, "prompt_end closes it")
ok(prompts.current(store + [E("// action:prompt_begin Next"), E("// action:prompt_text half built")]) is None,
   "a question still being built is not shown")
ok(prompts.current([E("RESPOND TYPE=command MSG=\"action:prompt_begin Fake\"", typ="command"),
                    E("// action:prompt_begin Fake", typ="command"), E("// action:prompt_show", typ="command")]) is None,
   "lines typed in the console never count as Klipper's question")
noise = [E(f"echo: line {i}", 3.0 + i) for i in range(300)]
long_store = store + noise
ok(prompts.current(long_store[-309:])["id"] == prompts.current(long_store)["id"] == q["id"],
   "a question keeps its id while newer console lines scroll older ones out of the window")
ok(prompts.current(store[:3] + store[3:] + [E("// action:prompt_begin Laser setup", 9.0), E("// action:prompt_show", 9.0)])["id"] != q["id"],
   "the same question shown again later gets a new id (an old press cannot land on it)")
ok(prompts.button(q, 9) is None and prompts.button(q, "1") is None and prompts.button(q, 1)["command"] == "_STOP",
   "button numbers outside the question are refused")

from simmoon import SimBackend  # noqa: E402
SB = SimBackend(CFG, tool=3)


class SimH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        import urllib.parse as _up
        u = _up.urlparse(self.path)
        if u.path == "/server/info":
            return self._send(200, {"result": {"klippy_state": "ready"}})
        if u.path == "/server/gcode_store":
            return self._send(200, {"result": {"gcode_store": SB.store(int(_up.parse_qs(u.query).get("count", ["200"])[0]))}})
        if u.path == "/printer/objects/query":
            st = SB.status()
            return self._send(200, {"result": {"status": {"print_stats": {"state": st["print_state"]},
                                                          "gcode_macro SWAP_TOOL": {"current_tool": st["current_tool"]}}}})
        self._send(404, {})

    def do_POST(self):
        import urllib.parse as _up
        u = _up.urlparse(self.path)
        if u.path == "/printer/gcode/script":
            err = SB.script(_up.parse_qs(u.query)["script"][0])
            return self._send(400, {"error": {"message": err}}) if err else self._send(200, {"result": "ok"})
        self._send(404, {})


srv2 = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SimH)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
app2 = create_app(CFG, f"http://127.0.0.1:{srv2.server_port}")
c2 = app2.test_client()
write_settings(CFG, None)
ok(c2.get("/api/prompt").status_code == 400, "slicing off: no question endpoint")
write_settings(CFG, {"enabled": True})
ok(c2.get("/api/prompt").get_json()["prompt"] is None, "nothing asked yet: no question")


def wait_idle():
    for _ in range(100):
        d = c2.get("/api/prompt").get_json()
        if not d["running"]:
            return d
        time.sleep(0.05)
    return d


def press_label(label, hdr=HDR):
    d = c2.get("/api/prompt").get_json()
    labels = [b["label"] for it in d["prompt"]["items"] for b in it.get("group", [])] + [b["label"] for b in d["prompt"]["footer"]]
    r = c2.post("/api/prompt/press", json={"id": d["prompt"]["id"], "n": labels.index(label)}, headers=hdr)
    return r, wait_idle()


import time  # noqa: E402
SB.script("LASER_JOB_SETUP FILE=LightSaber-cut.gcode")
d = c2.get("/api/prompt").get_json()
ok(d["prompt"]["title"] == "Laser setup" and "command" not in json.dumps(d), "the safety checklist shows - labels only, no commands sent to the page")
qid = d["prompt"]["id"]
n_before = len(SB.store(1000))
r = c2.post("/api/prompt/press", json={"id": qid, "n": 0})
ok(r.status_code == 400 and len(SB.store(1000)) == n_before, "press without the portal token: refused, nothing run")
r = c2.post("/api/prompt/press", json={"id": "1.0-0", "n": 0}, headers=HDR)
ok(r.status_code == 409 and len(SB.store(1000)) == n_before, "press on a question that is not showing: refused (409), nothing run")
r = c2.post("/api/prompt/press", json={"id": qid, "n": 7}, headers=HDR)
ok(r.status_code == 400 and len(SB.store(1000)) == n_before, "a button number not in the question: refused")
orig_run = SB.script
import threading as _th  # noqa: E402
gate = _th.Event()
def slow_script(text):
    gate.wait(5)
    return orig_run(text)
SB.script = slow_script
r1 = c2.post("/api/prompt/press", json={"id": qid, "n": 0}, headers=HDR)
r2 = c2.post("/api/prompt/press", json={"id": qid, "n": 0}, headers=HDR)
ok(r1.status_code == 200 and r2.status_code == 409 and "still doing" in r2.get_json()["error"],
   "a second press while Klipper is still busy with the first: refused (no double bed move)")
gate.set(); wait_idle(); SB.script = orig_run
d = c2.get("/api/prompt").get_json()
ok(d["prompt"]["title"].startswith("Set Z zero"), "...the first press went through once")
SB.script("_Z_ZERO_CANCEL"); SB.script("LASER_JOB_SETUP FILE=LightSaber-cut.gcode")
r, d = press_label("All checked - set focus")
ok(r.status_code == 200 and d["prompt"]["title"].startswith("Set Z zero"), "All checked: the Set Z zero window comes up")
r, d = press_label("Bed up 10 mm")
ok(any(e["type"] == "command" and e["message"] == "_Z_ZERO_MOVE D=-10" for e in SB.store(1000))
   and d["prompt"]["title"].startswith("Set Z zero"), "Bed up 10 mm runs its own command (_Z_ZERO_MOVE D=-10) and the window stays")
r, d = press_label("SET - Z zero here")
ok(d["prompt"]["title"] == "Check the test mark", "SET: test fire, then the test-mark question")
r, d = press_label("Yes - continue")
ok(d["prompt"]["title"] == "Ready to cut", "Yes: Ready to cut")
SB.set_tool(1)
r, d = press_label("Start the cut")
ok(d["prompt"] is None and "not LightSaber" in d["error"] and SB.status()["print_state"] == "standby"
   and SB.sim.pins.get("LASER_INITIALIZE", 0.0) == 0.0,
   "tool swapped before Start: Klipper refuses, its message shows, nothing starts, laser off")
SB.set_tool(3)
SB.script("LASER_JOB_SETUP FILE=LightSaber-cut.gcode")
for lab in ("All checked - set focus", "SET - Z zero here", "Yes - continue"):
    press_label(lab)
r, d = press_label("Start the cut")
ok(d["prompt"] is None and d["error"] == "" and SB.status()["print_state"] == "printing" and SB.status()["filename"] == "LightSaber-cut.gcode"
   and SB.sim.pins.get("LASER_INITIALIZE") == 1.0, "Start the cut from the portal: the file runs with the laser powered (1.4.1)")
srv2.shutdown()
write_settings(CFG, None)

srv.shutdown()
shutil.rmtree(os.path.dirname(os.path.dirname(CFG)), ignore_errors=True)
print()
print("ALL PASSED" if not fails else f"{len(fails)} problems:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
