"""Back up now and restore (1.7). Run: python3 dev/test_backup.py  (needs flask)

A stub Moonraker answers like the real one (endpoints and behaviour read from Arksine/moonraker@b559b9a):
database backup/restore refuse while printing, a namespace read with no key returns all of it, history
pages with limit/start. Test names cite the invariants (docs/invariants.md)."""
import io, json, os, re, shutil, socket, sys, threading, time, zipfile, http.server, urllib.parse
sys.dont_write_bytecode = True
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-backup-test-")
PD = ROOT + "/printer_data"
CFG = PD + "/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT                  # klipper-backup and ~/rhino-backups live under the test home
from rhino.portal import create_app, security
from rhino import backup as B

# ---------------------------------------------------------------- stub moonraker
M = {"print_state": "standby", "restarts": 0, "db": {"rhino_studio": {"theme": "dark", "mesh_seen": {"bed-60": 1}},
                                                       "mainsail": {"uiSettings": {"mode": "dark"}}},
     "jobs": [{"job_id": f"{i:06X}", "filename": f"part{i}.gcode", "status": "completed"} for i in range(123)],
     "restored": None, "fail_ns": None}
DBDIR = PD + "/backup/database"


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _q(self):
        u = urllib.parse.urlparse(self.path)
        return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

    def do_GET(self):
        p, q = self._q()
        if p == "/server/info": self._send(200, {"result": {"klippy_state": "ready"}})
        elif p == "/printer/objects/query":
            self._send(200, {"result": {"status": {"print_stats": {"state": M["print_state"]}, "gcode_macro SWAP_TOOL": {"current_tool": 1}}}})
        elif p == "/server/database/list": self._send(200, {"result": {"namespaces": sorted(M["db"]), "backups": os.listdir(DBDIR) if os.path.isdir(DBDIR) else []}})
        elif p == "/server/database/item":
            if q["namespace"] == M["fail_ns"]: return self._send(500, {})
            self._send(200, {"result": {"namespace": q["namespace"], "key": None, "value": M["db"].get(q["namespace"], {})}})
        elif p == "/server/history/list":
            s, l = int(q.get("start", 0)), int(q.get("limit", 50))
            self._send(200, {"result": {"count": len(M["jobs"]), "jobs": M["jobs"][s:s + l]}})
        else: self._send(404, {})

    def do_POST(self):
        p, q = self._q()
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        busy = M["print_state"] in ("printing", "paused")
        if p == "/printer/firmware_restart": M["restarts"] += 1; self._send(200, {"result": "ok"})
        elif p == "/server/database/backup":
            if busy: return self._send(400, {"error": {"message": "Cannot backup when Klipper is printing"}})
            os.makedirs(DBDIR, exist_ok=True)
            with open(f"{DBDIR}/{q['filename']}", "w") as f: json.dump(M["db"], f)
            self._send(200, {"result": {"backup_path": f"{DBDIR}/{q['filename']}"}})
        elif p == "/server/database/restore":
            if busy: return self._send(400, {})
            with open(f"{DBDIR}/{q['filename']}") as f: M["db"] = json.load(f)
            M["restored"] = q["filename"]; self._send(200, {"result": {"restored_tables": ["job_history"]}})
        elif p == "/server/database/item":
            M["db"].setdefault(body["namespace"], {})[body["key"]] = body["value"]; self._send(200, {"result": {}})
        else: self._send(404, {})

    def do_DELETE(self):
        p, q = self._q()
        if p == "/server/database/backup":
            try: os.remove(f"{DBDIR}/{q['filename']}")
            except OSError: pass
            self._send(200, {"result": {}})
        else: self._send(404, {})


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
MR = f"http://127.0.0.1:{srv.server_port}"
app = create_app(CFG, MR)
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
SVC = app.config["BACKUP"]
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


def post(url, body=None):
    return c.post(url, json=body or {}, headers=HDR)


def archives():
    return c.get("/api/backup").get_json()["archives"]


# serial paths in the shipped config are /dev/serial/by-id/... that don't exist here; make them exist for "same machine"
def cfg_serials():
    out = []
    for root, _, files in os.walk(CFG):
        for fn in files:
            if fn.endswith(".cfg"):
                sec = ""
                for line in open(os.path.join(root, fn), encoding="utf-8", errors="replace"):
                    s = line.split("#", 1)[0].strip()
                    m = re.match(r"^\[([^\]]+)\]", s)
                    if m: sec = m.group(1).lower()
                    elif sec.startswith("mcu") and re.match(r"^serial\s*[:=]", s): out.append(re.split(r"[:=]", s, maxsplit=1)[1].strip())
    return out


