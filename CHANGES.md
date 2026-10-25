# What changed

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
