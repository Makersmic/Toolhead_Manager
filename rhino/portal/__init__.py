"""Rhino tool portal: a small Flask app on top of rhino.service.ToolService."""
import os

from flask import Flask

from ..maint import MaintService
from ..monitor import Monitor
from ..moonraker import Moonraker
from ..paths import resolve
from ..service import ToolService
from . import maint_routes, routes, security, slice_routes


def create_app(config_dir=None, moonraker_url=None, start_monitor=False):
    """start_monitor=True runs the background watcher (job timer, auto-restart, maintenance meters).
    Tests leave it off and call app.config["MONITOR"].tick(now) themselves."""
    paths = resolve(config_dir)
    app = Flask(__name__)
    app.json.sort_keys = False          # keep list orders (priorities, statuses, rule choices) as written
    mr = Moonraker(moonraker_url or os.environ.get("RHINO_MOONRAKER", "http://127.0.0.1:7125"))
    mon = Monitor(paths, mr)
    svc = ToolService(paths)
    maint = MaintService(paths, svc)
    mon.listeners.append(maint.collector(mr))
    app.config.update(PATHS=paths, SERVICE=svc, MOONRAKER=mr, MONITOR=mon, MAINT=maint,
                      MAX_CONTENT_LENGTH=8 * 1024 * 1024, JSON_SORT_KEYS=False)
    if start_monitor:
        mon.start()
    app.register_blueprint(routes.bp)
    app.register_blueprint(maint_routes.bp)
    app.register_blueprint(slice_routes.bp)      # prototype Slice tab; inert unless myrhino/slicer.json enables it
    app.after_request(security.add_headers)
    return app
