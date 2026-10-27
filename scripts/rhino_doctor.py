#!/usr/bin/env python3
"""Health check: is this host ready to run the Rhino, and will it stay ready when left alone?

    python3 rhino_doctor.py                  print the checks, save a report in your home folder
    python3 rhino_doctor.py --compare A B    what differs between two saved reports (the Pi's and the 7050's)

Read-only: it changes nothing, needs no sudo, and every check that can't run says so instead of failing the
rest. Run it on the Pi before the move and on the 7050 after (docs/migrate-7050.md); menu option 7 runs it.

Each line is PASS, WARN (works, but worth a look), FAIL (fix before trusting the machine) or INFO.
The "facts" block at the end is what --compare lines up: names, versions, boards, cameras.
"""
import glob
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
CFG = os.environ.get("RHINO_CONFIG_DIR") or os.path.join(HOME, "printer_data", "config")
MOONRAKER = os.environ.get("RHINO_MOONRAKER", "http://127.0.0.1:7125")
PORTAL = os.environ.get("RHINO_PORTAL", "http://127.0.0.1:5000")
SYS = os.environ.get("RHINO_SYS_ROOT", "")           # tests point /sys and /dev lookups at a fake tree
B, G, Y, R, N = ("\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m") if sys.stdout.isatty() else ("",) * 5
COLOUR = {"PASS": G, "WARN": Y, "FAIL": R, "INFO": ""}

results, facts = [], {}


def say(level, what, detail=""):
    results.append({"level": level, "what": what, "detail": detail})
    print(f"  {COLOUR[level]}{level:4}{N}  {what}" + (f"  - {detail}" if detail else ""))


def fact(key, value):
    facts[key] = value


def run(*cmd, timeout=8):
    """-> (exit code, output) or (None, why) when the command isn't there."""
    try:
        p = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        out = (p.stdout + p.stderr).strip()
        if "System has not been booted with systemd" in out or "Failed to connect to bus" in out:
            return None, "systemd isn't running here"
        return p.returncode, out
    except FileNotFoundError:
        return None, f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return None, f"{cmd[0]} took too long"


def get_json(url, timeout=4):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def sysfs(path):
    return SYS + path


def section(title):
    print(f"\n{B}{title}{N}")


def config_lines():
    """(file, section, key, value) for every key in every .cfg under the config folder."""
    for path in sorted(glob.glob(os.path.join(CFG, "**", "*.cfg"), recursive=True)):
        sec = ""
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for line in text.splitlines():
            s = line.split("#", 1)[0].strip()
            m = re.match(r"^\[([^\]]+)\]", s)
            if m:
                sec = m.group(1).strip().lower()
                continue
            m = re.match(r"^([A-Za-z_]+)\s*[:=]\s*(.*)$", s)
            if m and sec:
                yield os.path.relpath(path, CFG), sec, m.group(1).lower(), m.group(2).strip()


