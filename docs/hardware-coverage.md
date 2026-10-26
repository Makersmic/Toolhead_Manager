# Add hardware wizard: any Klipper hardware, any machine (design draft v2)

Status: **approved Oct 26** (answers in `decisions.md`). Replaces v1 (inventory only).

## Goal

Someone with a different machine, like a Klipper CNC router, a diode laser or a printer with an enclosure, can add
every piece of hardware it has from one guided wizard. They answer what it is, how it's wired, what it follows and
where it shows. Rhino then writes valid, safe Klipper config.

Durability filter: whatever this wizard writes must be safe to leave alone for months. That means outputs default
off at shutdown, heaters are covered by idle timeout, nothing runs unattended, and every job-end path turns it off.

Answers: guided forms only; job hooks in the macros; interlocks on by default for laser and spindle; heater cap 120 °C; a second board is in this job (Mike, Oct 25–26).

## The model: five questions

The 6 roles we have today stay as they are. Each item the wizard adds is defined by five answers, and each answer
is data in one table rather than code.

| # | Question | What it decides |
|---|---|---|
| 1 | **What is it?** (device) | Klipper section, default values, safety rules |
| 2 | **How is it wired?** (pins) | Which pins can be picked, pull-up/invert, electrical warnings |
| 3 | **What machine or tools is it for?** (scope) | Additive / Subtractive / Passive / Whole machine, or named tools |
| 4 | **What does it follow?** (relationships) | When it turns on and off by itself, and what it blocks |
| 5 | **Where does it show?** (exposure) | Control tab group, Dashboard, Care hours, job hooks, generated ON/OFF macros |

### 1. Devices (what it is), grouped by what people call them

| Group | Devices (wizard label → Klipper section) |
|---|---|
| **Power and switching** | Relay or contactor → `output_pin`; Dimmer / PWM level → `output_pin`; Laser or other move-synced power → `pwm_tool`; Fixed at boot → `static_digital_output` |
| **Spindles** *(new group)* | Spindle on a relay → `output_pin`; Spindle speed by PWM (or PWM→0-10 V for a VFD) → `pwm_tool` + optional direction pin; VFD fault input → `gcode_button` |
| **Coolant, air and dust** *(new group)* | Mist / flood coolant (M7/M8/M9), air assist, dust collector, vacuum table, exhaust. All are relays or PWM, each with a "follows" rule |
| **Fans** | Fan by speed → `fan_generic`; Hotend fan → `heater_fan`; Electronics / driver fan → `controller_fan`; Hold a temperature → `temperature_fan` |
| **Heat and temperature** | Chamber / enclosure / generic heater → `heater_generic`; Temperature readout → `temperature_sensor`; Custom thermistor → `thermistor` / `adc_temperature` |
| **Lights** | Plain LED (1–4 channels) → `led`; Addressable → `neopixel` / `dotstar`; I2C LED chips → `pca9533` / `pca9632` |
| **Switches and sensors** | Button / pedal → `gcode_button`; Door or lid interlock; Flame sensor; Pressure or flow switch; Filament runout → `filament_switch_sensor`; Filament jam → `filament_motion_sensor`; Filament width → hall / tsl1401cl |
| **Movement** | Servo → `servo`; Extra motor (gate, feeder, rotary) → `manual_stepper` |
| **Measuring** | Accelerometer → `adxl345` / `lis2dw` / `lis3dh` / `mpu9250` / `icm20948` / `bmi160` + `resonance_tester`; Angle sensor → `angle`; Load cell → `load_cell`; Analog input → `adc_scaled` / `ads1x1x` |
| **Advanced** | `multi_pin`, `duplicate_pin_override`, `sx1509`, digipots (`ad5206`, `mcp4451`, `mcp4728`, `mcp4018`), `samd_sercom`, a second board `[mcu name]` |

"Interlock", "flame sensor" and "flow switch" are all `gcode_button` under the hood. The wizard labels them by
purpose so it can apply the right safety defaults (section 4).

