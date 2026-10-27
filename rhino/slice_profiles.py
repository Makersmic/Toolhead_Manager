"""Slice profiles (Tool Manager 1.8, Phase 1). Design: docs/phase1-slice-profiles.md.

    myrhino/slice_profiles.json           {"schema": 1, "profiles": [...]}
    myrhino/slice_profiles.history.json   {"schema": 1, "revisions": {id: [old, ...]}, "deleted": [...]}
    rhino_data/prepare_jobs.json          {"schema": 1, "jobs": {file: job}}   (in the backup zip, not GitHub)

A profile holds one engine's own settings (Kiri: Studio's FdmSettings / LaserSettings / KnifeSettings /
CncSettings; PrusaSlicer: the INI options changed) and a header the Portal writes from them. There is no
cross-engine translator (decisions.md, 2026-10-23). Temperatures stay in the materials table.

Rules:
- Every save carries the rev it started from; a stale rev is refused (another device changed it).
- Unknown keys and out-of-range values are refused. Prepare's inputs clamp more tightly; these limits
  only stop nonsense from reaching the file.
- A file that exists but can't be read is never overwritten: saves are refused until it's fixed.
- Profiles never send G-code, start anything or change tool state.
"""
import copy
import functools
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time

from .errors import Fail

SCHEMA = 1
KEEP_REVISIONS = 5
KEEP_DELETED_S = 30 * 86400
MAX_PROFILES = 200
MAX_JOBS = 2000
ENGINES = ("kiri", "prusa")
PROCESSES = ("fdm", "laser", "dragknife", "cnc")      # Studio's own names
_ID = re.compile(r"^p_[a-z0-9]{5,12}$")
_NAME = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")      # toolhead and material keys
_FILE = re.compile(r"^[A-Za-z0-9_.\-/ ]{1,200}$")
_INI_KEY = re.compile(r"^[a-z0-9_]{1,64}$")


def _num(lo, hi):
    return ("num", lo, hi)


def _enum(*v):
    return ("enum", v)


BOOL = ("bool",)

# Every key Studio's settings types have (src/slicer/types.ts), with outer limits.
SPECS = {
    "fdm": {
        "nozzle": _num(0.1, 2), "path": _enum(0, 1), "layerHeight": _num(0.02, 1.5), "firstLayer": _num(0.02, 1.5),
        "walls": _num(0, 50), "topLayers": _num(0, 100), "bottomLayers": _num(0, 100), "infill": _num(0, 1),
        "infillType": _enum("grid", "gyroid", "hex", "linear", "triangle"), "supports": BOOL, "brim": _num(0, 100),
        "speed": _num(1, 1000), "firstLayerSpeed": _num(1, 1000), "retract": _num(0, 20), "fan": _num(0, 1),
        "lineWidth": _num(0, 3), "adaptive": BOOL, "minLayer": _num(0, 1.5),
        "wallOrder": _enum("in-out", "out-in", "alternate"), "seam": _enum("last", "center", "origin", "random", "spiral"),
        "thinWalls": _enum("off", "basic", "adaptive"), "fillAngle": _num(-360, 360), "fillOverlap": _num(0, 2),
        "outerSpeed": _num(0, 1000), "travelSpeed": _num(1, 2000), "minSpeed": _num(0, 1000), "maxFlow": _num(0, 200),
        "retractSpeed": _num(0, 300), "zHop": _num(0, 10), "wipe": _num(0, 20), "coast": _num(0, 20),
        "retractEachLayer": BOOL, "avoidCrossing": BOOL, "supportAngle": _num(0, 90), "supportDensity": _num(0, 1),
        "supportGapXY": _num(0, 10), "supportGapZ": BOOL, "supportOutline": BOOL, "fanFromLayer": _num(0, 1000),
        "minLayerTime": _num(0, 600), "skirtGap": _num(0, 100), "raft": BOOL, "raftSpacing": _num(0, 10), "vase": BOOL,
    },
    "laser": {"power": _num(0, 1), "feed": _num(1, 20000), "passes": _num(1, 100), "cutHeight": _num(0, 100),
              "kerf": _num(0, 5), "smooth": _num(0, 5), "outerOnly": BOOL},
    "dragknife": {"feed": _num(1, 20000), "depth": _num(0, 20), "passes": _num(1, 100), "tip": _num(0, 10),
              "plunge": _num(1, 20000), "cutHeight": _num(0, 100), "smooth": _num(0, 5), "outerOnly": BOOL},
    "cnc": {"operation": _enum("cutout", "clear-and-cutout"), "ops": ("ops",), "toolType": _enum("endmill", "ballmill"),
            "toolDiameter": _num(0.05, 50), "fluteLength": _num(0, 200), "extraTop": _num(0, 50), "stepDown": _num(0, 50),
            "stepOver": _num(0, 1), "feed": _num(1, 20000), "plunge": _num(1, 20000), "margin": _num(0, 100),
            "clearance": _num(0, 100)},
}
CNC_OP = {"kind": _enum("level", "rough", "outline"), "on": BOOL, "stepDown": _num(0, 50), "stepOver": _num(0, 1),
          "feed": _num(1, 20000), "leave": _num(0, 50), "depth": _num(0, 200), "side": _enum("outside", "inside"),
          "direction": _enum("climb", "conventional")}
