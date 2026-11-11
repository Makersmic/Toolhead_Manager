# What changed

## 1.9.29 - Signed releases, the Portal checks its own name, console fixes

Rhino Studio 0.25.0. No Klipper config changes. From the November 2026 audit (`docs/audit-2026-11.md`, M1-M5).

- **Signed releases.** Every release zip comes with a `.sig` (ed25519, made by the release workflow with Mike's
  key). The root-owned updater installs only a zip whose signature checks out against the key built into it; the
  Portal keeps nothing unsigned, and *Install from zip* in Studio takes the zip and its `.sig` together or one after
  the other. *Update* fetches both from GitHub. Releases before 1.9.29 have no `.sig`, so they install by hand
  (`rhino.sh` option 3); *Go back* skips them. `dev/sign_release.py --new-key` makes a key; the secret is
  `RHINO_SIGNING_KEY`.
- **The Portal refuses a change that arrives under a name that isn't this machine's** (`rhino/portal/hosts.py`): its
  hostname, any `.local` name, an IP address, `*.ts.net`, or a name in Moonraker's `cors_domains`. This closes DNS
  rebinding, where a web page's own name is pointed at the Rhino so the Origin check and the token both pass. The
  message says where to add a name of your own.
- **Studio's console reads lines the way Klipper does:** a leading line number (`N1 G28`) no longer hides the command;
  quoted values count (`MACRO="SWAP_TOOL"`); and `G28.1`, `M104.1`, `G1.1` (the raw commands behind the Rhino's
  wrappers) always ask and say which check they skip.
- **README › Security** rewritten to say what anyone Moonraker trusts can do, and what is in place.

## 1.9.28 - The start wizards in the manual and Help

Rhino Studio 0.24.1. No Klipper config changes.

- **Manual and Help:** *Running a job* starts with Studio's start wizard for the laser, drag knife and CNC, step by
  step, with what the Rhino refuses and why. *Tuning a laser or drag knife* explains setting the laser's Z zero from
  the tuned focus height and the knife's test cut. Job setup's note points to the wizard, and engrave values now say
  they feed the Engrave fill operation.
- **Help in Studio:** the **?** on the start wizard opens its section of *Running a job*.

## 1.9.27 - Start CNC jobs from Studio

Rhino Studio 0.24.0. Klipper macros change (below): restart Klipper after installing.

- **Studio's start wizard for the HotJoe.** Start on a CNC file opens it: the setup's checklist, X/Y zero on the stock's
  corner with the jog panel, Set Z zero (Klipper's window), the outline traced 5 mm above the stock with the spindle off
  (offered), the warm-up at a throttle (±5 %, Stop always there), then the start. Each step asks first. Older configs
  keep the prompt chain.
- **Macros** (`dev/proposal_cnc_start.py`, applied): `CNC_JOB_SETUP FROM=STUDIO` runs the same checks and starts straight
  away, refused without the HotJoe's Z zero or with the spindle stopped. `_CNC_WARMUP QUIET=1` checks the lid before
  the spindle starts; `_CNC_SAVE_XY QUIET=1` and `_CNC_ADJUST_SPEED QUIET=1` leave out the windows. Without FROM=STUDIO
  / QUIET=1 nothing changes.

## 1.9.26 - Spindle tuning, bits and laser operations

Rhino Studio 0.23.0. No Klipper config changes.

- **Laser operations** (Studio, Job setup › Settings): cut, score and engrave fill, each with its own power, speed
  and passes, for loops picked by clicking them on a drawing of the job. They run in the order you set; Studio warns
  when a cut frees a part before work inside it. Everything not picked is cut last with the job's own settings.
  Fills start from the tuned engrave values.
- **Spindle throttle** now reads the same on Control, the Dashboard and the CNC setup's prompt: 0.6 is 60 %, and
  30 % is stopped.
- **Bits** (Studio: Assets › Parts › Bits): the spindle's bits kept on the Rhino in `myrhino/lists.json`: name, end mill
  or ball, diameter, flutes, cutting length, a note. Job setup's CNC panel picks one and fills the tool fields.
- **Spindle tuning** (Tune HotJoe): True diameter (one slot you measure with the caliper's inside jaws: the bit's real
  cutting width, runout included), Feed (five slots, feed stepped, with the throttle the setup ran at) and Depth per
  pass (five slots, deeper each time). Each runs through CNC_JOB_SETUP like any CNC job. Kept in `tuning.json` per bit
  (diameter) and per bit and material (the rest); Job setup starts a CNC job from them when you pick the bit.
- **Care: "Run the spindle in"** for a new spindle or after a long idle, in the CNC spindle book.

## 1.9.25 - Start laser and knife jobs from Studio

Rhino Studio 0.22.0. Klipper macros change (below): restart Klipper after installing.

- **Studio's start wizard for laser and drag knife jobs.** Start on a LightSaber or DragKnife file opens it: the
  setup prompts' checklist, Set Z zero (Klipper's own window; with a tuned focus height, the presses to reach it), the
  outline traced 5 mm above the zero with the tool off (offered), the test fire or test cut, then the start. Each step
  asks first. Older configs keep the prompt chain.
