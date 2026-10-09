📂 MASTER SPECIFICATION: THE RHINO MULTI-TOOL ECOSYSTEM
🤖 System Introduction & Context
This file serves as the definitive architecture manual and "State of the Machine" baseline for The Rhino—a heavily customized, modular 5-axis hybrid manufacturing workspace powered by Klipper, Moonraker, and an OrcaSlicer frontend. This machine utilizes a shared coordinate rail system but completely switches disciplines based on the physically attached toolhead via a manual, hot-swappable 21-pin umbilical connection line.
🗺️ Stored Global Mappings (variables.cfg)
All macros are explicitly aligned to a single, persistent disk cache file (variables.cfg) via Klipper’s [save_variables] module to prevent volatile dual-tracking sync lag across machine boots:
• Tool Registries: Built-in tools live in variables.cfg (tool_mapping / toolheads), slots 1-5: BlockOne, SwitchFly, LightSaber, HotJoe, DragKnife. Tools added with the portal or ADD_TOOLHEAD live in myrhino/custom_tools.json and are written to the generated myrhino/custom_tools.cfg ([gcode_macro CUSTOM_TOOLS], slots 6 and up). Macros read BOTH through the merged registry; never edit custom_tools.cfg by hand.
• Active Hardware Position Tracker: The wizard uses printer["gcode_macro SWAP_TOOL"].current_tool to track what is physically connected. Macro variables do not survive a Klipper restart, so every confirmed swap also saves current_tool to variables.save; ~8 s after a restart a prompt offers to restore it (RESTORE_TOOL). Nothing assumes the tool silently.
• Workspace Transformations: Persistent CNC registers (cnc_g54_x, cnc_g54_y, cnc_g54_z) store offsets for subtractive tasks, safely isolating industrial coordinate shifts from default 3D print endstops.
🔧 Active Toolhead Modules & Software Rules
1. BlockOne (Slot 1)
• Type: DEPOSITION
• Configuration: Standard single-extruder 3D printing toolhead. Starts execution by passing explicit formatting via OrcaSlicer: START_JOB TOOLHEAD="BlockOne" MATERIAL="[filament_type]" NOZZLE_SIZE=[nozzle_diameter] EXTRUDER=0. Numbers are cleanly passed un-quoted to ensure stepper current arithmetic checks parse flawlessly.
2. SwitchFly (Slot 2)
• Type: DEPOSITION
• Configuration: Single physical stepper motor shared between two independent filament tubes. Alignments are shifted using a dedicated _SWITCHFLY_SET_PATH servo flag (0 to 180 degrees).
• The Direction-Reversal Override: Because path 1 pulls filament from the backside of the drive gears, G0 and G1 are globally intercepted using rawparams. If SwitchFly path 1 is active, extrusion targets are dynamically inverted to a negative orientation (E * -1.0) on the fly, safely preserving all travel tracking, layer speeds, and slicer width strings.
3. LightSaber (Slot 3)
• Type: LASER
• Configuration: High-frequency laser diode cutter. Integrates standard GRBL convention parameters (M3/M4/M5, scaled against laser_s_max) through the single shared M3/M4/M5 dispatcher in tools/tool_power.cfg.
• Safety Lockout: Implements hard hardware-gated overrides inside SET_LASER_POWER. If any job streams an M3 signal while a 3D printer hotend or spindle is attached, Klipper forces an immediate safety shutdown to protect the umbilical pins and user workspace. Isolates LEDFLASH from high-frequency lines to eliminate processor stutter. Features an interactive 1% duty-cycle visibility target utility (LASER_FOCUS_ALIGN).
• Power rail (1.4.1): the LightSaber fires only with LASER_INITIALIZE on; M3 only sets the level. LASER_JOB_SETUP's last step, _LASER_START, loads the FILE and then runs ACTIVATE_LASER (if the file fails to load, the rail stays off; with no FILE nothing starts; with another tool mounted it refuses before the file starts). END_PRINT, CANCEL_PRINT, EMERGENCY_STOP and SWAP_TOOL switch the rail off; PAUSE drops only the level and TOOL_RESUME restores it.
4. HotJoe (Slot 4)
• Type: CNC
• Configuration: Brushless outrunner CNC spindle motor driven by a 400Hz open-loop RC Electronic Speed Controller (ESC). Low-endpoint throttle arms at 0.3, scaling to high-endpoint maximum thresholds at 1.0.
• Shared channels: SERVO_LASER (PB0) is both the LightSaber intensity and the SwitchFly path servo; SPINDLE_SPEED idles at 0.3 (ESC neutral), never 0.
• Subtractive Calibration: Houses an interactive, graphical windowed CALIBRATE_ESC endpoints synchronization wizard. Integrates G54 offsets and an automated PROBE_Z_WORK_ZERO 10mm aluminum touch-plate downward search matrix.
5. DragKnife (Slot 5)
• Type: DRAG_KNIFE
• Configuration: Mechanical spring-loaded vector vinyl plotting blade. Features a dedicated, safety-gated absolute scoring utility (_DK_TEST_CUT) which drops exactly 0.3mm beneath the G54-zero material face to trace a 10mm validation cut line, protecting underlying cutting mats from relative plunge errors.
🖥️ Graphic User Experience Panels (Mainsail UI)
• SWAP_TOOL: A modular 2-stage hot-swap wizard. Shuts down heaters, cools gantry items to a safe 40°C, cuts extruder power lines to prevent pin-arcing, and pauses execution (PAUSE_BASE). It prompts the physical hand-swap before allowing verification hooks (CONFIRM_TOOL_INSTALL) to read the universal PF4 thermistor circuit line.
• PREHEAT: A dynamic pre-flight checker. If a sliced job specifies PLA, it halts execution and opens a web-interface modal allowing the operator to click a button and completely bypass build plate heating/soaking, leaping straight into the file.
• CNC_JOB_SETUP: A sequential step-by-step setup screen for machining. Guides workholding clamps, collet torque, and launches an optional dynamic choice path between touch-plate or manual paper zeroing.
• BACKUP_CONFIG: Automatically hooks into CONFIRM_TOOL_INSTALL and any successful print job that tracks an execution runtime greater than 2 hours (printer.print_stats.total_duration >= 7200). Packages and pushes the entire .cfg layout tree, macro sets, and uploaded OrcaSlicer .bb bundles straight to your remote GitHub repo over an authenticated secure SSH key tunnel (git_protocol="ssh").

