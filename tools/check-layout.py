#!/usr/bin/env python3
"""tools/check-layout.py [BINARY ...]: stage H's layout (unit H-1, docs/specs/2026-11-05-h-hybrid.md sections 4, 5
and 7). The Python twin of user/ci/kit/layout.ci runs the cases of user/ci/hlayout.ci and prints the same lines;
each BINARY (a build of user/ci/hlayout.ci) must print them byte for byte. With no BINARY, prints the lines.
K-7: tiles GAP apart and from the plane's edges; the color mark (user/ci/kit/cmark.ci) is fingerprinted at 20, 440
and 480 px against this file's twin, which reads user/ci/kit/cmark.svg itself."""
import os
import re
import subprocess
import sys
from fractions import Fraction as Q

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user", "ci", "kit")

WINS, RECTS, BAR, GAP = 16, 32, 28, 8
TILED, FLOAT, MONOCLE, MINIMIZED = 0, 1, 2, 3
OVERLAY, RANK_CAP = 15, 1 << 40


def svg_shapes(path):
    """K-5: user/ci/kit/cmark.svg's shapes in paint order as (test, word): each test takes a point (u, v) and n, the
    point in tenths of the SVG's units times n (every constant of the SVG is a whole number of tenths), and the word
    is the fill's hex as an XRGB word. Rects are half open; circles, polygons and the half disks of the two arc paths
    closed; a circle clipped by the polygon is both tests."""
    svg = open(path, encoding="ascii").read()

    def num(v):
        t = Q(v) * 10
        assert t.denominator == 1, v
        return int(t)

    def poly(pts):
        ps = [tuple(map(num, q.split(","))) for q in pts.split()]

        def inside(x, y, n):
            sg = [(bx - ax) * n * (y - ay * n) - (by - ay) * n * (x - ax * n)
                  for (ax, ay), (bx, by) in zip(ps, ps[1:] + ps[:1])]
            return all(v <= 0 for v in sg) or all(v >= 0 for v in sg)
        return inside

    clips = {m.group(1): poly(m.group(2)) for m in
             re.finditer(r'<clipPath id="([^"]+)">\s*<polygon points="([^"]+)"', svg)}
    body = svg.split("</defs>")[1]
    out = []
    for m in re.finditer(r"<(rect|circle|path|polygon) ([^>]*)/>", body):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(2)))
        word = int(a["fill"][1:], 16)
        if m.group(1) == "rect":
            x0, y0 = num(a["x"]), num(a["y"])
            x1, y1 = x0 + num(a["width"]), y0 + num(a["height"])
            t = lambda x, y, n, x0=x0, y0=y0, x1=x1, y1=y1: x0 * n <= x < x1 * n and y0 * n <= y < y1 * n
        elif m.group(1) == "circle":
            cx, cy, r = num(a["cx"]), num(a["cy"]), num(a["r"])
            t = lambda x, y, n, cx=cx, cy=cy, r=r: (x - cx * n) ** 2 + (y - cy * n) ** 2 <= (r * n) ** 2
            if "clip-path" in a:
                c = clips[re.match(r"url\(#(.*)\)", a["clip-path"]).group(1)]
                t = lambda x, y, n, t=t, c=c: t(x, y, n) and c(x, y, n)
        elif m.group(1) == "polygon":
            t = poly(a["points"])
        else:                            # M x y0 A r r 0 0 sweep x y1 Z: the half disk on the sweep's side
            v = a["d"].split()
            mx, y0, r, sweep, y1 = num(v[1]), num(v[2]), num(v[4]), v[8], num(v[10])
            assert (y0 + y1) % 2 == 0
            cy, right = (y0 + y1) // 2, (sweep == "1") == (y1 > y0)
            t = lambda x, y, n, mx=mx, cy=cy, r=r, right=right: (x - mx * n) ** 2 + (y - cy * n) ** 2 <= (r * n) ** 2 \
                and (x >= mx * n if right else x <= mx * n)
        out.append((t, word))
    return out


SHAPES = svg_shapes(os.path.join(KIT, "cmark.svg"))


