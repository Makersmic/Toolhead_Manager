"""Slice tab (PROTOTYPE): Kiri:Moto inside the portal, opened on the mounted tool.

Off unless myrhino/slicer.json has "enabled": true - with it off, the tab stays hidden, no extra
security rule is added and the portal behaves exactly as before.

Kiri:Moto runs as its own small server on the same machine (port 8090 by default). The page frames
it and sends it the mounted tool's machine profile (built from variables.cfg by rhino.slice.profiles);
the Rhino mod inside Kiri:Moto selects it.
"""
import re
import threading
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from .. import pending
from ..errors import Fail
from ..slice import jobs, profiles
from . import security

bp = Blueprint("slice", __name__)
_send_lock = threading.Lock()      # one send / start at a time


def _settings():
    return profiles.load_settings(current_app.config["PATHS"])


def _mounted(st=None):
    """-> (slot, tool name or "", printer reachable?) from Moonraker's SWAP_TOOL.current_tool."""
    st = st or current_app.config["MOONRAKER"].status()
    slot = int(st.get("mounted_slot") or 0)
    name = ""
    if slot:
        for t in current_app.config["SERVICE"].list_tools():
            if int(t["slot"]) == slot:
                name = t["name"]
                break
    return slot, name, bool(st.get("online")) and st.get("klippy") == "ready"


@bp.get("/api/slice/context")
def context():
    s = _settings()
    if not s["enabled"]:
        return jsonify({"ok": True, "enabled": False})
    try:
        built = profiles.build(current_app.config["PATHS"], s)
    except Fail as e:
        built = {"profiles": {}, "problems": [str(e)]}
    slot, name, online = _mounted()
    prof = built["profiles"].get(name)
    if not online:
        why = "The printer is not reachable, so the mounted tool is not known. Kiri:Moto opens without a Rhino profile."
    elif not slot:
        why = "No toolhead is recorded as mounted. Answer the 'which toolhead is mounted?' question in Mainsail first."
    elif not prof:
        why = f"{name or 'Slot ' + str(slot)} is mounted. This prototype only has a Kiri:Moto profile for laser tools (LightSaber)."
    else:
        why = ""
    return jsonify({"ok": True, "enabled": True, "kiri_port": s["kiri_port"], "mainsail_url": s["mainsail_url"],
                    "mounted": {"slot": slot, "name": name, "online": online},
                    "profile": prof, "why": why, "available": sorted(built["profiles"]),
                    "problems": built["problems"]})


def _enabled_or_404():
    if not _settings()["enabled"]:
        raise Fail("Slicing is not turned on (myrhino/slicer.json).")


def _profiles():
    try:
        return profiles.build(current_app.config["PATHS"], _settings())["profiles"]
    except Fail:
        return {}


def _conflicts(stamp):
    """Live check: Moonraker's status, the mounted tool, the portal's own pending restart."""
    st = current_app.config["MOONRAKER"].status()
    _, name, _ = _mounted(st)
    found = jobs.conflicts(stamp, st, name, _profiles(), pending.get(current_app.config["PATHS"]) is not None)
    return found, {"mounted": name, "print_state": st.get("print_state"), "klippy": st.get("klippy")}


def _sent():
    """Files this portal sent, {file name: tool} - only these can be started from the Slice tab."""
    return current_app.config.setdefault("SLICE_SENT", {})


@bp.get("/api/slice/check")
def check():
    _enabled_or_404()
    stamp = request.args.get("tool", "")
    found, info = _conflicts(stamp)
    return jsonify({"ok": True, "tool": stamp, "conflicts": found, **info})


@bp.post("/api/slice/send")
def send():
    """Body {name, gcode}. Refused (409, with the reasons) unless every check passes."""
    security.check_write()
    _enabled_or_404()
    body = security.json_body()
    text = body.get("gcode")
    if not isinstance(text, str) or not text.strip():
        raise Fail("No G-code was received.")
    stamp = jobs.read_stamp(text)
    with _send_lock:
        found, info = _conflicts(stamp)
        if found:
            return jsonify({"ok": False, "error": "Not sent - " + found[0], "conflicts": found, "tool": stamp, **info}), 409
        fname = jobs.safe_name(stamp, body.get("name"))
        current_app.config["MOONRAKER"].upload_gcode(fname, text.encode("utf-8"))
        _sent()[fname] = stamp
    p = _profiles().get(stamp) or {}
    return jsonify({"ok": True, "file": fname, "tool": stamp, "setup": jobs.SETUP_MACRO.get(p.get("mode", "")),
                    "bytes": len(text.encode("utf-8")), **info})


@bp.post("/api/slice/start")
def start():
    """Body {file}. Starts the tool's guided setup with FILE=<file>; the setup's own questions appear in Mainsail."""
    security.check_write()
    _enabled_or_404()
    fname = str(security.json_body().get("file") or "")
    stamp = _sent().get(fname)
    if not stamp or not jobs.VALID_FILE.match(fname):
        raise Fail("That file was not sent from this Slice tab - send it again.")
    p = _profiles().get(stamp) or {}
    macro = jobs.SETUP_MACRO.get(p.get("mode", ""))
    if not macro:
        raise Fail(f"The portal does not know how to start a {stamp} job yet.")
    with _send_lock:
        found, info = _conflicts(stamp)
        if found:
            return jsonify({"ok": False, "error": "Not started - " + found[0], "conflicts": found, "tool": stamp, **info}), 409
        current_app.config["MOONRAKER"].run_gcode(f"{macro} FILE={fname}")
    return jsonify({"ok": True, "started": f"{macro} FILE={fname}", "tool": stamp, **info})


@bp.after_app_request
def allow_kiri_frame(resp):
    """Only when slicing is on: let the portal page frame Kiri:Moto (same host, its own port).
    Runs after security.add_headers, so it extends that policy rather than replacing it."""
    csp = resp.headers.get("Content-Security-Policy")
    if not csp or not resp.mimetype == "text/html":
        return resp
    s = _settings()
    if not s["enabled"]:
        return resp
    host = _host_name()
    if host:
        resp.headers["Content-Security-Policy"] = f"{csp}; frame-src http://{host}:{s['kiri_port']}"
    return resp


def _host_name():
    """The host name the browser used for the portal (rhino.local, 192.168.1.20, ...), or "" if it
    holds anything but name/address characters - it ends up inside a security header."""
    host = urlsplit("//" + (request.host or "")).hostname or ""
    if not re.fullmatch(r"[A-Za-z0-9.\-:]{1,253}", host):
        return ""
    return f"[{host}]" if ":" in host else host
