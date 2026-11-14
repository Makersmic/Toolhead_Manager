# Proposal: AS5600 filament encoder on the toolhead (`[filament_angle_sensor]`)

Nov 14 2026. **Draft: waiting on the FE1-FE6 readout** (`docs/testing.md`). Mike: "I want to use the sensor in the
picture" (an AS5600 magnetic angle board with a filament-driven magnet wheel, mounted above the BlockOne). Numbers
marked *(from the readout)* are filled in after FE2, FE5 and FE6; nothing here is built before Mike approves the
filled-in version.

## What changes, in one line

The toolhead gets a filament encoder that gives Klipper the filament's real travel in millimetres, so a print pauses
when the filament stops moving while the extruder keeps turning, and Studio can show measured against commanded
travel. Nothing changes for the laser, spindle or drag knife, and no existing macro changes.

## Why the AS5600 and not a pulse sensor

Stock Klipper's `filament_motion_sensor` only wants a pin that toggles; the AS5600 gives a 12-bit absolute angle
instead. That is a measurement (slip in percent, travel in mm), not a switch, and it is what Mike asked for. The
cost is one small custom Klipper module, which Tool Manager has never shipped before (see *Install* for how that is
kept reversible).

## Wiring

| Umbilical contact | Toolhead end | Board end |
|---|---|---|
| 14 (+12 V) and 13 (12 V GND) | 3.3 V regulator in → AS5600 VCC/GND | unchanged: the probe's 12 V rail |
| 17 (spare today) | AS5600 OUT, analog mode | EXP2 pin 3, `PB1` (analog-capable, no pull-up) |
| 19 | stays spare | — |

- 3.3 V, not 5 V, so OUT never exceeds the STM32's ADC range and no divider is needed. A linear regulator, not a
  buck, so nothing switches on the analog line.
- Not a thermistor header: the AS5600 datasheet rates the analog output for a 100 kΩ minimum load (10 kΩ in reduced
  range, 1 nF max); the T headers' 4.7 kΩ pull-up is below that. `PB1` on EXP2 has no pull-up and the LCD headers are
  unused on the Rhino. Build sheet: `docs/filament-encoder-wiring.pdf`.
- The signal is referenced to the 12 V supply's ground. The laser PWM and the SwitchFly servo already depend on the
  12 V and 24 V grounds being common; FE2 confirms it with a meter. *(from the readout: FE2 result.)*
- I2C over the umbilical was rejected: four wires against two spares, and an I2C read error shuts Klipper down
  mid-print. A noisy analog line only jitters.
- The readout block (`[adc_temperature as5600_angle]` + `[temperature_sensor filament_angle]`) is removed when the
  module's section goes in; both can't own `PB1`.

## The module: `filament_angle_sensor.py`

A Klipper extra (host-side Python, GPLv3 like Klipper, ~150 lines) kept in this repo at
`klipper_extras/filament_angle_sensor.py` with the licence header, and linked into `~/klipper/klippy/extras/`.

Config block, written by the Portal's add-hardware flow as a new catalog row `encoder` (type
`filament_angle_sensor`, sensors group, analog pin):

```
[filament_angle_sensor filament_encoder]
adc_pin: PB1
adc_voltage: 3.3
wheel_circumference: <mm, from FE6>
extruder: extruder
detection_length: <mm, see below>
report_time: 0.1
pause_on_runout: True
runout_gcode: <the same pause path hw_devices writes for the other filament sensors>
```

### What it does, in order

1. **Sample.** `mcu_adc.setup_adc_sample(report_time, 0.001, 8, minval=0, maxval=1, range_check_count=0)`: eight
   1 ms samples every `report_time`, no range shutdown (the angle is allowed anywhere in 0-100 %). *Check on the
   machine:* 0.1 s is below the 0.3 s Klipper's own sensors use; the MCU query slot should take it, and the fallback is
   0.2 s.
2. **Unwrap.** Each sample is an angle in turns (0-1). The difference to the previous sample is taken modulo 1 into
   -0.5..+0.5 and summed, so travel is continuous across the wrap. The direction sign is a config option
   (`invert: True`) in case the wheel runs backwards. Half a turn per sample is the limit: at 0.1 s and a
   *(from FE6)* mm wheel that is *(5 × circumference)* mm/s, above any retract speed Mike uses.
