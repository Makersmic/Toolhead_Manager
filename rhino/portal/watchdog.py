"""Lets systemd restart the Portal when it is running but no longer answering.

systemd already restarts a Portal that crashes (Restart=on-failure). A Portal that has hung (every worker thread stuck,
a deadlock) is still "running", so it stayed hung until someone restarted it by hand. With Type=notify and WatchdogSec in
the service file, systemd expects a sign of life every so often. This thread sends it, but only while the Portal's own web
server really answers a request: if it doesn't, the signs stop and systemd restarts the Portal.

It also tells systemd the Portal is READY once that first request has been answered, so "systemctl restart" and the
installer's start check wait for a Portal that is serving, not just started.

Everything here does nothing unless systemd started the Portal with a notify socket (NOTIFY_SOCKET), so tests, the
demo server and a Portal started by hand are unchanged.
"""
import logging
import os
import socket
import threading
import urllib.request

log = logging.getLogger("rhino.portal.watchdog")
CHECK_TIMEOUT = 10.0   # seconds to wait for the Portal's answer to its own request


def notify(text):
    """Send a line (READY=1, WATCHDOG=1, STOPPING=1) to systemd. False when there is nobody to tell."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path:
        return False
    if path.startswith("@"):               # an abstract socket
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(path)
            s.send(text.encode())
        return True
    except OSError:
        return False


def watchdog_seconds():
    """How long systemd waits between signs of life (WATCHDOG_USEC), or None if the watchdog isn't on."""
    try:
        v = float(os.environ.get("WATCHDOG_USEC", ""))
    except ValueError:
        return None
    return v / 1e6 if v > 0 else None


def answers(url, timeout=CHECK_TIMEOUT):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


class Watchdog:
    def __init__(self, url, check=answers, tell=notify, wait=None):
        self.url, self.check, self.tell = url, check, tell
        self.period = watchdog_seconds()
        self.every = max(1.0, min(20.0, self.period / 3)) if self.period else 20.0
        self.ready = False
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait

    def step(self):
        """One round: ask the web server for a page; if it answers, say so to systemd."""
        if not self.check(self.url):
            log.warning("the Portal did not answer its own request at %s%s", self.url,
                        "; systemd will restart it if this goes on" if self.period else "")
            return False
        if not self.ready:
            self.tell("READY=1")
            self.ready = True
        if self.period:
            self.tell("WATCHDOG=1")
        return True

    def run(self):
        while True:
            self.step()
            if self._wait(1.0 if not self.ready else self.every):
                return

    def start(self):
        """Only when systemd is listening. Returns the thread, or None."""
        if not os.environ.get("NOTIFY_SOCKET"):
            return None
        t = threading.Thread(target=self.run, name="rhino-watchdog", daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop.set()
        self.tell("STOPPING=1")
