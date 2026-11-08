"""A small versioned JSON store, shared by slice profiles (1.8) and your macros (1.9.13).

    myrhino/<name>.json           {"schema": 1, "<key>": [...]}
    myrhino/<name>.history.json   {"schema": 1, "revisions": {id: [old, ...]}, "deleted": [...]}

Rules (moved here unchanged from slice_profiles.py):
- Every save carries the rev it started from; a stale rev is refused (another device changed it).
- Each item is checked by its kind's `clean` on every save and import, before anything is written.
- A file that exists but can't be read is never overwritten: saves are refused until it's fixed.
- The last KEEP_REVISIONS revisions of each item are kept; a deleted item can be brought back for 30 days.
- Writes are atomic and one at a time.
"""
import copy
import functools
import json
import os
import secrets
import tempfile
import threading
import time

from .errors import Fail

SCHEMA = 1
KEEP_REVISIONS = 5
KEEP_DELETED_S = 30 * 86400


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


class VersionedStore:
    """Subclasses set: NAME (file name stem), KEY (the list's key), PREFIX (id prefix), NOUN / NOUNS (words for
    messages), MAX (how many), LIST_KEYS, DELETED_KEYS, EXPORT_KEY, EXPORT_FIELDS, and clean(raw) -> item."""
    NAME = KEY = PREFIX = NOUN = NOUNS = EXPORT_KEY = ""
    MAX = 200
    LIST_KEYS = DELETED_KEYS = EXPORT_FIELDS = ()

    def __init__(self, paths, now=time.time):
        self.paths, self.now = paths, now
        my = os.path.join(paths.cfg, "myrhino")
        self.file = os.path.join(my, self.NAME + ".json")
        self.hist_file = os.path.join(my, self.NAME + ".history.json")

    def clean(self, raw):
        raise NotImplementedError

    # ---- reading
    def _items(self):
        d, ok = _read(self.file, {"schema": SCHEMA, self.KEY: []})
        if not ok:
            raise Fail(f"myrhino/{self.NAME}.json can't be read, so it's kept as it is. Fix or remove it by hand "
                       "(a backup has the last good copy), then try again.")
        return d

    def _history(self):
        d, ok = _read(self.hist_file, {"schema": SCHEMA, "revisions": {}, "deleted": []})
        if not ok:
            raise Fail(f"myrhino/{self.NAME}.history.json can't be read, so it's kept as it is. Fix or remove it by hand.")
        cut = self.now() - KEEP_DELETED_S
        d["deleted"] = [p for p in d.get("deleted", []) if p.get("deleted_at", 0) >= cut]
        return d

    def state(self, full=False):
        """For a list screen: the items, or why the file can't be read."""
        try:
            return {"ok": True, self.KEY: self.list(full)}
        except Fail as e:
            return {"ok": False, "error": str(e), self.KEY: []}

    def list(self, full=False):
        return [{k: p[k] for k in self.LIST_KEYS} for p in self._items()[self.KEY]]

    def get(self, pid):
        for p in self._items()[self.KEY]:
            if p["id"] == pid:
                return p
        raise Fail(f"That {self.NOUN} isn't on the Rhino (deleted, or never saved)")

    # ---- writing
    def _unique_name(self, items, name, skip=None):
        taken = {p["name"].lower() for p in items if p["id"] != skip}
        if name.lower() not in taken:
            return name
        n = 2
        while f"{name} ({n})".lower() in taken:
            n += 1
        return f"{name} ({n})"[:60]

    @_locked
    def create(self, raw):
        d = self._items()
        if len(d[self.KEY]) >= self.MAX:
            raise Fail(f"The Rhino keeps up to {self.MAX} {self.NOUNS}. Delete some first.")
        p = self.clean(raw)
        p["name"] = self._unique_name(d[self.KEY], p["name"])
        t = int(self.now())
        p.update(id=self.PREFIX + secrets.token_hex(4), created=t, updated=t, rev=1)
        d[self.KEY].append(p)
        _write(self.file, d)
        return p

    @_locked
    def save(self, pid, raw, rev):
        d = self._items()
        h = self._history()
        for i, old in enumerate(d[self.KEY]):
            if old["id"] != pid:
                continue
            if rev != old["rev"]:
                raise Fail(f"{old['name']} was changed on another device (now revision {old['rev']}). Reload it, then save again.")
            p = self.clean(raw)
            if p["name"].lower() != old["name"].lower():
                p["name"] = self._unique_name(d[self.KEY], p["name"], skip=pid)
            p.update(id=pid, created=old["created"], updated=int(self.now()), rev=old["rev"] + 1)
            revs = h["revisions"].setdefault(pid, [])
            revs.insert(0, old)
            del revs[KEEP_REVISIONS:]
            d[self.KEY][i] = p
            _write(self.hist_file, h)
            _write(self.file, d)
            return p
        raise Fail(f"That {self.NOUN} isn't on the Rhino (deleted, or never saved)")

    @_locked
    def delete(self, pid):
        d = self._items()
        h = self._history()
        keep = [p for p in d[self.KEY] if p["id"] != pid]
        if len(keep) == len(d[self.KEY]):
            raise Fail(f"That {self.NOUN} isn't on the Rhino")
        gone = next(p for p in d[self.KEY] if p["id"] == pid)
        h["deleted"].insert(0, dict(gone, deleted_at=int(self.now())))
        d[self.KEY] = keep
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
        return [{k: p.get(k) for k in self.DELETED_KEYS} for p in self._history()["deleted"]]

    @_locked
    def undelete(self, pid):
        h = self._history()
        p = next((x for x in h["deleted"] if x["id"] == pid), None)
        if p is None:
            raise Fail(f"That {self.NOUN} isn't in the deleted list any more")
        d = self._items()
        if any(x["id"] == pid for x in d[self.KEY]):
            raise Fail(f"That {self.NOUN} is already back")
        p = {k: v for k, v in p.items() if k != "deleted_at"}
        p["name"] = self._unique_name(d[self.KEY], p["name"])
        d[self.KEY].append(p)
        h["deleted"] = [x for x in h["deleted"] if x["id"] != pid]
        _write(self.file, d)
        _write(self.hist_file, h)
        return p

    # ---- export / import
    def export(self, pid=None):
        ps = [self.get(pid)] if pid else self._items()[self.KEY]
        return {self.EXPORT_KEY: SCHEMA, "exported": int(self.now()),
                self.KEY: [{k: p[k] for k in self.EXPORT_FIELDS} for p in ps]}

    @_locked
    def import_(self, data):
        """Every item is checked before any is added; a clashing name gets " (2)"."""
        if not isinstance(data, dict) or data.get(self.EXPORT_KEY) != SCHEMA or not isinstance(data.get(self.KEY), list):
            raise Fail(f"That isn't a Rhino {self.NOUNS} export")
        cleaned = []
        for i, p in enumerate(data[self.KEY]):
            try:
                cleaned.append(self.clean(p))
            except Fail as e:
                raise Fail(f"{self.NOUN.capitalize()} {i + 1} in the file: {e}. Nothing was imported.")
        d = self._items()
        if len(d[self.KEY]) + len(cleaned) > self.MAX:
            raise Fail(f"The Rhino keeps up to {self.MAX} {self.NOUNS}; this file would go over")
        t = int(self.now())
        added = []
        for p in cleaned:
            p["name"] = self._unique_name(d[self.KEY], p["name"])
            p.update(id=self.PREFIX + secrets.token_hex(4), created=t, updated=t, rev=1)
            d[self.KEY].append(p)
            added.append({"id": p["id"], "name": p["name"]})
        _write(self.file, d)
        return added
