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
