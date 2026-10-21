"""PrusaSlicer on the Rhino host, for Rhino Studio (config 1.5.2).

Studio sends a part (binary STL, already turned and scaled), the full PrusaSlicer INI and where the
part's centre goes; this runs PrusaSlicer's command line and hands back the G-code. Studio then wraps
it in the Rhino's own start and end lines and checks every line before it reaches Klipper.

Keeping the machine first:
  - one slice at a time (one more may wait); a newer request from Studio cancels the older one
  - lowest CPU and disk priority (nice 19, ionice idle), a thread cap, and a memory watchdog over the
    whole process tree that stops the slice before it can starve Klipper or Moonraker of memory
  - while a job prints: hosts under 4 GB (a 2 GB board; PRINT_SLICE_MB) refuse to slice at all; bigger ones
    slice with half the cores and a lower memory cap
  - the INI is re-checked here: only known option names, single-line values, and the options that
    could run programs or rewrite G-code (post_process, gcode_substitutions) are forced empty
  - identical requests (same part, settings, engine) come straight from a small cache

Where the engine comes from (1.5.2): Prusa publishes its Linux build only on Flathub
(com.prusa3d.PrusaSlicer); its GitHub releases carry Windows and Mac builds only. So the engine is a
per-user Flatpak (`flatpak --user`): no root, nothing outside ~/.local/share/flatpak. The Portal never
runs sudo; the host needs the `flatpak` command once (`sudo apt install flatpak`, by hand over SSH).
Hosts under 2 GB of memory aren't offered the engine at all: they slice with Kiri:Moto in Studio.

Each slice runs in Flatpak's sandbox with no network, no display and no files but its own job folder.
`flatpak run` starts bubblewrap, which may start the slicer in a session of its own, so cancelling and
the memory watchdog follow the process tree (parent PIDs), not just the process group.

Before an update the installed Flatpak commit is recorded; if the new version fails its test slice, the
previous commit is put back (`flatpak update --commit=`), and Studio can ask for that by hand too.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
import uuid

from .errors import Fail

APP = "com.prusa3d.PrusaSlicer"
REMOTE = "flathub"
REMOTE_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
# A "2 GB" board reports roughly 1850-1950 MB to the OS (the rest goes to the GPU/firmware),
# so the line sits at 1800 MB: 2 GB boards are offered the engine, a Pi 3B (~906 MB) isn't. (1.5.3)
SMALL_HOST_MB = 1800
# Slicing while a job prints needs more headroom than slicing at all: 2 GB boards wait for the
# job to end (as the Pi 3B did before 1.5.3); 4 GB and up slice alongside it, niced and watched.
PRINT_SLICE_MB = 3000
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
# Flatpak's sandbox for a slice: no network, no display, no sound, no host or home files; the job
# folder is added per slice. --die-with-parent: killing `flatpak run` takes the sandbox with it.
SANDBOX = ["--die-with-parent", "--unshare=network", "--nosocket=x11", "--nosocket=fallback-x11", "--nosocket=wayland",
           "--nosocket=pulseaudio", "--nofilesystem=host", "--nofilesystem=home", "--env=DISPLAY=", "--env=WAYLAND_DISPLAY="]
ARCHES = ("x86_64", "aarch64")
NO_FLATPAK = ("PrusaSlicer comes from Flathub, so the Rhino's host needs Flatpak first. Over SSH, run once: "
              "sudo apt install flatpak — then press Install again. (The Portal never runs sudo itself.)")
SMALL_MSG = ("PrusaSlicer needs a host with 2 GB of memory or more. Kiri:Moto in the browser still slices on this one.")


# Automatic updates (1.5.8): only while PrusaSlicer is actually being used, never during a job or a slice.
AUTO_EVERY_S = 6 * 3600          # look at Flathub this often
AUTO_FIRST_S = 10 * 60           # first look this long after the Portal starts
AUTO_USED_DAYS = 30              # "being used": sliced with it within this many days


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


def parse_info(text):
    """Version and commit from `flatpak info` / `flatpak remote-info` (same `Key: value` layout)."""
    v = re.search(r"^\s*Version:\s*(\S+)", text, re.M)
    c = re.search(r"^\s*Commit:\s*([0-9a-f]{8,})", text, re.M)
    return {"version": v.group(1) if v else None, "commit": c.group(1) if c else None}


def test_cube_stl(size=20.0):
    """A small binary STL cube (12 facets) for the test slice after an install."""
    s = size
    v = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
             (3, 0, 4), (3, 4, 7)]
    out = bytearray(b"Rhino test cube".ljust(80, b" ")) + struct.pack("<I", len(faces))
    for a, b, c in faces:
        out += struct.pack("<3f", 0, 0, 0)
        for i in (a, b, c):
            out += struct.pack("<3f", *v[i])
        out += b"\0\0"
    return bytes(out)


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


def _tree(root):
    """`root` and every process under it, by parent PID (bubblewrap may give the slicer its own session)."""
    kids = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/stat") as f:
                st = f.read().rsplit(")", 1)[1].split()
            kids.setdefault(int(st[1]), []).append(int(pid))
        except (OSError, ValueError, IndexError):
            continue
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(kids.get(p, []))
    return out


def _kill_tree(proc):
    """Stop a slice and everything it started; the group kill catches anything already re-parented."""
    pids = _tree(proc.pid)
    for p in reversed(pids):
        try:
            os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError):
        pass
    try:
        proc.kill()
    except Exception:
        pass


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
    def __init__(self, base_dir, printer_state=lambda: "standby", run=subprocess.Popen, flatpak=None,
                 mem_mb=None, cpus=None, arch=None):
        self.base = base_dir
        self.printer_state = printer_state
        self.Popen = run
        self._flatpak = flatpak            # path to `flatpak`; None = look it up; "" = treat as missing (tests)
        self.mem_mb = mem_mb or _meminfo()
        self.cpus = cpus or os.cpu_count() or 1
        self.arch = arch or _arch()
        self.jobs = {}
        self.queue = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.worker = None
        self._latest = {"at": 0, "version": None, "commit": None, "error": None, "no_build": False}
        self._info = {"at": 0, "version": None, "commit": None}
        self.installing = False
        self.install_phase = None
        self.install_error = None
        self._auto_checked = time.time() - AUTO_EVERY_S + AUTO_FIRST_S   # first look a few minutes after start
        self._auto_thread = None
        os.makedirs(os.path.join(self.base, "jobs"), exist_ok=True)
        os.makedirs(os.path.join(self.base, "cache"), exist_ok=True)

    # ------------------------------------------------------------ flatpak
    def flatpak(self):
        if self._flatpak is not None:
            return self._flatpak or None
        return shutil.which("flatpak")

    def _env(self):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "USER", "TMPDIR", "XDG_RUNTIME_DIR")}
        if "XDG_RUNTIME_DIR" not in env:       # the Portal is a system service: no login session of its own
            d = f"/run/user/{os.getuid()}"
            if os.path.isdir(d) and os.access(d, os.W_OK):
                env["XDG_RUNTIME_DIR"] = d
        env["DISPLAY"] = ""                    # never try to open a window
        return env

    def _fp(self, args, timeout=120, low=False):
        """Run `flatpak <args>`; returns (exit code, output)."""
        fp = self.flatpak()
        if not fp:
            raise Fail(NO_FLATPAK)
        cmd = ([*self._low(), fp] if low else [fp]) + args
        p = self.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=self._env(),
                       start_new_session=True)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(p)
            p.communicate()
            return 124, f"flatpak {' '.join(args[:2])} took longer than {timeout} s and was stopped"
        return p.returncode, out or ""

    @staticmethod
    def _low():
        cmd = ["nice", "-n", "19"]
        if shutil.which("ionice"):
            cmd += ["ionice", "-c", "3"]
        return cmd

    def engine_cmd(self, workdir):
        """The sandboxed PrusaSlicer command line, allowed to see only `workdir`."""
        fp = self.flatpak()
        if not fp:
            raise Fail(NO_FLATPAK)
        return [fp, "run", "--user", "--command=prusa-slicer", *SANDBOX, f"--filesystem={workdir}", APP]

    # ------------------------------------------------------------ engine
    @property
    def small(self):
        return self.mem_mb < SMALL_HOST_MB

    def info(self, fresh=False):
        """{version, commit} of the installed engine (both None if it isn't installed); cached 20 s."""
        if not fresh and time.time() - self._info["at"] < 20:
            return self._info
        v = {"version": None, "commit": None}
        if self.flatpak():
            rc, out = self._fp(["--user", "info", APP], timeout=30)
            if rc == 0:
                v = parse_info(out)
                if not v["version"] and v["commit"]:
                    v["version"] = v["commit"][:10]
        self._info = {"at": time.time(), **v}
        return self._info

    def installed(self):
        return self.info()["version"]

    def binary(self):
        """Raises if there's no engine to slice with (kept for callers that only need the check)."""
        if not self.flatpak() or not self.info()["commit"]:
            raise Fail("PrusaSlicer isn't installed on the Rhino yet (Studio: Settings > Software).")
        return self.flatpak()

    def keys(self):
        """Option names the installed engine accepts, from its own --help-fff (cached per commit)."""
        commit = self.info()["commit"]
        if not commit:
            return []
        cache = os.path.join(self.base, f"keys-{commit[:16]}.json")
        try:
            with open(cache) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
        keys = self._help_keys()
        if len(keys) < 50:
            raise Fail("The installed PrusaSlicer didn't list its options; reinstall it from Settings > Software.")
        for f in os.listdir(self.base):
            if f.startswith("keys-") and f.endswith(".json"):
                os.remove(os.path.join(self.base, f))
        with open(cache, "w") as f:
            json.dump(keys, f)
        return keys

    def _help_keys(self):
        d = tempfile.mkdtemp(prefix=".help-", dir=self.base)
        try:
            p = self.Popen(self.engine_cmd(d) + ["--help-fff"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=self._env(), start_new_session=True)
            try:
                out, _ = p.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                _kill_tree(p)
                return []
            return sorted({k.replace("-", "_") for k in re.findall(r"^\s*--([a-z][a-z0-9-]*)", out or "", re.M)})
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def refuse(self):
        """Why a slice can't start right now, or None."""
        if self.mem_mb < PRINT_SLICE_MB and self.printer_state() in ("printing", "paused"):
            return ("This host has under 4 GB of memory: slicing while a job prints could starve Klipper. "
                    "Slice when the job ends, or use Kiri:Moto in the browser.")
        return None

    def limits(self):
        """(threads, memory cap MB) for a slice now."""
        busy = self.printer_state() in ("printing", "paused")
        if busy:
            return max(1, self.cpus // 2), int(self.mem_mb * 0.4)
        return max(1, self.cpus - 1), max(256, min(int(self.mem_mb * 0.7), self.mem_mb - 768))

    # ------------------------------------------------------------ install, update, go back
    def _has_remote(self):
        rc, out = self._fp(["--user", "remotes", "--columns=name"], timeout=30)
        return rc == 0 and REMOTE in out.split()

    def latest(self, force=False):
        """What Flathub offers for this processor; checked at most every 6 hours unless forced."""
        if not force and time.time() - self._latest["at"] < 6 * 3600:
            return self._latest
        lat = {"at": time.time(), "version": None, "commit": None, "error": None, "no_build": False}
        try:
            if self.flatpak() and self._has_remote():   # before the first install there's nothing to ask yet
                rc, out = self._fp(["--user", "remote-info", REMOTE, APP], timeout=60)
                if rc == 0:
                    lat.update(parse_info(out))
                elif re.search(r"nothing matches|not found|no such ref|couldn't find", out, re.I):
                    lat["no_build"] = True
                else:
                    lat["error"] = "Couldn't check Flathub: " + (out.strip().splitlines() or ["no answer"])[-1][:200]
        except Fail:
            pass
        self._latest = lat
        return lat

    def blocked(self):
        """Why the engine can't be installed or updated on this host, or None."""
        if self.arch not in ARCHES:
            return f"There's no official PrusaSlicer build for this processor ({self.arch}). Kiri:Moto in the browser still slices."
        if self.small:
            return SMALL_MSG
        if not self.flatpak():
            return NO_FLATPAK
        if self._latest["no_build"]:
            return f"Flathub has no PrusaSlicer build for this processor ({self.arch}). Kiri:Moto in the browser still slices."
        return None

    def previous(self):
        try:
            with open(os.path.join(self.base, "previous.json")) as f:
                p = json.load(f)
            return p if p.get("commit") else None
        except (OSError, ValueError):
            return None

    def state(self):
        inf = self.info()
        lat = self.latest()
        why = self.blocked()
        inst = inf["version"]
        def newer():
            if not inst:
                return False
            if inf["commit"] and lat["commit"]:
                return inf["commit"] != lat["commit"]
            n = lambda v: [int(x) for x in re.findall(r"\d+", v or "")]
            return bool(lat["version"] and n(lat["version"]) > n(inst))
        prev = self.previous()
        return {
            "engine": {"name": "PrusaSlicer", "source": "Flathub", "installed": inst, "latest": lat["version"],
                       "update_available": not why and (not inst or newer()),
                       "installing": self.installing, "install_phase": self.install_phase,
                       "install_error": self.install_error or lat["error"],
                       "can_install": not why, "blocked": why, "arch": self.arch,
                       "previous": prev["version"] if prev and inst and prev["commit"] != inf["commit"] else None},
            "auto": self.auto_state(),
            "host": {"mem_total_mb": self.mem_mb, "cpus": self.cpus, "small": self.small},
            "busy": next((j.id for j in self.jobs.values() if j.state == "running"), None),
            "refuse": self.refuse(),
        }

    def _start(self, target, *args):
        if self.installing:
            raise Fail("An install is already running.")
        if self.printer_state() in ("printing", "paused"):
            raise Fail("Not while a job is running: installing uses the processor and the disk.")
        self.latest(force=True)
        why = self.blocked()
        if why:
            raise Fail(why)
        self.installing, self.install_error, self.install_phase = True, None, "Starting"
        threading.Thread(target=target, args=args, daemon=True).start()

    def install_latest(self):
        """Install, or update to, Flathub's current PrusaSlicer in the background; test it; go back if it fails."""
        self._start(self._install)
        return {"ok": True, "version": self._latest["version"]}

    def roll_back(self):
        """Put back the version that was installed before the last update."""
        prev = self.previous()
        if not prev or not self.info(fresh=True)["commit"] or prev["commit"] == self.info()["commit"]:
            raise Fail("There's no earlier PrusaSlicer to go back to.")
        self._start(self._roll_back, prev)
        return {"ok": True, "version": prev["version"]}

    def _fail_tail(self, what, rc, out):
        lines = [l for l in (out or "").strip().splitlines() if l.strip()]
        return f"{what} (flatpak exit {rc}): " + (" / ".join(lines[-2:])[:300] or "no output")

    def _install(self, on_done=None):
        try:
            self.install_phase = "Adding Flathub"
            rc, out = self._fp(["--user", "remote-add", "--if-not-exists", REMOTE, REMOTE_URL], timeout=300, low=True)
            if rc != 0:
                raise Fail(self._fail_tail("Couldn't add Flathub", rc, out))
            before = self.info(fresh=True)
            if before["commit"]:
                self.install_phase = "Updating from Flathub"
                rc, out = self._fp(["--user", "update", "-y", "--noninteractive", APP], timeout=3600, low=True)
            else:
                self.install_phase = "Downloading from Flathub (the first time brings its runtime too)"
                rc, out = self._fp(["--user", "install", "-y", "--noninteractive", REMOTE, APP], timeout=3600, low=True)
            if rc != 0:
                if re.search(r"nothing matches|not found|no such ref", out, re.I):
                    self._latest["no_build"] = True
                raise Fail(self._fail_tail("Flathub install failed", rc, out))
            after = self.info(fresh=True)
            if not after["commit"]:
                raise Fail("Flatpak says it installed PrusaSlicer, but it isn't listed afterwards.")
            if before["commit"] and before["commit"] == after["commit"]:
                return                                       # already the latest
            self.install_phase = "Checking it slices"
            err = self._self_test()
            if err:
                if before["commit"]:
                    self.install_phase = f"Going back to {before['version']}"
                    rc, out = self._fp(["--user", "update", "-y", "--noninteractive", f"--commit={before['commit']}", APP],
                                       timeout=3600, low=True)
                    self.info(fresh=True)
                    if rc == 0:
                        raise Fail(f"The new PrusaSlicer failed its test slice ({err}), so {before['version']} was put back.")
                    raise Fail(f"The new PrusaSlicer failed its test slice ({err}), and going back failed too: "
                               + self._fail_tail("", rc, out) + ". Use Kiri:Moto until it's sorted.")
                raise Fail(f"PrusaSlicer installed but failed its test slice: {err}")
            if before["commit"]:
                with open(os.path.join(self.base, "previous.json"), "w") as f:
                    json.dump({"version": before["version"], "commit": before["commit"]}, f)
        except Exception as e:
            self.install_error = str(e)
        finally:
            try:                                   # settle the state before saying it's done
                self.info(fresh=True)
                self.latest(force=True)            # Flathub may have only just been added
                if on_done:
                    on_done()                      # e.g. the automatic updater's note, before anyone sees "done"
            finally:
                self.installing, self.install_phase = False, None

    def _roll_back(self, prev):
        try:
            cur = self.info(fresh=True)
            self.install_phase = f"Going back to {prev['version']}"
            rc, out = self._fp(["--user", "update", "-y", "--noninteractive", f"--commit={prev['commit']}", APP],
                               timeout=3600, low=True)
            if rc != 0:
                raise Fail(self._fail_tail(f"Couldn't go back to {prev['version']} (Flathub may no longer have it)", rc, out))
            self.info(fresh=True)
            self.install_phase = "Checking it slices"
            err = self._self_test()
            if err:
                raise Fail(f"{prev['version']} is back but failed its test slice: {err}")
            with open(os.path.join(self.base, "previous.json"), "w") as f:   # going back again = forward
                json.dump({"version": cur["version"], "commit": cur["commit"]}, f)
            # you went back from it on purpose: automatic updates wait for something newer than that
            self._auto_save(skip=cur["commit"])
        except Exception as e:
            self.install_error = str(e)
        finally:
            try:                                   # settle the state before saying it's done
                self.info(fresh=True)
                self.latest(force=True)            # Flathub may have only just been added
            finally:
                self.installing, self.install_phase = False, None

    def _self_test(self):
        """Slice a 20 mm cube in the sandbox exactly as a real slice runs; returns an error or None."""
        keys = self._help_keys()
        if "layer_height" not in keys:
            return "it didn't start without a screen"
        d = tempfile.mkdtemp(prefix=".selftest-", dir=self.base)
        try:
            part, out = os.path.join(d, "cube.stl"), os.path.join(d, "cube.gcode")
            with open(part, "wb") as f:
                f.write(test_cube_stl())
            p = self.Popen([*self._low(), *self.engine_cmd(d), "--export-gcode", "--center", "100,100", "--threads", "1",
                            "--output", out, part], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env=self._env(), start_new_session=True)
            try:
                log, _ = p.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                _kill_tree(p)
                return "the test slice took over 10 minutes"
            if p.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
                tail = [l for l in (log or "").splitlines() if l.strip()][-2:]
                return "the test slice failed: " + (" / ".join(tail)[:200] or f"exit {p.returncode}")
            for f in os.listdir(self.base):          # a new engine knows different options
                if f.startswith("keys-"):
                    os.remove(os.path.join(self.base, f))
            return None
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # ------------------------------------------------------------ automatic updates (1.5.8)
    def _auto_file(self):
        return os.path.join(self.base, "auto.json")

    def _auto_load(self):
        try:
            with open(self._auto_file()) as f:
                a = json.load(f)
            return a if isinstance(a, dict) else {}
        except (OSError, ValueError):
            return {}

    def _auto_save(self, **kw):
        a = self._auto_load()
        a.update(kw)
        tmp = self._auto_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(a, f)
        os.replace(tmp, self._auto_file())

    def mark_used(self, now=None):
        try:
            with open(os.path.join(self.base, "last_used"), "w") as f:
                f.write(str(now or time.time()))
        except OSError:
            pass

    def last_used(self):
        try:
            with open(os.path.join(self.base, "last_used")) as f:
                return float(f.read().strip())
        except (OSError, ValueError):
            return None

    def auto_state(self, now=None):
        a = self._auto_load()
        used = self.last_used()
        return {"on": a.get("on", True), "last_used": used,
                "in_use": bool(used and (now or time.time()) - used < AUTO_USED_DAYS * 86400),
                "used_days": AUTO_USED_DAYS, "skip": a.get("skip"), "last": a.get("last")}

    def set_auto(self, on):
        self._auto_save(on=bool(on))
        return self.auto_state()

    def auto_why_not(self, now=None):
        """Why an automatic update wouldn't run now, or None if it would. Asks Flathub only through latest()."""
        now = now or time.time()
        a = self.auto_state(now)
        if not a["on"]:
            return "off"
        if self.installing:
            return "installing"
        if not self.info()["commit"]:
            return "not installed"
        if not a["in_use"]:
            return "not used lately"
        if self.blocked():
            return "blocked"
        if self.printer_state() in ("printing", "paused"):
            return "job"
        if any(j.state in ("queued", "running") for j in self.jobs.values()):
            return "slicing"
        lat, inf = self._latest, self.info()
        if not lat["commit"] or lat["commit"] == inf["commit"]:
            return "up to date"
        if a["skip"] and lat["commit"] == a["skip"]:
            return "went back from it"
        return None

    def auto_tick(self, now=None):
        """Called by the Portal's monitor every few seconds; looks at Flathub every AUTO_EVERY_S in the background."""
        now = now or time.time()
        if now - self._auto_checked < AUTO_EVERY_S or (self._auto_thread and self._auto_thread.is_alive()):
            return
        self._auto_checked = now
        if not self.auto_state(now)["on"] or not self.info()["commit"]:
            return
        self._auto_thread = threading.Thread(target=self._auto_check, daemon=True)
        self._auto_thread.start()

    def _auto_check(self):
        self.latest(force=True)
        if self.auto_why_not():
            return
        before = self.info()["version"]
        try:
            self._start(self._auto_install, before)
        except Fail:
            pass                                   # a job started meanwhile: next time

    def _auto_install(self, before):
        def note():
            self._auto_save(last={"from": before, "to": self.info()["version"], "at": time.time(),
                                  "ok": not self.install_error, "error": self.install_error})
        self._install(on_done=note)

    # ------------------------------------------------------------ slicing
    def submit(self, model, ini, name, center):
        why = self.refuse()
        if why:
            raise Fail(why)
        self.binary()                      # says to install first if there's no engine
        self.mark_used()
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
        key = hashlib.sha256(model + ini.encode() + f"{cx:.3f},{cy:.3f}|{self.info()['commit']}".encode()).hexdigest()[:32]
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
            job.cmd = self.engine_cmd(d)
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
            _kill_tree(job.proc)

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

    @staticmethod
    def _tree_rss_mb(root):
        total = 0
        for pid in _tree(root):
            try:
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
        cmd = [*self._low(), *job.cmd, "--export-gcode", "--load", os.path.join(job.dir, "rhino.ini"),
                "--center", f"{job.center[0]:.3f},{job.center[1]:.3f}", "--threads", str(threads),
                "--loglevel", "3", "--output", out, os.path.join(job.dir, "part.stl")]
        env = self._env()
        log = []
        try:
            job.proc = self.Popen(cmd, cwd=job.dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                  start_new_session=True)
            stop = threading.Event()
            peak = [0]
            def watch():
                while not stop.wait(0.5):
                    mb = self._tree_rss_mb(job.proc.pid)
                    peak[0] = max(peak[0], mb)
                    if mb > cap:
                        job.error = (f"PrusaSlicer needed more than {cap} MB of memory, so it was stopped to keep Klipper safe. "
                                     "Try simpler supports, classic perimeters, or a lower-detail model.")
                        self._cancel(job)
                        return
                    if self.mem_mb < PRINT_SLICE_MB and self.printer_state() in ("printing", "paused"):
                        job.error = "A job started, and this host has under 4 GB of memory, so the slice was stopped to keep Klipper safe."
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
