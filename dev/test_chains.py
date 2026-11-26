"""Process chains (Studio 0.40): store, validation, the order rules, revisions, delete and undelete, export and import, backup.
Run: python3 dev/test_chains.py  (needs flask)"""
import copy, json, os, shutil, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = tempfile.mkdtemp(prefix="rhino-chains-test-")
CFG = ROOT + "/printer_data/config"
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns("__pycache__", ".git", "studio", "node_modules", "registry_backups"))
sys.path.insert(0, CFG)
os.environ["HOME"] = ROOT
from rhino.portal import create_app, security
from rhino import backup as B

app = create_app(CFG, "http://127.0.0.1:9")
c = app.test_client()
HDR = {security.HEADER: security.TOKEN}
FILE = CFG + "/myrhino/chains.json"
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)


def st(i, kind, role, what, tool): return {"id": i, "kind": kind, "role": role, "what": what, "tool": tool}


FULL = {"name": "Front plate 001", "preset": "sheet-print-laser", "thickness": 3.1, "sheet": {"width": 160, "depth": 110, "x": 275, "y": 200}, "stages": [
    st(1, "print", "fixtures", "Print fixtures", "BlockOne"), st(2, "manual", "place", "Place the sheet", None),
    st(3, "print", "features", "Print features", "BlockOne"), st(4, "laser", "work", "Laser", "LightSaber")],
    "jobs": [{"file": "front-plate-001_job1_print.gcode", "tool": "BlockOne", "stages": [1, 2, 3]},
             {"file": "front-plate-001_job2_laser.gcode", "tool": "LightSaber", "stages": [4]}]}


def post(path, body, hdr=HDR): return c.post(path, json=body, headers=hdr)
def err(r): return (r.get_json() or {}).get("error", "")
def mk(**kw):
    d = copy.deepcopy(FULL); d.update(kw); return d


# ---- create, read, list
r = post("/api/chains", FULL)
ch = r.get_json().get("chain") or {}
ok(r.status_code == 200 and ch.get("id", "").startswith("c_") and ch.get("rev") == 1, "a chain is saved, with an id and revision 1")
ok(os.path.isfile(FILE) and json.load(open(FILE))["schema"] == 1, "it's in myrhino/chains.json (inside the config folder, so it's backed up)")
ok(c.get("/api/chains").get_json()["chains"][0]["name"] == "Front plate 001", "it's listed")
ok(c.get(f"/api/chains/{ch['id']}").get_json()["chain"]["stages"][1]["role"] == "place", "and read back whole")
r = post("/api/chains", FULL, hdr={})
ok(r.status_code == 400 and "Reload the page" in err(r), "a write without the Portal's token is refused")
ok(post("/api/chains", mk(name="Bracket", preset="print-laser", thickness=None, jobs=[],
                          stages=[st(1, "print", "features", "Print", "BlockOne"), st(2, "laser", "work", "Laser", "LightSaber")])).status_code == 200,
   "a chain without a sheet saves, with no thickness")
ok(post("/api/chains", mk(name="Draft", thickness=None, jobs=[])).status_code == 200, "a sheet chain saves before the sheet is measured")

# ---- validation: every refusal says why
def refused(body, words, msg):
    r = post("/api/chains", body)
    ok(r.status_code == 400 and words in err(r), msg + f" ({err(r)[:70]})")


refused(mk(name=""), "name of 1 to 60", "a name is needed")
refused(mk(name="a<b"), "name of 1 to 60", "no angle brackets in a name")
refused(mk(preset="mystery"), "unknown preset", "the preset is checked")
for t in (0, 0.1, 21, -3, True, "3", float("nan")):
    refused(mk(thickness=t), "thickness", f"thickness {t!r} is refused")
