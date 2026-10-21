"""Install a release zip from Rhino Studio (config 1.5.3).

The Portal never installs anything itself and never runs sudo. It only:
  * checks an uploaded zip and keeps it in rhino_data/update/incoming,
  * writes rhino_data/update/request.json, which starts the root-owned updater
    (scripts/rhino_update_helper.py as /usr/local/sbin/rhino-update, via rhino-update.path),
  * reads rhino_data/update/status.json, which the updater writes as it goes.
The zip check is the updater's own (check_zip), loaded from the file next to this package;
the updater checks its own copy again before using it.

GET  /api/update              what's installed, the zips kept, the last run (status.json), whether the updater is set up
POST /api/update/upload       multipart "zip": check and keep it (nothing is installed)
POST /api/update/install      {"zip": "rhino-config-1.5.3.zip"}: ask the updater to install it (also "Go back")
POST /api/update/github       {"version": "1.5.8"}: download that release's zip from GitHub, check it like an upload
                              (and against the release's .sha256), then install it as above (1.5.8)

The newest release on GitHub (Makersmic/Toolhead_Manager, "releases/latest") is in GET /api/update as "latest",
asked at most once an hour. Releases are built by .github/workflows/release.yml: the zip with Studio inside, and its
SHA256 next to it.
"""
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, current_app, jsonify, request

from . import security
from .. import __version__
from ..errors import Fail

bp = Blueprint("update", __name__)
ZIP_RE = re.compile(r"^rhino-config-(\d+\.\d+\.\d+)\.zip$")
UNIT = os.environ.get("RHINO_UPDATE_UNIT", "/etc/systemd/system/rhino-update.path")
STALE = 50 * 60  # a run that hasn't written status for this long has died
RELEASES = os.environ.get("RHINO_RELEASES_URL", "https://api.github.com/repos/Makersmic/Toolhead_Manager/releases/latest")
DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
ZIP_MAX = 100 * 1024 * 1024
_latest = {"at": 0.0, "value": None}
_latest_lock = threading.Lock()


def _helper():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location("rhino_update_helper", os.path.join(here, "scripts", "rhino_update_helper.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def drop_dir():
    return os.path.join(current_app.config["PATHS"].state_dir, "update")


def _incoming():
    d = os.path.join(drop_dir(), "incoming")
    os.makedirs(d, exist_ok=True)
    return d


def read_status():
    try:
        with open(os.path.join(drop_dir(), "status.json")) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"state": "idle"}
    if st.get("state") == "running" and time.time() - float(st.get("updated") or 0) > STALE:
        st["state"] = "failed"
        st["error"] = "The updater stopped answering. See: journalctl -u rhino-update -n 50"
    return st


def installed_version():
    try:
        with open(os.path.expanduser("~/rhino-manager/installed-version")) as f:
            return f.read().strip() or __version__
    except OSError:
        return __version__


def _zips():
    out = []
    d = _incoming()
    for n in sorted(os.listdir(d)):
        m = ZIP_RE.match(n)
        if m:
            p = os.path.join(d, n)
            out.append({"zip": n, "version": m.group(1), "size": os.path.getsize(p), "at": os.path.getmtime(p)})
    return out


def _busy():
    st = read_status()
    return st.get("state") == "running" or os.path.exists(os.path.join(drop_dir(), "request.json"))


def _job_state():
    try:
        return current_app.config["MOONRAKER"].status().get("print_state", "standby")
    except Exception:
        return "unknown"


@bp.get("/api/update")
def state():
    return jsonify({
        "ok": True,
        "installed": installed_version(),
        "helper": os.path.exists(UNIT),
        "zips": _zips(),
        "busy": _busy(),
        "status": read_status(),
        "latest": latest_release(),
    })


@bp.post("/api/update/upload")
def upload():
    security.check_write()
    f = request.files.get("zip")
    if not f or not f.filename:
        raise Fail("Send the zip (rhino-config-<version>.zip).")
    if _busy():
        raise Fail("An install is running. Wait for it to finish.")
    d = _incoming()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".upload-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        try:
            version = _helper().check_zip(tmp)
        except ValueError as e:
            raise Fail(str(e))
        name = f"rhino-config-{version}.zip"
        os.replace(tmp, os.path.join(d, name))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return jsonify({"ok": True, "zip": name, "version": version, "installed": installed_version()})


@bp.post("/api/update/install")
def install():
    security.check_write()
    body = security.json_body()
    name = str(body.get("zip", ""))
    if not ZIP_RE.match(name) or not os.path.isfile(os.path.join(_incoming(), name)):
        raise Fail("That zip isn't here. Upload it again.")
    return jsonify(_request_install(name))


def _request_install(name):
    """Hand a kept zip to the root-owned updater. Same checks for every way in (upload, Go back, GitHub)."""
    if not os.path.exists(UNIT):
        raise Fail("The updater isn't set up on this Rhino yet. Install this zip once by hand (rhino.sh option 3); "
                   "after that, Studio can install the next ones.")
    if _busy():
        raise Fail("An install is already running.")
    js = _job_state()
    if js in ("printing", "paused"):
        raise Fail(f"A job is {js}. Finish or cancel it first.")
    d = drop_dir()
    # the updater's status is replaced as soon as it starts; say "waiting" until then
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".status-")
    with os.fdopen(fd, "w") as out:
        json.dump({"state": "running", "zip": name, "version": ZIP_RE.match(name).group(1), "from_version": installed_version(),
                   "step": -1, "step_name": "Waiting for the updater", "started": time.time(), "updated": time.time(), "log": []}, out)
    os.replace(tmp, os.path.join(d, "status.json"))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".request-")
    with os.fdopen(fd, "w") as out:
        json.dump({"zip": name, "at": time.time()}, out)
    os.replace(tmp, os.path.join(d, "request.json"))  # rhino-update.path starts the updater now
    return {"ok": True, "zip": name}


