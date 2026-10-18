#!/usr/bin/python3 -I
"""rhino-net: the only thing the Rhino Portal runs as root (config 1.4.8).

Installed by install.sh as /usr/local/sbin/rhino-net (root-owned, not writable by your login), with
one sudoers line letting the Portal's user run exactly this file. It changes the Pi's network through
NetworkManager and nothing else, and every change can undo itself:

  1. it records how things are now (pending.json),
  2. starts a timer that runs `rhino-net undo` after REVERT_SECONDS,
  3. only then makes the change.
`rhino-net keep` stops the timer. If the change cut the Pi off, nobody can press Keep, so it switches
back on its own. One change waits at a time.

  rhino-net hostname NAME
  rhino-net ipv4 CONNECTION auto
  rhino-net ipv4 CONNECTION manual ADDRESS/PREFIX GATEWAY [DNS ...]
  rhino-net wifi IFACE SSID            (password, if any, on stdin: never on the command line or in logs)
  rhino-net powersave CONNECTION on|off
  rhino-net keep | undo | pending

Every argument is checked against a strict pattern before anything runs; commands are run as argument
lists, never through a shell.
"""
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import uuid

REVERT_SECONDS = 120
TIMER_UNIT = "rhino-net-revert"
HELPER = "/usr/local/sbin/rhino-net"


class Paths:
    def __init__(self, root=""):
        self.state = root + "/var/lib/rhino-net"
        self.pending = self.state + "/pending.json"
        self.hosts = root + "/etc/hosts"
        self.connections = root + "/etc/NetworkManager/system-connections"


class Fail(Exception):
    pass


HOST_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
CON_RE = re.compile(r"^[A-Za-z0-9 ._@+:-]{1,64}$")          # NetworkManager connection names we accept
IFACE_RE = re.compile(r"^[a-z][a-z0-9]{1,14}$")


def run(cmd, stdin=None, check=True):
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)
    if check and p.returncode != 0:
        raise Fail((p.stderr or p.stdout or f"{cmd[0]} failed").strip().splitlines()[-1][:300])
    return p.stdout


# ---------------------------------------------------------------- checks
def check_hostname(h):
    if not HOST_RE.match(h or ""):
        raise Fail("Hostname: letters, digits and hyphens, 1-63, no hyphen at the ends")
    return h


def check_connection(name, R):
    if not CON_RE.match(name or ""):
        raise Fail("Unknown connection")
    names = R(["nmcli", "-t", "-f", "NAME", "connection", "show"]).splitlines()
    if name not in [n.replace("\\:", ":") for n in names]:
        raise Fail(f"No NetworkManager connection called {name}")
    return name


