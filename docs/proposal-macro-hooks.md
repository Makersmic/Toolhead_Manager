# Proposal: job hooks, interlocks and filament sensors in the macros

**Status: approved by Mike and applied (Oct 26, Tool Manager 1.9.0).** The 16 insertions below are in the
macros, `job_hooks.LIVE` is `True`, and the three macros live in the generated `myrhino/job_hooks.cfg` (a starter copy
ships with the config, so they always exist; the installer keeps yours). It was the "show the macro diff first" step
from `decisions.md` (2026-10-26). `dev/test_job_hooks.py` checks every call site is in place exactly once. Running
`dev/proposal_macro_hooks.py --apply` again would add them twice: don't.

## What it adds

Three generated macros, each written by the Portal from what's saved (examples below):

| Macro | Does | Written from |
|---|---|---|
| `_RHINO_HOOKS SLOT=… [TOOL=…]` | Runs the saved hook lines for that slot: whole machine, then the tool's category, then that tool | `myrhino/job_hooks.json` |
| `_RHINO_INTERLOCKS [TOOL=…]` | Refuses (raises an error) while a lid interlock is open for a laser or spindle tool, a required flame sensor is triggered, or a must-be-OK pressure switch isn't | interlock / flame / pressure hardware |
| `_RHINO_FILAMENT_SENSORS [TOOL=…]` | Turns filament sensors on only with a print head mounted | runout / jam hardware |

TOOL defaults to the mounted tool, so most call sites are one short line.

And **calls only** in existing macros: 16 insertions, no existing line edited or removed. The diff is at the end.

## What runs, in order

1. **Print head** (`START_JOB`): mismatch and material checks (unchanged) → `_RHINO_INTERLOCKS` → **before start** → `G28`
   and the Rhino's start (unchanged) → `CONFIRM_TOOLHEAD` prompt → `_START_JOB_FILE`: `_RHINO_INTERLOCKS` again →
   **after start** → the file runs.
2. **Laser / CNC / knife / custom** (`*_JOB_SETUP`): its own checks (unchanged) → `_RHINO_INTERLOCKS` → **before start** →
   setup prompts (focus, zero, test fire) → `_START_JOB_FILE`: interlocks again → **after start** → the file runs.
   The laser test fire also checks interlocks first.
3. **End** (`END_PRINT`): **before end** → the Rhino's end sequence (unchanged) → **after end** → the long-job backup (unchanged).
4. **Cancel** (`_RHINO_CANCEL`): the Rhino's cancel (unchanged: `_TOOL_SAFE_OFF` first, park, offsets) → **on cancel**,
   last. That runs everything any hook turned on → off, then the user's cancel lines.
5. **Pause** (`_RHINO_PAUSE_HOOK`): the Rhino's pause (unchanged, tool power off first) → **on pause**.
6. **Resume**: print heads (`_RHINO_RESUME_HOOK`) and other tools (`TOOL_RESUME`) both check interlocks and run
   **on resume** *before* the spindle or laser comes back.
7. **Tool mounted** (`CONFIRM_TOOL_INSTALL`, `RESTORE_TOOL` at start-up): `_RHINO_FILAMENT_SENSORS`.

Every job path ends in `_START_JOB_FILE`, so "after start" is one place for every tool. Print heads use `START_JOB`
and the others use their `*_JOB_SETUP` (checked: the flows don't overlap), so "before start" runs once per job.

## What can go wrong, and the guard for each

- **A before-start hook moves an axis before homing.** Refused on save: no G0/G1/G2/G3/G28 in before start.
- **A hook names a macro that's later removed or renamed.** Checked on save. If it happens afterwards: in before or
  after start, the job stops at start with "Unknown command", before the file runs (safe). In cancel it can't stop the
  Rhino's own cancel, because the hook call is the **last** line. The editor shows "Needs attention" when a saved hook
  no longer checks out.
- **An "on" with no "off".** The editor warns, and on cancel the hooks macro turns off everything any hook turned on
  **before** running the user's cancel lines.
- **A heater hook.** Targets are checked against that heater's `max_temp` (chamber heaters are capped at 120 C anyway).
- **The lid opens during setup prompts.** Caught by the second interlock check in `_START_JOB_FILE`, the last gate.
- **The lid opens mid-job.** The interlock's own button pauses the job (that's already in the generated
  `[gcode_button]`). For laser and spindle tools, resume refuses until it's closed.
