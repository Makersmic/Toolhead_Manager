"""The model library (docs/proposal-stl-library.md): rhino/library.py and the Portal's /api/library routes.
Run: python3 dev/test_library.py  (needs flask)"""
import atexit, io, json, os, shutil, struct, sys, tempfile, zipfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix="rhino-lib-test-")
atexit.register(shutil.rmtree, ROOT, True)
shutil.copytree(os.path.dirname(HERE), ROOT + "/printer_data/config", ignore=shutil.ignore_patterns("__pycache__", "registry_backups"))
sys.path.insert(0, ROOT + "/printer_data/config")
from rhino import library
from rhino.errors import Fail
from rhino.library import Library, Clash

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)
def raises(fn, text="", cls=Fail):
    try:
        fn()
    except cls as e:
        return text.lower() in str(e).lower()
    return False

def stl(n=2):
    return b"\0" * 80 + struct.pack("<I", n) + b"\0" * (50 * n)
def ascii_stl():
    return b"solid t\n facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 1 0 0\n   vertex 0 1 0\n  endloop\n endfacet\nendsolid t\n"
def threemf():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
    return b.getvalue()
def tmpfile(data):
    fd, p = tempfile.mkstemp(dir=ROOT)
    os.write(fd, data); os.close(fd)
    return p

LIB = os.path.join(ROOT, "models")
lib = Library(LIB, free=lambda p: 100 * 1024 ** 3)

# --- names and paths ------------------------------------------------------------------------------------------
for bad in ["../x", "a/../../etc", "a/.hidden", "/etc/passwd/../x", "a\\b", "a:b", "a/" * 7 + "b", ".", "a/./b"]:
    ok(raises(lambda b=bad: lib.parts(b)) or raises(lambda b=bad: lib.real(b, False)), f"path refused: {bad!r}")
ok(lib.parts("a/b") == ["a", "b"] and lib.parts("") == [] and lib.parts("/") == [], "good paths and the root")
ok(raises(lambda: library.check_name("x" * 121)) and raises(lambda: library.check_name(" x")) and raises(lambda: library.check_name("a|b")), "bad names refused")

# --- content checks -------------------------------------------------------------------------------------------
def kept(name, data, folder="", mode=""):
    return lib.save(folder, name, tmpfile(data), mode)
