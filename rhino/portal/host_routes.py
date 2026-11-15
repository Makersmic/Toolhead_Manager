"""Settings > Host health in Rhino Studio: temperatures, cores, memory, disks and processes of the host.

GET /api/host/stats    rhino.hoststats.snapshot(): read only, nothing run, nothing written.
Moonraker already reports the per-core load each second; this is what it doesn't.
GET /api/host/extras   the Klipper extras this package ships, and whether their links into klippy/extras are in place.
POST /api/host/extras/relink   make or mend those links (token; the user owns ~/klipper, no sudo). Klipper picks them
                        up at its next restart.
"""
import os

from flask import Blueprint, current_app, jsonify

from . import security
from .. import hoststats, klipper_extras

bp = Blueprint("host", __name__)


@bp.get("/api/host/stats")
def stats():
    cfg = current_app.config["PATHS"].cfg
    data = os.path.dirname(os.path.abspath(cfg))  # ~/printer_data
    places = [("System disk", "/"), ("printer_data", data)]
    return jsonify(hoststats.snapshot("/", places))


@bp.get("/api/host/extras")
def extras():
    return jsonify(klipper_extras.status(current_app.config["PATHS"].cfg))


@bp.post("/api/host/extras/relink")
def extras_relink():
    security.check_write()
    return jsonify(klipper_extras.relink(current_app.config["PATHS"].cfg))
