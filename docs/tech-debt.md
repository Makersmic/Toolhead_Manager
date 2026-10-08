# Tech-debt audit

**Date:** 8 October 2026 | **Version:** 1.3.9 | **Scope:** Klipper config and macros (4,900 lines, 186 macros),
the `rhino/` Python package (5,600 lines), portal JS/CSS/HTML (3,100 lines), installer scripts, `dev/` tests.
Report only: nothing here is changed yet.

**Overall:** the Python is in good shape (pyflakes finds only an unused import or two in test files, every module
has a clear job). The test suite is now strong. Most of the debt is in the Klipper side: inherited macros that
predate the tool manager, numbers written out in several places, and boilerplate that every macro repeats. It
matters more if the Rhino software is ever shared: those machine-specific numbers are what another machine would
trip over first.

Priority = (Impact + Risk) x (6 - Effort), each 1-5.

## Prioritized list

| # | Item | Type | Impact | Risk | Effort | Priority |
|---|---|---|---|---|---|---|
| 1 | Every G0/G1 move goes through a macro | Code / performance | 4 | 4 | 3 | **24** |
| 2 | Machine positions and limits written out in several places | Code | 3 | 3 | 2 | **24** |
| 3 | Klipper never checks the config until `FIRMWARE_RESTART` on the Pi | Test | 4 | 4 | 3 | **24** |
| 4 | Old and overlapping macros in the Mainsail macro list | Code | 2 | 2 | 1 | **20** |
| 5 | CI on actions and a runner image that are being retired; unpinned test tools | Infrastructure | 1 | 3 | 1 | **20** |
| 6 | Version number kept by hand in two files (plus docs) | Infrastructure | 2 | 2 | 1 | **20** |
| 7 | The "which tool is mounted" lookup copied into 20 macros | Code | 3 | 3 | 3 | **18** |
| 8 | The on-machine test plan exists twice (docs and manual) | Documentation | 2 | 2 | 2 | **16** |
| 9 | Inherited naming and messages ("Master Unified Engine", emoji, 65 `M117`) | Code / UX | 2 | 1 | 2 | **12** |
| 10 | Two large files: `rhino/maint/service.py` (1,141 lines), `portal.js` (1,049) | Architecture | 2 | 2 | 3 | **12** |
| 11 | One-off installer check for the old `.git` problem | Code | 1 | 1 | 1 | **10** |

### 1. Every G0/G1 move goes through a macro (24)

`[gcode_macro G1]` and `[gcode_macro G0]` (`tools/3dp_macros.cfg`) rename Klipper's moves and render a Jinja template
for **every move in every file**: to flip E on SwitchFly's second path and to strip E for HotJoe. A detailed print
has hundreds of thousands of moves; rendering a template for each costs host CPU and can starve Klipper's move queue
on a Pi (pauses and blobs on small curved details). The E edit is also a text replace (`rawparams|replace("E" ~
params.E, ...)`), which is fragile with unusual number formats.

**Fix:** Klipper's `SET_EXTRUDER_ROTATION_DISTANCE` inverts the extruder with a negative distance (Klipper G-code
docs - check on the machine), so `_SWITCHFLY_SET_PATH` can set the direction once per path change, and CAM files
for HotJoe don't contain E moves. Then both overrides can go. **Why:** print quality on long jobs, and one less
thing between the slicer and the motors. Needs the machine (SwitchFly both paths, a long detailed print).

### 2. Machine positions and limits written out in several places (24)

The park spot X551 Y381 (`client_macros.cfg`, `toolchanger.cfg`), the 150 mm safe height, Set Z zero's Z380, the
swap spot X100 Y100, the paper-test spot X307.5 Y208 (worked out by hand from `safe_z_home` + probe offset) and the
550 mm bed width are typed in where they're used. Changing the Y limit (still an open question) or the bed means
finding every copy. **Fix:** keep the Rhino's measured numbers in one place (`VARIABLES`) and work the rest out from
`printer.toolhead.axis_maximum` and `printer.configfile` (`safe_z_home`, `probe`). The values stay identical, and the
motion tests prove it. **Why:** the first thing that breaks on another machine, and on this one after a frame change.

### 3. Klipper never sees the config until the Pi restarts (24)

