# Tuning wizards for print heads (design draft)

Nov 8 2026. **Draft for Mike's review. No code yet.** Mike asked for guided wizards, based on Ellis' Print Tuning Guide,
that walk through tuning a print head and store the results.

## What it's for

Tuning a print head today means reading a guide, slicing test objects by hand, typing commands, and writing numbers into
config files. These wizards turn each of Ellis' tests into a short series of prompts in Rhino Studio: print this, look
at that, pick the best, and the result is saved where it belongs, on the Rhino and in the backup.

Durability filter: the results live with the toolhead and material on the Rhino, so a cleared browser, a new screen or a
host move keeps them, and a print months later starts with the values that were tuned. Every test that moves or heats
the machine goes through the same check and confirm as the console. Nothing is saved without Mike seeing the old and
new value side by side.

## What the guide says (Ellis' order)

Source: https://ellis3dp.com/Print-Tuning-Guide/ (read Nov 8, every tuning article). Full notes: kept privately.

| # | Test | What's printed / done | What you judge | Result | Where it's stored |
|---|---|---|---|---|---|
| 0 | Before we begin | Checklist: everything tight, nozzle not clogged (extrude in air: falls straight), thermistor right, clean nozzle, nozzle hot-tightened | Yes/no per item | None | None |
| 1 | Extruder calibration | Mark 120 mm, extrude 100 mm at 1 mm/s (`M83`, `G1 E100 F60`), measure what's left | Length left (mm) | `new = old * (120 - left) / 100`; repeat until two runs agree | Klipper `[extruder] rotation_distance`, per extruder |
| 2 | Build surface | Wash with dish soap, don't touch, scuff smooth PEI | Checklist | None | None |
| 3 | First-layer squish | Scattered 0.25 mm patches, 120% line width; babystep live (`SET_GCODE_OFFSET Z_ADJUST=±0.01 MOVE=1`) | Pick the best patch (photos: top and bottom) | Z offset | Klipper `Z_OFFSET_APPLY_PROBE` + `SAVE_CONFIG` |
| 4 | Pressure advance | Pattern method (recommended): rows of corners at stepped PA. Tower method (Klipper): `TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE START=0 FACTOR=.0025` (direct drive) | Sharpest corner; "when in doubt, lower" | PA value (tower: `height * FACTOR + START`) | `[extruder] pressure_advance`, or `SET_PRESSURE_ADVANCE` per filament |
| 5 | Extrusion multiplier | 30x30x3 cubes at 1-2% steps (then 0.5%), many top layers, monotonic top | Smoothest top surface; "if you can't decide, pick the higher" | EM / flow ratio | Slicer, per filament |
| 6 | Cooling, layer times | Guidance only | None | Fan %, minimum layer time | Slicer / material table |
| 7 | Retraction | Defaults (direct drive 0.5 mm at 35 mm/s); tower only if stringing persists | Stringing on towers | Length, speed | Slicer, per filament |
| A | Max volumetric flow (optional) | Extrude 100 mm at rising speeds until under 98% comes out | Length extruded | mm³/s = mm/s × 2.4 (1.75 mm), pick a bit lower | Slicer, per filament |

Interplay: extruder calibration first; squish before PA and EM; PA before EM and retraction. PA changes with nozzle
size, filament, large temperature changes, input shaper and hotend; re-tune when those change.

## What users struggle with (community feedback)