# What a list shows, per process (header: filled from settings on every save, never edited)
HEADER_KEYS = {"fdm": ("nozzle", "layerHeight", "walls", "infill", "speed"), "laser": ("power", "feed", "passes"),
               "dragknife": ("feed", "depth", "passes"), "cnc": ("toolDiameter", "stepDown", "feed")}
PRUSA_HEADER = {"layer_height": "layerHeight", "nozzle_diameter": "nozzle", "perimeters": "walls", "fill_density": "infill"}


def _check_value(where, key, spec, v):
    kind = spec[0]
    if kind == "num":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise Fail(f"{where}: {key} must be a number")
        if not spec[1] <= v <= spec[2]:
            raise Fail(f"{where}: {key} must be between {spec[1]} and {spec[2]}")
    elif kind == "bool":
        if not isinstance(v, bool):
            raise Fail(f"{where}: {key} must be true or false")
    elif kind == "enum":
        if isinstance(v, bool) or v not in spec[1]:
            raise Fail(f"{where}: {key} must be one of {', '.join(map(str, spec[1]))}")
    elif kind == "ops":
        if not isinstance(v, list) or len(v) > 10:
            raise Fail(f"{where}: ops must be a list of up to 10 operations")
        for i, op in enumerate(v):
            _check_keys(f"{where}, operation {i + 1}", op, CNC_OP)


def _check_keys(where, obj, spec):
    if not isinstance(obj, dict):
        raise Fail(f"{where}: expected settings")
    extra = sorted(set(obj) - set(spec))
    if extra:
        raise Fail(f"{where}: unknown setting {extra[0]}")
    for k, v in obj.items():
        _check_value(where, k, spec[k], v)


def check_settings(engine, process, settings, where="Profile"):
    """Kiri: Studio's own settings shape, may be partial (Prepare fills the rest from its defaults).
    PrusaSlicer: INI options as strings (Studio checks each against PrusaSlicer's schema)."""
    if engine == "prusa":
        if process != "fdm":
            raise Fail(f"{where}: PrusaSlicer profiles are for 3D printing only")
        if not isinstance(settings, dict) or len(settings) > 600:
            raise Fail(f"{where}: expected PrusaSlicer options")
        for k, v in settings.items():
            if not _INI_KEY.match(str(k)):
                raise Fail(f"{where}: {k!r} isn't a PrusaSlicer option name")
            if not isinstance(v, str) or len(v) > 2000 or "\n" in v or "\r" in v:
                raise Fail(f"{where}: {k} must be one line of text")
        return
    _check_keys(where, settings, SPECS[process])