- **Macros** (`dev/proposal_studio_start.py`, applied): `SET_Z_ZERO` remembers which tool its zero is for, and a tool
  swap or restart clears it. `LASER_JOB_SETUP` / `DRAGKNIFE_JOB_SETUP FROM=STUDIO` run the same checks, then start
  straight away, and refuse without that zero. `_LASER_TEST_FIRE QUIET=1` / `_DK_TEST_CUT QUIET=1`: the same test, no
  prompt after it (the knife's needs its zero). `_DK_XY_ZERO`: the knife's G54 lines, shared. Without FROM=STUDIO
  nothing changes.
- **Studio's console** now asks before any `*_JOB_SETUP` line (a job start) and `SET_Z_ZERO` (it moves the bed).
- **Manual: Tuning a laser or drag knife**, a new chapter after Tuning a print head (PDF and Help): the seven tests,
  how each runs, what to pick, and how Job setup starts from the results. The ? on a LightSaber or DragKnife Tune page
  opens it.

## 1.9.24 - Help in Rhino Studio

Rhino Studio 0.21.0. No Klipper config changes.

- **Help in Rhino Studio** (Settings › Help, and a **?** in the top bar that opens the chapter for the screen you're on):
  the user manual as web pages, served by the Rhino itself, so it works with no internet and always matches the
  installed version. Contents, search across every section, Previous and Next, and a link to the printable PDF.
  Made from the same chapters as the PDF by `manual/web.py` (36 chapters, 3.1 MB with web copies of the pictures);
  the release copies them into Studio as `help/`. nginx answers a missing Help page with a 404.
- **Studio's Built with** names Claude (Opus 5.5), who wrote code, tests and docs alongside Mike.
- Tests: `dev/test_help.py` (Help matches the manual's sources, nothing in it can run, under 6 MB); backup and install
  tests pass on a desktop PC (Arch) as well as GitHub's runner.

## 1.9.23 - Laser and knife tuning

Rhino Studio 0.20.0: laser and drag knife tuning, Job setup from tuned values, and the wizard rhino. No Klipper config changes.

- **Laser tuning** (Assets › Toolheads › LightSaber › Tune): focus height (a ramp that lifts from 1 mm above the
  touched surface, ticks every millimetre), cut and engrave grids of power and speed, passes, and kerf from a measured
  20 mm part. Each test is a normal job through LASER_JOB_SETUP, checked like any prepared file before it's sent.
- **Drag knife tuning**: depth (six lines, with the pressure dial noted) and blade offset (five squares).
- **The Portal keeps them** in myrhino/tuning.json: focus height and blade offset once per tool, the rest per tool and
  material (no nozzle). Same revisions, history and backup as the print head results.
- **Job setup starts from tuned values**: a laser job takes the tuned cut power, speed, passes and kerf for its tool and
  material; a knife job takes the tuned depth and blade offset. A job saved for the same file keeps its own values. A
  note under the settings says what's tuned and offers Use tuned values after an edit. Engrave values aren't used yet.
- **The wizard rhino** (Studio): Mike's rhino crew beside every wizard step: Add hardware, Add a toolhead and every
  tuning test.
- Proposal, not applied: `docs/proposal-studio-start.md` (start laser and knife jobs from Studio's start wizard).

## 1.9.22 - Camera sound fix

Rhino Studio 0.19.2. No Klipper config changes.

- **Camera sound installs on Debian's ffmpeg** (1.9.21 on the 7050: "sound skipped: This ffmpeg has no Opus encoder").
  It has one: the check stopped reading ffmpeg's long encoder list early, and the script's own error handling counted
  that as a failure. The list is now read whole first (the same for go2rtc's answer). The test's stand-in ffmpeg now
  prints a full-length list, and fails the old check exactly as the 7050 did.
- **Settings › Cameras › Edit** (Studio): the preview is a 16:9 picture again, a little bigger, with the same space
  above and below; the panel is no taller than the form.

## 1.9.21 - The install sets up the camera sound

Rhino Studio 0.19.1. No Klipper config changes. Haven't run on a real machine yet: MIC1-MIC4 in docs/testing.md.

- **Camera sound comes with the install** (Mike, Nov 9): when a USB camera with a microphone is plugged in, the
  install sets up ffmpeg, go2rtc and the `rhino-mic` service by itself (`docs/install-mic.md`). go2rtc 1.9.15 now
  comes inside the release zip (fetched and checked against the pinned checksum when the release is built, MIT licence
  beside it), so nothing is downloaded from GitHub on the Rhino; ffmpeg still comes from Debian. It never stops the
  install: anything missing is skipped with a note and a log. It stays out of the config folder (and its backups).
  Undo takes it away again if that install added it.

## 1.9.20 - Job setup and camera changes; the camera's microphone

Rhino Studio 0.19.0. No Klipper config changes. Haven't run on a real machine yet: JS1-JS6, PV8, CM1-CM2 and SND1 in
Studio's docs/testing.md, and MIC1-MIC4 below.

- **Job setup** (Studio): parts cards lie over the left of a full-width 3D view; where a print touches the plate
  shows green; the support controls moved into Settings, at the top of each engine's Support section; PrusaSlicer's
  sections fold; a Prepare button ends Settings; the job file's name can be changed before sending, and Start job sits
  in the row with Send, Preview and Download.
- **Preview** draws the same white plate as Job setup.
- **Cameras** (Studio): Settings › Appearance sets each of the Dashboard's and Control's camera to fill or show the
  whole picture, and its zoom. The camera edit preview is as tall as the form.
- **The camera's microphone** (optional, `docs/install-mic.md`): `scripts/rhino_mic.sh install|status|remove` puts
  in ffmpeg, go2rtc 1.9.15 (pinned, checksum checked) and a low-priority `rhino-mic` service; Studio's nginx site
  passes `/mic/webrtc` (POST, home network, one fixed stream) to it. Studio plays it on the Dashboard with mute and
  volume. Sound only: the cameras' pictures don't depend on it. Not installed by the menu.

## 1.9.19 - Studio on the bare address; host health; own pause, resume and cancel

Rhino Studio 0.18.1. One Klipper config change: `printer.cfg`'s first line. Haven't run on a real machine yet: run
BA1-BA4, HS1 and MC1-MC4 in docs/testing.md and HH1-HH4 in Studio's.

- **`http://rhino.local` opens Rhino Studio** (installer). Mainsail moves to port 8090 as a spare until it is removed
  (Mike, Nov 9). Only the port-80 `listen` lines of Mainsail's own nginx site change; the site as it was goes into the
  install's backup, and undo puts it back. nginx is reloaded only after `nginx -t`, and if Studio doesn't answer the
  bare address afterwards, Mainsail's site is put back by itself. `RHINO_MAINSAIL_PORT` picks another port.
- **Settings › Host health** (Rhino Studio, Portal `GET /api/host/stats`). Each core's load over the last ten minutes,
  temperature and clock; the package temperature, load average and how long programs waited for a core, memory or the
  disk; memory, swap and free space; the Rhino's own programs (Klipper, Moonraker, the Portal, cameras, nginx,
  PrusaSlicer) and the busiest others with the core each runs on and the cores it may use; each board's load, resent
  bytes and round trip; the services; every other temperature sensor. "What to look at" lists anything out of the
  ordinary in plain words, and Copy report / Download put every reading in a text file for troubleshooting. Read only.
- The install's closing steps name Studio instead of Mainsail.
- **Pause, resume and cancel no longer need Mainsail installed** (`docs/proposal-own-client-macros.md`, approved
  Nov 9). `printer.cfg` includes `client_mainsail.cfg`, a pinned, credited copy of mainsail-config's `client.cfg`
  (GPL-3.0, Alex Zellner), instead of `mainsail.cfg`. It is the machine's own `mainsail.cfg` byte for byte (md5
  checked), so every macro runs exactly as before; the Rhino's hooks in `client_macros.cfg` are unchanged. The installer
  says whether your `mainsail.cfg` matches the copy and never edits either file. The health check (menu option 7) checks
  the include. **Once Mainsail is removed, don't undo past 1.9.19**: older `printer.cfg`s include `mainsail.cfg`.

## 1.9.18 - Tuning test files upload; lead screws drawn evenly

Rhino Studio only; no Klipper config changes. Haven't run on a real machine yet: run TU7 in Studio's docs/testing.md.

- **Tuning tests upload again** (Rhino Studio). The first-layer squish, pressure advance and extrusion multiplier
  wizards' Make the test failed with "Upload failed: HTTP 500" when `gcodes/tuning/` didn't exist yet: Moonraker only
  makes a missing folder from the upload's folder field, not from a folder in the file name. Studio now sends the
  folder separately, and a failed upload shows Moonraker's reason.
- **Bed › Configuration** (Rhino Studio). The lead screws are drawn by place (front left, rear centre ...), not to
  scale, with same-size label cards and a key. A screw whose motor is off says "motor off" (Klipper also switches
  motors off when idle), not "released". Home and level reads "NO Z_TILT PERFORMED SINCE RESTART" before any Z-tilt.

## 1.9.17 - Tuning applied from the Rhino; Bed › Configuration

Rhino Studio 0.18.0. These changes pass the automated tests (macros in the simulator, not real Klipper) but haven't run
on a real machine yet: run TA1-TA5 below and BC1-BC6 in Studio's docs/testing.md.

- **Tuned values: stored if there is one, else the default** (Klipper macros, Rhino Studio). The tuning wizards' results
  are now stored on the Rhino as save variables (`rhino_rd_<head>`, `rhino_pa_<head>_<material>_<nozzle>`,
  `rhino_em_<head>_<material>_<nozzle>`), and Klipper applies them, so every job gets them whichever slicer made the
  file. At job start, SET_PRINT now sets the extruder from scratch (`_RHINO_APPLY_TUNING`): the head's tuned rotation
  distance, and the material's tuned pressure advance and flow (M221), or printer.cfg's values and 100 % where nothing
  is tuned. Nothing carries over from the last job any more (before, a tuned flow or rotation distance stayed set
  until Klipper restarted). A SwitchFly path change applies its material's values the same way.
- **CALCULATE_PA uses the tuned value when there is one** and works it out as before when there isn't, saying which in
  the console. In a job it uses the head, material and nozzle START_JOB checked, so a slicer naming the filament
  differently (PLA+ for PLA) still gets PLA's value, with a console note that the names differ. With no head known (the
  tool slot isn't mapped) it calculates and says why; TOOLHEAD= names one by hand. A material it has no estimate for
  uses its base (PLA-CF as PLA), or keeps printer.cfg's value instead of stopping the job. A stored value out of range
  is ignored and reported. Studio-prepared files now carry only the CALCULATE_PA line; Studio's Tune page offers to
  store results saved before this version ("Not on the Rhino yet").
- **Extruder calibration pushes 100 mm as two 50 mm moves** (Rhino Studio). Klipper's default
  `max_extrude_only_distance` (50, which the Rhino keeps) refused one 100 mm move. No printer.cfg change.
- **Bed › Configuration** (Rhino Studio). The rail's Bed mesh is now Bed, with Bed mesh and Configuration. Configuration
  draws the bed with each Z lead screw from `[z_tilt]` and moves the ticked ones on their own (FORCE_MOVE, red padlock,
  up to 5 mm a step) or releases them to turn by hand, for when Z_TILT_ADJUST faults out because the bed is too far
  off level. Z is marked not homed and the saved park height dropped before anything moves. Home and level runs
  Z_TILT_ADJUST and shows each pass. Checks BC1-BC6.

## 1.9.16 - Print head tuning wizards

Rhino Studio 0.17.0. These changes pass the automated tests but haven't printed on a real machine yet: run TU1-TU6 in
Studio's docs/testing.md, in order, watching each test print.

- **Print head tuning wizards** (Rhino Studio, Portal), after Ellis' Print Tuning Guide. A print head's page has **Tune**:
  the tests in his order, each saying why it comes there. **Extruder calibration** is the first: it walks through
  marking and pushing 100 mm (asks first), works out the rotation distance, repeats until two runs agree, and saves it
  for that head. Results are kept on the Rhino (`config/myrhino/tuning.json`, backed up after every save, restorable on
  its own); prints Studio prepares use them after START_JOB. printer.cfg isn't changed. The page's **Tuning** panel shows
  which tests have been run, per material. **First-layer squish** prints five patches around the bed and lets you
  move the nozzle closer or farther live (behind the padlock); Keep saves it as that head and material's fine-tune
  over the paper test, which START_JOB already applies. **Pressure advance** prints Ellis' pattern (corner columns at
  stepped values); pick the sharpest, Refine for finer steps, and prints use it instead of the CALCULATE_PA estimate.
  **Extrusion multiplier** prints a row of cubes at stepped flow with Ellis' judging tips on screen; prints get the
  saved flow as M221 after START_JOB, whichever slicer. Checks TU1-TU6.

## 1.9.15 - Paint support marks; see under the part

Rhino Studio 0.16.0. These changes pass the automated tests but haven't run on a real machine yet: check SM5 in
Studio's docs/testing.md, and the plate from below on a real screen.

- **Paint support marks** (Rhino Studio). In Job setup's Mark supports, a ring in the theme's accent shows where support
  would go as you point at the part; click to mark, or press and drag to size the mark. Click a mark to select it and
  change its size or remove it; Erase marks wipes them by dragging. Marks are painted on the part's underside and shown
  as rings through it, so they're visible from above. Check SM5.
- **See under the part** (Rhino Studio). Settings › Appearance › 3D view sets how see-through Job setup's white build
  plate is when you look from below (75 % to start).

## 1.9.14 - Job setup in five steps, supports coloured in Preview

Rhino Studio 0.15.0. These changes pass the automated tests but haven't run on a real machine yet: check Job setup's
steps on the 7050 and Preview with a theme applied.

- **Job setup in five steps** (Rhino Studio): File, Process, Setup, Preview, Job file. Preview is now a step of Job setup
  (it prepares the file when the setup changed) and Job file (checks, Send, Start) its own; move between Setup, Preview
  and Job file without losing anything. Files' Preview still opens the full page.
- **Supports stand out in Preview** (Rhino Studio): the model in the theme's own colour, supports in its second one (a
  lighter tint in the plain look).
- **Macro fields keep what you type** (Rhino Studio): a number in the macro editor no longer jumps back while you type.

## 1.9.13 - Your macros, start and end G-code; white fields and build plate

Rhino Studio 0.14.0. These changes pass the automated tests but haven't run on a real machine yet. The checks to run are
MB1-MB8 in Studio's docs/testing.md; MB6 is the first real print with a start G-code: watch the first layer.

- **Your macros** (Rhino Studio, Portal). Settings › Your macros builds short routines from steps: home, move to, move by,
  set a temperature, heat for a material, part fan, wait, run one of Klipper's macros, a message, and (if you turn it on)
  one line of G-code. They're saved on the Rhino (`config/myrhino/user_macros.json`, in backups, restorable on their own)
  and run from Control › System Macros through the console's own check: moves ask first, heat-only doesn't. Building
  refuses a job running, the wrong or an unconfirmed toolhead, unhomed axes, moves past the travel and a hotend without
  a print head; M112, SAVE_CONFIG, restarts, SET_KINEMATIC_POSITION, FORCE_MOVE and SET_STEPPER_ENABLE are refused even
  as a G-code line. Three starters: park the head, heat for PLA, cool down. Checks MB1-MB5, MB8.
- **Start and end G-code from your macros** (Rhino Studio, Portal). A toolhead's page picks a macro as its start G-code
  (after START_JOB homes and heats) and end G-code (before END_PRINT cools and parks). The steps are copied into the
  tool's job hooks; when the macro changes, the page offers Update. Job setup says which run. Live after a Klipper
  restart. Checks MB6, MB7.
- **Fields are white** (Rhino Studio). Every field you type into or pick from is white with dark text in day, night and
  every theme; a locked one is light grey.
- **A white build plate** in Job setup's 3D view, with grey grid lines.

## 1.9.12 - A 3D rhino on the hologram; PrusaSlicer fields fixed

Rhino Studio 0.13.0. These changes pass the automated tests but haven't run on a real machine yet. The checks to run
are HG4 and HG5 in Studio's docs/testing.md.

- **PrusaSlicer settings keep what you type** (Rhino Studio). In Job setup, a PrusaSlicer field jumped back to its old
  value while you typed, because the live machine status kept redrawing it. It now holds what you type until you leave
  the field or press Enter.
- **The hologram's rhino is 3D** (Rhino Studio). An original rhino made in Studio itself: one smooth, see-through
  turquoise skin with folds at the shoulders, hips and neck, a hump, wrinkled legs and face, and horns that grow out of
  the head. During a print it trots at the front of the dial. When the print finishes it runs up the right side going
  away, across the back and down the left side head-on, then faces you, rears, hops and stands proud. Settings > Style
  guide shows it large, to turn and play. Check HG4.
- **The hologram turns again after you touch it** (Rhino Studio). A click or drag stops the turn; it starts again
  3 seconds after you let go. Check HG5.

## 1.9.11 - Typefaces, the Dashboard hologram, supports where you mark; PrusaSlicer 2.9.7 slices again

Rhino Studio 0.12.0. These changes pass the automated tests, but none has run on a real machine yet. The PrusaSlicer fix
was checked on 2.8.1 and against a stand-in for 2.9.7's fault, not on 2.9.7 itself. Block supports for PrusaSlicer are
built but hidden: small blocks had no effect in PrusaSlicer. The checks to run are in docs/testing.md (P10, SM1-SM4,
SJ1-SJ3, HG1-HG3, TH5).

- **Supports only where you mark them** (Rhino Studio, Kiri:Moto). Job setup > Supports: Off, Automatic or Only where I mark.
  With marks, **Mark supports** and click the part above where it needs holding up: the mark goes on the overhang below,
  and Kiri builds support there and nowhere else. Overhangs are tinted amber while supports are on. Marks follow the part
  when it's turned or moved, and are saved with that file's job. The Portal now keeps a job's `supportMarks`, checked:
  at most 500, each a part name, a point and a reach of 0.5-50 mm. Check SM1-SM3 in Studio's `docs/testing.md`.
- **The job as a hologram** (Rhino Studio). While a job runs, the Dashboard shows its outer walls as turquoise light over the
  camera: done, the layer being made now, and still to make, with a dial for progress, speed and material, a scan line,
  and a little rhino. It reads the job's file once per job, and asks first over 40 MB. Checks HG1-HG3.
- **Several files at once in Job setup** (Rhino Studio): the ones that fit become parts of one job; the rest are named.
- **Start a job from Job setup** (Rhino Studio). After Send to Rhino, the "Sent as" line has **Start job**: the same check and
  confirm as Files, or **Swap to <tool>** when another tool is mounted. Studio then opens Control. While a job runs there is no
  Start, only **Open in Files**: nothing queues. Checks SJ1-SJ3.
- **Supports where you mark them, with PrusaSlicer too** (Rhino Studio, Portal). One Supports control for both engines. With
  PrusaSlicer, marks go to the Portal with the part and become support enforcers in the project PrusaSlicer slices. Check SM4.

- **PrusaSlicer 2.9.7 slices again.** Flathub's 2.9.7 misread Studio's empty per-filament start template and every slice
  failed with "Failed to process the custom G-code template start_filament_gcode". The Portal now sends it as one empty
  template, the way PrusaSlicer saves it. Check P10.
- **PrusaSlicer's test slice uses Studio's settings.** After an install or update, the test slice now loads the same empty
  templates and forced values as a real slice, so a build that can't take them fails its test and the old one is put back.
- **A failed slice says why.** The message names the template and the parse error instead of PrusaSlicer's closing lines.

- **Choose the typefaces** (Rhino Studio). Settings > Appearance > Typefaces sets a font for category titles, subcategories and
  regular text, from 16 open-licensed fonts inside Studio, so no internet is needed. Sizes don't change. Big numbers, positions,
  the console and Stop keep their own fonts. Check TH5.

## 1.9.10 - Several parts in 3D, built-in themes and background pictures; safer backups

Rhino Studio 0.11.0. These changes pass the automated tests, but most haven't run on a real machine yet, including the
BACKUP_CFG change, a print or cut with several parts, and the themes on a kiosk. The checks to run are in docs/testing.md.

- **23 built-in themes** (Rhino Studio). Settings > Appearance > Theme: Cold Cache, Sudo Plum, Bubblegum Segfault, Jungle
  Grep and more, each with a day and a night look. Stop, Cancel and unlocked panels look the same in all of them. Check TH4.

- **Place parts in 3D** (Rhino Studio). Print jobs open on a 3D bed: drag the part, turn it on any axis, or lay it flat by
  clicking a face. It warns if the part is off the bed, too tall, or over a keep-out. Laser, knife, CNC and ready-made
  files can switch between the view from above and 3D. Checks PW1-PW6 in Studio's `docs/testing.md`.
- **Saved jobs can hold a tilted part.** The Portal now accepts `tiltX` and `tiltY` in a job's placement, checked like its
  other values. Plain jobs are saved exactly as before.
- **Several parts in a job** (Rhino Studio). Print, laser and knife jobs can hold several parts: Add file, or drop one on the
  bed. A list beside the bed shows each part, and the selected one has an outline. Each has its own position and way up, and
  all share the job's settings. Overlapping parts warn but don't block. A CNC job stays one part. Checks PW7-PW10.
- **Right-click menu on a part** (Rhino Studio): Duplicate, Lay flat, Centre, Reset way up and Delete from job. Long-press on a
  phone, or the ⋯ in the list. Right-drag still pans. A duplicate goes 5 mm to the right, else the next free spot.
- **Themes can set their own style** (Rhino Studio). As well as a panel's background, text and border, a theme can now set filled
  buttons, the selected colour, control edges, titles, big numbers and the page, top bar and rail. Stop, Cancel and the unlocked
  red panel never change. Existing themes look as they did. Check TH1.
- **`BACKUP_CFG` no longer stops a print.** The GitHub push ran while Klipper's G-code queue waited, which left the head
  stopped on the part. During a job, or if the job state can't be read, the backup and push now wait until the job is over,
  and several requests make one backup. A failed push shows in Studio, not the console. The wait now lasts up to 7 days,
  not 12 hours. Check B3.
- **One GitHub push at a time.** `BACKUP_CFG`, Back up now and the backup watcher now take turns.
- **Background picture options and a text colour** (Rhino Studio). A background picture can fill the page, fit, stretch, show at actual size or tile. Appearance also sets one text colour across the screen, for day and night separately. Checks TH2, TH3.
- **Toolhead photos are now in Rhino backups.** The backup only took files at the top of the images folder, and photos sit in
  one folder per tool, so no backup ever held them, and a restore couldn't bring them back. Take a new backup after updating.
- **Background pictures for themes.** Studio can show a picture behind the page. The Portal keeps up to 12, checked like photos,
  outside the config folder, and they're backed up with the photos.
- **Health check: no more false VERSION failure.** It looked for a file the installer leaves out, so every install showed
  "No VERSION" and `tool manager ?`. It now reads the version from the installed program files.
- **Health check: reads the config Klipper loads.** It follows `printer.cfg` and its includes, not every `.cfg` in the folder.
  The boards line no longer lists a board twice, and a leftover copy naming an old board can't fail the check.

## 1.9.9 - 3D G-code preview; one backup per burst of changes

- **3D Preview** (Rhino Studio 0.10.0). Files and Job setup can now open a G-code file in 3D, with layer and move
  sliders. Printed moves are drawn at their real width and lit from one side. Start job, Send to Rhino and Download sit
  beside the drawing, and go through the same checks as everywhere else. The preview itself sends nothing to the
  machine. It uses three.js (MIT). Checks PV1-PV7 in Studio's `docs/testing.md`.
- **The backup watcher no longer floods the host.** klipper-backup's watcher ran one whole backup and push per file
  event, in turn, so installing an update queued hours of backups, a commit for each, and kept the host busy. Tool
  Manager now runs its own watcher in its place: changes in a burst make one backup a minute after they stop, and a
  steady stream still gets one every 15 minutes. rsync's temporary files no longer count as changes. klipper-backup's
  own files aren't touched: it's a systemd override, and uninstalling takes it away. Check BW1-BW4.
- **Changes during a job are no longer skipped.** The old watcher dropped them until something else changed. They're
  now backed up once when the job is over, and nothing runs while it prints or is paused.
- **The Care meters no longer start a backup.** `meters.json` saves about every 5 minutes, which meant up to about 288
  commits a day and more wear on the SD card. It now goes up with the next backup something else starts, so GitHub's
  copy of the meters can lag behind. Local archives still include them. Check BW5.
- **The move version is now 1.9.9** (`docs/migrate-7050.md`): the Pi and the 7050 both run it.

## 1.9.8 - A failed GitHub push no longer shows as pushed

- **The GitHub backup line tells the truth.** klipper-backup can exit normally after git has failed, and the Portal
  trusted that exit code. On one machine, a corrupt local copy stopped every push for 19 days while the status said
  OK. A push now counts only if git reported no errors, the latest commit can be read, and that commit reached GitHub.
  Otherwise Studio and `BACKUP_CFG` say the push failed and give the reason. Check B2b.
- **The move version is now 1.9.8** (`docs/migrate-7050.md`): the Pi and the 7050 both run it.

## 1.9.7 - Large models prepare; job saves no longer clash

- **Large models prepare** (Rhino Studio). Prepare built the job file with one call per line, so a real-sized model
  (a 4 MB sphere is hundreds of thousands of lines) failed with "Maximum call stack size exceeded". A 10 mm cube
  never showed it. Check LM1.
- **Saving a job's settings no longer clashes.** Studio saves a new file's settings under its toolhead and under its
  file name at the same instant. The Portal wrote both through one shared temp file with no lock, so one save failed
  ("Couldn't save the job on the Rhino: Unexpected error"), a job could be lost, and the jobs file could be left
  unreadable. Slice profiles and saved jobs now change one at a time, each write uses a temp file of its own and is
  flushed to disk before it replaces the old one. The job hooks file and the restart flag get their own temp files
  too. Check LM2.
- **The move version is now 1.9.7** (`docs/migrate-7050.md`): the Pi and the 7050 both run it.

## 1.9.6 - Edit wizard hardware; job hooks editor in Studio

No Tool Manager code change: this release carries Rhino Studio's new screens.

- **Edit hardware added with the wizard** (Assets › System hardware › Edit). Its answers, pins and settings are
  filled in; its own pins are offered again; Save replaces it. The kind can't change (remove it and add the new one).
  The Portal refuses an edit that would break a job hook. Checks HE1-HE2.
- **Job hooks editor** (Assets › Hardware › Job hooks): pick the whole machine, a kind of tool or one tool, then one
  line per moment of the job (before and when it starts, before and after it ends, cancel, pause, resume). **Save**
  only after **Check** has passed for exactly what's typed; the Portal checks every line again. Checks HK1-HK2.

## 1.9.5 - Health check, ready for the move

- **Health check** (`rhino.sh` option 7, `scripts/rhino_doctor.py`): read-only checks of this host, with PASS / WARN
  / FAIL and what to do. It checks the board connected by its serial name, the camera, Klipper, Moonraker, the Portal and
  nginx, `job_hooks.cfg` and `custom_tools.cfg` included, `mainsail.cfg`, NetworkManager, clock sync, disk space,
  sleep (a desktop PC that suspends stops a job), backups and klipper-backup. It saves a report; option 7 compares
  the newest with an earlier one (the Pi's before the move, the 7050's after). `docs/migrate-7050.md` §0.7, §3.4, §8.
- **Tests:** real Klipper now reads the config (`dev/test_real_klipper.py`): Klipper's own batch mode, on the
  shipped config and on one the Portal filled with a second board, every wizard device and job hooks, then every
  macro once. The **move drill** (`dev/test_move.py`) backs up a used "Pi", restores it on a freshly installed
  "7050" with another host name, and goes back again. Both are in `dev/run_all.sh`.
- **Hardware a job hook uses can't vanish under it.** Removing or renaming a wizard device or a piece of system
  hardware, or taking away the macro a hook calls, is refused and names the hook. Before, `job_hooks.cfg` would
  have called a command that was gone, and every job start would have stopped on it. Hooks that were already broken
  don't block unrelated changes. Check HC0b.
- `AGENTS.md` (and `CLAUDE.md` pointing to it): the rules for anyone, person or AI, changing this repository.
  README brought up to date.

## 1.9.4 - Check now finds a new release straight away

- **Settings › Software › Check now** re-checks GitHub for a new Tool Manager release, not just Moonraker's
  software. Before, the Portal answered from its hourly check, so a release published since could take up to an hour
  to show. Check now asks GitHub at most once a minute (GitHub allows 60 unsigned requests an hour); opening the
  page still uses the hourly answer.
- **Rhino Studio: the Toolheads tab is now Assets**, with three groups: Toolheads (Library, Tool connector, Kinds of
  tool), Hardware (System hardware, Board pins and outputs) and Parts (Materials, Nozzles, Categories, each on its own
  page). Old Toolheads bookmarks still open the right page.

## 1.9.3 - Control › Hardware and macro values (Rhino Studio)

No Tool Manager change; this release carries the newer Rhino Studio:

- **Control › Hardware:** each piece of system hardware with the control that fits it. Fans, dimmers and lights get a
  slider and a % field; switches Off / On; servos an angle; heaters, spindles and laser-style power sit behind the red
  padlock. Fans Klipper runs itself, interlocks, sensors and temperatures are shown read-only.
- **Macro buttons that take values** (DRIVER_FAN_SET SPEED=...) show a small sliders icon and ask for the values
  first, with a slider when the macro states a range, and the exact line before it's sent.
- On-machine checks: Rhino Studio docs/testing.md HC1-HC5.

## 1.9.2 - 4-wire fans at 25 kHz

- **A PWM cycle of 0.00004 (25 kHz) is accepted.** Both the Add hardware wizard and the System hardware form had a
  0.00005 minimum, so a 4-wire fan couldn't be set the way the Rhino's own part fan runs (`pin: !PA8`,
  `cycle_time: 0.00004`). The minimum is now 0.00001, and the value is written as `0.00004`, not `4e-05`.
- **A 4-wire fan's speed input can be on a fan header**, as the part fan is: only the header's − pin goes to the blue
  wire, + stays unconnected, and the signal is inverted. The wizard used to refuse this; it now warns until
  "inverted" is ticked.

## 1.9.1 - Fans: 2, 3 and 4 wires

- **Every fan the wizard adds asks how many wires it has.** 3 and 4 wires can read the fan's speed back (its yellow
  wire, `tachometer_pin` with the pull-up written for you). A 4-wire fan's blue speed input goes on a logic pin (a
  MOSFET header is refused there), with an optional fan header as its power (`enable_pin`) so it really stops at 0 %.
  The speed input can be marked inverted for a transistor in between. Pulses per turn and the PWM cycle are settable;
  Klipper's 10 ms default is kept unless you change it.
