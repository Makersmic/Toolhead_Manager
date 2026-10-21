"""Network settings (1.4.8): the root helper, the Portal's rhino.net, and /api/net.
Run: python3 dev/test_net.py   (needs flask). Nothing here touches this machine's network:
every nmcli/systemd/hostname call goes to a fake."""
import json, os, shutil, stat, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import rhino_net_helper as H
from rhino.net import Network, split_t
from rhino.errors import Fail

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, contains=""):
    try: fn()
    except (H.Fail, Fail) as e: return contains.lower() in str(e).lower()
    return False

# ---------------------------------------------------------------- the root helper
class FakeSys:
    """Answers the commands the helper runs, and records them in order."""
    def __init__(self):
        self.cmds = []
        self.host = "mainsailos"
        self.cons = {"ShopNet": {"ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "", "802-11-wireless.powersave": "0"}}
        self.active = {"wlan0": "ShopNet", "eth0": ""}
    def __call__(self, cmd, stdin=None, check=True):
        self.cmds.append(list(cmd))
        c = cmd
        if c[:2] == ["hostnamectl", "--static"] or c == ["hostname"]: return self.host + "\n"
        if c[:2] == ["hostnamectl", "set-hostname"]: self.host = c[2]; return ""
        if c[:5] == ["nmcli", "-t", "-f", "NAME", "connection"]: return "\n".join(self.cons) + "\n"
        if c[:5] == ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"]: return "wlan0:wifi\neth0:ethernet\nlo:loopback\n"
        if c[:5] == ["nmcli", "-t", "-f", "DEVICE,CONNECTION", "device"]: return "".join(f"{d}:{n}\n" for d, n in self.active.items())
        if c[:2] == ["nmcli", "-g"]:
            con = c[-1]; return "\n".join(self.cons[con].get(k, "") for k in c[2].split(",")) + "\n"
        if c[:3] == ["nmcli", "connection", "modify"]:
            con = c[3]; kv = c[4:]
            for k, v in zip(kv[::2], kv[1::2]): self.cons[con][k] = v
            return ""
        return ""
    def index(self, pred):
        return next((i for i, c in enumerate(self.cmds) if pred(c)), -1)

def setup(root=None):
    root = root or tempfile.mkdtemp(prefix="rhino-net-")
    os.makedirs(root + "/etc", exist_ok=True)
    with open(root + "/etc/hosts", "w") as f: f.write("127.0.0.1\tlocalhost\n127.0.1.1\tmainsailos\n")
    return H.Paths(root), FakeSys()

armed = lambda c: c[0] == "systemd-run"
# hostname
P, R = setup()
out = H.main(["hostname", "rhino-shop"], P, R)
pend = H.read_pending(P)
ok(R.host == "rhino-shop" and "127.0.1.1\trhino-shop" in open(P.hosts).read(), "hostname: set, and /etc/hosts follows")
ok(pend["kind"] == "hostname" and pend["before"] == {"hostname": "mainsailos"} and pend["expires_at"] > pend["created"] + 100,
   "hostname: the way back is recorded, with a 2-minute deadline")
ok(0 <= R.index(armed) < R.index(lambda c: c[:2] == ["hostnamectl", "set-hostname"]), "the undo timer is armed BEFORE anything changes")
ok(stat.S_IMODE(os.stat(P.pending).st_mode) == 0o644, "pending.json readable by the Portal (not root)")
t = next(c for c in R.cmds if armed(c))
ok(t == ["systemd-run", "--unit=rhino-net-revert", "--on-active=120s", "--timer-property=AccuracySec=1s", "/usr/local/sbin/rhino-net", "undo"],
   "the timer runs `rhino-net undo` after 120 s")
ok(raises(lambda: H.main(["powersave", "ShopNet", "off"], P, R), "waiting network change"), "a second change waits until the first is kept or undone")
H.main(["undo"], P, R)
ok(R.host == "mainsailos" and "127.0.1.1\tmainsailos" in open(P.hosts).read() and H.read_pending(P) is None, "undo: old name back, nothing waiting")
for bad in ("-rhino", "rhino.local", "a" * 64, "rhino shop", "x;reboot"):
    P2, R2 = setup()
    ok(raises(lambda: H.main(["hostname", bad], P2, R2), "hostname") and not R2.cmds and H.read_pending(P2) is None, f"hostname {bad!r} refused before anything runs")

# ipv4
P, R = setup()
H.main(["ipv4", "ShopNet", "manual", "192.168.1.60/24", "192.168.1.1", "192.168.1.1", "1.1.1.1"], P, R)
ok(R.cons["ShopNet"]["ipv4.method"] == "manual" and R.cons["ShopNet"]["ipv4.addresses"] == "192.168.1.60/24"
   and R.cons["ShopNet"]["ipv4.dns"] == "192.168.1.1 1.1.1.1", "fixed address set on the connection")
ok(R.index(armed) < R.index(lambda c: c[:3] == ["nmcli", "connection", "modify"]), "...after the timer is armed")
ok(H.read_pending(P)["address"] == "192.168.1.60", "the new address is recorded, so the Portal can say where to keep it")
H.main(["undo"], P, R)
ok(R.cons["ShopNet"]["ipv4.method"] == "auto" and R.cons["ShopNet"]["ipv4.addresses"] == "", "undo puts DHCP back")
for args, why in ((["192.168.1.60/24", "10.0.0.1"], "same network"), (["192.168.1.60/31", "192.168.1.61"], "prefix"),
                  (["192.168.1.255/24", "192.168.1.1"], "can't be used"), (["192.168.1.1/24", "192.168.1.1"], "can't be used"),
                  (["300.1.1.1/24", "192.168.1.1"], "ipv4"), (["192.168.1.60/24", "192.168.1.1", "1.1.1.1", "8.8.8.8", "9.9.9.9", "1.0.0.1"], "")):
    P2, R2 = setup()
    ok(raises(lambda: H.main(["ipv4", "ShopNet", "manual", *args], P2, R2), why) and H.read_pending(P2) is None
       and not any(c[:3] == ["nmcli", "connection", "modify"] for c in R2.cmds), f"bad fixed address {args[:2]} refused, nothing changed")
P2, R2 = setup(); ok(raises(lambda: H.main(["ipv4", "NoSuch", "auto"], P2, R2), "no networkmanager connection"), "unknown connection refused")
P2, R2 = setup(); ok(raises(lambda: H.main(["ipv4", "Shop`Net`", "auto"], P2, R2), "unknown"), "odd connection names refused by pattern")

# wifi
P, R = setup()
H.main(["wifi", "wlan0", "HouseNet-5G"], P, R, stdin="correct horse battery\n")
f = P.connections + "/rhino-wifi-HouseNet-5G.nmconnection"
body = open(f).read()
ok("ssid=HouseNet-5G" in body and "psk=correct horse battery" in body and stat.S_IMODE(os.stat(f).st_mode) == 0o600, "join: keyfile written root-only with the password")
ok(not any("correct horse" in " ".join(c) for c in R.cmds), "the password never appears on any command line")
ok(R.index(armed) < R.index(lambda c: c[:3] == ["nmcli", "connection", "up"]), "...timer armed before it switches networks")
H.main(["undo"], P, R)
ok(["nmcli", "connection", "up", "ShopNet"] in R.cmds and ["nmcli", "connection", "delete", "rhino-wifi-HouseNet-5G"] in R.cmds, "undo: back on the old network, the new one deleted")
P2, R2 = setup(); ok(raises(lambda: H.main(["wifi", "wlan0", "X"], P2, R2, stdin="short\n"), "8 to 63") and H.read_pending(P2) is None, "too-short password refused before anything")
P2, R2 = setup(); ok(raises(lambda: H.main(["wifi", "wlan9", "X"], P2, R2, stdin="\n"), "no network interface"), "unknown interface refused")
P2, R2 = setup(); H.main(["wifi", "wlan0", "OpenCafe"], P2, R2, stdin="\n")
ok("[wifi-security]" not in open(P2.connections + "/rhino-wifi-OpenCafe.nmconnection").read(), "open network: no security section")

# power saving, keep
P, R = setup()
H.main(["powersave", "ShopNet", "off"], P, R)
ok(R.cons["ShopNet"]["802-11-wireless.powersave"] == "2", "power saving off = 2 (disable)")
out = H.main(["keep"], P, R)
ok(H.read_pending(P) is None and ["systemctl", "stop", "rhino-net-revert.timer"] in R.cmds and R.cons["ShopNet"]["802-11-wireless.powersave"] == "2",
   "keep: timer stopped, change stays")
ok(H.main(["undo"], P, R) == "nothing waiting", "undo with nothing waiting does nothing")
ok(raises(lambda: H.main(["reboot"], P, R), "unknown") and raises(lambda: H.main(["ipv4", "ShopNet", "dhcp"], P, R), "unknown"), "anything else is refused")

# ---------------------------------------------------------------- rhino.net (Portal side, not root)
ok(split_t(r"*:Shop\:Net:58:WPA2") == ["*", "Shop:Net", "58", "WPA2"], "nmcli -t lines split on unescaped colons")
class FakeRun:
    def __init__(self, helper_ok=True, running="running"):
        self.calls = []; self.running = running; self.helper_ok = helper_ok
    def __call__(self, cmd, stdin=None, timeout=20):
        self.calls.append((list(cmd), stdin))
        if cmd[:4] == ["nmcli", "-t", "-f", "RUNNING"]: return 0, self.running + "\n", ""
        if cmd == ["hostname"]: return 0, "mainsailos\n", ""
        if cmd[:5] == ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]:
            return 0, "wlan0:wifi:connected:ShopNet\neth0:ethernet:unavailable:\nlo:loopback:connected (externally):lo\np2p-dev-wlan0:wifi-p2p:disconnected:\n", ""
        if cmd[:3] == ["nmcli", "-t", "-f"] and cmd[3].startswith("IP4.ADDRESS"):
            return 0, ("IP4.ADDRESS[1]:192.168.1.50/24\nIP4.GATEWAY:192.168.1.1\nIP4.DNS[1]:192.168.1.1\nGENERAL.HWADDR:B8\\:27\\:EB\\:4C\\:91\\:2E\n" if cmd[-1] == "wlan0" else "GENERAL.HWADDR:B8\\:27\\:EB\\:11\\:22\\:33\n"), ""
        if cmd[:2] == ["nmcli", "-g"]: return 0, "auto\nShopNet\n2\n", ""
        if "wifi" in cmd and "list" in cmd: return 0, "*:ShopNet:58:WPA2\n :HouseNet-5G:81:WPA2\n :HouseNet-5G:40:WPA2\n :Neighbours:22:WPA3\n", ""
        if cmd[:2] == ["sudo", "-n"]: return (0, "ok\n", "") if self.helper_ok else (1, "", "Prefix must be 8 to 30\n")
        return 1, "", "?"
tmp = tempfile.mkdtemp(); helper = tmp + "/rhino-net"; open(helper, "w").close(); pend = tmp + "/pending.json"
N = lambda run, which=lambda x: "/usr/bin/" + x, h=helper: Network(run=run, helper=h, pending_path=pend, which=which)
st = N(FakeRun()).state()
w = st["interfaces"][0]
ok(st["supported"] and st["hostname"] == "mainsailos" and [i["name"] for i in st["interfaces"]] == ["wlan0", "eth0"], "state: Wi-Fi and wired, no loopback or p2p")
ok(w["ip"] == "192.168.1.50" and w["prefix"] == 24 and w["gateway"] == "192.168.1.1" and w["mac"] == "b8:27:eb:4c:91:2e"
   and w["method"] == "auto" and w["ssid"] == "ShopNet" and w["signal"] == 58 and w["powersave"] is False, "state: Wi-Fi address, signal and power saving read")
ok(N(FakeRun()).wifi_scan()[1] == {"ssid": "HouseNet-5G", "signal": 81, "security": "WPA2", "in_use": False}, "scan: one row per network, strongest kept")
ok(not N(FakeRun(), which=lambda x: None).state()["supported"], "no nmcli: read-only, says why")
ok("run by another network service" in N(FakeRun(running="stopped")).support()[1], "NetworkManager stopped: says what runs the network instead")
_dh = FakeRun(running="stopped"); _orig = _dh.__call__
class _Dh(FakeRun):
    def __call__(self, cmd, stdin=None, timeout=20):
        if cmd[:3] == ["systemctl", "is-active", "--quiet"]: return 0, "", ""
        return super().__call__(cmd, stdin, timeout)
_r = N(_Dh(running="stopped")).support()[1]
ok("run by dhcpcd" in _r and "Nothing is wrong" in _r and "raspi-config" in _r, "bullseye (dhcpcd): says it's normal and where to change the network")
ok("reinstall" in N(FakeRun(), h=tmp + "/missing").support()[1], "helper missing: says to reinstall")
r = FakeRun(); N(r).join_wifi("HouseNet-5G", "correct horse battery")
c = next(x for x in r.calls if x[0][:2] == ["sudo", "-n"])
ok(c[0] == ["sudo", "-n", helper, "wifi", "wlan0", "HouseNet-5G"] and c[1] == "correct horse battery\n", "join: sudo -n, password on stdin only")
r = FakeRun(); N(r).set_ipv4("wlan0", "manual", "192.168.1.60", 24, "192.168.1.1", ["1.1.1.1"])
ok(next(x for x in r.calls if x[0][:2] == ["sudo", "-n"])[0][3:] == ["ipv4", "ShopNet", "manual", "192.168.1.60/24", "192.168.1.1", "1.1.1.1"], "fixed address goes to the helper by connection name")
ok(raises(lambda: N(FakeRun(helper_ok=False)).set_ipv4("wlan0", "manual", "1.2.3.4", 31, "1.2.3.5"), "prefix"), "the helper's refusal comes back as the message")
json.dump({"kind": "ipv4", "summary": "wlan0: fixed address 192.168.1.60/24", "expires_at": 9e9, "address": "192.168.1.60", "before": {"x": 1}}, open(pend, "w"))
p = N(FakeRun()).pending()
ok(p == {"kind": "ipv4", "summary": "wlan0: fixed address 192.168.1.60/24", "expires_at": 9e9, "confirm_url": "http://192.168.1.60:5000/net"},
   "pending: summary, deadline and where to keep it; the way back stays private")
ok(raises(lambda: N(FakeRun()).set_powersave(True), "waiting"), "a change while one waits: refused before sudo")
os.remove(pend)

# ---------------------------------------------------------------- /api/net and /net
ROOT = tempfile.mkdtemp(prefix="rhino-net-portal-")
shutil.copytree(os.path.dirname(HERE), ROOT + "/cfg", ignore=shutil.ignore_patterns("__pycache__", "registry_backups", ".git"))
from rhino.portal import create_app, security
app = create_app(ROOT + "/cfg", "http://127.0.0.1:9")      # no Moonraker: status says offline
app.config["NETWORK"] = N(FakeRun())
class MR:
    state = "standby"
    def status(self): return {"print_state": self.state}
app.config["MOONRAKER"] = MR()
cl = app.test_client(); HDR = {security.HEADER: security.TOKEN}
s = cl.get("/api/net").get_json()
ok(s["ok"] and s["supported"] and s["interfaces"][0]["name"] == "wlan0" and s["pending"] is None, "GET /api/net")
ok(cl.post("/api/net/powersave", json={"on": False}).status_code == 400, "a change without the token is refused")
r = cl.post("/api/net/wifi", json={"ssid": "HouseNet-5G", "password": "correct horse battery"}, headers=HDR)
ok(r.status_code == 200 and b"correct horse" not in r.data, "join through the Portal; the password isn't echoed")
MR.state = "printing"
r = cl.post("/api/net/hostname", json={"hostname": "rhino"}, headers=HDR)
ok(r.status_code == 400 and "job" in r.get_json()["error"], "changes refused while a job is printing")
ok(cl.post("/api/net/undo", json={}, headers=HDR).status_code == 200, "...but keep/undo always work")
MR.state = "standby"
json.dump({"kind": "ipv4", "summary": "wlan0: fixed address 192.168.1.60/24", "expires_at": 9e9, "address": "192.168.1.60"}, open(pend, "w"))
pg = cl.get("/net")
ok(pg.status_code == 200 and b"fixed address 192.168.1.60" in pg.data and b"net.js" in pg.data and b"<script>" not in pg.data, "/net shows the waiting change, no inline script")
ok(cl.get("/static/net.js").status_code == 200, "/net's script is served")
os.remove(pend)
ok(b"Nothing is waiting" in cl.get("/net").data, "/net with nothing waiting says so")

shutil.rmtree(ROOT, ignore_errors=True); shutil.rmtree(tmp, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
