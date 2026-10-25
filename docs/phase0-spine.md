# Phase 0: the durable state of the Rhino

Draft, Oct 23 2026. Design only, no code. Found by reading the repos at TM `e7033ab` and Studio `6158f74`. **Mike: correct anything marked (verify).**

## Decisions this rests on

- **Thesis:** durability over parity. Rhino Studio is the durable interface for the Rhino. It is not a general Mainsail replacement. Filter for every feature: *does this help the machine survive being ignored?*
- **Order (changed from the review):** finish in-flight → backup → migrate to 7050 → slice profiles → welcome back → invariants finalized. Backup moves ahead of profiles because the 7050 migration is imminent and moving hosts without a complete backup is the biggest real risk.
- **No cross-engine translator.** A profile stores one engine's native settings plus a small shared header. Swapping engines means picking that engine's profile, not translating one.
- **"Away"** = time since the later of (last job end, last Studio visit). The Portal records visits. No manual toggle.

## Answers to the five questions

**a. What BACKUP_CFG grabs.** `BACKUP_CFG` runs `/home/pi/klipper-backup/script.sh` (third-party klipper-backup), which commits to GitHub whatever its `.env` `backupPaths` lists. On Mike's Pi it is `printer_data/config/*` (checked Oct 25). `END_PRINT` runs it after jobs > 2 h; the updater runs it best-effort. `install.sh` separately copies the config folder to `~/rhino-backup-<stamp>` on every install.

**b. Kiri:Moto settings.** Not on the Pi. Per-file Prepare jobs (process, device, material, tool) live in **browser localStorage** `rs.prepare.jobs`. PrusaPanel UI state is also in localStorage. Clearing the browser or switching from PC to phone loses them. Defaults come from `src/slicer/profiles.ts` (code) and materials from `variables.cfg` (backed up).

**c. PrusaSlicer profiles.** There are none on the host. Each job writes `rhino.ini` into a temp job folder under `~/printer_data/rhino_data/prusaslicer/jobs/` and deletes it afterwards. The only lasting files there are engine-install state (`previous.json`, `auto.json`, `last_used`, a G-code cache). `rhino_data` sits **outside** the config folder, so it is not backed up.

**d. Portal data model.** Plain JSON files in `config/myrhino/`, each with:
- a top-level `"version"` (schema version, not history)
- validation on save
- atomic write (`.tmp` then `os.replace`)

The files:

| File | Holds |
|---|---|
| `custom_tools.json` | Tool registry; also generates `custom_tools.cfg` |
| `portal_lists.json` | Kinds, material names, nozzles, hardware categories |
| `umbilical.json` | Umbilical |
| `maintenance/tasks.json`, `history.json`, `meters.json` | Maintenance |

Material *values* (temps, power, feed) live in `variables.cfg`. There is **no export/import route** and **no version history**; the only history is klipper-backup's git commits.

**e. Away.** Decided above.

## Backup inventory

