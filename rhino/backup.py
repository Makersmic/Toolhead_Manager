"""Back up now (Tool Manager 1.7, Phase 2 of docs/phase0-spine.md; spec docs/phase2-backup.md).

One archive holds everything a person would be upset to lose (INV-B1), in
~/rhino-backups/rhino_studio_os-<YYYYMMDD-HHMMSS>.zip (1.8.1; older ones are rhino-<host>-<date>.zip), OUTSIDE the config folder so klipper-backup
never pushes archives to GitHub:

    config/                     printer_data/config (everything but .git)
    moonraker/moonraker-sql.db  Moonraker's whole database, copied by Moonraker itself
    moonraker/history.json      every job, readable (Moonraker has no history import)
    moonraker/namespaces/*.json every database namespace, readable (partial restore of Studio settings)
    images/                     rhino_data/images (toolhead photos)
    manifest.json               versions, host, time, reason, and path + size + sha256 of every file

INV-B4: an archive is complete or refused. Anything that should go in and can't be read deletes the
whole archive and the error names it. INV-B5: what goes in is INVENTORY below, which mirrors
the "Backup inventory" table in docs/phase0-spine.md (dev/test_backup.py checks they agree).

Never during a job: Moonraker refuses its database backup and restore while printing, and so does this.
The last KEEP archives are kept; older ones are deleted after each new one.

Restore:
  item  one of ITEMS, after a backup of how things are now. Shown first with plan().
  full  idle only, typed host name, a backup first, stops before changing anything if a [mcu]
        serial path in the archive does not exist on this host (a different machine).
"""
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import zipfile

from . import __version__, pending
from .errors import Fail
from .moonraker import BUSY_STATES

KEEP = 10
NAME_RE = re.compile(r"^rhino[-_][A-Za-z0-9._-]{1,80}\.zip$")   # rhino_studio_os-<date>.zip, and older rhino-<host>-<date>.zip
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
ARCHIVE_PREFIX = "rhino_studio_os"     # Mike, 2026-10-25: no host name (the Pi's was mainsailos); the manifest still records the host
SKIP_FILES = re.compile(r"(\.part|\.tmp|\.swp)$")
# 1.8.2: zips in the config folder are installer uploads (every release is on GitHub; klipper-backup skips *.zip
# too), and the manual PDF comes with every install. They made each backup ~130 MB on Mike's Pi.
SKIP_REDERIVABLE = re.compile(r"(\.zip$|^manual/[^/]+\.pdf$)", re.I)

# id -> what it is. Mirrors docs/phase0-spine.md § Backup inventory (rows marked ✅ under "Should be").
INVENTORY = {
    "config": "Klipper config, macros, materials, tool registry, lists, umbilical, maintenance, meshes, variables.save",
    "moonraker_db": "Moonraker database: job history and totals, Studio settings, mesh_seen, Mainsail settings",
    "history": "job history as readable JSON",
    "namespaces": "every Moonraker database namespace as readable JSON",
    "images": "toolhead photos (rhino_data/images)",
}
# inventory table row (its first cell) -> INVENTORY id. dev/test_backup.py fails if a ✅ row has no entry.
DOC_ROWS = {
    "printer.cfg, macros, myrhino/*.cfg": "config",
    "Materials table": "config",
    "Tool registry, lists, umbilical": "config",
    "Maintenance tasks/history/meters": "config",
    "Saved bed meshes": "config",
    "Mesh records, tool state": "config",
    "moonraker.conf": "config",
    "**Job history**": "moonraker_db",
    "**Studio settings, `mesh_seen`**": "namespaces",
    "**Slice settings per file**": "config",       # Phase 1: profiles in config/myrhino, per-file jobs in prepare/
    "Toolhead photos": "images",
}

