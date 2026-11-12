#!/usr/bin/env python3
"""tools/wbglyph.py [--check]: the window bar's stroked button glyphs (DN-23, design note 23, l's approval of frame 8)
into user/ci/kit/wbglyph.ci. With --check, exits 1 if the module is not what this file writes.

Each glyph is a 12 x 12 box of the sheet's paths, stroked 1.5 px with round caps and joins and no fill: minimize
`M2 9.5H10`; full screen `M2 5V2H5M7 2H10V5M10 7V10H7M5 10H2V7`; tile the rect 1.75,1.75 8.5 x 8.5 rx 1.5 and
`M6 2V10`; close `M2.5 2.5L9.5 9.5M9.5 2.5L2.5 9.5`. At scale z (1, 2, 3) every coordinate and the stroke are
times z. A pixel's value is the count, 0 to 16, of its 4 x 4 samples at ((8 x + 2 i + 1) / 8, (8 y + 2 j + 1) / 8)
inside the stroke, tested exactly in integers (eighths of a pixel), as kit/shape.ci samples an edge: a sample is in
a stroked segment when its distance to the segment is at most 0.75 z (round caps and joins are the union of these
capsules), and in the rect's stroke when it is inside the rect grown by 0.75 z (radius 2.25 z) and not inside the
rect shrunk by 0.75 z (radius 0.75 z). The module holds one U8 table, glyph k at scale z from G_AT[3 k + z - 1],
12 z rows of 12 z values; tools/check-hdesk.py reads the same table."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "wbglyph.ci")

# The glyphs' segments and the tile's rect, in eighths of the 12 unit box at z 1.
SEGS = [
    [((16, 76), (80, 76))],                                                                    # minimize
    [((16, 40), (16, 16)), ((16, 16), (40, 16)), ((56, 16), (80, 16)), ((80, 16), (80, 40)),
     ((80, 56), (80, 80)), ((80, 80), (56, 80)), ((40, 80), (16, 80)), ((16, 80), (16, 56))],  # full screen
    [((48, 16), (48, 80))],                                                                    # tile, its bar
    [((20, 20), (76, 76)), ((76, 20), (20, 76))],                                              # close
]
RECT = (14, 14, 82, 82, 12)      # tile: x0, y0, x1, y1, rx in eighths at z 1
HALF = 6                         # half the stroke, 0.75 px, in eighths


def seg_in(u, v, a, b, r):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = (u - ax) * dx + (v - ay) * dy
    if t <= 0:
        return (u - ax) ** 2 + (v - ay) ** 2 <= r * r
    if t >= l2:
        return (u - bx) ** 2 + (v - by) ** 2 <= r * r
    pu, pv = u - ax, v - ay
    return (pu * pu + pv * pv) * l2 - t * t <= r * r * l2


def rr_in(u, v, x0, y0, x1, y1, r):
    """(u, v) inside the rounded rectangle, all in eighths (as kit/shape.ci inside, closed edges)."""
    if u < x0 or u > x1 or v < y0 or v > y1:
        return False
    dx = max(0, x0 + r - u, u - (x1 - r))
    dy = max(0, y0 + r - v, v - (y1 - r))
    return dx * dx + dy * dy <= r * r


def covered(k, z, u, v):
    r = HALF * z
    if any(seg_in(u, v, (a[0] * z, a[1] * z), (b[0] * z, b[1] * z), r) for a, b in SEGS[k]):
        return True
    if k == 2:
        x0, y0, x1, y1, rx = (c * z for c in RECT)
        return rr_in(u, v, x0 - r, y0 - r, x1 + r, y1 + r, rx + r) and not \
            rr_in(u, v, x0 + r, y0 + r, x1 - r, y1 - r, rx - r)
    return False


def glyph(k, z):
    n = 12 * z
    return [[sum(covered(k, z, 8 * x + 2 * i + 1, 8 * y + 2 * j + 1) for j in range(4) for i in range(4))
             for x in range(n)] for y in range(n)]


def tables():
    vals, at = [], []
    for k in range(4):
        for z in (1, 2, 3):
            at.append(len(vals))
            for r in glyph(k, z):
                vals += r
    return at, vals


def module():
    at, vals = tables()
    L = ["// user/ci/kit/wbglyph.ci: the window bar's four stroked button glyphs (DN-23: minimize, full screen, tile,",
         "// close), 12 x 12 at 1x and every coordinate and the 1.5 px stroke times z at 2x and 3x; written by",
         "// tools/wbglyph.py; do not edit. A value is the count, 0 to 16, of a pixel's 4 x 4 samples in the stroke.",
         "",
         "I64[12] G_AT = [%s];" % ", ".join(str(a) for a in at),
         "U8[%d] cov = [" % len(vals)]
    for i in range(0, len(vals), 32):
        L.append("    " + ", ".join(str(v) for v in vals[i:i + 32]) + ("," if i + 32 < len(vals) else ""))
    L += ["];", "",
          "// The count, 0 to 16, of pixel (x, y) of glyph k (0 minimize, 1 full screen, 2 tile, 3 close) at scale z.",
          "export I64 at(I64 k, I64 z, I64 x, I64 y) {",
          "    if (k < 0 || k > 3 || z < 1 || z > 3 || x < 0 || y < 0 || x >= 12 * z || y >= 12 * z) { return 0; }",
          "    return cov[G_AT[3 * k + z - 1] + 12 * z * y + x] as I64;",
          "}",
          "// SPDX-License-Identifier: Apache-2.0"]
    return "\n".join(L) + "\n"


def main():
    text = module()
    if sys.argv[1:] == ["--check"]:
        ok = os.path.exists(OUT) and open(OUT).read() == text
        print("%s  wbglyph: user/ci/kit/wbglyph.ci is what tools/wbglyph.py writes" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    open(OUT, "w").write(text)
    print("wrote user/ci/kit/wbglyph.ci, %d values" % len(tables()[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