3. **Convert.** turns × `wheel_circumference` = measured mm. Kept as a running total since the last reset, plus a
   short window.
4. **Compare.** When the printer is printing (the `idle_timeout:printing` event, exactly as `filament_motion_sensor`
   does), the module records the extruder's commanded position each sample. If commanded travel grows by
   `detection_length` while measured travel grows by less than a quarter of it, that is a runout or jam: the
   standard `RunoutHelper` from `filament_switch_sensor` fires (`pause_on_runout`, `runout_gcode`,
   `SET_FILAMENT_SENSOR ENABLE=0/1`, `QUERY_FILAMENT_SENSOR` all work unchanged). Not printing: nothing is compared,
   nothing fires.
5. **Status.** `printer["filament_angle_sensor filament_encoder"]` adds `angle` (degrees), `measured_mm`,
   `commanded_mm`, `slip_pct` (over the last 50 mm commanded) and `wheel_circumference` to the helper's
   `enabled`/`filament_detected`.
6. **Calibrate.** `FILAMENT_ENCODER_CALIBRATE LENGTH=100`: zeroes the counters, extrudes `LENGTH` at 5 mm/s (through
   the normal `G1 E`, so the hotend must be at temperature), waits, then reports the circumference that would have
   made measured equal commanded and offers `SAVE_CONFIG` style persistence through `variables.cfg`
   (`SAVE_VARIABLE`), since the module reads an override from there at start. No hand edit of the user's cfg.

### `detection_length`

Jitter from FE5 sets the floor: ±3° on a *(FE6)* mm wheel is ±*(circumference × 3/360)* mm, far under a millimetre.
The default stays Klipper's 7 mm unless FE5 is worse than expected; retracts up to 8 mm don't trigger it because the
comparison is on commanded travel growing, which retract-then-unretract nets to zero.

### What can go wrong

| Failure | What happens | Why that is acceptable |
|---|---|---|
| Magnet lost or board unpowered | angle stuck; measured travel 0 while commanded grows | pause, like a real jam. The message names the sensor |
| Umbilical noise burst | one or two bad samples; unwrap sees a jump under half a turn | a few mm of false travel at most, never a false pause; a false "no travel" needs `detection_length` of stillness |
| Module file missing after a Klipper update | Klipper refuses to start: "Unknown config object" | `rhino.sh` and the Portal's Host health check the link and offer to relink; the section can be commented out to print without it |
| No print head mounted | `_RHINO_FILAMENT_SENSORS` disables it like the other sensors (new type added to its list) | a laser job never pauses for "runout" |
| Readout block left in | Klipper: pin `PB1` used twice | the Portal refuses to write the section while `PB1` is in use and says which section has it |

## Install and rollback

- `install.sh` and the updater copy `klipper_extras/*.py` to `~/rhino-manager/klipper_extras/` and symlink each into
  `~/klipper/klippy/extras/` (a link, so a Klipper `git pull` neither removes nor complains about it; Moonraker's
  update manager ignores untracked files). Done only when `~/klipper/klippy/extras/` exists; otherwise a Host health
  line says the module is not installed.
- Rollback: remove the symlink and the config section, `FIRMWARE_RESTART`. The readout block can go back in.
- Documented in `AGENTS.md` (new area: Klipper extras) and `docs/developer.md`.

## Studio (Mike, Nov 14: "add the Studio sections to the proposal")

Each item lands in a screen that exists. Order is the build order; items 1-2 ship with the module, the rest follow
with their own small review. No new no-confirm path: every control goes through the existing `check` / `approve` gate.

| # | Where | What | Readout or control |
|---|---|---|---|
| 1 | Control › Hardware panel (`src/control/HardwarePanel.vue`, which already lists filament sensors) | "Filament" row: measured and commanded travel for the current job, slip %, the sensor's enabled/paused state | readout |
| 2 | Dashboard status strip | one slip figure while printing; red only when the sensor has paused the job (red stays reserved) | readout |
| 3 | Tuning › Extruder calibration (`src/tuning/ExtruderCalWizard.vue`) | the wizard reads the real distance from the encoder beside the hand measurement and proposes the rotation distance; **Calibrate encoder** button runs `FILAMENT_ENCODER_CALIBRATE` through the usual confirm (print head mounted, hotend hot) | control |
| 4 | Print head tuning page | slip % at which a job pauses, stored with tuning; sensor on/off per print head through the existing `SET_FILAMENT_SENSOR` path, state shown | control |
| 5 | Care (`src/maintenance/`, meters) | "filament fed" meter per print head in metres, so nozzle and gear tasks can be scheduled on throughput, not hours | readout |
| 6 | Settings › Hardware | the encoder as a Portal catalog type (`encoder`), with a "turn the wheel, see the angle" check callable from Studio | both |