# ---------------------------------------------------------------- INV-B5: the code's inventory is the doc's table
doc = open(os.path.join(REPO, "docs", "phase0-spine.md"), encoding="utf-8").read()
tbl = doc.split("## Backup inventory", 1)[1].split("\n## ", 1)[0]
rows = [[x.strip() for x in l.strip().strip("|").split("|")] for l in tbl.splitlines() if l.startswith("|") and "---" not in l][1:]
should = [r[0] for r in rows if len(r) >= 4 and r[3].startswith("✅")]
ok(should and all(r in B.DOC_ROWS for r in should), f"INV-B5: every ✅ row of the inventory table is in backup.DOC_ROWS ({len(should)} rows)")
ok(all(v in B.INVENTORY for v in B.DOC_ROWS.values()), "INV-B5: every DOC_ROWS entry maps to an INVENTORY id")
ok(not [k for k in B.DOC_ROWS if k not in [r[0] for r in rows]], "INV-B5: DOC_ROWS names no row the table doesn't have")

# ---------------------------------------------------------------- make one
r = post("/api/backup"); j = r.get_json()
ok(r.status_code == 200 and j["ok"] and j["archive"]["complete"], f"Back up now makes a complete archive ({j.get('archive', {}).get('name')})")
name = j["archive"]["name"]
path = os.path.join(ROOT, "rhino-backups", name)
ok(os.path.isfile(path) and not path.startswith(CFG), "the archive is in ~/rhino-backups, outside the config folder")
with zipfile.ZipFile(path) as z:
    names = set(z.namelist()); man = json.loads(z.read("manifest.json"))
    hist = json.loads(z.read("moonraker/history.json"))
ok("config/printer.cfg" in names and "config/variables.cfg" in names and "config/myrhino/bed_mesh.cfg" in names, "config files are in it")
ok(not any(n.startswith("config/.git/") for n in names), "config/.git is left out")
ok("moonraker/moonraker-sql.db" in names, "Moonraker's database (its own backup) is in it")
ok(len(hist) == 123, f"every job is in history.json, across pages ({len(hist)} of 123)")
ok("moonraker/namespaces/rhino_studio.json" in names and "moonraker/namespaces/mainsail.json" in names, "every namespace is in it as JSON")
ok(all(f["path"] in names for f in man["files"]) and man["host"] == socket.gethostname(), "the manifest lists every file with its hash")
ok(not os.listdir(DBDIR), "Moonraker's temporary database copy is deleted again")
gz = c.get(f"/api/backup/file/{name}")
ok(gz.status_code == 200 and gz.data[:2] == b"PK", "the archive downloads")
ok(c.get("/api/backup/file/..%2Fetc%2Fpasswd").status_code in (400, 404), "a download name that isn't a backup is refused")
ok(post("/api/backup", None).status_code == 200 and c.post("/api/backup").status_code == 400, "Back up now needs the page token")

# ---------------------------------------------------------------- INV-B4: complete or refused
before = {a["name"] for a in archives()}
M["fail_ns"] = "mainsail"
r = post("/api/backup"); j = r.get_json()
ok(r.status_code == 400 and "Nothing was kept" in j.get("error", ""), f"INV-B4: a namespace that can't be read refuses the backup ({j.get('error')})")
ok({a["name"] for a in archives()} == before and not [f for f in os.listdir(SVC.dir) if f.endswith(".part")], "INV-B4: nothing is left behind (no new archive, no .part)")
M["fail_ns"] = None
unread = os.path.join(CFG, "myrhino", "unreadable.json")
open(unread, "w").write("{}")
_real_open = open
def _deny(f, *a, **k):
    if str(f) == unread: raise PermissionError(13, "Permission denied")
    return _real_open(f, *a, **k)
B.open = _deny                                       # works as root too
r = post("/api/backup")
ok(r.status_code == 400 and "unreadable.json" in r.get_json()["error"], "INV-B4: a config file that can't be read refuses the backup and names it")
del B.open; os.remove(unread)
M["print_state"] = "printing"
r = post("/api/backup")
ok(r.status_code == 400 and "Not during a job" in r.get_json()["error"], "no backup during a job")
M["print_state"] = "standby"

# damaged and foreign uploads
bad = io.BytesIO(open(path, "rb").read())
zb = io.BytesIO()
with zipfile.ZipFile(bad) as zi, zipfile.ZipFile(zb, "w") as zo:
    for n in zi.namelist():
        d = zi.read(n)
        zo.writestr(n, d + b"x" if n == "config/printer.cfg" else d)
