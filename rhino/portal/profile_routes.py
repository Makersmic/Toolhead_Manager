"""Slice profiles and per-file Prepare jobs (Tool Manager 1.8). See rhino/slice_profiles.py and
docs/phase1-slice-profiles.md. Reads are GETs; writes are token-checked (security.check_write).
Every change is a POST or DELETE, as everywhere in the Portal. Nothing here talks to Klipper."""
from flask import Blueprint, current_app, jsonify, request

from ..errors import Fail
from . import security

bp = Blueprint("profiles", __name__)


def _svc():
    return current_app.config["PROFILES"]


def _rev(b):
    r = b.get("rev")
    if isinstance(r, bool) or not isinstance(r, int):
        raise Fail("Save needs the revision it started from")
    return r


@bp.get("/api/slice-profiles")
def listing():
    s = _svc()
    st = s.state()
    try:
        st["deleted"] = s.deleted()
    except Fail:
        st["deleted"] = []
    return jsonify(st)


@bp.get("/api/slice-profiles/<pid>")
def one(pid):
    return jsonify({"ok": True, "profile": _svc().get(pid)})


@bp.post("/api/slice-profiles")
def create():
    security.check_write()
    return jsonify({"ok": True, "profile": _svc().create(security.json_body())})


@bp.post("/api/slice-profiles/<pid>")
def save(pid):
    security.check_write()
    b = security.json_body()
    return jsonify({"ok": True, "profile": _svc().save(pid, b.get("profile"), _rev(b))})


@bp.delete("/api/slice-profiles/<pid>")
def delete(pid):
    security.check_write()
    return jsonify({"ok": True, **_svc().delete(pid)})


@bp.get("/api/slice-profiles/<pid>/history")
def history(pid):
    return jsonify({"ok": True, "revisions": _svc().history(pid)})


@bp.post("/api/slice-profiles/<pid>/revert")
def revert(pid):
    security.check_write()
    b = security.json_body()
    to = b.get("to")
    if isinstance(to, bool) or not isinstance(to, int):
        raise Fail("Say which revision to go back to")
    return jsonify({"ok": True, "profile": _svc().revert(pid, to)})


@bp.post("/api/slice-profiles/<pid>/undelete")
def undelete(pid):
    security.check_write()
    return jsonify({"ok": True, "profile": _svc().undelete(pid)})


@bp.get("/api/slice-profiles-export")
def export():
    pid = request.args.get("id") or None
    data = _svc().export(pid)
    r = jsonify(data)
    r.headers["Content-Disposition"] = f'attachment; filename="rhino-slice-profiles{"-" + pid if pid else ""}.json"'
    return r


@bp.post("/api/slice-profiles-import")
def import_():
    security.check_write()
    return jsonify({"ok": True, "added": _svc().import_(security.json_body())})


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
