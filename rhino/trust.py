"""Moonraker's trusted_clients, edited safely (1.5.4). Used by the installer (scripts/rhino_trust.py ensure) and by the
Portal's Settings > Trusted addresses (rhino/portal/trust_routes.py).

Only the trusted_clients lines inside [authorization] in moonraker.conf itself are ever changed; every other line, comment
and blank stays byte for byte. With no [authorization] section Moonraker trusts every address, so nothing is added (adding
the section would turn checking ON and could lock screens out).

Entries are IP addresses or CIDR ranges only (no host names), never wider than /8 (IPv4) or /16 (IPv6), so "trust
everyone" (0.0.0.0/0) can't be added by mistake. The new text must parse as INI and read back with the new list before it
is written. Then: backup, write (same owner and mode), restart Moonraker through its own API (no sudo), wait for it to
answer; if it doesn't, the old file goes back and systemd's own restart picks it up.
"""
import configparser
import ipaddress
import os
import re
import shutil
import subprocess
import time

from .errors import Fail

SECTION_RE = re.compile(r"^\s*\[\s*authorization\s*\]\s*(?:[#;].*)?$", re.I)
ANY_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]")
KEY_RE = re.compile(r"^(trusted_clients)\s*[:=]\s*(.*)$", re.I)
INCLUDE_RE = re.compile(r"^\s*\[\s*include\s+", re.I)
LOOPBACK = "127.0.0.0/8"
TAILNET = "100.64.0.0/10"
SKIP_IFACES = ("lo", "docker", "br-", "veth", "virbr", "tailscale", "wg", "tun")


def _strip(line):
    s = line.split(" #", 1)[0].split(" ;", 1)[0].strip()
    return "" if s.startswith(("#", ";")) else s


def normalize(entry):
    """'192.168.86.31/24' -> '192.168.86.0/24'; a bare address stays an address. Raises Fail."""
    s = str(entry or "").strip()
    if not s:
        raise Fail("Type an address or a range, for example 192.168.1.0/24.")
    try:
        if "/" in s:
            net = ipaddress.ip_network(s, strict=False)
            low = 8 if net.version == 4 else 16
            if net.prefixlen < low:
                raise Fail(f"{s} is too wide: that would trust far more than your own networks (at most /{low}).")
            return str(net)
        return str(ipaddress.ip_address(s))
    except ValueError:
        raise Fail(f'"{s}" isn\'t an address or a range (for example 192.168.1.50 or 192.168.1.0/24).')


def _network(e):
    try:
        return ipaddress.ip_network(e, strict=False)
    except ValueError:
        return None          # a host name Moonraker resolves itself: never treated as covering anything here


def covers(entries, ip):
    """Does any entry cover this address?"""
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return any(n is not None and a.version == n.version and a in n for n in map(_network, entries))


def _locate(lines):
    """-> (section_start, section_end, key_line or None, [entry line indexes])."""
    start = next((i for i, l in enumerate(lines) if SECTION_RE.match(l)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if ANY_SECTION_RE.match(lines[i])), len(lines))
    key, idx = None, []
    for i in range(start + 1, end):
        m = KEY_RE.match(lines[i])
        if m:
            key = i
            if _strip(m.group(2)):
                idx.append(i)
            j = i + 1
            while j < end:
                l = lines[j]
                if l.strip() == "" or l.lstrip().startswith(("#", ";")):
                    j += 1
                    continue
                if l[:1] in (" ", "\t"):
                    idx.append(j)
                    j += 1
                    continue
                break
            break
    return start, end, key, idx


def read(text):
    """-> {configured, entries, force_logins, include}"""
    lines = text.splitlines()
    loc = _locate(lines)
    out = {"configured": loc is not None, "entries": [], "force_logins": False,
           "include": any(INCLUDE_RE.match(l) for l in lines)}
    if loc is None:
        return out
    start, end, key, idx = loc
    for i in idx:
        v = KEY_RE.match(lines[i]).group(2) if i == key else lines[i]
        out["entries"] += [p for p in (_strip(v).replace(",", " ").split()) if p]
    for i in range(start + 1, end):
        m = re.match(r"^force_logins\s*[:=]\s*(\S+)", lines[i], re.I)
        if m:
            out["force_logins"] = m.group(1).lower() in ("true", "yes", "1", "on")
    return out


