"""Installer test: run install.sh, uninstall.sh and the rhino.sh menu on a fake Pi and check what they do.

    python3 dev/test_install.py

The fake Pi is a temporary home folder (login "tester", not "pi") with an existing Klipper config of its own: a
SAVE_CONFIG block, saved variables, a GitHub-backup .git folder, a moonraker.conf. sudo, systemctl, apt-get, id
and hostname are stand-ins on PATH; the systemctl stand-in really starts the portal from the installed service file,
so the service file's paths are checked too. A small fake Moonraker reports the job state. Nothing outside the
temporary folder is touched. Needs bash, rsync, unzip/zip and Flask; uses port 5000 (SKIP if it's taken).
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


for tool in ("bash", "rsync", "unzip", "zip"):
    if not shutil.which(tool):
        print(f"SKIP installer test: {tool} is not installed")
        sys.exit(0)
with socket.socket() as s:
    if s.connect_ex(("127.0.0.1", 5000)) == 0:
        print("SKIP installer test: port 5000 is in use on this computer")
        sys.exit(0)

ROOT = tempfile.mkdtemp(prefix="rhino-install-")
HOME = os.path.join(ROOT, "home", "tester")
CFG = os.path.join(HOME, "printer_data", "config")
BIN = os.path.join(ROOT, "bin")
SERVICE = os.path.join(ROOT, "etc", "rhino-portal.service")
LOG = os.path.join(ROOT, "calls.log")
PIDF = os.path.join(ROOT, "portal.pid")
VERSION = open(os.path.join(REPO, "VERSION")).read().strip()
MARK = "#*# <---------------------- SAVE_CONFIG ---------------------->"

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
    # systemctl: is-active / stop / disable --now / enable --now / restart / daemon-reload, using the installed
    # service file's ExecStart, Environment and WorkingDirectory (python3 from PATH, so the test's Flask is used)
    "systemctl": r'''echo "systemctl $*" >> "$CALLS"
alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
stop_() { if alive; then p=$(cat "$PIDF"); kill "$p"; for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.2; done; fi; rm -f "$PIDF"; }
start_() {
  [ -f "$RHINO_SERVICE_FILE" ] || exit 5
  stop_
  wd=$(sed -n 's/^WorkingDirectory=//p' "$RHINO_SERVICE_FILE")
  cmd=$(sed -n 's/^ExecStart=//p' "$RHINO_SERVICE_FILE" | sed "s#^/usr/bin/python3#$(command -v python3)#")
  envs=$(sed -n 's/^Environment=//p' "$RHINO_SERVICE_FILE" | tr '\n' ' ')
  ( cd "$wd" || exit 1; env $envs nohup $cmd > "$PORTAL_LOG" 2>&1 & echo $! > "$PIDF" )
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 0.3; alive || break; python3 -c "import socket;s=socket.socket();exit(s.connect_ex(('127.0.0.1',5000)))" && break; done
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


def env(**extra):
    e = {"HOME": HOME, "USER": "tester", "PATH": BIN + os.pathsep + os.environ["PATH"], "CALLS": LOG, "PIDF": PIDF,
         "RHINO_SERVICE_FILE": SERVICE, "RHINO_MOONRAKER": f"http://127.0.0.1:{moon.server_port}",
         "PORTAL_LOG": os.path.join(ROOT, "portal.log"), "TERM": "dumb", "LANG": "C.UTF-8"}
    e.update(extra)
    return e


def run(script, *args, stdin="", **extra):
    r = subprocess.run(["bash", script, *args], input=stdin, capture_output=True, text=True, env=env(**extra), timeout=120)
    return r.returncode, r.stdout + r.stderr


def tree(d):
    """Fingerprint of a folder: relative path -> content hash (folders and links included)."""
    out = {}
    for base, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            p = os.path.join(base, f)
            out[os.path.relpath(p, d)] = hashlib.sha1(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else "link"
    return out


def portal_up():
    try:
        return urllib.request.urlopen("http://127.0.0.1:5000/", timeout=2).status == 200
    except OSError:
        return False


def backups():
    return sorted(x for x in os.listdir(HOME) if x.startswith("rhino-backup-"))


def package(dest):
    """The release zip's contents, unpacked (same exclusions as the zip)."""
    shutil.copytree(REPO, dest, ignore=shutil.ignore_patterns(".git", ".github", "__pycache__", "node_modules", "manual",
                                                              "docs", "*.zip", "package*.json"))
    return dest


# ---------------------------------------------------------------- a Pi with a Klipper config of its own
os.makedirs(CFG)
open(os.path.join(CFG, "printer.cfg"), "w").write("[include mainsail.cfg]\n[printer]\nkinematics: cartesian\n\n"
                                                  f"{MARK}\n#*# [probe]\n#*# z_offset = 1.234\n")
