"""Add hardware wizard catalog (docs/hardware-coverage.md, step 1). Read-only: one GET that hands Studio
the device, pin-kind, sensor-type and menu tables from rhino/hw_catalog.py. Nothing here writes."""
from flask import Blueprint, jsonify

from .. import hw_catalog

bp = Blueprint("hw_catalog", __name__)


@bp.get("/api/hardware/catalog")
def catalog():
    return jsonify({"ok": True, **hw_catalog.for_ui()})
