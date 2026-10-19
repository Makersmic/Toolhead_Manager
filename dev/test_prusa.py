"""PrusaSlicer on the Rhino (1.5.0): install/update, slicing limits, cache, cancel, and /api/slicer.
Run: python3 dev/test_prusa.py   (needs flask). A small stand-in plays PrusaSlicer, so nothing is
downloaded and no real slicing happens; the real engine is checked on the machine (P1-P8)."""
import io, json, os, shutil, stat, sys, tempfile, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from rhino.prusa import PrusaService, clean_ini, pick_asset
from rhino.errors import Fail

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, contains=""):
    try: fn()
    except Fail as e: return contains.lower() in str(e).lower()
    return False
def wait(fn, t=10):
    end = time.time() + t
    while time.time() < end:
        if fn(): return True
        time.sleep(0.05)
    return False

TMP = tempfile.mkdtemp(prefix="rhino-prusa-")
KEYS = ["layer-height", "perimeters", "fill-density", "post-process", "gcode-substitutions", "binary-gcode", "thumbnails",
        "output-filename-format", "temperature"] + [f"opt-{i}" for i in range(60)]
FAKE = f'''#!{sys.executable}
import sys, os, time
a = sys.argv[1:]
if "--help-fff" in a:
    print("PrusaSlicer-2.9.6 fake\\nPrint options:")
    for k in {KEYS!r}: print("  --" + k + " ABC   something")
    sys.exit(0)
if "--appimage-extract" in a:
    os.makedirs("squashfs-root", exist_ok=True)
    me = open(__file__).read()
    p = os.path.join("squashfs-root", "AppRun"); open(p, "w").write(me); os.chmod(p, 0o755); sys.exit(0)
ini = open(a[a.index("--load") + 1]).read()
open(os.path.join(os.path.dirname(a[a.index("--load") + 1]), "argv.txt"), "w").write(" ".join(a))
print("Processing triangulated mesh", flush=True)
if "layer_height = 9" in ini: print("Error: layer height too big", flush=True); sys.exit(1)
if "perimeters = 999" in ini: x = bytearray(400 * 1024 * 1024); time.sleep(5)
if "perimeters = 77" in ini: time.sleep(10)
print("Generating perimeters", flush=True); print("Exporting G-code", flush=True)
open(a[a.index("--output") + 1], "w").write(";LAYER_CHANGE\\nG1 X1 Y1 E1\\n; estimated printing time (normal mode) = 12s\\n")
'''
def fake_file(path):
    open(path, "w").write(FAKE); os.chmod(path, 0o755); return path
APPIMAGE = fake_file(os.path.join(TMP, "PrusaSlicer-2.9.6+linux-x64-newer-distros-GTK3-202510.AppImage"))
RELEASE = {"tag_name": "version_2.9.6", "assets": [
    {"name": "PrusaSlicer-2.9.6+MacOS-universal.dmg", "browser_download_url": "x"},
    {"name": "PrusaSlicer-2.9.6+linux-x64-older-distros-GTK2-202510.AppImage", "browser_download_url": "old"},
    {"name": os.path.basename(APPIMAGE), "browser_download_url": "file://" + APPIMAGE}]}
calls = []
def fetch(url, dest=None, timeout=30):
    calls.append(url)
    if dest is None: return json.dumps(RELEASE).encode()
    shutil.copyfile(url[len("file://"):], dest); return dest

STATE = {"p": "standby"}
def svc(**kw):
    base = tempfile.mkdtemp(prefix="eng-", dir=TMP)
    return PrusaService(base, lambda: STATE["p"], fetch=fetch, **{"mem_mb": 16000, "cpus": 8, "arch": "x86_64", **kw})
STL = b"\0" * 80 + (1).to_bytes(4, "little") + b"\0" * 50

# ---------------------------------------------------------------- picking the right download
ok(pick_asset(RELEASE["assets"], "x86_64")["name"].startswith("PrusaSlicer-2.9.6+linux-x64-newer-distros-GTK3"), "x86-64: the newer-distros GTK3 AppImage")
ok(pick_asset(RELEASE["assets"], "armv7l") is None and pick_asset(RELEASE["assets"], "aarch64") is None, "no build for this processor: none picked")

