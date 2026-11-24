# Proposal: more tuning wizards (probe, heaters incl. chamber, drivers, retraction and temperature, input shaping)

Nov 23 2026. **For Mike's review: nothing is built.** Source: Mike's "Klipper Tuning & Calibration Tests: Master Outline" (Nov 23), checked against the
Rhino's config and the Klipper source (Nov 20 2026 checkout). Mike asked for items 1 to 5, a heated-chamber PID tune, an ADXL345 (USB) wizard, and
my opinion on a TMC driver tuning wizard. All of it follows `docs/wizard-rules.md` (one plain sentence per step, "What this does", editable G-code
with Reset, read before write, a slow or cold first run, on-machine checks with *Stop if*) and lives next to the existing tuning wizards
(`docs/phase-tuning-wizards.md`: first layer, extruder calibration, extrusion multiplier, pressure advance).

## Facts from the config and Klipper that shape the design

1. **`SAVE_CONFIG` can't be used for heater or driver values here.** `PID_CALIBRATE` and `SHAPER_CALIBRATE` end by asking for `SAVE_CONFIG`.
   The Rhino's `pid_Kp/Ki/Kd` for the hotend and bed sit in `tools/3dp.cfg`, an *included* file. Klipper refuses to start when a
   `SAVE_CONFIG` value conflicts with an included one (`configfile.py`: "SAVE_CONFIG section … conflicts with included value"). Our wizard rules also list
   `SAVE_CONFIG` as never-from-a-button. So **the wizard reads the numbers from the console result and keeps them itself** (below).
2. **Klipper can't change PID live.** There is no `SET_HEATER_PID` in mainline Klipper (only Kalico has PID profiles). A new PID takes a restart.
3. **One `[extruder]` section serves every print head** (`tools/3dp.cfg`); the bed is `[heater_bed]`. There is **no chamber heater in the base config**:
   `Chamber_Temp` is only a sensor. A chamber heater exists only if added with Add hardware (`heater_generic`, capped at 120 C). So one hotend PID
   per machine, not per head (a question below).
