"""Supports placed by hand, for PrusaSlicer (Rhino Studio's marks and blocks).

Studio sends the part as a binary STL, as always, and beside it a short list of numbers: where to force
support (enforce) and where to stop it (block), each a point in the STL's own coordinates and a radius.
This module checks those numbers and builds the 3MF project PrusaSlicer reads them from: the part, then
one small ball per mark as a support enforcer or blocker volume.

The Portal never accepts a 3MF (a zip) from the network: it only ever writes one, from an STL it has
checked and numbers it has checked, so there's nothing to unpack and no XML from outside.

Checked on PrusaSlicer 2.8.1 (Nov 2026): an enforcer ball under one wing of a T gives support under that
wing only, with "support_material = 1, support_material_auto = 0"; a blocker ball under the other wing
stops the automatic support there; --center moves the balls with the part. Enforcers need
support_material on: with it off they do nothing.
"""
import json
import math
import struct
import zipfile

from .errors import Fail

MAX_MARKS = 500
# The 3MF repeats every corner as text, so a part with marks is held to fewer triangles than a plain STL
MAX_TRIANGLES = 3_000_000
KINDS = ("enforce", "block")


def clean_supports(text):
    """The marks Studio sent, checked: {"enforce": [[x, y, z, r], ...], "block": [...]}, or None for none."""
    if text in (None, ""):
        return None
    if len(text) > 200_000:
        raise Fail("Too many support marks")
    try:
        data = json.loads(text)
    except ValueError:
        raise Fail("The support marks aren't readable")
    if not isinstance(data, dict) or set(data) - set(KINDS):
        raise Fail("Support marks: expected enforce and block lists")
    out = {}
    total = 0
    for kind in KINDS:
        items = data.get(kind, [])
        if not isinstance(items, list):
            raise Fail(f"Support marks: {kind} must be a list")
        total += len(items)
        clean = []
        for m in items:
            if not (isinstance(m, list) and len(m) == 4):
                raise Fail("Support marks: each is [x, y, z, r]")
            for i, v in enumerate(m):
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise Fail("Support marks: numbers only")
                lo, hi = (0.5, 50) if i == 3 else (-5000, 5000)
                if not lo <= v <= hi:
                    raise Fail("Support marks: a mark is out of range")
            clean.append([float(v) for v in m])
        out[kind] = clean
    if total > MAX_MARKS:
        raise Fail(f"At most {MAX_MARKS} support marks")
    return out if total else None


def stl_triangles(model):
    """How many triangles a binary STL holds, checking it really is one."""
    if len(model) < 84:
        raise Fail("The part is empty")
    (n,) = struct.unpack_from("<I", model, 80)
    if len(model) != 84 + 50 * n:
        raise Fail("The part isn't a binary STL")
    return n


def _ball(cx, cy, cz, r, rings=6, segments=12):
    """A low-poly ball as triangles: enough to mark a spot, few enough to keep the file small."""
    pts = []
    for i in range(rings + 1):
        a = math.pi * i / rings
        for j in range(segments):
            b = 2 * math.pi * j / segments
            pts.append((cx + r * math.sin(a) * math.cos(b), cy + r * math.sin(a) * math.sin(b), cz + r * math.cos(a)))
    tris = []
    for i in range(rings):
        for j in range(segments):
            p = i * segments + j
            q = i * segments + (j + 1) % segments
            tris.append((pts[p], pts[p + segments], pts[q + segments]))
            tris.append((pts[p], pts[q + segments], pts[q]))
    return tris


_CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                  'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                  'relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.'
                  '3dmanufacturing-3dmodel+xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
         'relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/'
         '3dmanufacturing/2013/01/3dmodel"/></Relationships>')
_VOLUME_TYPE = {"part": "ModelPart", "enforce": "SupportEnforcer", "block": "SupportBlocker"}


def write_3mf(model, supports, path):
    """The part (binary STL bytes) and its marks as a PrusaSlicer 3MF at `path`. Corners are written as they come,
    three per triangle, streamed so a big part never sits in memory as text."""
    n = stl_triangles(model)
    if n > MAX_TRIANGLES:
        raise Fail(f"The part has too many triangles for marked supports ({n:,}); use automatic supports")
    volumes = [("part", n)]
    balls = {k: [t for m in supports.get(k, []) for t in _ball(*m)] for k in ("enforce", "block")}
    for k in ("enforce", "block"):
        if balls[k]:
            volumes.append((k, len(balls[k])))

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        with z.open("3D/3dmodel.model", "w", force_zip64=True) as f:
            w = lambda s: f.write(s.encode())  # noqa: E731
            w('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
              'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n<metadata name="slic3rpe:Version3mf">1</metadata>\n'
              '<resources><object id="1" type="model"><mesh><vertices>\n')
            for i in range(n):
                o = 84 + 50 * i + 12
                for c in range(3):
                    x, y, zz = struct.unpack_from("<3f", model, o + 12 * c)
                    w(f'<vertex x="{x:.5g}" y="{y:.5g}" z="{zz:.5g}"/>\n')
            for k in ("enforce", "block"):
                for t in balls[k]:
                    for x, y, zz in t:
                        w(f'<vertex x="{x:.5g}" y="{y:.5g}" z="{zz:.5g}"/>\n')
            w("</vertices><triangles>\n")
            for t in range(n + len(balls["enforce"]) + len(balls["block"])):
                w(f'<triangle v1="{3 * t}" v2="{3 * t + 1}" v3="{3 * t + 2}"/>\n')
            w('</triangles></mesh></object></resources>\n<build><item objectid="1" printable="1"/></build></model>\n')
        cfg = ['<?xml version="1.0" encoding="UTF-8"?>\n<config><object id="1" instances_count="1">'
               '<metadata type="object" key="name" value="part"/>']
        first = 0
        for kind, count in volumes:
            cfg.append(f'<volume firstid="{first}" lastid="{first + count - 1}"><metadata type="volume" key="name" '
                       f'value="{kind}"/><metadata type="volume" key="volume_type" value="{_VOLUME_TYPE[kind]}"/></volume>')
            first += count
        cfg.append("</object></config>\n")
        z.writestr("Metadata/Slic3r_PE_model.config", "".join(cfg))
    return {k: len(supports.get(k, [])) for k in ("enforce", "block")}
