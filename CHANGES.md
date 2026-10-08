# What changed

## 1.3.6 - Set Z zero by eye

- **New `SET_Z_ZERO` window** for the LightSaber, HotJoe, DragKnife and tools you add (also a Mainsail button):
  Bed up / Bed down 10, 1 and 0.1 mm, then **SET** - that bed height becomes G-code Z0. Nothing moves when you press
  SET, and machine Z is never redefined, so Klipper's travel limits stay right. The window never lowers the bed past
  Z 380 or raises it past position_min. With the LightSaber you set it at the focus point (focus-dot buttons are in
  the window) and the job runs at Z0 with no extra offset.
- All the job setups use it: `LASER_JOB_SETUP` (replaces the stored focus offset), `CNC_JOB_SETUP` (replaces the touch
  plate and manual zero), `DRAGKNIFE_JOB_SETUP` and `TOOL_JOB_SETUP` (still adds the material's Z offset on top).
- **Z after a restart:** the exact park height is now saved whenever the bed is parked. If Z isn't homed but the bed
  was left parked, the setups ask "Is the bed still down where it was parked?" - **Yes** takes the saved height as Z
  (`SET_KINEMATIC_POSITION`) and homes X/Y, then carries on where you were; **No** leaves Z unhomed. If the bed was
  not left parked (a job was running), nothing is offered and Z must be homed with a print head, as before.
  Needs `[force_move] enable_force_move: True`, added in `toolchanger.cfg`.
- **Removed:** the 10 mm touch-plate option and `PROBE_Z_WORK_ZERO` - they used `G38.2`, which Klipper doesn't have.
- **Fixed:** `G54` no longer uses `MOVE=1` (it moved the tool by the change in offset when a zero was set);
  `SET_WORK_ZERO` and the CNC X/Y zero read the machine position, so an older offset can't leak into the new one;
  `LASERHOME` no longer moves the bed up to Z20 toward the laser.
- **Fixed:** choosing a laser, spindle, knife or added-tool material (`SET_TOOLHEAD`, or a `START_JOB` line in a job
  file) no longer resets the Z offset, and a drag-knife job's start no longer sets it to 0 - either would have
  wiped the Z zero you just set. The material `z_offset` values for the LightSaber, HotJoe and DragKnife are no longer
  used.
- Starter task "Check the Z belt drive" says 2:1. OrcaSlicer BlockOne profile: bowden length 5.9.

## 1.3.5 - Orca profiles match the machine

- Rhino PLA: 210 °C nozzle and 65 °C bed, the same as `PLA_0_4` in variables.cfg (was 220 / 55, so the bed dropped
  to 55 °C from layer 2). Its temperature range now starts at 205 so Orca doesn't warn. PETG already matched (245 / 90).
- Rhino BlockOne 0.4: printable width 550 mm (was 575), the X endstop position.
- No macro or printer setting changed.

## 1.3.4 - OrcaSlicer profiles for BlockOne

- New folder `slicer/orca/`: printer, process, PLA and PETG presets for BlockOne with the 0.4 mm nozzle, rebuilt from
  your own Orca 2.3.0 slices (settings from the latest one, Body3). First layer 15 mm/s at 500 mm/s².
  Import in Orca with File > Import > Import Configs. See `slicer/orca/README.md`.
- Start G-code uses `START_JOB TOOLHEAD=BlockOne ... EXTRUDER=0` (the PETG files still called the old `START_PRINT`).
- Bed temperature is the same on every Orca plate type, so picking a different plate can't drop PETG to 35 °C.
- **Fix: the zips up to 1.3.3 contained a `.git` folder** (our own test history) and the installer copied it into
  your config folder. If your config folder is a git repository (for example a GitHub backup), its current branch was
  replaced. The installer no longer copies `.git` or `.gitignore`, and its checks now tell you if your config folder
  has the leftover and how to fix it: put your own back from the oldest backup that has one, or delete it if you never
  had one. It only reports this; it doesn't change anything.
- No macro or printer setting changed.

## 1.3.3 - the PLA preheat question waits for an answer

- The job start ran on past the PLA "heat the bed or bypass it" question: Klipper macros do not wait for a pop-up,
  so the prime line (heating the nozzle first) and the rest of the start sequence ran while the question was still
  open, and the question could only close once that was done. The file was also released before the question and
  held again by it, then never released by the answer.
  Now the file stays held from the "Confirm Toolhead and Material" question until everything is ready; the PLA
  question closes as soon as it is answered and only then does the machine heat, prime and release the file
  (`_RHINO_JOB_GO`). Other materials go straight on. `PREHEAT` on its own (no `CONTINUE=1`) only asks and heats.
- Park position 20 mm in from Mainsail's default on both axes: X551, Y381 (was X/Y maximum minus 5, X571 Y401, which
  runs into the frame). Set in `_CLIENT_VARIABLE` (`custom_park_x/y`) in `client_macros.cfg`; used by Mainsail's pause
  park and at the end of a cancel (after `G28 X Y`).