open(os.path.join(CFG, "moonraker.conf"), "w").write("[server]\nhost: 0.0.0.0\n")
open(os.path.join(CFG, "variables.cfg"), "w").write("[gcode_macro VARIABLES]\nvariable_tool_swap_park_x: 100.0\nvariable_tool_swap_park_y: 100.0\ngcode:\n")
os.makedirs(os.path.join(CFG, ".git", "refs", "heads"))
open(os.path.join(CFG, ".git", "HEAD"), "w").write("ref: refs/heads/main\n")
open(os.path.join(CFG, ".git", "refs", "heads", "main"), "w").write("1111111111111111111111111111111111111111\n")
open(LOG, "w").close()
PKG = package(os.path.join(HOME, f"rhino-{VERSION}"))
original = tree(CFG)

try:
    # ============================================================ refusals: each stops before changing anything
    print("== refusals ==")
    rc, out = run(f"{PKG}/install.sh", FAKE_UID="0")
    ok(rc == 1 and "without sudo" in out and tree(CFG) == original, "run with sudo: STOPPED, nothing changed")
    STATE["print_state"] = "printing"
    rc, out = run(f"{PKG}/install.sh")
    ok(rc == 1 and "A job is printing" in out and tree(CFG) == original and not backups(), "a job printing: STOPPED, no backup, nothing changed")
    STATE["print_state"] = "standby"
    inside = os.path.join(CFG, "rhino-inside")
    shutil.copytree(PKG, inside)
    rc, out = run(f"{inside}/install.sh")
    ok(rc == 1 and "inside your config folder" in out, "package unzipped inside the config folder: STOPPED")
    shutil.rmtree(inside)
    rc, out = run(f"{PKG}/install.sh", RHINO_CONFIG_DIR=os.path.join(ROOT, "nowhere"))
    ok(rc == 1 and "No printer.cfg" in out, "no printer.cfg: STOPPED")
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 5000))
    blocker.listen()
    rc, out = run(f"{PKG}/install.sh")
    blocker.close()
    ok(rc == 1 and "Something else is using port 5000" in out and tree(CFG) == original, "port 5000 taken by something else: STOPPED, nothing changed")

    # ============================================================ dry run
    print("== preview (dry run) ==")
    open(LOG, "w").close()
    rc, out = run(f"{PKG}/install.sh", "--dry-run")
    ok(rc == 0 and "Dry run finished - nothing was changed" in out, "dry run finishes")
    ok(tree(CFG) == original and not backups() and not os.path.exists(SERVICE), "...and really changes nothing (config, backups, service)")
    ok("SAVE_CONFIG section - it would be carried over" in out and "would change /home/pi in:" in out, "...and says what it would do")
    ok(open(LOG).read() == "", "...without calling sudo, apt or systemctl")

    # ============================================================ first install
    print("== first install ==")
    rc, out = run(f"{PKG}/install.sh")
    ok(rc == 0 and "Install finished." in out, "install finishes" + ("" if rc == 0 else f" - {out[-600:]}"))
    bks = backups()
    bk = {k: v for k, v in tree(os.path.join(HOME, bks[0])).items() if not k.startswith("_rhino_install/")} if bks else {}
    ok(len(bks) == 1 and bk == original, "backup made first, an exact copy of the old config folder")
    now = tree(CFG)
    ok(all(k in now for k in ("toolchanger.cfg", "scripts/rhino_portal.py", "rhino/portal/__init__.py")), "new files copied in")
    ok(not any(k.startswith(("dev/", "install.sh", "uninstall.sh", "rhino.sh", "VERSION")) for k in now), "dev/, the installers and VERSION are not copied")
    ok(now[".git/HEAD"] == original[".git/HEAD"] and now[".git/refs/heads/main"] == original[".git/refs/heads/main"],
       "your own .git (GitHub backup) is left alone")
    ok(open(os.path.join(CFG, "variables.cfg")).read() == open(os.path.join(HOME, bks[0], "variables.cfg")).read(),
       "variables.cfg (saved state: paper test, mounted tool) kept")
    pc = open(os.path.join(CFG, "printer.cfg")).read()
    ok(pc.count(MARK) == 1 and "z_offset = 1.234" in pc, "SAVE_CONFIG block carried over, exactly once")
    stale = [k for k in now if k.endswith(".cfg") and "/home/pi" in open(os.path.join(CFG, k), errors="ignore").read()]
    ok(not stale, f"/home/pi paths pointed at this login's home ({stale})")
    svc = open(SERVICE).read() if os.path.exists(SERVICE) else ""
    ok("User=tester" in svc and f"WorkingDirectory={CFG}" in svc and f"{CFG}/scripts/rhino_portal.py" in svc and "/home/pi" not in svc,
       "service file installed for this login (User, folder, start command)")
    ok(portal_up(), "the portal started from that service file answers on port 5000")
    ok(os.path.isfile(os.path.join(CFG, "myrhino", "positions.cfg")) and "myrhino/positions.cfg is new" in out,
       "positions.cfg put in place (first install), and the install says so")
    ok("You can delete those three lines" in out, "...and it points out the old tool_swap_park lines in variables.cfg")
    calls = open(LOG).read()
    ok("systemctl daemon-reload" in calls and "systemctl enable --now rhino-portal" in calls, "service enabled to start at boot")

    # ============================================================ update over the top
    print("== update (install again) ==")
    open(os.path.join(CFG, "myrhino", "custom_tools.cfg"), "a").write("# a tool added in the portal\n")
    posf = os.path.join(CFG, "myrhino", "positions.cfg")
    txt = open(posf).read()
    open(posf, "w").write(txt.replace("variable_park_x: 551.0", "variable_park_x: 540.0"))
    before_update = tree(CFG)
    rc, out = run(f"{PKG}/install.sh")
    ok(rc == 0 and "an existing rhino-portal service was found" in out and "used by the old rhino-portal service" in out,
       "second install: finds the running portal, replaces it")
    bks = backups()
    ok(len(bks) == 2 and not os.path.exists(os.path.join(HOME, bks[0], "config")),
       f"a second backup of its own, even in the same minute - not copied inside the first ({bks})")
    ok(open(os.path.join(CFG, "printer.cfg")).read().count(MARK) == 1, "still exactly one SAVE_CONFIG block")
    ok(tree(CFG)["myrhino/custom_tools.cfg"] == before_update["myrhino/custom_tools.cfg"], "tools added in the portal (custom_tools.cfg) kept")
    ok("variable_park_x: 540.0" in open(posf).read() and "positions (myrhino/positions.cfg) kept" in out,
       "your edited positions (myrhino/positions.cfg) kept on update")
    ok(portal_up(), "portal back up after the update")

    # ============================================================ undo
    print("== undo (uninstall.sh) ==")
    first = os.path.join(HOME, backups()[0])
    rc, out = run(f"{PKG}/uninstall.sh", "--dry-run", first)
    ok(rc == 0 and "Dry run finished" in out and tree(CFG)["myrhino/custom_tools.cfg"] == before_update["myrhino/custom_tools.cfg"],
       "undo preview changes nothing")
    rc, out = run(f"{PKG}/uninstall.sh", first)
    restored = tree(CFG)
    ok(rc == 0 and restored == original, "undo to the first backup: the config folder is exactly as before the first install")
    ok(not os.path.exists(SERVICE) and not portal_up(), "...the service is removed and the portal stopped")
    ok(any(x.startswith("rhino-undone-") for x in os.listdir(HOME)), "...and what was there is kept aside in ~/rhino-undone-<time>")

    # ============================================================ the menu: option 3 (new zip), then option 4 back
    print("== menu: install a new zip ==")
    zp = os.path.join(CFG, f"rhino-config-{VERSION}.zip")
    subprocess.run(["zip", "-qr", zp, "."], cwd=PKG, check=True)
    shutil.rmtree(PKG)
    rc, out = run(os.path.join(REPO, "rhino.sh"), stdin="3\n1\ny\n\nq\n")
    ok(os.path.isfile(os.path.join(HOME, f"rhino-{VERSION}", "install.sh")), f"option 3 unpacks the zip to ~/rhino-{VERSION}")
    ok("DRY RUN" in out and "Install finished." in out, "...shows the preview, then installs after 'y'")
    ok(open(os.path.join(HOME, "rhino-manager", "installed-version")).read().strip() == VERSION and
       os.path.isfile(os.path.join(HOME, "rhino-manager", "rhino.sh")), "...and records the version; the menu is kept in ~/rhino-manager")
    ok(not os.path.exists(os.path.join(CFG, ".git", "objects")) and tree(CFG)[".git/HEAD"] == original[".git/HEAD"],
       "the zip carries no .git of its own")
    ok(portal_up(), "portal running after a menu install")
    rc, out = run(os.path.join(HOME, "rhino-manager", "rhino.sh"), stdin="4\n1\ny\n\nq\n")
    ok(tree(CFG) == original and not os.path.exists(os.path.join(HOME, "rhino-manager", "installed-version")),
       "menu option 4 puts the oldest backup back and forgets the installed version")
finally:
    if os.path.exists(PIDF):
        try:
            os.kill(int(open(PIDF).read()), 15)
        except (OSError, ValueError):
            pass
    moon.shutdown()
    shutil.rmtree(ROOT, ignore_errors=True)

print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
