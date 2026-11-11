"""Help for Rhino Studio: the manual as web pages (docs/phase-help.md).

    python3 manual/web.py [out_dir]          default manual/web

Builds the manual the same way the PDF does (build.py), then writes, for Studio's Settings > Help:
  index.json      parts, chapters, their sections, and plain text for search
  <key>.html      one cleaned HTML fragment per chapter
  img/*.webp      web copies of the pictures (at most 1000 px wide)

One source: a chapter is edited in manual/src (or build.py) once, and the PDF and Help both change. The print-only
parts (cover, contents, part pages, blank forms) are left out. The HTML is cleaned to a short list of tags and
attributes, so nothing that runs reaches Studio. Fails if the output passes SIZE_LIMIT, so the zip doesn't grow quietly.
Needs bs4 and Pillow."""
import hashlib
import json
import os
import re
import shutil
import sys

from bs4 import BeautifulSoup, Comment, NavigableString
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SIZE_LIMIT = 6 * 1024 * 1024
MAX_W = 1000
PDF_URL = "https://github.com/Makersmic/Toolhead_Manager/blob/main/manual/Rhino-User-Manual.pdf"
SKIP = {"contents", "toolslog"}                    # print-only: the contents page and the blank tools log
SKIP_PREFIX = ("the-tools-new-tool-sheet-",)       # blank sheets for tools you build, to fill in by hand

