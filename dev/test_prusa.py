"""PrusaSlicer on the Rhino (1.5.2): install/update/go back through Flathub, slicing limits, cache, cancel, /api/slicer.
Run: python3 dev/test_prusa.py   (needs flask). A stand-in `flatpak` plays Flathub and PrusaSlicer, so nothing is
downloaded and no real slicing happens; the real engine is checked on the machine (P1-P9).

The stand-in behaves like the real thing where it matters: `flatpak run` starts the slicer as a grandchild in a
session of its own (as bubblewrap can), and the slicer can only write inside the --filesystem folders it was given."""
import io, json, os, shutil, sys, tempfile, time
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from rhino.prusa import PrusaService, clean_ini, parse_info, test_cube_stl, SANDBOX, SMALL_MSG, NO_FLATPAK, _tree
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
STATE_FILE = os.path.join(TMP, "flatpak-state.json")
KEYS = ["layer-height", "perimeters", "fill-density", "post-process", "gcode-substitutions", "binary-gcode", "thumbnails",
        "output-filename-format", "temperature"] + [f"opt-{i}" for i in range(60)]
V1, V2, V3 = ({"version": v, "commit": c * 64} for v, c in (("2.9.4", "a"), ("2.9.6", "b"), ("2.9.7", "c")))
SLICER = os.path.join(TMP, "fake-prusa-slicer")
open(SLICER, "w").write(f'''#!{sys.executable}
import sys, os, json, time
allowed, a = json.loads(sys.argv[1]), sys.argv[2:]
if "--help-fff" in a:
    print("PrusaSlicer-2.9.6 fake\\nPrint options:")
    for k in {KEYS!r}: print("  --" + k + " ABC   something")
    sys.exit(0)
out = a[a.index("--output") + 1]
if not any(os.path.realpath(out).startswith(os.path.realpath(d) + os.sep) for d in allowed):
    print("Error: Permission denied: " + out, flush=True); sys.exit(1)
ini = open(a[a.index("--load") + 1]).read() if "--load" in a else ""
open(os.path.join(os.path.dirname(out), "argv.txt"), "w").write(" ".join(sys.argv))
print("Processing triangulated mesh", flush=True)
if "layer_height = 9" in ini: print("Error: layer height too big", flush=True); sys.exit(1)
if "perimeters = 999" in ini: x = bytearray(400 * 1024 * 1024); x[::4096] = b"x" * len(x[::4096]); time.sleep(5)
if "perimeters = 77" in ini:
    open(os.path.join(os.path.dirname(out), "pid"), "w").write(str(os.getpid())); time.sleep(10)
print("Generating perimeters", flush=True); print("Exporting G-code", flush=True)
open(out, "w").write(";LAYER_CHANGE\\nG1 X1 Y1 E1\\n; estimated printing time (normal mode) = 12s\\n")
''')
FLATPAK = os.path.join(TMP, "flatpak")
open(FLATPAK, "w").write(f'''#!{sys.executable}
import sys, os, json, subprocess
ST = {STATE_FILE!r}
a = sys.argv[1:]
st = json.load(open(ST))
with open(ST + ".log", "a") as f: f.write(" ".join(a) + "\\n")
def save(): json.dump(st, open(ST, "w"))
def show(v): print("\\nPrusaSlicer - fake\\n\\n          ID: com.prusa3d.PrusaSlicer\\n     Version: " + v["version"] + "\\n      Commit: " + v["commit"] + "\\n")
APP = "com.prusa3d.PrusaSlicer"
if a[0] == "run":
    i = a.index(APP); flags, rest = a[1:i], a[i + 1:]
    if not st["installed"]: print("error: app/" + APP + " not installed"); sys.exit(1)
    if st["installed"]["commit"] in st["broken"]: print("prusa-slicer: error while loading shared libraries"); sys.exit(127)
    fs = [f.split("=", 1)[1] for f in flags if f.startswith("--filesystem=")]
    child = subprocess.Popen([sys.executable, {SLICER!r}, json.dumps(fs)] + rest, start_new_session=True)
    sys.exit(child.wait())
a = [x for x in a if x != "--user"]
cmd = a[0]
if cmd == "remotes": print("flathub" if st["remote"] else ""); sys.exit(0)
if cmd == "remote-add": st["remote"] = True; save(); sys.exit(0)
if cmd == "remote-info":
    if not st["remote"]: print("error: Remote \\"flathub\\" not found"); sys.exit(1)
    if not st["arch_ok"]: print("error: Nothing matches " + APP + " in remote flathub"); sys.exit(1)
    show(st["latest"]); sys.exit(0)
if cmd == "info":
    if not st["installed"]: print("error: " + APP + "/*unspecified*/*unspecified* not installed"); sys.exit(1)
    show(st["installed"]); sys.exit(0)
if cmd == "install":
    if not st["arch_ok"]: print("error: Nothing matches " + APP + " in remote flathub"); sys.exit(1)
    st["installed"] = st["latest"]; save(); print("Installation complete."); sys.exit(0)
if cmd == "update":
    c = next((x.split("=", 1)[1] for x in a if x.startswith("--commit=")), None)
    if c:
        if c not in st["history"]: print("error: Can't find commit " + c + " in remote"); sys.exit(1)
        st["installed"] = {{"version": st["history"][c], "commit": c}}
    else:
        st["installed"] = st["latest"]
    save(); print("Updates complete."); sys.exit(0)
print("error: unknown command " + cmd); sys.exit(1)
''')
os.chmod(SLICER, 0o755); os.chmod(FLATPAK, 0o755)