Reddit itself couldn't be read from here (blocked for automated reading), so this comes from the guide's GitHub issues
(https://github.com/AndrewEllis93/Print-Tuning-Guide/issues) and the Duet forum, where the author answers users.

- **Judging the extrusion cubes is hard.** One user printed 92, 96, 98, 99 and 100% in white and found them "all pretty
  much the same" (Duet forum, post 312228). Another suggests rubbing a marker over the top: the right EM lets the ink
  run least into the grooves; it doesn't work on dark filament (issue #167). → The wizard shows side-by-side reference
  photos, suggests the marker trick for light colours, uses a raking light, and defaults to the higher value when unsure,
  as the guide says.
- **Reading PA corners is subjective**, and gaps at 90° corners leave people unsure whether it's PA or squish (issue
  #161, unanswered). → Show what too low and too high look like next to each row, ask "which row has the sharpest
  corner", and offer "I can't tell" which narrows the range and prints again at finer steps.
- **Why this order?** A user asked for the reason PA comes before EM (#148). → Each step says in one line why it comes
  where it does.
- **The PA pattern tool has ~43 settings** and the author declines adding more (Duet forum, topic 30614). → The wizard
  fills them in from what the Rhino already knows (nozzle, material temperatures, accelerations, bed size) and shows
  only the range to test.
- **Slicer differences:** PrusaSlicer can't set EM per object, so cubes are printed one at a time (#177). → The Rhino
  generates its own test G-code for EM, one object per value, so the slicer doesn't matter.
- **The pattern method is now built into Orca** (#173): the method itself is widely accepted.
- **Several issues go unanswered for months** (#161, #148, #155, #167): the guide is a good method but not maintained
  as a product. → We follow its method, not its tools, and link the source.

## How it would work on the Rhino

**Where:** Assets › Toolheads › a print head's page › **Tune**, and Settings › Tuning for the history. Print heads only
(DEPOSITION). A wizard opens on the mounted, confirmed print head and the chosen material and nozzle.

**Each wizard** is a list of steps on one screen, phone-friendly, like the macro builder:
1. **Why and what you need** (one paragraph; the "before we begin" checklist on the first run).
2. **Run the test.** Studio makes the test G-code itself (no slicer needed) from the toolhead, nozzle, material
   temperatures and the machine's limits. It goes to the Rhino as a normal job through Start job, so the tool check,
   START_JOB and the end-of-job safety all apply. Tests that only extrude (extruder calibration, max flow) send a few
   lines through the console's check instead, with the hotend hot and a confirm.
3. **Judge.** Pictures of good and bad side by side, then the user picks (a row, a cube, a patch) or types a measurement.
   "I can't tell" narrows the range and offers a finer test.
4. **Result.** The old value, the new value, and what it changes. **Save** stores it; **Try it first** applies it live
   for the next print without saving (`SET_PRESSURE_ADVANCE`, `SET_GCODE_OFFSET`).

**Order:** a "Tune this print head" path runs 0 → 1 → 3 → 4 → 5 (→ 7, A optional), each step marked done with its date.
Any wizard can also be run on its own. Changing the nozzle size or the material marks PA and EM as "re-tune
recommended".

## Where results are stored (needs Mike's decision)

The guide's homes for these values don't fit the Rhino as they are:

- **Pressure advance** is one `[extruder] pressure_advance` for every print head and material today. Ellis says it's
  per filament and per nozzle.
- **Rotation distance** is one value too, and its comment shows it's been changed per nozzle size
  (`0.4= 4.014 0.8=4.487`). Ellis is clear that rotation distance is the extruder's own calibration and must not be used
  for flow ("Don't mess with your rotation_distance" for dimensions). **I won't change that value** (AGENTS.md: never a
  working machine value without asking); I'm flagging it.
- **EM, retraction, max flow** are slicer settings; Studio's slice profiles already hold them.
- **Z offset** already lives per material in the toolhead table (`z_offset`).

Proposal: a Portal-owned `myrhino/tuning.json` (versioned, in the backup, like slice profiles), one entry per
**toolhead + nozzle + material**: rotation distance, PA, EM, retraction, max flow, Z offset, each with the date and the
test it came from. Then:
- **Studio's slicing** reads EM, retraction and max flow from it for that toolhead/material (no slicer profile editing).
- **PA and rotation distance** are applied when a job starts, per toolhead and material: either Studio sends
  `SET_PRESSURE_ADVANCE` / `SET_EXTRUDER_ROTATION_DISTANCE` as the tool's start G-code (job hooks, like the macros), or a
  generated `myrhino/tuning.cfg` that START_JOB calls. Either one is a change to what runs at job start, so it gets a
  `docs/proposal-*.md` with the order of events and what can go wrong before any code.
- **Z offset** stays in the material table, written by the Portal's existing tool editing path.

## Safety

- Test prints run as normal jobs: tool check, START_JOB, END_PRINT, cancel all as today.
- Extrude-only tests need a confirmed print head, a hot nozzle, and a confirm; they send through `check()`/`approve()`.
  The temporary `max_extrude_only_distance >= 101` the guide asks for is a config value: the Rhino's current value is
  checked first, and if it's too low the wizard says so instead of changing it.
- Live tries (`SET_PRESSURE_ADVANCE`, `SET_GCODE_OFFSET`) use the existing tuning path, behind the padlock.
- Nothing writes printer.cfg. Saving goes through the Portal with revisions and undo.
- Out of scope: motor currents, max speeds/accelerations (`TEST_SPEED`), input shaper. They touch working machine values
  and the guide marks them optional.

## Questions for Mike

1. **Where results live:** OK with a Portal-owned `tuning.json` per toolhead + nozzle + material, with PA and rotation
   distance applied at job start (the mechanism to be proposed separately)?
2. **Rotation distance:** should the extruder calibration wizard set the true extruder value, and move the per-nozzle
   difference you've been making there into EM (flow) instead, as Ellis recommends? That changes a working value, so
   it's your call, and it would be done once, on purpose, with a before/after test print.
3. **Which wizards first?** My suggestion: extruder calibration, first-layer squish, pressure advance (pattern),
   extrusion multiplier. Retraction and max flow after.
4. **Test G-code:** generate it in Studio (no slicer, fits every toolhead), or slice Ellis' STL test prints with
   PrusaSlicer/Kiri? Generating is more work but avoids the slicer differences users trip over.
