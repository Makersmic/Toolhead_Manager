# OrcaSlicer profiles - BlockOne, 0.4 mm nozzle

Built from Mike's own Orca 2.3.0 slices (latest: Body3, 2025-09-03). Stand-alone user presets, so they
don't need any other Orca printer installed.

| File | Orca tab | What it is |
|---|---|---|
| Rhino BlockOne 0.4.json | Printer | Bed 550 x 375 (X endstop at 550), height 300, Klipper, start G-code START_JOB + CALCULATE_PA, end G-code END_PRINT |
| 0.20mm Standard @Rhino BlockOne.json | Process | 0.2 mm layers, first layer 15 mm/s at 500 mm/s², walls/infill 60 mm/s, 5 walls, 10 % crosshatch |
| Rhino PLA @BlockOne 0.4.json | Filament | 210 °C, bed 65 °C, flow 0.95 |
| Rhino PETG @BlockOne 0.4.json | Filament | 245 °C, bed 90 °C, flow 1.2, fan max 35 % |

Bed temperature is the same for every plate type, so the plate picked in Orca doesn't change it.

## Import
1. Download the four .json files (Mainsail: Machine > slicer/orca, or the zip you were sent).
2. Orca: File > Import > Import Configs... and select all four.
3. Pick printer "Rhino BlockOne 0.4", process "0.20mm Standard @Rhino BlockOne", filament "Rhino PLA @BlockOne 0.4".

## Start G-code
    M140 S0 ; Reset bed temperature
    M104 S0 ; Reset extruder temperature
    START_JOB TOOLHEAD=BlockOne MATERIAL=[filament_type] NOZZLE_SIZE=[nozzle_diameter] EXTRUDER=0
    ;
    CALCULATE_PA BOWDEN_LENGTH=5.9 MATERIAL=[filament_type] LAYER_HEIGHT=[layer_height] NOZZLE_SIZE=[nozzle_diameter] PRINT_SPEED=[outer_wall_speed] FILAMENT_DIAMETER=[filament_diameter] LINE_WIDTH=[line_width]

The first-layer nozzle and bed temperatures come from the Rhino config (variables.cfg, set by PREHEAT);
Orca only sends a bed temperature from layer 2. The Orca filament temperatures match variables.cfg (PLA 210/65,
PETG 245/90) - if you change one, change the other.
