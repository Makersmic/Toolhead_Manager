"""Add hardware wizard (docs/hardware-coverage.md).

    GET    /api/hardware/catalog               step 1: device, pin-kind, sensor-type and menu tables (read-only)
    GET    /api/hardware/pins?kind=&sensor=    step 2: free pins that can do a pin kind, with capabilities and warnings
    POST   /api/hardware/pins/check            step 2: one typed pin {"pin", "kind", "sensor"?, "isolated"?} (writes nothing)
    GET    /api/hardware/boards                step 2: board presets, added boards, USB serial ports
    POST   /api/hardware/boards                add or change a second board ([mcu name]; "original" = its name)
    POST   /api/preview/hardware/boards        check one (writes nothing, returns the .cfg lines)
    DELETE /api/hardware/boards/<name>         remove an added board nothing uses
    GET    /api/hardware/devices               steps 3/5: hardware added with the wizard
    POST   /api/hardware/devices               add or replace one {"device", "name", "pins", ...; "original"?}
    POST   /api/preview/hardware/devices       check one, return the exact .cfg text (writes nothing)
    DELETE /api/hardware/devices/<name>
"""
from flask import Blueprint, jsonify, request

from .. import hw_catalog
from . import security
from .routes import _svc, _write

bp = Blueprint("hw_catalog", __name__)


@bp.get("/api/hardware/catalog")
def catalog():
    return jsonify({"ok": True, **hw_catalog.for_ui()})


@bp.get("/api/hardware/pins")
def pins():
    return jsonify(_svc().pin_choices(request.args.get("kind", ""), request.args.get("sensor") or None,
                                      request.args.get("exclude_hw") or None))


@bp.post("/api/hardware/pins/check")
def pin_check():
    return jsonify(_svc().pin_check(security.json_body()))


@bp.get("/api/hardware/boards")
def boards():
    return jsonify(_svc().boards_list())


@bp.post("/api/hardware/boards")
def board_save():
    return _write(lambda: _svc().board_save(security.json_body()), lambda r: f"board {r['name']} saved")


@bp.post("/api/preview/hardware/boards")
def board_preview():
    security.check_write()
    return jsonify(_svc().board_save(security.json_body(), dry_run=True))


@bp.delete("/api/hardware/boards/<name>")
def board_remove(name):
    return _write(lambda: _svc().board_remove(name), lambda r: f"board {r['name']} removed")


@bp.get("/api/hardware/devices")
def devices():
    return jsonify(_svc().devices_list())


@bp.post("/api/hardware/devices")
def device_save():
    return _write(lambda: _svc().device_save(security.json_body()), lambda r: f"hardware {r['name']} saved")


@bp.post("/api/preview/hardware/devices")
def device_preview():
    security.check_write()
    return jsonify(_svc().device_save(security.json_body(), dry_run=True))


@bp.delete("/api/hardware/devices/<name>")
def device_remove(name):
    return _write(lambda: _svc().device_remove(name), lambda r: f"hardware {r['name']} removed")
