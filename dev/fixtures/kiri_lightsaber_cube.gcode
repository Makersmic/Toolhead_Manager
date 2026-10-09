; RHINO_TOOL=LightSaber
; RHINO_PROFILE=Rhino LightSaber (made by the Rhino Tool Manager 1.4.0 from variables.cfg)
; Start this file with LASER_JOB_SETUP FILE=<this file> - it sets the focus and test-fires first.
G21 ; millimetres
G90 ; absolute X/Y - machine coordinates, same as the slicer bed
M5 ; laser off before the first move
ACTIVATE_LASER ; power the LightSaber rails (refused if another tool is mounted)
G0 X265.242 Y187.500
M3 S800.000
G1 X275.000 Y197.259 F600
G1 X284.758 Y187.500
G1 X275.000 Y177.742
G1 X265.242 Y187.500
M5
G0 X262.400 Y175.459
M3 S800.000
G1 X262.400 Y199.541 F600
G1 X262.959 Y200.100
G1 X287.041 Y200.100
G1 X287.600 Y199.541
G1 X287.600 Y175.459
G1 X287.041 Y174.900
G1 X262.959 Y174.900
G1 X262.400 Y175.459
M5
M5 ; laser off
DEACTIVATE_LASER ; rails off
_RHINO_PARK ; bed down to the safe park height