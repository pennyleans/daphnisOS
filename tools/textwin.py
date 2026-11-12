"""tools/textwin.py: the Python twin of the kit's coverage text (FONT-1, F4 and the swap): kit/ctext.ci (chrome text by
role), kit/mtext.ci (terminal cells), kit/ucode.ci (UTF-8) and MS-1's blend (kit/blend.ci), for the twins
(tools/check-tiler.py, check-hdesk.py, check-layout.py). It reads the tables tools/glyphs.py writes under
user/ci/kit/ (glyphs.py --check holds them to the TTFs), so it draws what cint draws, pixel for pixel; `python3
tools/textwin.py PROOF-OUTPUT` checks that against a run of tests/font/proof.ci."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "user", "ci", "kit")

# kit/faces.ci's roles, in its order (tools/glyphs.py ROLES).
PATH, BODY, NAME, LABEL, SEARCH, TITLE, NAME_BOLD, SMALL, MONO_BOLD, SHORTCUT, NAME_LARGE, CLOCK, CAPTION, SMALL_NAME, PIN11, PIN10 = range(16)
ROLE_MODULES = ["jbm12_r", "inter13_r", "inter13_m", "inter11_s", "inter16_r", "inter20_s", "inter13_s", "inter12_r", "jbm13_s", "jbm11_r", "inter16_s",
                "jbm40_s", "inter11_r", "inter12_m", "inter11_r", "inter10_r"]
BAD = 0xFFFD


def _arrays(name):
    with open(os.path.join(KIT, name + ".ci")) as f:
        text = f.read()
    out = {}
    for m in re.finditer(r"^(?:export )?const I64 (\w+) = (-?\d+);", text, re.M):
        out[m.group(1)] = int(m.group(2))
    for m in re.finditer(r"^U(?:8|32|64)\[(\d+)\] (\w+) = \[(.*?)\];", text, re.M | re.S):
        vals = [int(v, 0) for v in m.group(3).replace("\n", " ").split(",") if v.strip()]
        if len(vals) != int(m.group(1)):
            raise SystemExit("textwin.py: %s.%s holds %d, not %s" % (name, m.group(2), len(vals), m.group(1)))
        out[m.group(2)] = vals
    return out


_CACHE = {}


def table(name):
    if name not in _CACHE:
        _CACHE[name] = _arrays(name)
    return _CACHE[name]


def mix_px(p, c, a):
    """MS-1 (kit/blend.ci mix_px; tools/check-hdesk.py's twin): law 1, p - ((p - c) * a >> 8) a channel."""
    a = max(0, min(256, a))
    out = 0
    for sh in (16, 8, 0):
        v, w = p >> sh & 255, c >> sh & 255
        out |= (v - ((v - w) * a >> 8)) << sh
    return out


def alpha(v):
    """kit/ctext.ci alpha: coverage 0 to 15 to 256ths."""
    return (v * 256 + 7) // 15


def decode(s, at):
    """kit/ucode.ci decode over the bytes s from at: (code point, length)."""
    n = len(s)
    b0 = s[at]
    if b0 < 0x80:
        return b0, 1
    if 0xC2 <= b0 <= 0xDF:
        need, cp, least = 1, b0 & 0x1F, 0x80
    elif 0xE0 <= b0 <= 0xEF:
        need, cp, least = 2, b0 & 0x0F, 0x800
    elif 0xF0 <= b0 <= 0xF4:
        need, cp, least = 3, b0 & 0x07, 0x10000
    else:
        return BAD, 1
    if at + need >= n:
        return BAD, 1
    for k in range(1, need + 1):
        b = s[at + k]
        if b & 0xC0 != 0x80:
            return BAD, 1
        cp = cp * 64 + (b & 0x3F)
    if cp < least or cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
        return BAD, 1
    return cp, need + 1


def _index(t, cp):
    codes = t["codes"]
    lo, hi = 0, len(codes)
    while lo < hi:
        mid = (lo + hi) // 2
        if codes[mid] < cp:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(codes) and codes[lo] == cp:
        return lo
    return t["MISSING"]


def _nib(words, bit):
    return words[bit // 64] >> (60 - bit % 64) & 15


class Face:
    """One role of kit/faces.ci at scale z: ctext.ci's tables."""

    def __init__(self, role, z):
        self.t = table("%s%d" % (ROLE_MODULES[role], z))
        self.ascent, self.descent = self.t["ASCENT"], self.t["DESCENT"]

    def index(self, cp):
        return _index(self.t, cp)

    def advance(self, g):
        return self.t["adv"][g]

    def box(self, g):
        b = self.t["box"][g]
        return (b >> 8 & 255) - 128, (b & 255) - 128, b >> 24 & 255, b >> 16 & 255, b >> 32

    def at(self, g, x, y):
        _, _, w, _, off = self.box(g)
        bit = (y * w + x) * 4
        return _nib(self.t["cov"], off * 64 + bit)


def face(role, z):
    key = ("face", role, z)
    if key not in _CACHE:
        _CACHE[key] = Face(role, z)
    return _CACHE[key]


def width(s, role, z):
    """kit/ctext.ci width: the sum of the advances of the UTF-8 bytes s."""
    f, w, at = face(role, z), 0, 0
    while at < len(s):
        cp, k = decode(s, at)
        w += f.advance(f.index(cp))
        at += k
    return w


def text(row, y, x0, base, x1, s, c, role, z):
    """kit/ctext.ci text: row y of the UTF-8 bytes s, the pen from x0 on baseline row base; the pen past the last
    glyph drawn, none past x1."""
    f, x, at = face(role, z), x0, 0
    while at < len(s):
        cp, k = decode(s, at)
        at += k
        g = f.index(cp)
        a = f.advance(g)
        if x + a > x1:
            return x
        left, top, w, h, _ = f.box(g)
        gy = y - base - top
        if 0 <= gy < h:
            for i in range(w):
                px = x + left + i
                if 0 <= px < len(row):
                    v = f.at(g, i, gy)
                    if v:
                        row[px] = mix_px(row[px], c, alpha(v))
        x += a
    return x


def cell_index(cp):
    """kit/mtext.ci index."""
    return _index(table("jbm_r1"), cp)


def cell_row(row, x, cy, g, bold, fg, bg, z):
    """kit/mtext.ci cell_row: row cy of glyph g's cell at x, ground bg, ink fg."""
    t = table("jbm_%s%d" % ("b" if bold else "r", z))
    w, per = 8 * z, 8 * z * 16 * z * 4 // 64
    for i in range(w):
        px = x + i
        if 0 <= px < len(row):
            v = _nib(t["cov"], g * per * 64 + (cy * w + i) * 4)
            row[px] = mix_px(bg & 0xFFFFFF, fg, alpha(v))


def check_proof(path):
    """Compare the twin with a run of tests/font/proof.ci: the chrome frames, row by row."""
    sys.path.insert(0, HERE)
    frames, cur = {}, None
    with open(path) as f:
        for line in f:
            p = line.split()
            if p and p[0] == "frame":
                cur = []
                frames[p[1]] = (int(p[2]), int(p[3]), cur)
            elif p and p[0] == "r":
                row = []
                for k in range(1, len(p), 2):
                    row += [int(p[k], 16)] * int(p[k + 1])
                cur.append(row)
    return frames


if __name__ == "__main__":
    frames = check_proof(sys.argv[1])
    # The proof's chrome lines (tests/font/proof.ci chrome_line and gap), dark theme words of kit/tokens.ci.
    lines = [(LABEL, 1, "SECTION LABEL 11 PX SEMIBOLD \u00b7 RECENT FILES", 28),
             (BODY, 0, "Body 13 px: The quick brown fox jumps over the lazy dog. 0123456789", 24),
             (BODY, 0, "Latin-1: \u00c0\u00e9\u00ee\u00f5\u00fc \u00c7\u00d1\u00df \u00e6\u00f8\u00e5 \u00ab\u00bb \u00bf\u00a1 \u201cquotes\u201d \u2018single\u2019 \u2013 \u2014 \u20ac \u00a3 \u00a5 \u00a9 \u00ae \u00b0", 24),
             (NAME, 0, "Finder   Terminal   Editor   Settings   Calculator   Viewer   (13 px 500)", 24),
             (SEARCH, 0, "Search apps, files and windows", 34),
             (SEARCH, 1, "No recent files", 26),
             (TITLE, 0, "Open in Editor", 34),
             (PATH, 1, "/home/opt/cint/bin/cint   12.0 MB   2026-11-10 03:45", 24)]
    themes = {"dark": (0x1D2021, 0xF3EFE6, 0xA8A295), "light": (0xF5F4F0, 0x141413, 0x525E6E)}
    bad = 0
    for theme, (ground, ink, dim) in themes.items():
        for z in (1, 2):
            w, h, rows = frames["chrome-%s-%dx" % (theme, z)]
            for y in range(h):
                row = [ground] * w
                base = 0
                for role, isdim, s, gap in lines:
                    base += gap * z
                    text(row, y, 24 * z, base, w, s.encode(), dim if isdim else ink, role, z)
                if row != rows[y]:
                    bad += 1
            print("%s  textwin: chrome-%s-%dx equals the kit's %d rows" % ("PASS" if not bad else "FAIL", theme, z, h))
    sys.exit(1 if bad else 0)
