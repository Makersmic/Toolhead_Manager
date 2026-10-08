# Testing strategy

How the Rhino tool manager is tested, what each layer can and can't prove, and the on-machine acceptance plan for
each release. Automated tests catch logic mistakes in seconds; only the machine can prove that something moves the
right distance, switches the right pin, or stops when it should. Both are needed.

## The layers

```
            On-machine acceptance          few, slow - the only proof of motion, pins, heat and safety
          Demo portal + screenshots        every screen, with realistic data, in a browser
      Portal and service tests (Flask)     HTTP, registry, generated config, maintenance maths
   Simulated-Klipper macro tests           macro chains, pop-ups, buttons, saved variables
Static lint of every .cfg file             unknown commands, invalid options, bad values
```

| Layer | Tool | What it proves | What it can't prove |
|---|---|---|---|
| Lint | `dev/lint_rhino.py` | Every macro calls a command that exists; options Klipper rejects at start-up (e.g. `description:` in a `delayed_gcode`, soft-PWM `shutdown_value` other than 0/1); pins used twice | That Klipper accepts the whole config on your board |
| Macro tests | `dev/test_macros.py` with `dev/klippersim.py` (178 checks) | Macros render the way Klipper renders them (whole template first), run in order, show the right pop-up and buttons, save the right variables, refuse what they should | Real motion: the simulator records `G1`/`G28` commands but doesn't move. Timing, heaters, pins |
| Portal tests | `test_portal.py` (52), `test_extras.py` (46), `test_v12.py` (71), `test_maint.py` (60) | The portal API, security (token, same-origin), tool registry and generated `custom_tools.cfg`, controls and macros, Task Books, maintenance schedule maths, meters | The browser screens themselves |
| Demo and screenshots | `dev/demo_server.py`, `dev/maint_year_demo.py` | Every screen renders with realistic data in light and dark mode, on desktop and phone | Your Moonraker and your real job history |
| On-machine | The plan below | Everything above, for real | - |

Run every automated layer with `sh dev/run_all.sh` (407 checks; needs `pip install jinja2 flask`). It runs on every
push to GitHub (`.github/workflows/tests.yml`).

## What to cover, by risk

Highest first. A change to anything in the top rows gets on-machine testing before the release is trusted.

| Risk | Area | Automated | On machine |
|---|---|---|---|
| Crash into the bed or a tool | Homing, park height, `SET_Z_ZERO`, Z restore after restart, tool swap | Commands and order (macro tests) | B, C, E |
| Tool powered when it shouldn't be | Laser/spindle/relay lockouts, safe-off on cancel, swap and e-stop | Pin values (macro tests) | C, F, H |
| Job runs in the wrong place | Work offsets (G54), X/Y zero, offsets cleared between jobs | Offset commands (macro tests) | E6, F |
| Wrong temperature or speed | Preheat, materials, Orca profiles | Prompts and values (macro tests) | D |
| Lost data | Tool registry, maintenance files, installer backups, Klipper-Backup | Registry and maintenance tests | A, I |
| Wrong information shown | Dashboard, maintenance status, pin map | Portal tests, screenshots | G |

## Gaps, and what would close them

1. **The simulator doesn't move.** Tests check the command sent (`G1 Z-10.000`), not where the bed ends up. Next
   step: track position in `klippersim.py` (G90/G91, G1, G28, offsets, `SET_KINEMATIC_POSITION`) and assert
   positions and travel limits.
2. **The installer has no automated test.** It's checked by hand with a fake Pi user. Next step:
   `dev/test_install.sh` running `install.sh` and `uninstall.sh` against a temporary home folder with stub
   `sudo`/`systemctl`.
3. **The portal's browser code is only checked by eye.** Next step: a Playwright smoke test that opens each screen
   of the demo portal and fails on any console error.
4. **The Orca profiles are checked by hand** (sliced with the OrcaSlicer command line). Next step: a script that
   slices a test cube and checks the start G-code, first-layer speed and bed size.
5. **Klipper itself never sees the config before you restart.** The first `FIRMWARE_RESTART` (test A2) is the real
   check; keep it the first step after every install.

## Release checklist

For every version, before the zip is sent:

- [ ] `sh dev/run_all.sh` passes
- [ ] New behaviour has new tests (each fix in `CHANGES.md` names what it changes)
- [ ] Demo portal opens and every screen loads
- [ ] Installer preview (menu option 1) runs clean on the test Pi user
- [ ] `CHANGES.md`, `VERSION` and the manual updated
- [ ] The on-machine tests for whatever changed are listed in `CHANGES.md`

## On-machine acceptance plan (1.3.7)

Work through it in order: later sections rely on earlier ones. Have a hand on the emergency stop for every test that
moves the machine. **Stop if** means stop, don't press on - note what happened and report it.

### A. Install and start

- [ ] **A1 Install.** Menu option 3, pick `rhino-config-1.3.7.zip`, read the preview, install.
  *Pass:* ends with the portal answering on port 5000. *Stop if:* the preview shows STOPPED.
- [ ] **A2 Restart.** With a print head mounted: `FIRMWARE_RESTART`.
  *Pass:* Klipper ready, no config errors.
- [ ] **A3 Tool question.** *Pass:* "Klipper restarted - which toolhead is mounted?" appears; Yes records the tool.
- [ ] **A4** `CHECK_TOOLHEADS` lists every tool without errors.
- [ ] **A5 Portal.** Opens at `http://<pi>:5000`, matches Mainsail's dark/light theme, shows version 1.3.7.

### B. Motion and homing

- [ ] **B1 X/Y distance.** Jog X +100 mm, measure; same for Y. *Pass:* 100 mm ±0.5. *Stop if:* about 50 mm - report it.
- [ ] **B2 Z distance.** Jog Z +10 mm, measure. *Pass:* 10 mm ±0.1.
- [ ] **B3 Home** (`G28`) with BlockOne. *Pass:* homes X, Y, then Z at the probe point, no knocking.
- [ ] **B4** `Z_TILT_ADJUST` finishes within tolerance.
- [ ] **B5 Cancel park.** Start any print, cancel it. *Pass:* bed lowers to Z150 or more, X/Y home, head goes to
  X551 Y381 without touching the frame. *Stop if:* it hits - report the position.

### C. Tool swap safety

- [ ] **C1 Swap BlockOne to LightSaber** (`SWAP_TOOL`). *Pass:* waits until the hotend and bed are below 40 °C,
  lowers the bed to 150 or more, never homes Z, numbered swap window, confirm names LightSaber.
- [ ] **C2 Not detected.** During a swap, confirm with the umbilical unplugged. *Pass:* "Toolhead not detected";
  plug in, Check again works.
- [ ] **C3 Wrong tool.** With LightSaber mounted, start a BlockOne file. *Pass:* refused with "hardware mismatch",
  nothing moves.

### D. Printing (BlockOne)

- [ ] **D1 Nozzle height** (`NOZZLE_HEIGHT_CALIBRATE`). *Pass:* paper drags at the saved height; prime line sticks.
- [ ] **D2 Test cube with the 1.3.7 Orca profiles.** *Pass:* confirm window, PLA question closes as soon as it's
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