ok(kept("cube.stl", stl())["status"] == "added", "a binary STL is kept")
ok(kept("t.stl", ascii_stl())["status"] == "added", "a text STL is kept")
ok(kept("p.3mf", threemf())["status"] == "added", "a 3MF is kept")
ok(kept("o.obj", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")["status"] == "added", "an OBJ is kept")
ok(kept("d.dxf", b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n")["status"] == "added", "a DXF is kept")
ok(kept("l.svg", b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>")["status"] == "added", "an SVG is kept")
ok(raises(lambda: kept("cut.stl", stl(5)[:-10]), "isn't an STL"), "a cut-short binary STL is refused")
ok(raises(lambda: kept("x.stl", b"hello world"), "isn't an STL"), "text called .stl is refused")
ok(raises(lambda: kept("x.3mf", b"PK not a zip"), "zip"), "a bad 3MF is refused")
b = io.BytesIO()
with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("3D/3dmodel.model", b"0" * 50_000_000)
ok(raises(lambda: kept("bomb.3mf", b.getvalue()), "zip bomb"), "a 3MF that unpacks to 200 times its size is refused")
ok(raises(lambda: kept("x.gcode", b"G1 X1"), "isn't a kind"), "G-code isn't kept here")
ok(raises(lambda: kept("e.stl", b""), "empty"), "an empty file is refused")
ok(raises(lambda: kept("../evil.stl", stl()), "usable"), "a name with .. is refused")

# --- clashes --------------------------------------------------------------------------------------------------
ok(kept("cube.stl", stl())["status"] == "same", "the same file again says it is already here")
ok(raises(lambda: kept("cube.stl", stl(3)), "already here", Clash), "a different file with the same name asks")
ok(kept("cube.stl", stl(3), mode="both")["name"] == "cube (2).stl", "keep both names the new one (2)")
ok(kept("cube.stl", stl(4), mode="replace")["status"] == "replaced" and os.path.getsize(os.path.join(LIB, "cube.stl")) == 84 + 200, "replace replaces")

# --- folders, rename, move, delete ----------------------------------------------------------------------------
lib.mkdir("", "Bracket")
lib.mkdir("Bracket", "v2")
ok(raises(lambda: lib.mkdir("", "Bracket"), "already here"), "a folder name twice is refused")
kept("a.stl", stl(), "Bracket/v2")
ok(raises(lambda: lib.save("Nope", "a.stl", tmpfile(stl())), "isn't in the library"), "saving into a missing folder is refused")
lib.rename("Bracket/v2/a.stl", "b.stl")
ok(raises(lambda: lib.rename("Bracket/v2/b.stl", "b.obj"), "keeps its kind"), "a rename can't change the kind")
lib.move("Bracket/v2/b.stl", "")
ok(os.path.isfile(os.path.join(LIB, "b.stl")), "move a file to the top")
ok(raises(lambda: lib.move("Bracket", "Bracket/v2"), "inside itself"), "a folder can't go inside itself")
ok(raises(lambda: lib.move("b.stl", ""), "already in"), "moving onto the same place is refused")
d = lib.list("")
ok([e["name"] for e in d["entries"]][:1] == ["Bracket"] and d["entries"][0]["dir"] and d["entries"][0]["items"] == 1, "listing: folders first, with a count")
ok(all(not e["name"].startswith(".") for e in d["entries"]) and {"kind": "stl"}.items() <= next(e for e in d["entries"] if e["name"] == "b.stl").items(), "listing hides dot files and gives the kind")
open(os.path.join(LIB, "notes.txt"), "w").write("x")
ok("notes.txt" not in [e["name"] for e in lib.list("")["entries"]], "listing shows only model files")
ok(lib.count("Bracket") == {"files": 0, "folders": 2}, "count: what a delete would remove")
ok(lib.delete("Bracket") == {"files": 0, "folders": 2} and not os.path.exists(os.path.join(LIB, "Bracket")), "delete a folder straight away")
ok(raises(lambda: lib.delete(""), "can't be deleted"), "the library folder can't be deleted")
ok(raises(lambda: lib.delete("nope.stl"), "isn't in the library"), "deleting a missing file says so")

# --- links and the outside ------------------------------------------------------------------------------------
outside = os.path.join(ROOT, "outside"); os.makedirs(outside)
open(os.path.join(outside, "secret.stl"), "wb").write(stl())
os.symlink(outside, os.path.join(LIB, "link"))
os.symlink(os.path.join(outside, "secret.stl"), os.path.join(LIB, "l.stl"))
ok(raises(lambda: lib.list("link"), "links") and raises(lambda: lib.file("l.stl"), "links"), "a link out of the library is refused")
ok("link" not in [e["name"] for e in lib.list("")["entries"]] and "l.stl" not in [e["name"] for e in lib.list("")["entries"]], "links aren't listed")
ok(raises(lambda: lib.save("link", "x.stl", tmpfile(stl())), "links"), "saving through a link is refused")

# --- space ----------------------------------------------------------------------------------------------------
low = Library(LIB, free=lambda p: library.FREE_FLOOR + 100)
ok(raises(lambda: low.save("", "big.stl", tmpfile(stl(10))), "not enough room"), "an upload that would leave under 2 GB free is refused")
u = lib.usage()
ok(u["files"] >= 5 and u["free"] == 100 * 1024 ** 3 and u["floor"] == library.FREE_FLOOR, "usage: files, bytes, free, floor")

# --- a power cut / interrupted upload -------------------------------------------------------------------------
t = os.path.join(LIB, library.TMP_PREFIX + "abc"); open(t, "wb").write(b"half")
ok(t.split("/")[-1] not in [e["name"] for e in lib.list("")["entries"]], "a half file isn't listed")
os.utime(t, (1, 1))
ok(lib.sweep() == 1 and not os.path.exists(t), "sweep removes an old half file")

ok(Library(os.path.join(ROOT, 'nothere')).list('')['total'] == 0, 'a library with no folder yet lists as empty, not an error')
ok(raises(lambda: Library(os.path.join(ROOT, 'nothere')).list('x'), 'isn\'t in the library'), 'a missing sub-folder of it is still refused')

# --- the Portal ------------------------------------------------------------------------------------------------
os.environ["RHINO_MODELS_DIR"] = os.path.join(ROOT, "pmodels")
from rhino.portal import create_app, security
app = create_app(ROOT + "/printer_data/config", moonraker_url="http://127.0.0.1:9")
c = app.test_client()
H = {security.HEADER: security.TOKEN}
def up(name, data, path="", mode=""):
    return c.post("/api/library/upload", data={"file": (io.BytesIO(data), name), "path": path, "mode": mode}, headers=H, content_type="multipart/form-data")
r = c.get("/api/library")
r = c.get("/api/library"); ok(r.json["ok"] and r.json["total"] == 0 and "usage" in r.json, "an empty library lists")
r = c.post("/api/library/upload", data={"file": (io.BytesIO(stl()), "a.stl")}, content_type="multipart/form-data")
ok(r.status_code == 400 and "out of date" in r.json["error"], "upload without the token is refused")
r = up("a.stl", stl()); ok(r.json == {"ok": True, "name": "a.stl", "status": "added"}, "upload with the token")
r = up("a.stl", stl(3)); ok(r.status_code == 409 and r.json["clash"] is True, "a clash is a 409 with clash: true")
r = up("a.stl", stl(3), mode="replace"); ok(r.json["status"] == "replaced", "replace over the Portal")
r = up("sub/../b.stl", stl()); ok(r.json["ok"] and r.json["name"] == "b.stl", "a browser's path in the file name is cut to its base name")
r = up("x.stl", b"nope"); ok(r.status_code == 400 and "isn't an STL" in r.json["error"], "a bad file is a 400 with the reason")
r = c.post("/api/library/folder", json={"path": "", "name": "Box"}, headers=H); ok(r.json["ok"], "make a folder")
r = c.post("/api/library/folder", json={"path": "../x", "name": "Box"}); ok(r.status_code == 400, "a write without the token is refused")
r = c.post("/api/library/move", json={"path": "a.stl", "to": "Box"}, headers=H); ok(r.json["ok"], "move")
r = c.get("/api/library/file?path=Box/a.stl"); ok(r.status_code == 200 and r.data == stl(3), "download gives the same bytes")
r = c.get("/api/library/file?path=../../etc/passwd"); ok(r.status_code == 400, "download outside the library is refused")
r = c.get("/api/library/count?path=Box"); ok(r.json["files"] == 1 and r.json["folders"] == 1, "count over the Portal")
r = c.post("/api/library/rename", json={"path": "Box/a.stl", "name": "c.stl"}, headers=H); ok(r.json["ok"], "rename")
r = c.post("/api/library/delete", json={"path": "Box"}, headers=H); ok(r.json["files"] == 1 and r.json["folders"] == 1, "delete over the Portal")
r = c.post("/api/library/delete", json={"path": ""}, headers=H); ok(r.status_code == 400, "deleting the library itself is refused")
ok(not [f for f in os.listdir(tempfile.gettempdir()) if f.startswith("rhino-lib-") and os.path.isfile(os.path.join(tempfile.gettempdir(), f))], "no upload temp files left behind")

print(f"\n{len(fails)} failed" if fails else "\nALL PASSED")
sys.exit(1 if fails else 0)
