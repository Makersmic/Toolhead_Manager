# Proposal: a nozzle cleaning wizard (for the wipe brush)

Nov 23 2026. **For Mike's review: nothing is built, and no Klipper macro or machine value changes until he answers.** Mike plans a
nozzle wipe brush so cleaning can be automatic; the brush isn't designed yet. Follows `docs/wizard-rules.md`, including its rule that a wizard
which writes G-code shows it and lets you edit it.

## Why a wizard, and why before the brush exists

The brush's shape, height and place aren't fixed, so the wizard can't have numbers baked in. It **measures** instead: the person jogs the
nozzle to the brush and the wizard records the spot. Any brush then works, and the wizard doubles as a way to try out brush placements
while the brush is being designed (it can be run again as often as needed).

## Revised Nov 23 after Mike's answer: define it in the wizard, call it from Job hooks

Mike: "I want to define the sequence with the wizard but then call it with Job Hooks. I thought there was a place for all of the print
heads and the filament change." What the Rhino has today, checked in `rhino/hw_catalog.py` and `rhino/job_hooks.py`:

- **All print heads: yes.** Hook scopes are `machine`, `category:additive` (every print head), `category:subtractive`, `category:passive`
  and `tool:<name>`.
- **Moments (slots): seven.** `before_start`, `after_start`, `before_end`, `after_end`, `on_cancel`, `on_pause`, `on_resume`.
  **There is no "filament change" slot.** Pausing for a change runs `on_pause` / `on_resume`, but a filament change that isn't a pause (a
  lane switch, a purge between colours, a spool swap) has no moment of its own.
- **Copy from a macro: yes (1.9.13).** A hook can be filled from a saved Studio macro and remembers which one and which revision, so
  the editor can say "the macro has changed since you copied it".

