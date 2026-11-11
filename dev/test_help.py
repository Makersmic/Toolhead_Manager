"""Help in Rhino Studio (docs/phase-help.md): the manual's web pages in manual/web.

    python3 dev/test_help.py

Checks, without the build's own tools (bs4, Pillow): the pages match the manual's sources, every chapter and picture
is there, nothing in them can run, they stay small, and the release copies them into Studio."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAN = os.path.join(ROOT, "manual")
WEB = os.path.join(MAN, "web")
FAILED = []


def ok(cond, what):
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        FAILED.append(what)


# web.py's source_hash, without importing web.py (it needs bs4 and Pillow)
import hashlib                                          # noqa: E402
src = open(os.path.join(MAN, "web.py")).read()
SOURCES = eval(re.search(r"^SOURCES = (\(.*?\))$", src, re.M).group(1))
h = hashlib.sha256()
files = [os.path.join("src", f) for f in sorted(os.listdir(os.path.join(MAN, "src")))]
files += list(SOURCES) + [os.path.join("img", f) for f in sorted(os.listdir(os.path.join(MAN, "img")))]
for rel in files:
    h.update(rel.encode() + b"\0")
    h.update(open(os.path.join(MAN, rel), "rb").read())

ix = json.load(open(os.path.join(WEB, "index.json")))
ok(ix.get("source") == h.hexdigest(), "Help matches the manual's sources (if not: python3 manual/web.py, then commit manual/web)")
ok(ix.get("pdf", "").startswith("https://github.com/Makersmic/") and ix["pdf"].endswith(".pdf"), "Download PDF points at the manual on GitHub")

keys = [k for p in ix["parts"] for k in p["chapters"]]
ok(len(keys) >= 30 and len(keys) == len(set(keys)) and set(keys) == set(ix["chapters"]), f"every chapter is listed once ({len(keys)})")
ok(all(os.path.isfile(os.path.join(WEB, f"{k}.html")) for k in keys), "every chapter has its page")
ok(not {"contents", "toolslog"} & set(keys) and not any(k.startswith("the-tools-new-tool-sheet") for k in keys),
   "print-only pages (contents, blank forms) are left out")

# Studio's "?" links (src/help/help.ts HELP_FOR) land on these
for need in ["rhino-studio-at-a-glance", "job-setup-and-preview", "control", "bed", "files", "assets", "care", "settings", "tuning-a-print-head"]:
    ok(need in ix["chapters"], f"the chapter Studio's ? opens is there: {need}")
ok(any(s["id"] == "bed-mesh" for s in ix["chapters"]["bed"]["sections"])
   and any(s["id"] == "configuration-moving-one-lead-screw" for s in ix["chapters"]["bed"]["sections"]), "and the Bed sections it opens")

bad, pics, links = [], set(), []
for k in keys:
    html = open(os.path.join(WEB, f"{k}.html")).read()
    if re.search(r"<\s*(script|iframe|object|embed|style|link|meta|form)\b", html, re.I) or re.search(r"\son[a-z]+\s*=", html, re.I) \
            or "javascript:" in html.lower():
        bad.append(k)
    pics |= set(re.findall(r'<img[^>]*\ssrc="([^"]+)"', html))
    links += re.findall(r'href="([^"]+)"', html)
ok(not bad, f"nothing in the pages can run ({bad[:3]})")
ok(pics and all(p.startswith("img/") and os.path.isfile(os.path.join(WEB, p)) for p in pics), f"every picture is there, as a local file ({len(pics)})")
ok(all(l.startswith("#/settings/help/") or l.startswith("https://") for l in links), "links open Help pages or the web, nothing else")
size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(WEB) for f in fs)
ok(size <= 6 * 1024 * 1024, f"Help stays under 6 MB ({size / 1048576:.1f} MB)")

mz = open(os.path.join(HERE, "make_zip.sh")).read()
ok('cp -a manual/web studio/help' in mz, "the release copies Help into Studio's site")

print("\n" + ("ALL PASSED" if not FAILED else f"FAILED: {FAILED}"))
sys.exit(1 if FAILED else 0)
