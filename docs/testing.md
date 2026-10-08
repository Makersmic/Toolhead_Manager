# Testing strategy

How the Rhino tool manager is tested, what each layer can and can't prove, and the on-machine acceptance plan for
each release. Automated tests catch logic mistakes in seconds; only the machine can prove that something moves the
right distance, switches the right pin, or stops when it should. Both are needed.

## The layers

```
              On-machine acceptance          few, slow - the only proof of real motion, pins, heat and safety
            Browser smoke test               every screen and dialog in headless Chromium, desktop and phone
        Portal and service tests (Flask)     HTTP, registry, generated config, maintenance maths
     Simulated motion + sweep                where the bed and head go; safety rules over every macro/button
   Simulated-Klipper macro tests             macro chains, pop-ups, buttons, saved variables
Static lint of every .cfg file               unknown commands, invalid options, bad values
```

| Layer | Tool | What it proves | What it can't prove |
|---|---|---|---|
| Lint | `dev/lint_rhino.py` | Every macro calls a command that exists; options Klipper rejects at start-up (e.g. `description:` in a `delayed_gcode`, soft-PWM `shutdown_value` other than 0/1); pins used twice | That Klipper accepts the whole config on your board |
| Macro tests | `dev/test_macros.py` with `dev/klippersim.py` (178 checks) | Macros render the way Klipper renders them (whole template first), run in order, show the right pop-up and buttons, save the right variables, refuse what they should | Timing, heaters, real pins |
| Motion tests | `dev/test_motion.py` (82 checks, about a minute) | Where the bed and head end up: the simulator follows the position like Klipper (G90/G91, G92, offsets, `safe_z_home`, `SAVE`/`RESTORE_GCODE_STATE`, pause/resume) and refuses moves past `position_min`/`max` or on unhomed axes, with the limits read from `printer.cfg`. Flows: homing, paper test, print, cancel, swap, Set Z zero, Z restore, CNC, knife, laser pause/resume, filament change. Then a sweep of every macro and every button from 7 machine states x 5 tools (about 15,600 runs) against five safety rules (below) | Collisions: it knows the travel limits, not tool lengths or stock height, so "too close" is judged by rules, not geometry |
| Portal tests | `test_portal.py` (52), `test_extras.py` (46), `test_v12.py` (71), `test_maint.py` (60) | The portal API, security (token, same-origin), tool registry and generated `custom_tools.cfg`, controls and macros, Task Books, maintenance schedule maths, meters | The browser screens themselves |
| Installer test | `dev/test_install.py` (35 checks) | `install.sh`, `uninstall.sh` and the `rhino.sh` menu on a fake Pi (login "tester", an existing config with SAVE_CONFIG, saved variables and a GitHub-backup `.git`; stand-in `sudo`/`systemctl`/`apt-get`; the portal really started from the installed service file): refusals (sudo, job printing, unzipped in the config folder, no printer.cfg, port 5000 taken) change nothing; preview changes nothing; install backs up first, keeps your saved state, `.git` and SAVE_CONFIG (once), rewrites `/home/pi`, starts the portal; update keeps added tools; undo restores exactly; menu options 3 and 4 | Real `apt`, real systemd, the Pi's own Python |
| Browser smoke test | `dev/test_browser.py` (46 checks) | Headless Chromium on the demo portal with a year of maintenance history: every sidebar screen, each tool page, the Add-a-tool wizard, the editor, Details and Log work (saved, then found in the Work log), Mainsail's light theme, a job running, Klipper down, and a phone screen with no sideways scrolling. Fails on any script error or failed request | How the screens look - that's still the screenshots (`dev/demo_server.py`, `dev/maint_year_demo.py`) |
| On-machine | The plan below | Everything above, for real | - |