# Tool Manager's own program files live in the config folder too. They are backed up (a full record) but a
# full restore leaves them as installed: restoring an old backup must not roll the program back.
PROGRAM_DIRS = ("config/rhino/", "config/scripts/", "config/dev/", "config/service/", "config/studio/", "config/manual/")
PROGRAM_FILES = {"config/VERSION", "config/install.sh", "config/uninstall.sh", "config/rhino.sh", "config/requirements.txt",
                 "config/README.md", "config/CHANGES.md", "config/Prompt.md", "config/slicer.md"}


def is_program(arc):
    return arc.startswith(PROGRAM_DIRS) or arc in PROGRAM_FILES


# Partial restore. Files are archive paths under config/; "namespace" is a Moonraker namespace.
ITEMS = {
    "maintenance": {"label": "Maintenance (tasks, work log, meters)", "prefix": "config/myrhino/maintenance/"},
    "tools": {"label": "Tool registry, lists and umbilical",
              "files": ["config/myrhino/custom_tools.json", "config/myrhino/custom_tools.cfg",
                        "config/myrhino/portal_lists.json", "config/myrhino/umbilical.json",
                        "config/myrhino/job_hooks.json", "config/myrhino/job_hooks.history.json", "config/myrhino/job_hooks.cfg"]},
    "studio": {"label": "Rhino Studio settings", "namespace": "rhino_studio"},
    "images": {"label": "Toolhead photos", "prefix": "images/"},
    "profiles": {"label": "Slice profiles and saved Prepare jobs",
                 "files": ["config/myrhino/slice_profiles.json", "config/myrhino/slice_profiles.history.json",
                           "prepare/prepare_jobs.json"]},
    "macros": {"label": "Your macros", "files": ["config/myrhino/user_macros.json", "config/myrhino/user_macros.history.json"]},
}


def _sha(b):
    return hashlib.sha256(b).hexdigest()



KB_WORK_FOLDER = "config_backup"  # klipper-backup's working copy; its script.sh fixes this name
PUSH_LOCK = ".rhino-push.lock"    # in the home folder; scripts/rhino_backup_watch.sh takes the same one


def _no_secrets(line):
    """Status lines reach Studio, so a token that git printed must not."""
    line = re.sub(r"(https?://)[^/@\s]+@", r"\1", line)
    return re.sub(r"\b(ghp|gho|ghs|ghu|github_pat)_\w+", "[token removed]", line)


def github_status(state_dir, home=None):
    """klipper-backup: installed? .env? and the result of the last push this Portal or BACKUP_CFG ran."""
    home = home or os.path.expanduser("~")
    kb = os.path.join(home, "klipper-backup")
    out = {"installed": os.path.isfile(os.path.join(kb, "script.sh")),
           "env": os.path.isfile(os.path.join(kb, ".env")), "last": None}
    try:
        with open(os.path.join(state_dir, "backup_status.json"), encoding="utf-8") as f:
            out["last"] = json.load(f).get("github")
    except (OSError, ValueError):
        pass
    if not out["installed"]:
        out["state"] = "not_installed"
    elif not out["env"]:
        out["state"] = "no_env"
    elif not out["last"]:
        out["state"] = "never"
    else:
        out["state"] = "ok" if out["last"].get("ok") else "failed"
    return out


