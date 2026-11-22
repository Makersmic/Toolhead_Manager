# Decisions

Append-only. Each entry is dated and gives its reason. An entry is never edited; a later entry can reverse an earlier one, and says so. Invariants (docs/invariants.md) cite these by date.

- **2026-10-23: Durability over parity.** Rhino Studio is the durable interface for the Rhino, not a general Mainsail replacement. Every feature is tested against one question: does it help the machine survive being left alone and be resumed safely? *Reason:* it's one owner's multi-tool machine, and it sits idle for long stretches.
- **2026-10-23: Parked:** timelapse, Spoolman, job queue, input-shaper graphs, the exhaustive UI tweak list. The full list and the reasons are in docs/parked.md. *Reason:* none of them help the machine survive being ignored.
- **2026-10-23: Order of work:** finish what's in flight (1.6.1) → Phase 2 backup → 7050 migration → Phase 1 slice profiles → Phase 3 welcome back → Phase 4 invariants finalized. One phase at a time. Each phase ships in a zip and is installed before the next one starts. *Reason:* the host migration is next, and a complete backup is its safety net. Four half-finished tracks would be the opposite of durable.
- **2026-10-23: Slice profiles get a new Portal file,** `config/myrhino/slice_profiles.json`. It follows the registry/lists pattern: schema version, validated on save, atomic write. *Reason:* a file inside the config folder is backed up with no extra work. Materials stay Klipper-facing in variables.cfg.
- **2026-10-23: No cross-engine translator.** A profile is engine-native (one engine's settings plus a shared header). Switching engines means choosing that engine's profile. *Reason:* Kiri:Moto and PrusaSlicer settings don't map one-to-one, so a translator would silently print differently.
- **2026-10-23: "Away"** means the time since the later of the last job's end and the last Studio visit. There is no toggle. *Reason:* it can be worked out without the operator having to remember anything.
- **2026-10-23: The browser holds nothing durable.** *Reason:* a cleared cache or a different device must not lose work.
- **2026-10-23: The 7050 migration is accepted on a load test:** slice a long job while a print runs, with no missed steps and no timer-too-close errors. Pinning cores is a mitigation, not the test. *Reason:* only a measurement settles it.
- **2026-10-23: PrusaSlicer will be first-class or out,** decided after that load test. *Reason:* the middle position is the worst, because the safety notes then have to cover two half-supported paths.
- **2026-10-25: "First-class" PrusaSlicer means all four of these:**
  - (a) a Portal profile type
  - (b) its output goes through the same file check as Kiri:Moto (already true)
  - (c) a README safety section
  - (d) the job-setup flow
  
  *Reason:* the definition is set before the decision, so it can't be decided by feel (INV-C2).
- **2026-10-25: Versioning (INV-B2):** objects added from Phase 1 on are versioned by the Portal, keeping the last 5 revisions and pruning on save. Older objects (tools, lists, maintenance) are versioned by the backup's git history. *Reason:* this keeps the invariant true without claiming the Portal already does something it doesn't.
- **2026-10-25: What the backup covers** is defined once, in docs/phase0-spine.md § Backup inventory. Three open questions must be answered before Phase 2 code starts:
  - klipper-backup's `backupPaths`
  - whether `variables.save` is git-ignored
  - whether PrusaSlicer has a saved profile on the Pi
  
  *Reason:* a backup promise is only as good as its inventory.
- **2026-10-25: Phase 2 gates, answered on the Pi.**
  - (1) klipper-backup `backupPaths` is `printer_data/config/*` only, so it covers the whole config folder and nothing outside it. This confirms the inventory: Moonraker data and `rhino_data` aren't covered today.
  - (3) There are no saved PrusaSlicer profiles on the Pi; `rhino_data/prusaslicer/` holds only `cache` and `jobs`, which are re-derivable and not backed up.
  - (2) `variables.save` is backed up. There is no `.gitignore` entry for it, and the `.env` `exclude` array only skips `*.swp *.tmp printer-<stamp>.cfg *.bak *.bkp *.csv *.zip`. All three gates are clear; Phase 2 code can start once Mike approves the design.
- **2026-10-25: Backups keep the last 10 archives** (Mike).
- **2026-10-25: The Moonraker database is backed up with Moonraker's own backup endpoint** (the whole DB), rather than exported by hand. *Reason:* it is complete (history, totals, every namespace) and Moonraker restores it itself, refusing while printing. Checked in the Moonraker source.
- **2026-10-25: History merge is pending Mike's answer.** Moonraker has no import API, so a merge means writing into its SQLite file while it's stopped. The 7050 move doesn't need one.
- **2026-10-25: Phase 1 slice profiles design approved as drafted, with the leans** (Mike). Per-file jobs go on the Rhino in `rhino_data/prepare_jobs.json`, in the backup zip but not on GitHub. A profile belongs to a process with an optional toolhead. An imported name clash gets " (2)". PrusaSlicer profiles use the same file and path until the 7050 load test.
- **2026-10-25: Portal profile routes use POST and DELETE only** (no PUT), like every other Portal write.
- **2026-10-25: The visual macro builder comes back as its own phase after Phase 1** (Mike asked for it). It will be the durable form, pending a one-page design: macros saved as versioned JSON in `config/myrhino/`, steps picked from an allowed list and checked by the console's safety gate, and a plain reorderable list rather than a drag-and-drop canvas.
- **2026-10-25: Backups are named `rhino_studio_os-<YYYYMMDD-HHMMSS>.zip`** (Mike: no "mainsailos"). The host stays in the manifest and the backup list. Old names still work.
- **2026-10-25: The old-browser-settings import is a prompt** (RsDialog: Import / Not now), not a red notice (Mike). Red stays for stop/destroy, unlocked-live and the Dashboard's "needs you".
- **2026-10-25: Backups leave out zips in the config folder and the manual PDF** (Mike). They're re-downloadable, and they made each backup about 133 MB on the Pi.
- **2026-10-25: The driver cooling fan stays on an always-on Octopus port**, not in Klipper. That's how it has always been wired. A `[controller_fan]` on PD15 is an option for later, as a wiring change plus a config change, written up first.
- **2026-10-26: Add hardware wizard design approved** (`docs/hardware-coverage.md`, Mike), with these answers:
  - Guided forms only, no raw "paste a Klipper section" box.
  - **Job hooks run from the macros** (`START_JOB`, `*_JOB_SETUP`, `END_PRINT`, `_RHINO_CANCEL`, pause/resume hooks) through one `_RHINO_HOOKS` call, not from the sliced file. They work for every slicer, and cancel always turns off whatever a hook turned on. The macro diff is shown to Mike before it's written.
  - **Interlocks: "must be closed to start" is on by default** for laser and spindle.
  - **`heater_generic` is capped at 120 °C.**
  - **A second control board (`[mcu name]`) is in this job**, so its pins can be used from the start.
  - The wizard mascot is final: six poses with speech bubbles, used in this wizard only.
- **2026-10-26: the job-hooks macro change approved and applied** (`docs/proposal-macro-hooks.md`, Mike: "yes").
  16 call-only insertions, including the laser test fire checking interlocks. The three called macros live in the
  generated `myrhino/job_hooks.cfg` (starter copy shipped, kept by the installer, rewritten on every hooks or
  registry save and at Portal start). Released as 1.9.0.
- **2026-10-26: 7050 migration answers** (`docs/migrate-7050.md`, Mike): network option A (NetworkManager on the
  7050), hostname `rhino`, nothing on the Pi's GPIO header (only the Octopus and the webcam, USB). **The Pi is retired**
  a month after the 7050 is accepted: until then it's the fallback, frozen at 1.9.1 (replacing the 1.8.1 the draft
  named); the 7050 stays on 1.9.1 until the load test passes so the way back can restore. After acceptance, a one-time
  Clonezilla image of the 7050 SSD; releases then target x86 only.
