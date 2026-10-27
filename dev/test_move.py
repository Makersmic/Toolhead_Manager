"""Moving to another host (docs/migrate-7050.md): back up on one machine, restore on a freshly installed one.

    python3 dev/test_move.py   (needs flask)

test_backup.py restores on the same machine. This is the move itself, with two machines side by side in temp
folders, each with its own Portal and its own stub Moonraker:

  "mainsailos" (the Pi) has been used: a user tool, a second board, wizard devices, job hooks, maintenance with a
  work log, saved variables, a SAVE_CONFIG block, a tool photo, slice profiles, Studio settings, job history and
  its own moonraker.conf. "rhino" (the 7050) is a fresh install of the same version, with Mainsail's
  mainsail.cfg as a symlink the way MainsailOS and KIAUH make it.

  1  the Pi's backup downloads, uploads to the 7050 and checks out
  2  a full restore wants the 7050's name typed, and refuses while the board isn't plugged in (nothing changes)
  3  then restores: every file the Pi had is on the 7050 byte for byte, the 7050's program files and its own
     mainsail.cfg symlink are left alone, and the Portal there reads back the same tools, devices, hooks and care
  4  the way back (section 11): a change made on the 7050 travels back to the Pi the same way
"""
import io, json, os, shutil, socket, sys, tempfile, threading, urllib.parse, http.server
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


try:
    import flask  # noqa: F401
except ImportError:
    print("SKIP move test: flask is not installed")
    sys.exit(0)

ROOT = tempfile.mkdtemp(prefix="rhino-move-")
IGNORE = shutil.ignore_patterns("__pycache__", ".git", "node_modules", "registry_backups", "custom_tools.json",
                                "maintenance", "job_hooks.json", "job_hooks.history.json")


