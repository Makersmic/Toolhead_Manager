# Proposal: the Rhino writes its own PAUSE, RESUME and CANCEL_PRINT

Nov 22 2026. **Approved by Mike on Nov 22 (design, the left-out features, the reworded lines, and deleting `client_mainsail.cfg` in the same release) and applied in 1.9.44** (`dev/proposal_own_pause_resume.py --apply`).
The sections below are the proposal as approved; "Changed while applying" at the end lists what differs.

## Why

Mike (Nov 22): Studio should stand on its own, with no dependency on Mainsail. Since 1.9.19 Klipper no longer needs
Mainsail *installed*: `printer.cfg`'s first line includes `client_mainsail.cfg`, a pinned, unchanged copy of
mainsail-config's `client.cfg`. But those 322 lines are still Mainsail's code, in Mainsail's shape:

- every pause, resume and cancel runs through Mainsail's macros and its `_CLIENT_VARIABLE` settings macro;
- the Rhino's own steps are attached to it through three text variables (`user_pause_macro` and friends);
- the park spot is copied into `_CLIENT_VARIABLE` half a second after Klipper starts (`positions.cfg`);
- most of the file is features the Rhino never uses (delta and polar parking, firmware retraction, a runout check).

## What the Rhino uses today

| In `client_mainsail.cfg` | Rhino uses it for | The Rhino's values (all Mainsail's defaults, never overridden) |
|---|---|---|
| `[virtual_sdcard]` with `on_error_gcode: CANCEL_PRINT` | every job file; a job error runs the cancel | |
| `[pause_resume]`, `[display_status]`, `[respond]` | pause, progress, every `RESPOND` and prompt | `recover_velocity` 50 mm/s |
| `PAUSE`, `RESUME`, `CANCEL_PRINT` | Studio's buttons (Moonraker runs these three names), `on_error_gcode`, the Rhino's hooks | |
| `_TOOLHEAD_PARK_PAUSE_CANCEL`, `_CLIENT_RETRACT`, `_CLIENT_EXTRUDE` | pause park; retract and unretract | retract 1, cancel retract 5, unretract 1 (mm); 35 mm/s; lift 2 mm at 15 mm/s; park X551 Y381 from `positions.cfg` |
| `SET_PAUSE_AT_LAYER`, `SET_PAUSE_NEXT_LAYER`, `SET_PRINT_STATS_INFO` | slicer layer info; pause at a layer | |
| `_CLIENT_VARIABLE` | holds the numbers above and the three hooks | `user_pause_macro`, `user_resume_macro`, `user_cancel_macro` point at the Rhino's macros |
| `_CLIENT_LINEAR_MOVE` | nothing (it is for Mainsail's own jog buttons) | |

## What changes

1. **New `pause_resume.cfg`** (the draft). Same macro names for the public ones (`PAUSE`, `RESUME`, `CANCEL_PRINT`,
   `SET_PAUSE_*`, `SET_PRINT_STATS_INFO`), because Moonraker and Studio call those. Same steps, same order, same numbers.
   A rewrite, not a copy: it still credits mainsail-config and its licence at the top (GPL-3.0, Alex Zellner).
2. **Hooks called by name.** `PAUSE` calls `_RHINO_PAUSE_HOOK`, `RESUME` calls `_RHINO_RESUME_HOOK`, `CANCEL_PRINT`
   calls `_RHINO_CANCEL`. Those three macros are **not changed**.
3. **One settings macro of the Rhino's own**, `_RHINO_PAUSE_SETTINGS`, holds the numbers in the table, so they are visible in one
   place. It replaces `_CLIENT_VARIABLE`.
4. **The park spot is read straight from `RHINO_POSITIONS`** when parking. The start-up copy in `positions.cfg`
   (`_RHINO_POSITIONS_APPLY`, two `SET_GCODE_VARIABLE` lines) goes. This also removes a half-second window after start
   when the old copy held a fallback number.
5. **Helpers renamed:** `_TOOLHEAD_PARK_PAUSE_CANCEL` to `_RHINO_PAUSE_PARK`, `_CLIENT_EXTRUDE` to `_RHINO_EXTRUDE`,
   `_CLIENT_RETRACT` to `_RHINO_RETRACT`. Nothing else in the package calls them.
6. **`printer.cfg` line 1** becomes `[include pause_resume.cfg]`. Only one pause/resume file may be included.
7. **`client_mainsail.cfg` is deleted**, along with the installer step that compares it with the machine's `mainsail.cfg`
   (`install.sh`, which says whether they differ) and its test. Going back is the installer's own Undo (menu option 4),
   which restores the whole config folder from before the install, including `client_mainsail.cfg`. That works with or
   without Mainsail installed.
8. **`client_macros.cfg`** loses the `_CLIENT_VARIABLE` block and the long note about Mainsail's sections. `_RHINO_CANCEL`
   stays in it, unchanged.
9. **Wording.** Nine lines that you see in Studio mention Mainsail (below) and are reworded; 27 comment lines get the
   same pass. No logic changes in any of them.

| File | Now says | Would say |
|---|---|---|
| `tools/tool_power.cfg:342` (pop-up when a laser, CNC or knife job pauses) | "Mainsail's own Resume button is for print jobs and will refuse because the extruder is cold." | "The normal Resume button is for print jobs and will refuse because the extruder is cold." |
| `tools/tool_power.cfg:375` | "...handing over to Mainsail's RESUME." | "...handing over to RESUME." |
| `tools/tool_power.cfg:279, 349, 363` (macro descriptions) | "Mainsail user_pause_macro...", "Stops Mainsail's RESUME...", "(print jobs use Mainsail's RESUME)" | the same sentences without Mainsail |
| `myrhino/TOOLHEAD_DISPATCH.cfg:254` | "Start the job from Mainsail's Print button..." | "Start the job from Studio..." |
| `guided/cnc_workflow.cfg:76` | "...with Mainsail's move panel." | "...with Studio's jog controls." |
| `toolchanger.cfg:294, 329` (descriptions) | "(Mainsail's temperature boxes)", "Mainsail's Home buttons come through here too." | "(the temperature boxes)", "The Home buttons come through here too." |
| `client_macros.cfg:52` (description) | "...called by Mainsail's CANCEL_PRINT through user_cancel_macro" | "...called by CANCEL_PRINT" |

## What is left out, on purpose

The Rhino never turned these on, so nothing it does changes. Each is a feature of Mainsail's file:

- **Delta and polar bed parking** (the Rhino is Cartesian).
- **Firmware retraction mode** (`use_fw_retract`: off, and the Rhino has no `[firmware_retraction]`).
- **The runout-sensor check inside RESUME** (`runout_sensor` was never set; the Rhino's filament sensors work through its own hooks).
- **The idle-timeout override in PAUSE** (`idle_timeout` was never set, so Klipper's own timeout applied). RESUME still heats back up if the printer timed out while paused. `RESUME.restore_idle_timeout` stays as a variable fixed at 0 because `TOOL_RESUME` still reads it; removing those reads is a follow-up.
- **Park-on-cancel** (`park_at_cancel`: off; `_RHINO_CANCEL` parks).
- **`_CLIENT_LINEAR_MOVE`** (used only by Mainsail's own front end).
- **The three `user_*_macro` text variables** (replaced by direct calls).

## What runs, in what order (unchanged)

- **Pause:** `PAUSE` → remember the nozzle target for `RESUME` → `PAUSE_BASE` → `_RHINO_PAUSE_HOOK` (tool power off, lift 10 mm, pop-up for non-print tools; job hooks) → `_RHINO_PAUSE_PARK` (retract 1 mm, lift 2 mm, move to X551 Y381).
- **Resume:** `RESUME` → checks the extruder is hot enough (or heats back to the remembered target if the printer timed out) → `_RHINO_RESUME_HOOK` (refuses for non-print tools, which use `TOOL_RESUME`; interlocks; job hooks) → unretract 1 mm → `RESUME_BASE` at `recover_velocity`. Too cold: "Resume aborted" in the console and a pop-up, and nothing moves.
- **Cancel** (Studio, or a job error through `on_error_gcode`): `CANCEL_PRINT` → retract 5 mm → heaters off → fan off → `_RHINO_CANCEL` (tool power off, bed down, X/Y homed or not for the laser, park, hooks) → forget a layer pause → `CANCEL_PRINT_BASE`.

## Evidence so far (all in the simulated Klipper, which is not real Klipper)

- **27 scenarios run on the old macros and on the draft, and their output compared (`python3 dev/compare_pause_resume.py <old tree> <new tree>`):** print head pause, resume and cancel; pause with `X Y Z_MIN`; `RESTORE=0`; unhomed; relative extrusion; resume with a cold extruder; resume after an idle timeout that restores 210 °C; `VELOCITY=`; pause at a layer and at the next layer; cancel clearing a layer pause; and, for the laser, CNC and knife: pause, a refused Resume, `TOOL_RESUME` and cancel. **All 27 match**: the same G-code in the same order, the same errors, pop-ups and console messages, once the three helper names are mapped.
- `lint_rhino`, `test_macros`, `test_motion`, `test_mesh`, `test_studio_start`, `test_cnc_start`, `test_job_hooks`, `test_user_macros`, `test_tuning` and `test_doctor` pass against the draft in a scratch copy. The only test lines changed are the ones that look for the old `_CLIENT_VARIABLE` and for the pinned file's checksum. `test_install` fails as expected (it checks the pinned copy; that check goes away).
- Klipper's config reader accepts the `;` comments on the settings lines (checked in its source).
- **Not yet done:** `test_real_klipper.py` (real Klipper reading the shipped config) needs an ARM compiler (`arm-none-eabi-gcc`), which this PC doesn't have, plus a Klipper checkout. I'd ask you to run it, or to install the compiler, before anything ships.

## What can go wrong

| Risk | Guard |
|---|---|
| Klipper won't start: both pause/resume files included, or neither | A test requires exactly one include; the health check (menu option 7) fails it; Undo restores the old files. |
| A template error that only shows when a macro actually runs (the simulator is not Klipper) | The scenario comparison above; `test_real_klipper.py` before shipping; checks OP1-OP7 on the machine, with a hand near Stop. |
| A move that differs from today: a pause parking somewhere else, a cancel not clearing the tool | The 27-scenario comparison; the park spot is checked in `test_motion` with edited positions. OP1-OP3 on the machine. |
| `CANCEL_PRINT` stops half-way and leaves heaters or a tool on | The order is the same as today (heaters and fan off, then `_RHINO_CANCEL`, which switches tools off first). Not made stricter in this change. A cancel that errors before `CANCEL_PRINT_BASE` leaves the job paused, as it does now. |
| An old backup restored after this change brings back `[include client_mainsail.cfg]` | Undo and restore both restore a matching set of files, so the old `printer.cfg` and `client_mainsail.cfg` return together. A restore that mixes old and new config is the risk: the stop rule below covers it. |
| Mainsail's own web page (the spare on port 8090) could lose a convenience that reads `_CLIENT_VARIABLE` (not checked) | Accepted: it is being retired. Studio doesn't use it. |
| Someone's own macro calls `_CLIENT_EXTRUDE` or `_CLIENT_RETRACT` | Nothing in the package does. The health check and the lint flag an undefined command at install. |

## Install and undo

`dev/proposal_own_pause_resume.py --apply` (following the pattern of the 1.9.19 script)
makes changes 1 to 8. It stops and changes nothing if any anchor isn't exactly as expected. The release then ships it;
the installer backs up the config folder first, as always. **Undo** is menu option 4.

## On the machine afterwards (checks to add to `docs/testing.md`)

Hand near Stop for every one.

- **OP1:** Klipper starts, `head -1 ~/printer_data/config/printer.cfg` prints `[include pause_resume.cfg]`, `client_mainsail.cfg` is gone, and `CHECK_TOOLHEADS` says OK. *Stop if* Klipper won't start: Undo.
- **OP2:** Pause and resume a print from Studio. *Pass:* it pulls back 1 mm, lifts 2 mm, parks at X551 Y381, then returns and carries on. *Stop if* it parks anywhere else.
- **OP3:** Cancel a print. *Pass:* heaters off, bed down, X and Y home, the head parks, History shows it cancelled.
- **OP4:** Laser pause: press Resume by mistake, then `TOOL_RESUME`. *Pass:* Resume is refused with its pop-up; `TOOL_RESUME` carries on. *Stop if* the laser fires before `TOOL_RESUME`.
- **OP5:** Pause with the nozzle cold and the printer left idle for the timeout (or `SET_IDLE_TIMEOUT TIMEOUT=60`), then Resume. *Pass:* it heats back first, then carries on.
- **OP6:** `SET_PAUSE_AT_LAYER LAYER=3` on a short print. *Pass:* it pauses at layer 3.
- **OP7:** Edit the park spot in `positions.cfg`, `FIRMWARE_RESTART`, then pause straight away. *Pass:* it parks at the new spot.

## Not part of this

Removing Mainsail from the machine (KIAUH, the `[update_manager mainsail]` sections, the installer's step that moves
Mainsail to port 8090) is separate, with its own steps in `docs/install-without-mainsail.md`. Renaming `_RHINO_CANCEL`,
`_RHINO_PAUSE_HOOK` and the other hooks is not proposed.

## Changed while applying

- **A compatibility stub, `_CLIENT_VARIABLE`, stays in `pause_resume.cfg`.** The installer keeps your own `myrhino/positions.cfg`, so a machine updated from before 1.9.44 still has the old start-up step, whose two `SET_GCODE_VARIABLE MACRO=_CLIENT_VARIABLE` lines would fail on every restart (and skip the position check after them) once that macro was gone. The stub has no hooks and nothing reads it; `test_macros` loads an old-style `positions.cfg` to prove the start-up stays clean. Remove it once `positions.cfg` has been brought up to date.
- **The installer takes `client_mainsail.cfg` out of the config folder** when the release has `pause_resume.cfg` (the backup it makes first keeps the file). Without that, an unused copy would sit there.
- **The doctor** (`rhino.sh` option 7) now checks for `pause_resume.cfg`, still passes a machine on the 1.9.19 setup (saying it is older), and fails any printer.cfg that includes more than one of them.
- **Tests:** the 27 old-versus-new scenarios became permanent step-by-step checks in `test_macros.py` (pause, resume, cancel, layer pauses); the lint no longer skips the pause/resume file.

## Questions for Mike (answered Nov 22)

1. **Approve the design?** Yes.
2. **Are the left-out features right?** Yes.
3. **Are the reworded lines right?** Yes, looks good.
4. **Delete `client_mainsail.cfg` in the same release,** relying on Undo to go back, or ship both files for one release? Delete.
