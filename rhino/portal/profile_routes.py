"""Slice profiles and per-file Prepare jobs (Tool Manager 1.8). See rhino/slice_profiles.py and
docs/phase1-slice-profiles.md. Reads are GETs; writes are token-checked (security.check_write).
Every change is a POST or DELETE, as everywhere in the Portal. Nothing here talks to Klipper."""
from flask import Blueprint, current_app, jsonify

from . import security
from .store_routes import add_store_routes

bp = Blueprint("profiles", __name__)


def _svc():
    return current_app.config["PROFILES"]


add_store_routes(bp, "slice-profiles", "PROFILES", "profile", "rhino-slice-profiles")


@bp.get("/api/prepare-jobs")
def jobs():
    return jsonify({"ok": True, "jobs": _svc().jobs()})


@bp.post("/api/prepare-jobs")
def save_job():
    security.check_write()
    b = security.json_body()
    return jsonify({"ok": True, "job": _svc().save_job(b.get("file"), b.get("job"))})


@bp.delete("/api/prepare-jobs")
def delete_job():
    security.check_write()
    b = security.json_body()
    return jsonify({"ok": True, **_svc().delete_job(str(b.get("file", "")))})
