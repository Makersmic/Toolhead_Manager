# Phase 2: Back up now (design)

Draft, Oct 25 2026, for Mike to review. No code yet.

- **Spec:** INV-B3, B4 and B5 in docs/invariants.md.
- **What it covers:** the § Backup inventory table in docs/phase0-spine.md, and only that table.
- **Gates before code starts:**
  1. klipper-backup's `backupPaths`
  2. whether `variables.save` is git-ignored
  3. whether PrusaSlicer has a saved profile on the Pi

## What it is for

1. Get the Rhino onto the 7050 without losing anything. This is the first real use, and it's why Phase 2 comes before profiles.
2. After months away, have a backup you know is complete and know how old it is.

## The archive

`~/rhino-backups/rhino-<host>-<YYYYMMDD-HHMM>.zip`. It lives outside the config folder, so klipper-backup never pushes archives to GitHub.

| Inside | From |
|---|---|
| `config/` | all of `printer_data/config` except `.git/` |
| `moonraker/moonraker-sql.db` | Moonraker's whole database, made by Moonraker itself (`POST /server/database/backup`), then copied in. This covers job history and totals, the `rhino_studio` namespace, `mesh_seen` and Mainsail's settings |
| `moonraker/rhino_studio.json` | the Studio namespace as readable JSON (`GET /server/database/item?namespace=rhino_studio`, no key gives the whole namespace), used for partial restore |
| `images/` | `rhino_data/images` |
| `manifest.json` | TM and Studio versions, host, time, and for each file its path, size and sha256. Also lists the expected items that were found. |

- **Left out on purpose:** G-code files (too big; they can be re-sliced), the PrusaSlicer engine and cache, browser state, and klipper-backup's `.env` (it holds a GitHub token).
- **Complete or refused (INV-B4).** The Portal builds the list of what it expects from the inventory table: printer.cfg, variables.cfg, every `myrhino/*.json`, the Moonraker exports and the images folder (even if empty). If any expected item can't be read, the whole archive is deleted and the error names the missing item. No partial zip is ever kept.
- Old archives are pruned on save. The last 10 are kept (prune on save, same as B2).
- Size check: the zip is refused if the disk has less than 3 × its expected size free.

## When it runs

- **The "Back up now" button** in Studio Settings › Host, and in the Portal.
- **After a job longer than 2 h** (END_PRINT already calls BACKUP_CFG). BACKUP_CFG gains one step: ask the Portal for an archive first, then run klipper-backup as before.
- **Before every update** (the updater already calls BACKUP_CFG; nothing new needed).
- **During a print:** allowed. It only reads, and it runs at `nice 19`. On a Pi 3B the config zip is small. (verify on the machine: B-test 4)

## klipper-backup health

The Portal reports one of these, and the archive records it:
- not installed
- installed but `.env` missing
- last push OK at a given time
- last push failed

It reads the push result from the script's exit code and saves it in `rhino_data/backup_status.json`. "Backed up" in Studio means the local archive succeeded. The GitHub push is shown separately and is never shown as done when it wasn't (INV-B8).

## Restore

1. **Partial restore, first.** Pick an archive, then pick one item: maintenance, tool registry and lists, Studio settings, or images. That item is shown before and after, and you confirm it. Any job state is fine except "printing"; the restore waits for idle. Klipper-facing items (registry → `custom_tools.cfg`) end with the normal "restart Klipper" banner.
2. **Full restore.** Only when idle and Klipper is not printing. It needs a typed confirm (the host name), and it first makes a backup of the current state. Steps:
   1. Stop the Portal's writers.
   2. Unpack `config/` over the config folder; files not in the archive are kept and listed.
   3. Re-post the Moonraker namespace.
   4. Restore Moonraker's database with `POST /server/database/restore`. This replaces the whole database, and Moonraker refuses it while printing. On the 7050 nothing is lost, because its database starts empty.
   5. Restart Klipper.
   
   **This is the 7050 path:** install TM 1.7 on the 7050, open the Portal, choose Restore from file, upload the zip.
3. **Never restored:** a different machine's `printer.cfg` MCU serial paths aren't edited. If the `[mcu] serial` path in the archive isn't present on this host, the restore stops before Klipper restarts, and the Portal shows the path to fix.

## Routes (Portal) and allowlist (Studio, INV-A7)

| Route | Kind | Notes |
|---|---|---|
| `POST /api/backup` | write `backup.now` | returns manifest or the refusal |
| `GET /api/backup` | read | list: name, time, size, complete, GitHub push status |
| `GET /api/backup/<name>` | read | download |
| `POST /api/backup/upload` | write `backup.upload` | for the 7050; checked against the manifest before it's listed |
| `POST /api/restore` | write `backup.restore` | `{archive, item | "all", confirm}`; idle-only |

## Studio

The "Back up now" card in Settings › Host shows:
- the last backup's time and whether it was complete
- the GitHub push status
- how many archives are kept
- Download

The welcome-back summary (Phase 3) reads the same list.

## Tests (named for the invariants)

- **INV-B4:**
  - Remove a myrhino JSON → backup refused, nothing left on disk.
  - Corrupt a file after zipping → manifest check fails on upload.
- **INV-B5:** the expected list is built from the inventory table. A test fails if the table and the code disagree.
- **INV-B8:** klipper-backup is missing → Studio never says "pushed".
- **Restore:**
  - Partial restore puts back exactly one item.
  - Full restore refuses while printing, and refuses on a wrong typed name.
  - A missing serial path stops before the Klipper restart.
- **Simulator:** archive → wipe → restore gives byte-identical `config/` and the same history count.
- **On the machine:**
  - B1: back up now, check the manifest
  - B2: partial restore of maintenance
  - B3: full restore on the 7050
  - B4: back up during a print, check for no "Timer too close" in klippy.log

## Open questions for Mike

1. ~~Keep 10~~ (Mike: 10).
2. ~~History merge~~ (see below).
3. Should the archive also copy to a USB stick or network share if one is set? (Lean: later.)

## Checked against Moonraker's source (Oct 25, `Arksine/moonraker@b559b9a`)

- `/server/database/backup`, `/server/database/restore` and `/server/database/list` exist. Restore refuses while Klipper is printing, and it replaces the whole database.
- `/server/database/item` with no `key` returns the whole namespace.
- Job history lives in its own SQLite table (`job_history`). **There is no API to add or import jobs.** `/server/history/list` defaults to `limit=50`.
- **So "merge history" can't go through Moonraker.** It would mean the Portal writing rows straight into `moonraker-sql.db` with Moonraker stopped. For the 7050 move a merge isn't needed, because the target is empty and a full restore keeps every job. Merge is parked until there's a case for it (Mike chose merge on Oct 25 before this was known; that's his call).
