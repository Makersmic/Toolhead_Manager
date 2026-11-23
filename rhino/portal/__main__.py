"""python3 -m rhino.portal [--host 0.0.0.0] [--port 5000] [--config-dir DIR]"""
import argparse
import logging
import signal
import sys

from . import create_app
from .watchdog import Watchdog


def main():
    ap = argparse.ArgumentParser(prog="rhino.portal")
    ap.add_argument("--host", default="0.0.0.0", help="address to listen on (default: whole LAN)")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--config-dir", help="Klipper config dir (default $RHINO_CONFIG_DIR or ~/printer_data/config)")
    ap.add_argument("--moonraker", help="Moonraker URL (default http://127.0.0.1:7125)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = create_app(a.config_dir, a.moonraker, start_monitor=True)
    print(f"Rhino portal on http://{a.host}:{a.port}  (config: {app.config['PATHS'].cfg})")

    dog = Watchdog(f"http://127.0.0.1:{a.port}/api/ping")

    def stop(*_):                       # systemctl stop / restart: save the meters first
        dog.stop()
        app.config["MONITOR"].stop()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    dog.start()                         # only when systemd started us with a watchdog (see watchdog.py)
    try:
        from waitress import serve        # preferred if installed
        serve(app, host=a.host, port=a.port, threads=8)
    except ImportError:
        app.run(host=a.host, port=a.port, debug=False, threaded=True)
    finally:
        app.config["MONITOR"].stop()


if __name__ == "__main__":
    main()