def fp_state(**kw):
    st = {"remote": False, "installed": None, "latest": V2, "arch_ok": True, "broken": [],
          "history": {v["commit"]: v["version"] for v in (V1, V2, V3)}}
    st.update(kw); json.dump(st, open(STATE_FILE, "w")); return st
def fp_get(): return json.load(open(STATE_FILE))
def fp_log():
    try: return open(STATE_FILE + ".log").read()
    except OSError: return ""

STATE = {"p": "standby"}
def svc(**kw):
    base = tempfile.mkdtemp(prefix="eng-", dir=TMP)
    return PrusaService(base, lambda: STATE["p"], **{"flatpak": FLATPAK, "mem_mb": 16000, "cpus": 8, "arch": "x86_64", **kw})
STL = b"\0" * 80 + (1).to_bytes(4, "little") + b"\0" * 50
def fresh(s): s._info["at"] = 0; return s

# ---------------------------------------------------------------- reading flatpak's answers
inf = parse_info("PrusaSlicer\n\n          ID: com.prusa3d.PrusaSlicer\n     Version: 2.9.6\n      Commit: " + "f" * 64 + "\n Parent: -\n")
ok(inf == {"version": "2.9.6", "commit": "f" * 64}, "version and commit read from flatpak info")
ok(len(test_cube_stl()) == 84 + 12 * 50, "test cube is a 12-facet binary STL")

# ---------------------------------------------------------------- who can install
fp_state()
ok(raises(lambda: svc(flatpak="").install_latest(), "sudo apt install flatpak"), "no flatpak: says the one command to run, never runs sudo")
ok(svc(flatpak="").state()["engine"]["blocked"] == NO_FLATPAK and not svc(flatpak="").state()["engine"]["can_install"], "no flatpak: shown in the state, no Install offered")
pi3 = svc(mem_mb=906, cpus=4, arch="aarch64")
two_gb = svc(mem_mb=1850, cpus=4, arch="aarch64")
ok(not two_gb.state()["engine"].get("blocked"), "2 GB board (reports ~1850 MB): engine offered (1.5.3)")
ok(svc(mem_mb=1799, cpus=4, arch="aarch64").state()["engine"].get("blocked") == SMALL_MSG, "just under 1800 MB: still not offered")
ok(raises(lambda: pi3.install_latest(), "2 GB of memory") and pi3.state()["engine"]["blocked"] == SMALL_MSG, "Pi 3B (under 2 GB): not offered, Kiri:Moto named instead")
ok(not pi3.state()["engine"]["update_available"], "Pi 3B: no Install/Update badge")
ok(raises(lambda: svc(arch="armv7l").install_latest(), "no official PrusaSlicer build"), "32-bit ARM: no official build")
ok("sudo" not in fp_log(), "nothing ran sudo")

# ---------------------------------------------------------------- install
s = svc()
st = s.state()
ok(st["engine"]["installed"] is None and st["engine"]["latest"] is None and st["engine"]["can_install"] and st["engine"]["update_available"],
   "not installed, Flathub not added yet: Install offered without asking Flathub")
ok("remote-add" not in fp_log(), "looking at the state never adds Flathub")
ok(raises(lambda: s.submit(STL, "", "x", "100,100"), "isn't installed"), "slicing before install says to install from Settings > Software")
STATE["p"] = "printing"; ok(raises(lambda: s.install_latest(), "job is running"), "no install during a print"); STATE["p"] = "standby"
s.install_latest()
ok(wait(lambda: not s.installing), "install finishes")
ok(s.install_error is None and s.installed() == "2.9.6", "installed 2.9.6 from Flathub" + (f" ({s.install_error})" if s.install_error else ""))
log = fp_log()
ok("remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo" in log and "install -y --noninteractive flathub com.prusa3d.PrusaSlicer" in log,
   "per-user Flathub remote added, then installed without questions")
