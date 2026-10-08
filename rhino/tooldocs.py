"""Reference pages for the built-in toolheads, from the Rhino literature (the manual's tool pages).

Pictures: static/img/tools/<image>-light.png (black line work) and -dark.png (white line work), both on a
transparent background, made from the manual's drawings by dev/lineart.py; the portal shows the one that
matches Mainsail's theme. Used by the portal's tool page: what the tool is, which connector contacts it uses and for what, its
picture, and the macros that belong to it. Change the wording here; pins and materials come from the
live config, not from this file.
"""

BUILTIN_DOCS = {
    "BlockOne": {
        "function": "3D printing (0.4 and 0.8 mm nozzles)",
        "about": "Direct-drive 3D printing, with profiles for 0.4 mm and 0.8 mm nozzles in OrcaSlicer. "
                 "E3D v6 Volcano hotend at 24 V, BMG drive gear and 1.75 mm filament.",
        "setup": "Slicer start G-code (START_JOB)",
        "outputs": "Hotend heater, hotend fan, part-cooling fan",
        "pins": {1: "24 V hotend", 2: "24 V hotend", 3: "Thermistor", 4: "Thermistor", 5: "24 V hotend fan",
                 6: "24 V hotend fan", 7: "Stepper", 8: "Stepper", 9: "Stepper", 10: "Stepper",
                 13: "Probe", 14: "Probe", 15: "Probe"},
        "image": "blockone", "image_notes": ["Part cooling provided by the universal blow-air system."],
        "macros": ["NOZZLE_HEIGHT_CALIBRATE", "PRIME_LINE", "PURGE", "FILAMENT_CHANGE", "CALCULATE_PA"],
    },
    "SwitchFly": {
        "function": "Dual-extrusion 3D printing (0.4 and 0.8 mm nozzles)",
        "about": "Dual extrusion at its finest: the first true direct-drive, dual-extrusion, single-nozzle extruder "
                 "for 3D printing. Optimized for the E3D v6 Volcano hotend and BMG drive gear, and rated at 24 V "
                 "for 1.75 mm filament.",
        "setup": "Slicer start G-code (START_JOB)",
        "outputs": "Hotend heater, fans, filament-path servo (SERVO_LASER)",
        "pins": {1: "24 V + hotend", 2: "24 V hotend", 3: "Thermistor", 4: "Thermistor", 5: "24 V hotend fan",
                 6: "24 V hotend fan", 7: "Stepper", 8: "Stepper", 9: "Stepper", 10: "Stepper",
                 11: "24 V + power activate", 12: "24 V - power activate", 13: "Probe", 14: "Probe", 15: "Probe",
                 18: "PWM - signal"},
        "image": "switchfly", "image_notes": ["Part cooling provided by the universal blow-air system."],
        "macros": ["NOZZLE_HEIGHT_CALIBRATE", "PRIME_LINE", "PURGE", "SWITCH_T0", "SWITCH_T1", "FILAMENT_CHANGE",
                   "CALCULATE_PA"],
    },
    "LightSaber": {
        "function": "Laser cutting and engraving",
        "about": "12 V, 80 W, 450 nm blue diode laser cutter and engraver.",
        "setup": "LASER_JOB_SETUP FILE=<name>.gcode",
        "outputs": "LASER_INITIALIZE 12 V rail, SERVO_LASER intensity",
        "pins": {3: "Thermistor", 4: "Thermistor", 13: "Probe", 14: "Probe", 15: "Probe", 16: "Laser PWM (5 V)",
                 20: "+ 12 V power activate", 21: "- 12 V power activate"},
        "image": "lightsaber", "image_notes": ["Blow-air provided by the universal blow-air system."],
        "macros": ["LASER_JOB_SETUP", "SET_Z_ZERO", "LASERHOME", "LASER_FOCUS_ALIGN", "SET_LASER_POWER", "ACTIVATE_LASER",
                   "DEACTIVATE_LASER"],
    },
    "HotJoe": {
        "function": "CNC spindle for light engraving and milling",
        "about": "Spindle attachment with an ER8 collet and a 2814 1000 kV brushless motor, driven by an 80 A "
                 "HobbyWing ESC on 24 V power.",
        "setup": "CNC_JOB_SETUP FILE=<name>.gcode",
        "outputs": "Spindle_power relay, SPINDLE_SPEED ESC signal",
        "pins": {3: "Thermistor", 4: "Thermistor", 11: "24 V relay power", 12: "24 V relay power", 13: "Probe",
                 14: "Probe", 15: "Probe", 18: "PWM"},
        "image": "hotjoe", "image_notes": ["Shown without safety covers.",
                                               "Blow-air provided by the universal blow-air system."],
        "macros": ["CNC_JOB_SETUP", "SET_Z_ZERO", "SET_WORK_ZERO", "G54", "Spindle_ACTIVATE",
                   "Spindle_DEACTIVATE", "CALIBRATE_ESC"],
    },
    "DragKnife": {
        "function": "Drag-knife cutting (vinyl, cardstock, thin foam)",
        "about": "A drag-knife tool designed for Roland No. 9 and No. 10 blade holders.",
        "setup": "DRAGKNIFE_JOB_SETUP FILE=<name>.gcode",
        "outputs": "None (passive tool)",
        "pins": {3: "Thermistor", 4: "Thermistor", 13: "Probe", 14: "Probe", 15: "Probe"},
        "image": "dragknife", "image_notes": ["Rendered from the build files."],
        "macros": ["DRAGKNIFE_JOB_SETUP", "SET_Z_ZERO"],
    },
}

# Material columns shown per tool type: (field, heading, unit)
MATERIAL_COLUMNS = {
    "DEPOSITION": [("extruder_temp", "Nozzle", "°C"), ("bed_temp", "Bed", "°C"), ("fan_speed", "Fan", "%"),
                   ("accel", "Accel", "mm/s²")],
    "LASER": [("laser_power", "Power", "%"), ("feed_rate", "Feed", "mm/min"), ("accel", "Accel", "mm/s²")],
    "CNC": [("spindle_speed", "Spindle", "rpm"), ("feed_rate", "Feed", "mm/min"), ("accel", "Accel", "mm/s²")],
    "DRAG_KNIFE": [("pressure", "Pressure", ""), ("feed_rate", "Feed", "mm/min"), ("accel", "Accel", "mm/s²")],
    "POWERED": [("power", "Power", "%"), ("feed_rate", "Feed", "mm/min"), ("z_offset", "Z offset", "mm")],
    "PASSIVE": [("feed_rate", "Feed", "mm/min"), ("z_offset", "Z offset", "mm")],
}
PERCENT_FIELDS = {"fan_speed", "laser_power", "power"}      # stored 0..1, shown as %
