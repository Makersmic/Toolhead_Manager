"""The drop-down lists the Admin screen edits (tool side). Maintenance lists live with the tasks.

    myrhino/portal_lists.json      kinds (sub-types of Additive / Subtractive / Passive), material names,
                                   nozzle sizes, system-hardware categories

A missing file means "the defaults below". Built-in kinds can be renamed and their starting values
changed but not deleted (starter maintenance tasks and old tools refer to them); a kind or category
something still uses cannot be deleted either.
"""
import copy
import json
import os
import re

from .errors import Fail
from .presets import (BEHAVIOUR_TYPE, BEHAVIOURS, CATEGORIES, CATEGORY_BEHAVIOURS, KIND_ID_RE, LIMITS, MAT_RE,
                      MAX_CHECKLIST_ITEMS, MAX_CHECKLIST_LEN, PASSIVE_PRESET, POWER_PRESETS, SAFE_TEXT, SAFE_TEXT_HELP)

DEFAULT_KINDS = [
    {"id": "PRINT_HEAD", "category": "additive", "behaviour": "PRINT_HEAD", "label": "3D-print head (clone of an existing one)",
     "help": "A new nozzle size or head that reuses an existing print tool's extruder and heater."},
    {"id": "DISPENSER", "category": "additive", "behaviour": "POWERED", "label": "Paste or glue dispenser",
     "help": "A pump or plunger driven by a PWM output.", "cap": 1.0, "max_on_s": 300,
     "materials": {"DEFAULT": {"power": 0.5, "feed_rate": 400}},
     "checklist": ["Cartridge loaded and the nozzle is clear", "Work surface is clean and clamped"]},
    {"id": "HOT_WIRE", "category": "subtractive", "behaviour": "POWERED", "label": "Hot wire foam cutter",
     "help": "Heated wire for cutting foam. Power is capped and a timer switches it off."},
    {"id": "NEEDLE", "category": "subtractive", "behaviour": "POWERED", "label": "Needle / vibrating knife",
     "help": "Oscillating needle or knife driven by a PWM output."},
    {"id": "POWERED", "category": "subtractive", "behaviour": "POWERED", "label": "Other powered cutter",
     "help": "Any other cutting tool driven by a PWM power output."},
    {"id": "BLADE", "category": "subtractive", "behaviour": "PASSIVE", "label": "Unpowered blade or knife",
     "help": "Cuts by moving through the material: a drag or tangential blade with no power."},
    {"id": "PASSIVE", "category": "passive", "behaviour": "PASSIVE", "label": "Passive tool (pen, probe, holder)",
     "help": "No power output: a pen, probe, camera or holder. Only needs its offsets and feed rate."},
]
BUILTIN_KIND_IDS = {k["id"] for k in DEFAULT_KINDS}
DEFAULT_MATERIALS = {
    "additive": ["PLA", "PETG", "ABS", "ASA", "TPU", "NYLON", "PC", "PASTE", "GLUE"],
    "subtractive": ["PLYWOOD", "MDF", "HARDWOOD", "ACRYLIC", "LEATHER", "CARDSTOCK", "VINYL", "FABRIC",
                    "FOAM_EPS", "FOAM_XPS", "ALUMINIUM", "PCB"],
    "passive": ["PAPER", "CARD", "DEFAULT"],
}
DEFAULT_NOZZLES = [0.2, 0.25, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2]
DEFAULT_HW_CATEGORIES = [
    {"id": "cooling", "label": "Fans and cooling"}, {"id": "lighting", "label": "Lighting"},
    {"id": "heating", "label": "Heating"}, {"id": "air", "label": "Air and vacuum"},
    {"id": "sensors", "label": "Sensors and switches"}, {"id": "safety", "label": "Safety"},
    {"id": "other", "label": "Other"},
]
_ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def _builtin_presets(k):
    """Fill a kind with its starting values (cap, on-time, checklist, materials)."""
    k = copy.deepcopy(k)
    pre = POWER_PRESETS.get(k["id"]) or (POWER_PRESETS["POWERED"] if k["behaviour"] == "POWERED" else None)
    if k["behaviour"] == "POWERED":
        k.setdefault("cap", pre["cap"])
        k.setdefault("max_on_s", pre["max_on_s"])
        k.setdefault("materials", copy.deepcopy(pre["materials"]))
        k.setdefault("checklist", list(pre["checklist"]))
    elif k["behaviour"] == "PASSIVE":
        k.setdefault("materials", copy.deepcopy(PASSIVE_PRESET["materials"]))
        k.setdefault("checklist", list(PASSIVE_PRESET["checklist"]))
    k.setdefault("help", "")
    return k