def stub_moonraker(state):
    """Just enough Moonraker for backups and restores (same behaviour as test_backup.py's stub)."""
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def _q(self):
            u = urllib.parse.urlparse(self.path)
            return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

        def do_GET(self):
            p, q = self._q()
            if p == "/server/info":
                self._send(200, {"result": {"klippy_state": "ready"}})
            elif p == "/printer/objects/query":
                self._send(200, {"result": {"status": {"print_stats": {"state": "standby"}, "gcode_macro SWAP_TOOL": {"current_tool": 1}}}})
            elif p == "/server/database/list":
                self._send(200, {"result": {"namespaces": sorted(state["db"]), "backups": []}})
            elif p == "/server/database/item":
                self._send(200, {"result": {"namespace": q["namespace"], "key": None, "value": state["db"].get(q["namespace"], {})}})
            elif p == "/server/history/list":
                s, n = int(q.get("start", 0)), int(q.get("limit", 50))
                self._send(200, {"result": {"count": len(state["jobs"]), "jobs": state["jobs"][s:s + n]}})
            else:
                self._send(404, {})

        def do_POST(self):
            p, q = self._q()
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            dbdir = state["dbdir"]
            if p == "/printer/firmware_restart":
                state["restarts"] += 1; self._send(200, {"result": "ok"})
            elif p == "/server/database/backup":
                os.makedirs(dbdir, exist_ok=True)
                with open(os.path.join(dbdir, q["filename"]), "w") as f:
                    json.dump({"db": state["db"], "jobs": state["jobs"]}, f)
                self._send(200, {"result": {}})
            elif p == "/server/database/restore":
                with open(os.path.join(dbdir, q["filename"])) as f:
                    saved = json.load(f)
                state["db"], state["jobs"] = saved["db"], saved["jobs"]
                self._send(200, {"result": {"restored_tables": ["job_history"]}})
            elif p == "/server/database/item":
                state["db"].setdefault(body["namespace"], {})[body["key"]] = body["value"]; self._send(200, {"result": {}})
            else:
                self._send(404, {})

        def do_DELETE(self):
            p, q = self._q()
            if p == "/server/database/backup":
                try:
                    os.remove(os.path.join(state["dbdir"], q["filename"]))
                except OSError:
                    pass
            self._send(200, {"result": {}})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Machine:
    """A fresh install: the release's files in ~/printer_data/config, Mainsail's symlinked mainsail.cfg."""
    def __init__(self, host):
        self.host = host
        self.home = os.path.join(ROOT, host)
        self.pd = os.path.join(self.home, "printer_data")
        self.cfg = os.path.join(self.pd, "config")
        shutil.copytree(REPO, self.cfg, ignore=IGNORE)
        shutil.rmtree(os.path.join(self.cfg, "dev"), ignore_errors=True)
        os.makedirs(os.path.join(self.home, "mainsail-config"))
        open(os.path.join(self.home, "mainsail-config", "client.cfg"), "w").write(f"# Mainsail's client.cfg on {host}\n")
        os.symlink(os.path.join(self.home, "mainsail-config", "client.cfg"), os.path.join(self.cfg, "mainsail.cfg"))
        open(os.path.join(self.cfg, "moonraker.conf"), "w").write(f"[server]\nhost: 0.0.0.0\n# {host}'s own\n")
        self.mr = {"db": {"rhino_studio": {}, "mainsail": {}}, "jobs": [], "restarts": 0,
                   "dbdir": os.path.join(self.pd, "backup", "database")}
        self.srv = stub_moonraker(self.mr)
        os.environ["RHINO_BACKUP_DIR"] = os.path.join(self.home, "rhino-backups")
        os.environ["HOME"] = self.home
        self.app = create_app(self.cfg, f"http://127.0.0.1:{self.srv.server_port}")
        self.c = self.app.test_client()

    def __enter__(self):
        B.socket.gethostname = lambda: self.host       # the Portal asks the OS for its name
        os.environ["HOME"] = self.home
        return self

    def __exit__(self, *a):
        B.socket.gethostname = REAL_HOSTNAME

    def post(self, url, body=None):
        return self.c.post(url, json=body if body is not None else {}, headers=HDR)

    def get(self, url):
        return self.c.get(url).get_json() or {}

    def files(self):
        """Everything a backup should carry: config (not symlinks, not program files) and photos."""
        out = {}
        for base, pre in ((self.cfg, "config/"), (self.app.config["BACKUP"].paths.images_dir, "images/")):
            for root, dirs, fs in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
                for fn in fs:
                    full = os.path.join(root, fn)
                    arc = pre + os.path.relpath(full, base).replace(os.sep, "/")
                    if not os.path.islink(full) and not B.is_program(arc) and not B.SKIP_REDERIVABLE.search(arc[7:] if pre == "config/" else arc):
                        out[arc] = open(full, "rb").read()
        return out


# One copy of the program for both machines: same version on both sides is the plan (migrate-7050 section 7.1).
pi_tmp = os.path.join(ROOT, "program")
shutil.copytree(REPO, pi_tmp, ignore=IGNORE)
sys.path.insert(0, pi_tmp)
from rhino.portal import create_app, security  # noqa: E402
from rhino import backup as B  # noqa: E402
HDR = {security.HEADER: security.TOKEN}
REAL_HOSTNAME = socket.gethostname
REAL_EXISTS = os.path.exists


def board_plugged(yes):
    os.path.exists = (lambda p: True if str(p).startswith("/dev/serial/") else REAL_EXISTS(p)) if yes else REAL_EXISTS


pi, n7050 = Machine("mainsailos"), Machine("rhino")

