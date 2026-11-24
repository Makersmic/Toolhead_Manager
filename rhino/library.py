"""The model library (docs/proposal-stl-library.md): a folder the Portal owns, `~/printer_data/models/`, where STL and
other model files are kept, browsed and picked from in Rhino Studio (Files > Models).

Everything here is plain file handling with no Flask in it, so it is tested alone (dev/test_library.py).

Rules that keep it safe to leave alone:
- A path is a list of names under the root. No `..`, no hidden names, no links anywhere on the way, at most 6 deep, and the
  resolved path must still be inside the root. A path outside the library is refused, never "fixed".
- A file is checked by its contents (an STL must be an STL), not by its name, before it is kept.
- A file arrives under a temporary name, is flushed to the disk, then renamed: a power cut or a pulled drive leaves no half
  model. A leftover temporary file is ignored by the listing and removed by `sweep()`.
- Nothing is written when it would leave less than FREE_FLOOR free on the disk (a full disk stops Klipper's own logs).
- Delete is straight away (Mike, Nov 23: no trash). The caller says what will go before it asks.
"""
import hashlib
import os
import re
import shutil
import tempfile
import time
import zipfile

from .errors import Fail

TYPES = ("stl", "obj", "3mf", "svg", "dxf")           # what job setup takes (Studio MODEL_TYPES)
MAX_DEPTH = 6
MAX_NAME = 120
MAX_FILE = 210 * 1024 * 1024                          # the same limit as a slicer upload (nginx allows 210 MB on /portal/)
FREE_FLOOR = 2 * 1024 ** 3
PAGE = 200
_BAD = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
TMP_PREFIX = ".incoming-"


