"""The four wiring diagrams, redrawn as vector drawings in one style (Rhino Wiring: Diagrams pages).

Conventions on every diagram: red = + supply, black = ground / -, blue = signal or PWM, grey = motor
phases. Blocks are labelled in the manual's type; terminals are the coloured tabs from the original
sheets. Each function returns an inline <svg>.
"""
RED, BLK, BLU, GRY = "#c62828", "#161616", "#1565c0", "#8a8a8a"
W, H = 700, 360


class D:
    def __init__(self, h=H):
        self.h = h
        self.o = [f'<svg class="wd" viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" font-family="Inter">']

    def block(self, x, y, w, h, title, sub="", dashed=False, dx=0, dy=0):
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        self.o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#fff" stroke="#222" stroke-width="1.6"{dash}/>')
        cx = x + w / 2 + dx
        y += dy
        self.o.append(f'<text x="{cx}" y="{y + h / 2 - (6 if sub else -5)}" text-anchor="middle" font-size="14" font-weight="700" '
                      f'font-family="Inter Display">{title}</text>')
        if sub:
            for i, line in enumerate(sub.split("\n")):
                self.o.append(f'<text x="{cx}" y="{y + h / 2 + 12 + i * 12}" text-anchor="middle" font-size="9.5" fill="#666">{line}</text>')

    def pin(self, x, y, side, label, color, note=""):
        """A terminal tab on a block edge. side: l/r/t/b = which edge it sticks out of."""
        if side in "lr":
            px = x - 14 if side == "l" else x
            self.o.append(f'<rect x="{px}" y="{y - 4.5}" width="14" height="9" fill="{color}" stroke="#222" stroke-width="0.8"/>')
            tx, anchor = (x + 6, "start") if side == "l" else (x - 6, "end")
            self.o.append(f'<text x="{tx}" y="{y + 3.5}" text-anchor="{anchor}" font-size="9.5" font-weight="600">{label}</text>')
        else:
            py = y - 14 if side == "t" else y
            self.o.append(f'<rect x="{x - 4.5}" y="{py}" width="9" height="14" fill="{color}" stroke="#222" stroke-width="0.8"/>')
            ty = y + 14 if side == "t" else y - 7
            self.o.append(f'<text x="{x}" y="{ty}" text-anchor="middle" font-size="9.5" font-weight="600">{label}</text>')
        if note:
            if side in "lr":
                self.text(x + (18 if side == "r" else -18), y + 17, note, anchor="start" if side == "r" else "end", size=8.5, color="#777", italic=True)
            else:
                self.text(x, y + (-20 if side == "t" else 26), note, anchor="middle", size=8.5, color="#777", italic=True)

    def wire(self, pts, color, dash=False):
        d = " ".join(f"{'M' if i == 0 else 'L'}{x} {y}" for i, (x, y) in enumerate(pts))
        da = ' stroke-dasharray="6 4"' if dash else ""
        self.o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"{da}/>')

    def dot(self, x, y, color):
        self.o.append(f'<circle cx="{x}" cy="{y}" r="3.6" fill="{color}"/>')

    def text(self, x, y, s, anchor="start", size=10, color="#222", bold=False, italic=False):
        st = (' font-weight="700"' if bold else "") + (' font-style="italic"' if italic else "")
        self.o.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{color}"{st}>{s}</text>')

    def supply(self, x, y1, y2, label, sub=""):
        """Bare wire ends coming in from the left (a supply that arrives on the umbilical)."""
        for y, s in ((y1, "+"), (y2, "&#8722;")):
            self.o.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#fff" stroke="#222" stroke-width="1.4"/>')
            self.text(x - 9, y + 4, s, anchor="end", size=12, bold=True)
        self.text(x - 14, y1 - 26, label, size=10.5, bold=True)
        if sub:
            self.text(x - 14, y1 - 14, sub, size=8.5, color="#777")

    def legend(self, items):
        x = 14
        for color, label, dash in items:
            da = ' stroke-dasharray="6 4"' if dash else ""
            self.o.append(f'<line x1="{x}" y1="{self.h - 12}" x2="{x + 24}" y2="{self.h - 12}" stroke="{color}" stroke-width="2.2"{da}/>')
            self.text(x + 30, self.h - 8.5, label, size=9, color="#555")
            x += 40 + len(label) * 5.4

    def svg(self):
        return "".join(self.o) + "</svg>"


LEGEND = [(RED, "+ supply", False), (BLK, "ground / -", False), (BLU, "signal / PWM", False)]


def switchfly():
    d = D()
    d.supply(40, 95, 145, "12 V activate", "switched on with the tool")
    d.block(210, 60, 140, 120, "PW-D", "12 V to 5 V\nregulator")
    d.pin(210, 95, "l", "IN +", RED); d.pin(210, 145, "l", "IN -", BLK)
    d.pin(350, 95, "r", "5 V +", RED); d.pin(350, 145, "r", "GND", BLK)
    d.block(540, 45, 140, 150, "Servo", "SwitchFly\nfilament path")
    d.pin(540, 80, "l", "5 V +", RED); d.pin(540, 120, "l", "SIG", BLU); d.pin(540, 160, "l", "GND", BLK)
    d.block(250, 250, 230, 85, "Octopus (MCU)", "2-pin PWM fan header", dy=10)
    d.pin(320, 250, "t", "+", RED, note="not used"); d.pin(410, 250, "t", "- (PWM)", BLK)
    d.wire([(44, 95), (196, 95)], RED); d.wire([(44, 145), (196, 145)], BLK)
    d.wire([(364, 95), (450, 95), (450, 80), (526, 80)], RED)
    d.wire([(364, 145), (470, 145), (470, 160), (526, 160)], BLK)
    d.wire([(410, 236), (410, 215), (500, 215), (500, 120), (526, 120)], BLU)
    d.legend(LEGEND)
    return d.svg()


