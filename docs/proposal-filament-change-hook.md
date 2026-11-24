# Proposal: a job-hook slot for the filament change (a Klipper macro change, needs Mike's OK)

Nov 23 2026. **APPLIED Nov 23 in 1.9.46 (Mike: "apply the after_filament_change slot").** Untested on the machine: checks FH1-FH3. Mike asked (Nov 23, "all print heads and the filament change"; "write it up") for the custom job hooks to cover
the filament change as well as the start, end, pause and resume.

## What exists

`FILAMENT_CHANGE` (`guided/filament_change.cfg`) works mid-print or standalone. Order of what runs:

1. `FILAMENT_CHANGE`: checks (print head mounted, homed). If printing it runs `PAUSE` (**the `on_pause` hook already runs here**), then
   `SAVE_GCODE_STATE NAME=filament_change_state`, then a prompt.
2. `_FC_HEAT`: `M109` to the material temperature, `_RHINO_LIFT DZ=10`, move to the swap spot (`swap_x/swap_y`).
3. `_FC_RETRACT_PROMPT`, `_FC_RETRACT` (retract), you pull the filament, `_FC_LOAD_PROMPT`, `_FC_LOAD` (feed 80 mm, ask if it extrudes cleanly).
4. `_FC_FINISH`: `PURGE`, then `RESTORE_GCODE_STATE ... MOVE=1` (back to where it was), then `RESUME` if it paused a print (**`on_resume` runs here**).

So pause and resume hooks already fire around a mid-print filament change; what is missing is a hook that fires **only for a filament change**
(also a standalone one) and that runs **after the purge, hot, at the swap spot, before the head goes back**.

## The change

One new slot, `after_filament_change` ("After a filament change"), and one added line in `_FC_FINISH`, between `PURGE ...` and
`RESTORE_GCODE_STATE`:

```
  PURGE TOOLHEAD="{TOOLHEAD}" MATERIAL="{MATERIAL}" NOZZLE_SIZE={NOZZLE_SIZE} EXTRUDER={EXTRUDER}
  # job hooks (docs/proposal-filament-change-hook.md): after the purge, hot, at the swap spot, before the head goes back
  _RHINO_HOOKS SLOT=after_filament_change TOOL={TOOLHEAD}
  RESTORE_GCODE_STATE NAME=filament_change_state MOVE=1 MOVE_SPEED=100
```

The line is added by `dev/proposal_filament_hooks.py --apply` (same anchor-checked method as `proposal_macro_hooks.py`; it stops and
changes nothing if the anchor isn't found exactly once). Alongside it: `after_filament_change` in `HOOK_SLOTS`, the Studio slot list and
labels, and the tests that count slots and calls. A machine with nothing set in the slot is unchanged: `_RHINO_HOOKS` has no branch for it
and does nothing. The hook line checker, scopes (machine, category, tool) and the 20-line limit apply as for the other slots.

## What can go wrong (and one thing I found that stops me attaching the nozzle wipe to it)

1. **Z crash with an absolute Z move.** Hook lines are plain G-code. The nozzle wipe macro the wizard writes goes to an **absolute** Z
   (bed lowered by "clearance" from the brush contact height). At the start of a job the bed is near the first layer, so that only lowers it.
   **Mid-print the bed has already moved down by the printed height**, and an absolute move to the wipe's Z would **raise the bed back up
   toward the nozzle with the part on it**. That is a crash. So **the wipe wizard must not attach itself to this slot** as it is
   built. I haven't offered it. (It stays attached to the start slot only.)
2. **What the slot is safe for:** things that don't move Z absolutely: fan, LED, a message, a macro of your own with relative moves, a sound.
3. **To make a wipe safe here** needs a guard that can only be written in a macro (`{% if printer.toolhead.position.z < ... %}`), which the
   hook lines can't carry. That would be a second macro change (a Portal-owned `_RHINO_WIPE_SAFE`), and it needs its own write-up. I have
   not started it.
4. The hook runs **hot** and **after** the purge: a hook line that waits (`G4`) keeps the nozzle hot over the print; keep it short.
5. If the hook line errors, `_FC_FINISH` stops at that line: the state stays saved, `FILAMENT_CHANGE active` stays 1, the print stays
   **paused** and the head stays at the swap spot. Nothing moves further. The way out is `_FC_ABORT` (Cancel in the prompt) or RESUME. The
   hook line checker already refuses lines Klipper wouldn't know, so this is the same level of risk as the other slots.

## My view

Low value on its own, until the guarded wipe exists. The honest cost-benefit: the change is small and safe, but what Mike wants it for
(cleaning the nozzle after a filament change) isn't safe through it yet. **Recommended: approve the slot (small), and decide separately
whether to write the guarded wipe.** Or leave both until the brush is built and measured on the machine: nothing is lost by waiting.

## Checks (on the machine, if applied)

- **FH1** With nothing in the slot, run a filament change on a cold, standalone head: it behaves as before. *Stop if* any new message or move.
- **FH2** Put `M117 Hook ran` in the slot, run a standalone change: it shows after the purge. *Stop if* it runs before the purge or the head moves back before it.
- **FH3** Mid-print (short job): the print resumes where it was. *Stop if* the head moves somewhere new.