- Driver, hotend, temperature, exhaust and plain fans all get this. Plain fans and hotend fans now go through the
  wizard too.
- With Rhino Studio: fans with a speed signal show their rpm on the Dashboard, and a fan driven at 30 % or more that
  reads nothing for 10 s shows "<name> fan isn't turning" in red.
- The interlock and filament-sensor notes in the wizard no longer say they're waiting for review (they're live since 1.9.0).

## 1.9.0 - Add hardware, job hooks, interlocks

- **Add hardware wizard (Portal side).** Rhino Studio's new wizard asks five questions: what it is, where it's
  wired, which tools it's for, what turns it on and off, where it shows. 24 kinds of hardware so far: driver and
  temperature fans, a chamber heater (capped at 120 C, always switched off at the end of a job, on cancel and on a
  swap), temperature readouts, door / flame / pressure / VFD-fault inputs, spindles (relay or PWM), coolant, air
  assist, dust collection, vacuum tables, exhaust fans, LEDs and strips, filament runout and jam sensors, an extra
  motor. Coolant and air can follow M7 / M8 / M9.
- **Pins that can do the job.** The pin picker only offers free pins that suit the hardware: MOSFET headers for
  loads, analog pins for thermistors, never a MOSFET for an input, never a PNP sensor straight to a pin. Header names
  and analog pins come from Klipper's own board configs.
- **A second control board** (`[mcu name]`, USB or CAN): BTT EBB36/42, EBB SB, SKR Mini E3 v3, SKR Pico, Pi Pico, an
  Octopus, or "other board". Its pins appear in every picker as `name:PIN`. Klipper won't start while it's unplugged.
- **Job hooks.** Lines that run before or after the Rhino's start and end, on cancel, pause and resume, for the
  whole machine, a tool category or one tool. Saved in `myrhino/job_hooks.json` (with history, in the backup).
  Nothing moves before homing, every command must exist, heater targets stay within limits, and cancel turns off
  anything a hook turned on.
- **Interlocks: must be closed to start.** A door or lid interlock stops a laser or spindle job (and the laser test
  fire) from starting while it's open, and resume waits until it's closed. A flame sensor and a pressure switch can be
  required too.
- **Filament sensors only with a print head**, so a laser or CNC job never pauses for "runout".
- **The macro change** (approved, `docs/proposal-macro-hooks.md`): calls only, in START_JOB, the four *_JOB_SETUP
  macros, the laser test fire, _START_JOB_FILE, END_PRINT, _RHINO_CANCEL, the pause and resume hooks, and the
  tool-swap confirm. They call three generated macros in the new `myrhino/job_hooks.cfg`, which always exists and
  is kept by the installer like custom_tools.cfg.

## 1.8.2 - Smaller backups

