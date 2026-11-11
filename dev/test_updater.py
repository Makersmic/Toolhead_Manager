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
import base64
# A test signing key (1.9.29): the helper and the Portal trust only it for this run (the real one is in the release workflow)
SEED = bytes(range(32))
PUB = base64.b64encode(H.ed25519_public(SEED)).decode()
H.PUBLIC_KEYS = (PUB,)
OTHER = bytes(range(32, 64))

def sign(path, seed=SEED):
    open(path + ".sig", "w").write(base64.b64encode(H.ed25519_sign(seed, path=path)).decode() + "  " + os.path.basename(path) + "\n")
    return path

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

print("== ed25519 (RFC 8032 test vectors) ==")
seed1 = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
ok(H.ed25519_public(seed1).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "test 1: public key")
sig1 = H.ed25519_sign(seed1, b"")
ok(sig1.hex() == "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b", "test 1: signature")
seed2 = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
ok(H.ed25519_sign(seed2, bytes.fromhex("72")).hex().startswith("92a009a9f0d4cab8720e820b5f642540"), "test 2: signature over one byte")
ok(H.ed25519_verify(H.ed25519_public(seed1), sig1, b"") and not H.ed25519_verify(H.ed25519_public(seed1), sig1, b"x")
   and not H.ed25519_verify(H.ed25519_public(seed2), sig1, b"") and not H.ed25519_verify(b"\0" * 32, sig1, b"") and not H.ed25519_verify(H.ed25519_public(seed1), sig1[:-1] + b"\xff", b""),
   "verify: right key and message only; a bad point, key or S is just false")

print("== the zip check ==")
good = make_zip(os.path.join(TMP, "good.zip"))
ok(H.check_zip(good) == "1.5.3", "a release zip: version read")
def sig_err(z, s=None):
    try: H.check_signature(z, s or z + ".sig"); return None
    except ValueError as e: return str(e)
sign(good)
ok(sig_err(good) is None, "SG1 a zip signed by the release key: accepted")
ok("missing" in sig_err(make_zip(os.path.join(TMP, "unsigned.zip"))), "SG2 no .sig: refused")
ok("isn't signed by the Rhino release key" in sig_err(sign(make_zip(os.path.join(TMP, "other.zip")), OTHER)), "SG3 signed by another key: refused")
sign(make_zip(os.path.join(TMP, "tamper.zip"))); open(os.path.join(TMP, "tamper.zip"), "ab").write(b"x")
ok("isn't signed by the Rhino release key" in sig_err(os.path.join(TMP, "tamper.zip")), "SG4 a zip changed after signing: refused")
open(os.path.join(TMP, "junk.zip.sig"), "w").write("not base64!!"); shutil.copy(good, os.path.join(TMP, "junk.zip"))
ok("isn't a signature" in sig_err(os.path.join(TMP, "junk.zip")), "SG5 a .sig that isn't one: refused")
try: H.check_signature(good, good + ".sig", keys=()); ok(False, "SG6 no keys built in: refused")
except ValueError as e: ok("no release key built in" in str(e), "SG6 no keys built in: refused, says to install by hand")
ok(all(not k.startswith("@") and len(base64.b64decode(k)) == 32 for k in H.__dict__["PUBLIC_KEYS"]) and len(open(os.path.join(REPO, "scripts", "rhino_update_helper.py")).read().split('PUBLIC_KEYS = (')[1].split(")")[0].strip().strip('",')) == 44,
   "SG7 the shipped helper carries one real 32-byte public key")
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
update_routes._helper = lambda: H          # the Portal checks with the test key too
CFG = os.path.join(TMP, "printer_data", "config"); os.makedirs(CFG)
app = create_app(CFG, "http://127.0.0.1:9")  # no Moonraker: job state "unknown"
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
UNIT = os.path.join(TMP, "rhino-update.path")
update_routes.UNIT = UNIT
DROP = os.path.join(TMP, "printer_data", "rhino_data", "update")

s = c.get("/api/update").get_json()
ok(s["ok"] and s["helper"] is False and s["zips"] == [] and s["status"]["state"] == "idle", "GET: updater not set up, nothing kept")
def up(z, s=None, hdr=HDR, name="whatever.zip"):
    data = {"zip": (open(z, "rb"), name)}
    if s is not False: data["sig"] = (open(s or z + ".sig", "rb"), name + ".sig")
    return c.post("/api/update/upload", headers=hdr, data=data, content_type="multipart/form-data")