**Not in the wizard** (owned elsewhere): `printer`, `stepper_*`, homing endstops, `extruder*`, `heater_bed`, the part
cooling `fan`, `probe` / `bltouch` / eddy, `tmc*`, the main `[mcu]`, bed mesh and leveling (base config and Portal);
`gcode_macro` / `delayed_gcode` (macro builder phase); `display` and menus; `replicape`, `palette2`,
`static_pwm_clock`, `endstop_phase` (retired or not ours).

### 2. Pins: sensor types and their requirements

Each device declares **what kind of pin it needs**. The pin picker then shows only free pins that can do it, using the
Board pins table we already have (Type, Contact, Idle). The user picks the **sensor type**, not pull-ups or `!`
flags; the wizard writes those.

| Pin kind | Typical devices | What the wizard asks / writes |
|---|---|---|
| **Digital in** | Switches, buttons, interlocks | Contact type (see below) → `^` and `!` written for you |
| **Digital out** | Relays, plain on/off | "Relay module turns on when the pin is LOW?" (many cheap modules do) → `!` |
| **PWM out** | Fans, dimmers, lasers, spindle speed | Frequency preset by device (fan 10 ms, laser/spindle per driver); MOSFET header vs logic pin |
| **Analog (ADC)** | Thermistors, analog pressure, pots | Only ADC-capable pins; thermistor type + pull-up resistor value |
| **SPI** | MAX31865 (PT100/PT1000), MAX31855/6675/31856 (thermocouple), accelerometers | Bus + one free CS pin |
| **I2C** | BME280, SHT3x, AHT10, LM75, PCA LED chips, some accelerometers | Bus + address |
| **One data line** | Neopixel | 1 pin; warns that 5 V strips may need a level shifter |
| **Data + clock** | Dotstar | 2 pins |
| **Step / dir / enable** | `manual_stepper` | 3 pins + a driver slot |
| **Tach in** | 3- and 4-wire fans | Optional second pin with a pull-up |

**Switch and sensor types**:

| Type | Wires | Signal | Wizard writes / warns |
|---|---|---|---|
| Mechanical, normally closed (**recommended**) | 2 | to GND | `^pin`. A broken wire reads as triggered, which fails safe. |
| Mechanical, normally open | 2 | to GND | `^!pin`, with a note that a broken wire is invisible |
| Optical (slotted) | 3 (5 V, GND, S) | 3.3–5 V | Polarity choice; warns if the pin isn't 5 V tolerant |
| Inductive / capacitive **NPN** | 3 | open collector to GND | `^` pull-up; NO/NC sets `!`. **Warns: these run on 6–36 V. Check the signal isn't at supply voltage.** |
| Inductive / capacitive **PNP** | 3 | outputs supply voltage | **Refuses a direct pin.** Needs an optocoupler or divider; the wizard says so and asks to confirm one is fitted |
| Hall effect (A3144-style) | 3 | open collector | `^pin`, active-low |
| Sensorless (TMC DIAG) | — | virtual | Homing only, so it's out of scope (core) |
| Thermistor | 2 | ADC | Type list (NTC 100K 3950, ATC Semitec 104GT/104NT, PT1000 direct…) |
| PT100 / PT1000 amp | SPI | — | MAX31865 + wire count (2/3/4) + ref resistor |
| Thermocouple | SPI | — | MAX31855 / MAX6675 / MAX31856 + type |
| DS18B20 | 1-wire | — | Needs the host as a Klipper MCU (the 7050 can be); asks before adding that |
| Host / MCU temperature | — | — | No pin; the 7050's CPU temperature for free |

### 3. Scope: which machine or tools it's for

This uses the existing Additive / Subtractive / Passive base, plus **Whole machine**:

- **Whole machine**: always available (case light, controller fan, enclosure heater).
- **A category**: active only while a tool of that category is mounted (dust collector → Subtractive).
- **Named tools**: active only with those tools (air assist → the laser kinds; vacuum with the sander, as now).