def check_iface(i, R):
    if not IFACE_RE.match(i or ""):
        raise Fail("Unknown interface")
    devs = [l.split(":")[0] for l in R(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"]).splitlines()]
    if i not in devs:
        raise Fail(f"No network interface called {i}")
    return i


def check_ipv4(cidr, gateway, dns):
    try:
        iface = ipaddress.IPv4Interface(cidr)
        gw = ipaddress.IPv4Address(gateway)
        servers = [ipaddress.IPv4Address(d) for d in dns]
    except ValueError:
        raise Fail("Address, gateway and DNS must be IPv4 addresses (address as 192.168.1.50/24)")
    net = iface.network
    if not 8 <= net.prefixlen <= 30:
        raise Fail("Prefix must be 8 to 30")
    if gw not in net:
        raise Fail("The gateway isn't on the same network as the address")
    if iface.ip in (net.network_address, net.broadcast_address) or iface.ip == gw:
        raise Fail("That address can't be used (network, broadcast or the gateway's own)")
    if len(servers) > 3:
        raise Fail("At most three DNS servers")
    return str(iface), str(gw), [str(s) for s in servers]


def check_ssid(s):
    if not s or len(s.encode()) > 32 or any(ord(c) < 32 for c in s):
        raise Fail("SSID: 1-32 bytes, no control characters")
    return s


def check_password(p):
    if p == "":
        return ""
    if not 8 <= len(p) <= 63 or any(ord(c) < 32 or ord(c) > 126 for c in p):
        raise Fail("Wi-Fi password: 8 to 63 ordinary characters")
    return p


# ---------------------------------------------------------------- pending + timer
def read_pending(P):
    try:
        with open(P.pending) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_pending(P, rec):
    os.makedirs(P.state, exist_ok=True)
    tmp = P.pending + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.chmod(tmp, 0o644)          # the Portal (not root) reads it to show the countdown
    os.replace(tmp, P.pending)


def clear_pending(P):
    try:
        os.remove(P.pending)
    except FileNotFoundError:
        pass


def start_timer(R, seconds):
    R(["systemctl", "stop", f"{TIMER_UNIT}.timer"], check=False)
    R(["systemctl", "reset-failed", f"{TIMER_UNIT}.service"], check=False)
    R(["systemd-run", f"--unit={TIMER_UNIT}", f"--on-active={seconds}s", "--timer-property=AccuracySec=1s",
       HELPER, "undo"])


def stop_timer(R):
    R(["systemctl", "stop", f"{TIMER_UNIT}.timer"], check=False)


def begin(P, R, kind, summary, before, extra=None, seconds=REVERT_SECONDS):
    """Record the way back and arm the timer BEFORE changing anything."""
    if read_pending(P):
        raise Fail("Keep or undo the waiting network change first")
    write_pending(P, {"kind": kind, "summary": summary, "before": before, "created": time.time(),
                      "expires_at": time.time() + seconds, **(extra or {})})
    try:
        start_timer(R, seconds)
    except Fail:
        clear_pending(P)
        raise


# ---------------------------------------------------------------- the four changes
def _hostname(P, R, name, old):
    R(["hostnamectl", "set-hostname", name])
    try:
        with open(P.hosts) as f:
            lines = f.read().splitlines()
        out, done = [], False
        for l in lines:
            if l.startswith("127.0.1.1"):
                out.append(f"127.0.1.1\t{name}"); done = True
            else:
                out.append(l)
        if not done:
            out.append(f"127.0.1.1\t{name}")
        with open(P.hosts + ".rhino-tmp", "w") as f:
            f.write("\n".join(out) + "\n")
        os.replace(P.hosts + ".rhino-tmp", P.hosts)
    except OSError:
        pass
    R(["systemctl", "try-restart", "avahi-daemon"], check=False)   # announces the new name.local


def get_ipv4(R, con):
    vals = R(["nmcli", "-g", "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns", "connection", "show", con]).splitlines()
    vals += [""] * (4 - len(vals))
    return {"method": vals[0], "addresses": vals[1], "gateway": vals[2], "dns": vals[3]}


def put_ipv4(R, con, v, up=True):
    R(["nmcli", "connection", "modify", con, "ipv4.method", v["method"], "ipv4.addresses", v["addresses"],
       "ipv4.gateway", v["gateway"], "ipv4.dns", v["dns"].replace(",", " ")])
    if up:
        R(["nmcli", "connection", "up", con], check=False)


def wifi_connection_file(P, name, iface, ssid, password):
    """A NetworkManager keyfile, written root-only, so the password never appears in a process list."""
    os.makedirs(P.connections, exist_ok=True)
    path = os.path.join(P.connections, f"{name}.nmconnection")
    sec = f"\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={password}\n" if password else "\n"
    body = (f"[connection]\nid={name}\nuuid={uuid.uuid4()}\ntype=wifi\ninterface-name={iface}\nautoconnect=true\n\n"
            f"[wifi]\nmode=infrastructure\nssid={ssid}\n{sec}\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    return path


def active_connection(R, iface):
    for l in R(["nmcli", "-t", "-f", "DEVICE,CONNECTION", "device"]).splitlines():
        dev, _, con = l.partition(":")
        if dev == iface:
            return con.replace("\\:", ":") or None
    return None


def get_powersave(R, con):
    return R(["nmcli", "-g", "802-11-wireless.powersave", "connection", "show", con]).strip() or "0"


def put_powersave(R, con, value):
    R(["nmcli", "connection", "modify", con, "802-11-wireless.powersave", value])
    R(["nmcli", "connection", "up", con], check=False)


# ---------------------------------------------------------------- undo
def undo(P, R):
    p = read_pending(P)
    stop_timer(R)
    if not p:
        return "nothing waiting"
    b = p["before"]
    k = p["kind"]
    if k == "hostname":
        _hostname(P, R, b["hostname"], None)
    elif k == "ipv4":
        put_ipv4(R, b["connection"], b["ipv4"])
    elif k == "powersave":
        put_powersave(R, b["connection"], b["powersave"])
    elif k == "wifi":
        if b.get("connection"):
            R(["nmcli", "connection", "up", b["connection"]], check=False)
        R(["nmcli", "connection", "delete", p["new_connection"]], check=False)
    clear_pending(P)
    return f"switched back: {p['summary']}"


def keep(P, R):
    stop_timer(R)
    p = read_pending(P)
    clear_pending(P)
    return f"kept: {p['summary']}" if p else "nothing waiting"


# ---------------------------------------------------------------- main
def main(argv, P=None, R=None, stdin=None):
    P = P or Paths()
    R = R or run
    if not argv:
        raise Fail("usage: rhino-net hostname|ipv4|wifi|powersave|keep|undo|pending ...")
    cmd, args = argv[0], argv[1:]
    if cmd == "pending":
        return json.dumps(read_pending(P))
    if cmd == "keep":
        return keep(P, R)
    if cmd == "undo":
        return undo(P, R)
    if cmd == "hostname" and len(args) == 1:
        name = check_hostname(args[0])
        old = R(["hostnamectl", "--static"]).strip() or R(["hostname"]).strip()
        begin(P, R, "hostname", f"Renamed to {name}.local", {"hostname": old})
        _hostname(P, R, name, old)
        return f"renamed to {name}"
    if cmd == "ipv4" and len(args) >= 2:
        con = check_connection(args[0], R)
        before = {"connection": con, "ipv4": get_ipv4(R, con)}
        if args[1] == "auto" and len(args) == 2:
            begin(P, R, "ipv4", f"{con}: automatic address", before)
            put_ipv4(R, con, {"method": "auto", "addresses": "", "gateway": "", "dns": ""})
            return "automatic"
        if args[1] == "manual" and 4 <= len(args) <= 7:
            cidr, gw, dns = check_ipv4(args[2], args[3], args[4:])
            begin(P, R, "ipv4", f"{con}: fixed address {cidr}", before, {"address": cidr.split("/")[0]})
            put_ipv4(R, con, {"method": "manual", "addresses": cidr, "gateway": gw, "dns": " ".join(dns)})
            return f"fixed {cidr}"
    if cmd == "wifi" and len(args) == 2:
        iface = check_iface(args[0], R)
        ssid = check_ssid(args[1])
        password = check_password((stdin if stdin is not None else sys.stdin.read()).rstrip("\n"))
        old = active_connection(R, iface)
        new = "rhino-wifi-" + re.sub(r"[^A-Za-z0-9_-]", "_", ssid)[:40]
        begin(P, R, "wifi", f"Joined {ssid}", {"connection": old}, {"new_connection": new})
        wifi_connection_file(P, new, iface, ssid, password)
        R(["nmcli", "connection", "reload"])
        R(["nmcli", "connection", "up", new], check=False)
        return f"joining {ssid}"
    if cmd == "powersave" and len(args) == 2 and args[1] in ("on", "off"):
        con = check_connection(args[0], R)
        begin(P, R, "powersave", f"Wi-Fi power saving {args[1]}", {"connection": con, "powersave": get_powersave(R, con)})
        put_powersave(R, con, "3" if args[1] == "on" else "2")
        return f"power saving {args[1]}"
    raise Fail("rhino-net: unknown or malformed command")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("rhino-net must run as root (through sudo)", file=sys.stderr)
        sys.exit(2)
    try:
        print(main(sys.argv[1:]))
    except Fail as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
