"""Settings > Trusted addresses in Rhino Studio (config 1.5.4): Moonraker's trusted_clients, from a screen that is
already trusted (access.py refuses every /api call from one that isn't, so a screen can never let itself in).

GET    /api/moonraker-trust      {configured, force_logins, include, entries, address, covered, suggestions}
POST   /api/moonraker-trust      {"entry": "100.64.0.0/10"}   add it, restart Moonraker, wait for it
DELETE /api/moonraker-trust      {"entry": "..."}              take it out - never the one that lets this screen in,
                                                                and never the last one covering 127.0.0.1 (the Portal)
Both changes: refused during a job (Moonraker restarts), backup in rhino_data/config_backups, see rhino/trust.py.
"""
import os
import threading

from flask import Blueprint, current_app, jsonify, request

from . import security
from .. import trust
from ..errors import Fail

bp = Blueprint("trust", __name__)
_busy = threading.Lock()


def _conf():
    return os.path.join(current_app.config["PATHS"].cfg, "moonraker.conf")


def _text():
    try:
        with open(_conf()) as f:
            return f.read()
    except OSError:
        raise Fail("moonraker.conf isn't in the config folder.")


def _state():
    info = trust.read(_text())
    acc = current_app.config["ACCESS"]
    ip = acc.client_ip(request)
    sugg = [{"entry": e, "why": why} for e, why in trust.local_networks()
            if info["configured"] and e not in info["entries"] and not trust.covers(info["entries"], e.split("/")[0])]
    if info["configured"] and trust.TAILNET not in [s["entry"] for s in sugg] and not trust.covers(info["entries"], "100.64.0.1"):
        sugg.append({"entry": trust.TAILNET, "why": "Tailscale (any device on your tailnet)"})
    return {"ok": True, **info, "address": ip, "covered": trust.covers(info["entries"], ip), "suggestions": sugg}


def _change(new_text):
    mr = current_app.config["MOONRAKER"]
    if mr.status()["restart_blocked"]:
        raise Fail("A job is running. Changing trusted_clients restarts Moonraker - wait until it's finished.")
    if not _busy.acquire(blocking=False):
        raise Fail("Already changing trusted_clients - wait a moment.")
    try:
        trust.apply(_conf(), new_text, os.path.join(current_app.config["PATHS"].state_dir, "config_backups"), mr)
    finally:
        _busy.release()
    current_app.config["ACCESS"]._cache.clear()


@bp.get("/api/moonraker-trust")
def state():
    return jsonify(_state())


@bp.post("/api/moonraker-trust")
def add_entry():
    security.check_write()
    entry = trust.normalize(security.json_body().get("entry"))
    text = _text()
    if not trust.read(text)["configured"]:
        raise Fail("moonraker.conf has no [authorization] section, so Moonraker already trusts every address.")
    _change(trust.add(text, [entry]))
    return jsonify(_state())


@bp.delete("/api/moonraker-trust")
def remove_entry():
    security.check_write()
    entry = str(security.json_body().get("entry") or "").strip()
    text = _text()
    have = trust.read(text)["entries"]
    rest = [e for e in have if e != entry]
    ip = current_app.config["ACCESS"].client_ip(request)
    if trust.covers(have, ip) and not trust.covers(rest, ip):
        raise Fail(f"{entry} is what lets this screen ({ip}) in. Remove it from another trusted screen, or over SSH.")
    if trust.covers(have, "127.0.0.1") and not trust.covers(rest, "127.0.0.1"):
        raise Fail(f"{entry} is what lets the Portal read the printer (127.0.0.1). It has to stay.")
    _change(trust.remove(text, entry))
    return jsonify(_state())
