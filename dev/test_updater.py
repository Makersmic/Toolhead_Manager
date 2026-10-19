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
