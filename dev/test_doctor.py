"""Health check (scripts/rhino_doctor.py, menu option 7) on a pretend host.

    python3 dev/test_doctor.py

A temp home with a config folder, stand-in systemctl and timedatectl on PATH, a fake /sys and /dev tree
(RHINO_SYS_ROOT) with the Octopus's by-id link, its USB power setting and a camera, and tiny Moonraker and Portal
servers. Checks that it changes nothing, finds what's wrong, and that --compare lines two reports up."""
import glob, hashlib, http.server, json, os, shutil, subprocess, sys, tempfile, threading
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOC = os.path.join(REPO, "scripts", "rhino_doctor.py")
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


T = tempfile.mkdtemp(prefix="rhino-doctor-")
HOME = os.path.join(T, "home", "pi")
CFG = os.path.join(HOME, "printer_data", "config")
os.makedirs(os.path.join(CFG, "myrhino"))
SERIAL = "/dev/serial/by-id/usb-Klipper_stm32f446xx_460055000951303532383235-if00"
open(os.path.join(CFG, "printer.cfg"), "w").write(
    f"[include mainsail.cfg]\n[include myrhino/custom_tools.cfg]\n[include myrhino/job_hooks.cfg]\n[mcu]\nserial: {SERIAL}\n")
open(os.path.join(CFG, "mainsail.cfg"), "w").write("# client\n")
open(os.path.join(CFG, "myrhino", "custom_tools.cfg"), "w").write("#\n")
open(os.path.join(CFG, "myrhino", "job_hooks.cfg"), "w").write("#\n")
open(os.path.join(CFG, "VERSION"), "w").write("1.9.4\n")
os.makedirs(os.path.join(HOME, "rhino-manager"))
open(os.path.join(HOME, "rhino-manager", "installed-version"), "w").write("1.9.4\n")

# fake /sys and /dev: the board's by-id link -> ttyACM0 -> a USB device whose power/control is "auto"
SYS = os.path.join(T, "root")
os.makedirs(SYS + "/dev/serial/by-id")
open(SYS + "/dev/ttyACM0", "w").close()
open(SYS + "/dev/video0", "w").close()
os.symlink(SYS + "/dev/ttyACM0", SYS + SERIAL)
usbdev = SYS + "/sys/devices/pci0000:00/usb1/1-3"
os.makedirs(usbdev + "/1-3:1.0")
os.makedirs(usbdev + "/power")
open(usbdev + "/power/control", "w").write("auto\n")
os.makedirs(SYS + "/sys/class/tty/ttyACM0")
os.symlink(usbdev + "/1-3:1.0", SYS + "/sys/class/tty/ttyACM0/device")
os.makedirs(SYS + "/sys/module/usbcore/parameters")
open(SYS + "/sys/module/usbcore/parameters/autosuspend", "w").write("2\n")

# stand-in commands: systemctl reads its answers from a JSON file the test edits
BIN = os.path.join(T, "bin")
os.makedirs(BIN)
STATE = os.path.join(T, "systemd.json")
json.dump({"is-active": {"klipper": "active", "moonraker": "active", "rhino-portal": "active", "nginx": "active",
                         "crowsnest": "inactive", "NetworkManager": "active", "dhcpcd": "inactive"},
           "is-enabled": {}}, open(STATE, "w"))
open(BIN + "/systemctl", "w").write(f"""#!/usr/bin/env python3
import json, sys
s = json.load(open({STATE!r}))
v = s.get(sys.argv[1], {{}}).get(sys.argv[2], "inactive" if sys.argv[1] == "is-active" else "enabled")
print(v); sys.exit(0 if v in ("active", "enabled", "masked") else 3)
""")
open(BIN + "/timedatectl", "w").write("#!/bin/sh\necho yes\n")
for f in ("systemctl", "timedatectl"):
    os.chmod(os.path.join(BIN, f), 0o755)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = {"/server/info": {"result": {"klippy_state": "ready", "moonraker_version": "v0.9.3-1"}},
                "/printer/info": {"result": {"software_version": "v0.13.0-200"}},
                "/api/state": {"ok": True}}.get(self.path)
        b = json.dumps(body or {}).encode()
        self.send_response(200 if body else 404); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}"
