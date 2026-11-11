"""Tuning results for print heads (1.9.16), the laser and the drag knife (1.9.23): what the tuning wizards in Rhino Studio found. Design:
docs/phase-tuning-wizards.md (after Ellis' Print Tuning Guide).

    myrhino/tuning.json           {"schema": 1, "rev": n, "updated": t, "heads": {...}, "materials": {...}, "runs": [...]}
    myrhino/tuning.history.json   {"schema": 1, "revisions": [old file, ...]}   (newest first)

- heads[tool]: values that belong to the print head itself: rotation_distance (extruder calibration).
- materials["tool|nozzle|material"]: values per head, nozzle and material: pressure_advance, extrusion_multiplier.
- materials["tool|material"]: laser and drag knife values per tool and material (no nozzle): cut and engrave power
  and speed, passes, kerf, knife depth and pressure dial (1.9.23).
- heads[tool] also keeps the laser's focus height and the knife's blade offset (1.9.23).
- materials["tool|bit=<bit>"]: the spindle bit's measured cutting diameter; materials["tool|material|bit=<bit>"]: feed,
  throttle, depth per pass and plunge per bit and material (1.9.26). Bits are the Portal's list (Assets › Parts › Bits).
- runs: every test run, newest first (what the tool page shows as done): tool, nozzle, material, test, value, time.

Every value is {"value", "time", "old"}: what it was before, so the page can show old and new. The file is in the
config folder, so the backup watcher backs it up after every save, and it restores on its own from a backup.

The Portal only stores these. It never talks to Klipper: Studio applies them (a tuned pressure advance and rotation
distance go into each prepared file after START_JOB; the first-layer fine-tune is Klipper's own rhino_zfine_ variable).
"""
import copy
import os
import re
import time

from .errors import Fail
from .versioned_store import SCHEMA, _locked, _read, _write

KEEP_REVISIONS = 10
MAX_RUNS = 300
_TOOL = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
_MATERIAL = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
# test -> (where it's kept: "head", "material" (+ nozzle) or "stock" (material, no nozzle), the value it sets, lowest,
# highest). The laser and knife limits match Studio's src/tuning/cutTests.ts CUT_LIMITS.
TESTS = {
    "extruder_calibration": ("head", "rotation_distance", 0.5, 100.0),
    "first_layer": ("material", "first_layer_fine", -1.0, 1.0),
    "pressure_advance": ("material", "pressure_advance", 0.0, 2.0),
    "extrusion_multiplier": ("material", "extrusion_multiplier", 0.5, 1.5),
    "laser_focus_height": ("head", "laser_focus_height", 1.0, 30.0),
    "laser_cut_power": ("stock", "laser_cut_power", 0.01, 1.0),
    "laser_cut_speed": ("stock", "laser_cut_speed", 30.0, 6000.0),
    "laser_engrave_power": ("stock", "laser_engrave_power", 0.01, 1.0),
    "laser_engrave_speed": ("stock", "laser_engrave_speed", 30.0, 12000.0),
    "laser_passes": ("stock", "laser_passes", 1, 10),
    "laser_kerf": ("stock", "laser_kerf", 0.0, 1.0),
    "knife_depth": ("stock", "knife_depth", 0.01, 3.0),
    "knife_pressure": ("stock", "knife_pressure", 0.0, 1000.0),
    "knife_blade_offset": ("head", "knife_blade_offset", 0.0, 2.0),
    # spindle (1.9.26): "bit" = per tool and bit, "cut" = per tool, material and bit. Studio: cutTests.ts CUT_LIMITS
    "cnc_diameter": ("bit", "cnc_diameter", 0.1, 25.0),
    "cnc_feed": ("cut", "cnc_feed", 10.0, 6000.0),
    "cnc_throttle": ("cut", "cnc_throttle", 0.3, 1.0),
    "cnc_depth": ("cut", "cnc_depth", 0.05, 10.0),
    "cnc_plunge": ("cut", "cnc_plunge", 10.0, 3000.0),
}
EMPTY = {"schema": SCHEMA, "rev": 0, "updated": 0, "heads": {}, "materials": {}, "runs": []}


def material_key(tool, nozzle, material):
    return f"{tool}|{nozzle:g}|{material}"


def stock_key(tool, material):
    return f"{tool}|{material}"


def bit_key(tool, bit, material=None):
    """The spindle's keys: "tool|bit=<bit>", or "tool|<material>|bit=<bit>" (never mistaken for a nozzle key)."""
    return f"{tool}|bit={bit}" if material is None else f"{tool}|{material}|bit={bit}"


