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
| Macro tests | `dev/test_macros.py` with `dev/klippersim.py` (190 checks) | Macros render the way Klipper renders them (whole template first), run in order, show the right pop-up and buttons, save the right variables, refuse what they should | Timing, heaters, real pins |
| Motion tests | `dev/test_motion.py` (110 checks, about a minute) | Where the bed and head end up: the simulator follows the position like Klipper (G90/G91, G92, offsets, `safe_z_home`, `SAVE`/`RESTORE_GCODE_STATE`, pause/resume) and refuses moves past `position_min`/`max` or on unhomed axes, with the limits read from `printer.cfg`. Flows: homing, paper test, print, cancel, swap, Set Z zero, Z restore, CNC, knife, laser pause/resume, filament change. Then a sweep of every macro and every button from 7 machine states x 5 tools (about 15,600 runs) against five safety rules (below) | Collisions: it knows the travel limits, not tool lengths or stock height, so "too close" is judged by rules, not geometry |
| Portal tests | `test_portal.py` (52), `test_extras.py` (46), `test_v12.py` (71), `test_maint.py` (60) | The portal API, security (token, same-origin), tool registry and generated `custom_tools.cfg`, controls and macros, Task Books, maintenance schedule maths, meters | The browser screens themselves |
| Installer test | `dev/test_install.py` (38 checks) | `install.sh`, `uninstall.sh` and the `rhino.sh` menu on a fake Pi (login "tester", an existing config with SAVE_CONFIG, saved variables and a GitHub-backup `.git`; stand-in `sudo`/`systemctl`/`apt-get`; the portal really started from the installed service file): refusals (sudo, job printing, unzipped in the config folder, no printer.cfg, port 5000 taken) change nothing; preview changes nothing; install backs up first, keeps your saved state, `.git` and SAVE_CONFIG (once), rewrites `/home/pi`, starts the portal; update keeps added tools; undo restores exactly; menu options 3 and 4 | Real `apt`, real systemd, the Pi's own Python |
| Browser smoke test | `dev/test_browser.py` (46 checks) | Headless Chromium on the demo portal with a year of maintenance history: every sidebar screen, each tool page, the Add-a-tool wizard, the editor, Details and Log work (saved, then found in the Work log), Mainsail's light theme, a job running, Klipper down, and a phone screen with no sideways scrolling. Fails on any script error or failed request | How the screens look - that's still the screenshots (`dev/demo_server.py`, `dev/maint_year_demo.py`) |
| On-machine | The plan below | Everything above, for real | - |

