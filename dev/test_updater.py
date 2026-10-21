"""Updater (1.5.3): the zip check, the Portal's update routes, install.sh's --unattended guard, and a
whole updater run (as root only) with a stub install.sh inside a test zip.

    python3 dev/test_updater.py
"""
import io, json, os, shutil, subprocess, sys, tempfile, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import importlib.util
spec = importlib.util.spec_from_file_location("helper", os.path.join(REPO, "scripts", "rhino_update_helper.py"))
H = importlib.util.module_from_spec(spec); spec.loader.exec_module(H)

FAILED = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: FAILED.append(msg)

TMP = tempfile.mkdtemp(prefix="rhino-upd-")

def make_zip(path, version="1.5.3", init_version=None, extra=None, drop=(), install="echo installing; exit 0"):
    files = {"VERSION": version + "\n", "install.sh": install + "\n", "rhino.sh": "echo menu\n", "uninstall.sh": "echo undo\n",
             "rhino/__init__.py": f'__version__ = "{init_version or version}"\n', "scripts/rhino_portal.py": "# portal\n"}
    for d in drop: files.pop(d, None)
    with zipfile.ZipFile(path, "w") as z:
        for n, t in files.items(): z.writestr(n, t)
        for n, t in (extra or {}).items():
            if isinstance(t, zipfile.ZipInfo): z.writestr(t, "x")
            else: z.writestr(n, t)
    return path

def err(path):
    try: H.check_zip(path); return None
    except ValueError as e: return str(e)

print("== the zip check ==")
good = make_zip(os.path.join(TMP, "good.zip"))
ok(H.check_zip(good) == "1.5.3", "a release zip: version read")
ok("outside its folder" in err(make_zip(os.path.join(TMP, "a.zip"), extra={"../evil.sh": "x"})), "../ in a name: refused")
ok("outside its folder" in err(make_zip(os.path.join(TMP, "b.zip"), extra={"/etc/x": "x"})), "absolute name: refused")
li = zipfile.ZipInfo("link"); li.external_attr = (0o120777 << 16)
ok("link" in err(make_zip(os.path.join(TMP, "c.zip"), extra={"link": li})), "a symlink inside: refused")
ok("missing install.sh" in err(make_zip(os.path.join(TMP, "d.zip"), drop=("install.sh",))), "missing install.sh: not a release")
ok("don't agree" in err(make_zip(os.path.join(TMP, "e.zip"), init_version="1.5.2")), "VERSION and code disagree: refused")
ok("version number" in err(make_zip(os.path.join(TMP, "f.zip"), version="latest")), "VERSION not a number: refused")
open(os.path.join(TMP, "g.zip"), "w").write("not a zip")
ok("isn't a zip" in err(os.path.join(TMP, "g.zip")), "not a zip at all: refused")
os.symlink(good, os.path.join(TMP, "h.zip"))
ok("plain file" in err(os.path.join(TMP, "h.zip")), "a link to a zip: refused")

