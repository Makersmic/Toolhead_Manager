# Proposal: bringing other machines and users onto the Rhino software

Nov 23 2026. **For Mike's review: nothing is built.** Mike's idea: once the wizards are done, build "aspects for porting other users over easily", such as wizards that
capture axis lengths and endstop positions, "and we aren't far off". This is my reading of it, what already exists, what is missing, and a build order. It follows
`docs/wizard-rules.md` (plain sentence plus "What this does", editable text, read before write, nothing changes unless you keep it) and the durability rule.

## First, what "porting" can mean (three different jobs)

| Level | Who | What they have | What they need from us |
|---|---|---|---|
| **A. Studio on any Klipper machine** | someone with an ordinary Klipper printer | Klipper, Moonraker, their own config | Studio's screens, tuning wizards, models, health check, with nothing of ours in their config |
| **B. The Rhino Tool Manager on a similar machine** | a builder of another multi-tool or tool-changing printer | their own hardware, their own travel, bed, probe, dock | the Tool Manager's macros, safe tool changing and job hooks, **fitted to their geometry** |
| **C. Clone a Rhino** | someone building the same machine, or Mike moving to a new host | the same hardware | the whole config and what was learned, copied over safely |

I'd treat **A and C as the near-term wins** and **B as the real "porting" project**, because B is where the machine-specific numbers live.

## What already exists (so this adds, not replaces)

- **C is mostly there:** the backup (`rhino-backup`, the Rhino backup zip), Settings > Host restore with a plan, `docs/install-ubuntu-server.md`, `docs/install-without-mainsail.md`, `dev/test_move.py`
  (moving a machine to a new host is tested), the installer's SAVE_CONFIG carry-over and its "keep your own files" rules, and the health check. What C lacks: **one guided path** that strings
  these together, and carrying the *tuned* values (tuning.json, tuned.cfg, hooks, macros, slice profiles) in a way a person can see and choose.
- **A works today for the screens that only read Klipper** (Files, Models, Control, the health check, the probe, motor, heater and shaping wizards use Klipper's own objects). The pieces that assume a Rhino
  are the tool registry, SwitchFly, the job start macros and the tool-change flow. Studio doesn't yet *say* "this isn't a Rhino, these screens won't apply".
- **For B, the geometry is hand-written in `printer.cfg`** (Mike's numbers): `[stepper_x]` `position_max: 576`, `position_endstop: 550`, `[stepper_y]` `position_max: 406`, the Z carriage's `position_max: 295` with its comment about the
  bed height, the three Z motors and `gear_ratio: 2:1`, `[probe]` offsets (20, 5), `[safe_z_home]` (287.5, 203), the `[z_tilt]` points, the `[bed_mesh]` area (40,40 to 500,300), and the MCU serial. The Rhino's own
  `myrhino/positions.cfg` (park, swap, safe height, prime, lowest bed) already has a **Park and positions** wizard.

## The missing pieces for B ("machine geometry" wizards)

One idea that makes the rest easy: **a machine profile kept the same way as `tuned.cfg`**: a Portal-owned, generated `myrhino/machine.cfg` (from `myrhino/machine.json`), included
after `printer.cfg`'s own sections, carrying only the machine-specific numbers, so a builder's changes never mean hand-editing the shared files and an update never overwrites them. (It needs the same approved
one-line include as `tuned.cfg`.) On Mike's own machine it starts empty: **nothing existing is moved or changed**; the wizards only fill it for a machine that doesn't have those values yet, or when the person asks.

Wizards (Wizards > Set up, each read-first, with the usual "What this does" and Keep):

1. **Axis travel and endstops.** For each axis: which way it homes, which switch it uses, home it slowly with a hand near Stop, jog to the far end with "Use this spot", and the wizard works out `position_endstop` and
   `position_max`, shows the lines, and keeps them only on Keep. Reuses the Motor check's switch and direction tests, and the Park wizard's jog and "Use this spot" step.
2. **Bed and probe.** Probe offsets (touch a mark with the nozzle, then with the probe; the wizard subtracts), the bed's usable area, and from them the mesh area and the Z-tilt points, with the same reach checks Klipper makes.
   Reuses the Probe check.
3. **Drives (steps and gears).** A calculator for `rotation_distance` and `gear_ratio` from belt pitch and pulley teeth or the lead screw, with the Extruder calibration to confirm by measuring. **It never changes a value that is already
   working**: a machine that has one gets it shown, not replaced.
4. **Tool docks.** Where each head parks and where the carriage meets it (the swap spot exists in Park and positions); the wizard adds each dock's pick-up and drop positions, tried slowly and dry first.
5. **Boards, pins and heaters** are already the **Add hardware** wizard.
6. **Adopt this machine (read-only first):** on a machine that already runs Klipper, read its config through Moonraker and *list what the Rhino software would need that it doesn't have*, without writing a thing:
   "no probe, 2 Z motors, no tool changer". That is also the honest answer to Level A.

## Moving a Rhino to a new owner (level C), one guided path

A wizard that strings the existing steps: choose what to carry (the config, the tuned values, the hooks and macros, the slice profiles, Studio's settings, the model library if wanted), show the list and the size, write
one **transfer file**, and on the new Rhino a review step that says what it will add and what it will replace, with a backup first and a way back (the rollback in the install docs). Secrets (`rhino-backup` tokens) are never carried.

## Safety and durability

- Nothing changes until Keep; everything is shown as text and can be edited; the Portal re-checks every line with the existing rules.
- A geometry value that is wrong can crash the machine (too long a travel, a wrong endstop side). So the travel wizard **homes slowly first, needs a hand near Stop, and refuses a value outside what was just measured**.
- Another person's machine is not Mike's: the shared files stay the Rhino's, the new `machine.cfg` holds their numbers, and an update can't overwrite them.
- Every wizard gets on-machine checks with a pass condition and a *Stop if*, and Level B needs **a real second machine (or a simulated one) to try on**; I can't prove it on this PC alone.

## Order I suggest

1. **Adopt this machine (read-only):** safe, quick, and it decides what Level A and B each need. Also tells Studio when a screen doesn't apply.
2. **Machine profile file** (`machine.cfg`, the one include) with **Axis travel and endstops** and **Bed and probe**, tried first on Mike's own machine in "show only" mode (it should reproduce his own numbers: a good test).
3. **Transfer file** for Level C.
4. **Drives** and **Tool docks**, then a first trial on another builder's machine.

## Questions for Mike

1. **Which level do you mean?** A (Studio on other people's Klipper machines), B (the Rhino software on other builders' machines), C (cloning a Rhino), or all three in that order?
2. **Who are "other users"?** People building a Rhino from your design, or owners of other printers? That decides how much of the Rhino's macros must be generalised.
3. **`machine.cfg` include:** OK to add one more generated, Portal-owned file the same way as `tuned.cfg`?
4. **First test:** can I use your own machine in **show-only** mode (the wizards propose values and compare them with what `printer.cfg` already has, writing nothing)? That proves the maths without touching anything.
5. **A second machine:** is there one (even a different printer) I could have the Adopt step read, or should I build a simulated one for the tests?