r = c.post("/api/backup/upload", data={"archive": (io.BytesIO(zb.getvalue()), "rhino-other-20261001-120000.zip")}, headers=HDR, content_type="multipart/form-data")
ok(r.status_code == 400 and "damaged" in r.get_json()["error"], "INV-B4: an upload with a changed file is refused (checksum)")
r = c.post("/api/backup/upload", data={"archive": (io.BytesIO(b"hello"), "rhino-x-1.zip")}, headers=HDR, content_type="multipart/form-data")
ok(r.status_code == 400, "an upload that isn't a zip is refused")
r = c.post("/api/backup/upload", data={"archive": (io.BytesIO(open(path, "rb").read()), "rhino-other-20261001-120000.zip")}, headers=HDR, content_type="multipart/form-data")
ok(r.status_code == 200 and r.get_json()["archive"]["complete"], "a good backup from another machine can be added")

# ---------------------------------------------------------------- INV-B8: GitHub status never claims a push that didn't happen
g = c.get("/api/backup").get_json()["github"]
ok(g["state"] == "not_installed", "INV-B8: no klipper-backup -> 'not installed', not 'pushed'")
kb = os.path.join(ROOT, "klipper-backup"); os.makedirs(kb)
open(kb + "/script.sh", "w").write("#!/bin/bash\necho 'pushing'\nexit 1\n")
ok(B.github_status(SVC.paths.state_dir, ROOT)["state"] == "no_env", "INV-B8: klipper-backup without .env -> 'no .env'")
open(kb + "/.env", "w").write("x=1\n")
st = SVC.push_github("t")
ok(st["state"] == "failed" and st["last"]["code"] == 1, "INV-B8: a failed push is shown as failed")
# like the real klipper-backup: only flags; a bare argument gets its usage error and exit 1
open(kb + "/script.sh", "w").write('#!/bin/bash\nif [ -n "$1" ] && [ "$1" != "--commit_message" ]; then echo "Unknown option: $1"; echo "script.sh --debug"; exit 1; fi\necho "ok $2"\n')
st = SVC.push_github("rhino_backup_now")
ok(st["state"] == "ok" and "rhino_backup_now" in " ".join(st["last"]["tail"]), "the message goes to klipper-backup as --commit_message (a bare argument is refused)")
st = SVC.push_github("")
ok(st["state"] == "ok", "a push that worked is shown as ok")

# ---------------------------------------------------------------- keep 10
for i in range(12):
    SVC.now = (lambda k: (lambda: time.time() + 60 * (k + 1)))(i)
    SVC.create("test")
SVC.now = time.time
ok(len(archives()) == B.KEEP, f"only the last {B.KEEP} archives are kept ({len(archives())})")
for a in archives():
    os.remove(os.path.join(SVC.dir, a["name"]))

# ---------------------------------------------------------------- partial restore
tasks = os.path.join(CFG, "myrhino", "maintenance", "tasks.json")
os.makedirs(os.path.dirname(tasks), exist_ok=True)
saved_tasks = b'{"version": 2, "areas": {}, "tasks": {}, "settings": {}}'
open(tasks, "wb").write(saved_tasks)
SVC.now = lambda: time.time() - 7200            # made two hours ago: the oldest
keep_name = SVC.create("for restore")["name"]
SVC.now = time.time
r = post("/api/restore/plan", {"archive": keep_name, "item": "maintenance"})
ok(r.status_code == 200 and "config/myrhino/maintenance/tasks.json" in r.get_json()["plan"]["same"], "a restore can be planned (shown before anything changes)")
open(tasks, "w").write('{"version": 2, "changed": true}')
p = post("/api/restore/plan", {"archive": keep_name, "item": "maintenance"}).get_json()["plan"]
ok("config/myrhino/maintenance/tasks.json" in p["replace"], "the plan shows the changed maintenance file")
M["print_state"] = "paused"
ok(post("/api/restore", {"archive": keep_name, "item": "maintenance"}).status_code == 400, "no restore during a job (paused)")
M["print_state"] = "standby"
r = post("/api/restore", {"archive": keep_name, "item": "maintenance"}); j = r.get_json()
ok(r.status_code == 200 and j["before"], f"maintenance restored, after a backup of how it was ({j.get('before')})")
ok(open(tasks, "rb").read() == saved_tasks, "the maintenance file is back as it was in the archive")
for a in archives():
    if a["name"] != keep_name: os.remove(os.path.join(SVC.dir, a["name"]))
for i in range(B.KEEP - 1):
    SVC.now = (lambda k: (lambda: time.time() - 3600 + 60 * k))(i)
    SVC.create("newer")