def _header(p):
    s = p["settings"]
    if p["engine"] == "prusa":
        return {short: s[k] for k, short in PRUSA_HEADER.items() if k in s}
    return {k: s[k] for k in HEADER_KEYS[p["process"]] if k in s}


def clean(raw, where="Profile"):
    """A profile as the Portal stores it: checked, header filled. Raises Fail with a message for the screen."""
    if not isinstance(raw, dict):
        raise Fail(f"{where}: expected a profile")
    name = str(raw.get("name", "")).strip()
    if not _NAME.match(name):
        raise Fail(f"{where}: give it a name (up to 60 characters)")
    engine, process = raw.get("engine"), raw.get("process")
    if engine not in ENGINES:
        raise Fail(f"{name}: engine must be kiri or prusa")
    if process not in PROCESSES:
        raise Fail(f"{name}: process must be fdm, laser, dragknife or cnc")
    out = {"name": name, "engine": engine, "process": process}
    for k in ("toolhead", "material"):
        v = raw.get(k)
        if v in (None, ""):
            out[k] = None
        elif isinstance(v, str) and _TOKEN.match(v):
            out[k] = v
        else:
            raise Fail(f"{name}: {k} must be a name of letters, digits, - _ .")
    settings = raw.get("settings", {})
    check_settings(engine, process, settings, name)
    out["settings"] = copy.deepcopy(settings)
    notes = raw.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 2000:
        raise Fail(f"{name}: notes must be text, up to 2000 characters")
    out["notes"] = notes
    out["header"] = _header(out)
    return out


# ---------------------------------------------------------------- files
def _read(path, empty):
    """(data, ok). Missing = empty and ok. Present but unreadable = (None, False): never overwrite it."""
    if not os.path.exists(path):
        return copy.deepcopy(empty), True
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or d.get("schema") != SCHEMA:
            return None, False
        return d, True
    except (OSError, ValueError):
        return None, False


