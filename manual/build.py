"""Build the printable Rhino manual (content.html). Run paginate.py afterwards.

    python3 build.py [pages.json]     pages.json (from paginate.py) fills in the contents page numbers
"""
import html, json, os, re, sys
from bs4 import BeautifulSoup
import diagrams as WD
from his_data import (CONSTANT, HARDWARE, MAINBOARD, MICROCONTROLLER, OTHER_PINS, STEPPERS, TOOLS, UMBILICAL)

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
SRC = os.path.join(HERE, "src")
PAGES = json.load(open(sys.argv[1])) if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else {}

# old doc blob -> image file
BLOB = {"c867a3d7-25e6": "welcome.jpg", "505aefe6-155b": "assembly.jpg", "5de126d6-ed99": "gantry.png",
        "92ce6612-4a37": "carriage_render.png", "bbdc872d-96fb": "tool_seated.jpg", "0a16d356-312d": "tensioner.png",
        "4133c188-cacc": "frame.png", "ea360dfa-b5e8": "dragknife_render.png",
        "e334e325-f8b1": "mt_lib.png", "20090a51-e194": "mt_due.png", "33aa834b-6821": "mt_new.png",
        "1a244df4-8d20": "mt_done.png", "ee3836d3-7a0a": "mt_log.png", "a8f5d77f-5c98": "mt_tasks.png",
        "74e18d06-c469": "mt_meters.png", "0070c62c-e9ad": "phone_maint.png"}

TOC = []          # (level, title, key)
HEIGHTS = {"xcarriage.png": 2.9, "tool_seated.jpg": 2.5, "assembly.jpg": 2.7, "gantry.png": 2.0, "tensioner.png": 3.6,
           "frame.png": 4.0, "mt_due.png": 4.2, "mt_tasks.png": 4.0, "mt_log.png": 3.6, "mt_meters.png": 4.2,
           "mt_lib.png": 4.6, "mt_new.png": 4.8, "mt_done.png": 4.6, "phone_maint.png": 3.6}
CUR_PART = [""]


def esc(s):
    return html.escape(s, quote=True)


def src(name):
    return "file://" + os.path.join(IMG, name if "." in name else name + ".png")


def fig(name, caption="", cls="", h=None):
    style = f' style="max-height:{h}in"' if h else ""
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="{cls}"><img src="{src(name)}" alt="{esc(caption)}"{style}>{cap}</figure>'


def keep(*parts, cls=""):
    return f'<div class="keep {cls}">' + "".join(parts) + "</div>"


def step(text, name, caption, h=None, cls=""):
    """A step and its picture: never split across pages."""
    return keep(text, fig(name, caption, h=h), cls="step " + cls)


MARKS = {}


def marker(kind, text):
    key, _, title = text.partition("|")
    MARKS[key] = title
    return f'<span class="mk">@@{kind}@{text}@@</span>'


def section(title, body, key=None, toc=True, cls=""):
    key = key or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if toc:
        TOC.append((2, title, key))
    return f'<section class="sec {cls}" id="{key}"><h2 class="sec">{marker("S", key + "|" + title)}{title}</h2>{body}</section>'


def part(n, title, blurb, sections):
    CUR_PART[0] = title
    TOC.append((1, f'<span class="pk">Part {n}</span><span class="pd">·</span>{title}', f"part{n}"))
    items = "".join(f"<li>{s}</li>" for s in sections)
    return (f'<section class="partpage" id="part{n}">{marker("P", f"part{n}|Part {n}|{title}")}'
            f'<div class="partnum">PART {n}</div><div class="parttitle">{title}</div><div class="partbar"></div>'
            f'<p class="partblurb">{blurb}</p><ul class="partlist">{items}</ul></section>')


