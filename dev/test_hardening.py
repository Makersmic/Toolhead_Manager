"""Durability tests: what happens when the power goes, Moonraker hangs or the Portal sticks (Tool Manager 1.9.45).

    python3 dev/test_hardening.py

Files are written so a power cut leaves the old or the new one (rhino/atomic.py) and the usage meters fall back to their
last good copy; Moonraker not answering doesn't make every web request wait; the monitor's long poll doesn't hold up a web
request; the Portal's watchdog tells systemd only while the Portal answers; the service file asks for it. No machine,
no systemd: all stand-ins."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import http.server

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from rhino import atomic, moonraker
from rhino.errors import Fail
from rhino.maint import meters
from rhino.monitor import Monitor
from rhino.portal import watchdog

fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


TMP = tempfile.mkdtemp(prefix="rhino-hardening-")

# ---------------------------------------------------------------- atomic writes
p = os.path.join(TMP, "a", "file.json")
fsyncs = []
real_fsync = os.fsync
os.fsync = lambda fd: (fsyncs.append(fd), real_fsync(fd))[1]
atomic.write_text(p, "one")
os.fsync = real_fsync
ok(open(p).read() == "one" and (os.stat(p).st_mode & 0o777) == 0o644, "a new file is written whole, mode 0644")
ok(len(fsyncs) >= 2, f"the data and then the folder are flushed to the disk ({len(fsyncs)} fsyncs)")
os.chmod(p, 0o600)
atomic.write_text(p, "two")
ok(open(p).read() == "two" and (os.stat(p).st_mode & 0o777) == 0o600, "an existing file keeps its permissions")
ok(os.listdir(os.path.dirname(p)) == ["file.json"], "no temp file is left after a good write")

real_replace = os.replace
def boom(*a):
    raise OSError("disk full")
os.replace = boom
try:
    atomic.write_text(p, "three")
    ok(False, "a failed rename is reported")
except OSError:
    ok(True, "a failed rename is reported")
finally:
    os.replace = real_replace
ok(open(p).read() == "two" and os.listdir(os.path.dirname(p)) == ["file.json"], "...the old file is untouched and no temp is left")

ths = [threading.Thread(target=atomic.write_text, args=(p, f"writer {i}" * 500)) for i in range(12)]
[t.start() for t in ths]
[t.join() for t in ths]
body = open(p).read()
ok(body in {f"writer {i}" * 500 for i in range(12)} and os.listdir(os.path.dirname(p)) == ["file.json"], "twelve writers at once: one whole file wins, nothing left over")

# ---------------------------------------------------------------- meters after a power cut
mp = os.path.join(TMP, "m", "meters.json")
st = meters.MeterStore(mp)
st.data["machine"]["up_h"] = 11.0
st.dirty = True
st.save()
first = open(mp).read()
st.data["machine"]["up_h"] = 12.0
st.dirty = True
st.save()
ok(open(mp + ".prev").read() == first and json.loads(open(mp).read())["machine"]["up_h"] == 12.0, "each save keeps the one before it as .prev")
open(mp, "w").close()                          # what a power cut can leave: an empty file
back = meters.MeterStore(mp)
ok(back.data["machine"]["up_h"] == 11.0, "an empty meters file falls back to the last good copy, not zero")
ok(os.path.exists(mp + ".bad"), "...and the bad file is kept for a look")
open(mp, "w").write("{broken")
open(mp + ".prev", "w").write("also broken")
fresh = meters.MeterStore(mp)
ok(fresh.data["machine"]["up_h"] == 0.0 and os.path.exists(mp + ".bad"), "both unreadable: starts fresh, keeps the bad file (as before)")
st2 = meters.MeterStore(os.path.join(TMP, "m2", "meters.json"))
st2.dirty = True
st2.save()
open(st2.path, "w").write("{broken")
st2.dirty = True
st2.save()
ok(not os.path.exists(st2.path + ".prev") or json.loads(open(st2.path + ".prev").read()), "a bad file is never copied over the good .prev")

# ---------------------------------------------------------------- Moonraker that never answers
dead = socket.socket()
dead.bind(("127.0.0.1", 0))
dead.listen(8)                                  # accepts connections in the kernel, never answers
mr = moonraker.Moonraker(f"http://127.0.0.1:{dead.getsockname()[1]}", timeout=0.4)
t0 = time.time()
try:
    mr.klippy_state()
except Fail:
    pass
first_s = time.time() - t0
ok(0.3 < first_s < 1.5, f"the first call waits its short time ({first_s:.2f} s)")
t0 = time.time()
states = [mr.klippy_state() for _ in range(5)]
quick = time.time() - t0
ok(states == ["offline"] * 5 and quick < 0.2, f"then five more calls fail at once, not 5 x 0.4 s ({quick:.3f} s)")
ok(mr.status()["online"] is False, "status() says offline without waiting")
moonraker.HUNG_FOR = 0.3
mr._hung_until = time.monotonic() + 0.3
time.sleep(0.4)
t0 = time.time()
mr.klippy_state()
ok(time.time() - t0 > 0.3, "after a few seconds it tries Moonraker again")
before = mr._hung_until
mr._hung_until = 0.0
try:
    mr._call("GET", "/server/history/list", timeout=0.3)
except Fail:
    pass
ok(mr._hung_until == 0.0, "a call with its own long wait doesn't start the quick-fail period")
mr._hung_until = time.monotonic() + 30
t0 = time.time()
try:
    mr._call("GET", "/server/database/list", timeout=0.3)
except Fail:
    pass
ok(time.time() - t0 > 0.25, "...and isn't stopped by it either")
refused = socket.socket()
refused.bind(("127.0.0.1", 0))
port = refused.getsockname()[1]
refused.close()
mr2 = moonraker.Moonraker(f"http://127.0.0.1:{port}", timeout=0.4)
mr2.klippy_state()
ok(mr2._hung_until == 0.0, "a refused connection (Moonraker off) is not treated as a hang")
dead.close()

# ---------------------------------------------------------------- the monitor's poll doesn't hold up a web request
gate = threading.Event()
class SlowMR:
    def klippy_state(self):
        gate.wait(5)
        return "offline"
class _Paths:
    restart_flag = os.path.join(TMP, "no_restart_pending")
    state_dir = TMP
mon = Monitor(_Paths(), SlowMR())
th = threading.Thread(target=lambda: mon.tick(time.time()), daemon=True)
th.start()
time.sleep(0.2)
t0 = time.time()
info = mon.job_info()
ok(time.time() - t0 < 0.5 and info["active"] is False, f"job_info answers while the monitor waits on Moonraker ({time.time() - t0:.3f} s)")
gate.set()
th.join(3)

# ---------------------------------------------------------------- the Portal's watchdog
told = []
state = {"up": False}
dog = watchdog.Watchdog("http://x/api/ping", check=lambda u: state["up"], tell=told.append, wait=lambda s: True)
dog.period = 90.0
ok(dog.step() is False and told == [], "a Portal that doesn't answer is not called READY and gets no sign of life")
state["up"] = True
dog.step()
dog.step()
ok(told == ["READY=1", "WATCHDOG=1", "WATCHDOG=1"], f"once it answers: READY once, then a sign of life each round ({told})")
state["up"] = False
dog.step()
ok(told == ["READY=1", "WATCHDOG=1", "WATCHDOG=1"], "when it stops answering the signs of life stop (systemd restarts it)")
for k in ("NOTIFY_SOCKET", "WATCHDOG_USEC"):
    os.environ.pop(k, None)
ok(watchdog.Watchdog("http://x/").start() is None and watchdog.notify("READY=1") is False, "without systemd's socket it does nothing at all")
os.environ["WATCHDOG_USEC"] = "90000000"
ok(watchdog.watchdog_seconds() == 90.0 and watchdog.Watchdog("http://x/").every == 20.0, "90 s of watchdog means a sign of life every 20 s")
os.environ["WATCHDOG_USEC"] = "6000000"
ok(watchdog.Watchdog("http://x/").every == 2.0, "...and every third of it for a short one")
os.environ.pop("WATCHDOG_USEC")
sock_path = os.path.join(TMP, "notify.sock")
srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
srv.bind(sock_path)
srv.settimeout(2)
os.environ["NOTIFY_SOCKET"] = sock_path
ok(watchdog.notify("READY=1") is True and srv.recv(100) == b"READY=1", "READY=1 really reaches a notify socket")
os.environ.pop("NOTIFY_SOCKET")
srv.close()

class Slow(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path == "/hang":
            time.sleep(3)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")
web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
threading.Thread(target=web.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{web.server_port}"
ok(watchdog.answers(base + "/ok", 1) is True, "answers() is true for a server that replies")
t0 = time.time()
ok(watchdog.answers(base + "/hang", 0.5) is False and time.time() - t0 < 1.5, "...false for one that hangs, after the short wait")
web.shutdown()
ok(watchdog.answers(base + "/ok", 1) is False, "...and false for one that is gone")

# ---------------------------------------------------------------- the service file asks for it
unit = open(os.path.join(REPO, "service", "rhino-portal.service")).read()
ok("Type=notify" in unit and "NotifyAccess=main" in unit and "WatchdogSec=90" in unit, "rhino-portal.service: notify, main process only, 90 s watchdog")
ok("Restart=on-failure" in unit, "...and still restarts on failure (a missed watchdog counts as one)")
ok("rhino_portal.py" in unit and "--port 5000" in unit, "...and still starts the same program on the same port")

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
