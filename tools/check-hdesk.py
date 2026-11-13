#!/usr/bin/env python3
"""tools/check-hdesk.py TRANSCRIPT FRAME WAD: the H-3a and H-3b gate (docs/specs/2026-11-05-h-hybrid.md section 7)
on a boot of the hdesk flavor (src/main_hdesk.ci), where check-hybrid.sh typed: Super+Enter; `mkdir notes; cd notes` (the
variable `/notes`, cish's OSC 2, K-9) and `cd ..; ./doom --sealed` in the second terminal; Alt+Tab once doom ended; Alt+`; Alt+Ctrl+Tab, Right, Right, Enter;
Super+m, a Super tap (the Super plane, FF-5), `con`, Down, Enter (both terminals read `Console - /`, K-9; window 0 is the second row); Super+z; Super+2, Super+1, Super+z; Super+Shift+Right,
Super+Shift+Left; Super+f, Super+Shift+Right twice, Super+Ctrl+Down, Super+Ctrl+Right, Super+f; Super+Left; `exit`;
a Super tap, `sett`, Enter (Settings from the plane, the keyboard on its sidebar, ST-K1), Right, Tab three times,
Right twice (portrait), Tab, Enter, Down, Enter (1080 x 1920), Enter (kept; the failed save's message gone), Tab
twice (back to the sidebar), Right, Right (Warm Paper, K-3), Esc; `exec grant disk sh` in the first, the pointer up
to the bar (DN-72: no DISK pill to click), Super+m, Super+Shift+m;
Super+= twice and Super+- (the UI scale 2x, 3x, 2x); then `exit`. Each layout block is laid out at its UI scale. Each layout block is checked at the size it was laid out at. FRAME is the last frame of a Linux run of `doom --sealed --headless --frame-out FRAME`.

  layouts     every `hdesk: layout` block is user/ci/kit/layout.ci's (tools/check-layout.py's twin) for the
              windows' desktops, modes, ranks and float frames it names; every switcher frame is E2-2's card (K-1)
  places      every `hdesk: place` is the window's content box (a float's less its bar, WB-1) at the largest scale 1..6 that holds 320 x 200,
              centered, its rectangles the visible ones cut to the scaled surface; each returned 0
  steps       the script's steps in order: a second terminal, its variable on the bar, doom bound as window 2 and
              ended, the switchers' choices, the plane's window and Settings, monocle, desktop 2 empty, the swaps,
              the second terminal ended, the first
  menu        every list is the open list kept by its query; each choice is the selected entry (the plane's
              own lines are check-hybrid.sh's golden, tests/expected/hdesk-ff.out)
  doom        doom's private surface is FRAME 1x through the WAD's PLAYPAL
  clock       K-6: the bar's clock is the fixed epoch's, `Thu Jan 1  12:00 AM` (RS-TZb), printed once; Super+c
              opened the calendar on January 2026, Right stepped to February and Left back, each month's first
              weekday, length and today the Python's calendar
  screen      the surface after the desk, at its UI scale (2x), is the bar (K-5: the color mark, the App pill, desktop
              1 and its sienna pip, no grant pill (DN-72), the clock filled) and the first terminal alone, focused, its sienna grant ring, its rows and cursor
              as printed, under the calendar left open (RS-CAL, frame 44: kit/calpop.ci's twin, CalPop)
  ends        the shell ended with status 0, nothing dropped, the pool whole"""
import datetime
import hashlib
import importlib.util
import os
import re
import sys
from math import isqrt

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ct = load("ct", "check-tiler.py")
gl = load("gl", "guestlines.py")         # RS-TTL: a transcript's lines, split at line ends only
cl = load("cl", "check-layout.py")
tw = load("tw", "textwin.py")            # FONT-1: the chrome's text, kit/ctext.ci's twin
F_PATH, F_BODY, F_NAME, F_LABEL = tw.PATH, tw.BODY, tw.NAME, tw.LABEL   # kit/faces.ci's roles
F_NAME_BOLD, F_SMALL = tw.NAME_BOLD, tw.SMALL           # DN-23 and DN-20
TBASE = 13                               # hdesk.ci TBASE: a 16 px text slot's top to its baseline


def txt(r1, y, x0, y0, x1, s, c, f):
    """hdesk.ci txt: s in role f at 1x on row y, the slot's top y0, from x0, none past x1; the pen."""
    return tw.text(r1, y, x0, y0 + TBASE, x1, s, c, f, 1)


def txt_w(s, f):
    """hdesk.ci txt_w."""
    return tw.width(s, f, 1)


# FONT-2 A (docs/specs/2026-11-07-k-kit2.md section 3i): user/ci/kit/pen.ci's twin. The chrome's rows keep their 1x
# geometry and draw it at a zoom (zoom(sc)): 1x point (ox, oy) is device point (ox, oy), a 1x length is z device
# pixels, the row being drawn is device row dy, and the text is the z tables'. The row is then spread by sc // z.
PEN = [1, 0, 0, 0]                       # z, ox, oy, dy


def zoom(sc):
    """hdesk.ci tz: the chrome and the terminal draw at 2 at an even UI scale (native at 2x), at 1 at an odd one."""
    return 2 if sc % 2 == 0 else 1


def pen_at(ox, oy, z, dy):
    PEN[:] = [z, ox, oy, dy]


def pen_x(v):
    return PEN[1] + (v - PEN[1]) * PEN[0]


def pen_y(v):
    return PEN[2] + (v - PEN[2]) * PEN[0]


def p_paint(r, x0, x1, c):
    ct.paint(r, pen_x(x0), pen_x(x1), c)


def p_rect(r, x0, y0, x1, y1, c):
    if pen_y(y0) <= PEN[3] < pen_y(y1):
        p_paint(r, x0, x1, c)


def p_frame(r, x0, y0, x1, y1, b, c):
    ct.frame(r, PEN[3], pen_x(x0), pen_y(y0), pen_x(x1), pen_y(y1), b * PEN[0], c)


def p_round(r, x0, y0, x1, y1, rad, c):
    """kit/pen.ci round (FF 3g): the 1x rectangle with corners of 1x radius rad, through kit/shape.ci's twin."""
    sh_rounded(r, PEN[3], pen_x(x0), pen_y(y0), pen_x(x1), pen_y(y1), rad * PEN[0], c)


def p_lower_round(r, x0, y0, x1, y1, rad, c):
    """kit/pen.ci lower_round (DN-36)."""
    sh_lower_rounded(r, PEN[3], pen_x(x0), pen_y(y0), pen_x(x1), pen_y(y1), rad * PEN[0], c)


def sh_focus_ring(row, y, x0, y0, x1, y1, r, u, ground, rc):
    """kit/shape.ci focus_ring (DN-40): a 2 px gap in ground, then a 2 px ring in rc, outside the control."""
    sh_ring(row, y, x0 - 4 * u, y0 - 4 * u, x1 + 4 * u, y1 + 4 * u, r + 4 * u, 2 * u, rc)
    sh_ring(row, y, x0 - 2 * u, y0 - 2 * u, x1 + 2 * u, y1 + 2 * u, r + 2 * u, 2 * u, ground)


def p_focus_ring(r, x0, y0, x1, y1, rad, ground, rc):
    """kit/pen.ci focus_ring (DN-40)."""
    sh_focus_ring(r, PEN[3], pen_x(x0), pen_y(y0), pen_x(x1), pen_y(y1), rad * PEN[0], PEN[0], ground, rc)


def p_ring(r, x0, y0, x1, y1, rad, t, c):
    """kit/pen.ci ring (FF 3g)."""
    sh_ring(r, PEN[3], pen_x(x0), pen_y(y0), pen_x(x1), pen_y(y1), rad * PEN[0], t * PEN[0], c)


def p_width(s, f):
    """kit/pen.ci width: s's width in role f at the zoom, in device pixels."""
    return tw.width(s, f, PEN[0])


def p_text(r, x0, base, x1, s, c, f):
    """kit/pen.ci text: s from 1x pen x0 on 1x baseline base, none past 1x x1; the device pen after."""
    return tw.text(r, PEN[3], pen_x(x0), pen_y(base), pen_x(x1), s, c, f, PEN[0])


def p_mid(r, x0, span, base, x1, s, c, f):
    """kit/pen.ci text_mid: s centered in the 1x span from x0 by its width at the zoom."""
    xd = pen_x(x0) + tdiv(span * PEN[0] - p_width(s, f), 2)
    return tw.text(r, PEN[3], xd, pen_y(base), pen_x(x1), s, c, f, PEN[0])


def p_right(r, x, base, s, c, f):
    """kit/pen.ci text_right: s ending at 1x x, by its width at the zoom."""
    xd = pen_x(x) - p_width(s, f)
    return tw.text(r, PEN[3], xd, pen_y(base), pen_x(x), s, c, f, PEN[0])


def p_text_dev(r, xd, base, s, c, f):
    """kit/pen.ci text_dev: s from device pen xd on 1x baseline base, none past its own width at the zoom."""
    return tw.text(r, PEN[3], xd, pen_y(base), xd + p_width(s, f), s, c, f, PEN[0])


def ptxt(r, x0, y0, x1, s, c, f):
    """hdesk.ci ptxt: txt through the pen, a 16 px slot's top y0."""
    return p_text(r, x0, y0 + TBASE, x1, s, c, f)


def spread_by(px, m):
    """Each pixel of px m wide (hdesk.ci expand_by)."""
    return [c for c in px for _ in range(m)]


BAR, B, OFFER_W, OFFER_H, EW, EH = 28, 1, 320, 200, 120, 40
TILED, FLOAT, MONOCLE, MINIMIZED = 0, 1, 2, 3
SIENNA, OCHRE = ct.WORDS[3], ct.WORDS[4]
T = ct.TOK                               # K-3: the theme's words by name (Gruvbox Dark until use_theme)


THEME = [0]                              # the theme use_theme last chose (tokens.theme(), the symbols' accents)


def use_theme(n):
    """K-3: the twins draw theme n (0 Gruvbox Dark, 1 Warm Paper) from now on."""
    global T, SIENNA, OCHRE
    ct.use_theme(n)
    T, SIENNA, OCHRE = ct.TOK, ct.WORDS[3], ct.WORDS[4]
    THEME[0] = n
EPOCH = 1767225600                       # 2026-01-01T00:00:00Z: the date of every gate flavor (A-3)


def day_text(t):
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return "%s %d" % (d.strftime("%a %b"), d.day)


def clock_text(t, h24=False):
    """K-6, RS-TZb: the bar's clock at t in UTC (a gate's image has no zone file), `Www Mmm D  H:MM AM` on 12 hours,
    `Www Mmm D  HH:MM` with 24-Hour Time (user/ci/kit/clocktext.ci bar)."""
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    hm = d.strftime("%H:%M") if h24 else "%d:%02d %s" % (d.hour % 12 or 12, d.minute, "AM" if d.hour < 12 else "PM")
    return "%s  %s" % (day_text(t), hm)


