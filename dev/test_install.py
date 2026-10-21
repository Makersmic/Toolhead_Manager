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
    "sudo": 'echo "sudo $*" >> "$CALLS"; [ "${1:-}" = "-v" ] && exit 0; [ "${1:-}" = "-u" ] && shift 2; exec "$@"',
    # nginx: only "nginx -t" is used; NGINX_T_FAIL=1 makes it refuse the config
    "nginx": 'echo "nginx $*" >> "$CALLS"; [ "${NGINX_T_FAIL:-0}" = 1 ] && { echo "nginx: [emerg] unknown directive (fake)" >&2; exit 1; }; exit 0',
    # APT_404=1: "install" fails with 404 until "update" has run (stale package lists); APT_404=always: never works
    "apt-get": 'echo "apt-get $*" >> "$CALLS"; [ "${1:-}" = update ] && { touch "$CALLS.updated"; exit 0; }; case "${APT_404:-}" in always) echo "E: 404  Not Found"; exit 100 ;; 1) [ -f "$CALLS.updated" ] || { echo "E: 404  Not Found"; exit 100; } ;; esac; exit 0',
    "hostname": '[ "${1:-}" = "-I" ] && { echo 127.0.0.1; exit 0; }; echo "${FAKE_HOSTNAME:-127.0.0.1}"',
    # avahi (1.5.3): the name service is only installed, never run here; avahi-resolve answers for it
    "avahi-publish": 'echo "avahi-publish $*" >> "$CALLS"; exit 0',
    "avahi-resolve": 'echo "rhinostudio.local	127.0.0.1"',
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
  *rhino-studio-name*) exit 0 ;;
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
NGX = os.path.join(ROOT, "etc", "nginx")
for d in ("sites-available", "sites-enabled"):
    os.makedirs(os.path.join(NGX, d))
open(os.path.join(NGX, "nginx.conf"), "w").write("user www-data;\nhttp { include sites-enabled/*; }\n")
STUDIO = os.path.join(HOME, "rhino-studio")
SITE = os.path.join(NGX, "sites-available", "rhino-studio")
LINK = os.path.join(NGX, "sites-enabled", "rhino-studio")
with socket.socket() as s_:
    s_.bind(("127.0.0.1", 0))
    STUDIO_PORT = s_.getsockname()[1]
with socket.socket() as s_:
    s_.bind(("127.0.0.1", 0))
    NAME_PORT = s_.getsockname()[1]   # stands in for port 80 (1.5.3)
NSITE = os.path.join(NGX, "sites-available", "rhino-studio-name")
NLINK = os.path.join(NGX, "sites-enabled", "rhino-studio-name")
UNITS0 = os.path.join(ROOT, "units-default")
os.makedirs(UNITS0)
NUNIT = os.path.join(UNITS0, "rhino-studio-name.service")
AVAHI_SOCK = os.path.join(ROOT, "avahi-socket")   # avahi-daemon "running"
open(AVAHI_SOCK, "w").close()


def env(**extra):
    e = {"HOME": HOME, "USER": "tester", "PATH": BIN + os.pathsep + os.environ["PATH"], "CALLS": LOG, "PIDF": PIDF, "RHINO_SKIP_NET": "1", "RHINO_SKIP_UPDATER": "1",
         "RHINO_SERVICE_FILE": SERVICE, "RHINO_MOONRAKER": f"http://127.0.0.1:{moon.server_port}",
         "PORTAL_LOG": os.path.join(ROOT, "portal.log"), "TERM": "dumb", "LANG": "C.UTF-8",
         "RHINO_NGINX_DIR": NGX, "RHINO_NGINX_BIN": os.path.join(BIN, "nginx"), "RHINO_STUDIO_DIR": STUDIO,
         "RHINO_STUDIO_PORT": str(STUDIO_PORT), "RHINO_STUDIO_NAME_PORT": str(NAME_PORT), "RHINO_UNIT_DIR": UNITS0, "RHINO_AVAHI_SOCKET": AVAHI_SOCK}
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
    if not os.path.isfile(os.path.join(dest, "studio", "index.html")):   # a stand-in Studio build (dev/make_zip.sh adds the real one)
        os.makedirs(os.path.join(dest, "studio", "assets"), exist_ok=True)
        open(os.path.join(dest, "studio", "index.html"), "w").write("<!doctype html><title>Rhino Studio</title>")
        open(os.path.join(dest, "studio", "assets", "app-1.js"), "w").write("// v1")
        open(os.path.join(dest, "studio", "VERSION"), "w").write("0.6.0\n")
    return dest


