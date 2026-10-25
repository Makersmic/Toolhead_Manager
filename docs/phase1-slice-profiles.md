# Phase 1: Slice profiles (design draft)

Oct 25 2026. **Draft for Mike's review. No code until he approves it.**
Builds on the § Decision: slice profiles and § Phase 1 sketch in docs/phase0-spine.md.

## What it's for

Durability filter: a print that came out right must still come out right after a cleared browser, a different device, a host move (Pi → 7050) or six months away.

Today none of that holds:
- Every slice setting lives in the browser (localStorage `rs.prepare.jobs`), keyed by file.
- Each saved job carries settings for all four processes (`fdm`, `laser`, `knife`, `cnc`), any PrusaSlicer options changed (`prusa`) and the placement.
- Defaults live in code (`src/slicer/profiles.ts`). Materials and temperatures live in `variables.cfg`, which is already backed up.

## 1. The file: `config/myrhino/slice_profiles.json`

```
{
  "schema": 1,
  "profiles": [
    {
      "id": "p_8f3k2",
      "name": "PLA 0.2 everyday",
      "engine": "kiri" | "prusa",
      "process": "fdm" | "laser" | "knife" | "cnc",
      "toolhead": "BlockOne" | null,     // null = any toolhead of that process
      "material": "PLA" | null,          // a key in the materials table, or null
      "settings": { ... },               // the engine's own shape, below
      "header": { ... },                 // summary for lists, written by the Portal on save
      "notes": "",
      "created": 1761430000, "updated": 1761430000, "rev": 3
    }
  ]
}
```

- **`settings`, Kiri:** exactly Studio's own `FdmSettings` / `LaserSettings` / `KnifeSettings` / `CncSettings`, the same shapes Prepare edits today. `kiriSettings.ts` already turns these into Kiri's names; that is a fixed mapping for one engine, not a translator.
- **`settings`, PrusaSlicer:** the INI options the user changed (`Record<string, string>`), checked against `src/slicer/prusa/schema.json`.
- **No cross-engine translator.** This was decided on 2026-10-23. A Kiri profile and a Prusa profile are separate profiles.
- **`header` is never edited.** The Portal fills it from `settings` on every save (nozzle, layer height, walls, infill %, laser power…), so there is one source of truth.
- **Temperatures stay in the materials table.** Klipper's macros read them there, and a profile only names the material. This keeps "what the hotend is allowed to do" in one place.
- **Built-in profiles** are the defaults from `profiles.ts`. They are shown as "Built in", can't be edited, and "Copy to edit" makes a saved one. They are not written to the file.

**History.** `config/myrhino/slice_profiles.history.json` keeps the last 5 revisions of each profile, plus deleted profiles for 30 days. A delete can be undone from there.

**Writing.** The same pattern as the registry and lists:
- validate on save
- write atomically (tmp + `os.replace`)
- every save sends the `rev` it started from, and a stale `rev` gets 409 ("changed on another device, reload")

Validation uses the same ranges Prepare's inputs already clamp to, and unknown keys are refused.

## 2. Portal routes: `/api/slice-profiles`

| Route | Does |
|---|---|
| `GET /` | list (id, name, engine, process, toolhead, material, header, updated, rev) |
| `GET /<id>` | one profile |
| `POST /` | new profile → id |
| `PUT /<id>` | save, with `rev` (409 on a stale rev) |
| `DELETE /<id>` | moves it to history |
| `GET /<id>/history`, `POST /<id>/revert` | the last 5 revisions, and go back to one |
| `GET /export?id=…` | one profile, or all of them, as a `.json` download |
| `POST /import` | a `.json` from export, checked like a save |

Every write goes into Studio's `PORTAL_WRITES` allowlist as its own reviewed kind, `PORTAL_PROFILES`.

## 3. Per-file jobs

A job becomes small: `{profileId, profileRev, overrides, toolhead, material, placement}`.
- `overrides` holds only the keys changed from the profile.
- If the profile changed after the job was saved (its rev moved on), Prepare says so and offers to use the new version or keep the old settings as overrides.

**Where it lives (question 1):**
- **Lean:** `rhino_data/prepare_jobs.json` on the Rhino, added to the backup zip.
- **Why not `config/`:** jobs change on every slice, and klipper-backup would push that churn to GitHub.
- **Why not the browser:** the browser holds nothing durable (decided 2026-10-23).

## 4. Studio (Prepare)

- **Picker.** Each process gets a profile picker, filtered by the mounted or chosen toolhead and the material. Built-in profiles come first.
- **Status line.** One line under the picker:
  - "Saved on the Rhino"
  - "Changed: 3 settings", with Save to profile / Save as new / Reset
  - "Not on the Rhino yet" when offline. Edits still slice, but they can't be saved.
- **Settings › Slice profiles** (a new page under Machine):
  - list, rename, notes, delete
  - history and revert
  - export and import
- **One-time import.** The first time Studio finds `rs.prepare.jobs`, it offers once to bring those jobs to the Rhino:
  - Each distinct set of settings becomes a profile named "Imported <date> <file>".
  - The jobs point at those profiles.
  - The browser key is only cleared after the Portal confirms the write.

## 5. Safety and invariants

- **Profiles never touch Klipper.** Loading or saving a profile sends no G-code, starts nothing and changes no tool state.
- **Jobs start as before.** Laser, knife and CNC jobs still start through their setup wizards. A profile's laser power is clamped as it is today: `laser_s_max` from `VARIABLES` wins.
- **The Portal re-validates every save.** A hand-edited file that fails validation is shown as "can't read, kept as is" and is never overwritten. It's the same rule as the registry.

## 6. Backup

- **Expected items.** `slice_profiles.json` and its history file join the backup's expected items (INV-B4). The archive is refused if either exists but can't be read.
- **Jobs file.** `rhino_data/prepare_jobs.json` joins the archive under `prepare/` and is restored with a partial restore ("Slice profiles and jobs").
- **Inventory.** In phase0-spine.md, the table row "Slice settings per file" changes to ✅.

## 7. Tests

**Off the machine:**
- TM: `dev/test_slice_profiles.py` (validate, rev conflict, history, export/import round trip, unreadable-file rule), added to run_all.
- Studio: unit tests for the picker filter, the overrides diff, the one-time import and the `PORTAL_PROFILES` allowlist.

**On the machine, SP1–SP8 in testing.md:**
1. Save a profile.
2. Slice from it on a second device.
3. Clear the browser, then reslice.
4. Get a 409 by editing on two devices.
5. Revert a revision.
6. Do an export/import round trip.
7. Back up and partially restore profiles.
8. Run the one-time import from an existing browser.

**Version:** TM 1.8.0 / Studio 0.9.0, one zip and one release.

## Questions for Mike

1. Per-file jobs on the Rhino in `rhino_data/prepare_jobs.json`, inside the backup zip but not GitHub. **Lean: yes.**
2. Does a profile belong to a process (any print head), with an optional toolhead, or to one toolhead only? **Lean: process plus optional toolhead.**
3. Importing a profile whose name already exists: add " (2)" or refuse? **Lean: add " (2)".**
4. PrusaSlicer profiles: same file and same path now, with no special treatment until the 7050 load test decides first-class or out. **Lean: yes**, which matches the 2026-10-23 decision.