Tool swaps (`SWAP_TOOL` → `_TOOL_SAFE_OFF`) turn off anything whose scope no longer matches. Filament sensors are
disabled with `SET_FILAMENT_SENSOR` when no print head is mounted, so a laser job is never paused for "runout".

### 4. Relationships: what it follows

One rule per item, picked from a list. Each maps to config or to one of our existing macro hooks.

| Follows | Example | How |
|---|---|---|
| **Nothing (manual)** | Work light | Control tab only |
| **A heater** | Hotend fan | `heater_fan` |
| **The motors** | Driver fan | `controller_fan` (`idle_timeout`, steppers, heaters) |
| **A temperature** | Enclosure exhaust | `temperature_fan` |
| **Another output** | Dust collector with spindle; air assist with laser | Turns on with it, off after a **run-on delay** (default 10 s) |
| **The job** | Exhaust, vacuum table, mist | Job hooks (section 6), with run-on |
| **G-code** | Coolant M7/M8/M9 | Generated `M7`/`M8`/`M9` macros, only if not already defined |

Inputs get an **action**, and the purpose label sets a safe default:

| Purpose | Default action | Extra rule |
|---|---|---|
| Button / pedal | Run a command | — |
| **Door / lid interlock** | **Pause** if opened during a job | **"Must be closed to start"**: checked at `START_JOB` / `*_JOB_SETUP`; laser won't fire, spindle won't start |
| **Flame sensor** | **Emergency stop** | Laser jobs can't start without it if Mike marks it required |
| Pressure / flow switch (air, coolant) | Pause | Optional "must be OK to start" |
| VFD fault | Emergency stop | — |
| Filament runout / jam | Pause (print head only) | Off when no print head is mounted |

**Honest limits** (shown in help text, not hidden):

- An "Emergency stop" input is **not** a hardware E-stop: it waits in Klipper's queue. A real E-stop must cut motor and
  spindle/laser power.
- Klipper allows **one `[probe]`**. A CNC tool-length setter or touch plate can't be a second probe. Options to
  decide at build time: use the existing probe slot when the CNC kind is mounted, or a homing-style move to an input.
  This needs its own short design doc; it isn't in this job.
- Spindle **speed feedback** has no clean Klipper section. Fault input yes; RPM readout no.
- Modbus VFD control isn't Klipper-native, so it's out of scope.

### 5. Exposure: where it shows

Checkboxes, with defaults set by the device:

- **Control tab**, in the group for its scope (print head controls with print heads, spindle extras with CNC).
  Switches/levels behind the same `PadLock` rule when they're live-dangerous (spindle, laser, heater).
- **Dashboard** (temperatures, interlock state).
- **Care**: count running hours for maintenance (spindle, dust bag, fan).
- **Generated macros**: `<NAME>_ON` / `<NAME>_OFF` (exists today).
- **Job hooks** (next section).

### 6. Job hooks: before/after the Rhino's own sequences

Mike asked for start/end G-code with the choice of before or after the Rhino's start. **My lean: hooks live in the
Portal and run from the macros, not from the Kiri file.** Kiri's own start/end stays empty by design. The reasons:

- Hooks then run for **every** job: Kiri, PrusaSlicer, Orca, or a file from someone else.
- Files already sliced pick up a changed hook without re-slicing.
- Cancel and pause paths can run the matching "off" hook, and a file can't do that.

Per scope (whole machine / category / tool kind), five slots, each a short list of lines or a hardware action
("Dust collector ON"):

| Slot | Runs | Inside |
|---|---|---|
| Before start | before homing / heating | `START_JOB` and `*_JOB_SETUP`, first line |
| After start | after the Rhino's start sequence, just before the first job move | same macros, last line |
| Before end | before parking / power off | `END_PRINT`, first line |
| After end | after the Rhino's end sequence | `END_PRINT`, last line |
| On cancel / pause | when stopped early | `_RHINO_CANCEL`, `_RHINO_PAUSE_HOOK` (+ resume: `_RHINO_RESUME_HOOK`) |

