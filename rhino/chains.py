"""Process chains (Studio 0.40): a placement and the stages that work on it, saved by name. Design: rhino-studio docs/design-process-chain.md.

    myrhino/chains.json           {"schema": 1, "chains": [...]}
    myrhino/chains.history.json   revisions and deleted chains (rhino/versioned_store.py)

A chain: {id, name, preset, thickness, sheet, stages: [{id, kind, role, what, tool}], jobs: [{file, tool, stages}], created, updated, rev}.
sheet is where the placed sheet sits: {width, depth, x, y} in mm, x and y the centre on the bed (or null before it is set).

The Portal only stores chains. It never runs one, never starts a job and never writes Klipper config for one: Studio builds the job
files and runs each stage through today's start gates. This file still checks everything Studio checks, so a bad file can't reach
the screens even by hand:
- unknown fields, kinds or roles; numbers out of range; text with line breaks or control characters;
- the order rules: fixtures first, the sheet right after them, and no print after a laser, knife or spindle stage (order B needs the
  machine to keep Z homed, which isn't built);
- job file names that are plain names ending in .gcode (a start wizard takes one as FILE=).
Progress is not stored here: Studio reads it from the machine's job history.
"""
import re

from .errors import Fail
from .versioned_store import VersionedStore

MAX_CHAINS = 50
MAX_STAGES = 12
MAX_JOBS = 12
SHEET_MIN, SHEET_MAX = 0.2, 20        # the same limits as Studio's src/chain/chain.ts
PRESETS = ("sheet-print-laser", "print-laser")
KINDS = ("print", "manual", "laser", "knife", "cnc")
ROLES = ("fixtures", "place", "features", "work")
_NAME = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
_WHAT = re.compile(r"^[^\x00-\x1f<>\"\\]{1,60}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")                 # toolhead names
SHEET_SIZE = (10, 600)               # mm, one side of a sheet
SHEET_AT = (0, 700)                  # mm, the centre's X or Y on the bed
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,98}\.gcode$")  # no spaces, no path, no leading dot


def _only(d, keys, where):
    extra = set(d) - set(keys)
    if extra:
        raise Fail(f"{where}: unknown field {sorted(extra)[0]}")