Not planned: a live slip graph during printing. It fails the durability test on its own; it rides along only if the
row in item 1 makes it nearly free.

## Tests

- `dev/test_filament_encoder.py`: the module against a fake ADC in the simulated Klipper: unwrap across the wrap in
  both directions, a noise burst, jam detection firing only while printing, `SET_FILAMENT_SENSOR ENABLE=0` silencing it,
  calibrate arithmetic, status fields.
- Portal: catalog row writes the section, refuses a busy pin, `_RHINO_FILAMENT_SENSORS` lists the new type.
- On the machine (`docs/testing.md`, to be added as FE7-FE12): module loads, live values in Studio, pull the filament
  out of the wheel during a test print → pause within `detection_length`, laser job with the sensor present never
  pauses, calibrate result matches FE6 within 5 %, relink after a simulated missing link.

## Decisions for Mike

1. Wiring as in the table (3.3 V regulator on 14/13, OUT on 17 → `PB1`). Approved Nov 14 in principle; confirmed by FE1-FE4.
2. Tool Manager ships a Klipper extra for the first time, as a symlink with a Host health check.
3. Calibration persists through `variables.cfg`, not a hand edit of the config.

---

# Stage 2: spindle tachometer (`[spindle_tachometer]`)

Nov 14 2026. Mike: "go with the 30 line extra … Hall at the bell rim is ok." Draft: waiting on the SP1-SP7 readout
(`docs/testing.md`; build sheet `docs/spindle-tachometer-wiring.pdf`).

## What changes, in one line

The HotJoe gets a hall switch fixed beside the motor bell, reading the rotor's own 14 magnets as 7 pulses per turn, so
Klipper knows the spindle's real RPM. The spindle driver (`[output_pin SPINDLE_SPEED]`, its 0.3 idle and shutdown
values, the relay) does not change.

## Hardware

| Item | Detail |
|---|---|
| Sensor | one unipolar hall switch, A3144 class (4.5-24 V, open-collector), or a latching US1881. A KY-003 module works only with its 10 kΩ pull-up to 5 V removed |
| Where | in a pocket of the printed motor mount, flat face toward the open rim of the bell, 1-2 mm from the magnet ends, at the magnet ring's radius. Nothing on the rotating side |
| Power | the ESC's BEC 5 V and GND on the servo lead (today "not connected"). Present only while the spindle rail is on; ground is the 24 V supply's, which is the board's |
| Signal | hall OUT → umbilical **contact 19** → **EXP2 pin 10 (`PC5`)** with the MCU's pull-up (`^PC5`). Open-collector, so the pin never sees 5 V. Not a STOP header: those may carry RC filters and driver DIAG jumpers |
| Rate | D2814 1000 KV on 24 V: ≤ 24,000 RPM = 400 turns/s × 7 = 2.8 kHz worst case; 1.4-2.1 kHz at cutting speeds |

Why the rotor magnets: an outrunner's bell is already a balanced 14-pole magnet ring. A magnet glued to the shaft or
cone would unbalance a 30,000 RPM spindle and can let go; an optical mark fails under chips and dust. The ESC
(Hobbywing Skywalker 80A UBEC) has no RPM or telemetry output.

## The module: `spindle_tachometer.py`

Klipper's counter is software-polled (`src/pulse_counter.c`: one GPIO read per `poll_ticks`, counting both edges), so
the poll interval must be well under half a pulse period: `0.0001` s gives ~1.8 samples per half-cycle at 24,000 RPM and
3-4 at cutting speeds. SP5/SP6 prove the rate and the MCU load on the machine.

```
[spindle_tachometer spindle]
pin: ^PC5
pulses_per_rev: 7
poll_interval: 0.0001
sample_time: 0.5
```

