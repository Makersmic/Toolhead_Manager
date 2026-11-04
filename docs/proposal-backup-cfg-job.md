# Proposal: BACKUP_CFG never holds the print

**Status: approved by Mike Nov 3 (script fix, 7-day wait). Built, not released. Not yet tried on a real print (B3).**

## The problem

Seen on the Pi on Nov 3: `BACKUP_CFG` during a print stopped the head on the part until the backup ended.

What runs today during a job:

1. `BACKUP_CFG` calls `RUN_SHELL_COMMAND CMD=backup_cfg`. Klipper's G-code queue waits until that command exits, up to
   its `timeout: 240.`
2. `scripts/rhino_backup_cfg.py` asks Moonraker for the job state. The state is `printing`.
3. It starts a background process for the archive, which waits for the job to end. That part is fine.
4. **It then runs the klipper-backup push itself, in the foreground, for up to 180 s.** This is the stall.

Two related faults:

- **Unknown state counts as idle.** If Moonraker doesn't answer in step 2, the state is `unknown`, so a mid-job call makes
  the whole archive and push in the foreground.
- **`END_PRINT` has the same hold** after any job over 2 hours. It's harmless to the part, but the job shows as printing until
  the push ends.

## Recommended fix: change the script, not the macro

The macro text and `END_PRINT` stay as they are. Only `scripts/rhino_backup_cfg.py` changes, with one lock added in
`rhino/backup.py` and `scripts/rhino_backup_watch.sh`.

What runs after the fix, whenever the job state isn't clearly idle:

1. `BACKUP_CFG` calls the script, and Klipper's queue waits as before.
2. The script asks Moonraker for the state. If it's printing, paused or unknown, it starts the background process.
3. The script prints "a job is running: the backup and GitHub push will run when it's finished", then exits.
4. Klipper's queue carries on.
5. When the job is over, the background process makes the archive, then pushes. A second `BACKUP_CFG` during the same job
   sees one already waiting and starts nothing.

An idle `BACKUP_CFG` works exactly as it does now, which includes the updater's call. The updater already refuses during a job.

**A push lock:** the watcher holds its changes during a job, then pushes when the job ends. The background process would
now push at about the same moment. Nothing stops two runs of klipper-backup at once in the same folder today, and this
change makes that more likely. So the watcher, the Portal and this script would all take one lock around the push. If
it's taken, they wait for it.

## What can go wrong

| Risk | How bad | Handling |
|---|---|---|
| A short hold remains: Python's start-up plus the Moonraker question | About 0.1 s expected on the 7050; up to about 3-6 s if Moonraker has hung (two calls, each with a 3 s limit) | Klipper's move buffer should cover the normal case. Not measured on a real print, so check B3 below |
| The host restarts before the job ends | That backup never happens | Already true of the archive; now true of the push too. The next backup picks up the changes |
| The job runs longer than 12 hours after the call | The background process gives up, and no backup is made | Already true of the archive. Limit raised to 7 days, and Studio's GitHub line says why if it gives up |
| A failed push after the job | The console no longer shows it, because the command has ended | Studio's GitHub line still shows the failure and the reason (never a false "pushed") |
| The push lock is left stuck | Later pushes could wait forever | The system frees it when the holder exits, and waiting has a time limit that reports a failed push |

## The other option: refuse during a job

The macro checks `printer.print_stats.state` and refuses without starting the shell command at all.

- **For:** no hold of any length, and a clear refusal, which is the project's usual preference.
- **Against:** it's a real macro change. `END_PRINT` runs while the state is still `printing`, so it needs its own path to the
  backup, and a manual request during a job is dropped, not kept.
- **Not needed yet:** I'd add it only if B3 shows that the short hold is visible on a print.

## Tests

- `dev/test_backup.py`: during a job, the script returns without running klipper-backup. The push happens once the job
  ends. Unknown state is treated as busy. A second call doesn't add a second waiter. Pushes never overlap.
- `dev/test_backup_watch.py`: the watcher takes the same lock.
- **Check on the machine, B3 (reworded):** during a print, run `BACKUP_CFG` several times. *Pass:* the console answers at once,
  the head doesn't pause, and one archive and one push arrive after the job. *Stop if:* the print stutters, or klippy.log
  shows "Timer too close".

## Until this ships

Don't run `BACKUP_CFG` during a job. That includes the load test (`docs/migrate-7050.md` §9).