- **2026-11-02: The Pi and the 7050 both move on 1.9.8.** This replaces the frozen version named in the Oct 26 entry
  and in `docs/migrate-7050.md` (1.9.7 until now). The rest of that entry stands. *Reason:* the Pi's backup failed
  silently for 19 days while the status said OK. The way back also needs a backup with a truthful status, so the Pi
  gets the fix before the move.
- **2026-11-02: `rhino-backup` is private.** It was public and includes `moonraker.conf`. *Reason:* a backup of a live
  machine's config isn't public material. Going private doesn't undo the time it was public, so its contents still
  need checking for secrets.
- **2026-11-02: The Pi and the 7050 both move on 1.9.9.** This replaces 1.9.8 in the entry above and in
  `docs/migrate-7050.md`. The rest stands. *Reason:* the Pi needs the backup watcher fix, and a restore wants the same
  version on both.
- **2026-11-02: The 3D Preview uses three.js and draws toolpaths, not solid parts** (Mike). `three` 0.186.0 (MIT),
  pinned exactly, with one parser and viewer in Studio shared by later screens. Printed moves are threads at their real
  width from `;WIDTH:` or the nozzle size, lit from one side; laser, CNC, knife and travel moves stay thin lines.
  *Reason:* it shows the real moves in the file on the Pi's kiosk-class hardware, and Lighter drawing covers weak screens.
