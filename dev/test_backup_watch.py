#!/usr/bin/env python3
"""The backup watcher (scripts/rhino_backup_watch.sh), run for real with a pretend inotifywait, curl and klipper-backup."""
import fcntl
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "rhino_backup_watch.sh")
ROOT = tempfile.mkdtemp(prefix="rhino-watch-test-")
BIN = os.path.join(ROOT, "bin")
KB = os.path.join(ROOT, "klipper-backup")
CFG = os.path.join(ROOT, "printer_data", "config")
for d in (BIN, KB, CFG):
    os.makedirs(d)
open(os.path.join(CFG, "printer.cfg"), "w").close()
LOG = os.path.join(ROOT, "backups.log")
ARGS = os.path.join(ROOT, "inotify.args")
STATE = os.path.join(ROOT, "state")
FEED = os.path.join(ROOT, "feed.sh")
fails = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def tool(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


tool(os.path.join(BIN, "inotifywait"), f'printf "%s\\n" "$@" > "{ARGS}"\nbash "{FEED}"')
tool(os.path.join(BIN, "curl"), f'echo "{{\\"result\\":{{\\"status\\":{{\\"print_stats\\":{{\\"state\\": \\"$(cat "{STATE}")\\"}}}}}}}}"')
# Reads stdin the way a careless child would: if the watcher didn't protect it, this would swallow later events
tool(os.path.join(KB, "script.sh"), f'cat > /dev/null\necho "backup $*" >> "{LOG}"\necho pushed')
with open(os.path.join(KB, ".env"), "w") as f:
    f.write('backupPaths=( "printer_data/config/*" )\n')


def watch(feed, state="standby", quiet=1, maxwait=4, poll=1, wait=None, during=None):
    """Runs the watcher against a scripted feed of events, and returns the backups it made."""
    if os.path.exists(LOG):
        os.remove(LOG)
    with open(STATE, "w") as f:
        f.write(state)
    with open(FEED, "w") as f:
        f.write(feed)
    env = dict(os.environ, HOME=ROOT, PATH=BIN + ":" + os.environ["PATH"], RHINO_KB_DIR=KB, RHINO_WATCH_QUIET=str(quiet),
               RHINO_WATCH_MAX=str(maxwait), RHINO_WATCH_JOB_POLL=str(poll))
    p = subprocess.Popen(["bash", SCRIPT], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if during:
        during()
    try:
        out, _ = p.communicate(timeout=wait or 20)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
    lines = open(LOG).read().splitlines() if os.path.exists(LOG) else []
    return lines, out, p.returncode


def events(n, name="printer.cfg"):
    return "for i in $(seq 1 %d); do echo \"%s/ CLOSE_WRITE,CLOSE %s\"; done\n" % (n, CFG, name)


try:
    # The point of it: a burst is one backup
    lines, out, rc = watch(events(500) + "sleep 3\n")
    ok(len(lines) == 1, f"500 file events in a burst make one backup ({len(lines)})")
    ok(lines and "500 changes" in lines[0] and "printer.cfg" in lines[0], "its commit message says how many changed and names the latest")
    ok(lines and lines[0].startswith("backup --commit_message "), "klipper-backup gets the message as --commit_message, the flag it accepts")

    lines, out, rc = watch(events(3) + "sleep 2.5\n" + events(2, "macros.cfg") + "sleep 2.5\n")
    ok(len(lines) == 2 and "3 changes" in lines[0] and "2 changes" in lines[1], "two separate bursts are two backups, and later events aren't lost to the first backup")

    lines, out, rc = watch("sleep 2\n")
    ok(not lines, "no changes, no backup")

    # A steady stream can't put a backup off for ever
    lines, out, rc = watch("for i in $(seq 1 40); do echo \"%s/ CLOSE_WRITE,CLOSE a.cfg\"; sleep 0.25; done; sleep 2\n" % CFG, quiet=2, maxwait=3)
    ok(2 <= len(lines) <= 5, f"changes that never stop still get a backup at the longest wait, not one per event ({len(lines)})")

    # Jobs
    for state in ("printing", "paused"):
        lines, out, rc = watch(events(5) + "sleep 4\n", state=state)
        ok(not lines, f"nothing runs while a job is {state}")

    def finish_job():
        time.sleep(2.5)
        with open(STATE, "w") as f:
            f.write("complete")

    lines, out, rc = watch(events(5) + "sleep 6\n", state="printing", during=finish_job)
    ok(len(lines) == 1 and "5 changes" in lines[0], "what changed during a job is backed up once when it's over")

    # One push at a time, with the lock rhino/backup.py takes
    held = open(os.path.join(ROOT, ".rhino-push.lock"), "a")
    fcntl.flock(held, fcntl.LOCK_EX)
    seen_while_held = []

    def release_later():
        time.sleep(3)
        seen_while_held.append(os.path.exists(LOG))
        held.close()

    lines, out, rc = watch(events(5) + "sleep 5\n", during=release_later)
    ok(seen_while_held == [False] and len(lines) == 1, "the watcher waits while another push runs, then pushes")

    held = open(os.path.join(ROOT, ".rhino-push.lock"), "a")
    fcntl.flock(held, fcntl.LOCK_EX)
    os.environ["RHINO_PUSH_LOCK_WAIT"] = "1"
    lines, out, rc = watch(events(5) + "sleep 3\n")
    del os.environ["RHINO_PUSH_LOCK_WAIT"]
    held.close()
    ok(not lines and "another push ran too long" in out, "if the other push never ends, it says so instead of waiting for ever")

    # What it watches
    lines, out, rc = watch("true\n")
    args = open(ARGS).read().splitlines()
    ok(args[-1] == CFG and args.count(CFG) == 1, "it watches the folder from klipper-backup's .env, once")
    ok(args[0] == "-mrP" and "close_write" in args and "--exclude" in args, "it watches for saved, moved and deleted files")
    pattern = args[args.index("--exclude") + 1]
    for name in (".client_macros.cfg.BEunKm", ".toolchanger.cfg.DZL0ep", ".Rhino PLA @BlockOne 0.4.json.sMpONz", "printer-20261102_030000.cfg", "a.cfg.bak", "a.swp", "meters.json.tmp", "myrhino/maintenance/meters.json"):
        ok(re.search(pattern, CFG + "/" + name), f"ignored: {name}")
    for name in ("printer.cfg", "toolchanger.cfg", "myrhino/custom_tools.json", "myrhino/maintenance/tasks.json", "myrhino/maintenance/history.json", "meters.json", ".hidden.cfg"):
        ok(not re.search(pattern, CFG + "/" + name), f"still watched: {name}")

    # When things go wrong
    lines, out, rc = watch(events(4))
    ok(rc == 1 and len(lines) == 1 and "4 changes" in lines[0], "if inotifywait stops, what's waiting is saved, and it exits so systemd restarts it")
    lines, out, rc = watch(events(4), state="printing")
    ok(rc == 1 and not lines, "if inotifywait stops during a job, it doesn't back up then")
    os.rename(os.path.join(KB, ".env"), os.path.join(KB, ".env.off"))
    lines, out, rc = watch("true\n")
    ok(rc == 1 and ".env is missing" in out and not lines, "with no klipper-backup .env it stops and says why")
    os.rename(os.path.join(KB, ".env.off"), os.path.join(KB, ".env"))
finally:
    shutil.rmtree(ROOT, ignore_errors=True)

print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
raise SystemExit(1 if fails else 0)
