"""Tiny Moonraker client (stdlib only). The portal uses it to show printer and job state, to restart
Klipper after a tool change - and to REFUSE to restart while a job is running - and the
maintenance monitor uses it to read what the machine is doing."""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .errors import Fail

BUSY_STATES = ("printing", "paused")


class Moonraker:
    def __init__(self, url="http://127.0.0.1:7125", timeout=3.0):
        self.url, self.timeout = url.rstrip("/"), timeout
        self._estimates = {}             # filename -> slicer estimated_time (or None); files rarely change
        self._lock = threading.Lock()

    def _call(self, method, path, query=None):
        full = self.url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(full, method=method, data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 503:        # klippy is not ready - the caller decides what that means
                return {"error": "klippy_not_ready"}
            if e.code == 404:
                return {"error": "not_found"}
            raise Fail(f"Moonraker returned HTTP {e.code} for {path}")
        except (urllib.error.URLError, OSError, ValueError):
            raise Fail("Cannot reach Moonraker - is it running?")

    # ------------------------------------------------------------------ raw reads
    def query(self, objects):
        """{object name: status dict} for the named Klipper objects. Raises Fail if unreachable."""
        r = self._call("GET", "/printer/objects/query", {o: "" for o in objects})
        try:
            return r["result"]["status"]
        except (KeyError, TypeError):
            raise Fail("Klipper is not ready")

    def klippy_state(self):
        """'ready', 'startup', 'shutdown', 'error', ... or 'offline' when Moonraker is unreachable."""
        try:
            return self._call("GET", "/server/info")["result"].get("klippy_state", "unknown")
        except (Fail, KeyError, TypeError):
            return "offline"

    def estimated_time(self, filename):
        """Slicer time estimate (s) from the file's metadata, or None (laser/CNC files usually have none)."""
        if not filename:
            return None
        with self._lock:
            if filename in self._estimates:
                return self._estimates[filename]
        est = None
        try:
            md = self._call("GET", "/server/files/metadata", {"filename": filename}).get("result") or {}
            v = md.get("estimated_time")
            est = float(v) if v else None
        except (Fail, TypeError, ValueError):
            return None              # do not cache a failed lookup
        with self._lock:
            if len(self._estimates) > 200:
                self._estimates.clear()
            self._estimates[filename] = est
        return est

    def history(self, since=None, limit=50):
        """Finished and in-progress jobs, newest first: [{job_id, filename, status, start_time, end_time,
        print_duration, total_duration, filament_used}]. [] if the history component is off."""
        q = {"limit": limit, "order": "desc"}
        if since:
            q["since"] = since
        r = self._call("GET", "/server/history/list", q)
        return list((r.get("result") or {}).get("jobs") or [])

    def ui_theme(self):
        """Mainsail's appearance settings (Moonraker database, namespace "mainsail", key uiSettings):
        {"mode": "dark"|"light", "primary": "#rrggbb"}. Defaults to Mainsail's own defaults when the
        database or the key is missing; never raises."""
        out = {"mode": "dark", "primary": "#2196f3", "source": "default"}
        try:
            r = self._call("GET", "/server/database/item", {"namespace": "mainsail", "key": "uiSettings"})
            v = (r.get("result") or {}).get("value") or {}
        except Fail:
            return out
        if v.get("mode") in ("dark", "light"):
            out["mode"], out["source"] = v["mode"], "mainsail"
        p = str(v.get("primary") or "")
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", p):
            out["primary"], out["source"] = "#" + p.lstrip("#").lower(), "mainsail"
        return out

    # ------------------------------------------------------------------ portal status
    def status(self):
        """-> {online, klippy, print_state, mounted_slot, restart_blocked, job}; never raises.
        job is None unless a job is printing or paused: {filename, progress, print_duration,
        total_duration, estimated_time}."""
        out = {"online": False, "klippy": "unknown", "print_state": "unknown", "mounted_slot": 0,
               "restart_blocked": False, "job": None}
        k = self.klippy_state()
        if k == "offline":
            return out
        out.update(online=True, klippy=k)
        if k == "ready":
            try:
                objs = self.query(["print_stats", "virtual_sdcard", "gcode_macro SWAP_TOOL"])
                ps = objs.get("print_stats", {})
                out["print_state"] = ps.get("state", "unknown")
                out["mounted_slot"] = int((objs.get("gcode_macro SWAP_TOOL") or {}).get("current_tool", 0))
                if out["print_state"] in BUSY_STATES:
                    fn = ps.get("filename") or ""
                    out["job"] = {"filename": fn,
                                  "progress": float((objs.get("virtual_sdcard") or {}).get("progress") or 0.0),
                                  "print_duration": float(ps.get("print_duration") or 0.0),
                                  "total_duration": float(ps.get("total_duration") or 0.0),
                                  "estimated_time": self.estimated_time(fn)}
            except (Fail, KeyError, TypeError, ValueError):
                pass
        out["restart_blocked"] = out["print_state"] in BUSY_STATES
        return out

    # ------------------------------------------------------------------ jobs (Slice tab prototype)
    def _send(self, req, timeout, what):
        """Run a request; Klipper/Moonraker refusals come back as Fail with Klipper's own message."""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                msg = (json.loads(e.read().decode() or "{}").get("error") or {}).get("message") or ""
            except (ValueError, AttributeError, OSError):
                pass
            raise Fail(f"{what}: {msg}" if msg else f"{what}: Moonraker returned HTTP {e.code}")
        except (urllib.error.URLError, OSError, ValueError):
            raise Fail(f"{what}: cannot reach Moonraker - is it running?")

    def upload_gcode(self, filename, data):
        """Put a G-code file in Mainsail's G-Code Files list (Moonraker 'gcodes' root). Overwrites a file of
        the same name. -> the stored path, e.g. 'LightSaber-sign.gcode'."""
        boundary = "----rhino" + uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"root\"\r\n\r\ngcodes\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n".encode(), data, b"\r\n",
            f"--{boundary}--\r\n".encode()])
        req = urllib.request.Request(self.url + "/server/files/upload", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        r = self._send(req, 60, "Upload failed")
        item = (r.get("result") or r).get("item") or {}
        return item.get("path") or filename

    def gcode_store(self, count=200):
        """Klipper's recent console lines, oldest first: [{"message", "time", "type"}]. [] if unavailable."""
        try:
            r = self._call("GET", "/server/gcode_store", {"count": count})
        except Fail:
            return []
        return list((r.get("result") or {}).get("gcode_store") or [])

    def run_gcode(self, script, timeout=30):
        """Run a G-code command the way the Mainsail console does; returns when Klipper has finished it.
        Klipper's error, if any, comes back as Fail."""
        req = urllib.request.Request(self.url + "/printer/gcode/script?" + urllib.parse.urlencode({"script": script}),
                                     data=b"", method="POST")
        self._send(req, timeout, "Klipper refused it")
        return {"ok": True}

    def restart(self):
        """FIRMWARE_RESTART so brand-new output pins are configured. Never while a job is running."""
        st = self.status()
        if not st["online"]:
            raise Fail("Cannot reach Moonraker - restart Klipper from Mainsail instead.")
        if st["restart_blocked"]:
            raise Fail(f"A job is {st['print_state']}. Restarting now would kill it - wait until it is finished.")
        self._call("POST", "/printer/firmware_restart")
        return {"ok": True}


def job_timing(job, paused_s=0.0, now_paused=False):
    """Remaining-time estimate for the banner: {elapsed, remaining, method} (seconds; None if unknown).

    * slicer:  the file's estimated_time minus print_duration (Klipper only starts print_duration at
               the first extrusion, so this only works for 3D prints)
    * file:    time actually running divided by progress - what Mainsail calls the file estimate. Used
               for laser / CNC / cutter jobs, which have no slicer estimate and no extrusion.
    """
    if not job:
        return None
    total = float(job.get("total_duration") or 0.0)
    running = max(total - float(paused_s or 0.0), 0.0)
    pd, est, prog = float(job.get("print_duration") or 0.0), job.get("estimated_time"), float(job.get("progress") or 0.0)
    if est and pd > 0:
        return {"elapsed": total, "remaining": max(est - pd, 0.0), "method": "slicer"}
    if prog >= 0.02:
        return {"elapsed": total, "remaining": max(running / prog - running, 0.0), "method": "file"}
    return {"elapsed": total, "remaining": None, "method": "none"}
