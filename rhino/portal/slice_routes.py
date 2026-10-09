"""Slice tab (PROTOTYPE): Kiri:Moto inside the portal, opened on the mounted tool.

Off unless myrhino/slicer.json has "enabled": true - with it off, the tab stays hidden, no extra
security rule is added and the portal behaves exactly as before.

Kiri:Moto runs as its own small server on the same machine (port 8090 by default). The page frames
it and sends it the mounted tool's machine profile (built from variables.cfg by rhino.slice.profiles);
the Rhino mod inside Kiri:Moto selects it.
"""
import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from ..errors import Fail
from ..slice import profiles

bp = Blueprint("slice", __name__)


def _settings():
    return profiles.load_settings(current_app.config["PATHS"])


def _mounted():
    """-> (slot, tool name or "", printer reachable?) from Moonraker's SWAP_TOOL.current_tool."""
    st = current_app.config["MOONRAKER"].status()
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
    return jsonify({"ok": True, "enabled": True, "kiri_port": s["kiri_port"],
                    "mounted": {"slot": slot, "name": name, "online": online},
                    "profile": prof, "why": why, "available": sorted(built["profiles"]),
                    "problems": built["problems"]})


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
