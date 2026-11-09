"""Settings > Host health in Rhino Studio: temperatures, cores, memory, disks and processes of the host.

GET /api/host/stats    rhino.hoststats.snapshot(): read only, nothing run, nothing written.
Moonraker already reports the per-core load each second; this is what it doesn't.
"""
import os

from flask import Blueprint, current_app, jsonify

from .. import hoststats

bp = Blueprint("host", __name__)


@bp.get("/api/host/stats")
def stats():
    cfg = current_app.config["PATHS"].cfg
    data = os.path.dirname(os.path.abspath(cfg))  # ~/printer_data
    places = [("System disk", "/"), ("printer_data", data)]
    return jsonify(hoststats.snapshot("/", places))
