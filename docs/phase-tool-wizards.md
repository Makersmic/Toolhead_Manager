# Tuning and start wizards for the laser, spindle and drag knife (design draft)

Nov 10 2026. **Waiting for Mike's answers (end of this page). Nothing is built.** Mike: "tune the laser, spindle, and
drag knife much like I did for BlockOne", and "start wizards for those … a guided workflow for setting up the stock on
the build plate", with a vacuum pump for the vacuum table coming back soon (added with Studio's Add hardware wizard).

## Why (durability)

- **Tuning:** today each job's power, feed, depth and blade offset are typed from memory. Stored per tool and
  material on the Rhino (backed up), a job months later starts from values that were tested on that material.
- **Start wizards:** the jobs most likely to damage the machine or the work are a bit driven into a clamp, a laser
  focused wrong, stock that shifts mid-cut, and a zero set on the wrong corner. A guided start with a **frame check**
  (trace the job's outline before anything cuts) catches most of them. Today's Mainsail prompt chains can't show the
  bed, the job's outline or Studio's jog panel; Studio can.

## What exists (reused, not rebuilt)

| Piece | Today | Used for |
|---|---|---|
| Tuning framework (Studio `src/tuning/`, Portal `tuning.json`) | 4 print head wizards: make a test file, run it as a job, judge with pictures, save with old/new side by side | The same steps, framework and storage for the three tools |
| Test files run as jobs | Laser/CNC/knife jobs start through `LASER_JOB_SETUP` / `CNC_JOB_SETUP` / `DRAGKNIFE_JOB_SETUP FILE=` | Every tuning test runs through them unchanged: checklist, interlocks, hooks, rails, `_TOOL_SAFE_OFF` at the end |
| Job setup settings | Laser power, speed, passes, kerf; knife speed, depth, passes, blade offset; CNC bit, feed, plunge, clearance | The tuned values fill these per material (and per bit) |
| `SET_Z_ZERO`, `_CNC_SAVE_XY` (G54), `_RHINO_HOME_SAFE`, `_RHINO_LIFT` | Prompt-driven zeroing | Called by the start wizard instead of re-invented |
| Control's motion panel (padlock, 60 s relock) | Jog | Embedded in the start wizard for zeroing |
| Add hardware wizard: **Vacuum table** type (relay, `output_pin`) | "Follows" manual only; following the job is not built yet; job hooks are | The hold-down step and the hooks below |

## Tuning: the tests

Each test is a Studio-made file (no slicer, no CAM), run as a normal job of that tool, then judged on screen.
Results live in `tuning.json` per **tool + material** (CNC: + bit), with the date, and fill Job setup's fields.

### Laser (LightSaber)

| # | Test | What it cuts or marks | You judge | Saved | Used by |
|---|---|---|---|---|---|
| L1 | **Focus ramp** | A 60 mm line at low power while Z climbs steadily from 4 mm below to 4 mm above the current zero, with a tick every 1 mm of Z | The tick where the line is thinnest | **Focus height** above the surface | Start wizard: touch the surface, then lift by this. No more focusing by eye |
| L2 | **Power and speed grid** | 5 × 5 squares, power down one side, speed across, each labelled with small vector digits. Two kinds: **cut** (outlines) and **engrave** (filled) | The cut square that dropped out cleanly with the least char, or the engrave square that looks best | Cut power + speed; engrave power + speed | Job setup's Power and Speed for that material |
| L3 | **Passes** (only if nothing cut through in L2) | One square at full-cut settings for each pass count from 1 to 5 | The fewest passes that cut through | Passes | Job setup's Passes |
| L4 | **Kerf** | A 20 mm square cut out (part and hole) | Measure the part with calipers | Kerf = (20 − part) / 2 | Job setup's Kerf |

### Spindle (HotJoe)

The ESC is set by throttle %, not RPM (there's no speed sensor), so results are throttle %, feed and depth, per bit and
material. Run in scrap stock.

| # | Test | What it cuts | You judge | Saved |
|---|---|---|---|---|
| C1 | **Bit** | Nothing: diameter, flutes, cutting length, end mill or ball | Typed once per bit | The bit list (Job setup's Tool, Diameter, Cutting length) |
| C2 | **Feed ladder** | 30 mm slots at one depth, feed stepped across the row (for example 300 to 1500 mm/min) | Smooth walls, no chatter or burning, sound steady | Feed, at that throttle |
| C3 | **Depth ladder** | Slots at the chosen feed, depth per pass stepped | The deepest clean pass | Depth per pass, plunge |
| C4 | **Size check** | A 20 mm square outline | Measure it | The bit's true cutting diameter (runout), so parts come out the right size |
| C5 | **Run-in** (optional, a new spindle or long idle) | Nothing: throttle 30, 50, 70 and 100 % a minute each, Z raised | Sound and heat | Date only (a Care item) |

**Spoilboard surfacing** (for the vacuum table): a generator for a flat surfacing pass over the spoilboard with a
surfacing bit. It's a job rather than tuning, but the vacuum table needs a flat, sealed board. Offered as a separate
item: say if you want it.

### Drag knife

| # | Test | What it cuts | You judge | Saved | Used by |
|---|---|---|---|---|---|
| K1 | **Blade offset** | A row of 15 mm squares, blade offset stepped from 0.1 to 0.5 mm | The square with the sharpest, closed corners | Blade offset (per blade) | Job setup's Blade offset |
| K2 | **Depth** | A row of short lines, depth below the surface stepped by 0.05 mm | The shallowest that cut through cleanly with the backing intact | Depth per material, plus the pressure dial setting you used (it's turned by hand; the wizard records it so you can set it the same next time) | Job setup's Depth; the start wizard's dial reminder |

## Start wizards: setting up the stock

One Studio page per job of these tools, opened by **Start job** for a laser, CNC or knife file (from Files, Job setup
or the tool page). It replaces the Mainsail prompt chain on screen; the same Klipper macros still do the work.

```
 1 Check        2 Stock & hold-down     3 Zero            4 Frame            5 Tool test       6 Start
 ☐ glasses      bed map: where the      jog (padlock)     trace the job's    laser: test fire  summary:
 ☐ extraction   job lands, stock size   X/Y corner (CNC)  outline, tool off  knife: test cut   material,
 ☐ …            vacuum: on, push test   Z: touch surface  "stayed on stock,  spindle: warm-up  tuned values
 interlocks ✓   clamps: keep outside    laser: + focus    clear of clamps?"                    [Start job]
```

1. **Check:** today's checklist from each setup macro, plus live interlock status (lid closed, …).
2. **Stock and hold-down:** the bed from above with the job's area drawn. The laser uses machine coordinates, so it
   shows exactly where the stock goes; CNC and knife show the stock size needed and where the zero corner is. Then
   how it's held:
   - **Vacuum table** (when a Vacuum table device exists): **Turn the vacuum on**, then "push the stock: it doesn't
     slide". Cover any open table area for suction.
   - **Clamps:** "keep clamps outside the dashed line"; the frame check proves it.
   - **Tape** (knife, thin laser stock).
3. **Zero:** the jog panel (padlock, relock) is embedded. CNC: jog to the corner, **Set X/Y zero** (`_CNC_SAVE_XY`). Z:
   lower onto the surface with a sheet of paper, **Set Z zero** (`SET_Z_ZERO`). Laser with a tuned focus height: touch
   the surface, then the wizard lifts by the focus height and that becomes the zero. Without one: focus by eye, as
   today.
4. **Frame:** the head traces the job's outline at a safe height (5 mm above the stock), **tool off**: no spindle, no
   laser, blade up. "Did it stay on the stock and clear of every clamp?" No → fix and frame again.
5. **Tool test:** laser test fire (today's), knife test cut (today's, at the tuned depth), spindle warm-up ramp
   (today's).
6. **Start:** the file, the material, the tuned values it uses, passes; **Start job**.

### The vacuum table (when you add the pump)

- Add it in Studio: Add hardware › **Vacuum table** (relay). Following the job automatically isn't built yet, so the
  wizard and job hooks switch it:
  - The start wizard turns it **on** in step 2 (manual control, confirmed), so the stock is held while you zero and frame.
  - A job hook turns it **off** after the job ends; the wizard offers to add the hook the first time.
- **Pause keeps the vacuum on**: the stock must not move while paused (the pause hook only switches the tool off; to
  be checked in the simulator).
- **Cancel and E-stop switch it off** (the device is "switch off when the machine is made safe"): the stock is loose
  afterwards, which is fine because the job has stopped.
- The pump's runtime can be a Care item (filter, oil if it's a vane pump).

## What changes where

- **Studio:** the tuning wizards (L1-L4, C1-C5, K1-K2) on the framework that exists; tool pages show their ticks and
  dates; Job setup reads the results; the start wizard page.
- **Portal:** `tuning.json` gains these tools' keys (same revisions, history and backup); the bit list.
- **Klipper macros:** the tuning tests need **no** macro change; they run through today's setup macros. The start
  wizard needs one small change, so it gets its own `docs/proposal-*.md` with the order of events before any code.
  Each `*_JOB_SETUP` takes `FROM=STUDIO`: it runs the same checks, interlocks and hooks, then skips the prompts Studio
  has just walked through and goes straight to its start step. It still refuses if the tool isn't mounted, if a job is
  running, or if the Z zero wasn't set in this session. The frame moves are plain moves Studio builds and sends
  through the console's check (motion confirms); nothing new runs without a confirm.

## Safety

- Every test and every job still starts through the tool's setup macro: tool check, interlocks, hooks, the laser's
  rails only after the file loads, `_TOOL_SAFE_OFF` at the end and on cancel.
- The laser focus ramp and test fire need the lid interlock closed (when there is one) and run at the test's low power,
  capped.
- The frame never powers the tool. The laser's low-power "pointer" option is left out on purpose: a visible dot is still
  a beam.
- Motion only behind the padlock, with confirms; Z is never homed with these tools mounted (`_RHINO_HOME_SAFE`).
- Nothing writes printer.cfg. Tuned values are records on the Portal plus Job setup defaults; a bad value can be undone
  from the history.

## Questions for Mike

1. **Order:** my suggestion is laser first (L1 focus and L2 grid help most), then the knife (K1, K2: quick wins), then
   the spindle (C1-C4), with the start wizard built alongside the laser and used by all three. OK, or a different order?
2. **Start wizard replaces the Mainsail prompts on screen:** OK to add `FROM=STUDIO` to the three setup macros (a macro
   change, proposal first)? The prompts stay for Mainsail until it's removed.
3. **Laser L2:** cut test, engrave test, or both? Your notes say the LightSaber is set up as a cutter.
4. **Spindle:** do you know the HotJoe's no-load RPM at 100 % (its kV × voltage)? Then feeds can be suggested from the
   bit's chip load instead of found purely by test.
5. **Vacuum:** a vane pump or a diaphragm pump? And should the start wizard insist on a "push test" before zeroing when
   the vacuum table is in use?
6. **Spoilboard surfacing:** wanted with the vacuum table?