refused(dict(FULL, extra=1), "unknown field", "an unknown field is refused")
refused(mk(stages=[]), "1 to 12 stages", "at least one stage")
refused(mk(stages=FULL["stages"] * 4), "1 to 12 stages", "at most 12 stages")
s = copy.deepcopy(FULL["stages"])
s[0]["kind"] = "plasma"; refused(mk(stages=s), "unknown kind", "an unknown kind")
s = copy.deepcopy(FULL["stages"]); s[0]["role"] = "boss"; refused(mk(stages=s), "unknown role", "an unknown role")
s = copy.deepcopy(FULL["stages"]); s[1]["tool"] = "BlockOne"; refused(mk(stages=s), "no tool", "a manual stage has no tool")
s = copy.deepcopy(FULL["stages"]); s[3]["tool"] = None; refused(mk(stages=s), "toolhead name", "a tool stage needs a tool")
s = copy.deepcopy(FULL["stages"]); s[3]["tool"] = "a b"; refused(mk(stages=s), "toolhead name", "tool names are checked")
s = copy.deepcopy(FULL["stages"]); s[0]["what"] = 'x"; M112'; refused(mk(stages=s), "without quotes", "no quotes or odd text in a stage name")
s = copy.deepcopy(FULL["stages"]); s[3]["id"] = 1; refused(mk(stages=s, jobs=[]), "share an id", "stage ids are unique")
s = copy.deepcopy(FULL["stages"]); s[2]["role"] = "fixtures"; refused(mk(stages=s, jobs=[]), "more than one fixtures", "one fixtures stage")
s = copy.deepcopy(FULL["stages"]); s[0]["kind"] = "laser"; refused(mk(stages=s, jobs=[]), "fixtures is a print", "fixtures are a print stage")
s = copy.deepcopy(FULL["stages"]); s[1]["kind"] = "print"; s[1]["tool"] = "BlockOne"; refused(mk(stages=s, jobs=[]), "manual stage", "placing the sheet is manual")

# ---- the order rules (the same as Studio's)
f, p, ft, la = copy.deepcopy(FULL["stages"])
refused(mk(stages=[ft, f, p, la], jobs=[]), "Fixtures come first", "fixtures first")
refused(mk(stages=[f, ft, p, la], jobs=[]), "right after the fixtures", "the sheet right after the fixtures")
refused(mk(stages=[f, p, la, ft], jobs=[]), "touch check", "no print after the laser (order B is not built)")
refused(mk(preset="print-laser", stages=[la, ft], jobs=[]), "touch check", "the same without a sheet")
sw = [st(1, "print", "work", "Print", "BlockOne"), st(2, "print", "work", "Print", "BlockOne")]
ok(post("/api/chains", mk(name="Two prints", preset="print-laser", thickness=None, stages=sw, jobs=[])).status_code == 200, "two prints in either order are fine")

# ---- the sheet's place
ok(post("/api/chains", mk(name="No sheet yet", sheet=None)).status_code == 200, "a chain saves before the sheet is placed")
ok(c.get("/api/chains").get_json()["chains"][0]["sheet"] == {"width": 160, "depth": 110, "x": 275, "y": 200}, "the sheet's place is stored as given")
for bad in ({"width": 5, "depth": 110, "x": 275, "y": 200}, {"width": 160, "depth": 700, "x": 275, "y": 200}, {"width": 160, "depth": 110, "x": -1, "y": 200},
            {"width": "160", "depth": 110, "x": 275, "y": 200}, {"width": True, "depth": 110, "x": 275, "y": 200}, {"width": 160, "depth": 110, "x": 275},
            {"width": 160, "depth": 110, "x": 275, "y": 200, "z": 3}, "big"):
    refused(mk(sheet=bad), "sheet", f"a bad sheet is refused ({str(bad)[:40]})")

# ---- jobs
refused(mk(jobs=[dict(FULL["jobs"][0], file="a b.gcode")]), "file name", "no spaces in a job file")
refused(mk(jobs=[dict(FULL["jobs"][0], file="../x.gcode")]), "file name", "no paths in a job file")
refused(mk(jobs=[dict(FULL["jobs"][0], file="x.txt")]), "file name", "a job file ends in .gcode")
refused(mk(jobs=[dict(FULL["jobs"][0], file=".hidden.gcode")]), "file name", "no leading dot")
refused(mk(jobs=[dict(FULL["jobs"][0], stages=[1, 77])]), "stage ids from this chain", "a job names this chain's stages")
refused(mk(jobs=[dict(FULL["jobs"][0], stages=[])]), "stage ids from this chain", "a job has stages")
refused(mk(jobs=[FULL["jobs"][0], dict(FULL["jobs"][1], file=FULL["jobs"][0]["file"])]), "share a file name", "job file names are unique")
refused(mk(jobs=[dict(FULL["jobs"][0], mystery=1)]), "unknown field", "an unknown job field")
refused(mk(jobs=[FULL["jobs"][0]] * 13), "up to 12 jobs", "at most 12 jobs")