SVC.now = time.time
ok(archives()[-1]["name"] == keep_name, "the archive to restore is now the oldest of the ten")
j = post("/api/restore", {"archive": keep_name, "item": "images"}).get_json()
ok(j.get("ok") and any(a["name"] == keep_name for a in archives()) and any(a["name"] == j["before"] for a in archives()),
   "restoring from the oldest archive keeps it and the backup made first (neither is pruned)")
M["db"]["rhino_studio"]["theme"] = "light"
j = post("/api/restore", {"archive": keep_name, "item": "studio"}).get_json()
ok(M["db"]["rhino_studio"]["theme"] == "dark", "Studio settings restored into Moonraker's rhino_studio namespace")
j = post("/api/restore", {"archive": keep_name, "item": "tools"}).get_json()
ok(j.get("ok") and "Restart Klipper" in j["note"] and os.path.exists(SVC.paths.restart_flag), "restoring tools waits for a Klipper restart (banner)")

# ---------------------------------------------------------------- full restore
r = post("/api/restore", {"archive": keep_name, "item": "all", "confirm": "wrong"})
ok(r.status_code == 400 and "Type this machine's name" in r.get_json()["error"], "full restore needs this machine's name typed")
serials = [s for s in cfg_serials() if s.startswith("/dev/")]
if serials:
    r = post("/api/restore", {"archive": keep_name, "item": "all", "confirm": socket.gethostname()})
    ok(r.status_code == 400 and "isn't connected here" in r.get_json()["error"], "a board serial path that isn't here stops a full restore before anything changes")
REAL_EXISTS = os.path.exists
os.path.exists = lambda p: True if str(p).startswith("/dev/") else REAL_EXISTS(p)
try:
    open(os.path.join(CFG, "printer.cfg"), "a").write("\n# changed after the backup\n")
    extra = os.path.join(CFG, "my_extra.cfg"); open(extra, "w").write("# mine\n")
    open(os.path.join(CFG, "rhino", "backup.py"), "a").write("# newer program\n")
    M["db"]["rhino_studio"]["theme"] = "light"
    rs0 = M["restarts"]
    r = post("/api/restore", {"archive": keep_name, "item": "all", "confirm": socket.gethostname()}); j = r.get_json()
    ok(r.status_code == 200 and j["ok"], f"full restore works on the same machine ({j.get('note') or j.get('error')})")
    ok("changed after the backup" not in open(os.path.join(CFG, "printer.cfg")).read(), "printer.cfg is back as it was")
    ok(open(os.path.join(CFG, "rhino", "backup.py")).read().endswith("# newer program\n"), "Tool Manager's own program files are left as installed")
    ok(os.path.exists(extra) and "config/my_extra.cfg" in j["kept"], "files that weren't in the backup are kept and listed")
    ok(M["restarts"] == rs0 + 1 and M["restored"], "Klipper restarted and Moonraker restored its database")
    ok(M["db"]["rhino_studio"]["theme"] == "dark", "Moonraker's database is the archive's")
finally:
    os.path.exists = REAL_EXISTS

# ---------------------------------------------------------------- BACKUP_CFG launcher
import subprocess
env = dict(os.environ, RHINO_MOONRAKER=MR, RHINO_CONFIG_DIR=CFG, HOME=ROOT)
out = subprocess.run([sys.executable, os.path.join(CFG, "scripts", "rhino_backup_cfg.py"), "test_msg"], capture_output=True, text=True, env=env, timeout=60)
ok(out.returncode == 0 and "rhino: backup rhino-" in out.stdout and "pushed to GitHub" in out.stdout, f"BACKUP_CFG makes an archive, then pushes ({out.stdout.strip().splitlines()[-1:]})")
M["print_state"] = "printing"
out = subprocess.run([sys.executable, os.path.join(CFG, "scripts", "rhino_backup_cfg.py")], capture_output=True, text=True, env=env, timeout=60)
ok(out.returncode == 0 and "when it's finished" in out.stdout, "BACKUP_CFG during a job leaves the archive until the job is over")
M["print_state"] = "standby"
sc = open(os.path.join(REPO, "shell_command.cfg")).read()
ok("scripts/rhino_backup_cfg.py" in sc and "klipper-backup/script.sh" not in sc.split("[gcode_macro SHOW_BACKUP_LOCATION]")[0].split("[gcode_shell_command backup_cfg]")[1],
   "BACKUP_CFG runs the Rhino launcher (which runs klipper-backup itself)")

srv.shutdown()
shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
