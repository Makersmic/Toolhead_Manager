"""Settings > Health check in Rhino Studio: the health check (scripts/rhino_doctor.py, menu option 7) run from a page.

GET  /api/health       the last result {ok, running, at, result}; nothing run. `result` is what `rhino_doctor.py --json`
                       printed: counts, facts and a list of {section, level, what, detail}; None before the first run.
POST /api/health/run   (token) start the check in the background and return at once; Studio asks GET until it is done.
                       One at a time. The check only reads (it changes nothing, needs no sudo) and takes a few seconds.

The check runs as a separate program, as it does from the menu, so a check that hangs or fails can't take the Portal with
it: it has 90 seconds, then it is stopped and the page says so. The result is kept in memory (the Portal restarting clears it).
"""
import json
import os
import subprocess
import sys
import threading
import time

from flask import Blueprint, current_app, jsonify, request

from . import security

bp = Blueprint("health", __name__)
TIMEOUT = 90
_lock = threading.Lock()
_state = {"running": False, "at": None, "result": None, "error": None}


def _run(script, env):
    """Run the check, keep what it says. Never raises."""
    result, error = None, None
    try:
        p = subprocess.run([sys.executable, script, "--json"], capture_output=True, text=True, timeout=TIMEOUT, env=env)
        try:
            result = json.loads(p.stdout)
        except ValueError:
            error = "The health check didn't give a result" + (f": {p.stderr.strip()[-200:]}" if p.stderr.strip() else ".")
    except subprocess.TimeoutExpired:
        error = f"The health check took longer than {TIMEOUT} seconds and was stopped."
    except OSError as e:
        error = f"The health check couldn't start: {e}"
    with _lock:
        _state.update(running=False, at=time.time(), result=result, error=error)


@bp.get("/api/health")
def state():
    with _lock:
        return jsonify({"ok": True, **_state})


@bp.post("/api/health/run")
def run():
    security.check_write()
    paths = current_app.config["PATHS"]
    script = os.path.join(paths.cfg, "scripts", "rhino_doctor.py")
    if not os.path.isfile(script):
        return security.error("The health check program isn't in the config folder (scripts/rhino_doctor.py). Install the release again (rhino.sh option 3).")
    env = dict(os.environ, RHINO_CONFIG_DIR=paths.cfg, PYTHONDONTWRITEBYTECODE="1",
               RHINO_PORTAL=f"http://127.0.0.1:{request.environ.get('SERVER_PORT') or 5000}")
    mr = current_app.config.get("MOONRAKER")
    if mr is not None and getattr(mr, "url", None):
        env["RHINO_MOONRAKER"] = mr.url
    with _lock:
        if _state["running"]:
            return jsonify({"ok": True, **_state})
        _state.update(running=True, error=None)
    threading.Thread(target=_run, args=(script, env), name="rhino-health", daemon=True).start()
    with _lock:
        return jsonify({"ok": True, **_state})
