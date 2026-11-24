# Proposal: apply the input shaper per print head (a Klipper macro change, needs Mike's OK)

Nov 23 2026. **APPLIED Nov 23 in 1.9.49 (Mike: "per head now").** The Input shaping wizard (Wizards > Input shaping) measures each print head and keeps the result for that head. This
change makes Klipper use the right head's result at the start of each job.

## What exists

`SET_PRINT` runs at every print-head job start and calls `_RHINO_APPLY_TUNING` (`tools/3dp_macros.cfg`), which sets the extruder's rotation distance, pressure
advance and flow from values Studio stored as save variables (`rhino_rd_<head>`, `rhino_pa_…`, `rhino_em_…`), or printer.cfg's when there is none. Nothing carries over from the last job.
The wizard keeps the shaper two ways: in `myrhino/tuned.cfg` (`[input_shaper]` holds the **last** head's result, loaded at Klipper start) and, once this is approved, as a save variable per head.

## The change

One block added at the end of `_RHINO_APPLY_TUNING`, after the extruder lines and before the "out of range" report:

```
  # Input shaping for this head (docs/proposal-per-head-shaping.md): the pick Studio's Input shaping wizard stored, else leave it as it is
  {% set sh = sv.get(("rhino_shaper_" ~ tool)|lower) %}
  {% set sp = sh.split(",") if sh is string else [] %}
  {% set sh_ok = sp|length == 4 and sp[0] in ["zv","mzv","zvd","ei","2hump_ei","3hump_ei"] and sp[2] in ["zv","mzv","zvd","ei","2hump_ei","3hump_ei"] and sp[1]|float > 10 and sp[1]|float < 200 and sp[3]|float > 10 and sp[3]|float < 200 %}
  {% if sh_ok and "input_shaper" in printer.configfile.settings %}
    SET_INPUT_SHAPER SHAPER_TYPE_X={sp[0]} SHAPER_FREQ_X={sp[1]} SHAPER_TYPE_Y={sp[2]} SHAPER_FREQ_Y={sp[3]}
    RESPOND MSG="Input shaper for {tool}: X {sp[0]} {sp[1]} Hz, Y {sp[2]} {sp[3]} Hz (tuned)"
  {% elif sh is not none and not sh_ok %}
    RESPOND TYPE=error MSG="rhino_shaper_{tool} = {sh} isn't valid, so the shaper stays as Klipper loaded it. Run the Input shaping wizard again."
  {% endif %}
```

**What runs, in what order:** a job starts: `SET_PRINT` → `_RHINO_APPLY_TUNING` sets the extruder, then (new) looks for a stored shaper for the mounted head. If it is valid and Klipper has an
`[input_shaper]` section, it sets the four values (a live change, no restart; the next restart goes back to `tuned.cfg`). If there is none, nothing changes: the head prints with
whatever Klipper has loaded, as today. A bad stored value is reported and ignored, never used.

## What can go wrong, and what stops it

- **A wrong shaper makes prints worse, never unsafe:** a shaper only changes how moves are smoothed. The values are range-checked (type in Klipper's list, 10 to 200 Hz) before they are used.
- **No `[input_shaper]` section** (no accelerometer set up yet): the new block does nothing, so every machine without it behaves exactly as now.
- **A head with no result:** keeps the loaded shaper. Mixed heads (one measured, one not) is the case to watch: the unmeasured head would use the last-loaded shaper, which was another head's. The wizard says so on its Keep step.
- **`SET_INPUT_SHAPER` mid-print:** it only runs at job start (SET_PRINT), before any move of the job. It is not called on a swap during a job.
- **Macro variables reset on restart, save variables don't:** the stored pick survives restarts and power cuts.

## How it is applied

`dev/proposal_per_head_shaping.py` (anchor-checked in the same style as `proposal_macro_hooks.py`; refuses a second run) adds the block. Studio's Keep also writes
`SAVE_VARIABLE VARIABLE=rhino_shaper_<head> VALUE='"mzv,47.8,ei,40.0"'` (lower-case head name, as the other `rhino_*` variables). Tests: the simulated Klipper runs `_RHINO_APPLY_TUNING` with a good, a missing and a bad value;
`test_real_klipper.py` is told the new command. On the machine (`docs/testing.md`, SH1-SH3): a job start prints the "Input shaper for <head>" line for a measured head; an unmeasured head prints nothing new;
a bad value (set by hand with SAVE_VARIABLE) is reported and ignored.

**Question for Mike:** apply it? It changes a macro that runs at every print start, so I would apply it in its own release with the checks above, after the Input shaping wizard has been run once on the machine.
