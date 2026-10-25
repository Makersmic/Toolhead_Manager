#!/usr/bin/env python3
"""BACKUP_CFG (Tool Manager 1.7): a local Rhino backup, then klipper-backup's GitHub push.

    python3 rhino_backup_cfg.py [MSG]

1. A complete archive in ~/rhino-backups (rhino/backup.py). During a job (END_PRINT after a long job runs
   this while the file is still printing) the archive is made in the background as soon as the job is over.
2. klipper-backup (~/klipper-backup/script.sh), as BACKUP_CFG always did, if it's installed. Its result is
   recorded in rhino_data/backup_status.json so Studio and the Portal show whether the push worked.
Prints "rhino:" lines for the Mainsail console. Exit 0 unless the archive was refused."""
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from rhino.backup import BackupService                  # noqa: E402
from rhino.errors import Fail                           # noqa: E402
from rhino.moonraker import BUSY_STATES, Moonraker     # noqa: E402
from rhino.paths import resolve                         # noqa: E402


def say(m):
    print("rhino: " + m, flush=True)


def main(argv):
    wait = argv[:1] == ["--wait"]
    if wait:
        argv = argv[1:]
    msg = argv[0] if argv else ""
    svc = BackupService(resolve(os.environ.get("RHINO_CONFIG_DIR") or os.path.join(HERE, "..")),
                        Moonraker(os.environ.get("RHINO_MOONRAKER", "http://127.0.0.1:7125")),
                        backup_dir=os.environ.get("RHINO_BACKUP_DIR") or None)
    if wait:                                   # the background half: wait for the job, then back up
        try:
            a = svc.wait_then_create(msg or "after job")
            say(f"backup {a['name']} made after the job")
        except Fail as e:
            say(f"backup refused: {e}")
            return 1
        return 0
    rc = 0
    if svc.mr.status().get("print_state") in BUSY_STATES:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--wait", msg or "after_long_job"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        say("a job is running: the Rhino backup will be made when it's finished")
    else:
        try:
            a = svc.create(msg or "BACKUP_CFG")
            say(f"backup {a['name']} made ({a['files']} files, {a['size'] // 1024} KB) in {svc.dir}")
        except Fail as e:
            say(str(e))
            rc = 1
    gh = svc.push_github(msg)
    say({"not_installed": "klipper-backup isn't installed: no GitHub copy",
         "no_env": "klipper-backup has no .env: no GitHub copy",
         "ok": "klipper-backup pushed to GitHub",
         "failed": "klipper-backup did NOT push to GitHub: " + " / ".join((gh.get("last") or {}).get("tail") or [])
         }.get(gh["state"], gh["state"]))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
