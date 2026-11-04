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


# ---- background pictures for Studio's themes, in images/_theme: backed up with the photos, outside the config folder.
# NAME_RE needs a tool name to start with a letter or digit, so no tool can be called _theme.
THEME_DIR = "_theme"
MAX_THEME_IMAGES = 12


def theme_list(paths):
    d = os.path.join(paths.images_dir, THEME_DIR)
    if not os.path.isdir(d):
        return []
    out = []
    for f in os.listdir(d):
        if valid_filename(f):
            s = os.stat(os.path.join(d, f))
            out.append({"name": f, "size": s.st_size, "added": int(s.st_mtime)})
    return sorted(out, key=lambda x: (x["added"], x["name"]))


def theme_save(paths, upload):
    if len(theme_list(paths)) >= MAX_THEME_IMAGES:
        raise Fail(f"There are already {MAX_THEME_IMAGES} background pictures on the Rhino. Delete one first.")
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in SIGNATURES:
        raise Fail("Background pictures must be PNG, JPG, GIF or WEBP files")
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Fail(f"That picture is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not any(data.startswith(sig) for sig in SIGNATURES[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise Fail("That file is not really a " + ext[1:].upper() + " image")
    d = os.path.join(paths.images_dir, THEME_DIR)
    os.makedirs(d, exist_ok=True)
    name = secrets.token_hex(8) + (".jpg" if ext == ".jpeg" else ext)
    tmp = os.path.join(d, name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(d, name))
    return name


def theme_path(paths, filename):
    if not valid_filename(filename):
        raise Fail("Bad file name")
    return os.path.join(paths.images_dir, THEME_DIR, filename)


def theme_delete(paths, filename):
    try:
        os.remove(theme_path(paths, filename))
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