def cmark_at(n, x, y):
    """Pixel (x, y) of the n x n color mark: the word of its center under the shapes, None where clear."""
    u, v, c = 160 * (2 * x + 1), 160 * (2 * y + 1), None
    for t, word in SHAPES:
        if t(u, v, n):
            c = word
    return c


def cmark_px(n):
    """The n x n color mark: rows of words, None where clear."""
    return [[cmark_at(n, x, y) for x in range(n)] for y in range(n)]


def emblem(n):
    """K-7: hlayout's fingerprint of the n x n color mark: the pixels of each token (tokens.ci's lockup table, by word) and
    the sum over painted pixels of (y * n + x + 1) * (token + 2)."""
    with open(os.path.join(KIT, "tokens.ci")) as f:
        words = [int(v, 16) for v in re.search(r"U32\[6\] lockup_words = \[([^\]]*)\]", f.read()).group(1)
                 .replace(",", " ").split()]
    cnt, tot = [0] * 6, 0
    for y, r in enumerate(cmark_px(n)):
        for x, c in enumerate(r):
            if c is not None:
                t = words.index(c)
                cnt[t] += 1
                tot += (y * n + x + 1) * (t + 2)
    return "layout: emblem %d tokens %s sum %d" % (n, " ".join(map(str, cnt)), tot)