# ---------------------------------------------------------------------------------------------------- checks
def check_host():
    section("This computer")
    host = socket.gethostname()
    fact("host name", host)
    fact("architecture", platform.machine())
    fact("python", platform.python_version())
    os_name = ""
    try:
        for line in open("/etc/os-release"):
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    fact("system", os_name or platform.platform())
    say("INFO", f"{host}: {os_name or platform.platform()}, {platform.machine()}, Python {platform.python_version()}")
    user = os.environ.get("USER") or os.path.basename(HOME)
    fact("login", user)
    if os.path.basename(HOME.rstrip("/")) == "pi":
        say("PASS", "Login is pi: every /home/pi path in the config and backups matches")
    else:
        say("WARN", f"Login is {user}, not pi", "the installer rewrites /home/pi paths, but a backup from a pi machine "
            "restored here keeps them; see docs/migrate-7050.md section 3")

    code, out = run("systemctl", "is-active", "NetworkManager")
    if code is None:
        say("INFO", "Network manager: couldn't ask systemd", out)
    elif out.strip() == "active":
        fact("network", "NetworkManager")
        say("PASS", "NetworkManager runs the network (Studio's Network page can change it)")
    else:
        code2, out2 = run("systemctl", "is-active", "dhcpcd")
        who = "dhcpcd" if out2.strip() == "active" else "something other than NetworkManager"
        fact("network", who)
        say("INFO", f"The network is run by {who}", "fine on a Pi; the 7050 plan uses NetworkManager")

    code, out = run("timedatectl", "show", "-p", "NTPSynchronized", "--value")
    if code is None:
        say("INFO", "Clock sync: couldn't ask", out)
    elif out.strip() == "yes":
        say("PASS", "The clock is synced (calendar care tasks and backup dates rely on it)")
    else:
        say("WARN", "The clock isn't synced", "care tasks by date and backup names use it; check the network or timedatectl")

    try:
        st = shutil.disk_usage(HOME)
        free_gb = st.free / 1e9
        fact("disk free (GB)", round(free_gb, 1))
        (say("PASS", f"{free_gb:.1f} GB free in the home folder") if free_gb >= 2
         else say("WARN" if free_gb >= 0.5 else "FAIL", f"Only {free_gb:.1f} GB free", "backups, logs and G-code files need room"))
    except OSError as e:
        say("INFO", "Disk space: couldn't read", str(e))


def check_left_alone():
    """Things that matter on a desktop PC left running for months (they don't apply to a Pi)."""
    section("Left alone for months")
    sleepers = []
    for target in ("sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target"):
        code, out = run("systemctl", "is-enabled", target)
        if code is None:
            say("INFO", "Sleep: couldn't ask systemd", out)
            return
        if out.strip() != "masked":
            sleepers.append(target)
    if not sleepers:
        say("PASS", "Sleep and suspend are switched off (masked)")
    elif platform.machine() in ("x86_64", "amd64"):
        say("WARN", "This PC can still go to sleep", "a sleeping host stops Klipper mid-job. Switch it off with: "
            "sudo systemctl mask " + " ".join(sleepers))
    else:
        say("INFO", "Sleep isn't masked", "a Pi doesn't suspend on its own")

    auto = None
    try:
        auto = int(open(sysfs("/sys/module/usbcore/parameters/autosuspend")).read().strip())
    except (OSError, ValueError):
        pass
    boards = board_usb_devices()
    on_auto = [d for d, ctl in boards if ctl == "auto"]
    if auto is None:
        say("INFO", "USB power saving: couldn't read")
    elif auto < 0 or not on_auto:
        say("PASS", "USB power saving won't switch the board off" + (" (autosuspend off)" if auto < 0 else ""))
    else:
        say("INFO", "USB power saving is on for the board's port (the Linux default)", "Klipper keeps the port busy, so "
            "it rarely matters; if the board ever disconnects, usbcore.autosuspend=-1 is the first fix (docs/migrate-7050.md 9.4)")


def board_usb_devices():
    """(usb device folder, power/control) for each /dev/serial/by-id link, where /sys tells us."""
    out = []
    for link in glob.glob(sysfs("/dev/serial/by-id/*")):
        try:
            tty = os.path.basename(os.path.realpath(link))
            dev = os.path.realpath(sysfs(f"/sys/class/tty/{tty}/device"))
            for _ in range(4):                       # walk up from the interface to the USB device
                ctl = os.path.join(dev, "power", "control")
                if os.path.isfile(ctl):
                    out.append((dev, open(ctl).read().strip()))
                    break
                dev = os.path.dirname(dev)
        except OSError:
            continue
    return out