# ----------------------------------------------------------------------------- GitHub releases (1.5.8)
def _get(url, limit, timeout=20, accept="application/octet-stream"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"rhino-tool-manager/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        host = urllib.parse.urlparse(r.geturl()).hostname or ""
        if url.startswith("https://") and not (host in DOWNLOAD_HOSTS or host.endswith(".githubusercontent.com") or host == "api.github.com"):
            raise Fail(f"GitHub sent the download somewhere unexpected ({host}).")
        data = r.read(limit + 1)
    if len(data) > limit:
        raise Fail("The download is bigger than a release zip can be.")
    return data


def latest_release(force=False):
    """{version, zip, url, sha256_url, published, notes_url} of the newest release, {error} if GitHub can't say,
    None before the first answer. Asked at most once an hour (GitHub allows 60 unsigned requests an hour)."""
    with _latest_lock:
        if not force and _latest["value"] is not None and time.time() - _latest["at"] < 3600:
            return _latest["value"]
    try:
        rel = json.loads(_get(RELEASES, 2 * 1024 * 1024, timeout=8, accept="application/vnd.github+json"))
        assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets") or []}
        zips = [n for n in assets if n and ZIP_RE.match(n)]
        if not zips:
            out = {"error": f"The newest release ({rel.get('tag_name')}) has no rhino-config zip."}
        else:
            z = zips[0]
            out = {"version": ZIP_RE.match(z).group(1), "zip": z, "url": assets[z], "sha256_url": assets.get(z + ".sha256"),
                   "published": rel.get("published_at"), "notes_url": rel.get("html_url")}
    except Fail as e:
        out = {"error": str(e)}
    except (urllib.error.URLError, OSError, ValueError) as e:
        code = getattr(e, "code", None)
        out = {"error": "No releases on GitHub yet." if code == 404 else "Can't reach GitHub from the Rhino right now."}
    with _latest_lock:
        _latest.update(at=time.time(), value=out)
    return out


@bp.post("/api/update/github")
def from_github():
    """Download the newest release's zip, check it, install it. Only the version GitHub names as newest."""
    security.check_write()
    want = str(security.json_body().get("version", ""))
    if _busy():
        raise Fail("An install is already running.")
    js = _job_state()
    if js in ("printing", "paused"):
        raise Fail(f"A job is {js}. Finish or cancel it first.")
    rel = latest_release(force=True)
    if not rel or rel.get("error"):
        raise Fail((rel or {}).get("error") or "GitHub didn't answer.")
    if rel["version"] != want:
        raise Fail(f"GitHub's newest release is now {rel['version']}, not {want}. Check again.")
    if not rel.get("sha256_url"):
        raise Fail(f"Release {want} has no .sha256 next to its zip, so it can't be checked. Use Install from zip instead.")
    try:
        sha_line = _get(rel["sha256_url"], 4096).decode("ascii", "replace").split()
        expect = sha_line[0].lower() if sha_line else ""
        if not re.fullmatch(r"[0-9a-f]{64}", expect):
            raise Fail("The release's .sha256 file isn't a SHA256.")
        data = _get(rel["url"], ZIP_MAX, timeout=300)
    except (urllib.error.URLError, OSError) as e:
        raise Fail(f"Downloading {rel['zip']} from GitHub didn't work ({e.__class__.__name__}). Try again, or use Install from zip.")
    if hashlib.sha256(data).hexdigest() != expect:
        raise Fail(f"{rel['zip']} from GitHub doesn't match its .sha256, so it wasn't kept.")
    d = _incoming()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".github-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        try:
            version = _helper().check_zip(tmp)
        except ValueError as e:
            raise Fail(str(e))
        if version != want:
            raise Fail(f"The zip says it is {version}, not {want}.")
        name = f"rhino-config-{version}.zip"
        os.replace(tmp, os.path.join(d, name))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return jsonify(_request_install(name))
