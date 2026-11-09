# Proposal: the Rhino keeps its own PAUSE, RESUME and CANCEL_PRINT

Nov 9 2026. **Waiting for Mike's answer. Nothing is applied.**

## Why

Mike wants Mainsail gone after a two-week spare period (Nov 9 2026: "I do not want to give myself a crutch to fall
back on"). Klipper can't run without one piece of Mainsail: `printer.cfg`'s first line is `[include mainsail.cfg]`,
the read-only file from the `mainsail-config` package. It defines:

| Section | Used by the Rhino for |
|---|---|
| `[virtual_sdcard]` (with `on_error_gcode: CANCEL_PRINT`) | every job file; a job error runs the cancel |
| `[pause_resume]`, `[display_status]`, `[respond]` | pause, progress, every `RESPOND` and prompt |
| `PAUSE`, `RESUME`, `CANCEL_PRINT` | Studio's Pause / Resume / Cancel buttons, `on_error_gcode`, the Rhino's hooks |
| `SET_PRINT_STATS_INFO` (wraps Klipper's), `SET_PAUSE_NEXT_LAYER`, `SET_PAUSE_AT_LAYER` | slicer layer info; pause at a layer |
| `_TOOLHEAD_PARK_PAUSE_CANCEL`, `_CLIENT_EXTRUDE`, `_CLIENT_RETRACT`, `_CLIENT_LINEAR_MOVE` | the park move; pause/resume retract |

Removing Mainsail with KIAUH may take `mainsail-config` with it. Klipper would then refuse to start: the include is missing,
and so would be every section above.

## What changes

1. **A pinned copy goes into the package:** `client_mainsail.cfg`. It's the current upstream `mainsail-config`
   `client.cfg` (GPL-3.0, © Alex Zellner, credited at the top), with **the macro bodies unchanged**. Only the header
   comment says where it came from and which version it is.
2. **`printer.cfg`'s first line:** `[include mainsail.cfg]` becomes `[include client_mainsail.cfg]`. Only one of
   the two may be included: both together is a "section already defined" error.
3. **`client_macros.cfg` is unchanged.** `_CLIENT_VARIABLE` still points the three hooks at `_RHINO_PAUSE_HOOK`,
   `_RHINO_RESUME_HOOK` and `_RHINO_CANCEL`, and the copied macros read it exactly as Mainsail's do.
4. **The installer compares** the machine's `mainsail.cfg` (if it still exists) with the pinned copy and *says* if
   they differ. It never edits either file.
5. **Tests:** the simulated Klipper runs every pause, resume and cancel path against the copy (the same checks as today,
   in `test_macros.py` and `test_motion.py`). A new check fails if `printer.cfg` includes both files, or neither.
6. `dev/proposal_own_client_macros.py --apply` makes changes 1 and 2. A test checks its anchors.

## What runs, in what order (unchanged)

- **Pause** (Studio, a prompt, or a layer pause): `PAUSE` → `PAUSE_BASE` → `_RHINO_PAUSE_HOOK` (tool power off, lift
  10 mm) → `_TOOLHEAD_PARK_PAUSE_CANCEL` (park at `custom_park_x/y` from `positions.cfg`).
- **Resume:** `RESUME` → `_RHINO_RESUME_HOOK` (refuses for non-print tools, which use `TOOL_RESUME`) → unretract →
  `RESUME_BASE` (back to the position, at `recover_velocity`).
- **Cancel** (Studio, or a job error through `on_error_gcode`): `CANCEL_PRINT` → heaters off, retract →
  `_RHINO_CANCEL` (`_TOOL_SAFE_OFF`, bed down, home X/Y or not for the laser, park, hooks) → `CANCEL_PRINT_BASE`.

## What can go wrong

| Risk | Guard |
|---|---|
| The machine runs a newer `mainsail.cfg` than the pinned copy, and behaves slightly differently afterwards | The copy is taken from upstream on the day it's applied. The installer reports any difference. **Mike: before applying, send** `md5sum ~/printer_data/config/mainsail.cfg` **(and its first 5 lines).** |
| Both files included: Klipper won't start | The test above. The installer also refuses a `printer.cfg` that has both. |
| Undo (menu option 4) to a backup from before this change, *after* Mainsail is removed: the old `printer.cfg` includes a missing file | Stop rule in the install notes: once Mainsail is removed, don't undo past this release. If it happens anyway, change the first line back by hand. |
| Mainsail's UI (still on port 8090 for two weeks) calls the same macro names | They're the same macros, so nothing changes for it. |
| A slicer's `SET_PRINT_STATS_INFO` stops working | It's in the copy, and the sim runs a layer-info job. |

## On the machine afterwards (checks to add to testing.md)

- **MC1:** Klipper starts with no `mainsail.cfg` line in `printer.cfg`, and `CHECK_TOOLHEADS` says OK.
- **MC2:** Pause, then resume, a print from Studio. It parks at X551 Y381, then comes back and carries on.
- **MC3:** Cancel a print. The bed comes down, X and Y home, the head parks, and the job shows as cancelled.
- **MC4:** Pause and resume a laser job with `TOOL_RESUME`. Pressing Resume by mistake is refused, as now.
- *Stop if* Klipper won't start or any of these moves differently from before: undo with menu option 4 (Mainsail is still there during the two weeks).

## Then, in two weeks: removing Mainsail

These are separate steps, each with its own OK:
1. KIAUH › Remove › Mainsail, and `mainsail-config` if offered.
2. Take `[update_manager mainsail]` and `[update_manager mainsail-config]` out of `moonraker.conf`.
3. Retire the installer's step that moves Mainsail aside.
4. Update the manual and the skills.
