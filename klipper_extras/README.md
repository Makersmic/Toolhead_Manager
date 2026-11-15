# Klipper extras shipped with the Rhino Tool Manager

Small Klipper modules (host-side Python) that stock Klipper has no equivalent for. `install.sh` copies this folder
with the rest of the package and links each `*.py` into `~/klipper/klippy/extras/`, so a Klipper update neither
removes them nor sees changed files. Settings › Host in Rhino Studio shows whether the links are in place and can
remake them; `uninstall.sh` removes them. A module does nothing until a section of its own is in the config.

| File | Section | What it does | Design |
|---|---|---|---|
| `filament_angle_sensor.py` | `[filament_angle_sensor name]` | filament travel from an AS5600 angle board on an ADC pin; pauses a print when the filament stops moving; `FILAMENT_ENCODER_CALIBRATE` | `docs/proposal-filament-encoder.md` |
| `spindle_tachometer.py` | `[spindle_tachometer name]` | spindle RPM from a pulse input, on Klipper's own pulse counter | same, stage 2 |

Both are GPLv3 like Klipper. Tests: `python3 dev/test_klipper_extras.py` (against a fake Klipper: the real one is
run by `dev/test_real_klipper.py` when a checkout is available).