r = up(good, hdr={})
ok(r.status_code >= 400, "upload without the token: refused")
bad = sign(make_zip(os.path.join(TMP, "x.zip"), extra={"../x": "y"}))
r = up(bad)
ok(r.status_code >= 400 and "outside" in r.get_json()["error"] and os.listdir(os.path.join(DROP, "incoming")) == [], "a bad zip: refused, nothing kept")
r = up(good, s=False)
ok(r.status_code >= 400 and ".sig" in r.get_json()["error"] and os.listdir(os.path.join(DROP, "incoming")) == [], "SG8 upload without the .sig: refused, nothing kept")
r = up(os.path.join(TMP, "other.zip"))
ok(r.status_code >= 400 and "release key" in r.get_json()["error"] and os.listdir(os.path.join(DROP, "incoming")) == [], "SG9 upload signed by another key: refused, nothing kept")
r = up(good, name="my download (1).zip")
j = r.get_json()
ok(j["ok"] and j["zip"] == "rhino-config-1.5.3.zip" and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.3.zip"))
   and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.3.zip.sig")), "a good zip: kept with its .sig under its release name, whatever it was called")
ok(c.get("/api/update").get_json()["zips"][0]["signed"] is True, "GET lists the kept zip as signed")
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
r = up(good, name="a.zip")
ok(r.status_code >= 400, "upload during an install: refused")
st = json.load(open(os.path.join(DROP, "status.json"))); st["updated"] = time.time() - 3600
json.dump(st, open(os.path.join(DROP, "status.json"), "w")); os.unlink(os.path.join(DROP, "request.json"))
ok(c.get("/api/update").get_json()["status"]["state"] == "failed", "a run that went silent shows as failed")

print("== from GitHub (1.5.8) ==")
import hashlib, http.server, threading
GH = {"zip": open(sign(make_zip(os.path.join(TMP, "gh.zip"), version="1.5.9")), "rb").read(), "sha": None, "tag": "v1.5.9", "status": 200, "assets": True, "sig": True}
GH["sha"] = hashlib.sha256(GH["zip"]).hexdigest()
GH["sigtext"] = open(os.path.join(TMP, "gh.zip.sig")).read()
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
            if GH["assets"] and GH["sig"]: assets.append({"name": "rhino-config-1.5.9.zip.sig", "browser_download_url": base + "/dl/sig"})
            return self._send(200, json.dumps({"tag_name": GH["tag"], "published_at": "2026-10-21T16:00:00Z", "html_url": base + "/rel", "assets": assets}).encode(), "application/json")
        if self.path == "/dl/zip": return self._send(200, GH["zip"])
        if self.path == "/dl/sha": return self._send(200, (GH["sha"] + "  rhino-config-1.5.9.zip\n").encode())
        if self.path == "/dl/sig": return self._send(200, GH["sigtext"].encode())
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
GH["sig"] = False; fresh_latest()
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"})
ok(r.status_code >= 400 and "no .sig" in r.get_json()["error"], "GH4b a release without a .sig: refused before any download")
GH["sig"] = True; fresh_latest()
keep_sig = GH["sigtext"]; GH["sigtext"] = open(os.path.join(TMP, "other.zip.sig")).read()
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"})
ok(r.status_code >= 400 and "release key" in r.get_json()["error"] and "rhino-config-1.5.9.zip" not in os.listdir(os.path.join(DROP, "incoming")),
   "GH4c a release whose .sig is another key's: not kept, not installed")
GH["sigtext"] = keep_sig
r = c.post("/api/update/github", headers=HDR, json={"version": "1.5.9"})
req = json.load(open(os.path.join(DROP, "request.json")))
ok(r.get_json()["ok"] and req["zip"] == "rhino-config-1.5.9.zip" and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.9.zip"))
   and os.path.isfile(os.path.join(DROP, "incoming", "rhino-config-1.5.9.zip.sig")),
   "GH5 the newest release: downloaded with its .sig, checked, handed to the updater like an upload")
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
# Studio's Check now: ?refresh=1 asks again (a release published since shows), but at most once a minute
GH["tag"] = "v1.6.0"
calls = []
update_routes._get = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
update_routes._latest["at"] -= update_routes.FORCE_GAP_S          # the last answer is a minute old
c.get("/api/update?refresh=1")
c.get("/api/update?refresh=1"); c.get("/api/update?refresh=1")  # clicked again straight away
update_routes._get = orig
ok(calls == [1], f"GH11 Check now asks GitHub again, once a minute at most ({len(calls)} asks)")
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
    sign(make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.3.zip"), install=stub))
    sign(make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.2.zip"), version="1.5.2"))
    sign(make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.0.zip"), version="1.5.0"))
    run = H.Run(me.pw_name, drop, "http://127.0.0.1:9")
    run.pw = run.pw._replace(pw_dir=home) if hasattr(run.pw, "_replace") else run.pw
    run.home = home
    json.dump({"zip": "rhino-config-1.5.3.zip"}, open(os.path.join(drop, "request.json"), "w"))
    run.go(run.read_request())
    st = json.load(open(os.path.join(drop, "status.json")))
    ok(st["state"] == "done" and st["version"] == "1.5.3" and st["from_version"] == "1.5.2", "run: done, 1.5.2 -> 1.5.3")
    ok(any("unattended=--unattended" in l for l in st["log"]), "install.sh ran with --unattended and RHINO_USER")
    ok(open(os.path.join(home, "rhino-manager", "installed-version")).read().strip() == "1.5.3", "installed version recorded")
    ok(sorted(os.listdir(os.path.join(drop, "incoming"))) == ["rhino-config-1.5.2.zip", "rhino-config-1.5.2.zip.sig", "rhino-config-1.5.3.zip", "rhino-config-1.5.3.zip.sig"], "kept: this zip and the one before (Go back) with their .sig; older ones removed")
    # an unsigned zip in incoming/: the run stops before unpacking
    make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.5.zip"), version="1.5.5")
    json.dump({"zip": "rhino-config-1.5.5.zip"}, open(os.path.join(drop, "request.json"), "w"))
    run = H.Run(me.pw_name, drop, "http://127.0.0.1:9"); run.home = home
    try: run.go(run.read_request())
    except SystemExit: pass
    st = json.load(open(os.path.join(drop, "status.json")))
    ok(st["state"] == "failed" and "no .sig" in st["error"] and st["step"] == 0, "SG10 an unsigned zip: the run stops at the check, nothing unpacked")
    ok(not os.path.exists(os.path.join(drop, "request.json")), "request taken")
    # a failing install: status says so
    sign(make_zip(os.path.join(drop, "incoming", "rhino-config-1.5.4.zip"), version="1.5.4", install='echo "STOPPED: test"; exit 1'))
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