def _write(path, data):
    """Atomic: a temp file of its own (two writers never share one), flushed to disk, then renamed over."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)   # mkstemp makes 0600; keep what the old writer gave
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# One change at a time. Studio saves a job under its toolhead and under its file name in the same instant;
# Flask serves them on two threads, and an unlocked read -> change -> write lost one, or crashed (Oct 27).
_LOCK = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def run(*a, **kw):
        with _LOCK:
            return fn(*a, **kw)
    return run


class SliceProfiles:
    def __init__(self, paths, now=time.time):
        self.paths, self.now = paths, now
        my = os.path.join(paths.cfg, "myrhino")
        self.file = os.path.join(my, "slice_profiles.json")
        self.hist_file = os.path.join(my, "slice_profiles.history.json")
        self.jobs_file = os.path.join(paths.state_dir, "prepare_jobs.json")

    # ---- reading
    def _profiles(self):
        d, ok = _read(self.file, {"schema": SCHEMA, "profiles": []})
        if not ok:
            raise Fail("myrhino/slice_profiles.json can't be read, so it's kept as it is. Fix or remove it by hand "
                       "(a backup has the last good copy), then try again.")
        return d

    def _history(self):
        d, ok = _read(self.hist_file, {"schema": SCHEMA, "revisions": {}, "deleted": []})
        if not ok:
            raise Fail("myrhino/slice_profiles.history.json can't be read, so it's kept as it is. Fix or remove it by hand.")
        cut = self.now() - KEEP_DELETED_S
        d["deleted"] = [p for p in d.get("deleted", []) if p.get("deleted_at", 0) >= cut]
        return d

    def state(self, full=False):
        """For the list screen (full: with settings, for Prepare): profiles, or why the file can't be read."""
        try:
            return {"ok": True, "profiles": self.list(full)}
        except Fail as e:
            return {"ok": False, "error": str(e), "profiles": []}

    def list(self, full=False):
        keys = ("id", "name", "engine", "process", "toolhead", "material", "header", "notes", "created", "updated", "rev")
        return [{k: p[k] for k in keys + (("settings",) if full else ())} for p in self._profiles()["profiles"]]

    def get(self, pid):
        for p in self._profiles()["profiles"]:
            if p["id"] == pid:
                return p
        raise Fail("That profile isn't on the Rhino (deleted, or never saved)")

    # ---- writing
    def _unique_name(self, profiles, name, skip=None):
        taken = {p["name"].lower() for p in profiles if p["id"] != skip}
        if name.lower() not in taken:
            return name
        n = 2
        while f"{name} ({n})".lower() in taken:
            n += 1
        return f"{name} ({n})"[:60]

    @_locked
    def create(self, raw):
        d = self._profiles()
        if len(d["profiles"]) >= MAX_PROFILES:
            raise Fail(f"The Rhino keeps up to {MAX_PROFILES} profiles. Delete some first.")
        p = clean(raw)
        p["name"] = self._unique_name(d["profiles"], p["name"])
        t = int(self.now())
        p.update(id="p_" + secrets.token_hex(4), created=t, updated=t, rev=1)
        d["profiles"].append(p)
        _write(self.file, d)
        return p

    @_locked
    def save(self, pid, raw, rev):
        d = self._profiles()
        h = self._history()
        for i, old in enumerate(d["profiles"]):
            if old["id"] != pid:
                continue
            if rev != old["rev"]:
                raise Fail(f"{old['name']} was changed on another device (now revision {old['rev']}). Reload it, then save again.")
            p = clean(raw)
            if p["name"].lower() != old["name"].lower():
                p["name"] = self._unique_name(d["profiles"], p["name"], skip=pid)
            p.update(id=pid, created=old["created"], updated=int(self.now()), rev=old["rev"] + 1)
            revs = h["revisions"].setdefault(pid, [])
            revs.insert(0, old)
            del revs[KEEP_REVISIONS:]
            d["profiles"][i] = p
            _write(self.hist_file, h)
            _write(self.file, d)
            return p
        raise Fail("That profile isn't on the Rhino (deleted, or never saved)")

    @_locked
    def delete(self, pid):
        d = self._profiles()
        h = self._history()
        keep = [p for p in d["profiles"] if p["id"] != pid]
        if len(keep) == len(d["profiles"]):
            raise Fail("That profile isn't on the Rhino")
        gone = next(p for p in d["profiles"] if p["id"] == pid)
        h["deleted"].insert(0, dict(gone, deleted_at=int(self.now())))
        d["profiles"] = keep
        _write(self.hist_file, h)
        _write(self.file, d)
        return {"deleted": pid, "name": gone["name"]}

    def history(self, pid):
        return self._history()["revisions"].get(pid, [])

    @_locked
    def revert(self, pid, to_rev):
        """Save an old revision as the newest one (history keeps what it replaces)."""
        cur = self.get(pid)
        old = next((r for r in self.history(pid) if r["rev"] == to_rev), None)
        if old is None:
            raise Fail(f"Revision {to_rev} isn't kept any more (the last {KEEP_REVISIONS} are)")
        return self.save(pid, old, cur["rev"])

    def deleted(self):
        return [{k: p.get(k) for k in ("id", "name", "engine", "process", "deleted_at")} for p in self._history()["deleted"]]

    @_locked
    def undelete(self, pid):
        h = self._history()
        p = next((x for x in h["deleted"] if x["id"] == pid), None)
        if p is None:
            raise Fail("That profile isn't in the deleted list any more")
        d = self._profiles()
        if any(x["id"] == pid for x in d["profiles"]):
            raise Fail("That profile is already back")
        p = {k: v for k, v in p.items() if k != "deleted_at"}
        p["name"] = self._unique_name(d["profiles"], p["name"])
        d["profiles"].append(p)
        h["deleted"] = [x for x in h["deleted"] if x["id"] != pid]
        _write(self.file, d)
        _write(self.hist_file, h)
        return p

    # ---- export / import
    def export(self, pid=None):
        ps = [self.get(pid)] if pid else self._profiles()["profiles"]
        return {"rhino_slice_profiles": SCHEMA, "exported": int(self.now()),
                "profiles": [{k: p[k] for k in ("name", "engine", "process", "toolhead", "material", "settings", "notes")}
                             for p in ps]}

    @_locked
    def import_(self, data):
        """Every profile is checked before any is added; a clashing name gets " (2)"."""
        if not isinstance(data, dict) or data.get("rhino_slice_profiles") != SCHEMA or not isinstance(data.get("profiles"), list):
            raise Fail("That isn't a Rhino slice profiles export")
        cleaned = []
        for i, p in enumerate(data["profiles"]):
            try:
                cleaned.append(clean(p))
            except Fail as e:
                raise Fail(f"Profile {i + 1} in the file: {e}. Nothing was imported.")
        d = self._profiles()
        if len(d["profiles"]) + len(cleaned) > MAX_PROFILES:
            raise Fail(f"The Rhino keeps up to {MAX_PROFILES} profiles; this file would go over")
        t = int(self.now())
        added = []
        for p in cleaned:
            p["name"] = self._unique_name(d["profiles"], p["name"])
            p.update(id="p_" + secrets.token_hex(4), created=t, updated=t, rev=1)
            d["profiles"].append(p)
            added.append({"id": p["id"], "name": p["name"]})
        _write(self.file, d)
        return added

    # ---- per-file jobs (rhino_data: in the backup zip, never pushed to GitHub)
    def _jobs(self):
        d, ok = _read(self.jobs_file, {"schema": SCHEMA, "jobs": {}})
        if not ok:
            raise Fail("rhino_data/prepare_jobs.json can't be read, so it's kept as it is. Fix or remove it by hand.")
        return d

    def jobs(self):
        return self._jobs()["jobs"]

    @_locked
    def save_job(self, file, job):
        if not isinstance(file, str) or not _FILE.match(file) or ".." in file:
            raise Fail("That file name can't hold a saved job")
        j = _clean_job(job)
        d = self._jobs()
        if file not in d["jobs"] and len(d["jobs"]) >= MAX_JOBS:
            oldest = min(d["jobs"], key=lambda k: d["jobs"][k].get("saved", 0))
            del d["jobs"][oldest]
        j["saved"] = int(self.now())
        d["jobs"][file] = j
        _write(self.jobs_file, d)
        return j

    @_locked
    def delete_job(self, file):
        d = self._jobs()
        if d["jobs"].pop(file, None) is not None:
            _write(self.jobs_file, d)
        return {"deleted": file}


