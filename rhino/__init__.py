"""rhino - tool management for the Rhino multi-tool machine.

One shared library, two front ends:
    scripts/rhino_toolgen.py   command line (what Klipper's RUN_SHELL_COMMAND calls)
    rhino/portal/              web portal (dropdowns, keyboard input, photos, live pin checks)

Layout (read top to bottom; each module only imports the ones above it):
    errors.py       Fail - the one exception both front ends turn into a message
    paths.py        where everything lives on disk
    presets.py      tool kinds, starting values, limits, allowed characters
    klipper_cfg.py  read-only access to the Klipper config tree (built-in tools, pin claims)
    sections.py     Klipper text for a tool's extra controls and macros (rendering only)
    registry.py     the user-added tool registry: JSON in, generated Klipper .cfg out
    builders.py     validate input and build / edit one tool dict
    extras.py       validate a tool's controls (guided pin setup) and macros
    service.py      add / edit / remove / rename / check / reports - the API the front ends call
    cli.py          KEY=VALUE command line on top of service.py
    moonraker.py    printer + job status, job history, guarded restart (stdlib only)
    pending.py      changes saved but waiting for a Klipper restart (the banner)
    monitor.py      background poll: job timer, auto-restart after a job, feeds maint meters
    maint/          preventive maintenance: schedule, meters, starter library, service
    portal/         Flask app: routes.py + maint_routes.py (HTTP), security.py, media.py (photos),
                    static/ (portal.js, maint.js, portal.css) + templates/ (screens)
"""
__version__ = "1.3.5"