- **Backups leave out zip files in the config folder, and the manual PDF.** The zips are installer uploads
  (`rhino-config-*.zip` and the like). Every release is on GitHub, and klipper-backup skips them too. The PDF comes
  with every install. On the Pi this takes a backup from about 133 MB to about 20 MB. Restore is unchanged: those
  were never settings.

## 1.8.1 - Back up now's GitHub copy

- **Back up now** passed its note to klipper-backup the wrong way, so klipper-backup refused to run and the
  GitHub copy showed as failed. It's now sent as `--commit_message`. BACKUP_CFG wasn't affected: its push
  carries no note.
- **Backups are now named `rhino_studio_os-<date>.zip`**, without the host name (the Pi's was mainsailos). The
  host is still recorded inside each backup. Older `rhino-<name>-<date>.zip` backups still list, upload and restore.

## 1.8.0 - Slice profiles, kept on the Rhino

- **Slice profiles** live on the Rhino in `config/myrhino/slice_profiles.json`, so the backup and klipper-backup
  include them. A cleared browser, another device or a new host no longer loses your settings. Each profile is
  one engine's own settings (Kiri:Moto or PrusaSlicer); nothing is translated between engines.
- **Job setup** (Rhino Studio 0.9.0, inside this zip) has a profile picker, a line saying whether the settings
  are saved on the Rhino, and Save to profile / Save as new / Reset. Each file and toolhead remembers its
  profile plus only the settings you changed, in `rhino_data/prepare_jobs.json` (in the backup zip, not on GitHub).
- **Settings › Slice profiles**: rename, notes, the last 5 revisions with Go back, delete (Bring back for
  30 days), export and import.
- **No silent overwrites:** a save from an out-of-date copy is refused ("changed on another device").
- **Restore** has a new item, "Slice profiles and saved Prepare jobs".
- **The first time** Studio finds settings this browser saved before 0.9.0, it offers once to bring them to the Rhino.
- **Rhino Studio UI:**
  - the red padlock on Motion, Speed and Flow
  - Speed and Flow are now foldable panels, and Flow and pressure advance need the padlock
  - console input on top with the newest line first
  - the camera card is level with Motion
  - the hostname moved to Settings › Host
  - Update says "Updating…" until it's done
- **Nothing here talks to Klipper:** profiles and jobs never send G-code.

## 1.7.0 - Back up now, and restore

- **One complete backup of the Rhino**, kept on the Rhino in `~/rhino-backups` (the last 10). It holds the config
  folder, Moonraker's whole database (job history and totals, Studio and Mainsail settings, made by Moonraker
  itself), job history and every settings namespace as readable files, the toolhead photos, and a manifest with a
  checksum for every file. **It's complete or it's refused:** if anything that should go in can't be read, nothing is
  kept and the message names what was missing.
- **Back up now** is in Studio › Settings › Host › Backups (Rhino Studio 0.8.0, inside this zip). That panel also shows the age of the last
  backup and whether klipper-backup's GitHub copy really worked; it never says "pushed" when it didn't. You can
  download any backup from there.
- **BACKUP_CFG** now makes that backup first, then runs klipper-backup as before. After a long job, END_PRINT's
  BACKUP_CFG makes the backup as soon as the job is over (Moonraker won't copy its database mid-print).
- **Restore** one thing (maintenance, the tool registry and lists, Studio settings, or photos) or everything. You see
  what changes before anything does, and a backup of how things are now is always made first.
  - A full restore needs the machine's name typed and only runs when idle.
  - It stops before changing anything if the backup's board isn't connected to this host.
  - It leaves Tool Manager's own program files as installed.
- **Moving to a new host:** add the old host's backup ("Add a backup from another Rhino"), then restore everything.
  The backup is checked file by file before it's listed.
- New tests: `dev/test_backup.py` (47). On the machine: B1-B6.

## 1.6.2 - Update from GitHub works

- **Releases now publish themselves.** No release had ever been published on GitHub, so Studio's Update button had
  nothing to download and told you to fetch the zip by hand. Now, when a new version reaches main, GitHub builds the zip
  (with Studio inside) and its .sha256 and publishes the release a few minutes later. There's nothing to run by hand.
  Update in Studio › Settings › Software then installs it, the same way Install from zip does.
- **Rhino Studio 0.7.2.** If main has a newer version whose release isn't published yet, Update says so and doesn't tell
  you to download a zip.
- Nothing changed in the Klipper config or the macros.

## 1.6.1 - Lists that fit a snapped window

- **Rhino Studio 0.7.1.** Files and Job history no longer squeeze the file name down to a letter when the window is
  snapped to half the screen. The date, size and last run now sit in small type under the name instead of in their own
  columns. On Files, **the toolhead pill is the Start button**: ▶ starts the file (with the same check and confirm as
  before), ⇄ starts the tool swap when the file needs another tool, and "No toolhead ▶" covers files that don't say which
  tool they need. Sorting (Name · Modified · Size) is in the header. On a narrow list, the toolhead moves under the name.
  Job history shows how each job ended, when it started, the printing time and the filament under the file name, with a
  Reprint button.
- New design notes (not shipped in the zip): docs/decisions.md, docs/parked.md, docs/invariants.md and
  docs/phase0-spine.md (the backup inventory and the plan for slice profiles).
- Nothing changed in the Klipper config or the macros.

## 1.6.0 - Bed mesh

- **Bed mesh is on** (`[bed_mesh]` in printer.cfg): probe area X40 Y40 to X500 Y300, 5 × 3 points (the old example's
  values, well inside the bed and every point reachable with the probe's 20, 5 offset). **Check it on the machine (BM1)**
  before relying on it. Studio 0.7.0's Bed mesh page shows and makes meshes.
- **`RHINO_MESH_CALIBRATE PROFILE= BED= SOAK= TILT=`** makes a mesh the way it should be made: print heads only (the
  probe is on them), never during a job; homes if needed, heats the bed and lets it soak (default 5 min), levels the
  gantry (Z_TILT_ADJUST), probes. Bad names, adaptive- names, a bed over its max_temp and soaks over an hour are refused
  before anything moves.
- **Each mesh is recorded** in variables.save (`mesh_meta`: bed temperature, head, time), because Klipper keeps none of
  that and the bed changes shape as it heats.
- **A print loads the mesh made at its bed temperature** (within 5°C; `variable_match_c` in RHINO_MESH). Klipper stopped
  loading a mesh at start-up a while ago, which quietly gives uncompensated first layers. With no mesh for that
  temperature the start asks, with the file held: probe one now, use the closest, print without, or cancel. Nothing is
  probed before you answer. A mesh made this way is saved as `bed-<temp>`; it stays until Klipper restarts unless you
  save it (Studio, or SAVE_CONFIG) after the job.
- **The spindle never cuts with a bed mesh**: its Z zero is set on the material, so a mesh would change the cut depth.
  SET_Z_ZERO switches the mesh off for a CNC tool, and a spindle job with a mesh loaded again since stops (spindle off
  first). Laser and drag knife keep the mesh.
- `RHINO_MESH_REMOVE PROFILE=` removes a mesh and its record; `RHINO_MESH` lists the meshes with their temperatures.
- The simulator (dev/klippersim.py) models bed_mesh; the lint knows the bed_mesh commands and options. Older job-start
  tests run with saved meshes so they test what they always did.
- New tests: `dev/test_mesh.py` (57). On the machine: BM1-BM9.
- Studio 0.7.0 in the zip.

## 1.5.8 - Update from GitHub; PrusaSlicer keeps itself up to date

- **Update from GitHub.** Studio's Settings › Software › Rhino Tool Manager › Update now downloads the newest release from
  GitHub on the Rhino (`POST /api/update/github`) and installs it with the same root-owned updater as Install from zip.
  The zip must match the `.sha256` published next to it and pass the same zip check as an upload; only the version
  GitHub names as newest is accepted. GitHub is asked at most once an hour (`GET /api/update` → `latest`).
  **Install from zip stays** for a downloaded zip or a Rhino without internet.
- **Releases are built by GitHub** (`.github/workflows/release.yml`): push a tag `v<VERSION>` and Actions builds Rhino
  Studio, makes `rhino-config-<VERSION>.zip` with Studio inside, its `.sha256`, and the release with this file's notes.
- **Rhino Studio isn't listed separately** any more when it's served by the Rhino: it comes in the Tool Manager's zip,
  so the Tool Manager row names the Studio inside.
- **PrusaSlicer keeps itself up to date while you use it** (on by default, a tick box on its row). Every 6 hours the
  Portal looks at Flathub; it updates only if PrusaSlicer is installed, you've sliced with it in the last 30 days, no
  job is printing and nothing is slicing. The update is the normal one: test slice, and the old version put back if it
  fails. After you press Go back it won't reinstall the version you left, only a newer one. The last automatic update
  is shown on the row.
- New tests: GH1-GH10 (test_updater), AU1-AU12 (test_prusa).

## 1.5.7 - Studio 0.6.5

- Studio 0.6.5 in the zip: every page fits a browser snapped to half a screen (Board pins and outputs and Tool
  connector ran off their panels), and the top bar's Stop button stays whole at every window width.
- Nothing else changed since 1.5.6.

## 1.5.6 - Packages that vanished from Debian (bullseye after its end of life)

- Debian 11 "bullseye" left long-term support on 31 August 2026. A Pi's package lists can still name a version that
  security.debian.org no longer serves (avahi-utils 0.8-5+deb11u3: "404 Not Found"), and avahi's packages must all be
  the same version, so neither `apt update` nor an older avahi-utils helps.
- **The install now fetches such a package from snapshot.debian.org** (`scripts/rhino_snapshot_deb.py`), which keeps
  every file Debian ever published. The version and its SHA256 come from the Pi's own package lists, which apt has
  already checked against Debian's keys; the file is used only if its SHA256 matches. Anything else: not installed.
- If even that fails, the note links `docs/install-avahi-by-hand.md` (the same steps by hand) instead of advice that
  doesn't help. avahi-utils still never stops an install.
- New tests: `dev/test_snapshot.py` (6) and three installer cases.
- Longer term: move the Pi to Debian 12 "bookworm" (security support until June 2028).

## 1.5.5 - Notes from the first day on 1.5.4

- **Studio 0.6.4** in the zip: scrolling install and update logs, a status bar under the install log, camera previews
  about 2.5x larger.
- **The install log keeps 400 lines** for Studio to scroll through (was 60). The whole run is still in
  `rhino_data/update/install-<version>.log`.
- **Settings › Network on a bullseye Pi** no longer says "NetworkManager isn't running" as if something were wrong. It
  says the network is run by dhcpcd (the normal setup on Raspberry Pi OS and MainsailOS before bookworm), that Studio
  can show it but not change it, and to use `sudo raspi-config` for Wi-Fi or the address.

## 1.5.4 - trusted_clients, as Mainsail: the Portal follows it, the install and Studio can add to it

Rhino Studio 0.6.3 works like Mainsail: no login, Moonraker's `[authorization] trusted_clients` decides who may
connect. The Portal now follows the same list, so port 5000 is never a way around it.

- **Every `/api` request asks Moonraker about the same address** (`rhino/portal/access.py`, Moonraker's `/access/user`
  with the address in `X-Real-IP`). From nginx the address is the browser's; straight to port 5000 it is the peer's own,
  so nobody on the LAN can claim a trusted address with a header. Untrusted: 401 naming the address and saying to add
  it to `trusted_clients`. Answers kept 60 s (refusals 5 s).
- **No `[authorization]` in moonraker.conf: nothing changes.**
- **Moonraker down:** if it has ever refused someone (`rhino_data/moonraker_trust_seen`), the Portal refuses with 503
  rather than guess; otherwise it works as before.
- The Portal's own reads (job state, meters, restart) still need 127.0.0.1 trusted, as KIAUH sets it up.
- Pages, photos and static files aren't checked; they change nothing.
- **The install adds what this Rhino needs to `trusted_clients`** (`scripts/rhino_trust.py ensure`), only when
  `[authorization]` exists (without it Moonraker trusts everyone, and adding the section would lock screens out) and only
  what isn't covered yet: `127.0.0.0/8` (the Portal's own reads), this Rhino's LAN range, and `100.64.0.0/10` when
  Tailscale is up. KIAUH's default list already covers the first two, so most installs add nothing.
- **Settings › Trusted addresses in Studio** (`/api/moonraker-trust`): see the list, add an address or range (Tailscale's
  `100.64.0.0/10` is offered), remove one. Only from a screen that's already trusted, never during a job, never the entry
  that lets the screen itself or the Portal in, never wider than /8, never a name.
- Both edit `trusted_clients` and nothing else in moonraker.conf (`rhino/trust.py`): the new text must read back with
  the new list before it's written; backup first (`rhino_data/config_backups`, or the install's backup); same owner and
  mode; Moonraker restarts through its own API (no sudo) and if it doesn't answer within 45 s the old file goes back.