4. **Results the Rhino applies per head and material** are stored as save variables and applied at the start of a job (`_RHINO_APPLY_TUNING`, 1.9.17,
   with the Portal's `tuning.json` as the record). New wizards extend that, they don't invent a second place.
5. **There is no accelerometer, `[resonance_tester]`, `[input_shaper]` or `[firmware_retraction]` section** in the config today.
6. The drivers are **TMC2240 on X, Y and the extruder (software SPI), TMC2208 on Z, Z1, Z2 (UART)**. X and Y run always-stealthChop
   (`stealthchop_threshold: 999999`, `driver_TPFD: 0`); these are working values and stay as they are unless Mike says otherwise.

## One new piece shared by items 2, 4 and 5: a Portal-owned "tuned values" file

A generated, never hand-edited `myrhino/tuned.cfg` (written by the Portal from `tuning.json`, like `custom_tools.cfg` and `job_hooks.cfg`), included
**after** the others from `printer.cfg`. Klipper lets a later file override an earlier option, so it can carry `[extruder] pid_Kp…`, `[heater_bed] pid…`, a chamber heater
section's `pid…`, `[input_shaper]`, `[resonance_tester]` and `[firmware_retraction]` **without touching the tools files or using `SAVE_CONFIG`**. It is written atomically with a backup (`rhino/atomic.py`), parsed back the way
Klipper reads it before it is kept, and refused when anything is out of range. Needs: the one-line `[include myrhino/tuned.cfg]` added to `printer.cfg`
(a config change, applied with a `dev/proposal_tuned_cfg.py --apply` script in the same anchor-checked style as the hooks change, and **your OK first**).
Until the file has content it is empty and Klipper ignores it. A restart (`FIRMWARE_RESTART`, which the wizard offers and never does by itself) applies it.

## 1. Probe and bed-level check ("Probe check")

*Plain sentence:* "Is the probe repeatable enough to trust a bed mesh?"
- **Steps:** (1) Read: homed, a print head mounted, no job, probe type and offsets from Klipper. (2) Pick a spot (default: the middle of the bed, clear of the
  clamps). (3) Run `PROBE_ACCURACY` (10 samples) and show maximum, minimum, **range** and standard deviation in a sentence: under about 0.02 mm is good, under
  0.0125 is excellent, over 0.05 means "don't trust a mesh until this is fixed" (the thresholds are the outline's and Klipper's guidance; they are shown as guidance, not a pass or fail that blocks).
  (4) Optionally heat the bed to a chosen temperature and run it again: the difference is **thermal drift**, which cold-only tests hide. (5) Optionally
  read `Z_TILT_ADJUST`'s own report (how far the three Z corners differed, how many retries it took); it's already run at every print start, so this
  just shows the numbers.
- **Not included on purpose:** `PROBE_CALIBRATE` (probe z_offset). The Rhino sets nozzle height with the paper test per head and material; `PROBE_CALIBRATE`
  writes `z_offset` through `SAVE_CONFIG`, the conflict in fact 1, and could fight the per-head offsets.
- **Writes nothing.** Result saved only as a dated line in the tuning history ("probe range 0.008 mm on Nov 23, cold").
- **Risk:** the head moves to the spot and the probe lowers a few mm at it: low. Z-only probing, hand near Stop. *Stop if* the probe doesn't stop at the bed or the
  numbers jump around by more than 0.1 mm.

## 2. Heater tuning ("Tune a heater"): hotend, bed and chamber

*Plain sentence:* "Teach the heater how much power it needs so the temperature stays steady."
- **Which heaters:** found by asking Klipper (`extruder`, `heater_bed`, and any `heater_generic`, which is how a **heated chamber** appears). A chamber is listed only when its heater
  exists; if the machine has only the `Chamber_Temp` sensor the wizard says so and points to Add hardware.
- **Steps:** (1) Read: current PID values, current temperature, `control:` type, the heater's own limit. A heater using `control: watermark` (some chamber heaters)
  can't be PID-tuned: the wizard says that, and doesn't change the control type. (2) Pick the **target** (suggested from the material and the heater: for the hotend the
  usual print temperature; the bed the most used bed temperature; the chamber the temperature the person wants to hold, e.g. 45 C), clamped to the heater's limit and
  `HEATER_MAX_TEMP`. For the hotend the **part fan is switched on** as the outline says, because the fan is on while printing. (3) Safety line: "the heater will run on its own for N minutes; stay nearby; Stop cuts it".
  (4) Run `PID_CALIBRATE HEATER=<name> TARGET=<temp>` and follow it live (temperature graph from the existing dashboard). (5) Read the line `PID parameters: pid_Kp=… pid_Ki=… pid_Kd=…`
  from the console, show **old and new side by side**, and explain which way each number moves. (6) **Keep it** writes them into `myrhino/tuned.cfg`
  (fact 1) and offers the restart; **Discard** forgets them. `SAVE_CONFIG` is never sent: Klipper only holds the new values in memory until the next restart, so a Discard needs nothing else.
- **Chamber specifics (Mike's request):** a chamber is slow and loses heat to the room, so (a) the wizard says it takes **20 to 60 minutes**, (b) it asks for the door closed and any chamber
  fan or vent set the way a print uses them, (c) it starts only if the chamber is within a few degrees of the room (it reads `Chamber_Temp`), (d) the target is capped at the chamber heater's
  limit (120 C today), and (e) it asks whether the bed is allowed to be on (a hot bed warms the chamber and changes the result). Klipper's tuner runs at a fixed
  target and ends after the cycles it needs; for a very slow chamber it can time out, and the wizard then says "the chamber is too slow for the automatic tune; see below" and offers a
  hand-set conservative PID (documented values) rather than guessing.
- **Hardware safety unchanged:** `[verify_heater]` (thermal runaway) stays on and is not touched; the wizard never raises a heater beyond its own `max_temp` or turns off a safety.
  If Klipper stops with a thermal error, the wizard shows the error and the Firmware restart guidance, and keeps nothing.
- **Per head?** The hotend PID is per machine (fact 3). If SwitchFly and BlockOne heat through different cartridges, a second set could matter; Klipper can't switch them live, so I'd show a note and
  **not** try a per-head PID. (Question 3.)
- **Risk:** heater on unattended: the same as any print, plus a long chamber run. *Stop if* the temperature doesn't rise within the time Klipper expects, or passes the target by more than 20 C.

## 3. Motor, endstop and driver check ("Check the motors")

*Plain sentence:* "Are the motors, switches and drivers all answering?" **Read-mostly, the safest of the wizards.**
- **Switches:** `QUERY_ENDSTOPS`, then a live view of each endstop and the probe (read from Klipper's `query_endstops` object) while the person presses each switch by hand:
  the row turns "triggered" and the wizard ticks it. Nothing moves.
- **Drivers:** for every driver Klipper knows (the six steppers and the extruder, TMC2240 and TMC2208), read `drv_status` and the temperature that Klipper exposes and show: overtemperature
  warning or shutdown, short to ground or supply, open load, and the run and hold current in amps. Plain sentences per flag ("this driver is hot: check the fan"). The full register text (`DUMP_TMC`) is in "What this does".
  A flag that is expected is explained, not hidden (for example "open load" when a motor is unplugged).
- **Motors:** `STEPPER_BUZZ STEPPER=<name>` per motor (it moves one motor 1 mm and back ten times). Before it the wizard lowers the bed 10 mm and moves the head to the middle (Z first) so nothing
  can touch; it runs one motor at a time, the person confirms "moved, and the right way" or "no/wrong", and the answer is shown per motor. (A wrong direction or a silent motor is the point of the test.)
- **Writes nothing.** Result is a dated summary. **Risk:** low (1 mm moves). *Stop if* a motor moves more than about 1 mm, grinds, or the Z axis moves the wrong way far enough to touch.
- The same read-only driver report is a good addition to the existing health check (Settings > Health check): a "drivers" section.

## 4. Retraction and temperature ("Material tower")

*Plain sentence:* "Find the lowest temperature that still prints cleanly, then the smallest retraction that stops stringing."
- **Temperature tower:** Studio makes the tower G-code itself (the way the pressure-advance and extrusion wizards already generate their test prints), changing the temperature with
  `TUNING_TOWER COMMAND=M104 PARAMETER=S START=… FACTOR=…` as it climbs. The person picks the best band in a picture; the result is stored per material (and head if the person wants) in `tuning.json`,
  and offered as the print temperature in Studio's slice profile. Order: temperature before pressure advance, because heat changes PA (the outline says so too).
- **Retraction test:** a stringing tower with `SET_RETRACTION RETRACT_LENGTH=…` stepped by `TUNING_TOWER`, which needs Klipper's `[firmware_retraction]` section: added to
  `myrhino/tuned.cfg` with `retract_length: 0` (does nothing unless a test uses it). The test G-code uses G10/G11. The person picks the cleanest height; the wizard stores length and speed per head and
  material. A second pass finds the retract speed.
- **Where the result goes:** Studio's own slicing and the slice profiles keep using their slicer retraction; the wizard saves the tuned length and speed into the profile defaults
  for that head and material (they already hold retraction, extrusion multiplier and max flow). **Firmware retraction is not turned on for ordinary jobs.**
- **Writes:** `tuned.cfg` (the `[firmware_retraction]` section, once) and `tuning.json`. **Risk:** a print, hot: the standard print-start checks apply. *Stop if* the first layer doesn't stick.

## 5. Per-head results ("Tuning results" page, not a wizard)

The outline's section 9 point: each head weighs something different. A single page lists, per print head: rotation distance, pressure advance per material and nozzle (the
existing values), temperature, retraction, and, once item 6 exists, input shaping; with dates and a "re-run" button per row. Storage: the existing save variables
(`rhino_<thing>_<head>…`) and `tuning.json`, applied by the existing `_RHINO_APPLY_TUNING` at job start. New value kinds are added to that macro **as a separate Klipper macro change with its own write-up** (what runs,
in what order, what can go wrong) before they are applied; this proposal doesn't change it.

## 6. Input shaping with the USB ADXL345 ("Shake the machine")

*Plain sentence:* "Measure how the machine rings, and pick the setting that removes it."
**The one that most improves print quality, and the one that needs the most care.**
- **Hardware (needs Mike's answers):** a USB ADXL345 is normally a small board running Klipper's firmware (RP2040), seen by Klipper as a second MCU. The config needs
  `[mcu adxl]` (`serial: /dev/serial/by-id/usb-Klipper_rp2040_…`), `[adxl345]` (`cs_pin: adxl:gpio…`, `spi_bus: spi0a`, `axes_map`) and `[resonance_tester]`
  (`accel_chip: adxl345`, `probe_points` at the middle of the bed). The wizard **detects** whether these exist and shows the exact lines to add (editable, written to `tuned.cfg` after your OK, never
  to `printer.cfg`). Which board and where the cable runs are in the questions.
- **Steps:** (1) Read: homed, which head is mounted, whether the accelerometer answers. (2) `ACCELEROMETER_QUERY` (shows live X, Y and Z, about 1 g down; a plain "it works" or "not answering: check the cable, the serial name").
  (3) `MEASURE_AXES_NOISE` (a quiet machine is below a few units; a high number means a loose mount or a nearby fan; the wizard says what to fix). (4) **Slow first run:** a short low-force sweep
  (`TEST_RESONANCES AXIS=X`/`Y` with a small `ACCEL_PER_HZ` and a narrow range) so the person hears and sees it is gentle. (5) The real runs: `SHAPER_CALIBRATE AXIS=X`, then `Y` (each takes about a minute).
  (6) **Show** per axis the fitted shapers (MZV, EI, 2HUMP_EI, 3HUMP_EI, ZV), their frequency, remaining vibration and smoothing, the one Klipper recommends, and the **maximum acceleration** each allows;
  the Rhino plots the response curve and the shaper curves itself (see below), so no Shake&Tune install is needed. (7) The person picks (default: Klipper's recommendation), **Keep it** writes
  `[input_shaper]` (type and frequency per axis) into `tuned.cfg` for the **head that was mounted**, and optionally the recommended `max_accel`.
- **Per head (Mike's section 9):** every head changes the moving mass, so the answer differs. The wizard records the result against the mounted head; at a tool change or job start
  `SET_INPUT_SHAPER SHAPER_TYPE_X=… SHAPER_FREQ_X=…` for that head is run. That is **a Klipper macro change** (in `_RHINO_APPLY_TUNING` or the swap path), written up separately before it is applied. The `[input_shaper]` section itself holds a safe
  default (the last measured head, or none) so a head with no result is never worse than today.
- **Showing the curves:** `SHAPER_CALIBRATE` writes its raw data as CSV in `/tmp` on the Rhino, outside Moonraker's file roots. A small **read-only** Portal route returns only
  files named like Klipper's (`/tmp/calibration_data_*.csv`, `/tmp/resonances_*.csv`), nothing else, size-limited; Studio draws the chart. (Shake&Tune's belt comparison and vibration map are
  extras that need its plugin installed; they are left out of the first release. Whether the Rhino is a CoreXY-style gantry decides if the belt comparison even applies.)
- **Mounting:** the accelerometer must be rigidly fixed. For X and Y shaping on a machine whose XY gantry carries the head, it goes on the **carriage or the head**; with several heads, the practical choice is a mount on the carriage plate
  (so every head is measured the same way) or on each head (so each head carries its own). The wizard asks which, and says what it will measure.
- **Risk (the highest here):** it shakes the whole machine at up to several hundred hertz and the toolhead dock and tool lock are loaded. Checks before: head mounted **and locked**, homed, bed
  clear, nothing loose on the bed, the umbilical (cable bundle) free to move; hand on Stop; the first run is the gentle one; the wizard can end the test early. *Stop if* anything rattles loose, the head unlocks, or a cable
  catches.

## 7. TMC driver tuning: my opinion (Mike asked)

**Split it in two. The reading half is a good candidate; the writing half isn't, at least not yet.**
- **Good, and already inside item 3:** a driver *check*: read each driver's status, temperature and current, in plain words, and show them in the health check. Safe, useful for support ("send me your driver report"), and it makes
  newcomers aware that a motor can overheat.
- **A tuning wizard that writes driver registers: not recommended now.**
  1. The two community tools (`klipper_tmc_autotune`, `chopper-resonance-tuner`) are **third-party plugins** that must be installed and kept current, and that write **the same registers**: only one may run per motor. Klipper's developers also don't support a "dirty" install that has them.
  2. They change **working machine values**: currents, chopper timing, stealthChop. Our rule is never to change those without being asked, and a wrong value can overheat a driver or lose steps on a gantry head.
  3. The effect is **subtle** (noise, a little heat, a little vibration), so a wrong choice isn't obvious to the person; there's no pass or fail picture like a tower print has.
  4. The Rhino's drivers are a **mix** (2240 SPI and 2208 UART) with different registers, and the X/Y settings are deliberate.
- **If you want it later:** the one that fits our method is the **chopper tuner, which uses the accelerometer** you now have. It becomes an *expert* wizard after item 6 works: one motor at a time, a dry run, a hard temperature
  watch, nothing kept until you press Keep, results stored as `driver_*` lines in `tuned.cfg` (so the original files are untouched), with a **"Put back what I had"** button. `klipper_tmc_autotune`'s plugin install I would leave out.
- Live experiments are already safe in the Console (`SET_TMC_CURRENT`, `SET_TMC_FIELD` change a value until the next restart); the wizard doesn't need to wrap them.

## Order I suggest

1. Probe check (item 1): read-mostly, quick, a good first one to build the shared "run a command, read the result, show it" step.
2. Motor, endstop and driver check (item 3): read-only; adds the health-check driver section.
3. Tune a heater (item 2), including the chamber: needs `tuned.cfg` (your OK for the include line).
4. Input shaping with the ADXL345 (item 6): needs your answers below, `tuned.cfg`, the read-only CSV route, and a macro change write-up for per-head apply.
5. Material tower (item 4), then the results page (item 5).

## Questions for Mike

1. **`myrhino/tuned.cfg` and the one include line in `printer.cfg`:** OK? (It is the only way to keep PID and shaper values without `SAVE_CONFIG` conflicts.)
2. **Chamber:** does a chamber heater exist yet (what is it: a PTC, a bed-style pad, a heat gun)? Is it `heater_generic` in Klipper, with `control: pid`? Max temperature you want?
3. **Hotends:** do BlockOne and SwitchFly use the same heater cartridge and sensor on the umbilical (one PID for both) or different parts?
4. **The USB ADXL345:** which board (model, and does it run Klipper's firmware on an RP2040, or is it a USB-to-SPI board that needs a different config)? Where will it be mounted (carriage plate, or on a head), and how long is its cable?
5. **Which Z moves are safe for the motor test?** (I plan: lower the bed 10 mm first, then 1 mm each way.) Anything on your bed or umbilical that should change this?
6. **Firmware retraction:** OK to add an inactive `[firmware_retraction]` (retract_length 0) section just for the retraction test?
7. **Order and priority:** anything above you want first or dropped (for example, skip the chamber run until the chamber exists)?

## Checks, when built (each with a pass condition and *Stop if*, in `rhino-studio/docs/testing.md`)

PC (probe check): a repeatable range under 0.02 mm; two runs within 0.01 mm of each other. HM (motors): each motor buzzes and the answers are recorded; a pressed endstop shows triggered. DR (drivers): no flags on a healthy machine, and an unplugged motor's flag is explained. HT (heaters): a tuned hotend holds
its target within 1 C for 5 minutes; the bed within 1 C; the chamber within 2 C; the new values survive a restart and "Put back" restores the old ones. SH (shaping): `ACCELEROMETER_QUERY` shows about 1 g on Z; a
test print or the existing tower shows less ringing with the chosen shaper than with none; a different head gets its own result. MT (material tower): the chosen temperature and retraction print a cleaner part than the old values.
Each wizard's G-code is shown and editable, and a refused line is shown with its reason.