- **2026-11-02: Tool Manager replaces klipper-backup's watcher through a systemd override** (Mike: "fix the backup
  watcher"). `scripts/rhino_backup_watch.sh` makes one backup per burst, holds during a job, and leaves klipper-backup's
  files untouched. Uninstalling removes the override. *Reason:* the old watcher ran one whole backup per file event, so an
  update kept the host busy for hours.
- **2026-11-02: `meters.json` doesn't start a backup** (Mike). It goes up with the next backup something else starts.
  *Reason:* it saves about every 5 minutes, up to about 288 commits a day and needless SD card wear. *Accepted cost:*
  GitHub's copy of the meters can lag behind while nothing else changes. Local archives still include them.
- **2026-11-07: The 7050 is the Rhino's host (accepted).** The load test passed with all four cores loaded (`nice -n 10 yes`, 10 min, from 20 min in) during a BlockOne print, standing in for the PrusaSlicer slices of the 2026-10-23 entry: no layer shift or stall, and no new timer-too-close, lost-communication or shutdown lines in klippy.log. Tool Manager updates resume on the 7050. The Pi stays frozen at 1.9.9 for a month, then it's retired, and releases after that target x86 only. PrusaSlicer stays undecided (first-class or out) until its template error on the 7050 is fixed and P1-P9 run. *Reason:* a full load on every core is harsher than a niced slice, and PrusaSlicer was failing for a reason unrelated to the host (Mike).
- **2026-11-07: Block supports are hidden** (Mike). On real PrusaSlicer 2.8.1, a blocker under about 8 mm had no effect,
  because PrusaSlicer fills small holes in support back in. The button would mislead, so it's hidden (`SHOW_BLOCKS` in
  Studio). Marks ship. The store, the request and the Portal still carry blocks. *Next:* block the whole overhang that's
  clicked, then show the button again.
- **2026-11-07: The hologram's rhino is an original model built in Studio's code** (Mike). It's a smooth distance-field
  skin with the same joints and trot as before. Free "CC-BY" rhinos were looked at and turned down: the one downloaded
  looked like a model ripped from a mobile game (bulk uploads, game rig with dizzy-star bones), the CC0 options were
  cartoons, and paid models' licences don't allow shipping the file in a public repo. *Reason:* nothing in a public GPL
  repo should carry doubt about who made it.
- **2026-11-07: The macro builder makes Studio-only macros, with an advanced G-code step** (Mike). Macros are stored
  by the Portal and run from Studio through the console's check; Klipper doesn't load them, so editing needs no
  restart and the generated config stays small. The advanced step takes one typed line, which goes through the same
  check and confirm as the console. Starter routines are simple moves and heating: park, heat for the mounted
  material, cool down. *Reason:* that's what Mike types by hand most, and nothing in it can do more than the console.
