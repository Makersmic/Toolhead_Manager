# Add system hardware: full Klipper coverage (design draft)

Status: draft for Mike's OK. No code until approved.

## Goal

Every piece of hardware Klipper can put on a pin can be added from **Settings › System hardware › Add**,
with sensible defaults, limits and plain-language options. Durability filter: anything added here must be
safe to leave alone for months (sane `shutdown_value`, heaters off on idle, nothing that can run unattended).

Source of truth: Klipper `docs/Config_Reference.md` (master, Oct 2026). Before building, re-check the
installed Klipper version on the 7050 and hide any section it doesn't know.

## Today

Six roles, all built on `clean_control`: switch / level (`output_pin`), fan (`fan_generic`),
heater fan (`heater_fan`), servo (`servo`), input (`gcode_button`).
`controller_fan` was started last session and lost; it is redone here.

## Proposed menu (8 groups)

| Group | Klipper sections | Notes |
|---|---|---|
| **Switches and power** | `output_pin` (switch / level), `pwm_tool`, `static_digital_output` | `pwm_tool` for anything that needs a PWM change in step with moves (laser-style). Static = fixed at boot, no control. |
| **Fans** | `fan_generic`, `heater_fan`, `controller_fan` *(new)*, `temperature_fan` *(new)* | Controller fan: "Run it while the motors are on". Temperature fan: "Hold a temperature" (enclosure, electronics bay). |
| **Heat and temperature** | `heater_generic` *(new)*, `temperature_sensor` *(new)*, custom `thermistor` / `adc_temperature` *(new, sub-form)* | Sensor types incl. host (the 7050's CPU), MCU, and `temperature_combined`. |
| **Lights** | `led`, `neopixel`, `dotstar`, `pca9533`, `pca9632` *(all new)* | Low risk. Colour order + chain count for addressable. |
| **Buttons and sensors** | `gcode_button`, `filament_switch_sensor`, `filament_motion_sensor` *(new)*, `hall_filament_width_sensor`, `tsl1401cl_filament_width_sensor` *(new)* | See safety below. |
| **Movement** | `servo`, `manual_stepper` *(new)* | Manual stepper: one extra motor (gate, feeder, rotary). |
| **Measuring** | `adxl345`, `lis2dw`, `lis3dh`, `mpu9250`, `icm20948`, `bmi160` + `resonance_tester` *(new)*, `angle`, `load_cell` | Accelerometer gets a "used for input shaper" link. Load cell is advanced. |
| **Advanced** | `multi_pin`, `duplicate_pin_override`, `adc_scaled`, `sx1509`, `ads1x1x`, digipots (`ad5206`, `mcp4451`, `mcp4728`, `mcp4018`), `samd_sercom`, extra `[mcu name]` board | Guided forms, shorter help. Second board unlocks its pins everywhere else. |

The list is short labels with the Klipper name in small text under each (lists rule).

## Not in this menu (owned elsewhere)

- **Machine core** (base config / Portal): `printer`, `stepper_*`, `extruder*`, `heater_bed`, `fan` (part cooling, per print head), `probe`/`bltouch`/eddy, `tmc*`, main `[mcu]`, homing, bed mesh, leveling.
- **Macros**: `gcode_macro`, `delayed_gcode` → macro builder phase.
- **Features, not hardware**: `firmware_retraction`, `exclude_object`, `input_shaper` values, `idle_timeout`, `virtual_sdcard`, `display` + menus.
- **Retired / not ours**: `replicape`, `palette2`, `static_pwm_clock`, `endstop_phase`.

## Safety rules for the new types

- **heater_generic**: needs a sensor; `max_temp` capped (proposed 120 °C unless Mike raises it); `min_temp` 0; `verify_heater` always written; watermark control by default, PID only after a PID run. Shown on the Dashboard; "Turn off heaters" and idle timeout cover it (Klipper includes generic heaters). Never on an umbilical pin.
- **temperature_fan**: `max_temp` is a shutdown limit in Klipper, so the form says so and defaults it 10 °C above target.
- **Filament sensors**: `pause_on_runout` only while a print head is mounted. Tool swaps send `SET_FILAMENT_SENSOR ENABLE=0/1`, so a laser or spindle job is never paused by an empty filament path.
- **Buttons**: the existing "Emergency stop (M112)" action stays, but the help text says plainly it is **not** a hardware E-stop (it waits in Klipper's queue behind the current command). A real E-stop must cut power.
- **Switches / pwm_tool**: `shutdown_value` defaults to off and can't be set to on for anything marked as a pump, laser, heater or spindle.
- **controller_fan**: defaults to `idle_timeout: 30`, `stepper` = all, and also on when any heater is hot.
- **manual_stepper**: no homing unless an endstop pin is given; speed and accel capped.

## Build order (once approved)

1. Framework: role table becomes data (group, section, fields, limits, `hardware_only`), so new types are rows, not code.
2. Fans + heat (most safety weight), with tests.
3. Lights, buttons and sensors, movement.
4. Measuring, advanced.
5. Studio: grouped picker, per-type fields, role picker hides `hardware_only` roles for tool controls.

Each step: TM tests + Studio unit tests + one screenshot round.

## Questions for Mike

1. Menu groups and the out-of-scope list OK?
2. `heater_generic` cap: 120 °C OK, or what do you actually plan to heat?
3. Advanced group: guided forms (lean), or a raw "paste a Klipper section" box? Lean is no raw box, since it bypasses every check.
4. Second `[mcu]` board: in this job, or later?
