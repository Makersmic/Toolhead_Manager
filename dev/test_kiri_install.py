"""Kiri:Moto installer test (PROTOTYPE): run kiri/install-kiri.sh and the rhino.sh menu (option 7) on a fake Pi.

    python3 dev/test_kiri_install.py                     a small stand-in Kiri:Moto package (fast)
    RHINO_KIRI_ZIP=../rhino-kiri-4.7.0-1.zip python3 dev/test_kiri_install.py    the real package

The fake Pi is a temporary home folder (login "tester") with a Rhino config that has the Slice tab. sudo,
systemctl, apt-get and hostname are stand-ins on PATH; the systemctl stand-in really starts Kiri:Moto from the
installed service file, so its paths are checked too. Node.js is NOT on the PATH, so the installer has to
download it: a local stand-in for nodejs.org serves this computer's own Node.js 22 as a tarball, with a
checksum list. Needs bash, curl, tar, xz, unzip, zip and Node.js 22; uses port 8090 (SKIP if taken).
"""
import hashlib
import http.server
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


NODE = shutil.which("node")
for tool in ("bash", "curl", "tar", "xz", "unzip", "zip", "sha256sum"):
    if not shutil.which(tool):
        print(f"SKIP Kiri:Moto installer test: {tool} is not installed")
        sys.exit(0)
if not NODE or int(subprocess.run([NODE, "-p", "process.versions.node.split('.')[0]"], capture_output=True, text=True).stdout or 0) < 22:
    print("SKIP Kiri:Moto installer test: Node.js 22 is not installed")
    sys.exit(0)
with socket.socket() as s:
    if s.connect_ex(("127.0.0.1", 8090)) == 0:
        print("SKIP Kiri:Moto installer test: port 8090 is in use on this computer")
        sys.exit(0)

ROOT = tempfile.mkdtemp(prefix="rhino-kiri-install-")
HOME = os.path.join(ROOT, "home", "tester")
CFG = os.path.join(HOME, "printer_data", "config")
BIN = os.path.join(ROOT, "bin")
SERVICE = os.path.join(ROOT, "etc", "rhino-kiri.service")
LOG = os.path.join(ROOT, "calls.log")
PIDF = os.path.join(ROOT, "kiri.pid")
KHOME = os.path.join(HOME, "rhino-kiri")
NODE_VER = subprocess.run([NODE, "-p", "process.versions.node"], capture_output=True, text=True).stdout.strip()