print("== install.sh --unattended guard ==")
r = subprocess.run(["bash", os.path.join(REPO, "install.sh"), "--unattended"], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
ok(r.returncode == 1 and "only for the Rhino updater" in r.stdout, "without RHINO_USER (or not root): refused before anything")

print("== Portal routes ==")
from rhino.portal import create_app, security
from rhino.portal import update_routes
CFG = os.path.join(TMP, "printer_data", "config"); os.makedirs(CFG)
app = create_app(CFG, "http://127.0.0.1:9")  # no Moonraker: job state "unknown"
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
UNIT = os.path.join(TMP, "rhino-update.path")
update_routes.UNIT = UNIT
DROP = os.path.join(TMP, "printer_data", "rhino_data", "update")

s = c.get("/api/update").get_json()
ok(s["ok"] and s["helper"] is False and s["zips"] == [] and s["status"]["state"] == "idle", "GET: updater not set up, nothing kept")
r = c.post("/api/update/upload", data={"zip": (open(good, "rb"), "whatever.zip")}, content_type="multipart/form-data")
ok(r.status_code >= 400, "upload without the token: refused")
r = c.post("/api/update/upload", headers=HDR, data={"zip": (open(make_zip(os.path.join(TMP, "x.zip"), extra={"../x": "y"}), "rb"), "x.zip")}, content_type="multipart/form-data")
ok(r.status_code >= 400 and "outside" in r.get_json()["error"] and os.listdir(os.path.join(DROP, "incoming")) == [], "a bad zip: refused, nothing kept")
r = c.post("/api/update/upload", headers=HDR, data={"zip": (open(good, "rb"), "my download (1).zip")}, content_type="multipart/form-data")
j = r.get_json()
ok(j["ok"] and j["zip"] == "rhino-config-1.5.3.zip" and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.3.zip")), "a good zip: kept under its release name, whatever it was called")
r = c.post("/api/update/install", headers=HDR, json={"zip": "rhino-config-1.5.3.zip"})
ok(r.status_code >= 400 and "isn't set up" in r.get_json()["error"], "install before the updater is set up: says to install once by hand")
open(UNIT, "w").write("x")
r = c.post("/api/update/install", headers=HDR, json={"zip": "../../etc/passwd"})
ok(r.status_code >= 400 and not os.path.exists(os.path.join(DROP, "request.json")), "install of a made-up name: refused")
r = c.post("/api/update/install", headers=HDR, json={"zip": "rhino-config-1.5.3.zip"})
req = json.load(open(os.path.join(DROP, "request.json")))
ok(r.get_json()["ok"] and req["zip"] == "rhino-config-1.5.3.zip", "install: request dropped for the updater")
s = c.get("/api/update").get_json()
ok(s["busy"] and s["status"]["state"] == "running", "while it waits: busy, status running")
r = c.post("/api/update/install", headers=HDR, json={"zip": "rhino-config-1.5.3.zip"})
ok(r.status_code >= 400 and "already running" in r.get_json()["error"], "a second install: refused")
r = c.post("/api/update/upload", headers=HDR, data={"zip": (open(good, "rb"), "a.zip")}, content_type="multipart/form-data")
ok(r.status_code >= 400, "upload during an install: refused")
st = json.load(open(os.path.join(DROP, "status.json"))); st["updated"] = time.time() - 3600
json.dump(st, open(os.path.join(DROP, "status.json"), "w")); os.unlink(os.path.join(DROP, "request.json"))
ok(c.get("/api/update").get_json()["status"]["state"] == "failed", "a run that went silent shows as failed")

print("== from GitHub (1.5.8) ==")
import hashlib, http.server, threading
GH = {"zip": open(make_zip(os.path.join(TMP, "gh.zip"), version="1.5.9"), "rb").read(), "sha": None, "tag": "v1.5.9", "status": 200, "assets": True}
GH["sha"] = hashlib.sha256(GH["zip"]).hexdigest()
class GHH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ct="application/octet-stream"):
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/releases/latest":
            if GH["status"] != 200: return self._send(GH["status"], b"{}")
            assets = [{"name": "rhino-config-1.5.9.zip", "browser_download_url": base + "/dl/zip"},
                      {"name": "rhino-config-1.5.9.zip.sha256", "browser_download_url": base + "/dl/sha"}] if GH["assets"] else []
            return self._send(200, json.dumps({"tag_name": GH["tag"], "published_at": "2026-10-21T16:00:00Z", "html_url": base + "/rel", "assets": assets}).encode(), "application/json")
        if self.path == "/dl/zip": return self._send(200, GH["zip"])
        if self.path == "/dl/sha": return self._send(200, (GH["sha"] + "  rhino-config-1.5.9.zip\n").encode())
        self._send(404, b"")
ghs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GHH); threading.Thread(target=ghs.serve_forever, daemon=True).start()
update_routes.RELEASES = f"http://127.0.0.1:{ghs.server_port}/releases/latest"
def fresh_latest(): update_routes._latest.update(at=0, value=None)
os.unlink(os.path.join(DROP, "status.json"))
fresh_latest()
s = c.get("/api/update").get_json()
ok(s["latest"]["version"] == "1.5.9" and s["latest"]["sha256_url"].endswith("/dl/sha"), "GH1 GET /api/update names GitHub's newest release")
ok(c.post("/api/update/github", json={"version": "1.5.9"}).status_code >= 400, "GH2 without the token: refused")
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.8"})
ok(r.status_code >= 400 and "now 1.5.9" in r.get_json()["error"], "GH3 asking for a version that isn't the newest: refused")
GH["zip"] += b"tampered"
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"})
ok(r.status_code >= 400 and "doesn't match its .sha256" in r.get_json()["error"] and "rhino-config-1.5.9.zip" not in os.listdir(os.path.join(DROP, "incoming")),
   "GH4 a download that doesn't match the release's SHA256: not kept, not installed")
GH["zip"] = GH["zip"][: -len(b"tampered")]
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"})
req = json.load(open(os.path.join(DROP, "request.json")))
ok(r.get_json()["ok"] and req["zip"] == "rhino-config-1.5.9.zip" and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.9.zip")),
   "GH5 the newest release: downloaded, checked, handed to the updater like an upload")