ok(all("--user" in l for l in log.splitlines() if not l.startswith("run")) and all(" --user " in f" {l} " for l in log.splitlines() if l.startswith("run")),
   "every flatpak call is --user")
ok("--help-fff" in log and log.count("--export-gcode") >= 1, "after installing: --help-fff and a test slice in the sandbox")
ok(len(s.keys()) == len(KEYS) and "layer_height" in s.keys(), "option names read from the engine's own --help-fff")
ok(not s.state()["engine"]["update_available"] and s.state()["engine"]["latest"] == "2.9.6", "up to date afterwards")

# a newer build on Flathub
fp_state(**{**fp_get(), "latest": V3})
ok(s.state()["engine"]["latest"] == "2.9.6", "Flathub asked at most every 6 h")
s.latest(force=True); ok(s.state()["engine"]["update_available"] and s.state()["engine"]["latest"] == "2.9.7", "a newer build is offered")
s.install_latest(); wait(lambda: not s.installing)
ok(fresh(s).installed() == "2.9.7" and s.install_error is None and s.state()["engine"]["previous"] == "2.9.6", "update to 2.9.7; 2.9.6 offered to go back to")
ok(len(s.keys()) == len(KEYS), "option names read again for the new engine")
s.roll_back(); wait(lambda: not s.installing)
ok(fresh(s).installed() == "2.9.6" and s.install_error is None and s.state()["engine"]["previous"] == "2.9.7", "go back: 2.9.6 again (and 2.9.7 to go forward)")
s.roll_back(); wait(lambda: not s.installing); fresh(s)

# a bad update goes back by itself
fp_state(**{**fp_get(), "latest": {"version": "2.9.8", "commit": "d" * 64}, "broken": ["d" * 64],
            "history": {**fp_get()["history"], "d" * 64: "2.9.8"}})
s.latest(force=True); s.install_latest(); wait(lambda: not s.installing)
ok(fresh(s).installed() == "2.9.7" and "failed its test slice" in (s.install_error or "") and "2.9.7 was put back" in s.install_error,
   "an update that can't slice is undone, and says so")
fp_state(**{**fp_get(), "latest": V3, "broken": []})
s.install_error = None; s.latest(force=True)

# Flathub without a build for this processor
q = svc(arch="aarch64"); fp_state(**{**fp_get(), "arch_ok": False})
ok(raises(lambda: q.install_latest(), "no PrusaSlicer build for this processor (aarch64)"), "Flathub without an aarch64 build: clear message")
fp_state(**{**fp_get(), "arch_ok": True})

# ---------------------------------------------------------------- the settings file
ini = clean_ini("layer_height = 0.2\npost_process = /bin/rm -rf ~\nnot_known = 1\nBad Key = 2\ntemperature = 215\nlayer_height = 0.3\n", set(k.replace("-", "_") for k in KEYS))
ok("layer_height = 0.2" in ini and "layer_height = 0.3" not in ini and "not_known" not in ini and "Bad Key" not in ini, "only known, well-formed options, first value wins")
ok("post_process = \n" in ini and "gcode_substitutions = \n" in ini and "binary_gcode = 0" in ini, "scripts and substitutions forced empty, plain G-code forced")

# ---------------------------------------------------------------- slicing
j = s.submit(STL, "layer_height = 0.2\nperimeters = 3\n", "part", "275,187.5")
ok(wait(lambda: s.job(j["id"])["state"] == "done"), "a slice finishes" + (f" ({s.job(j['id'])['error']})" if s.job(j["id"])["error"] else ""))
jdir = os.path.join(s.base, "jobs", j["id"])
argv = open(os.path.join(jdir, "argv.txt")).read()
ok("--center 275.000,187.500" in argv and "--threads 7" in argv and "--export-gcode" in argv, "placed where Studio says, cores-1 threads when idle")
run = [l for l in fp_log().splitlines() if l.startswith("run") and j["id"] in l][-1]
ok(all(f in run for f in SANDBOX) and f"--filesystem={jdir}" in run and "--command=prusa-slicer" in run,
   "sandboxed: no network, display or home; only its own job folder")
ok(open(s.gcode_path(j["id"])).read().startswith(";LAYER_CHANGE"), "G-code served")
ok(not os.path.exists(os.path.join(jdir, "part.stl")), "the uploaded part is deleted after slicing")
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