class Tuning:
    def __init__(self, paths, now=time.time):
        self.paths, self.now = paths, now
        my = os.path.join(paths.cfg, "myrhino")
        self.file = os.path.join(my, "tuning.json")
        self.hist_file = os.path.join(my, "tuning.history.json")

    def _load(self):
        d, ok = _read(self.file, EMPTY)
        if not ok:
            raise Fail("myrhino/tuning.json can't be read, so it's kept as it is. Fix or remove it by hand "
                       "(a backup has the last good copy), then try again.")
        return d

    def state(self):
        try:
            return {"ok": True, **self._load()}
        except Fail as e:
            return {"ok": False, "error": str(e), **copy.deepcopy(EMPTY)}

    @_locked
    def save_result(self, raw):
        """{"rev", "tool", "nozzle", "material", "bit", "test", "value"}: keep a test's result. A stale rev is refused."""
        if not isinstance(raw, dict):
            raise Fail("Expected a tuning result")
        d = self._load()
        rev = raw.get("rev")
        if isinstance(rev, bool) or rev != d["rev"]:
            raise Fail(f"Tuning was changed on another screen (now revision {d['rev']}). Reload, then save again.")
        test = raw.get("test")
        if test not in TESTS:
            raise Fail("Unknown tuning test")
        where, key, lo, hi = TESTS[test]
        tool = raw.get("tool")
        if not isinstance(tool, str) or not _TOOL.match(tool):
            raise Fail("Which tool?")
        v = raw.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
            raise Fail(f"{key.replace('_', ' ')} must be from {lo:g} to {hi:g}")
        v = round(float(v), 6)
        nozzle = material = None
        if where == "material":
            nozzle = raw.get("nozzle")
            if isinstance(nozzle, bool) or not isinstance(nozzle, (int, float)) or not 0.1 <= nozzle <= 2.0:
                raise Fail("Which nozzle size (0.1 to 2 mm)?")
        if where in ("material", "stock"):
            material = raw.get("material")
            if not isinstance(material, str) or not _MATERIAL.match(material):
                raise Fail("Which material?")
        bit = None
        if where in ("bit", "cut"):
            bit = raw.get("bit")
            if not isinstance(bit, str) or not _MATERIAL.match(bit):
                raise Fail("Which bit?")
        if where == "cut":
            material = raw.get("material")
            if not isinstance(material, str) or not _MATERIAL.match(material):
                raise Fail("Which material?")
        t = int(self.now())
        new = copy.deepcopy(d)
        if where == "head":
            slot = new["heads"].setdefault(tool, {})
        elif where == "stock":
            slot = new["materials"].setdefault(stock_key(tool, material), {})
        elif where in ("bit", "cut"):
            slot = new["materials"].setdefault(bit_key(tool, bit, material), {})
        else:
            slot = new["materials"].setdefault(material_key(tool, float(nozzle), material), {})
        old = slot.get(key, {}).get("value")
        slot[key] = {"value": v, "time": t, "old": old}
        run = {"tool": tool, "test": test, "value": v, "time": t}
        if where == "material":
            run.update(nozzle=float(nozzle), material=material)
        elif where == "stock":
            run.update(material=material)
        elif where == "bit":
            run.update(bit=bit)
        elif where == "cut":
            run.update(bit=bit, material=material)
        new["runs"] = ([run] + new["runs"])[:MAX_RUNS]
        new.update(rev=d["rev"] + 1, updated=t)
        self._keep_history(d)
        _write(self.file, new)
        return new

    @_locked
    def clear(self, raw):
        """Forget one value (the job goes back to the Rhino's default): {"rev", "tool", "test", "nozzle"?, "material"?}"""
        d = self._load()
        if raw.get("rev") != d["rev"]:
            raise Fail(f"Tuning was changed on another screen (now revision {d['rev']}). Reload, then try again.")
        test = raw.get("test")
        if test not in TESTS:
            raise Fail("Unknown tuning test")
        where, key, _, _ = TESTS[test]
        new = copy.deepcopy(d)
        tool = str(raw.get("tool", ""))
        if where == "head":
            slot = new["heads"].get(tool)
        elif where == "stock":
            slot = new["materials"].get(stock_key(tool, str(raw.get("material", ""))))
        elif where in ("bit", "cut"):
            slot = new["materials"].get(bit_key(tool, str(raw.get("bit", "")), str(raw.get("material", "")) if where == "cut" else None))
        else:
            slot = new["materials"].get(material_key(tool, float(raw.get("nozzle") or 0), str(raw.get("material", ""))))
        if not slot or key not in slot:
            raise Fail("Nothing tuned there to forget")
        del slot[key]
        new.update(rev=d["rev"] + 1, updated=int(self.now()))
        self._keep_history(d)
        _write(self.file, new)
        return new

    def _keep_history(self, d):
        if not d["rev"]:
            return
        h, ok = _read(self.hist_file, {"schema": SCHEMA, "revisions": []})
        if not ok:
            raise Fail("myrhino/tuning.history.json can't be read, so it's kept as it is. Fix or remove it by hand.")
        h["revisions"].insert(0, d)
        del h["revisions"][KEEP_REVISIONS:]
        _write(self.hist_file, h)
