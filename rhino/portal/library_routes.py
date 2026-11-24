"""The model library in Rhino Studio (Files > Models). docs/proposal-stl-library.md. All the rules are in rhino/library.py.

GET  /api/library?path=&offset=      one folder: {entries, total, offset, path} plus {usage}: files, bytes, free, floor
GET  /api/library/file?path=         the file's bytes (Studio gives it to job setup as if it had been dropped)
GET  /api/library/count?path=        what deleting this would remove: {files, folders}
POST /api/library/upload   (token)   multipart: file, path (the folder), mode ('' | 'replace' | 'both'). 409 + {clash: true}
                                     when the name is taken by a different file and mode is empty
POST /api/library/folder   (token)   {path, name}      make a folder
POST /api/library/rename   (token)   {path, name}
POST /api/library/move     (token)   {path, to}        to = the folder
POST /api/library/delete   (token)   {path}            straight away, no trash (Mike, Nov 23)
"""
import os
import tempfile

from flask import Blueprint, current_app, jsonify, request, send_file

from ..errors import Fail
from ..library import Clash, Library
from . import security

bp = Blueprint("library", __name__)


def _lib():
    lib = current_app.config.get("LIBRARY")
    if lib is None:
        lib = current_app.config["LIBRARY"] = Library(current_app.config["PATHS"].models_dir)
    return lib


@bp.get("/api/library")
def listing():
    lib = _lib()
    out = lib.list(request.args.get("path", ""), request.args.get("offset", 0, type=int))
    return jsonify({"ok": True, **out, "usage": lib.usage()})


@bp.get("/api/library/file")
def file():
    fp = _lib().file(request.args.get("path", ""))
    return send_file(fp, conditional=True, as_attachment=False, mimetype="application/octet-stream", max_age=0)


@bp.get("/api/library/count")
def count():
    return jsonify({"ok": True, **_lib().count(request.args.get("path", ""))})


@bp.post("/api/library/upload")
def upload():
    security.check_write()
    up = request.files.get("file")
    if not up or not up.filename:
        raise Fail("Send a file.")
    lib = _lib()
    mode = request.form.get("mode", "")
    if mode not in ("", "replace", "both"):
        raise Fail("mode must be replace or both.")
    # to a temporary file first (never in the library until it has been checked and flushed); the size limit is nginx's and the Portal's
    fd, tmp = tempfile.mkstemp(prefix="rhino-lib-")
    os.close(fd)
    try:
        up.save(tmp)
        # the name is the base name only: a browser may send a path
        name = os.path.basename(up.filename.replace("\\", "/"))
        try:
            res = lib.save(request.form.get("path", ""), name, tmp, mode)
        except Clash as e:
            return jsonify({"ok": False, "error": str(e), "clash": True, "name": name}), 409
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return jsonify({"ok": True, **res})


@bp.post("/api/library/folder")
def folder():
    security.check_write()
    d = security.json_body()
    _lib().mkdir(d.get("path", ""), d.get("name"))
    return jsonify({"ok": True})


@bp.post("/api/library/rename")
def rename():
    security.check_write()
    d = security.json_body()
    _lib().rename(d.get("path", ""), d.get("name"))
    return jsonify({"ok": True})


@bp.post("/api/library/move")
def move():
    security.check_write()
    d = security.json_body()
    _lib().move(d.get("path", ""), d.get("to", ""))
    return jsonify({"ok": True})


@bp.post("/api/library/delete")
def delete():
    security.check_write()
    d = security.json_body()
    return jsonify({"ok": True, **_lib().delete(d.get("path", ""))})