## 1.3.2 - tool pages, menu option 3 installs

- **Tool library cards are now quick links**: picture, name, slot, what the tool is, how many materials and macros,
  and a Mounted mark. Selecting one opens the tool's **own page**, laid out like its pages in the user manual:
  - right: the tool's picture (the manual's drawings for the built-in tools; the first photo for added tools) with
    its notes;
  - left: about the tool (function, slot, how to set up a job, its Klipper outputs), the tool connector drawing
    with the contacts it uses filled in (select a contact to find it in the table) and the pin table (show all 21 on
    request), its materials with the settings that matter for that kind of tool, and the macros that belong to it
    with their descriptions;
  - Edit tool (added tools) and Maintenance tasks buttons at the top.
- The built-in tools' drawings are transparent line art that follows the theme: black lines in light mode, white
  lines in dark mode, the red callouts unchanged (made from the manual's drawings by `dev/lineart.py`). Photos of
  added tools are shown as taken.
  Built-in wording comes from `rhino/tooldocs.py`; pins, materials and macro descriptions come from the live config.
- Menu option 3 now goes straight on: unpack the zip you pick, preview it, then ask "Install now?". Before, it only
  opened the new version's menu, and option 2 still had to be chosen there - easy to miss (Mike installed the old
  version again that way).
- The dashboard shows what went wrong instead of staying on "Loading..." if a chart cannot be drawn.

## 1.3.1 - nozzle height (paper test), no park on the job-start question

- **NOZZLE_HEIGHT_CALIBRATE** (paper test, one per print head): homes, goes to the middle of the bed and opens a
  window with Down/Up 1, 0.1, 0.02 mm and Save. Save stores where that head's nozzle touches the bed
  (`rhino_zcal_<tool>`, paper thickness allowed for). `SET_PRINT` and `PRIME_LINE` now set the Z offset through
  `_RHINO_APPLY_Z`: the paper test plus an optional per-material fine-tune (`rhino_zfine_<tool>_<material>`, 0 until
  set). Without a paper test they fall back to the old per-material `z_offset` and say so. (`SET_PRINT` looked up the
  saved offset under a misspelt key, so a saved per-material offset was never used there.)
- The "Confirm Toolhead and Material" question at the start of a file holds the file with `PAUSE_BASE` /
  `RESUME_BASE`. It used Mainsail's `PAUSE`, which also parks the head at X/Y max minus 5 mm - past the end of the
  Rhino's X rail.

## 1.3.0 - Dashboard, Mainsail colours, first-start tool question

**Dashboard** (the portal now opens on it). Toolheads on the left, maintenance on the right, same weight:
- Tiles: machine state and mounted tool, production hours, jobs (and how many finished, last 12 weeks), filament,
  overdue and due-soon counts.
- Toolheads: hours by toolhead (producing vs mounted, not producing), jobs by toolhead, a card per tool with its
  use and its most urgent maintenance task, jobs per week (finished / cancelled / failed, from Moonraker).
