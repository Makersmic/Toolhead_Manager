"""Maintenance HTTP API (same rules as routes.py: every change is a POST/DELETE with the token).

    GET  /api/maint                      tasks with status, areas, meters, counts
    GET  /api/maint/history              completions, skips and meter changes (newest first)
    GET  /api/maint/library              starter tasks that fit this machine and its tools
    POST /api/maint/library              {"picks": [{"key", "asset"}]} add starter tasks
    POST /api/maint/tasks                create
    POST /api/maint/tasks/<id>           update
    DELETE /api/maint/tasks/<id>         delete
    POST /api/maint/tasks/<id>/done      {"action": "done"|"skipped", "date", "notes"}
    POST /api/maint/tasks/<id>/snooze    {"days": 0..90}  (0 cancels a snooze)
    POST /api/maint/meters               {"scope", "tool", "meter", "value", "note"} set a reading
    POST /api/maint/areas                {"areas": [{"id", "label"}]}
    POST /api/maint/settings             {"boot_reminder": bool}
    POST /api/maint/tasks/<id>/status    {"status": custom status id or "" to clear, "note"}
    POST /api/maint/tasks/<id>/to-library  make a task a Task Library task (and link it)
    GET  /api/maint/lists                kinds of work, priorities, areas, status codes (Admin screen)
    POST /api/maint/lists                {"types": [{"id", "label"}], "priorities": {"low": "..."}}
    POST /api/maint/statuses             {"builtin": {id: {label, color}}, "custom": [...]}
    GET  /api/maint/tasklib              Task Library: library tasks and Task Books
    POST /api/maint/templates[/<id>]     create / edit a library task (edits update every linked task)
    DELETE /api/maint/templates/<id>     (tasks made from it are kept, unlinked)
    POST /api/maint/templates/<id>/assign  {"asset"}  add it to one asset
    POST /api/maint/books[/<id>]         create / edit a Task Book {"name", "description", "templates"}
    DELETE /api/maint/books/<id>
    POST /api/maint/books/<id>/assign    {"asset", "on": true|false}  ("machine" = the whole machine)
"""
import threading

from flask import Blueprint, current_app, jsonify, request

from . import security

bp = Blueprint("maint", __name__)
_lock = threading.Lock()


def _m():
    return current_app.config["MAINT"]


def _write(fn):
    security.check_write()
    with _lock:
        return jsonify(fn())


@bp.get("/api/maint")
def overview():
    return jsonify(_m().overview())


@bp.get("/api/maint/history")
def history():
    recs = list(reversed(_m()._load_history()))
    asset = request.args.get("asset")
    if asset:
        recs = [r for r in recs if r.get("asset") == asset]
    return jsonify({"ok": True, "records": recs[:500]})


@bp.get("/api/maint/library")
def library():
    return jsonify(_m().library_view())


@bp.post("/api/maint/library")
def library_add():
    return _write(lambda: _m().library_add(security.json_body().get("picks")))


@bp.post("/api/maint/tasks")
def create():
    return _write(lambda: _m().create(security.json_body()))


@bp.post("/api/maint/tasks/<tid>")
def update(tid):
    return _write(lambda: _m().update(tid, security.json_body()))


@bp.delete("/api/maint/tasks/<tid>")
def delete(tid):
    return _write(lambda: _m().delete(tid))


@bp.post("/api/maint/tasks/<tid>/done")
def done(tid):
    return _write(lambda: _m().complete(tid, security.json_body()))


@bp.post("/api/maint/tasks/<tid>/snooze")
def snooze(tid):
    return _write(lambda: _m().snooze(tid, security.json_body().get("days", 0)))


@bp.post("/api/maint/meters")
def meters():
    return _write(lambda: _m().adjust_meter(security.json_body()))


@bp.post("/api/maint/areas")
def areas():
    return _write(lambda: _m().save_areas(security.json_body().get("areas")))


@bp.post("/api/maint/settings")
def settings():
    return _write(lambda: _m().save_settings(security.json_body()))


@bp.post("/api/maint/tasks/<tid>/status")
def set_status(tid):
    return _write(lambda: _m().set_status(tid, security.json_body()))


@bp.post("/api/maint/tasks/<tid>/to-library")
def to_library(tid):
    return _write(lambda: _m().template_from_task(tid))


@bp.get("/api/maint/lists")
def lists_view():
    return jsonify(_m().lists_view())


@bp.post("/api/maint/lists")
def lists_save():
    return _write(lambda: _m().save_lists(security.json_body()))


@bp.post("/api/maint/statuses")
def statuses():
    return _write(lambda: _m().save_statuses(security.json_body()))


@bp.get("/api/maint/tasklib")
def tasklib():
    return jsonify(_m().library())


@bp.post("/api/maint/templates")
def template_new():
    return _write(lambda: _m().template_save(None, security.json_body()))


@bp.post("/api/maint/templates/<tid>")
def template_edit(tid):
    return _write(lambda: _m().template_save(tid, security.json_body()))


@bp.delete("/api/maint/templates/<tid>")
def template_delete(tid):
    return _write(lambda: _m().template_delete(tid))


@bp.post("/api/maint/templates/<tid>/assign")
def template_assign(tid):
    return _write(lambda: _m().assign_template(tid, security.json_body().get("asset")))


@bp.post("/api/maint/books")
def book_new():
    return _write(lambda: _m().book_save(None, security.json_body()))


@bp.post("/api/maint/books/<bid>")
def book_edit(bid):
    return _write(lambda: _m().book_save(bid, security.json_body()))


@bp.delete("/api/maint/books/<bid>")
def book_delete(bid):
    return _write(lambda: _m().book_delete(bid))


@bp.post("/api/maint/books/<bid>/assign")
def book_assign(bid):
    b = security.json_body()
    return _write(lambda: _m().book_assign(bid, b.get("asset"), b.get("on", True) not in (False, 0, "0", "false")))
