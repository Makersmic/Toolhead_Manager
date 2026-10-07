"""Background watcher: one Moonraker poll every few seconds, shared by everything that needs to know
what the machine is doing over time.

* the restart banner: how long the current job has been paused (Klipper does not report it)
* "restart automatically when this job finishes"
* the maintenance meters (rhino.maint.collector registers itself as a listener)

tick(now) does one poll and is called by the thread; tests call it directly with a fake clock.
"""
import logging
import threading
import time

from . import pending
from .errors import Fail
from .moonraker import BUSY_STATES

log = logging.getLogger("rhino.monitor")
AUTO_RESTART_DELAY = 30.0     # let END_PRINT / CANCEL_PRINT finish before restarting
BASE_OBJECTS = ("print_stats", "virtual_sdcard", "gcode_macro SWAP_TOOL", "extruder")


class Snapshot:
    """What one poll saw. objects is {} unless Klipper is ready."""
    def __init__(self, now, dt, klippy, objects):
        self.now, self.dt, self.klippy, self.objects = now, dt, klippy, objects
        ps = objects.get("print_stats") or {}
        self.print_state = ps.get("state", "unknown") if klippy == "ready" else "unknown"
        self.filename = ps.get("filename") or ""
        try:
            self.mounted_slot = int((objects.get("gcode_macro SWAP_TOOL") or {}).get("current_tool", 0))
        except (TypeError, ValueError):
            self.mounted_slot = 0

    @property
    def busy(self):
        return self.print_state in BUSY_STATES


class Monitor:
    def __init__(self, paths, moonraker, interval=5.0):
        self.paths, self.mr, self.interval = paths, moonraker, interval
        self.listeners = []          # objects with objects() -> [names] and on_tick(snapshot, prev)
        self.prev = None
        self.last_tick = None
        self.job = {"active": False, "filename": "", "paused_s": 0.0, "paused_since": None}
        self._restart_at = None
        self._down_since = None      # first poll that saw Klipper not ready
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------------ thread
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="rhino-monitor", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        for l in self.listeners:
            getattr(l, "flush", lambda: None)()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick(time.time())
            except Exception:                       # never let the watcher die
                log.exception("monitor tick failed")
            self._stop.wait(self.interval)

    # ------------------------------------------------------------------ one poll
    def tick(self, now):
        with self._lock:
            dt = 0.0 if self.last_tick is None else max(0.0, min(now - self.last_tick, 3 * self.interval))
            self.last_tick = now
            klippy = self.mr.klippy_state()
            objects = {}
            if klippy == "ready":
                names = list(BASE_OBJECTS)
                for l in self.listeners:
                    names += [n for n in l.objects() if n not in names]
                try:
                    objects = self.mr.query(names)
                except Fail:
                    klippy = "startup"
            snap = Snapshot(now, dt, klippy, objects)
            self._note_restart(snap)
            self._track_job(snap)
            self._auto_restart(snap)
            for l in self.listeners:
                try:
                    l.on_tick(snap, self.prev)
                except Exception:
                    log.exception("monitor listener failed")
            self.prev = snap
            return snap

    def _track_job(self, s):
        j = self.job
        if s.busy and not j["active"]:
            j.update(active=True, filename=s.filename, paused_s=0.0, paused_since=None)
        elif not s.busy and s.klippy == "ready":
            j.update(active=False, paused_since=None)
        if j["active"]:
            j["filename"] = s.filename or j["filename"]
            if s.print_state == "paused":
                if j["paused_since"] is None:
                    j["paused_since"] = s.now        # count from the first poll that saw the pause
                else:
                    j["paused_s"] += s.dt
            else:
                j["paused_since"] = None

    def _note_restart(self, s):
        """Klipper re-reads its whole config on every restart, so once it comes back from a restart
        that began after the last change was saved, nothing is waiting any more - however the
        restart was started (portal, console RESTART_FOR_TOOLS, Mainsail's button)."""
        if s.klippy != "ready":
            if self._down_since is None:
                self._down_since = s.now
            return
        if self._down_since is not None:
            p = pending.get(self.paths)
            if p is not None and float(p.get("since", s.now)) < self._down_since:
                pending.clear(self.paths)
            self._down_since = None

    def job_info(self):
        with self._lock:
            return dict(self.job)

    # ------------------------------------------------------------------ auto restart
    def _auto_restart(self, s):
        p = pending.get(self.paths)
        if not p or not p.get("auto_restart"):
            self._restart_at = None
            return
        was_busy = self.prev is not None and self.prev.busy
        if was_busy and not s.busy and s.klippy == "ready":
            if s.print_state == "error":
                pending.set_note(self.paths, "The job ended with an error, so Klipper was not restarted automatically.",
                                 auto_restart=False)
                return
            self._restart_at = s.now + AUTO_RESTART_DELAY
        if self._restart_at is not None and s.now >= self._restart_at and not s.busy and s.klippy == "ready":
            self._restart_at = None
            try:
                self.mr.restart()
                pending.clear(self.paths)
                log.info("auto-restart after job: Klipper restarted to load tool changes")
            except Fail as e:
                pending.set_note(self.paths, f"Automatic restart failed: {e}", auto_restart=False)

    def restart_eta(self):
        return self._restart_at
