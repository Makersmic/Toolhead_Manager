"""Routes for a versioned store (rhino/versioned_store.py): list, get, create, save with rev, delete, history, revert,
undelete, export and import. Used by slice profiles and your macros, so both behave the same. Reads are GETs; every
write is a POST or DELETE and token-checked (security.check_write). Nothing here talks to Klipper."""
from flask import current_app, jsonify, request

from ..errors import Fail
from . import security


def _rev(b):
    r = b.get("rev")
    if isinstance(r, bool) or not isinstance(r, int):
        raise Fail("Save needs the revision it started from")
    return r


def add_store_routes(bp, path, config_key, item, download):
    """Under /api/<path>: `item` is the JSON key one item travels under ("profile", "macro")."""
    svc = lambda: current_app.config[config_key]  # noqa: E731
    base = f"/api/{path}"

    def listing():
        s = svc()
        st = s.state(full=request.args.get("full") == "1")
        try:
            st["deleted"] = s.deleted()
        except Fail:
            st["deleted"] = []
        return jsonify(st)

    def one(pid):
        return jsonify({"ok": True, item: svc().get(pid)})

    def create():
        security.check_write()
        return jsonify({"ok": True, item: svc().create(security.json_body())})

    def save(pid):
        security.check_write()
        b = security.json_body()
        return jsonify({"ok": True, item: svc().save(pid, b.get(item), _rev(b))})

    def delete(pid):
        security.check_write()
        return jsonify({"ok": True, **svc().delete(pid)})

    def history(pid):
        return jsonify({"ok": True, "revisions": svc().history(pid)})

    def revert(pid):
        security.check_write()
        to = security.json_body().get("to")
        if isinstance(to, bool) or not isinstance(to, int):
            raise Fail("Say which revision to go back to")
        return jsonify({"ok": True, item: svc().revert(pid, to)})

    def undelete(pid):
        security.check_write()
        return jsonify({"ok": True, item: svc().undelete(pid)})

    def export():
        pid = request.args.get("id") or None
        r = jsonify(svc().export(pid))
        r.headers["Content-Disposition"] = f'attachment; filename="{download}{"-" + pid if pid else ""}.json"'
        return r

    def import_():
        security.check_write()
        return jsonify({"ok": True, "added": svc().import_(security.json_body())})

    p = path.replace("-", "_")
    bp.add_url_rule(base, f"{p}_list", listing, methods=["GET"])
    bp.add_url_rule(f"{base}/<pid>", f"{p}_one", one, methods=["GET"])
    bp.add_url_rule(base, f"{p}_create", create, methods=["POST"])
    bp.add_url_rule(f"{base}/<pid>", f"{p}_save", save, methods=["POST"])
    bp.add_url_rule(f"{base}/<pid>", f"{p}_delete", delete, methods=["DELETE"])
    bp.add_url_rule(f"{base}/<pid>/history", f"{p}_history", history, methods=["GET"])
    bp.add_url_rule(f"{base}/<pid>/revert", f"{p}_revert", revert, methods=["POST"])
    bp.add_url_rule(f"{base}/<pid>/undelete", f"{p}_undelete", undelete, methods=["POST"])
    bp.add_url_rule(f"{base}-export", f"{p}_export", export, methods=["GET"])
    bp.add_url_rule(f"{base}-import", f"{p}_import", import_, methods=["POST"])