def _clean_job(job):
    """{profileId, profileRev, process, engine, toolhead, material, overrides, placement}. Overrides are
    checked like a profile's settings, so a job can't smuggle in what a profile couldn't hold."""
    if not isinstance(job, dict):
        raise Fail("Expected a job")
    process, engine = job.get("process"), job.get("engine", "kiri")
    if process not in PROCESSES or engine not in ENGINES:
        raise Fail("A job needs its process and engine")
    pid = job.get("profileId")
    if pid is not None and not (isinstance(pid, str) and (_ID.match(pid) or pid.startswith("builtin:")) and len(pid) <= 60):
        raise Fail("A job's profile id isn't valid")
    rev = job.get("profileRev")
    if rev is not None and (isinstance(rev, bool) or not isinstance(rev, int) or rev < 0):
        raise Fail("A job's profile revision isn't valid")
    out = {"profileId": pid, "profileRev": rev, "process": process, "engine": engine}
    for k in ("toolhead", "material"):
        v = job.get(k)
        if v not in (None, "") and not (isinstance(v, str) and _TOKEN.match(v)):
            raise Fail(f"A job's {k} isn't valid")
        out[k] = v or None
    ov = job.get("overrides", {})
    check_settings(engine, process, ov, "Job settings")
    out["overrides"] = copy.deepcopy(ov)
    pl = job.get("placement", {})
    _check_keys("Job placement", pl, {"x": _num(-5000, 5000), "y": _num(-5000, 5000), "rotate": _num(-3600, 3600),
                                      "scale": _num(0.001, 1000)})
    out["placement"] = dict(pl)
    return out
