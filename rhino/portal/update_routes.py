"""Install a release zip from Rhino Studio (config 1.5.3).

The Portal never installs anything itself and never runs sudo. It only:
  * checks an uploaded zip and keeps it in rhino_data/update/incoming,
  * writes rhino_data/update/request.json, which starts the root-owned updater
    (scripts/rhino_update_helper.py as /usr/local/sbin/rhino-update, via rhino-update.path),
  * reads rhino_data/update/status.json, which the updater writes as it goes.
The zip check is the updater's own (check_zip), loaded from the file next to this package;
the updater checks its own copy again before using it.

GET  /api/update              what's installed, the zips kept, the last run (status.json), whether the updater is set up
POST /api/update/upload       multipart "zip": check and keep it (nothing is installed)
POST /api/update/install      {"zip": "rhino-config-1.5.3.zip"}: ask the updater to install it (also "Go back")
"""
import importlib.util
import json
import os
import re
import tempfile
import time

from flask import Blueprint, current_app, jsonify, request

from . import security
from .. import __version__
from ..errors import Fail

bp = Blueprint("update", __name__)
ZIP_RE = re.compile(r"^rhino-config-(\d+\.\d+\.\d+)\.zip$")
UNIT = os.environ.get("RHINO_UPDATE_UNIT", "/etc/systemd/system/rhino-update.path")
STALE = 50 * 60  # a run that hasn't written status for this long has died


def _helper():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location("rhino_update_helper", os.path.join(here, "scripts", "rhino_update_helper.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def drop_dir():
    return os.path.join(current_app.config["PATHS"].state_dir, "update")


def _incoming():
    d = os.path.join(drop_dir(), "incoming")
    os.makedirs(d, exist_ok=True)
    return d


def read_status():
    try:
        with open(os.path.join(drop_dir(), "status.json")) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"state": "idle"}
    if st.get("state") == "running" and time.time() - float(st.get("updated") or 0) > STALE:
        st["state"] = "failed"
        st["error"] = "The updater stopped answering. See: journalctl -u rhino-update -n 50"
    return st


def installed_version():
    try:
        with open(os.path.expanduser("~/rhino-manager/installed-version")) as f:
            return f.read().strip() or __version__
    except OSError:
        return __version__


def _zips():
    out = []
    d = _incoming()
    for n in sorted(os.listdir(d)):
        m = ZIP_RE.match(n)
        if m:
            p = os.path.join(d, n)
            out.append({"zip": n, "version": m.group(1), "size": os.path.getsize(p), "at": os.path.getmtime(p)})
    return out


def _busy():
    st = read_status()
    return st.get("state") == "running" or os.path.exists(os.path.join(drop_dir(), "request.json"))


def _job_state():
    try:
        return current_app.config["MOONRAKER"].status().get("print_state", "standby")
    except Exception:
        return "unknown"


@bp.get("/api/update")
def state():
    return jsonify({
        "ok": True,
        "installed": installed_version(),
        "helper": os.path.exists(UNIT),
        "zips": _zips(),
        "busy": _busy(),
        "status": read_status(),
    })


@bp.post("/api/update/upload")
def upload():
    security.check_write()
    f = request.files.get("zip")
    if not f or not f.filename:
        raise Fail("Send the zip (rhino-config-<version>.zip).")
    if _busy():
        raise Fail("An install is running. Wait for it to finish.")
    d = _incoming()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".upload-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        try:
            version = _helper().check_zip(tmp)
        except ValueError as e:
            raise Fail(str(e))
        name = f"rhino-config-{version}.zip"
        os.replace(tmp, os.path.join(d, name))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return jsonify({"ok": True, "zip": name, "version": version, "installed": installed_version()})


@bp.post("/api/update/install")
def install():
    security.check_write()
    body = security.json_body()
    name = str(body.get("zip", ""))
    if not ZIP_RE.match(name) or not os.path.isfile(os.path.join(_incoming(), name)):
        raise Fail("That zip isn't here. Upload it again.")
    if not os.path.exists(UNIT):
        raise Fail("The updater isn't set up on this Rhino yet. Install this zip once by hand (rhino.sh option 3); "
                   "after that, Studio can install the next ones.")
    if _busy():
        raise Fail("An install is already running.")
    js = _job_state()
    if js in ("printing", "paused"):
        raise Fail(f"A job is {js}. Finish or cancel it first.")
    d = drop_dir()
    # the updater's status is replaced as soon as it starts; say "waiting" until then
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".status-")
    with os.fdopen(fd, "w") as out:
        json.dump({"state": "running", "zip": name, "version": ZIP_RE.match(name).group(1), "from_version": installed_version(),
                   "step": -1, "step_name": "Waiting for the updater", "started": time.time(), "updated": time.time(), "log": []}, out)
    os.replace(tmp, os.path.join(d, "status.json"))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".request-")
    with os.fdopen(fd, "w") as out:
        json.dump({"zip": name, "at": time.time()}, out)
    os.replace(tmp, os.path.join(d, "request.json"))  # rhino-update.path starts the updater now
    return jsonify({"ok": True, "zip": name})