def defaults():
    return {"version": 1, "kinds": [_builtin_presets(k) for k in DEFAULT_KINDS],
            "materials": copy.deepcopy(DEFAULT_MATERIALS), "nozzles": list(DEFAULT_NOZZLES),
            "hw_categories": copy.deepcopy(DEFAULT_HW_CATEGORIES)}


def load(paths):
    d = defaults()
    p = paths.lists_json
    if not os.path.exists(p):
        return d
    try:
        with open(p, encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as e:
        raise Fail(f"{p} is unreadable: {e}")
    for key in ("kinds", "materials", "nozzles", "hw_categories"):
        if key in saved:
            d[key] = saved[key]
    have = {k["id"] for k in d["kinds"]}               # a built-in kind can never go missing
    for k in DEFAULT_KINDS:
        if k["id"] not in have:
            d["kinds"].append(_builtin_presets(k))
    d["kinds"] = [_builtin_presets(k) for k in d["kinds"]]
    return d


def kinds_by_id(lists):
    return {k["id"]: k for k in lists["kinds"]}


def kind_type(lists, kind_id):
    """'HOT_WIRE' -> 'POWERED' (the type the Klipper macros dispatch on), None if unknown."""
    k = kinds_by_id(lists).get(kind_id)
    return BEHAVIOUR_TYPE[k["behaviour"]] if k else None


# ----------------------------------------------------------------------------- validation
def _text(v, label, maxlen):
    s = " ".join(str(v or "").split())
    if len(s) > maxlen:
        raise Fail(f"{label} is too long (max {maxlen} characters)")
    if not SAFE_TEXT.match(s):
        raise Fail(f"{label} may only contain {SAFE_TEXT_HELP}")
    return s


def _num(v, label, lo, hi, integer=False):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Fail(f"{label} must be a number")
    if not (lo <= x <= hi):
        raise Fail(f"{label} must be between {lo:g} and {hi:g}")
    return int(round(x)) if integer else x


def _clean_kind(raw, old):
    label = _text(raw.get("label"), "Sub-type name", 60)
    if not label:
        raise Fail("Every sub-type needs a name")
    kid = str(raw.get("id") or "").strip().upper() or re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")[:24]
    if not KIND_ID_RE.match(kid):
        kid = "KIND_" + kid[:18] if kid else "KIND"
    cat = raw.get("category")
    if cat not in CATEGORIES:
        raise Fail(f"{label}: choose Additive, Subtractive or Passive")
    beh = raw.get("behaviour")
    if old is not None:                               # what a kind does cannot change once it exists
        beh = old["behaviour"]
    if beh not in BEHAVIOURS:
        raise Fail(f"{label}: choose what the tool needs")
    if beh not in CATEGORY_BEHAVIOURS[cat]:
        raise Fail(f"{label}: a {CATEGORIES[cat].lower()} tool cannot be '{BEHAVIOURS[beh]}'")
    k = {"id": kid, "category": cat, "behaviour": beh, "label": label, "help": " ".join(str(raw.get("help") or "").split())[:200]}
    if beh in ("POWERED", "PASSIVE"):
        items = raw.get("checklist") or []
        items = items.splitlines() if isinstance(items, str) else list(items)
        items = [_text(i, "checklist item", MAX_CHECKLIST_LEN) for i in items if str(i).strip()]
        if len(items) > MAX_CHECKLIST_ITEMS:
            raise Fail(f"{label}: at most {MAX_CHECKLIST_ITEMS} checklist items")
        k["checklist"] = items
        mats = {}
        for name, m in (raw.get("materials") or {}).items():
            if not MAT_RE.match(str(name)):
                raise Fail(f"{label}: material name {name!r} must be letters, digits or _")
            entry = {"feed_rate": _num(m.get("feed_rate", 600), f"{label} {name} feed rate", *LIMITS["feed_rate"])}
            if beh == "POWERED":
                entry["power"] = _num(m.get("power", 0.5), f"{label} {name} power", *LIMITS["power"])
            mats[name] = entry
        k["materials"] = mats or ({"DEFAULT": {"power": 0.5, "feed_rate": 600}} if beh == "POWERED" else {"DEFAULT": {"feed_rate": 800}})
    if beh == "POWERED":
        k["cap"] = _num(raw.get("cap", 1.0), f"{label} power cap", *LIMITS["cap"])
        k["max_on_s"] = _num(raw.get("max_on_s", 300), f"{label} maximum on-time", *LIMITS["max_on_s"], integer=True)
    return k


def _names(v, label, maxn=60):
    items = v.split(",") if isinstance(v, str) else list(v or [])
    out = []
    for i in items:
        n = str(i).strip().upper().replace(" ", "_")
        if not n:
            continue
        if not MAT_RE.match(n):
            raise Fail(f"{label}: {n!r} must be letters, digits or _ (max 32)")
        if n not in out:
            out.append(n)
    if len(out) > maxn:
        raise Fail(f"{label}: at most {maxn}")
    return out


def save(paths, body, in_use):
    """body: any of kinds / materials / nozzles / hw_categories. in_use: {"kinds": {id: [tool names]},
    "hw_categories": {id: [hardware names]}} - those cannot be deleted. Returns the saved lists."""
    cur = load(paths)
    out = copy.deepcopy(cur)
    if "kinds" in body:
        old = kinds_by_id(cur)
        kinds, seen = [], set()
        for raw in body["kinds"] or []:
            k = _clean_kind(raw, old.get(str(raw.get("id") or "").upper()))
            if k["id"] in seen:
                k["id"] = (k["id"][:20] + "_" + str(len(seen)))[:24]
            seen.add(k["id"])
            kinds.append(k)
        gone = [i for i in old if i not in seen]
        for i in gone:
            if i in BUILTIN_KIND_IDS:
                raise Fail(f"{old[i]['label']} is built in - rename it instead of deleting it")
            if in_use.get("kinds", {}).get(i):
                raise Fail(f"{old[i]['label']} is used by {', '.join(in_use['kinds'][i])} - change those tools first")
        if not any(k["category"] == c for k in kinds for c in CATEGORIES):
            raise Fail("Keep at least one sub-type")
        out["kinds"] = kinds
    if "materials" in body:
        m = body["materials"] or {}
        out["materials"] = {c: _names(m.get(c, []), f"{CATEGORIES[c]} materials") for c in CATEGORIES}
    if "nozzles" in body:
        raw = body["nozzles"]
        items = raw.split(",") if isinstance(raw, str) else list(raw or [])
        sizes = sorted({round(_num(x, "Nozzle size", *LIMITS["nozzle"]), 3) for x in items if str(x).strip()})
        if not sizes:
            raise Fail("Keep at least one nozzle size")
        out["nozzles"] = sizes
    if "hw_categories" in body:
        cats, seen = [], set()
        for raw in body["hw_categories"] or []:
            label = _text(raw.get("label"), "Category name", 40)
            if not label:
                continue
            cid = str(raw.get("id") or "").strip() or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:32]
            if not _ID.match(cid) or cid in seen:
                cid = f"cat_{len(seen) + 1}"
            seen.add(cid)
            cats.append({"id": cid, "label": label})
        for c in cur["hw_categories"]:
            if c["id"] not in seen and in_use.get("hw_categories", {}).get(c["id"]):
                raise Fail(f"{c['label']} still has hardware: {', '.join(in_use['hw_categories'][c['id']])}")
        if not cats:
            raise Fail("Keep at least one category")
        out["hw_categories"] = cats
    os.makedirs(os.path.dirname(paths.lists_json), exist_ok=True)
    tmp = paths.lists_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: out[k] for k in ("version", "kinds", "materials", "nozzles", "hw_categories")}, f, indent=1)
    os.replace(tmp, paths.lists_json)
    return out