def kind_of(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in TYPES else ""


def check_name(name, what="name"):
    if not isinstance(name, str) or not name.strip():
        raise Fail(f"The {what} is empty.")
    if name != name.strip() or name in (".", "..") or name.startswith(".") or name.endswith("."):
        raise Fail(f"'{name}' isn't a usable {what}: no leading dot, no spaces at the ends, nothing ending in a dot.")
    if len(name) > MAX_NAME or _BAD.search(name):
        raise Fail(f"'{name}' isn't a usable {what}: up to {MAX_NAME} characters, and none of / \\ : * ? \" < > |.")
    return name


def check_content(path, kind):
    """The file's contents must be what its name says. Raises Fail with a reason."""
    size = os.path.getsize(path)
    if size == 0:
        raise Fail("The file is empty.")
    with open(path, "rb") as f:
        head = f.read(4096)
    if kind == "stl":
        if size >= 84:
            n = int.from_bytes(head[80:84], "little")
            if 84 + 50 * n == size and n > 0:
                return
        if head.lstrip()[:5].lower() == b"solid" and b"facet" in head + _tail(path) and b"vertex" in head + _tail(path):
            return
        raise Fail("That isn't an STL file: it is neither a whole binary STL nor a text STL (it may be cut short).")
    if kind == "obj":
        if b"\0" in head or not re.search(rb"^v\s+[-+0-9.eE]+\s+[-+0-9.eE]+", head, re.M):
            raise Fail("That isn't an OBJ file: no vertex lines at the start.")
        return
    if kind == "3mf":
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                if "3D/3dmodel.model" not in names:
                    raise Fail("That isn't a 3MF file: it has no 3D/3dmodel.model inside.")
                total = sum(i.file_size for i in z.infolist())
                if total > 2 * 1024 ** 3 or (size and total / size > 200):
                    raise Fail("That 3MF unpacks to far more than its size (a zip bomb, or a broken file), so it isn't kept.")
        except zipfile.BadZipFile:
            raise Fail("That isn't a 3MF file: it isn't a zip file.")
        return
    if kind == "svg":
        if b"<svg" not in head.lower():
            raise Fail("That isn't an SVG file: no <svg> at the start.")
        return
    if kind == "dxf":
        if head.startswith(b"AutoCAD Binary DXF") or re.search(rb"SECTION", head):
            return
        raise Fail("That isn't a DXF file: no SECTION at the start.")
    raise Fail("That kind of file isn't kept in the library.")


def _tail(path, n=4096):
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - n))
        return f.read()


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Library:
    def __init__(self, root, free=None, floor=FREE_FLOOR):
        self.root = os.path.abspath(root)
        self._free = free or (lambda p: shutil.disk_usage(p).free)
        self.floor = floor

    # ------------------------------------------------------------------ paths
    def parts(self, path):
        """'a/b' -> ['a','b'] after checking every name; '' is the root."""
        if path in (None, "", "/"):
            return []
        if not isinstance(path, str):
            raise Fail("The path isn't text.")
        parts = [p for p in path.strip("/").split("/")]
        if len(parts) > MAX_DEPTH:
            raise Fail(f"Folders go {MAX_DEPTH} deep at most.")
        for p in parts:
            check_name(p, "folder or file name")
        return parts

    def real(self, path, must_exist=True):
        """The path on disk, proven to be inside the library with no link on the way."""
        cur = self.root
        for p in self.parts(path):
            cur = os.path.join(cur, p)
            if os.path.islink(cur):
                raise Fail("Links aren't followed in the library.")
        if os.path.commonpath([os.path.realpath(cur), os.path.realpath(self.root)]) != os.path.realpath(self.root):
            raise Fail("That path is outside the library.")
        if must_exist and not os.path.exists(cur):
            raise Fail("That isn't in the library (it may have been moved or deleted).")
        return cur

    def ensure_root(self):
        os.makedirs(self.root, exist_ok=True)

    # ------------------------------------------------------------------ reading
    def list(self, path="", offset=0, limit=PAGE):
        if not self.parts(path) and not os.path.isdir(self.root):      # nothing kept yet: the folder is made by the first upload
            return {"path": "", "total": 0, "offset": 0, "entries": []}
        d = self.real(path)
        if not os.path.isdir(d):
            raise Fail("That isn't a folder.")
        rows = []
        try:
            names = sorted(os.listdir(d), key=str.lower)
        except OSError as e:
            raise Fail(f"The folder can't be read: {e.strerror or e}")
        for n in names:
            if n.startswith("."):
                continue
            fp = os.path.join(d, n)
            if os.path.islink(fp):
                continue
            try:
                st = os.stat(fp)
            except OSError:
                continue
            if os.path.isdir(fp):
                try:
                    inside = sum(1 for x in os.listdir(fp) if not x.startswith("."))
                except OSError:
                    inside = 0
                rows.append({"name": n, "dir": True, "modified": st.st_mtime, "items": inside})
            elif kind_of(n):
                rows.append({"name": n, "dir": False, "size": st.st_size, "modified": st.st_mtime, "kind": kind_of(n)})
        rows.sort(key=lambda r: (not r["dir"],))     # folders first, the name order kept inside each
        total = len(rows)
        offset = max(0, int(offset))
        limit = max(1, min(PAGE, int(limit)))
        return {"path": "/".join(self.parts(path)), "total": total, "offset": offset, "entries": rows[offset:offset + limit]}

    def file(self, path):
        fp = self.real(path)
        if not os.path.isfile(fp) or not kind_of(os.path.basename(fp)):
            raise Fail("That isn't a model file in the library.")
        return fp

    def usage(self):
        files = size = 0
        if os.path.isdir(self.root):
            for dp, dn, fn in os.walk(self.root):
                dn[:] = [d for d in dn if not d.startswith(".") and not os.path.islink(os.path.join(dp, d))]
                for n in fn:
                    fp = os.path.join(dp, n)
                    if not n.startswith(".") and not os.path.islink(fp):
                        try:
                            size += os.path.getsize(fp)
                            files += 1
                        except OSError:
                            pass
        probe = self.root if os.path.isdir(self.root) else os.path.dirname(self.root)
        return {"files": files, "bytes": size, "free": self._free(probe), "floor": self.floor, "max_file": MAX_FILE,
                "types": list(TYPES), "root": self.root}

    # ------------------------------------------------------------------ writing
    def save(self, folder, name, tmp_path, mode=""):
        """Keep the uploaded file at `tmp_path` as folder/name. mode: '' (ask on a clash), 'replace', 'both'.
        -> {'name', 'status': 'added'|'same'|'replaced'|'renamed'}. `tmp_path` is consumed (moved or removed)."""
        try:
            check_name(name, "file name")
            kind = kind_of(name)
            if not kind:
                raise Fail(f"'{name}' isn't a kind of model the library keeps ({', '.join(TYPES)}).")
            size = os.path.getsize(tmp_path)
            if size > MAX_FILE:
                raise Fail(f"'{name}' is bigger than {MAX_FILE // 1048576} MB, the most the library takes.")
            self.ensure_root()
            dest_dir = self.real(folder)
            if not os.path.isdir(dest_dir):
                raise Fail("That folder isn't in the library.")
            if self._free(self.root) - size < self.floor:
                raise Fail(f"Not enough room: the disk must keep {self.floor // 1024 ** 3} GB free for Klipper. Free some space or delete models.")
            check_content(tmp_path, kind)
            dest = os.path.join(dest_dir, name)
            status = "added"
            if os.path.lexists(dest):
                if os.path.islink(dest) or os.path.isdir(dest):
                    raise Fail(f"'{name}' is a folder or a link here, so a file can't take its place.")
                if os.path.getsize(dest) == size and sha(dest) == sha(tmp_path):
                    return {"name": name, "status": "same"}
                if mode == "replace":
                    status = "replaced"
                elif mode == "both":
                    name, dest = self._free_name(dest_dir, name), None
                    dest = os.path.join(dest_dir, name)
                    status = "renamed"
                else:
                    raise Clash(f"'{name}' is already here with different contents.")
            self._place(tmp_path, dest)
            return {"name": name, "status": status}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _free_name(d, name):
        stem, dot, ext = name.rpartition(".")
        for i in range(2, 1000):
            cand = f"{stem} ({i}).{ext}"
            if not os.path.lexists(os.path.join(d, cand)):
                return cand
        raise Fail("Too many copies of that name.")

    @staticmethod
    def _place(src, dest):
        """Copy to a temporary name beside the target, flush, rename, flush the folder. (src may be on another disk.)"""
        d = os.path.dirname(dest)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=TMP_PREFIX)
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
                shutil.copyfileobj(inp, out, 1 << 20)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        try:
            dfd = os.open(d, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass

    def mkdir(self, folder, name):
        check_name(name, "folder name")
        self.ensure_root()
        parent = self.real(folder)
        if len(self.parts(folder)) + 1 > MAX_DEPTH:
            raise Fail(f"Folders go {MAX_DEPTH} deep at most.")
        d = os.path.join(parent, name)
        if os.path.lexists(d):
            raise Fail(f"'{name}' is already here.")
        os.mkdir(d, 0o755)

    def rename(self, path, new_name):
        check_name(new_name, "new name")
        src = self.real(path)
        if not self.parts(path):
            raise Fail("The library folder itself can't be renamed.")
        if os.path.isfile(src) and kind_of(new_name) != kind_of(os.path.basename(src)):
            raise Fail("A model keeps its kind: the new name must end the same way.")
        dest = os.path.join(os.path.dirname(src), new_name)
        if os.path.lexists(dest):
            raise Fail(f"'{new_name}' is already here.")
        os.rename(src, dest)

    def move(self, path, folder):
        src = self.real(path)
        if not self.parts(path):
            raise Fail("The library folder itself can't be moved.")
        dest_dir = self.real(folder)
        if not os.path.isdir(dest_dir):
            raise Fail("That folder isn't in the library.")
        if os.path.commonpath([os.path.realpath(dest_dir), os.path.realpath(src)]) == os.path.realpath(src):
            raise Fail("A folder can't go inside itself.")
        if len(self.parts(folder)) + 1 + (self._depth(src) if os.path.isdir(src) else 0) > MAX_DEPTH:
            raise Fail(f"That would put folders more than {MAX_DEPTH} deep.")
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.lexists(dest):
            raise Fail(f"'{os.path.basename(src)}' is already in that folder.")
        os.rename(src, dest)

    @staticmethod
    def _depth(d):
        deepest = 0
        for dp, dn, _ in os.walk(d):
            deepest = max(deepest, dp[len(d):].count(os.sep))
        return deepest + 1

    def count(self, path):
        """What deleting `path` would remove: {'files', 'folders'}."""
        p = self.real(path)
        if os.path.isfile(p):
            return {"files": 1, "folders": 0}
        files = folders = 0
        for dp, dn, fn in os.walk(p):
            folders += len(dn)
            files += len(fn)
        return {"files": files, "folders": folders + 1}

    def delete(self, path):
        if not self.parts(path):
            raise Fail("The library folder itself can't be deleted.")
        p = self.real(path)
        n = self.count(path)
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.unlink(p)
        return n

    def sweep(self, older=3600):
        """Remove temporary files an interrupted upload left behind. -> how many."""
        n = 0
        if not os.path.isdir(self.root):
            return 0
        for dp, dn, fn in os.walk(self.root):
            for f in fn:
                fp = os.path.join(dp, f)
                if f.startswith(TMP_PREFIX) and time.time() - os.path.getmtime(fp) > older:
                    try:
                        os.unlink(fp)
                        n += 1
                    except OSError:
                        pass
        return n


class Clash(Fail):
    """The name is taken by a different file: the caller asks what to do (replace, keep both, cancel)."""