def _int(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise Fail(f"{what} must be a whole number from {lo} to {hi}")
    return v


def clean_stage(st, where):
    if not isinstance(st, dict):
        raise Fail(f"{where}: not a stage")
    _only(st, ("id", "kind", "role", "what", "tool"), where)
    kind, role = st.get("kind"), st.get("role")
    if kind not in KINDS:
        raise Fail(f"{where}: unknown kind {kind!r}")
    if role not in ROLES:
        raise Fail(f"{where}: unknown role {role!r}")
    what = st.get("what")
    if not isinstance(what, str) or not _WHAT.match(what.strip()):
        raise Fail(f"{where}: a name of 1 to 60 characters, without quotes or line breaks")
    tool = st.get("tool")
    if kind == "manual":
        if tool is not None:
            raise Fail(f"{where}: a manual stage has no tool")
    elif not isinstance(tool, str) or not _TOKEN.match(tool):
        raise Fail(f"{where}: needs a toolhead name")
    if role in ("fixtures", "features") and kind != "print":
        raise Fail(f"{where}: {role} is a print stage")
    if role == "place" and kind != "manual":
        raise Fail(f"{where}: placing the sheet is a manual stage")
    return {"id": _int(st.get("id"), 1, 99, f"{where}: id"), "kind": kind, "role": role, "what": what.strip(), "tool": tool}


def order_problem(stages):
    """The first rule an order breaks, or None (Studio's orderProblem, word for word)."""
    roles = [s["role"] for s in stages]
    fx = roles.index("fixtures") if "fixtures" in roles else -1
    if fx > 0:
        return "Fixtures come first."
    if "place" in roles:
        pl = roles.index("place")
        if fx >= 0 and pl != fx + 1:
            return "The sheet is placed right after the fixtures."
        if any(r != "fixtures" for r in roles[:pl]):
            return "The sheet is placed before any stage that works on it."
    tool_kinds = [s["kind"] for s in stages if s["kind"] != "manual"]
    first = next((i for i, k in enumerate(tool_kinds) if k != "print"), None)
    if first is not None and "print" in tool_kinds[first:]:
        return ("A print after a laser, knife or spindle stage needs the machine to keep Z homed and a touch check, "
                "which is not built yet. Put the print first.")
    return None


def clean_sheet(sh, name):
    if sh is None:
        return None
    if not isinstance(sh, dict):
        raise Fail(f"{name}: the sheet's place must be width, depth, x and y")
    _only(sh, ("width", "depth", "x", "y"), f"{name}, sheet")
    out = {}
    for k, (lo, hi) in (("width", SHEET_SIZE), ("depth", SHEET_SIZE), ("x", SHEET_AT), ("y", SHEET_AT)):
        v = sh.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
            raise Fail(f"{name}: the sheet's {k} must be a number from {lo} to {hi} mm")
        out[k] = v
    return out


BODY_ROLES = ("sheet", "fixture", "feature", "skip")
MAX_BODIES = 200
_DESIGN_FILE = re.compile(r"^[^\x00-\x1f\\]{1,200}\.(3mf|stl|obj)$", re.I)


def clean_design(d, name):
    """The design a chain was made from: a file in the model library and the part each body plays (matched by position and name).
    The Portal doesn't read the file here; Studio fetches it from the library, which checks the path again."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise Fail(f"{name}: the design must be a library file and the part of each body")
    _only(d, ("file", "roles"), f"{name}, design")
    f, roles = d.get("file"), d.get("roles")
    if not isinstance(f, str) or not _DESIGN_FILE.match(f) or f.startswith("/") or any(p in ("", ".", "..") for p in f.split("/")):
        raise Fail(f"{name}: the design must be a 3MF, STL or OBJ file in the model library")
    if not isinstance(roles, list) or len(roles) > MAX_BODIES:
        raise Fail(f"{name}: the design lists the part each body plays (up to {MAX_BODIES})")
    out = []
    for i, r in enumerate(roles):
        if not isinstance(r, dict):
            raise Fail(f"{name}: design body {i + 1} is not a name and a part")
        _only(r, ("name", "role"), f"{name}, design body {i + 1}")
        n, role = r.get("name"), r.get("role")
        if not isinstance(n, str) or not 1 <= len(n) <= 120 or any(ord(ch) < 32 for ch in n):
            raise Fail(f"{name}: design body {i + 1} needs a name of 1 to 120 characters")
        if role not in BODY_ROLES:
            raise Fail(f"{name}: design body {i + 1}'s part must be one of {', '.join(BODY_ROLES)}")
        out.append({"name": n, "role": role})
    if sum(1 for r in out if r["role"] == "sheet") > 1:
        raise Fail(f"{name}: only one body can be the sheet")
    return {"file": f, "roles": out}


def clean_job(j, ids, where):
    if not isinstance(j, dict):
        raise Fail(f"{where}: not a job")
    _only(j, ("file", "tool", "stages"), where)
    f, tool, sts = j.get("file"), j.get("tool"), j.get("stages")
    if not isinstance(f, str) or not _FILE.match(f):
        raise Fail(f"{where}: the file name must be plain letters, numbers, . _ - and end in .gcode")
    if not isinstance(tool, str) or not _TOKEN.match(tool):
        raise Fail(f"{where}: needs a toolhead name")
    if not isinstance(sts, list) or not 1 <= len(sts) <= MAX_STAGES or not all(isinstance(i, int) and not isinstance(i, bool) and i in ids for i in sts):
        raise Fail(f"{where}: its stages must be stage ids from this chain")
    return {"file": f, "tool": tool, "stages": sts}


def clean(raw, where="Chain"):
    if not isinstance(raw, dict):
        raise Fail(f"{where}: not a chain")
    _only(raw, ("name", "preset", "thickness", "sheet", "design", "stages", "jobs", "id", "created", "updated", "rev", "schema"), where)
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME.match(name.strip()):
        raise Fail(f"{where}: a name of 1 to 60 characters")
    name = name.strip()
    if raw.get("preset") not in PRESETS:
        raise Fail(f"{name}: unknown preset")
    t = raw.get("thickness")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or t != t or not SHEET_MIN <= t <= SHEET_MAX):
        raise Fail(f"{name}: the sheet's thickness must be {SHEET_MIN} to {SHEET_MAX} mm, or not measured yet")
    sheet = clean_sheet(raw.get("sheet"), name)
    design = clean_design(raw.get("design"), name)
    sts = raw.get("stages")
    if not isinstance(sts, list) or not 1 <= len(sts) <= MAX_STAGES:
        raise Fail(f"{name}: 1 to {MAX_STAGES} stages")
    stages = [clean_stage(s, f"{name}, stage {i + 1}") for i, s in enumerate(sts)]
    ids = [s["id"] for s in stages]
    if len(set(ids)) != len(ids):
        raise Fail(f"{name}: two stages share an id")
    for role in ("fixtures", "place"):
        if sum(1 for s in stages if s["role"] == role) > 1:
            raise Fail(f"{name}: more than one {role} stage")
    bad = order_problem(stages)
    if bad:
        raise Fail(f"{name}: {bad}")
    jobs = raw.get("jobs", [])
    if not isinstance(jobs, list) or len(jobs) > MAX_JOBS:
        raise Fail(f"{name}: up to {MAX_JOBS} jobs")
    jobs = [clean_job(j, set(ids), f"{name}, job {i + 1}") for i, j in enumerate(jobs)]
    if len({j["file"] for j in jobs}) != len(jobs):
        raise Fail(f"{name}: two jobs share a file name")
    return {"name": name, "preset": raw["preset"], "thickness": t, "sheet": sheet, "design": design, "stages": stages, "jobs": jobs}


class Chains(VersionedStore):
    NAME, KEY, PREFIX, NOUN, NOUNS, EXPORT_KEY = "chains", "chains", "c_", "chain", "chains", "rhino_chains"
    MAX = MAX_CHAINS
    LIST_KEYS = ("id", "name", "preset", "thickness", "sheet", "design", "stages", "jobs", "created", "updated", "rev")
    DELETED_KEYS = ("id", "name", "deleted_at")
    EXPORT_FIELDS = ("name", "preset", "thickness", "sheet", "design", "stages", "jobs")

    def clean(self, raw):
        return clean(raw)
