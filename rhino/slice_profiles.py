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
import math
import os
import re
import time

from .errors import Fail
from .versioned_store import KEEP_REVISIONS, SCHEMA, VersionedStore, _locked, _read, _write  # noqa: F401 (KEEP_REVISIONS: tests)

MAX_PROFILES = 200
MAX_JOBS = 2000
ENGINES = ("kiri", "prusa")
PROCESSES = ("fdm", "laser", "dragknife", "cnc")      # Studio's own names
_ID = re.compile(r"^p_[a-z0-9]{5,12}$")
_NAME = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")      # toolhead and material keys
_FILE = re.compile(r"^[A-Za-z0-9_.\-/ ]{1,200}$")
# a part's name is its file's name as loaded: no folders, no control characters
_PART = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")
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


# ---------------------------------------------------------------- the store (rhino/versioned_store.py)
class SliceProfiles(VersionedStore):
    NAME, KEY, PREFIX, NOUN, NOUNS, EXPORT_KEY = "slice_profiles", "profiles", "p_", "profile", "profiles", "rhino_slice_profiles"
    MAX = MAX_PROFILES
    LIST_KEYS = ("id", "name", "engine", "process", "toolhead", "material", "header", "notes", "created", "updated", "rev")
    DELETED_KEYS = ("id", "name", "engine", "process", "deleted_at")
    EXPORT_FIELDS = ("name", "engine", "process", "toolhead", "material", "settings", "notes")

    def __init__(self, paths, now=time.time):
        super().__init__(paths, now)
        self.jobs_file = os.path.join(paths.state_dir, "prepare_jobs.json")

    def clean(self, raw):
        return clean(raw)

    def _profiles(self):
        return self._items()

    def list(self, full=False):
        keys = self.LIST_KEYS + (("settings",) if full else ())
        return [{k: p[k] for k in keys} for p in self._items()["profiles"]]

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
    """{profileId, profileRev, process, engine, toolhead, material, overrides, placement, supportMarks?}. Overrides are
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
                                      "tiltX": _num(-3600, 3600), "tiltY": _num(-3600, 3600),
                                      "scale": _num(0.001, 1000)})
    out["placement"] = dict(pl)
    if "supportMarks" in job:
        out["supportMarks"] = _clean_marks(job["supportMarks"])
    return out


MAX_MARKS = 500
_MARK = {"part": None, "x": _num(-5000, 5000), "y": _num(-5000, 5000), "z": _num(-5000, 5000), "r": _num(0.5, 50)}


def _clean_marks(marks):
    """Supports placed by hand (Studio 0.12+): only where these marks are, on the parts they name, each a point in that
    part's own coordinates as loaded and a radius in mm; "kind": "block" stops support there (PrusaSlicer only). Its
    presence means "only where I mark", even with none placed. {"marks": [{"part", "x", "y", "z", "r", "kind"?}]}"""
    if not isinstance(marks, dict) or set(marks) - {"marks"}:
        raise Fail("Support marks: expected {marks: [...]}")
    lst = marks.get("marks", [])
    if not isinstance(lst, list) or len(lst) > MAX_MARKS:
        raise Fail(f"Support marks: a list of at most {MAX_MARKS}")
    out = []
    for m in lst:
        if not isinstance(m, dict) or set(m) - {"kind"} != set(_MARK):
            raise Fail("Support marks: each needs part, x, y, z and r")
        if "kind" in m and m["kind"] not in ("enforce", "block"):
            raise Fail("Support marks: kind is enforce or block")
        if not (isinstance(m["part"], str) and _PART.match(m["part"]) and not m["part"].startswith(".")):
            raise Fail("Support marks: a part name isn't valid")
        for k, spec in _MARK.items():
            if spec:
                _check_value("Support marks", k, spec, m[k])
        out.append({k: m[k] for k in _MARK} | ({"kind": "block"} if m.get("kind") == "block" else {}))
    return {"marks": out}