# cancel reaches the slicer even in its own session, and a newer request replaces an older one
def slicer_pid(jid):
    p = os.path.join(s.base, "jobs", jid, "pid")
    return int(open(p).read()) if os.path.exists(p) else None
def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f: return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError: return False
j = s.submit(STL, "perimeters = 77\n", "part", "100,100")
ok(wait(lambda: slicer_pid(j["id"])), "(slow slice running)")
pid = slicer_pid(j["id"])
ok(os.getsid(pid) != os.getsid(s.jobs[j["id"]].proc.pid), "(the stand-in slicer runs in a session of its own)")
k = s.submit(STL, "perimeters = 5\n", "part", "100,100")
ok(wait(lambda: s.job(j["id"])["state"] == "cancelled") and wait(lambda: s.job(k["id"])["state"] == "done"), "a newer request from Studio stops the older slice")
ok(wait(lambda: not alive(pid), 3), "and the slicer itself is gone, not just `flatpak run`")
j = s.submit(STL, "perimeters = 77\n", "part", "100,100"); wait(lambda: slicer_pid(j["id"])); pid = slicer_pid(j["id"])
s.cancel(j["id"]); ok(wait(lambda: s.job(j["id"])["state"] == "cancelled") and wait(lambda: not alive(pid), 3), "cancel stops a running slice, sandbox and all")

# memory watchdog and small hosts (an engine put there by hand still slices, within its limits)
small = svc(mem_mb=1000, cpus=4, arch="aarch64")
ok(small.installed() == "2.9.7" and small.state()["engine"]["blocked"] == SMALL_MSG, "(small host sees the engine but isn't offered updates)")
ok(small.limits() == (3, 256), "small host idle: cores-1, memory cap leaves room for Klipper")
STATE["p"] = "printing"
ok(raises(lambda: small.submit(STL, "", "x", "1,1"), "under 4 GB") and small.state()["refuse"], "small host: no slicing during a print, and says why")
two_gb = svc(mem_mb=1850, cpus=4, arch="aarch64")
ok(raises(lambda: two_gb.submit(STL, "", "x", "1,1"), "under 4 GB"), "2 GB board (1.5.3): offered the engine, but still waits for a running job")
big = svc(mem_mb=3800, cpus=4, arch="aarch64")
ok(not big.refuse(), "4 GB board: may slice alongside a job (niced, watched)")
STATE["p"] = "standby"
j = small.submit(STL, "perimeters = 999\n", "part", "1,1")
ok(wait(lambda: small.job(j["id"])["state"] == "failed", 15) and "memory" in (small.job(j["id"])["error"] or ""),
   "memory counted over the whole tree: a slice over its cap is stopped, with a reason")
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
ok(r["ok"] and r["engine"]["installed"] == "2.9.7" and r["engine"]["source"] == "Flathub" and r["host"]["cpus"] == 8, "GET /api/slicer")
ok(len(c.get("/api/slicer/keys").get_json()["keys"]) == len(KEYS), "GET /api/slicer/keys")
data = lambda: {"model": (io.BytesIO(STL), "part.stl"), "config": (io.BytesIO(b"layer_height = 0.25\n"), "rhino.ini"), "name": "part", "center": "50,60"}
ok(c.post("/api/slicer/slice", data=data(), content_type="multipart/form-data").status_code == 400, "slice without the token: refused")
r = c.post("/api/slicer/slice", data=data(), headers=HDR, content_type="multipart/form-data").get_json()
ok(r["ok"] and wait(lambda: c.get(f"/api/slicer/jobs/{r['id']}").get_json()["state"] == "done"), "POST /api/slicer/slice, then poll the job")
ok(c.get(f"/api/slicer/jobs/{r['id']}/gcode").data.startswith(b";LAYER_CHANGE"), "GET the G-code")
big = {"model": (io.BytesIO(b"\0" * (9 * 1024 * 1024)), "p.jpg")}
ok(c.post("/api/tools/X/photos", data=big, headers=HDR, content_type="multipart/form-data").status_code == 413, "other uploads keep their 8 MB limit")
ok(c.post("/api/slicer/engine/check", headers=HDR, json={}).get_json()["ok"], "POST engine/check")
ok(c.post("/api/slicer/engine/rollback", json={}).status_code == 400, "go back without the token: refused")
r = c.post("/api/slicer/engine/rollback", headers=HDR, json={}).get_json()
ok(r["ok"] and wait(lambda: not s.installing) and fresh(s).installed() == "2.9.6", "POST engine/rollback")

shutil.rmtree(TMP, ignore_errors=True); shutil.rmtree(ROOT, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
