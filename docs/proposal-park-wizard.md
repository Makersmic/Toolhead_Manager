# Proposal: a positions wizard (park spot, tool swap, prime line)

Nov 23 2026. **For Mike's review: nothing is built, and no Klipper macro or machine value changes until he answers.** Follows
`docs/wizard-rules.md`, including its rule that a wizard which writes text shows it and lets you edit it.

## Why

Where the head waits after a pause or cancel is set by two numbers in `myrhino/positions.cfg` (`park_x`, `park_y`), which people edit by
hand and have to get right. Today's file holds, in machine coordinates: **park** (after a cancel, a pause and a cancelled job), **tool swap**
(where the head goes to change a toolhead; the file says a filament change uses it too), **safe height** (the bed is lowered to at
least this before a swap, a park or the end of a job), **zero max Z** (the lowest the Set Z zero window goes), and the **prime line**
(start X/Y and length, for print heads). `RHINO_POSITIONS` checks them against the travel limits at start-up and when run. A wrong park
spot can put the head into the frame or a clamp, so this is the right place for a guided "jog it there and press Use this spot".

The park spot also decides where `PAUSE` and `CANCEL_PRINT` (1.9.44) take the head, so a wrong one is felt on every pause.

## The one hard rule: the Portal never writes `positions.cfg`

`AGENTS.md`: the only config files the Portal writes are the two it generates (`custom_tools.cfg`, `job_hooks.cfg`). `positions.cfg` is
the person's own file, kept by every install. So this wizard does **not** use the Portal to save anything. Two ways, both through what
Studio already does:

1. **Write through Moonraker's file API, the way Studio's Config editor does** (Files > Config): the person sees the exact lines in the
   review step (editable), presses Save, and Studio edits only the lines for the values changed in the file, keeping every comment. Needs
   a check that Studio's editor takes a copy first (it should; see open question 2). `FIRMWARE_RESTART` follows (the file is read at
   start-up).
2. **Or show the lines and let the person paste them** (the safe fallback if 1 isn't acceptable): the wizard measures, the person edits.

Proposed: 1, with a backup copy beside the file (`positions.cfg.<date>`) and a plain "Restore the previous values" button.

## The wizard (five steps)

1. **What is there.** Read only: `RHINO_POSITIONS` run quietly through the console path, showing each value now, with the travel limits and
   which are out of range. *What this does:* the macro's own text.
2. **Pick one:** Park, Tool swap, Prime line start, Safe height, Zero max Z. (One at a time, so the person never has to hold five jogs in mind.)
3. **Jog there.** The existing safe jog with small steps. Park and swap are X/Y: the head is lifted to the safe height first, and
   the wizard shows how close the spot is to the frame, the travel limits and the Z axis. Safe height is a Z measurement with the
   *lowest* tool mounted ("measured: 150" in the file today). **Use this spot.**
4. **Review (edit here).** The changed lines as text with Edit and Reset, and a plain sentence: "After a pause or cancel the head will wait
   at X551 Y381 (was X551 Y381)". Checked again against the travel limits before Save.
5. **Try it.** Sets the new value live (`SET_GCODE_VARIABLE MACRO=RHINO_POSITIONS VARIABLE=park_x VALUE=…`, which lasts until the next
   restart) and offers a **test park** ("Park the head" from the starter macros: lift 10 mm, go to the park spot) at slow speed, hand near
   Stop. Only if it looks right does the person **Keep it**, which writes the file and restarts Klipper (refused during a job).

## What can go wrong, and what stops it

- **A spot outside the travel limits or too near the frame.** Refused with the reason; the same check `RHINO_POSITIONS` makes.
- **The head hits something on the way to the spot.** The test park is slow, lifts first, and runs with a hand near Stop; the wizard says to
  clear the bed first and gives the path ("up, across, down").
- **A numbers typo in the edit box.** Same check as above, plus "this is a number" for each value.
- **A comment or a value lost from the file.** The edit touches only the named `variable_*` lines; the rest of the file is byte for byte.
  A test compares before and after on a copy of the real file.
- **A job running.** Keep refuses; moving the head to test is refused too.
- **Another value changing by mistake** (gear ratios, offsets, fan times): none are touched. Only the `variable_*` lines for the five
  positions can be edited here.

## What it needs

- No new Portal route. Studio: `src/views/PositionsWizardView.vue`; plain logic in `src/positions/` (read the file's values, replace
  only the named lines, the limits check, the sentence for each value) with tests on a copy of the shipped `positions.cfg`; mascot poses.
- Entry points: Settings > Tool changing (tool swap), Control (a "Positions" card), and the health check's note about an old `positions.cfg`.
- Also the natural place to **remove the two old `_CLIENT_VARIABLE` lines** the health check now flags in older files: the wizard can offer
  "tidy this file" in step 1 and show those lines in the edit box.

## Open questions for Mike

1. Prime line and zero max Z in this wizard as well, or only park, swap and safe height? Proposed: all five; they share the mechanism.
2. Does Studio's Config editor keep a copy of the file before it saves? I need to read it (and, if not, add the copy to the editor for
   every file, not only this wizard).
3. The tool swap spot is also used for filament changes. Should the wizard say so on that step? Proposed: yes.
4. Per-tool park spots (a tall head parks differently)? Today there is one. Proposed: not in this wizard.

## Tests and checks

Unit tests as above; headless run against the mock, each step, light and dark, desktop, phone and 760 px, one screenshot round. On the
machine (`docs/testing.md`): PW1 read-only step matches `RHINO_POSITIONS` in the console; PW2 test park at slow speed goes where the
wizard said, hand near Stop; PW3 Keep writes only those lines (compare with the backup copy) and the head parks there after a pause (OP2);
PW4 an out-of-range value is refused; PW5 Restore puts the old values back. Each with a pass condition and a *Stop if*.