Run every automated layer with `sh dev/run_all.sh` (613 checks, about three minutes; needs `pip install jinja2 flask`,
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

## On-machine acceptance plan (1.5.0)

Work through it in order: later sections rely on earlier ones. Have a hand on the emergency stop for every test that
moves the machine. **Stop if** means stop, don't press on - note what happened and report it.

### A. Install and start

- [ ] **A1 Install.** Menu option 3, pick `rhino-config-1.5.0.zip`, read the preview, install.
  *Pass:* ends with the portal answering on port 5000. *Stop if:* the preview shows STOPPED.
- [ ] **A2 Restart.** With a print head mounted: `FIRMWARE_RESTART`.
  *Pass:* Klipper ready, no config errors.
- [ ] **A3 Tool question.** *Pass:* "Klipper restarted - which toolhead is mounted?" appears; Yes records the tool.
- [ ] **A4** `CHECK_TOOLHEADS` lists every tool without errors.
- [ ] **A5 Portal.** Opens at `http://<pi>:5000`, matches Mainsail's dark/light theme, shows version 1.5.0.
  Switch Mainsail between dark and light twice: *Pass:* the portal follows each switch within 15 s, and at once
  when you click back to its tab.

### B. Motion and homing

- [ ] **B1 X/Y distance.** Jog X +100 mm, measure; same for Y. *Pass:* 100 mm ±0.5. *Stop if:* about 50 mm - report it.
- [ ] **B2 Z distance.** Jog Z +10 mm, measure. *Pass:* 10 mm ±0.1.
- [ ] **B3 Home** (`G28`) with BlockOne. *Pass:* homes X, Y, then Z at the probe point, no knocking.
- [ ] **B4** `Z_TILT_ADJUST` finishes within tolerance.
- [ ] **B5 Cancel park.** Start any print, cancel it. *Pass:* bed lowers to Z150 or more, X/Y home, head goes to
  X551 Y381 without touching the frame. *Stop if:* it hits - report the position.
- [ ] **B5b Cancel a laser job** (new in 1.4.5). LightSaber mounted, start a laser job on cardboard at low power,
  cancel it. *Pass:* laser and rail off at once, bed lowers, **no X/Y homing**, the head goes straight to X551 Y381,
  the job shows cancelled in Mainsail. *Stop if:* X or Y starts homing - report it.
- [ ] **B6 Z travel** (new in 1.4.3: `position_max` 295, measured). Home with BlockOne, `G1 Z290 F600`, then
  `G1 Z300`. *Pass:* Z290 leaves the bed clear of its mounts; Z300 is refused ("Move out of range"), nothing moves.
  *Stop if:* the bed touches a mount at Z290 - send the Z where it's 10 mm clear.

- [ ] **A6 Homing guard** (new in 1.3.8). With LightSaber mounted, press Mainsail's Home All. *Pass:* refused with a
  message, nothing moves; Home X and Home Y work once the Y endstop is set for the LightSaber. With BlockOne: Home All homes as before. *Stop if:* the bed rises.
- [ ] **A7 Positions** (new in 1.4.0). Type `RHINO_POSITIONS`. *Pass:* lists park X551 Y381, swap X100 Y100, safe
  Z150, Set Z zero Z290 (or your own numbers), prime X5 Y10 120 mm, and "All positions are inside the travel limits". Then change
  `park_x` in `myrhino/positions.cfg` to 540, `FIRMWARE_RESTART`, run B5 again: the head parks at X540. Put it back.

### C. Tool swap safety

- [ ] **C1 Swap BlockOne to LightSaber** (`SWAP_TOOL`). *Pass:* waits until the hotend and bed are below 40 °C,
  lowers the bed to 150 or more, never homes Z, numbered swap window, confirm names LightSaber.
- [ ] **C2 Not detected** (works from 1.4.2). During a swap, unplug the umbilical: Klipper keeps running (the nozzle
  reads about -50 °C). Confirm with it still unplugged. *Pass:* "Toolhead not detected"; plug in, Check again
  works. Swapping to a print head: its extruder motor only gets power after Check again succeeds.
- [ ] **C5 Heater guard** (new in 1.4.2). With LightSaber mounted, type 200 in Mainsail's nozzle temperature box.
  *Pass:* refused with "only for print heads", the heater stays off.
- [ ] **C3 Wrong tool.** With LightSaber mounted, start a BlockOne file. *Pass:* refused with "hardware mismatch",
  nothing moves.

- [ ] **C4 Park height after a restart** (new in 1.3.8). Bed parked, `FIRMWARE_RESTART`, answer the tool question,
  swap to another tool. *Pass:* the console says homing X/Y lowered the bed 10 mm and the park height was updated;
  `SET_Z_ZERO` - Yes then shows that height.

### D. Printing (BlockOne)

- [ ] **D1 Nozzle height** (`NOZZLE_HEIGHT_CALIBRATE`). *Pass:* paper drags at the saved height; prime line sticks.
- [ ] **D2 Test cube with the Orca profiles.** The first layer is laid at the paper-test height (fixed in 1.3.8). *Pass:* confirm window, PLA question closes as soon as it's
  answered, 210 °C / 65 °C, prime line drawn, first layer slow (15 mm/s), `END_PRINT` lowers the bed to the park
  height, then the head goes to the park spot X551 Y381 (1.4.4; it went to X0 Y200 before).
- [ ] **D3 Prime line length.** Measure it. *Pass:* about 120 mm. *Stop if:* about half - same cause as B1.

### D, continued. SwitchFly materials and the end of a job (new in 1.4.6)

With SwitchFly mounted, its nozzle height set (D1), and both paths loaded:

- [ ] **D4 Path question.** Start a SwitchFly file from Orca or Studio (it names one material, e.g. PLA on path 1).
  *Pass:* the file is held and "Path 2 (T1) material?" appears, showing "Path 1 (T0): PLA" and the materials for
  the nozzle; nothing moves after homing. Pick the one loaded in path 2.
  *Stop if:* the print starts before you answer.
- [ ] **D5 Confirm shows both.** *Pass:* the confirm window lists Path 1 (T0) and Path 2 (T1) with what you chose,
  and "Prints from: path 1 (T0)". Proceed: the usual PLA bed question, heating, prime line, print.
- [ ] **D6 Same as last time.** Start the same file again. *Pass:* "Same as last time (<your path 2 material>)" is
  the first button; it goes straight to the confirm window. After `FIRMWARE_RESTART` it is still offered.
- [ ] **D7 Cancel at the path question.** Start the file, press Cancel. *Pass:* job shows cancelled, nothing heats.
- [ ] **D8 SWITCH_T0/T1 by hand.** Machine idle and homed: type `SWITCH_T1`. *Pass:* retracts, moves the selector
  servo, heats to path 2's material, loads and purges using the material from D4 (the console says
  `MATERIAL=<it>_0_4_T1`), with no "defaulting to PLA". Then `SWITCH_T0 MATERIAL=NYLON`: *Pass:* refused with the
  list of materials, nothing moves.
- [ ] **D9 End of job, extras keep running.** Add a test item ticked "switch off when made safe" (or use your
  exhaust fan) and switch it on. Finish a short print normally. *Pass:* the heaters go off, the head parks, and that
  item is **still on**. Then start a print and cancel it: *Pass:* cancel switches it off. Repeat the normal finish
  with LightSaber (low power, scrap): *Pass:* laser and rail off at the end, the item still on.

### D, continued. The material record follows the tool (new in 1.4.7)

Install `rhino-config-1.4.7.zip` first. Have a bin under the nozzle and a hand near the emergency stop.

