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


# ---- fonts for Studio's themes, in images/_theme/fonts: backed up with the pictures, outside the config folder.
# The file name is random, so a name can't reach outside the folder; the name the person gave is kept beside it in a .name file.
FONT_DIR = os.path.join(THEME_DIR, "fonts")
MAX_THEME_FONTS = 12
MAX_FONT_BYTES = 2 * 1024 * 1024
FONT_SIGNATURES = {".woff2": (b"wOF2",), ".woff": (b"wOFF",), ".ttf": (b"\x00\x01\x00\x00", b"true"), ".otf": (b"OTTO",)}
FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}
_FONT_RE = re.compile(r"^[0-9a-f]{16}\.(woff2|woff|ttf|otf)$")
_FONT_LABEL_BAD = re.compile(r"[^A-Za-z0-9 ._-]+")


def valid_font(name):
    return bool(_FONT_RE.match(name or ""))


def font_type(name):
    return FONT_TYPES[os.path.splitext(name)[1].lower()]


def _font_dir(paths):
    return os.path.join(paths.images_dir, FONT_DIR)


def font_label(upload_name):
    """A short, plain name for the list, from the file name the person chose."""
    stem = os.path.splitext(os.path.basename(upload_name or ""))[0]
    return _FONT_LABEL_BAD.sub(" ", stem).strip()[:40] or "Uploaded font"


def font_list(paths):
    d = _font_dir(paths)
    if not os.path.isdir(d):
        return []
    out = []
    for f in os.listdir(d):
        if valid_font(f):
            s = os.stat(os.path.join(d, f))
            try:
                with open(os.path.join(d, f.rsplit(".", 1)[0] + ".name"), encoding="utf-8") as h:
                    label = font_label(h.read(80))
            except OSError:
                label = "Uploaded font"
            out.append({"name": f, "label": label, "size": s.st_size, "added": int(s.st_mtime)})
    return sorted(out, key=lambda x: (x["added"], x["name"]))


def font_save(paths, upload):
    if len(font_list(paths)) >= MAX_THEME_FONTS:
        raise Fail(f"There are already {MAX_THEME_FONTS} fonts on the Rhino. Delete one first.")
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in FONT_SIGNATURES:
        raise Fail("Fonts must be WOFF2, WOFF, TTF or OTF files")
    data = upload.read(MAX_FONT_BYTES + 1)
    if len(data) > MAX_FONT_BYTES:
        raise Fail(f"That font is larger than {MAX_FONT_BYTES // (1024 * 1024)} MB")
    if not any(data.startswith(sig) for sig in FONT_SIGNATURES[ext]):
        raise Fail("That file is not really a " + ext[1:].upper() + " font")
    d = _font_dir(paths)
    os.makedirs(d, exist_ok=True)
    stem = secrets.token_hex(8)
    name = stem + ext
    tmp = os.path.join(d, name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(d, name))
    with open(os.path.join(d, stem + ".name"), "w", encoding="utf-8") as f:
        f.write(font_label(upload.filename))
    return name


def font_path(paths, filename):
    if not valid_font(filename):
        raise Fail("Bad file name")
    return os.path.join(_font_dir(paths), filename)


def font_delete(paths, filename):
    p = font_path(paths, filename)
    for q in (p, p.rsplit(".", 1)[0] + ".name"):
        try:
            os.remove(q)
        except FileNotFoundError:
            pass
