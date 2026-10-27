"""Slice profiles and saved Prepare jobs (1.8, Phase 1). Run: python3 dev/test_slice_profiles.py  (needs flask)

Design: docs/phase1-slice-profiles.md. Covers validation, the stale-revision refusal, history and revert,
delete and undelete, export/import round trip, the unreadable-file rule, saved jobs and the backup zip."""
import io, json, os, shutil, sys, tempfile, zipfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-profiles-test-")
CFG = ROOT + "/printer_data/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT
from rhino.portal import create_app, security
from rhino import slice_profiles as SP
from rhino.errors import Fail

app = create_app(CFG, "http://127.0.0.1:9")
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
FILE = CFG + "/myrhino/slice_profiles.json"
HIST = CFG + "/myrhino/slice_profiles.history.json"
JOBS = ROOT + "/printer_data/rhino_data/prepare_jobs.json"
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


def post(url, body=None):
    return c.post(url, json=body if body is not None else {}, headers=HDR)


PLA = {"name": "PLA 0.2 everyday", "engine": "kiri", "process": "fdm", "toolhead": "BlockOne", "material": "PLA",
       "settings": {"nozzle": 0.4, "layerHeight": 0.2, "walls": 3, "infill": 0.2, "infillType": "gyroid", "speed": 60,
                    "supports": False}, "notes": "the one that works"}

# ---- listing with no file
r = c.get("/api/slice-profiles").get_json()
ok(r["ok"] and r["profiles"] == [], "no file yet means no profiles, not an error")

# ---- create
r = post("/api/slice-profiles", PLA)
p = r.get_json().get("profile") or {}
ok(r.status_code == 200 and p.get("rev") == 1 and p["id"].startswith("p_"), "a new profile gets an id and revision 1")
ok(p.get("header") == {"nozzle": 0.4, "layerHeight": 0.2, "walls": 3, "infill": 0.2, "speed": 60}, "the Portal writes the header from the settings")
ok(os.path.isfile(FILE) and json.load(open(FILE))["schema"] == 1, "the profile is in myrhino/slice_profiles.json (inside the config folder)")
ok(c.post("/api/slice-profiles", json=PLA).status_code == 400, "a write without the page token is refused")
dup = post("/api/slice-profiles", PLA).get_json()["profile"]
ok(dup["name"] == "PLA 0.2 everyday (2)", "a second profile with the same name gets (2)")

full = c.get("/api/slice-profiles?full=1").get_json()["profiles"]
ok("settings" in full[0] and "settings" not in c.get("/api/slice-profiles").get_json()["profiles"][0], "?full=1 includes settings (Prepare), the plain list doesn't")
ok(post("/api/slice-profiles", {"name": "Vinyl", "engine": "kiri", "process": "dragknife", "settings": {"depth": 0.3}}).status_code == 200,
   "process names are Studio's own (dragknife)")

# ---- validation
bad = [
    (dict(PLA, settings={"nozzle": 0.4, "flux": 1}), "unknown setting flux"),
    (dict(PLA, settings={"infill": 3}), "between 0 and 1"),
    (dict(PLA, settings={"walls": "3"}), "must be a number"),
    (dict(PLA, settings={"supports": 1}), "true or false"),
    (dict(PLA, settings={"infillType": "honeycomb"}), "must be one of"),
    (dict(PLA, engine="cura"), "kiri or prusa"),
    (dict(PLA, name=""), "give it a name"),
    (dict(PLA, toolhead="Block One!"), "toolhead must be"),
    (dict(PLA, engine="prusa", settings={"Layer Height": "0.2"}), "isn't a PrusaSlicer option"),
    (dict(PLA, engine="prusa", settings={"start_gcode": "G28\nM104"}), "one line"),
    (dict(PLA, engine="prusa", process="laser", settings={}), "3D printing only"),
    ({"name": "Cut", "engine": "kiri", "process": "cnc", "settings": {"ops": [{"kind": "drill"}]}}, "operation 1"),
    ({"name": "Burn", "engine": "kiri", "process": "laser", "settings": {"power": 1.5}}, "between 0 and 1"),
]
for body, want in bad:
    r = post("/api/slice-profiles", body)
    err = (r.get_json() or {}).get("error", "")
    ok(r.status_code == 400 and want in err, f"refused: {want} ({err})")
r = post("/api/slice-profiles", {"name": "Prusa PLA", "engine": "prusa", "process": "fdm",
                                 "settings": {"layer_height": "0.2", "perimeters": "3", "start_gcode": "G28 ; home"}})