- **2026-11-09: Rhino Studio answers the bare address; Mainsail is a two-week spare, then removed** (Mike: "I do not
  want to give myself a crutch to fall back on"). From 1.9.19 the installer gives port 80 to Studio and moves Mainsail's
  own nginx site to port 8090 (the cameras use 8080-8083). Undo puts Mainsail back. After the on-machine checks and
  about two weeks, Mainsail is removed one step at a time, each with its own OK. *Reason:* one front end to learn
  and maintain; a spare that stays forever becomes the thing used when Studio is missing something.
- **2026-11-09: Klipper doesn't need Mainsail installed** (Mike approved `docs/proposal-own-client-macros.md`).
  `printer.cfg` includes `client_mainsail.cfg`, a pinned, credited copy of mainsail-config's `client.cfg` (GPL-3.0),
  byte for byte the machine's `mainsail.cfg` (md5 `0b6bf780f4dba4d0ca7294dd0f6b5d40`), in place of `mainsail.cfg`.
  The Rhino's hooks stay in `client_macros.cfg`. *Reason:* removing Mainsail could take `mainsail.cfg` with it, and
  Klipper would refuse to start. *Accepted cost:* upstream fixes to those macros arrive only when we copy them in, and
  once Mainsail is gone, undo can't go back past 1.9.19.
- **2026-11-09: Studio has a read-only Host health page** (Mike: the load and temperature of the four cores, and
  whatever else is needed to troubleshoot). The Portal reads `/proc` and `/sys` (`GET /api/host/stats`); Studio adds
  Moonraker's per-core load and Klipper's board stats. Nothing on the page changes the machine. *Reason:* the 7050 runs
  Klipper and slicing on the same cores, and timer errors start as host load or USB resends.
- **2026-11-09: The name stays Rhino Studio** (Mike). It was a working title; the brand stays in one file
  (`src/brand/brand.ts`) all the same.
- **2026-11-09: Camera sound is set up by the install when a USB camera microphone is plugged in** (Mike: "allow that
  audio to come through", then "Installer adds it"). Sound only, from the camera's own microphone: ffmpeg (Debian)
  and go2rtc 1.9.15 (MIT, pinned by checksum and shipped inside the release zip) in a low-priority `rhino-mic`
  service, reached only through Studio's `/mic/webrtc` from the home network. It never stops an install: anything
  missing is skipped with a note and a log. Undo takes it away if that install added it. *Reason:* hearing the
  machine (a grinding extruder, skipped steps, spindle chatter) helps when it's left running, and the pictures stay on
  crowsnest, so the cameras never depend on it. *Accepted cost:* ffmpeg's first install needs the internet, and
  anyone who can open Studio on the network can listen while Sound is on.
- **2026-11-10: External devices go through Tool Manager only.** ESP32, ESP8266 and similar devices (for example a
  handheld pendant) may control the machine only through a fixed-command Tool Manager endpoint: no raw Moonraker, no
  G-code. Nothing is scheduled; this sets the rule for when one is built. *Reason:* the command list and its safety
  checks stay in one place that is tested, and a device that drops its link or misbehaves can only send commands that
  were made safe to send.
- **2026-11-10: The wizard mascot is Mike's rhino crew, in every wizard** (Mike: "replace all of the existing rhino
  images", "change the hearts to something appropriate"). Sixteen poses cut from his two sheets by Studio's
  `scripts/wizard_art.py`, drawn in the theme's ink colour, one beside every step of Add hardware, Add a toolhead and
  every tuning test. The sheets' hearts are replaced with hex nuts. The shocked rhinos only mean trouble. *Reason:* one
  recognisable character across the wizards, from Mike's own art, replaces the earlier made-up one.
- **2026-11-10: Laser and drag knife tuning** (Mike). The focus test zeroes with the shroud touching the stock, then
  ramps upward from 1 mm. The knife runs depth before blade offset. Focus height and blade offset are kept per tool;
  the rest per tool and material. Job setup starts a laser or knife job from the tuned values; a job saved for the same
  file keeps its own.
- **2026-11-10: Answers for the Studio start wizard** (`docs/proposal-studio-start.md`, not applied yet). The `zeroed`
  flag on `SET_Z_ZERO`, cleared by `SWAP_TOOL`, is approved. The frame check is offered, not required. The wizard's
  checklist uses the Mainsail prompts' lines word for word. *Reason:* both ways of starting a job say the same thing,
  and a frame check that can be skipped doesn't get in the way of a job that's already been framed.
- **2026-11-11: The spindle's bits are a library on the Rhino** (Mike). Assets › Parts › Bits (`myrhino/lists.json`
  "bits": name, end mill or ball, diameter, flutes, cutting length, note). Spindle tuning is kept per bit (its measured
  diameter) and per bit and material (feed, throttle, depth per pass, plunge); Job setup fills a CNC job from the bit
  picked. Feeds are found by test only: the HotJoe's no-load RPM isn't known. *Reason:* a result that can't say which
  bit it was for can't be trusted months later.
- **2026-11-11: The spindle size check measures a slot, not a square outline.** One slot's width, read with the
  caliper's inside jaws, is the bit's true cutting diameter, runout included. *Reason:* a square outline only measures
  cleanly when it's cut through, which risks the spoilboard.
- **2026-11-11: The spindle run-in is a Care task** ("Run the spindle in", CNC spindle book, every 6 months), done
  with the console's spindle commands, not a tuning test. *Reason:* it's maintenance with no value to keep, and a
  tuning button that spins the spindle would need a new no-confirm path.
- **2026-11-11: Spindle throttle shows as the ESC pin's value everywhere** (Mike): 0.6 reads 60 % on Control, the
  Dashboard, tuning and the CNC setup's prompt; at 30 % the spindle is stopped, and Control says so.
- **2026-11-11: Laser operations, after LaserWeb** (Mike). In Job setup a laser job can have operations, each a cut,
  a score or an engrave fill with its own power, speed and passes, for loops picked by clicking them on a drawing of
  the job. They run in the order the user sets (up/down); Studio warns when a cut frees a part before work inside it.
  Loops not picked are cut last with the job's own settings. Kerf and outline height stay job-wide. *Reason:* one
  drawing often needs engraving, scoring and cutting, and doing it in one job keeps the parts registered.
- **2026-11-11: CNC jobs start from Studio's wizard too** (Mike: "apply and ship 1.9.27"). `CNC_JOB_SETUP
  FROM=STUDIO` refuses unless the HotJoe has its Z zero and the spindle is running; the quiet warm-up checks the lid
  before the spindle starts, because Studio warms up before `CNC_JOB_SETUP` runs. *Reason:* the same steps as the
  laser and knife, on screen, and a job can never start on a stopped bit.
- **2026-11-11: Lead screws are driven from the screen** (Mike: "drive one motor from the screen"). Bed ›
  Configuration moves each Z motor on its own through `FORCE_MOVE`, behind the padlock, with release to turn by hand
  and Home and level. Chosen over guiding a turn by hand only. *Reason:* it's what recovers a Z-tilt fault, and it
  was already built (Nov 8); the padlock, steps and relocks are its safety design (BC1-BC6 on the machine).
- **2026-11-11: No event GIF animations in the theme** (Mike). Custom images in panels stay on the roadmap.
  *Reason:* dropped by choice; it also kept animation away from alerts and red panels.
- **2026-11-12: Releases are signed, and the key is Mike's** (Mike: "I want U1 settled", audit M5). Every release zip
  carries an ed25519 `.sig` made by the release workflow from the `RHINO_SIGNING_KEY` secret; the public half is in
  `scripts/rhino_update_helper.py`, and the root-owned updater, the Portal's upload and GitHub paths and Studio's
  *Install from zip* refuse anything that doesn't verify. `rhino.sh` option 3 stays the unsigned, by-hand path.
  *Reason:* a zip swapped on GitHub, on the way down or in the drop folder can't reach the machine, and the seed never
  leaves Mike (a copy off this PC is his to keep).
- **2026-11-12: The Portal accepts a change only under the machine's own names** (audit M4): its hostname, any
  `.local` name, an IP, `*.ts.net`, or a name in Moonraker's `cors_domains`. Reads aren't checked. *Reason:* DNS
  rebinding points a web page's own name at the Rhino so the Origin check and the token both pass; the Host header
  is the one thing that page can't choose.
- **2026-11-12: The raw commands behind the Rhino's wrappers always ask** (audit M3): `G28.1`, `M104.1`, `G1.1` and
  the other `rename_existing` targets are at least `internal` in Studio's console, with the reason shown. *Reason:*
  they skip the wrapper's own checks (mounted tool, heater rules), which is the whole point of the wrappers.
- **2026-11-14: A filament encoder on the BlockOne, read as travel, not as a switch** (Mike: "I want to use the
  sensor in the picture", "B, the toolhead"). The AS5600 angle board stays: at 3.3 V from a linear regulator on the
  probe's 12 V rail (contacts 14/13), analog OUT on contact 17 → `PB1` (EXP2 pin 3; not a thermistor header, whose
  4.7 kΩ pull-up is under the chip's 100 kΩ minimum load). Stock Klipper can't consume an angle, so Tool Manager
  ships its first Klipper extra, `filament_angle_sensor`, as a symlink into `klippy/extras` with a Host health line
  and a relink. Readout first with stock Klipper (`docs/testing.md` FE1-FE6), then the module. *Reason:* the angle is
  a measurement (slip, travel, a self-measuring extruder calibration), which is what Mike asked for; a pulse sensor
  would only have given pause-on-jam. I2C over the umbilical was rejected: four wires against two spares, and an I2C
  fault shuts Klipper down mid-print.
- **2026-11-14: Spindle RPM from a hall switch at the bell rim, through a 30-line extra** (Mike: "go with the 30 line
  extra", "Hall at the bell rim is ok"). The D2814's 14 rotor magnets pass one hall switch fixed to the mount: 7
  pulses per turn, nothing on the rotating side; 5 V from the ESC's BEC; open-collector output on contact 19 → `PC5`
  (EXP2 pin 10) with the MCU's pull-up. `spindle_tachometer` reads it on Klipper's pulse counter and only reports.
  `SPINDLE_SPEED` stays an `output_pin` (a `fan_generic` conversion would have changed the ESC macros and Studio's
  throttle readout). Both spare umbilical contacts are now assigned. *Reason:* the throttle has been a guess and the
  bits' feeds assume an RPM nobody measured; a magnet on the shaft would unbalance a 30,000 RPM spindle and can let go;
  the ESC (Skywalker 80A) has no RPM output. What consumes the RPM (tuning, Bits, a stall rule, target-RPM mode) each
  gets its own review; target RPM needs a design note first.
- **2026-11-15: The belt-tension guide listens with the camera's microphone and its analyser lives in Studio** (Mike:
  "I want to build our own frequency app into Rhino Studio", "use the microphone from the webcam", "structured like a
  wizard", a live spectrogram while the belt is tuned; the 7050's own microphone input as a second source later).
  Belts are 15 mm 2GT with no tensioners yet (tension is a clamp on the carriage). Built in batches: the analyser and a
  microphone test page first (1.9.31), the wizard only after BT0 proves the microphone path. The analyser is browser
  Web Audio on the WebRTC sound that already reaches Studio, so it needs no HTTPS and no new service on the host; it
  sends nothing to the machine. *Reason:* matching the two belts is what keeps a CoreXY square, and a belt that drifts
  while the machine sits idle is a real cause of a bad first print; a phone app would do it, but Mike wants it built in,
  so it is built in small steps with a typed-Hz fallback. Not decided yet: how the driver fans are switched off, and the
  host-side second source (needs its own proposal and install document).
- **2026-11-15: Care tasks get one guide shell, with gates in Studio, not a wizard each** (Mike: "Go ahead with the suggested build
  order"). 29 starter tasks were sorted into 10 wizards, 17 guided checklists and 2 links. The shell has six kinds of step (gate, do,
  wait, measure, tick, log). Gates and waits live in Studio and read Klipper; task text from the library is never run as a command, and
  a Do step will use the existing check and confirm, with no new no-confirm path. Order: shell and checklists (built), belts, emergency
  stop, level, Z drive, nozzle, spindle, umbilical. Also: a read-only "What's happening" strip on the tuning pages (Mike: it would
  help to be informed while a test heats and runs). *Reason:* one component to build and test instead of ten, and a precondition such
  as "spindle relay off" is only a safety gate if Studio reads it from Klipper.
- **2026-11-21: Support marks belong to the model on screen** (Mike, Nov 21). Marks start empty with each model and are not saved or restored per file name; removing a part
  removes its marks; any change to the marks clears the prepared file. *Reason:* marks restored by file name had put old spots on a new part, and a stale prepared file looked
  like "Preview kept the first model".
- **2026-11-21: Marked supports go to PrusaSlicer as a 3MF the Portal builds with shared, exact corners** (found with Mike's drilled washer). A 3MF's loose corners are not
  welded by PrusaSlicer the way an STL's are, so holes filled in; each corner is now written once with exact float32 values. No marks means a plain STL, and the slice reports what
  the Rhino received (triangle count, size, CRC-32). Marked parts are capped at 1.5 million triangles. *Reason:* proved on PrusaSlicer 2.8.1 and confirmed by Mike on 2.9.7.
- **2026-11-21: Job setup is the model full width, with floating, foldable Process and Settings panels** (Mike, Nov 21). They stack under the model at 1100 px and under. Fold state
  is kept per browser only.
- **2026-11-21: Supports have one control, settings groups start folded, changed settings get a red border, Preview asks to save** (Mike, Nov 21: "keep the red border").
  The Supports drop-down (Off / Automatic / Only where I mark) is the only support control; PrusaSlicer's `support_material` and `support_material_auto` checkboxes are hidden
  because it sets them. Every settings group starts folded (PrusaSlicer groups keep what the viewer opened). A setting that differs from the profile in use gets a red border
  (`--rs-changed`): a deliberate exception to "red only means stop", recorded in Studio's AGENTS.md. Opening Preview with unsaved changes asks: save to the profile, save as a new
  profile, or continue without saving; "continue" is not asked again until the changes change. *Reason:* two controls for one thing invited conflicting settings, and a profile
  quietly drifting from what was sliced is how a good setup gets lost.
- **2026-11-21: The part cooling fan is set from Control, in the status strip** (Mike, Nov 21). Click the Part fan reading, type 0 to 100 %, Enter; it sends `M106 S<0-255>` or
  `M107` through the normal command check (no confirmation, like the heat commands) and only for a confirmed print head. *Reason:* the strip showed the fan but there was no way to
  set it. The Rhino's `[fan]` pin and cycle time are untouched.
- **Logged late, from earlier sessions (wording as in the handoff; no new decision):** tool power is on for a task, not a mount (SwitchFly UBEC PA1); WireViz not adopted; the
  notes folder was restructured; Studio does not start the spindle in the run-in; Studio never moves Z in the Z drive wizard; Care guide progress is kept in memory only.
- **2026-11-22: Two filaments in one job: how the lanes work** (Mike, Nov 22: "the lanes feed one nozzle", "both" for supports and interface, "both" slicers, "No lane by height, same nozzle so same height", "keep as one assembly for default is fine", lanes "two to eight" with an external filament switcher contemplated).
  Lane 1 and lane 2 are the lanes of SwitchFly's one nozzle; lane 2 can print the supports and their interface layers; PrusaSlicer and Kiri:Moto both do it (Kiri: the whole job in one lane, supports from another, no separate interface filament, because its bundled engine slices one model at a time). Several files dropped together are one assembly by default
  (they keep their places relative to each other and move as one; each part still sits on the bed). The lane model allows two to eight lanes, drawn as piano keys, so an external switcher can use it. Pause for a hand filament change and automatic spool change on an optional per-lane runout endstop are wanted: the machine side waits for Mike's hardware redesign.
  *Reason:* one nozzle means every lane change purges; PrusaSlicer's wipe tower can't be built when supports or their interface print from another lane than their part (test slices, Nov 22), so there are two purge modes (a tower on the bed, or the machine purges) and the machine purges when supports come from another lane. A support lane on every layer of a 26 mm part made 133 lane changes in the test slice, against 5 for the interface layers alone, so Studio shows a change estimate and recommends interface-only.
- **2026-11-22: A file that changes lane is held back from sending until Klipper has a `SWITCH_LANE` macro, and the settings file may carry only one G-code template** (Mike: the lane-change macros are written "when the design is assembled"). Studio's file check `lanes` is an error unless Klipper reports a `SWITCH_LANE` macro, so Send and Download are refused; `SWITCH_LANE` is a placeholder name.
  The Portal's INI filter accepts only `toolchange_gcode = ;RHINO_LANE {next_extruder}`, a comment: Studio turns the markers into `SWITCH_LANE LANE=n` after slicing and removes PrusaSlicer's bare `Tn` and heat commands (temperatures stay the machine's, from the material table). *Reason:* Klipper only reports an unknown command and carries on, so a lane file on a machine without the macro would print the second lane's parts in the first lane's filament; and no G-code the machine would run should travel through the settings.
- **2026-11-22: Lane colours** (Mike, Nov 22: click a lane's colour in the style guide and pick it). Each lane has a tone and its own pattern, never red, so colour is never the only signal; the tone is user-pickable in the style guide, kept in that browser only, and applies to the keys, part chips, lane tabs and the Preview. The style guide's "dither" swatch became one flat light grey, as did an empty lane key (the dots made text hard to read).
- **2026-11-22: Lane filament options live with the job, not in profiles (for now).** Another lane's PrusaSlicer filament options are kept only as what it changes from lane 1, saved with the job. Whether a profile should keep both lanes' settings is Mike's open call.
