"""The Klipper extras this package ships (klipper_extras/*.py), linked into Klipper's klippy/extras by install.sh.

status(cfg_dir)  -> what is shipped and whether each link is in place (read only); all_linked sums it up.
relink(cfg_dir)  -> make or mend the links (the user owns ~/klipper, so no sudo); refuses when Klipper isn't there.
Klipper's folder: $KLIPPER_DIR or ~/klipper. A link is "ok" when it exists, points at our file and the file exists.
"""
import os

from .errors import Fail


def klipper_dir():
    return os.environ.get("KLIPPER_DIR") or os.path.expanduser("~/klipper")


def _extras_dir():
    return os.path.join(klipper_dir(), "klippy", "extras")


def shipped(cfg_dir):
    d = os.path.join(cfg_dir, "klipper_extras")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".py") and not f.startswith("_"))


def status(cfg_dir):
    ext = _extras_dir()
    found = os.path.isdir(ext)
    out = []
    for f in shipped(cfg_dir):
        target = os.path.join(cfg_dir, "klipper_extras", f)
        link = os.path.join(ext, f)
        linked = os.path.islink(link) and os.path.realpath(link) == os.path.realpath(target) and os.path.isfile(link)
        other = os.path.lexists(link) and not linked
        out.append({"name": f[:-3], "file": f, "linked": bool(linked), "in_the_way": bool(other)})
    return {"ok": True, "klipper_dir": klipper_dir(), "found": found, "extras": out,
            "all_linked": found and all(e["linked"] for e in out)}


def relink(cfg_dir):
    ext = _extras_dir()
    if not os.path.isdir(ext):
        raise Fail(f"Klipper's extras folder isn't at {ext}. If Klipper lives somewhere else, set KLIPPER_DIR for the "
                   f"portal service; otherwise install Klipper first.")
    for f in shipped(cfg_dir):
        target = os.path.join(cfg_dir, "klipper_extras", f)
        link = os.path.join(ext, f)
        if os.path.lexists(link) and not os.path.islink(link):
            raise Fail(f"{link} is a real file, not a link. Move it aside first; nothing was changed.")
        tmp = link + ".rhino-tmp"
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(target, tmp)
        os.replace(tmp, link)
    return status(cfg_dir)