pp = r.get_json().get("profile", {})
ok(r.status_code == 200 and pp["header"] == {"layerHeight": "0.2", "walls": "3"}, "a PrusaSlicer profile keeps its own INI options")
cnc = post("/api/slice-profiles", {"name": "Plywood 6mm", "engine": "kiri", "process": "cnc",
                                   "settings": {"toolDiameter": 3.175, "ops": [{"kind": "outline", "on": True, "side": "outside"}]}})
ok(cnc.status_code == 200, "a CNC profile with operations saves")

# ---- save with revisions
pid = p["id"]
r = post(f"/api/slice-profiles/{pid}", {"profile": dict(PLA, settings=dict(PLA["settings"], walls=4)), "rev": 1})
ok(r.status_code == 200 and r.get_json()["profile"]["rev"] == 2, "saving bumps the revision")
r = post(f"/api/slice-profiles/{pid}", {"profile": dict(PLA, settings=dict(PLA["settings"], walls=5)), "rev": 1})
ok(r.status_code == 400 and "another device" in r.get_json()["error"], "a save from a stale revision is refused (changed on another device)")
ok(post(f"/api/slice-profiles/{pid}", {"profile": PLA}).status_code == 400, "a save without a revision is refused")
for w in (6, 7, 8, 9, 10, 11):
    cur = c.get(f"/api/slice-profiles/{pid}").get_json()["profile"]
    post(f"/api/slice-profiles/{pid}", {"profile": dict(PLA, settings=dict(PLA["settings"], walls=w)), "rev": cur["rev"]})
h = c.get(f"/api/slice-profiles/{pid}/history").get_json()["revisions"]
ok(len(h) == SP.KEEP_REVISIONS and h[0]["settings"]["walls"] == 10, f"history keeps the last {SP.KEEP_REVISIONS} revisions, newest first")
old = h[-1]["rev"]
r = post(f"/api/slice-profiles/{pid}/revert", {"to": old})
rv = r.get_json().get("profile", {})
ok(r.status_code == 200 and rv["settings"]["walls"] == h[-1]["settings"]["walls"] and rv["rev"] == 9, "revert saves the old settings as a new revision")
ok(post(f"/api/slice-profiles/{pid}/revert", {"to": 1}).status_code == 400, "a revision that's no longer kept can't be reverted to")

# ---- delete and undelete
r = c.delete(f"/api/slice-profiles/{dup['id']}", headers=HDR)
ok(r.status_code == 200 and all(x["id"] != dup["id"] for x in c.get("/api/slice-profiles").get_json()["profiles"]), "delete takes it off the list")
lst = c.get("/api/slice-profiles").get_json()
ok(any(x["id"] == dup["id"] for x in lst["deleted"]), "a deleted profile is kept in history for 30 days")
r = post(f"/api/slice-profiles/{dup['id']}/undelete")
ok(r.status_code == 200 and r.get_json()["profile"]["name"] == "PLA 0.2 everyday (2)", "undelete brings it back")

# ---- export / import
ex = c.get("/api/slice-profiles-export")
data = ex.get_json()
ok(ex.status_code == 200 and "attachment" in ex.headers.get("Content-Disposition", "") and len(data["profiles"]) == 5, "export gives every profile as a download")
ok(all("id" not in x and "rev" not in x for x in data["profiles"]), "an export carries settings, not this Rhino's ids or revisions")
r = post("/api/slice-profiles-import", data)
added = r.get_json().get("added", [])
ok(r.status_code == 200 and len(added) == 5 and all(a["name"].endswith(")") for a in added), "import adds them all, renaming clashes")
before = len(c.get("/api/slice-profiles").get_json()["profiles"])
broken = json.loads(json.dumps(data)); broken["profiles"][2]["settings"] = {"bogus": 1}
r = post("/api/slice-profiles-import", broken)
ok(r.status_code == 400 and "Profile 3 in the file" in r.get_json()["error"] and len(c.get("/api/slice-profiles").get_json()["profiles"]) == before,
   "a bad profile in an import refuses the whole file, nothing added")
ok(post("/api/slice-profiles-import", {"profiles": []}).status_code == 400, "a file that isn't an export is refused")

# ---- saved Prepare jobs
job = {"profileId": pid, "profileRev": 9, "process": "fdm", "engine": "kiri", "toolhead": "BlockOne", "material": "PLA",
       "overrides": {"infill": 0.35}, "placement": {"x": 100, "y": 80, "rotate": 0, "scale": 1}}
