"""Tuned heater values (Wizards > Tune a heater in Rhino Studio). All the rules are in rhino/tuned.py.

GET  /api/tuned        {rev, pid: {"extruder": {kp, ki, kd, at, previous}, ...}, restart_needed}
POST /api/tuned/pid    (token) {rev, heater, kp, ki, kd}   keep a heater's PID values (writes myrhino/tuned.cfg; marks a restart pending)
POST /api/tuned/accelerometer (token) {rev, serial, cs_pin, spi_bus, axes_map, probe: {x, y, z}}   the USB accelerometer's board (tuned.cfg)
POST /api/tuned/accelerometer/clear (token) {rev}   take the accelerometer out of tuned.cfg (do this, restart Klipper, then unplug the board)
POST /api/tuned/shaper (token) {rev, head, x: {type, freq}, y: {type, freq}, max_accel}   keep an input shaper pick for a print head
POST /api/tuned/shaper/clear (token) {rev, head}
GET  /api/resonance-data?axis=x&name=rhino_x   the CSV SHAPER_CALIBRATE wrote (read only; only /tmp/calibration_data_<axis>_<name>.csv, up to 2 MB)
POST /api/tuned/clear  (token) {rev, heater}               forget them: the heater goes back to its own config
Nothing here restarts Klipper or sends anything to Moonraker.
"""
import os
import re

from flask import Blueprint, Response, current_app, jsonify, request

from ..errors import Fail
from ..tuned import Tuned
from . import security

bp = Blueprint("tuned", __name__)


def _svc():
    return current_app.config["SERVICE"]


def _tuned():
    return Tuned(current_app.config["PATHS"])


def _heaters():
    """The heater keys Klipper has: 'extruder', 'heater_bed' and each heater_generic's own name."""
    return set(_svc()._hook_known().heater_max)


@bp.get("/api/tuned")
def state():
    return jsonify(_tuned().state())


@bp.post("/api/tuned/pid")
def pid():
    security.check_write()
    return jsonify(_tuned().set_pid(security.json_body(), _heaters()))


@bp.post("/api/tuned/clear")
def clear():
    security.check_write()
    return jsonify(_tuned().clear(security.json_body(), _heaters()))


@bp.post("/api/tuned/accelerometer")
def accelerometer():
    security.check_write()
    return jsonify(_tuned().set_accelerometer(security.json_body(), _heaters()))


@bp.post("/api/tuned/accelerometer/clear")
def accelerometer_clear():
    security.check_write()
    return jsonify(_tuned().clear_accelerometer(security.json_body(), _heaters()))


@bp.post("/api/tuned/shaper")
def shaper():
    security.check_write()
    return jsonify(_tuned().set_shaper(security.json_body(), _heaters()))


@bp.post("/api/tuned/shaper/clear")
def shaper_clear():
    security.check_write()
    return jsonify(_tuned().clear_shaper(security.json_body(), _heaters()))


@bp.get("/api/resonance-data")
def resonance_data():
    """Klipper writes SHAPER_CALIBRATE's raw data to /tmp, outside Moonraker's file roots. This reads exactly one kind of file from there."""
    axis, name = request.args.get("axis", ""), request.args.get("name", "")
    if axis not in ("x", "y") or not re.match(r"^[A-Za-z0-9_-]{1,40}$", name):
        raise Fail("Which axis and which run?")
    path = os.path.join(os.environ.get("RHINO_RESONANCE_DIR", "/tmp"), f"calibration_data_{axis}_{name}.csv")
    try:
        if os.path.islink(path) or os.path.getsize(path) > 2 * 1024 * 1024:
            raise Fail("That data file isn't usable.")
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        raise Fail("That run's data isn't on the Rhino (run the measurement again).")
    return Response(text, mimetype="text/plain")
