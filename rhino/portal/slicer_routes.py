"""PrusaSlicer on the Rhino, for Rhino Studio (config 1.5.0; Flathub engine 1.5.2). See rhino/prusa.py.

Reads are plain GETs. Starting or cancelling a slice and installing the engine are token-checked
POSTs (security.check_write); the slice upload is multipart (the part as STL, the settings as INI)."""
import time

from flask import Blueprint, current_app, jsonify, request, send_file

from ..errors import Fail
from . import security

bp = Blueprint("slicer", __name__)


def _svc():
    return current_app.config["PRUSA"]


@bp.get("/api/slicer")
def state():
    return jsonify({"ok": True, **_svc().state()})


@bp.get("/api/slicer/keys")
def keys():
    return jsonify({"ok": True, "keys": _svc().keys()})


@bp.post("/api/slicer/slice")
def slice_():
    security.check_write()
    model = request.files.get("model")
    config = request.files.get("config")
    if not model or not config:
        raise Fail("Send the part (model) and the settings (config).")
    job = _svc().submit(model.read(), config.read().decode("utf-8", "replace"), request.form.get("name", "part"),
                        request.form.get("center", ""))
    return jsonify({"ok": True, **job})


@bp.get("/api/slicer/jobs/<jid>")
def job(jid):
    return jsonify({"ok": True, **_svc().job(jid)})


@bp.get("/api/slicer/jobs/<jid>/gcode")
def gcode(jid):
    return send_file(_svc().gcode_path(jid), mimetype="text/plain", as_attachment=False)


@bp.post("/api/slicer/jobs/<jid>/cancel")
def cancel(jid):
    security.check_write()
    return jsonify(_svc().cancel(jid))


@bp.post("/api/slicer/engine/check")
def check():
    security.check_write()
    _svc().latest(force=True)
    return jsonify({"ok": True, **_svc().state()})


@bp.post("/api/slicer/engine/update")
def update():
    security.check_write()
    return jsonify(_svc().install_latest())


@bp.post("/api/slicer/engine/rollback")
def rollback():
    security.check_write()
    return jsonify(_svc().roll_back())


@bp.post("/api/slicer/engine/auto")
def auto():
    """{"on": true|false}: keep PrusaSlicer up to date by itself while it's being used (1.5.8)."""
    security.check_write()
    return jsonify({"ok": True, "auto": _svc().set_auto(bool(security.json_body().get("on")))})


class AutoUpdater:
    """Monitor listener: lets the engine look for updates now and then (it does the waiting itself)."""
    def __init__(self, svc):
        self.svc = svc

    def objects(self):
        return []

    def on_tick(self, snap, prev):
        self.svc.auto_tick()


def printer_state_from(moonraker, every=2.0):
    """print_state from Moonraker, asked at most every `every` seconds (the watchdog asks twice a second)."""
    memo = {"at": 0.0, "v": "standby"}
    def get():
        if time.time() - memo["at"] > every:
            try:
                memo["v"] = moonraker.status().get("print_state", "standby")
            except Exception:
                memo["v"] = "unknown"
            memo["at"] = time.time()
        return memo["v"]
    return get