- **avahi-utils no longer stops an install.** It's only for the `rhinostudio.local` name, so when it can't be installed
  (a Pi with stale package lists got "404 Not Found" for it from Studio's Install from zip) the install goes on and
  just skips the name; Studio still opens at `:5001`. Any apt failure now refreshes the package lists once and tries
  again, even if `apt-get update` complains about a retired source; required helpers (rsync, unzip) still stop the
  install if they can't go in, before anything changes.
- New tests: `dev/test_access.py` (12 checks) and `dev/test_trust.py` (33), in `dev/run_all.sh`.

## 1.5.3 - 2 GB boards, updates from Studio, rhinostudio.local, pin labels

- **2 GB boards are offered PrusaSlicer.** A "2 GB" board reports about 1850-1950 MB to Linux, so 1.5.2's 2048 MB
  line refused them. The line is now 1800 MB (`SMALL_HOST_MB`); a Pi 3B (~906 MB) is still not offered it.
- **Install a new zip from Rhino Studio.** Settings > Software > Install from zip: drop `rhino-config-<version>.zip`,
  see what it is, press Install. A small root-owned updater (`/usr/local/sbin/rhino-update`, started only by
  `rhino-update.path` when the Portal drops a request) checks the zip again, refuses during a job, runs BACKUP_CFG if you
  have it, installs with `install.sh --unattended` (backup first, as always), records the version and sends
  FIRMWARE_RESTART. The Portal never gets sudo (its service keeps `NoNewPrivileges`). The zip installed and the one
  before are kept, so Studio offers **Go back**. Set up by this install, so 1.5.3 itself goes in once by hand.
- **Open Studio at `http://rhinostudio.local`**, no port to remember (`:5001` keeps working). Two pieces, both put in
  by the install and both taken out by Undo:
  - a second copy of Studio's nginx site on port 80 that answers **only** that name
    (`/etc/nginx/sites-available/rhino-studio-name`). It never claims `default_server`, so Mainsail keeps the bare
    address and every other name. As in 1.5.1, nginx is only reloaded after `nginx -t`; on top of that the install
    compares the page the host's bare address shows before and after, and takes the name site out again if it
    changed. Port 80 held by something other than nginx: skipped with a note.
  - `rhino-studio-name.service` (runs as your login, not root) asks avahi to announce `rhinostudio.local` for the
    host's address, and follows the address if DHCP changes it. The host's own name (`rhino.local`, `mainsailos.local`)
    is untouched. A host already named `rhinostudio` needs no service. No avahi-daemon (Ubuntu Server out of the
    box): the install says the one line to run (`sudo apt install avahi-daemon avahi-utils`); it never installs the
    daemon itself. If avahi-daemon runs but its tools are missing, `avahi-utils` is installed with the other helpers.
  - The Portal needed no change: nginx passes the browser's Host, so its cross-site check sees `rhinostudio.local` on
    both sides. Moonraker's own same-origin check passes the same way.
  - Some Android phones don't resolve `.local` names; use the address with `:5001` there.
- **Pin labels: names for board pins, as Klipper aliases.** Kept in the registry (`custom_tools.json` "labels") and
  written as `[board_pins rhino]` into the generated `custom_tools.cfg`, which printer.cfg always includes and an update
  never overwrites. Any section can then say `pin: ENCLOSURE_LIGHT` (with `!` / `^` as usual); moving the light is one
  change to the label. Rhino Studio shows them on Toolheads › Board pins (pick a free pin, save, the old pin shows under
  it). Routes: `POST /api/pins/label` (add, or change with "original"), `POST /api/preview/pins/label`,
  `DELETE /api/pins/label/<alias>` (refused while something uses it), `POST /api/pins/label/use`.
  - **Use a label** rewrites exactly one `key: pin` line in one of your files to the label (prefix and comment kept),
    after copying the file to `rhino_data/config_backups` (newest 20 kept); it's read back the way Klipper will, and
    put back if the section doesn't resolve to the same pin. Paths outside the config folder and the generated file
    are refused.
  - **System hardware can sit on a label** (Studio's Scan Config picks one): its section says `pin: <label>`, the label
    lists it as a user, and moving the label moves the hardware. A labelled pin can't be taken by its raw name.
  - Aliases in your own `[board_pins]` sections are listed read-only. Fixed: named `[board_pins <name>]` sections
    (Klipper allows several) were not read at all, so their pins counted as unknown.
  - Nothing restarts Klipper; every change waits in the restart banner as before. Tests: `dev/test_labels.py`.
- **Slicing during a job needs 4 GB** (`PRINT_SLICE_MB` = 3000 MB): a 2 GB board waits for the job to end, as the
  Pi 3B did, and a slice running when a job starts is stopped. 4 GB and up slice alongside a job, niced and watched.

Tests: `dev/test_studio_site.py` runs the name site in real nginx next to a Mainsail stand-in holding
`default_server` (only `rhinostudio.local` reaches Studio; the bare address and other names still get Mainsail; the
Portal and Moonraker see the name as Host). `dev/test_install.py`: the name site and service filled in, port 80 held
by something else, the bare address's page changing (site taken out), no avahi, host already named, bad name, undo.
Fixed on the way: looking for nginx on port 80 now follows `sites-enabled` links (`grep -R`). Check on the machine:
**S8-S12** and **U1-U6** (`docs/testing.md`).

## 1.5.2 - PrusaSlicer comes from Flathub

- **Fixed: Install said "No PrusaSlicer build for this processor".** Prusa no longer puts Linux builds on GitHub; its
  only official Linux build is the Flatpak on Flathub (`com.prusa3d.PrusaSlicer`). The 1.5.0 installer looked for an
  AppImage on GitHub, so it failed on every processor, not just ARM. The engine now installs, updates and runs
  through Flathub, for x86-64 and 64-bit ARM.
- **One step by hand, once:** the host needs Flatpak (`sudo apt install flatpak` over SSH). The Portal never runs sudo;
  until Flatpak is there, Studio's Software row says exactly that instead of offering Install.
- **Per-user and sandboxed.** The engine goes in for the Portal's login only (`flatpak --user`, under
  `~/.local/share/flatpak`). Each slice runs in Flatpak's sandbox with no network, no display and no files but its
  own job folder.
- **Hosts under 2 GB of memory (a Pi 3B) aren't offered the engine**: Studio says so and names Kiri:Moto in the
  browser, which still slices there. An engine already on a small host keeps working, within the old limits.
- **Every install and update is test-sliced** (a 20 mm cube, in the sandbox, exactly as a real slice) before it's
  used. If an update can't slice, the version before is put back by itself. **Go back** in Studio does the same by
  hand (`flatpak update --commit=`; it needs Flathub to still hold that build).
- **Cancel and the memory watchdog follow the whole process tree.** `flatpak run` starts bubblewrap, which can start
  the slicer in a session of its own; stopping only the process group could leave it running. Unchanged: nice 19,
  ionice idle, thread cap, half the cores during a print, one slice at a time, cache, forced safety options.
- New route: `POST /api/slicer/engine/rollback` (token-checked). `GET /api/slicer` adds `source`, `install_phase`,
  `blocked` and `previous`; nothing was removed, so Studio 0.6.0 still works (it just shows less).
- The old AppImage download, its checksum check and the unpacked engine folders are gone; old
  `~/printer_data/rhino_data/prusaslicer/<version>` folders from 1.5.0-1.5.1 can be deleted by hand.

Tests: `dev/test_prusa.py` now drives a stand-in `flatpak` (no flatpak missing, small host, 32-bit ARM, install,
update, a broken update undone, go back, no build on Flathub, sandbox flags, cancel killing a slicer in its own
session, memory counted over the tree, routes). Check on the machine: **P0-P9** (`docs/testing.md`).

## 1.5.1 - Rhino Studio served from the Rhino

- **New: open Rhino Studio from any PC, phone or tablet at `http://<pi>:5001`**, with nothing to install on it. The
  zip now carries a build of Rhino Studio (0.6.0); the installer puts it in `~/rhino-studio` and adds an nginx site
  of its own on port 5001 (`/etc/nginx/sites-available/rhino-studio`, from `service/rhino-studio.nginx`). The nginx
  that serves Mainsail serves it; **Mainsail's own site is not touched**.
- The site forwards what Studio needs, as the dev server on a PC does: Moonraker (its port read from
  `moonraker.conf`, sent the way Mainsail's site sends it), crowsnest's cameras (`/webcam/` to `/webcam4/`) and
  `/portal` to the Portal. Slicer uploads up to 210 MB; G-code uploads go to Moonraker unlimited, as in Mainsail.
- **It can't take Mainsail down:** nginx is only reloaded (never restarted) after `nginx -t` accepts the new site;
  if it doesn't, the site is taken out again and the install says why. No nginx, port 5001 taken, or a zip without
  Studio: that step is skipped with a note, and the rest of the install carries on. Studio still runs from a PC.
- **Undo** (menu option 4) puts back the Studio folder and site from before that install, or removes them.
- The menu shows where Studio is served. Updating the Tool Manager updates Studio.
- `dev/make_zip.sh ../rhino-studio` builds the release zip with Studio in it (`studio/` is never committed).
- No Klipper config, macro or Portal code changed.

Tests: `dev/test_install.py` (Studio files, site, backup and undo, nginx refusing the site, port taken, no Studio),
`dev/test_studio_site.py` (the site in a real nginx: Studio's files, Moonraker and websocket headers, Portal Host
and Origin, upload limits, cameras, WebAssembly type).
Check on the machine: **S1-S7** (in Rhino Studio's `docs/testing.md`), and that Mainsail still opens.

## 1.5.0 - PrusaSlicer runs on the Rhino, for Rhino Studio

- **New: slicing service** in the Portal for Rhino Studio's Prepare. Studio sends the part (as STL) and only the
  PrusaSlicer settings you changed; the Portal slices with **PrusaSlicer** on the host and hands back the G-code,
  which Studio turns into a Rhino file and checks as before. Kiri:Moto in the browser stays available.
- **The Rhino's safety values are forced here too.** The Portal rebuilds the settings file itself: unknown names are
  dropped, and start/end G-code, temperatures, G-code flavour (klipper), bed shape, nozzle, relative E, scripts and
  substitutions are always the Rhino's, whatever was sent. Labelling objects for `EXCLUDE_OBJECT` and arc moves
  (G2/G3) are refused unless `[exclude_object]` / `[gcode_arcs]` are in the config.
- **Slicing gives way to the printer.** One slice at a time (a newer request stops the older one), run at the lowest
  CPU and disk priority (`nice 19`, `ionice idle`), with a thread count and a memory cap watched over the whole
  process group:
  - idle: all cores but one, up to 70% of memory (and always 768 MB left over);
  - while a job prints or is paused: half the cores, 40% of memory;
  - small hosts (under 2 GB, e.g. a Pi 3B) don't slice during a job, and stop a slice if a job starts.
  The 8 most recent results are kept, so slicing the same thing again comes back at once.
- **Engine in the update manager.** Rhino Studio, Settings / Software has a PrusaSlicer row: Install, or Update when a
  newer stable release is out (checked every 6 hours). It installs the official Linux (arm64/x86-64) release
  unpacked into `~/printer_data/rhino_data/prusaslicer/<version>`, checks the download's sha256 where GitHub gives one,
  checks the new engine runs before switching to it, and keeps the previous version. Nothing goes in system folders,
  and no sudo.
- Uploads to `/api/slicer/slice` may be up to 200 MB; every other Portal request keeps the 8 MB limit.
- No Klipper config or macro changed.

Tests: `dev/test_prusa.py` (37 checks: settings cleaning and forced values, refusals, limits, cancel, cache,
memory watchdog, install and keep-previous, routes; PrusaSlicer faked).
Check on the machine: **P1-P8**. PrusaSlicer's command-line options and the unpacked engine running without a
screen are not proven on the Pi yet - P1 and P2 check them first.

PrusaSlicer is © Prusa Research and the Slic3r authors, AGPL-3.0. It is downloaded from Prusa's GitHub releases on
the machine; this zip doesn't contain it.

## 1.4.8 - The Pi's network from Rhino Studio, with an automatic undo

- **New: network settings** through the Portal, for Rhino Studio's Settings / Network: the Pi's name on the
  network (`name.local`), a fixed or automatic (DHCP) address per interface, joining a Wi-Fi network, and Wi-Fi
  power saving (off stops the Pi 3B dropping out). Reading needs nothing new; changing needs NetworkManager.
- **Every change switches back by itself after 2 minutes unless it's kept.** The helper records how things are,
  starts a timer, and only then makes the change. If the change cut the Pi off, nobody can press Keep, so it
  undoes itself. After a fixed-address change, keep it from the new address: `http://<new address>:5000/net`.
  One change waits at a time; changes are refused while a job is printing or paused (Keep and Undo always work).
- **One small root helper**, `/usr/local/sbin/rhino-net` (from `scripts/rhino_net_helper.py`), root-owned, and one
  sudoers line (`/etc/sudoers.d/rhino-net`) that lets your login run exactly that file. It checks every argument
  against a strict pattern, runs commands as argument lists (never a shell), and only touches NetworkManager,
  the hostname and `/etc/hosts`. Wi-Fi passwords reach it on stdin and go into a root-only NetworkManager file:
  never on a command line, in the sudo log or in a reply. `install.sh` adds both (after `visudo` checks the
  sudoers file); `uninstall.sh` removes them.
- No Pi without NetworkManager (`nmcli`) gets the helper; the Portal then shows the network read-only and says why.
- No Klipper config or macro changed.

Tests: `dev/test_net.py` (55 checks: helper, Portal module, routes; every system call faked).
Check on the machine: **N1-N8**. Have a keyboard and screen (or the SD card) handy for N5-N7, in case.

## 1.4.7 - The material record always matches the mounted tool, and SwitchFly's selector matches the record

- **The problem:** G0/G1 decide what E does from the saved record (`set_material_toolhead` and
  `set_material_extruder_index`): reversed on SwitchFly path 2, dropped for HotJoe. A swap already re-pointed the
  record at the new tool (1.4.0, bug 9), but two cases could still leave it out of step:
  - **Swapping SwitchFly on** wrote path 1 to the record without moving the selector. The servo stays wherever it was
    last turned while the head is off the machine, so if it was left on path 2, feeding filament ran the stepper the
    wrong way for the path actually selected: Extrude pulled filament out.
  - **After a restart**, picking a tool from the first-start list ("No toolhead has been recorded yet") didn't touch
    the record at all, so a stale SwitchFly path-2 record could reverse E on BlockOne.
- **The fix:** one new macro, `_RHINO_RECORD_TOOL`, run by `CONFIRM_TOOL_INSTALL` (always) and by
  `_RESTORE_TOOL_CONFIRM` (only when the record names a different tool). It points the record at the mounted tool,
  and for SwitchFly turns the selector to path 1 (T0) with `_SWITCHFLY_SET_PATH PATH=0` so the servo and the record
  agree; the console says so. Use `SWITCH_T1` for path 2 as before.
- **What moves:** only the SwitchFly selector servo, at the end of the swap you confirmed (about a second). No axis,
  no heat, no extrusion. `SET_SERVO_ANGLE` still refuses with LightSaber mounted. Answering "Yes - SwitchFly is
  mounted" after a restart moves nothing: nothing was swapped, so the record is still right.
- No values changed.

Tests: 9 new simulator checks in `dev/test_macros.py`.
Check on the machine: **D10-D12** (swap to SwitchFly with the selector on path 2, restart, BlockOne after SwitchFly).
Rhino Studio's extruder block (branch `extruder-block`) relies on this record to know which path is in use.

## 1.4.6 - SwitchFly knows each path's material; the end of a job makes every tool safe

**SwitchFly materials**
- **The bug:** `SWITCH_T0` and `SWITCH_T1` defaulted to `PLA_0_4`, which isn't a SwitchFly key (its keys end in
  `_T0` / `_T1`), so they stopped with an error. Any other unknown name quietly became PLA.
- **Each path has its own material.** `START_JOB` takes `MATERIAL_T0` and `MATERIAL_T1` (PLA, PETG, ABS, ASA).
  `MATERIAL`, as Orca and Studio write it now, fills the path named by `EXTRUDER`.
- **A path left out is asked at the start of the job**, with the file held the same way as the confirm question:
  "Path 2 (T1) material?" with **Same as last time** first, then that path's materials for the nozzle, and Cancel.
  The confirm window then lists both paths and the one the file prints from.
- **Remembered like BlockOne's material:** `SET_PRINT` checks both paths before it saves or sets anything, then keeps
  them in `switchfly_material_t0` / `_t1`. They survive a restart and aren't cleared at the end of a job.
- **`SWITCH_T0` / `SWITCH_T1`** take `MATERIAL=PLA` or a full key. Without it they use the path's remembered material;
  run by hand with nothing remembered, they ask. They never fall back to PLA, and an unknown name is refused before
  anything moves. Both now share one macro (`_SWITCHFLY_SWITCH`), so the two paths can't drift apart. Switching also
  records that path's material as the one in use.
- A bad name or a clash (`MATERIAL=PLA MATERIAL_T0=PETG`) stops `START_JOB` before it homes.

**End of a job**
- `END_PRINT` now runs `_TOOL_SAFE_OFF` for every kind of tool, after the tool's own shutdown: every tool output to
  its safe level and the powered-tool watchdog stood down, as cancel, swap and the emergency stop already did.
  It leaves `SERVO_LASER` alone with SwitchFly mounted. No values changed.
- Controls and system hardware ticked "switch off when made safe" (an exhaust fan, air assist) **keep running** after
  a normal finish (new `KEEP_CONTROLS=1` on `_TOOL_SAFE_OFF`). Cancel, swap and the emergency stop still switch them
  off. Added POWERED tools end exactly as before, with the full safe-off.

Tests: 50 new simulator checks in `dev/test_macros.py`.
Check on the machine: **D4-D9** (SwitchFly path materials, end of a job).

## 1.4.5 - Cancel doesn't home X/Y with the laser on

- **CANCEL_PRINT with a laser mounted** (LightSaber, or any tool of type LASER) no longer runs `G28 X Y`: homing Y
  with the LightSaber on hits the frame unless the Y endstop has been moved for it (a mount that suits the LightSaber
  is planned). It still switches the laser and its rail off and lowers the bed,
  then goes straight to the park spot, the same move END_PRINT makes. If X/Y aren't homed it says so and leaves the
  head where it is, so Mainsail's own cancel clean-up still finishes.
- Every other tool cancels exactly as before (home X/Y, then park).

Check on the machine: **B5b** (cancel a laser job).

## 1.4.4 - the end of a print parks where everything else does

- **END_PRINT** moves the head to the park spot in `myrhino/positions.cfg` (X551 Y381 unless you changed it), after
  lowering the bed to the safe height as before. It used to go to X0 Y200, a number written into the macro.
  It doesn't home first: the job has just run with X and Y homed.

Check on the machine: **D2** (where the head ends after a print).

## 1.4.3 - the real Z travel

Found on the machine: the bed hit its mounts near Z300, with Klipper allowing 400.
- **Z travel is now 0-295** (`[stepper_z] position_max: 295`, was 400), measured with BlockOne homed: at Z295 the bed
  is about 10 mm above its mounts. Every lift, park and Set Z zero step stops there, and Klipper refuses anything past it.
- **Starter `myrhino/positions.cfg`:** Set Z zero's lowest bed is 290 (was 380). Your own file is kept as always; the
  installer now says if a number in it (`safe_z`, `zero_max_z`) is past the new limit, and `RHINO_POSITIONS` reports it
  at every start.
- **Drag knife test cut:** the lift after the test line stops at the end of Z travel instead of being refused when
  the surface is within 10 mm of it (found by the motion sweep with the new limit).
- **Portal theme:** follows Mainsail's dark/light switch within 15 s, and at once when you come back to its tab
  (it could take up to three minutes).
- **Installer:** when an old portal started from your crontab holds port 5000, it says so and lists the commands to
  turn it off.

Check on the machine: **B6** (Z travel), **A5** (theme switching), **A7** (positions check).

## 1.4.2 - swapping heads without a Klipper shutdown

Found on the machine during test C1: unplugging BlockOne made Klipper shut down ("ADC out of range"). Every
toolhead's thermistor is on the same umbilical contacts (3-4), and with `min_temp: 0` an unplugged plug (about
-50 °C) is an instant shutdown.
- **`[extruder] min_temp: -100`** (`tools/3dp.cfg`): unplugging during a swap no longer shuts Klipper down.
  In its place:
  - **Nozzle heater guard:** `M104`, `M109` and `SET_HEATER_TEMPERATURE` (Mainsail's temperature box) only switch
    the nozzle heater on with a print head mounted and confirmed and its thermistor reading -20 °C or more. Off (0)
    always works. The bed heater is not affected.
  - **Heater watchdog** (`_RHINO_HEATER_WATCH`, every second): if the nozzle heater is on while the thermistor
    reads below -20 °C (unplugged or a broken wire), it is switched off with an error.
  - Klipper's own heating-rate check stays on.
- **Swap: "Toolhead not detected" now works.** It counted only readings below -50 °C as unplugged (an unplugged
  plug read -50.3, so it could slip through) - now below -20 °C. And its window could never appear: the error was
  raised while Klipper was still reading the macro, before the window was drawn. It now uses `_TOOL_REJECT`.
- **Swap: the extruder driver gets power only after the head is detected.** It was switched on first, so confirming
  a print head with its plug not fully in meant plugging a stepper into a powered driver.
- The swap window says the tool connector is off and that about -50 °C while unplugged is expected.

Check on the machine: **C1, C2** (unplug during a swap: no shutdown; confirm unplugged: "Toolhead not detected"),
**C5** (nozzle temperature refused with LightSaber).

## 1.4.1 - the laser's power is switched on for the job

- **Fix: laser jobs did not fire.** The LightSaber only fires with its power rails on (`LASER_INITIALIZE`), and an
  `M3` in the file only sets the level. In 1.4.0 the rails were only switched on for the test fire and the focus dot,
  and switched off again after them, so a job started with "Start the cut" ran with the rails off. "Start the cut"
  (`_LASER_START`) now runs `ACTIVATE_LASER` right after the file is loaded - the same way the CNC setup has the
  spindle running before its file starts. If the file fails to load, Klipper stops before that line and the rails
  stay off; with no `FILE=` nothing starts and they stay off. Typed by hand with another tool mounted, it is refused
  before the file starts.
- Unchanged and checked: a pause drops the level and keeps the rails, `TOOL_RESUME` puts the level back;
  `END_PRINT`, `CANCEL_PRINT` and `EMERGENCY_STOP` switch the rails off.
- A laser file from other software that ends without `END_PRINT` (or `DEACTIVATE_LASER`) leaves the rails on at level
  0 until the next cancel, swap or emergency stop - end laser files with `END_PRINT`.

Check on the machine: **F1** (laser at low power on scrap - now it should cut), then **F4** for the laser and
**H1**.

## 1.4.0 - positions in one place, old test macros removed

- **One place for positions: `myrhino/positions.cfg`.** Park (X551 Y381), tool swap spot (X100 Y100), safe height
  (Z150), the Set Z zero window's lowest bed (Z380) and the prime line (X5 Y10, 120 mm) are set there, and every macro
  reads them - cancel, pause (Mainsail's own park too: copied to `_CLIENT_VARIABLE` at start-up), swap, filament
  change, Set Z zero, prime line. Change a number, `FIRMWARE_RESTART`. `RHINO_POSITIONS` lists them and checks them
  against the travel limits; the same check runs at every start. The installer puts the file in place once and never
  overwrites it. The numbers are the same as before - nothing moves differently.
- The paper test's spot is worked out from `[safe_z_home]` + `[probe]` offset in printer.cfg (same 307.5, 208).
- `tool_swap_park_x/y/z` in `variables.cfg` are no longer read (the installer says so if yours still has them - you
  can delete those lines).
- **Removed old test macros:** `home`, `ACTIVATE_SERVO`, `DEACTIVATE_SERVO`, `TEST_SERVO`, `HELLO_WORLD`, `Test_Card`,
  `BACKUP_CONFIG`, `BACKUP_VARIABLES` and the shell commands only they used. The automatic backup after jobs over 2
  hours now runs `BACKUP_CFG`. `SET_SERVO_ANGLE` stays: it moves SwitchFly's path servo.

Check on the machine: **A7** (positions), and B5/C1 as usual.

## 1.3.9 - portal accessibility, installer backups

Nothing changes on the machine; the Klipper macros are the same as 1.3.8.
- **Portal accessibility** (WCAG 2.1 AA, audit in `docs/accessibility.md`): every form field is announced by its
  label; dialogs take keyboard focus, keep it, and give it back when closed; a Skip to content link; scrolling tables
  work with the keyboard; charts are named, each bar announces its value; the current screen is marked in the
  sidebar; readable contrast for badges, warnings, Delete buttons and links in both themes; Task Library fits a
  320 px screen; less motion when the phone or PC asks for it. axe-core: 97 problems before, 0 after.
- **Installer:** two installs in the same minute used to share one backup folder (the second copy went inside the
  first, and an undo then restored the wrong thing). Each install now gets its own (`-2`, `-3` on the same minute);
  the same for undo's keep-aside folder.
- **Tests:** installer test on a fake Pi (`dev/test_install.py`), accessibility and keyboard checks in the browser
  test. 570 checks.
- **Docs:** `docs/accessibility.md`, `docs/tech-debt.md`.

## 1.3.8 - fixes from the motion tests

New tests (`dev/test_motion.py`, `dev/test_browser.py`, see `docs/testing.md`) follow where the bed and head go and run
every macro and button against safety rules. What they found, now fixed:
- **M1 - first layer at the paper-test height again.** The nozzle height saved by the paper test is applied while
  `START_JOB` holds the file, and Klipper's resume put back the offsets from the moment it was held - so the file
  printed with no nozzle height. `_RHINO_JOB_GO` now re-applies the offsets after the release. The paper test itself
  is unchanged: run once per head, stored for that head.
- **M2 - Z is only homed with a print head.** New `[gcode_macro G28]` (Klipper's own becomes `G28.1`): `G28`,
  `G28 Z`, Mainsail's Home All/Home Z and the old `HOME` macro are refused with a laser, spindle, knife or added tool
  mounted, and before the "which toolhead is mounted?" question is answered after a restart. `G28 X Y` always works.
- **M3 - print-head-only commands.** `PURGE`, `PREHEAT` and `FILAMENT_CHANGE` stop unless a print head is mounted
  (they heated the nozzle output, and `PURGE` raised the bed to Z5, with any tool). Filament change also needs the
  printer homed before it heats.
- **M4 - saved park height stays true.** Homing X/Y with Z not homed makes Klipper's `[safe_z_home]` lower the bed
  10 mm first. The `G28` guard now adds that to the saved park height (and refuses if it would pass the end of
  travel), so "Bed position - Yes" restores the right height.
- **M5 - lifts stop at the end of Z travel.** CNC warm-up and cancel, knife cancel and filament change use the new
  `_RHINO_LIFT`: same lift, never past Z400.
- **M6 -** `PRIME_LINE` ends 2 mm above the bed instead of at first-layer height.
- **M7 -** `ABORT_TOOL_SWAP` and filament-change Cancel say "nothing to cancel" instead of a Klipper error.
- Manual: the wiring items at the end of *Still to check on the machine* were repeated after every list; now once.

Check on the machine: **A6** (homing guard), **C4** (park height after a restart), **D2** (first layer).

## 1.3.7 - review fixes and clearer pop-ups

From a code review of 1.3.6:
- **Work offsets no longer carry over between jobs.** A CNC or drag-knife job set an X/Y work zero (G54) that stayed
  after the job ended or was cancelled, so the next print or laser job would have been shifted by it (and the cancel
  park move could go out of range). `END_PRINT` and cancel now clear X/Y/Z offsets for every tool, `SET_PRINT` clears
  X/Y before a print, and `LASER_JOB_SETUP` clears X/Y (laser files use machine X/Y).
- **Park record cleared at once:** moving the bed below the park height in the Set Z zero window forgets the park
  height straight away, instead of up to 5 s later - so a restart in that moment can't offer a stale height.

Pop-up wording (Mainsail prompts), made consistent:
- Sentence-case titles, no emoji or all-caps buttons; buttons say what they do ("Start the cut", "Set X/Y zero here",
  "Cancel setup"); every checklist starts "Check before you start:"; no divider or blank lines.
- Clearer errors and steps, e.g. "Toolhead not detected - the toolhead's thermistor (contacts 3-4) reads open. Push
  the umbilical connector fully home, then check again."; the swap window numbers its steps and the confirm button
  names the tool.
- No commands changed - only the words. The manual uses the new button names.

## 1.3.6 - Set Z zero by eye

- **New `SET_Z_ZERO` window** for the LightSaber, HotJoe, DragKnife and tools you add (also a Mainsail button):
  Bed up / Bed down 10, 1 and 0.1 mm, then **SET** - that bed height becomes G-code Z0. Nothing moves when you press
  SET, and machine Z is never redefined, so Klipper's travel limits stay right. The window never lowers the bed past
  Z 380 or raises it past position_min. With the LightSaber you set it at the focus point (focus-dot buttons are in
  the window) and the job runs at Z0 with no extra offset.
- All the job setups use it: `LASER_JOB_SETUP` (replaces the stored focus offset), `CNC_JOB_SETUP` (replaces the touch
  plate and manual zero), `DRAGKNIFE_JOB_SETUP` and `TOOL_JOB_SETUP` (still adds the material's Z offset on top).
- **Z after a restart:** the exact park height is now saved whenever the bed is parked. If Z isn't homed but the bed
  was left parked, the setups ask "Is the bed still down where it was parked?" - **Yes** takes the saved height as Z
  (`SET_KINEMATIC_POSITION`) and homes X/Y, then carries on where you were; **No** leaves Z unhomed. If the bed was
  not left parked (a job was running), nothing is offered and Z must be homed with a print head, as before.
  Needs `[force_move] enable_force_move: True`, added in `toolchanger.cfg`.
- **Removed:** the 10 mm touch-plate option and `PROBE_Z_WORK_ZERO` - they used `G38.2`, which Klipper doesn't have.
- **Fixed:** `G54` no longer uses `MOVE=1` (it moved the tool by the change in offset when a zero was set);
  `SET_WORK_ZERO` and the CNC X/Y zero read the machine position, so an older offset can't leak into the new one;
  `LASERHOME` no longer moves the bed up to Z20 toward the laser.
- **Fixed:** choosing a laser, spindle, knife or added-tool material (`SET_TOOLHEAD`, or a `START_JOB` line in a job
  file) no longer resets the Z offset, and a drag-knife job's start no longer sets it to 0 - either would have
  wiped the Z zero you just set. The material `z_offset` values for the LightSaber, HotJoe and DragKnife are no longer
  used.
- Starter task "Check the Z belt drive" says 2:1. OrcaSlicer BlockOne profile: bowden length 5.9.

## 1.3.5 - Orca profiles match the machine

- Rhino PLA: 210 °C nozzle and 65 °C bed, the same as `PLA_0_4` in variables.cfg (was 220 / 55, so the bed dropped
  to 55 °C from layer 2). Its temperature range now starts at 205 so Orca doesn't warn. PETG already matched (245 / 90).
- Rhino BlockOne 0.4: printable width 550 mm (was 575), the X endstop position.
- No macro or printer setting changed.

## 1.3.4 - OrcaSlicer profiles for BlockOne

- New folder `slicer/orca/`: printer, process, PLA and PETG presets for BlockOne with the 0.4 mm nozzle, rebuilt from
  your own Orca 2.3.0 slices (settings from the latest one, Body3). First layer 15 mm/s at 500 mm/s².
  Import in Orca with File > Import > Import Configs. See `slicer/orca/README.md`.
- Start G-code uses `START_JOB TOOLHEAD=BlockOne ... EXTRUDER=0` (the PETG files still called the old `START_PRINT`).
- Bed temperature is the same on every Orca plate type, so picking a different plate can't drop PETG to 35 °C.
- **Fix: the zips up to 1.3.3 contained a `.git` folder** (our own test history) and the installer copied it into
  your config folder. If your config folder is a git repository (for example a GitHub backup), its current branch was
  replaced. The installer no longer copies `.git` or `.gitignore`, and its checks now tell you if your config folder
  has the leftover and how to fix it: put your own back from the oldest backup that has one, or delete it if you never
  had one. It only reports this; it doesn't change anything.
- No macro or printer setting changed.

## 1.3.3 - the PLA preheat question waits for an answer

- The job start ran on past the PLA "heat the bed or bypass it" question: Klipper macros do not wait for a pop-up,
  so the prime line (heating the nozzle first) and the rest of the start sequence ran while the question was still
  open, and the question could only close once that was done. The file was also released before the question and
  held again by it, then never released by the answer.
  Now the file stays held from the "Confirm Toolhead and Material" question until everything is ready; the PLA
  question closes as soon as it is answered and only then does the machine heat, prime and release the file
  (`_RHINO_JOB_GO`). Other materials go straight on. `PREHEAT` on its own (no `CONTINUE=1`) only asks and heats.
- Park position 20 mm in from Mainsail's default on both axes: X551, Y381 (was X/Y maximum minus 5, X571 Y401, which
  runs into the frame). Set in `_CLIENT_VARIABLE` (`custom_park_x/y`) in `client_macros.cfg`; used by Mainsail's pause
  park and at the end of a cancel (after `G28 X Y`).

## 1.3.2 - tool pages, menu option 3 installs

- **Tool library cards are now quick links**: picture, name, slot, what the tool is, how many materials and macros,
  and a Mounted mark. Selecting one opens the tool's **own page**, laid out like its pages in the user manual:
  - right: the tool's picture (the manual's drawings for the built-in tools; the first photo for added tools) with
    its notes;
  - left: about the tool (function, slot, how to set up a job, its Klipper outputs), the tool connector drawing
    with the contacts it uses filled in (select a contact to find it in the table) and the pin table (show all 21 on
    request), its materials with the settings that matter for that kind of tool, and the macros that belong to it
    with their descriptions;
  - Edit tool (added tools) and Maintenance tasks buttons at the top.
- The built-in tools' drawings are transparent line art that follows the theme: black lines in light mode, white
  lines in dark mode, the red callouts unchanged (made from the manual's drawings by `dev/lineart.py`). Photos of
  added tools are shown as taken.
  Built-in wording comes from `rhino/tooldocs.py`; pins, materials and macro descriptions come from the live config.
- Menu option 3 now goes straight on: unpack the zip you pick, preview it, then ask "Install now?". Before, it only
  opened the new version's menu, and option 2 still had to be chosen there - easy to miss (Mike installed the old
  version again that way).
- The dashboard shows what went wrong instead of staying on "Loading..." if a chart cannot be drawn.

## 1.3.1 - nozzle height (paper test), no park on the job-start question

- **NOZZLE_HEIGHT_CALIBRATE** (paper test, one per print head): homes, goes to the middle of the bed and opens a
  window with Down/Up 1, 0.1, 0.02 mm and Save. Save stores where that head's nozzle touches the bed
  (`rhino_zcal_<tool>`, paper thickness allowed for). `SET_PRINT` and `PRIME_LINE` now set the Z offset through
  `_RHINO_APPLY_Z`: the paper test plus an optional per-material fine-tune (`rhino_zfine_<tool>_<material>`, 0 until
  set). Without a paper test they fall back to the old per-material `z_offset` and say so. (`SET_PRINT` looked up the
  saved offset under a misspelt key, so a saved per-material offset was never used there.)
- The "Confirm Toolhead and Material" question at the start of a file holds the file with `PAUSE_BASE` /
  `RESUME_BASE`. It used Mainsail's `PAUSE`, which also parks the head at X/Y max minus 5 mm - past the end of the
  Rhino's X rail.

## 1.3.0 - Dashboard, Mainsail colours, first-start tool question

**Dashboard** (the portal now opens on it). Toolheads on the left, maintenance on the right, same weight:
- Tiles: machine state and mounted tool, production hours, jobs (and how many finished, last 12 weeks), filament,
  overdue and due-soon counts.
- Toolheads: hours by toolhead (producing vs mounted, not producing), jobs by toolhead, a card per tool with its
  use and its most urgent maintenance task, jobs per week (finished / cancelled / failed, from Moonraker).
- Maintenance: task status, the six most urgent tasks with how far through their interval they are, tasks by
  machine and toolhead, maintenance logged per week.
- Every chart has a Table button, hover/focus tooltips, and each toolhead keeps one colour everywhere.

**Matches Mainsail.** The portal reads Mainsail's own appearance settings from Moonraker (dark or light mode and the
primary colour under Settings > UI-Settings) and follows them, checking every 2 minutes. If Mainsail has never
saved its settings, the portal uses Mainsail's defaults (dark, blue).


- First start after an install: `RESTORE_TOOL` only printed "No saved toolhead" in the console when no tool had
  been recorded yet. It now shows the "which toolhead is mounted?" pop-up with a button per tool, and the choice
  is saved for the next restart.
- Z `gear_ratio` back to 2:1, the value the Rhino had before 1.2 (confirmed by Mike). 1.2 had changed it to 3:1.

## 1.2.1 - first run on the machine: start-up errors, safe park height, no Z homing with non-print tools

Found installing 1.2 on the Rhino:
- `[delayed_gcode TOOL_POWER_WATCHDOG]` had a `description:` line, which Klipper refuses in that section.
- `[output_pin SPINDLE_SPEED]` had `shutdown_value: 0.3`; software PWM only allows 0 or 1. Now 0 (a steady
  level, no pulses; the spindle relay also opens on a shutdown).
- `SWAP_TOOL` stopped with "Must home axis first" after a restart.

**Safe park height.** `_RHINO_PARK` (in `toolchanger.cfg`, `variable_safe_z: 150`) lowers the bed to at least
Z150, which clears every tool; it never raises the bed toward the tool. `END_PRINT`, cancel and `SWAP_TOOL` use
it (they used to lift only 10 mm). A 5 s watcher saves `rhino_z_safe` (1 = bed at or below the safe height)
whenever Z is homed; starting a job clears it.

**Z is never homed with a non-print tool.** `SWAP_TOOL` homes X/Y only: by itself if the bed was parked before
the restart, otherwise after you confirm the tool is clear. The laser, CNC, drag-knife and added-tool flows
(`LASERHOME`, `_CNC_ZERO_XY`, `PROBE_Z_WORK_ZERO`, `_DK_ZERO_Z`, `TOOL_JOB_SETUP`) now call `_RHINO_HOME_SAFE`:
Z must already be homed (with a print head; it stays homed through a swap), the bed goes to the safe height and
only X/Y are homed. Their old check read `printer.homed_axes`, which does not exist, so they ran a full `G28`
every time. `PURGE` had the same broken check (print head, so it still homes all axes when needed).

**Installer.** `install.sh` / `uninstall.sh` replace the hand-typed install: checks first, backup, copy, SAVE_CONFIG
carried over (never doubled), paths, packages, service, a pass/fail summary, and `--dry-run` to preview. The
`CHECK_TOOLHEADS` pop-up now says where the OK / ERROR line is.

The lint now refuses options Klipper rejects at start-up in `delayed_gcode` / `gcode_macro` sections and soft-PWM
shutdown values other than 0 or 1.

## 1.2 - categories, the 21-pin connector, system hardware, admin lists, status codes, Task Books

**Add a tool, step 1** asks Additive, Subtractive or Passive, then the kind of tool within it. Kinds are
edited under Admin > Tool lists (name, help, starting cap / on-time / materials / checklist); what a kind
needs (a print head, a power output, nothing) is fixed once it exists. Old kind codes keep working.

**Outputs by umbilical contact.** The Outputs step lists one row per output with a "+": main power (the
PWM level M3 S sets) or "switch on with the tool". Each row picks a contact of the 21-pin connector whose
board pin drives an output in the config, a new output on a spare pin, system hardware (e.g. a vacuum
that runs with the tool) or another output. Extra switch outputs become `also_on` in the registry and
`SET_TOOL_POWER`, `M5` and `_TOOL_OUTPUT_OFF` drive them. Every tool records the contacts it uses
(ticked, plus the ones its outputs and controls drive) - shown as a pin map on its card and on the Pins page.
`umbilical.json` may now describe the contacts (`"contacts": [...]`); the default is the Rhino pin map.

**System hardware** (Hardware > System hardware): enclosure fans and lights, pumps, door switches -
anything on a board pin that is not on the umbilical. Same guided set-up as a tool control, no
mounted-tool guard, optional safe-off, written to custom_tools.cfg. Maintenance tasks can be put on it.

**Admin** (new sidebar group): Tool lists (kinds, material-name suggestions, nozzle sizes, hardware
categories), Maintenance lists (machine areas, kinds of work, priority names), Status codes.

**Status codes.** Built-in statuses can be renamed and recoloured. Custom statuses ("Pending - Waiting
on parts") carry rules: where the task is listed, whether its clock keeps running, pauses, or counts as
done, when the status ends by itself (never / after N days / when the machine is used again), whether it
stays in the Mainsail reminder, whether a note is required, and whether it is offered in Log work, which
is now a drop-down (Done, Skipped, your statuses).

**Task Library and Task Books.** All tasks is now Tasks. The Task Library holds task definitions (the
starter tasks are seeded into it) and Task Books, named groups of them. Assigning a book to a toolhead,
system hardware or the whole machine adds its tasks there, linked: editing a library task updates every
copy, adding or removing a task in an assigned book adds or archives it. A linked task can be detached to
customise it. After Add a tool, the portal offers the book that fits the new tool.

**Merged from the 1 October session** (these had been made on another copy of the config):
- `TOOL_RESUME` and the safer pause for laser, CNC, drag-knife and user-added-tool jobs: Mainsail's Pause
  lifts the head 10 mm and switches the tool off before parking; a pop-up offers **Resume job** /
  **Cancel job**. `TOOL_RESUME` travels back over the paused spot, spins HotJoe back up first, lowers the
  last 2 mm slowly and only then restores laser / tool power. Mainsail's own RESUME is stopped for those
  jobs (it refuses with a cold extruder anyway). Print jobs pause and resume exactly as before.
- Mainsail hooks: `_CLIENT_VARIABLE` (`user_pause_macro`, `user_resume_macro`, `user_cancel_macro`) instead
  of a second `CANCEL_PRINT` that silently replaced Mainsail's. Rhino's cancel steps are `_RHINO_CANCEL`.
- Touch-plate probe: `PROBE_Z_WORK_ZERO` and `_CNC_PROBE_Z_RUN` read Z after `G38.2` (new
  `_CNC_SAVE_TOUCH_Z`); before, the saved work zero was the start height, e.g. 8 mm too high.
- `printer.cfg`: old duplicate `run_klipper_backup` removed; Z `gear_ratio` 3:1 (was 2:1). Re-check Z
  travel, `Z_TILT_ADJUST`, the probe Z offset and per-material Z offsets.
- Tests run against the real Mainsail macros (`dev/fixtures/mainsail.cfg`, used only by the simulator -
  do not copy it into the config folder). Pop-up messages sit bottom-right, clear of Restart Klipper.

**Smaller:** collapsible sidebar groups; notes-only and pin-map-only edits no longer ask for a Klipper
restart; the Save button in the control/macro popup runs a pending check instead of being ignored; phone
layout fixes.

## 1.1 - controls, macros, restart timer, preventive maintenance

**Tool controls** (new Controls step in the add wizard, Controls tab in the editor). Describe what an extra
output or input does; the portal deduces the Klipper section (`output_pin` on/off or PWM, `fan_generic`,
`heater_fan`, `servo`, `gcode_button`), checks the name against every object in the config, offers only
free umbilical pins (filtered by pin type when `umbilical.json` describes them), and previews the exact
text. Options: active-low, state at power-up, off-or-on at Klipper shutdown, switch off on safe-off
(`_TOOL_SAFE_OFF` now calls the generated `_RHINO_CONTROLS_OFF`), and generated on/off/set/angle macros that
can be limited to "only while this tool is mounted".

**Tool macros** (new Macros step / tab). Name, purpose (becomes `description:`), body, optional
mounted-only guard. Refused before saving: names used by any macro or Klipper command (case-insensitive),
G-code words, Jinja errors (the section is parsed the way Klipper parses it, then compiled with Klipper's
template delimiters). Warned: `SAVE_CONFIG`/`FIRMWARE_RESTART`/`M112`..., unknown commands, text after
` #` or ` ;` that Klipper drops as a comment.

**Restart banner.** Lists the waiting changes (portal and console), shows the running job with progress,
elapsed, time left (slicer estimate, or file progress for laser/CNC files), when a restart becomes
possible, and pause duration. Opt-in automatic restart 30 s after the job completes or is cancelled (not
after an error). Any Klipper restart clears the banner. Edits during a job are saved and queued; the
console commands stay blocked during a job because their shell command would stall the job's G-code.

**Preventive maintenance.** New Maintenance section: due & upcoming dashboard, task list per machine area
and tool, work log, usage meters, starter task library covering every machine area and tool type.
Schedules by time (from last done or fixed calendar), usage meter, event, or date, whichever comes first,
each with an early alarm. Meters come from a background Moonraker poll plus Moonraker's job history.
Never blocks a job; one Mainsail prompt after each Klipper start (`guided/maintenance.cfg`) and
`PM_STATUS` in the console. Tool renames and removals carry over to tasks and meters.

**Safety fix carried over:** `tools/spindle.cfg` `SPINDLE_SPEED` had `shutdown_value: 1`, so a Klipper
shutdown (e.g. M112) sent the ESC signal to full throttle. Now `0.3` (ESC neutral).

**Also:** `toolchanger.cfg` restore prompt hands over to the maintenance reminder (`_RESTORE_TOOL_DISMISS`),
the lint now fails the run on problems and knows `SET_SERVO`/`M112`, the simulator handles fans and
servos, `dev/demo_server.py` added, new tests `dev/test_extras.py` and `dev/test_maint.py`.

## 1.0

## Bugs fixed in your existing config
Each was reproduced against your original files in a Klipper macro simulator first, then re-tested after the fix.

| File | Problem | Fix |
|---|---|---|
| `tools/spindle_macros.cfg`, `tools/laser_macros.cfg` | `M3`/`M4`/`M5` were defined in **both** files. Klipper merges duplicates and the later include (laser) won, so a CNC job's `M5` hit the laser lockout and the spindle versions never ran. | One dispatcher in `tools/tool_power.cfg` that acts on the mounted tool (laser, spindle, custom tool). |
| `tools/laser_macros.cfg`, `spindle_macros.cfg` | A rejection (`action_raise_error`) in a macro aborts the **whole macro before any line runs**, so the "switch it off" lines above it never executed. | Switch off first, then a separate `_TOOL_REJECT` macro raises. |
| `myrhino/TOOLHEAD_DISPATCH.cfg` | `SET_STEPPER_PARAMETERS` only worked for `_0_4`/`_0_8` deposition keys, so a laser, CNC or drag-knife job failed with "not found". | Key is `MATERIAL_NOZZLE` for deposition tools only; any nozzle size; other tools use the plain material name. |
| `tools/3dp_macros.cfg` | `PRIME_LINE` set an `is_running` flag that was never cleared, and required `toolheads` in `variables.save` (which is not there). | Both removed. |
| `LED/led_macros.cfg` | `LEDOFF` checked the wrong object name, so it always reported an invalid pin. | Correct `output_pin` lookup. |
| `myrhino/mysystem.cfg` | Servo macros wrote `SERVO_LASER`, which is the **laser intensity** pin while LightSaber is mounted. | Blocked while LightSaber is mounted. |
| `myrhino/mysystem.cfg` | `EMERGENCY_STOP` left the laser rail/signal on. | Calls `_TOOL_SAFE_OFF` (laser, spindle relay + ESC neutral, custom tools); centres the SwitchFly servo only if SwitchFly is mounted. |
| `client_macros.cfg` | `CANCEL_PRINT` left the spindle/laser on. | Calls `_TOOL_SAFE_OFF`. |
| `toolchanger.cfg` | `SWAP_TOOL.current_tool` is a macro variable and resets to 0 on every Klipper restart. | Saved to `variables.save` on each confirmed swap; ~8 s after startup a prompt offers to restore it (`RESTORE_TOOL`). |
| `toolchanger.cfg` | After a swap the saved "last toolhead" could still say SwitchFly, so `G1 E` was inverted on BlockOne. | The confirmed swap re-points the saved toolhead and resets the extruder index. |
| `toolchanger.cfg` | `ADD_NEW_TOOL_RESPONSE` and its edit/delete twins used `action:prompt_input`, which Mainsail does not support. They could never work. | Removed. Replaced by the portal and `guided/add_toolhead.cfg`. |
| `shell_command.cfg` | Typo `github.com{username}`; `PREFLIGHT_BACKUP_CHECK` called `tc.run_shell_command`, which does not exist. | Fixed. |
| `client_macros.cfg` | `CREATE_TOOLHEAD_LOG` ran a shell command that is defined nowhere. | Commented out. |
| `printer.cfg` | The `ADD_TOOLING` include was commented out. | Includes for the new files. |

## New files
- `rhino/` - the tool-management package (see README for the map). `scripts/rhino_toolgen.py` and `scripts/rhino_portal.py` are thin launchers.
- `myrhino/custom_tools.cfg` - generated registry (empty until you add a tool).
- `tools/tool_power.cfg` - M3/M4/M5, `_TOOL_SAFE_OFF`, `SET_TOOL_POWER`, power cap, watchdog, pause/resume handling.
- `guided/add_toolhead.cfg` - console commands. `guided/generic_workflow.cfg` - `TOOL_JOB_SETUP`.
- `service/rhino-portal.service`, `dev/` (lint + tests), `README.md`, updated `Prompt.md`.

## Not changed - please check on the machine
1. **`G54` uses `SET_GCODE_OFFSET ... MOVE=1`.** That physically moves the head by the change in offset, so "set zero here" flows can drive the head away from where you set it. My new `TOOL_JOB_SETUP` does not use `MOVE=1`; I left your CNC macros alone because I cannot test them on the machine.
2. **`G38.2` is not a stock Klipper command**, so the CNC touch-plate step (`PROBE_Z_WORK_ZERO`) will fail unless you have a module that provides it.
3. **`COOLDOWN.cfg`:** the full ABS/ASA ramp is longer than Klipper's default 600 s idle timeout; add `[idle_timeout] timeout: 1800` if you want it.
4. **Connector pins:** of the nine pins on your portal's whitelist, PE0, PE1, PE2, PE3, PF4 and PB0 are already used in `printer.cfg`/`3dp.cfg`/`laser.cfg`. Only **PB1, PC0, PC1** are free, so at most three new pins - sharing existing outputs is how you add more. If your umbilical really carries other pins, list them in `myrhino/umbilical.json`.
5. `run_klipper_backup` is defined in both `printer.cfg` and `shell_command.cfg`; they merge and one wins per option. Delete one.
6. `LEDFLASH` blocks for about 1.35 s every time it runs, which also delays safety macros that call it.
7. Pause/resume power handling uses Mainsail's `user_pause_macro`/`user_resume_macro` hooks when they exist (I could not see your `mainsail.cfg`). If they do not, the 5 s watchdog still cuts power during a pause and restores it after resume, up to 5 s late.
8. All starting power values (hot wire 40-50 %, caps, max on-times) are placeholders. Start low.
