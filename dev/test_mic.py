"""scripts/rhino_mic.sh (the camera's microphone, docs/install-mic.md) against stand-ins for sudo, apt-get, systemctl,
curl and ffmpeg. Nothing outside a temporary folder is touched and nothing is downloaded.

    python3 dev/test_mic.py
"""
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


T = tempfile.mkdtemp(prefix="rhino-mic-")
HOME = os.path.join(T, "home")
CFG = os.path.join(HOME, "printer_data", "config")
ROOT = os.path.join(T, "root")
BIN = os.path.join(T, "bin")
LOG = os.path.join(T, "calls.log")
for d in (os.path.join(CFG, "scripts"), os.path.join(CFG, "service"), os.path.join(ROOT, "proc", "asound"),
          os.path.join(ROOT, "etc", "systemd", "system"), os.path.join(ROOT, "etc", "nginx", "sites-available"), BIN):
    os.makedirs(d)
shutil.copy(os.path.join(REPO, "scripts", "rhino_mic.sh"), os.path.join(CFG, "scripts"))
for f in ("rhino-mic.service", "rhino-mic.yaml"):
    shutil.copy(os.path.join(REPO, "service", f), os.path.join(CFG, "service"))
CARDS = os.path.join(ROOT, "proc", "asound", "cards")
REAL_CARDS = (" 0 [C920           ]: USB-Audio - HD Pro Webcam C920\n                      HD Pro Webcam C920 at usb-0000:00:14.0-7, high speed\n"
              " 1 [PCH            ]: HDA-Intel - HDA Intel PCH\n")
open(os.path.join(ROOT, "etc", "nginx", "sites-available", "rhino-studio"), "w").write(open(os.path.join(REPO, "service", "rhino-studio.nginx")).read())
FAKE_GO2RTC = b"#!/bin/sh\necho go2rtc\n"
SHA = hashlib.sha256(FAKE_GO2RTC).hexdigest()
open(os.path.join(T, "go2rtc.download"), "wb").write(FAKE_GO2RTC)


def tool(name, body):
    p = os.path.join(BIN, name)
    open(p, "w").write("#!/bin/sh\n" + f'echo "{name} $*" >> "{LOG}"\n' + body)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)


tool("sudo", 'exec "$@"\n')
tool("systemctl", 'case "$1" in is-active) [ -f "$T/up" ] && echo active || echo inactive ;; restart) touch "$T/up" ;; disable) rm -f "$T/up" ;; esac\nexit 0\n')
tool("apt-get", f'[ -f "$T/apt_fails" ] && exit 100\nprintf \'#!/bin/sh\\necho " A..... libopus  libopus Opus"\\nseq 1 200000\\n\' > "{BIN}/ffmpeg"; chmod +x "{BIN}/ffmpeg"\n')
# curl: Moonraker's print state, the download, go2rtc's stream list
tool("curl", f'''for a in "$@"; do last="$a"; done
case "$last" in
  *print_stats*) echo '{{"result":{{"status":{{"print_stats":{{"state": "'"${{STATE:-standby}}"'"}}}}}}}}' ;;
  *api/streams) [ -f "$T/up" ] && [ ! -f "$T/api_dead" ] && echo '{{"mic":{{"producers":[]}}}}' || exit 7 ;;
  *) out=""; prev=""; for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done; cp "$T/${{DL:-go2rtc.download}}" "$out" ;;
esac
''')
# Only these real tools, so this computer's own ffmpeg, curl or systemctl can't answer for the stand-ins
SYS = os.path.join(T, "sys")
os.makedirs(SYS)
for name in ("bash", "sh", "grep", "sed", "tr", "cut", "cat", "mkdir", "install", "rm", "cp", "mktemp", "sha256sum",
             "uname", "id", "sleep", "seq", "dirname", "chmod", "touch", "head"):
    real = shutil.which(name)
    if real:
        os.symlink(real, os.path.join(SYS, name))
open(LOG, "w").close()
ENV0 = {"PATH": f"{BIN}:{SYS}", "HOME": HOME, "T": T, "RHINO_MIC_ROOT": ROOT, "RHINO_MIC_TEST_SHA": SHA,
        "RHINO_MIC_URL": "https://example.invalid/go2rtc_linux_amd64", "RHINO_MIC_WAIT": "2", "LC_ALL": "C"}
SCRIPT = os.path.join(CFG, "scripts", "rhino_mic.sh")
DIR = os.path.join(HOME, "rhino-mic")
UNIT = os.path.join(ROOT, "etc", "systemd", "system", "rhino-mic.service")


def run(*args, **env):
    r = subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env={**ENV0, **env}, timeout=60)
    return r.returncode, r.stdout + r.stderr


def calls():
    return open(LOG).read()