TAGS = {"h2", "h3", "h4", "p", "ul", "ol", "li", "b", "strong", "i", "em", "code", "pre", "br", "a", "img", "figure",
        "figcaption", "table", "thead", "tbody", "tr", "th", "td", "div", "span", "section", "small", "sup", "sub", "hr",
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs", "title"}
DROP = {"script", "style", "iframe", "object", "embed", "link", "meta", "form", "input", "button", "textarea", "select"}
ATTRS = {"id", "class", "href", "src", "alt", "colspan", "rowspan", "viewbox", "d", "x", "y", "x1", "y1", "x2", "y2", "cx",
         "cy", "r", "rx", "ry", "width", "height", "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap",
         "stroke-linejoin", "points", "transform", "text-anchor", "dominant-baseline", "font-size", "font-weight",
         "font-family", "opacity", "fill-opacity", "xmlns"}


SOURCES = ("build.py", "web.py", "his_data.py", "diagrams.py")


def source_hash(here=HERE):
    """What the Help pages are made from: the chapters, the build scripts and the pictures. dev/test_help.py compares
    this with the one in index.json, so a chapter changed without rebuilding Help fails the tests."""
    h = hashlib.sha256()
    files = [os.path.join("src", f) for f in sorted(os.listdir(os.path.join(here, "src")))]
    files += list(SOURCES) + [os.path.join("img", f) for f in sorted(os.listdir(os.path.join(here, "img")))]
    for rel in files:
        h.update(rel.encode() + b"\0")
        h.update(open(os.path.join(here, rel), "rb").read())
    return h.hexdigest()


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def build_manual():
    import build as B                                   # writes content.html, like the PDF build's first step
    B.build()
    return open(os.path.join(HERE, "content.html")).read()


def chapters(doc):
    """-> [(part title, key, title, [nodes])] in reading order."""
    soup = BeautifulSoup(doc, "html.parser")
    out, part = [], ""
    for el in soup.body.children:
        if not getattr(el, "name", None):
            continue
        cls = el.get("class", [])
        if "cover" in cls or "tocpage" in cls:
            continue
        if "partpage" in cls:
            part = el.find(class_="parttitle").get_text(strip=True)
            continue
        mk = " ".join(m.get_text() for m in el.find_all("span", class_="mk"))
        start = re.search(r"@@S@([^@]+)@@", mk)
        if "sec" in cls:
            h2 = el.find("h2")
            for m in (h2.find_all("span", class_="mk") if h2 else []):
                m.decompose()                           # the print build's page markers, not part of the title
            title = h2.get_text(strip=True) if h2 else el.get("id", "")
            if h2:
                h2.decompose()
            out.append([part, el.get("id") or slug(title), title, [el]])
        elif start:
            key, _, title = start.group(1).partition("|")
            title = title.split(" · ")[-1]
            out.append([part, key, title, [el]])
        elif out:
            out[-1][3].append(el)                       # a designed page that continues the one before
    return [c for c in out if c[1] not in SKIP and not c[1].startswith(SKIP_PREFIX)]


class Pictures:
    def __init__(self, out):
        self.dir = os.path.join(out, "img")
        os.makedirs(self.dir, exist_ok=True)
        self.done = {}

    def web(self, src):
        """file:///…/img/name.png -> img/<name>.webp (made once)."""
        path = src[7:] if src.startswith("file://") else src
        if path in self.done:
            return self.done[path]
        if not os.path.isfile(path):
            raise SystemExit(f"help: picture not found: {path}")
        base = os.path.splitext(os.path.basename(path))[0]
        name = f"{base}.webp" if re.fullmatch(r"[A-Za-z0-9_-]+", base) else hashlib.sha1(base.encode()).hexdigest()[:16] + ".webp"
        im = Image.open(path)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
        im.save(os.path.join(self.dir, name), "WEBP", quality=72, method=6)
        self.done[path] = "img/" + name
        return self.done[path]


def clean(nodes, pics, where):
    """The chapter's nodes as safe HTML: allowed tags and attributes only, pictures made web copies, the print markers
    gone, links pointed at Help's own pages. where: {anchor id: chapter key}."""
    soup = BeautifulSoup("".join(str(n) for n in nodes), "html.parser")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for m in soup.find_all("span", class_="mk"):
        m.decompose()
    for el in soup.find_all(True):
        if el.name in DROP:
            el.decompose()
    for el in soup.find_all(True):
        if el.name not in TAGS:
            el.unwrap()
            continue
        for a in list(el.attrs):
            if a.lower() not in ATTRS or a.lower().startswith("on"):
                del el[a]
        if el.name == "img":
            src = el.get("src", "")
            if not src:
                el.decompose()
                continue
            el["src"] = pics.web(src)
            el["loading"] = "lazy"
        if el.name == "a":
            h = el.get("href", "")
            if h.startswith("#") and h[1:] in where:
                el["href"] = f"#/settings/help/{where[h[1:]]}/{h[1:]}"
            elif re.match(r"https://[^\s\"'<>]+$", h):
                el["target"] = "_blank"
                el["rel"] = "noopener"
            else:
                el.unwrap()
    for h in soup.find_all(["h3", "h4"]):              # every heading can be linked to and searched for
        if not h.get("id"):
            h["id"] = slug(h.get_text())
    for el in soup.find_all(True):                     # one last check: nothing here may run
        bad = [a for a in el.attrs if a.lower().startswith("on") or str(el.get(a, "")).strip().lower().startswith("javascript:")]
        if bad or el.name in DROP:
            raise SystemExit(f"help: {where.get('_', '?')}: unsafe markup left in <{el.name}>")
    return soup


def sections_of(soup):
    """-> [{id, title, text}]: the chapter's opening text (id "") and each h3 section, for search to jump to."""
    out = [{"id": "", "title": "", "text": []}]
    for node in soup.descendants:
        if getattr(node, "name", None) == "h3":
            out.append({"id": node["id"], "title": node.get_text(" ", strip=True), "text": []})
        elif isinstance(node, NavigableString) and not isinstance(node, Comment) and node.parent.name not in ("h3", "title"):
            out[-1]["text"].append(str(node))
    for s in out:
        s["text"] = re.sub(r"\s+", " ", " ".join(s["text"])).strip()
    return [s for s in out if s["id"] or s["text"]]


def main(out):
    doc = build_manual()
    chs = chapters(doc)
    tmp = out + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    pics = Pictures(tmp)
    where = {}
    for _, key, _, nodes in chs:                        # every id a link can point at, and its chapter
        where[key] = key
        for n in nodes:
            for el in n.find_all(id=True):
                where.setdefault(el["id"], key)
    parts, index = [], {}
    for part, key, title, nodes in chs:
        soup = clean(nodes, pics, {**where, "_": key})
        for h in soup.find_all(["h3", "h4"]):
            where.setdefault(h["id"], key)
        html = str(soup)
        open(os.path.join(tmp, f"{key}.html"), "w").write(html)
        if not parts or parts[-1]["title"] != part:
            parts.append({"title": part, "chapters": []})
        parts[-1]["chapters"].append(key)
        index[key] = {"title": title, "part": part, "sections": sections_of(soup)}
    from build import VERSION
    json.dump({"version": VERSION, "pdf": PDF_URL, "source": source_hash(), "parts": parts, "chapters": index},
              open(os.path.join(tmp, "index.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(tmp) for f in fs)
    if size > SIZE_LIMIT:
        raise SystemExit(f"help: {size / 1048576:.1f} MB, over the {SIZE_LIMIT / 1048576:.0f} MB limit: shrink the pictures")
    shutil.rmtree(out, ignore_errors=True)
    os.rename(tmp, out)
    print(f"help: {len(index)} chapters, {len(pics.done)} pictures, {size / 1048576:.1f} MB in {out}")


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "web")))