# ---------------------------------------------------------------- install
s = svc()
st = s.state()
ok(st["engine"]["installed"] is None and st["engine"]["latest"] == "2.9.6" and st["engine"]["update_available"], "not installed: latest 2.9.6 offered")
ok(raises(lambda: s.submit(STL, "", "x", "100,100"), "isn't installed"), "slicing before install says to install from Settings > Software")
STATE["p"] = "printing"; ok(raises(lambda: s.install_latest(), "job is running"), "no install during a print"); STATE["p"] = "standby"
s.install_latest()
ok(wait(lambda: not s.installing), "install finishes")
ok(s.installed() == "2.9.6" and s.install_error is None and os.path.islink(os.path.join(s.base, "current")), "installed 2.9.6, `current` points at it")
ok(len(s.keys()) == len(KEYS) and "layer_height" in s.keys(), "option names read from the engine's own --help-fff")
ok(not s.state()["engine"]["update_available"], "up to date afterwards")
RELEASE["tag_name"] = "version_2.9.7"
ok(s.state()["engine"]["latest"] == "2.9.6", "release list cached (6 h), not asked every time")
s.latest(force=True); ok(s.state()["engine"]["update_available"], "a newer release is offered")
s.install_latest(); wait(lambda: not s.installing)
ok(s.installed() == "2.9.7" and open(os.path.join(s.base, "previous")).read() == "2.9.6" and os.path.isdir(os.path.join(s.base, "2.9.6")),
   "update switches to 2.9.7 and keeps 2.9.6 to go back to")
RELEASE["tag_name"] = "version_2.9.6"

# ---------------------------------------------------------------- the settings file
ini = clean_ini("layer_height = 0.2\npost_process = /bin/rm -rf ~\nnot_known = 1\nBad Key = 2\ntemperature = 215\nlayer_height = 0.3\n", set(k.replace("-", "_") for k in KEYS))
ok("layer_height = 0.2" in ini and "layer_height = 0.3" not in ini and "not_known" not in ini and "Bad Key" not in ini, "only known, well-formed options, first value wins")
ok("post_process = \n" in ini and "gcode_substitutions = \n" in ini and "binary_gcode = 0" in ini, "scripts and substitutions forced empty, plain G-code forced")

# ---------------------------------------------------------------- slicing
j = s.submit(STL, "layer_height = 0.2\nperimeters = 3\n", "part", "275,187.5")
ok(wait(lambda: s.job(j["id"])["state"] == "done"), "a slice finishes")
argv = open(os.path.join(s.base, "jobs", j["id"], "argv.txt")).read()
ok("--center 275.000,187.500" in argv and "--threads 7" in argv and "--export-gcode" in argv, "placed where Studio says, cores-1 threads when idle")
ok(open(s.gcode_path(j["id"])).read().startswith(";LAYER_CHANGE"), "G-code served")
ok(not os.path.exists(os.path.join(s.base, "jobs", j["id"], "part.stl")), "the uploaded part is deleted after slicing")
j2 = s.submit(STL, "layer_height = 0.2\nperimeters = 3\n", "part", "275,187.5")
ok(j2["state"] == "done" and j2["cached"], "the same part and settings again: straight from the cache")
STATE["p"] = "printing"
j3 = s.submit(STL, "layer_height = 0.2\nperimeters = 4\n", "part", "275,187.5")
wait(lambda: s.job(j3["id"])["state"] == "done")
ok("--threads 4" in open(os.path.join(s.base, "jobs", j3["id"], "argv.txt")).read(), "during a print: half the cores")
STATE["p"] = "standby"
j = s.submit(STL, "layer_height = 9\n", "part", "275,187.5")
ok(wait(lambda: s.job(j["id"])["state"] == "failed") and "layer height too big" in s.job(j["id"])["error"], "engine errors come back in its own words")
ok(raises(lambda: s.submit(STL, "", "x", "9999,1"), "outside"), "a position off the bed is refused")
ok(raises(lambda: s.submit(b"x", "", "x", "1,1"), "empty"), "an empty part is refused")

