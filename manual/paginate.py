"""Print content.html, add running headers, page tabs and Notes pages, and fill the contents.

    python3 paginate.py            -> Rhino-User-Manual.pdf

Every part starts on a right-hand (odd) page for double-sided printing; when it would not, a
ruled Notes page is put in front of it. The section named at the top left of each page is the one
the page starts in (or the one that begins on it).
"""
import html, json, os, re, subprocess, sys
from pypdf import PdfReader, PdfWriter, PageObject
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Rhino-User-Manual.pdf")
MK = re.compile(r"@@([SPCE])@([^@]*)@@")


def render(html_path, pdf_path, margin_zero=False):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + html_path)
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(300)
        kw = {"margin": {"top": "0", "bottom": "0", "left": "0", "right": "0"}} if margin_zero else {}
        pg.pdf(path=pdf_path, prefer_css_page_size=True, print_background=True, **kw)
        b.close()


def markers(pdf_path):
    """Markers per page, in reading order (pdftotext keeps them intact; pages split on form feeds)."""
    txt = subprocess.run(["pdftotext", "-raw", pdf_path, "-"], capture_output=True, text=True, check=True).stdout
    pages = txt.split("\f")
    n = len(PdfReader(pdf_path).pages)
    return [MK.findall(pages[i].replace("\n", "")) if i < len(pages) else [] for i in range(n)]


def plan(marks):
    """-> list of final pages: dict(src=index|None, section, part, kind)"""
    titles = json.load(open(os.path.join(HERE, "marks.json")))
    titles["even"] = "even"
    marks = [[(k, v.split("|", 1)[0] + "|" + titles.get(v.split("|", 1)[0], v.split("|", 1)[-1])) for k, v in ms] for ms in marks]
    final, section, partname = [], "", ""
    for i, ms in enumerate(marks):
        kinds = [k for k, _ in ms]
        is_part = "P" in kinds
        if is_part and len(final) % 2 == 1:          # next final page would be even (left-hand)
            final.append({"src": None, "section": "Notes", "part": partname, "kind": "notes"})
        if "E" in kinds and len(final) % 2 == 0:     # a facing pair must start on a left-hand page
            final.append({"src": None, "section": "Notes", "part": partname, "kind": "notes"})
        kind = "cover" if "C" in kinds else ("part" if is_part else "body")
        for k, v in ms:
            if k == "P":
                partname = v.split("|", 1)[1].replace("|", "  ·  ")
        first_s = next((v for k, v in ms if k == "S"), None)
        if first_s:
            section = first_s.split("|", 1)[1]
        final.append({"src": i, "section": section, "part": partname, "kind": kind, "marks": ms})
        # a section that starts lower on this page still governs the next one
        last_s = [v for k, v in ms if k == "S"]
        if last_s:
            section = last_s[-1].split("|", 1)[1]
    if len(final) % 2 == 1:                            # end on a back page
        final.append({"src": None, "section": "Notes", "part": partname, "kind": "notes"})
    return final


def page_numbers(final):
    nums = {}
    for n, f in enumerate(final, 1):
        for k, v in f.get("marks", []):
            key = v.split("|", 1)[0]
            nums.setdefault(key, n)
    return nums


# Thumb tabs on the outer edge: one slot per part, so a closed manual shows where each part starts.
TABS = {1: "The Rhino", 2: "Tools", 3: "Software", 4: "Maintenance", 5: "Reference"}
TAB_TOP, TAB_H, TAB_STEP, TAB_W = 1.25, 1.2, 1.62, 0.42   # inches


def part_no(f):
    m = re.match(r"Part (\d+)", f.get("part") or "")
    return int(m.group(1)) if m else None


def thumb(n, odd, active=True, all_parts=False):
    side = "right:0" if odd else "left:0"
    out = []
    for p, label in TABS.items():
        if not all_parts and p != n:
            continue
        top = TAB_TOP + (p - 1) * TAB_STEP
        cls = "thumb" + ("" if (active and p == n) or all_parts else " dim")
        out.append(f'<div class="{cls} {"r" if odd else "l"}" style="{side};top:{top}in">'
                   f'<b>{p}</b><span>{html.escape(label)}</span></div>')
    return "".join(out)