def hotjoe():
    d = D()
    d.supply(40, 95, 155, "24 V activate", "40 A relay, on with the spindle")
    d.block(210, 60, 160, 130, "ESC", "brushless speed\ncontroller")
    d.pin(210, 95, "l", "+", RED); d.pin(210, 155, "l", "-", BLK)
    for i, ph in enumerate("ABC"):
        d.pin(370, 90 + i * 35, "r", ph, GRY)
    d.pin(240, 190, "b", "SIG", BLU); d.pin(290, 190, "b", "5 V", RED); d.pin(340, 190, "b", "GND", BLK)
    d.text(360, 222, "BEC 5 V and GND: not connected", anchor="start", size=8.5, color="#777", italic=True)
    d.block(540, 60, 140, 130, "BLDC motor", "HotJoe spindle")
    for i, ph in enumerate("ABC"):
        d.pin(540, 90 + i * 35, "l", ph, GRY)
        d.wire([(384, 90 + i * 35), (526, 90 + i * 35)], GRY)
    d.block(150, 262, 230, 80, "Octopus (MCU)", "2-pin PWM fan header", dy=10)
    d.pin(240, 262, "t", "- (PWM)", BLK); d.pin(330, 262, "t", "+", RED, note="not used")
    d.wire([(44, 95), (196, 95)], RED); d.wire([(44, 155), (196, 155)], BLK)
    d.wire([(240, 204), (240, 248)], BLU)
    d.legend(LEGEND + [(GRY, "motor phases", False)])
    return d.svg()


def fan():
    d = D()
    d.block(30, 40, 230, 270, "Octopus (MCU)", "", dx=-20)
    d.text(145, 66, "Big Tree Tech Octopus v1.1", anchor="middle", size=9, color="#777")
    d.pin(260, 100, "r", "+24 V", RED, note="always-on fan header")
    d.pin(260, 175, "r", "PWM", BLU, note="FAN0 header (PA8), switched -")
    d.pin(260, 250, "r", "GND", BLK, note="board ground")
    d.block(480, 55, 190, 240, "Part-cooling fan", "4-pin PWM fan", dx=14)
    d.pin(480, 100, "l", "+", RED); d.pin(480, 175, "l", "PWM", BLU); d.pin(480, 250, "l", "-", BLK)
    d.pin(480, 280, "l", "TACH", "#fff", note="not connected")
    d.wire([(274, 100), (466, 100)], RED); d.wire([(274, 175), (466, 175)], BLU); d.wire([(274, 250), (466, 250)], BLK)
    d.legend(LEGEND)
    return d.svg()


def probe():
    d = D(380)
    d.block(20, 40, 150, 120, "Capacitive sensor", "LJC18A3-H-Z/BX\nsenses 1-10 mm", dx=-10)
    d.pin(170, 70, "r", "OUT", BLU, note=""); d.pin(170, 100, "r", "+", RED); d.pin(170, 130, "r", "-", BLK)
    d.text(176, 60, "black", size=8, color="#777", italic=True); d.text(176, 90, "brown", size=8, color="#777", italic=True)
    d.text(176, 145, "blue", size=8, color="#777", italic=True)
    d.block(20, 230, 130, 100, "Power supply", "12 V", dx=-12)
    d.pin(150, 260, "r", "+12 V", RED); d.pin(150, 305, "r", "GND", BLK)
    d.block(300, 55, 150, 160, "Optocoupler", "12 V input\n1 channel")
    d.pin(300, 90, "l", "IN -", BLU); d.pin(300, 175, "l", "IN +", RED)
    d.pin(450, 80, "r", "VCC", RED); d.pin(450, 135, "r", "OUT", BLU); d.pin(450, 190, "r", "GND", BLK)
    d.block(560, 55, 128, 160, "Z endstop", "board\nconnector", dx=18)
    d.pin(560, 80, "l", "+5 V", RED); d.pin(560, 135, "l", "SIG", BLU); d.pin(560, 190, "l", "GND", BLK)
    d.block(560, 262, 128, 80, "Microswitch", "Z endstop\n(recommended)", dashed=True, dx=12)
    d.pin(560, 282, "l", "C", BLU); d.pin(560, 322, "l", "NO", BLK)
    # sensor side
    d.wire([(184, 70), (255, 70), (255, 90), (286, 90)], BLU)
    d.wire([(184, 100), (225, 100), (225, 260), (164, 260)], RED)
    d.wire([(225, 175), (286, 175)], RED); d.dot(225, 175, RED)
    d.wire([(184, 130), (200, 130), (200, 305), (164, 305)], BLK)
    # board side
    d.wire([(464, 80), (546, 80)], RED)
    d.wire([(464, 135), (546, 135)], BLU); d.wire([(500, 135), (500, 282), (546, 282)], BLU); d.dot(500, 135, BLU)
    d.wire([(464, 190), (546, 190)], BLK); d.wire([(522, 190), (522, 322), (546, 322)], BLK); d.dot(522, 190, BLK)
    d.legend(LEGEND)
    return d.svg()
