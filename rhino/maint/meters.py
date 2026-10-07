"""Usage meters: what maintenance schedules count.

Two sources, each used for what it is good at:

* the monitor's live poll (every few seconds) - machine up hours, production hours (pauses are not
  counted), which tool is mounted, when a tool is actually working (nozzle heater on, laser firing,
  spindle running, a custom tool's output on), tool swaps, emergency stops / shutdowns.
* Moonraker's job history - job counts and filament per job, and production hours for any job that
  ran while the portal was not running (so nothing is lost if the portal is down for a while).

Stored in myrhino/maintenance/meters.json (inside the config folder, so klipper-backup keeps it).
Written at most every few minutes, plus straight away after a job or an event, to spare the SD card.
"""
import datetime
import json
import logging
import os
import threading
import time

from ..errors import Fail

log = logging.getLogger("rhino.maint")
SAVE_EVERY = 300.0
HISTORY_EVERY = 300.0
KEEP_DAYS = 120
KEEP_SEEN = 600

MACHINE_METERS = {
    "up_h": {"label": "Machine up hours", "unit": "h", "noun": "machine up hours",
             "help": "Klipper running and ready (counted while the portal runs)"},
    "prod_h": {"label": "Production hours", "unit": "h", "noun": "production hours",
               "help": "A job running. Pauses are not counted."},
    "jobs": {"label": "Jobs", "unit": "", "noun": "jobs", "event": "after each job", "help": "Finished jobs from Moonraker's history"},
    "filament_m": {"label": "Filament used", "unit": "m", "noun": "of filament", "help": "From Moonraker's job history"},
    "swaps": {"label": "Tool swaps", "unit": "", "noun": "tool swaps", "event": "after each tool swap",
              "help": "Times a different tool was mounted (connector and dock wear)"},
    "shutdowns": {"label": "Emergency stops and shutdowns", "unit": "", "noun": "shutdowns",
                  "event": "after an emergency stop or Klipper shutdown", "help": "Klipper entering shutdown"},
}
TOOL_METERS = {
    "mounted_h": {"label": "Hours mounted", "unit": "h", "noun": "hours mounted", "help": "Mounted while Klipper is up"},
    "prod_h": {"label": "Production hours", "unit": "h", "noun": "production hours", "help": "Jobs run with this tool, pauses not counted"},
    "active_h": {"label": "Working hours", "unit": "h", "noun": "working hours",
                 "help": "Print heads: nozzle heater on. LightSaber: laser on. HotJoe: spindle running. "
                         "Powered tools: output on. Passive tools: running a job."},
    "jobs": {"label": "Jobs", "unit": "", "noun": "jobs", "event": "after each job with this tool", "help": "Finished jobs with this tool"},
    "mounts": {"label": "Times mounted", "unit": "", "noun": "mounts", "event": "each time this tool is mounted",
               "help": "Swaps onto this tool"},
    "filament_m": {"label": "Filament used", "unit": "m", "noun": "of filament", "help": "Print heads only"},
}


def meter_defs():
    """{"machine.prod_h": {...}, "tool.mounts": {...}} - the shape schedule.py expects."""
    out = {f"machine.{k}": dict(v, scope="machine", meter=k) for k, v in MACHINE_METERS.items()}
    out.update({f"tool.{k}": dict(v, scope="tool", meter=k) for k, v in TOOL_METERS.items()})
    return out