- Maintenance: task status, the six most urgent tasks with how far through their interval they are, tasks by
  machine and toolhead, maintenance logged per week.
- Every chart has a Table button, hover/focus tooltips, and each toolhead keeps one colour everywhere.

**Matches Mainsail.** The portal reads Mainsail's own appearance settings from Moonraker (dark or light mode and the
primary colour under Settings > UI-Settings) and follows them, checking every 2 minutes. If Mainsail has never
saved its settings, the portal uses Mainsail's defaults (dark, blue).


- First start after an install: `RESTORE_TOOL` only printed "No saved toolhead" in the console when no tool had
  been recorded yet. It now shows the "which toolhead is mounted?" pop-up with a button per tool, and the choice
  is saved for the next restart.
- Z `gear_ratio` back to 2:1, the value the Rhino had before 1.2 (confirmed by Mike). 1.2 had changed it to 3:1.

## 1.2.1 - first run on the machine: start-up errors, safe park height, no Z homing with non-print tools

Found installing 1.2 on the Rhino:
- `[delayed_gcode TOOL_POWER_WATCHDOG]` had a `description:` line, which Klipper refuses in that section.
- `[output_pin SPINDLE_SPEED]` had `shutdown_value: 0.3`; software PWM only allows 0 or 1. Now 0 (a steady
  level, no pulses; the spindle relay also opens on a shutdown).
- `SWAP_TOOL` stopped with "Must home axis first" after a restart.

**Safe park height.** `_RHINO_PARK` (in `toolchanger.cfg`, `variable_safe_z: 150`) lowers the bed to at least
Z150, which clears every tool; it never raises the bed toward the tool. `END_PRINT`, cancel and `SWAP_TOOL` use
it (they used to lift only 10 mm). A 5 s watcher saves `rhino_z_safe` (1 = bed at or below the safe height)
whenever Z is homed; starting a job clears it.

**Z is never homed with a non-print tool.** `SWAP_TOOL` homes X/Y only: by itself if the bed was parked before
the restart, otherwise after you confirm the tool is clear. The laser, CNC, drag-knife and added-tool flows
(`LASERHOME`, `_CNC_ZERO_XY`, `PROBE_Z_WORK_ZERO`, `_DK_ZERO_Z`, `TOOL_JOB_SETUP`) now call `_RHINO_HOME_SAFE`:
Z must already be homed (with a print head; it stays homed through a swap), the bed goes to the safe height and
only X/Y are homed. Their old check read `printer.homed_axes`, which does not exist, so they ran a full `G28`
every time. `PURGE` had the same broken check (print head, so it still homes all axes when needed).

**Installer.** `install.sh` / `uninstall.sh` replace the hand-typed install: checks first, backup, copy, SAVE_CONFIG
carried over (never doubled), paths, packages, service, a pass/fail summary, and `--dry-run` to preview. The
`CHECK_TOOLHEADS` pop-up now says where the OK / ERROR line is.

The lint now refuses options Klipper rejects at start-up in `delayed_gcode` / `gcode_macro` sections and soft-PWM
shutdown values other than 0 or 1.

## 1.2 - categories, the 21-pin connector, system hardware, admin lists, status codes, Task Books

**Add a tool, step 1** asks Additive, Subtractive or Passive, then the kind of tool within it. Kinds are
edited under Admin > Tool lists (name, help, starting cap / on-time / materials / checklist); what a kind
needs (a print head, a power output, nothing) is fixed once it exists. Old kind codes keep working.

**Outputs by umbilical contact.** The Outputs step lists one row per output with a "+": main power (the
PWM level M3 S sets) or "switch on with the tool". Each row picks a contact of the 21-pin connector whose
board pin drives an output in the config, a new output on a spare pin, system hardware (e.g. a vacuum
that runs with the tool) or another output. Extra switch outputs become `also_on` in the registry and
`SET_TOOL_POWER`, `M5` and `_TOOL_OUTPUT_OFF` drive them. Every tool records the contacts it uses
(ticked, plus the ones its outputs and controls drive) - shown as a pin map on its card and on the Pins page.
`umbilical.json` may now describe the contacts (`"contacts": [...]`); the default is the Rhino pin map.