def check_board_and_camera():
    section("Board and camera")
    serials = [(f, sec, v) for f, sec, k, v in config_lines() if sec.startswith("mcu") and k == "serial"]
    canbus = [(f, sec, v) for f, sec, k, v in config_lines() if sec.startswith("mcu") and k == "canbus_uuid"]
    fact("boards", sorted([f"[{sec}] {os.path.basename(v)} ({'connected' if os.path.exists(sysfs(v)) else 'NOT connected'})"
                           for _, sec, v in serials] + [f"[{sec}] CAN {v}" for _, sec, v in canbus]))
    if not serials and not canbus:
        say("FAIL", "No [mcu] serial: found in the config", f"looked in {CFG}")
    for f, sec, dev in serials:
        if os.path.exists(sysfs(dev)):
            say("PASS", f"[{sec}] is connected", dev)
        else:
            say("FAIL", f"[{sec}] isn't connected", f"{dev} (from {f}) isn't here. Plug the board in; "
                "ls /dev/serial/by-id/ shows what is")
    for f, sec, uuid in canbus:
        say("INFO", f"[{sec}] is on CAN ({uuid})", "Klipper reports whether it answers")
    cams = sorted(os.path.basename(p) for p in glob.glob(sysfs("/dev/video*")))
    fact("cameras", cams)
    (say("PASS", f"Camera device: {', '.join(cams)}") if cams
     else say("WARN", "No camera device (/dev/video*)", "Studio's Dashboard and Control show the camera"))


def check_services():
    section("Services")
    for svc, need in (("klipper", "FAIL"), ("moonraker", "FAIL"), ("rhino-portal", "FAIL"), ("nginx", "WARN"),
                      ("crowsnest", "INFO")):
        code, out = run("systemctl", "is-active", svc)
        if code is None:
            say("INFO", f"{svc}: couldn't ask systemd", out)
        elif out.strip() == "active":
            say("PASS", f"{svc} is running")
        else:
            say(need, f"{svc} is {out.strip() or 'not running'}")
    try:
        info = get_json(MOONRAKER + "/server/info")["result"]
        fact("moonraker", info.get("moonraker_version", "?"))
        k = info.get("klippy_state")
        (say("PASS", "Moonraker answers; Klipper is ready") if k == "ready"
         else say("WARN", f"Moonraker answers; Klipper is {k}", "a restart or the console says why"))
        try:
            pi = get_json(MOONRAKER + "/printer/info")["result"]
            fact("klipper", pi.get("software_version", "?"))
        except Exception:
            pass
    except Exception as e:
        say("FAIL", "Moonraker doesn't answer", f"{MOONRAKER}: {e}")
    try:
        get_json(PORTAL + "/api/state")
        say("PASS", "The Portal answers")
    except Exception as e:
        say("FAIL", "The Portal doesn't answer", f"{PORTAL}: {e}")


def check_rhino():
    section("Rhino files")
    ver = ""
    try:
        ver = open(os.path.join(CFG, "VERSION")).read().strip()
    except OSError:
        pass
    inst = ""
    try:
        inst = open(os.path.join(HOME, "rhino-manager", "installed-version")).read().strip()
    except OSError:
        pass
    fact("tool manager", ver or "?")
    if ver and inst and ver != inst:
        say("WARN", f"Config says Tool Manager {ver}, the menu says {inst}", "install from the menu again to line them up")
    elif ver:
        say("PASS", f"Tool Manager {ver}")
    else:
        say("FAIL", "No VERSION in the config folder", "Tool Manager isn't installed here")
    printer_cfg = os.path.join(CFG, "printer.cfg")
    text = open(printer_cfg, errors="replace").read() if os.path.isfile(printer_cfg) else ""
    for rel in ("myrhino/custom_tools.cfg", "myrhino/job_hooks.cfg"):
        here = os.path.isfile(os.path.join(CFG, rel))
        inc = f"[include {rel}]" in text
        if here and inc:
            say("PASS", f"{rel} is there and included")
        else:
            say("FAIL", f"{rel} is {'missing' if not here else 'not included in printer.cfg'}",
                "the job and swap macros call what it defines; restarting the Portal writes it again")
    mainsail = os.path.join(CFG, "mainsail.cfg")
    if os.path.islink(mainsail) and not os.path.exists(mainsail):
        say("FAIL", "mainsail.cfg points at a file that isn't there", os.readlink(mainsail))
    elif os.path.exists(mainsail):
        say("PASS", "mainsail.cfg is there" + (" (Mainsail's link)" if os.path.islink(mainsail) else ""))
    else:
        say("FAIL", "mainsail.cfg is missing", "printer.cfg includes it; install Mainsail's config (KIAUH)")