The lint and the simulator copy Klipper's rules, but they're our copies: the RESUME offset bug (M1) was Klipper
behaviour the simulator didn't have until this week. **Fix:** in CI, check out Klipper and run its own config
loader in batch mode (Klipper's `scripts/test_klippy.py` approach: `klippy.py printer.cfg -i job.gcode -o /dev/null
-d <mcu dictionary>`), which parses every section and runs a short G-code file through the real gcode/macro code.
**Why:** catches config errors on GitHub instead of a red box in Mainsail, and keeps the simulator honest.

### 4. Old and overlapping macros (20)

Still in the macro list: `home` (now redundant: the G28 guard covers homing), `TURN_ON_MOTORS`, `ACTIVATE_SERVO` /
`DEACTIVATE_SERVO` / `SET_SERVO_ANGLE` / `TEST_SERVO`, `M0`, `HELLO_WORLD`, `Test_Card` (in `printer.cfg`), and three
backup macros that overlap (`BACKUP_CFG` 120 s timeout, `BACKUP_CONFIG` running the same script with 60 s,
`BACKUP_VARIABLES`). **Fix:** you pick which to keep; the rest go, or get a leading `_` to hide them from Mainsail's
panel. **Why:** a shorter macro list, fewer ways to do the same thing, less to keep safe.

### 5. CI on retiring versions (20)

GitHub warns that `actions/checkout@v4` and `actions/setup-python@v5` run on the retired Node 20, and `ubuntu-latest`
moves to Ubuntu 26 from 19 October 2026. Playwright and Flask are unpinned. **Fix:** move to the current action
versions, pin `runs-on: ubuntu-24.04`, pin Playwright and Flask versions in CI. Ten minutes. **Why:** a red test
run caused by GitHub, not the code, is the fastest way to stop trusting the tests.

### 6. Version kept by hand (20)

`VERSION` and `rhino/__init__.py` both hold it, and the manual and test plan quote it. **Fix:** read `__version__`
from `VERSION`, and a test that fails if the manual's install example or `docs/testing.md` names another version.

### 7. The tool lookup copied 20 times (18)

Twenty macros start with the same six lines (merge `VARIABLES` and `CUSTOM_TOOLS` maps, find the mounted tool and its
type); 1.3.8 added two more. A macro that forgets `CUSTOM_TOOLS` silently ignores added tools. Klipper macros can't
share functions, but they can share state: **fix** with a `_RHINO_TOOL` macro whose variables (`name`, `type`,
`is_print_head`) are set whenever the mounted tool changes (confirm, restore, swap), so a macro reads one line.
**Why:** fewer places for added tools to be forgotten.

### 8. Two copies of the on-machine test plan (16)

`docs/testing.md` and the manual's *Still to check on the machine* say the same things in different words, and both
need updating each release. **Fix:** build the manual chapter from `docs/testing.md`.

### 9. Inherited names and messages (12)

Comments like "Master Unified G1 Intercept Engine", "noobydp principle", emoji in console messages (✅ ❌ ⚠️) next to
the plain style from the 1.3.7 copy review, and 65 `M117` lines (Mainsail shows them briefly; most duplicate a
`RESPOND`). **Fix:** tidy as each file is next touched.

### 10. Two large files (12)

`rhino/maint/service.py` (71 functions: schedules, meters, library, books, history, statuses) and `portal.js`
(84 functions: library, wizard, editor, hardware, pins). Both are readable, but every maintenance change goes through
one file. **Fix:** split along the existing section comments when next changed (books/library out of the maintenance
service; wizard and editor out of `portal.js`), not as a project of its own.

### 11. One-off `.git` check in the installer (10)

The installer recognises the stray `.git` from the 1.3.3 zips (commit `ba3346d`). Once your `rhino-backup` repository
is fixed, it can come out.

## Phased plan, alongside normal work

**Phase 1 - next release, nothing changes on the machine (about an hour):** #5 CI versions, #6 one version number,
#11 once the backup is fixed, and pyflakes in CI for the Python.

**Phase 2 - your decisions, then a behaviour-identical refactor:** #4 which macros to keep, then #2 one place for
positions and #7 the shared tool lookup. The motion tests and the sweep already check every position, so these can
be proved unchanged before they reach the Pi. #8 when the manual is next rebuilt.

**Phase 3 - with the machine:** #1 replace the G0/G1 overrides (test SwitchFly's two paths and a long, detailed
print), and #3 the real-Klipper config check in CI. #9 and #10 as files are touched.
