#!/usr/bin/env python3
"""Rhino updater (1.5.3): installs a Rhino Tool Manager release zip that Rhino Studio uploaded.

Installed root-owned as /usr/local/sbin/rhino-update by install.sh, and started only by
systemd: rhino-update.path watches <drop>/request, rhino-update.service runs this once.
The Portal never gets sudo (its service keeps NoNewPrivileges); it only drops a zip and a
request file in its own folder (~/printer_data/rhino_data/update) and reads status.json.

What a run does, stopping at the first problem:
  1. take the request (and delete it, so the path unit doesn't fire again)
  2. copy the zip into a root-owned work folder and check it there (never trust the drop folder)
  3. refuse while a job prints or is paused (asks Moonraker)
  4. BACKUP_CFG, if Klipper has that macro (your config backup to GitHub); a failure only warns
  5. unpack, then run install.sh --unattended as root for the login that owns the Rhino
     (install.sh backs up the config folder first; menu option 4 undoes it, as always)
  6. copy the menu to ~/rhino-manager, record the installed version
  7. FIRMWARE_RESTART so Klipper loads the new config
The zip that was installed and the one before are kept, so Studio can offer "Go back".

Safety: everything read from the drop folder is opened without following links; status.json
is written through a temp file and renamed (a link planted there is replaced, never written
through). Only zips that look like a Rhino release are installed.
"""
import argparse
import datetime
import fcntl
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ZIP_RE = re.compile(r"^rhino-config-(\d+\.\d+\.\d+)\.zip$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_ZIP = 100 * 1024 * 1024
MAX_UNPACKED = 400 * 1024 * 1024
MAX_MEMBERS = 20000
REQUIRED = ("VERSION", "install.sh", "rhino.sh", "uninstall.sh", "rhino/__init__.py", "scripts/rhino_portal.py")
WORK = "/var/lib/rhino-update"
KEEP_ZIPS = 2
STEPS = ["Checking the zip", "Checking no job runs", "Backing up the config (BACKUP_CFG)", "Unpacking",
         "Installing", "Restarting Klipper (FIRMWARE_RESTART)"]


# ---------------------------------------------------------------- checking a zip (the Portal uses this too)
def check_zip(path):
    """Return the zip's version, or raise ValueError saying what's wrong. Reads names and VERSION only."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        raise ValueError("The zip isn't there.")
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("That isn't a plain file.")
    if st.st_size > MAX_ZIP:
        raise ValueError(f"The zip is too big ({st.st_size // (1024 * 1024)} MB; a release is a few MB).")
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("That isn't a zip file.")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("The zip has too many files to be a Rhino release.")
        total = 0
        names = set()
        for i in infos:
            n = i.filename
            if n.startswith("/") or "\\" in n or ".." in n.split("/") or re.match(r"^[A-Za-z]:", n):
                raise ValueError(f"The zip has a file outside its folder ({n}).")
            mode = (i.external_attr >> 16) & 0o170000
            if mode and mode not in (stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"The zip has a link or special file ({n}).")
            total += i.file_size
            names.add(n.rstrip("/"))
        if total > MAX_UNPACKED:
            raise ValueError("The zip unpacks too large to be a Rhino release.")
        missing = [r for r in REQUIRED if r not in names]
        if missing:
            raise ValueError("This isn't a Rhino Tool Manager release zip (missing " + ", ".join(missing) + ").")
        version = z.read("VERSION").decode("utf-8", "replace").strip()
        if not VERSION_RE.match(version):
            raise ValueError("The zip's VERSION isn't a version number.")
        init = z.read("rhino/__init__.py").decode("utf-8", "replace")
        m = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M)
        if not m or m.group(1) != version:
            raise ValueError("The zip's VERSION and its code don't agree; build it again with dev/make_zip.sh.")
    return version


def version_key(v):
    return tuple(int(x) for x in v.split("."))


# ---------------------------------------------------------------- the run
class Run:
    def __init__(self, user, drop, moonraker):
        self.pw = pwd.getpwnam(user)
        self.user, self.home = user, self.pw.pw_dir
        self.drop = os.path.realpath(drop)
        if not self.drop.startswith(self.home + "/"):
            raise SystemExit(f"The drop folder must be inside {self.home}")
        self.incoming = os.path.join(self.drop, "incoming")
        self.moonraker = moonraker.rstrip("/")
        self.status = {"state": "idle"}
        self.log = []

    # -- status.json: temp file + rename, owned by the login so the Portal can read and clean it
    def save(self, **kw):
        self.status.update(kw)
        self.status["log"] = self.log[-60:]
        self.status["updated"] = time.time()
        fd, tmp = tempfile.mkstemp(dir=self.drop, prefix=".status-")
        with os.fdopen(fd, "w") as f:
            json.dump(self.status, f)
        os.chown(tmp, self.pw.pw_uid, self.pw.pw_gid)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(self.drop, "status.json"))

    def say(self, line):
        self.log.extend(str(line).rstrip("\n").split("\n"))
        self.save()

    def step(self, i):
        self.save(step=i, step_name=STEPS[i])

    def fail(self, msg):
        self.save(state="failed", error=msg, finished=time.time())
        raise SystemExit(1)

    def read_request(self):
        p = os.path.join(self.drop, "request.json")
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return None
        try:
            with os.fdopen(fd) as f:
                req = json.load(f)
        except ValueError:
            req = None
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass
        return req if isinstance(req, dict) else None

    def moon(self, path, method="GET", timeout=10):
        req = urllib.request.Request(self.moonraker + path, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("result")

    def job_state(self):
        try:
            return self.moon("/printer/objects/query?print_stats")["status"]["print_stats"]["state"]
        except Exception:
            return None

    def has_macro(self, name):
        try:
            objs = self.moon("/printer/objects/list")["objects"]
            return f"gcode_macro {name}" in objs or f"gcode_macro {name.lower()}" in objs
        except Exception:
            return False

    def as_user(self, *paths):
        for p in paths:
            if p and os.path.lexists(p):
                subprocess.run(["chown", "-R", "--no-dereference", f"{self.user}:{self.pw.pw_gid}", p], check=False)

    def installed_version(self):
        try:
            with open(os.path.join(self.home, "rhino-manager", "installed-version")) as f:
                return f.read().strip()
        except OSError:
            return None

    def go(self, req):
        name = str(req.get("zip", ""))
        m = ZIP_RE.match(name)
        if not m:
            self.fail("No zip named in the request.")
        before = self.installed_version()
        self.save(state="running", zip=name, version=m.group(1), from_version=before, started=time.time(),
                  error=None, finished=None, steps=STEPS, step=0)

        # 1. copy into a root-owned folder, then check the copy
        self.step(0)
        os.makedirs(WORK, mode=0o700, exist_ok=True)
        work = tempfile.mkdtemp(dir=WORK, prefix="run-")
        src = os.path.join(self.incoming, name)
        try:
            fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            self.fail(f"{name} isn't in the update folder any more. Upload it again.")
        copy = os.path.join(work, name)
        with os.fdopen(fd, "rb") as fin, open(copy, "wb") as fout:
            shutil.copyfileobj(fin, fout, 1024 * 1024)
        try:
            version = check_zip(copy)
        except ValueError as e:
            self.fail(str(e))
        if version != m.group(1):
            self.fail("The file name and the zip's VERSION don't agree.")
        self.say(f"Zip checked: Rhino Tool Manager {version}")

        # 2. no job
        self.step(1)
        state = self.job_state()
        if state in ("printing", "paused"):
            self.fail(f"A job is {state}. Finish or cancel it first, then install.")
        self.say(f"No job running ({state or 'Moonraker did not answer; install.sh checks again'})")

        # 3. BACKUP_CFG (best effort)
        self.step(2)
        if self.has_macro("BACKUP_CFG"):
            try:
                self.moon("/printer/gcode/script?script=" + urllib.parse.quote("BACKUP_CFG"), "POST", timeout=180)
                self.say("BACKUP_CFG done")
            except Exception as e:
                self.say(f"note BACKUP_CFG did not finish ({e}); install.sh still backs up the config folder")
        else:
            self.say("note no BACKUP_CFG macro; install.sh still backs up the config folder")

        # 4. unpack into the work folder (root-owned)
        self.step(3)
        dest = os.path.join(work, f"rhino-{version}")
        with zipfile.ZipFile(copy) as z:
            z.extractall(dest)
        for root, dirs, files in os.walk(dest):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                p = os.path.join(root, f)
                os.chmod(p, 0o755 if f.endswith((".sh", ".py")) else 0o644)
        os.chmod(work, 0o755)  # the login reads it during the install (sudo -u checks)
        self.say(f"Unpacked to {dest}")

        # 5. install.sh, unattended, as root for the login
        self.step(4)
        env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "RHINO_USER": self.user,
               "HOME": self.home, "USER": self.user, "LOGNAME": self.user, "LANG": "C.UTF-8", "TERM": "dumb"}
        logpath = os.path.join(self.drop, f"install-{version}.log")
        p = subprocess.Popen(["bash", os.path.join(dest, "install.sh"), "--unattended"], cwd=dest, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        with open(logpath, "w") as lf:
            for line in p.stdout:
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                lf.write(clean)
                if clean.strip():
                    self.say(clean)
        rc = p.wait()
        self.as_user(logpath)
        if rc != 0:
            self.fail(f"install.sh stopped (code {rc}). Your config folder is as the install left it; "
                      "the last lines above say why. Undo with rhino.sh option 4.")

        # 6. the menu and the installed version, as rhino.sh option 2 does
        mgr = os.path.join(self.home, "rhino-manager")
        os.makedirs(mgr, exist_ok=True)
        for f in ("rhino.sh", "install.sh", "uninstall.sh"):
            shutil.copy2(os.path.join(dest, f), os.path.join(mgr, f))
        with open(os.path.join(mgr, "installed-version"), "w") as f:
            f.write(version + "\n")
        self.as_user(mgr)
        self.say(f"Installed version {version}")

        # 7. FIRMWARE_RESTART
        self.step(5)
        try:
            self.moon("/printer/firmware_restart", "POST", timeout=30)
            self.say("FIRMWARE_RESTART sent")
        except Exception as e:
            self.say(f"note FIRMWARE_RESTART did not go ({e}); run it from Studio, Settings > Host")

        # keep this zip and the one that was installed before it (for "Go back"); drop the rest
        keep = {name} | ({f"rhino-config-{before}.zip"} if before else set())
        for z in os.listdir(self.incoming):
            if ZIP_RE.match(z) and z not in keep:
                try:
                    os.unlink(os.path.join(self.incoming, z))
                except OSError:
                    pass
        shutil.rmtree(work, ignore_errors=True)
        self.save(state="done", finished=time.time(), step=len(STEPS))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--user", required=True)
    ap.add_argument("--drop", required=True)
    ap.add_argument("--moonraker", default="http://127.0.0.1:7125")
    ap.add_argument("--check", metavar="ZIP", help="only check a zip and print its version")
    a = ap.parse_args()
    if a.check:
        try:
            print(check_zip(a.check))
            return 0
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
    if os.geteuid() != 0:
        print("rhino-update runs as root, started by rhino-update.path", file=sys.stderr)
        return 1
    r = Run(a.user, a.drop, a.moonraker)
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    with open(os.path.join(WORK, "lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0  # one already running; it will see nothing new
        req = r.read_request()
        if not req:
            return 0
        try:
            r.go(req)
        except SystemExit:
            pass
        except Exception as e:  # anything unexpected still ends in a readable status
            r.save(state="failed", error=f"Updater error: {e}", finished=time.time(),
                   when=datetime.datetime.now().isoformat(timespec="seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
