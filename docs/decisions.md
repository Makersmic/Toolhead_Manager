# Decisions

Append-only. Each entry is dated and gives its reason. An entry is never edited; a later entry can reverse an earlier one, and says so. Invariants (docs/invariants.md) cite these by date.

- **2026-10-23: Durability over parity.** Rhino Studio is the durable interface for the Rhino, not a general Mainsail replacement. Every feature is tested against one question: does it help the machine survive being left alone and be resumed safely? *Reason:* it's one owner's multi-tool machine, and it sits idle for long stretches.
- **2026-10-23: Parked:** timelapse, Spoolman, job queue, input-shaper graphs, the exhaustive UI tweak list. The full list and the reasons are in docs/parked.md. *Reason:* none of them help the machine survive being ignored.
- **2026-10-23: Order of work:** finish what's in flight (1.6.1) → Phase 2 backup → 7050 migration → Phase 1 slice profiles → Phase 3 welcome back → Phase 4 invariants finalized. One phase at a time. Each phase ships in a zip and is installed before the next one starts. *Reason:* the host migration is next, and a complete backup is its safety net. Four half-finished tracks would be the opposite of durable.
- **2026-10-23: Slice profiles get a new Portal file,** `config/myrhino/slice_profiles.json`. It follows the registry/lists pattern: schema version, validated on save, atomic write. *Reason:* a file inside the config folder is backed up with no extra work. Materials stay Klipper-facing in variables.cfg.
- **2026-10-23: No cross-engine translator.** A profile is engine-native (one engine's settings plus a shared header). Switching engines means choosing that engine's profile. *Reason:* Kiri:Moto and PrusaSlicer settings don't map one-to-one, so a translator would silently print differently.
- **2026-10-23: "Away"** means the time since the later of the last job's end and the last Studio visit. There is no toggle. *Reason:* it can be worked out without the operator having to remember anything.
- **2026-10-23: The browser holds nothing durable.** *Reason:* a cleared cache or a different device must not lose work.
- **2026-10-23: The 7050 migration is accepted on a load test:** slice a long job while a print runs, with no missed steps and no timer-too-close errors. Pinning cores is a mitigation, not the test. *Reason:* only a measurement settles it.
- **2026-10-23: PrusaSlicer will be first-class or out,** decided after that load test. *Reason:* the middle position is the worst, because the safety notes then have to cover two half-supported paths.
- **2026-10-25: "First-class" PrusaSlicer means all four of these:**
  - (a) a Portal profile type
  - (b) its output goes through the same file check as Kiri:Moto (already true)
  - (c) a README safety section
  - (d) the job-setup flow
  
  *Reason:* the definition is set before the decision, so it can't be decided by feel (INV-C2).
- **2026-10-25: Versioning (INV-B2):** objects added from Phase 1 on are versioned by the Portal, keeping the last 5 revisions and pruning on save. Older objects (tools, lists, maintenance) are versioned by the backup's git history. *Reason:* this keeps the invariant true without claiming the Portal already does something it doesn't.
- **2026-10-25: What the backup covers** is defined once, in docs/phase0-spine.md § Backup inventory. Three open questions must be answered before Phase 2 code starts:
  - klipper-backup's `backupPaths`
  - whether `variables.save` is git-ignored
  - whether PrusaSlicer has a saved profile on the Pi
  
  *Reason:* a backup promise is only as good as its inventory.
- **2026-10-25: Phase 2 gates, answered on the Pi.**
  - (1) klipper-backup `backupPaths` is `printer_data/config/*` only, so it covers the whole config folder and nothing outside it. This confirms the inventory: Moonraker data and `rhino_data` aren't covered today.
  - (3) There are no saved PrusaSlicer profiles on the Pi; `rhino_data/prusaslicer/` holds only `cache` and `jobs`, which are re-derivable and not backed up.
  - (2) `variables.save` is backed up. There is no `.gitignore` entry for it, and the `.env` `exclude` array only skips `*.swp *.tmp printer-<stamp>.cfg *.bak *.bkp *.csv *.zip`. All three gates are clear; Phase 2 code can start once Mike approves the design.
- **2026-10-25: Backups keep the last 10 archives** (Mike).
- **2026-10-25: The Moonraker database is backed up with Moonraker's own backup endpoint** (the whole DB), rather than exported by hand. *Reason:* it is complete (history, totals, every namespace) and Moonraker restores it itself, refusing while printing. Checked in the Moonraker source.
- **2026-10-25: History merge is pending Mike's answer.** Moonraker has no import API, so a merge means writing into its SQLite file while it's stopped. The 7050 move doesn't need one.
