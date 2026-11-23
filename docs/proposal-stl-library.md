# Proposal: a model library in Files (STLs you keep, browse and start jobs from)

Nov 23 2026. **For Mike's review: nothing is built, and it has open questions (below) that change the design.** Mike asked for a place to
upload STLs to a folder, browse that folder, pick a file and set up a job from it, with drag and drop to fill it like the job setup page,
and possibly an external drive one day.

## What exists today (so this adds, not replaces)

- **Files** has four tabs (Gcode files, Config, Logs, Job history). Each of the first three is one of **Moonraker's fixed roots**; the browser
  uploads by button or drag and drop (several files, with progress), makes folders, renames, moves (drag a row onto a folder), downloads
  and deletes (`src/files/FileBrowser.vue`, `fileOps.ts`).
- **Job setup** takes a model from a drop or a file picker: `stl`, `obj`, `3mf`, `svg`, `dxf` (`MODEL_TYPES`); several files dropped together
  become one assembly. **Studio keeps nothing: the model lives in the browser** until it is sliced. The saved Prepare job (profile, overrides,
  placement, lanes) is kept on the Rhino, **keyed by file name**.
- **Moonraker's roots can't be extended** by configuration, and I haven't verified whether it follows a symlink out of its roots. So a library
  can't simply be "another Moonraker folder". The Portal (Flask, on the same host) already stores files of its own (background pictures,
  fonts, backups, profiles) with token-checked writes, so the library is **a Portal-owned folder with its own routes**.

## The design

**Storage.** A folder the Portal owns, outside the config folder: `~/printer_data/models/` (not in `config/`, so it is not in the GitHub
config backup, which is the right place for binaries to stay out of). Nested folders, up to 6 deep. Types: the same five as job setup.
G-code stays in Gcode files.

**Portal** (`rhino/portal/library_routes.py`, `rhino/library.py` with tests): `GET /api/library?path=` (list: name, size, modified, kind,
triangle count and size in mm when known), `GET /api/library/file?path=` (bytes), and token-checked writes: upload (one file, name checked),
make folder, rename, move, delete (to a trash that keeps 30 days, as profiles do). Every path is resolved and kept inside the root; no
`..`, no links, no hidden or odd names; a file's type is checked by its contents, not its extension (an STL must be a consistent
binary STL or start with `solid`; a 3MF must be a zip holding `3D/3dmodel.model`).

**Studio.** A fifth Files tab, **Models**. The browser is the same component as the other tabs, working through a small backend interface
(list, upload, rename, move, delete, download) with two implementations, Moonraker's and the Portal's, so drag and drop to upload, drag a row onto a
folder to move, progress, rename and the menus are **the same code**, not a copy. Added: a thumbnail per model, size in mm, a search box, sort by
name, date or size.

**Set up a job from a file.** A row's main action is **Set up a job**: Studio fetches the file from the Portal and hands it to job setup **exactly as
if it had been dropped**, so every existing rule (lanes, assemblies, the file check) applies unchanged. Select several rows (or a folder)
and **Set up as one job** loads them together as an assembly. The model is copied into the browser, so pulling an external drive
afterwards doesn't disturb a job in progress.