About 30 lines, kept in `klipper_extras/` beside the filament module and installed the same way:

```python
# Spindle tachometer: RPM from a pulse input, using Klipper's own pulse counter.
from . import pulse_counter

class SpindleTachometer:
    def __init__(self, config):
        printer = config.get_printer()
        pin = config.get('pin')
        self.ppr = config.getint('pulses_per_rev', 1, minval=1)
        poll = config.getfloat('poll_interval', 0.0001, above=0.)
        sample = config.getfloat('sample_time', 0.5, above=0.)
        self.counter = pulse_counter.FrequencyCounter(printer, pin, sample, poll)
    def get_status(self, eventtime):
        edges = self.counter.get_frequency()          # both edges, like the fan tachometer
        return {'rpm': edges * 30. / self.ppr, 'edges_per_second': edges}

def load_config_prefix(config):
    return SpindleTachometer(config)
```

`printer["spindle_tachometer spindle"].rpm` is then available to macros, the Portal and Studio. No commands, no
timers of its own, nothing it can do to the spindle.

## What consumes it (after the readout, each its own review)

1. `_CNC_WARMUP` reports RPM next to throttle; Studio's spindle panel and the CNC start wizard show it.
2. Tuning (`myrhino/tuning.json`) stores the RPM measured at the tuned throttle, so bits get feed per tooth from a
   measurement; the Portal's bits page shows RPM where it shows throttle.
3. Stall rule: during a CNC job, RPM under half the warm-up value for one second → pause and raise through the
   existing hooks. Only while the relay is on and the throttle is above idle; 0 RPM with the rail off is normal.

## Studio (Mike, Nov 14)

| # | Where | What | Readout or control |
|---|---|---|---|
| 1 | Control › spindle output cell and status strip (`src/control/OutputCell.vue`, `StatusStrip.vue`, which show throttle) | RPM beside throttle, live. The first thing to ship: throttle alone has been a guess | readout |
| 2 | Start wizard › warm-up (`src/views/StartWizardView.vue`) | RPM while it spins up; the ±5 % buttons show their effect in RPM | readout |
| 3 | Tuning › cut tests (`src/tuning/CutTuning.vue`, `CutTestWizard.vue`) | RPM recorded with each test and stored in `tuning.json` beside throttle | readout |
| 4 | Toolheads › Bits (`src/views/toolheads/BitsView.vue`) | feed per tooth and chip load from measured RPM; a bit's page shows "tuned at N RPM" | readout |
| 5 | Tuning | the stall rule's RPM floor and time-to-pause, per bit or material, shown and editable | control |
| 6 | Care | spindle run-hours meter driven by RPM > 0, for bearing and collet tasks; a one-line health note when RPM at a known throttle drifts down over weeks | readout |
| 7 | Settings › Hardware | the tachometer as a Portal catalog type (`tachometer`), with a "spin the bell by hand, see the RPM" check | both |
| 8 | Warm-up and job setup, later | **Target RPM instead of throttle**: enter 18,000, Studio finds the throttle from the table built during warm-up and holds it. Needs its own design note first: closed-loop control of a cutting tool, so a slow correction with limits, never a fast loop, off by default | control |

Shared with stage 1: Help pages made from the two build sheets, so the wiring isn't only in a PDF.

## What can go wrong

| Failure | What happens | Why that is acceptable |
|---|---|---|
| Hall unpowered (rail off) | 0 RPM | expected; the stall rule only runs with the rail on |
| Hall too far from the magnets | 0 or ragged RPM at speed | SP1 (7 per turn by hand) and SP5 catch it before any rule uses it |
| Poll too slow at full throttle | RPM reads low or falls as throttle rises (aliasing) | SP5 compares steps; if it happens, the fix is a divide-by-7 stage, not a faster poll |
| MCU load from a 10 kHz timer | "Timer too close" in `klippy.log` | SP6; the fallback is `poll_interval: 0.00015` with the top-end caveat recorded |
| Module missing after a Klipper update | Klipper refuses to start | the same Host health check and relink as the filament module |

## Decisions for Mike

1. Hall at the bell rim on the ESC's BEC, contact 19 → `PC5`. Approved in principle Nov 14; confirmed by SP1-SP2.
2. The extra, not a `fan_generic` conversion of `SPINDLE_SPEED`. Approved Nov 14.