Run every automated layer with `sh dev/run_all.sh` (570 checks, about three minutes; needs `pip install jinja2 flask`,
for the browser test `pip install playwright && python3 -m playwright install chromium` and, for its accessibility
scan, `npm install --prefix dev axe-core@4.10.2` - without them those parts say SKIP). It runs on every push to GitHub (`.github/workflows/tests.yml`). `python3 dev/test_motion.py --quick`
skips the sweep.

### The motion sweep's safety rules

| Rule | Must always hold |
|---|---|
| R1 | No move Klipper would refuse: past the travel limits, a G-code state that was never saved, or (starting homed) an axis that stopped being homed |
| R2 | Z is never homed with a non-print tool mounted (the probe is on the print heads) |
| R3 | The bed never rises toward a non-print tool, except where that's the point (Set Z zero's Bed up, returning to the cut on resume, the knife's test cut) |
| R4 | The nozzle heater is never switched on with a non-print tool mounted |
| R5 | X/Y are never homed with Z unhomed while a park height is saved (Klipper's `safe_z_home` lowers the bed 10 mm blind, so the saved height goes wrong) |

Findings waiting on a decision are listed in `KNOWN` in `dev/test_motion.py`: they're reported but don't fail the run.
Anything new fails it. When a finding is fixed, the test says so and it comes off the list. Since 1.3.8 the list is empty.

## What to cover, by risk

Highest first. A change to anything in the top rows gets on-machine testing before the release is trusted.

| Risk | Area | Automated | On machine |
|---|---|---|---|
| Crash into the bed or a tool | Homing, park height, `SET_Z_ZERO`, Z restore after restart, tool swap | Positions and limits (motion tests), rules R1-R3 and R5 over every macro (sweep) | B, C, E |
| Tool powered when it shouldn't be | Laser/spindle/relay lockouts, safe-off on cancel, swap and e-stop | Pin values (macro tests), rule R4 (sweep) | C, F, H |
| Job runs in the wrong place | Work offsets (G54), X/Y zero, offsets cleared between jobs | Where file moves land (motion tests) | D2, E6, F |
| Wrong temperature or speed | Preheat, materials, Orca profiles | Prompts and values (macro tests) | D |
| Lost data | Tool registry, maintenance files, installer backups, Klipper-Backup | Registry and maintenance tests | A, I |
| Wrong information shown | Dashboard, maintenance status, pin map | Portal tests, browser smoke test | G |

## Gaps, and what would close them

1. **The Orca profiles are checked by hand** (sliced with the OrcaSlicer command line). Next step: a script that
   slices a test cube and checks the start G-code, first-layer speed and bed size.
2. **The motion tests know limits, not shapes.** They can't tell that a tool is 40 mm long or the stock is 20 mm
   tall; "too close" comes from the rules above and the measured 150 mm park height. Only the machine proves clearance.
3. **Klipper itself never sees the config before you restart.** The first `FIRMWARE_RESTART` (test A2) is the real
   check; keep it the first step after every install. Next step: run Klipper's own config loader in CI
   ([tech-debt.md](tech-debt.md) #3).
4. **No screen-reader pass.** The accessibility checks are automated (axe-core) plus scripted keyboard use; a pass with
   VoiceOver on a phone would catch what they can't.

Closed in October 2026: the simulator now follows the machine position (motion tests and sweep), the portal's
screens are opened in a real browser on every push (browser smoke test, with an accessibility scan), and the
installer runs on a fake Pi (installer test).

## Findings from the motion tests (fixed in 1.3.8)

Found by `dev/test_motion.py` in October 2026; each one now has its own checks in that file, and the sweep's known
list is empty.

| ID | Was | Fix |
|---|---|---|
| M1 | The nozzle height saved by the paper test was applied while `START_JOB` held the file, and Klipper's resume put back the offsets from the moment it was held, so the first layer printed without it | `_RHINO_JOB_GO` re-applies the job's offsets right after the release |
| M2 | Z could be homed with a non-print tool: the old `HOME` macro, `PURGE`, Mainsail's Home buttons | `[gcode_macro G28]` (renames Klipper's to `G28.1`): Z only with a print head confirmed; `G28 X Y` always |
| M3 | `PURGE`, `PREHEAT` and `FILAMENT_CHANGE` heated the nozzle (and `PURGE` moved the bed to Z5) with any tool mounted | `_RHINO_NEED_PRINT_HEAD` at the top of each: refused unless a print head is mounted; filament change also needs X/Y/Z homed |
| M4 | Homing X/Y with Z unhomed lowers the bed 10 mm (Klipper's `safe_z_home`), leaving the saved park height 10 mm off | The `G28` guard adds the 10 mm to the saved height, and refuses if that would pass the end of travel |
| M5 | CNC warm-up/cancel, knife cancel and filament change lifted without a limit check | `_RHINO_LIFT`: same lift, stopped at the end of Z travel |
| M6 | The prime line ended at first-layer height, so the next travel dragged from there | `PRIME_LINE` ends 2 mm up |
| M7 | `ABORT_TOOL_SWAP` / filament-change Cancel with nothing running gave a Klipper error | They say there's nothing to cancel |

## Release checklist

For every version, before the zip is sent:

- [ ] `sh dev/run_all.sh` passes
- [ ] New behaviour has new tests (each fix in `CHANGES.md` names what it changes)
- [ ] Demo portal opens and every screen loads
- [ ] Installer preview (menu option 1) runs clean on the test Pi user
- [ ] `CHANGES.md`, `VERSION` and the manual updated
- [ ] The on-machine tests for whatever changed are listed in `CHANGES.md`

## On-machine acceptance plan (1.3.9)

Work through it in order: later sections rely on earlier ones. Have a hand on the emergency stop for every test that
moves the machine. **Stop if** means stop, don't press on - note what happened and report it.

### A. Install and start

- [ ] **A1 Install.** Menu option 3, pick `rhino-config-1.3.9.zip`, read the preview, install.
  *Pass:* ends with the portal answering on port 5000. *Stop if:* the preview shows STOPPED.
- [ ] **A2 Restart.** With a print head mounted: `FIRMWARE_RESTART`.
  *Pass:* Klipper ready, no config errors.
- [ ] **A3 Tool question.** *Pass:* "Klipper restarted - which toolhead is mounted?" appears; Yes records the tool.
- [ ] **A4** `CHECK_TOOLHEADS` lists every tool without errors.
- [ ] **A5 Portal.** Opens at `http://<pi>:5000`, matches Mainsail's dark/light theme, shows version 1.3.9.

### B. Motion and homing

- [ ] **B1 X/Y distance.** Jog X +100 mm, measure; same for Y. *Pass:* 100 mm ±0.5. *Stop if:* about 50 mm - report it.
- [ ] **B2 Z distance.** Jog Z +10 mm, measure. *Pass:* 10 mm ±0.1.
- [ ] **B3 Home** (`G28`) with BlockOne. *Pass:* homes X, Y, then Z at the probe point, no knocking.
- [ ] **B4** `Z_TILT_ADJUST` finishes within tolerance.
- [ ] **B5 Cancel park.** Start any print, cancel it. *Pass:* bed lowers to Z150 or more, X/Y home, head goes to
  X551 Y381 without touching the frame. *Stop if:* it hits - report the position.

- [ ] **A6 Homing guard** (new in 1.3.8). With LightSaber mounted, press Mainsail's Home All. *Pass:* refused with a
  message, nothing moves; Home X and Home Y work. With BlockOne: Home All homes as before. *Stop if:* the bed rises.

### C. Tool swap safety

- [ ] **C1 Swap BlockOne to LightSaber** (`SWAP_TOOL`). *Pass:* waits until the hotend and bed are below 40 °C,
  lowers the bed to 150 or more, never homes Z, numbered swap window, confirm names LightSaber.
- [ ] **C2 Not detected.** During a swap, confirm with the umbilical unplugged. *Pass:* "Toolhead not detected";
  plug in, Check again works.
- [ ] **C3 Wrong tool.** With LightSaber mounted, start a BlockOne file. *Pass:* refused with "hardware mismatch",
  nothing moves.

- [ ] **C4 Park height after a restart** (new in 1.3.8). Bed parked, `FIRMWARE_RESTART`, answer the tool question,
  swap to another tool. *Pass:* the console says homing X/Y lowered the bed 10 mm and the park height was updated;
  `SET_Z_ZERO` - Yes then shows that height.

### D. Printing (BlockOne)

- [ ] **D1 Nozzle height** (`NOZZLE_HEIGHT_CALIBRATE`). *Pass:* paper drags at the saved height; prime line sticks.
- [ ] **D2 Test cube with the Orca profiles.** The first layer is laid at the paper-test height (fixed in 1.3.8). *Pass:* confirm window, PLA question closes as soon as it's
  answered, 210 °C / 65 °C, prime line drawn, first layer slow (15 mm/s), `END_PRINT` lowers the bed to the park
  height.
- [ ] **D3 Prime line length.** Measure it. *Pass:* about 120 mm. *Stop if:* about half - same cause as B1.

### E. Set Z zero (new in 1.3.6)

With LightSaber or HotJoe mounted:

- [ ] **E1 Window.** `SET_Z_ZERO`. *Pass:* Bed up/down 10, 1, 0.1 mm move the bed that far, the height shown
  follows, and Bed down stops at Z380.
- [ ] **E2 SET.** Bring the material up to the tool tip (laser: focus), press SET. *Pass:* nothing moves; then
  `G1 Z5 F300` lifts the tool 5 mm above the surface.
- [ ] **E3 Restart, bed parked.** Finish or cancel a job (bed parks), `FIRMWARE_RESTART`, run `SET_Z_ZERO`.
  *Pass:* "Bed position" question; Yes - bed doesn't move, X/Y home, then the Set Z zero window opens.
  *Stop if:* the bed moves before you press a Bed button.
- [ ] **E4 Restart, bed not parked.** Move the bed below Z150 in the window, restart. *Pass:* no question - the
  message says to home Z with a print head.
- [ ] **E5 Focus dot** (LightSaber, glasses on). *Pass:* ON shows a faint dot; OFF, SET and Cancel all turn it off.
- [ ] **E6 No carry-over.** After a CNC or drag-knife setup, swap to BlockOne and start a print. *Pass:* the print
  starts where Orca put it - no X/Y shift.

### F. Laser, CNC and drag-knife jobs

- [ ] **F1 Laser** at low power on scrap: `LASER_JOB_SETUP`, focus with Set Z zero, test mark, short file.
- [ ] **F2 CNC air cut:** set Z zero 10 mm above the stock and run the file - it cuts air. Then a shallow real cut.
- [ ] **F3 Drag knife** test line on vinyl: blade cuts, backing intact.
- [ ] **F4 Pause and resume** each tool type. *Pass:* lifts 10 mm, tool off; Resume job brings it back on; the
  spindle reaches speed before it re-enters the cut.

### G. Portal and maintenance

- [ ] **G1 Dashboard** job counts match Mainsail's history.
- [ ] **G2 Log work** on a task; it restarts its schedule and appears in the Work log.
- [ ] **G3 Reminder** after a restart lists overdue and due-soon tasks once.
- [ ] **G4 Remote:** the portal and Mainsail open on your phone through Tailscale.

### H. Emergency stop

- [ ] **H1** With the laser focus dot on: `EMERGENCY_STOP`. *Pass:* laser off at once.
- [ ] **H2** With HotJoe mounted: `EMERGENCY_STOP`. *Pass:* relay opens, ESC stays quiet (no full-throttle spin).

### I. Backups

- [ ] **I1** After `rm -rf ~/printer_data/config/.git`, the next Klipper-Backup push shows your config files in
  `rhino-backup` on GitHub.

Record results in the portal's Work log or in an issue on GitHub, with the test ID (e.g. "E3 failed: bed rose 2 mm").