ok(c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"}).status_code >= 400, "GH6 while that install runs: refused")
os.unlink(os.path.join(DROP, "request.json")); os.unlink(os.path.join(DROP, "status.json"))
GH["assets"] = False; fresh_latest()
ok("no rhino-config zip" in c.get("/api/update").get_json()["latest"]["error"], "GH7 a release without the zip: says so")
GH["status"] = 404; fresh_latest()
ok(c.get("/api/update").get_json()["latest"]["error"] == "No releases on GitHub yet.", "GH8 no releases yet: says so")
update_routes.RELEASES = "http://127.0.0.1:9/releases/latest"; fresh_latest()
ok("Can't reach GitHub" in c.get("/api/update").get_json()["latest"]["error"], "GH9 GitHub unreachable: says so, the page still works")
GH["status"] = 200; GH["assets"] = True
update_routes.RELEASES = f"http://127.0.0.1:{ghs.server_port}/releases/latest"; fresh_latest(); c.get("/api/update")
calls = []
orig = update_routes._get
update_routes._get = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
c.get("/api/update"); c.get("/api/update")
update_routes._get = orig
ok(calls == [], "GH10 asked GitHub at most once an hour")
ghs.shutdown()

print("== a whole updater run ==")
if os.geteuid() != 0:
    print("SKIP updater run (needs root)")
else:
    import pwd
    me = pwd.getpwuid(os.geteuid())
    home = tempfile.mkdtemp(prefix="home-", dir=me.pw_dir) if me.pw_dir != "/" else tempfile.mkdtemp()
    drop = os.path.join(home, "printer_data", "rhino_data", "update"); os.makedirs(os.path.join(drop, "incoming"))
    os.makedirs(os.path.join(home, "rhino-manager")); open(os.path.join(home, "rhino-manager", "installed-version"), "w").write("1.5.2\n")
    H.WORK = os.path.join(TMP, "work")
    stub = 'echo "unattended=$1 user=$RHINO_USER"; [ "$1" = "--unattended" ] || exit 3; exit 0'
    make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.3.zip"), install=stub)
    make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.2.zip"), version="1.5.2")
    make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.0.zip"), version="1.5.0")
    run = H.Run(me.pw_name, drop, "http://127.0.0.1:9")
    run.pw = run.pw._replace(pw_dir=home) if hasattr(run.pw, "_replace") else run.pw
    run.home = home
    json.dump({"zip": "rhino-config-1.5.3.zip"}, open(os.path.join(drop, "request.json"), "w"))
    run.go(run.read_request())
    st = json.load(open(os.path.join(drop, "status.json")))
    ok(st["state"] == "done" and st["version"] == "1.5.3" and st["from_version"] == "1.5.2", "run: done, 1.5.2 -> 1.5.3")
    ok(any("unattended=--unattended" in l for l in st["log"]), "install.sh ran with --unattended and RHINO_USER")
    ok(open(os.path.join(home, "rhino-manager", "installed-version")).read().strip() == "1.5.3", "installed version recorded")
    ok(sorted(os.listdir(os.path.join(drop, "incoming"))) == ["rhino-config-1.5.2.zip", "rhino-config-1.5.3.zip"], "kept: this zip and the one before (Go back); older ones removed")
    ok(not os.path.exists(os.path.join(drop, "request.json")), "request taken")
    # a failing install: status says so
    make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.4.zip"), version="1.5.4", install='echo "STOPPED: test"; exit 1')
    json.dump({"zip": "rhino-config-1.5.4.zip"}, open(os.path.join(drop, "request.json"), "w"))
    run = H.Run(me.pw_name, drop, "http://127.0.0.1:9"); run.home = home
    try: run.go(run.read_request())
    except SystemExit: pass
    st = json.load(open(os.path.join(drop, "status.json")))
    ok(st["state"] == "failed" and "install.sh stopped" in st["error"] and any("STOPPED: test" in l for l in st["log"]), "install fails: status failed, with its last lines")
    # a link planted as status.json is replaced, never written through
    target = os.path.join(TMP, "victim"); open(target, "w").write("keep")
    os.unlink(os.path.join(drop, "status.json")); os.symlink(target, os.path.join(drop, "status.json"))
    run.save(state="idle")
    ok(open(target).read() == "keep" and not os.path.islink(os.path.join(drop, "status.json")), "a planted link at status.json: replaced, its target untouched")
    shutil.rmtree(home, ignore_errors=True)

shutil.rmtree(TMP, ignore_errors=True)
print("\nALL PASSED" if not FAILED else f"\nFAILED: {FAILED}")
sys.exit(1 if FAILED else 0)
