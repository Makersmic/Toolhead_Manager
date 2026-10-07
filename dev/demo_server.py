#!/usr/bin/env python3
"""Run the portal against a throw-away copy of this config and a fake Moonraker, for trying the
screens (and taking the guide's screenshots) without a printer.

    python3 dev/demo_server.py [--port 5055]

The fake Moonraker listens on a random port; change what it reports with
    curl -X POST 'http://127.0.0.1:<port>/__set?print_state=printing&progress=0.47'
Keys: print_state, progress, filename, print_duration, total_duration, estimated_time,
current_tool, klippy, extruder_target, laser, spindle, ui_mode (dark/light/none), ui_primary.
POST /__job?filename=..&status=completed&total_duration=..&start_time=.. adds a finished job.
"""
import argparse
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = {"klippy": "ready", "print_state": "standby", "progress": 0.0, "filename": "", "print_duration": 0.0,
         "total_duration": 0.0, "estimated_time": 0.0, "current_tool": 1, "extruder_target": 0.0,
         "laser": 0.0, "spindle": 0.0, "restarts": 0, "jobs": [],
         "ui_mode": "dark", "ui_primary": "#2196f3"}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if u.path == "/server/info":
            return self._send(200, {"result": {"klippy_state": STATE["klippy"]}})
        if STATE["klippy"] != "ready" and u.path.startswith("/printer"):
            return self._send(503, {})
        if u.path == "/printer/objects/query":
            st = {"print_stats": {"state": STATE["print_state"], "filename": STATE["filename"],
                                  "print_duration": STATE["print_duration"], "total_duration": STATE["total_duration"]},
                  "virtual_sdcard": {"progress": STATE["progress"]},
                  "gcode_macro SWAP_TOOL": {"current_tool": STATE["current_tool"]},
                  "extruder": {"target": STATE["extruder_target"], "temperature": 25.0},
                  "output_pin SERVO_LASER": {"value": STATE["laser"]},
                  "output_pin LASER_INITIALIZE": {"value": 1.0 if STATE["laser"] else 0.0},
                  "output_pin Spindle_power": {"value": STATE["spindle"]},
                  "gcode_macro TOOL_POWER_STATE": {"active": 0}}
            return self._send(200, {"result": {"status": {k: v for k, v in st.items() if k in q}}})
        if u.path == "/server/files/metadata":
            return self._send(200, {"result": {"estimated_time": STATE["estimated_time"] or None}})
        if u.path == "/server/database/item":
            if STATE.get("ui_mode") == "none":
                return self._send(404, {})
            return self._send(200, {"result": {"namespace": "mainsail", "key": "uiSettings",
                                               "value": {"mode": STATE["ui_mode"], "primary": STATE["ui_primary"],
                                                         "theme": "mainsail", "logo": "#D41216"}}})
        if u.path == "/server/history/list":
            return self._send(200, {"result": {"jobs": list(reversed(STATE["jobs"]))}})
        self._send(404, {})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/printer/firmware_restart":
            STATE["restarts"] += 1
            return self._send(200, {"result": "ok"})
        if u.path == "/__set":
            for k, v in urllib.parse.parse_qs(u.query).items():
                cur = STATE.get(k)
                STATE[k] = type(cur)(v[0]) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else v[0]
            return self._send(200, STATE)
        if u.path == "/__job":     # append a finished job to the history
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            now = time.time()
            dur = float(q.get("total_duration", 3600))
            end = float(q.get("end_time", now))
            STATE["jobs"].append({"job_id": f"{len(STATE['jobs']) + 1:06X}", "filename": q.get("filename", "part.gcode"),
                                  "status": q.get("status", "completed"), "start_time": end - dur, "end_time": end,
                                  "print_duration": dur, "total_duration": dur, "filament_used": float(q.get("filament_used", 0))})
            return self._send(200, {"ok": True})
        self._send(404, {})


def start_fake():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def make_config(root=None):
    root = root or tempfile.mkdtemp(prefix="rhino-demo-")
    cfg = os.path.join(root, "printer_data", "config")
    shutil.copytree(os.path.dirname(HERE), cfg, ignore=shutil.ignore_patterns("__pycache__", "registry_backups", ".git",
                                                                             "custom_tools.json", "maintenance"))
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5055)
    ap.add_argument("--monitor-interval", type=float, default=2.0)
    a = ap.parse_args()
    cfg = make_config()
    sys.path.insert(0, cfg)
    from rhino.portal import create_app
    fake = start_fake()
    app = create_app(cfg, f"http://127.0.0.1:{fake.server_port}", start_monitor=True)
    app.config["MONITOR"].interval = a.monitor_interval
    print(f"portal http://127.0.0.1:{a.port}  fake moonraker http://127.0.0.1:{fake.server_port}  config {cfg}", flush=True)
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