# ---------------------------------------------------------------- the Pi's Rhino config (with the Slice tab)
shutil.copytree(REPO, CFG, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", "manual", "docs", "*.zip"))
json.dump({"enabled": False, "kiri_port": 8090, "work_area": {"LightSaber": {"x": 540, "y": 370}}},
          open(os.path.join(CFG, "myrhino", "slicer.json"), "w"))

# ---------------------------------------------------------------- the Kiri:Moto package
PKG = os.path.join(ROOT, "pkg")


def make_package(dest, version):
    if os.environ.get("RHINO_KIRI_ZIP"):
        subprocess.run(["unzip", "-q", "-o", os.environ["RHINO_KIRI_ZIP"], "-d", dest], check=True)
        open(os.path.join(dest, "VERSION"), "w").write(version + "\n")
        return
    app = os.path.join(dest, "app")
    srv = os.path.join(app, "node_modules", "@gridspace", "app-server")
    os.makedirs(srv)
    open(os.path.join(app, "app.js"), "w").write("// stand-in\n")
    # a tiny stand-in for Kiri:Moto's server: answers /kiri/ on --port
    open(os.path.join(srv, "app-server-run.js"), "w").write(
        "const http=require('http');const i=process.argv.indexOf('--port');const port=+process.argv[i+1];"
        "http.createServer((q,r)=>{r.writeHead(q.url.startsWith('/kiri/')?200:404);r.end('Kiri:Moto stand-in '+process.version)})"
        ".listen(port,'0.0.0.0');\n")
    for f in ("PINNED", "NODE", "install-kiri.sh"):
        shutil.copy(os.path.join(REPO, "kiri", f), dest)
    open(os.path.join(dest, "VERSION"), "w").write(version + "\n")


make_package(PKG, "4.7.0-1")
INSTALL = os.path.join(PKG, "install-kiri.sh")

# ---------------------------------------------------------------- stand-in nodejs.org (this computer's Node.js, re-packed)
ARCH = {"x86_64": "x64", "aarch64": "arm64", "armv7l": "armv7l"}[os.uname().machine]
MIRROR = os.path.join(ROOT, "mirror")
tarname = f"node-v{NODE_VER}-linux-{ARCH}.tar.xz"
os.makedirs(os.path.join(MIRROR, f"v{NODE_VER}"))
node_prefix = os.path.dirname(os.path.dirname(os.path.realpath(NODE)))
with tarfile.open(os.path.join(MIRROR, f"v{NODE_VER}", tarname), "w:xz") as t:
    t.add(os.path.join(node_prefix, "bin", "node"), arcname=f"node-v{NODE_VER}-linux-{ARCH}/bin/node")
digest = hashlib.sha256(open(os.path.join(MIRROR, f"v{NODE_VER}", tarname), "rb").read()).hexdigest()
open(os.path.join(MIRROR, f"v{NODE_VER}", "SHASUMS256.txt"), "w").write(f"{'0' * 64}  node-v{NODE_VER}-other.tar.gz\n{digest}  {tarname}\n")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=MIRROR, **k)

    def log_message(self, *a):
        pass


mirror = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=mirror.serve_forever, daemon=True).start()
MIRROR_URL = f"http://127.0.0.1:{mirror.server_port}"

# ---------------------------------------------------------------- fake Moonraker (job state)
STATE = {"print_state": "standby"}