def under_html(final):
    """Full-bleed artwork under the content: the cover band, the part openers' outer strip."""
    pages = []
    for n, f in enumerate(final, 1):
        odd = n % 2 == 1
        art = ""
        if f["kind"] == "cover":
            art = '<div class="band"></div>'
        elif f["kind"] == "part":
            p = part_no(f)
            side = "right:0" if odd else "left:0"
            art = f'<div class="strip" style="{side}"></div>'
        pages.append(f'<div class="pg">{art}</div>')
    css = """
    @page { size: 8.5in 11in; margin: 0; }
    body { margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .pg { width: 8.5in; height: 11in; position: relative; page-break-after: always; overflow: hidden; }
    .band { position: absolute; left: 0; right: 0; top: 0; height: 4.55in; background: #111; }
    .strip { position: absolute; top: 0; bottom: 0; width: 0.42in; background: #111; }
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(pages)}</body></html>"


def overlay_html(final):
    pages = []
    for n, f in enumerate(final, 1):
        if f["kind"] == "cover":
            pages.append('<div class="pg"></div>')
            continue
        odd = n % 2 == 1
        head = ""
        if f["kind"] != "part":
            head = (f'<div class="head"><span class="sec">{html.escape(f["section"])}</span>'
                    f'<span class="part">{html.escape(f["part"])}</span></div>')
        tab = f'<div class="foot"></div><div class="tab {"r" if odd else "l"}">{n}</div>'
        if f["section"] == "Contents" and f["kind"] != "part":
            tab += thumb(None, odd, all_parts=True)
        elif part_no(f):
            tab += thumb(part_no(f), odd)
        notes = ""
        if f["kind"] == "notes":
            notes = '<div class="notes"><div class="nt">Notes</div>' + "<i></i>" * 30 + "</div>"
        pages.append(f'<div class="pg">{head}{notes}{tab}</div>')
    css = """
    @page { size: 8.5in 11in; margin: 0; }
    body { margin: 0; font-family: Inter; }
    .pg { width: 8.5in; height: 11in; position: relative; page-break-after: always; overflow: hidden; }
    .head { position: absolute; left: 0.85in; right: 0.85in; top: 0.42in; height: 0.22in; border-bottom: 1.2pt solid #111;
            display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 2pt; }
    .head .sec { font: 700 8.6pt Inter; text-transform: uppercase; letter-spacing: 0.8pt; color: #111; }
    .head .part { font: 500 7.6pt Inter; color: #777; letter-spacing: 0.3pt; }
    .foot { position: absolute; left: 0.85in; right: 0.85in; top: 10.38in; border-top: 1.2pt solid #111; }
    .tab { position: absolute; top: 10.38in; width: 0.95in; height: 0.25in; background: #111; color: #fff;
           font: 700 10pt/0.25in Inter; padding: 0 7pt; }
    .tab.r { right: 0.85in; text-align: right; } .tab.l { left: 0.85in; text-align: left; }
    .thumb { position: absolute; width: 0.42in; height: 1.2in; background: #111; color: #fff; display: flex; flex-direction: column;
             align-items: center; padding-top: 7pt; gap: 7pt; }
    .thumb.dim { background: #fff; }
    .thumb b { font: 800 13pt 'Inter Display'; }
    .thumb span { font: 700 6.2pt Inter; letter-spacing: 1.1pt; text-transform: uppercase; writing-mode: vertical-rl; white-space: nowrap; }
    .thumb.l span { transform: rotate(180deg); }
    .notes { position: absolute; left: 0.85in; right: 0.85in; top: 0.95in; }
    .notes .nt { font: 700 19pt 'Inter Display'; border-bottom: 1.6pt solid #111; padding-bottom: 4pt; margin-bottom: 4pt; }
    .notes i { display: block; height: 0.29in; border-bottom: 0.6pt solid #b5b5b5; }
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(pages)}</body></html>"


def assemble(content_pdf, final):
    oh = os.path.join(HERE, "overlay.html")
    op = os.path.join(HERE, "overlay.pdf")
    open(oh, "w").write(overlay_html(final))
    render(oh, op, margin_zero=True)
    uh = os.path.join(HERE, "underlay.html")
    up = os.path.join(HERE, "underlay.pdf")
    open(uh, "w").write(under_html(final))
    render(uh, up, margin_zero=True)
    src = PdfReader(content_pdf)
    ov = PdfReader(op)
    un = PdfReader(up)
    w = PdfWriter()
    for n, f in enumerate(final):
        base = PageObject.create_blank_page(width=612, height=792)
        if f["kind"] in ("cover", "part"):
            base.merge_page(un.pages[n])
        if f["src"] is not None:
            base.merge_page(src.pages[f["src"]])
        base.merge_page(ov.pages[n])
        w.add_page(base)
    w.add_metadata({"/Title": "Rhino Multi-Tool Motion System - User Manual", "/Author": "Makersmic"})
    with open(OUT, "wb") as fh:
        w.write(fh)


def main():
    content_html = os.path.join(HERE, "content.html")
    content_pdf = os.path.join(HERE, "content.pdf")
    pages_json = os.path.join(HERE, "pages.json")
    prev = None
    for attempt in range(4):
        subprocess.run([sys.executable, os.path.join(HERE, "build.py"), pages_json], check=True)
        render(content_html, content_pdf)
        final = plan(markers(content_pdf))
        nums = page_numbers(final)
        json.dump(nums, open(pages_json, "w"))
        if nums == prev:
            break
        prev = nums
    assemble(content_pdf, final)
    blanks = sum(1 for f in final if f["src"] is None)
    print(f"{len(final)} pages ({blanks} notes pages added); contents stable after {attempt + 1} passes")
    json.dump([{k: v for k, v in f.items() if k != "marks"} for f in final], open(os.path.join(HERE, "plan.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
