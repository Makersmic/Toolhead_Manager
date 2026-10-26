# AGENTS.md: working on the Rhino Tool Manager

Instructions for AI coding agents (and people) changing this repository. Read it before your first change.
If something here disagrees with `docs/decisions.md`, the decisions log wins: it is newer and records why.

## What this is

The Klipper config and tool-management package for the **Rhino Multi Motion System**: one machine, swappable
toolheads (3D printing, laser, CNC spindle, drag knife, and tools users add). It contains:

- **Klipper config and macros**: `printer.cfg`, `toolchanger.cfg`, `tools/`, `guided/` (Mainsail prompt wizards),
  `myrhino/` (dispatch, positions, generated files), `variables.cfg`.
- **The Rhino Portal**: a Flask app (`rhino/`, port 5000) that owns the tool registry, system hardware, maintenance
  (Care), backups, slice profiles and the updater. **Rhino Studio** (the separate `rhino-studio` repo) is its main front end.
- **The installer and menu**: `install.sh`, `rhino.sh`. Releases are zips installed through the menu or Studio's updater.

**The goal is durability, not feature parity.** This machine can sit idle for months. For every change, ask:
*does this help it survive being left alone and be resumed safely?* Prefer a clear refusal with a reason over a
clever default.

## Never

- **Never change a working machine value** (gear ratios, offsets, shutdown values, temperatures, pins in use) without
  the maintainer asking for it, even if it looks wrong. Say what you think is wrong instead.
- **Never change a Klipper macro without a review step.** Write the change up first: what runs, in what order, and what
  can go wrong. Big changes go in a `docs/proposal-*.md` with an `--apply` script whose anchors a test checks
  (see `docs/proposal-macro-hooks.md` and `dev/proposal_macro_hooks.py`).
- **Never write to the user's own config files** except through the generated files the Portal owns:
  `myrhino/custom_tools.cfg` (from `custom_tools.json`) and `myrhino/job_hooks.cfg`. Never hand-edit those two.
- **Never let tool state come from anywhere but Klipper.** The mounted tool is `printer["gcode_macro SWAP_TOOL"].current_tool`.
- **Never weaken a safety rule** to make something convenient: `_TOOL_SAFE_OFF` on every end/cancel/swap path, interlocks
  "must be closed to start" for laser and spindle, heater caps, PNP sensors never wired direct, a MOSFET header never
  used as an input.
- **Never push, tag or release** without the maintainer's OK. Releases publish automatically when `VERSION` changes on main.

## Hard facts that cause bugs

- `action_raise_error` aborts the whole macro before any of its lines run. Switch hardware off in a separate macro call first.
- Duplicate `[gcode_macro]` definitions merge silently; the later include wins. Search before adding one.
- Macro variables reset on restart; anything that must survive goes through `SAVE_VARIABLE`.
- Mainsail prompts support only text and buttons. Anything that needs typed input belongs in Studio or macro parameters.
- The laser fires only with its power rail on (`ACTIVATE_LASER`); every laser path ends with `M5` and `DEACTIVATE_LASER`.
- `SERVO_LASER` is both the laser's power and the SwitchFly path servo. The spindle ESC idles at 0.3, never 0.
- `START_JOB` ends at a prompt; the job file actually starts in `_START_JOB_FILE`, where every job path ends.
- Pins on a second board are written `name:PIN` (`ebb:PA1`). `ConfigTree.resolve` and the pin picker understand them.
- Write small numbers plainly in generated config (`cycle_time: 0.00004`, never `4e-05`).

## Where things live

| Area | Files |
|---|---|
| Tool registry (user-added tools, system hardware, wizard devices, second boards, pin labels) | `rhino/registry.py`, `rhino/service.py`, `rhino/builders.py`, `rhino/extras.py`, `rhino/sections.py` |
| Add hardware wizard | catalog `rhino/hw_catalog.py`, boards and pins `rhino/hw_boards.py` (+ generated `hw_boards_data.py` from `scripts/board_pins_from_klipper.py`), writers `rhino/hw_devices.py` |
| Job hooks, interlocks, filament sensors | `rhino/job_hooks.py`, `rhino/hw_devices.py` (`interlock_macro`, `filament_macro`) |
| Portal HTTP | `rhino/portal/*_routes.py`; every write needs the per-process token (`X-Rhino-Token`) |
| Backups, updater | `rhino/backup.py`, `rhino/portal/update_routes.py`, `service/` |
| Design and decisions | `docs/hardware-coverage.md`, `docs/decisions.md`, `docs/testing.md` (on-machine checks) |

Data that must survive is versioned JSON in `config/myrhino/` (rev + history, refused when stale or unreadable);
per-job data goes in `rhino_data/`. Hardware types are **data** in `rhino/hw_catalog.py`: add a row, not a code path.

## Testing

```
sh dev/run_all.sh          # lint, simulated Klipper macros, portal, installer, browser + accessibility checks
```

- Run it as a **normal user**, not root: CI does, and permission problems hide under root.
- Install `rsync` and `nginx` (and `npm install --prefix dev axe-core@4.10.2`) or those tests skip instead of running.
- The simulated Klipper is not real Klipper. New power hardware is tried on a current-limited supply first, and every
  change that touches the machine gets an on-machine check in `docs/testing.md` with a pass condition and a *Stop if*.
- `python3 dev/demo_server.py --port 5055` runs the Portal against a throw-away config and a fake Moonraker.

## Conventions

- Commit messages: `<area>: <what changed>`; a release commit starts with the version. Update `CHANGES.md`, `VERSION`
  and `rhino/__init__.py` together.
- User-facing text: sentence case, plain verbs, say what will happen; errors say why and what to do next.
- Fail closed: validate everything the Portal writes, parse generated config back the way Klipper will, and keep a
  backup before replacing a file.
- Rhino Studio is built into each release zip from the `rhino-studio` repo's main branch, so a Studio-only change
  reaches users only with a Tool Manager version bump. Push Studio first, then this repo.