class Moon(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        b = json.dumps({"result": {"status": {"print_stats": {"state": STATE["print_state"]}}}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


moon = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Moon)
threading.Thread(target=moon.serve_forever, daemon=True).start()

# ---------------------------------------------------------------- stand-ins for the Pi's system commands
STUBS = {
    "id": '[ "${1:-}" = "-u" ] && { echo "${FAKE_UID:-1000}"; exit 0; }; exec /usr/bin/id "$@"',
    "sudo": 'echo "sudo $*" >> "$CALLS"; [ "${1:-}" = "-v" ] && exit 0; exec "$@"',
    "apt-get": 'echo "apt-get $*" >> "$CALLS"; exit 0',
    "hostname": 'echo 127.0.0.1',
    "journalctl": 'echo "(fake journal)"',
    "clear": 'exit 0',
    "systemctl": r'''echo "systemctl $*" >> "$CALLS"
alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
stop_() { if alive; then p=$(cat "$PIDF"); kill "$p"; for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.2; done; fi; rm -f "$PIDF"; }
start_() {
  [ -f "$RHINO_KIRI_SERVICE_FILE" ] || exit 5
  stop_
  wd=$(sed -n 's/^WorkingDirectory=//p' "$RHINO_KIRI_SERVICE_FILE")
  cmd=$(sed -n 's/^ExecStart=//p' "$RHINO_KIRI_SERVICE_FILE")
  ( cd "$wd" || exit 1; nohup $cmd > "$KIRI_LOG" 2>&1 & echo $! > "$PIDF" )
}
case "$*" in
  *is-active*) alive ;;
  *disable*) stop_ ;;
  stop*) stop_ ;;
  *enable*--now*|restart*) start_ ;;
  *) exit 0 ;;
esac''',
}
os.makedirs(BIN)
for name, body in STUBS.items():
    p = os.path.join(BIN, name)
    open(p, "w").write("#!/usr/bin/env bash\n" + body + "\n")
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
os.makedirs(os.path.dirname(SERVICE))
# PATH without Node.js: the system folders plus the stand-ins (python3, curl, tar ... from /usr/bin)
PATH = BIN + os.pathsep + "/usr/sbin:/usr/bin:/sbin:/bin"
assert not any(os.path.exists(os.path.join(d, "node")) for d in PATH.split(os.pathsep)), "node must not be on the test PATH"


def env(**extra):
    e = {"HOME": HOME, "USER": "tester", "PATH": PATH, "CALLS": LOG, "PIDF": PIDF, "RHINO_KIRI_SERVICE_FILE": SERVICE,
         "RHINO_MOONRAKER": f"http://127.0.0.1:{moon.server_port}", "RHINO_NODE_MIRROR": MIRROR_URL,
         "RHINO_NODE_VERSION": NODE_VER, "KIRI_LOG": os.path.join(ROOT, "kiri.log"), "TERM": "dumb", "LANG": "C.UTF-8"}
    e.update(extra)
    return e


def run(script, *args, stdin="", **extra):
    r = subprocess.run(["bash", script, *args], input=stdin, capture_output=True, text=True, env=env(**extra), timeout=300)
    return r.returncode, r.stdout + r.stderr


def kiri_up():
    try:
        return urllib.request.urlopen("http://127.0.0.1:8090/kiri/", timeout=2).status == 200
    except OSError:
        return False


def slicer():
    return json.load(open(os.path.join(CFG, "myrhino", "slicer.json")))


def calls():
    return open(LOG).read() if os.path.exists(LOG) else ""


try:
    print("== refusals ==")
    rc, out = run(INSTALL, FAKE_UID="0")
    ok(rc == 1 and "without sudo" in out and not os.path.exists(KHOME), "run with sudo: STOPPED, nothing changed")
    STATE["print_state"] = "printing"
    rc, out = run(INSTALL)
    ok(rc == 1 and "A job is printing" in out and not os.path.exists(KHOME) and calls() == "", "a job printing: STOPPED, nothing changed")
    STATE["print_state"] = "standby"
    shutil.move(os.path.join(CFG, "rhino", "slice"), os.path.join(ROOT, "slice-aside"))
    rc, out = run(INSTALL)
    ok(rc == 1 and "no Slice tab yet" in out and not os.path.exists(KHOME), "Rhino Tool Manager without the Slice tab: STOPPED")
    shutil.move(os.path.join(ROOT, "slice-aside"), os.path.join(CFG, "rhino", "slice"))

    print("== dry run ==")
    before = json.dumps(slicer())
    rc, out = run(INSTALL, "--dry-run")
    ok(rc == 0 and "Dry run finished" in out, "dry run finishes")
    ok(not os.path.exists(KHOME) and not os.path.exists(SERVICE) and json.dumps(slicer()) == before and calls() == "",
       "...and changes nothing (no files, no service, slicer.json as it was, no sudo/systemctl)")
    ok(f"would download {MIRROR_URL}/v{NODE_VER}/{tarname}" in out, "...and says it would download Node.js (none on this Pi)")

    print("== a download that does not match its checksum ==")
    good = open(os.path.join(MIRROR, f"v{NODE_VER}", tarname), "rb").read()
    open(os.path.join(MIRROR, f"v{NODE_VER}", tarname), "wb").write(good[:-10] + b"x" * 10)
    rc, out = run(INSTALL)
    ok(rc == 1 and "did not match its checksum" in out, "tampered Node.js download: STOPPED")
    ok(not os.path.exists(os.path.join(KHOME, "node")) and not os.path.exists(SERVICE) and slicer()["enabled"] is False,
       "...nothing installed, Slice tab still off")
    open(os.path.join(MIRROR, f"v{NODE_VER}", tarname), "wb").write(good)

    print("== install ==")
    open(LOG, "w").close()
    rc, out = run(INSTALL)
    ok(rc == 0 and "Kiri:Moto installed." in out, "install finishes")
    ok("download checked (sha256)" in out and os.access(os.path.join(KHOME, "node", "bin", "node"), os.X_OK),
       "Node.js downloaded, checked and put in ~/rhino-kiri/node")
    ok(os.path.realpath(os.path.join(KHOME, "app")) == os.path.join(KHOME, "app-4.7.0-1"), "app -> app-4.7.0-1")
    unit = open(SERVICE).read()
    ok("User=tester" in unit and f"ExecStart={KHOME}/node/bin/node {KHOME}/app/node_modules/@gridspace/app-server/app-server-run.js --single --port 8090" in unit
       and f"WorkingDirectory={KHOME}/app" in unit and f"ReadWritePaths={KHOME}" in unit, "service file: this login, its own Node.js, port 8090")
    ok("systemctl enable --now rhino-kiri" in calls() and "systemctl daemon-reload" in calls(), "service enabled to start at boot")
    ok(kiri_up(), "Kiri:Moto answers on port 8090 (started from the installed service file)")
    s = slicer()
    ok(s["enabled"] is True and s["work_area"] == {"LightSaber": {"x": 540, "y": 370}}, "Slice tab turned on, the other settings in slicer.json kept")
    ok(open(os.path.join(KHOME, "installed-version")).read().strip() == "4.7.0-1", "installed version recorded")

    print("== update to a newer package, then another ==")
    for v in ("4.7.0-2", "4.7.0-3"):
        p2 = os.path.join(ROOT, "pkg-" + v)
        make_package(p2, v)
        open(LOG, "w").close()
        rc, out = run(os.path.join(p2, "install-kiri.sh"))
        ok(rc == 0 and "already installed for Kiri:Moto" in out and "Downloading" not in out, f"{v}: Node.js reused, not downloaded again")
        ok("port 8090 is used by the installed Kiri:Moto" in out and kiri_up(), f"{v}: replaces the running one, answering again")
    apps = sorted(d for d in os.listdir(KHOME) if d.startswith("app-"))
    ok(apps == ["app-4.7.0-2", "app-4.7.0-3"] and os.path.realpath(os.path.join(KHOME, "app")).endswith("app-4.7.0-3"),
       "keeps the version in use and the one before it, removes older ones")

    print("== remove ==")
    rc, out = run(INSTALL, "--remove")
    ok(rc == 0 and not os.path.exists(SERVICE) and not kiri_up(), "remove: service stopped and its file gone")
    ok(slicer()["enabled"] is False and slicer()["work_area"] == {"LightSaber": {"x": 540, "y": 370}}, "...Slice tab off, other settings kept")
    ok(not os.path.exists(KHOME), "...~/rhino-kiri removed")

    print("== the menu: option 7 ==")
    zp = os.path.join(CFG, "rhino-kiri-4.7.0-1.zip")
    subprocess.run(["zip", "-qr", zp, "."], cwd=PKG, check=True)
    open(LOG, "w").close()
    rc, out = run(os.path.join(CFG, "rhino.sh"), stdin="7\n1\n1\ny\n\nq\n")
    ok("rhino-kiri-4.7.0-1.zip" in out and "DRY RUN" in out and "Kiri:Moto installed." in out, "7 > 1: lists the zip, previews, installs")
    ok(kiri_up() and slicer()["enabled"] is True, "...Kiri:Moto running, Slice tab on")
    ok(not os.path.exists(os.path.join(HOME, "rhino-kiri-4.7.0-1")), "...the unpacked copy is tidied away")
    rc, out = run(os.path.join(CFG, "rhino.sh"), stdin="7\n2\ny\n\nq\n")
    ok("Kiri:Moto removed." in out and not kiri_up() and slicer()["enabled"] is False, "7 > 2: removes it (installer kept in the config folder)")
finally:
    if os.path.exists(PIDF):
        try:
            os.kill(int(open(PIDF).read()), 15)
        except (OSError, ValueError):
            pass
    mirror.shutdown()
    moon.shutdown()
    time.sleep(0.3)
    shutil.rmtree(ROOT, ignore_errors=True)

print()
print("ALL PASSED" if not fails else f"{len(fails)} problems:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