- [ ] **D10 SwitchFly back on, selector left on path 2.** With SwitchFly mounted, `SWITCH_T1` (path 2). Swap to
  BlockOne, then back to SwitchFly and press *Confirm - SwitchFly is installed*. *Pass:* you hear the selector turn,
  the console says it turned to path 1 (T0), `variables.save` shows `set_material_extruder_index = 0`. Heat, then
  `M83` and `G1 E5 F120`: filament goes **in** on path 1. *Stop if:* the selector doesn't move, or filament comes out.
- [ ] **D11 Restart, Yes.** With SwitchFly on path 2 (`SWITCH_T1`), `FIRMWARE_RESTART`, answer *Yes - SwitchFly is
  mounted*. *Pass:* the selector doesn't move and the record still says path 2; heated, `G1 E5` feeds **in**.
- [ ] **D12 BlockOne after SwitchFly path 2.** From D11, swap to BlockOne and confirm. *Pass:* the record says
  BlockOne, path 1; heated, `G1 E5` feeds **in**. *Stop if:* filament comes out.

### N. Network settings (new in 1.4.8)

Install `rhino-config-1.4.8.zip`. Use Rhino Studio, Settings / Network. Before N5-N7, make sure you could reach the
Pi another way if needed (keyboard and screen, or the router's device list). **Stop if** anything doesn't switch
back by itself within about 2 minutes.

- [ ] **N1 Read.** *Pass:* name, Wi-Fi interface with its address, signal and power saving show; nothing changes.
  `sudo -l` on the Pi lists only `/usr/local/sbin/rhino-net` for the Rhino line.
- [ ] **N2 Power saving off, Keep.** *Pass:* a 2:00 countdown appears; Keep ends it; `iw dev wlan0 get power_save`
  says off.
- [ ] **N3 Undo now.** Turn power saving on, press Undo now. *Pass:* back to off.
- [ ] **N4 Let it run out.** Turn it on and wait. *Pass:* after about 2 minutes it is off again by itself.
- [ ] **N5 Rename.** Rename to `rhino`, open `http://rhino.local:5000/net` from your PC, press Keep. *Pass:* the
  new name answers; Rename back to `mainsailos` the same way.
- [ ] **N6 Fixed address.** Give `wlan0` a fixed address outside your router's DHCP range. *Pass:* Studio loses
  the Pi (expected), `http://<new address>:5000/net` shows the change, Keep works. Then set it back to Automatic.
- [ ] **N7 A wrong address.** Give `wlan0` a fixed address on a network you don't have, e.g. `10.9.9.50/24` with
  gateway `10.9.9.1`, and don't keep it. *Pass:* Studio loses the Pi, and within about 2 minutes the Pi is back on
  its old address by itself. *Stop if* it isn't back after 5 minutes.
- [ ] **N8 During a print.** Start a print. *Pass:* changes are refused ("Not while a job is running").


### P. PrusaSlicer on the Rhino (new in 1.5.0)

Install `rhino-config-1.5.0.zip`, then use Rhino Studio. Keep `htop` open in an SSH window. **Stop if** Klipper reports
"Timer too close" or shuts down, or a print stutters while slicing.

- [ ] **P1 Install the engine.** Settings / Software, PrusaSlicer, Install. *Pass:* asks first, takes a few minutes,
  then shows the version and Up to date. `ls ~/printer_data/rhino_data/prusaslicer` shows the version and `current`.
- [ ] **P2 It runs without a screen.** `~/printer_data/rhino_data/prusaslicer/current/AppRun --help-fff | head` over SSH.
  *Pass:* prints options, including `--threads` and `--center`. *Stop if:* it complains about a display or a missing
  library - report the message.
- [ ] **P3 Slice.** Prepare a small part with PrusaSlicer, BlockOne, PLA. *Pass:* progress shows, time and filament
  appear, every check passes, `htop` shows `prusa-slicer` at nice 19.
- [ ] **P4 Forced values.** Open the sliced file. *Pass:* it starts with `START_JOB`, uses the material's
  temperatures, has `M83`, and no `M104`/`M140` above 0 or `G28` of its own.
- [ ] **P5 Cancel and newer wins.** Change a setting while it slices. *Pass:* the old `prusa-slicer` goes from `htop`
  and a new one starts; only one runs at a time.
- [ ] **P6 Cache.** Prepare again with nothing changed. *Pass:* back at once.
- [ ] **P7 During a print.** Start a print, then Prepare a bigger part. *Pass:* 4 GB+ host slices with about half the
  cores and the print keeps going smoothly; Pi 3B refuses, saying why.
- [ ] **P8 Update and keep previous.** When a newer release is out, Update. *Pass:* the new version shows, the old
  folder is still there, and slicing works.

### E. Set Z zero (new in 1.3.6)

With LightSaber or HotJoe mounted:

- [ ] **E1 Window.** `SET_Z_ZERO`. *Pass:* Bed up/down 10, 1, 0.1 mm move the bed that far, the height shown
  follows, and Bed down stops at Z290.
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
  *Pass (fixed in 1.4.1):* the file cuts; when it ends (with `END_PRINT`) the laser is off. *Stop if:* the head moves
  through the file without marking - report it.
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