def page(body, title=None, cls="", key=None, even=False):
    """A designed, fixed page (forms, tool sheets). title starts a new running header."""
    key = key or (re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") if title else "")
    m = marker("S", key + "|" + title) if title else ""
    return f'<div class="fixed {cls}">{m}{body}</div>'


def htitle(t, sub=""):
    return f'<div class="htitle">{t}</div>' + (f'<div class="hsub">{sub}</div>' if sub else "")


def table(head, rows, cls="", widths=None):
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


# ----------------------------------------------------------------------------- the 21W4 connector drawing
# Layout taken from the manual's connector drawings: big contacts 1, 2 (left) and 11, 12 (right);
# top row 3-10 and 13, bottom row 21 ... 14.
TOP = [3, 4, 5, 6, 7, 8, 9, 10, 13]
BOT = [21, 20, 19, 18, 17, 16, 15, 14]


def connector_svg(used=(), w=560, blank=False):
    used = set(used)
    out = ['<svg class="conn" viewBox="0 0 560 120" width="%d" xmlns="http://www.w3.org/2000/svg">' % w,
           '<path d="M14 12 Q8 12 9 18 L40 104 Q42 110 48 110 L512 110 Q518 110 520 104 L551 18 Q552 12 546 12 Z" '
           'fill="#fff" stroke="#222" stroke-width="2.2"/>',
           '<path d="M24 20 L52 100 L508 100 L536 20 Z" fill="none" stroke="#999" stroke-width="1"/>']

    def pin(n, x, y, r):
        fill = "#111" if n in used else "#fff"
        out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="#333" stroke-width="1.6"/>')
        if r > 12:
            out.append(f'<circle cx="{x}" cy="{y}" r="{r - 4}" fill="none" stroke="{"#666" if n in used else "#bbb"}" stroke-width="1"/>')
        out.append(f'<text x="{x}" y="{y + r + 10}" font-size="9.5" text-anchor="middle" fill="#666" '
                   f'font-family="Inter">{n}</text>')
    pin(1, 75, 58, 17)
    pin(2, 120, 58, 17)
    for i, n in enumerate(TOP):
        pin(n, 160 + i * 30, 38, 9.5)
    for i, n in enumerate(BOT):
        pin(n, 175 + i * 30, 76, 9.5)
    pin(11, 440, 58, 17)
    pin(12, 485, 58, 17)
    out.append("</svg>")
    return "".join(out)


# ----------------------------------------------------------------------------- reuse of the current manual
def xsec(fname, replace=(), drop=(), title=None):
    """A section of the current manual: blob images mapped, and every picture kept with the paragraph
    before it, every heading kept with what follows it."""
    s = open(os.path.join(SRC, fname)).read()
    for a, b in replace:
        if a not in s:
            raise SystemExit(f"{fname}: text to replace not found: {a[:60]!r}")
        s = s.replace(a, b)
    soup = BeautifulSoup(s, "html.parser")
    h2 = soup.find("h2")
    t = title or h2.get_text()
    h2.decompose()
    for d in drop:
        for el in soup.select(d):
            el.decompose()
    blocks = [c for c in soup.contents if getattr(c, "name", None)]
    out = []
    for b in blocks:
        img = b.find("img") if b.name == "p" else None
        if img is not None and len(b.get_text(strip=True)) == 0:
            blob = img["src"].split("/", 1)[1]
            name = BLOB.get(blob)
            if name is None:
                raise SystemExit(f"{fname}: no image for {blob}")
            f = fig(name, img.get("alt", ""), h=HEIGHTS.get(name))
            if out and out[-1][0] in ("p", "h3", "keep") and len(out[-1][1]) < 1400:
                prev = out.pop()
                out.append(("keep", keep(prev[1], f) if prev[0] != "keep" else prev[1][:-6] + f + "</div>"))
            else:
                out.append(("keep", keep(f)))
            continue
        if b.name == "figure":         # the software diagram embed
            out.append(("keep", keep(fig("diagram", b.get_text(), cls="plain"))))
            continue
        out.append((b.name, str(b)))
    # headings stay with the next block
    final = []
    i = 0
    while i < len(out):
        k, h = out[i]
        if k in ("h3", "h4") and i + 1 < len(out):
            final.append(keep(h, out[i + 1][1], cls="hk"))
            i += 2
            continue
        final.append(h)
        i += 1
    return section(t, "".join(final))


# ============================================================================= front matter
def cover():
    return (f'<div class="cover">{marker("C", "cover|cover")}'
            f'<div class="covertitle">Rhino Multi-Tool Motion System</div><div class="coverrule"></div>'
            f'<div class="coversub">User Manual</div>'
            f'<img class="coverimg" src="{src("welcome.jpg")}">'
            '<p class="coverblurb">The Rhino is a multi-tool motion system equipped with a variety of tools to help you '
            'build your dreams. It uses Klipper firmware. Information can be found online at the Makersmic GitHub page.</p>'
            f'<div class="tag"><img src="{src("logo")}"><div>2026</div><small>A Makersmic<br>Project</small></div></div>')


def contents():
    rows = []
    for lvl, t, key in TOC:
        pg = PAGES.get(key, "")
        rows.append(f'<div class="toc{lvl}"><span class="tt">{t}</span><span class="dots"></span><span class="pn">{pg}</span></div>')
    return page(htitle("Contents") + "".join(rows), "Contents", cls="tocpage", key="contents")


# ============================================================================= Part 1: the Rhino
def necessities():
    mc = table(["", "Microcontroller"], [[f'<span class="rn">{i + 1}</span>', x] for i, x in enumerate(MICROCONTROLLER)],
               cls="spec", widths=["8%", "92%"])
    mb = table(["", "Mainboard"], [["", x] for x in MAINBOARD], cls="spec", widths=["8%", "92%"])
    hw = table(["Qty", "Recommended additional hardware"], [list(r) for r in HARDWARE] + [["", ""], ["", ""]],
               cls="spec compact", widths=["10%", "90%"])
    body = ('<p>Klipper runs on a wide range of controller boards, so the Rhino is not tied to one. This manual and the '
            'configuration are written for the Big Tree Tech Octopus v1.1, but any controller will do if its microcontroller and '
            'mainboard provide what the two tables below list. The third table is the additional hardware the build needs: power, '
            'switching, protection and wiring for the electronics cabinet, plus the mechanical parts.</p>' + keep(mc) + keep(mb) + hw)
    return section("System necessities", body)


def machine():
    rep = [
        ('<h3 id="x-carriage-and-tool-slot">X-carriage and tool slot</h3>',
         '<h3 id="x-carriage-and-tool-slot">X-carriage and tool slot</h3>'),
        ('<p><img src="blob/92ce6612-4a37" alt="X-carriage, rendered from the build files"></p>',
         '<p><img src="blob/XCARRIAGE" alt="X-carriage detail: the tool drops into the wedge-type slot"></p>'),
        ('only the wiring each tool needs travels with it.', 'only the wiring of each individual tool travels with it.'),
        ('<p>Each tool ends in a male 21W4 D-sub',
         '<p>An essential assembly of the Rhino, the umbilical provides all the connections each toolhead needs. It uses a '
         '21W4 socket connector for every tool connection, with automatic reconfiguration between tool changes, and the '
         'umbilical LED strip signals user-specified alarms.</p><p>Each tool ends in a male 21W4 D-sub'),
    ]
    BLOB["XCARRIAGE"] = "xcarriage.png"
    s = open(os.path.join(SRC, "02_the-machine.html")).read()
    # the old per-type pin table and pin picture move to "Wiring and pin mapping"
    s = re.sub(r'<p><img src="blob/5a6dde33-dead"[^>]*></p>', "", s)
    s = re.sub(r'<p><img src="blob/bbdc872d-96fb"[^>]*></p>', "", s)          # the photo of a seated tool
    s = re.sub(r"<table><thead><tr><th>Pin</th>.*?</table>",
               '<p>The pin-by-pin assignment of the umbilical, with the board pin behind each contact, is in '
               '<em>Wiring and pin mapping</em>. Each tool\'s own page in <em>The tools</em> shows which contacts that tool uses.</p>', s,
               flags=re.S)
    open(os.path.join(SRC, "_machine.html"), "w").write(s)
    return xsec("_machine.html", rep)


def wiring():
    um = [[f'<span class="rn">{n}</span>', f"<b>{UMBILICAL[n][0]}</b>", UMBILICAL[n][1], UMBILICAL[n][2]] for n in range(1, 22)]
    t1 = table(["Umbilical pin", "Board pin", "Function", "Board label"], um, cls="pinmap", widths=["15%", "17%", "50%", "18%"])
    t2 = table(["Umbilical constant connections", "Board pin"], [[a, f"<b>{b}</b>"] for a, b in CONSTANT], cls="pinmap",
               widths=["60%", "40%"])
    p1 = htitle("Rhino Wiring: Pin Mapping", "Board: Big Tree Tech Octopus v1.1") + t1 + t2
    chart = table(["Pin", "Wire colour"], [[str(n), ""] for n in range(1, 22)], cls="chart", widths=["35%", "65%"])
    p2 = page(htitle("Umbilical colour coding") +
              '<div class="twocol"><div>' + f'<img class="connector" src="{src("connector")}">' + "</div><div>" + chart + "</div></div>"
              '<p class="small">Record the wire colour on each contact of your umbilical as you build it.</p>')
    other = [[f"<b>{p}</b>", d + (f'<div class="note">{n}</div>' if n else ""), l] for p, d, l, n in OTHER_PINS]
    other += [["", "", ""] for _ in range(9)]
    p3 = page(htitle("Rhino Wiring: Pin Mapping", "Other board pins · Big Tree Tech Octopus v1.1") +
              table(["Pin", "Description", "Board label"], other, cls="pinmap tall", widths=["16%", "64%", "20%"]))
    aux = table(["Pin", "Description", "", "", ""], [["", "", "", "", ""] for _ in range(24)], cls="pinmap tall",
                widths=["16%", "30%", "18%", "18%", "18%"])
    p4 = page(htitle("Rhino Wiring: Auxiliary Board") +
              '<div class="fill"><span>Aux board:</span><i></i></div><div class="fill"><span>Model no:</span><i></i></div>' + aux)
    cards = [stepper_card(*s) for s in STEPPERS]
    steppers = ""
    for i in range(0, len(cards), 2):
        steppers += page(htitle("Rhino Wiring: Stepper Assignments", "Big Tree Tech Octopus v1.1") + cards[i] + cards[i + 1])
    def dfig(svg, title, cap):
        return f'<figure class="wdfig"><div class="wdt">{title}</div>{svg}<figcaption>{cap}</figcaption></figure>'
    diagrams = (page(htitle("Rhino Wiring: Diagrams", "Red: + supply · black: ground / – · blue: signal or PWM · grey: motor phases") +
                     dfig(WD.switchfly(), "SwitchFly servo",
                          "A PW-D regulator turns the switched 12 V into 5 V for the servo; the board's PWM output drives its signal line.") +
                     dfig(WD.hotjoe(), "HotJoe BLDC spindle",
                          "The relay-switched 24 V powers the ESC; the board's PWM output (SPINDLE_SPEED) drives its signal lead.")) +
                page(htitle("Rhino Wiring: Diagrams", "Red: + supply · black: ground / – · blue: signal or PWM") +
                     dfig(WD.fan(), "4-pin part-cooling fan",
                          "Power from an always-on fan header; the PWM line from the FAN0 header (PA8). The tachometer wire is not used.") +
                     dfig(WD.probe(), "Capacitive probe",
                          "The 12 V sensor switches an optocoupler, which gives the Z endstop input a clean 5 V signal. A microswitch "
                          "in parallel is recommended as a backup.")))
    intro = ('<p>These pages record how the Rhino is wired to its Big Tree Tech Octopus v1.1 controller: the 21 contacts of '
             'the umbilical, the board pins that stay on the machine, every stepper driver, and the wiring diagrams for the '
             'special cases. Blank rows and cards are for your own additions.</p>'
             '<div class="callout">Where these sheets and <code>printer.cfg</code> disagree, Klipper follows <code>printer.cfg</code>. '
             'The differences found while preparing this manual are listed in <em>Still to check on the machine</em>.</div>')
    return section("Wiring and pin mapping", intro + p1) + p2 + p3 + p4 + steppers + diagrams


def stepper_card(axis, driver, cur, sock, st, di, en, cs, note):
    rows = (f'<tr><td colspan="2"><span class="lab">Driver type and manufacturer</span><div class="val">{driver}</div></td></tr>'
            '<tr><td colspan="2" class="red">SPI / UART</td></tr>'
            f'<tr><td class="lab">Run current</td><td class="val">{cur}</td></tr>'
            f'<tr><td colspan="2"><span class="lab">Board socket</span><div class="val">{sock}</div></td></tr>'
            f'<tr><td>Step</td><td><b>{st}</b></td></tr><tr><td>Dir</td><td><b>{di}</b></td></tr>'
            f'<tr><td>Enable</td><td><b>{en}</b></td></tr><tr><td>CS / UART</td><td><b>{cs}</b></td></tr>')
    n = f'<div class="cardnote">{note}</div>' if note else '<div class="lines3"><i></i><i></i></div>'
    return f'<div class="scard"><div class="saxis">{axis}</div><table class="sgrid">{rows}</table></div>{n}'


# ============================================================================= Part 2: the tools
def tools_intro():
    rep = [("12 V 80 W blue diode laser", "12 V 80 W 450 nm blue diode laser"),
           ("Ostrich drag-knife holder", "Drag knife for Roland No. 9 and No. 10 blade holders")]
    s = open(os.path.join(SRC, "03_the-tools.html")).read()
    s = s[:s.index('<h3 id="print-heads')]       # the per-tool text moves onto each tool's pages
    open(os.path.join(SRC, "_tools.html"), "w").write(s)
    return xsec("_tools.html", rep)


NOTES = {
    "BlockOne": "<p>BlockOne supersedes the Jack Rabbit print head in the repository; the Jack Rabbit files there are outdated. "
                "Its materials cover 0.4 and 0.8 mm nozzles.</p>",
    "SwitchFly": "<p>SwitchFly feeds two filaments through one stepper and one hotend, so there is no second nozzle to align. "
                 "<code>SWITCH_T0</code> and <code>SWITCH_T1</code> select the filament with a servo on the shared "
                 "<code>SERVO_LASER</code> output.</p>",
    "LightSaber": "<p>A relay switches the laser's 12 V supply and Klipper drives its intensity through the PWM contact. The printed "
                  "height gauge in the build files sets the focus distance.</p><p><b>Safety:</b> wear glasses rated for the laser's "
                  "wavelength, run extraction, never cut PVC or vinyl, and stay with the machine for the whole cut.</p>",
    "HotJoe": "<p>Meant for light-duty milling. A 40 A relay powers the ESC only while the spindle is in use; the speed signal runs at "
              "400 Hz, where 0.3 is stopped (neutral) and about 0.99 is full throttle. Check real speeds at the collet with a "
              "tachometer before relying on them. Calibrate the ESC once with <code>CALIBRATE_ESC</code> (see <em>Maintenance</em>). "
              "The build files also include a 70 mm brush holder for dust collection, a blow-air clip and motor and gearbox shields.</p>",
    "DragKnife": "<p>The drag knife has no power output; cut depth comes from the blade holder's dial and the Z zero set in the job "
                 "wizard. Its thermistor and probe contacts let the swap wizard confirm the umbilical is seated.</p>",
}


def pin_rows(pins, board=True):
    rows = []
    for n in range(1, 22):
        d = pins.get(n, "")
        bp = UMBILICAL[n][0].replace(" +", "").replace(" –", "").strip("+– ") if d and board else ""
        rows.append([f'<span class="rn">{n}</span>', d, f"<b>{bp}</b>" if bp else ""] if board else [f'<span class="rn">{n}</span>', d])
    return rows


def tool_pages(name):
    t = TOOLS[name]
    info = table(["", ""], [["<b>Function</b>", t["function"]], ["<b>Slot</b>", str(t["slot"])],
                            ["<b>Set up a job with</b>", t["setup"]], ["<b>Outputs in Klipper</b>", t["outputs"]]],
                 cls="info", widths=["30%", "70%"])
    a = page(htitle(f"Rhino Tools: {name}") + f'<p class="about">{t["about"]}</p>' + info +
             '<div class="lab2">Umbilical connector</div>' + connector_svg(t["pins"], w=470) +
             table(["Pin no", "Description", "Board pin"], pin_rows(t["pins"]), cls="pins", widths=["14%", "62%", "24%"]),
             f"The tools · {name}", key=f"tool-{name}").replace('<span class="mk">', '<span class="mk">@@E@even|even@@ ', 1)
    notes = "".join(f'<div class="redfoot">*{n}</div>' for n in t["image_notes"])
    b = page(f'<div class="artwrap"><img class="art" src="{src(t["image"])}"></div>{notes}'
             f'<div class="toolnotes">{NOTES[name]}</div>')
    pieces = []
    if t["printed"]:
        pieces.append(("3D-printed pieces", t["printed"]))
    pieces.append(("Off-the-shelf hardware", t["hardware"] or []))
    if t["fasteners"]:
        pieces.append(("Fasteners", t["fasteners"]))
    rows = []
    for head, items in pieces:
        rows.append([("", f"<b>{head}:</b>")])
        rows += [[(q, d)] for q, d in items]
    flat = []
    for r in rows:
        q, d = r[0]
        flat.append([q, d])
    blank = max(0, 30 - len(flat))
    flat += [["", ""] for _ in range(min(blank, 12 if t["printed"] else 22))]
    pn = "".join(f'<div class="redfoot">*{n}</div>' for n in t["parts_notes"])
    c = page(htitle(f"Rhino Tools: {name}", f"Parts list · {t['function']}") +
             table(["Qty", "Description"], flat, cls="parts" + (" dense" if len(flat) > 31 else ""), widths=["14%", "86%"]) + pn)
    d = page(htitle(f"Rhino Tools: {name}", "Notes · settings that worked, changes, repairs") +
             table(["Date", "Note"], [["", ""] for _ in range(27)], cls="fillin notelog", widths=["18%", "82%"]))
    return a + b + c + d


def custom_sheets(n):
    out = ""
    kinds = "".join(f'<span class="box"></span>{k}&nbsp;&nbsp; ' for k in ["Additive", "Subtractive", "Passive"]) + "&nbsp; kind: ______________"
    for i in range(1, n + 1):
        ident = table(["", ""], [["<b>Tool name</b>", ""], ["<b>Slot</b>", ""], ["<b>Category and kind</b>", kinds],
                                 ["<b>Function</b>", ""], ["<b>Main power (PWM)</b>", 'contact ____ &nbsp;or&nbsp; new pin ______ &nbsp; output ______________'],
                                 ["<b>Switch outputs</b>", 'contacts / pins ________________________________'],
                                 ["<b>Power cap / max on-time</b>", "________ %&nbsp;&nbsp;/&nbsp;&nbsp;________ s"]],
                      cls="info fillin", widths=["30%", "70%"])
        a = page(htitle("Rhino Tools: ______________________", f"New tool sheet {i} · identity and umbilical") + ident +
                 '<div class="lab2">Umbilical connector <span class="small">(shade the contacts the tool uses)</span></div>' +
                 connector_svg((), w=470) +
                 table(["Pin no", "Description", "Board pin", "Output / control"],
                       [[f'<span class="rn">{k}</span>', "", "", ""] for k in range(1, 22)], cls="pins fillin tight",
                       widths=["12%", "46%", "18%", "24%"]),
                 f"The tools · New tool sheet {i}") .replace('<div class="fixed ', '<div class="fixed ' , 1).replace('<span class="mk">', '<span class="mk">@@E@even|even@@ ', 1)
        ctl = table(["Control name", "What it does", "Pin", "Off on safe-off", "Macros"], [["", "", "", '<span class="box"></span>', ""] for _ in range(5)],
                    cls="fillin", widths=["24%", "30%", "12%", "14%", "20%"])
        mac = table(["Macro name", "Purpose"], [["", ""] for _ in range(4)], cls="fillin", widths=["35%", "65%"])
        mat = table(["Material", "Power %", "Feed mm/min", "Z offset mm"], [["", "", "", ""] for _ in range(4)], cls="fillin",
                    widths=["40%", "20%", "20%", "20%"])
        parts = table(["Qty", "Part"], [["", ""] for _ in range(7)], cls="fillin", widths=["14%", "86%"])
        b = page(htitle("Rhino Tools: ______________________", f"New tool sheet {i} · portal settings and parts") +
                 '<div class="lab2">Controls</div>' + ctl + '<div class="lab2">Macros</div>' + mac +
                 '<div class="lab2">Materials</div>' + mat + '<div class="lab2">Parts list</div>' + parts +
                 '<div class="lab2">Notes</div><div class="lines"><i></i><i></i><i></i></div>')
        out += a + b
    return out


def tools_added():
    body = ('<p>Hot-wire cutters, needle cutters, dispensers, pens and other holders, and extra print-head nozzle sizes are added '
            'from the Tool Manager (see <em>The Tool Manager portal</em>). A powered tool takes its main power from an umbilical contact '
            'it can share, such as the spindle ESC signal on contact 18, or from a new output on a spare pin, and can switch more '
            'outputs on with itself.</p>'
            '<p>The next pages are blank tool sheets, two per tool, laid out like the built-in tools\' pages. Fill one in for each '
            'tool you design. They face each other when the manual lies open: the left page records what the tool is and which '
            'umbilical contacts it uses, the right page the settings you enter in the portal (controls, macros, materials) and its '
            'parts. Keep the sheet with the tool.</p>'
            '<div class="callout">Before wiring a new tool, check <b>Pins &amp; outputs</b> in the portal: it shows every contact of the '
            'umbilical and what drives it. Only free pins can be given to a new output, and the portal refuses a pin that anything in '
            'the config already uses.</div>')
    return section("Tools you add", body) + custom_sheets(3)


def tools_log():
    def nozzle(title):
        return (f'<div class="logbox"><div class="lbh">{title}</div><div class="lbr"><div><span class="lab">Nozzle size</span>'
                '<div class="opts">0.2 / 0.25 / 0.3 / 0.4 / 0.6 / 0.8 / 1.0</div></div><div><span class="lab">Nozzle type</span>'
                '<div class="opts">Brass / Steel / Specialty</div></div></div></div>')
    names = [f"Extruder {i}" for i in range(1, 10)] + [f"SwitchFly {i}" for i in range(1, 9)] + ["____________"]
    grid = '<div class="loggrid">' + "".join(nozzle(n) for n in names) + "</div>"
    foot = '<div class="redfoot center">*Ensure all extruders use the same heater cartridge and thermistor type for consistent firmware setup.</div>'
    p1 = page(htitle("Rhino Tools Log", "Print heads and nozzles") + grid + foot, "Rhino tools log", key="toolslog")

    def spec(title, cols, opts):
        return (f'<div class="logbox wide"><div class="lbh">{title}</div>' +
                table(cols, [opts, [""] * len(cols)], cls="logt") + "</div>")
    hj = ["Voltage", "ESC rating", "Motor size", "kV rating", "Max RPM"]
    hjo = ["12 / 24 / 36 / 48 V", "20 / 30 / 50 / 80 A", "", "", ""]
    ls = ["Voltage", "Wattage", "Diode type", "Wavelength", "Focal distance"]
    lso = ["12 / 24 / 36 / 48 V", "", "", "", ""]
    dk = ["Blade holder", "Blade angle", "Blade offset", "Cut depth", "Notes"]
    p2 = page(htitle("Rhino Tools Log", "Spindles, lasers, knives and your own tools") +
              spec("Hot Joe", hj, hjo) + spec("Hot Joe (spare)", hj, hjo) + spec("Light Saber", ls, lso) +
              spec("Light Saber (spare)", ls, lso) + spec("Drag Knife", dk, [""] * 5) +
              "".join(f'<div class="logbox wide"><div class="lbh name">Name:</div>' +
                      table(["", "", "", "", ""], [[""] * 5], cls="logt nohead") + "</div>" for _ in range(3)))
    return p1 + p2


# ============================================================================= Part 3: the portal (laid out step by step)
def portal():
    P = []
    a = P.append
    a('<p>Open <code>http://&lt;printer address&gt;:5000</code>. The portal adds, edits, renames and deletes your own tools, records '
      'which umbilical contacts each one uses, sets up system hardware, tracks maintenance, and restarts Klipper when changes '
      'need loading. The sidebar groups it into <b>Tools</b>, <b>Hardware</b>, <b>Maintenance</b> and <b>Admin</b>; click a group\'s '
      'name to fold it away. The screenshots come from a test run with three example tools (FoamWire, PenPlotter, Needle), three '
      'pieces of system hardware and placeholder photos.</p>')
    a(step('<h3>Tool library</h3><p>Every tool is a card: slot, category and kind, outputs, materials, notes and photos. The row of '
           'numbered boxes is the tool\'s pin map: the umbilical contacts it uses are filled in, as on the tool pages in Part 2. The '
           'chips at the top right show Klipper\'s state, the job state and the mounted tool. Built-in tools are read-only here; your '
           'tools have an <b>Edit</b> button.</p>', "library", "Tool library with the built-in and added tools", h=4.0))
    a('<h3>Adding a tool</h3><p>Press <b>+ Add a tool</b>. The wizard\'s steps depend on the kind of tool: powered tools get all '
      'seven, passive tools get a Connector step instead of Outputs and Limits, print-head clones get Hardware. Every kind gets '
      'Controls and Macros.</p>')
    a(step('<p class="st"><b>Step 1 · Tool</b> – say whether the tool is <b>Additive</b> (adds material: print heads, paste or glue '
           'dispensers), <b>Subtractive</b> (removes or cuts material: lasers, spindles, hot wires, knives) or <b>Passive</b> (pens, '
           'probes, cameras, holders). Then pick the kind of tool within it, type a name and optional notes. The kind fills in safe '
           'starting values; the list of kinds is yours to edit under <b>Admin › Tool lists</b>. The name is what G-code and slicers '
           'use: 2–24 letters, digits or <code>_</code>, starting with a letter.</p>', "w1_tool", "Step 1: category, kind, name and notes", h=3.6))
    a(step('<p class="st">Mistakes are caught before you move on, with the rule spelled out:</p>', "w_error",
           "A name that breaks the rules is refused at step 1", h=3.0))
    a(step('<p class="st"><b>Step 2 · Outputs</b> – one row per output the tool needs. Most tools have a main power feed and a '
           'signal or two, so press <b>+ Add an output</b> for each. Every row has a job and a source:</p><ul>'
           '<li><b>Main power level (PWM)</b> – the output <code>M3 S</code> sets, scaled and capped. Exactly one per tool.</li>'
           '<li><b>Switch on with the tool</b> – an on/off output that turns on when the tool\'s power does and off with it: a relay, '
           'a driver enable line, a vacuum.</li></ul><p class="st">The source is a <b>contact of the umbilical</b> that a Klipper '
           'output already drives (contact 18, the spindle ESC signal, for example), a <b>new output on a spare pin</b>, a piece of '
           '<b>system hardware</b>, or another output in the config. Below the outputs, tick the other contacts the tool uses – returns, '
           'supplies, the probe – so its pin map is complete. Contacts its outputs drive are ticked for you.</p>', "w2_outputs",
           "Step 2: a PWM signal on contact 18, a relay on contact 11, and the contacts the tool uses", h=5.4))
    a(step('<p class="st"><b>Step 3 · Limits</b> – the power cap (a hard ceiling whatever the G-code asks), minimum and idle levels, '
           'the watchdog\'s maximum on-time, and the <code>S</code> value that means full power. Sharing the ESC channel sets the idle '
           'level to its neutral 30%.</p>', "w3_limits", "Step 3: power limits and watchdog", h=2.6))
    a(step('<p class="st"><b>Step 4 · Materials</b> – the presets you pick when starting a job (power, feed, Z offset), and the '
           'pre-job checklist shown before every job with this tool. The material name box suggests the names listed under '
           '<b>Admin › Tool lists</b>.</p>', "w4_materials", "Step 4: materials and checklist", h=3.0))
    a(step('<p class="st"><b>Step 5 · Controls</b> – extra outputs and inputs the tool brings that are not simply switched with it: '
           'a fan with its own speed, a servo, a lid switch. Press <b>+ Add a control</b> and answer the guide\'s questions: you describe '
           'what the control does, and the portal works out which Klipper section that needs and shows the exact text it will write.</p>',
           "w5_controls", "Step 5: the tool's extra controls", h=2.6))
    a(keep('<p class="st"><b>The control guide</b> asks, in order:</p><ol>'
           '<li><b>Name and purpose.</b> Lower-case letters, digits and <code>_</code>, such as <code>needle_vacuum</code>. G-code uses '
           'the name (<code>SET_PIN PIN=needle_vacuum</code>), so it must not match anything else in your config.</li>'
           '<li><b>Which way does the signal go?</b> Rhino controls something on the tool, or the tool sends a signal to Rhino.</li>'
           '<li><b>What should Rhino do with it?</b> Pick the closest match:</li></ol>' +
           table(["You pick", "Klipper section", "Typical use"],
                 [["Switch it on and off", "<code>output_pin</code>", "Relay, solenoid, vacuum pump, light, valve"],
                  ["Set a level", "<code>output_pin</code>, <code>pwm: True</code>", "Driver board, LED dimmer, small heater"],
                  ["Run it like a fan", "<code>fan_generic</code>", "Fan or blower set by speed, with a kick-start"],
                  ["Run it while a heater is hot", "<code>heater_fan</code>", "Hotend or heat-break cooling"],
                  ["Move it to an angle", "<code>servo</code>", "Gate, pen lift, deflector"],
                  ["The tool sends a signal", "<code>gcode_button</code>", "Lid switch, limit switch, foot pedal, sensor"]],
                 widths=["32%", "30%", "38%"]) +
           '<ol start="4"><li><b>Which pin?</b> Only free tool-connector pins are listed. If <code>myrhino/umbilical.json</code> says '
           'what each pin is (<code>"type": "logic"</code> or <code>"type": "mosfet"</code>), pins that cannot do the job are greyed out.</li>'
           '<li><b>How does it behave?</b> Active-low wiring and power-up state for a switch; maximum level and PWM cycle time for a '
           'level or a fan; heater and turn-on temperature for a heater fan; pulse widths for a servo.</li>'
           '<li><b>Safety and shortcuts.</b> Switch it off whenever the machine is made safe (end of job, cancel, tool swap, '
           '<code>EMERGENCY_STOP</code>; ticked by default); switch it off or leave it on if Klipper shuts down; and make '
           '<code>NAME_ON</code> / <code>NAME_OFF</code> (or <code>NAME_SET</code>, <code>NAME_ANGLE</code>) macros, optionally only while '
           'this tool is mounted.</li></ol>'))
    a(step('<p class="st">The top of the guide: name, direction, what it does and the pin.</p>', "c_top",
           "A new control: name, direction and what it does", h=4.3))
    a(step('<p class="st">The bottom of the guide: safety options, the macros it makes, and the exact text written to '
           '<code>custom_tools.cfg</code>. <b>Add control</b> saves only a valid entry; a name already in use, a taken pin or two '
           'controls on one pin are refused, with the reason in the preview box.</p>', "c_bottom",
           "Safety options and the text written to custom_tools.cfg", h=4.3))
    a(step('<p class="st">For a signal from the tool, the guide asks how it is wired. A switch to ground turns on the pin\'s pull-up; '
           'a sensor that drives the line needs none. Then it asks what happens when the signal triggers and when it is released: '
           'show a message, pause the job (only while one is running), emergency stop, or run a command or macro.</p>', "c_input",
           "A lid switch that pauses the job when opened", h=4.3))
    a(step('<p class="st"><b>Step 6 · Macros</b> – G-code macros that belong to this tool: a test cut, a purge, a park move. They are '
           'written to <code>custom_tools.cfg</code> with the tool and removed with it. Macros your controls made are listed underneath.</p>',
           "w6_macros", "Step 6: the tool's macros", h=2.6))
    a(step('<p class="st">Press <b>+ Add a macro</b>. <b>Macro name</b>: letters, digits and <code>_</code>, saved in capitals because '
           'Klipper ignores letter case. <b>Purpose</b>: one line, shown in Mainsail\'s macro list. <b>Only run when this tool is '
           'mounted</b>: with another tool on the machine the macro refuses with a message. <b>Macro</b>: Klipper G-code and Jinja '
           'exactly as in a <code>[gcode_macro]</code>. The box underneath shows exactly what will be written.</p>'
           '<p class="st small"><b>Refused:</b> a name used by any macro or Klipper command (<code>SET_PIN</code>, <code>home</code>, '
           '<code>PAUSE</code>), G-code words such as <code>M3</code>, and template errors such as a missing <code>{% endif %}</code>. '
           '<b>Warned:</b> <code>SAVE_CONFIG</code>, <code>FIRMWARE_RESTART</code> or <code>M112</code> in the body, an unrecognised '
           'command (usually a typo), and text after <code>&nbsp;#</code> or <code>&nbsp;;</code>, which Klipper drops as a comment.</p>',
           "m_macro", "A macro with its live preview", h=4.0))
    a(step('<p class="st"><b>Step 7 · Review</b> – the portal checks everything against your live Klipper config, warns about shared '
           'outputs, and tells you the slot the tool will get. Add up to six photos here, then <b>Create tool</b>.</p>', "w7_review",
           "Step 7: review, with the outputs, controls and macros listed", h=3.8))
    a(step('<p class="st">Press <b>Add maintenance tasks</b> on the confirmation and the portal offers the Task Book that fits the new '
           'tool (see <em>Task Library and Task Books</em> in Part 4).</p>', "mt_assign_new", "The Task Book offered for a new needle cutter", h=1.8))
    a(step('<h3>Restarting Klipper to load changes</h3><p>A new or changed tool is saved immediately but is not live until Klipper '
           'restarts. A yellow banner lists what is waiting, from the portal or the console; press <b>Restart Klipper</b> when the '
           'machine is idle. Changes Klipper never sees – notes, photos, the pin map – are saved without asking for a restart.</p>',
           "banner_idle", "Changes waiting; the machine is idle, so the restart is allowed", h=1.6))
    a(step('<p class="st">While a job is printing or paused, <b>Restart Klipper</b> is greyed out and the banner says why, with the '
           'file name, a progress bar, time elapsed and time left, and the clock time when a restart becomes possible. Changes made '
           'during a job are saved and queued; only the restart waits, so it can never kill a job.</p>', "b_job",
           "A print running: progress, time left and when a restart is possible", h=1.6))
    a(step('<p class="st">Paused, the countdown stops and the banner shows how long the job has been paused.</p>', "b_paused",
           "The same job paused", h=1.6))
    a(step('<p class="st">Time left comes from the slicer\'s estimate for 3D prints. Laser, CNC and cutter files usually carry none, so '
           'the portal works it out from file progress, the way Mainsail does, and says so.</p>', "b_laser",
           "A laser job: time left estimated from file progress", h=1.7))
    a('<p><b>Restart automatically when this job finishes</b> is off by default. Tick it and the portal restarts Klipper 30 seconds '
      'after the job completes or is cancelled, which leaves time for <code>END_PRINT</code> or <code>CANCEL_PRINT</code> to finish. '
      'After an error it does not restart, so you can see what happened. A restart started anywhere else (Mainsail, '
      '<code>RESTART_FOR_TOOLS</code>) also clears the banner. The console commands (<code>ADD_TOOLHEAD</code> and the rest) stay '
      'refused during a job: they run a shell command that Klipper waits for, which would stall the job\'s G-code.</p>')
    a(step('<h3>Editing a tool</h3><p>Press <b>Edit</b> on the tool\'s card. On the <b>Settings</b> tab you can rename it and change its '
           'power limits and materials; the legend above the limits lists its outputs and the contacts they use.</p>',
           "e_settings", "Edit window: name, outputs, limits and materials", h=4.0))
    a(step('<p class="st">Further down are the checklist, the contacts the tool uses (tick more as you wire them), notes and photos. '
           '<b>x</b> on a photo deletes it; <b>Choose Files</b> adds more. Photos are kept in <code>~/printer_data/rhino_data/images/</code>, '
           'outside the config folder, so config backups stay small.</p>', "e_lower", "Edit window: checklist, contacts, notes and photos", h=4.6))
    a(step('<p class="st">The <b>Controls</b> and <b>Macros</b> tabs work exactly like steps 5 and 6 of the wizard; their changes are '
           'saved with <b>Save changes</b> and are live after the restart.</p>', "e_controls", "Edit window, Controls tab", h=2.4))
    a(step('<h3>Deleting a tool</h3><p>In the edit window press <b>Delete tool</b>. The button changes to <b>Click again to delete '
           '&lt;name&gt;</b>; press it within 4 seconds to confirm. The tool\'s pins are freed, its photos removed and its maintenance '
           'tasks archived. Restart Klipper afterwards.</p>', "e_delete", "Two-click delete confirmation", h=0.6))
    a(keep('<h3>On a phone</h3><p>The portal works on a phone: the menu folds behind <b>☰</b>, and the status chips scroll sideways in '
           'the top bar.</p><div class="phones">' + fig("phone_library", "Tool library") + fig("phone_menu", "Menu") +
           fig("phone_maint", "Maintenance") + "</div>"))
    return section("The Tool Manager portal", "".join(P))


def pins_and_hardware():
    P = []
    a = P.append
    a(step('<p><b>Hardware › Pins &amp; outputs</b> starts with the tool connector: all 21 contacts of the umbilical, the board pin '
           'behind each, what drives it in the Klipper config and which tools use it. A contact whose board pin nothing in the config '
           'uses is highlighted – it means the pin map and <code>printer.cfg</code> disagree (contact 20 here; see <em>Still to check on '
           'the machine</em>). The contacts come from the Rhino pin map; describe different wiring with <code>"contacts"</code> in '
           '<code>myrhino/umbilical.json</code>.</p>', "pins_contacts", "The 21 contacts, what drives them and which tools use them", h=6.6))
    a(step('<p class="st">Further down: the spare pins a new tool output may claim (Free, In use with the file and section, or '
           'Reserved by a tool), the outputs tools can share with their contact and idle level, and the system hardware.</p>',
           "pins_channels", "Output channels tools can share", h=2.0))
    a(step('<h3>System hardware</h3><p>Some hardware belongs to the machine rather than a tool: enclosure fans and lights, an air or '
           'vacuum pump, a door switch, a sensor. It is wired to board pins that are <i>not</i> on the umbilical and works whatever '
           'tool is mounted. <b>Hardware › System hardware</b> lists it by category; <b>+ Add system hardware</b> opens the same guide '
           'as a tool control.</p>', "hw_list", "System hardware, grouped by category", h=4.0))
    a(step('<p class="st">The differences from a tool control: the pin list offers free <b>board headers</b> (FAN5, HE2, DIAG4...) and '
           'refuses any pin on the umbilical; you can type another free pin; you choose a <b>category</b> (edited under <b>Admin › '
           'Tool lists</b>); and its macros have no mounted-tool guard. <b>Switch it off whenever the machine is made safe</b> is '
           'off by default, since lights and fans usually stay on. A powered tool can switch a piece of system hardware on with '
           'itself – a shop vacuum with a cutter – by choosing it as a <b>Switch on with the tool</b> output in step 2. Each piece can '
           'carry maintenance tasks (<b>Maintenance</b> on its card).</p>', "hw_editor", "An enclosure door switch that pauses the job", h=5.2))
    return section("Pins, outputs and system hardware", "".join(P))


def admin():
    P = []
    a = P.append
    a('<p>The <b>Admin</b> group sets what the portal\'s drop-down menus offer. Every list is checked as you save: a kind of tool, '
      'category or kind of work that something still uses cannot be removed (rename it instead).</p>')
    a(step('<h3>Tool lists</h3><p><b>Kinds of tool</b> are grouped under Additive, Subtractive and Passive – what step 1 of Add a tool '
           'offers. Each has a name, the help line shown in the wizard and what it needs: a print head (copies an extruder), a power '
           'output, or nothing. What it needs is fixed once the kind exists; built-in kinds can be renamed but not removed.</p>',
           "admin_tools", "Admin › Tool lists: kinds of tool by category", h=6.0))
    a(step('<p class="st">Open <b>Starting values for new tools of this kind</b> to set the power cap, maximum on-time, materials '
           '(one per line: name, power %, feed) and pre-job checklist that a new tool of this kind starts with.</p>', "admin_kind",
           "Starting values of the hot-wire kind", h=2.0))
    a(step('<p class="st">The same page holds the material names suggested in the material tables, by category; the nozzle sizes '
           'offered when you add a print head; and the system hardware categories.</p>', "admin_materials",
           "Material name suggestions by category", h=1.4))
    a(step('<h3>Maintenance lists</h3><p>The machine areas tasks are grouped by, the kinds of work (Inspect, Clean...) with how many '
           'tasks use each, and the names of the four priority levels.</p>', "admin_maint", "Admin › Maintenance lists", h=5.2))
    a('<p><b>Status codes</b> are described with maintenance tracking in Part 4.</p>')
    return section("Admin lists", "".join(P))


def maintenance():
    P = []
    a = P.append
    a('<p>The portal keeps track of preventive maintenance for the machine, every tool and the system hardware. It tells you what is '
      'overdue, what is coming up and what parts to have ready. It never blocks a job, a swap or a command. Open it from '
      '<b>Maintenance</b> in the sidebar: <b>Due &amp; upcoming</b>, <b>Tasks</b>, <b>Task Library</b>, <b>Work log</b> and '
      '<b>Usage meters</b>.</p>')
    a(keep('<h3>Getting started</h3><p>Open the <b>Task Library</b> and assign a <b>Task Book</b> to the whole machine and to each tool: '
           '<i>Rhino motion system and frame</i> on the machine, <i>3D print head</i> on BlockOne and SwitchFly, <i>Laser module</i> on '
           'LightSaber, and so on. The intervals are starting points; tune them to how your machine wears (see <em>Task Library and '
           'Task Books</em>). When you add a tool, the confirmation offers the book that fits it.</p>'))
    a(step('<h3>Due &amp; upcoming</h3><p>Tasks are grouped by status. The tiles at the top count them. Each card shows every rule with '
           'a progress bar, how far off it is, and an estimate in days at your usual rate of use. Once the early alarm goes off, the '
           'card lists the parts to <b>Have ready</b>.</p>', "mt_due", "Due & upcoming", h=6.0))
    a(keep(table(["Group", "Meaning"], [["Overdue", "Past the due point"],
                                        ["Due soon", "Inside the early alarm: time to plan the work and order parts"],
                                        ["A status code's own group", "Tasks set to a status shown in its own group, such as <i>Pending – Waiting on parts</i>"],
                                        ["Snoozed", "Put off on purpose"],
                                        ["Coming up", "The next eight tasks by how close they are to due, plus tasks set to a status shown with the upcoming ones"]],
                 widths=["30%", "70%"]) +
           '<p><b>Log work</b> records what happened. <b>Set status</b> puts a status code on the task. <b>Snooze</b> puts an overdue or '
           'due-soon task off for 1 day to 2 weeks. <b>Details</b> opens the task. The sidebar badge and a chip in the top bar show the '
           'count: red for overdue, amber for due soon.</p>'))
    a(step('<p class="st">A card with a status code set shows it at the top in its colour, with the note, when it was set and when it '
           'ends by itself. Here <i>In progress</i> ends after three days; the task is still due soon underneath.</p>', "mt_card",
           "A task set to In progress, with its note", h=3.2))
    a(step('<h3>Logging work</h3><p><b>Log work</b> shows the task\'s steps and safety notes. <b>What happened?</b> is a list: '
           '<b>Done</b>; <b>Skipped – not needed this time</b> if you checked and nothing needed doing; or one of your status codes. '
           'Done and Skipped start the schedule again from here, and so do a part\'s hours, so a new nozzle starts at zero. You can '
           'backdate the entry and add notes; the current meter readings are saved with it.</p>', "mt_done",
           "Logging a nozzle clean as done", h=3.4))
    a(step('<p class="st">Choosing a status code instead sets that status on the task and logs it. The help line says what the status '
           'does; <i>Pending – Waiting on parts</i> needs a note saying what is on order.</p>', "mt_done_status",
           "Logging a task as waiting on parts", h=3.4))
    a(step('<p class="st"><b>Set status</b> on a card does the same without the steps, and <b>Clear the status</b> takes it off again.</p>',
           "mt_status", "Setting a status from the card", h=1.9))
    a(step('<h3>Tasks</h3><p>Every task in one table, sorted overdue first, with its status code and status. Library tasks show '
           '<i>Library</i> and the Task Book they came from. <b>Show</b> filters it: overdue and due soon, with a status set, one machine '
           'area, one tool or piece of system hardware, or archived. Choosing an area or a tool also shows its usage meters.</p>',
           "mt_tasks", "Tasks", h=4.5))
    a(step('<h3>Creating a task</h3><p><b>+ New task</b> opens the task editor:</p><ul>'
           '<li><b>Task</b> – a short title. It is also shown in the Mainsail reminder.</li>'
           '<li><b>For</b> – a machine area, a tool or a piece of system hardware.</li>'
           '<li><b>Kind of work</b> and <b>Priority</b> – used for sorting and the card\'s label (the lists are under <b>Admin › '
           'Maintenance lists</b>).</li>'
           '<li><b>When is it due?</b> – up to four rules. The task is due when the first of them is reached.</li>'
           '<li><b>Start counting from</b> (new tasks only) – now, or the date it was last done, with the meter readings at that time.</li>'
           '<li><b>How to do it</b> – steps, parts and consumables, tools needed, time needed, safety notes and links.</li>'
           '<li><b>Reminders</b> – include it in the start-up reminder, or pause the task.</li></ul>', "mt_new",
           "A new task with two rules", h=4.4))
    a(keep(table(["Rule", "Example", "Early alarm"],
                 [["Every so often", "every 3 months", "14 days before"],
                  ["After so much use", "every 100 working hours of this tool", "10 h before"],
                  ["After each event", "after each emergency stop or Klipper shutdown", "due straight away"],
                  ["Once, on a date", "1 Dec 2026", "7 days before"]], widths=["24%", "48%", "28%"]) +
           '<p>Time rules count from when the task was last done, so doing it late moves the next one later. Choose <b>On a fixed '
           'calendar</b> to keep the same dates every time, such as the 1st of every month. A usage rule\'s early alarm is in the '
           'meter\'s own unit; leave it empty for 10% of the interval. Events are a tool swap, this tool being mounted, a job, and an '
           'emergency stop or shutdown. <b>Add this task to the Task Library</b>, at the bottom of an existing task, turns it into a '
           'library task and links it.</p>'))
    a(step('<h3>Work log</h3><p>Every entry, newest first: work done or skipped, status codes set and cleared, and meter changes. Filter '
           'it by machine area, tool or system hardware.</p>', "mt_log", "Work log", h=2.6))
    a(step('<h3>Usage meters</h3><p>Usage rules count these meters. The portal reads them from Moonraker every few seconds and from '
           'Moonraker\'s job history.</p>', "mt_meters", "Usage meters", h=4.4))
    a(keep(table(["Meter", "Machine", "Each tool", "Counts"],
                 [["Machine up hours", "yes", "–", "Klipper running and ready"],
                  ["Production hours", "yes", "yes", "A job running. Pauses are not counted."],
                  ["Hours mounted", "–", "yes", "The tool on the machine while Klipper is up"],
                  ["Working hours", "–", "yes", "Print heads: nozzle heater on. LightSaber: laser on. HotJoe: spindle running. Added "
                   "powered tools: output on. Passive tools and DragKnife: running a job."],
                  ["Jobs", "yes", "yes", "Finished jobs, from the job history"],
                  ["Filament used", "yes", "print heads", "From the job history"],
                  ["Tool swaps / Times mounted", "yes", "yes", "A different tool mounted. A restart is not a swap."],
                  ["Emergency stops and shutdowns", "yes", "–", "Klipper entering shutdown"]],
                 widths=["26%", "11%", "13%", "50%"]) +
           '<p>The first time the portal runs, it imports the jobs already in Moonraker\'s history as the machine\'s starting reading. If '
           'the machine had hours before that, press <b>Set</b> on a meter and note why; the change goes in the work log. Jobs that ran '
           'while the portal was stopped are filled in from the history the next time it starts. System hardware tasks count the '
           'machine\'s meters. The page also has the start-up reminder switch.</p>'))
    a(keep('<h3>Reminders in Mainsail</h3><p>After Klipper starts, once you answer <i>which toolhead is mounted?</i>, Mainsail shows a '
           '<b>Maintenance due</b> pop-up with up to eight overdue and due-soon tasks, overdue first. It appears once per start; close it '
           'with <b>OK</b>. Snoozed tasks, tasks with the reminder unticked and tasks set to a status code that leaves them out of the '
           'reminder are not shown.</p><p>The portal keeps <code>myrhino/maintenance_status.cfg</code> up to date, and Klipper reads it '
           'when it starts. At any other time, type <code>PM_STATUS</code> in the console for the live list, or <code>PM_REMINDER</code> '
           'to show the start-up pop-up again. Renaming a tool moves its tasks and meters with it. Removing a tool or a piece of system '
           'hardware archives its tasks (filter <b>Archived</b>) and keeps their work-log entries.</p>'))
    out = section("Maintenance tracking", "".join(P))

    L = []
    b = L.append
    b('<p>The <b>Task Library</b> holds task definitions that are not tied to anything yet – the starter tasks for the Rhino and each '
      'kind of tool, and any you add. A <b>Task Book</b> is a named group of library tasks. Assign a book to a toolhead, a piece of '
      'system hardware or the whole machine, and it carries all of its tasks there.</p>')
    b(step('<p class="st">The <b>Task Books</b> tab shows each book, its tasks and where it is assigned. <b>Assign...</b> puts it on '
           'something more; the <b>×</b> on an assignment takes it off, which archives the tasks it added there (their work log is '
           'kept). Books whose tasks count a tool\'s own use, such as working hours, can only go on toolheads.</p>', "mt_books",
           "Task Books, with where each is assigned", h=6.0))
    b(step('<p class="st"><b>Assign...</b> asks where. <b>Whole machine</b> puts each task in its own machine area (belts in Motion X/Y, '
           'leadscrews in Motion Z...). Assigning a book twice adds nothing twice.</p>', "mt_assign", "Assigning a Task Book", h=1.8))
    b(step('<h3>Linked tasks</h3><p>Tasks that come from the library stay <b>linked</b> to it. Their steps and schedule are the '
           'library\'s, so <b>Details</b> on a linked task shows them read-only with two choices: <b>Edit the library task</b>, which '
           'changes every copy at once, or <b>Detach to customise</b>, which turns this one task into an ordinary task you can edit on '
           'its own. Pausing a linked task affects only that task. Each copy keeps its own schedule: when it was last done, its '
           'readings and its status.</p>', "mt_linked", "A linked task", h=3.0))
    b(step('<p class="st">The <b>Library tasks</b> tab lists every library task: its schedule, what it can go on, the books it is in and '
           'the tasks made from it. <b>Edit</b> opens the editor; saving says how many linked tasks it updates. <b>Add to...</b> puts one '
           'library task on something without a book. <b>+ Library task</b> adds your own; its <b>Area when the book goes on the whole '
           'machine</b> decides where it lands with <b>Whole machine</b>. Deleting a library task keeps the tasks made from it as ordinary '
           'tasks.</p>', "mt_libtasks", "Library tasks", h=5.6))
    b(step('<p class="st">Editing a library task: the box at the top lists the tasks it will update.</p>', "mt_tpl",
           "Editing the laser-lens library task", h=4.8))
    b(step('<p class="st"><b>+ Task Book</b> makes a book: a name, an optional description and the library tasks in it, found with the '
           'search box. Tasks you add to a book that is already assigned are added there too; tasks you take out are archived there.</p>',
           "mt_book", "A new Task Book for wide-nozzle print heads", h=5.0))
    out += section("Task Library and Task Books", "".join(L))

    C = []
    c = C.append
    c('<p><b>Admin › Status codes</b> lists two kinds of status. The <b>built-in statuses</b> – Overdue, Due soon, Scheduled, Done, '
      'Snoozed and Paused – are worked out from each task\'s schedule, the snooze and the pause switch. Rename them or change their '
      'colour; they cannot be removed.</p>')
    c(step('', "admin_status_builtin", "Built-in statuses: name and colour", h=2.2))
    c(step('<p class="st"><b>Your status codes</b> are set by hand, from a task card or the Log work list: <i>Pending – Waiting on '
           'parts</i>, <i>In progress</i>, <i>Deferred to next shutdown</i>, or any you add with <b>+ Add a status code</b>. Each answers '
           'four questions, and the portal applies the answers as rules.</p>', "admin_status_card", "The rules of Pending – Waiting on parts", h=3.2))
    c(keep(table(["Question", "Choices", "What it does"],
                 [["1. Where does the task show?", "With the due tasks · in its own group · with the upcoming tasks",
                   "Where Due &amp; upcoming lists it. Only <i>with the due tasks</i> keeps it in the overdue and due-soon counts."],
                  ["2. What happens to its schedule?", "Keeps running · pauses · counts as done",
                   "<i>Keeps running</i>: the task still ages toward overdue. <i>Pauses</i>: time and use while the status is set do "
                   "not count; the due point moves later by that much when it ends. <i>Counts as done</i>: the interval starts again "
                   "when the status is set."],
                  ["3. When does it end by itself?", "Never · after a number of days · when the machine or tool is used again",
                   "When it ends, the task goes back to its built-in status and the end is logged. Logging the task done also ends it."],
                  ["4. Also", "Keep it in the Mainsail reminder · a note is required · offer it in the Log work list",
                   "Whether the start-up pop-up still shows the task when due; whether whoever sets it must say why; whether it appears "
                   "next to Done and Skipped."]],
                 widths=["24%", "30%", "46%"]) +
           '<p>A status code that tasks are set to cannot be removed until they are cleared. The three codes the portal starts with:</p>' +
           table(["Status code", "Shows", "Schedule", "Ends"],
                 [["Pending – Waiting on parts", "own group", "keeps running", "never (note required)"],
                  ["In progress", "with the due tasks", "keeps running", "after 3 days"],
                  ["Deferred to next shutdown", "with the upcoming tasks", "pauses", "when the machine is used again"]],
                 widths=["32%", "24%", "20%", "24%"])))
    out += section("Status codes", "".join(C))
    return out


# ============================================================================= assemble
def still_to_check():
    extra = ('<li data-checked="false"><p><input type="checkbox" disabled> <strong>Spindle and servo PWM contact.</strong> The '
             'umbilical pin map puts the ESC signal (PB11) on contact 18, but the original HotJoe and SwitchFly sheets listed the PWM '
             'signal on contact 19. This manual and the portal use 18, which matches the pin map and <code>printer.cfg</code>; '
             'check the connector and correct the pages if it is 19.</p></li>'
             '<li data-checked="false"><p><input type="checkbox" disabled> <strong>Laser 12 V power pin.</strong> The pin map lists '
             'PD12 (Fan2) for the 12 V power activate on contacts 20–21; <code>printer.cfg</code> drives <code>LASER_INITIALIZE</code> '
             'from PD13 (Fan3 on the Octopus v1.1).</p></li>'
             '<li data-checked="false"><p><input type="checkbox" disabled> <strong>X and Y endstops.</strong> The wiring sheets give '
             'X-limit PG6 and Y-limit PG9; <code>printer.cfg</code> has <code>stepper_x</code> on PG9 and <code>stepper_y</code> on PG6.</p></li>'
             '<li data-checked="false"><p><input type="checkbox" disabled> <strong>SwitchFly servo power.</strong> The SwitchFly page '
             'lists 24 V power activate on contacts 11–12, while its servo wiring diagram feeds the regulator from 12 V activate.</p></li>'
             '<li data-checked="false"><p><input type="checkbox" disabled> <strong>Fan labels.</strong> On the Octopus v1.1 PA8 is FAN0 '
             'and PE5 is FAN1; the pin sheets label them Fan5 and Fan0. The pins are right; only the labels differ.</p></li></ul>')
    return xsec("17_still-to-check-on-the-machine.html", [("</ul>", extra)])


ORCA_OLD = ('<p><strong>OrcaSlicer (printing).</strong> The printer profile&#39;s start G-code must call <code>START_JOB</code> with the '
            'tool, material, nozzle size and extruder, for example <code>START_JOB TOOLHEAD=&quot;SwitchFly&quot; MATERIAL=&quot;PLA&quot; '
            'NOZZLE_SIZE=0.4 EXTRUDER=0</code>. End the file with <code>END_PRINT</code>.</p>')
ORCA_NEW = ('<p><strong>OrcaSlicer (printing).</strong> Make one printer profile per print head (BlockOne, SwitchFly, and any print '
            'head you add). In each profile, <b>Printer settings › Machine G-code › Machine start G-code</b> calls <code>START_JOB</code>. '
            'Type the tool\'s name once; OrcaSlicer fills in the rest from the filament and nozzle chosen when you slice:</p>'
            '<pre class="code">START_JOB TOOLHEAD="SwitchFly" MATERIAL="{filament_type[initial_extruder]}" '
            'NOZZLE_SIZE={nozzle_diameter[initial_extruder]} EXTRUDER={initial_extruder}</pre>' +
            table(["START_JOB parameter", "OrcaSlicer placeholder", "Becomes"],
                  [["<code>TOOLHEAD</code>", "typed in each printer profile", "<code>SwitchFly</code> – must match the mounted tool"],
                   ["<code>MATERIAL</code>", "<code>{filament_type[initial_extruder]}</code>", "<code>PLA</code>, <code>PETG</code>... – the filament profile's type"],
                   ["<code>NOZZLE_SIZE</code>", "<code>{nozzle_diameter[initial_extruder]}</code>", "<code>0.4</code> – the printer profile's nozzle"],
                   ["<code>EXTRUDER</code>", "<code>{initial_extruder}</code>", "<code>0</code> or <code>1</code> – the first filament used (SwitchFly)"]],
                  widths=["24%", "40%", "36%"]) +
            '<p>Together they pick the tool\'s material profile, such as <code>PLA_0_4</code>. <b>Filament type</b> (in the filament '
            'profile\'s settings) must be one of the tool\'s materials – PLA, PETG, ABS or ASA for BlockOne and SwitchFly; a type such as '
            '<i>PLA-CF</i> stops the job at the start with <i>Material PLA-CF_0_4 not defined for toolhead BlockOne</i>. End the file (<b>Machine end '
            'G-code</b>) with <code>END_PRINT</code>.</p>')


def build():
    body = []
    body.append(part(1, "The Rhino", "The machine, what it needs, and how it is wired.",
                     ["About the Rhino", "System necessities", "The machine", "Wiring and pin mapping"]))
    body.append(xsec("01_about-the-rhino.html"))
    body.append(necessities())
    body.append(machine())
    body.append(wiring())
    body.append(part(2, "The Tools", "The built-in tools, their umbilical contacts and parts, and sheets for the tools you build.",
                     ["The tools", "BlockOne", "SwitchFly", "LightSaber", "HotJoe", "DragKnife", "Tools you add", "Rhino tools log"]))
    body.append(tools_intro())
    for n in ["BlockOne", "SwitchFly", "LightSaber", "HotJoe", "DragKnife"]:
        TOC.append((3, n, f"tool-{n}"))
        body.append(tool_pages(n))
    body.append(tools_added())
    TOC.append((3, "Rhino tools log", "toolslog"))
    body.append(tools_log())
    body.append(part(3, "Software and Operation", "Installing the software, changing tools, running jobs and the Tool Manager portal.",
                     ["How the software fits together", "Install and first start", "Swapping tools", "Running a job",
                      "Pause, resume and cancel", "The Tool Manager portal", "Pins, outputs and system hardware", "Admin lists",
                      "Console commands", "Safety systems"]))
    body.append(xsec("04_how-the-software-fits-together.html"))
    body.append(xsec("05_install-and-first-start.html"))
    body.append(xsec("06_swapping-tools.html"))
    body.append(xsec("07_running-a-job.html", [(ORCA_OLD, ORCA_NEW)]))
    body.append(xsec("08_pause-resume-and-cancel.html"))
    body.append(portal())
    body.append(pins_and_hardware())
    body.append(admin())
    body.append(xsec("10_console-commands.html"))
    body.append(xsec("11_safety-systems.html"))
    body.append(part(4, "Maintenance", "Tracking preventive maintenance in the portal, and the procedures themselves.",
                     ["Maintenance tracking", "Task Library and Task Books", "Status codes", "Maintenance procedures"]))
    body.append(maintenance())
    body.append(xsec("13_maintenance.html", title="Maintenance procedures"))
    body.append(part(5, "Reference", "When something goes wrong, where things live, and what is left to check.",
                     ["Troubleshooting", "Files, backups and tests", "Build reference", "Still to check on the machine"]))
    body.append(xsec("14_troubleshooting.html"))
    body.append(xsec("15_files-backups-and-tests.html"))
    body.append(xsec("16_build-reference.html"))
    body.append(still_to_check())
    main = "".join(body)
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><title>Rhino Multi-Tool Motion System - User Manual</title>'
           f'<link rel="stylesheet" href="file://{HERE}/manual.css"></head><body>{cover()}{contents()}{main}</body></html>')
    open(os.path.join(HERE, "content.html"), "w").write(doc)
    json.dump(TOC, open(os.path.join(HERE, "toc.json"), "w"))
    json.dump(MARKS, open(os.path.join(HERE, "marks.json"), "w"))
    print("built", len(doc), "chars,", len(TOC), "contents entries")


if __name__ == "__main__":
    build()