# cancel, and a newer request replacing an older one
j = s.submit(STL, "perimeters = 77\n", "part", "100,100")
wait(lambda: s.job(j["id"])["state"] == "running")
k = s.submit(STL, "perimeters = 5\n", "part", "100,100")
ok(wait(lambda: s.job(j["id"])["state"] == "cancelled") and wait(lambda: s.job(k["id"])["state"] == "done"), "a newer request from Studio stops the older slice")
j = s.submit(STL, "perimeters = 77\n", "part", "100,100"); wait(lambda: s.job(j["id"])["state"] == "running")
s.cancel(j["id"]); ok(wait(lambda: s.job(j["id"])["state"] == "cancelled"), "cancel stops a running slice")

# memory watchdog and small hosts
small = svc(mem_mb=1000, cpus=4)
small._install(*[RELEASE["tag_name"].replace("version_", ""), pick_asset(RELEASE["assets"], "x86_64") | {"url": "file://" + APPIMAGE}])
ok(small.installed() == "2.9.6", "(small host installed)")
ok(small.limits() == (3, 256), "small host idle: cores-1, memory cap leaves room for Klipper")
STATE["p"] = "printing"
ok(raises(lambda: small.submit(STL, "", "x", "1,1"), "under 2 GB") and small.state()["refuse"], "small host: no slicing during a print, and says why")
STATE["p"] = "standby"
j = small.submit(STL, "perimeters = 999\n", "part", "1,1")
ok(wait(lambda: small.job(j["id"])["state"] == "failed", 15) and "memory" in small.job(j["id"])["error"], "a slice using more than its memory cap is stopped, with a reason")
j = small.submit(STL, "perimeters = 77\n", "part", "1,1"); wait(lambda: small.job(j["id"])["state"] == "running")
STATE["p"] = "printing"
ok(wait(lambda: small.job(j["id"])["state"] == "failed", 15) and "job started" in small.job(j["id"])["error"], "small host: a print starting mid-slice stops the slice")
STATE["p"] = "standby"

# ---------------------------------------------------------------- routes
ROOT = tempfile.mkdtemp(prefix="rhino-prusa-portal-")
shutil.copytree(os.path.dirname(HERE), ROOT + "/cfg", ignore=shutil.ignore_patterns("__pycache__", "registry_backups", ".git", "manual"))
from rhino.portal import create_app, security
app = create_app(ROOT + "/cfg", "http://127.0.0.1:9")
app.config["PRUSA"] = s
c = app.test_client(); HDR = {security.HEADER: security.TOKEN}
r = c.get("/api/slicer").get_json()
ok(r["ok"] and r["engine"]["installed"] == "2.9.7" and r["host"]["cpus"] == 8, "GET /api/slicer")
ok(len(c.get("/api/slicer/keys").get_json()["keys"]) == len(KEYS), "GET /api/slicer/keys")
data = lambda: {"model": (io.BytesIO(STL), "part.stl"), "config": (io.BytesIO(b"layer_height = 0.25\n"), "rhino.ini"), "name": "part", "center": "50,60"}
ok(c.post("/api/slicer/slice", data=data(), content_type="multipart/form-data").status_code == 400, "slice without the token: refused")
r = c.post("/api/slicer/slice", data=data(), headers=HDR, content_type="multipart/form-data").get_json()
ok(r["ok"] and wait(lambda: c.get(f"/api/slicer/jobs/{r['id']}").get_json()["state"] == "done"), "POST /api/slicer/slice, then poll the job")
ok(c.get(f"/api/slicer/jobs/{r['id']}/gcode").data.startswith(b";LAYER_CHANGE"), "GET the G-code")
big = {"model": (io.BytesIO(b"\0" * (9 * 1024 * 1024)), "p.jpg")}
ok(c.post("/api/tools/X/photos", data=big, headers=HDR, content_type="multipart/form-data").status_code == 413, "other uploads keep their 8 MB limit")
ok(c.post("/api/slicer/engine/check", headers=HDR, json={}).get_json()["ok"], "POST engine/check")

shutil.rmtree(TMP, ignore_errors=True); shutil.rmtree(ROOT, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