**Drag and drop into the library** works as in Files today: drop files onto the Models tab or a folder in it. Dropping a folder from the computer
is offered where the browser allows it (Chrome and Edge do; Safari doesn't).

**External drive (later, designed for now).** The library takes a short list of **locations**: the internal folder, and any extra folders the
person adds that sit on a mounted drive under `/media` or `/mnt` (nothing else is allowed). Each location shows as a root in the Models tab with a
connected or not connected state. A missing drive is a calm "not connected", never an error page. The Portal never mounts or unmounts
anything (that needs root); the person mounts the drive once (see the first item in the next section).

## Things you may not have thought of

1. **A drive in `/etc/fstab` can stop the Rhino booting.** An entry without `nofail` makes a missing drive hang the boot, on a machine
   meant to restart by itself after a power cut. The proposal's setup note requires `nofail,x-systemd.automount,x-systemd.device-timeout=5`
   and the Portal never edits fstab. Ubuntu Server doesn't automount USB drives by default.
2. **File systems.** exFAT and NTFS drives work but have case-insensitive names and odd characters; FAT32 can't hold a file over 4 GB;
   many drives from a PC are NTFS. Proposed: read and write on ext4, exFAT and NTFS, say which it is, and refuse names the drive can't hold.
3. **Pulling the drive.** An unplug during an upload leaves a half file. Uploads are written to a temporary name and renamed when whole, and
   flushed (the same writer as 1.9.45), so a half file never appears as a model. A safe-eject button would need a root helper (like
   the network one): not proposed; the note says to use `udisksctl unmount` or stop writing first.
4. **Saved jobs are keyed by file name.** Two library files named `bracket.stl` in different folders would share one saved job. Proposed:
   library jobs are keyed by the file's path and content fingerprint (`lib:<folder>/<name>#<short hash>`), so a renamed or changed
   file doesn't silently reuse the wrong placement, and a moved one is found again by its fingerprint.
5. **Duplicates and overwrites.** Same name, same content: say "already here". Same name, different content: ask (replace, keep both as
   `name (2).stl`, or cancel). A replaced model's saved job is kept, with a note that the model changed.
6. **Backups.** A library of models can be gigabytes. Proposed: **not in the Rhino backup by default** (a separate "Include the model
   library" choice with its size shown), never in the GitHub config backup. A disk or SD card failure then costs the library unless the
   person has copied it: the page says where the folder is and how big it is.
7. **Disk space.** The internal disk can fill; a full disk breaks Klipper's own logs. Proposed: refuse an upload that would leave less than
   2 GB free on the system disk (the Rhino's host stats already read this), and show free space at the top of the tab. On a Raspberry Pi's SD card,
   a large library also wears the card: say so, and prefer a drive.
8. **Who can upload.** Any trusted screen can, as for Gcode files; writes need the Portal's token. On a shared network that means anyone
   on a trusted address can fill the disk, so the free-space floor in item 7 matters.
9. **Big files.** The Portal accepts up to 210 MB for a slicer upload and nginx allows 210 MB on `/portal/`. Many 3MF files with textures are
   larger. Proposed: the same 210 MB limit per file, stated in the drop zone. A very large mesh is flagged: marked parts above 1.5 million
   triangles are refused today, and slicing them in the browser is slow.
10. **Thumbnails** cost browser time. Proposed: made once, when a file is uploaded (Studio already has the mesh in memory then), as a small image the
   Portal keeps in its own cache folder on the internal disk (never on the external drive), and made lazily for files that arrive by other means.
11. **Tags and notes** (material it was printed in, "needs supports", "scaled 95%"): useful, easy to overbuild. Proposed: a one-line note per file in a
   small index file, nothing more at first.
12. **A last-used mark**, like the Gcode files list's "Last run": when a job is set up from a model, remember when and with which head.
13. **Where it lives for the durability rule:** on the Rhino, not in the browser, so another screen or a cleared browser sees the same library.

## Open questions for Mike

1. **One location or several from the start?** The internal folder only for the first release (drive support following), or the location list
   from day one? Proposed: internal first, with the code written for several, because the drive needs the notes in item 1 and a test on real hardware.
2. **Which file types?** The five job setup takes, or also STEP (Studio can't open STEP, so no) and `.gcode`? Proposed: the five.
3. **Does "drag and drop like I do now for setting up a job" mean** (a) drop files onto the library to store them, (b) drag a library row onto
   the job setup bed to load it, or both? Proposed: both; (b) is a small addition once rows can be dragged.
4. **Keep a folder as an assembly?** "Set up as one job" for a selected folder (a project of several parts). Proposed: yes, one level of folder.
5. **Delete:** straight away with a confirm, or to a trash for 30 days (as for profiles)? Proposed: trash, with a plain "Restore".
6. **Backups:** off by default (item 6), or on with a size warning? Proposed: off by default.
7. **Naming:** the tab is "Models" in this draft. Or "Library", "Parts", "STL library"? (It holds 3MF, OBJ, SVG and DXF too.)
8. **Thumbnails:** generate on upload only (cheap), or also scan a folder you copied in by hand (needs a "Rescan")? Proposed: both, scan on demand.
9. **Per-file notes and tags** in the first release, or later? Proposed: a note field only.
10. **External drives:** what drive do you picture (a USB stick, a USB SSD, a network share)? A **network share** (a NAS on the home
    network) is a different animal (Samba or NFS, slower, can vanish) and not covered here: say if that is what you want.
11. **Should the Rhino also copy a model into the library when you drop it into job setup?** ("Add to library" button on the part list.)
    Proposed: a button, never automatic.

## What can go wrong, and what stops it

- **A path trick** (`../../etc`, a link, a drive path outside `/media` and `/mnt`): resolved and refused; tests include every one I can think of.
- **A bad or hostile file** (not an STL, a zip bomb in a 3MF): checked by content and size before it is kept; the browser's own loader still has
  its limits and errors.
- **A full disk** or a **drive that vanishes mid-write**: items 3 and 7.
- **Slowing the Portal**: listing a folder of thousands of models is paged (200 per page) and thumbnails are cached, so a big library doesn't
  stall the Portal's 8 worker threads. Uploads of large files take a thread for a while; the 1.9.45 time limits apply.
- **A library change during a print:** allowed (it doesn't touch Klipper), but moving or deleting the file that the current job came from
  doesn't matter, because the model was copied to the browser when the job was set up.
- Nothing here sends anything to Moonraker, Klipper or the machine.

## Tests and checks

Portal: path safety, type checks, upload/rename/move/delete/trash, duplicate handling, free-space floor, listing pages, a vanished drive
(simulated by a missing directory). Studio: the backend interface (both implementations pass the same tests), the job key, the drop
into library, "Set up a job" handing a file to job setup unchanged. Headless run against the mock, light and dark, desktop, phone and 760 px, one
screenshot round. On the machine (`docs/testing.md`): LB1 upload by drag and drop, several files and a folder; LB2 Set up a job from a
row gives the same job as dropping the same file; LB3 a saved job reopens for the same file; LB4 the free-space floor refuses; and, when
drives arrive: LB5 a drive in fstab with `nofail`, boot with the drive unplugged (the Rhino must start); LB6 unplug during an upload leaves no
half file. Each with a pass condition and a *Stop if*.

## Order and size

Medium: one Portal module with routes and tests, one Studio tab on a refactored file browser. The refactor (the backend interface)
is the part that touches working code, so it comes first, with the Gcode, Config and Logs tabs unchanged and re-tested. External drives
come after, on real hardware, behind the notes in "Things you may not have thought of" item 1.
