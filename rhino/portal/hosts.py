"""Which Host names a Portal write may arrive under (1.9.29, audit M4).

The write token and the Origin check stop other web sites from driving the Portal, but both compare against the
Host header the browser sent. Under DNS rebinding a page's own name is pointed at the Rhino, so Origin and Host
agree and the token is readable same-origin. The missing piece is: the Host must be a name this machine is really
reached by. Allowed:

* an IP address (IPv4, or IPv6 in brackets), with or without a port
* localhost, this host's name, and any .local name (mDNS names are answered on the local link, not by DNS)
* Tailscale MagicDNS names (*.ts.net)
* anything listed under cors_domains in moonraker.conf's [authorization] section, the same list Mainsail
  needs for a name of its own (a scheme and port are ignored; * matches any run of characters)

Reads are not checked: they change nothing and Moonraker answers them to the same names anyway.
"""
import fnmatch
import ipaddress
import os
import re
import socket
import time

SECTION_RE = re.compile(r"^\s*\[\s*authorization\s*\]\s*(?:[#;].*)?$", re.I)
ANY_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]")
KEY_RE = re.compile(r"^cors_domains\s*[:=]\s*(.*)$", re.I)


def _strip(line):
    s = line.split(" #", 1)[0].split(" ;", 1)[0].strip()
    return "" if s.startswith(("#", ";")) else s


def read_cors_domains(text):
    """The cors_domains entries of [authorization], as written (one per line, or inline, comma or space separated)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if SECTION_RE.match(l)), None)
    if start is None:
        return []
    out = []
    i = start + 1
    while i < len(lines) and not ANY_SECTION_RE.match(lines[i]):
        m = KEY_RE.match(lines[i])
        if m:
            out += _strip(m.group(1)).replace(",", " ").split()
            j = i + 1
            while j < len(lines) and not ANY_SECTION_RE.match(lines[j]):
                l = lines[j]
                if l.strip() == "" or l.lstrip().startswith(("#", ";")):
                    j += 1
                    continue
                if l[:1] not in (" ", "\t"):
                    break
                out += _strip(l).replace(",", " ").split()
                j += 1
            break
        i += 1
    return out


def host_name(host):
    """'rhino.local:5001' -> 'rhino.local'; '[fe80::1]:80' -> 'fe80::1'. Lower case."""
    h = (host or "").strip().lower()
    if h.startswith("["):
        return h[1:].split("]", 1)[0]
    if h.count(":") == 1:
        h = h.split(":", 1)[0]
    return h


def _pattern(entry):
    """A cors_domains entry as a host pattern: 'http://my.rhino.lan:80' -> 'my.rhino.lan', '*.local' stays."""
    e = entry.strip().lower()
    e = re.sub(r"^[a-z*]*://", "", e)
    e = e.split("/", 1)[0]
    return host_name(e)


def allowed_host(host, hostname=None, cors_domains=()):
    name = host_name(host)
    if not name:
        return False
    try:
        ipaddress.ip_address(name.split("%")[0])
        return True
    except ValueError:
        pass
    own = (hostname or socket.gethostname()).lower()
    if name in ("localhost", own) or name.endswith(".local") or name.endswith(".ts.net"):
        return True
    return any(fnmatch.fnmatchcase(name, _pattern(d)) for d in cors_domains if _pattern(d))


class Hosts:
    """Reads moonraker.conf's cors_domains at most every KEEP_S seconds."""
    KEEP_S = 60.0

    def __init__(self, moonraker_conf, hostname=None):
        self.path = moonraker_conf
        self.hostname = hostname
        self._at = 0.0
        self._domains = []

    def cors_domains(self):
        now = time.monotonic()
        if now - self._at > self.KEEP_S:
            try:
                with open(self.path, encoding="utf-8", errors="replace") as f:
                    self._domains = read_cors_domains(f.read())
            except OSError:
                self._domains = []
            self._at = now
        return self._domains

    def allowed(self, host):
        return allowed_host(host, self.hostname, self.cors_domains())

    def refusal(self, host):
        own = (self.hostname or socket.gethostname())
        return (f'Refused: this page was opened as "{host_name(host)}", which isn\'t this machine\'s name or address. '
                f"Open Studio as http://{own}.local or by its IP address, or add that name to cors_domains under "
                f"[authorization] in {os.path.basename(self.path)} and restart Moonraker.")