def _today(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


class MeterStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.dirty = False
        self.last_save = 0.0
        self.data = self._load()

    # ------------------------------------------------------------------ disk
    def _empty(self):
        return {"version": 1, "tracking_since": time.time(), "machine": {k: 0.0 for k in MACHINE_METERS}, "tools": {},
                "daily": {}, "seen_jobs": [], "imported_jobs": 0, "history_synced": 0.0, "last_klippy": "",
                "last_tool": 0, "adjustments": [], "new": True}

    def _load(self):
        if not os.path.exists(self.path):
            return self._empty()
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or not isinstance(d.get("machine"), dict):
                raise ValueError("not a meter file")
        except (OSError, ValueError) as e:
            # never throw usage away: keep the unreadable file next to the fresh one
            log.error("meters file unreadable (%s) - starting fresh, old file kept as .bad", e)
            try:
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
            return self._empty()
        base = self._empty()
        base.pop("new")
        for k, v in base.items():
            d.setdefault(k, v)
        for k in MACHINE_METERS:
            d["machine"].setdefault(k, 0.0)
        return d

    def save(self, force=False):
        with self.lock:
            if not (self.dirty or force):
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
            self.dirty, self.last_save = False, time.time()

    def maybe_save(self, now):
        if self.dirty and now - self.last_save >= SAVE_EVERY:
            self.save()

    # ------------------------------------------------------------------ values
    def tool(self, name):
        with self.lock:
            return self.data["tools"].setdefault(name, {k: 0.0 for k in TOOL_METERS})

    def value(self, scope, meter, tool=None):
        with self.lock:
            if scope == "machine":
                return float(self.data["machine"].get(meter, 0.0))
            if not tool:
                return None
            t = self.data["tools"].get(tool)
            return float(t.get(meter, 0.0)) if t else 0.0

    def add(self, scope, meter, amount, tool=None):
        if not amount:
            return
        with self.lock:
            bucket = self.data["machine"] if scope == "machine" else self.tool(tool)
            bucket[meter] = float(bucket.get(meter, 0.0)) + amount
            self.dirty = True

    def snapshot(self, tool=None):
        """Every reading a completion record needs: {'machine.prod_h': 12.5, 'tool.active_h': 3.1, ...}."""
        with self.lock:
            out = {f"machine.{k}": float(v) for k, v in self.data["machine"].items()}
            if tool:
                t = self.data["tools"].get(tool, {})
                out.update({f"tool.{k}": float(t.get(k, 0.0)) for k in TOOL_METERS})
            return out

    def adjust(self, scope, meter, value, tool=None, note="", now=None):
        defs = MACHINE_METERS if scope == "machine" else TOOL_METERS
        if meter not in defs:
            raise Fail(f"Unknown meter {meter}")
        if scope == "tool" and not tool:
            raise Fail("Choose the tool whose meter to set")
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise Fail("The new reading must be a number")
        if not (0 <= v < 1e7):
            raise Fail("The new reading must be 0 or more")
        with self.lock:
            bucket = self.data["machine"] if scope == "machine" else self.tool(tool)
            old = float(bucket.get(meter, 0.0))
            bucket[meter] = v
            self.data["adjustments"] = (self.data["adjustments"] + [
                {"at": now or time.time(), "scope": scope, "tool": tool or "", "meter": meter, "from": old, "to": v,
                 "note": (note or "")[:200]}])[-200:]
            self.dirty = True
        self.save()
        return old

    def rename_tool(self, old, new):
        with self.lock:
            if old in self.data["tools"]:
                self.data["tools"][new] = self.data["tools"].pop(old)
                for day in self.data["daily"].values():
                    if old in day.get("tools", {}):
                        day["tools"][new] = day["tools"].pop(old)
                self.dirty = True
        self.save()

    # ------------------------------------------------------------------ rates
    def roll_day(self, now):
        """First tick of a new day: remember the readings, for 'about N days at your usual rate'."""
        day = _today(now)
        with self.lock:
            if day in self.data["daily"]:
                return
            self.data["daily"][day] = {"machine": dict(self.data["machine"]),
                                       "tools": {n: dict(t) for n, t in self.data["tools"].items()}}
            for old in sorted(self.data["daily"])[:-KEEP_DAYS]:
                del self.data["daily"][old]
            self.dirty = True

    def rate(self, scope, meter, tool=None, now=None, window=30):
        """Average use per day over (up to) the last `window` days; None with under 3 days of history."""
        now = now or time.time()
        with self.lock:
            days = sorted(self.data["daily"])
            if not days:
                return None
            cutoff = _today(now - window * 86400)
            first = next((d for d in days if d >= cutoff), days[0])
            span = (now - datetime.datetime.strptime(first, "%Y-%m-%d").timestamp()) / 86400
            if span < 3:
                return None
            snap = self.data["daily"][first]
            old = (snap["machine"] if scope == "machine" else snap.get("tools", {}).get(tool, {})).get(meter, 0.0)
        cur = self.value(scope, meter, tool) or 0.0
        return max(cur - float(old), 0.0) / span


class Collector:
    """Monitor listener that turns polls into meter readings."""

    ACTIVE_OBJECTS = ("output_pin SERVO_LASER", "output_pin Spindle_power", "gcode_macro TOOL_POWER_STATE")

    def __init__(self, store, moonraker, tool_lookup, on_change=None):
        self.store, self.mr, self.tool_lookup = store, moonraker, tool_lookup
        self.on_change = on_change or (lambda: None)   # called after events (status may have changed)
        self.online_since = None
        self.live_jobs = []                              # [{"filename", "start", "tool"}] seen this run
        self.last_history = 0.0
        self.last_status = 0.0

    def objects(self):
        return list(self.ACTIVE_OBJECTS)

    def flush(self):
        self.store.save()

    # ------------------------------------------------------------------ one poll
    def on_tick(self, s, prev):
        st, d = self.store, self.store.data
        now = s.now
        if self.online_since is None:
            self.online_since = now
        st.roll_day(now)
        hours = s.dt / 3600.0
        event = False

        if s.klippy == "shutdown" and d.get("last_klippy") != "shutdown":
            st.add("machine", "shutdowns", 1)
            event = True
        if s.klippy in ("ready", "shutdown", "error", "startup") and d.get("last_klippy") != s.klippy:
            d["last_klippy"] = s.klippy
            st.dirty = True

        tools = self.tool_lookup()
        mounted = tools.get(s.mounted_slot) if s.klippy == "ready" else None
        name = mounted["name"] if mounted else None

        if s.klippy == "ready":
            st.add("machine", "up_h", hours)
            if name:
                st.add("tool", "mounted_h", hours, name)
            # swaps: a different tool than the last one seen (a restart passes through slot 0 - not a swap)
            if s.mounted_slot and s.mounted_slot != d.get("last_tool"):
                if d.get("last_tool") and name:
                    st.add("machine", "swaps", 1)
                    st.add("tool", "mounts", 1, name)
                    event = True
                d["last_tool"] = s.mounted_slot
                st.dirty = True

        if s.print_state == "printing":
            st.add("machine", "prod_h", hours)
            if name:
                st.add("tool", "prod_h", hours, name)
        if s.busy and not (prev and prev.busy):
            self.live_jobs = (self.live_jobs + [{"filename": s.filename, "start": now, "tool": name}])[-20:]
        if name and self._working(mounted, s):
            st.add("tool", "active_h", hours, name)

        job_ended = prev is not None and prev.busy and not s.busy and s.klippy == "ready"
        if job_ended or now - self.last_history >= HISTORY_EVERY or self.last_history == 0.0:
            if self.sync_history(now, tools, name):
                event = True
        if event or job_ended:
            st.save()
            self.on_change()
            self.last_status = now
        else:
            st.maybe_save(now)
            if now - self.last_status >= 60:      # time-based tasks become due without any event
                self.last_status = now
                self.on_change()

    @staticmethod
    def _working(tool, s):
        o, ty = s.objects, tool.get("type")
        try:
            if ty == "DEPOSITION":
                return float((o.get("extruder") or {}).get("target", 0) or 0) > 0
            if ty == "LASER":
                return float((o.get("output_pin SERVO_LASER") or {}).get("value", 0) or 0) > 0
            if ty == "CNC":
                return float((o.get("output_pin Spindle_power") or {}).get("value", 0) or 0) > 0.5
            if ty == "POWERED":
                tp = o.get("gcode_macro TOOL_POWER_STATE") or {}
                return int(tp.get("active", 0) or 0) == 1 and int(tp.get("suspended", 0) or 0) == 0
        except (TypeError, ValueError):
            return False
        return s.print_state == "printing"          # passive tools, drag knife: working while a job runs

    # ------------------------------------------------------------------ Moonraker history
    def sync_history(self, now, tools, mounted_name):
        """Count finished jobs once each. Returns True if anything was counted."""
        self.last_history = now
        d = self.store.data
        first = d.get("new", False) and not d.get("seen_jobs")
        try:
            jobs = self.mr.history(since=None if first else max(d.get("history_synced", 0) - 86400, 0),
                                   limit=1000 if first else 100)
        except Fail:
            return False
        seen = set(d.get("seen_jobs", []))
        types = {t["name"]: t.get("type") for t in tools.values()}
        counted = 0
        for j in sorted(jobs, key=lambda j: j.get("start_time") or 0):
            jid = str(j.get("job_id", ""))
            if not jid or jid in seen or j.get("status") == "in_progress":
                continue
            seen.add(jid)
            counted += 1
            fil_m = float(j.get("filament_used") or 0.0) / 1000.0
            total_h = float(j.get("total_duration") or 0.0) / 3600.0
            start = float(j.get("start_time") or 0.0)
            if first:
                # first run: the machine's past from Moonraker's history becomes the starting reading
                self.store.add("machine", "jobs", 1)
                self.store.add("machine", "filament_m", fil_m)
                self.store.add("machine", "prod_h", total_h)
                d["imported_jobs"] = d.get("imported_jobs", 0) + 1
                continue
            live = next((x for x in self.live_jobs if x["filename"] == j.get("filename")
                         and abs(x["start"] - start) < 900), None)
            tool = live["tool"] if live else mounted_name
            self.store.add("machine", "jobs", 1)
            self.store.add("machine", "filament_m", fil_m)
            if tool:
                self.store.add("tool", "jobs", 1, tool)
                if types.get(tool) == "DEPOSITION":
                    self.store.add("tool", "filament_m", fil_m, tool)
            # the part of the job before this portal started was not counted live
            unseen_h = max(0.0, min(float(j.get("end_time") or start) , self.online_since) - start) / 3600.0
            if unseen_h > 0 and not live:
                unseen_h = min(unseen_h, total_h)
                self.store.add("machine", "prod_h", unseen_h)
                if tool:
                    self.store.add("tool", "prod_h", unseen_h, tool)
        d["seen_jobs"] = sorted(seen, key=lambda x: x)[-KEEP_SEEN:] if len(seen) > KEEP_SEEN else sorted(seen)
        d["history_synced"] = now
        if first:
            d.pop("new", None)
        self.store.dirty = True
        return counted > 0
