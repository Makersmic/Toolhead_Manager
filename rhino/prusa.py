"""PrusaSlicer on the Rhino host, for Rhino Studio (config 1.5.0).

Studio sends a part (binary STL, already turned and scaled), the full PrusaSlicer INI and where the
part's centre goes; this runs PrusaSlicer's command line and hands back the G-code. Studio then wraps
it in the Rhino's own start and end lines and checks every line before it reaches Klipper.

Keeping the machine first:
  - one slice at a time (one more may wait); a newer request from Studio cancels the older one
  - lowest CPU and disk priority (nice 19, ionice idle), a thread cap, and a memory watchdog that stops
    the slice before it can starve Klipper or Moonraker of memory
  - while a job prints: small hosts (under 2 GB, e.g. a Pi 3B) refuse to slice at all; bigger ones
    slice with half the cores and a lower memory cap
  - the INI is re-checked here: only known option names, single-line values, and the options that
    could run programs or rewrite G-code (post_process, gcode_substitutions) are forced empty
  - identical requests (same part, settings, engine) come straight from a small cache

The engine lives in <rhino_data>/prusaslicer/<version>/ (an unpacked official AppImage), with
`current` pointing at the one in use and the previous one kept for going back. Installing and
updating come from PrusaSlicer's GitHub releases; Studio shows them under Settings > Software.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid

from .errors import Fail

RELEASES = "https://api.github.com/repos/prusa3d/PrusaSlicer/releases/latest"
SMALL_HOST_MB = 2048
MAX_MODEL = 200 * 1024 * 1024
MAX_INI = 512 * 1024
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
# Forced whatever Studio sends: these run programs or change lines after Studio's checks
FORCED = {"post_process": "", "gcode_substitutions": "", "binary_gcode": "0", "output_filename_format": "{input_filename_base}.gcode",
          "thumbnails": ""}
# Phases PrusaSlicer logs, roughly in order, for a progress bar
PHASES = [("Processing triangulated mesh", 0.05, "Reading the part"), ("Generating perimeters", 0.2, "Walls"),
          ("Preparing infill", 0.45, "Infill"), ("Generating support", 0.6, "Supports"), ("Generating skirt", 0.75, "Skirt and brim"),
          ("Exporting G-code", 0.85, "Writing G-code"), ("Slicing result exported", 1.0, "Done")]


def _meminfo():
    try:
        with open("/proc/meminfo") as f:
            m = dict(l.split(":", 1) for l in f if ":" in l)
        return int(m["MemTotal"].split()[0]) // 1024
    except (OSError, KeyError, ValueError):
        return 1024


def _arch():
    m = platform.machine().lower()
    return "x86_64" if m in ("x86_64", "amd64") else "aarch64" if m in ("aarch64", "arm64") else m


def pick_asset(assets, arch):
    """The official Linux AppImage for this processor (the newer-distros GTK3 build on x86-64)."""
    names = [(a.get("name", ""), a) for a in assets]
    if arch == "x86_64":
        pats = [r"linux-x64-newer-distros-GTK3.*\.AppImage$", r"linux-x64.*GTK3.*\.AppImage$", r"linux-x64.*\.AppImage$"]
    elif arch == "aarch64":
        pats = [r"linux-(armv8|aarch64|arm64).*\.AppImage$"]
    else:
        return None
    for p in pats:
        for n, a in names:
            if re.search(p, n):
                return a
    return None


def clean_ini(text, known):
    """Only `key = value` lines for options the engine knows; forced safety values win."""
    if len(text) > MAX_INI:
        raise Fail("Settings file too big")
    out, seen = [], set()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, sep, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if not sep or not KEY_RE.match(k) or (known and k not in known) or k in FORCED or k in seen:
            continue
        seen.add(k)
        out.append(f"{k} = {v}")
    for k, v in FORCED.items():
        if not known or k in known:
            out.append(f"{k} = {v}")
    return "\n".join(out) + "\n"


class Job:
    def __init__(self, jid, workdir, key):
        self.id, self.dir, self.key = jid, workdir, key
        self.state, self.phase, self.progress, self.error = "queued", "Waiting", None, None
        self.started = time.time()
        self.finished = None
        self.cached = False
        self.proc = None
        self.cancel = False

    def view(self):
        end = self.finished or time.time()
        return {"id": self.id, "state": self.state, "phase": self.phase, "progress": self.progress, "error": self.error,
                "seconds": round(end - self.started, 1), "cached": self.cached}


class PrusaService:
    def __init__(self, base_dir, printer_state=lambda: "standby", run=subprocess.Popen, fetch=None,
                 mem_mb=None, cpus=None, arch=None):
        self.base = base_dir
        self.printer_state = printer_state
        self.Popen = run
        self.fetch = fetch or self._fetch
        self.mem_mb = mem_mb or _meminfo()
        self.cpus = cpus or os.cpu_count() or 1
        self.arch = arch or _arch()
        self.jobs = {}
        self.queue = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.worker = None
        self._latest = {"at": 0, "version": None, "asset": None, "error": None}
        self.installing = False
        self.install_error = None
        os.makedirs(os.path.join(self.base, "jobs"), exist_ok=True)
        os.makedirs(os.path.join(self.base, "cache"), exist_ok=True)

    # ------------------------------------------------------------ engine
    @property
    def small(self):
        return self.mem_mb < SMALL_HOST_MB

    def current_dir(self):
        p = os.path.join(self.base, "current")
        return os.path.realpath(p) if os.path.exists(p) else None

    def installed(self):
        d = self.current_dir()
        try:
            with open(os.path.join(d, "VERSION")) as f:
                return f.read().strip()
        except (OSError, TypeError):
            return None

    def binary(self):
        d = self.current_dir()
        b = os.path.join(d, "squashfs-root", "AppRun") if d else None
        if not b or not os.path.exists(b):
            raise Fail("PrusaSlicer isn't installed on the Rhino yet (Studio: Settings > Software).")
        return b

    def keys(self):
        """Option names the installed engine accepts, from its own --help-fff (cached per version)."""
        d = self.current_dir()
        if not d:
            return []
        cache = os.path.join(d, "keys.json")
        try:
            with open(cache) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
        p = self.Popen([self.binary(), "--help-fff"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out, _ = p.communicate(timeout=60)
        keys = sorted({k.replace("-", "_") for k in re.findall(r"^\s*--([a-z][a-z0-9-]*)", out, re.M)})
        if len(keys) < 50:
            raise Fail("The installed PrusaSlicer didn't list its options; reinstall it from Settings > Software.")
        with open(cache, "w") as f:
            json.dump(keys, f)
        return keys

    def refuse(self):
        """Why a slice can't start right now, or None."""
        if self.small and self.printer_state() in ("printing", "paused"):
            return ("This host has under 2 GB of memory: slicing while a job prints could starve Klipper. "
                    "Slice when the job ends, or use Kiri:Moto in the browser.")
        return None

    def limits(self):
        """(threads, memory cap MB) for a slice now."""
        busy = self.printer_state() in ("printing", "paused")
        if busy:
            return max(1, self.cpus // 2), int(self.mem_mb * 0.4)
        return max(1, self.cpus - 1), max(256, min(int(self.mem_mb * 0.7), self.mem_mb - 768))

    # ------------------------------------------------------------ releases
    def _fetch(self, url, dest=None, timeout=30):
        req = urllib.request.Request(url, headers={"User-Agent": "Rhino-Tool-Manager", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if dest is None:
                return r.read()
            with open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1024 * 1024)
            return dest

    def latest(self, force=False):
        if not force and time.time() - self._latest["at"] < 6 * 3600 and self._latest["version"]:
            return self._latest
        try:
            data = json.loads(self.fetch(RELEASES))
            tag = data.get("tag_name", "")
            ver = re.sub(r"^version_", "", tag)
            asset = pick_asset(data.get("assets", []), self.arch)
            self._latest = {"at": time.time(), "version": ver or None,
                            "asset": {"url": asset["browser_download_url"], "name": asset["name"], "size": asset.get("size"),
                                      "digest": asset.get("digest")} if asset else None, "error": None}
        except Exception as e:  # offline, rate limited
            self._latest = {**self._latest, "at": time.time(), "error": f"Couldn't check GitHub: {e}"}
        return self._latest

    def state(self):
        inst = self.installed()
        lat = self.latest()
        def newer(a, b):
            n = lambda v: [int(x) for x in re.findall(r"\d+", v or "")]
            return bool(a and b and n(b) > n(a))
        return {
            "engine": {"name": "PrusaSlicer", "installed": inst, "latest": lat["version"],
                       "update_available": (not inst and bool(lat["asset"])) or (newer(inst, lat["version"]) and bool(lat["asset"])),
                       "installing": self.installing, "install_error": self.install_error or lat["error"],
                       "can_install": bool(lat["asset"]) or lat["version"] is None, "arch": self.arch},
            "host": {"mem_total_mb": self.mem_mb, "cpus": self.cpus, "small": self.small},
            "busy": next((j.id for j in self.jobs.values() if j.state == "running"), None),
            "refuse": self.refuse(),
        }

    def install_latest(self):
        """Download, unpack and test the latest release in the background, then switch to it."""
        if self.installing:
            raise Fail("An install is already running.")
        if self.printer_state() in ("printing", "paused"):
            raise Fail("Not while a job is running: installing uses the processor and the disk.")
        lat = self.latest(force=True)
        if not lat["asset"]:
            raise Fail(lat["error"] or f"No PrusaSlicer build for this processor ({self.arch}).")
        self.installing, self.install_error = True, None
        threading.Thread(target=self._install, args=(lat["version"], lat["asset"]), daemon=True).start()
        return {"ok": True, "version": lat["version"]}

    def _install(self, version, asset):
        target = os.path.join(self.base, version)
        tmp = tempfile.mkdtemp(prefix=f".install-{version}-", dir=self.base)
        try:
            img = os.path.join(tmp, "PrusaSlicer.AppImage")
            self.fetch(asset["url"], img, timeout=900)
            if asset.get("digest", "") and asset["digest"].startswith("sha256:"):
                h = hashlib.sha256()
                with open(img, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
                if h.hexdigest() != asset["digest"].split(":", 1)[1]:
                    raise Fail("The download didn't match GitHub's checksum.")
            os.chmod(img, 0o755)
            p = self.Popen(["nice", "-n", "19", img, "--appimage-extract"], cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            _, err = p.communicate(timeout=900)
            app = os.path.join(tmp, "squashfs-root", "AppRun")
            if p.returncode != 0 or not os.path.exists(app):
                raise Fail(f"Unpacking failed: {(err or '').strip()[-200:]}")
            os.remove(img)
            t = self.Popen([app, "--help-fff"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            out, _ = t.communicate(timeout=120)
            if t.returncode not in (0, 1) or "--layer-height" not in out:
                raise Fail("The new PrusaSlicer didn't start on this machine; the old one stays in use.")
            with open(os.path.join(tmp, "VERSION"), "w") as f:
                f.write(version + "\n")
            if os.path.exists(target):
                shutil.rmtree(target)
            os.replace(tmp, target)
            prev = self.current_dir()
            link = os.path.join(self.base, "current")
            tmp_link = link + ".new"
            if os.path.lexists(tmp_link):
                os.remove(tmp_link)
            os.symlink(version, tmp_link)
            os.replace(tmp_link, link)                  # atomic switch
            keep = {version, os.path.basename(prev) if prev else None}
            for d in os.listdir(self.base):             # keep the new one and the one before it
                full = os.path.join(self.base, d)
                if d not in keep and d not in ("current", "jobs", "cache") and not d.startswith(".") and os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
            if prev and os.path.basename(prev) != version:
                with open(os.path.join(self.base, "previous"), "w") as f:
                    f.write(os.path.basename(prev))
        except Exception as e:
            self.install_error = str(e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.installing = False

    # ------------------------------------------------------------ slicing
    def submit(self, model, ini, name, center):
        why = self.refuse()
        if why:
            raise Fail(why)
        binary = self.binary()
        if not model or len(model) > MAX_MODEL or len(model) < 84:
            raise Fail("The part is empty or too big")
        try:
            cx, cy = (float(v) for v in str(center).split(","))
        except ValueError:
            raise Fail("Bad part position")
        if not (0 <= cx <= 2000 and 0 <= cy <= 2000):
            raise Fail("Part position outside the bed")
        known = set(self.keys())
        ini = clean_ini(ini, known)
        key = hashlib.sha256(model + ini.encode() + f"{cx:.3f},{cy:.3f}|{self.installed()}".encode()).hexdigest()[:32]
        with self.lock:
            # Studio sends a new request when its settings change: the older ones are no longer wanted
            for j in self.jobs.values():
                if j.state in ("queued", "running"):
                    self._cancel(j)
            jid = uuid.uuid4().hex[:12]
            d = os.path.join(self.base, "jobs", jid)
            os.makedirs(d)
            job = Job(jid, d, key)
            self.jobs[jid] = job
            cached = os.path.join(self.base, "cache", key + ".gcode")
            if os.path.exists(cached):
                shutil.copyfile(cached, os.path.join(d, "out.gcode"))
                job.state, job.phase, job.progress, job.cached, job.finished = "done", "Done", 1.0, True, time.time()
                os.utime(cached)
                return job.view()
            with open(os.path.join(d, "part.stl"), "wb") as f:
                f.write(model)
            with open(os.path.join(d, "rhino.ini"), "w") as f:
                f.write(ini)
            job.center = (cx, cy)
            job.binary = binary
            self.queue.append(job)
            self._prune()
            if not self.worker or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._work, daemon=True)
                self.worker.start()
            self.wake.set()
            return job.view()

    def _cancel(self, job):
        job.cancel = True
        if job.state == "queued":
            job.state, job.phase, job.finished = "cancelled", "Cancelled", time.time()
        elif job.proc and job.proc.poll() is None:
            try:
                os.killpg(job.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, AttributeError):
                job.proc.kill()

    def cancel(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            if not j:
                raise Fail("No such slice")
            self._cancel(j)
        return {"ok": True}

    def job(self, jid):
        j = self.jobs.get(jid)
        if not j:
            raise Fail("No such slice (the Portal may have restarted)")
        return j.view()

    def gcode_path(self, jid):
        j = self.jobs.get(jid)
        if not j or j.state != "done":
            raise Fail("That slice isn't finished")
        return os.path.join(j.dir, "out.gcode")

    def _work(self):
        while True:
            with self.lock:
                job = next((j for j in self.queue if j.state == "queued"), None)
                self.queue = [j for j in self.queue if j.state == "queued" and j is not job]
            if job is None:
                self.wake.clear()
                if not self.wake.wait(30):
                    return
                continue
            self._run(job)

    def _group_rss_mb(self, pgid):
        total = 0
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/stat") as f:
                    st = f.read().rsplit(")", 1)[1].split()
                if int(st[2]) != pgid:
                    continue
                with open(f"/proc/{pid}/statm") as f:
                    total += int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            except (OSError, ValueError, IndexError):
                continue
        return total // (1024 * 1024)

    def _run(self, job):
        if job.cancel:
            return
        threads, cap = self.limits()
        job.state, job.phase, job.progress = "running", "Starting PrusaSlicer", 0.0
        out = os.path.join(job.dir, "out.gcode")
        cmd = ["nice", "-n", "19"]
        if shutil.which("ionice"):
            cmd += ["ionice", "-c", "3"]
        cmd += [job.binary, "--export-gcode", "--load", os.path.join(job.dir, "rhino.ini"),
                "--center", f"{job.center[0]:.3f},{job.center[1]:.3f}", "--threads", str(threads),
                "--loglevel", "3", "--output", out, os.path.join(job.dir, "part.stl")]
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "USER", "TMPDIR")}
        env["DISPLAY"] = ""          # never try to open a window
        log = []
        try:
            job.proc = self.Popen(cmd, cwd=job.dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                  start_new_session=True)
            stop = threading.Event()
            peak = [0]
            def watch():
                while not stop.wait(0.5):
                    mb = self._group_rss_mb(job.proc.pid)
                    peak[0] = max(peak[0], mb)
                    if mb > cap:
                        job.error = (f"PrusaSlicer needed more than {cap} MB of memory, so it was stopped to keep Klipper safe. "
                                     "Try simpler supports, classic perimeters, or a lower-detail model.")
                        self._cancel(job)
                        return
                    if self.small and self.printer_state() in ("printing", "paused"):
                        job.error = "A job started on this small host, so the slice was stopped to keep Klipper safe."
                        self._cancel(job)
                        return
            w = threading.Thread(target=watch, daemon=True)
            w.start()
            for line in job.proc.stdout:
                log.append(line.rstrip())
                del log[:-200]
                for text, frac, label in PHASES:
                    if text.lower() in line.lower() and (job.progress or 0) < frac:
                        job.phase, job.progress = label, frac
            rc = job.proc.wait()
            stop.set()
            job.peak_mb = peak[0]
            if job.cancel:
                job.state = "cancelled" if not job.error else "failed"
                job.phase = "Stopped"
            elif rc != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
                job.state, job.phase = "failed", "Failed"
                tail = [l for l in log if re.search(r"error|fail|invalid|cannot|outside", l, re.I)][-3:] or log[-3:]
                job.error = "PrusaSlicer stopped: " + (" / ".join(tail).strip() or f"exit code {rc}")
            else:
                job.state, job.phase, job.progress = "done", "Done", 1.0
                shutil.copyfile(out, os.path.join(self.base, "cache", job.key + ".gcode"))
        except Exception as e:
            job.state, job.phase, job.error = "failed", "Failed", str(e)
        finally:
            job.finished = time.time()
            for f in ("part.stl",):
                try:
                    os.remove(os.path.join(job.dir, f))
                except OSError:
                    pass

    def _prune(self, keep_jobs=12, keep_cache=8):
        done = sorted((j for j in self.jobs.values() if j.state not in ("queued", "running")), key=lambda j: j.started)
        for j in done[:-keep_jobs]:
            shutil.rmtree(j.dir, ignore_errors=True)
            self.jobs.pop(j.id, None)
        c = os.path.join(self.base, "cache")
        files = sorted((os.path.join(c, f) for f in os.listdir(c)), key=os.path.getmtime)
        for f in files[:-keep_cache]:
            try:
                os.remove(f)
            except OSError:
                pass