def check_backups():
    section("Backups")
    arch = sorted(glob.glob(os.path.join(HOME, "rhino-backups", "rhino*.zip")), key=os.path.getmtime)
    if not arch:
        say("WARN", "No Rhino backup on this machine yet", "Studio > Settings > Host > Backups > Back up now")
    else:
        age = (time.time() - os.path.getmtime(arch[-1])) / 86400
        fact("newest backup", os.path.basename(arch[-1]))
        (say("PASS", f"Newest backup is {age:.0f} days old ({len(arch)} kept)") if age <= 14
         else say("WARN", f"Newest backup is {age:.0f} days old", "Back up now, then copy the zip off this machine"))
    kb = os.path.join(HOME, "klipper-backup")
    if not os.path.isdir(kb):
        say("WARN", "klipper-backup isn't installed", "no copy on GitHub; docs/migrate-7050.md section 7.5")
    elif not os.path.isfile(os.path.join(kb, ".env")):
        say("WARN", "klipper-backup has no .env", "it can't push until its repo and token are set")
    else:
        say("PASS", "klipper-backup is installed and set up")


def main():
    print(f"{B}Rhino health check{N}  {time.strftime('%Y-%m-%d %H:%M')}  (changes nothing)")
    for chk in (check_host, check_left_alone, check_board_and_camera, check_services, check_rhino, check_backups):
        try:
            chk()
        except Exception as e:                      # one check failing to run never hides the others
            say("INFO", f"{chk.__name__} couldn't run", repr(e))
    counts = {k: sum(1 for r in results if r["level"] == k) for k in ("PASS", "WARN", "FAIL")}
    print(f"\n{B}Summary{N}: {counts['PASS']} pass, {counts['WARN']} to look at, {counts['FAIL']} to fix")
    print(f"\n{B}Facts{N} (what --compare lines up)")
    for k, v in facts.items():
        print(f"  {k:16} {', '.join(v) if isinstance(v, list) else v}")
    name = f"rhino-health-{facts.get('host name', 'host')}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path = os.path.join(HOME, name)
    try:
        with open(path, "w") as f:
            json.dump({"made": time.strftime("%Y-%m-%d %H:%M:%S"), "facts": facts, "results": results}, f, indent=1)
        print(f"\nSaved {path}")
    except OSError as e:
        print(f"\n(couldn't save the report: {e})")
    return 1 if counts["FAIL"] else 0


def compare(a, b):
    ra, rb = json.load(open(a)), json.load(open(b))
    print(f"{B}{os.path.basename(a)}{N}  vs  {B}{os.path.basename(b)}{N}\n")
    keys = list(dict.fromkeys(list(ra["facts"]) + list(rb["facts"])))
    for k in keys:
        va, vb = ra["facts"].get(k, "-"), rb["facts"].get(k, "-")
        mark = " " if va == vb else "*"
        fmt = lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        print(f" {mark} {k:16} {fmt(va):34} {fmt(vb)}")
    print("\n * = differs. Expected after a move: host name, architecture, system, maybe network and versions.")
    print("   Not expected: boards (the same Octopus has the same serial name), Tool Manager version (until the load test).")
    worse = [r for r in rb["results"] if r["level"] == "FAIL"]
    if worse:
        print(f"\n{R}To fix on the second machine:{N}")
        for r in worse:
            print(f"  FAIL  {r['what']}" + (f"  - {r['detail']}" if r["detail"] else ""))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    sys.exit(main())
