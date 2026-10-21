"""The Portal follows Moonraker's trusted_clients (1.5.4). Run: python3 dev/test_access.py  (needs flask)

A stub Moonraker with [authorization]: trusted addresses only, read from X-Real-IP like Moonraker's use_xheaders."""
import json, os, shutil, sys, tempfile, threading, http.server
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="rhino-access-test-")
shutil.copytree(os.path.dirname(HERE), ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
sys.path.insert(0, ROOT + "/printer_data/config")
from rhino.portal import create_app, security

MR = {"auth": True, "trusted": {"10.0.0.5", "127.0.0.1"}, "seen": []}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        if self.path == "/access/user":
            MR["seen"].append(ip)
            if not MR["auth"]:
                return self._send(404, {})
            return self._send(200, {"result": {"username": "_TRUSTED_USER_"}}) if ip in MR["trusted"] else self._send(401, {})
        if self.path.startswith("/server/info"):
            return self._send(200, {"result": {"klippy_state": "ready"}})
        if self.path.startswith("/printer/objects/query"):
            return self._send(200, {"result": {"status": {"print_stats": {"state": "standby"}, "gcode_macro SWAP_TOOL": {"current_tool": 3}}}})
        self._send(404, {})


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
app = create_app(ROOT + "/printer_data/config", f"http://127.0.0.1:{srv.server_port}")
acc, mr = app.config["ACCESS"], app.config["MOONRAKER"]
c = app.test_client()
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


def get(path, ip="10.0.0.9", peer="127.0.0.1", headers=None):
    acc._cache.clear()
    h = {"X-Real-IP": ip} if peer == "127.0.0.1" else {}
    h.update(headers or {})
    return c.get(path, headers=h, environ_base={"REMOTE_ADDR": peer})


ok(get("/api/state", ip="10.0.0.5").status_code == 200, "T1 trusted address (via nginx X-Real-IP) gets in")
r = get("/api/state", ip="10.0.0.9"); j = r.get_json()
ok(r.status_code == 401 and j["untrusted"] and j["address"] == "10.0.0.9" and "trusted_clients" in j["error"], "T2 untrusted address: 401 naming the address and trusted_clients")
ok(get("/api/state", peer="10.0.0.9", headers={"X-Real-IP": "10.0.0.5"}).status_code == 401, "T3 straight to :5000 from the LAN can't claim a trusted address")
ok(get("/api/state", peer="10.0.0.5").status_code == 200, "T4 straight to :5000 from a trusted address works")
acc._cache.clear()
r = c.post("/api/restart", headers={security.HEADER: security.TOKEN, "X-Real-IP": "10.0.0.9"}, environ_base={"REMOTE_ADDR": "127.0.0.1"})
ok(r.status_code == 401, "T5 a change from an untrusted address is refused before the route")
ok(get("/").status_code == 200 and get("/static/portal.js").status_code == 200, "T6 pages and static files aren't gated")
MR["seen"].clear(); acc._cache.clear()
for _ in range(5):
    c.get("/api/options", headers={"X-Real-IP": "10.0.0.5"}, environ_base={"REMOTE_ADDR": "127.0.0.1"})
ok(MR["seen"].count("10.0.0.5") == 1, "T7 five calls cost one Moonraker check (kept 60 s)")
ok(acc.decide("10.0.0.9", now=10**9)[0] is False and acc.decide("10.0.0.9", now=10**9 + 6)[0] is False, "T8 refusals kept only 5 s")
ok(acc.seen, "T9 Portal remembers Moonraker has trusted_clients")
port = srv.server_port
mr.url = "http://127.0.0.1:9"
r = get("/api/state", ip="10.0.0.5")
ok(r.status_code == 503 and "isn't answering" in r.get_json()["error"], "T10 Moonraker down after trust was seen: 503, no guessing")
mr.url = f"http://127.0.0.1:{port}"
MR["auth"] = False
ok(get("/api/state", ip="10.0.0.9").status_code == 200 and not acc.seen, "T11 no [authorization]: everyone, as before")
mr.url = "http://127.0.0.1:9"
ok(get("/api/state", ip="10.0.0.9").status_code == 200, "T12 never seen + Moonraker down: works as before")
mr.url = f"http://127.0.0.1:{port}"

srv.shutdown()
shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