**Macro change, as required before touching macros**:

- What runs: each macro gets one call, `_RHINO_HOOKS SLOT=<slot> TOOL=<kind>`, which runs the lines saved for that
  slot and scope. Nothing else in the macros changes.
- Order: before-start → Rhino start → after-start → job → before-end → Rhino end → after-end.
- What can go wrong, and the guard for each:
  - A "before start" hook moves an axis before homing. **Refused**: the editor blocks G0/G1/G28 in before-start.
  - A hook calls a missing macro, so the job aborts at start. Checked on save against the known macro list.
  - An "on" hook isn't matched by an "off". The editor shows which hardware turned on with no off, and **cancel always
    turns off everything a hook turned on**, whatever the user wrote.
  - A hook sets a heater. Allowed only within that heater's limits.
- Storage: `config/myrhino/job_hooks.json`, versioned with rev and history like slice profiles, and in the backup.

The editor lives in Settings › Job hooks, with a short link from Prepare ("Runs before/after this tool's start").
The Rhino's own sequence is shown greyed between the slots so the order is visible.

## The wizard

Five steps, one question each, matching the model: **What is it → Wiring → For which tools → Follows → Shows**, plus
a preview of the Klipper section before saving (exists today).

**Graphics (final, approved by Mike Oct 26):** only this wizard gets the mascot. It is not used in Add a toolhead
or anywhere else. The mascot is an original Rhino Studio rhino: slate blue, yellow hard hat, safety glasses. It's drawn
in a soft 1980s-cartoon style with a hand-drawn look: pressure-varying pencil line, grainy fill, front and
three-quarter views with shading. One pose per step panel, beside the question, each with a speech bubble of odd tech glyphs:

| Step | File | Pose | Bubble |
|---|---|---|---|
| What is it | `rhino-what.svg` | Three-quarter, holding a stepper motor up | ? · resistor · gear |
| Wiring | `rhino-wiring.svg` | Front, a connector in each paw | switch · bolt · ground |
| For which tools | `rhino-tools.svg` | Three-quarter, pointing | drill bit · laser · chip |
| Follows | `rhino-follows.svg` | Three-quarter (left), paw at chin | thought: ○ → □ |
| Shows | `rhino-shows.svg` | Three-quarter, waving | bars · sine · spiral |
| Done | `rhino-done.svg` | Front, thumbs up | ✓ · spark · gear |

Files live in `rhino-studio/src/assets/wizard/` and come from `scripts/wizard_poses.py`. Change a pose there, never
by hand-editing an SVG. Checked in light and dark. Everything else keeps the Rhino Studio theme.
The other looks tried on Oct 25 (anime eyes, work jacket) are in git history.

## Build order (once approved)

1. Framework: devices, pin kinds and sensor types as data tables in `presets.py`; one `clean_item` path.
2. Pin picker filtered by pin kind, with electrical warnings. **Second board** here: add a board, then its pins appear in the picker.
3. Fans + heat + interlocks (most safety weight), with tests. Includes redoing `controller_fan`.
4. Job hooks: `_RHINO_HOOKS`, `job_hooks.json`, editor, cancel-turns-off guard. Macro diff shown to Mike first.
5. Spindles, coolant/air/dust, lights, switches and sensors, movement.
6. Measuring, advanced.
7. Studio wizard with mascot; role picker hides `hardware_only` roles for tool controls.

Each step: TM tests + Studio unit tests + one screenshot round. Likely 3–4 sessions.

## Questions for Mike

1. **Job hooks in the macros (lean), or in the sliced file?**
2. `heater_generic` cap: 120 °C OK, or what will you heat?
3. **Second board now or later?** It matters for your CNC (more pins).
4. Tool setter / touch plate: a short design doc right after this job?
5. Interlocks: should "must be closed to start" be **on by default** for laser and spindle (lean: yes)?