def _check(text, want):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text)
    except configparser.Error as e:
        raise Fail(f"The changed moonraker.conf wouldn't read back ({e.__class__.__name__}); nothing was written.")
    if read(text)["entries"] != want:
        raise Fail("The changed moonraker.conf didn't read back with the new list; nothing was written.")


def add(text, entries):
    """Add entries (already normalized) to trusted_clients. Raises Fail if there's no [authorization] section."""
    lines = text.splitlines()
    loc = _locate(lines)
    if loc is None:
        raise Fail("moonraker.conf has no [authorization] section, so Moonraker already trusts every address.")
    start, end, key, idx = loc
    have = read(text)["entries"]
    new = [e for e in entries if e not in have]
    if not new:
        return text
    indent = "    "
    for i in idx:
        if i != key:
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())] or indent
            break
    add_lines = [indent + e for e in new]
    if key is None:
        at = end
        while at > start + 1 and lines[at - 1].strip() == "":
            at -= 1
        lines[at:at] = ["trusted_clients:"] + add_lines
    else:
        at = (idx[-1] if idx else key) + 1
        lines[at:at] = add_lines
    out = "\n".join(lines) + ("\n" if text.endswith("\n") or not text else "")
    _check(out, have + new)
    return out


def remove(text, entry):
    lines = text.splitlines()
    loc = _locate(lines)
    if loc is None:
        raise Fail("moonraker.conf has no [authorization] section.")
    _, _, key, idx = loc
    have = read(text)["entries"]
    if entry not in have:
        raise Fail(f"{entry} isn't in trusted_clients.")
    for i in reversed(idx):
        if i == key:
            m = KEY_RE.match(lines[i])
            parts = [p for p in _strip(m.group(2)).replace(",", " ").split() if p != entry]
            lines[i] = f"{m.group(1)}: " + " ".join(parts) if parts else f"{m.group(1)}:"
        elif entry in _strip(lines[i]).replace(",", " ").split():
            rest = [p for p in _strip(lines[i]).replace(",", " ").split() if p != entry]
            if rest:
                lines[i] = lines[i][: len(lines[i]) - len(lines[i].lstrip())] + " ".join(rest)
            else:
                del lines[i]
    out = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    _check(out, [e for e in have if e != entry])
    return out


def local_networks():
    """This host's own networks to suggest: [(range, why)]. LAN /24s (or the interface's own prefix if narrower)
    and the Tailscale range when tailscale0 has an address."""
    out = []
    try:
        res = subprocess.run(["ip", "-o", "-4", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3)
        rows = res.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        rows = []
    for row in rows:
        parts = row.split()
        if len(parts) < 4:
            continue
        iface, cidr = parts[1], parts[3]
        try:
            itf = ipaddress.ip_interface(cidr)
        except ValueError:
            continue
        if itf.ip in ipaddress.ip_network(TAILNET):
            if (TAILNET, "Tailscale") not in out:
                out.append((TAILNET, "Tailscale"))
            continue
        if iface.startswith(SKIP_IFACES):
            continue
        net = itf.network if itf.network.prefixlen >= 24 else ipaddress.ip_network(f"{itf.ip}/24", strict=False)
        item = (str(net), f"this Rhino's network ({iface})")
        if item not in out:
            out.append(item)
    return out


def apply(conf, new_text, backup_dir, mr, wait_s=45, sleep=time.sleep, now=time.monotonic):
    """Back up, write, restart Moonraker through its API, wait for it. Puts the old file back if it doesn't answer.
    -> backup path. Raises Fail."""
    with open(conf) as f:
        old = f.read()
    if old == new_text:
        return None
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, f"moonraker.conf.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(conf, backup)
    _write_like(conf, new_text)
    mr.restart_moonraker()
    sleep(3)                                  # let the old process go before asking
    deadline = now() + wait_s
    while now() < deadline:
        if mr.klippy_state() != "offline":
            return backup
        sleep(1.5)
    _write_like(conf, old)
    raise Fail("Moonraker didn't come back after the change, so the old moonraker.conf is back "
               f"(another copy: {backup}). systemd restarts Moonraker on its own in a few seconds.")


def _write_like(path, text):
    st = os.stat(path)
    tmp = path + ".rhino-tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except (PermissionError, AttributeError):
        pass
    os.replace(tmp, path)