# ---------------------------------------------------------------- the Pi, after months of use
with pi:
    r = pi.post("/api/hardware/boards", {"name": "ebb", "preset": "ebb_v1_2", "link": "can", "canbus_uuid": "0123456789ab"})
    ok(r.status_code == 200, "Pi: a second board (EBB over CAN)")
    pins = {k: [p["pin"] for p in pi.get(f"/api/hardware/pins?kind={k}")["pins"] if p["pin"].startswith("ebb:")] for k in ("pwm_out", "digital_in")}
    r1 = pi.post("/api/hardware/devices", {"device": "fan", "name": "driver_fan", "wires": "4", "cycle": 0.00004, "pins": {"pin": pins["pwm_out"][0]}})
    r2 = pi.post("/api/hardware/devices", {"device": "interlock", "name": "lid", "sensor_type": "mech_nc", "pins": {"pin": next(p for p in pins["digital_in"] if p != pins["pwm_out"][0])}})
    ok(r1.status_code == 200 and r2.status_code == 200, "Pi: a 4-wire driver fan and a lid interlock on it"
       + "".join(f" ({x.get_json().get('error')})" for x in (r1, r2) if x.status_code != 200))
    st = pi.get("/api/hooks")
    r = pi.post("/api/hooks", {"rev": st["rev"], "hooks": {"machine": {"before_start": ["M117 Pi hooks"]}}})
    ok(r.status_code == 200, "Pi: a job hook")
    mdir = os.path.join(pi.cfg, "myrhino", "maintenance")
    os.makedirs(mdir, exist_ok=True)
    open(os.path.join(mdir, "tasks.json"), "w").write('{"version": 2, "tasks": {"belts": {"every_hours": 200}}}')
    open(os.path.join(mdir, "log.json"), "w").write('[{"task": "belts", "done": "2026-09-01", "note": "tensioned"}]')
    open(os.path.join(pi.cfg, "variables.save"), "w").write("[Variables]\ncurrent_tool = 3\ncnc_g54_z = 12.345\n")
    open(os.path.join(pi.cfg, "printer.cfg"), "a").write("\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [bed_mesh default]\n#*# version = 1\n")
    open(os.path.join(pi.cfg, "myrhino", "slice_profiles.json"), "w").write('{"rev": 3, "profiles": {"PLA fast": {}}}')
    img = pi.app.config["BACKUP"].paths.images_dir
    os.makedirs(img, exist_ok=True)
    open(os.path.join(img, "hotjoe-1.jpg"), "wb").write(b"\xff\xd8 photo of HotJoe")
    open(os.path.join(pi.cfg, "moonraker.conf"), "a").write("[authorization]\ntrusted_clients:\n  192.168.86.0/24\n")
    pi.mr["db"]["rhino_studio"] = {"theme": "dark", "mesh_seen": {"default": 1}}
    pi.mr["jobs"] = [{"job_id": f"{i:06X}", "filename": f"part{i}.gcode", "status": "completed"} for i in range(240)]
    before_move = pi.files()
    pi_tools, pi_devices = pi.get("/api/hardware/devices")["devices"], pi.get("/api/hardware/boards")
    pi_hooks = pi.get("/api/hooks")["hooks"]
    r = pi.post("/api/backup")
    j = r.get_json() or {}
    ok(r.status_code == 200 and j.get("archive", {}).get("complete"), "Pi: Back up now")
    name = j["archive"]["name"]
    blob = pi.c.get(f"/api/backup/file/{name}").data
    ok(blob[:2] == b"PK", f"Pi: the backup downloads ({len(blob) // 1024} KB)")

