"""scripts/rhino_snapshot_deb.py (1.5.5): fetch a vanished package from snapshot.debian.org, only if its SHA256 matches
this Pi's package lists. A local stand-in for snapshot.debian.org, and stand-ins for apt-cache and dpkg.
Run: python3 dev/test_snapshot.py"""
import hashlib, http.server, json, os, shutil, subprocess, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "rhino_snapshot_deb.py")
T = tempfile.mkdtemp(prefix="rhino-snap-")
fails = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

GOOD = b"!<arch>\ngenuine avahi-utils deb"
BAD = b"!<arch>\nsomething else"
SNAP = {"files": {}, "list": [], "up": True}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if not SNAP["up"]:
            self.send_response(503); self.end_headers(); return
        if self.path.startswith("/mr/binary/avahi-utils/0.8-5%2Bdeb11u3/binfiles"):
            b = json.dumps({"result": SNAP["list"]}).encode()
        elif self.path.startswith("/file/") and self.path[6:] in SNAP["files"]:
            b = SNAP["files"][self.path[6:]]
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

BIN = os.path.join(T, "bin"); os.makedirs(BIN)
def stub(name, body):
    p = os.path.join(BIN, name); open(p, "w").write("#!/bin/sh\n" + body + "\n"); os.chmod(p, 0o755)
stub("dpkg", 'echo arm64')
stub("apt-cache", r'''case "$1" in
  policy) echo "avahi-utils:"; echo "  Installed: (none)"; echo "  Candidate: ${CAND:-0.8-5+deb11u3}" ;;
  show) echo "Package: avahi-utils"; echo "SHA256: $WANT" ;;
esac''')

def run(want, cand=None):
    env = {**os.environ, "PATH": BIN + os.pathsep + os.environ["PATH"], "WANT": want, "RHINO_SNAPSHOT_URL": f"http://127.0.0.1:{srv.server_port}"}
    if cand: env["CAND"] = cand
    return subprocess.run([sys.executable, SCRIPT, "avahi-utils", os.path.join(T, "out")], capture_output=True, text=True, env=env, timeout=60)

good_h, bad_h = hashlib.sha1(GOOD).hexdigest(), hashlib.sha1(BAD).hexdigest()
SNAP["files"] = {good_h: GOOD, bad_h: BAD}
want = hashlib.sha256(GOOD).hexdigest()

SNAP["list"] = [{"architecture": "armhf", "hash": bad_h}, {"architecture": "arm64", "hash": good_h}]
r = run(want)
ok(r.returncode == 0 and r.stdout.strip().endswith("avahi-utils_0.8-5+deb11u3_arm64.deb") and open(r.stdout.strip(), "rb").read() == GOOD,
   "S1 the arm64 file whose SHA256 matches the Pi's package lists is fetched")
SNAP["list"] = [{"architecture": "arm64", "hash": bad_h}]
shutil.rmtree(os.path.join(T, "out"), ignore_errors=True)
r = run(want)
ok(r.returncode == 1 and "matching this Pi's package lists" in r.stderr and not os.path.exists(os.path.join(T, "out")),
   "S2 a file that doesn't match the Pi's SHA256 is never kept")
SNAP["list"] = [{"architecture": "arm64", "hash": "../../etc/passwd"}]
ok(run(want).returncode == 1, "S3 a hash that isn't hex is ignored")
SNAP["list"] = [{"architecture": "arm64", "hash": good_h}]
ok(run("").returncode == 1 and "no SHA256" in run("").stderr, "S4 no SHA256 in the package lists: refuses")
ok(run(want, cand="(none)").returncode == 1, "S5 apt doesn't know the package: refuses")
SNAP["up"] = False
r = run(want)
ok(r.returncode == 1 and "didn't answer" in r.stderr, "S6 snapshot.debian.org down: says so, exit 1")

srv.shutdown(); shutil.rmtree(T, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
