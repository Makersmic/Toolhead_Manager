# Proposal: bringing other machines and users onto the Rhino software

> **PARKED Nov 23 2026 (Mike): stays a proposal. Build nothing around it yet; he wants to think more.** Revisit when he says.

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

## Update Nov 23: aim at one audience first, and my view of Voron

Mike's idea: instead of "any Klipper machine", target a community, such as **Voron owners**, and build for the way their **toolheads are interchangeable** (a Stealthburner, a Dragon Burner, a different hotend or extruder on the same gantry), not for tool changers as such. Mike knows no Voron owner, so there is nobody to test with yet.

**What fits, from what is already built:** everything per print head. Each head keeps its own tuned values (rotation distance, pressure advance, flow, temperature, retraction, input shaper) and Studio applies them at job start; the accelerometer wizard measures each head once; Care tracks each head; the health check, Models, Files, the probe, motor and heater wizards need only Klipper's own objects. A Voron owner who swaps hotends or toolheads is the person this serves best.

**What a Voron adds (from my general knowledge: check each against the real Voron docs before building):**
- **Leveling:** a 2.4 uses `quad_gantry_level` (four Z motors), a Trident `z_tilt` (three), a Switchwire none. Studio today knows `z_tilt`; it must recognise QGL and say which of its screens apply (the Bed screens read `z_tilt` points).
- **Standard files:** Voron publishes sample `printer.cfg` files and macros (`PRINT_START` and friends), and most owners start from them. A **read-only "adopt this machine"** step can recognise those and list what Studio would need; it must never rewrite their files.
- **Probes:** Klicky and Tap are common; the Probe check applies to both.
- **Toolhead boards:** many Voron builds use CAN or USB toolhead boards (EBB36, EBB42 or similar), so the accelerometer, heaters and extruder may sit on a second board. Studio's board and pin handling already covers second boards; the shaping wizard already treats the accelerometer as a second board.
- **Where they already work:** Mainsail and Fluidd, KAMP, Happy Hare. Studio has to win on specifics, not on being "another interface": guided wizards in plain words with editable G-code, per-head memory, the health check and Care.

**My view:** a good audience, because the community is large, the config is standard enough to recognise, and per-head tuning is the feature they lack. The risk is that I **can't prove anything on a Voron from this PC**. So: build only the **read-only parts first** (adopt, recognise QGL and Z tilt, say what applies), keep Studio's writes limited to the Rhino-owned generated files (`tuned.cfg` and its siblings), and **find two or three real Voron owners** to try each release before widening. One way to find them: a short post in the Voron or Klipper communities offering the wizards and per-head tuning for testing, once there is a read-only build that cannot change their config.

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
