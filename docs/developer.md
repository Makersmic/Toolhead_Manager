# Developer notes

For changing the Tool Manager itself. Users don't need any of this - see the user manual.

## Run it without the printer

```
pip install flask jinja2
pip install playwright && python3 -m playwright install chromium    # only for the browser test
npm install --prefix dev axe-core@4.10.2                             # its accessibility scan
sh dev/run_all.sh                  # lint + every test suite (see docs/testing.md)
python3 dev/test_motion.py --quick # motion flows without the minute-long sweep
python3 dev/demo_server.py         # the portal against a copy of this config and a fake Moonraker
python3 dev/maint_year_demo.py /tmp/rhino-year   # a config with a simulated year of maintenance
python3 dev/demo_server.py --config /tmp/rhino-year/printer_data/config
```

The simulator (`dev/klippersim.py`) reproduces Klipper's template rules - a macro is rendered whole before any of
its lines run - against the real Mainsail macros in `dev/fixtures/mainsail.cfg`. `Sim(root, motion=True)` also follows the machine
position the way Klipper does (G90/G91, G92, offsets, `[safe_z_home]`, saved G-code states, pause/resume) and
refuses moves past the limits in `printer.cfg`; every move is in `sim.moves` with the macro chain that made it.
`sim.clone()` copies a loaded simulator, which is what makes the sweep fast. It is not Klipper: test new tools
on the real machine, powered from a current-limited supply first.

A new macro that moves anything gets a flow in `dev/test_motion.py`; the sweep picks up every macro and button by
itself.

## Where things are

| To change... | Edit |
|---|---|
| default power caps, materials, checklists, allowed characters, limits | `rhino/presets.py` |
| which pins reach the tool connector | `myrhino/umbilical.json` (copy `umbilical.example.json`) |
| validation rules (what is refused, and the message) | `rhino/builders.py` |
| how the config is scanned for used pins | `rhino/klipper_cfg.py` |
| the generated Klipper file / JSON saving / backups | `rhino/registry.py` |
| add / edit / remove behaviour | `rhino/service.py` |
| console output | `rhino/cli.py` |
| web endpoints and security | `rhino/portal/routes.py`, `security.py`, `media.py` |
| portal screens (wizard, editor, controls, macros) | `rhino/portal/static/portal.js`, `templates/index.html`, `portal.css` |
| control and macro rules / the Klipper text they become | `rhino/extras.py` / `rhino/sections.py` |
| maintenance schedules, meters, starter tasks | `rhino/maint/schedule.py`, `meters.py`, `library.py`, `service.py` |
| maintenance screens | `rhino/portal/static/maint.js`, `rhino/portal/maint_routes.py` |
| Admin screens (drop-down lists, status codes) | `rhino/portal/static/admin.js`, `rhino/lists.py` |
| the 21 umbilical contacts, board-header labels | `rhino/presets.py` (`DEFAULT_CONTACTS`, `BOARD_HEADERS`) or `myrhino/umbilical.json` |
| the start-up maintenance prompt, `PM_STATUS` | `guided/maintenance.cfg` |
| job timer, auto-restart, meter polling | `rhino/monitor.py` |
| M3/M4/M5, power cap, watchdog, safe-off | `tools/tool_power.cfg` |
| console commands ADD_/EDIT_/REMOVE_TOOLHEAD | `guided/add_toolhead.cfg` |
| guided job setup for custom tools | `guided/generic_workflow.cfg` |

Data: `myrhino/custom_tools.json` (source of truth; last 10 versions kept in `myrhino/registry_backups/`),
`myrhino/custom_tools.cfg` (generated, do not edit), photos in `~/printer_data/rhino_data/images/`
(outside the config folder, so backups stay small).

## Building the manual

```
cd manual
python3 build.py && python3 paginate.py              # first pass
python3 build.py pages.json && python3 paginate.py   # fills in the contents page numbers
```
Sources are in `manual/src/` (one HTML file per chapter) and `manual/img/`; `build.py` adds the tool pages and
generated sections.

## Releases

`VERSION` and `rhino/__init__.py` hold the version; `CHANGES.md` says what changed and what to check on the machine.
The release checklist is in [testing.md](testing.md#release-checklist).