class BackupService:
    def __init__(self, paths, moonraker, backup_dir=None, home=None, now=time.time):
        self.paths, self.mr, self.now = paths, moonraker, now
        self.home = home or os.path.expanduser("~")
        self.dir = backup_dir or os.path.join(self.home, "rhino-backups")
        self.printer_data = os.path.dirname(paths.cfg)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _idle(self, what):
        st = self.mr.status()
        if not st.get("online"):
            raise Fail(f"Moonraker isn't answering, so {what} can't include its database. Nothing was changed.")
        if st.get("print_state") in BUSY_STATES:
            raise Fail(f"Not during a job: {what} waits until the job is finished.")
        return st

    def _flock(self):
        os.makedirs(self.dir, exist_ok=True)
        f = open(os.path.join(self.dir, ".lock"), "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            raise Fail("Another backup or restore is running. Try again in a minute.")
        return f

    def _path(self, name):
        if not NAME_RE.match(name or ""):
            raise Fail("That is not a Rhino backup name")
        p = os.path.join(self.dir, name)
        if not os.path.isfile(p):
            raise Fail(f"No backup called {name}")
        return p

    def _config_files(self):
        for root, dirs, files in os.walk(self.paths.cfg):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fn in sorted(files):
                if not SKIP_FILES.search(fn):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, self.paths.cfg).replace(os.sep, "/")
                    if os.path.isfile(full) and not os.path.islink(full) and not SKIP_REDERIVABLE.search(rel):
                        yield full, "config/" + rel

    def _images(self):
        # Photos sit in one folder per tool and pictures in _theme, so this has to look inside folders
        # (until Nov 2026 it only took files at the top, which left every toolhead photo out of the backup)
        d = self.paths.images_dir
        for root, dirs, files in os.walk(d):
            dirs.sort()
            for fn in sorted(files):
                full = os.path.join(root, fn)
                if os.path.isfile(full) and not os.path.islink(full):
                    yield full, "images/" + os.path.relpath(full, d).replace(os.sep, "/")

    # ------------------------------------------------------------------ create
    def create(self, reason="button"):
        """-> the new archive's summary. Raises Fail and keeps nothing if anything is missing (INV-B4)."""
        with self._lock:
            lk = self._flock()
            try:
                self._idle("a backup")
                return self._create(reason)
            finally:
                lk.close()

    def _create(self, reason, protect=None):
        if not os.path.isfile(self.paths.printer_cfg):
            raise Fail("Backup refused: printer.cfg is missing, so this isn't a Rhino config folder. Nothing was kept.")
        cfg_bytes = sum(os.path.getsize(f) for f, _ in self._config_files())
        img_bytes = sum(os.path.getsize(f) for f, _ in self._images())
        need = 3 * (cfg_bytes + img_bytes) + 50 * 1024 * 1024
        if shutil.disk_usage(self.dir).free < need:
            raise Fail(f"Backup refused: the disk needs about {need // (1024 * 1024)} MB free. Nothing was kept.")
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.now()))
        name = f"{ARCHIVE_PREFIX}-{stamp}.zip"
        final = os.path.join(self.dir, name)
        n = 1
        while os.path.exists(final):
            n += 1
            name = f"{ARCHIVE_PREFIX}-{stamp}-{n}.zip"
            final = os.path.join(self.dir, name)
        part = final + ".part"
        files = []
        dbname = f"rhino-{stamp}-{os.getpid()}.db"
        db_path = ""
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
                def put(arc, data):
                    z.writestr(arc, data)
                    files.append({"path": arc, "size": len(data), "sha256": _sha(data)})

                def put_file(full, arc):
                    try:
                        with open(full, "rb") as f:
                            data = f.read()
                    except OSError as e:
                        raise Fail(f"could not read {arc} ({e.strerror})")
                    put(arc, data)

                for full, arc in self._config_files():
                    put_file(full, arc)
                db_path = self.mr.db_backup(dbname)
                if not db_path or not os.path.isfile(db_path):
                    db_path = os.path.join(self.printer_data, "backup", "database", dbname)
                put_file(db_path, "moonraker/moonraker-sql.db")
                put("moonraker/history.json", json.dumps(self.mr.history_all(), indent=1).encode())
                for ns in self.mr.db_namespaces():
                    if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", ns):
                        put(f"moonraker/namespaces/{ns}.json", json.dumps(self.mr.db_get(ns), indent=1).encode())
                for full, arc in self._images():
                    put_file(full, arc)
                jobs = os.path.join(self.paths.state_dir, "prepare_jobs.json")    # Phase 1: saved Prepare jobs
                if os.path.exists(jobs):
                    put_file(jobs, "prepare/prepare_jobs.json")
                manifest = {"format": 1, "tool_manager": __version__, "studio": self._studio_version(),
                            "host": socket.gethostname(), "time": self.now(), "reason": str(reason)[:60],
                            "inventory": sorted(INVENTORY), "files": files}
                z.writestr("manifest.json", json.dumps(manifest, indent=1))
            self._verify(part)
            os.replace(part, final)
        except Fail as e:
            self._drop(part)
            raise Fail(f"Backup refused: {e}. Nothing was kept.")
        except Exception as e:                       # zip or disk trouble: same promise
            self._drop(part)
            raise Fail(f"Backup refused: {e}. Nothing was kept.")
        finally:
            self.mr.db_backup_delete(dbname)
        self.prune(protect={name, protect})
        return self.summary(name)

    def _drop(self, p):
        try:
            os.remove(p)
        except OSError:
            pass

    def _studio_version(self):
        try:
            with open(os.path.join(self.paths.cfg, "studio", "VERSION"), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return None

    # ------------------------------------------------------------------ check, list, prune
    def _verify(self, path):
        """Every file the manifest lists is there with the same hash, and the must-haves are listed.
        -> manifest. Raises Fail naming the first problem."""
        try:
            with zipfile.ZipFile(path) as z:
                try:
                    man = json.loads(z.read("manifest.json"))
                except KeyError:
                    raise Fail("it has no manifest.json")
                names = set(z.namelist())
                listed = {f["path"] for f in man.get("files", [])}
                for must in ("config/printer.cfg", "moonraker/moonraker-sql.db", "moonraker/history.json"):
                    if must not in listed:
                        raise Fail(f"{must} is missing")
                for f in man["files"]:
                    if f["path"] not in names:
                        raise Fail(f"{f['path']} is listed but not in the zip")
                    if _sha(z.read(f["path"])) != f["sha256"]:
                        raise Fail(f"{f['path']} is damaged (checksum differs)")
                return man
        except zipfile.BadZipFile:
            raise Fail("it is not a readable zip")
        except (KeyError, TypeError, ValueError) as e:
            raise Fail(f"its manifest is unreadable ({e})")

    def summary(self, name):
        p = os.path.join(self.dir, name)
        out = {"name": name, "size": os.path.getsize(p), "time": os.path.getmtime(p), "complete": False}
        try:
            with zipfile.ZipFile(p) as z:
                man = json.loads(z.read("manifest.json"))
            out.update(time=man.get("time", out["time"]), host=man.get("host"), reason=man.get("reason"),
                       tool_manager=man.get("tool_manager"), files=len(man.get("files", [])), complete=True)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            pass
        return out

    def list(self):
        if not os.path.isdir(self.dir):
            return []
        names = [n for n in os.listdir(self.dir) if NAME_RE.match(n)]
        return sorted((self.summary(n) for n in names), key=lambda s: s["time"], reverse=True)

    def prune(self, keep=KEEP, protect=()):
        """Keep `keep` archives: the protected ones (the one just made, the one a restore is reading),
        then the newest of the rest. A clock that went backwards can't make a new archive delete itself."""
        protect = {p for p in protect if p}
        rest = [s for s in self.list() if s["name"] not in protect]
        for s in rest[max(0, keep - len(protect)):]:
            self._drop(os.path.join(self.dir, s["name"]))

    def path_for_download(self, name):
        return self._path(name)

    def add_upload(self, filename, data):
        """A backup from another machine (the 7050 move). Checked before it is listed."""
        name = os.path.basename(filename or "")
        if not NAME_RE.match(name):
            raise Fail("Only Rhino backups (rhino_studio_os-<date>.zip, or an older rhino-<name>-<date>.zip) can be added")
        os.makedirs(self.dir, exist_ok=True)
        final = os.path.join(self.dir, name)
        if os.path.exists(final):
            raise Fail(f"{name} is already here")
        part = final + ".part"
        with open(part, "wb") as f:
            f.write(data)
        try:
            self._verify(part)
        except Fail as e:
            self._drop(part)
            raise Fail(f"That backup can't be used: {e}.")
        os.replace(part, final)
        return self.summary(name)

    # ------------------------------------------------------------------ restore
    def _item_files(self, z, item):
        spec = ITEMS[item]
        names = [n for n in z.namelist() if not n.endswith("/")]
        if "prefix" in spec:
            return [n for n in names if n.startswith(spec["prefix"])]
        return [n for n in spec.get("files", []) if n in names]

    def _target(self, arc):
        if arc.startswith("config/"):
            rel = arc[len("config/"):]
            base = self.paths.cfg
        elif arc.startswith("images/"):
            rel = arc[len("images/"):]
            base = self.paths.images_dir
        elif arc == "prepare/prepare_jobs.json":
            rel = "prepare_jobs.json"
            base = self.paths.state_dir
        else:
            raise Fail(f"{arc} has no place to go")
        full = os.path.normpath(os.path.join(base, rel))
        if not full.startswith(os.path.normpath(base) + os.sep):
            raise Fail(f"{arc} points outside its folder")
        return full

    def plan(self, name, item):
        """What a restore would change, before it changes anything. item: one of ITEMS or "all"."""
        if item != "all" and item not in ITEMS:
            raise Fail("Pick what to restore")
        p = self._path(name)
        man = self._verify(p)
        with zipfile.ZipFile(p) as z:
            out = {"archive": name, "item": item, "made": man.get("time"), "host": man.get("host"),
                   "this_host": socket.gethostname(), "add": [], "replace": [], "same": [], "keep": []}
            if item in ITEMS and "namespace" in ITEMS[item]:
                ns = ITEMS[item]["namespace"]
                arc = f"moonraker/namespaces/{ns}.json"
                saved = json.loads(z.read(arc)) if arc in z.namelist() else {}
                try:
                    now = self.mr.db_get(ns) or {}
                except Fail:
                    now = {}
                for k in sorted(set(saved) | set(now)):
                    if k not in now:
                        out["add"].append(k)
                    elif k not in saved:
                        out["keep"].append(k)
                    elif saved[k] != now[k]:
                        out["replace"].append(k)
                    else:
                        out["same"].append(k)
                return out
            arcs = (self._item_files(z, item) if item != "all" else self._all_files(z))
            for arc in arcs:
                full = self._target(arc)
                if not os.path.exists(full):
                    out["add"].append(arc)
                else:
                    with open(full, "rb") as f:
                        (out["same"] if _sha(f.read()) == _sha(z.read(arc)) else out["replace"]).append(arc)
            if item == "all":
                inside = set(arcs)
                out["keep"] = [a for _, a in list(self._config_files()) + list(self._images())
                               if a not in inside and not is_program(a)]
                out["backup_version"], out["installed_version"] = man.get("tool_manager"), __version__
                out["missing_serial"] = self._missing_serial(z)
                out["history_jobs"] = len(json.loads(z.read("moonraker/history.json")))
        return out

    def _all_files(self, z):
        return [n for n in z.namelist() if (n.startswith(("config/", "images/")) or n == "prepare/prepare_jobs.json") and not n.endswith("/") and not is_program(n)]

    def _missing_serial(self, z):
        """[mcu ...] serial: paths in the archive's config that don't exist here (another machine's)."""
        miss = []
        for n in z.namelist():
            if not (n.startswith("config/") and n.endswith(".cfg")):
                continue
            section = ""
            for line in z.read(n).decode("utf-8", "replace").splitlines():
                s = line.split("#", 1)[0].strip()
                m = re.match(r"^\[([^\]]+)\]", s)
                if m:
                    section = m.group(1).strip().lower()
                elif section.startswith("mcu") and re.match(r"^serial\s*[:=]", s):
                    dev = re.split(r"[:=]", s, maxsplit=1)[1].strip()
                    if dev.startswith("/dev/") and not os.path.exists(dev):
                        miss.append({"file": n[len("config/"):], "section": section, "serial": dev})
        return miss

    def _write(self, full, data):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".rhino-restore"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)

    def restore(self, name, item, confirm="", maint=None):
        """item: one of ITEMS, or "all" with confirm == this host's name. A backup of the present state is
        made first; if that is refused, nothing is restored."""
        if item != "all" and item not in ITEMS:
            raise Fail("Pick what to restore")
        with self._lock:
            lk = self._flock()
            try:
                self._idle("a restore")
                p = self._path(name)
                self._verify(p)
                if item == "all":
                    if confirm.strip() != socket.gethostname():
                        raise Fail(f"Type this machine's name ({socket.gethostname()}) to confirm a full restore")
                    with zipfile.ZipFile(p) as z:
                        miss = self._missing_serial(z)
                    if miss:
                        raise Fail("Nothing was restored: this backup's board isn't connected here ("
                                   + ", ".join(f"[{m['section']}] serial {m['serial']}" for m in miss)
                                   + "). Restore it, then fix the serial path, or restore items one by one.")
                try:
                    before = self._create("before restore", protect=name)
                except Fail as e:
                    raise Fail(f"Nothing was restored: I couldn't back up how things are now first ({e})")
                if item == "all":
                    return self._restore_all(p, before, maint)
                return self._restore_item(p, item, before, maint)
            finally:
                lk.close()

    def _restore_item(self, p, item, before, maint):
        spec = ITEMS[item]
        done = []
        with zipfile.ZipFile(p) as z:
            if "namespace" in spec:
                arc = f"moonraker/namespaces/{spec['namespace']}.json"
                saved = json.loads(z.read(arc)) if arc in z.namelist() else {}
                for k, v in (saved or {}).items():
                    self.mr.db_post(spec["namespace"], k, v)
                    done.append(k)
            else:
                lock = maint.lock if (maint and item == "maintenance") else threading.Lock()
                with lock:
                    for arc in self._item_files(z, item):
                        self._write(self._target(arc), z.read(arc))
                        done.append(arc)
                    if maint and item == "maintenance":
                        maint.meters.data = maint.meters._load()
        note = ""
        if item == "tools":
            pending.mark(self.paths, "restored tools from a backup")
            note = "Restart Klipper to use the restored tools."
        return {"ok": True, "item": item, "restored": done, "before": before["name"], "note": note}

    def _restore_all(self, p, before, maint):
        written = []
        with zipfile.ZipFile(p) as z:
            inside = self._all_files(z)
            keep = [a for _, a in list(self._config_files()) + list(self._images()) if a not in set(inside) and not is_program(a)]
            ver = json.loads(z.read("manifest.json")).get("tool_manager")
            lock = maint.lock if maint else threading.Lock()
            with lock:
                for arc in inside:
                    self._write(self._target(arc), z.read(arc))
                    written.append(arc)
                if maint:
                    maint.meters.data = maint.meters._load()
            db = z.read("moonraker/moonraker-sql.db")
        notes = []
        if ver and ver != __version__:
            notes.append(f"This backup was made with Tool Manager {ver}; {__version__} is installed and its program files were kept.")
        try:
            self.mr.restart()
            notes.append("Klipper restarted with the restored config.")
        except Fail as e:
            notes.append(f"Restart Klipper yourself: {e}")
        dbname = f"rhino-restore-{time.strftime('%Y%m%d-%H%M%S')}.db"
        dbdir = os.path.join(self.printer_data, "backup", "database")
        os.makedirs(dbdir, exist_ok=True)
        with open(os.path.join(dbdir, dbname), "wb") as f:
            f.write(db)
        self.mr.db_restore(dbname)
        notes.append("Moonraker restored its database (history, Studio and Mainsail settings) and is restarting.")
        return {"ok": True, "item": "all", "restored": len(written), "kept": keep, "before": before["name"],
                "note": " ".join(notes)}

    # ------------------------------------------------------------------ GitHub (klipper-backup)
    def _push_lock(self, wait):
        """-> the held push lock, or None if it's still taken after wait seconds. scripts/rhino_backup_watch.sh takes the
        same one. The system frees it when the holder exits, however that happens."""
        f = open(os.path.join(self.home, PUSH_LOCK), "a")
        end = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return f
            except OSError:
                if time.monotonic() >= end:
                    f.close()
                    return None
                time.sleep(min(0.5, max(0.01, end - time.monotonic())))

    def record_push(self, res):
        os.makedirs(self.paths.state_dir, exist_ok=True)
        tmp = os.path.join(self.paths.state_dir, "backup_status.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"github": res}, f)
        os.replace(tmp, os.path.join(self.paths.state_dir, "backup_status.json"))

    def push_failed(self, why):
        """Record a push that never ran, so Studio shows the reason (INV-B8)."""
        self.record_push({"ok": False, "code": None, "time": self.now(), "tail": [why]})

    def push_github(self, msg="", timeout=180, lock_wait=200):
        """Run klipper-backup if it's installed and record the result (INV-B8: never claim a push that failed).
        One push at a time: two runs in the same working folder would trip over each other."""
        st = github_status(self.paths.state_dir, self.home)
        if st["state"] in ("not_installed", "no_env"):
            return st
        lock = self._push_lock(lock_wait)
        if lock is None:
            self.push_failed("Another push was still running, so this one didn't start. Back up again in a few minutes.")
            return github_status(self.paths.state_dir, self.home)
        try:
            return self._push(msg, timeout)
        finally:
            lock.close()

    def _push(self, msg, timeout):
        cmd = ["bash", os.path.join(self.home, "klipper-backup", "script.sh")]
        if msg:  # klipper-backup takes the message as --commit_message; a bare argument is refused (its usage error)
            cmd += ["--commit_message", re.sub(r"[^A-Za-z0-9_.:-]", "_", msg)[:60]]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            lines = (r.stdout + r.stderr).strip().splitlines()
            # klipper-backup can exit 0 after git failed, so exit 0 alone proves nothing (Nov 2026: 19 days of false "ok")
            problem = self._push_problem(lines) if r.returncode == 0 else None
            tail = lines[-3:] + ([problem] if problem else [])  # Studio shows the last line, so the reason goes there
            res = {"ok": r.returncode == 0 and not problem, "code": r.returncode, "time": self.now(),
                   "tail": [_no_secrets(line) for line in tail]}
        except (OSError, subprocess.TimeoutExpired) as e:
            res = {"ok": False, "code": None, "time": self.now(), "tail": [str(e)]}
        self.record_push(res)
        return github_status(self.paths.state_dir, self.home)

    def _push_problem(self, lines):
        """Why this push can't be called good, or None. A real push moves the upstream ref to HEAD, so the
        check needs neither the network nor the GitHub token. It reads HEAD's object too, to catch a corrupt copy."""
        for line in lines:
            if line.startswith(("fatal:", "error:")):
                return f"git reported {line}"
        repo = os.path.join(self.home, KB_WORK_FOLDER)
        try:
            head, upstream = (subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", ref],
                                             capture_output=True, text=True, timeout=30)
                              for ref in ("HEAD^{commit}", "@{u}^{commit}"))
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"couldn't check the local backup copy: {e}"
        if head.returncode != 0:
            return "the latest commit in the local backup copy can't be read"
        if upstream.returncode != 0:
            return "the local backup copy has no GitHub branch to compare with"
        if head.stdout.strip() != upstream.stdout.strip():
            return "the latest commit didn't reach GitHub"
        return None

    def clearly_idle(self):
        """True only when Moonraker says no job is running. Not knowing counts as a job: guessing wrong holds a print."""
        st = self.mr.status()
        if not st.get("online") or st.get("print_state") in BUSY_STATES:
            return False
        return not (st.get("klippy") == "ready" and st.get("print_state") == "unknown")

    def claim_after_job(self):
        """-> a held lock while this process waits for the job to end, or None if another one is already waiting."""
        os.makedirs(self.dir, exist_ok=True)
        f = open(os.path.join(self.dir, ".after-job-lock"), "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return None
        return f

    def wait_until_idle(self, poll=30, max_wait=7 * 24 * 3600):
        """For BACKUP_CFG during a job. -> True once the job is over, False if it's still going after max_wait."""
        end = self.now() + max_wait
        while self.now() < end:
            if self.clearly_idle():
                return True
            time.sleep(poll)
        return False