ENV = dict(os.environ, HOME=HOME, USER="pi", PATH=BIN + os.pathsep + os.environ["PATH"], RHINO_SYS_ROOT=SYS,
           RHINO_CONFIG_DIR=CFG, RHINO_MOONRAKER=URL, RHINO_PORTAL=URL)


def tree():
    h = hashlib.sha256()
    for p in sorted(glob.glob(CFG + "/**", recursive=True)):
        if os.path.isfile(p):
            h.update(p.encode() + open(p, "rb").read())
    return h.hexdigest()


def doctor(*args):
    p = subprocess.run([sys.executable, DOC, *args], capture_output=True, text=True, env=ENV, timeout=60)
    return p.returncode, p.stdout + p.stderr


def line(out, text):
    return next((ln for ln in out.splitlines() if text in ln), "")


before = tree()
code, out = doctor()
ok(tree() == before, "it changes nothing in the config folder")
ok("PASS  Login is pi" in out, "login pi passes")
ok("PASS  NetworkManager runs the network" in out, "NetworkManager is recognised")
ok("PASS  [mcu] is connected" in out, "the Octopus by-id link is found")
ok("PASS  Camera device: video0" in out, "the camera is found")
ok("PASS  klipper is running" in out and "PASS  Moonraker answers; Klipper is ready" in out and "PASS  The Portal answers" in out,
   "services, Moonraker and the Portal")
ok("PASS  myrhino/job_hooks.cfg is there and included" in out, "job_hooks.cfg is there and included")
ok("WARN  This PC can still go to sleep" in out or "INFO  Sleep isn't masked" in out, "sleep that isn't masked is reported")
ok("INFO  USB power saving is on for the board's port" in out, "USB autosuspend on the board's port is noted (the doc's 9.4 fallback)")
ok("WARN  No Rhino backup on this machine yet" in out and "WARN  klipper-backup isn't installed" in out, "no backups yet is a warning")
ok(code == 0, f"no FAIL -> exit 0 ({line(out, 'Summary')})")
reports = glob.glob(os.path.join(HOME, "rhino-health-*.json"))
ok(len(reports) == 1 and json.load(open(reports[0]))["facts"]["klipper"] == "v0.13.0-200", "the report is saved with its facts")

# the 7050 after the move, with things to fix
st = json.load(open(STATE))
st["is-enabled"] = {t: "masked" for t in ("sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target")}
st["is-active"]["rhino-portal"] = "failed"
json.dump(st, open(STATE, "w"))
open(SYS + "/sys/module/usbcore/parameters/autosuspend", "w").write("-1\n")
os.remove(SYS + SERIAL)
os.remove(os.path.join(CFG, "myrhino", "job_hooks.cfg"))
os.remove(os.path.join(CFG, "mainsail.cfg"))
os.symlink(os.path.join(HOME, "mainsail-config", "client.cfg"), os.path.join(CFG, "mainsail.cfg"))
import time; time.sleep(1.1)
code, out = doctor()
ok("PASS  Sleep and suspend are switched off (masked)" in out, "masked sleep passes")
ok("PASS  USB power saving won't switch the board off (autosuspend off)" in out, "autosuspend off passes")
ok("FAIL  [mcu] isn't connected" in out and "ls /dev/serial/by-id/" in out, "an unplugged board fails and says how to look")
ok("FAIL  rhino-portal is failed" in out, "a failed Portal service fails")
ok("FAIL  myrhino/job_hooks.cfg is missing" in out, "a missing job_hooks.cfg fails")
ok("FAIL  mainsail.cfg points at a file that isn't there" in out, "a broken mainsail.cfg link fails")
ok(code == 1, "any FAIL -> exit 1")
reports = sorted(glob.glob(os.path.join(HOME, "rhino-health-*.json")))
ok(len(reports) == 2, "a second report is saved beside the first")
code, out = doctor("--compare", *reports)
ok(code == 0 and "boards" in out and "* boards" in out, "--compare marks the board line that differs")
ok("To fix on the second machine" in out and "rhino-portal is failed" in out, "--compare lists what to fix on the second")

# the menu runs it
sh = open(os.path.join(REPO, "rhino.sh")).read()
ok("7)" in sh and "rhino_doctor.py" in sh, "rhino.sh menu option 7 runs the health check")

srv.shutdown()
shutil.rmtree(T, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{len(fails)} FAILED")
sys.exit(1 if fails else 0)