class Layout:
    def __init__(self, w, h, scale):
        self.sw, self.sh, self.sc = w, h, scale
        self.win = {}          # i: [desk, mode, rank, x, y, w, h]
        self.rects = {}
        self.mru = []
        self.dirs = {}         # HX-14: desktop: 0 the long side, 1 columns, 2 rows
        self.cd = 1

    def put(self, i, d, m, r, x, y, w, h):
        self.win[i] = [d, m, r, x, y, w, h]

    def plane_y(self):
        return BAR * self.sc

    @staticmethod
    def at(a, span, n, i):
        return a + span if i == n else a + i * (span // n)

    def tile(self, i, k, n):
        py, pw = self.plane_y(), self.sw
        ph = self.sh - py
        cols = rows = span = 1
        c = r = 0
        if n == 2:
            cols, c = 2, k
        elif n == 3:
            cols = rows = 2
            if k == 0:
                span = 2
            else:
                c, r = 1, k - 1
        elif n >= 4:
            cols, rows, c, r = (n + 1) // 2, 2, k // 2, k % 2
            if n % 2 == 1 and k == n - 1:
                span, r = 2, 0
        w = self.win[i]
        dr = self.dirs.get(self.cd, 0)
        g = GAP * self.sc                     # K-7: cells over the plane less a gap, each frame a gap into its cell
        if (dr == 0 and ph > pw) or dr == 2:  # HX-12 A: portrait turns the grid; HX-14: or the desktop says rows
            w[4] = self.at(py, ph - g, cols, c) + g
            w[6] = self.at(py, ph - g, cols, c + 1) - w[4]
            w[3] = self.at(0, pw - g, rows, r) + g
            w[5] = self.at(0, pw - g, rows, r + span) - w[3]
            return
        w[3] = self.at(0, pw - g, cols, c) + g
        w[5] = self.at(0, pw - g, cols, c + 1) - w[3]
        w[4] = self.at(py, ph - g, rows, r) + g
        w[6] = self.at(py, ph - g, rows, r + span) - w[4]

    def layer(self, i):
        m = self.win[i][1]
        if i == OVERLAY:
            return RANK_CAP + 2
        return 0 if m == TILED else 1 + min(max(self.win[i][2], 0), RANK_CAP)

    def shown(self, i, d):
        return i in self.win and self.win[i][0] == d and self.win[i][1] != MINIMIZED

    def above(self, j, i):
        a, b = self.layer(j), self.layer(i)
        return a > b or (a == b and j > i)

    def clip(self, i, d):
        _, _, _, x, y, w, h = self.win[i]
        occ = [self.win[j][3:] for j in range(WINS) if j != i and self.shown(j, d) and self.above(j, i)]
        ys = sorted({y} | {v for (ox, oy, ow, oh) in occ for v in (oy, oy + oh) if y < v < y + h}) + [y + h]
        out, prev, prev_y1, first = [], [], -1, 0
        for b in range(len(ys) - 1):
            y0, y1 = ys[b], ys[b + 1]
            cover = [(ox, ox + ow) for (ox, oy, ow, oh) in occ if oy <= y0 and oy + oh >= y1]
            xs = sorted({x} | {v for (a0, a1) in cover for v in (a0, a1) if x < v < x + w}) + [x + w]
            spans = []
            for k in range(len(xs) - 1):
                x0, x1 = xs[k], xs[k + 1]
                if any(a0 <= x0 and a1 >= x1 for (a0, a1) in cover):
                    continue
                if spans and spans[-1][1] == x0:
                    spans[-1][1] = x1
                else:
                    spans.append([x0, x1])
            if spans and spans == prev and prev_y1 == y0:
                for k in range(len(spans)):
                    out[first + k][3] = y1 - out[first + k][1]
            elif spans:
                if len(out) + len(spans) > RECTS:
                    return -1
                first = len(out)
                out += [[a, y0, b_ - a, y1 - y0] for a, b_ in spans]
                prev = [list(s) for s in spans]
            else:
                prev = []
            if spans:
                prev_y1 = y1
        return out

    def compute(self, d):
        self.cd = d
        tiled = sorted((i for i in self.win if self.shown(i, d) and self.win[i][1] == TILED), key=lambda i: (self.win[i][2], i))
        for k, i in enumerate(tiled):
            self.tile(i, k, len(tiled))
        for i in sorted(self.win):
            if self.shown(i, d) and self.win[i][1] == MONOCLE:
                self.win[i][3:] = [0, self.plane_y(), self.sw, self.sh - self.plane_y()]
        self.rects = {i: (self.clip(i, d) if self.shown(i, d) else []) for i in self.win}

    def focus(self, i):
        if i in self.mru:
            self.mru.remove(i)
        self.mru.insert(0, i)

    def entries(self, d):
        return [i for i in self.mru if i in self.win and self.win[i][0] == d]


def show(out, L, c, d):
    L.compute(d)
    out.append("layout: case %d screen %dx%d scale %d desktop %d" % (c, L.sw, L.sh, L.sc, d))
    for i in sorted(L.win):
        dk, m, _, x, y, w, h = L.win[i]
        rs = L.rects[i]
        n = -1 if rs == -1 else len(rs)
        s = "layout: win %d desktop %d mode %d frame %d,%d %dx%d rects %d" % (i, dk, m, x, y, w, h, n)
        for r in (rs if rs != -1 else []):
            s += " %d,%d,%dx%d" % tuple(r)
        out.append(s)


def lines():
    out, c = [], 0
    for n in range(1, 9):
        L = Layout(1920, 1080, 1)
        for i in range(n):
            L.put(i, 1, TILED, 0, 0, 0, 0, 0)
        show(out, L, c, 1)
        c += 1
    L = Layout(1920, 1080, 1)
    for i in range(3):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    L.put(3, 1, FLOAT, 1, 640, 304, 960, 528)
    L.put(4, 1, FLOAT, 2, 1200, 600, 400, 320)
    show(out, L, c, 1)
    c += 1
    L = Layout(1920, 1080, 1)
    L.put(0, 1, TILED, 0, 0, 0, 0, 0)
    L.put(1, 1, MONOCLE, 0, 0, 0, 0, 0)
    L.put(2, 1, FLOAT, 1, 80, 64, 320, 200)
    L.put(3, 1, MINIMIZED, 0, 0, 0, 0, 0)
    L.put(4, 2, TILED, 0, 0, 0, 0, 0)
    show(out, L, c, 1)
    c += 1
    show(out, L, c, 2)
    c += 1
    L = Layout(640, 480, 1)
    for i in range(5):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    show(out, L, c, 1)
    c += 1
    L = Layout(3840, 2160, 2)
    for i in range(3):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    show(out, L, c, 1)
    c += 1
    L = Layout(1920, 1080, 1)
    L.put(0, 1, TILED, 0, 0, 0, 0, 0)
    for i in range(1, 16):
        L.put(i, 1, FLOAT, i, 60 + 120 * (i - 1), 60 + 60 * (i - 1), 100, 100)
    show(out, L, c, 1)
    c += 1
    L = Layout(1920, 1080, 1)
    for i in range(3):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    L.put(3, 1, MINIMIZED, 0, 0, 0, 0, 0)
    L.put(4, 2, TILED, 0, 0, 0, 0, 0)
    for i in (3, 4, 0, 1, 2):
        L.focus(i)

    def switcher(d):
        out.append("layout: switcher desktop %d:%s" % (d, "".join(" %d" % e for e in L.entries(d))))
    switcher(1)
    L.focus(0)
    switcher(1)
    L.mru.remove(1)
    del L.win[1]
    switcher(1)
    switcher(2)
    L = Layout(1920, 1080, 1)
    for i, r in ((0, 3), (1, 1), (2, 2), (3, 1)):
        L.put(i, 1, TILED, r, 0, 0, 0, 0)
    show(out, L, c, 1)
    c += 1
    for n in (1, 2, 3, 5):
        L = Layout(1080, 1920, 1)
        for i in range(n):
            L.put(i, 1, TILED, 0, 0, 0, 0, 0)
        show(out, L, c, 1)
        c += 1
    L = Layout(1920, 1080, 1)
    for i in range(3):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    L.dirs[1] = 2
    show(out, L, c, 1)
    c += 1
    L = Layout(1080, 1920, 1)
    for i in range(3):
        L.put(i, 1, TILED, 0, 0, 0, 0, 0)
    L.dirs[1] = 1
    show(out, L, c, 1)
    c += 1
    # HX-1: a monocle window ranked over a float covers it; the float ranked after covers the monocle window
    for r in (3, 1):
        L = Layout(1920, 1080, 1)
        L.put(0, 1, TILED, 0, 0, 0, 0, 0)
        L.put(1, 1, MONOCLE, r, 0, 0, 0, 0)
        L.put(2, 1, FLOAT, 2, 400, 300, 640, 400)
        show(out, L, c, 1)
        c += 1
    # HX-1: the overlay over a float whose rank was pushed past 10^6 and past RANK_CAP
    L = Layout(1920, 1080, 1)
    L.put(3, 1, FLOAT, 2000000, 200, 200, 800, 600)
    L.put(4, 1, FLOAT, (1 << 50), 300, 300, 800, 600)
    L.put(OVERLAY, 1, FLOAT, 1000000, 400, 400, 400, 300)
    show(out, L, c, 1)
    c += 1
    for n in (20, 440, 480):
        out.append(emblem(n))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import textwin
    every, pairs = bytes(range(32, 127)), b"Il1| O0o rn m daphnis 5S"
    for z in (1, 2):
        for s, x1 in ((every[:47], 800), (every[47:], 800), (pairs, 800), (pairs, 4 + 100 * z)):
            out.append(text_case(textwin, s, z, x1))
    out.append("layout: done")
    return out


def text_case(tw, s, z, x1):
    """FONT-1: user/ci/hlayout.ci's text_case: ctext.text of s in BODY at z, white on black, from pen 4 on the
    baseline at the face's ascent, stopped at x1, over the line box."""
    f = tw.face(tw.BODY, z)
    pen, ink, tot = 4, 0, 0
    for y in range(f.ascent + f.descent):
        row = [0] * 800
        pen = tw.text(row, y, 4, f.ascent, x1, s, 0xFFFFFF, tw.BODY, z)
        for x, v in enumerate(row):
            if v:
                ink += 1
                tot += (y * 800 + x + 1) * (v & 255)
    return "layout: text body %d n %d to %d width %d pen %d ink %d sum %d" % (z, len(s), x1, tw.width(s, tw.BODY, z),
                                                                             pen, ink, tot)


def main(argv):
    want = lines()
    if not argv:
        print("\n".join(want))
        return 0
    bad = 0
    for b in argv:
        try:
            got = subprocess.run([b], stdout=subprocess.PIPE, timeout=60).stdout.decode("ascii", "replace").splitlines()
        except (OSError, subprocess.TimeoutExpired) as e:
            got = [str(e)]
        diff = next(((g, w) for g, w in zip(got + [None] * len(want), want) if g != w), None)
        ok = got == want
        bad += not ok
        print("%s  %s prints the %d lines of the Python twin%s" % ("PASS" if ok else "FAIL", b, len(want),
                                                                   "" if ok else ": first difference %r" % (diff,)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