# ---- save with rev, history, revert, delete, undelete
cid = ch["id"]
r = post(f"/api/chains/{cid}", {"chain": mk(name="Front plate", thickness=3.2), "rev": 1})
ok(r.status_code == 200 and r.get_json()["chain"]["rev"] == 2 and r.get_json()["chain"]["thickness"] == 3.2, "saved with the revision it started from")
r = post(f"/api/chains/{cid}", {"chain": FULL, "rev": 1})
ok(r.status_code == 400 and "changed on another device" in err(r), "a stale revision is refused")
ok(post(f"/api/chains/{cid}", {"chain": FULL}).status_code == 400, "a save with no revision is refused")
ok(c.get(f"/api/chains/{cid}/history").get_json()["revisions"][0]["rev"] == 1, "the old revision is kept")
for i in range(2, 9):
    post(f"/api/chains/{cid}", {"chain": mk(thickness=3 + i / 10), "rev": i})
ok(len(c.get(f"/api/chains/{cid}/history").get_json()["revisions"]) == 5, "only the last 5 revisions are kept")
r = post(f"/api/chains/{cid}/revert", {"to": 1})
ok(r.status_code == 400 and "isn't kept any more" in err(r), "a revision that was pruned can't be reverted to")
top = max(x["rev"] for x in c.get(f"/api/chains/{cid}/history").get_json()["revisions"])
r = post(f"/api/chains/{cid}/revert", {"to": top})
ok(r.status_code == 200 and r.get_json()["chain"]["rev"] == 10, "revert saves an old one as the newest")
ok(c.delete(f"/api/chains/{cid}", headers=HDR).status_code == 200 and all(x["id"] != cid for x in c.get("/api/chains").get_json()["chains"]), "deleted")
ok(any(x["id"] == cid for x in c.get("/api/chains").get_json()["deleted"]), "and listed as deleted, for undo")
ok(c.delete(f"/api/chains/{cid}").status_code == 400, "a delete without the token is refused")
ok(post(f"/api/chains/{cid}/undelete", {}).status_code == 200, "brought back")

# ---- export, import
ex = c.get("/api/chains-export").get_json()
ok(ex.get("rhino_chains") == 1 and len(ex["chains"]) >= 3 and "id" not in ex["chains"][0] and "rev" not in ex["chains"][0], "export holds every chain without ids")
n0 = len(c.get("/api/chains").get_json()["chains"])
r = post("/api/chains-import", ex)
names = [x["name"] for x in c.get("/api/chains").get_json()["chains"]]
ok(r.status_code == 200 and len(names) == 2 * n0 and any(x.endswith("(2)") for x in names), "import adds copies, a clashing name gets (2)")
bad = dict(ex, chains=ex["chains"] + [mk(name="Evil", stages=[la, ft], jobs=[])])
n = len(c.get("/api/chains").get_json()["chains"])
r = post("/api/chains-import", bad)
ok(r.status_code == 400 and len(c.get("/api/chains").get_json()["chains"]) == n, "a file with one bad chain imports nothing")
ok(post("/api/chains-import", {"rhino_user_macros": 1, "macros": []}).status_code == 400, "a macros export isn't taken as chains")

# ---- the limit
import rhino.chains as CH
CH.Chains.MAX = n
r = post("/api/chains", mk(name="One too many"))
ok(r.status_code == 400 and "keeps up to" in err(r), "the number of chains is limited")
CH.Chains.MAX = CH.MAX_CHAINS

# ---- an unreadable file is never overwritten
open(FILE, "w").write("{broken")
r = post("/api/chains", FULL)
ok(r.status_code == 400 and "can't be read" in err(r) and open(FILE).read() == "{broken", "an unreadable file is kept as it is, saves refused")
ok(c.get("/api/chains").get_json()["ok"] is False, "and the list says why")
os.remove(FILE)

# ---- backup: a restorable item of its own
ok(B.ITEMS["chains"]["files"] == ["config/myrhino/chains.json", "config/myrhino/chains.history.json"], "chains restore on their own from a backup")

# ---- nothing here talks to Klipper
src = "".join(open(os.path.join(REPO, *p)).read() for p in (("rhino", "chains.py"), ("rhino", "portal", "chain_routes.py")))
ok("moonraker" not in src.lower() and "gcode/script" not in src and "printer.gcode" not in src, "the Portal never runs a chain or calls Moonraker")

shutil.rmtree(ROOT, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