So the design becomes: **the wizard writes the sequence as a Studio macro called "Clean nozzle"** (the one place it is defined and
edited, with the review step's Edit box), then offers **Attach it to Job hooks**: scope *all print heads* (`category:additive`) or one
head, slot `after_start` (or any other the person picks), copied from that macro. Re-running the wizard updates the macro, and the hook
editor flags that the copy is old, so nothing changes in a job without a person saving it. The same macro still works as a button in
Control > Macros.

**Adding a "filament change" slot** (and a "tool mounted" one) is a small change to the slot list and to the macros that call
`_RHINO_HOOKS`: a Klipper macro change, so it gets its own write-up, exactly as `docs/proposal-macro-hooks.md` did, and waits for Mike's
answer. Until then the wipe can be attached to `on_resume`, which is the nearest existing moment.

**One thing to settle before "all print heads":** the brush spot is recorded with one head mounted. If Klipper applies each tool's
offset to its coordinates, the same numbers put another head's nozzle in a slightly different place. Either the wizard is run once per
head (scope `tool:<name>`), or it records the spot in machine coordinates and subtracts the mounted head's offset. I must read how the
Rhino applies tool offsets (`SWAP_TOOL`, `SET_GCODE_OFFSET`) before choosing; the safe default is one run per head.

## What it writes, and where (nothing new in Klipper's structure)

It uses what the Rhino already has: **job hooks** (`rhino/job_hooks.py`, the Add hardware wizard's step 4). A hook is a list of up to 20
lines Klipper runs at a moment of a job, saved by the Portal with its own checks, history and a revision check, written into
`myrhino/job_hooks.cfg` (a file the Portal owns). So there is **no new macro file, no new write route and no hand-edited config**.

- **Scope:** `tool:<print head>` (the offsets belong to the tool, so the wizard is run once per print head). Optionally
  `category:additive` for "every print head".
- **Slot:** `after_start` (after the machine is homed and the start routine has run, before the first layer). The exact moment, and
  whether the nozzle is hot by then, must be checked against `START_JOB`'s order before building (see "Before building").
- **Also as a button:** the same lines saved as a Studio macro ("Clean nozzle") so you can run it from Control > Macros by hand. Studio
  sends it through the console's own check and confirm, as every Studio macro.

### The lines it would write (a draft: the numbers come from the person's measurements)

```
SAVE_GCODE_STATE NAME=rhino_wipe
G90
G1 Z{safe_z} F{z_speed}                    ; lift clear of the part and the brush
G1 X{x_start} Y{y_brush} F{travel_speed}   ; over the start of the bristles
G1 Z{z_wipe} F{z_speed}                    ; down to the bristles
G1 X{x_end} F{wipe_speed}                  ; pass 1
G1 X{x_start} F{wipe_speed}                ; pass 2
G1 X{x_end} F{wipe_speed}                  ; pass 3 (the passes are as many lines as passes)
G1 Z{safe_z} F{z_speed}                    ; clear again
RESTORE_GCODE_STATE NAME=rhino_wipe
```

What runs, in order: the move state is saved; the head lifts to a safe height; travels to the brush; goes down to the bristles; wipes the
chosen number of passes; lifts; the move state is put back so the next lines behave as before. Up to 6 passes fit in 20 lines. A
retract before the wipe (`G1 E-1 F1800`, relative extrusion) is an optional line, off by default.

## The wizard (seven steps)

1. **Check.** A print head is mounted (from Klipper, as everywhere), it is homed, and its hotend can heat. A laser, knife or CNC head
   gets "this wizard is for print heads" and stops. *Read only.*
2. **The brush's start.** Jog the nozzle to the start of the bristles, at the height it should touch (the jog uses the existing safe jog
   with small steps and the tool's own offsets). **Use this spot.** The wizard shows X, Y and Z and checks them against the axis limits.
3. **The brush's end.** Jog to the other end of the bristles. The wipe runs along that line.
4. **How hard.** Number of passes (default 3), wipe speed (default 60 mm/s), travel speed and the safe height (default: 10 mm above the
   bristles; never below the part's own clearance). Plain notes: the bristles' temperature rating is the person's to check against the
   nozzle temperature; the wizard doesn't know the brush's material.
5. **Review (edit here).** The seven-line sequence above in plain words, then the generated G-code in a box with **Edit**. Edits are
   checked again by the Portal (the job-hook rules: every command must exist, no internal macros, no never-from-a-button commands, no axis
   moves in `before_start`, heater targets inside the heater's limit, at most 20 lines) and a refused line says why.
6. **Try it, cold, slowly.** A dry run with the heater **off**, at 20% speed, with "keep a hand near Stop". It moves along the real
   path and the wizard asks "did it touch the bristles and clear everything?". Then, if wanted, a run at the real speed, still cold.
   Hot runs only through a real print start.
7. **Save and choose when.** *Before every print* (the hook), *only when I press the button* (the Studio macro), or both. The hook can
   be switched off later without deleting the brush positions.

## What can go wrong, and what stops it

- **A crash into the brush or the bed.** The positions are checked against the axis limits and the bed; the dry run is cold and slow;
  a measurement can't put the head below the safe height on the way in; Stop works as always.
- **Wiping a nozzle that isn't hot enough or is too hot for the brush.** The wizard never sets a temperature by itself in this first version:
  the wipe happens at whatever the start routine has reached. Whether to add a "wipe at this temperature" step is an open question below.
- **Wiping when something else is mounted.** The check in step 1 and the hook's scope (`tool:<name>`) mean it only runs for that head.
- **A hand-edited block** is marked edited; re-running the wizard asks before replacing it.

No existing value changes: no gear ratio, offset, shutdown value or fan time. The hook adds lines only to the hook list the person chose.

## Before building (things I must confirm against the real macros)

1. Where `after_start` runs in `START_JOB`/`*_JOB_SETUP` (homed? heated? mesh done?) so the wipe isn't before homing or after the
   first line of the part.
2. Whether wiping should be before or after bed mesh and the probe, and whether the tool offsets are applied at that moment.
3. The hook slot list may need a new moment, "at tool change to this head", for automatic cleaning when a print head is mounted. That
   would be a change to `_RHINO_HOOKS`'s callers (a macro change: it gets its own write-up, as `docs/proposal-macro-hooks.md` did).

## Open questions for Mike

1. ~~Which print heads?~~ Answered by Mike (Nov 23): all print heads, called through Job hooks; see the revision above. Still open: one run per head or one run with offsets.
2. Should the wizard offer a **wipe temperature** ("heat to X, wipe, then back")? Proposed: not in the first version; the nozzle is wiped
   at the start routine's temperature, and the person decides after trying the brush.
3. A silicone brush and a brass brush want different temperatures and speeds. Proposed: the wizard asks which one it is and shows its
   own caution text, but doesn't change the numbers by it. Say if you'd rather it did.
4. ~~Wipe after a filament change?~~ Mike asked for the filament change place; it doesn't exist yet. Proposed: add the slot (its own write-up).

## Tests and checks

- Plain logic in `src/wipe/` (positions to lines, limits check, pass count) with tests; Portal tests reuse the job-hook ones (an edit
  with a forbidden command is refused, more than 20 lines is refused, a stale revision is refused).
- Headless run against the mock: each step, light and dark, desktop, phone and 760 px, one screenshot round.
- On the machine (`docs/testing.md`, new section; each with a pass condition and a *Stop if*): NW1 the dry run touches the bristles and
  clears everything, cold, at 20% speed; NW2 at full speed, cold; NW3 a real print start wipes then prints; NW4 an edited line is kept and
  marked; NW5 switching the hook off stops the wipe. Hand near Stop for all of them.

## Order

After the connect wizard, or sooner if the brush is ready: the wizard is useful while Mike designs the brush, because it records where
the bristles are and lets him try the motion cold.

## Built Nov 23 (Studio 0.37.0), and what reading the macros settled

Mike said go ahead. Read from `START_JOB`, `_PREHEAT_STAGE2`, `_RHINO_JOB_GO`, `_START_JOB_FILE` (nothing changed in them):

1. **When `after_start` runs:** `START_JOB` (checks, before-start hook, `G28`, the toolhead prompt) then `START_SEQUENCE` and `PreCheck`, then `PREHEAT CONTINUE=1` (hotend `M109`, bed heat-soak, `Z_TILT_ADJUST`), the bed mesh, **`PRIME_LINE`**, then `_RHINO_JOB_GO`, which calls `_START_JOB_FILE`: interlocks, **`after_start`**, `SDCARD_PRINT_FILE`. So at `after_start` the nozzle is **hot**, the machine homed, tilt and mesh done, and the prime line already laid: a wipe there is "prime, then wipe, then print". It can't clean the nozzle before probing the mesh; that would be a different moment.
2. **Offsets:** the Rhino shifts G-code coordinates with `SET_GCODE_OFFSET` (the paper-test nozzle height, CNC work zeros). The wizard's lines set the offsets to zero inside `SAVE_GCODE_STATE` / `RESTORE_GCODE_STATE`, so the jogged spot (machine coordinates) is where the head goes, and every offset is back afterwards. The Portal's hook rules accept `SAVE_GCODE_STATE`, `RESTORE_GCODE_STATE` and `SET_GCODE_OFFSET` (`rhino/presets.py` `KLIPPER_COMMANDS`).
3. **"All print heads":** Mike asked for all heads through Job hooks. Because tool lengths differ, a brush spot measured with one head is wrong for another (a Z that touches the bristles with one head can crash another's nozzle into them). So the wizard is **one run per print head**, attached to that head's start G-code (`tool:<head>`); `category:additive` is not used. Running it again for the next head takes a few minutes. Say if you'd rather have one shared set of numbers and accept the risk.
4. **Z direction:** bigger Z is the bed lower, so the wizard's "clear" lowers the bed (+Z), as the starter "Park the head" macro does. A frame-mounted brush option leaves the bed height alone.
5. **Still not built:** the "filament change" slot (a Klipper macro change, needs its own write-up and Mike's approval), the wipe temperature step, and cleaning before the mesh probe.
