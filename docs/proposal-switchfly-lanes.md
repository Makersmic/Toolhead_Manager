# Proposal: SwitchFly lanes (servo power for a task, saved positions, retract per lane)

Status: **built and released in 1.9.35 (revision 3, Nov 16 2026).** Mike approved the power rule and the Studio layout. Assumed, not yet confirmed by Mike: the retract is the lane being left's, 0-180 degrees is the servo range.

## Why

SwitchFly's path servo is fed from a UBEC on umbilical contacts 11/12, which are PA1 (`Spindle_power`, the HotJoe
spindle relay). Nothing switches that rail on for SwitchFly today. Mike tested the servo: it does not hold its position
without power. The servo angles (0 and 180) are fixed in code, and the retract on a lane change comes only from the
material.

## Rule (Mike, Nov 16): power the servo for a task, never because the tool is mounted

The rail goes on only when the servo is about to be used, and is cut by the existing safe-off at the end of a job,
cancel, tool swap and e-stop. **`_TOOL_SAFE_OFF`, `_TOOL_OUTPUT_OFF`, the swap and the e-stop are not changed.**
The spindle path is not changed either: HotJoe powers PA1 only through its own activate macros, as now.

## What changes (only `tools/3dp_macros.cfg`; the user's own config is not touched)

New `_SWITCHFLY_POWER_ON`: if the mounted tool (Klipper's `SWAP_TOOL.current_tool`) is SwitchFly, set `Spindle_power`
to 1; otherwise do nothing. Called first in `_SWITCHFLY_SET_PATH`, which is already how every lane is commanded:

| Task | Reaches `_SWITCHFLY_SET_PATH` through |
|---|---|
| Swap to SwitchFly | `toolchanger.cfg:93` |
| Job start | `SET_PRINT` (`3dp_macros.cfg:470`), path `EXTRUDER` |
| `SWITCH_T0` / `SWITCH_T1` (buttons, slicer lane change) | `_SWITCHFLY_SWITCH` (`:135`) |
| Filament change | `guided/filament_change.cfg:84` |

So the servo is powered and re-sent its angle at the start of every task, whether or not it drifted while off.

Also new, all with SwitchFly mounted only:
- `SWITCHFLY_SERVO_TEST ANGLE=n`: needs SwitchFly mounted and the power already on (it never powers the rail itself), range-checks, moves the servo. Never saves.
- `SWITCHFLY_SERVO_POWER ON=1|0`: Studio's power button. On needs SwitchFly mounted; off always works.
- `SWITCHFLY_SET_LANE PATH=0|1 [ANGLE=] [RETRACT=]`: check SwitchFly is mounted, angle in range, retract 0-100 mm, save.
  Moves nothing.
- Saved angles `switchfly_angle_t0` / `_t1` (save_variables), default 0 and 180 (today's values). `_SWITCHFLY_SET_PATH` uses them.
- Saved retract `switchfly_retract_t0` / `_t1` (mm). `_SWITCHFLY_SWITCH` already retracts before the servo moves, using
  the material's `retraction_length`; a saved value replaces it for the lane being left, unset keeps the material's.

## What can go wrong

1. **Powered during a job, then a cancel or end cuts it.** Intended. The servo may drift afterwards; the next task
   re-commands the lane before anything uses it.
2. **Manual use leaves the rail on.** A lane button or bench test powers it; it stays on until a cancel, end of job,
   swap or Studio's Turn power off. The Lanes panel shows the power state and the button.
3. **Pause** does not call safe-off today, so the servo stays powered through a pause and resume. Unchanged.
4. **A bad saved angle** could jam the selector. Mitigation: range limit, no save from the test move, padlock in Studio.
5. **Cold retract.** `SWITCH_T0/T1` retract before they heat; a cold hotend stops with Klipper's min-extrude error. Existing.
6. **E-stop's "centre the servo" line** runs after safe-off has cut the rail, so it only works if the servo is still
   powered. Existing behaviour, left alone.
7. **Studio's spindle readouts.** Checked: the spindle tile appears only with a spindle tool mounted, so SwitchFly never shows "spindle on". One edge left alone on purpose: once a spindle tachometer is fitted, the Dashboard's rail would read "Spindle 0 rpm" while the UBEC is powered. Hiding a spindle reading on other tools would be worse than showing it.

## Tests

Simulator (`dev/`): power on only with SwitchFly mounted; every task above powers it; safe-off still cuts it; other
tools unchanged; defaults; range checks; retract override.
On the machine (`docs/testing.md`, each with a pass and a *Stop if*): SF1 power at a lane change, SF2 cut at end of job
and re-powered at the next start, SF3 lane angles, SF4 retract, SF5 swap away cuts power, SF6 release button.