# ---------------------------------------------------------------- the 7050: fresh install, then the restore
with n7050:
    mainsail_link = os.readlink(os.path.join(n7050.cfg, "mainsail.cfg"))
    r = n7050.c.post("/api/backup/upload", data={"archive": (io.BytesIO(blob), name)}, headers=HDR, content_type="multipart/form-data")
    ok(r.status_code == 200 and (r.get_json() or {}).get("archive", {}).get("complete"), "7050: the Pi's backup uploads and checks out")
    r = n7050.post("/api/restore", {"archive": name, "item": "all", "confirm": "mainsailos"})
    ok(r.status_code == 400 and "rhino" in r.get_json()["error"], "7050: typing the Pi's name is refused (it wants this machine's: rhino)")
    untouched = n7050.files()
    board_plugged(False)
    r = n7050.post("/api/restore", {"archive": name, "item": "all", "confirm": "rhino"})
    ok(r.status_code == 400 and "isn't connected here" in r.get_json()["error"], "7050: with the Octopus unplugged, a full restore is refused")
    ok(n7050.files() == untouched, "7050: ... and nothing changed")
    plan = n7050.post("/api/restore/plan", {"archive": name, "item": "maintenance"}).get_json() or {}
    ok(plan.get("ok") and "config/myrhino/maintenance/log.json" in plan["plan"].get("add", []) + plan["plan"].get("replace", []),
       "7050: a plan shows what would change before anything does")
    board_plugged(True)
    rs0 = n7050.mr["restarts"]
    try:
        r = n7050.post("/api/restore", {"archive": name, "item": "all", "confirm": "rhino"})
    finally:
        board_plugged(False)
    j = r.get_json() or {}
    ok(r.status_code == 200 and j.get("ok"), f"7050: full restore ({j.get('note') or j.get('error')})")
    after = n7050.files()
    diff = sorted(k for k in before_move if after.get(k) != before_move[k])
    ok(not diff, f"7050: every file the Pi had is here, byte for byte ({len(before_move)} files)" + (f"; differ: {diff[:6]}" if diff else ""))
    ok(os.path.islink(os.path.join(n7050.cfg, "mainsail.cfg")) and os.readlink(os.path.join(n7050.cfg, "mainsail.cfg")) == mainsail_link,
       "7050: its own mainsail.cfg symlink is untouched (backups skip symlinks)")
    ok(open(os.path.join(n7050.cfg, "moonraker.conf")).read() == before_move["config/moonraker.conf"].decode(),
       "7050: moonraker.conf is the Pi's (the doc says to check trusted_clients after)")
    ok(n7050.mr["restarts"] == rs0 + 1, "7050: Klipper was restarted once")
    ok(len(n7050.mr["jobs"]) == 240 and n7050.mr["db"]["rhino_studio"].get("theme") == "dark",
       "7050: Moonraker's database came over (240 jobs, Studio settings)")
    ok(n7050.get("/api/hardware/devices")["devices"] == pi_tools and n7050.get("/api/hardware/boards") == pi_devices,
       "7050: the Portal reads back the same board and devices")
    ok(n7050.get("/api/hooks")["hooks"] == pi_hooks, "7050: the same job hooks")
    hooks_cfg = open(os.path.join(n7050.cfg, "myrhino", "job_hooks.cfg")).read()
    ok("lid" in hooks_cfg and "Pi hooks" in hooks_cfg, "7050: job_hooks.cfg has the Pi's hooks and interlock")
    n7050.app.config["SERVICE"].write_hooks_cfg() if "SERVICE" in n7050.app.config else None
    ok(open(os.path.join(n7050.cfg, "myrhino", "job_hooks.cfg")).read() == hooks_cfg,
       "7050: rewriting job_hooks.cfg from the restored registry gives the same file (as at Portal start)")
    names = [a["name"] for a in n7050.get("/api/backup")["archives"]]
    ok(j.get("before") in names and name in names, "7050: its fresh state was backed up first, and the Pi's archive is kept")

    # ------------------------------------------------------------ used on the 7050, then the way back
    st = n7050.get("/api/hooks")
    n7050.post("/api/hooks", {"rev": st["rev"], "hooks": {"machine": {"before_start": ["M117 7050 hooks"]}}})
    n7050.mr["jobs"].append({"job_id": "0000F0", "filename": "load-test.gcode", "status": "completed"})
    r = n7050.post("/api/backup")
    back = (r.get_json() or {}).get("archive", {}).get("name")
    blob2 = n7050.c.get(f"/api/backup/file/{back}").data
    ok(r.status_code == 200 and blob2[:2] == b"PK", "7050: a backup after the load test")

with pi:
    r = pi.c.post("/api/backup/upload", data={"archive": (io.BytesIO(blob2), back)}, headers=HDR, content_type="multipart/form-data")
    ok(r.status_code == 200, "way back: the 7050's backup uploads to the Pi")
    board_plugged(True)
    try:
        r = pi.post("/api/restore", {"archive": back, "item": "all", "confirm": "mainsailos"})
    finally:
        board_plugged(False)
    ok(r.status_code == 200, f"way back: full restore on the Pi ({(r.get_json() or {}).get('note', '')[:60]})")
    ok(pi.get("/api/hooks")["hooks"]["machine"]["before_start"] == ["M117 7050 hooks"] and len(pi.mr["jobs"]) == 241,
       "way back: the change made on the 7050 and its job history are on the Pi")

for m in (pi, n7050):
    m.srv.shutdown()
if fails:
    print(f"\n{len(fails)} FAILED (kept {ROOT})")
    sys.exit(1)
shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED")