🧩 Adding Your Own Toolheads (slots 6+)
• Kinds: HOT_WIRE and NEEDLE (cap-limited PWM power with a watchdog), POWERED (any PWM tool), PASSIVE (pen, blade, probe: offsets + feed only), PRINT_HEAD (clone of an existing 3D-print tool with other nozzle sizes).
• Where: the Rhino portal (python3 scripts/rhino_portal.py, port 5000) has drop-down menus, typed names, photos and a live pin map - things Mainsail prompts cannot do (they support only text and buttons). Console fallback: ADD_TOOLHEAD / EDIT_TOOLHEAD / REMOVE_TOOLHEAD / RENAME_TOOLHEAD / LIST_TOOLHEADS / TOOLHEAD_PINS / CHECK_TOOLHEADS, all of which call scripts/rhino_toolgen.py.
• Hardware sharing: a powered tool may take a NEW tool-connector pin (checked against every pin in the Klipper config and the umbilical list in myrhino/umbilical.json) or SHARE an existing PWM output. Sharing defaults the idle level to that output's configured value.
• Safety: power is capped (power_cap), scaled from M3 S<value> against s_max, forced to idle by _TOOL_SAFE_OFF on swap / cancel / end / emergency stop, and a 5 s watchdog cuts a tool left on for max_on_s with no job running. A paused job cuts the power and RESUME restores it.
• Job flow: SET_TOOLHEAD TOOLHEAD=<name> MATERIAL=<material>, then TOOL_JOB_SETUP FILE=<name.gcode> (checklist, work zero without moving, test pulse, start with tool power ON or file-controlled).
• Changes are saved immediately and take effect after a FIRMWARE_RESTART (the portal and macros offer a button, and refuse while a job is printing or paused).
• Code map for troubleshooting: rhino/presets.py (defaults and limits), klipper_cfg.py (reads the config), registry.py (JSON + generated cfg), builders.py (validation rules), service.py (add/edit/remove API), cli.py (console), portal/routes.py (HTTP), portal/static/portal.js (screens).
