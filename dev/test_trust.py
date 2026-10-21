"""trusted_clients editing (1.5.4): rhino/trust.py, the Portal's /api/moonraker-trust and scripts/rhino_trust.py.
Run: python3 dev/test_trust.py  (needs flask)"""
import json, os, shutil, subprocess, sys, tempfile, threading, http.server
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="rhino-trust-test-")
shutil.copytree(os.path.dirname(HERE), ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
sys.path.insert(0, ROOT + "/printer_data/config")
from rhino import trust
from rhino.errors import Fail
from rhino.portal import create_app, security

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, text=""):
    try:
        fn()
    except Fail as e:
        return text in str(e)
    return False

KIAUH = """[server]
host: 0.0.0.0
port: 7125
klippy_uds_address: ~/printer_data/comms/klippy.sock

[authorization]
trusted_clients:
    10.0.0.0/8
    127.0.0.0/8
    169.254.0.0/16
    172.16.0.0/12
    192.168.0.0/16
    FE80::/10
    ::1/128
cors_domains:
    *.lan
    *.local
    *://localhost
    *://localhost:*

# a comment that must survive
[octoprint_compat]

[history]
"""
NARROW = """[authorization]
force_logins: False
trusted_clients: 192.168.86.0/24   # the house
    127.0.0.1
cors_domains:
  *.local
"""

# ---- normalize / covers
ok(trust.normalize("192.168.86.31/24") == "192.168.86.0/24" and trust.normalize(" 192.168.86.31 ") == "192.168.86.31", "N1 ranges lose host bits; addresses stay")
ok(trust.normalize("100.64.0.0/10") == "100.64.0.0/10", "N2 the Tailscale range is allowed")
ok(raises(lambda: trust.normalize("0.0.0.0/0"), "too wide") and raises(lambda: trust.normalize("10.0.0.0/7"), "too wide"), "N3 wider than /8 refused (no trust-everyone)")
ok(raises(lambda: trust.normalize("printer.local"), "isn't an address") and raises(lambda: trust.normalize(""), "Type"), "N4 names and blanks refused")
ok(trust.covers(["192.168.0.0/16"], "192.168.86.31") and not trust.covers(["10.0.0.0/8"], "192.168.86.31"), "N5 covers")
ok(trust.covers(["127.0.0.1"], "::ffff:127.0.0.1") and not trust.covers(["printer.local"], "1.2.3.4"), "N6 IPv4-mapped counts; names never cover")

# ---- read
r = trust.read(KIAUH)
ok(r["configured"] and r["entries"][:2] == ["10.0.0.0/8", "127.0.0.0/8"] and len(r["entries"]) == 7 and not r["force_logins"], "R1 KIAUH's default list read")
r = trust.read(NARROW)
ok(r["entries"] == ["192.168.86.0/24", "127.0.0.1"], "R2 first value on the key line, inline comment, two-space continuation")
ok(not trust.read("[server]\nport: 7125\n")["configured"], "R3 no [authorization]: not configured")
ok(trust.read("[authorization]\nforce_logins: True\n")["force_logins"], "R4 force_logins noticed")

# ---- add
out = trust.add(KIAUH, ["100.64.0.0/10"])
ok(trust.read(out)["entries"][-1] == "100.64.0.0/10" and "    ::1/128\n    100.64.0.0/10\ncors_domains:" in out, "A1 added after the last entry, same indent")
ok(out.replace("    100.64.0.0/10\n", "", 1) == KIAUH, "A2 every other byte unchanged")
ok(trust.add(out, ["100.64.0.0/10"]) == out, "A3 adding again changes nothing")
out = trust.add(NARROW, ["10.1.0.0/16"])
ok(trust.read(out)["entries"] == ["192.168.86.0/24", "127.0.0.1", "10.1.0.0/16"] and "\n    10.1.0.0/16\n" in out, "A4 two-space file keeps its own indent")
out = trust.add("[authorization]\ncors_domains:\n    *.local\n\n[history]\n", ["192.168.1.0/24"])
ok(trust.read(out)["entries"] == ["192.168.1.0/24"] and out.index("trusted_clients") < out.index("[history]"), "A5 no trusted_clients key yet: added inside the section")
ok(raises(lambda: trust.add("[server]\n", ["1.2.3.0/24"]), "already trusts every address"), "A6 no [authorization]: refused, never added")

# ---- remove
out = trust.remove(trust.add(KIAUH, ["100.64.0.0/10"]), "100.64.0.0/10")
ok(out == KIAUH, "D1 remove gives the original back")
out = trust.remove(NARROW, "192.168.86.0/24")
ok(trust.read(out)["entries"] == ["127.0.0.1"], "D2 remove an entry on the key line")
ok(raises(lambda: trust.remove(KIAUH, "1.2.3.4"), "isn't in"), "D3 removing what isn't there says so")

# ---- apply
class FakeMr:
    def __init__(self, comes_back): self.back, self.restarts = comes_back, 0
    def restart_moonraker(self): self.restarts += 1
    def klippy_state(self): return "ready" if self.back else "offline"
conf = os.path.join(ROOT, "moonraker.conf"); open(conf, "w").write(KIAUH); os.chmod(conf, 0o640)
t = [0.0]
clock = dict(sleep=lambda s: t.__setitem__(0, t[0] + s), now=lambda: t[0])
mr = FakeMr(True); b = trust.apply(conf, trust.add(KIAUH, ["100.64.0.0/10"]), ROOT + "/bk", mr, **clock)
ok(mr.restarts == 1 and "100.64.0.0/10" in open(conf).read() and open(b).read() == KIAUH, "P1 backup, write, restart through the API")
ok(oct(os.stat(conf).st_mode & 0o777) == "0o640", "P2 file keeps its mode")
before = open(conf).read(); mr = FakeMr(False)
ok(raises(lambda: trust.apply(conf, trust.add(before, ["10.9.0.0/16"]), ROOT + "/bk", mr, **clock), "old moonraker.conf is back"), "P3 Moonraker doesn't come back: says so")
ok(open(conf).read() == before, "P4 ... and the old file is back")

