"""The Pi's network (config 1.4.8): /api/net/* for Rhino Studio, and /net, a small page to keep or
undo a waiting change from the Pi's NEW address after a fixed-address change.

Reads are plain GETs. Changes are token-checked POSTs (security.check_write), refused while a job is
printing or paused (a dropped link mid-job is worse than waiting), and go through rhino.net, whose
root helper arms an automatic undo before it changes anything. Wi-Fi passwords are never logged or
sent back."""
import threading

from flask import Blueprint, current_app, jsonify, render_template

from .. import __version__
from ..errors import Fail
from . import security

bp = Blueprint("net", __name__)
_lock = threading.Lock()
BUSY = ("printing", "paused")


def _net():
    return current_app.config["NETWORK"]


def _change(fn, job_check=True):
    security.check_write()
    if job_check and current_app.config["MOONRAKER"].status().get("print_state") in BUSY:
        raise Fail("Not while a job is running: the link could drop mid-job.")
    with _lock:
        msg = fn(security.json_body())
    return jsonify({"ok": True, "message": msg, "pending": _net().pending()})


@bp.get("/api/net")
def state():
    return jsonify({"ok": True, **_net().state()})


@bp.get("/api/net/wifi")
def wifi():
    return jsonify({"ok": True, "networks": _net().wifi_scan()})


@bp.post("/api/net/hostname")
def hostname():
    return _change(lambda b: _net().set_hostname(b.get("hostname", "")))


@bp.post("/api/net/ipv4")
def ipv4():
    return _change(lambda b: _net().set_ipv4(b.get("iface", ""), b.get("method"), b.get("address"), b.get("prefix") or 0,
                                             b.get("gateway"), b.get("dns") or []))


@bp.post("/api/net/wifi")
def join():
    return _change(lambda b: _net().join_wifi(b.get("ssid", ""), b.get("password", "")))


@bp.post("/api/net/powersave")
def powersave():
    return _change(lambda b: _net().set_powersave(bool(b.get("on"))))


# Keep and undo are always allowed: they end a waiting change, they never start one.
@bp.post("/api/net/keep")
def keep():
    return _change(lambda b: _net().keep(), job_check=False)


@bp.post("/api/net/undo")
def undo():
    return _change(lambda b: _net().undo(), job_check=False)


@bp.get("/net")
def page():
    return render_template("net.html", token=security.TOKEN, version=__version__, pending=_net().pending())
