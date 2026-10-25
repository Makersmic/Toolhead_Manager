"""Back up now and restore (Tool Manager 1.7). See rhino/backup.py and docs/phase2-backup.md.

Reads are GETs. Writes are token-checked POSTs (security.check_write). Backup and restore are both
refused during a job (Moonraker refuses its own database backup and restore while printing too).
After "Back up now" the GitHub push (klipper-backup) runs in the background; GET /api/backup shows its
result, and never calls a push done that wasn't (INV-B8)."""
import threading

from flask import Blueprint, current_app, jsonify, request, send_file

from ..backup import ITEMS, KEEP, github_status
from ..errors import Fail
from . import security

bp = Blueprint("backup", __name__)
_push = {"running": False}


def _svc():
    return current_app.config["BACKUP"]


def _push_in_background(svc, msg):
    if _push["running"]:
        return

    def go():
        try:
            svc.push_github(msg)
        finally:
            _push["running"] = False
    _push["running"] = True
    threading.Thread(target=go, daemon=True).start()


@bp.get("/api/backup")
def listing():
    svc = _svc()
    gh = github_status(svc.paths.state_dir, svc.home)
    gh["running"] = _push["running"]
    return jsonify({"ok": True, "archives": svc.list(), "keep": KEEP, "folder": svc.dir, "github": gh,
                    "items": {k: v["label"] for k, v in ITEMS.items()}})


@bp.post("/api/backup")
def now():
    security.check_write()
    svc = _svc()
    made = svc.create("button")
    _push_in_background(svc, "rhino_backup_now")
    return jsonify({"ok": True, "archive": made})


@bp.get("/api/backup/file/<name>")
def download(name):
    return send_file(_svc().path_for_download(name), as_attachment=True, download_name=name)


@bp.post("/api/backup/upload")
def upload():
    security.check_write()
    up = request.files.get("archive")
    if up is None:
        raise Fail("No backup file was sent")
    return jsonify({"ok": True, "archive": _svc().add_upload(up.filename, up.read())})


@bp.post("/api/restore/plan")
def plan():
    b = security.json_body()
    return jsonify({"ok": True, "plan": _svc().plan(str(b.get("archive", "")), str(b.get("item", "")))})


@bp.post("/api/restore")
def restore():
    security.check_write()
    b = security.json_body()
    r = _svc().restore(str(b.get("archive", "")), str(b.get("item", "")), str(b.get("confirm", "")),
                       maint=current_app.config.get("MAINT"))
    return jsonify(r)
