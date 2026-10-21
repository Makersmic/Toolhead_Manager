"""Who may use the Portal's /api (1.5.4): whoever Moonraker trusts, the same as Mainsail.

Mainsail has no login of its own: Moonraker's [authorization] trusted_clients decides who may connect. The
Portal follows the same list, so port 5000 is never a way around it.

* No [authorization] in moonraker.conf: everyone, as before 1.5.4.
* The browser's address: the peer's, unless the peer is this host's nginx (127.0.0.1 / ::1), which puts the
  real one in X-Real-IP. Someone on the LAN can't claim another address by sending the header.
* Answers are kept 60 s per address (refusals 5 s), so a page of Portal calls costs one Moonraker request.
* Moonraker not answering: if it has ever refused someone (remembered in rhino_data), the Portal refuses with 503
  rather than guess; if it never has, the Portal works as before.
* Pages, photos and static files are not checked; they change nothing. Every change is a POST/DELETE under /api.
"""
import os
import threading
import time

from flask import jsonify, request

LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
KEEP_OK_S = 60.0
KEEP_REFUSED_S = 5.0
MAX_CACHE = 256


class Access:
    def __init__(self, mr, state_dir):
        self.mr = mr
        self.flag = os.path.join(state_dir, "moonraker_trust_seen")
        self.seen = os.path.exists(self.flag)
        self._cache = {}
        self._lock = threading.Lock()

    @staticmethod
    def client_ip(req):
        peer = req.remote_addr or ""
        if peer in LOOPBACK:
            return (req.headers.get("X-Real-IP") or peer).strip()
        return peer

    def _remember_seen(self, seen):
        if seen == self.seen:
            return
        self.seen = seen
        try:
            if seen:
                os.makedirs(os.path.dirname(self.flag), exist_ok=True)
                open(self.flag, "w").close()
            else:
                os.remove(self.flag)
        except OSError:
            pass

    def decide(self, ip, now=None):
        """-> (allowed, status, message)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hit = self._cache.get(ip)
            if hit and hit[0] > now:
                return hit[1]
        kind = self.mr.trusts(ip)
        if kind == "off":
            self._remember_seen(False)
            out, keep = (True, 200, ""), KEEP_OK_S
        elif kind == "trusted":
            self._remember_seen(True)
            out, keep = (True, 200, ""), KEEP_OK_S
        elif kind == "refused":
            self._remember_seen(True)
            out, keep = (False, 401, f"Moonraker doesn't trust this address ({ip}). Add it to trusted_clients "
                                     "in moonraker.conf and restart Moonraker."), KEEP_REFUSED_S
        else:   # offline: don't keep, ask again next time
            if self.seen:
                return False, 503, "Can't check this address: Moonraker isn't answering. Try again when it's back."
            return True, 200, ""
        with self._lock:
            if len(self._cache) >= MAX_CACHE:
                self._cache.clear()
            self._cache[ip] = (now + keep, out)
        return out

    def gate(self):
        """before_request hook: every /api call needs Moonraker's trust."""
        if not request.path.startswith("/api/"):
            return None
        ip = self.client_ip(request)
        allowed, status, msg = self.decide(ip)
        if allowed:
            return None
        return jsonify({"ok": False, "error": msg, "untrusted": status == 401, "address": ip}), status