def month_of(y, m, t):
    """(first weekday 0 Sunday, days, today or 0) of month y-m, today being t's date."""
    first = (datetime.date(y, m, 1).weekday() + 1) % 7
    days = ((datetime.date(y + m // 12, m % 12 + 1, 1)) - datetime.date(y, m, 1)).days
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
    return first, days, d.day if (d.year, d.month) == (y, m) else 0


# ---- RS-CAL: the calendar under the bar's clock (user/ci/kit/calpop.ci, frame 44) ---------------------------------
# The kit's twin: its month, steps, hover and rows, stroke.ci's path_row for the chevrons. The screen check draws it
# where the desk opens it; --calpop-sums prints the sums tests/rs/calpop_twin_test.ci pins.
CP_W, CP_RAD, CP_SHADOW, CP_TOP, CP_SIDE, CP_BOTTOM, CP_GAP = 272, 12, 3, 14, 12, 12, 10
CP_HEAD, CP_WD_H, CP_BTN, CP_CELL_W, CP_CELL_H, CP_PITCH, CP_LINE = 24, 11, 24, 32, 28, 36, 30
CP_DIM = [0x6F6B62, 0x8A94A3]           # frame 44: the other months' days, dark and light
CP_CHEVRON = [[104, 32, 56, 80, 56, 80, 104, 128], [56, 32, 104, 80, 104, 80, 56, 128]]   # back, on: sixteenths
CP_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]


def am_z(sc):
    """hdesk.ci am_z: the kit's plates draw at 2 from UI scale 2 up, at 1 below."""
    return 2 if sc >= 2 else 1


def st_dev(o, v, num, den):
    """kit/stroke.ci dev: floor(o + v * num / (16 * den))."""
    return o + v * num // (16 * den)


def st_near(u, v, ax, ay, ex, ey, r2):
    """kit/stroke.ci near."""
    dx, dy, px, py = ex - ax, ey - ay, u - ax, v - ay
    l2, pr = dx * dx + dy * dy, px * dx + py * dy
    if l2 == 0 or pr <= 0:
        return px * px + py * py <= r2
    if pr >= l2:
        return (u - ex) ** 2 + (v - ey) ** 2 <= r2
    cr = px * dy - py * dx
    return cr * cr <= r2 * l2


def st_path_row(row, y, x0, y0, num, den, seg, w16, c):
    """kit/stroke.ci path_row: row y of the segments seg (four a segment, sixteenths of a unit, num / den device
    pixels a unit, from device point x0, y0) stroked w16 wide in c; 4 x 4 samples a pixel, each counted once."""
    h = w16 // 2 + 1
    segs = [seg[k:k + 4] for k in range(0, len(seg), 4)]
    live = [q for q in segs if st_dev(y0, min(q[1], q[3]) - h, num, den) <= y <= st_dev(y0, max(q[1], q[3]) + h,
                                                                                         num, den)]
    if not live:
        return
    lo = max(min(st_dev(x0, min(q[0], q[2]) - h, num, den) for q in live), 0)
    hi = min(max(st_dev(x0, max(q[0], q[2]) + h, num, den) + 1 for q in live), len(row), lo + 4096)
    if lo >= hi:
        return
    mk = [0] * (hi - lo)
    r = w16 * num
    r2 = r * r // 4
    for q in live:
        ax, ay, ex, ey = (v * num for v in q)
        for x in range(max(lo, st_dev(x0, min(q[0], q[2]) - h, num, den)),
                       min(hi, st_dev(x0, max(q[0], q[2]) + h, num, den) + 1)):
            for j in range(4):
                v = ((y - y0) * 8 + 2 * j + 1) * 2 * den
                for i in range(4):
                    if st_near(((x - x0) * 8 + 2 * i + 1) * 2 * den, v, ax, ay, ex, ey, r2):
                        mk[x - lo] |= 1 << (4 * j + i)
    for x in range(lo, hi):
        n = bin(mk[x - lo]).count("1")
        if n:
            row[x] = mix_px(row[x], c, n * 16)


def cp_base(y0, h, f, z):
    """calpop.ci mid_base: the baseline centering face f's line box in [y0, y0 + h) at zoom z, in device rows."""
    fa = tw.face(f, z)
    return y0 * z + (h * z - fa.ascent - fa.descent) // 2 + fa.ascent


def cp_centered(row, y, x0, w, base, s, c, f, z):
    """calpop.ci centered."""
    n = tw.width(s, f, z)
    x = x0 * z + (w * z - n) // 2
    tw.text(row, y, x, base, x + n, s, c, f, z)


class CalPop:
    """calpop.ci's state and functions: open on t's month, today being t's date in UTC (the gate's machine keeps no
    zone file, RS-TZc), the first column week, the plate's right edge xr and top yt (logical)."""

    def __init__(self, t, week, xr, yt):
        d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
        self.t, self.sy, self.sm, self.ws = t, d.year, d.month, week % 2
        self.ax, self.ay, self.hot = xr - CP_W, yt, -1

    def first(self):
        return month_of(self.sy, self.sm, self.t)[0]

    def days(self):
        return month_of(self.sy, self.sm, self.t)[1]

    def today(self):
        return month_of(self.sy, self.sm, self.t)[2]

    def lead(self):
        return (self.first() - self.ws + 7) % 7

    def weeks(self):
        return (self.lead() + self.days() + 6) // 7

    def height(self):
        return CP_TOP + CP_HEAD + CP_GAP + CP_WD_H + CP_GAP + CP_LINE * self.weeks() - 2 + CP_BOTTOM

    def step(self, d):
        k = self.sy * 12 + self.sm - 1 + d
        if k < 12 or k >= 10000 * 12:
            return False
        self.sy, self.sm = k // 12, k % 12 + 1
        return True

    def btn_x(self, b):
        return self.ax + CP_W - CP_SIDE - 4 - CP_BTN - (CP_BTN + 2) * (1 - b)

    def hover(self, px, py):
        h = next((b for b in range(2) if self.btn_x(b) <= px < self.btn_x(b) + CP_BTN and
                  self.ay + CP_TOP <= py < self.ay + CP_TOP + CP_BTN), -1)
        ch, self.hot = h != self.hot, h
        return ch

    def area(self, z, th):
        """area_left, area_top, area_right, area_bottom: the device box the plate and its shadow touch."""
        sd = sh_reach(CP_SHADOW, th, z, "side")
        return (self.ax * z - sd, self.ay * z - sh_reach(CP_SHADOW, th, z, "up"), (self.ax + CP_W) * z + sd,
                (self.ay + self.height()) * z + sh_reach(CP_SHADOW, th, z, "down"))

    def head_row(self, row, y, z):
        hy = self.ay + CP_TOP
        if not hy * z <= y < (hy + CP_HEAD) * z:
            return
        t = ("%s %d" % (CP_MONTHS[self.sm - 1], self.sy)).encode()
        tw.text(row, y, (self.ax + CP_SIDE + 8) * z, cp_base(hy, CP_HEAD, F_NAME_BOLD, z), self.btn_x(0) * z, t,
                T["INK"], F_NAME_BOLD, z)
        for b in range(2):
            bx = self.btn_x(b)
            if b == self.hot:
                sh_rounded(row, y, bx * z, hy * z, (bx + CP_BTN) * z, (hy + CP_BTN) * z, 6 * z, T["BAR_RULE"])
            st_path_row(row, y, (bx + 7) * z, (hy + 7) * z, z, 1, CP_CHEVRON[b], 24, T["INK"])

    def weekday_row(self, row, y, z):
        wy = self.ay + CP_TOP + CP_HEAD + CP_GAP
        if not wy * z <= y < (wy + CP_WD_H) * z:
            return
        base = cp_base(wy, CP_WD_H, F_LABEL, z)
        for c in range(7):
            d = (c + self.ws) % 7
            cp_centered(row, y, self.ax + CP_SIDE + CP_PITCH * c, CP_CELL_W, base, b"SMTWTFS"[d:d + 1], T["INK_DIM"],
                        F_LABEL, z)

    def week_row(self, row, y, th, z):
        gy = self.ay + CP_TOP + CP_HEAD + CP_GAP + CP_WD_H + CP_GAP
        if y < gy * z:
            return
        r = (y // z - gy) // CP_LINE
        cy = gy + CP_LINE * r
        if r >= self.weeks() or y >= (cy + CP_CELL_H) * z:
            return
        base = cp_base(cy, CP_CELL_H, F_PATH, z)
        lead, n, now = self.lead(), self.days(), self.today()
        pd = month_of(self.sy, self.sm - 1, self.t)[1] if self.sm > 1 else 31   # December's, before January
        for c in range(7):
            day = 7 * r + c - lead + 1
            v, fg = day, T["INK"]
            if day < 1:
                v, fg = pd + day, CP_DIM[th % 2]
            elif day > n:
                v, fg = day - n, CP_DIM[th % 2]
            cx = self.ax + CP_SIDE + CP_PITCH * c
            if now > 0 and day == now:
                sh_rounded(row, y, cx * z, cy * z, (cx + CP_CELL_W) * z, (cy + CP_CELL_H) * z, 14 * z, T["FILL"])
                fg = T["ON_FILL"]
            cp_centered(row, y, cx, CP_CELL_W, base, b"%d" % v, fg, F_PATH, z)

    def row_at(self, row, y, z, th):
        """calpop.ci row_at: device row y at zoom z on theme th, no ground: the shadow, plate, header, weekdays and
        weeks mixed over what row holds."""
        x0, y0, x1, y1 = self.ax * z, self.ay * z, (self.ax + CP_W) * z, (self.ay + self.height()) * z
        al, at, ar, ab = self.area(z, th)
        if not at <= y < ab:
            return
        shade_row(row, max(al, 0), min(ar, len(row)), y, x0, y0, x1, y1, CP_RAD, CP_SHADOW, th, z)
        if not y0 <= y < y1:
            return
        sh_rounded(row, y, x0, y0, x1, y1, CP_RAD * z, T["SURF2"])
        self.head_row(row, y, z)
        self.weekday_row(row, y, z)
        self.week_row(row, y, th, z)


# The frames tests/rs/calpop_twin_test.ci pins, FW x FH at 1x over the mantle, the plate's right edge 8 in and its top
# at 36: the gate's (January 2026 on its first day, from Sunday); November 9, 2026 from Monday (October's days lead,
# dim); stepped back to August 2026 (six weeks), the next chevron hovered; February 2026 (four weeks), the back one.
CP_FW, CP_FH = 304, 360
CP_NOV = 1794207540                     # 2026-11-09T06:59:00Z


def cp_frame_cal(name):
    if name == "gate":
        return CalPop(EPOCH, 0, CP_FW - 8, 36)
    if name == "monday":
        return CalPop(CP_NOV, 1, CP_FW - 8, 36)
    c = CalPop(CP_NOV if name == "august" else EPOCH, 0, CP_FW - 8, 36)
    if name == "august":
        for _ in range(3):
            c.step(-1)
        c.hover(c.ax + CP_W - 20, c.ay + 20)
    else:
        c.step(1)
        c.hover(c.btn_x(0) + 12, c.ay + 20)
    return c


CP_FRAMES = ["gate", "monday", "august", "february"]


def calpop_sums():
    """--calpop-sums: the sums tests/rs/calpop_twin_test.ci pins, each frame dark and light at 1x and 2x."""
    for name in CP_FRAMES:
        out = []
        for th in (0, 1):
            use_theme(th)
            for z in (1, 2):
                c, rows = cp_frame_cal(name), []
                for y in range(CP_FH * z):
                    row = [T["MANTLE"]] * (CP_FW * z)
                    c.row_at(row, y, z, th)
                    rows.append(row)
                out.append(dn_sum(rows))
        print(name, out)
    use_theme(0)
    return 0


def arrow_lists():
    """src/cursor.ci's two lists, the arrow's edge (paper) and body (ink), a byte a row, bit 7 the left pixel."""
    src = open(os.path.join(HERE, "..", "src", "cursor.ci")).read()
    out = []
    for name in ("edge", "body"):
        m = re.search(r"U8\[16\] %s = \[([^\]]*)\]" % name, src)
        out.append([int(v, 16) for v in m.group(1).replace(",", " ").split()])
    return out


EDGE, BODY = arrow_lists()


def arrow_at(i, j):
    """The arrow's pixel (i, j) at 1x: 0 none, 1 paper, 2 ink (src/cursor.ci's at)."""
    if not (0 <= i < 8 and 0 <= j < 16):
        return 0
    m = 0x80 >> i
    return 2 if BODY[j] & m else 1 if EDGE[j] & m else 0


def shape_lists():
    """src/cursor.ci's 24 x 24 shapes (DN-51 frame 26): edge24 and body24, 24 rows a shape from Text (2), bit 23 the
    left pixel."""
    src = open(os.path.join(HERE, "..", "src", "cursor.ci")).read()
    out = []
    for name in ("edge24", "body24"):
        m = re.search(r"U32\[192\] %s = \[([^\]]*)\]" % name, src)
        out.append([int(v, 16) for v in m.group(1).replace(",", " ").split()])
    return out


EDGE24, BODY24 = shape_lists()


def shape_box(k):
    """Shape k's width, height and hot spot (src/cursor.ci width, height, hot): the arrow 8 x 16 from its tip, the
    others 24 x 24 about their center."""
    return (8, 16, 0) if k <= 1 or k > 9 else (24, 24, 12)


def shape_at(k, i, j):
    """Shape k's pixel (i, j) at 1x: 0 none, 1 paper, 2 ink (src/cursor.ci shape_at)."""
    if k <= 1 or k > 9:
        return arrow_at(i, j)
    if not (0 <= i < 24 and 0 <= j < 24):
        return 0
    r, m = 24 * (k - 2) + j, 0x800000 >> i
    return 2 if BODY24[r] & m else 1 if EDGE24[r] & m else 0


def blocks(lines):
    """Each layout block: (desktop, focus, {i: (kind, desk, mode, rank, x, y, w, h, rects)}, screen w, h, the
    desktop's tiling direction), the screen the last `hdesk: screen` line's (HX-13 switches it)."""
    out = []
    sw, sh = ct.W, ct.H
    for k, l in enumerate(lines):
        ms = re.match(r"^hdesk: screen (\d+)x(\d+) plane", l)
        if ms:
            sw, sh = int(ms.group(1)), int(ms.group(2))
        m = re.match(r"^hdesk: layout desktop (\d+) focus (-?\d+)(?: dir (\d))?(?: scale (\d))?$", l)
        if not m:
            continue
        wins = {}
        for l2 in lines[k + 1:]:
            m2 = re.match(r"^hdesk: win (\d+) kind (\d+) desktop (\d+) mode (\d+) rank (\d+) frame (-?\d+),(-?\d+) "
                          r"(\d+)x(\d+) rects (-?\d+)(.*)$", l2)
            if not m2:
                break
            v = [int(g) for g in m2.groups()[:10]]
            rects = [tuple(int(t) for t in re.split(r"[,x]", r)) for r in m2.group(11).split()]
            wins[v[0]] = tuple(v[1:9]) + (rects if v[9] >= 0 else -1,)
        out.append((int(m.group(1)), int(m.group(2)), wins, sw, sh, int(m.group(3) or 0), int(m.group(4) or 1)))
    return out



def sw_frame(W, H, sc, n):
    """DN-6 frame 10 (hdesk.ci overlay): the switcher's plate for n windows: one row of 116 px tiles 8 apart, 16 in,
    as many as the screen holds 32 px from its edges, 148 high, centered on the plane."""
    k = min(n, max(1, (W // sc - 64 - 32 + 8) // (DN_SW_T + 8)))
    ow, oh = (32 + DN_SW_T * k + 8 * (k - 1)) * sc, DN_SW_H * sc
    return (W - ow) // 2, BAR * sc + (H - BAR * sc - oh) // 2, ow, oh


def switcher_frames(lines, bl):
    """The overlay's frame in each layout block while the switcher shows n windows, against sw_frame: (count, bad)."""
    k, n, count, bad = -1, None, 0, []
    for l in lines:
        if l.startswith("hdesk: layout desktop "):
            k += 1
        m = re.match(r"^hdesk: switcher \d+ of (\d+), window", l)
        if m:
            n = int(m.group(1))
        if re.match(r"^hdesk: switcher (chose|closed)", l):
            n = None
        if l.startswith("hdesk: win 15 ") and n is not None:
            d, f, wins, W, H, dr, sc = bl[k]
            count += 1
            if tuple(wins[15][4:8]) != sw_frame(W, H, sc, n):
                bad.append((l, sw_frame(W, H, sc, n)))
    return count, bad


def switcher(path):
    """--switcher TRANSCRIPT: K-1 on a boot straight into 1080 x 1920 where Super+Enter five times made six
    terminals (the old card was 1,216 px there), Alt+Ctrl+Tab opened the sticky switcher, Down moved a row to the
    first terminal and Enter chose it, and its shell ended: every layout block is the twin's and every switcher frame
    the card's, on the screen."""
    lines = gl.lines(open(path, encoding="utf-8", errors="replace").read())
    bl = blocks(lines)
    bad = [(d, i) for d, f, wins, bw, bh, dr, sc in bl for i, v in wins.items()
           if v[1] == d and v[2] != MINIMIZED and (v[4], v[5], v[6], v[7], v[8]) != twin(bw, bh, d, wins, dr, sc)[i]]
    count, sbad = switcher_frames(lines, bl)
    on = all(0 <= w[15][4] and w[15][4] + w[15][6] <= bw for d, f, w, bw, bh, *_ in bl if 15 in w)
    six = any(len([i for i in w if i < 15]) == 6 for d, f, w, *_ in bl)
    seq = [r"^hdesk: switcher sticky$", r"^hdesk: switcher 1 of 6, window 4$", r"^hdesk: switcher 5 of 6, window 0$",
           r"^hdesk: switcher chose 0 \(sticky\)$", r"^hdesk: shell ended, status 0$"]
    pos, miss = 0, None
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            miss = p
            break
        pos = hit + 1
    ok = bool(bl) and not bad and count > 0 and not sbad and on and six and miss is None and \
        "hdesk: screen 1080x1920 plane 1080x1892" in lines and lines[-1:] == ["daphnis: done"]
    print("%s  switcher: %d blocks the twin's; six terminals on 1080 x 1920; %d switcher frames DN-6's plate, on the "
          "screen; Down went to the last tile, the first terminal, chosen; its shell ended%s" % (
              "PASS" if ok else "FAIL", len(bl), count, "" if ok else ": bad %r, frames %r, on %r, six %r, missing %r"
              % (bad[:1], sbad[:1], on, six, miss)))
    return 0 if ok else 1


def twin(W, H, d, wins, dr, sc):
    L = cl.Layout(W, H, sc)
    L.dirs[d] = dr
    for i, (kind, dk, mode, rank, x, y, w, h, _) in wins.items():
        L.put(i, dk, mode, rank, x, y, w, h)
    L.compute(d)
    return {i: (L.win[i][3], L.win[i][4], L.win[i][5], L.win[i][6], [tuple(r) for r in L.rects[i]]
                if L.rects[i] != -1 else -1) for i in L.win}


cmark_at = cl.cmark_at


def roundel_px(n, x, y, ground):
    """AA-1: pixel (x, y) of user/ci/kit/roundel.ci's n x n Albers d roundel over ground, the mean of 8 x 8 samples."""
    m = 16 * n
    lw = ct.LOCKUP

    def disk(u, v, cx, cy, r):
        return (u - cx * m) ** 2 + (v - cy * m) ** 2 <= (r * m) ** 2

    acc = [0, 0, 0]
    for j in range(8):
        for i in range(8):
            u, v = (16 * x + 2 * i + 1) * 1000, (16 * y + 2 * j + 1) * 1000
            c = ground
            bowl, left = disk(u, v, 500, 560, 380), u < 500 * m
            if bowl and left:
                c = lw[2]
            if not left and (bowl or (u < 880 * m and 80 * m <= v < 560 * m)):
                c = lw[5]
            if left and disk(u, v, 500, 560, 180):
                c = lw[1]
            if not left and disk(u, v, 500, 560, 250):
                c = 0xF5F4F0
            if disk(u, v, 240, 200, 120):
                c = lw[4]
            acc = [acc[0] + (c >> 16 & 255), acc[1] + (c >> 8 & 255), acc[2] + (c & 255)]
    return (acc[0] // 64) << 16 | (acc[1] // 64) << 8 | acc[2] // 64


ROUNDEL = {}


def roundel(sc, ground):
    """The bar's mark at scale sc, 20 sc a side, as rows of words (kept, as hdesk keeps it)."""
    if (sc, ground) not in ROUNDEL:
        n = 20 * sc
        ROUNDEL[(sc, ground)] = [[roundel_px(n, x, y, ground) for x in range(n)] for y in range(n)]
    return ROUNDEL[(sc, ground)]


def tdiv(a, b):
    """cint's I64 division as cint 0.2.18 computes it: the quotient rounded toward minus infinity (-7 / 2 is -4,
    -8769 / 256 is -35), Python's //. FONT-2 A: the twin truncated toward zero before, which moved the chevron's
    turning frames 1 to 3 and 5 to 7 off the desk's (0, 4 and 8, the gate's screendumps, divide exactly)."""
    return a // b


def blend_step(v, w, a):
    """MS-1 (kit/blend.ci step): channel v toward w by a / 256, law 1's p - ((p - c) * a >> 8)."""
    return v - ((v - w) * a >> 8)


def mix_px(p, c, a):
    """MS-1 (kit/blend.ci mix_px): pixel p toward color c by a / 256, a clamped to 0..256, channel by channel."""
    a = max(0, min(256, a))
    return sum(blend_step(p >> sh & 255, c >> sh & 255, a) << sh for sh in (16, 8, 0))


def mix(row, x0, x1, c, a):
    """MS-1 (kit/blend.ci mix): the span [x0, x1) of row toward c by a / 256, cut to the row."""
    for x in range(max(0, x0), min(len(row), x1)):
        row[x] = mix_px(row[x], c, a)


def ease_tables():
    """MS-2: user/ci/kit/ease.ci's three curves as checked in, which must be what tools/ease.py makes."""
    with open(os.path.join(HERE, "..", "user", "ci", "kit", "ease.ci")) as f:
        body = f.read().split("= [", 1)[1].split("];", 1)[0]
    words = [int(v) for v in body.replace("\n", " ").split(",")]
    made = load("ease", "ease.py").tables()
    assert words == [v for c in made for v in c], "user/ci/kit/ease.ci is not what tools/ease.py makes"
    return [words[65 * k:65 * k + 65] for k in range(2)]


EASE = ease_tables()
ANIM_OUT, ANIM_IN = 0, 1
ANIM_MS, ANIM_STEP = 1000000, 10000000


def anim_progress(k, e, dur):
    """MS-2 (kit/anim.ci progress): curve k at e ns into dur, in thousandths, the line between two entries
    rounded down; every division here has a dividend of 0 or more, so // is cint's /."""
    if dur <= 0 or e >= dur:
        return 1000
    if e <= 0:
        return 0
    p = e * 64
    i = p // dur
    a, b = EASE[k][i], EASE[k][i + 1]
    return a + (b - a) * (p % dur) // dur


def anim_value(an, t):
    """MS-2 (kit/anim.ci value): an = (t0, dur, from, to, curve) at time t, rounded toward from."""
    t0, dur, v0, v1, k = an
    c = anim_progress(k, t - t0, dur)
    if v1 >= v0:
        return v0 + (v1 - v0) * c // 1000
    return v0 - (v0 - v1) * c // 1000


def anim_rest(v):
    """MS-2 (kit/anim.ci rest)."""
    return (0, 0, v, v, ANIM_OUT)


def anim_toward(an, t, to, dur, k, on):
    """MS-2 (kit/anim.ci toward): from where an stands at t; at to at once with animations off."""
    if not on or dur <= 0:
        return anim_rest(to)
    return (t, dur, anim_value(an, t), to, k)


PLATE_OPEN_MS, PLATE_CLOSE_MS, MSG_IN_MS, MSG_OUT_MS, MSG_DROP, PLATE_SHUT = 160, 100, 160, 200, 8, 960


def plate_open(an, t, on):
    """MS-5 (kit/plate.ci open)."""
    return anim_toward(an, t, 1000, PLATE_OPEN_MS * 1000000, ANIM_OUT, on)


def plate_close(an, t, on):
    """MS-5 (kit/plate.ci close)."""
    return anim_toward(an, t, 0, PLATE_CLOSE_MS * 1000000, ANIM_IN, on)


def plate_msg_in(an, t, on):
    """MS-5 (kit/plate.ci msg_in)."""
    return anim_toward(an, t, 1000, MSG_IN_MS * 1000000, ANIM_OUT, on)


def plate_msg_out(an, t, on):
    """MS-5 (kit/plate.ci msg_out)."""
    return anim_toward(an, t, 0, MSG_OUT_MS * 1000000, ANIM_IN, on)


def plate_move(an, t, on):
    """MS-8 (kit/plate.ci move)."""
    return anim_toward(an, t, 1000, 200 * 1000000, ANIM_OUT, on)


def plate_between(a, b, p):
    """MS-8 (kit/plate.ci between): rounded down, as cint's division floors."""
    return a + (b - a) * p // 1000


def plate_alpha(p):
    return (256 * p + 500) // 1000


def plate_scale(p):
    return PLATE_SHUT + ((1000 - PLATE_SHUT) * p + 500) // 1000


def plate_inset(n, p):
    return (n * (1000 - plate_scale(p)) + 1000) // 2000


def plate_radius(r, p):
    return (r * plate_scale(p) + 500) // 1000


def plate_drop(p, sc):
    """MS-5 (kit/plate.ci drop): toward its place (a non-negative quotient, floored as cint floors)."""
    return -((MSG_DROP * sc * (1000 - p)) // 1000)


def tw_cover16(x, y, x0, y0, x1, y1, r):
    """MS-5 (hdesk.ci cover16): the 4 x 4 samples of (x, y) inside the rounded rectangle, 0 to 16."""
    if not (x0 <= x < x1 and y0 <= y < y1):
        return 0
    px = x - x0 if x < x0 + r else x1 - 1 - x if x >= x1 - r else -1
    py = y - y0 if y < y0 + r else y1 - 1 - y if y >= y1 - r else -1
    if px < 0 or py < 0:
        return 16
    return sum(1 for s_ in range(4) for t in range(4)
               if (8 * r - (8 * px + 2 * s_ + 1)) ** 2 + (8 * r - (8 * py + 2 * t + 1)) ** 2 <= 64 * r * r)


def tw_cast_plate(row, W, x0, y0, x1, y1, r, lv, msg, drop_on, p, py, th, sc):
    """MS-5 (hdesk.ci cast_plate): an animating plate's shadow on row py, scaled (a message is not; coming in it drops)
    and mixed over what lay under it by the plate's opacity."""
    ps, d = (1000, plate_drop(p, sc) if drop_on else 0) if msg else (p, 0)
    ix, iy = plate_inset(x1 - x0, ps), plate_inset(y1 - y0, ps)
    fa = list(row)
    shade_row_dev(row, 0, W, py, x0 + ix, y0 + iy + d, x1 - ix, y1 - iy + d, plate_radius(r, ps), lv, th, sc)
    a = plate_alpha(p)
    for x in range(W):
        if row[x] != fa[x]:
            row[x] = mix_px(fa[x], row[x], a)


def tw_plate_mix(row, fb, x0, y0, x1, y1, r, ps, p, py):
    """MS-5 (hdesk.ci plate_mix): the plate drawn at full size, clipped to its scaled frame and mixed over fb."""
    if not y0 <= py < y1:
        return
    ix, iy, rr, a = plate_inset(x1 - x0, ps), plate_inset(y1 - y0, ps), plate_radius(r, ps), plate_alpha(p)
    for x in range(x0, x1):
        q = tw_cover16(x, py, x0 + ix, y0 + iy, x1 - ix, y1 - iy, rr)
        row[x] = mix_px(fb[x], row[x], (a * q + 8) // 16)


def tw_plate_row(row, W, py, sc, th, kind, closing, p, frame, draw):
    """MS-5 (hdesk.ci plate_row and ghost_row): the panel or the message on row py at progress p, opening (the message
    coming in, dropping) or closing (the record; the message fading); draw(row, y) draws the plate's row y at rest."""
    ox, oy, ow, oh = frame
    msg = kind == "msg"
    r, lv = (DN_MSG_H // 2 if msg else DN_RPLATE) * sc, 1 if msg else 3
    ps = 1000 if msg else p
    d = plate_drop(p, sc) if msg and not closing else 0
    if py < BAR * sc:
        return
    if not closing and p >= 1000:              # opened: no longer moving, so hdesk draws it at rest (cast_row, win_row)
        shade_row_dev(row, 0, W, py, ox, oy, ox + ow, oy + oh, r, lv, th, sc)
        if oy <= py < oy + oh:
            draw(row, py)
        return
    tw_cast_plate(row, W, ox, oy, ox + ow, oy + oh, r, lv, msg, msg and not closing, p, py, th, sc)
    if closing and not oy <= py < oy + oh:
        return
    fb = list(row)
    if oy <= py - d < oy + oh:
        draw(row, py - d)
    tw_plate_mix(row, fb, ox, oy + d, ox + ow, oy + oh + d, r, ps, p, py)


def anim_running(an, t):
    """MS-2 (kit/anim.ci running)."""
    return an[1] > 0 and t - an[0] < an[1]


TSIN91 = [0, 71, 143, 214, 286, 357, 428, 499, 570, 641, 711, 782, 852, 921, 991, 1060, 1129, 1198, 1266, 1334, 1401, 1468, 1534, 1600, 1666, 1731, 1796, 1860, 1923, 1986, 2048, 2110, 2171, 2231, 2290, 2349, 2408, 2465, 2522, 2578, 2633, 2687, 2741, 2793, 2845, 2896, 2946, 2996, 3044, 3091, 3138, 3183, 3228, 3271, 3314, 3355, 3396, 3435, 3474, 3511, 3547, 3582, 3617, 3650, 3681, 3712, 3742, 3770, 3798, 3824, 3849, 3873, 3896, 3917, 3937, 3956, 3974, 3991, 4006, 4021, 4034, 4046, 4056, 4065, 4074, 4080, 4086, 4090, 4094, 4095, 4096]   # DN-14: hdesk.ci tsin, sin of 0 to 90 degrees times 4096


def sin_d(a):
    return TSIN91[a] if a <= 90 else TSIN91[180 - a]


def cos_d(a):
    return TSIN91[90 - a] if a <= 90 else -TSIN91[a - 90]

def shadow_tables():
    """MS-3, MS-3b: user/ci/kit/shadow.ci's arrays as checked in (check.sh's tools/shadow.py --check holds them to the
    tool): lay, cu, fu, po, pf, to, tv, ca, the factors made and the bounds of fits."""
    import re as _re
    with open(os.path.join(HERE, "..", "user", "ci", "kit", "shadow.ci")) as f:
        text = f.read()
    arr = {m.group(1): [int(v) for v in m.group(2).replace("\n", " ").split(",")]
           for m in _re.finditer(r"^(?:I64|U8)\[\d+\] (\w+) = \[(.*?)\];", text, _re.S | _re.M)}
    s0, s1, _ = (int(v) for v in _re.search(r"if \(s >= (\d+) && s <= (\d+)\) \{ return s - (\d+); \}", text).groups())
    mc, box = (int(v) for v in _re.search(r"\(rad \+ (\d+)\) \* sc <= (\d+);", text).groups())
    frac = int(_re.search(r"\) << (\d+)\) - r \* \d+;", text).group(1))
    return arr, list(range(s0, s1 + 1)), mc, box, frac


SH, SH_SCALES, SH_MAXCUT, SH_BOX, SH_SHIFT = shadow_tables()
SH_ONE = 1 << ((SH_SHIFT + 2) // 2)
SHADOW_DARK, SHADOW_LIGHT = 0x000000, 0x141413


def sh_fits(rad, sc):
    """MS-3b (kit/shadow.ci fits)."""
    return sc in SH_SCALES and rad >= 1 and (rad + SH_MAXCUT) * sc <= SH_BOX


def sh_fits_dev(r, sc):
    """MS-5 (kit/shadow.ci fits_dev)."""
    return sc in SH_SCALES and r >= 1 and r + SH_MAXCUT * sc <= SH_BOX


def sh_dy(lv, k):
    return SH["lay"][4 * (lv - 1) + 2 * k]


def sh_cut(lv, th, k):
    """MS-3 (kit/shadow.ci cut)."""
    return SH["cu"][4 * (lv - 1) + 2 * th + k]


def sh_edge(si, lv, th, k, b, d):
    """MS-3 (kit/shadow.ci edge)."""
    if d > b:
        return 0
    return SH["pf"][SH["po"][4 * (3 * si + lv - 1) + 2 * th + k] + max(d, -b - 1) + b + 1]


def sh_corner(si, r, lv, th, k, n, i, j):
    """MS-3b (kit/shadow.ci corner): contact by cut_corners' 4 x 4 samples, ambient by the thresholds its distance
    to the arc lies within."""
    if i < 0 or j < 0 or i >= n or j >= n:
        return 0
    if k == 0:
        q = sum(1 for x in range(4) for y in range(4)
                if (8 * i + 2 * x + 1) ** 2 + (8 * j + 2 * y + 1) ** 2 <= 64 * r * r)
        return SH["ca"][17 * (2 * (lv - 1) + th) + q]
    s, c = si + SH_SCALES[0], sh_cut(lv, th, 1)
    p = isqrt(((2 * i + 1) ** 2 + (2 * j + 1) ** 2) << SH_SHIFT) - r * SH_ONE
    if 2 * p > (2 * c * s - 1) * SH_ONE:
        return 0
    if 2 * p < -(2 * c * s + 1) * SH_ONE:
        return SH["fu"][4 * (lv - 1) + 2 * th + 1]
    t = 2 * (3 * si + lv - 1) + th
    lo, hi = SH["to"][t], SH["to"][t + 1]
    base = lo
    while lo < hi:
        mid = (lo + hi) // 2
        if p <= SH["tv"][mid]:
            lo = mid + 1
        else:
            hi = mid
    return lo - base


def sh_layer_at(si, lv, th, k, r, b, x, y, sx0, sy0, sx1, sy1):
    """MS-3 (kit/shade.ci layer_at)."""
    i = sx0 + r - 1 - x if x < sx0 + r else x - (sx1 - r) if x >= sx1 - r else -1
    j = sy0 + r - 1 - y if y < sy0 + r else y - (sy1 - r) if y >= sy1 - r else -1
    if i >= 0 and j >= 0:
        return sh_corner(si, r, lv, th, k, r + b, i, j)
    if i < 0 and j < 0:
        return sh_edge(si, lv, th, k, b, -b - 1)
    if i < 0:
        return sh_edge(si, lv, th, k, b, sy0 - y if y < sy0 + r else y - (sy1 - 1))
    return sh_edge(si, lv, th, k, b, sx0 - x if x < sx0 + r else x - (sx1 - 1))


def shade_row(row, lo, hi, y, x0, y0, x1, y1, rad, lv, th, sc):
    """MS-3 (kit/shade.ci shade_row): level lv's shadow of the shape [x0, x1) x [y0, y1), corner radius rad at 1x,
    theme th, UI scale sc, on screen row y over [lo, hi): contact then ambient, each through mix_px; the shape's
    inside is left as it is except under its corners."""
    if not sh_fits(rad, sc):
        return
    shade_row_dev(row, lo, hi, y, x0, y0, x1, y1, rad * sc, lv, th, sc)


def shade_row_dev(row, lo, hi, y, x0, y0, x1, y1, r, lv, th, sc):
    """MS-5 (kit/shade.ci shade_row_dev): shade_row for a corner radius of r device pixels."""
    if not sh_fits_dev(r, sc) or not 1 <= lv <= 3:
        return
    si = SH_SCALES.index(sc)
    if x1 - x0 < 2 * r or y1 - y0 < 2 * r:
        return
    c = SHADOW_LIGHT if th == 1 else SHADOW_DARK
    in_rows, corner_rows = y0 <= y < y1, y < y0 + r or y >= y1 - r
    for k in range(2):
        dy, b = sh_dy(lv, k) * sc, sh_cut(lv, th, k) * sc
        sy0, sy1 = y0 + dy, y1 + dy
        if not sy0 - b <= y < sy1 + b:
            continue
        for x in range(max(x0 - b, lo, 0), min(x1 + b, hi, len(row))):
            if in_rows and x0 <= x < x1 and not (corner_rows and (x < x0 + r or x >= x1 - r)):
                continue
            a = sh_layer_at(si, lv, th, k, r, b, x, y, x0, sy0, x1, sy1)
            if a > 0:
                row[x] = mix_px(row[x], c, a)


TCOS = [256, 237, 181, 98, 0, -98, -181, -237, -256]
TSIN = [0, 98, 181, 237, 256, 237, 181, 98, 0]


def seg_d2(u, v, ax, ay, ex, ey):
    dx, dy = ex - ax, ey - ay
    l2, t = dx * dx + dy * dy, (u - ax) * dx + (v - ay) * dy
    if t <= 0:
        return (u - ax) ** 2 + (v - ay) ** 2
    if t >= l2:
        return (u - ex) ** 2 + (v - ey) ** 2
    return (u - ax) ** 2 + (v - ay) ** 2 - tdiv(t * t, l2)


def chevron(r1, y, cx, cy, a, ink=None):
    """DN-14 (hdesk.ci chevron): the tray's chevron turned a degrees about (cx, cy), M2.5 4.25 L6 7.75 L9.5 4.25 of a
    12 px box stroked 1.75 px with round ends, 4 x 4 samples a pixel, ink over the row by coverage, at the pen's
    zoom z (each device pixel sampled in eighths of a device pixel)."""
    if not cy - 6 <= y < cy + 6:
        return
    z, dy = PEN[0], PEN[3]
    ink = ct.INK if ink is None else ink
    ox, oy = pen_x(cx), pen_y(cy)
    c, s_ = cos_d(a), sin_d(a)
    for px in range(pen_x(cx - 6), pen_x(cx + 6)):
        cov = 0
        for s in range(4):
            for t in range(4):
                x8, y8 = 8 * (px - ox) + 2 * s + 1, 8 * (dy - oy) + 2 * t + 1
                u, v = tdiv(x8 * c + y8 * s_, 4096), tdiv(y8 * c - x8 * s_, 4096)
                if seg_d2(u, v, -28 * z, -14 * z, 0, 14 * z) <= 49 * z * z or \
                        seg_d2(u, v, 28 * z, -14 * z, 0, 14 * z) <= 49 * z * z:
                    cov += 1
        if cov:
            r1[px] = sum(((cov * (ink >> 8 * ch & 255) + (16 - cov) * (r1[px] >> 8 * ch & 255) + 8) // 16) << 8 * ch
                         for ch in range(3))


def bar_1x(r1, y, W1, d, occupied, pips, title, var, disk, net, clk, cal, kern=b"", panel=False, tray=(0, 0, False),
           z=1, dy=None, strip=False, bare=False):
    """K-5: bar row y at 1x (hdesk.ci bar_row): the color mark, the App pill and the variable, the desktops and their
    grant pips, the clock (filled while the calendar is open); DN-72: no grant pill, so disk, net and kern draw
    nothing (the callers pass the log's counts); WB-7: no rules, slots the bar's
    full height, this desktop filled, one with windows a 2 x 2 dot. FONT-2 A: drawn at zoom z on device row dy (y at
    1), into r1 W1 * z wide."""
    pen_at(0, 0, z, y if dy is None else dy)
    p_paint(r1, 0, W1, T["BAR"])

    def pill(x0, pw, t, bg, fg, f):
        if bg is not None:                  # WB-7: a slot fills the bar's height; none has a frame
            p_paint(r1, x0, x0 + pw, bg)
        p_mid(r1, x0, pw, 6 + TBASE, x0 + pw, t, fg, f)   # centered in the slot, cut at its end (FONT-2 A)
    if bare:                                # DN-41 (a): login, lock, first boot: the clock alone (and the roundel)
        cw = 8 * len(clk) + 16
        pill(W1 - 8 - cw, cw, clk, None, ct.INK, F_PATH)
        return

    x0 = (W1 - 9 * 24) // 2
    if title:
        aw = txt_w(title, F_NAME) + 16    # l 11-08 14:42Z: the title alone, no icon, no chevron
        pill(44, aw, title, None, ct.INK, F_NAME)
        ptxt(r1, 44 + aw + 12, 6, x0 - 8, var, T["INK_DIM"], F_PATH)
    for dd in range(1, 10):
        if not strip:                    # FF 3g: the desktop strip shows only with the plane open or after a switch
            break
        dx = x0 + (dd - 1) * 24
        if dd == d:
            p_round(r1, dx + 1, 4, dx + 23, 24, 10, T["FILL"])   # FF 3g: this desktop, a pill
        elif dd in occupied:
            p_rect(r1, dx + 11, 24, dx + 13, 26, ct.INK)
        dg = b"%d" % dd                  # the digit centered in its 24 px cell
        p_mid(r1, dx, 24, 6 + TBASE, dx + 24, dg, T["ON_FILL"] if dd == d else ct.INK, F_NAME)
        g = pips.get(dd, 0)
        gc = T["CADMIUM"] if g & 8 else OCHRE if g & 1 else SIENNA if g & 2 else None   # R0-3: ring 0 cadmium; WB-5
        if gc is not None:
            p_rect(r1, dx + 18, 4, dx + 22, 8, gc)
    cw = 8 * len(clk) + 16               # FONT-1: the slots right of the desktops keep the 8 x 16 face's spans
    cx = W1 - 8 - cw
    spx = cx - 32                        # SP-1: the four squares' 24 px slot, left of the clock
    nt, turn, topen = tray
    tx = spx - 32                        # DN-14: the chevron's 24 px slot, 8 px left of the panel's, always shown
    if panel:
        p_paint(r1, spx, spx + 24, T["BAR_SLOT"])
    p_rect(r1, spx + 5, 7, spx + 11, 13, ct.ULTRAMARINE)
    p_rect(r1, spx + 13, 7, spx + 19, 13, SIENNA)
    p_rect(r1, spx + 5, 15, spx + 11, 21, OCHRE)
    p_rect(r1, spx + 13, 15, spx + 19, 21, T["CADMIUM"])
    if topen:
        p_round(r1, tx, 4, tx + 24, 24, R_CTRL, T["BAR_SLOT"])
    chevron(r1, y, tx + 12, 14, turn, ct.INK if nt > 0 else mix_px(T["BAR"], T["INK_DIM"], 128))
    if cal:                              # frame 44: the open calendar's clock on a pill 22 high, radius 11
        p_round(r1, cx, 3, cx + cw, 25, 11, T["BAR_SLOT"])
    pill(cx, cw, clk, None, ct.INK, F_PATH)


SP_W, SP_H, TR_W = 360, 368, 360


def sp_text(r1, y, x, ty, t, c, f, right=False):
    """hdesk.ci sp_text: t in role f at (x, ty), right aligned to x when right; FONT-2 A: through the pen, measured
    at its zoom."""
    if right:
        p_right(r1, x, ty + TBASE, t, c, f)
    else:
        p_text_dev(r1, pen_x(x), ty + TBASE, t, c, f)


def sp_mid(r1, y, x, span, ty, t, c, f):
    """hdesk.ci sp_mid: the same centered in the span px from x."""
    p_mid(r1, x, span, ty + TBASE, x + span, t, c, f)


def sp_track(r1, y, cy, lv):
    if lv < 0:
        if cy + 30 <= y < cy + 34:
            for k in range(40):
                p_paint(r1, 20 + 8 * k, 24 + 8 * k, T["RULE"])
        return
    at = 20 + 320 * lv // 100
    if cy + 30 <= y < cy + 36:
        p_paint(r1, 20, at, ct.ULTRAMARINE)
        p_paint(r1, at, 340, T["RULE"])
    if cy + 26 <= y < cy + 40:
        p_paint(r1, at - 3, at + 3, ct.INK)


def card(r1, y, x0, y0, x1, y1, c):
    """A panel's card (FF 3g: radius RAD)."""
    if y0 <= y < y1:
        p_round(r1, x0, y0, x1, y1, RAD, c)


def panel_row(r1, y, p, z=1, dy=None):
    """SP-1 (hdesk.ci panel_row): the system panel's row y at 1x, its frame at 0,0; p is the last `hdesk: panel
    audio` line's (audio, level, player, comm, net, animations). FONT-2 A: at zoom z on device row dy (y at 1)."""
    pen_at(0, 0, z, y if dy is None else dy)
    au, lv, vp, comm, net, an = p
    p_frame(r1, 0, 0, SP_W, SP_H, 1, ct.ULTRAMARINE)
    dim, ink = T["INK_DIM"], ct.INK
    if 12 <= y < 28:
        sp_text(r1, y, 12, 12, b"SYSTEM PANEL", ink, F_LABEL)
        sp_text(r1, y, SP_W - 12, 12, b"Settings >", ct.ULTRAMARINE, F_BODY, True)
    elif 40 <= y < 104:
        for c, (name, link) in enumerate(((b"Wi-Fi", b"Wi-Fi Settings >"), (b"Bluetooth", b"BT Settings >"))):
            cx = 8 + 176 * c
            p_round(r1, cx, 40, cx + 168, 104, RAD, T["SURF1"])
            p_ring(r1, cx + 120, 44, cx + 160, 64, R_CTRL, 1, T["RULE"])
            sp_mid(r1, y, cx + 120, 40, 46, b"N/A", dim, F_BODY)
            sp_text(r1, y, cx + 10, 46, name, dim, F_BODY)
            sp_text(r1, y, cx + 10, 82, link, dim, F_BODY)
            sp_text(r1, y, cx + 10, 64, b"no driver", dim, F_BODY)
    elif 112 <= y < 144:
        card(r1, y, 8, 112, SP_W - 8, 144, T["SURF1"])
        sp_text(r1, y, 18, 120, b"NETWORK", dim, F_LABEL)
        sp_text(r1, y, SP_W - 18, 120, b"wired  10.0.2.15" if net else b"N/A", ink if net else dim,
                F_PATH if net else F_BODY, True)
    elif 152 <= y < 208:
        card(r1, y, 8, 152, SP_W - 8, 208, T["SURF1"])
        if not au:
            sp_text(r1, y, 18, 158, b"NOW PLAYING", dim, F_LABEL)
            sp_text(r1, y, SP_W - 18, 158, b"N/A", dim, F_BODY, True)
            sp_text(r1, y, 18, 180, b"no audio device", dim, F_BODY)
        else:
            sp_text(r1, y, 18, 158, b"NOW PLAYING", dim, F_LABEL)
            p_text_dev(r1, pen_x(18) + p_width(b"NOW PLAYING  ", F_LABEL), 158 + TBASE, b"AU-6 PCM 48 kHz", dim, F_BODY)
            if vp == 0:
                sp_text(r1, y, 18, 180, b"Nothing playing", dim, F_BODY)
            else:
                sp_text(r1, y, 18, 180, comm, ink, F_NAME)
                sp_text(r1, y, SP_W - 18, 180, b"pid %d" % vp, dim, F_PATH, True)
    elif 216 <= y < 264:
        card(r1, y, 8, 216, SP_W - 8, 264, T["SURF1"])
        if not au:
            sp_text(r1, y, 18, 222, b"SOUND VOLUME", dim, F_LABEL)
            sp_text(r1, y, SP_W - 18, 222, b"N/A", dim, F_BODY, True)
            sp_track(r1, y, 216, -1)
        else:
            sp_text(r1, y, 18, 222, b"SOUND VOLUME", ink, F_LABEL)
            sp_text(r1, y, SP_W - 18, 222, b"%d%%" % lv, ink, F_PATH, True)
            sp_track(r1, y, 216, lv)
    elif 272 <= y < 320:
        card(r1, y, 8, 272, SP_W - 8, 320, T["SURF1"])
        sp_text(r1, y, 18, 278, b"SCREEN BRIGHTNESS", dim, F_LABEL)
        sp_text(r1, y, SP_W - 18, 278, b"N/A", dim, F_BODY, True)
        sp_track(r1, y, 272, -1)
    elif 328 <= y < 360:
        card(r1, y, 8, 328, SP_W - 8, 360, T["SURF1"])
        sp_text(r1, y, 18, 336, b"UI ANIMATIONS", ink, F_LABEL)
        if an:
            p_round(r1, SP_W - 58, 334, SP_W - 18, 354, R_CTRL, T["FILL"])
            sp_mid(r1, y, SP_W - 58, 40, 336, b"ON", T["ON_FILL"], F_BODY)
        else:
            p_round(r1, SP_W - 58, 334, SP_W - 18, 354, R_CTRL, T["SURF2"])
            p_ring(r1, SP_W - 58, 334, SP_W - 18, 354, R_CTRL, 1, T["RULE"])
            sp_mid(r1, y, SP_W - 58, 40, 336, b"OFF", ink, F_BODY)


def dn_tray_at_row(row, x0, y0, icons, sel, hov, y):
    """DN-15 (hdesk.ci tray_at_row): the tray's plate at 1x, a 16 px icon centered a 32 px cell, 5 across from 4 px
    in; the keyboard's cell FILL, the pointer's SURF1, radius 6."""
    for k, ic in enumerate(icons):
        cx, cy = x0 + 4 + 32 * (k % 5), y0 + 4 + 32 * (k // 5)
        if cy <= y < cy + 32:
            g = "FILL" if k == sel else "SURF1" if k == hov else "SURF2"
            if g != "SURF2":
                p_round(row, cx, cy, cx + 32, cy + 32, R_CTRL, T[g])
            if cy + 8 <= y < cy + 24:
                iw.icon_at(row, PEN[3], pen_x(cx + 8), pen_y(cy + 8), ic, 16, PEN[0], T[g])


def dn_tray_pw(n):
    return 8 + 32 * min(max(n, 1), 5)


def dn_tray_ph(n):
    return 8 + 32 * ((max(n, 1) + 4) // 5)


RAD = 8                                  # FF 3g: hdesk.ci RAD, 7 became 8
R_CTRL = 6


def round_corners(row, under, py, x0, y0, x1, y1, e, sc):
    """WB-7 (hdesk.ci cut_corners): a popover's four corners on screen row py, a quarter circle of radius RAD * sc
    with a 1 px outline e, each corner pixel 4 x 4 samples mixed from under, the outline and the inside."""
    r, b = RAD * sc, sc
    if not (y0 <= py < y0 + r or y1 - r <= py < y1):
        return
    qy = py - y0 if py < y0 + r else y1 - 1 - py
    for px in range(r):
        nu = no = 0
        for s in range(4):
            for t in range(4):
                dx, dy = 8 * r - (8 * px + 2 * s + 1), 8 * r - (8 * qy + 2 * t + 1)
                d2 = dx * dx + dy * dy
                if d2 > 64 * r * r:
                    nu += 1
                elif d2 > 64 * (r - b) * (r - b):
                    no += 1
        ni = 16 - nu - no
        for x in (x0 + px, x1 - 1 - px):
            row[x] = sum(((nu * (under[x] >> 8 * ch & 255) + no * (e >> 8 * ch & 255) + ni * (row[x] >> 8 * ch & 255)
                           + 8) // 16) << 8 * ch for ch in range(3))


def screen_of(text, lines, bl, W, H, mo=None, rows_out=None):
    """The final screen as the Python composes it: the bar, the first window alone (its frame, grant ring and
    terminal rows at the UI scale) and the arrow on top where `hdesk: pointer` says; (ok, digest, the kernel's).
    MS-9a: mo, a frame in motion on the stepped clock (motion_check): "plate" (kind "panel" or "msg", p, closing,
    frame, text), "frame0" (window 0's frame of the moment, MS-8), "term" and "pointer" as the plan says. rows_out,
    a list, takes the composed rows."""
    mo = mo or {}
    rows = {}
    for l in lines:
        m = re.match(r"^hdesk: term (\d\d) \|(.*)\|$", l)
        if m:
            rows[int(m.group(1))] = m.group(2)
    cur = re.findall(r"^hdesk: cursor (\d+),(\d+)$", text, re.M)
    if "term" in mo:                     # MS-9a: a screen in mid run: the terminal and its cursor as the plan says
        rows, cur = mo["term"][0], [mo["term"][1]]
    bars = re.findall(r"^hdesk: bar desktop (\d+) \|(.*)\| var \|(.*)\| grants \|(.*)\|$", text, re.M)
    clk = clock_text(EPOCH).encode("ascii")
    cal = None                           # the month the calendar shows at the end, when it is open
    for l in lines:
        mc = re.match(r"^hdesk: calendar (\d+)-(\d\d) ", l)
        if mc:
            cal = (int(mc.group(1)), int(mc.group(2)))
        if l == "hdesk: calendar closed":
            cal = None
    panel, pline, tray, trows, topen = False, None, (0, 0, False), [], False
    ticons, tsel, thov = {}, -1, -1      # DN-15: the plate's icons, keyboard cell and pointer cell
    pgrants, pend = [], []               # DN-6 frame 9: the panel's grant rows as its last read listed them
    for l in lines:                      # SP-1, SP-2: the panel and the tray as the desk left them
        mg = re.match(r"^hdesk: panel grant (\d+) window \d+ bit (\d+) \|(.*)\|$", l)
        if mg:
            pend = ([] if mg.group(1) == "0" else pend) + [(int(mg.group(2)), mg.group(3).encode("utf-8"))]
        if l in ("hdesk: panel open", "hdesk: panel closed"):
            panel = l.endswith("open")
        mp = re.match(r"^hdesk: panel audio ([01]) level (\d+) player (\d+) \|(.*)\| streams \d+ net ([01]) animations "
                      r"([01])$", l)
        if mp:
            pgrants, pend = pend, []
            pline = (mp.group(1) == "1", int(mp.group(2)), int(mp.group(3)), mp.group(4).encode("utf-8"),
                     mp.group(5) == "1", mp.group(6) == "1")
        mt = re.match(r"^hdesk: tray bar (\d+) turn (\d+) open ([01])$", l)
        if mt:
            tray = (int(mt.group(1)), int(mt.group(2)), mt.group(3) == "1")
        if re.match(r"^hdesk: tray open \d+$", l):
            topen, trows, ticons, tsel, thov = True, [], {}, -1, -1
        mi = re.match(r"^hdesk: tray icon (\d+) (\d+)$", l)
        if mi:
            ticons[int(mi.group(1))] = int(mi.group(2))
        ms_ = re.match(r"^hdesk: tray (sel|hover) (-?\d+)$", l)
        if ms_:
            if ms_.group(1) == "sel":
                tsel = int(ms_.group(2))
            else:
                thov = int(ms_.group(2))
        if l == "hdesk: tray closed" or re.match(r"^hdesk: tray opened \d+$", l):
            topen = False
        mr = re.match(r"^hdesk: tray row \d+ window \d+ ring (\d) \|(.*)\|$", l)
        if mr:
            trows.append((int(mr.group(1)), mr.group(2).encode("utf-8")))
    th = re.findall(r"^hdesk: theme ([01])$", text, re.M)
    use_theme(int(th[-1]) if th else 0)                 # K-3: the theme the desk last switched to
    grant = {}
    for gi, gv in re.findall(r"^hdesk: grant (\d+) (\d+)$", text, re.M):
        grant[int(gi)] = int(gv)
    d, f, wins, W, H, _, sc = bl[-1] if bl else (1, -1, {}, W, H, 0, 1)
    az = am_z(sc)
    if cal is not None:                  # RS-CAL (hdesk.ci cal_show_now): the plate's right edge 8 in from the screen's,
        ym = cal                         # its top 8 under the bar, from Sunday; the gate's pointer does not move while
        cal = CalPop(EPOCH, 0, (W - 8 * sc) // az, (BAR + 8) * sc // az)   # it is open, so no chevron is hovered
        cal.sy, cal.sm = ym
    pt = re.findall(r"^hdesk: pointer (\d+),(\d+) shown ([01])$", text, re.M)
    mx, my, shown = (int(pt[-1][0]), int(pt[-1][1]), pt[-1][2] == "1") if pt else (0, 0, False)
    if "pointer" in mo:                  # MS-9a: the pointer where the plan says, in mid run
        mx, my, shown = mo["pointer"]
    shp = re.findall(r"^hdesk: shape (\d+)$", text, re.M)    # DN-51 frame 26: the shape the desk last sent
    pk = int(shp[-1]) if shp else 1
    pw, ph, hot = shape_box(pk)
    at_size = r"^daphnis: surface %dx%d stride %d sha256 ([0-9a-f]{64})$" % (W, H, 4 * W)
    screen = bytearray()
    ok = bool(cur and bars and 0 in wins)
    if ok:
        cx, cy = int(cur[-1][0]), int(cur[-1][1])
        title, var = bars[-1][1].encode("utf-8"), bars[-1][2].encode("utf-8")
        counts = dict((k, int(v)) for k, v in re.findall(r"(DISK|NET) (\d+)", bars[-1][3]))
        kt = re.findall(r"KERN \d+(?: \S+)?", bars[-1][3])
        kern = kt[0].encode("utf-8") if kt else b""
        pips = {}
        for i, v in wins.items():
            pips[v[1]] = pips.get(v[1], 0) | grant.get(i, 0)
        g0 = grant.get(0, 0)
        gcol = T["CADMIUM"] if g0 & 8 else OCHRE if g0 & 1 else SIENNA if g0 & 2 else None   # R0-3: ring 0 first
        occupied = {v[1] for v in wins.values()}
        kind, dk, mode, rank, x, y, w, h, rects = wins[0]
        bs, W1 = B * sc, W // sc
        tp = TPAD * sc
        tc, tr = min((w - 2 * bs - 2 * tp) // (8 * sc), 480), min((h - 2 * bs - 2 * tp) // (16 * sc), 135)
        z = 2 if sc % 2 == 0 else 1       # K-2: the 16 x 32 drawing at an even scale, spread to sc / 2
        trow = ct.term_rows([rows.get(r, "") for r in range(tr)], tc, tr, cx, cy, z)
        if mode == FLOAT:                 # MS-9a: a floated window 0's terminal, sized by its frame at rest
            ftc = min((w - 2 * DN_FB * sc - 2 * tp) // (8 * sc), 480)
            ftr = min((h - 2 * DN_FB * sc - DN_WBAR * sc - 2 * tp) // (16 * sc), 135)
            ftrow = ct.term_rows([rows.get(r, "") for r in range(ftr)], ftc, ftr, cx, cy, z)

        # K-7: the emblem, centered on the plane, computed only outside the frames of the desktop's shown windows;
        # K-3 (D-4): on an empty desktop only
        e = min((480 if H > W else 440) * sc, W, H - BAR * sc)
        ex, ey = (W - e) // 2, BAR * sc + (H - BAR * sc - e) // 2
        cover = [v[4:8] for v in wins.values() if v[1] == d and v[2] != MINIMIZED]
        empty = not any(i < 15 and v[1] == d and v[2] != MINIMIZED for i, v in wins.items())

        def em_spans(py):
            if not empty or not ey <= py < ey + e:
                return []
            out, q = [], ex
            while q < ex + e:
                past = max([fx + fw for fx, fy, fw, fh in cover if fy <= py < fy + fh and fx <= q < fx + fw] + [q])
                if past > q:
                    q = past
                    continue
                q1 = q + 1
                while q1 < ex + e and not any(fy <= py < fy + fh and fx <= q1 < fx + fw for fx, fy, fw, fh in cover):
                    q1 += 1
                out.append((q, q1))
                q = q1
            return out

        cz = zoom(sc)                     # FONT-2 A: the chrome drawn at cz, spread by m (1 at 2x: native)
        m = sc // cz

        def spread(px, n):
            """n pixels at the zoom, each m wide."""
            return spread_by(px[:n * cz], m)

        thn = int(th[-1]) if th else 0

        def plane_row(py):
            """The plane's row py: the emblem on an empty desktop, then window 0 (MS-9a: floated, at its frame of the
            moment while it moves, MS-8)."""
            row = [T["MANTLE"]] * W
            for ex0, ex1 in em_spans(py):
                for q in range(ex0, ex1):
                    c = cmark_at(e, q - ex, py - ey)
                    if c is not None:
                        row[q] = c
            if mode == FLOAT and not (x == 0 and x + w == W):   # MS-9a: window 0 floated (hdesk.ci cast_row, win_row)
                fx_, fy_, fw_, fh_ = mo.get("frame0", (x, y, w, h))
                lit, r_ = f == 0, DN_RAD * sc
                if py >= BAR * sc:
                    shade_row(row, 0, W, py, fx_, fy_, fx_ + fw_, fy_ + fh_, DN_RAD, 2 if lit else 1, thn, sc)
                if fy_ <= py < fy_ + fh_:
                    fb_ = list(row)
                    rnd = py < fy_ + r_ or py >= fy_ + fh_ - r_
                    if rnd:
                        dn_keep_at(row, fx_, fx_ + fw_, r_)
                    ct.paint(row, fx_, fx_ + fw_, ct.TERM_PAPER)
                    dn_float_row(row, fx_, fy_, fx_ + fw_, fy_ + fh_, sc, lit, "ULTRAMARINE", 1, title, var, -1, py,
                                 -1, ct.TERM_PAPER)
                    cxo, cyo = fx_ + DN_FB * sc + tp, fy_ + (DN_FB + DN_WBAR) * sc + tp
                    ty = py - cyo
                    if 0 <= ty < 16 * sc * ftr:
                        px = ftrow[ty // (sc // z)]
                        one = [int.from_bytes(px[4 * q:4 * q + 4], "little") for q in range(8 * z * ftc)]
                        cells = [c for c in one for _ in range(sc // z)]
                        for q, c in enumerate(cells):
                            if 0 <= cxo + q < W:
                                row[cxo + q] = c
                    if rnd:
                        b_, e_ = dn_float_edge(lit, "ULTRAMARINE", sc)
                        dn_corners_at(row, fx_, fy_, fx_ + fw_, fy_ + fh_, r_, b_, e_, py)
                    if "frame0" in mo:                 # MS-8: cut to the frame of the moment
                        for q in range(W):
                            if q < fx_ or q >= fx_ + fw_:
                                row[q] = fb_[q]
                return row
            if y <= py < y + h:
                ct.paint(row, x, x + w, ct.TERM_PAPER)   # window 0 is the terminal: dark in both themes (K-DT)
                ct.frame(row, py, x, y, x + w, y + h, bs,
                         (T["FILL"] if DN_RIMLESS else gcol or ct.ULTRAMARINE) if f == 0 else T["RULE"])   # DN-27
                ty = py - (y + bs + tp)
                if 0 <= ty < 16 * sc * tr:
                    px = trow[ty // (sc // z)]
                    one = [int.from_bytes(px[4 * q:4 * q + 4], "little") for q in range(8 * z * tc)]
                    row[x + bs + tp:x + bs + tp + 8 * tc * sc] = [c for c in one for _ in range(sc // z)]
                if gcol is not None and f != 0 and y + 6 * sc <= py < y + 10 * sc:
                    ct.paint(row, x + w - 10 * sc, x + w - 6 * sc, gcol)   # WB-7: a resting tile's ring pip
            return row

        for py in range(H):
            row = [T["MANTLE"]] * W
            if py < BAR * sc:
                r1, y1 = [T["BAR"]] * (W1 * cz), py // sc
                bar_1x(r1, y1, W1, d, occupied, pips, title, var, counts.get("DISK", 0), counts.get("NET", 0), clk,
                       cal is not None, kern, panel, tray, cz, py // m)
                row[:W1 * sc] = spread(r1, W1)
                if 4 * sc <= py < 24 * sc:                  # AA-1: the roundel at the screen's scale, not spread
                    row[9 * sc:29 * sc] = roundel(sc, T["BAR"])[py - 4 * sc]
            else:
                row = plane_row(py)
            pm = mo.get("plate")
            if cal is not None and 15 in wins:   # RS-CAL: the OV window holds the plate and its shadow, no ground
                ox, oy, ow, oh = wins[15][4:8]
                if oy <= py < oy + oh:
                    cal.row_at(row, py, az, int(th[-1]) if th else 0)
            if pm and pm["kind"] == "panel" and pline:   # MS-9a: the panel opening or closing (MS-5)
                tw_plate_row(row, W, py, sc, thn, "panel", pm["closing"], pm["p"], pm["frame"],
                             lambda r_, yy: dn_panel_plate(r_, yy, sc, pm["frame"][0], pm["frame"][1], pgrants,
                                                           pline[1] if pline[0] else -1, thn,
                                                           (1 if pline[2] > 0 else 0) if pline[0] else -1, pline[3],
                                                           b"pid %d" % pline[2]))
            elif panel and pline and 15 in wins and py >= BAR * sc:   # MS-4 (hdesk.ci cast_row): the panel's shadow,
                ox, oy, ow, oh = wins[15][4:8]                           # High, over what lies under it
                shade_row(row, 0, W, py, ox, oy, ox + ow, oy + oh, DN_RPLATE, 3, int(th[-1]) if th else 0, sc)
            if pm and pm["kind"] == "msg":          # MS-9a: the bar message coming in or going (MS-5)
                tw_plate_row(row, W, py, sc, thn, "msg", pm["closing"], pm["p"], pm["frame"],
                             lambda r_, yy: dn_msg_plate(r_, yy, sc, pm["frame"][0], pm["frame"][1], pm["text"]))
            if (panel and pline or topen) and 15 in wins and not (pm and pm["kind"] == "panel"):
                ox, oy, ow, oh = wins[15][4:8]
                if oy <= py < oy + oh:
                    if panel:                    # DN-6 frame 9: the panel's plate (hdesk.ci panel_at)
                        dn_panel_plate(row, py, sc, ox, oy, pgrants, pline[1] if pline[0] else -1,
                                       int(th[-1]) if th else 0,
                                       (1 if pline[2] > 0 else 0) if pline[0] else -1, pline[3], b"pid %d" % pline[2])
                    else:                        # DN-15: the tray's plate (hdesk.ci tray_at_row), no outline
                        icons = [ticons.get(k, 8) for k in range(len(trows))]
                        dn_plate(row, ox, oy, ow // sc, oh // sc, sc, DN_RAD, 0, 0, T["SURF2"],
                                 lambda r, a, b, y1: dn_tray_at_row(r, a, b, icons, tsel, thov, y1), py)
            px0, py0 = mx - hot * sc, my - hot * sc
            if shown and py0 <= py < py0 + ph * sc:
                for q in range(max(px0, 0), min(px0 + pw * sc, W)):
                    c = shape_at(pk, (q - px0) // sc, (py - py0) // sc)
                    if c:
                        row[q] = ct.LOCKUP[1] if c == 2 else ct.LOCKUP[0]   # the kernel's arrow, both themes
            if rows_out is not None:
                rows_out.append(row)
            screen += b"".join(c.to_bytes(4, "little") for c in row)
    composed = hashlib.sha256(bytes(screen)).hexdigest()
    use_theme(0)
    return ok, composed, re.findall(at_size, text, re.M)


def smoke(path):
    """--smoke TRANSCRIPT: a boot straight into 1080 x 1920 (HX-12 A) where Super+Enter tiled a second terminal and
    both shells ended: every layout block is the twin's, the second terminal sat under the first, and the desk ended."""
    lines = gl.lines(open(path, encoding="utf-8", errors="replace").read())
    ct.screen_of("\n".join(lines))
    bl = blocks(lines)
    bad = [(d, i) for d, f, wins, bw, bh, dr, sc in bl for i, v in wins.items()
           if v[1] == d and v[2] != MINIMIZED and (v[4], v[5], v[6], v[7], v[8]) != twin(bw, bh, d, wins, dr, sc)[i]]
    two = any(len(w) == 2 and w.get(0, (0,) * 8)[4:8] == (8, 36, 1064, 934) and w.get(1, (0,) * 8)[4:8] ==
              (8, 978, 1064, 934) for d, f, w, *_ in bl)
    text = "\n".join(lines)
    seq = [r"^hdesk: click 340,760 button 0 window 0$", r"^hdesk: drag 0 kind 1$",
           r"^hdesk: drop 0 desktop 1 frame 16,68 1064x934$", r"^hdesk: click 380,1100 button 0 window 1$",
           r"^hdesk: terminal 1 ended, status 0$", r"^hdesk: pixel 1 (pid \d+ )?size 160x100$", r"^hdesk: bar desktop 1 \|mwin\| var \|notes\| grants \|\|$",
           r"^hdesk: resize 1 \d+x\d+ \(0\)$", r"^hdesk: pixel 1 ended$", 
           # AM-1: View opens its submenu under the pointer, Full Screen (the monocle) chosen in it
           r"^hdesk: app menu open$", r"^hdesk: click 300,150 button 0 window 15$",
           r"^hdesk: app menu chose 29 \|Full Screen\|$", r"^hdesk: pointer 300,150 shown 1$"]
    pos, miss = 0, None
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            miss = p
            break
        pos = hit + 1
    # H-3c3: the resize told mwin its content box in the layout just before it, at that layout's scale, in 1x pixels
    # (RS-SURF: the device box over the UI scale)
    rbad, k, told = [], -1, 0
    for l in lines:
        if l.startswith("hdesk: layout desktop "):
            k += 1
        mr = re.match(r"^hdesk: resize (\d+) (\d+)x(\d+) \((-?\d+)\)$", l)
        if mr:
            told += 1
            i, rw, rh = int(mr.group(1)), int(mr.group(2)), int(mr.group(3))
            v = bl[k][2][i]
            bs = (DN_FB if v[2] == FLOAT else B) * bl[k][6]   # DN-6 frame 8: a float's ring inset 2 px
            tb = DN_WBAR * bl[k][6] if v[2] == FLOAT else 0   # and its 32 px bar
            if (rw, rh) != ((v[6] - 2 * bs) // bl[k][6], (v[7] - 2 * bs - tb) // bl[k][6]):
                rbad.append(l)
    sok, composed, shots = screen_of(text, lines, bl, 1080, 1920)
    ok = bool(bl) and not bad and two and told > 0 and not rbad and "hdesk: screen 1080x1920 plane 1080x1892" in lines and \
        "hdesk: shell ended, status 0" in lines and lines[-1:] == ["daphnis: done"] and miss is None and \
        sok and shots == [composed]
    print("%s  portrait: %d blocks the twin's; two terminals stacked on 1080 x 1920; a click focused the first, a "
          "Super drag floated it, a click the second; mwin asked 160 x 100 and its variable, floated, told its box; the App Title's dropdown by click, monocle chosen by click; the screen with the arrow is the Python's %s; the desk ended%s"
          % ("PASS" if ok else "FAIL", len(bl), composed[:16], "" if ok else ": bad %r, stacked %r, missing %r, "
             "shots %r, resizes %d %r" % (bad[:1], two, miss, shots, told, rbad[:1])))
    return 0 if ok else 1


def kern(path):
    """--kern TRANSCRIPT: R0-1 to R0-3 at 1080 x 1920 (check-hybrid.sh, daphnis.kernhold=20): `kern -s` says ring 3;
    `kern kern -s` brings the desk's prompt, Esc refuses (kern: refused); again, Super+Enter runs it in ring 0; `kern
    -s` then runs in ring 0 with no prompt (the window's hold); the hold ends and `kern -s` says ring 3; a third
    request confirmed leaves the window cadmium, the bar with no KERN pill (DN-72), and the screen is the Python's."""
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = gl.lines(text)
    ct.screen_of(text)
    bl = blocks(lines)
    seq = [r"^hdesk: kern ask 0 pid 4 \|kern -s\|$", r"^hdesk: kern refused pid 4$",
           r"^hdesk: kern ask 0 pid 5 \|kern -s\|$", r"^hdesk: kern 0 pid 5$", r"^hdesk: grant 0 8$",
           r"^hdesk: bar desktop 1 \|Console\| var \|/\| grants \|KERN 1 <1m\|$", r"^hdesk: grant 0 0$",
           r"^hdesk: kern hold 0 ended$", r"^hdesk: kern ask 0 pid 8 \|kern -s\|$", r"^hdesk: kern 0 pid 8$",
           r"^hdesk: grant 0 8$", r"^hdesk: shell ended, status 0$"]
    pos, miss = 0, None
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            miss = p
            break
        pos = hit + 1
    rows = [m.group(1) for m in (re.match(r"^hdesk: term \d\d \|(.*)\|$", l) for l in lines) if m]
    want = ["# kern -s", "ring 3", "# kern kern -s", "kern: refused", "# kern kern -s", "ring 0", "# kern -s",
            "ring 0", "# kern -s", "ring 3", "# kern kern -s", "ring 0", "# exit"]
    said = [r.rstrip() for r in rows[:len(want)]] == want
    sok, composed, shots = screen_of(text, lines, bl, 1080, 1920)
    ok = bool(bl) and miss is None and said and sok and shots == [composed] and lines[-1:] == ["daphnis: done"]
    print("%s  kern: refused by Esc, run in ring 0 by Super+Enter, held by the window with no prompt, the hold "
          "ended, asked again; the cadmium window, no KERN pill (DN-72), is the Python's screen %s%s"
          % ("PASS" if ok else "FAIL", composed[:16], "" if ok else ": missing %r, rows %r, shots %r" %
             (miss, rows[:14], shots)))
    return 0 if ok else 1


def in_order(lines, seq):
    """The first pattern of seq not found in order in lines, or None."""
    pos = 0
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            return p
        pos = hit + 1
    return None


def panel(path):
    """--panel TRANSCRIPT: SP-1 and DN-34 at 1080 x 1920 with an audio device (check-hybrid.sh): `grant audio sh -c
    "cat > /dev/dsp"` holds a stream; a click on the four squares opens the system panel naming bin/cat in Now
    Playing; Left three times sets the volume to 85; a click at the middle of the volume's slider sets it to 50; Esc
    closes; the panel opened again says 50 and nothing playing, and the screen with it open is the Python's. Each
    click lands where the desk's own lines place its target (tools/sendkeys.py `@`). P2-c: the desk reads the device
    at start, before the panel first opens."""
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = gl.lines(text)
    ct.screen_of(text)
    bl = blocks(lines)
    miss = in_order(lines, [
        r"^hdesk: audio 1 net 0 \(0\)$",
        r"^hdesk: panel open$",
        r"^hdesk: panel audio 1 level 100 player \d+ \|bin/cat\| streams 1 net 0 animations 1$",
        r"^hdesk: volume 95 \(0\)$", r"^hdesk: volume 90 \(0\)$", r"^hdesk: volume 85 \(0\)$",
        r"^hdesk: volume 50 \(0\)$", r"^hdesk: panel closed$",
        r"^hdesk: panel open$", r"^hdesk: panel audio 1 level 50 player 0 \|\| streams 0 net 0 animations 1$",
        r"^hdesk: shell ended, status 0$"])
    sok, composed, shots = screen_of(text, lines, bl, 1080, 1920)
    ok = bool(bl) and miss is None and sok and shots == [composed] and lines[-1:] == ["daphnis: done"]
    print("%s  panel: the device read at desk start (P2-c); Now Playing named bin/cat on the AU-6 channel; Left set "
          "the volume to 85 and a click on the slider's middle to 50; the open panel and the bar's squares and "
          "chevron are the Python's screen %s%s" % ("PASS" if ok else "FAIL", composed[:16],
                                                     "" if ok else ": missing %r, shots %r" % (miss, shots)))
    return 0 if ok else 1


def ppm(path):
    """A P6 screendump: (w, h, rows of XRGB words)."""
    data = open(path, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
    w, h, at = int(m.group(1)), int(m.group(2)), m.end()
    return w, h, [[data[at + 3 * (y * w + x)] << 16 | data[at + 3 * (y * w + x) + 1] << 8 |
                   data[at + 3 * (y * w + x) + 2] for x in range(w)] for y in range(BAR)]


def tray_angles(a0, a1, k0, n):
    """DN-14: the chevron's angle at each of n stepped frames of a turn from a0 to a1 started at step k0 (160 ms on
    MS-2's out curve, a step 10 ms), as hdesk.ci turn_step prints them."""
    an = anim_toward(anim_rest(a0), k0 * ANIM_STEP, a1, 160 * ANIM_MS, ANIM_OUT, True)
    return [anim_value(an, (k0 + k) * ANIM_STEP) for k in range(1, n + 1)]


def tray(path, shots_at):
    """--tray TRANSCRIPT PPM0 PPM8 PPM16: SP-2, DN-14 and DN-15 at 1080 x 1920 with stepped frames
    (daphnis.stepframes): `tray cat` in a second terminal hides it in the tray; the Super plane's machine region
    leaves it out (one window, SP-R3 A); a click on the chevron opens the plate; Shift steps the chevron's half turn,
    16 frames of 10 ms on the out curve, its frames 0, 8 and 16 the Python's (the screendumps, the chevron's slot);
    a click on the plate's cell restores the window, Shift turns the chevron back; a click opens the plate again and
    a right click quits the window; `tray cat` again, the plate open and the window grown at rest (20 steps; the plate
    takes Enter, so Ctrl+J ends the shell's line), and the screen is the Python's."""
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = gl.lines(text)
    ct.screen_of(text)
    bl = blocks(lines)
    up = tray_angles(0, 180, 0, 16)
    down = tray_angles(180, 0, 16, 16)
    up2 = tray_angles(0, 180, 32, 16)
    step = lambda k, a: r"^hdesk: turn step %d angle %d$" % (k, a)
    miss = in_order(lines, [r"^hdesk: tray 1 in$", r"^hdesk: ff open pins \d+ recent \d+ grants \d+ windows 1$",
                            r"^hdesk: ff closed$", r"^hdesk: tray open 1$",
                            r"^hdesk: tray row 0 window 1 ring 3 \|bin/cat - /\|$", r"^hdesk: tray icon 0 1$"] +
                    [step(k + 1, a) for k, a in enumerate(up)] + [r"^hdesk: tray hover 0$", r"^hdesk: tray opened 1$"] +
                    [step(k + 1, a) for k, a in enumerate(down)] + [r"^hdesk: tray open 1$"] +
                    [step(k + 1, a) for k, a in enumerate(up2)] +
                    [r"^hdesk: tray quit 1$", r"^hdesk: close 1 \(0\)$", r"^hdesk: terminal 1 ended, status 15$",
                     r"^hdesk: tray bar 0 turn 0 open 0$", r"^hdesk: tray 1 in$", r"^hdesk: tray open 1$"] +
                    [step(k + 1, a) for k, a in enumerate(tray_angles(0, 180, 48, 16))] +
                    [r"^hdesk: shell ended, status 0$"])
    W1, clk = 1080, clock_text(EPOCH).encode("ascii")
    tx = W1 - 8 - (8 * len(clk) + 16) - 32 - 32
    frames = []
    for a, p in zip((0, up[7], up[15]), shots_at):
        w, h, rows = ppm(p)
        good = True
        for y in range(BAR):
            r1 = [T["BAR"]] * W1
            bar_1x(r1, y, W1, 1, {1}, {}, b"Console", b"", 0, 0, clk, False, b"", False, (1, a, True))
            good = good and rows[y][tx:tx + 24] == r1[tx:tx + 24]
        frames.append(good)
    sok, composed, shots = screen_of(text, lines, bl, 1080, 1920)
    ok = bool(bl) and miss is None and all(frames) and sok and shots == [composed] and lines[-1:] == ["daphnis: done"]
    print("%s  tray: tray cat hid its window; the chevron's frames 0, 8 and 16 are the Python's (%s); the plate's "
          "cell restored it, the chevron turned back; a right click quit it; the plate open at rest is the "
          "Python's screen %s%s"
          % ("PASS" if ok else "FAIL", " ".join("ok" if g else "bad" for g in frames), composed[:16],
             "" if ok else ": missing %r, shots %r" % (miss, shots)))
    return 0 if ok else 1


SLIDE_MS = 240


def slide_at(a, b, d, w, p):
    """MS-7 (DN-54), kit/slide.ci at: desktop d's left edge mid switch from a to b at progress p on a screen w wide;
    the size is cut before the sign, so a switch back mirrors the switch out."""
    m = abs(b - a) * w * p // 1000
    return (d - a) * w - (m if b > a else -m)


def slide_steps(a, b):
    """The stepped frames of one switch from a to b as hdesk.ci slide_tick prints them: a Shift press a frame while
    the 240 ms run, then the end."""
    out, k = [r"^hdesk: slide %d to %d$" % (a, b)], 1
    while k * ANIM_STEP < SLIDE_MS * ANIM_MS:
        out.append(r"^hdesk: slide step %d at %d$" % (k, anim_progress(ANIM_OUT, k * ANIM_STEP, SLIDE_MS * ANIM_MS)))
        k += 1
    return out + [r"^hdesk: slide ended desktop %d$" % b]


def slide(path, rest2, start, mid, end):
    """--slide TRANSCRIPT REST2 START MID END: MS-7 (DN-54, design note 50) at 1920 x 1080 with stepped frames
    (daphnis.stepframes): Super+2 slides desktop 1 out to the left and 2 in, 24 frames of 10 ms on the out curve;
    a terminal on desktop 2 (REST2); Super+1 slides back: its frame 0 (START) is desktop 2 at rest, its frame 12 (MID)
    is the Python's composition of desktop 1 (END, at rest after the slide) and desktop 2 (REST2) where the strip holds
    them, below the bar; the window list's jump to the terminal on desktop 2 slides there and focuses it when the
    slide ends; Super+1 again, and the desk ends."""
    lines = gl.lines(open(path, encoding="utf-8", errors="replace").read())
    miss = in_order(lines, slide_steps(1, 2) + slide_steps(2, 1) +
                    [r"^hdesk: ff chose win \|Console - /\| window 1$"] + slide_steps(1, 2) +
                    [r"^hdesk: layout desktop 2 focus 1$", r"^hdesk: terminal 1 ended"] + slide_steps(2, 1) +
                    [r"^hdesk: shell ended, status 0$"])

    def full(p):
        data = open(p, "rb").read()
        m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
        w, h, at = int(m.group(1)), int(m.group(2)), m.end()
        return w, h, [data[at + 3 * w * y:at + 3 * w * (y + 1)] for y in range(h)]
    (w, h, r2), (_, _, r0), (_, _, rm), (_, _, r1) = (full(p) for p in (rest2, start, mid, end))
    p = anim_progress(ANIM_OUT, 12 * ANIM_STEP, SLIDE_MS * ANIM_MS)
    x1, x2 = slide_at(2, 1, 1, w, p), slide_at(2, 1, 2, w, p)
    at0 = all(r0[y] == r2[y] for y in range(BAR, h))
    want = [r1[y][3 * -x1:] + r2[y][:3 * (w - x2)] for y in range(h)]       # x1 <= 0 <= x2: 1 on the left, 2 right
    atm = all(rm[y] == want[y] for y in range(BAR, h))
    ok = miss is None and at0 and atm and lines[-1:] == ["daphnis: done"]
    print("%s  slide: Super+2 and Super+1 slide the desks 240 ms on the out curve, a step 10 ms; Super+1's frame 0 is "
          "desktop 2 at rest (%s), its frame 12 (p %d) is desktop 1 at %d and 2 at %d (%s); the window list's jump "
          "slid to desktop 2 and focused the terminal at the end%s"
          % ("PASS" if ok else "FAIL", "ok" if at0 else "bad", p, x1, x2, "ok" if atm else "bad",
             "" if ok else ": missing %r" % (miss,)))
    return 0 if ok else 1


def bars(path):
    """--bars TRANSCRIPT: WB-1 and WB-4 at 1080 x 1920 (check-hybrid.sh): Super+f floated the terminal; a drag on its
    bar moved it 5 cells right and 2 rows down; a double click on the bar and F11 put it in and out of fullscreen;
    the fullscreen button, Super+z, the tile button, Super+f, a press on minimize released off the bar (nothing), a
    press and release on minimize, Super+Shift+m, Super+f; `sleep 999 &` and `cat` in it; the close button. Every
    layout block is the twin's; the bar's lines come in that order, each button once; a float's content box is its
    frame less its bar in every placement; the close ended the shell, the background sleep and cat, and the desk."""
    lines = gl.lines(open(path, encoding="utf-8", errors="replace").read())
    bl = blocks(lines)
    bad = [(d, i) for d, f, wins, bw, bh, dr, sc in bl for i, v in wins.items()
           if v[1] == d and v[2] != MINIMIZED and (v[4], v[5], v[6], v[7], v[8]) != twin(bw, bh, d, wins, dr, sc)[i]]
    seq = [r"^hdesk: win 0 kind 1 desktop 1 mode 1 rank \d+ frame 270,501 540x946 ", r"^hdesk: drag 0 kind 1 bar$",
           r"^hdesk: drop 0 desktop 1 frame 310,533 540x946$", r"^hdesk: drag 0 kind 1 bar$",
           r"^hdesk: drop 0 desktop 1 frame 310,533 540x946$", r"^hdesk: bar double 0$", r"^hdesk: fullscreen 0 on$",
           r"^hdesk: win 0 kind 1 desktop 1 mode 2 ", r"^hdesk: fullscreen 0 off$",
           r"^hdesk: win 0 kind 1 desktop 1 mode 1 rank \d+ frame 310,533 540x946 ",
           r"^hdesk: bar button 1 window 0$", r"^hdesk: fullscreen 0 on$", r"^hdesk: fullscreen 0 off$",
           r"^hdesk: bar button 2 window 0$", r"^hdesk: win 0 kind 1 desktop 1 mode 0 ",
           r"^hdesk: click 716,510 button 0 window 0$", r"^hdesk: click 716,510 button 0 window 0$",
           r"^hdesk: bar button 0 window 0$", r"^hdesk: win 0 kind 1 desktop 1 mode 3 ",
           r"^hdesk: bar desktop 1 \|bin/cat\| var ", r"^hdesk: bar button 3 window 0$", r"^hdesk: close 0 \(0\)$",
           r"^hdesk: shell ended, status 15$"]
    pos, miss = 0, None
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            miss = p
            break
        pos = hit + 1
    buttons = re.findall(r"^hdesk: bar button (\d) window 0$", "\n".join(lines), re.M)
    ok = bool(bl) and not bad and miss is None and buttons == ["1", "2", "0", "3"] and \
        ct.whole("\n".join(lines)) and lines[-1:] == ["daphnis: done"]
    print("%s  bars: %d blocks the twin's; the float dragged by its bar to 310,533; a double click and F11, the "
          "fullscreen button and Super+z in and out of fullscreen; tile, minimize (a release off the bar did "
          "nothing) and close acted on release; close ended the shell, sleep and cat (the pool whole) and the desk%s"
          % ("PASS" if ok else "FAIL", len(bl), "" if ok else ": bad %r, missing %r, buttons %r, last %r"
             % (bad[:1], miss, buttons, lines[-1:])))
    return 0 if ok else 1


def zones(path):
    """--zones TRANSCRIPT: WB-2 at 1080 x 1920 (check-hybrid.sh): three terminals; the third floated and dropped by
    its bar at the left edge, the right edge, the top left corner and the top; F11; the first tile Super-dragged to the
    bottom right corner. Every layout block is the twin's; after each `hdesk: zone I Z` the next block has window I
    where Z puts it: the first tile for the left edge, the last for the right, the tile at index min(q, n - 1) for
    quadrant q (0 top left .. 3 bottom right), monocle for the top; and the desk ended."""
    lines = gl.lines(open(path, encoding="utf-8", errors="replace").read())
    bl = blocks(lines)
    bad = [(d, i) for d, f, wins, bw, bh, dr, sc in bl for i, v in wins.items()
           if v[1] == d and v[2] != MINIMIZED and (v[4], v[5], v[6], v[7], v[8]) != twin(bw, bh, d, wins, dr, sc)[i]]
    k, want, seen, zbad = -1, None, [], []
    for l in lines:
        if l.startswith("hdesk: layout desktop "):
            k += 1
            if want is not None:
                i, z = want
                d, f, wins = bl[k][:3]
                tiles = sorted((v[3], j) for j, v in wins.items() if v[1] == d and v[2] == TILED)
                order = [j for r, j in tiles]
                if z == 7:
                    good = wins[i][2] == MONOCLE
                elif z == 1:
                    good = order[:1] == [i]
                elif z == 2:
                    good = order[-1:] == [i]
                else:
                    good = i in order and order.index(i) == min(z - 3, len(order) - 1)
                if not good:
                    zbad.append((i, z, order))
                want = None
        mz = re.match(r"^hdesk: zone (\d+) (\d)$", l)
        if mz:
            want = (int(mz.group(1)), int(mz.group(2)))
            seen.append(want)
    ok = bool(bl) and not bad and not zbad and seen == [(2, 1), (2, 2), (2, 3), (2, 7), (0, 6)] and \
        "hdesk: fullscreen 2 off" in lines and lines[-1:] == ["daphnis: done"]
    print("%s  zones: %d blocks the twin's; drops %r each where its zone puts it; F11 gave the third its float back; "
          "the desk ended%s" % ("PASS" if ok else "FAIL", len(bl), seen, "" if ok else ": bad %r, zones %r, last %r"
                                % (bad[:1], zbad[:2], lines[-1:])))
    return 0 if ok else 1


# --- the Super plane of FF edition 14 (section 3g): the twin of user/ci/kit/shape.ci and plane.ci's drawing ---
# Its own functions, apart from the screen's row and scale code. `--plane-proof OUTPUT [DIR]` reads a run of
# tests/ff/plane_proof.ci: each frame's model as plane.dump() prints it, then its device rows; it draws each frame
# from the model and compares row by row, and with DIR writes the twin's frames as PNGs.

ic = load("ic", "icons.py")
iw = load("iw", "iconwin.py")            # DN-5: kit/icons3.ci and fileicons.ci's twin
PL_ICONS = {}


def pl_icon_tok(k, d, x, y):
    """kit/icons.ci tok: the token of pixel (x, y) of icon k's d x d drawing (0 CLEAR outside it)."""
    if k < 0 or k >= len(ic.NAMES) or not (0 <= x < d and 0 <= y < d):
        return 0
    if (k, d) not in PL_ICONS:
        PL_ICONS[(k, d)] = ic.drawing(ic.NAMES[k], d)
    return PL_ICONS[(k, d)][y][x]


def sh_put(row, x, c):
    if 0 <= x < len(row):
        row[x] = c & 0xFFFFFF


def sh_paint(row, x0, x1, c):
    """kit/draw.ci paint."""
    for x in range(max(0, x0), min(len(row), x1)):
        row[x] = c & 0xFFFFFF


def sh_rect(row, y, x0, y0, x1, y1, c):
    if y0 <= y < y1:
        sh_paint(row, x0, x1, c)


def sh_inside(u, v, x0, y0, x1, y1, r):
    """kit/shape.ci inside: sample (u, v) in eighths inside the rounded rectangle."""
    if u < 8 * x0 or u >= 8 * x1 or v < 8 * y0 or v >= 8 * y1:
        return False
    dx = max(0, 8 * (x0 + r) - u, u - 8 * (x1 - r))
    dy = max(0, 8 * (y0 + r) - v, v - 8 * (y1 - r))
    return dx * dx + dy * dy <= 64 * r * r


def sh_fit(x0, y0, x1, y1, r):
    k = r
    if 2 * k > x1 - x0:
        k = (x1 - x0) // 2
    if 2 * k > y1 - y0:
        k = (y1 - y0) // 2
    return max(k, 0)


def sh_cover(row, x, c, n):
    if not 0 <= x < len(row) or n == 0:
        return
    row[x] = c & 0xFFFFFF if n == 16 else mix_px(row[x], c, 16 * n)


def sh_samples(x, y, x0, y0, x1, y1, r):
    return sum(sh_inside(8 * x + 2 * i + 1, 8 * y + 2 * j + 1, x0, y0, x1, y1, r) for j in range(4) for i in range(4))


def sh_rounded(row, y, x0, y0, x1, y1, r, c):
    """kit/shape.ci rounded."""
    if y < y0 or y >= y1 or x0 >= x1:
        return
    k = sh_fit(x0, y0, x1, y1, r)
    if y0 + k <= y < y1 - k:
        sh_paint(row, x0, x1, c)
        return
    sh_paint(row, x0 + k, x1 - k, c)
    for x in list(range(x0, x0 + k)) + list(range(x1 - k, x1)):
        sh_cover(row, x, c, sh_samples(x, y, x0, y0, x1, y1, k))


def arc_in(r, py):
    """hdesk.ci arc_in: the first pixel across a corner of radius r, py rows from its edge, kit/shape.ci arc16 covers whole."""
    def arc16(px):
        if px >= r or py >= r:
            return 16
        return sum((8 * r - (8 * px + 2 * s + 1)) ** 2 + (8 * r - (8 * py + 2 * t + 1)) ** 2 <= 64 * r * r
                   for s in range(4) for t in range(4))
    c = 0
    while c < r and arc16(c) < 16:
        c += 1
    return c


def place_cut(fx, fy, fw, fh, s, x0, y0, x1, y1):
    """hdesk.ci put_cut (WB-7, 0.1.1): a float's visible surface rectangle in bands, none of it past the body's lower
    corners (inset RING, radius RAD - RING)."""
    rb = (DN_RAD - DN_RING) * s
    bx0, bx1, by1 = fx + DN_RING * s, fx + fw - DN_RING * s, fy + fh - DN_RING * s
    out = [(x0, y0, x1, min(y1, by1 - rb))]
    y, ye = max(y0, by1 - rb), min(y1, by1)
    while y < ye:
        c = arc_in(rb, by1 - 1 - y)
        e = y + 1
        while e < ye and arc_in(rb, by1 - 1 - e) == c:
            e += 1
        out.append((max(x0, bx0 + c), y, min(x1, bx1 - c), e))
        y = e
    return out


def sh_lower_rounded(row, y, x0, y0, x1, y1, r, c):
    """kit/shape.ci lower_rounded (DN-36): square top corners, bottom corners of radius r."""
    if y < y0 or y >= y1 or x0 >= x1:
        return
    k = r
    if 2 * k > x1 - x0:
        k = (x1 - x0) // 2
    k = max(k, 0)
    if y < y1 - k:
        sh_paint(row, x0, x1, c)
        return
    sh_rounded(row, y, x0, y1 - 2 * k - 2, x1, y1, k, c)


def sh_ring(row, y, x0, y0, x1, y1, r, t, c):
    """kit/shape.ci ring."""
    if y < y0 or y >= y1 or x0 >= x1:
        return
    k = sh_fit(x0, y0, x1, y1, r)
    ki = max(k - t, 0)
    if y0 + k <= y < y1 - k:
        if y < y0 + t or y >= y1 - t:
            sh_paint(row, x0, x1, c)
            return
        sh_paint(row, x0, x0 + t, c)
        sh_paint(row, x1 - t, x1, c)
        return
    if y < y0 + t or y >= y1 - t:
        sh_paint(row, x0 + k, x1 - k, c)
    for x in range(x0, x1):
        if x < x0 + k or x >= x1 - k:
            n = 0
            for j in range(4):
                for i in range(4):
                    u, v = 8 * x + 2 * i + 1, 8 * y + 2 * j + 1
                    if sh_inside(u, v, x0, y0, x1, y1, k) and not sh_inside(u, v, x0 + t, y0 + t, x1 - t, y1 - t, ki):
                        n += 1
            sh_cover(row, x, c, n)


def sh_icon(row, y, x0, y0, k, s, pal):
    """kit/shape.ci icon: the s drawing when there is one, else the nearest of the 64 (32 below 32)."""
    if y < y0 or y >= y0 + s or s <= 0:
        return
    d = s if s in (32, 64) else (32 if s < 32 else 64)
    sy = (y - y0) * d // s
    for x in range(s):
        t = pl_icon_tok(k, d, x * d // s, sy)
        if t:
            sh_put(row, x0 + x, pal[t])


def sh_across(u, v, ax, ay, ex, ey):
    dx, dy = ex - ax, ey - ay
    l2 = dx * dx + dy * dy
    t = (u - ax) * dx + (v - ay) * dy
    if t < 0 or t > l2:
        return -1
    pu, pv = u - ax, v - ay
    return (pu * pu + pv * pv) * l2 - t * t


def sh_lens(row, y, x0, y0, z, c):
    """kit/shape.ci lens: the field's search glyph."""
    s = 16 * z
    if y < y0 or y >= y0 + s:
        return
    c0, ri, ro, a, e, w = 52 * z, 32 * z, 48 * z, 84 * z, 120 * z, 8 * z
    l2 = 2 * (e - a) * (e - a)
    for x in range(x0, x0 + s):
        n = 0
        for j in range(4):
            for i in range(4):
                u, v = 8 * (x - x0) + 2 * i + 1, 8 * (y - y0) + 2 * j + 1
                d2 = (u - c0) ** 2 + (v - c0) ** 2
                q = sh_across(u, v, a, a, e, e)
                if ri * ri <= d2 <= ro * ro or 0 <= q <= w * w * l2:
                    n += 1
        sh_cover(row, x, c, n)


def pl_bytes(field):
    return bytes(int(h, 16) for h in field.strip("|").split())


def pl_parse(path):
    """The frames of a run of tests/ff/plane_proof.ci: name, then (model, W, H, rows)."""
    frames, m, name = [], None, None
    with open(path) as f:
        for line in f:
            if line.startswith("r "):
                p = line.split()
                row = []
                for k in range(1, len(p), 2):
                    row += [int(p[k], 16)] * int(p[k + 1])
                frames[-1][4].append(row)
                continue
            bars = re.findall(r"\|[0-9a-f ]*\|", line)
            words = re.sub(r"\|[0-9a-f ]*\|", "|", line).split()
            if not words:
                continue
            k = words[0]
            if k == "name":
                name = words[1]
            elif k == "plane":
                v = dict(zip(words[8::2], words[9::2]))
                m = {"W": int(words[1]), "H": int(words[2]), "Z": int(words[3]), "theme": int(words[5]),
                     "q": pl_bytes(bars[0]), "armed": int(v["armed"]), "rsel": int(v["rsel"]), "hv": int(v["hv"]),
                     "lock": int(v.get("lock", 0)),
                     "pr": int(v["pr"]), "qpos": int(v["qpos"]), "previewing": int(v["previewing"]),
                     "pm": int(v.get("pm", 0)), "psel": int(v.get("psel", -1)), "phot": int(v.get("phot", 0)),
                     "pfoc": int(v.get("pfoc", 0)), "plock": int(v.get("plock", 0)),
                     "cells": [], "sizes": [], "picker": None, "recent": [], "windows": [], "grants": [], "rows": [], "fields": [], "lines": [],
                     "preview": None, "path": b"", "am": None}
            elif k == "cell":
                m["cells"].append((int(words[2]), int(words[3]), int(words[4]), pl_bytes(bars[0])))
                sizes = m["sizes"]
            elif k == "picker":
                v = dict(zip(words[2::2], words[3::2]))
                m["picker"] = {"q": pl_bytes(bars[0]), "sel": int(v["sel"]), "hv": int(v["hv"]), "pr": int(v["pr"]),
                               "list": [], "sizes": []}
            elif k == "pick":
                m["picker"]["list"].append((int(words[2]), int(words[3]), pl_bytes(bars[0])))
                sizes = m["picker"]["sizes"]
            elif k == "size":
                sizes.append(tuple(int(v) for v in words[1:6]))
            elif k == "pill":
                v = [int(x) for x in words[1:]]
                m["now"], m["pill_dom"], m["pill_x"], m["pill_y"] = v[0], v[1], tuple(v[2:7]), tuple(v[7:12])
            elif k == "recent":
                m["recent"].append((int(words[1]), pl_bytes(bars[0]), pl_bytes(bars[1])))
            elif k == "window":
                m["windows"].append((int(words[1]), int(words[2]), int(words[3]), pl_bytes(bars[0]), pl_bytes(bars[1])))
            elif k == "pinmenu":
                m["am"] = {"x": int(words[1]), "y": int(words[2]), "sel": int(words[3]), "rows": []}
            elif k == "amrow":
                m["am"]["rows"].append((int(words[1]), int(words[2])))
            elif k == "grant":
                m["grants"].append((int(words[1]), pl_bytes(bars[0])))
            elif k == "row":
                m["rows"].append((int(words[2]), int(words[3])) + tuple(pl_bytes(b) for b in bars[:4]))
            elif k == "preview":
                m["preview"] = (int(words[1]),) + tuple(pl_bytes(b) for b in bars[:4])
                m["pv_off"] = int(words[-1]) if len(words) > 6 else 0
            elif k == "field":
                m["fields"].append((int(words[1]), pl_bytes(bars[0]), pl_bytes(bars[1])))
            elif k == "path":
                m["path"] = pl_bytes(bars[0])
            elif k == "line":
                m["lines"].append(pl_bytes(bars[0]))
            elif k == "frame":
                frames.append((name, m, int(words[1]), int(words[2]), []))
    return frames


class Plane:
    """kit/plane.ci's geometry and drawing over a dumped model (section 3g; 1x units, drawn times Z)."""
    MARGIN, COL_MAX, FIELD_H, GAP = 32, 960, 44, 20
    PL_W, PL_H, PL_TOP, PL_R, PL_PAD, PL_GAP, PL_SHADOW, SCRIM = 720, 424, 40, 16, 20, 16, 3, 115   # DN-49
    RAIL_W, RAIL_ROW, RAIL_ICON, TOP_H = 132, 52, 32, 52
    CELL_H, CELL_GAP, FOOT_H = 80, 4, 44
    ROW_H, ROW_GAP, INSET, R_KEY, R_CTRL, R_PANEL, R_CELL = 28, 0, 0, 4, 6, 8, 12
    LABEL_H, HEAD, SECT_GAP, KEY_H, PANEL_H, PANEL_EMPTY_H = 11, 19, 20, 20, 300, 86

    def __init__(self, m):
        self.m = m
        self.Z = m["Z"]
        self.W, self.H = m["W"], m["H"]
        self.WP, self.HP = self.W // self.Z, self.H // self.Z
        self.qn = len(m["q"])
        self.gn = len(m["cells"])
        self.ppn = max(self.gn - 3, 0)          # DN-49: the pins, then the rail's three homes
        self.label_boxes = []                   # (cell, x0, x1, cell's x0 + pad, x1 - pad) of each label drawn
        self.rn = len(m["rows"])
        ct.use_theme(m["theme"])
        self.T = ct.TOK

    def tok(self, name):
        return self.T[name]

    # geometry, 1x (DN-49: the plate)
    def plate_w(self):
        return min(self.PL_W, self.WP)

    def plate_h(self):
        return min(self.PL_H + self.pv_grow(), max(self.HP - self.PL_TOP, 0))   # kit/plane.ci: a wrapped preview

    PV_LINES = 3

    def pv_wrap(self, w):
        """kit/plane.ci pv_wrap: each value's lines, 1 to PV_LINES, while the screen holds the plate; the lines past one."""
        room = max(self.HP - self.PL_TOP - self.PL_H, 0) // 16
        lines, more = [], 0
        for f, lab, val in self.m["fields"]:
            n = max(1, min(self.wrap_lines(val, f, w), self.PV_LINES, 1 + room - more))
            lines.append(n)
            more += n - 1
        return lines, more

    def pv_grow(self):
        m = self.m
        if not self.qn or not m["fields"] or m["previewing"] or self.WP < 880:
            return 0
        return 16 * self.pv_wrap(176 * self.Z)[1]

    def plate_x0(self):
        return (self.WP - self.plate_w()) // 2

    def col_w(self):
        return max(self.plate_w() - 2 * self.PL_PAD, 0)

    def col_x0(self):
        return self.plate_x0() + self.PL_PAD

    def col_x1(self):
        return self.col_x0() + self.col_w()

    def field_y0(self):
        return self.PL_TOP + self.PL_PAD

    @staticmethod
    def pin_cols(n):
        return 7 if n <= 14 else 9 if n <= 18 else 11 if n <= 22 else 14

    @staticmethod
    def pin_icon(n):
        return 48 if n <= 14 else 40 if n <= 18 else 32 if n <= 22 else 28

    def cols(self):
        return self.pin_cols(self.ppn)

    def grid_y0(self):
        return self.field_y0() + self.FIELD_H + self.PL_GAP

    def grid_y1(self):
        return self.grid_y0() + 2 * self.CELL_H + self.CELL_GAP

    def pins_x1(self):
        return self.col_x1() - self.RAIL_W - 2 * self.PL_GAP - 1

    def rule_x(self):
        return self.pins_x1() + self.PL_GAP

    def rail_x0(self):
        return self.col_x1() - self.RAIL_W

    def foot_y0(self):
        return self.PL_TOP + self.plate_h() - self.FOOT_H

    def stacked(self):
        return False

    def band_y0(self):
        return (self.field_y0() + self.FIELD_H if self.qn else self.grid_y1()) + self.PL_GAP

    def band_y1(self):
        return self.foot_y0()

    def left_x1(self):
        return self.col_x1() - 300 if self.qn else self.col_x0() + (self.col_w() - 20) // 2

    def right_x0(self):
        return self.col_x1() - 280 if self.qn else self.left_x1() + 20

    def cell_box(self, k):
        if k >= self.ppn:
            j = k - self.ppn
            y0 = self.grid_y0() + j * (self.RAIL_ROW + self.CELL_GAP)
            return self.rail_x0(), y0, self.col_x1(), y0 + self.RAIL_ROW
        c = self.cols()
        i = k % c
        w = self.pins_x1() - self.col_x0()
        x0 = self.col_x0() + i * (w + self.CELL_GAP) // c
        x1 = self.col_x0() + (i + 1) * (w + self.CELL_GAP) // c - self.CELL_GAP
        y0 = self.grid_y0() + (k // c) * (self.CELL_H + self.CELL_GAP)
        return x0, y0, x1, y0 + self.CELL_H

    def cells_shown(self):
        return self.gn

    # text
    def base_of(self, top, h, f):
        fa = tw.face(f, self.Z)
        d = h * self.Z - fa.ascent - fa.descent
        return top * self.Z + (d // 2 if d >= 0 else -(-d // 2)) + fa.ascent   # plane.ci half: toward zero

    def tw(self, s, f):
        return tw.width(s, f, self.Z)

    def say(self, row, y, x, top, h, x1, s, c, f):
        b = self.base_of(top, h, f)
        fa = tw.face(f, self.Z)
        if y < b - fa.ascent - 4 * self.Z or y >= b + fa.descent + 4 * self.Z:
            return
        tw.text(row, y, x, b, x1, s, c, f, self.Z)

    def wrap_end(self, s, at, f, w):
        e, good = at, -1
        while e <= len(s):
            if e == len(s) or s[e] == 32:
                if tw.width(s[at:e], f, self.Z) <= w or good < 0:
                    good = e
                else:
                    return good
                if e == len(s):
                    return good
            e += 1
        return good

    def wrap_lines(self, s, f, w):
        lines, at = 0, 0
        while at < len(s):
            at = self.wrap_end(s, at, f, w)
            lines += 1
            while at < len(s) and s[at] == 32:
                at += 1
        return lines

    def fit_rows(self, top, n):
        room = self.band_y1() - top + self.ROW_GAP
        return 0 if room < 0 else min(room // (self.ROW_H + self.ROW_GAP), n)

    def block_h(self, k, h0):
        return self.HEAD + k * (self.ROW_H + self.ROW_GAP) - self.ROW_GAP if k > 0 else self.HEAD + h0

    def grants_panel_h(self):
        return 16 + 13 + 8 + 20 * self.gr_lines + 16

    def lay_rest(self):
        m = self.m
        cn, grn = len(m["recent"]), len(m["grants"])
        wn = len([w for w in m["windows"] if w[2]])   # DN-41 (c): the minimized windows only
        self.vc = self.cells_shown()
        by, end = self.band_y0(), self.band_y1()
        self.rec_n = self.fit_rows(by + self.HEAD, cn)
        if self.stacked() and self.rec_n > 3:
            self.rec_n = 3
        self.rec_lab = self.rec_n > 0 or (cn == 0 and by + self.HEAD + self.PANEL_EMPTY_H <= end)
        rec_h = self.block_h(self.rec_n, self.PANEL_EMPTY_H) if self.rec_lab else 0
        self.ry0 = by + rec_h + self.GAP if self.stacked() and self.rec_lab else by
        self.gr_lines = 0                   # DN-46: no caption
        room = end - (self.ry0 + self.HEAD) + self.ROW_GAP     # DN-39 (a): no GRANTS block; windows take the band
        self.win_n = min(room // (self.ROW_H + self.ROW_GAP), wn) if room > 0 else 0
        if self.win_n == 0:
            self.win_n = self.fit_rows(self.ry0 + self.HEAD, wn)
        self.win_lab = self.win_n > 0 or (wn == 0 and self.ry0 + self.HEAD + 13 <= end)
        self.gr_y = self.ry0 + self.block_h(self.win_n, 13) + self.GAP if self.win_lab else self.ry0
        self.gr_n, self.gr_lab = 0, False                      # DN-39 (a)

    def lay_query(self):
        rows = self.m["rows"]
        y, end = self.band_y0(), self.band_y1()
        self.q_y = [-1] * 32
        self.q_sect = [-1] * 4
        self.q_none = [-1] * 4
        if self.rn > 0 and y + self.HEAD + self.TOP_H <= end:
            self.q_sect[0] = y
            self.q_y[0] = y + self.HEAD
        y += self.HEAD + self.TOP_H + self.SECT_GAP
        for s in (1, 2, 3):
            k = sum(1 for p in range(1, self.rn) if rows[p][0] == s)
            if s < 3 or k > 0:
                ry = y + self.HEAD
                if (k == 0 and ry + 13 <= end) or (k > 0 and ry + self.ROW_H <= end):
                    self.q_sect[s] = y
                if k == 0:
                    if ry + 13 <= end:
                        self.q_none[s] = ry
                    y = ry + 13 + self.SECT_GAP
                else:
                    for p in range(1, self.rn):
                        if rows[p][0] == s:
                            if ry + self.ROW_H <= end:
                                self.q_y[p] = ry
                            ry += self.ROW_H + self.ROW_GAP
                    y = ry - self.ROW_GAP + self.SECT_GAP
        self.pv_x0, self.pv_x1 = self.right_x0(), self.col_x1()
        self.pv_y0 = y - self.SECT_GAP + self.GAP if self.stacked() else self.band_y0()
        self.pv_y1 = end if self.m["previewing"] else self.pv_y0 + self.PANEL_H

    # painting
    def pal(self):
        return [0] + [self.tok(n) for n in ("PAPER", "INK", "ULTRAMARINE", "SIENNA", "OCHRE", "CADMIUM")]

    FILE_ICON = 100

    def has_size(self, px, file):
        return px in (16, 28, 32, 40, 48, 64) or (not file and px in (56, 72, 80, 88))

    def above(self, d):
        """kit/plane.ci above: the smallest drawn size whose device side is at least d (88 the largest)."""
        return min([c for c in (16, 28, 32, 40, 48, 56, 64, 72, 80, 88) if c * self.Z >= d] + [88])

    def icon_scaled(self, row, y, cx, cy, k, d, ground):
        """kit/plane.ci icon_scaled (DN-22): the next larger drawing laid over ground, scaled down bilinearly in
        256ths, its channels rounded."""
        px = self.above(d)
        m = px * self.Z
        x0, y0 = cx - d // 2, cy - d // 2
        if y < y0 or y >= y0 + d or m > 176:
            return

        def src(i):
            return max(0, (2 * i + 1) * m * 128 // d - 128)

        sy = src(y - y0)
        ya, fy = sy // 256, sy % 256
        yb = min(ya + 1, m - 1)
        g = ground & 0xFFFFFF
        r0, r1 = [g] * m, [g] * m
        iw.icon_at(r0, ya, 0, 0, k, px, self.Z, ground)
        iw.icon_at(r1, yb, 0, 0, k, px, self.Z, ground)
        for i in range(d):
            sx = src(i)
            xa, fx = sx // 256, sx % 256
            xb = min(xa + 1, m - 1)
            c = 0
            for sh in (16, 8, 0):
                va, vb, vc, ve = (r0[xa] >> sh & 255, r0[xb] >> sh & 255, r1[xa] >> sh & 255, r1[xb] >> sh & 255)
                top, bot = va * (256 - fx) + vb * fx, vc * (256 - fx) + ve * fx
                c |= (top * (256 - fy) + bot * fy + 32768) >> 16 << sh
            sh_put(row, x0 + i, c)

    def icon_d(self, row, y, cx, cy, k, d, ground):
        """kit/plane.ci icon_d: a drawn size exactly through tools/iconwin.py (icons3, or FILE_ICON + fileicons);
        a size between two the larger drawing scaled down (DN-22)."""
        file = k >= self.FILE_ICON
        if d % self.Z or not self.has_size(d // self.Z, file):
            if not file:
                self.icon_scaled(row, y, cx, cy, k, d, ground)
            return
        px = d // self.Z
        s = px * self.Z
        if y < cy - s // 2 or y >= cy - s // 2 + s:
            return
        if file:
            iw.file_at(row, y, cx - s // 2, cy - s // 2, k - self.FILE_ICON, px, self.Z)
        else:
            iw.icon_at(row, y, cx - s // 2, cy - s // 2, k, px, self.Z, ground)

    def icon_c3(self, row, y, cx, cy, k, s, ground):
        self.icon_d(row, y, cx, cy, k, s * self.Z, ground)

    def icon_c(self, row, y, cx, cy, k, s):
        d = s * self.Z
        sh_icon(row, y, cx - d // 2, cy - d // 2, k, d, self.pal())

    def key_w(self, t):
        return self.tw(t, F_PATH) + 14 * self.Z

    def keycap(self, row, y, x, top, t, c, tc):
        Z = self.Z
        w = self.key_w(t)
        sh_ring(row, y, x, top * Z, x + w, (top + self.KEY_H) * Z, self.R_KEY * Z, Z, c)
        self.say(row, y, x + 7 * Z, top, self.KEY_H, x + w, t, tc, F_PATH)
        return w

    def label(self, row, y, x, top, x1, t):
        self.say(row, y, (x + 10) * self.Z, top, self.LABEL_H, x1 * self.Z, t, self.tok("INK_DIM"), F_LABEL)

    def field_row(self, row, y):
        Z, q = self.Z, self.m["q"]
        x0, x1 = self.col_x0() * Z, self.col_x1() * Z
        ft = self.field_y0()
        y0, y1 = ft * Z, (ft + self.FIELD_H) * Z
        if y < y0 or y >= y1:
            return
        r = self.FIELD_H // 2 * Z
        sh_rounded(row, y, x0, y0, x1, y1, r, self.tok("SURF2"))
        sh_ring(row, y, x0, y0, x1, y1, r, 2 * Z, self.tok("ULTRAMARINE"))
        sh_lens(row, y, x0 + 18 * Z, (ft + (self.FIELD_H - 16) // 2) * Z, Z, self.tok("INK"))
        kx = x1 - 18 * Z                     # DN-46 (b): no Esc keycap
        tx1 = kx - 12 * Z
        if self.qn:
            ctx = b"No results" if self.rn == 0 else b"%d result%s" % (self.rn, b"" if self.rn == 1 else b"s")
            cw = self.tw(ctx, F_BODY)
            self.say(row, y, tx1 - cw, ft, self.FIELD_H, tx1, ctx, self.tok("INK_DIM"), F_BODY)
            tx1 = tx1 - cw - 12 * Z
        tx = x0 + 46 * Z
        if not self.qn:
            self.say(row, y, tx, ft, self.FIELD_H, tx1, b"Search files, programs and windows",
                     self.tok("INK_DIM"), tw.SEARCH)
        else:
            self.say(row, y, tx, ft, self.FIELD_H, tx1, q, self.tok("INK"), tw.SEARCH)
            e = min(tx + self.tw(q, tw.SEARCH), tx1)
            b = self.base_of(ft, self.FIELD_H, tw.SEARCH)
            fa = tw.face(tw.SEARCH, Z)
            sh_rect(row, y, e + Z, b - fa.ascent, e + 3 * Z, b + fa.descent, self.tok("INK"))

    def icon_size(self, k):
        m = self.m
        if k == m["pr"]:
            return 56
        if k == m["hv"] or k == m["rsel"]:
            return 72
        return 64

    def size_now(self, k):
        v = anim_value(self.m["sizes"][k], self.m["now"])
        return v if v > 0 else self.icon_size(k) * self.Z

    def pill_now(self):
        return anim_value(self.m["pill_x"], self.m["now"]), anim_value(self.m["pill_y"], self.m["now"])

    def grid_row(self, row, y):
        """kit/plane.ci grid_row (DN-49): the pins by the density, the rule, the rail's homes."""
        Z, m = self.Z, self.m
        if y < self.grid_y0() * Z or y >= self.grid_y1() * Z:
            return
        hv, rsel = m["hv"], m["rsel"]
        if 0 <= hv < self.vc and hv != rsel:
            bx0, by0, bx1, by1 = self.cell_box(hv)
            sh_rounded(row, y, bx0 * Z, by0 * Z, bx1 * Z, by1 * Z, self.R_CELL * Z, self.tok("SURF2"))
        if rsel < self.vc:
            bx0, by0, bx1, by1 = self.cell_box(rsel)
            px0, py0 = bx0 * Z, by0 * Z
            if m["pill_dom"] == 1:
                px0, py0 = self.pill_now()
            sh_rounded(row, y, px0, py0, px0 + (bx1 - bx0) * Z, py0 + (by1 - by0) * Z, self.R_CELL * Z,
                       self.tok("FILL"))
        rx = self.rule_x()
        sh_rect(row, y, rx * Z, self.grid_y0() * Z, (rx + 1) * Z, self.grid_y1() * Z, self.tok("BAR_RULE"))
        sz = self.pin_icon(self.ppn)
        names = sz > 28
        for k in range(self.vc):
            bx0, by0, bx1, by1 = self.cell_box(k)
            x0, y0, x1, y1 = bx0 * Z, by0 * Z, bx1 * Z, by1 * Z
            if not y0 <= y < y1:
                continue
            ink = self.tok("ON_FILL") if k == rsel else self.tok("INK")
            a, icon, win, name = m["cells"][k]
            gr = self.tok("FILL") if k == rsel else self.tok("SURF2") if k == hv else self.tok("MANTLE")
            if k >= self.ppn:
                self.icon_d(row, y, x0 + (10 + self.RAIL_ICON // 2) * Z, (by0 + self.RAIL_ROW // 2) * Z, icon,
                            self.RAIL_ICON * Z, gr)
                self.say(row, y, x0 + (10 + self.RAIL_ICON + 12) * Z, by0 + (self.RAIL_ROW - 16) // 2, 16, x1, name,
                         ink, F_NAME)
                continue
            top = by0 + (self.CELL_H - sz) // 2
            if names:
                top = by0 + (self.CELL_H - (sz + 8 + 12)) // 2
            self.icon_d(row, y, (x0 + x1) // 2, (top + sz // 2) * Z, icon, sz * Z, gr)
            if names:
                dw = (self.DOT + 5) * Z if win else 0
                room = x1 - x0 - 2 * self.LABEL_PAD * Z - dw
                pf = self.pin_face(name, room)          # DN-52 (e): 12, 11, then 10 px to fit, then the clip
                name = self.fit_name(name, pf, room)    # DN-49: in its cell
                w = self.tw(name, pf)
                nx = (x0 + x1) // 2 - (w + dw) // 2
                self.label_boxes.append((k, nx, nx + w + dw, x0 + self.LABEL_PAD * Z, x1 - self.LABEL_PAD * Z))
                ny = top + sz + 8
                if win:
                    dy0 = (ny + 3) * Z
                    if dy0 <= y < dy0 + self.DOT * Z:
                        sh_rounded(row, y, nx, dy0, nx + self.DOT * Z, dy0 + self.DOT * Z, self.DOT * Z // 2,
                                   self.tok("OCHRE"))
                self.say(row, y, nx + dw, ny - 2, 16, x1, name, ink, pf)

    LABEL_PAD = 0                            # kit/plane.ci: the whole cell (was 4)

    def pin_face(self, t, room):
        """kit/plane.ci pin_face (DN-52 (e), measured): 12 px, else 11, else 10, the first in which t fits room."""
        if self.tw(t, F_SMALL) <= room:
            return F_SMALL
        if self.tw(t, tw.PIN11) <= room:
            return tw.PIN11
        return tw.PIN10
    ELLIPSIS = b"\xe2\x80\xa6"

    def fit_name(self, t, f, wmax):
        """kit/plane.ci fit_name (DN-49): t whole, or its last whole code points that fit with an ellipsis."""
        if self.tw(t, f) <= wmax:
            return t
        ew = self.tw(self.ELLIPSIS, f)
        k = len(t)
        while k > 0:
            k -= 1
            while k > 0 and t[k] & 192 == 128:
                k -= 1
            if self.tw(t[:k], f) + ew <= wmax:
                break
        while k > 0 and t[k - 1] == 32:
            k -= 1
        return t[:k] + self.ELLIPSIS

    def pin_clipped(self, k):
        if self.pin_icon(self.ppn) <= 28:
            return True
        bx0, _, bx1, _ = self.cell_box(k)
        a, icon, win, name = self.m["cells"][k]
        dw = (self.DOT + 5) * self.Z if win else 0
        room = (bx1 - bx0 - 2 * self.LABEL_PAD) * self.Z - dw
        return self.fit_name(name, self.pin_face(name, room), room) != name

    def pin_tip_row(self, row, y):
        """kit/plane.ci pin_tip_row (DN-49): a hovered pin's full name in kit/tooltip.ci's plate under its cell, at
        28 px or where its label is clipped."""
        Z, m = self.Z, self.m
        hv = m["hv"]
        if hv < 0 or hv >= self.ppn or self.qn or not self.pin_clipped(hv):
            return
        bx0, by0, bx1, by1 = self.cell_box(hv)
        name = m["cells"][hv][3]
        w = (16 + tw.width(name, F_BODY, 1)) * Z
        x0, y0 = (bx0 + bx1) * Z // 2 - w // 2, (by1 + 6) * Z
        if not y0 <= y < y0 + 24 * Z:
            return
        sh_rounded(row, y, x0, y0, x0 + w, y0 + 24 * Z, 6 * Z, TIP_GROUND)
        z = min(Z, 2)
        tw.text(row, y, x0 + 8 * Z, y0 + (24 * Z - 24 * z) // 2 + 16 * z, x0 + w, name, TIP_INK, F_BODY, z)

    def row_ground(self, row, y, x0, top, x1, sel):
        """The rows' two passes (kit/plane.ci ps): grounds, then the pill, then contents. DN-49: no row ground."""
        return sel if sel or self.ps != 0 else False

    def row_pill(self, row, y, x0, x1, top):
        Z = self.Z
        py = top * Z
        if self.m["pill_dom"] in (2, 3):
            py = self.pill_now()[1]
        sh_rounded(row, y, (x0 + self.INSET) * Z, py, (x1 - self.INSET) * Z, py + self.ROW_H * Z, self.ROW_H * Z // 2,
                   self.tok("FILL"))

    def row_body(self, row, y, x0, top, x1, icon, name, nf, path, side, sf, sel, sidec):
        if self.ps != 1:
            return
        Z = self.Z
        ink, dim = self.tok("INK"), self.tok("INK_DIM")
        if sel:
            ink = dim = sidec = self.tok("ON_FILL")
        dx0, dx1 = x0 * Z, x1 * Z
        if icon >= 0:
            self.icon_c3(row, y, dx0 + 18 * Z, (top + self.ROW_H // 2) * Z, icon, 16,
                         self.tok("FILL") if sel else self.tok("SURF2"))
        sx = dx1 - 10 * Z - self.tw(side, sf)
        self.say(row, y, sx, top, self.ROW_H, dx1, side, sidec, sf)
        nx = dx0 + 36 * Z
        self.say(row, y, nx, top, self.ROW_H, sx - 10 * Z, name, ink, nf)
        px = nx + self.tw(name, nf) + 10 * Z
        if path and px < sx - 10 * Z:
            self.say(row, y, px, top, self.ROW_H, sx - 10 * Z, path, dim, F_PATH)

    def rest_band(self, row, y):
        m = self.m
        self.ps = 0
        self.rest_pass(row, y)
        rsel, vc, rn_, wn_ = m["rsel"], self.vc, self.rec_n, self.win_n
        if vc <= rsel < vc + rn_:
            self.row_pill(row, y, self.col_x0(), self.left_x1(),
                          self.band_y0() + self.HEAD + (rsel - vc) * (self.ROW_H + self.ROW_GAP))
        elif vc + rn_ <= rsel < vc + rn_ + wn_:
            self.row_pill(row, y, self.right_x0(), self.col_x1(),
                          self.ry0 + self.HEAD + (rsel - vc - rn_) * (self.ROW_H + self.ROW_GAP))
        self.ps = 1
        self.rest_pass(row, y)

    def rest_pass(self, row, y):
        Z, m = self.Z, self.m
        by, end = self.band_y0(), self.band_y1()
        lx0, lx1 = self.col_x0(), self.left_x1()
        if self.rec_lab and self.ps == 0:
            self.label(row, y, lx0, by, lx1, b"RECENT FILES")
        top = by + self.HEAD
        if not m["recent"] and top + self.PANEL_EMPTY_H <= end and self.ps == 0:
            y0, y1 = top * Z, (top + self.PANEL_EMPTY_H) * Z
            if y0 <= y < y1:
                sh_rounded(row, y, lx0 * Z, y0, lx1 * Z, y1, self.R_PANEL * Z, self.tok("PAPER"))
                bw = self.tw(b"Open Index", F_NAME) + 24 * Z
                bx1 = (lx1 - 24) * Z
                bx0 = bx1 - bw
                bt = top + 26
                sh_rounded(row, y, bx0, bt * Z, bx1, (bt + 33) * Z, self.R_CTRL * Z, self.tok("SURF1"))
                self.say(row, y, bx0 + 12 * Z, bt, 33, bx1, b"Open Index", self.tok("INK"), F_NAME)
                tx = (lx0 + 24) * Z
                self.say(row, y, tx, top + 20, 16, bx0 - 24 * Z, b"No recent files", self.tok("INK"), tw.SEARCH)
        for k in range(self.rec_n):
            ry = top + k * (self.ROW_H + self.ROW_GAP)
            if ry * Z <= y < (ry + self.ROW_H) * Z:
                icon, path, side = m["recent"][k]
                s = self.row_ground(row, y, lx0, ry, lx1, m["rsel"] == self.vc + k)
                self.row_body(row, y, lx0, ry, lx1, icon, path, F_PATH, b"", side, F_PATH, s, self.tok("INK_DIM"))
        rx0, rx1, ry0 = self.right_x0(), self.col_x1(), self.ry0
        mins = [w for w in m["windows"] if w[2]]       # DN-41 (c): titled Minimized, the minimized windows only
        if self.win_lab and self.ps == 0:
            self.label(row, y, rx0, ry0, rx1, b"MINIMIZED")
        if not mins and ry0 + self.HEAD + 13 <= end and self.ps == 0:
            self.say(row, y, (rx0 + 16) * Z, ry0 + self.HEAD, 13, rx1 * Z, b"No minimized windows.",
                     self.tok("INK_DIM"), F_BODY)
        for j in range(self.win_n):
            ry = ry0 + self.HEAD + j * (self.ROW_H + self.ROW_GAP)
            if ry * Z <= y < (ry + self.ROW_H) * Z:
                icon, desk, mini, title, path = mins[j]
                s = self.row_ground(row, y, rx0, ry, rx1, m["rsel"] == self.vc + self.rec_n + j)
                dk, dc = b"Desktop %d" % desk, self.tok("INK_DIM")
                if mini:
                    dk, dc = b"Minimized", self.tok("OCHRE")
                self.row_body(row, y, rx0, ry, rx1, icon, title, F_NAME, path, dk, F_BODY, s, dc)
        gy = self.gr_y
        if self.gr_lab and self.ps == 0:
            self.label(row, y, rx0, gy, rx1, b"GRANTS")
        gt = gy + self.HEAD
        if not m["grants"] and self.ps == 0 and self.gr_lab:
            ph = self.grants_panel_h()
            if gt + ph <= end and gt * Z <= y < (gt + ph) * Z:
                sh_rounded(row, y, rx0 * Z, gt * Z, rx1 * Z, (gt + ph) * Z, self.R_PANEL * Z, self.tok("PAPER"))
                self.say(row, y, (rx0 + 16) * Z, gt + 16, 13, (rx1 - 16) * Z, b"None active", self.tok("INK"), F_NAME)
        for j in range(self.gr_n):
            ry = gt + j * (self.ROW_H + self.ROW_GAP)
            if ry * Z <= y < (ry + self.ROW_H) * Z:
                g, title = m["grants"][j]
                self.row_ground(row, y, rx0, ry, rx1, False)
                gc, gw = (self.tok("OCHRE"), b"Network") if g == 2 else (self.tok("SIENNA"), b"Disk")
                self.row_body(row, y, rx0, ry, rx1, -1, title, F_NAME, b"", gw, F_BODY, False, gc)

    def top_hit(self, row, y, top):
        Z, m = self.Z, self.m
        x0, x1 = self.col_x0() * Z, self.left_x1() * Z
        y0, y1 = top * Z, (top + self.TOP_H) * Z
        if y < y0 or y >= y1:
            return
        _, icon, nm, pt, _, kw = m["rows"][0]
        ink = self.tok("INK")
        sel = m["qpos"] == 0
        sh_rounded(row, y, x0, y0, x1, y1, self.TOP_H // 2 * Z, self.tok("FILL") if sel else self.tok("SURF2"))
        if sel:
            ink = self.tok("ON_FILL")
        self.icon_c3(row, y, x0 + 28 * Z, (top + self.TOP_H // 2) * Z, icon, 32,
                     self.tok("FILL") if sel else self.tok("SURF2"))
        kx = x1 - 16 * Z                     # DN-46 (b): no Enter keycap
        wx = kx - self.tw(kw, F_BODY)
        self.say(row, y, wx, top, self.TOP_H, kx, kw, ink, F_BODY)
        tx = x0 + 56 * Z
        self.say(row, y, tx, top + 9, 16, wx - 12 * Z, nm, ink, tw.SEARCH)
        self.say(row, y, tx, top + 30, 12, wx - 12 * Z, pt, ink, F_PATH)

    def query_band(self, row, y):
        m = self.m
        self.ps = 0
        self.query_pass(row, y)
        if 1 <= m["qpos"] < self.rn and self.q_y[m["qpos"]] >= 0:
            self.row_pill(row, y, self.col_x0(), self.left_x1(), self.q_y[m["qpos"]])
        self.ps = 1
        self.query_pass(row, y)
        if self.rn:
            self.preview_panel(row, y)

    def query_pass(self, row, y):
        Z, m = self.Z, self.m
        lx0, lx1 = self.col_x0(), self.left_x1()
        if self.q_sect[0] >= 0 and self.ps == 0:
            self.label(row, y, lx0, self.q_sect[0], lx1, b"TOP HIT")
            self.top_hit(row, y, self.q_y[0])
        for s, head in ((1, b"FILES"), (2, b"WINDOWS"), (3, b"PROGRAMS")):
            if self.ps != 0:
                break
            if self.q_sect[s] >= 0:
                self.label(row, y, lx0, self.q_sect[s], lx1, head)
            if self.q_none[s] >= 0:
                nt = b'No file names match "' + m["q"] + b'".' if s == 1 else b"No open window matches."
                self.say(row, y, (lx0 + 10) * Z, self.q_none[s], 13, lx1 * Z, nt, self.tok("INK_DIM"), F_BODY)
        for p in range(1, self.rn):
            ry = self.q_y[p]
            if ry >= 0 and ry * Z <= y < (ry + self.ROW_H) * Z:
                _, icon, nm, pt, sd, _ = m["rows"][p]
                s = self.row_ground(row, y, lx0, ry, lx1, p == m["qpos"])
                self.row_body(row, y, lx0, ry, lx1, icon, nm, F_NAME, pt, sd, F_PATH, s, self.tok("INK_DIM"))

    def preview_panel(self, row, y):
        Z, m = self.Z, self.m
        if self.WP < 880 or (self.pv_y1 > self.band_y1() and not m["previewing"]):   # DN-22
            return
        x0, x1, y0, y1 = self.pv_x0 * Z, self.pv_x1 * Z, self.pv_y0 * Z, (self.pv_y1 + self.pv_grow()) * Z
        if y < y0 or y >= y1:
            return
        sh_rounded(row, y, x0, y0, x1, y1, self.R_CELL * Z, self.tok("PAPER"))   # DN-49 (frame 2)
        icon, name, what, opn, two = m["preview"]
        t = self.pv_y0
        lx, rx = x0 + 16 * Z, x1 - 16 * Z
        lines, more = ([], 0) if m["previewing"] else self.pv_wrap(rx - lx - 72 * Z)
        self.icon_c3(row, y, lx + 24 * Z, (t + 40) * Z, icon, 48, self.tok("PAPER"))
        tx = lx + 60 * Z
        self.say(row, y, tx, t + 20, 18, rx, name, self.tok("INK"), tw.TITLE)
        self.say(row, y, tx, t + 46, 13, rx, what, self.tok("INK_DIM"), F_BODY)
        fy = t + 80
        if m["previewing"]:
            self.say(row, y, lx, fy, 16, rx, m["path"], self.tok("INK_DIM"), F_PATH)
            for k, ln in enumerate(m["lines"]):
                r = fy + 24 + 16 * k
                if r + 16 <= self.pv_y1 - 16:
                    self.say(row, y, lx, r, 16, rx, ln, self.tok("INK"), F_PATH)
            return
        r = fy
        for i, (f, lab, val) in enumerate(m["fields"]):
            self.say(row, y, lx, r, 16, lx + 72 * Z, lab, self.tok("INK_DIM"), F_BODY)
            at = 0
            for ln in range(lines[i]):            # kit/plane.ci: wrapped at spaces, the last line the rest
                e = self.wrap_end(val, at, f, rx - lx - 72 * Z) if ln + 1 < lines[i] else len(val)
                self.say(row, y, lx + 72 * Z, r + 16 * ln, 16, rx, val[at:e], self.tok("INK"), f)
                at = e
                while at < len(val) and val[at] == 32:
                    at += 1
            r += 26 + 16 * (lines[i] - 1)
        for i, word in enumerate((opn, two)):
            bt = fy + 26 * 5 - 10 + 16 + 16 * more + 36 * i
            if bt * Z <= y < (bt + 32) * Z:
                sh_rounded(row, y, lx, bt * Z, rx, (bt + 32) * Z, self.R_CTRL * Z, self.tok("SURF1"))
                ink = self.tok("INK")
                if i == 1 and m.get("pv_off"):         # DN-49: Pin to Taskbar dimmed at 28 pins (ctxmenu.DIM)
                    ink = mix_px(self.tok("SURF1"), ink, 90)
                self.say(row, y, lx + 10 * Z, bt, 32, rx, word, ink, F_NAME)

    # DN-47: kit/plane.ci's power button and menu
    PB_D, PM_W, PM_R, PM_PAD, PM_ROW, PM_SIDE, PM_SYM_GAP, PM_GAP = 28, 168, 8, 6, 28, 10, 10, 6
    DOT = 6
    PM_ACT = (4, 6, 5, 3, 2)                 # DN-52 (d): Lock, Switch User, Sleep, Shut Down, Restart
    PM_DIM = 102                             # Switch User and Sleep, coming features: 40 percent, never focused

    def pm_shown(self, k):
        a = self.PM_ACT[k]
        return bool(self.m["plock"]) if a in (4, 6) else True

    def pm_live(self, k):
        return self.pm_shown(k) and self.PM_ACT[k] not in (5, 6)

    def pm_rows(self):
        return sum(self.pm_shown(k) for k in range(len(self.PM_ACT)))

    def pb_x0(self):
        return self.col_x1() - self.PB_D

    def pb_y0(self):
        return self.foot_y0() + (self.FOOT_H - self.PB_D) // 2

    def pm_x0(self):
        return self.col_x1() - self.PM_W

    def pm_h(self):
        return 2 * self.PM_PAD + self.PM_ROW * self.pm_rows()

    def pm_y0(self):
        return self.pb_y0() - self.PM_GAP - self.pm_h()

    def power_open(self):
        return bool(self.m["pm"]) or self.m["armed"] >= 0

    def footer_row(self, row, y):
        """kit/plane.ci footer_row (DN-46 (b), DN-47): the RULE line and the power button, nothing else."""
        Z = self.Z
        y0 = self.foot_y0() * Z
        if y < y0 or y >= (self.PL_TOP + self.plate_h()) * Z:
            return
        x0 = self.col_x0() * Z
        sh_rect(row, y, x0, y0, self.col_x1() * Z, y0 + Z, self.tok("BAR_RULE"))
        by0 = self.pb_y0() * Z
        if y < by0 or y >= (self.pb_y0() + self.PB_D) * Z:
            return
        bx0 = self.pb_x0() * Z
        if self.power_open() or self.m["phot"] or self.m["pfoc"]:
            g = 0x24272b if self.m["theme"] == 0 else self.tok("SURF1")
            sh_rounded(row, y, bx0, by0, bx0 + self.PB_D * Z, by0 + self.PB_D * Z, self.PB_D * Z // 2, g)
        sym_row(row, y, bx0 + (self.PB_D - 16) * Z // 2, by0 + (self.PB_D - 16) * Z // 2, SYM[5]["POWER"], Z,
                self.tok("INK"), self.m["theme"], 256)

    def power_menu_row(self, row, y):
        """kit/plane.ci power_menu_row."""
        if not self.power_open():
            return
        Z = self.Z
        mx0, my0 = self.pm_x0() * Z, self.pm_y0() * Z
        mx1, my1 = (self.pm_x0() + self.PM_W) * Z, (self.pm_y0() + self.pm_h()) * Z
        th = self.m["theme"]
        sd = sh_reach(2, th, Z, "side")          # DN-47: shadow Mid
        if my0 - sh_reach(2, th, Z, "up") <= y < my1 + sh_reach(2, th, Z, "down"):
            shade_row(row, max(mx0 - sd, 0), min(mx1 + sd, self.W), y, mx0, my0, mx1, my1, self.PM_R, 2, th, Z)
        if y < my0 or y >= my1:
            return
        sh_rounded(row, y, mx0, my0, mx1, my1, self.PM_R * Z, self.tok("SURF2"))
        sel = self.m["psel"]
        if self.m["armed"] >= 0:
            sel = self.PM_ACT.index(self.m["armed"])
        n = 0
        names = SYM[5]
        for k in range(len(self.PM_ACT)):
            if not self.pm_shown(k):
                continue
            ry = self.pm_y0() + self.PM_PAD + self.PM_ROW * n
            n += 1
            if not ry * Z <= y < (ry + self.PM_ROW) * Z:
                continue
            rx0, rx1 = (self.pm_x0() + self.PM_PAD) * Z, (self.pm_x0() + self.PM_W - self.PM_PAD) * Z
            ink = self.tok("INK")
            on = k == sel and self.pm_live(k)
            dim = not self.pm_live(k)
            sa = 256
            if on:
                sh_rounded(row, y, rx0, ry * Z, rx1, (ry + self.PM_ROW) * Z, self.PM_ROW * Z // 2, self.tok("FILL"))
                ink = self.tok("ON_FILL")
            if dim:
                ink = mix_px(self.tok("SURF2"), self.tok("INK"), self.PM_DIM)
                sa = self.PM_DIM
            a = self.PM_ACT[k]
            sym = {4: "LOCK", 6: "USERS", 5: "MOON", 3: "POWER", 2: "REFRESH"}[a] + ("_MONO" if on or dim else "")
            sx = rx0 + self.PM_SIDE * Z
            sk = self.tok("ON_FILL") if on else self.tok("INK")
            sym_row(row, y, sx, (ry + (self.PM_ROW - 16) // 2) * Z, names[sym], Z, sk, self.m["theme"], sa)
            word = {4: b"Lock", 6: b"Switch User", 5: b"Sleep", 3: b"Shut Down", 2: b"Restart"}[a]
            self.say(row, y, sx + (16 + self.PM_SYM_GAP) * Z, ry, self.PM_ROW, rx1, word, ink, F_BODY)

    # DN-5, sheet frame 7: kit/plane.ci's picker
    PK_FIELD_W, PK_FIELD_H, PK_TOP, PK_GRID_W, PK_COLS, PK_CELL_H, PK_GAP, DOT = 480, 44, 40, 800, 5, 148, 16, 6

    def pk_grid_w(self):
        return min(self.WP - 2 * self.MARGIN, self.PK_GRID_W)

    def pk_box(self, k):
        g = self.pk_grid_w()
        x0 = (self.WP - g) // 2
        i = k % self.PK_COLS
        bx0 = x0 + i * (g + self.PK_GAP) // self.PK_COLS
        bx1 = x0 + (i + 1) * (g + self.PK_GAP) // self.PK_COLS - self.PK_GAP
        by0 = self.PK_TOP * 2 + self.PK_FIELD_H + (k // self.PK_COLS) * (self.PK_CELL_H + self.PK_GAP)
        return bx0, by0, bx1, by0 + self.PK_CELL_H

    def picker_paint(self, row, y):
        Z, pk = self.Z, self.m["picker"]
        fw = min(self.WP - 2 * self.MARGIN, self.PK_FIELD_W)
        x0 = (self.WP - fw) // 2 * Z
        x1 = x0 + fw * Z
        y0, y1 = self.PK_TOP * Z, (self.PK_TOP + self.PK_FIELD_H) * Z
        if y0 <= y < y1:
            r = self.PK_FIELD_H // 2 * Z
            sh_rounded(row, y, x0, y0, x1, y1, r, self.tok("SURF2"))
            sh_ring(row, y, x0, y0, x1, y1, r, 2 * Z, self.tok("ULTRAMARINE"))
            sh_lens(row, y, x0 + 20 * Z, (self.PK_TOP + 14) * Z, Z, self.tok("INK"))
            tx = x0 + 48 * Z
            if not pk["q"]:
                self.say(row, y, tx, self.PK_TOP, self.PK_FIELD_H, x1 - 20 * Z, b"Search apps", self.tok("INK_DIM"),
                         tw.SEARCH)
            else:
                self.say(row, y, tx, self.PK_TOP, self.PK_FIELD_H, x1 - 20 * Z, pk["q"], self.tok("INK"), tw.SEARCH)
                e = tx + self.tw(pk["q"], tw.SEARCH)
                b = self.base_of(self.PK_TOP, self.PK_FIELD_H, tw.SEARCH)
                fa = tw.face(tw.SEARCH, Z)
                sh_rect(row, y, e + Z, b - fa.ascent, e + 3 * Z, b + fa.descent, self.tok("INK"))
        n = 0
        for k in range(len(pk["list"])):
            if self.pk_box(k)[3] <= self.HP - 48:
                n = k + 1
        sel, hv, pr = pk["sel"], pk["hv"], pk["pr"]
        if 0 <= hv < n and hv != sel:
            bx0, by0, bx1, by1 = self.pk_box(hv)
            sh_rounded(row, y, bx0 * Z, by0 * Z, bx1 * Z, by1 * Z, 16 * Z, self.tok("SURF2"))
        if sel < n:
            bx0, by0, bx1, by1 = self.pk_box(sel)
            px0, py0 = bx0 * Z, by0 * Z
            if self.m["pill_dom"] == 4:
                px0, py0 = self.pill_now()
            sh_rounded(row, y, px0, py0, px0 + (bx1 - bx0) * Z, py0 + self.PK_CELL_H * Z, 16 * Z, self.tok("FILL"))
        for k in range(n):
            bx0, by0, bx1, by1 = self.pk_box(k)
            if by0 * Z <= y < by1 * Z:
                icon, dot, name = pk["list"][k]   # DN-39 (e): the dot means open windows
                cx = (bx0 + bx1) * Z // 2
                v = anim_value(pk["sizes"][k], self.m["now"])
                if v <= 0:
                    v = (72 if k == pr else 88 if k in (hv, sel) else 80) * Z
                gr = self.tok("FILL") if k == sel else self.tok("SURF2") if k == hv else self.tok("MANTLE")
                self.icon_d(row, y, cx, (by0 + 59) * Z, icon, v, gr)
                w = self.tw(name, F_NAME)
                lx = cx - w // 2
                if dot:                      # DN-22: 6 px under the name's baseline, centered under the icon
                    dy0 = self.base_of(by0 + 115, 13, F_NAME) + 6 * Z
                    dx0 = cx - self.DOT * Z // 2
                    sh_rounded(row, y, dx0, dy0, dx0 + self.DOT * Z, dy0 + self.DOT * Z, self.DOT * Z // 2, self.tok("OCHRE"))
                ink = self.tok("ON_FILL") if k == sel else self.tok("INK")
                self.say(row, y, lx, by0 + 115, 13, bx1 * Z, name, ink, F_NAME)

    def paint(self, y, width):
        """kit/plane.ci paint: device row y, width pixels."""
        Z = self.Z
        if self.m["picker"] is not None:
            row = [self.tok("MANTLE") & 0xFFFFFF] * width
            self.picker_paint(row, y)
            return row
        row = [self.tok("PAPER") & 0xFFFFFF] * width     # the proof's desk under the scrim (tests/ff/plane_proof.ci)
        self.plate_row(row, y, width)
        self.field_row(row, y)
        if not self.qn:
            self.lay_rest()
            self.grid_row(row, y)
            if self.band_y0() * Z <= y < self.band_y1() * Z:
                self.rest_band(row, y)
        else:
            self.lay_query()
            if self.band_y0() * Z <= y < self.band_y1() * Z:
                self.query_band(row, y)
        self.footer_row(row, y)
        self.power_menu_row(row, y)
        if self.m["am"] is not None:
            self.pin_menu_row(row, y)
        else:
            self.pin_tip_row(row, y)
        return row

    # DN-39 (d), DN-49: kit/plane.ci's pin menu (frame 7's app menu)
    AM_W, AM_PAD, AM_ROW, AM_HEAD, AM_DIV = 248, 6, 28, 24, 11

    def am_h(self, k):
        return self.AM_HEAD if k == 0 else self.AM_DIV if k == 5 else self.AM_ROW

    def pin_menu_row(self, row, y):
        Z, am = self.Z, self.m["am"]
        rows = am["rows"]
        hh = 2 * self.AM_PAD + sum(self.am_h(k) for k, _ in rows)
        x0, y0 = am["x"] * Z, am["y"] * Z
        x1, y1 = (am["x"] + self.AM_W) * Z, (am["y"] + hh) * Z
        th = self.m["theme"]
        sd = sh_reach(2, th, Z, "side")
        if y0 - sh_reach(2, th, Z, "up") <= y < y1 + sh_reach(2, th, Z, "down"):
            shade_row(row, max(x0 - sd, 0), min(x1 + sd, self.W), y, x0, y0, x1, y1, 8, 2, th, Z)
        if y < y0 or y >= y1:
            return
        sh_rounded(row, y, x0, y0, x1, y1, 8 * Z, self.tok("SURF2"))
        rx0, rx1 = (am["x"] + self.AM_PAD) * Z, (am["x"] + self.AM_W - self.AM_PAD) * Z
        t = am["y"] + self.AM_PAD
        for r, (k, ref) in enumerate(rows):
            rh = self.am_h(k)
            if t * Z <= y < (t + rh) * Z:
                if k == 5:
                    sh_rect(row, y, rx0 + 8 * Z, (t + 5) * Z, rx1 - 8 * Z, (t + 6) * Z, self.tok("RULE"))
                elif k == 0:
                    self.say(row, y, rx0 + 10 * Z, t, self.AM_HEAD, rx1, b"OPEN WINDOWS", self.tok("INK_DIM"), F_LABEL)
                else:
                    ink, dim = self.tok("INK"), self.tok("INK_DIM")
                    if r == am["sel"]:
                        sh_rounded(row, y, rx0, t * Z, rx1, (t + self.AM_ROW) * Z, self.AM_ROW // 2 * Z, self.tok("FILL"))
                        ink = dim = self.tok("ON_FILL")
                    side = b""
                    if k == 1:
                        icon, desk, mini, title, path = self.m["windows"][ref]
                        word = title
                        side = b"Minimized" if mini else b"Desktop %d" % desk
                    else:
                        word = {2: b"New Window", 3: b"Unpin from Taskbar", 4: b"Close All Windows"}[k]
                    sx = rx1 - 10 * Z - self.tw(side, F_BODY)
                    if side:
                        self.say(row, y, sx, t, self.AM_ROW, rx1, side, dim, F_BODY)
                    self.say(row, y, rx0 + 10 * Z, t, self.AM_ROW, sx - 10 * Z, word, ink, F_BODY)
            t += rh

    def plate_row(self, row, y, width):
        """kit/plane.ci plate_row (DN-49): the 45 percent scrim, the plate's shadow High, the MANTLE plate."""
        Z, th = self.Z, self.m["theme"]
        mix(row, 0, min(self.W, width), 0, self.SCRIM)
        x0, y0 = self.plate_x0() * Z, self.PL_TOP * Z
        x1, y1 = x0 + self.plate_w() * Z, y0 + self.plate_h() * Z
        lv = self.PL_SHADOW
        sd = sh_reach(lv, th, Z, "side")
        if y0 - sh_reach(lv, th, Z, "up") <= y < y1 + sh_reach(lv, th, Z, "down"):
            shade_row(row, max(x0 - sd, 0), min(x1 + sd, self.W), y, x0, y0, x1, y1, self.PL_R, lv, th, Z)
        if y0 <= y < y1:
            sh_rounded(row, y, x0, y0, x1, y1, self.PL_R * Z, self.tok("MANTLE"))


def plane_proof(path, out):
    """The plane's twin against a run of tests/ff/plane_proof.ci, frame by frame and row by row."""
    bad = 0
    for name, m, w, h, rows in pl_parse(path):
        p = Plane(m)
        mine = [p.paint(y, w) for y in range(h)]
        over = [b for b in p.label_boxes if b[1] < b[3] or b[2] > b[4]]
        if over:                                  # DN-49: no pin label past its cell, 4 px in from each side
            k, a0, a1, c0, c1 = over[0]
            print("FAIL  plane %s: pin %d's label [%d, %d) is past its cell's [%d, %d)" % (name, k, a0, a1, c0, c1))
            bad += 1
            continue
        diff = [y for y in range(h) if mine[y] != rows[y]]
        if diff:
            y = diff[0]
            x = next(i for i in range(w) if mine[y][i] != rows[y][i])
            print("FAIL  plane %s: %d of %d rows differ, first row %d at x %d (twin %06x, kit %06x)"
                  % (name, len(diff), h, y, x, mine[y][x], rows[y][x]))
            bad += 1
        else:
            print("PASS  plane %s: %dx%d, the kit's rows are the twin's" % (name, w, h))
        if out:
            png = load("png", "png.py")
            png.write(os.path.join(out[0], "twin-%s.png" % name), w, h, mine)
    ct.use_theme(0)
    print("plane twin: %d frames, %d differ; every pin label inside its cell" % (len(pl_parse(path)), bad))
    return 1 if bad else 0

# --- DN-6 (design note 6, l 2026-11-10 04:48Z): the twin of hdesk.ci's frames 8 to 11 ---
# Its own functions, apart from the screen's and the plane's code. Each draws one device row of one surface from
# explicit state, as the hdesk.ci function of the same name does; tests/dn6/*_test.ci pin their sums at 1x and 2x
# in both themes, and `--dn6-proof DIR` writes the proof sheets (docs/handoff/evidence/20261110-dn6/).
iw = load("iw", "iconwin.py")            # DN-5: kit/icons3.ci and kit/fileicons.ci
DN_WBAR, DN_FB, DN_BTN, DN_RAD, DN_RCTRL = 32, 2, 24, 8, 6
TPAD = 12   # frames 40, 43, 44: a terminal's cells 12 px in from its content box on each side (hdesk.ci TPAD)
DN_GLYPH = {}


def dn_glyph(k, z, x, y):
    """kit/wbglyph.ci at (DN-23): the count, 0 to 16, of pixel (x, y) of button glyph k at scale z, from the module's
    own table (tools/wbglyph.py writes it; glyph k at z after the 12 z x 12 z tables before it)."""
    if not DN_GLYPH:
        DN_GLYPH["cov"] = tw._arrays("wbglyph")["cov"]
        at, n = [], 0
        for kk in range(4):
            for zz in (1, 2, 3):
                at.append(n)
                n += 144 * zz * zz
        DN_GLYPH["at"] = at
    if not (0 <= k <= 3 and 1 <= z <= 3 and 0 <= x < 12 * z and 0 <= y < 12 * z):
        return 0
    return DN_GLYPH["cov"][DN_GLYPH["at"][3 * k + z - 1] + 12 * z * y + x]
DN_UNDER = []


def dn_tz(s):
    """hdesk.ci tz for UI scale s: 2 at an even scale, else 1."""
    return 2 if s % 2 == 0 else 1


def dn_expand_by(row, x0, n, m):
    """hdesk.ci expand_by: row[x0..x0+n] spread to m pixels each, in place."""
    if m == 1:
        return
    px = row[x0:x0 + n]
    row[x0:x0 + n * m] = [c for c in px for _ in range(m)]


def dn_keep_at(row, x0, x1, r):
    """hdesk.ci keep_at."""
    DN_UNDER[:] = row[x0:x0 + r] + row[x1 - r:x1]


def dn_corners_at(row, x0, y0, x1, y1, r, b, e, y):
    """hdesk.ci corners_at: the four corners of [x0, x1) x [y0, y1) on row y, radius r, an outline b wide in e."""
    if y < y0 or y >= y1 or y0 + r <= y < y1 - r:
        return
    py = y1 - 1 - y if y >= y1 - r else y - y0
    for px in range(r):
        nu = no = 0
        for s in range(4):
            for t in range(4):
                dx, dy = 8 * r - (8 * px + 2 * s + 1), 8 * r - (8 * py + 2 * t + 1)
                d2 = dx * dx + dy * dy
                if d2 > 64 * r * r:
                    nu += 1
                elif d2 > 64 * (r - b) * (r - b):
                    no += 1
        ni = 16 - nu - no
        for x, k in ((x0 + px, px), (x1 - 1 - px, 2 * r - 1 - px)):
            row[x] = sum(((nu * (DN_UNDER[k] >> 8 * ch & 255) + no * (e >> 8 * ch & 255) +
                           ni * (row[x] >> 8 * ch & 255) + 8) // 16) << 8 * ch for ch in range(3))


def dn_bar_glyphs(row, cx, uw, s, g, fg, ic, nm, v, held, hov, dy):
    """hdesk.ci bar_glyphs (DN-23): the float bar's device row dy from device x cx, uw px wide at 1x."""
    z = dn_tz(s)
    pen_at(cx, 0, z, dy // (s // z))
    p_paint(row, cx, cx + uw, T[g])
    bx = cx + uw - 2 - 4 * DN_BTN
    for k in range(4):
        a = 41 if held == k else 31 if hov == k else 0
        if a:
            p_round(row, bx + DN_BTN * k, 4, bx + DN_BTN * (k + 1), 28, DN_RCTRL, mix_px(T[g], T[fg], a))
    iw.icon_at(row, PEN[3], pen_x(cx + 8), pen_y(8), ic, 16, z, T[g])
    e = p_text(row, cx + 32, 8 + TBASE, bx - 8, nm, T[fg], tw.NAME_BOLD)
    if v:
        tw.text(row, PEN[3], e + 8 * z, pen_y(8 + TBASE), pen_x(bx - 8), v, T[fg], F_PATH, z)
    dn_expand_by(row, cx, uw * z, s // z)
    gy = dy - 10 * s
    if not 0 <= gy < 12 * s:
        return
    for k in range(4):
        gx = cx + s * (uw - 2 - 4 * DN_BTN + DN_BTN * k + 6)
        for q in range(12 * s):
            c = dn_glyph(k, s, q, gy)
            if c:
                row[gx + q] = mix_px(row[gx + q], T[fg], 16 * c)


DN_RIMLESS = True                        # hdesk.ci RIMLESS (DN-24 B)
DN_RING = 1                              # hdesk.ci RING (DN-29): the ring below a bar and round a prompt, 1 px


def dn_ring_fill(rk):
    """hdesk.ci ring_fill: ULTRAMARINE's fill is FILL; a grant's color is its own."""
    return "FILL" if rk == "ULTRAMARINE" else rk


def dn_float_row(row, x0, y0, x1, y1, s, lit, rk, ic, nm, v, held, y, hov=-1, ground=None):
    """hdesk.ci float_row: a float's ring and bar on device row y, its content's ground already on the row."""
    if y < y0 or y >= y1:
        return
    if DN_RIMLESS:                       # DN-24 B: ring and bar one shape in one color; at rest neither ring nor rule
        c = "FILL" if lit else "SURF1"   # DN-27: never a grant's color
        ink = ("ON_OCHRE" if c == "OCHRE" else "ON_FILL") if lit else "INK_DIM"
        if y < y0 + DN_WBAR * s:       # DN-36: the bar, the shape's top WBAR px; nothing on its edges
            ct.paint(row, x0, x1, T[c])
            dn_bar_glyphs(row, x0 + DN_FB * s, (x1 - x0) // s - 2 * DN_FB, s, c, ink, ic, nm, v, held, hov, y - y0)
        elif lit:                      # DN-36: the shape beside and below the body, the body inset RING
            ct.paint(row, x0, x1, T[c])
            sh_lower_rounded(row, y, x0 + DN_RING * s, y0 + DN_WBAR * s, x1 - DN_RING * s, y1 - DN_RING * s,
                             (DN_RAD - DN_RING) * s, T["PAPER"] if ground is None else ground)
        return
    rt, e, g, fg = (2, T[rk], "FILL", "ON_FILL") if lit else (1, T["RULE"], "SURF1", "INK_DIM")
    if y0 + s <= y < y0 + (DN_FB + DN_WBAR) * s:
        ct.paint(row, x0 + s, x1 - s, T[g])
        dy = y - y0 - DN_FB * s
        if dy >= 0:
            dn_bar_glyphs(row, x0 + DN_FB * s, (x1 - x0) // s - 2 * DN_FB, s, g, fg, ic, nm, v, held, hov, dy)
    ct.frame(row, y, x0, y0, x1, y1, rt * s, e)


def dn_float(row, x0, y0, x1, y1, s, lit, rk, ground, ic, nm, v, held, y, hov=-1):
    """A float as hdesk.ci's win_row draws one with no content (ground, ring and bar, corners), on device row y."""
    if not y0 <= y < y1:
        return
    r = DN_RAD * s
    rnd = y < y0 + r or y >= y1 - r
    if rnd:
        dn_keep_at(row, x0, x1, r)
    ct.paint(row, x0, x1, ground)
    dn_float_row(row, x0, y0, x1, y1, s, lit, rk, ic, nm, v, held, y, hov, ground)
    if rnd:
        b, e = dn_float_edge(lit, rk, s)
        dn_corners_at(row, x0, y0, x1, y1, r, b, e, y)


def dn_float_edge(lit, rk, s):
    """hdesk.ci cut_corners for a float: the band and its color (DN-24 B: the bar's color, or none at rest)."""
    if DN_RIMLESS:
        return (0, T["FILL"]) if lit else (0, T["RULE"])   # DN-36: no stroke; the shape is the ring
    return ((2 if lit else 1) * s, T[rk] if lit else T["RULE"])


def dn_sum(rows):
    """The sum tests/dn6 pins: (s * 31 + pixel) mod 1000000007 over the rows, left to right."""
    h = 0
    for r in rows:
        for c in r:
            h = (h * 31 + c) % 1000000007
    return h


def dn_floats_frame(W, H, s, floats):
    """The device rows of a W x H 1x frame at UI scale s, MANTLE ground, with each float (x, y, w, h at 1x, lit,
    rk, ground token, icons3 icon, title, var, held) drawn in order."""
    rows = []
    for y in range(H * s):
        row = [T["MANTLE"]] * (W * s)
        for fx, fy, fw, fh, lit, rk, gt, ic, t, v, held, hov in floats:
            gr = ct.TERM_PAPER if gt == "TERM" else T[gt]
            dn_float(row, fx * s, fy * s, (fx + fw) * s, (fy + fh) * s, s, lit, rk, gr, ic, t, v, held, y, hov)
        rows.append(row)
    return rows


DN_FLOATS = [(16, 16, 440, 120, True, "ULTRAMARINE", "PAPER", 0, b"Index", b"/home/ci", -1, 1),   # Index (DN-28), hover full
             (16, 152, 400, 104, False, "ULTRAMARINE", "TERM", 1, b"sh", b"/etc", -1, 2),         # TERMINAL, hover tile
             (472, 16, 320, 96, False, "SIENNA", "TERM", 7, b"Fetch", b"/home/ci", 3, -1)]        # FETCH, close held
# DN-24: one focused surface at a time, so Fetch (holding net, SIENNA when focused) rests beside the focused Finder.
DN_FLOATS_W, DN_FLOATS_H = 808, 272




def dn_lit_of(focus, prompt):
    """hdesk.ci lit_of (DN-24): a window wears its colored bar and ring only focused with no prompt up."""
    return focus and not prompt


def dn_float_rows(row, y, s, ox, oy, prompt=False):
    """The DN_FLOATS frame's floats from 1x (ox, oy) on device row y at UI scale s; with a prompt up all at rest."""
    for fx, fy, fw, fh, lit, rk, gt, ic, t, v, held, hov in DN_FLOATS:
        lit = dn_lit_of(lit, prompt)
        gr = ct.TERM_PAPER if gt == "TERM" else T[gt]
        dn_float(row, (ox + fx) * s, (oy + fy) * s, (ox + fx + fw) * s, (oy + fy + fh) * s, s, lit, rk, gr, ic, t, v,
                 held, y, hov)


DN_GROUPS = {}                           # a proof sheet's name: its surfaces on a device row (row, y, s)
DN_GROUPS["frame8-float"] = lambda row, y, s: dn_float_rows(row, y, s, 72, 120)


DN_KP_W, DN_KP_H, DN_RPLATE, DN_RKEY = 420, 212, 12, 4


def dn_prompt_at(row, x0, y0, c, who, ic, p, y):
    """hdesk.ci prompt_at: the elevation prompt's plate at 1x from (x0, y0) through the pen."""
    x1 = x0 + DN_KP_W
    p_rect(row, x0, y0, x1, y0 + DN_KP_H, T["CADMIUM"])          # DN-36: one CADMIUM shape, the header its top 36
    p_lower_round(row, x0 + DN_RING, y0 + 36, x1 - DN_RING, y0 + DN_KP_H - DN_RING, DN_RPLATE - DN_RING, T["PAPER"])
    p_mid(row, x0, DN_KP_W, y0 + 10 + TBASE, x1, b"KERNEL ELEVATION REQUEST", T["ON_FILL"], F_LABEL)
    p_round(row, x0 + 16, y0 + 52, x1 - 16, y0 + 88, DN_RCTRL, T["SURF2"])
    ptxt(row, x0 + 28, y0 + 62, x1 - 28, c, T["INK"], F_PATH)
    ptxt(row, x0 + 16, y0 + 100, x1 - 16, b"requested from:", T["INK_DIM"], F_BODY)
    if y0 + 128 <= y < y0 + 144:
        iw.icon_at(row, PEN[3], pen_x(x0 + 16), pen_y(y0 + 128), ic, 16, PEN[0], T["PAPER"])
    px = pen_x(x1 - 16) - p_width(p, F_PATH)
    tw.text(row, PEN[3], pen_x(x0 + 40), pen_y(y0 + 128 + TBASE), px - 8 * PEN[0], who, T["INK"], F_PATH, PEN[0])
    p_right(row, x1 - 16, y0 + 128 + TBASE, p, T["INK_DIM"], F_PATH)
    kw = txt_w(b"Super+Enter", F_PATH) + 12
    rw = 12 + kw + 10 + txt_w(b"Run", F_NAME) + 12
    p_round(row, x0 + 16, y0 + 160, x0 + 16 + rw, y0 + 196, DN_RCTRL, T["CADMIUM"])
    p_ring(row, x0 + 28, y0 + 168, x0 + 28 + kw, y0 + 188, DN_RKEY, 1, T["ON_FILL"])
    p_mid(row, x0 + 28, kw, y0 + 170 + TBASE, x0 + 28 + kw, b"Super+Enter", T["ON_FILL"], F_PATH)
    ptxt(row, x0 + 38 + kw, y0 + 170, x0 + 16 + rw, b"Run", T["ON_FILL"], F_NAME)
    ew = txt_w(b"Esc", F_PATH) + 12
    fw = 12 + ew + 10 + txt_w(b"Refuse", F_NAME) + 12
    p_round(row, x1 - 16 - fw, y0 + 160, x1 - 16, y0 + 196, DN_RCTRL, T["SURF1"])
    p_ring(row, x1 - 4 - fw, y0 + 168, x1 - 4 - fw + ew, y0 + 188, DN_RKEY, 1, T["RULE"])
    p_mid(row, x1 - 4 - fw, ew, y0 + 170 + TBASE, x1 - 4 - fw + ew, b"Esc", T["INK_DIM"], F_PATH)
    ptxt(row, x1 + 6 - fw + ew, y0 + 170, x1 - 16, b"Refuse", T["INK"], F_NAME)


def dn_plate(row, x0, y0, pw, ph, s, rad, b, e, ground, draw, y):
    """A desk plate as hdesk.ci's win_row draws the OV window: what is under its corner rows kept, its ground, its
    1x drawing draw(row, x0, y0, y1x) through the pen at the zoom from device (x0, y0), spread by s / z, the corners
    (radius rad and an outline b wide in e, both at 1x)."""
    x1, y1 = x0 + pw * s, y0 + ph * s
    if not y0 <= y < y1:
        return
    r = rad * s
    rnd = y < y0 + r or y >= y1 - r
    if rnd:
        dn_keep_at(row, x0, x1, r)
    ct.paint(row, x0, x1, ground)
    z = dn_tz(s)
    pen_at(x0, y0, z, y0 + (y - y0) // (s // z))
    draw(row, x0, y0, y0 + (y - y0) // s)
    dn_expand_by(row, x0, pw * z, s // z)
    if rnd:
        dn_corners_at(row, x0, y0, x1, y1, r, b * s, e, y)


DN_PROMPT = (b"ced /etc/hosts", b"cish  /home/ci/kit", 1, b"pid 9")


def dn_prompt_rows(row, y, s, ox, oy):
    """The elevation prompt of DN_PROMPT with its 1x top left at (ox, oy), on device row y at UI scale s."""
    c, who, ic, p = DN_PROMPT
    dn_plate(row, ox * s, oy * s, DN_KP_W, DN_KP_H, s, DN_RPLATE, 0, T["CADMIUM"], T["PAPER"],
             lambda r, x0, y0, y1: dn_prompt_at(r, x0, y0, c, who, ic, p, y1), y)


def dn_frame(W, H, s, fn):
    """The device rows of a W x H 1x frame at UI scale s, MANTLE ground, fn(row, y, s) drawing on each."""
    rows = []
    for y in range(H * s):
        row = [T["MANTLE"]] * (W * s)
        fn(row, y, s)
        rows.append(row)
    return rows


DN_GROUPS["frame8-prompt"] = lambda row, y, s: (dn_float_rows(row, y, s, 72, 60, True),
                                                dn_prompt_rows(row, y, s, (1920 // s - DN_KP_W) // 2,
                                                               28 + (1080 // s - 28 - DN_KP_H) // 2))


DN_KP_H2 = 300


def dn_ring_type(rc):
    """hdesk.ci ring_type: a ring color's ink."""
    return "ON_OCHRE" if rc == "OCHRE" else "ON_FILL"


def dn_prompt_ac_at(row, x0, y0, rc, hd, par, sb, kd, ti, fd, ic, rt, np, bad, dx, nt, ky, go, y):
    """hdesk.ci prompt_ac_at: the approval prompt with its passphrase field (AC-1c with DN-6 frame 8, laid out as
    FV-1's draft, frame 17) at 1x from (x0, y0) through the pen, in ring color rc; np the passphrase's length (dots
    only), bad after a wrong passphrase, dx the field's shake."""
    x1 = x0 + DN_KP_W
    on = dn_ring_type(rc)
    p_rect(row, x0, y0, x1, y0 + DN_KP_H2, T[rc])                # DN-36: one shape in rc, the header its top 36
    p_lower_round(row, x0 + DN_RING, y0 + 36, x1 - DN_RING, y0 + DN_KP_H2 - DN_RING, DN_RPLATE - DN_RING, T["PAPER"])
    p_mid(row, x0, DN_KP_W, y0 + 10 + TBASE, x1, hd, T[on], F_LABEL)
    p_round(row, x0 + 16, y0 + 52, x1 - 16, y0 + 88, DN_RCTRL, T["SURF2"])
    if par:
        p_round(row, x0 + 28, y0 + 66, x0 + 36, y0 + 74, 4, T[rc])
        kx = pen_x(x1 - 28) - p_width(kd, F_BODY)
        tw.text(row, PEN[3], pen_x(x0 + 44), pen_y(y0 + 62 + TBASE), kx - 8 * PEN[0], sb, T["INK"], F_NAME_BOLD, PEN[0])
        p_right(row, x1 - 28, y0 + 62 + TBASE, kd, T["INK_DIM"], F_BODY)
    else:
        ptxt(row, x0 + 28, y0 + 62, x1 - 28, sb, T["INK"], tw.MONO_BOLD)   # DN-26: mono 13/600
    ptxt(row, x0 + 16, y0 + 100, x1 - 16, b"requested from:", T["INK_DIM"], F_BODY)
    if y0 + 125 <= y < y0 + 141:
        iw.icon_at(row, PEN[3], pen_x(x0 + 16), pen_y(y0 + 125), ic, 16, PEN[0], T["PAPER"])
    z = PEN[0]
    px = pen_x(x1 - 16) - p_width(rt, F_PATH)
    bl, tx = pen_y(y0 + 125 + TBASE), pen_x(x0 + 40)
    tw.text(row, PEN[3], tx, bl, px - 8 * z, ti, T["INK"], F_PATH, z)
    fx = tx + p_width(ti, F_PATH) + 8 * z
    room = px - 8 * z - fx
    if fd and room > 0:
        f = fd
        if p_width(fd, F_PATH) > room:   # DN-26: the folder cut from its left behind `...`
            k = 1
            while k < len(fd) and p_width(b"...", F_PATH) + p_width(fd[k:], F_PATH) > room:
                k += 1
            f = b"..." + fd[k:]
        tw.text(row, PEN[3], fx, bl, px - 8 * z, f, T["INK"], F_PATH, z)
    p_right(row, x1 - 16, y0 + 125 + TBASE, rt, T["INK_DIM"], F_PATH)
    fr = "CADMIUM" if bad else "ULTRAMARINE"
    p_round(row, x0 + 16 + dx, y0 + 157, x1 - 16 + dx, y0 + 193, DN_RCTRL, T["SURF2"])
    p_ring(row, x0 + 16 + dx, y0 + 157, x1 - 16 + dx, y0 + 193, DN_RCTRL, 2, T[fr])
    d = min(np, (DN_KP_W - 56) // 14)
    for k in range(d):
        p_round(row, x0 + 28 + dx + 14 * k, y0 + 171, x0 + 36 + dx + 14 * k, y0 + 179, 4, T["INK"])
    p_rect(row, x0 + 28 + dx + 14 * d, y0 + 166, x0 + 30 + dx + 14 * d, y0 + 184, T["INK"])
    ptxt(row, x0 + 16, y0 + 201, x1 - 16, nt, T["INK_DIM"], F_SMALL)
    kw = txt_w(ky, F_PATH) + 12
    rw = 12 + kw + 10 + txt_w(go, F_NAME) + 12
    p_round(row, x0 + 16, y0 + 248, x0 + 16 + rw, y0 + 284, DN_RCTRL, T[rc])
    p_ring(row, x0 + 28, y0 + 256, x0 + 28 + kw, y0 + 276, DN_RKEY, 1, T[on])
    p_mid(row, x0 + 28, kw, y0 + 258 + TBASE, x0 + 28 + kw, ky, T[on], F_PATH)
    ptxt(row, x0 + 38 + kw, y0 + 258, x0 + 16 + rw, go, T[on], F_NAME)
    ew = txt_w(b"Esc", F_PATH) + 12
    fw = 12 + ew + 10 + txt_w(b"Refuse", F_NAME) + 12
    p_round(row, x1 - 16 - fw, y0 + 248, x1 - 16, y0 + 284, DN_RCTRL, T["SURF1"])
    p_ring(row, x1 - 4 - fw, y0 + 256, x1 - 4 - fw + ew, y0 + 276, DN_RKEY, 1, T["RULE"])
    p_mid(row, x1 - 4 - fw, ew, y0 + 258 + TBASE, x1 - 4 - fw + ew, b"Esc", T["INK_DIM"], F_PATH)
    ptxt(row, x1 + 6 - fw + ew, y0 + 258, x1 - 16, b"Refuse", T["INK"], F_NAME)


# Three states of the approval prompt (tests/dn6/prompt_ac_test.ci pins each): a child's net ask with 7 characters
# typed; a parent's own kern in AC-D2's wait; a child's disk ask just after a wrong passphrase, mid-shake (dx -4).
DN_PROMPT_AC = (
    ("SIENNA", b"PARENT APPROVAL", True, b"fetch", b"Network", b"cish", b"/home/mia", 1, b"mia", 7, False, 0,
     b"Your password, not mia's.", b"Enter", b"Approve"),
    ("CADMIUM", b"KERNEL ELEVATION REQUEST", False, b"ced /etc/hosts", b"", b"cish", b"/home/ana", 1, b"pid 9", 3,
     False, 0, b"wait 4 s", b"Super+Enter", b"Run"),
    ("OCHRE", b"PARENT APPROVAL", True, b"cp", b"Disk", b"a-long-title-16c", b"/home/mia/photos/2026/summer/raw",
     1, b"mia", 0, True, -4, b"That password did not match.", b"Enter", b"Approve"),
)


def dn_prompt_ac_rows(row, y, s, ox, oy, k=0):
    """Approval prompt state k of DN_PROMPT_AC with its 1x top left at (ox, oy), on device row y at UI scale s."""
    st = DN_PROMPT_AC[k]
    dn_plate(row, ox * s, oy * s, DN_KP_W, DN_KP_H2, s, DN_RPLATE, 0, T[st[0]], T["PAPER"],
             lambda r, x0, y0, y1: dn_prompt_ac_at(r, x0, y0, *st, y1), y)


def dn_prompt_ac_sums():
    """--prompt-ac-sums: tests/dn6/prompt_ac_test.ci's sums, a 452 x 316 frame with each state at (16, 8)."""
    for th in (0, 1):
        use_theme(th)
        for k in range(len(DN_PROMPT_AC)):
            print(th, k, [dn_sum(dn_frame(452, 316, s, lambda row, y, s: dn_prompt_ac_rows(row, y, s, 16, 8, k)))
                          for s in (1, 2, 3)])
    use_theme(0)
    return 0


DN_GROUPS["frame8-approval"] = lambda row, y, s: (dn_float_rows(row, y, s, 72, 60, True),
                                                  dn_prompt_ac_rows(row, y, s, (1920 // s - DN_KP_W) // 2,
                                                                    28 + (1080 // s - 28 - DN_KP_H2) // 2))
DN_GROUPS["frame8-approval-kern"] = lambda row, y, s: (dn_float_rows(row, y, s, 72, 60, True),
                                                  dn_prompt_ac_rows(row, y, s, (1920 // s - DN_KP_W) // 2,
                                                                    28 + (1080 // s - 28 - DN_KP_H2) // 2, 1))
DN_GROUPS["frame8-approval-wrong"] = lambda row, y, s: (dn_float_rows(row, y, s, 72, 60, True),
                                                  dn_prompt_ac_rows(row, y, s, (1920 // s - DN_KP_W) // 2,
                                                                    28 + (1080 // s - 28 - DN_KP_H2) // 2, 2))


def approval(path, shot):
    """--approval TRANSCRIPT PPM: the desk side of elevation on a child's desk (check-hybrid.sh, accounts elevation).
    sam's `grant net` (past a ceiling of disk) asks PARENT APPROVAL; on the screendump the prompt is AC-1c's in frame
    8's parts, a SIENNA plate KP_W x KP_H2 at the UI scale, centered across the screen, its header whole; Super+Enter
    with the field
    empty answers nothing; a wrong passphrase is refused; ada's grants the net bit, once; sam's `kern` asks
    again and Super+L refuses it (AC-D5) and locks; sam's passphrase unlocks with no prompt back; sam logs out. No
    passphrase reaches the transcript."""
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = gl.lines(text)
    miss = in_order(lines, [r"^hdesk: accounts 2$", r"^hdesk: login sam uid 1001$",
                            r"^hdesk: approval ask want 2 uid 1001$", r"^hdesk: approval wrong passphrase$",
                            r"^hdesk: approved by ada$", r"^hdesk: grant 2 to pid \d+$",
                            r"^hdesk: approval ask want 8 uid 1001$", r"^hdesk: kern refused pid \d+$",
                            r"^hdesk: lock sam$", r"^hdesk: unlock sam$", r"^hdesk: logout sam$"])
    once = (sum(ln.startswith("hdesk: approved by ") for ln in lines) == 1 and
            sum(ln.startswith("hdesk: approval ask want 8 ") for ln in lines) == 1)
    secret = "sevenhorsesrun" in text or "sam-pass" in text
    data = open(shot, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
    w, h, at = int(m.group(1)), int(m.group(2)), m.end()
    use_theme(0)
    oc = T["SIENNA"]
    def px(x, y):
        k = at + 3 * (y * w + x)
        return data[k] << 16 | data[k + 1] << 8 | data[k + 2]
    xs, ys = [], []
    for y in range(84, h):                    # under the bar at 3x: its AUTH pill wears the prompt's ring color
        for x in range(0, w):
            if px(x, y) == oc:
                xs.append(x)
                ys.append(y)
    plate = "none"
    good = False
    if xs:
        x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
        s = (x1 - x0) // DN_KP_W
        plate = "%dx%d at %d,%d" % (x1 - x0, y1 - y0, x0, y0)
        good = (s >= 1 and x1 - x0 == DN_KP_W * s and y1 - y0 == DN_KP_H2 * s and x0 == (w - DN_KP_W * s) // 2 and
                all(px(x, y0 + 2 * s) == oc for x in range(x0 + DN_RPLATE * s, x1 - DN_RPLATE * s)))
    ok = miss is None and once and not secret and good
    print("%s  approval: PARENT APPROVAL for net drawn in frame 8's parts (%s); Super+Enter with an empty field and a "
          "wrong passphrase answer nothing; ada's grants once; Super+L refuses sam's kern and locks; no "
          "passphrase in the transcript%s"
          % ("PASS" if ok else "FAIL", plate,
             "" if ok else ": missing %r, once %r, secret %r, plate %r" % (miss, once, secret, good)))
    return 0 if ok else 1


DN_SP_W, DN_MSG_W, DN_MSG_H = 304, 320, 36


# kit/symbols.ci's twin (DN-32, DN-34): the symbol table read from its arrays, drawn as symbols.row_at draws it.
def sym_tables():
    """kit/symbols.ci's arrays (tools/symbols.py --check keeps them its sources')."""
    src = open(os.path.join(HERE, "..", "user", "ci", "kit", "symbols.ci")).read()

    def arr(name):
        m = re.search(r"\[\d+\] %s = \[(.*?)\];" % name, src, re.S)
        return [int(v, 0) for v in re.findall(r"0x[0-9a-f]+|-?\d+", m.group(1))]
    words = arr("tok")
    toks = []
    for w in words:
        toks += [w & 0xFFFF, w >> 16]
    names = dict(re.findall(r"export const I64 ([A-Z_]+) = (\d+);", src))
    return (toks, arr("row0"), arr("first"), arr("cls"), arr("accents"), {k: int(v) for k, v in names.items()},
            arr("cls2"))


SYM = sym_tables()


def sym_row(row, y, x0, y0, k, z, ink, th, a):
    """kit/symbols.ci row_at."""
    toks, row0, first, cls, accents, _, cls2 = SYM
    r = y - y0
    if k < 0 or k >= len(cls) or not 0 <= r < 16 * z:
        return
    for L in range(3):                   # the ink, then the accents in the file's order (DN-46 (e): two)
        c3 = (None, cls[k], cls2[k])[L]
        if L > 0 and c3 < 0:
            continue
        c = ink if L == 0 else accents[2 * c3 + th]
        i = row0[first[(k * 2 + (z - 1)) * 3 + L] + r]
        x = 0
        while x < 16 * z:
            t = toks[i]
            i += 1
            if t >= 0x8000:
                x += t - 0x8000
            else:
                if 0 <= x0 + x < len(row):
                    row[x0 + x] = mix_px(row[x0 + x], c, (t * a + 128) >> 8)
                x += 1


def dn_sp_h(n):
    """hdesk.ci sp_h: the panel's height at 1x (DN-34: the Grants pill in place of the list)."""
    return 346


DN_GLYPH_SEG = [[(28, -28, -12, 0), (-12, 0, 28, 28), (28, 28, 28, -28), (-28, -28, -28, 28)],
                [(-14, -28, -14, 28), (14, -28, 14, 28)],
                [(-16, -28, 28, 0), (28, 0, -16, 28), (-16, 28, -16, -28)],
                [(-28, -28, 12, 0), (12, 0, -28, 28), (-28, 28, -28, -28), (28, -28, 28, 28)],
                [(-20, -28, 4, 0), (4, 0, -20, 28)],
                [(-16, -32, 16, 0), (16, 0, -16, 32)]]   # DN-34: the Grants pill's 12 px chevron


def dn_glyph_at(r1, y, cx, cy, gk, ink):
    """DN-24 (hdesk.ci glyph_at): transport glyph gk (0 previous, 1 pause, 2 play, 3 next) or the link's chevron (4),
    a 12 px box centered on (cx, cy), stroked 1.5 px, 4 x 4 samples a pixel, at the pen's zoom."""
    if not cy - 6 <= y < cy + 6:
        return
    z, dy = PEN[0], PEN[3]
    ox, oy = pen_x(cx), pen_y(cy)
    for px in range(pen_x(cx - 6), pen_x(cx + 6)):
        cov = 0
        for s in range(4):
            for t in range(4):
                u, v = 8 * (px - ox) + 2 * s + 1 - 4 * z, 8 * (dy - oy) + 2 * t + 1 - 4 * z
                if any(seg_d2(u, v, a * z, b * z, c * z, d * z) <= 36 * z * z for a, b, c, d in DN_GLYPH_SEG[gk]):
                    cov += 1
        if cov:
            r1[px] = sum(((cov * (ink >> 8 * ch & 255) + (16 - cov) * (r1[px] >> 8 * ch & 255) + 8) // 16) << 8 * ch
                         for ch in range(3))


def dn_seg_at(row, x0, y0, wd, labs, sel):
    """hdesk.ci seg_at: a 32 px segmented pill, labs a list of labels, segment sel FILL."""
    p_round(row, x0, y0, x0 + wd, y0 + 32, 16, T["MANTLE"])
    sw = (wd - 4) // len(labs)
    for k, t in enumerate(labs):
        sx = x0 + 2 + sw * k
        if k == sel:
            p_round(row, sx, y0 + 2, sx + sw, y0 + 30, 14, T["FILL"])
            p_mid(row, sx, sw, y0 + 8 + TBASE, sx + sw, t, T["ON_FILL"], F_NAME)
        else:
            p_mid(row, sx, sw, y0 + 8 + TBASE, sx + sw, t, T["INK_DIM"], F_BODY)


def dn_grants_text(n):
    """hdesk.ci grants_text (DN-34)."""
    return b"None" if n <= 0 else b"1 app" if n == 1 else b"%d apps" % n


def dn_grant_rows(row, x0, x1, y0, grants, y):
    """hdesk.ci grant_rows (DN-34): the per-app grant list as the panel drew it, now on Settings' Grants page."""
    for r in range(max(len(grants), 1)):
        ry = y0 + 40 * r
        if ry <= y < ry + 32:
            p_round(row, x0, ry, x1, ry + 32, 16, T["PAPER"])
            if not grants:
                ptxt(row, x0 + 12, ry + 8, x1 - 12, b"None active", T["INK_DIM"], F_BODY)
            else:
                bit, nm = grants[r]
                c = {1: "OCHRE", 8: "CADMIUM"}.get(bit, "SIENNA")
                p_round(row, x0 + 12, ry + 12, x0 + 20, ry + 20, 4, T[c])
                kind = {2: b"Network", 1: b"Disk"}.get(bit, b"Ring 0")
                p_right(row, x1 - 12, ry + 8 + TBASE, kind, T["INK_DIM"], F_BODY)
                ptxt(row, x0 + 30, ry + 8, x1 - 80, nm, T["INK"], F_NAME)


def dn_panel_at(row, x0, y0, grants, lv, th, y, np=1, pn=b"cat", ic=8, pd=b"pid 14", ctl=0):
    """hdesk.ci panel_at: the system panel's row y at 1x; grants a list of (bit, name), lv the level or -1; DN-24's
    NOW PLAYING: np 1 the player (icon ic, name pn, pid pd, controls ctl), 0 none, -1 no device."""
    x1 = x0 + DN_SP_W
    if y0 + 16 <= y < y0 + 48:                     # DN-34: the Grants pill
        p_round(row, x0 + 16, y0 + 16, x1 - 16, y0 + 48, 16, T["PAPER"])
        sym_row(row, PEN[3], pen_x(x0 + 28), pen_y(y0 + 24), SYM[5]["KEY"], PEN[0], T["INK"], th, 256)
        t = dn_grants_text(len({nm for _, nm in grants}))
        ptxt(row, x0 + 54, y0 + 24, x1 - 58 - txt_w(t, F_BODY), b"Grants", T["INK"], F_NAME)
        p_right(row, x1 - 48, y0 + 24 + TBASE, t, T["INK_DIM"], F_BODY)
        dn_glyph_at(row, y, x1 - 32, y0 + 32, 5, T["INK_DIM"])
    ny = y0 + 68
    ptxt(row, x0 + 16, ny, x1 - 16, b"NOW PLAYING", T["INK_DIM"], F_LABEL)
    p_right(row, x1 - 30, ny + 1 + TBASE, b"Sound Settings", T["INK_DIM"], F_SMALL)   # at the pen's zoom
    if ny + 3 <= y < ny + 13:
        dn_glyph_at(row, y, x1 - 21, ny + 8, 4, T["INK_DIM"])
    py = ny + 24
    if py <= y < py + 32:
        p_round(row, x0 + 16, py, x1 - 16, py + 32, 16, T["PAPER"])
        if np < 1:
            ptxt(row, x0 + 28, py + 8, x1 - 28, b"Nothing playing" if np == 0 else b"Not available", T["INK_DIM"],
                 F_BODY)
        else:
            if py + 8 <= y < py + 24:
                iw.icon_at(row, PEN[3], pen_x(x0 + 28), pen_y(py + 8), ic, 16, PEN[0], T["PAPER"])
            bx = x1 - 20 - 24 * sum(1 for b in (1, 2, 4) if ctl & b)
            ptxt(row, x0 + 52, py + 8, bx - 8, pn, T["INK"], F_NAME)
            ptxt(row, x0 + 60 + txt_w(pn, F_NAME), py + 9, bx - 8, pd, T["INK_DIM"], F_PATH)
            if ctl & 1:
                dn_glyph_at(row, y, bx + 12, py + 16, 0, T["INK"])
                bx += 24
            if ctl & 2:
                p_round(row, bx, py + 4, bx + 24, py + 28, 12, T["FILL"])
                dn_glyph_at(row, y, bx + 12, py + 16, 1 if ctl & 8 else 2, T["ON_FILL"])
                bx += 24
            if ctl & 4:
                dn_glyph_at(row, y, bx + 12, py + 16, 3, T["INK"])
    vy = ny + 76
    ptxt(row, x0 + 16, vy, x1 - 16, b"VOLUME", T["INK_DIM"], F_LABEL)
    if lv < 0:
        p_right(row, x1 - 16, vy + TBASE, b"Not available", T["INK_DIM"], F_BODY)
    if vy + 26 <= y < vy + 46:
        p_round(row, x0 + 16, vy + 26, x1 - 16, vy + 46, 10, T["PAPER"])
        if lv >= 0:
            fw = 20 + (DN_SP_W - 52) * lv // 100
            p_round(row, x0 + 16, vy + 26, x0 + 16 + fw, vy + 46, 10, T["ULTRAMARINE"])
            p_round(row, x0 + fw - 2, vy + 28, x0 + fw + 14, vy + 44, 8, T["ON_FILL"])
    ty = vy + 66
    ptxt(row, x0 + 16, ty, x1 - 16, b"THEME", T["INK_DIM"], F_LABEL)
    if ty + 24 <= y < ty + 56:
        dn_seg_at(row, x0 + 16, ty + 24, DN_SP_W - 32, [b"Dark", b"Light"], th)
    wy = ty + 76
    ptxt(row, x0 + 16, wy, x1 - 16, b"Wi-Fi", T["INK_DIM"], F_BODY)
    p_right(row, x1 - 16, wy + TBASE, b"Not available", T["INK_DIM"], F_BODY)
    ptxt(row, x0 + 16, wy + 28, x1 - 16, b"Bluetooth", T["INK_DIM"], F_BODY)
    p_right(row, x1 - 16, wy + 28 + TBASE, b"Not available", T["INK_DIM"], F_BODY)


def dn_msg_at(row, x0, y0, t, y):
    """hdesk.ci msg_at: the bar message's row y at 1x, a 6 px dot and the sentence centered together."""
    z = PEN[0]
    dx = pen_x(x0) + tdiv(DN_MSG_W * z - (16 * z + p_width(t, F_NAME)), 2)
    if y0 + 15 <= y < y0 + 21:
        sh_rounded(row, PEN[3], dx, pen_y(y0 + 15), dx + 6 * z, pen_y(y0 + 21), 3 * z, T["INK"])
    tw.text(row, PEN[3], dx + 16 * z, pen_y(y0 + 10 + TBASE), pen_x(x0 + DN_MSG_W - 16), t, T["INK"], F_NAME, z)


def dn_panel_plate(row, y, s, x0, y0, grants, lv, th, np=1, pn=b"cat", pd=b"pid 14"):
    """The panel as the OV window from device (x0, y0) at UI scale s; the player as NOW PLAYING draws it (DN-24)."""
    dn_plate(row, x0, y0, DN_SP_W, dn_sp_h(len(grants)), s, DN_RPLATE, 0, 0, T["SURF2"],
             lambda r, a, b, y1: dn_panel_at(r, a, b, grants, lv, th, y1, np, pn, 8, pd), y)


def dn_msg_plate(row, y, s, x0, y0, t):
    """The bar message as the OV window from device (x0, y0) at UI scale s."""
    dn_plate(row, x0, y0, DN_MSG_W, DN_MSG_H, s, DN_MSG_H // 2, 0, 0, T["SURF1"],
             lambda r, a, b, y1: dn_msg_at(r, a, b, t, y1), y)


DN_PANEL = ([(2, b"fetch"), (1, b"ced")], 64)
DN_MSG = b"No free Console. 8 of 8 are open."


def dn_frame9(row, y, s, W1):
    """Frame 9 on a screen W1 wide at 1x: the panel at its place (8 under the bar, 8 from the right) and the bar
    message centered 12 under the bar, with the theme the twin draws."""
    g, lv = DN_PANEL
    dn_panel_plate(row, y, s, (W1 - DN_SP_W - 8) * s, 36 * s, g, lv, DN_TH[0])
    dn_msg_plate(row, y, s, (W1 - DN_MSG_W) // 2 * s, 40 * s, DN_MSG)


DN_TH = [0]
DN_GROUPS["frame9-panel"] = lambda row, y, s: dn_frame9(row, y, s, 1920 // s)
DN_GROUPS["frame9-transport"] = lambda row, y, s: dn_plate(
    row, (1920 // s - DN_SP_W - 8) * s, 36 * s, DN_SP_W, dn_sp_h(2), s, DN_RPLATE, 0, 0, T["SURF2"],
    lambda r, a, b, y1: dn_panel_at(r, a, b, DN_PANEL[0], DN_PANEL[1], DN_TH[0], y1, 1, b"cat", 8, b"pid 14", 15), y)


DN_SW_T, DN_SW_H = 116, 148


def dn_switcher_at(row, x0, y0, tiles, sel, y):
    """hdesk.ci switcher_at: the switcher's row y at 1x; tiles a list of (icons3 icon, name)."""
    for k, (ic, t) in enumerate(tiles):
        tx, ty = x0 + 16 + (DN_SW_T + 8) * k, y0 + 16
        if k == sel:
            s, g = 64, T["FILL"]
            p_round(row, tx, ty, tx + DN_SW_T, ty + DN_SW_T, 12, g)
            p_mid(row, tx, DN_SW_T, ty + 82 + TBASE, tx + DN_SW_T, t, T["ON_FILL"], tw.NAME_BOLD)
        else:
            s, g = 56, T["SURF2"]
            p_mid(row, tx, DN_SW_T, ty + 82 + TBASE, tx + DN_SW_T, t, T["INK"], F_BODY)
        iy = ty + 46 - s // 2
        if iy <= y < iy + s:
            iw.icon_at(row, PEN[3], pen_x(tx + (DN_SW_T - s) // 2), pen_y(iy), ic, s, PEN[0], g)


def dn_switcher_plate(row, y, s, x0, y0, tiles, sel):
    """The switcher as the OV window from device (x0, y0) at UI scale s."""
    pw = 32 + DN_SW_T * len(tiles) + 8 * (len(tiles) - 1)
    dn_plate(row, x0, y0, pw, DN_SW_H, s, 16, 0, 0, T["SURF2"],
             lambda r, a, b, y1: dn_switcher_at(r, a, b, tiles, sel, y1), y)


DN_TILES = [(0, b"Index"), (1, b"sh"), (2, b"Edit"), (1, b"sh"), (3, b"Settings")]   # DN-28


def dn_frame10(row, y, s, W1, H1):
    """Frame 10: the five tiles of DN_TILES, the third selected, centered on the plane."""
    pw = 32 + DN_SW_T * 5 + 8 * 4
    dn_switcher_plate(row, y, s, (W1 - pw) // 2 * s, (28 + (H1 - 28 - DN_SW_H) // 2) * s, DN_TILES, 2)


DN_GROUPS["frame10-switcher"] = lambda row, y, s: dn_frame10(row, y, s, 1920 // s, 1080 // s)


def dn_toolbar_at(row, y, w, live, p, focus, sel, q, ph):
    """finder.ci toolbar_at (DN-7): the Finder toolbar's row y at 1x, w wide; q the filter, or ph its placeholder."""
    if not 6 <= y < 34:
        return
    for b, g in enumerate((b"<", b">", b"^")):
        bx = 8 + 32 * b
        t = T["INK"] if live & (1 << b) else T["INK_DIM"]
        txt(row, y, bx + (28 - txt_w(g, F_BODY)) // 2, 12, bx + 28, g, t, F_BODY)
    fx, x0 = w - 176, 108
    x1 = fx - 8
    sh_rounded(row, y, x0, 6, x1, 34, 14, T["SURF1"])
    kw = txt_w(b"Ctrl+L", F_LABEL) + 10
    te = x1 - 12
    if not focus:
        te = x1 - 18 - kw
        sh_rounded(row, y, x1 - 6 - kw, 11, x1 - 6, 29, 4, T["PAPER"])
        txt(row, y, x1 - 1 - kw, 12, x1 - 6, b"Ctrl+L", T["INK_DIM"], F_LABEL)
    if focus and sel and p:
        pw = min(txt_w(p, F_PATH), te - x0 - 12)
        sh_rounded(row, y, x0 + 10, 10, x0 + 14 + pw, 30, 4, T["FILL"])
        txt(row, y, x0 + 12, 12, te, p, T["ON_FILL"], F_PATH)
    else:
        e = txt(row, y, x0 + 12, 12, te, p, T["INK"], F_PATH)
        if focus and 11 <= y < 29:
            ct.paint(row, e + 1, e + 2, T["INK"])
    if focus:
        sh_ring(row, y, x0, 6, x1, 34, 14, 2, T["ULTRAMARINE"])
    sh_rounded(row, y, fx, 6, w - 8, 34, 14, T["SURF1"])
    if q:
        txt(row, y, fx + 12, 12, w - 20, q, T["INK"], F_BODY)
    else:
        txt(row, y, fx + 12, 12, w - 20, ph, T["INK_DIM"], F_BODY)


DN_TOOLBARS = [(5, b"/home/ci", False, False, b"", b"Filter ci..."),
               (7, b"/home/ci/kit", True, True, b"", b"Filter kit..."),
               (2, b"/bin/", True, False, b"ce", b"")]
DN_ROWS = [(b"kit", True), (b"notes.txt", False), (b"hdesk.ci", False), (b"shot.PNG", False), (b"doom1.wad", False)]


def dn_finder_frame(W, sel_y=None):
    """Finder's frame of DN-7 and DN-9 at 1x (Finder draws at 1x; FD-2X A doubles it): three toolbars stacked, then
    five 26 px rows each a 16 px file icon at 8 and its name 26 px further, on PAPER."""
    rows = []
    for y in range(3 * 40 + 5 * 26):
        row = [T["PAPER"]] * W
        if y < 120:
            live, p, focus, sel, q, ph = DN_TOOLBARS[y // 40]
            dn_toolbar_at(row, y % 40, W, live, p, focus, sel, q, ph)
        else:
            k, ry = (y - 120) // 26, (y - 120) % 26
            name, d = DN_ROWS[k]
            iw.file_at(row, ry, 8, 4, iw.kind(name, d), 16, 1)
            txt(row, ry, 34, 5, W - 8, name, T["INK"], F_NAME)
        rows.append(row)
    return rows


def dn_finder_rows(row, y, s, ox, oy, W):
    """The Finder frame at 1x from (ox, oy), pixel-doubled to the UI scale s (FD-2X A), on device row y."""
    fr = DN_FINDER.get((ct.TOK["PAPER"], W))
    if fr is None:
        fr = DN_FINDER[(ct.TOK["PAPER"], W)] = dn_finder_frame(W)
    k = y // s - oy
    if 0 <= k < len(fr):
        row[ox * s:(ox + W) * s] = spread_by(fr[k], s)


DN_FINDER = {}
DN_GROUPS["dn7-finder"] = lambda row, y, s: (dn_float_rows(row, y, s, 72, 60),
                                             dn_finder_rows(row, y, s, 72, 420, 880))


# DN-10 (frame 11): what the desk still draws of it. The old Settings float, its sidebar and its pages' table are
# retired (DN-50, PR 412); the pages are the kit's (kit/stside.ci, kit/stpage.ci, kit/stbox.ci) with their own proof
# (tests/rs/side_proof.ci) and tests (tests/rs). The desk's own pages (Display, Sound, Grants, About) keep their rows
# (st_line, grant_rows), the Resolution menu (res_menu, menu_shadow) and the revert prompt (revert_at), twinned here.
DN_RV_W, DN_RV_H = 420, 160
DN_RES = [(1280, 720), (1360, 768), (1600, 900), (1920, 1080), (1920, 1200), (2560, 1440), (2560, 1600), (3840, 2160),
          (2560, 1080), (3440, 1440), (3840, 1600), (5120, 1440), (720, 1280), (1080, 1920), (1200, 1920),
          (1440, 2560), (1600, 2560), (2160, 3840), (1024, 768), (800, 600), (640, 480)]
DN_RES_AT = [0, 8, 12, 18, 21]


def dn_res_text(rw, rh):
    return b"%d x %d" % (rw, rh)


def dn_st_line(row, cx, ry, cr, what, focus, s, y, pn=b"cat"):
    """hdesk.ci st_line: one 40 px Settings row (DN-46); pn the player's name (DN-25)."""
    ink, dim = T["INK"], T["INK_DIM"]

    def lab(t, room):                    # DN-46: the label alone, no helper sentence
        ptxt(row, cx, ry + 12, cr - room, t, ink, F_NAME)
    if what == 1:
        lab(b"Theme", 184)
        if ry + 4 <= y < ry + 36:
            dn_seg_at(row, cr - 176, ry + 4, 176, [b"Dark", b"Light"], s[2])
    elif what == 2:
        lab(b"Size", 184)
        if ry + 4 <= y < ry + 36:
            dn_seg_at(row, cr - 176, ry + 4, 176, [b"1x", b"2x", b"3x"], s[3] - 1)
    elif what == 3:
        lab(b"Motion", 52)
        if ry + 8 <= y < ry + 32:
            if s[4] == 1:
                p_round(row, cr - 44, ry + 8, cr, ry + 32, 12, T["FILL"])
                p_round(row, cr - 22, ry + 10, cr - 2, ry + 30, 10, T["ON_FILL"])
            else:
                p_round(row, cr - 44, ry + 8, cr, ry + 32, 12, T["SURF1"])
                p_round(row, cr - 42, ry + 10, cr - 22, ry + 30, 10, T["INK_DIM"])
    elif what == 4:
        lab(b"Screen shape", 344)
        if ry + 4 <= y < ry + 36:
            dn_seg_at(row, cr - 336, ry + 4, 336, [b"Landscape", b"Ultrawide", b"Portrait", b"Legacy"], s[5])
    elif what == 5:
        ptxt(row, cx, ry + 12, cr - 184, b"Resolution", ink, F_NAME)
        t = dn_res_text(s[6], s[7])
        if s[8] == 1:
            p_right(row, cr, ry + 12 + TBASE, t, dim, F_PATH)
        else:
            if ry + 4 <= y < ry + 36:
                p_round(row, cr - 176, ry + 4, cr, ry + 36, DN_RCTRL, T["SURF1"])
            ptxt(row, cr - 164, ry + 12, cr - 24, t, ink, F_PATH)
            sym_row(row, PEN[3], pen_x(cr - 23), pen_y(ry + 12), SYM[5]["UP_MONO" if s[9] == 1 else "DOWN_MONO"],
                    PEN[0], ink, THEME[0], 256)
    elif what == 6:
        lab(b"Tiling", 344)
        if ry + 4 <= y < ry + 36:
            dn_seg_at(row, cr - 336, ry + 4, 336, [b"Long side", b"Columns", b"Rows"], s[11])
    elif what == 7:
        ptxt(row, cx, ry + 12, cr - 248, b"Volume", ink if s[13] >= 0 else dim, F_NAME)
        if ry + 10 <= y < ry + 30:
            p_round(row, cr - 240, ry + 10, cr, ry + 30, 10, T["MANTLE"])
            if s[13] >= 0:
                fw = 20 + 220 * s[13] // 100
                p_round(row, cr - 240, ry + 10, cr - 240 + fw, ry + 30, 10, T["ULTRAMARINE"])
                p_round(row, cr - 258 + fw, ry + 12, cr - 242 + fw, ry + 28, 8, T["INK"])
    elif what == 12:
        lab(b"Output", 184)
        if s[13] < 0:
            p_right(row, cr, ry + 12 + TBASE, b"Not available", dim, F_BODY)
        else:
            p_right(row, cr, ry + 12 + TBASE, b"Built-in audio", dim, F_BODY)   # frame 22
    elif what == 13:
        ptxt(row, cx, ry + 12, cr - 248, b"Now playing", ink, F_NAME)
        if s[14] == 1:
            t = b"pid %d" % s[15]
            pw = p_width(t, F_PATH)
            p_right(row, cr, ry + 12 + TBASE, t, dim, F_PATH)
            nx = pen_x(cr) - pw - 8 * PEN[0] - p_width(pn, F_NAME)
            tw.text(row, PEN[3], nx, pen_y(ry + 12 + TBASE), pen_x(cr) - pw - 8 * PEN[0], pn, ink, F_NAME, PEN[0])
        else:
            p_right(row, cr, ry + 12 + TBASE, b"Nothing playing" if s[14] == 0 else b"Not available", dim, F_BODY)
    elif what in (8, 9, 10):
        name = {8: b"Version", 9: b"Screen", 10: b"Storage"}[what]
        ptxt(row, cx, ry + 12, cr - 184, name, ink, F_NAME)
        if what == 8:
            p_right(row, cr, ry + 12 + TBASE, b"Daphnis 0.1.0", dim, F_BODY)
        elif what == 9:
            p_right(row, cr, ry + 12 + TBASE, dn_res_text(s[6], s[7]), dim, F_PATH)
        else:
            p_right(row, cr, ry + 12 + TBASE, b"Volume on /home" if s[12] == 1 else b"No volume", dim, F_BODY)
    if focus and ry + 0 <= y < ry + 40:
        if what in (1, 2):
            p_focus_ring(row, cr - 176, ry + 4, cr, ry + 36, 16, T["PAPER"], T["ULTRAMARINE"])   # DN-40
        if what in (4, 6):
            p_focus_ring(row, cr - 336, ry + 4, cr, ry + 36, 16, T["PAPER"], T["ULTRAMARINE"])   # DN-40
        if what == 5 and s[8] == 0:
            p_focus_ring(row, cr - 176, ry + 4, cr, ry + 36, DN_RCTRL, T["PAPER"], T["ULTRAMARINE"])   # DN-42
        if what == 7 and s[13] >= 0:
            p_ring(row, cr - 242, ry + 8, cr + 2, ry + 32, 12, 2, T["ULTRAMARINE"])
    if focus and what == 3 and ry + 6 <= y < ry + 34:
        p_ring(row, cr - 46, ry + 6, cr + 2, ry + 34, 14, 2, T["ULTRAMARINE"])


def dn_res_menu(row, cr, yb, s, y):
    """hdesk.ci res_menu: the Resolution menu, its right edge cr and bottom yb."""
    a = DN_RES_AT[s[5]]
    n = DN_RES_AT[s[5] + 1] - a
    mh = 12 + 28 * n + 2 * (n - 1)
    x0, y0 = cr - 240, yb - mh
    if not y0 <= y < yb:
        return
    p_round(row, x0, y0, cr, yb, DN_RAD, T["SURF1"])
    for k in range(n):
        ry = y0 + 6 + 30 * k
        fg, dim = T["INK"], T["INK_DIM"]
        if a + k == s[10]:
            if ry <= y < ry + 28:
                p_round(row, x0 + 6, ry, cr - 6, ry + 28, 14, T["FILL"])
            fg = dim = T["ON_FILL"]
        rw, rh = DN_RES[a + k]
        ptxt(row, x0 + 16, ry + 6, cr - 16, dn_res_text(rw, rh), fg, F_PATH)
        if (rw, rh) == (1920, 1080):
            p_right(row, cr - 16, ry + 6 + TBASE, b"Full HD", dim, F_BODY)
        if (rw, rh) == (3840, 2160):
            p_right(row, cr - 16, ry + 6 + TBASE, b"4K", dim, F_BODY)


def dn_menu_shadow(row, x0, x1, cr, yb, s):
    """MS-4 (hdesk.ci menu_shadow): the Resolution menu's shadow, High, radius 8, over Settings' content at the pen's
    zoom."""
    n = DN_RES_AT[s[5] + 1] - DN_RES_AT[s[5]]
    mh = 12 + 28 * n + 2 * (n - 1)
    shade_row(row, pen_x(x0), pen_x(x1), PEN[3], pen_x(cr - 240), pen_y(yb - mh), pen_x(cr), pen_y(yb), DN_RAD, 3,
              DN_TH[0], PEN[0])


def dn_revert_at(row, x0, y0, ow, oh, left, y):
    """hdesk.ci revert_at: the revert prompt's plate at 1x."""
    x1 = x0 + DN_RV_W
    if y0 + 16 <= y < y0 + 44:
        p_text(row, x0 + 24, y0 + 39, x1 - 24, b"Keep this resolution?", T["INK"], tw.TITLE)
    ptxt(row, x0 + 24, y0 + 64, x1 - 24, b"Back to " + dn_res_text(ow, oh) + b" in %d s" % left, T["INK_DIM"], F_BODY)
    kw = txt_w(b"Enter", F_PATH) + 12
    rw = 12 + kw + 10 + txt_w(b"Keep", F_NAME) + 12
    p_round(row, x0 + 24, y0 + 104, x0 + 24 + rw, y0 + 140, DN_RCTRL, T["FILL"])
    p_ring(row, x0 + 36, y0 + 112, x0 + 36 + kw, y0 + 132, DN_RKEY, 1, T["ON_FILL"])
    p_mid(row, x0 + 36, kw, y0 + 114 + TBASE, x0 + 36 + kw, b"Enter", T["ON_FILL"], F_PATH)
    ptxt(row, x0 + 46 + kw, y0 + 114, x0 + 24 + rw, b"Keep", T["ON_FILL"], F_NAME)
    ew = txt_w(b"Esc", F_PATH) + 12
    fw = 12 + ew + 10 + txt_w(b"Revert", F_NAME) + 12
    p_round(row, x1 - 24 - fw, y0 + 104, x1 - 24, y0 + 140, DN_RCTRL, T["SURF1"])
    p_ring(row, x1 - 12 - fw, y0 + 112, x1 - 12 - fw + ew, y0 + 132, DN_RKEY, 1, T["RULE"])
    p_mid(row, x1 - 12 - fw, ew, y0 + 114 + TBASE, x1 - 12 - fw + ew, b"Esc", T["INK_DIM"], F_PATH)
    ptxt(row, x1 - 2 - fw + ew, y0 + 114, x1 - 24, b"Revert", T["INK"], F_NAME)


def dn_revert_plate(row, y, s, x0, y0, ow, oh, left):
    dn_plate(row, x0, y0, DN_RV_W, DN_RV_H, s, DN_RPLATE, 0, 0, T["PAPER"],
             lambda r, a, b, y1: dn_revert_at(r, a, b, ow, oh, left, y1), y)


DN_GRANTS = [(2, b"fetch"), (1, b"ced"), (8, b"kern")]   # DN-34: the Grants page's list in the sums
# tests/dn6/settings_test.ci's rows frame, 736 x 1431 (MANTLE): six 720 px PAPER plates from x 8, each (its top, its
# height, its first row's top in it, the rows' kinds, the focused row, the state st_line reads: page, -, theme, size,
# motion, shape, screen w, h, one firmware mode, the menu open, its size, tiling, a volume, the level, the player, its
# pid): Display (Theme focused); Display on one firmware mode at 1080 x 1920 (no Screen shape, Resolution read-only,
# Motion off and focused); Display with the Resolution menu open over it (Resolution focused); Sound (Volume at 64
# focused, cat playing, pid 14); About; Grants' list (DN_GRANTS). Rows are 40 high and 49 apart, from cx 24 to cr 696,
# as the desk's pages lay them (PR 412: stpage.row_y); the theme word is the twin's.
DN_ROWS_AT = [(8, 284, 24, (1, 2, 3, 4, 5), 0, [0, -1, 0, 1, 1, 0, 1920, 1080, 0, 0, 3, 0, 1, -1, 0, 0]),
              (300, 235, 24, (1, 2, 3, 5), 2, [0, -1, 0, 2, 0, 2, 1080, 1920, 1, 0, 0, 0, 0, 64, 0, 0]),
              (543, 324, 64, (1, 2, 3, 4, 5), 4, [0, -1, 0, 1, 1, 0, 1920, 1080, 0, 1, 3, 0, 1, -1, 0, 0]),
              (875, 186, 24, (12, 7, 13), 1, [2, -1, 0, 1, 1, 0, 1920, 1080, 0, 0, 0, 0, 1, 64, 1, 14]),
              (1069, 186, 24, (8, 9, 10), -1, [4, -1, 0, 1, 1, 0, 1920, 1080, 0, 0, 0, 0, 1, -1, 0, 0]),
              (1263, 160, 24, (), -1, None)]
DN_ROWS_W, DN_ROWS_H = 736, 1431


def dn_rows_at(row, x0, y0, k, y):
    """Plate k of DN_ROWS_AT at 1x from (x0, y0): its rows by dn_st_line, the Resolution menu over them when open, or
    Grants' list by dn_grant_rows."""
    cx, cr = x0 + 24, x0 + 696
    _, _, top, kinds, f, st = DN_ROWS_AT[k]
    if st is None:
        dn_grant_rows(row, cx, cr, y0 + top, DN_GRANTS, y)
        return
    s = list(st)
    s[2] = DN_TH[0]
    for r, what in enumerate(kinds):
        ry = y0 + top + 49 * r
        if ry <= y < ry + 40:
            dn_st_line(row, cx, ry, cr, what, r == f, s, y)
    if s[9] == 1:
        yb = y0 + top + 49 * kinds.index(5) + 4          # the Resolution row's top and 4 (hdesk.ci dp_res_bottom)
        dn_menu_shadow(row, x0, x0 + 720, cr, yb, s)
        dn_res_menu(row, cr, yb, s, y)


def dn_rows(row, y, s):
    """The rows frame on device row y at UI scale s."""
    for k, (py, ph, _, _, _, _) in enumerate(DN_ROWS_AT):
        dn_plate(row, 8 * s, py * s, 720, ph, s, DN_RPLATE, 0, 0, T["PAPER"],
                 lambda r, a, b, y1, k=k: dn_rows_at(r, a, b, k, y1), y)


def dn_test_frame9(row, y, s):
    """tests/dn6/panel_test.ci's 944 x 480 frame: the panel with two grants at level 64, cat playing with every
    control (pause shown), the theme segment th, at (8, 8); none, no device, the other segment, at (320, 8); none at
    level 30, nothing playing, segment th, at (632, 8); the message at (8, 430)."""
    th = DN_TH[0]
    for x0, g, lv, t2, np, ctl in ((8, [(2, b"fetch"), (1, b"ced")], 64, th, 1, 15), (320, [], -1, 1 - th, -1, 0),
                                   (632, [], 30, th, 0, 0)):
        dn_plate(row, x0 * s, 8 * s, DN_SP_W, dn_sp_h(len(g)), s, DN_RPLATE, 0, 0, T["SURF2"],
                 lambda r, a, b, y1, g=g, lv=lv, t2=t2, np=np, ctl=ctl: dn_panel_at(r, a, b, g, lv, t2, y1, np, b"cat",
                                                                                    8, b"pid 14", ctl), y)
    dn_msg_plate(row, y, s, 8 * s, 430 * s, DN_MSG)


def dn_test_tray(row, y, s):
    """tests/dn6/tray_test.ci's 640 x 160 frame (MANTLE): chevrons on BAR slots 24 x 20 at (8 + 32 k, 4) turned 0, 45,
    90, 135 and 180 degrees (the last two on BAR_SLOT, open), one dim at 0; plates of 1, 5 and 7 icons from (8, 40),
    (64, 40) and (248, 40), the second with the keyboard on cell 2, the third the pointer on cell 6."""
    z = dn_tz(s)
    for k, (a, open_, dim) in enumerate(((0, False, False), (45, False, False), (90, False, False), (135, True, False),
                                         (180, True, False), (0, False, True))):
        x0 = 8 + 32 * k
        def draw(r, a0, b0, y1, a=a, open_=open_, dim=dim):
            if open_:
                p_round(r, a0, b0, a0 + 24, b0 + 20, 6, T["BAR_SLOT"])
            chevron(r, y1, a0 + 12, b0 + 10, a, mix_px(T["BAR"], T["INK_DIM"], 128) if dim else ct.INK)
        dn_plate(row, x0 * s, 4 * s, 24, 20, s, 0, 0, 0, T["BAR"], draw, y)
    for x0, n, sel, hov in ((8, 1, -1, -1), (64, 5, 2, -1), (248, 7, -1, 6)):
        icons = [(k % 8) for k in range(n)]
        dn_plate(row, x0 * s, 40 * s, dn_tray_pw(n), dn_tray_ph(n), s, DN_RAD, 0, 0, T["SURF2"],
                 lambda r, a0, b0, y1, icons=icons, sel=sel, hov=hov: dn_tray_at_row(r, a0, b0, icons, sel, hov, y1), y)


def dn_test_prompt_over(row, y, s):
    """tests/dn6/float_test.ci's 900 x 240 frame (MANTLE): Finder, focused, and sh behind the kern prompt, so both at
    rest (DN-24), the prompt at (464, 16)."""
    for fx, fy, fw, fh, focus, rk, gt, ic, t, v in ((16, 16, 420, 120, True, "ULTRAMARINE", "PAPER", 0, b"Index",
                                                    b"/home/ci"),
                                                   (16, 144, 420, 88, False, "ULTRAMARINE", "TERM", 1, b"sh", b"/etc")):
        gr = ct.TERM_PAPER if gt == "TERM" else T[gt]
        dn_float(row, fx * s, fy * s, (fx + fw) * s, (fy + fh) * s, s, dn_lit_of(focus, True), rk, gr, ic, t, v, -1, y)
    dn_prompt_rows(row, y, s, 464, 16)


DN_GROUPS["sp5-tray"] = lambda row, y, s: dn_test_tray(row, y, s)


def dn6_sums():
    """--dn6-sums: the sums tests/dn6/panel_test.ci and settings_test.ci pin, at UI scale 1, 2 and 3, both themes."""
    for th in (0, 1):
        use_theme(th)
        DN_TH[0] = th
        print("panel", th, [dn_sum(dn_frame(944, 480, s, dn_test_frame9)) for s in (1, 2, 3)])
        print("tray", th, [dn_sum(dn_frame(640, 160, s, dn_test_tray)) for s in (1, 2, 3)])
        print("rows", th, [dn_sum(dn_frame(DN_ROWS_W, DN_ROWS_H, s, dn_rows)) for s in (1, 2)])
        print("revert", th, [dn_sum(dn_frame(436, 176, s, lambda row, y, s: dn_revert_plate(
            row, y, s, 8 * s, 8 * s, 1280, 720, 12))) for s in (1, 2)])
        print("floats", th, [dn_sum(dn_floats_frame(DN_FLOATS_W, DN_FLOATS_H, s, DN_FLOATS)) for s in (1, 2, 3)])
        print("prompt-over", th, [dn_sum(dn_frame(900, 240, s, dn_test_prompt_over)) for s in (1, 2, 3)])
        print("prompt", th, [dn_sum(dn_frame(452, 228, s, lambda row, y, s: dn_prompt_rows(row, y, s, 16, 8)))
                             for s in (1, 2, 3)])
        print("switcher", th, [dn_sum(dn_frame(680, 320, s, lambda row, y, s: (
            dn_switcher_plate(row, y, s, 8 * s, 8 * s, DN_TILES, 2),
            dn_switcher_plate(row, y, s, 8 * s, 164 * s, DN_TILES[:2], 0)))) for s in (1, 2, 3)])
        print("wide", th, dn_sum(dn_floats_frame(5120, 136, 1, DN_WIDE)))
    use_theme(0)
    DN_TH[0] = 0
    return 0
DN_GROUPS["frame11-revert"] = lambda row, y, s: dn_revert_plate(row, y, s, (1920 // s - DN_RV_W) // 2 * s,
                                                                 (28 + (1080 // s - 28 - DN_RV_H) // 2) * s, 1280, 720,
                                                                 12)


def dn_mode_fits(w, h):
    """hdesk.ci mode_fits, rt/fbmode.h's fb_mode_fits (RES-1, PR 248)."""
    return 640 <= w <= 5120 and w % 8 == 0 and 480 <= h <= 3840 and w * h <= 3840 * 2160


def dn_rv_secs(ms):
    """hdesk.ci rv_secs: the revert prompt's seconds left after ms."""
    return max(0, tdiv(15000 - ms + 999, 1000))


DN_WIDE = [(4672, 8, 440, 120, True, "ULTRAMARINE", "PAPER", 0, b"Index", b"/home/ci", -1, -1)]   # a 5120-wide row's end


DN_RV_WAIT, DN_RV_KEEP, DN_RV_BACK, DN_KEY_ENTER, DN_KEY_ESC = 0, 1, 2, 28, 1


def dn_rv_plan(key, ms):
    """hdesk.ci rv_plan: wait, keep (FBIO_TILE_SAVE) or back (switch back, no save)."""
    if dn_rv_secs(ms) == 0:
        return DN_RV_BACK
    return {DN_KEY_ENTER: DN_RV_KEEP, DN_KEY_ESC: DN_RV_BACK}.get(key, DN_RV_WAIT)


def dn_rv_note(st):
    """hdesk.ci rv_note: the bar message for FBIO_TILE_SAVE's status."""
    return b"" if st == 0 else b"Couldn't save the resolution."


def dn_proof(out, names):
    """--dn6-proof DIR [NAME...]: each frame group's twin screens at 1920 x 1080, UI scale 1 and 2, dark and light,
    as one PNG of four screens (1x dark, 1x light over 2x dark, 2x light), DIR/dn6-NAME.png."""
    png = load("png", "png.py")
    W, H = 1920, 1080
    for name in names or sorted(DN_GROUPS):
        sheet = [[0] * (2 * W) for _ in range(2 * H)]
        for q, (th, s) in enumerate(((0, 1), (1, 1), (0, 2), (1, 2))):
            use_theme(th)
            DN_TH[0] = th
            for y in range(H):
                row = [T["MANTLE"]] * W
                DN_GROUPS[name](row, y, s)
                sheet[(q // 2) * H + y][(q % 2) * W:(q % 2 + 1) * W] = row[:W]
        use_theme(0)
        png.write(os.path.join(out, "dn6-%s.png" % name), 2 * W, 2 * H, sheet)
        print("dn6 proof: %s" % name)
    return 0


# ---- DN-32 and DN-33: the right-click menu (user/ci/kit/ctxmenu.ci) -------------------------------------------
# The kit's twin: its lists, layout, hover, keys and rows, and kit/symbols.ci's drawing read from its tables. The
# frames below are tests/dn32/ctxmenu_test.ci's; --ctxmenu-sums prints their sums, --ctxmenu-proof DIR draws them.

CM_FILE, CM_FOLDER, CM_EMPTY, CM_TEXT = 0, 1, 2, 3
(CM_CUT, CM_COPY, CM_RENAME, CM_SHARE, CM_TRASH, CM_PASTE, CM_NEW_FOLDER, CM_NEW_FILE, CM_OPEN, CM_OPEN_WITH,
 CM_OPEN_IN_CONSOLE, CM_COPY_PATH, CM_PROPERTIES, CM_OPEN_NEW_WINDOW, CM_CONSOLE_HERE, CM_VIEW, CM_SORT_BY,
 CM_SELECT_ALL, CM_DISPLAY_SETTINGS, CM_VIEW_GRID, CM_VIEW_TABLE, CM_SORT_NAME, CM_SORT_TYPE, CM_SORT_SIZE, CM_ABOUT,
 CM_WIN_VIEW, CM_TILED, CM_FLOATING, CM_FULL_SCREEN, CM_MINIMIZE, CM_EXIT) = range(1, 32)
CM_APP_MENU = 4                          # AM-1
CM_PIN_TASKBAR, CM_UNPIN_TASKBAR = 33, 34   # DN-46 (c), after AM's actions
CM_SUB_W, CM_OVERLAP = 160, 4           # DN-35
CM_APP, CM_SUB = 64, 128
CM_APP_SETTINGS, CM_ITEM_ROWS = 32, 16   # AM-2's Settings; AM-4: the app menu's own rows
CM_W, CM_PAD, CM_RAD, CM_SLOT_W, CM_SLOT_H, CM_PITCH, CM_ROW_H, CM_DIV_H, CM_DIM = 224, 6, 8, 36, 32, 43, 28, 11, 90
F_SHORTCUT = tw.SHORTCUT


def cm_near(px, py, ax, ay, qx, qy, h):
    dx, dy, wx, wy = qx - ax, qy - ay, px - ax, py - ay
    l2, t = dx * dx + dy * dy, wx * dx + wy * dy
    if t <= 0:
        return wx * wx + wy * wy <= h * h
    if t >= l2:
        return (px - qx) ** 2 + (py - qy) ** 2 <= h * h
    c = wx * dy - wy * dx
    return c * c <= h * h * l2


def cm_chevron(row, y, x0, y0, z, c):
    """ctxmenu.ci chevron_row."""
    r = y - y0
    if not 0 <= r < 10 * z:
        return
    for x in range(10 * z):
        n = 0
        for sy in range(4):
            for sx in range(4):
                u, v = (40 * x + 5 + 10 * sx) // z, (40 * r + 5 + 10 * sy) // z
                if cm_near(u, v, 140, 80, 260, 200, 30) or cm_near(u, v, 260, 200, 140, 320, 30):
                    n += 1
        if n > 0 and 0 <= x0 + x < len(row):
            row[x0 + x] = mix_px(row[x0 + x], c, n * 16)


def sh_reach(lv, th, sc, which):
    m = 0
    for k in range(2):
        v = {"down": sh_dy(lv, k) + sh_cut(lv, th, k), "up": sh_cut(lv, th, k) - sh_dy(lv, k),
             "side": sh_cut(lv, th, k)}[which]
        m = max(m, v)
    return m * sc


class Menu:
    """ctxmenu.ci's state and functions."""

    def __init__(self, l, desk=False, tb=False):
        self.l, self.desk, self.open = l, desk, False
        self.w, self.sh = (216, 3) if l == CM_APP_MENU else (CM_W, 2)   # AM-1: the app menu's width and shadow
        self.slots = []                  # [act, on]
        self.rows = []                   # [sec, act, parent, has, words, shortcut, cur, off, grp]
        self.n_app = 0
        self.sel = self.hot = self.sub = self.ssel = -1
        self.hot_key = False             # DN-42: the slot is the keyboard's (FILL)
        self.show, self.sub_show = [], []
        self.x = self.y = self.sub_x = self.sub_y = 0
        if l == CM_APP_MENU:                 # AM-1, DN-58: Window (4) with Tiled, Floating, Full Screen / Minimize; Exit
            self.slots = []
            self.rows = [[4, CM_WIN_VIEW, -1, True, b"Window", b"", False, False, False],
                         [4, CM_TILED, 0, False, b"Tiled", b"", False, False, False],
                         [4, CM_FLOATING, 0, False, b"Floating", b"", False, False, False],
                         [4, CM_FULL_SCREEN, 0, False, b"Full Screen", b"", False, False, False],
                         [6, CM_MINIMIZE, 0, False, b"Minimize", b"", False, False, False],
                         [5, CM_EXIT, -1, False, b"Exit", b"", False, False, False]]
            self.n_app = 0
            return
        acts = {CM_FILE: [CM_CUT, CM_COPY, CM_RENAME, CM_SHARE, CM_TRASH], CM_FOLDER: [CM_CUT, CM_COPY, CM_RENAME,
                CM_SHARE, CM_TRASH], CM_EMPTY: [CM_PASTE, CM_NEW_FOLDER, CM_NEW_FILE],
                CM_TEXT: [CM_CUT, CM_COPY, CM_PASTE]}[l]
        self.slots = [[a, a != CM_SHARE] for a in acts]
        fx = lambda sec, act, w, k=b"", parent=-1: self.rows.append(
            [sec, act, parent, parent < 0 and act in (CM_OPEN_WITH, CM_VIEW, CM_SORT_BY), w, k, False, False, False])
        if l == CM_FILE:
            fx(1, CM_OPEN, b"Open", b"Enter"); fx(1, CM_OPEN_WITH, b"Open With")
            fx(1, *((CM_UNPIN_TASKBAR, b"Unpin from Taskbar") if tb else (CM_PIN_TASKBAR, b"Pin to Taskbar")))
            fx(2, CM_OPEN_IN_CONSOLE, b"Open in Console"); fx(2, CM_COPY_PATH, b"Copy as Path", b"Ctrl+Shift+C")
        elif l == CM_FOLDER:
            fx(1, CM_OPEN, b"Open", b"Enter"); fx(1, CM_OPEN_NEW_WINDOW, b"Open in New Window")
            fx(1, *((CM_UNPIN_TASKBAR, b"Unpin from Taskbar") if tb else (CM_PIN_TASKBAR, b"Pin to Taskbar")))
            fx(2, CM_CONSOLE_HERE, b"Open Console Here"); fx(2, CM_COPY_PATH, b"Copy as Path", b"Ctrl+Shift+C")
        elif l == CM_EMPTY:
            fx(1, CM_VIEW, b"View"); fx(1, CM_SORT_BY, b"Sort By")
            fx(2, CM_CONSOLE_HERE, b"Open Console Here"); fx(2, CM_COPY_PATH, b"Copy as Path", b"Ctrl+Shift+C")
            if desk:
                self.rows.append([3, CM_DISPLAY_SETTINGS, -1, False, b"Display Settings", b"", False, False, False])
                self.n_app = 1
            for a, w in ((CM_VIEW_GRID, b"Grid"), (CM_VIEW_TABLE, b"Table")):
                fx(1, a, w, parent=0)
            for a, w in ((CM_SORT_NAME, b"Name"), (CM_SORT_TYPE, b"Type"), (CM_SORT_SIZE, b"Size")):
                fx(1, a, w, parent=1)
        else:
            fx(1, CM_SELECT_ALL, b"Select All")
        if l != CM_TEXT:
            fx(4, CM_PROPERTIES, b"Properties", b"Alt+Enter")

    def about(self, name):
        self.rows.append([1, CM_ABOUT, -1, False, b"About " + name, b"", False, False, False])

    def settings(self, off=False):
        self.rows.append([1, CM_APP_SETTINGS, -1, False, b"Settings", b"", False, off, False])

    def app_row(self, w, act, has=False):
        if self.n_app >= 3 or not CM_APP <= act < CM_SUB:
            return False
        self.rows.append([3, act, -1, has, w, b"", False, False, False])
        self.n_app += 1
        return True

    def item_row(self, w, kb, act, has=False, group=False, spot=False, off=False):
        """AM-4: the app menu's own row (ctxmenu.ci item_row)."""
        if self.l != CM_APP_MENU or self.n_app >= CM_ITEM_ROWS or not CM_APP <= act < CM_SUB:
            return False
        self.rows.append([3, act, -1, has, w, kb, spot, off, group])
        self.n_app += 1
        return True

    def item_sub(self, parent, w, kb, act, group=False, spot=False, off=False):
        """AM-4: a child row of the app's own (ctxmenu.ci item_sub)."""
        if self.l != CM_APP_MENU or self.n_app >= CM_ITEM_ROWS or act < CM_SUB:
            return False
        for i, r in enumerate(self.rows):
            if r[1] == parent and r[2] < 0 and r[3]:
                self.rows.append([r[0], act, i, False, w, kb, spot, off, group])
                self.n_app += 1
                return True
        return False

    def sub_row(self, parent, w, act):
        if act < CM_SUB:
            return False
        for i, r in enumerate(self.rows):
            if r[1] == parent and r[2] < 0 and r[3]:
                self.rows.append([r[0], act, i, False, w, b"", False, False, False])
                return True
        return False

    def current(self, act):
        for r in self.rows:
            if r[1] == act and r[2] >= 0:
                for q in self.rows:
                    if q[2] == r[2]:
                        q[6] = False
                r[6] = True

    def slot_off(self, act):
        for s in self.slots:
            if s[0] == act:
                s[1] = False

    def height_of(self, rs, strip):
        h, last = 2 * CM_PAD, -1
        if strip and self.slots:
            h, last = h + CM_SLOT_H, 0
        for i in rs:
            if last >= 0 and (self.rows[i][0] != last or self.rows[i][8]):
                h += CM_DIV_H
            last = self.rows[i][0]
            h += CM_ROW_H
        return h

    def tops(self, rs, strip, y0):
        y, last, out = y0 + CM_PAD, -1, []
        if strip and self.slots:
            y, last = y + CM_SLOT_H, 0
        for i in rs:
            if last >= 0 and (self.rows[i][0] != last or self.rows[i][8]):
                y += CM_DIV_H
            last = self.rows[i][0]
            out.append(y)
            y += CM_ROW_H
        return out

    def height(self):
        return self.height_of(self.show, True)

    def sub_height(self):
        return self.height_of(self.sub_show, False)

    @staticmethod
    def flip(p, e, lo, hi):
        v = p
        if v + e > hi:
            v = p - e
        if v + e > hi:
            v = hi - e
        return max(v, lo)

    def open_at(self, px, py, x0, y0, x1, y1, keyed=False):
        self.show = [i for sec in range(1, 7) for i, r in enumerate(self.rows) if r[2] < 0 and r[0] == sec]
        self.b = (x0, y0, x1, y1)
        self.x, self.y = self.flip(px, self.w, x0, x1), self.flip(py, self.height(), y0, y1)
        self.open, self.sel, self.hot, self.sub, self.sub_show, self.ssel = True, -1, -1, -1, [], -1
        if keyed:
            self.sel = self.live_row(self.show, -1, 1, True)

    def close(self):
        self.open, self.sub, self.sub_show = False, -1, []

    def sub_open_at(self, i):
        r = self.show[i]
        if not self.rows[r][3]:
            self.sub, self.sub_show, self.ssel = -1, [], -1
            return
        if self.sub == r:
            return
        self.sub = r
        self.sub_show = [j for j, q in enumerate(self.rows) if q[2] == r]
        self.ssel = -1
        x0, y0, x1, y1 = self.b
        self.sub_x = self.x + self.w - CM_OVERLAP
        if self.sub_x + CM_SUB_W > x1:
            self.sub_x = self.x - CM_SUB_W + CM_OVERLAP
        self.sub_x = max(self.sub_x, x0)
        self.sub_y = self.flip(self.tops(self.show, True, self.y)[i] - CM_PAD, self.sub_height(), y0, y1)
        if self.sub_y + self.sub_height() > y1:
            self.sub_y = y1 - self.sub_height()

    def slot_left(self, k):
        return self.x + CM_PAD + 2 + CM_PITCH * k

    def hit(self, px, py):
        if not self.open:
            return -1
        if self.sub >= 0 and self.sub_x <= px < self.sub_x + CM_SUB_W and self.sub_y <= py < self.sub_y + \
                self.sub_height():
            for j, t in enumerate(self.tops(self.sub_show, False, self.sub_y)):
                if t <= py < t + CM_ROW_H and self.sub_x + CM_PAD <= px < self.sub_x + CM_SUB_W - CM_PAD:
                    return 200 + j
            return -2
        if not (self.x <= px < self.x + self.w and self.y <= py < self.y + self.height()):
            return -1
        for k in range(len(self.slots)):
            sx = self.slot_left(k)
            if sx <= px < sx + CM_SLOT_W and self.y + CM_PAD <= py < self.y + CM_PAD + CM_SLOT_H:
                return 100 + k
        for i, t in enumerate(self.tops(self.show, True, self.y)):
            if t <= py < t + CM_ROW_H and self.x + CM_PAD <= px < self.x + self.w - CM_PAD:
                return i
        return -2

    def hover(self, px, py):
        if not self.open:
            return False
        before = (self.hot, self.sel, self.sub, self.ssel)
        at = self.hit(px, py)
        self.hot_key = False
        self.hot = at - 100 if 100 <= at < 200 and self.slots[at - 100][1] else -1
        if at >= 200:
            self.ssel = at - 200
        elif 0 <= at < 100:
            self.sel, self.ssel = at, -1
            self.sub_open_at(at)
        elif at >= 100:
            self.sel, self.sub, self.sub_show, self.ssel = -1, -1, [], -1
        return before != (self.hot, self.sel, self.sub, self.ssel)

    def click(self, px, py):
        at = self.hit(px, py)
        if at == -1:
            self.close()
            return -1
        if at >= 200:
            self.ssel = at - 200
            if self.rows[self.sub_show[self.ssel]][7]:   # a dimmed row takes no press
                return 0
            a = self.rows[self.sub_show[self.ssel]][1]
            self.close()
            return a
        if at >= 100:
            if not self.slots[at - 100][1]:
                return 0
            self.close()
            return self.slots[at - 100][0]
        if at >= 0:
            self.sel = at
            if self.rows[self.show[at]][3]:
                self.sub_open_at(at)
                return 0
            if self.rows[self.show[at]][7]:
                return 0
            self.close()
            return self.rows[self.show[at]][1]
        return 0

    def live_slot(self, k, d):
        k += d
        while 0 <= k < len(self.slots):
            if self.slots[k][1]:
                return k
            k += d
        return -1

    def live_row(self, rs, k, d, wrap):
        """ctxmenu.ci live_row: the row of rs after k (-1: before the first) in direction d not dimmed (AM-SET)."""
        n = len(rs)
        if k < 0 and d < 0:
            k = n
        for _ in range(n):
            k += d
            if not 0 <= k < n:
                if not wrap:
                    return -1
                k %= n
            if not self.rows[rs[k]][7]:
                return k
        return -1

    def key(self, c):
        ESC, ENTER, UP, LEFT, RIGHT, DOWN = 1, 28, 103, 105, 106, 108
        if not self.open:
            return -1
        self.hot_key = True
        if self.sub >= 0 and self.ssel >= 0:
            if c in (DOWN, UP):
                self.ssel = self.live_row(self.sub_show, self.ssel, 1 if c == DOWN else -1, True)
                if self.ssel < 0:
                    self.sub, self.sub_show = -1, []
            if c in (LEFT, ESC):
                self.ssel, self.sub, self.sub_show = -1, -1, []
            if c == ENTER and not self.rows[self.sub_show[self.ssel]][7]:
                a = self.rows[self.sub_show[self.ssel]][1]
                self.close()
                return a
            return 0
        if c == ESC:
            self.close()
            return -1
        if self.hot >= 0:
            if c == LEFT and self.live_slot(self.hot, -1) >= 0:
                self.hot = self.live_slot(self.hot, -1)
            if c == RIGHT and self.live_slot(self.hot, 1) >= 0:
                self.hot = self.live_slot(self.hot, 1)
            if c == DOWN and self.live_row(self.show, -1, 1, True) >= 0:
                self.hot, self.sel = -1, self.live_row(self.show, -1, 1, True)
            if c == ENTER:
                a = self.slots[self.hot][0]
                self.close()
                return a
            return 0
        if c == DOWN:
            self.sel, self.sub, self.sub_show = self.live_row(self.show, self.sel, 1, True), -1, []
        elif c == UP:
            up = self.live_row(self.show, self.sel, -1, False) if self.sel >= 0 else -1
            if up < 0 and self.live_slot(-1, 1) >= 0:
                self.sel, self.hot = -1, self.live_slot(-1, 1)
            elif up >= 0:
                self.sel = up
            else:
                self.sel = self.live_row(self.show, self.sel, -1, True)
            self.sub, self.sub_show = -1, []
        elif c in (RIGHT, ENTER) and self.sel >= 0 and self.rows[self.show[self.sel]][3]:
            self.sub_open_at(self.sel)
            self.ssel = self.live_row(self.sub_show, -1, 1, True)
        elif c == ENTER and self.sel >= 0 and not self.rows[self.show[self.sel]][7]:
            a = self.rows[self.show[self.sel]][1]
            self.close()
            return a
        return 0

    def content(self, scr, y, px0, py0, pw, rs, strip, pick, z, th):
        last, ty = -1, py0 + CM_PAD
        sym = {CM_CUT: "CUT", CM_COPY: "COPY", CM_RENAME: "EDIT", CM_SHARE: "SHARE", CM_TRASH: "TRASH",
               CM_PASTE: "PASTE", CM_NEW_FOLDER: "NEW_FOLDER", CM_NEW_FILE: "NEW_FILE"}
        if strip and self.slots:
            for k, (act, on) in enumerate(self.slots):
                sx, sy = (px0 + CM_PAD + 2 + CM_PITCH * k) * z, ty * z
                name, ink = sym[act], T["INK"]
                if k == self.hot and on:
                    if self.hot_key:             # DN-42: the keyboard's slot is the focus: FILL, mono in ON_FILL
                        sh_rounded(scr, y, sx, sy, sx + CM_SLOT_W * z, sy + CM_SLOT_H * z, 6 * z, T["FILL"])
                        name, ink = name + "_MONO", T["ON_FILL"]
                    else:
                        sh_rounded(scr, y, sx, sy, sx + CM_SLOT_W * z, sy + CM_SLOT_H * z, 6 * z, T["BAR_RULE"])
                sym_row(scr, y, sx + 10 * z, sy + 8 * z, SYM[5][name], z, ink, th, 256 if on else CM_DIM)
            ty, last = ty + CM_SLOT_H, 0
        for j, i in enumerate(rs):
            sec, act, parent, has, w, kb, cur, off, grp = self.rows[i]
            if last >= 0 and (sec != last or grp):
                sh_rect(scr, y, (px0 + CM_PAD + 8) * z, (ty + 5) * z, (px0 + pw - CM_PAD - 8) * z, (ty + 6) * z,
                        T["RULE"])
                ty += CM_DIV_H
            last = sec
            y0 = ty * z
            if y0 <= y < y0 + CM_ROW_H * z:
                ink, dim = T["INK"], T["INK_DIM"]
                if off:                      # DN-49: 35 percent of the ink over the plate, never picked
                    ink = dim = mix_px(T["SURF2"], ink, CM_DIM)
                if j == pick and not off:
                    sh_rounded(scr, y, (px0 + CM_PAD) * z, y0, (px0 + pw - CM_PAD) * z, y0 + CM_ROW_H * z, 14 * z,
                               T["FILL"])
                    ink = dim = T["ON_FILL"]
                right, base = (px0 + pw - CM_PAD - 10) * z, y0 + 18 * z
                if cur:                      # DN-35: the current choice's 8 px dot
                    sh_rounded(scr, y, right - 8 * z, y0 + 10 * z, right, y0 + 18 * z, 4 * z, ink)
                    right -= 16 * z
                if has:
                    cm_chevron(scr, y, right - 10 * z, y0 + 9 * z, z, dim)
                    right -= 18 * z
                if kb:
                    kw = tw.width(kb, F_SHORTCUT, z)
                    tw.text(scr, y, right - kw, base, right, kb, dim, F_SHORTCUT, z)
                    right -= kw + 12 * z
                tw.text(scr, y, (px0 + CM_PAD + 10) * z, base, right, w, ink, F_BODY, z)
            ty += CM_ROW_H

    def plate(self, row, y, px0, py0, pw, h, rs, strip, pick, z, th, v):
        ww, hh = pw * z, h * z
        s = 960 + 40 * v // 1000
        fw, fh = ww * s // 1000, hh * s // 1000
        fx0, fy0 = px0 * z + (ww - fw) // 2, py0 * z + (hh - fh) // 2
        fx1, fy1 = fx0 + fw, fy0 + fh
        up, dn, sd = sh_reach(self.sh, th, z, "up"), sh_reach(self.sh, th, z, "down"), sh_reach(self.sh, th, z, "side")
        if not fy0 - up <= y < fy1 + dn:
            return
        lo, hi = max(fx0 - sd, 0), min(fx1 + sd, len(row), 3840)
        if lo >= hi:
            return
        scr = list(row)
        shade_row(scr, lo, hi, y, fx0, fy0, fx1, fy1, CM_RAD, self.sh, th, z)
        sh_rounded(scr, y, fx0, fy0, fx1, fy1, CM_RAD * z, T["SURF2"])
        if fy0 <= y < fy1:
            cx0, cx1 = max(px0 * z, 0), min(px0 * z + ww, hi)
            keep = list(scr)
            self.content(scr, y, px0, py0, pw, rs, strip, pick, z, th)
            for x in range(cx0, cx1):
                if x < fx0 or x >= fx1:
                    scr[x] = keep[x]
        a = v * 256 // 1000
        for x in range(lo, hi):
            row[x] = mix_px(row[x], scr[x], a)

    def row_at(self, row, y, z, th, v=1000):
        if not self.open and v <= 0:
            return
        self.plate(row, y, self.x, self.y, self.w, self.height(), self.show, True, self.sel, z, th, v)
        if self.sub >= 0:
            self.plate(row, y, self.sub_x, self.sub_y, CM_SUB_W, self.sub_height(), self.sub_show, False, self.ssel, z,
                       th, v)


# The frames tests/dn32/ctxmenu_test.ci pins and the proof draws: (name, W, H at 1x, steps); steps build a Menu.
CM_OPEN_WITH_ROWS = [b"Edit", b"View", b"CVim"]
# AM-4: Edit's rows (user/ced/desk.ci words and ROW_MARKS, Word Wrap's dot on): words, keys, marks (g 1, o 2, d 4)
CM_EDIT_ROWS = [(b"New Window", b"Ctrl+N", 5), (b"Open", b"Ctrl+O", 4), (b"Open Recent", b"", 4),
                (b"Save", b"Ctrl+S", 0), (b"Save As", b"", 4), (b"Undo", b"Ctrl+Z", 1), (b"Redo", b"Ctrl+Y", 0),
                (b"Find", b"Ctrl+F", 1), (b"Replace", b"Ctrl+R", 0), (b"Word Wrap", b"", 3)]


def cm_frame_menu(name, W, H):
    if name == "file":                       # FILE at the pointer, Open With's submenu open, its Edit hovered
        m = Menu(CM_FILE)
        for k, w in enumerate(CM_OPEN_WITH_ROWS):
            m.sub_row(CM_OPEN_WITH, w, CM_SUB + k)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[1] + 4)
        m.hover(m.sub_x + 40, m.tops(m.sub_show, False, m.sub_y)[0] + 4)
        return m, 1000
    if name == "folder":                     # FOLDER by the Menu key, then Up: the strip's first slot keyed
        m = Menu(CM_FOLDER)
        m.open_at(16, 16, 0, 0, W, H, True)
        m.key(103)
        return m, 1000
    if name == "empty":                      # EMPTY in Index, View's submenu keyed open, Grid current (DN-35)
        m = Menu(CM_EMPTY)
        m.current(CM_VIEW_GRID)
        m.current(CM_SORT_NAME)
        m.open_at(16, 16, 0, 0, W, H, True)
        m.key(106)
        return m, 1000
    if name == "sort":                       # EMPTY, Sort By hovered open, Kind current, Size hovered (DN-35)
        m = Menu(CM_EMPTY)
        m.current(CM_VIEW_TABLE)
        m.current(CM_SORT_TYPE)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[1] + 4)
        m.hover(m.sub_x + 40, m.tops(m.sub_show, False, m.sub_y)[2] + 4)
        return m, 1000
    if name == "sort-flipped":               # the same at the bounds' right edge: the submenu flips left (DN-35)
        m = Menu(CM_EMPTY)
        m.current(CM_SORT_NAME)
        m.open_at(W - 16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[1] + 4)
        return m, 1000
    if name == "desk":                       # EMPTY on the desk: Display Settings as an app row; Paste hovered
        m = Menu(CM_EMPTY, True)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.slot_left(0) + 4, m.y + 10)
        return m, 1000
    if name == "text":                       # TEXT with three fixture app rows; Select All hovered
        m = Menu(CM_TEXT)
        for k in range(3):
            m.app_row(b"Fixture row %d" % (k + 1), CM_APP + k)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[0] + 4)
        return m, 1000
    if name == "flipped":                    # FILE at the bounds' far corner: flipped up and left, its submenu left
        m = Menu(CM_FILE)
        for k, w in enumerate(CM_OPEN_WITH_ROWS):
            m.sub_row(CM_OPEN_WITH, w, CM_SUB + k)
        m.slot_off(CM_TRASH)
        m.open_at(W - 20, H - 12, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[1] + 4)
        return m, 1000
    if name == "app":                        # AM-1: Edit's app menu, Tiled current, Window's submenu open (DN-58)
        m = Menu(CM_APP_MENU)
        m.about(b"Edit")
        m.current(CM_TILED)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[1] + 4)
        return m, 1000
    if name == "app-items":                  # AM-4, frame 41: Settings dimmed (plan A), Edit's rows as ced declares them
        m = Menu(CM_APP_MENU)
        m.about(b"Edit")
        m.settings(True)
        for k, (w, kb, mk) in enumerate(CM_EDIT_ROWS):
            m.item_row(w, kb, CM_APP + k, False, (mk & 1) != 0, (mk & 2) != 0, (mk & 4) != 0)
        m.current(CM_TILED)
        m.open_at(16, 16, 0, 0, W, H)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[5] + 4)
        return m, 1000
    if name == "opening":                    # FILE half way through its open (v 500)
        m = Menu(CM_FILE)
        m.open_at(16, 16, 0, 0, W, H)
        return m, 500
    raise SystemExit("no frame %s" % name)


CM_FRAMES = [("file", 520, 300), ("folder", 300, 300), ("empty", 440, 260), ("desk", 300, 300), ("text", 300, 260),
             ("flipped", 520, 300), ("opening", 300, 300), ("sort", 440, 260), ("sort-flipped", 440, 260),
             ("app", 440, 260), ("app-items", 300, 480)]


def cm_frame(name, W, H, z, th):
    use_theme(th)
    m, v = cm_frame_menu(name, W, H)
    rows = []
    for y in range(H * z):
        row = [T["PAPER"]] * (W * z)
        m.row_at(row, y, z, th, v)
        rows.append(row)
    return rows


def ctxmenu_sums():
    """--ctxmenu-sums: the sums tests/dn32/ctxmenu_test.ci pins, each frame at 1x and 2x on both themes."""
    for name, W, H in CM_FRAMES:
        print(name, [dn_sum(cm_frame(name, W, H, z, th)) for th in (0, 1) for z in (1, 2)])
    use_theme(0)
    return 0


def ctxmenu_proof(out):
    """--ctxmenu-proof DIR: each frame as one PNG of four (1x dark, 1x light; 2x dark, 2x light), DIR/dn32-NAME.png,
    and dn32-index.png: the FILE menu over the Index twin's rows (Finder draws at 1x; FD-2X A doubles it)."""
    png = load("png", "png.py")
    os.makedirs(out, exist_ok=True)
    for name, W, H in CM_FRAMES:
        sheet = cm_sheet(name, W, H)
        png.write(os.path.join(out, "dn32-%s.png" % name), len(sheet[0]), len(sheet), sheet)
        print("ctxmenu proof: %s" % name)
    for th in (0, 1):
        use_theme(th)
        DN_FINDER.clear()
        fr = dn_finder_frame(880)
        m = Menu(CM_FILE)
        for k, w in enumerate(CM_OPEN_WITH_ROWS):
            m.sub_row(CM_OPEN_WITH, w, CM_SUB + k)
        m.open_at(260, 120 + 26 + 13, 0, 0, 880, 520)
        m.hover(m.x + 40, m.tops(m.show, True, m.y)[0] + 4)
        rows = []
        for y in range(520):
            row = list(fr[y]) if y < len(fr) else [T["PAPER"]] * 880
            m.row_at(row, y, 1, th)
            rows.append(row)
        png.write(os.path.join(out, "dn32-index-%s.png" % ("dark", "light")[th]), 880, 520, rows)
        two = [spread_by(r, 2) for r in rows for _ in range(2)]
        png.write(os.path.join(out, "dn32-index-%s-2x.png" % ("dark", "light")[th]), 1760, 1040, two)
    use_theme(0)
    DN_FINDER.clear()
    print("ctxmenu proof: index")
    return 0


def cm_sheet(name, W, H):
    """1x dark and 1x light side by side over 2x dark and 2x light, 8 px gutters of #808080."""
    g = 8
    SW, SH = 4 * W + g, H + g + 2 * H
    sheet = [[0x808080] * SW for _ in range(SH)]
    for th in (0, 1):
        fr = cm_frame(name, W, H, 1, th)
        for y, r in enumerate(fr):
            sheet[y][th * (W + g):th * (W + g) + W] = r
        fr = cm_frame(name, W, H, 2, th)
        for y, r in enumerate(fr):
            sheet[H + g + y][th * (2 * W + g):th * (2 * W + g) + 2 * W] = r
    return sheet


def dn36_proof(out):
    """--dn36-proof DIR: DN-36's corners, DIR/dn36-corners.png: for a focused window, a window at rest and the kern
    prompt (radius 12, the 36 px header), dark and light, the top-left and bottom-left corners as 24 x 24 crops at 1x
    and 48 x 48 at 2x, each magnified 4 times; 8 px #808080 gutters."""
    png = load("png", "png.py")
    items = [("focused", False, True), ("rest", False, False), ("prompt", True, True), ("approval", 2, True)]
    tiles = []
    for th in (0, 1):
        use_theme(th)
        DN_TH[0] = th
        for name, prompt, lit in items:
            line = []
            for s in (1, 2):
                W, H = 480 * s, 340 * s
                fr = []
                for y in range(H):
                    row = [T["MANTLE"]] * W
                    if prompt == 2:
                        dn_prompt_ac_rows(row, y, s, 16, 16, 0)   # AC-1c's approval prompt (sienna, r12)
                    elif prompt:
                        dn_prompt_rows(row, y, s, 16, 16)
                    else:
                        dn_float(row, 16 * s, 16 * s, 456 * s, 136 * s, s, lit, "ULTRAMARINE", T["PAPER"], 1,
                                 b"Index", b"/home/ci", -1, y)
                    fr.append(row)
                h = (DN_KP_H2 if prompt == 2 else DN_KP_H if prompt else 120) * s
                c = 24 * s
                for cy in (16 * s - 4 * s, 16 * s + h - c + 4 * s):
                    crop = [r[16 * s - 4 * s:16 * s - 4 * s + c] for r in fr[cy:cy + c]]
                    m = 4 if s == 1 else 4
                    big = [[v for v in r for _ in range(m)] for r in crop for _ in range(m)]
                    line.append(big)
            tiles.append(line)
    use_theme(0)
    DN_TH[0] = 0
    g = 8
    widths = [len(t[0]) for t in tiles[0]]
    Wt = sum(widths) + g * (len(widths) + 1)
    rows = []
    for line in tiles:
        hh = max(len(t) for t in line)
        block = [[0x808080] * Wt for _ in range(hh + g)]
        x = g
        for t in line:
            for y, r in enumerate(t):
                block[g + y][x:x + len(r)] = r
            x += len(t[0]) + g
        rows += block
    rows += [[0x808080] * Wt for _ in range(g)]
    png.write(os.path.join(out, "dn36-corners.png"), Wt, len(rows), rows)
    print("dn36 proof: rows focused, rest, prompt, approval (dark), then light; columns 1x top-left, 1x bottom-left, 2x top-left,"
          " 2x bottom-left")
    return 0


def ac_bar_proof(out):
    """--ac-bar-proof DIR: DN-41 (a), the bar of login, lock and first boot (the roundel and the clock, nothing else)
    over a session's bar with DISK, NET, KERN and the tray for contrast, 1920 px at UI scale 1 and 2, dark and light:
    DIR/dn41-account-bar.png."""
    png = load("png", "png.py")
    rows = []
    for th in (0, 1):
        use_theme(th)
        for s in (1, 2):
            W1 = 1920 // s * s // s
            for bare in (True, False):
                for yd in range(28 * s):
                    row = [T["BAR"]] * (1920)
                    z = dn_tz(s)
                    r1 = [T["BAR"]] * (W1 * z)
                    if bare:
                        bar_1x(r1, yd // s, 1920 // s, 1, {1}, {}, b"", b"", 0, 0, b"10:42", False, z=z, dy=yd // (s // z),
                               bare=True)
                    else:
                        bar_1x(r1, yd // s, 1920 // s, 1, {1}, {1: 3}, b"Console", b"/home", 1, 1, b"10:42", False,
                               b"KERN 1 4m", False, (1, 0, False), z=z, dy=yd // (s // z))
                    row[:len(r1) * (s // z)] = spread_by(r1, s // z)[:1920]
                    if 4 * s <= yd < 24 * s:
                        row[9 * s:29 * s] = roundel(s, T["BAR"])[yd - 4 * s]
                    rows.append(row[:1920])
                rows.append([0x808080] * 1920)
    use_theme(0)
    png.write(os.path.join(out, "dn41-account-bar.png"), 1920, len(rows), rows)
    print("account bar proof: bare and session bars, 1x and 2x, dark then light")

TIP_GROUND, TIP_INK = 0x282a2c, 0xf3efe6   # DN-44: kit/tooltip.ci, the same dark plate in both themes


def sp7_proof(out):
    """--sp7-proof DIR: SP-7's Downloads in the tray with DN-44's tooltip, DIR/sp7-downloads-light.png, light theme:
    the open plate with two windows and the Downloads entry (Fetch, icons3 7) third by arrival, the pointer on it, and
    its tooltip (#282a2c, text #f3efe6, Inter 13, 24 px high, radius 6, 8 px padding, 6 px under the cell) for
    "Fetch", "1 download finished" and "3 downloads finished"; 1x (doubled) over 2x."""
    png = load("png", "png.py")
    texts = (b"Fetch", b"1 download finished", b"3 downloads finished")
    W1, H1 = 3 * 240, 100
    sheet = []
    use_theme(1)
    DN_TH[0] = 1
    for s in (1, 2):
        def fn(row, y, s):
            for j, t in enumerate(texts):
                x0 = 8 + 240 * j
                dn_plate(row, x0 * s, 8 * s, dn_tray_pw(3), dn_tray_ph(3), s, RAD, 0, 0, T["SURF2"],
                         lambda r, a0, b0, y1: dn_tray_at_row(r, a0, b0, [1, 3, 7], -1, 2, y1), y)
                tw_ = 16 + tw.width(t, F_BODY, 1)
                tx = x0 + 4 + 64
                ty = 8 + 4 + 32 + 6
                dn_plate(row, tx * s, ty * s, tw_, 24, s, 6, 0, 0, TIP_GROUND,
                         lambda r, a0, b0, y1, t=t: p_text(r, a0 + 8, b0 + 16, a0 + 8 + tw.width(t, F_BODY, 1),
                                                           t, TIP_INK, F_BODY), y)
        fr = dn_frame(W1, H1, s, fn)
        if s == 1:
            fr = [[c for c in r for _ in range(2)] for r in fr for _ in range(2)]
        sheet.extend(fr)
    os.makedirs(out, exist_ok=True)
    png.write(os.path.join(out, "sp7-downloads-light.png"), 2 * W1, len(sheet), sheet)
    print("sp7 proof: %s/sp7-downloads-light.png" % out)

# DN-20 and DN-21 (user/ci/kit/winrule.ci, word for word): a new float's size and place, and the restore's frames.
WR_SIDE, WR_MIN_W, WR_MIN_H, WR_CASCADE, WR_EDGE = 32, 480, 320, 32, 16


def wr_size(askw, askh, aw, ah, z):
    if askw > 0 and askh > 0:
        return min(askw, aw - 2 * WR_SIDE * z), min(askh, ah - 2 * WR_SIDE * z)
    u = 8 * z
    return min(max((aw * 5 // 8) // u * u, WR_MIN_W * z), aw), min(max((ah * 11 // 16) // u * u, WR_MIN_H * z), ah)


def wr_first(fw, fh, ax, ay, aw, ah):
    return ax + max(aw - fw, 0) // 2, ay + max(ah - fh, 0) // 3


def wr_next(placed, lx, ly, fw, fh, ax, ay, aw, ah, z):
    if placed:
        x, y = lx + WR_CASCADE * z, ly + WR_CASCADE * z
        if x + fw <= ax + aw - WR_EDGE * z and y + fh <= ay + ah - WR_EDGE * z:
            return x, y
    return wr_first(fw, fh, ax, ay, aw, ah)


def wr_between(c, f, t):
    return [f[k] + (t[k] - f[k]) * c // 1000 if t[k] >= f[k] else f[k] - (f[k] - t[k]) * c // 1000 for k in range(4)]


def wr_cascade(aw, ah, ay, z, n):
    """The first n default floats on one desktop: their frames (x, y, w, h)."""
    fw, fh = wr_size(0, 0, aw, ah, z)
    out, last = [], None
    for _ in range(n):
        x, y = wr_next(last is not None, *(last or (0, 0)), fw, fh, 0, ay, aw, ah, z)
        out.append((x, y, fw, fh))
        last = (x, y)
    return out


def winrule_cases():
    """--winrule-cases: the numbers tests/dn20/winrule_test.ci pins, from the twin."""
    print("size", wr_size(0, 0, 1920, 1044, 1), wr_size(0, 0, 1280, 764, 1), wr_size(0, 0, 640, 444, 1),
          wr_size(0, 0, 3840, 2088, 2), wr_size(0, 0, 400, 300, 1))
    print("ask", wr_size(720, 480, 1920, 1044, 1), wr_size(2000, 1200, 1920, 1044, 1), wr_size(2000, 1200, 1920, 1044, 2))
    print("first", wr_first(1200, 712, 0, 36, 1920, 1044), wr_first(2000, 1200, 0, 36, 1920, 1044))
    c = wr_cascade(1920, 1044, 36, 1, 8)
    print("cascade", [(x, y) for x, y, _, _ in c])
    print("cascade 2x", wr_next(True, 392, 178, 1200, 712, 0, 36, 1920, 1044, 2))
    print("restore", [wr_between(k, [0, 36, 1920, 1044], [360, 146, 1200, 712]) for k in (0, 500, 1000)])
    return 0


def winrule_proof(out):
    """--winrule-proof DIR: DIR/dn21-cascade.png, 1920 x 1080 at 1x shown at half size: the bar, then seven default
    floats cascading 32 px from the first place (the eighth goes back to it, ringed), and a maximized float's restore
    frames at 0, 25, 50, 75 and 100 percent of the out curve's progress."""
    png = load("png", "png.py")
    use_theme(0)
    W, H, bar = 1920, 1080, 36
    pix = [[T["MANTLE"]] * W for _ in range(H)]
    for y in range(bar):
        pix[y] = [T["SURF2"]] * W

    def frame(x, y, fw, fh, c, t):
        for yy in range(y, y + fh):
            for k in range(t):
                pix[yy][x + k] = c
                pix[yy][x + fw - 1 - k] = c
        for xx in range(x, x + fw):
            for k in range(t):
                pix[y + k][xx] = c
                pix[y + fh - 1 - k][xx] = c

    c = wr_cascade(W, H - bar, bar, 1, 8)
    for i, (x, y, fw, fh) in enumerate(c[:7]):
        frame(x, y, fw, fh, T["INK"] if i == 6 else T["INK_DIM"], 2)
    x, y, fw, fh = c[7]
    frame(x - 6, y - 6, fw + 12, fh + 12, T["ULTRAMARINE"], 2)
    for k in (0, 250, 500, 750, 1000):
        f = wr_between(k, [0, bar, W, H - bar], [600, 300, 720, 480])
        frame(f[0], f[1], f[2], f[3], T["CADMIUM"] if k in (0, 1000) else T["RULE"], 2)
    half = [[pix[2 * y][2 * x] for x in range(W // 2)] for y in range(H // 2)]
    os.makedirs(out, exist_ok=True)
    png.write(os.path.join(out, "dn21-cascade.png"), W // 2, H // 2, half)
    print("winrule proof: %s/dn21-cascade.png, cascade %s" % (out, [(x, y) for x, y, _, _ in c]))
    return 0


def ppm_full(path):
    """A P6 screendump, every row: (w, h, rows of XRGB words)."""
    data = open(path, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
    w, h, at = int(m.group(1)), int(m.group(2)), m.end()
    return w, h, [[data[at + 3 * (y * w + x)] << 16 | data[at + 3 * (y * w + x) + 1] << 8 |
                   data[at + 3 * (y * w + x) + 2] for x in range(w)] for y in range(h)]


def mo_frame15(bl):
    """The OV window's frame in the last layout block that has one (a plate's record keeps it after it closes)."""
    for d, f, wins, W, H, dr, sc in reversed(bl):
        if 15 in wins:
            return tuple(wins[15][4:8])
    return None


def mo_p(fn, start, k):
    """Progress after k steps of a motion fn (plate_open, plate_close, ...) begun at rest at start."""
    return anim_value(fn(anim_rest(start), 0, True), k * ANIM_STEP)


def mo_panel(fn, start, k, closing):
    return lambda sub, bl: {"plate": {"kind": "panel", "p": mo_p(fn, start, k), "closing": closing,
                                      "frame": mo_frame15(bl)}}


def mo_msg(fn, start, k, closing):
    """Gate 8: the bar message coming in (msg_in) or going out (msg_out) after k steps; its frame the OV window's last,
    its text the transcript's last `hdesk: message |...|`."""
    def f(sub, bl):
        t = [re.match(r"^hdesk: message \|(.*)\|$", l) for l in sub]
        text = [m.group(1) for m in t if m][-1].encode("utf-8")
        return {"plate": {"kind": "msg", "p": mo_p(fn, start, k), "closing": closing, "frame": mo_frame15(bl),
                          "text": text}}
    return f


def mo_move(k):
    """Gate 7: window 0 moved by key, k steps into MS-8's 200 ms: its frame between the last two it had in the
    layout blocks (kit/plate.ci between); at rest once the motion is over."""
    def f(sub, bl):
        frames = [tuple(b[2][0][4:8]) for b in bl if 0 in b[2]]
        to = frames[-1]
        frm = next((fr for fr in reversed(frames) if fr != to), to)
        p = mo_p(plate_move, 0, k)
        return {} if p >= 1000 else {"frame0": tuple(plate_between(a, b, p) for a, b in zip(frm, to))}
    return f


# MS-9a: each gate's dumps (gate 6, a desktop switch, is the recut's MS-7 slide leg, check-hdesk.py --slide): (name, the transcript line it waits on, its frame in motion or None at rest). The legs
# (check-hybrid.sh) dump DIR/NAME.ppm after that line; motion n counts the motions begun since boot (hdesk: step K of
# motion N, MS-9a), dark first, then light after Settings.
MOTION_GATES = {
    "4": [("g4-dark-rest", "before:hdesk: panel open", None),
          ("g4-dark-o8", "hdesk: step 8 of motion 1", mo_panel(plate_open, 0, 8, False)),
          ("g4-dark-o16", "hdesk: step 16 of motion 1", mo_panel(plate_open, 0, 16, False)),
          ("g4-dark-c5", "hdesk: step 5 of motion 2", mo_panel(plate_close, 1000, 5, True)),
          ("g4-dark-c10", "hdesk: step 10 of motion 2", mo_panel(plate_close, 1000, 10, True)),
          ("g4-light-o8", "hdesk: step 8 of motion 3", mo_panel(plate_open, 0, 8, False)),
          ("g4-light-o16", "hdesk: step 16 of motion 3", mo_panel(plate_open, 0, 16, False)),
          ("g4-light-c5", "hdesk: step 5 of motion 4", mo_panel(plate_close, 1000, 5, True)),
          ("g4-light-c10", "hdesk: step 10 of motion 4", mo_panel(plate_close, 1000, 10, True))],
    "8": [("g8-dark-m8", "hdesk: step 8 of motion 1", mo_msg(plate_msg_in, 0, 8, False)),
          ("g8-dark-m16", "hdesk: step 16 of motion 1", mo_msg(plate_msg_in, 0, 16, False)),
          ("g8-dark-g10", "hdesk: step 10 of motion 2", mo_msg(plate_msg_out, 1000, 10, True)),
          ("g8-dark-g20", "hdesk: step 20 of motion 2", mo_msg(plate_msg_out, 1000, 20, True)),
          ("g8-light-m8", "hdesk: step 8 of motion 3", mo_msg(plate_msg_in, 0, 8, False)),
          ("g8-light-m16", "hdesk: step 16 of motion 3", mo_msg(plate_msg_in, 0, 16, False)),
          ("g8-light-g10", "hdesk: step 10 of motion 4", mo_msg(plate_msg_out, 1000, 10, True)),
          ("g8-light-g20", "hdesk: step 20 of motion 4", mo_msg(plate_msg_out, 1000, 20, True))],
    "7": [("g7-dark-f0", "hdesk: win 0 kind 1 desktop 1 mode 1 rank 2 frame 270,501 540x946 rects 1 270,501,540x946",
           None),
          ("g7-dark-m10", "hdesk: step 10 of motion 1", mo_move(10)),
          ("g7-dark-m20", "hdesk: step 20 of motion 1", mo_move(20)),
          ("g7-light-m10", "hdesk: step 10 of motion 2", mo_move(10)),
          ("g7-light-m20", "hdesk: step 20 of motion 2", mo_move(20)),
          ("g7-light-t0", "hdesk: win 0 kind 1 desktop 1 mode 0 rank 4 frame 8,36 1064x1876 rects 1 8,36,1064x1876",
           None)],
}


def motion_check(gate, path, ddir):
    """--motion GATE TRANSCRIPT DIR (MS-9a, l's MS-R4 A): each of the gate's screendumps in DIR equals the screen
    the Python composes from the transcript up to the line the dump waited on, in motion where the plan says, on
    the stepped clock with kit/plate.ci's and anim.ci's twins. One line per dump; exit 1 when any differs."""
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    bad = 0
    for name, mark, mofn in MOTION_GATES[gate]:
        idx = None
        if mark.startswith("before:"):           # the screen at rest just before that line's first time
            idx = next((j for j, l in enumerate(lines) if l == mark[7:]), None)
            idx = None if idx is None else idx - 1
        else:
            idx = next((j for j, l in enumerate(lines) if l == mark), None)
        fpath = os.path.join(ddir, name + ".ppm")
        if idx is None or idx < 0 or not os.path.exists(fpath):
            print("FAIL  motion %s %s: no line %r or no dump" % (gate, name, mark))
            bad += 1
            continue
        sub = lines[:idx + 1]
        subtext = "\n".join(sub) + "\n"
        ct.screen_of(subtext)
        bl = blocks(sub)
        W, H = bl[-1][3], bl[-1][4]
        mo = dict(mofn(sub, bl)) if mofn else {}
        mo["term"] = ({0: "#"}, ("2", "0"))     # nothing is typed into window 0 before the gate's last dump
        pts = re.findall(r"^hdesk: pointer (\d+),(\d+) shown ([01])$", "\n".join(lines), re.M)
        moved = any(l.startswith("hdesk: click ") or l.startswith("hdesk: panel open") for l in sub)
        mo["pointer"] = (int(pts[-1][0]), int(pts[-1][1]), pts[-1][2] == "1") if pts and moved else (0, 0, False)
        rows = []
        screen_of(subtext, sub, bl, W, H, mo, rows)
        w, h, got = ppm_full(fpath)
        diff = [(y, x) for y in range(min(h, len(rows))) for x in range(min(w, W)) if got[y][x] != rows[y][x]]
        ok = (w, h) == (W, H) and len(rows) == H and not diff
        bad += 0 if ok else 1
        what = ("p %d" % mo["plate"]["p"]) if "plate" in mo else ("slide %r strip %r" % (mo["slide"], mo.get("strip"))
                                                               if "slide" in mo else "window 0 at %r" % (mo["frame0"],)
                                                               if "frame0" in mo else "at rest")
        print("%s  motion %s %s: %s%s" % ("PASS" if ok else "FAIL", gate, name, "frame %s" % what,
                                         "" if ok else ": %d pixels differ, first at %r (%dx%d dump)" %
                                         (len(diff), diff[:1], w, h)))
    return 1 if bad else 0


def main(argv):
    if argv[:1] == ["--motion"]:
        return motion_check(argv[1], argv[2], argv[3])
    if argv[:1] == ["--approval"]:
        return approval(argv[1], argv[2])
    if argv[:1] == ["--prompt-ac-sums"]:
        return dn_prompt_ac_sums()
    if argv[:1] == ["--sp7-proof"]:
        return sp7_proof(argv[1])
    if argv[:1] == ["--winrule-cases"]:
        return winrule_cases()
    if argv[:1] == ["--winrule-proof"]:
        return winrule_proof(argv[1])
    if argv[:1] == ["--dn6-sums"]:
        return dn6_sums()
    if argv[:1] == ["--calpop-sums"]:
        return calpop_sums()
    if argv[:1] == ["--ctxmenu-sums"]:
        return ctxmenu_sums()
    if argv[:1] == ["--ctxmenu-proof"]:
        return ctxmenu_proof(argv[1])
    if argv[:1] == ["--ac-bar-proof"]:
        return ac_bar_proof(argv[1])
    if argv[:1] == ["--dn36-proof"]:
        return dn36_proof(argv[1])
    if argv[:1] == ["--dn6-proof"]:
        return dn_proof(argv[1], argv[2:])
    if argv[:1] == ["--plane-proof"]:
        return plane_proof(argv[1], argv[2:3])
    if argv[:1] == ["--zones"]:
        return zones(argv[1])
    if argv[:1] == ["--smoke"]:
        return smoke(argv[1])
    if argv[:1] == ["--kern"]:
        return kern(argv[1])
    if argv[:1] == ["--panel"]:
        return panel(argv[1])
    if argv[:1] == ["--tray"]:
        return tray(argv[1], argv[2:5])
    if argv[:1] == ["--slide"]:
        return slide(*argv[1:6])
    if argv[:1] == ["--bars"]:
        return bars(argv[1])
    if argv[:1] == ["--switcher"]:
        return switcher(argv[1])
    path, frame_path, wad_path = argv
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = gl.lines(text)
    at_size = ct.screen_of(text)
    W, H = ct.W, ct.H
    results = []

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    bl = blocks(lines)
    bad = []
    for d, f, wins, bw, bh, dr, sc in bl:
        want = twin(bw, bh, d, wins, dr, sc)
        for i, v in wins.items():
            shown = v[1] == d and v[2] != MINIMIZED
            got = (v[4], v[5], v[6], v[7], v[8]) if shown else None
            exp = want[i] if shown else None
            if got != exp:
                bad.append((d, i, got, exp))
    swn, swbad = switcher_frames(lines, bl)
    line(bl != [] and not bad and swn > 0 and not swbad, "layouts: %d blocks, every frame and rectangle is layout.ci's "
         "twin; %d switcher frames E2-2's card (K-1)" % (len(bl), swn), "first %r, switcher %r" % (bad[:1], swbad[:1]))
    # places: against the layout block before each
    pbad, places = [], 0
    k = -1
    size = {}
    for l in lines:
        if l.startswith("hdesk: layout desktop "):
            k += 1
        mz = re.match(r"^hdesk: pixel (\d+) (?:pid \d+ )?size (\d+)x(\d+)$", l)
        if mz:
            size[int(mz.group(1))] = (int(mz.group(2)), int(mz.group(3)))
        mp = re.match(r"^hdesk: place (\d+) at (-?\d+),(-?\d+) scale (\d+) rects (\d+) \((-?\d+)\)$", l)
        if not mp:
            continue
        places += 1
        i, sx, sy, s, n, st = (int(g) for g in mp.groups())
        d, f, wins = bl[k][:3]
        kind, dk, mode, rank, x, y, w, h, rects = wins[i]
        fl = mode == FLOAT and kind in (1, 2)
        bs = (DN_FB if fl else B) * bl[k][6]                             # DN-6 frame 8: a float's ring inset 2 px
        tb = DN_WBAR * bl[k][6] if fl else 0                             # and its 32 px bar
        cw, ch = w - 2 * bs, h - 2 * bs - tb
        ow, oh = size.get(i, (OFFER_W, OFFER_H))
        ks = 6
        while ks > 1 and (ks * ow > cw or ks * oh > ch):
            ks -= 1
        ex, ey = x + bs + (cw - ks * ow) // 2, y + bs + tb + (ch - ks * oh) // 2
        cut = []
        zs, sw = bl[k][6], bl[k][3]
        r = DN_RAD * zs                                                  # WB-7 rounded: whole, not maximized
        rnd = fl and 2 * r <= 256 and x >= 0 and x + w <= sw and w >= 2 * r and h >= 2 * r and not (x == 0 and x + w == sw)
        if dk == d and mode != MINIMIZED and rects != -1:
            for (rx, ry, rw, rh) in rects:
                x0, y0, x1, y1 = max(rx, ex), max(ry, ey), min(rx + rw, ex + ks * ow), min(ry + rh, ey + ks * oh)
                for (a0, b0, a1, b1) in (place_cut(x, y, w, h, zs, x0, y0, x1, y1) if rnd else [(x0, y0, x1, y1)]):
                    if a0 < a1 and b0 < b1:
                        cut.append((a0, b0, a1 - a0, b1 - b0))
        if (sx, sy, s, n, st) != (ex, ey, ks, len(cut[:32]), 0):
            pbad.append((l, (ex, ey, ks, len(cut))))
    line(places > 0 and not pbad, "places: %d placements at the integer scale, centered, cut to the surface" % places,
         "first %r" % (pbad[:1],))
    # steps
    seq = [r"^hdesk: terminal 1 slot 1 pid \d+$", r"^hdesk: bar desktop 1 \|Console\| var \|/notes\| grants \|\|$",
           r"^hdesk: pixel 2 pid \d+ size 320x200$", r"^hdesk: pixel 2 ended$", r"^hdesk: switcher chose 0$",
           r"^hdesk: switcher 1 of 2, window 1$", r"^hdesk: switcher chose 1$", r"^hdesk: switcher sticky$",
           r"^hdesk: switcher chose 0 \(sticky\)$", r"^hdesk: ff open ", r"^hdesk: ff chose win \|Console - /\| window 0$",
           r"^hdesk: layout desktop 2 focus -1$", r"^hdesk: swap 0 1$",
           r"^hdesk: swap 0 1$", r"^hdesk: terminal 1 ended, status 0$", r"^hdesk: ff chose prog \|settings\|$",
           r"^hdesk: settings 1$", r"^hdesk: settings shape 2$", r"^hdesk: settings resolution 1080x1920$",
           r"^hdesk: mode 1080x1920 \(0\)$", r"^hdesk: screen 1080x1920 plane 1080x1892 \(0\)$",
           r"^hdesk: revert ask 1080x1920 from 1920x1080$", r"^hdesk: revert kept, saved \(-30\)$",
           r"^hdesk: message gone$", r"^hdesk: theme 1$", r"^hdesk: settings closed$", r"^hdesk: grant 0 1$",
           r"^hdesk: bar desktop 1 \|.*\| var \|/\| grants \|DISK 1\|$", r"^hdesk: scale 2$",
           r"^hdesk: scale 3$", r"^hdesk: scale 2$", r"^hdesk: calendar open$", r"^hdesk: calendar 2026-01 ",
           r"^hdesk: calendar 2026-02 ", r"^hdesk: calendar 2026-01 ", r"^hdesk: shell ended, status 0$"]
    pos, miss = 0, None
    for p in seq:
        hit = next((j for j in range(pos, len(lines)) if re.match(p, lines[j])), None)
        if hit is None:
            miss = p
            break
        pos = hit + 1
    three = any(len([v for v in wins.values() if v[1] == d and v[2] == TILED]) == 3 for d, f, wins, *_ in bl)
    mono = any(any(v[2] == MONOCLE for v in wins.values()) for d, f, wins, *_ in bl)
    flo = any(any(v[2] == FLOAT for i, v in wins.items() if i < 15) for d, f, wins, *_ in bl)
    line(miss is None and three and mono and flo, "steps: a second terminal and its variable, doom bound and tiled "
         "third, ended; Alt+Tab, Alt+`, the sticky switcher; the plane restored window 0; monocle; desktop 2 "
         "empty; two swaps, a float; the second terminal ended; the first",
         "missing %r, three %r, monocle %r, float %r" % (miss, three, mono, flo))
    # clock and calendar (K-6)
    clocks = re.findall(r"^hdesk: clock \|(.*)\|$", text, re.M)
    months = [tuple(int(g) for g in m) for m in re.findall(
        r"^hdesk: calendar (\d+)-(\d\d) first (\d) days (\d+) today (\d+)$", text, re.M)]
    cbad = [m for m in months if m[2:] != month_of(m[0], m[1], EPOCH)]
    line(clocks == [clock_text(EPOCH)] and [m[:2] for m in months] == [(2026, 1), (2026, 2), (2026, 1)] and not cbad,
         "clock: the bar's clock is the fixed epoch's, %r; the calendar's months 2026-01, 2026-02, 2026-01, each "
         "its first weekday, length and today" % clock_text(EPOCH), "clocks %r, months %r, bad %r" % (clocks, months, cbad))
    # menu: each list against the open list and the query
    def match(label, q):
        a, b = label.lower(), q.lower()
        if a.startswith(b):
            return 0
        it = iter(a)
        return 1 if all(c in it for c in b) else 2

    def keep(full, q):
        return [e for sec in (1, 2, 3) for m in (0, 1) for e in full if e[1] == sec and match(e[2], q) == m]

    mbad, lists, chose, full, cur_list, cur_sel = [], 0, 0, None, None, 0
    k = 0
    while k < len(lines):
        l = lines[k]
        if l in ("hdesk: menu open", "hdesk: app menu open"):
            full = None
        mm = re.match(r"^hdesk: menu \|(.*)\| sel (\d+) of (\d+)$", l)
        if mm:
            q, sel, n = mm.group(1), int(mm.group(2)), int(mm.group(3))
            items = []
            for l2 in lines[k + 1:k + 1 + n]:
                mi = re.match(r"^hdesk: item (\d+) kind (\d) \|(.*)\|$", l2)
                items.append((int(mi.group(1)), int(mi.group(2)), mi.group(3)) if mi else None)
            lists += 1
            if full is None:
                full = items if q == "" else []
            if items != keep(full, q) or not (0 <= sel < max(n, 1)):
                mbad.append((q, items, keep(full, q)))
            cur_list, cur_sel = items, sel
            k += 1 + n
            continue
        mc = re.match(r"^hdesk: menu chose (\d+) \|(.*)\|$", l)
        if mc:
            chose += 1
            if not cur_list or cur_list[cur_sel][0] != int(mc.group(1)) or cur_list[cur_sel][2] != mc.group(2):
                mbad.append(("chose", l))
        k += 1
    line(not mbad, "menu: %d lists, each the open list kept by its query; %d choices, each the selected entry "
         "(DN-72: no grant list)" % (lists, chose), "first %r" % (mbad[:1],))
    # doom
    pic = ct.frame_1x(open(frame_path, "rb").read(), ct.wad_lump(open(wad_path, "rb").read(), b"PLAYPAL"))
    tiles = re.findall(r"^daphnis: tile surface 320x200 at \d+,\d+ sha256 ([0-9a-f]{64})$", text, re.M)
    want_doom = hashlib.sha256(pic).hexdigest()
    line(tiles == [want_doom], "doom: its private surface is the Linux run's last frame 1x through PLAYPAL, %s" %
         want_doom[:16], "tiles %r" % tiles)
    ok, composed, shots = screen_of(text, lines, bl, W, H)
    line(ok and shots == [composed], "screen: the bar and its clock, the first terminal alone, focused, its rows and cursor, under the calendar, %s"
         % composed[:16], "surfaces %r" % shots)
    line("hdesk: shell ended, status 0" in lines and ct.whole(text) and
         lines[-1:] == ["daphnis: done"] and "daphnis: input dropped" not in lines,
         "ends: the shell ended with status 0, nothing dropped, the pool whole", "see %s" % path)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