**System hardware** (Hardware > System hardware): enclosure fans and lights, pumps, door switches -
anything on a board pin that is not on the umbilical. Same guided set-up as a tool control, no
mounted-tool guard, optional safe-off, written to custom_tools.cfg. Maintenance tasks can be put on it.

**Admin** (new sidebar group): Tool lists (kinds, material-name suggestions, nozzle sizes, hardware
categories), Maintenance lists (machine areas, kinds of work, priority names), Status codes.

**Status codes.** Built-in statuses can be renamed and recoloured. Custom statuses ("Pending - Waiting
on parts") carry rules: where the task is listed, whether its clock keeps running, pauses, or counts as
done, when the status ends by itself (never / after N days / when the machine is used again), whether it
stays in the Mainsail reminder, whether a note is required, and whether it is offered in Log work, which
is now a drop-down (Done, Skipped, your statuses).

**Task Library and Task Books.** All tasks is now Tasks. The Task Library holds task definitions (the
starter tasks are seeded into it) and Task Books, named groups of them. Assigning a book to a toolhead,
system hardware or the whole machine adds its tasks there, linked: editing a library task updates every
copy, adding or removing a task in an assigned book adds or archives it. A linked task can be detached to
customise it. After Add a tool, the portal offers the book that fits the new tool.

**Merged from the 1 October session** (these had been made on another copy of the config):
- `TOOL_RESUME` and the safer pause for laser, CNC, drag-knife and user-added-tool jobs: Mainsail's Pause
  lifts the head 10 mm and switches the tool off before parking; a pop-up offers **Resume job** /
  **Cancel job**. `TOOL_RESUME` travels back over the paused spot, spins HotJoe back up first, lowers the
  last 2 mm slowly and only then restores laser / tool power. Mainsail's own RESUME is stopped for those
  jobs (it refuses with a cold extruder anyway). Print jobs pause and resume exactly as before.
- Mainsail hooks: `_CLIENT_VARIABLE` (`user_pause_macro`, `user_resume_macro`, `user_cancel_macro`) instead
  of a second `CANCEL_PRINT` that silently replaced Mainsail's. Rhino's cancel steps are `_RHINO_CANCEL`.
- Touch-plate probe: `PROBE_Z_WORK_ZERO` and `_CNC_PROBE_Z_RUN` read Z after `G38.2` (new
  `_CNC_SAVE_TOUCH_Z`); before, the saved work zero was the start height, e.g. 8 mm too high.
- `printer.cfg`: old duplicate `run_klipper_backup` removed; Z `gear_ratio` 3:1 (was 2:1). Re-check Z
  travel, `Z_TILT_ADJUST`, the probe Z offset and per-material Z offsets.
- Tests run against the real Mainsail macros (`dev/fixtures/mainsail.cfg`, used only by the simulator -
  do not copy it into the config folder). Pop-up messages sit bottom-right, clear of Restart Klipper.

**Smaller:** collapsible sidebar groups; notes-only and pin-map-only edits no longer ask for a Klipper
restart; the Save button in the control/macro popup runs a pending check instead of being ignored; phone
layout fixes.

## 1.1 - controls, macros, restart timer, preventive maintenance

**Tool controls** (new Controls step in the add wizard, Controls tab in the editor). Describe what an extra
output or input does; the portal deduces the Klipper section (`output_pin` on/off or PWM, `fan_generic`,
`heater_fan`, `servo`, `gcode_button`), checks the name against every object in the config, offers only
free umbilical pins (filtered by pin type when `umbilical.json` describes them), and previews the exact
text. Options: active-low, state at power-up, off-or-on at Klipper shutdown, switch off on safe-off
(`_TOOL_SAFE_OFF` now calls the generated `_RHINO_CONTROLS_OFF`), and generated on/off/set/angle macros that
can be limited to "only while this tool is mounted".

**Tool macros** (new Macros step / tab). Name, purpose (becomes `description:`), body, optional
mounted-only guard. Refused before saving: names used by any macro or Klipper command (case-insensitive),
G-code words, Jinja errors (the section is parsed the way Klipper parses it, then compiled with Klipper's
template delimiters). Warned: `SAVE_CONFIG`/`FIRMWARE_RESTART`/`M112`..., unknown commands, text after
` #` or ` ;` that Klipper drops as a comment.

**Restart banner.** Lists the waiting changes (portal and console), shows the running job with progress,
elapsed, time left (slicer estimate, or file progress for laser/CNC files), when a restart becomes
possible, and pause duration. Opt-in automatic restart 30 s after the job completes or is cancelled (not
after an error). Any Klipper restart clears the banner. Edits during a job are saved and queued; the
console commands stay blocked during a job because their shell command would stall the job's G-code.

**Preventive maintenance.** New Maintenance section: due & upcoming dashboard, task list per machine area
and tool, work log, usage meters, starter task library covering every machine area and tool type.
Schedules by time (from last done or fixed calendar), usage meter, event, or date, whichever comes first,
each with an early alarm. Meters come from a background Moonraker poll plus Moonraker's job history.
Never blocks a job; one Mainsail prompt after each Klipper start (`guided/maintenance.cfg`) and
`PM_STATUS` in the console. Tool renames and removals carry over to tasks and meters.

**Safety fix carried over:** `tools/spindle.cfg` `SPINDLE_SPEED` had `shutdown_value: 1`, so a Klipper
shutdown (e.g. M112) sent the ESC signal to full throttle. Now `0.3` (ESC neutral).

**Also:** `toolchanger.cfg` restore prompt hands over to the maintenance reminder (`_RESTORE_TOOL_DISMISS`),
the lint now fails the run on problems and knows `SET_SERVO`/`M112`, the simulator handles fans and
servos, `dev/demo_server.py` added, new tests `dev/test_extras.py` and `dev/test_maint.py`.

## 1.0

## Bugs fixed in your existing config
Each was reproduced against your original files in a Klipper macro simulator first, then re-tested after the fix.

| File | Problem | Fix |
|---|---|---|
| `tools/spindle_macros.cfg`, `tools/laser_macros.cfg` | `M3`/`M4`/`M5` were defined in **both** files. Klipper merges duplicates and the later include (laser) won, so a CNC job's `M5` hit the laser lockout and the spindle versions never ran. | One dispatcher in `tools/tool_power.cfg` that acts on the mounted tool (laser, spindle, custom tool). |
| `tools/laser_macros.cfg`, `spindle_macros.cfg` | A rejection (`action_raise_error`) in a macro aborts the **whole macro before any line runs**, so the "switch it off" lines above it never executed. | Switch off first, then a separate `_TOOL_REJECT` macro raises. |
| `myrhino/TOOLHEAD_DISPATCH.cfg` | `SET_STEPPER_PARAMETERS` only worked for `_0_4`/`_0_8` deposition keys, so a laser, CNC or drag-knife job failed with "not found". | Key is `MATERIAL_NOZZLE` for deposition tools only; any nozzle size; other tools use the plain material name. |
| `tools/3dp_macros.cfg` | `PRIME_LINE` set an `is_running` flag that was never cleared, and required `toolheads` in `variables.save` (which is not there). | Both removed. |
| `LED/led_macros.cfg` | `LEDOFF` checked the wrong object name, so it always reported an invalid pin. | Correct `output_pin` lookup. |
| `myrhino/mysystem.cfg` | Servo macros wrote `SERVO_LASER`, which is the **laser intensity** pin while LightSaber is mounted. | Blocked while LightSaber is mounted. |
| `myrhino/mysystem.cfg` | `EMERGENCY_STOP` left the laser rail/signal on. | Calls `_TOOL_SAFE_OFF` (laser, spindle relay + ESC neutral, custom tools); centres the SwitchFly servo only if SwitchFly is mounted. |
| `client_macros.cfg` | `CANCEL_PRINT` left the spindle/laser on. | Calls `_TOOL_SAFE_OFF`. |
| `toolchanger.cfg` | `SWAP_TOOL.current_tool` is a macro variable and resets to 0 on every Klipper restart. | Saved to `variables.save` on each confirmed swap; ~8 s after startup a prompt offers to restore it (`RESTORE_TOOL`). |
| `toolchanger.cfg` | After a swap the saved "last toolhead" could still say SwitchFly, so `G1 E` was inverted on BlockOne. | The confirmed swap re-points the saved toolhead and resets the extruder index. |
| `toolchanger.cfg` | `ADD_NEW_TOOL_RESPONSE` and its edit/delete twins used `action:prompt_input`, which Mainsail does not support. They could never work. | Removed. Replaced by the portal and `guided/add_toolhead.cfg`. |
| `shell_command.cfg` | Typo `github.com{username}`; `PREFLIGHT_BACKUP_CHECK` called `tc.run_shell_command`, which does not exist. | Fixed. |
| `client_macros.cfg` | `CREATE_TOOLHEAD_LOG` ran a shell command that is defined nowhere. | Commented out. |
| `printer.cfg` | The `ADD_TOOLING` include was commented out. | Includes for the new files. |

## New files
- `rhino/` - the tool-management package (see README for the map). `scripts/rhino_toolgen.py` and `scripts/rhino_portal.py` are thin launchers.
- `myrhino/custom_tools.cfg` - generated registry (empty until you add a tool).
- `tools/tool_power.cfg` - M3/M4/M5, `_TOOL_SAFE_OFF`, `SET_TOOL_POWER`, power cap, watchdog, pause/resume handling.
- `guided/add_toolhead.cfg` - console commands. `guided/generic_workflow.cfg` - `TOOL_JOB_SETUP`.
- `service/rhino-portal.service`, `dev/` (lint + tests), `README.md`, updated `Prompt.md`.

## Not changed - please check on the machine
1. **`G54` uses `SET_GCODE_OFFSET ... MOVE=1`.** That physically moves the head by the change in offset, so "set zero here" flows can drive the head away from where you set it. My new `TOOL_JOB_SETUP` does not use `MOVE=1`; I left your CNC macros alone because I cannot test them on the machine.
2. **`G38.2` is not a stock Klipper command**, so the CNC touch-plate step (`PROBE_Z_WORK_ZERO`) will fail unless you have a module that provides it.
3. **`COOLDOWN.cfg`:** the full ABS/ASA ramp is longer than Klipper's default 600 s idle timeout; add `[idle_timeout] timeout: 1800` if you want it.
4. **Connector pins:** of the nine pins on your portal's whitelist, PE0, PE1, PE2, PE3, PF4 and PB0 are already used in `printer.cfg`/`3dp.cfg`/`laser.cfg`. Only **PB1, PC0, PC1** are free, so at most three new pins - sharing existing outputs is how you add more. If your umbilical really carries other pins, list them in `myrhino/umbilical.json`.
5. `run_klipper_backup` is defined in both `printer.cfg` and `shell_command.cfg`; they merge and one wins per option. Delete one.
6. `LEDFLASH` blocks for about 1.35 s every time it runs, which also delays safety macros that call it.
7. Pause/resume power handling uses Mainsail's `user_pause_macro`/`user_resume_macro` hooks when they exist (I could not see your `mainsail.cfg`). If they do not, the 5 s watchdog still cuts power during a pause and restores it after resume, up to 5 s late.
8. All starting power values (hot wire 40-50 %, caps, max on-times) are placeholders. Start low.