try:
    if subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip() != "x86_64":
        print("SKIP microphone test: this computer isn't x86-64")
        sys.exit(0)
    open(CARDS, "w").write(" 1 [PCH            ]: HDA-Intel - HDA Intel PCH\n")
    code, out = run("install")
    ok(code == 1 and "STOPPED: The camera's microphone (C920) isn't there." in out and "PCH" in out and not os.path.exists(DIR),
       "no C920 in the sound cards: stops, lists what is there, changes nothing")
    open(CARDS, "w").write(REAL_CARDS)

    code, out = run("install", STATE="printing")
    ok(code == 1 and "STOPPED: A job is running." in out and "apt-get" not in calls(), "a job running: stops before ffmpeg or any download")

    code, out = run("install", "--dry-run")
    ok(code == 0 and "Dry run finished: nothing changed." in out and "plughw:CARD=C920,DEV=0" in out
       and "would run: sudo apt-get install -y --no-install-recommends ffmpeg" in out and not os.path.exists(DIR)
       and not os.path.exists(UNIT) and "apt-get install" not in calls(), "dry run says every step and changes nothing")

    open(os.path.join(T, "apt_fails"), "w").close()
    code, out = run("install")
    ok(code == 1 and "STOPPED: ffmpeg didn't install." in out and not os.path.exists(DIR), "ffmpeg fails to install: stops, nothing else done")
    os.remove(os.path.join(T, "apt_fails"))

    open(os.path.join(T, "bad.download"), "wb").write(b"not the real one")
    code, out = run("install", DL="bad.download")
    ok(code == 1 and "isn't the pinned go2rtc" in out and not os.path.exists(os.path.join(DIR, "go2rtc")) and not os.path.exists(UNIT),
       "a download with another checksum isn't kept and nothing is installed")

    open(LOG, "w").close()
    code, out = run("install")
    conf = open(os.path.join(DIR, "go2rtc.yaml")).read() if os.path.exists(os.path.join(DIR, "go2rtc.yaml")) else ""
    unit = open(UNIT).read() if os.path.exists(UNIT) else ""
    ok(code == 0 and "Microphone installed." in out, "installs" + ("" if code == 0 else f": {out[-400:]}"))
    ok("-i plughw:CARD=C920,DEV=0" in conf and 'listen: "127.0.0.1:1984"' in conf and 'listen: "127.0.0.1:8554"' in conf
       and "ice_servers: []" in conf and "@" not in conf.split("streams:")[1].replace("{output}", ""),
       "go2rtc's settings: the C920 by name, API and RTSP on this host only, no outside STUN servers")
    user = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    ok(f"User={user}" in unit and f"ExecStart={DIR}/go2rtc -config {DIR}/go2rtc.yaml" in unit and "Nice=10" in unit and "@" not in unit.split("[Unit]")[1],
       "the service runs as this login, at low priority, from ~/rhino-mic")
    c = calls()
    ok("systemctl daemon-reload" in c and "systemctl enable rhino-mic" in c and "systemctl restart rhino-mic" in c, "service enabled and started")
    ok("Settings > Cameras > Sound" in out and "remove" in out, "says what to do in Studio and how to undo")

    open(LOG, "w").close()
    code, out = run("install")
    ok(code == 0 and "go2rtc 1.9.15 already in" in out and "example.invalid" not in calls(), "a second install keeps the checked go2rtc (no download)")

    code, out = run("status")
    ok(code == 0 and "rhino-mic running" in out and "lists the mic stream" in out and "C920 is there" in out, "status: the card, the service and go2rtc")

    open(os.path.join(T, "api_dead"), "w").close()
    code, out = run("install")
    ok(code == 1 and "doesn't answer on this host" in out and "remove" in out, "go2rtc not answering after the start: stops and says how to undo")
    os.remove(os.path.join(T, "api_dead"))

    code, out = run("remove")
    ok(code == 0 and not os.path.exists(UNIT) and not os.path.exists(DIR) and "systemctl disable --now rhino-mic" in calls()
       and "sudo apt-get remove ffmpeg" in out, "remove: service and go2rtc gone, ffmpeg left with how to remove it")
    code, out = run("remove")
    ok(code == 0 and "no rhino-mic service" in out, "removing twice is fine")

    os.remove(os.path.join(ROOT, "etc", "nginx", "sites-available", "rhino-studio"))
    code, out = run("install", "--dry-run")
    ok("Studio's site has no /mic route yet" in out, "an older Studio site without /mic is pointed out")

    # 1.9.21: the go2rtc inside the release zip (install.sh passes it), and the login when run as root
    open(CARDS, "w").write(REAL_CARDS)
    bundled = os.path.join(T, "zip-go2rtc"); open(bundled, "wb").write(FAKE_GO2RTC)
    open(os.path.join(ROOT, "etc", "nginx", "sites-available", "rhino-studio"), "w").write("location = /mic/webrtc {}\n")
    open(LOG, "w").close()
    code, out = run("install", RHINO_MIC_BIN=bundled, RHINO_MIC_USER="pi")
    ok(code == 0 and "go2rtc 1.9.15 from the release, checksum matches" in out and "example.invalid" not in calls(),
       "uses the go2rtc inside the release: nothing downloaded")
    ok("User=pi" in (open(UNIT).read() if os.path.exists(UNIT) else ""), "the service runs as the login it's given (the updater runs as root)")
    run("remove")
    open(bundled, "wb").write(b"damaged")
    code, out = run("install", RHINO_MIC_BIN=bundled)
    ok(code == 1 and "The go2rtc in the release isn't the pinned 1.9.15." in out and not os.path.exists(UNIT), "a damaged go2rtc in the zip stops it")

    code, out = run("nonsense")
    ok(code == 2 and "install --dry-run" in out, "an unknown action shows the usage")

    svc = open(os.path.join(REPO, "service", "rhino-mic.service")).read()
    ok("Restart=on-failure" in svc and "CPUQuota=" in svc and "MemoryMax=" in svc, "the service restarts on failure and is capped so it can't crowd Klipper")
finally:
    shutil.rmtree(T, ignore_errors=True)

print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