r = post("/api/prepare-jobs", {"file": "benchy.stl", "job": job})
ok(r.status_code == 200 and os.path.isfile(JOBS), "a Prepare job is saved on the Rhino, in rhino_data")
ok(c.get("/api/prepare-jobs").get_json()["jobs"]["benchy.stl"]["overrides"] == {"infill": 0.35}, "the job keeps only its overrides")
ok(post("/api/prepare-jobs", {"file": "../x.stl", "job": job}).status_code == 400, "a job name that climbs folders is refused")
ok(post("/api/prepare-jobs", {"file": "a.stl", "job": dict(job, overrides={"walls": -1})}).status_code == 400, "job overrides are checked like a profile")
ok(c.delete("/api/prepare-jobs", json={"file": "benchy.stl"}, headers=HDR).status_code == 200
   and "benchy.stl" not in c.get("/api/prepare-jobs").get_json()["jobs"], "a saved job can be deleted")
post("/api/prepare-jobs", {"file": "benchy.stl", "job": job})

# ---- two saves at once (Oct 27): Studio saves a new file's job under the toolhead and the file name together.
# Before 1.9.7 they shared one .tmp file: one crashed with a 500, or a job was lost, or the file was left corrupt.
import threading
codes, ROUNDS = [], 60
for i in range(ROUNDS):
    gate = threading.Barrier(3)
    def save(key):
        cl = app.test_client()
        gate.wait()
        codes.append((key, cl.post("/api/prepare-jobs", json={"file": key, "job": job}, headers=HDR).status_code))
    def read():   # a read at the same moment never sees a half-written file
        gate.wait()
        try: SP.SliceProfiles(app.config["PATHS"]).jobs()
        except Fail as e: codes.append(("read", str(e)))
    ts = [threading.Thread(target=save, args=(k,)) for k in (f"tool/T{i}", f"sphere {i}.stl")] + [threading.Thread(target=read)]
    [t.start() for t in ts]; [t.join() for t in ts]
saved = json.load(open(JOBS))["jobs"]
ok(all(code == 200 for _, code in codes) and len(codes) == 2 * ROUNDS, f"{2 * ROUNDS} saves in pairs at the same instant all succeed")
ok(all(f"tool/T{i}" in saved and f"sphere {i}.stl" in saved for i in range(ROUNDS)), "and no job is lost")
ok(not [n for n in os.listdir(os.path.dirname(JOBS)) if n.endswith(".tmp")], "and no temp file is left behind")
ok(oct(os.stat(JOBS).st_mode & 0o777) == "0o644", "the jobs file keeps its usual permissions (0644)")
for i in range(ROUNDS):
    for k in (f"tool/T{i}", f"sphere {i}.stl"):
        c.delete("/api/prepare-jobs", json={"file": k}, headers=HDR)

# ---- an unreadable file is never overwritten
good = open(FILE).read()
open(FILE, "w").write('{"schema": 1, "profiles": [')
lst = c.get("/api/slice-profiles").get_json()
ok(lst["ok"] is False and "can't be read" in lst["error"], "an unreadable profiles file is reported, not hidden")
r = post("/api/slice-profiles", PLA)
ok(r.status_code == 400 and open(FILE).read() == '{"schema": 1, "profiles": [', "and nothing is saved over it")
open(FILE, "w").write(good)

# ---- backup: profiles, history and saved jobs are in the zip, and restore as one item
from rhino import backup as B
ok("profiles" in B.ITEMS and "prepare/prepare_jobs.json" in B.ITEMS["profiles"]["files"], "backup has a 'Slice profiles and saved Prepare jobs' restore item")
svc = B.BackupService(app.config["PATHS"], None)
ok(svc._target("prepare/prepare_jobs.json") == JOBS, "saved jobs restore to rhino_data/prepare_jobs.json")
z = zipfile.ZipFile(io.BytesIO(), "w"); z.writestr("prepare/prepare_jobs.json", "{}"); z.writestr("config/myrhino/slice_profiles.json", "{}")
ok(sorted(svc._all_files(z)) == ["config/myrhino/slice_profiles.json", "prepare/prepare_jobs.json"], "a full restore brings back saved jobs too")

# ---- nothing here talks to Klipper
src = open(os.path.join(REPO, "rhino", "slice_profiles.py")).read() + open(os.path.join(REPO, "rhino", "portal", "profile_routes.py")).read()
ok("moonraker" not in src.lower().replace("nothing here talks to klipper", "") and "gcode/script" not in src, "profiles never send G-code or call Moonraker")

shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
