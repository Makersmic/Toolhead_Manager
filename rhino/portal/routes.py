"""HTTP layer. Thin on purpose: validate the request shape, call ToolService, shape the reply.

    GET  /                          the single-page app
    GET  /media/<tool>/<file>       tool photos
    GET  /api/state                 tools + pin report + printer status + restart-pending flag
    GET  /api/options               drop-down data for the add / edit forms
    GET  /api/tools/<name>          full detail of one custom tool (for the edit form)
    POST /api/tools/check           dry-run an add (validate only, writes nothing)
    POST /api/preview/macro|control validate one macro / control, return the exact .cfg text (writes nothing)
    POST /api/tools                 add
    POST /api/tools/<name>/edit     edit (any subset of fields)
    POST /api/tools/<name>/rename
    POST /api/tools/<name>/photos   upload one photo (multipart field "photo")
    DELETE /api/tools/<name>/photos/<file>
    DELETE /api/tools/<name>        remove tool (and its photos)
    GET  /api/lists                 the Admin screen's tool lists (sub-types, materials, nozzles, hardware categories)
    POST /api/lists                 save any of them
    POST /api/hardware              add or replace one piece of system hardware ("original" = its current name)
    POST /api/preview/hardware      validate one piece of system hardware, return the .cfg text (writes nothing)
    DELETE /api/hardware/<name>
    POST /api/restart               FIRMWARE_RESTART via Moonraker (refused while a job runs)
    POST /api/restart/auto          {"on": true|false} restart by itself when the running job ends
"""
import logging
import os
import threading
import time

from werkzeug.exceptions import HTTPException
from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from .. import __version__, pending
from ..errors import Fail
from ..moonraker import job_timing
from ..presets import MATERIAL_FIELDS
from . import media, security

bp = Blueprint("portal", __name__)
log = logging.getLogger("rhino.portal")
_write_lock = threading.Lock()   # one change at a time: load -> validate -> save is not re-entrant


def _svc():
    return current_app.config["SERVICE"]


def _paths():
    return current_app.config["PATHS"]


def _restart_pending():
    return pending.get(_paths()) is not None


def _write(fn, change=None):
    """Run a mutating handler: token check, one-at-a-time lock, restart flag, JSON reply.
    `change(result)` describes what is waiting for the restart, for the banner."""
    security.check_write()
    with _write_lock:
        result = fn()
    if result.get("restart_needed"):
        pending.mark(_paths(), change(result) if change else "")
    return jsonify({**result, "restart_pending": _restart_pending()})


def _printer_state():
    """Moonraker status plus how long the job has been paused (from the monitor) and a time estimate."""
    st = current_app.config["MOONRAKER"].status()
    mon = current_app.config.get("MONITOR")
    info = mon.job_info() if mon else {}
    job = st.get("job")
    if job:
        paused_s = float(info.get("paused_s") or 0.0) if info.get("filename") == job["filename"] else 0.0
        job.update(paused_s=paused_s, paused_since=info.get("paused_since"), timing=job_timing(job, paused_s))
    return st


# ----------------------------------------------------------------------------- pages
@bp.get("/")
def index():
    return render_template("index.html", token=security.TOKEN, version=__version__)


@bp.get("/media/<tool>/<filename>")
def photo(tool, filename):
    p = media.path_for(_paths(), tool, filename)
    if not os.path.isfile(p):
        return security.error("No such photo", 404)
    return send_file(p)


# ----------------------------------------------------------------------------- reads
@bp.get("/api/state")
def state():
    svc = _svc()
    p = pending.get(_paths())
    mon = current_app.config.get("MONITOR")
    if p is not None:
        p["restart_at"] = mon.restart_eta() if mon else None
    return jsonify({"ok": True, "tools": svc.list_tools(), "pins": svc.pin_report(),
                    "printer": _printer_state(), "restart_pending": p is not None, "pending": p,
                    "server_time": time.time()})


_theme_cache = {"at": 0.0, "value": None}


@bp.get("/api/theme")
def theme():
    """Mainsail's dark/light mode and primary colour, so the portal can match it (cached for a minute)."""
    now = time.time()
    if _theme_cache["value"] is None or now - _theme_cache["at"] > 60:
        _theme_cache.update(at=now, value=current_app.config["MOONRAKER"].ui_theme())
    return jsonify({"ok": True, **_theme_cache["value"]})


