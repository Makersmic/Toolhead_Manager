"""The Pi's network, for the Portal (config 1.4.8).

Reading needs no special rights (nmcli, /var/lib/rhino-net/pending.json). Changing goes through
the root helper scripts/rhino_net_helper.py, installed as /usr/local/sbin/rhino-net with one
sudoers line, which arms an automatic undo before it changes anything. Wi-Fi passwords go to it on
stdin, never on a command line.
"""
import json
import os
import shutil
import subprocess

from .errors import Fail

HELPER = "/usr/local/sbin/rhino-net"
PENDING = "/var/lib/rhino-net/pending.json"
REVERT_SECONDS = 120


def _run(cmd, stdin=None, timeout=20):
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def split_t(line):
    """Split an nmcli -t line on unescaped colons."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch; esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


class Network:
    def __init__(self, run=None, helper=HELPER, pending_path=PENDING, which=shutil.which):
        self.run = run or _run
        self.helper = helper
        self.pending_path = pending_path
        self.which = which

    # ---------------------------------------------------------------- reads
    def support(self):
        if not self.which("nmcli"):
            return False, "This Pi doesn't use NetworkManager (no nmcli), so its network can't be changed from here."
        rc, out, _ = self.run(["nmcli", "-t", "-f", "RUNNING", "general"])
        if rc != 0 or out.strip() != "running":
            return False, "NetworkManager isn't running on this Pi."
        if not os.path.exists(self.helper):
            return False, "The network helper isn't installed: reinstall the Rhino config with rhino.sh (option 3)."
        return True, None

    def pending(self):
        try:
            with open(self.pending_path) as f:
                p = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(p, dict):
            return None
        out = {"kind": p.get("kind"), "summary": p.get("summary", ""), "expires_at": p.get("expires_at", 0)}
        if p.get("kind") == "ipv4" and p.get("address"):
            out["confirm_url"] = f"http://{p['address']}:5000/net"
        return out

    def hostname(self):
        rc, out, _ = self.run(["hostname"])
        return out.strip() if rc == 0 else ""

    def interfaces(self):
        rc, out, _ = self.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
        if rc != 0:
            return []
        wifi = {w["ssid"]: w for w in self._wifi_list(rescan=False) if w["in_use"]}
        result = []
        for line in out.splitlines():
            dev, typ, state, con = (split_t(line) + ["", "", "", ""])[:4]
            if typ not in ("wifi", "ethernet") or dev.startswith("p2p"):
                continue
            i = {"name": dev, "type": typ, "state": state.split(" ")[0], "connection": con or None, "ip": None, "prefix": None,
                 "gateway": None, "dns": [], "mac": None, "method": None}
            rc, show, _ = self.run(["nmcli", "-t", "-f", "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,GENERAL.HWADDR", "device", "show", dev])
            for l in show.splitlines() if rc == 0 else []:
                k, _, v = l.partition(":")
                v = v.replace("\\:", ":")
                if k.startswith("IP4.ADDRESS") and "/" in v and not i["ip"]:
                    i["ip"], p = v.split("/", 1); i["prefix"] = int(p)
                elif k == "IP4.GATEWAY" and v:
                    i["gateway"] = v
                elif k.startswith("IP4.DNS") and v:
                    i["dns"].append(v)
                elif k == "GENERAL.HWADDR":
                    i["mac"] = v.lower() or None
            if con:
                rc, m, _ = self.run(["nmcli", "-g", "ipv4.method" + (",802-11-wireless.ssid,802-11-wireless.powersave" if typ == "wifi" else ""), "connection", "show", con])
                vals = m.splitlines() if rc == 0 else []
                i["method"] = "manual" if vals and vals[0] == "manual" else "auto"
                if typ == "wifi" and len(vals) >= 3:
                    i["ssid"] = vals[1] or None
                    # 2 = disable, 3 = enable, 0/1 = default (on for Raspberry Pi OS)
                    i["powersave"] = vals[2] not in ("2", "disable")
                    w = wifi.get(i["ssid"])
                    i["signal"] = w["signal"] if w else None
            result.append(i)
        return result

    def state(self):
        ok, why = self.support()
        base = {"supported": ok, "reason": why, "manager": "NetworkManager" if self.which("nmcli") else None,
                "hostname": self.hostname(), "revert_seconds": REVERT_SECONDS, "pending": self.pending()}
        base["interfaces"] = self.interfaces() if self.which("nmcli") else []
        return base

    def _wifi_list(self, rescan=True):
        rc, out, _ = self.run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes" if rescan else "no"], timeout=30)
        if rc != 0:
            return []
        seen = {}
        for line in out.splitlines():
            use, ssid, sig, sec = (split_t(line) + ["", "", "", ""])[:4]
            if not ssid:
                continue
            w = {"ssid": ssid, "signal": int(sig or 0), "security": sec.strip(), "in_use": use.strip() == "*"}
            if ssid not in seen or w["in_use"] or w["signal"] > seen[ssid]["signal"]:
                seen[ssid] = w
        return sorted(seen.values(), key=lambda w: (not w["in_use"], -w["signal"]))

    def wifi_scan(self):
        return self._wifi_list(rescan=True)

    # ---------------------------------------------------------------- changes (root helper)
    def _helper(self, *args, stdin=""):
        ok, why = self.support()
        if not ok:
            raise Fail(why)
        if self.pending():
            raise Fail("Keep or undo the waiting network change first.")
        return self._call(*args, stdin=stdin)

    def _call(self, *args, stdin=""):
        rc, out, err = self.run(["sudo", "-n", self.helper, *args], stdin=stdin, timeout=90)
        if rc != 0:
            raise Fail((err or out or "The network helper failed").strip().splitlines()[-1])
        return out.strip()

    def _iface(self, name):
        for i in self.interfaces():
            if i["name"] == name:
                return i
        raise Fail(f"No network interface called {name}")

    def set_hostname(self, name):
        return self._helper("hostname", str(name))

    def set_ipv4(self, iface, method, address=None, prefix=None, gateway=None, dns=()):
        i = self._iface(str(iface))
        if not i["connection"]:
            raise Fail(f"{iface} isn't connected, so there's no connection to change")
        if method == "auto":
            return self._helper("ipv4", i["connection"], "auto")
        if method != "manual":
            raise Fail("method must be auto or manual")
        dns = [str(d) for d in (dns or [])][:3]
        return self._helper("ipv4", i["connection"], "manual", f"{address}/{int(prefix)}", str(gateway), *dns)

    def join_wifi(self, ssid, password):
        wifi = [i for i in self.interfaces() if i["type"] == "wifi"]
        if not wifi:
            raise Fail("This Pi has no Wi-Fi interface")
        return self._helper("wifi", wifi[0]["name"], str(ssid), stdin=str(password or "") + "\n")

    def set_powersave(self, on):
        wifi = [i for i in self.interfaces() if i["type"] == "wifi" and i["connection"]]
        if not wifi:
            raise Fail("Not connected to Wi-Fi")
        return self._helper("powersave", wifi[0]["connection"], "on" if on else "off")

    def keep(self):
        return self._call("keep")

    def undo(self):
        return self._call("undo")