| Data | Where | Backed up today? | Should be |
|---|---|---|---|
| printer.cfg, macros, myrhino/*.cfg | config/ | ✅ klipper-backup (if set up) | ✅ |
| Materials table | config/variables.cfg | ✅ | ✅ |
| Tool registry, lists, umbilical | config/myrhino/*.json | ✅ | ✅ |
| Maintenance tasks/history/meters | config/myrhino/maintenance/ | ✅ | ✅ |
| Saved bed meshes | printer.cfg autosave block | ✅ | ✅ |
| Mesh records, tool state | config/variables.save | ✅ (verify it isn't in klipper-backup's .gitignore) | ✅ |
| moonraker.conf | config/ | ✅ | ✅ |
| **Job history** | Moonraker DB (`printer_data/database`) | ❌ | ✅ export to JSON |
| **Studio settings, `mesh_seen`** | Moonraker DB `rhino_studio` namespace | ❌ | ✅ export to JSON |
| **Slice settings per file** | browser localStorage | ❌ | ✅ via Phase 1 (move to Portal) |
| Toolhead photos | rhino_data/images | ❌ | ✅ (small) |
| PrusaSlicer engine state, G-code cache | rhino_data/prusaslicer | ❌ | ❌ re-derivable |
| G-code files | printer_data/gcodes | ❌ | optional (could be large) |
| klipper-backup itself + its .env | ~/klipper-backup | ❌ | document only (holds a GitHub token, never put it in an archive) |

Two more gaps:
- **Nothing checks that klipper-backup is installed and working.** BACKUP_CFG can fail silently on a machine where it was never set up.
- **"Backed up" today means "pushed to GitHub," and restore is manual.**

## Object model sketch

```
Machine durable state
├── Klipper config            config/*.cfg, variables.cfg, variables.save   (exists)
├── Portal objects            config/myrhino/*.json                         (exists)
│   ├── tools (registry)   ├── lists   ├── umbilical   ├── maintenance
│   └── slice_profiles     NEW (Phase 1)
├── Moonraker data            job history, rhino_studio namespace           (export into backup, Phase 2)
├── Media                     rhino_data/images                             (into backup, Phase 2)
└── Derived / disposable      Prusa engine, G-code cache, browser UI state  (never backed up)
```

Rule: anything a person would be upset to lose lives in `config/myrhino/` or is exported there at backup time. The browser holds nothing durable.

## Decision: slice profiles

**A new Portal file, `config/myrhino/slice_profiles.json`.** It is not a new kind of existing object. It follows the registry/lists pattern: schema version, validate on save, atomic write. Because it lives inside the config folder, today's backup picks it up for free.

Why not fold profiles into the materials table: materials are Klipper-facing (macros read `variables.cfg`). Profiles are slicer-facing and engine-specific, and putting them into Klipper's variables would bloat what every macro loads.

## Phase 1 sketch: slice profiles (design doc to follow before code)

**Profile fields**

```
{id, name, engine: "kiri"|"prusa", process: fdm|laser|cnc|knife,
 toolhead?, material?, header: {layer, nozzleTemp, bedTemp, ...},
 settings: {<engine-native>}, notes, created, updated, rev}
```

`rev` increments on every save. The Portal keeps the last 5 revisions per profile so a bad edit can be undone.

**Portal routes**
- list / get / save / delete
- export one or all as a file
- import with a duplicate-name check

**Studio**
- Prepare picks a profile.
- Edits are "Save to profile" or "Save as new".
- Profiles show a "Saved on the Rhino" mark.
- Per-file jobs reference a profile id plus overrides.
- On first run, existing localStorage jobs are offered for import once.

**Open questions**
- Do per-file overrides live on the Pi (keyed by file name) or stay in the browser? Lean: on the Pi, in `rhino_data`, and re-derivable.
- Is PrusaSlicer first-class? Decide after the 7050 load test. Until then, Prusa profiles work the same way with no special path.

## Later phases (scoped, not started)

- **Phase 2, backup button.**
  - Portal `BACKUP_NOW`: an archive of config + Moonraker exports + images, written to `~/rhino-backups/`.
  - Then klipper-backup pushes if it is present.
  - The archive is complete or refused.
  - Restore: partial (profiles, maintenance) first; full restore is idle-only and confirmed (first use is the 7050 migration).
  - The Studio button shows when the last backup ran and whether the GitHub push worked.
- **Phase 3, welcome back.** A dashboard card when away > N days:
  - jobs since
  - maintenance logged / overdue
  - mounted tool
  - last backup
  - newest mesh age
  - next steps
- **Phase 4, invariants.** `docs/invariants.md`, INV-n, cited from code and tests, with a check script. Draft the existing safety rules now (cheap); finalize after Phase 3.

## Parked (decided out, with reasons)

| Item | Reason |
|---|---|
| Timelapse | Nice for videos; does nothing for a machine left alone. Mainsail/crowsnest can still do it alongside. |
| Spoolman | One user, few spools; materials table covers it. Adds a service to keep alive. |
| Job queue | One machine, tool swaps between jobs need a person anyway. |
| 3D mesh view | It's the main complaint about Mainsail's mesh page; top-down map is clearer. |
| Mesh point editor | No safe Klipper API. |
| Input shaper graphs | Run once at build; console output is enough. |
| Exhaustive UI tweak list | Fix tweaks when a page is touched for another reason, not as a backlog. |
| Moonraker [power] devices | Only if the 7050 setup adds a switched outlet. |
| Exclude object | Keep as a maybe: saves a long print, but needs slicer labels. Revisit after profiles. |