- **`action_raise_error` in `_RHINO_INTERLOCKS`.** It aborts the calling macro at that line. Every call sits before
  anything moves or powers up, so nothing is left half-on. In `_START_JOB_FILE`'s "already running" branch (a job
  started from Mainsail's Print button), the error stops the print, which is the intended result with the lid open.
- **Klipper renders a macro before running it.** `_RHINO_INTERLOCKS` is its own macro, so it reads the button state
  when it runs, not when `START_JOB` was rendered.
- **Tools change after hooks are saved.** The generated tool-to-category map and the interlock tool lists are rebuilt
  on every registry or hooks save, once live. (Today's Portal saves already regenerate `custom_tools.cfg`, and the
  hooks file will follow the same rule.)
- **An interlock with a broken wire.** The recommended normally-closed type reads a broken wire as open, so the job
  refuses to start (fails safe).

## How it goes live (after "yes")

1. `python3 dev/proposal_macro_hooks.py --apply` writes the 16 insertions (the same anchors the test checks).
2. `job_hooks.LIVE = True`: the Portal writes `myrhino/job_hooks.cfg` (the three macros) on every hooks or registry
   save, and `printer.cfg` includes it.
3. Release as a normal version bump. On the machine, before trusting it: open the lid and press Start (refused);
   close it (starts); add a dust hook to Subtractive, run a short CNC air job and cancel it (dust goes off).

## Example generated macros

These are rendered from a sample setup (lid interlock, air-pressure switch, runout sensor, a dust collector hook
for Subtractive tools, a chamber heater hook):

```
[gcode_macro _RHINO_INTERLOCKS]
description: Refuse to start while a door / lid interlock is open or a required sensor is triggered (generated). TOOL defaults to the mounted tool.
gcode:
  {% set _map = {} %}
  {% set _ = _map.update(printer['gcode_macro VARIABLES'].tool_mapping) %}
  {% set _ = _map.update(printer['gcode_macro CUSTOM_TOOLS'].tool_mapping|default({})) %}
  {% set tool = params.TOOL|default(_map.get(printer['gcode_macro SWAP_TOOL'].current_tool|int, '')) %}
  {% if printer["gcode_button air_ok"].state == "PRESSED" %}
    { action_raise_error("air_ok isn't OK (no air or coolant pressure).") }
  {% endif %}
  {% if tool in ['LightSaber'] and printer["gcode_button lid"].state == "PRESSED" %}
    { action_raise_error("lid is open. Close it before starting the laser.") }
  {% endif %}
  {% if tool in ['HotJoe'] and printer["gcode_button lid"].state == "PRESSED" %}
    { action_raise_error("lid is open. Close it before starting the spindle.") }
  {% endif %}

[gcode_macro _RHINO_FILAMENT_SENSORS]
description: Filament sensors on only with a print head mounted (generated). TOOL defaults to the mounted tool.
gcode:
  {% set _map = {} %}
  {% set _ = _map.update(printer['gcode_macro VARIABLES'].tool_mapping) %}
  {% set _ = _map.update(printer['gcode_macro CUSTOM_TOOLS'].tool_mapping|default({})) %}
  {% set tool = params.TOOL|default(_map.get(printer['gcode_macro SWAP_TOOL'].current_tool|int, '')) %}
  {% set on = 1 if tool in ['BlockOne', 'SwitchFly'] else 0 %}
  SET_FILAMENT_SENSOR SENSOR=runout ENABLE={on}

[gcode_macro _RHINO_HOOKS]
description: Job hooks from Rhino Studio (generated). SLOT=before_start|after_start|before_end|after_end|on_cancel|on_pause|on_resume [TOOL=<name>, default the mounted tool]
variable_categories: {"BlockOne": "additive", "DragKnife": "subtractive", "HotJoe": "subtractive", "LightSaber": "subtractive", "SwitchFly": "additive"}
gcode:
  {% set slot = params.SLOT|default('')|lower %}
  {% set _map = {} %}
  {% set _ = _map.update(printer['gcode_macro VARIABLES'].tool_mapping) %}
  {% set _ = _map.update(printer['gcode_macro CUSTOM_TOOLS'].tool_mapping|default({})) %}
  {% set tool = params.TOOL|default(_map.get(printer['gcode_macro SWAP_TOOL'].current_tool|int, '')) %}
  {% set cat = categories[tool]|default('') %}
  {% if slot == 'before_start' %}
    SET_HEATER_TEMPERATURE HEATER=chamber TARGET=40
    {% if cat == "subtractive" %}
      DUST_ON
    {% endif %}
  {% elif slot == 'after_end' %}
    SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0
    {% if cat == "subtractive" %}
      G4 P10000
      DUST_OFF
    {% endif %}
  {% elif slot == 'on_cancel' %}
    SET_HEATER_TEMPERATURE HEATER=chamber TARGET=0
    SET_PIN PIN=dust VALUE=0
  {% endif %}

```

