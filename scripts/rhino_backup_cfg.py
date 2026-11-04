#!/usr/bin/env python3
"""BACKUP_CFG (Tool Manager 1.7): a local Rhino backup, then klipper-backup's GitHub push.

    python3 rhino_backup_cfg.py [MSG]

1. A complete archive in ~/rhino-backups (rhino/backup.py).
2. klipper-backup (~/klipper-backup/script.sh), as BACKUP_CFG always did, if it's installed. Its result is
   recorded in rhino_data/backup_status.json so Studio and the Portal show whether the push worked.

Klipper's G-code queue waits until this script exits, so during a job it must do no real work: a push here stopped the
head on the part (seen Nov 3 2026, docs/proposal-backup-cfg-job.md). Unless the machine is clearly idle, both steps go
to a background process that waits for the job to end, and this one exits at once.

Prints "rhino:" lines for the Mainsail console. Always exits 0: it runs inside END_PRINT, and a refused backup
must never look like a failed job. The refusal is printed instead."""
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from rhino.backup import BackupService                  # noqa: E402
from rhino.errors import Fail                           # noqa: E402
from rhino.moonraker import Moonraker                   # noqa: E402
from rhino.paths import resolve                         # noqa: E402

WAIT_POLL = float(os.environ.get("RHINO_BACKUP_WAIT_POLL", 30))
WAIT_MAX = float(os.environ.get("RHINO_BACKUP_WAIT_MAX", 7 * 24 * 3600))
FOREGROUND_LOCK_WAIT = 30                               # the macro's own timeout is 240 s, and the push may take 180


def say(m):
    print("rhino: " + m, flush=True)


def after_job(svc, msg):
    """The background half: wait for the job, then back up and push. Its output goes nowhere, so a failure that matters
    is recorded where Studio shows it."""
    claim = svc.claim_after_job()
    if claim is None:                          # one is already waiting, and it will cover this request too
        return
    try:
        if not svc.wait_until_idle(WAIT_POLL, WAIT_MAX):
            svc.push_failed("The job outlasted the wait, so BACKUP_CFG made no backup. Back up again when it's finished.")
            return
        try:
            svc.create(msg or "after job")
        except Fail:
            pass                               # same as the foreground: a refused archive doesn't stop the push
        svc.push_github(msg)
    finally:
        claim.close()


def main(argv):
    wait = argv[:1] == ["--wait"]
    if wait:
        argv = argv[1:]
    msg = argv[0] if argv else ""
    svc = BackupService(resolve(os.environ.get("RHINO_CONFIG_DIR") or os.path.join(HERE, "..")),
                        Moonraker(os.environ.get("RHINO_MOONRAKER", "http://127.0.0.1:7125")),
                        backup_dir=os.environ.get("RHINO_BACKUP_DIR") or None)
    if wait:
        after_job(svc, msg)
        return 0
    if not svc.clearly_idle():
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--wait", msg or "after_long_job"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        say("a job is running: the backup and GitHub push will run when it's finished. Studio shows the result")
        return 0
    try:
        a = svc.create(msg or "BACKUP_CFG")
        say(f"backup {a['name']} made ({a['files']} files, {a['size'] // 1024} KB) in {svc.dir}")
    except Fail as e:
        say(str(e))
    gh = svc.push_github(msg, lock_wait=FOREGROUND_LOCK_WAIT)
    say({"not_installed": "klipper-backup isn't installed: no GitHub copy",
         "no_env": "klipper-backup has no .env: no GitHub copy",
         "ok": "klipper-backup pushed to GitHub",
         "failed": "klipper-backup did NOT push to GitHub: " + " / ".join((gh.get("last") or {}).get("tail") or [])
         }.get(gh["state"], gh["state"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
