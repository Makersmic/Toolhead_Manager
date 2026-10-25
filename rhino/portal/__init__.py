"""Rhino tool portal: a small Flask app on top of rhino.service.ToolService."""
import os

from flask import Flask

from ..backup import BackupService
from ..maint import MaintService
from ..monitor import Monitor
from ..moonraker import Moonraker
from ..net import Network
from ..prusa import PrusaService
from ..paths import resolve
from ..service import ToolService
from ..slice_profiles import SliceProfiles
from . import backup_routes, maint_routes, net_routes, profile_routes, routes, security, slicer_routes, trust_routes, update_routes
from .access import Access


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
    app.config.update(PATHS=paths, SERVICE=svc, MOONRAKER=mr, MONITOR=mon, MAINT=maint, NETWORK=Network(),
                      ACCESS=Access(mr, paths.state_dir),
                      MAX_CONTENT_LENGTH=210 * 1024 * 1024, JSON_SORT_KEYS=False)
    app.config["BACKUP"] = BackupService(paths, mr, backup_dir=os.environ.get("RHINO_BACKUP_DIR") or None)
    app.config["PROFILES"] = SliceProfiles(paths)
    app.config["PRUSA"] = PrusaService(os.path.join(paths.state_dir, "prusaslicer"), slicer_routes.printer_state_from(mr))
    mon.listeners.append(slicer_routes.AutoUpdater(app.config["PRUSA"]))   # PrusaSlicer updates itself while in use (1.5.8)
    if start_monitor:
        mon.start()
    app.register_blueprint(routes.bp)
    app.register_blueprint(maint_routes.bp)
    app.register_blueprint(net_routes.bp)
    app.register_blueprint(slicer_routes.bp)
    app.register_blueprint(update_routes.bp)
    app.register_blueprint(trust_routes.bp)
    app.register_blueprint(backup_routes.bp)
    app.register_blueprint(profile_routes.bp)
    app.before_request(app.config["ACCESS"].gate)      # Moonraker's trusted_clients decides who may use /api (1.5.4)
    app.before_request(security.limit_upload)
    app.after_request(security.add_headers)
    return app