## The diff (calls only)

Produced by `python3 dev/proposal_macro_hooks.py` from the files at this commit. `dev/test_job_hooks.py` fails if any
anchor drifts.

```diff
--- a/myrhino/TOOLHEAD_DISPATCH.cfg
+++ b/myrhino/TOOLHEAD_DISPATCH.cfg
@@ -77,4 +77,8 @@
   {% endif %}
 
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): checks first, then the before-start hook. Nothing has moved yet.
+  _RHINO_INTERLOCKS TOOL={requested_toolhead}
+  _RHINO_HOOKS SLOT=before_start TOOL={requested_toolhead}
+
   # Secure verification cleared, proceed with job movements safely
   G28
@@ -236,6 +240,14 @@
     # Job already running (started from Mainsail's Print button) - nothing to start.
     M117 Job already running
+    {% if printer.print_stats.state == "printing" %}
+      # job hooks / interlocks (docs/proposal-macro-hooks.md)
+      _RHINO_INTERLOCKS
+      _RHINO_HOOKS SLOT=after_start
+    {% endif %}
   {% elif f != "" %}
     SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE="''"
+    # job hooks / interlocks (docs/proposal-macro-hooks.md): last gate before the file runs (a lid opened during setup is caught here)
+    _RHINO_INTERLOCKS
+    _RHINO_HOOKS SLOT=after_start
     SDCARD_PRINT_FILE FILENAME="{f}"
   {% else %}
@@ -724,4 +736,6 @@
   {% set TOOLHEAD = printer.save_variables.variables.set_material_toolhead|default("BlockOne") %}
   {% set tool_type = _th.get(TOOLHEAD, {}).get("type", "DEPOSITION") %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_HOOKS SLOT=before_end TOOL={TOOLHEAD}
 
   {% if tool_type == "DEPOSITION" %}
@@ -766,4 +780,7 @@
 
   # ====================================================================
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): after the Rhino's end sequence, before the backup
+  _RHINO_HOOKS SLOT=after_end TOOL={TOOLHEAD}
+  # ====================================================================
   # 👉 DESIGNER AUTOMATED BACKUP TRIGGER (ADDED HERE)
   # ====================================================================
--- a/guided/laser_workflow.cfg
+++ b/guided/laser_workflow.cfg
@@ -18,4 +18,7 @@
     { action_raise_error("LASER_JOB_SETUP sets a work zero, which a running or paused job's RESUME would undo. Run it BEFORE the job starts: LASER_JOB_SETUP FILE=<name.gcode>") }
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_INTERLOCKS
+  _RHINO_HOOKS SLOT=before_start
   SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE="'{params.FILE|default("")}'"
   SET_GCODE_OFFSET X=0 Y=0 ; laser files use machine X/Y - drop any CNC / knife X/Y work zero
@@ -61,4 +64,6 @@
 description: Fires a brief low-power pulse in place to confirm alignment/focus before cutting.
 gcode:
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): no test fire with the lid open
+  _RHINO_INTERLOCKS
   RESPOND TYPE=command MSG="action:prompt_end"
   M117 Test firing at low power...
--- a/guided/cnc_workflow.cfg
+++ b/guided/cnc_workflow.cfg
@@ -22,4 +22,7 @@
 
   # Map file target pointer payload
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_INTERLOCKS
+  _RHINO_HOOKS SLOT=before_start
   SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE="'{params.FILE|default("")}'"
   
--- a/guided/dragknife_workflow.cfg
+++ b/guided/dragknife_workflow.cfg
@@ -21,4 +21,7 @@
 
   # Map file target pointer payload
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_INTERLOCKS
+  _RHINO_HOOKS SLOT=before_start
   SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE="'{params.FILE|default("")}'"
   
--- a/guided/generic_workflow.cfg
+++ b/guided/generic_workflow.cfg
@@ -43,4 +43,7 @@
     { action_raise_error("Choose a material for " ~ name ~ " first: SET_TOOLHEAD TOOLHEAD=" ~ name ~ " MATERIAL=<" ~ t.get("materials", {}).keys()|join("|") ~ ">") }
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_INTERLOCKS
+  _RHINO_HOOKS SLOT=before_start
   SET_GCODE_VARIABLE MACRO=_START_JOB_FILE VARIABLE=file VALUE="'{params.FILE|default("")}'"
   _RHINO_HOME_SAFE RESUME=_TOOL_JOB_SETUP_AGAIN ; never homes Z; homes X/Y only if needed
--- a/client_macros.cfg
+++ b/client_macros.cfg
@@ -87,2 +87,4 @@
     M117 Print canceled
     LEDFLASH
+    # job hooks / interlocks (docs/proposal-macro-hooks.md): last, so a failing hook can't stop the Rhino's own cancel (tool power is already off)
+    _RHINO_HOOKS SLOT=on_cancel
--- a/tools/tool_power.cfg
+++ b/tools/tool_power.cfg
@@ -330,4 +330,6 @@
     _RHINO_PAUSE_PROMPT
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md)
+  _RHINO_HOOKS SLOT=on_pause
 
 
@@ -353,4 +355,7 @@
     _TOOL_REJECT MSG="This job was paused with a non-print tool - resume it with TOOL_RESUME (the Resume job button)."
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): print heads resume here (non-print tools were refused above)
+  _RHINO_INTERLOCKS
+  _RHINO_HOOKS SLOT=on_resume
 
 
@@ -380,4 +385,8 @@
     SET_GCODE_VARIABLE MACRO=RESUME VARIABLE=idle_state VALUE=False
 
+    # job hooks / interlocks (docs/proposal-macro-hooks.md): lid closed and hooks back on BEFORE the spindle or laser comes back
+    _RHINO_INTERLOCKS
+    _RHINO_HOOKS SLOT=on_resume
+
     # 1. Travel above the paused spot at the current (lifted) height.
     G90
--- a/toolchanger.cfg
+++ b/toolchanger.cfg
@@ -68,4 +68,6 @@
     _PM_BOOT_REMINDER
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): filament sensors only with a print head
+  _RHINO_FILAMENT_SENSORS
 
 
@@ -424,4 +426,6 @@
     RESPOND TYPE=command MSG="action:prompt_show"
   {% endif %}
+  # job hooks / interlocks (docs/proposal-macro-hooks.md): filament sensors only with a print head
+  _RHINO_FILAMENT_SENSORS
 
 [gcode_macro _RESTORE_TOOL_DISMISS]
```