@bp.get("/api/dash/jobs")
def dash_jobs():
    """Jobs per week for the dashboard, from Moonraker's job history: the last 12 weeks (Monday-based),
    each {start, completed, cancelled, error, hours}. Empty weeks are included so the axis is even."""
    weeks = 12
    now = time.time()
    lt = time.localtime(now)
    monday = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - lt.tm_wday, 0, 0, 0, 0, 0, -1))
    starts = [monday - 7 * 86400 * i for i in range(weeks - 1, -1, -1)]
    out = [{"start": s, "completed": 0, "cancelled": 0, "error": 0, "hours": 0.0} for s in starts]
    try:
        jobs = current_app.config["MOONRAKER"].history(since=starts[0], limit=1000)
    except Fail:
        return jsonify({"ok": True, "weeks": out, "available": False})
    for j in jobs:
        t = float(j.get("start_time") or 0)
        if t < starts[0]:
            continue
        i = min(int((t - starts[0]) // (7 * 86400)), weeks - 1)
        st = j.get("status") or ""
        key = "completed" if st == "completed" else "cancelled" if st == "cancelled" else "error" if st in ("error", "klippy_shutdown", "klippy_disconnect", "server_exit") else None
        if key:
            out[i][key] += 1
        out[i]["hours"] += float(j.get("print_duration") or 0) / 3600.0
    return jsonify({"ok": True, "weeks": out, "available": True})


@bp.get("/api/options")
def options():
    return jsonify({"ok": True, **_svc().options(),
                    "material_fields": {k: list(v) for k, v in MATERIAL_FIELDS.items()}})


@bp.get("/api/tools/<name>/sheet")
def sheet(name):
    return jsonify(_svc().sheet(name))


@bp.get("/api/tools/<name>")
def detail(name):
    return jsonify({"ok": True, "tool": _svc().get(name)})


# ----------------------------------------------------------------------------- writes
@bp.post("/api/tools/check")
def check_add():
    return _write(lambda: _svc().add(security.json_body(), dry_run=True))


@bp.post("/api/tools")
def add():
    return _write(lambda: _svc().add(security.json_body()), lambda r: f"added {r['name']}")


@bp.post("/api/tools/<name>/edit")
def edit(name):
    return _write(lambda: _svc().edit(name, security.json_body()), lambda r: f"edited {name}: " + _short(r["changes"]))


@bp.post("/api/preview/<kind>")
def preview(kind):
    """Validate one macro, control or piece of system hardware and return the exact Klipper text - writes nothing."""
    security.check_write()
    if kind == "hardware":
        return jsonify(_svc().hardware_preview(security.json_body().get("item") or {}))
    return jsonify(_svc().preview(kind, security.json_body()))


@bp.get("/api/lists")
def lists_get():
    return jsonify(_svc().lists_get())


@bp.post("/api/lists")
def lists_save():
    security.check_write()
    with _write_lock:
        return jsonify(_svc().lists_save(security.json_body()))


@bp.post("/api/hardware")
def hardware_save():
    def go():
        r = _svc().hardware_save(security.json_body())
        if r.get("renamed_from"):
            current_app.config["MAINT"].asset_renamed(f"hw:{r['renamed_from']}", f"hw:{r['name']}")
        return r
    return _write(go, lambda r: f"system hardware {r['name']} saved")


@bp.delete("/api/hardware/<name>")
def hardware_remove(name):
    def go():
        r = _svc().hardware_remove(name)
        current_app.config["MAINT"].asset_removed(f"hw:{name}")
        return r
    return _write(go, lambda r: f"system hardware {name} removed")


@bp.post("/api/tools/<name>/rename")
def rename(name):
    def go():
        r = _svc().rename(name, security.json_body().get("new_name", ""))
        old = os.path.join(_paths().images_dir, name)
        if os.path.isdir(old):                      # photos follow the tool
            os.rename(old, os.path.join(_paths().images_dir, r["name"]))
        current_app.config["MAINT"].tool_renamed(name, r["name"])   # tasks + meters follow it too
        return r
    return _write(go, lambda r: f"renamed {name} to {r['name']}")


@bp.delete("/api/tools/<name>")
def remove(name):
    def go():
        r = _svc().remove(name)
        media.delete_all(_paths(), name)
        current_app.config["MAINT"].tool_removed(name)          # its tasks are archived, history kept
        return {k: v for k, v in r.items() if k != "images"}
    return _write(go, lambda r: f"removed {name}")


@bp.post("/api/tools/<name>/photos")
def add_photo(name):
    def go():
        up = request.files.get("photo")
        if up is None:
            raise Fail("No photo was sent")
        t = _svc().get(name)
        if len(t.get("images", [])) >= 6:
            raise Fail("At most 6 photos per tool")
        fn = media.save(_paths(), name, up)
        try:
            return _svc().set_images(name, t.get("images", []) + [fn])
        except Fail:
            media.delete(_paths(), name, fn)
            raise
    return _write(go)


@bp.delete("/api/tools/<name>/photos/<filename>")
def delete_photo(name, filename):
    def go():
        t = _svc().get(name)
        if filename not in t.get("images", []):
            raise Fail("No such photo")
        r = _svc().set_images(name, [i for i in t["images"] if i != filename])
        media.delete(_paths(), name, filename)
        return r
    return _write(go)


@bp.post("/api/restart")
def restart():
    def go():
        r = current_app.config["MOONRAKER"].restart()
        pending.clear(_paths())
        return r
    return _write(go)


@bp.post("/api/restart/auto")
def restart_auto():
    def go():
        on = bool(security.json_body().get("on"))
        if pending.set_auto_restart(_paths(), on) is None:
            raise Fail("Nothing is waiting for a restart.")
        return {"ok": True, "auto_restart": on}
    return _write(go)


def _short(changes, n=4):
    """'power_cap, notes, EPS.power and 2 more' for the banner."""
    changes = list(changes)
    return ", ".join(changes[:n]) + (f" and {len(changes) - n} more" if len(changes) > n else "")


# ----------------------------------------------------------------------------- errors
@bp.app_errorhandler(Fail)
def on_fail(e):
    return security.error(str(e), 400)


@bp.app_errorhandler(413)
def too_big(_):
    return security.error("That upload is too large.", 413)


@bp.app_errorhandler(404)
def not_found(_):
    return security.error("Not found", 404)


@bp.app_errorhandler(405)
def bad_method(_):
    return security.error("Method not allowed", 405)


@bp.app_errorhandler(Exception)
def on_crash(e):
    if isinstance(e, HTTPException):
        return security.error(e.description, e.code)
    log.exception("unhandled error")
    return security.error("Unexpected error - see the portal log (journalctl -u rhino-portal).", 500)