# ---------------------------------------------------------------- a Pi with a Klipper config of its own
os.makedirs(CFG)
open(os.path.join(CFG, "printer.cfg"), "w").write("[include mainsail.cfg]\n[printer]\nkinematics: cartesian\n\n"
                                                  f"{MARK}\n#*# [probe]\n#*# z_offset = 1.234\n")
open(os.path.join(CFG, "moonraker.conf"), "w").write("[server]\nhost: 0.0.0.0\nport: 7130\n\n[authorization]\nport: 9\n")
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
    ok(not os.path.exists(STUDIO) and not os.path.exists(SITE) and f"would run: sudo {BIN}/nginx -t" in out,
       "...Studio: no files or nginx site, says it would check nginx before reloading it")

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
    # Studio on nginx
    site = open(SITE).read() if os.path.exists(SITE) else ""
    ok(os.path.isfile(os.path.join(STUDIO, "index.html")) and not any(k.startswith("studio/") for k in now),
       "Studio's files go to ~/rhino-studio, not into the config folder")
    ok(f"listen {STUDIO_PORT};" in site and f"root {STUDIO};" in site and "127.0.0.1:7130" in site and "@" not in site.split("server {", 1)[1],
       "nginx site filled in: port, Studio folder, Moonraker's port from moonraker.conf (not [authorization]'s)")
    ok(os.path.islink(LINK) and os.path.realpath(LINK) == os.path.realpath(SITE), "...and enabled")
    ok(calls.index(f"nginx -t") < calls.index("systemctl reload nginx") and "Studio:  http://127.0.0.1:" in out,
       "nginx -t passes before nginx is reloaded; the finish names Studio's address")
    ok("nginx -t" in calls and "systemctl restart nginx" not in calls, "...a reload, never a restart (Mainsail stays up)")
    # Studio by name (1.5.3): nothing on "port 80" here, so the site goes in without a Mainsail page to compare
    nsite = open(NSITE).read() if os.path.exists(NSITE) else ""
    nd = "\n".join(l.split("#", 1)[0] for l in nsite.splitlines())
    ok(f"listen {NAME_PORT};" in nd and "server_name rhinostudio.local;" in nd and "default_server" not in nd and f"root {STUDIO};" in nd
       and "rhino-studio-name-error.log" in nd and "@" not in nsite.split("server {", 1)[1] and os.path.islink(NLINK),
       "name site: port 80, only rhinostudio.local, never default_server, Studio's folder, its own log; enabled")
    unit = open(NUNIT).read() if os.path.exists(NUNIT) else ""
    ok("User=tester" in unit and f"/bin/bash {CFG}/scripts/rhino_studio_name.sh rhinostudio" in unit and "@" not in unit.split("[Unit]", 1)[1],
       "name service filled in: runs as this login, the script from the config folder, the name")
    ok("systemctl enable rhino-studio-name" in calls and "rhinostudio.local announced (127.0.0.1)" in out and "http://rhinostudio.local" in out,
       "...enabled; the install checks the name resolves and the finish names http://rhinostudio.local")
    lines = calls.splitlines()
    ok(lines.count("systemctl reload nginx") == 2 and lines.count("nginx -t") == 2, "the name site has its own nginx -t before its reload")
    open(os.path.join(STUDIO, "from-first-install"), "w").write("1")

    # ============================================================ update over the top
    print("== update (install again) ==")
    open(os.path.join(CFG, "myrhino", "custom_tools.cfg"), "a").write("# a tool added in the portal\n")
    posf = os.path.join(CFG, "myrhino", "positions.cfg")
    txt = open(posf).read()
    open(posf, "w").write(txt.replace("variable_park_x: 551.0", "variable_park_x: 540.0").replace("variable_zero_max_z: 290.0", "variable_zero_max_z: 300.0"))
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
    ok("zero_max_z is 300, past the bed's lowest point (Z295" in out and "safe_z is" not in out,
       "...and the install names the kept number that no longer fits Z travel (zero_max_z 300 > 295), and only that one")
    ok(portal_up(), "portal back up after the update")
    keep = os.path.join(HOME, bks[1], "_rhino_install")
    ok(os.path.isfile(os.path.join(keep, "old-rhino-studio", "from-first-install")) and os.path.isfile(os.path.join(keep, "old-rhino-studio.nginx")),
       "Studio update: the old Studio folder and site are kept in the new backup")
    ok(not os.path.exists(os.path.join(STUDIO, "from-first-install")) and os.path.isfile(os.path.join(STUDIO, "index.html")),
       "...and ~/rhino-studio is exactly the new build")

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
    ok(not os.path.exists(SITE) and not os.path.lexists(LINK) and not os.path.exists(STUDIO),
       "...Studio's nginx site and folder are gone again (there was none before)")
    ok(any(os.path.isdir(os.path.join(HOME, x, "rhino-studio")) for x in os.listdir(HOME) if x.startswith("rhino-undone-")),
       "...the Studio folder is kept aside too")
    ok(not os.path.exists(NSITE) and not os.path.lexists(NLINK) and not os.path.exists(NUNIT) and "systemctl disable --now rhino-studio-name" in open(LOG).read(),
       "...and rhinostudio.local goes too: name site and name service removed")

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

    # ============================================================ Studio problems never stop the install
    print("== Studio: nginx refuses, port taken, no Studio in the zip ==")
    PKG = os.path.join(HOME, f"rhino-{VERSION}")
    open(LOG, "w").close()
    rc, out = run(f"{PKG}/install.sh", NGINX_T_FAIL="1")
    ok(rc == 0 and "Install finished." in out and "did not accept the Studio site" in out and "unknown directive" in out,
       "nginx -t refuses the site: the install still finishes, and says why")
    ok(not os.path.exists(SITE) and not os.path.lexists(LINK) and "systemctl reload nginx" not in open(LOG).read(),
       "...the site is taken out again and nginx is never reloaded with it")
    run(f"{PKG}/uninstall.sh")
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", STUDIO_PORT))
    blocker.listen()
    rc, out = run(f"{PKG}/install.sh")
    blocker.close()
    ok(rc == 0 and f"something else already uses port {STUDIO_PORT}" in out and not os.path.exists(SITE),
       "Studio's port taken by something else: skipped with how to find it, install finishes")
    run(f"{PKG}/uninstall.sh")
    shutil.rmtree(os.path.join(PKG, "studio"))
    rc, out = run(f"{PKG}/install.sh")
    ok(rc == 0 and "this zip has no Studio in it" in out and not os.path.exists(STUDIO), "a zip without Studio: skipped, install finishes")
    run(f"{PKG}/uninstall.sh")

    # ============================================================ Studio by name (1.5.3)
    print("== Studio by name: Mainsail on port 80, its page changes, port 80 not nginx, no avahi, host already named ==")
    import http.server
    import threading
    mode = {"bad": False}

    class Fake80(http.server.BaseHTTPRequestHandler):
        """Mainsail on "port 80". In bad mode its page changes once the name site is in (what the install must catch)."""
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.headers.get("Host") == "rhinostudio.local" and os.path.lexists(NLINK):
                b = b"<title>Rhino Studio</title>"
            elif mode["bad"] and os.path.lexists(NLINK):
                b = b"<title>Rhino Studio</title> took the bare address"
            else:
                b = b"<title>Mainsail</title>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
    os.makedirs(os.path.join(PKG, "studio"), exist_ok=True)   # the test above took Studio out of the zip
    open(os.path.join(PKG, "studio", "index.html"), "w").write("<!doctype html><title>Rhino Studio</title>")
    srv80 = http.server.ThreadingHTTPServer(("127.0.0.1", NAME_PORT), Fake80)
    threading.Thread(target=srv80.serve_forever, daemon=True).start()
    try:
        # port 80 answers but no nginx site listens there: something else owns it
        rc, out = run(f"{PKG}/install.sh")
        ok(rc == 0 and "Install finished." in out and f"port {NAME_PORT} is used by something other than nginx" in out and not os.path.exists(NSITE),
           "port 80 taken by something that isn't nginx: name skipped with how to find it, install finishes")
        run(f"{PKG}/uninstall.sh")
        # Mainsail's site, as KIAUH / MainsailOS write it
        ms = os.path.join(NGX, "sites-available", "mainsail")
        open(ms, "w").write(f"server {{\n    listen {NAME_PORT} default_server;\n    root /home/tester/mainsail;\n}}\n")
        os.symlink(ms, os.path.join(NGX, "sites-enabled", "mainsail"))
        rc, out = run(f"{PKG}/install.sh")
        ok(rc == 0 and "serves Studio for rhinostudio.local" in out and "the bare address is unchanged" in out and os.path.lexists(NLINK),
           "next to Mainsail on port 80: the name site goes in, Studio answers its name, Mainsail still answers the bare address")
        ok(open(ms).read().count("default_server") == 1, "...Mainsail's site is not touched")
        run(f"{PKG}/uninstall.sh")
        mode["bad"] = True
        open(LOG, "w").close()
        rc, out = run(f"{PKG}/install.sh")
        ok(rc == 0 and "Install finished." in out and "bare address changed with the name site in, so it was taken out again" in out
           and not os.path.exists(NSITE) and not os.path.lexists(NLINK), "the bare address's page changes: the name site is taken out again, install finishes")
        ok(open(LOG).read().splitlines().count("systemctl reload nginx") == 3 and not os.path.exists(NUNIT) and "http://rhinostudio.local" not in out.split("Install finished.")[1],
           "...nginx reloaded without it, no name service, the finish doesn't offer the name")
        run(f"{PKG}/uninstall.sh")
        mode["bad"] = False
        # no avahi on the host (Ubuntu Server out of the box)
        rc, out = run(f"{PKG}/install.sh", RHINO_AVAHI_SOCKET=os.path.join(ROOT, "no-avahi"))
        ok(rc == 0 and "sudo apt install avahi-daemon avahi-utils" in out and not os.path.exists(NUNIT) and os.path.lexists(NLINK)
           and "apt-get install -y avahi" not in open(LOG).read(), "no avahi-daemon: the install says the one apt line to run and never installs the daemon itself")
        run(f"{PKG}/uninstall.sh")
        # 1.5.4: stale package lists (avahi-utils 404 on a Pi): refresh once and try again, then go on
        pub = os.path.join(BIN, "avahi-publish"); os.rename(pub, pub + ".off")
        for f in (LOG + ".updated",):
            if os.path.exists(f): os.remove(f)
        tree0 = tree(CFG)
        rc, out = run(f"{PKG}/install.sh", APT_404="1")
        calls = open(LOG).read()
        ok(rc == 0 and "refreshing the package lists" in out and "apt-get update -qq" in calls
           and calls.count("apt-get install -y avahi-utils") >= 2, "stale package lists (404): the install runs apt-get update and tries again, then finishes")
        run(f"{PKG}/uninstall.sh")
        rc, out = run(f"{PKG}/install.sh", APT_404="always")
        ok(rc == 1 and "apt could not install avahi-utils" in out and "Nothing after this point was changed" in out and tree(CFG) == tree0,
           "apt still fails after the refresh: STOPPED, config folder unchanged")
        os.rename(pub + ".off", pub)
        # the host is already called rhinostudio
        rc, out = run(f"{PKG}/install.sh", FAKE_HOSTNAME="rhinostudio")
        ok(rc == 0 and "already called rhinostudio" in out and not os.path.exists(NUNIT) and os.path.lexists(NLINK),
           "host already named rhinostudio: the name site goes in, no name service (avahi announces its own name)")
        run(f"{PKG}/uninstall.sh")
        # a bad name
        rc, out = run(f"{PKG}/install.sh", RHINO_STUDIO_NAME="Rhino Studio!")
        ok(rc == 0 and "must be letters, digits and dashes" in out and not os.path.exists(NSITE), "a bad RHINO_STUDIO_NAME is refused, install finishes")
        run(f"{PKG}/uninstall.sh")
        os.remove(os.path.join(NGX, "sites-enabled", "mainsail"))
        os.remove(ms)
    finally:
        srv80.shutdown()
        srv80.server_close()

    # ============================================================ the updater (1.5.3)
    print("== updater: set up by the install ==")
    UNITS = os.path.join(ROOT, "units"); os.makedirs(UNITS, exist_ok=True)
    UBIN = os.path.join(ROOT, "rhino-update")
    if os.geteuid() != 0:
        print("SKIP updater set-up (install -o root needs root here)")
    else:
        rc, out = run(f"{PKG}/install.sh", RHINO_SKIP_UPDATER="0", RHINO_UNIT_DIR=UNITS, RHINO_UPDATER_BIN=UBIN)
        drop = os.path.join(os.path.dirname(CFG), "rhino_data", "update")
        usvc = open(os.path.join(UNITS, "rhino-update.service")).read() if os.path.exists(os.path.join(UNITS, "rhino-update.service")) else ""
        upath = open(os.path.join(UNITS, "rhino-update.path")).read() if os.path.exists(os.path.join(UNITS, "rhino-update.path")) else ""
        ok(rc == 0 and os.path.isfile(UBIN) and os.path.isdir(os.path.join(drop, "incoming")), "updater program and drop folder installed")
        ok(f"--user tester --drop {drop}" in usvc and "@" not in usvc and "Type=oneshot" in usvc, "updater unit filled in for this login")
        ok(f"PathExists={drop}/request.json" in upath, "path unit watches the Portal's request file")
        ok("systemctl enable --now rhino-update.path" in open(LOG).read(), "path unit enabled")
        run(f"{PKG}/uninstall.sh")
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
