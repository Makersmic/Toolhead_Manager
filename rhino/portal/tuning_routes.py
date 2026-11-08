"""Tuning results (1.9.16): stored here, found by Rhino Studio's tuning wizards. See rhino/tuning.py. Reads are GETs;
writes are token-checked POSTs. Nothing here talks to Klipper."""
from flask import Blueprint, current_app, jsonify

from . import security

bp = Blueprint("tuning", __name__)


def _svc():
    return current_app.config["TUNING"]


@bp.get("/api/tuning")
def state():
    return jsonify(_svc().state())


@bp.post("/api/tuning/result")
def result():
    security.check_write()
    return jsonify({"ok": True, **_svc().save_result(security.json_body())})


@bp.post("/api/tuning/clear")
def clear():
    security.check_write()
    return jsonify({"ok": True, **_svc().clear(security.json_body())})
