"""Tool photos: validated, renamed, and stored OUTSIDE the Klipper config directory."""
import os
import re
import secrets

from ..errors import Fail
from ..presets import NAME_RE

MAX_BYTES = 6 * 1024 * 1024
# extension -> leading bytes that must match (browsers lie about content types, files do not)
SIGNATURES = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
              ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",)}
_FILE_RE = re.compile(r"^[0-9a-f]{16}\.(png|jpe?g|gif|webp)$")


def _dir(paths, tool, create=False):
    if not NAME_RE.match(tool or ""):
        raise Fail("Bad tool name")
    d = os.path.join(paths.images_dir, tool)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def valid_filename(name):
    return bool(_FILE_RE.match(name or ""))


def save(paths, tool, upload):
    """Store one uploaded file (werkzeug FileStorage). Returns the stored file name."""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in SIGNATURES:
        raise Fail("Photos must be PNG, JPG, GIF or WEBP files")
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Fail(f"Photo is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not any(data.startswith(sig) for sig in SIGNATURES[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise Fail("That file is not really a " + ext[1:].upper() + " image")
    name = secrets.token_hex(8) + (".jpg" if ext == ".jpeg" else ext)
    with open(os.path.join(_dir(paths, tool, create=True), name), "wb") as f:
        f.write(data)
    return name


def path_for(paths, tool, filename):
    if not valid_filename(filename):
        raise Fail("Bad file name")
    return os.path.join(_dir(paths, tool), filename)


def delete(paths, tool, filename):
    try:
        os.remove(path_for(paths, tool, filename))
    except FileNotFoundError:
        pass


def delete_all(paths, tool):
    d = _dir(paths, tool)
    if os.path.isdir(d):
        for f in os.listdir(d):
            if valid_filename(f):
                os.remove(os.path.join(d, f))
        try:
            os.rmdir(d)
        except OSError:
            pass