# ---- Portal routes
MR = {"trusted": {"10.0.0.5", "127.0.0.1"}, "restarts": 0, "state": "standby"}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        if self.path == "/access/user":
            return self._send(200, {"result": {"username": "_TRUSTED_USER_"}}) if ip in MR["trusted"] else self._send(401, {})
        if self.path.startswith("/server/info"): return self._send(200, {"result": {"klippy_state": "ready"}})
        if self.path.startswith("/printer/objects/query"):
            return self._send(200, {"result": {"status": {"print_stats": {"state": MR["state"]}, "gcode_macro SWAP_TOOL": {"current_tool": 3}}}})
        self._send(404, {})
    def do_POST(self):
        if self.path == "/server/restart": MR["restarts"] += 1; return self._send(200, {"result": "ok"})
        self._send(404, {})
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
cfg = ROOT + "/printer_data/config"
open(cfg + "/moonraker.conf", "w").write("[authorization]\ntrusted_clients:\n    127.0.0.0/8\n    10.0.0.0/24\n")
app = create_app(cfg, f"http://127.0.0.1:{srv.server_port}")
import rhino.trust as _t
_t.time.sleep = lambda s: None                       # no real waiting in tests
c = app.test_client()
def call(method, ip="10.0.0.5", body=None):
    app.config["ACCESS"]._cache.clear()
    h = {"X-Real-IP": ip, security.HEADER: security.TOKEN}
    return getattr(c, method)("/api/moonraker-trust", json=body, headers=h, environ_base={"REMOTE_ADDR": "127.0.0.1"})
j = call("get").get_json()
ok(j["configured"] and j["entries"] == ["127.0.0.0/8", "10.0.0.0/24"] and j["address"] == "10.0.0.5" and j["covered"], "W1 GET: list, this screen's address, covered")
ok(any(s["entry"] == "100.64.0.0/10" and "Tailscale" in s["why"] for s in j["suggestions"]), "W2 Tailscale offered")
ok(call("post", ip="10.0.0.99", body={"entry": "10.0.0.99"}).status_code == 401, "W3 an untrusted screen can't add itself")
r = call("post", body={"entry": "100.64.0.0/10"})
ok(r.status_code == 200 and "100.64.0.0/10" in r.get_json()["entries"] and MR["restarts"] == 1, "W4 add from a trusted screen: written, Moonraker restarted")
ok(len(os.listdir(ROOT + "/printer_data/rhino_data/config_backups")) >= 1, "W5 backup kept in rhino_data/config_backups")
r = call("delete", body={"entry": "10.0.0.0/24"})
ok(r.status_code == 400 and "lets this screen" in r.get_json()["error"], "W6 can't remove what lets this screen in")
r = call("delete", body={"entry": "127.0.0.0/8"})
ok(r.status_code == 400 and "127.0.0.1" in r.get_json()["error"], "W7 can't remove what lets the Portal in")
r = call("delete", body={"entry": "100.64.0.0/10"})
ok(r.status_code == 200 and "100.64.0.0/10" not in r.get_json()["entries"], "W8 remove another entry")
MR["state"] = "printing"
r = call("post", body={"entry": "192.168.5.0/24"})
ok(r.status_code == 400 and "job is running" in r.get_json()["error"], "W9 refused during a job")
MR["state"] = "standby"
ok(call("post", body={"entry": "0.0.0.0/0"}).status_code == 400, "W10 trust-everyone refused")

# ---- installer step
conf2 = ROOT + "/inst.conf"; open(conf2, "w").write("[authorization]\ntrusted_clients:\n    192.168.99.0/24\n")
script = os.path.join(cfg, "scripts", "rhino_trust.py")
p = subprocess.run([sys.executable, script, "ensure", "--conf", conf2, "--backup-dir", ROOT + "/ib", "--dry"], capture_output=True, text=True)
ok(p.returncode == 0 and "would add trusted_clients 127.0.0.0/8" in p.stdout and open(conf2).read().count("\n") == 3, "I1 dry run: says what it would add, changes nothing")
p = subprocess.run([sys.executable, script, "ensure", "--conf", conf2, "--backup-dir", ROOT + "/ib", "--moonraker", f"http://127.0.0.1:{srv.server_port}"], capture_output=True, text=True)
ok(p.returncode == 0 and "127.0.0.0/8" in trust.read(open(conf2).read())["entries"] and "restarted" in p.stdout, "I2 adds what's missing, restarts Moonraker")
p = subprocess.run([sys.executable, script, "ensure", "--conf", conf2, "--backup-dir", ROOT + "/ib", "--dry"], capture_output=True, text=True)
ok("already covers" in p.stdout, "I3 run again: nothing to add")
open(conf2, "w").write("[server]\nport: 7125\n")
p = subprocess.run([sys.executable, script, "ensure", "--conf", conf2, "--backup-dir", ROOT + "/ib"], capture_output=True, text=True)
ok("no [authorization]" in p.stdout and open(conf2).read() == "[server]\nport: 7125\n", "I4 no [authorization]: left alone")

srv.shutdown()
shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
