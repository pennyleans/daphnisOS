#!/usr/bin/env python3
"""tools/wheel.py: the loading wheel (DN-37, DN-38), user/ci/kit/wheel.ci's tables and its twin.

  python3 tools/wheel.py --write      the tables between the markers of user/ci/kit/wheel.ci
  python3 tools/wheel.py --check      the file's tables are these (status 1 otherwise)
  python3 tools/wheel.py --sums       the sums tests/dn37/wheel_test.ci pins
  python3 tools/wheel.py --proof PNG  dark, light (16, 24, 32 px; shares 0, 25, 50, 100; unknown at 0, 300, 600,
                                      900 ms) and the Busy pointer, at 2x, scaled 2x

The geometry is DN-37's 24-unit box: a disc at 12,12 r10.25 under a 1.5 edge, an arc r6 of stroke 3.5 with round
caps from 12 o'clock clockwise. A box of q quarter pixels at zoom z has n = q * z samples across, 4 a device pixel;
coordinates are in units of 1 / (8 n) box units, so every sample center and radius is an integer. Angles are
quarter degrees clockwise from 12 o'clock, by the tan table (0 to 45 degrees) and the sin table (0 to 90).
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(ROOT, "user", "ci", "kit", "wheel.ci")
ONE = 65536
TAN = [round(math.tan(math.radians(k / 4)) * ONE) for k in range(181)]
SIN = [round(math.sin(math.radians(k / 4)) * ONE) for k in range(361)]
COLORS = {0: (0x141413, 0xF3EFE6, 0xFABD2F), 1: (0xE8EAEE, 0x141413, 0xC98F00)}   # disc, edge, arc (DN-38)
TURN_MS = 1200                                      # one turn, linear (DN-37)
QUARTER = 360                                       # the unknown arc: a quarter turn, in quarter degrees


def tables():
    def arr(name, vals):
        rows = []
        for i in range(0, len(vals), 12):
            rows.append("    " + ", ".join(str(v) for v in vals[i:i + 12]))
        return "I64[%d] %s = [\n%s];\n" % (len(vals), name, ",\n".join(rows))
    return arr("TAN", TAN) + arr("SIN", SIN)


def atan_q(u, v):
    """u >= 0, v > 0: the angle of (u, v) from +v toward +u, quarter degrees 0..359."""
    if u <= v:
        t = u * ONE // v
        lo, hi = 0, 180
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if TAN[mid] <= t:
                lo = mid
            else:
                hi = mid - 1
        if lo < 180 and TAN[lo + 1] - t < t - TAN[lo]:
            lo += 1
        return lo
    return 360 - atan_q(v, u)


def angle(u, v):
    """Clockwise from 12 o'clock (v up), 0..1439."""
    q = 0
    while not (u >= 0 and v > 0):
        u, v = -v, u
        q += 1
    a = q * 360 + atan_q(u, v)
    return a % 1440


def sin_q(a):
    a %= 1440
    if a <= 360:
        return SIN[a]
    if a <= 720:
        return SIN[720 - a]
    if a <= 1080:
        return -SIN[a - 720]
    return -SIN[1440 - a]


def cos_q(a):
    return sin_q(a + 360)


def tdiv(a, b):
    """a / b truncated toward zero, as cint divides."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def span(share, t_ms, motion):
    """The arc as (start, length) in quarter degrees; length 0 none, 1440 the full ring."""
    if share >= 0:
        return 0, min(share, 100) * 1440 // 100
    if not motion:
        return 0, QUARTER
    return (t_ms % TURN_MS) * 1440 // TURN_MS, QUARTER


def classify(u, v, n, st, ln):
    """0 outside, 1 disc, 2 edge, 3 arc, for the sample at (u, v) from the center."""
    d2 = u * u + v * v
    if ln > 0:
        if 34 * n * 34 * n <= d2 <= 62 * n * 62 * n:
            if ln >= 1440:
                return 3
            a = angle(u, v) if d2 > 0 else 0
            if (a - st) % 1440 < ln:
                return 3
        if ln < 1440:
            for e in (st, st + ln):
                cu = tdiv(48 * n * sin_q(e), ONE)
                cv = tdiv(48 * n * cos_q(e), ONE)
                if (u - cu) ** 2 + (v - cv) ** 2 <= 14 * n * 14 * n:
                    return 3
    if 76 * n * 76 * n <= d2 <= 88 * n * 88 * n:
        return 2
    if d2 <= 82 * n * 82 * n:
        return 1
    return 0


def mix(bg, cols, counts, total):
    out = 0
    for sh in (16, 8, 0):
        acc = ((bg >> sh) & 255) * (total - sum(counts))
        for c, k in zip(cols, counts):
            acc += ((c >> sh) & 255) * k
        out |= (acc // total) << sh
    return out


def row_at(row, y, x0, y0, q, z, th, share, t_ms, motion):
    """kit/wheel.ci row_at."""
    n = q * z
    px = (n + 3) // 4
    if y < y0 or y >= y0 + px:
        return
    st, ln = span(share, t_ms, motion)
    cols = COLORS[th]
    for x in range(x0, min(x0 + px, len(row))):
        if x < 0:
            continue
        counts = [0, 0, 0]
        for j in range(4):
            sy = 4 * (y - y0) + j
            for i in range(4):
                sx = 4 * (x - x0) + i
                if sx >= n or sy >= n:
                    continue
                u = 192 * sx + 96 - 96 * n
                v = 96 * n - (192 * sy + 96)
                c = classify(u, v, n, st, ln)
                if c > 0:
                    counts[c - 1] += 1
        if sum(counts) > 0:
            row[x] = mix(row[x], cols, counts, 16)


# the Busy pointer: the kernel's arrow (src/cursor.ci) and the dark wheel, r4.5 (a box of 42 quarter pixels), its box's
# top left at (BUSY_X, BUSY_Y) from the hot spot
ARROW_EDGE = [0x80, 0xC0, 0xA0, 0x90, 0x88, 0x84, 0x82, 0x81, 0x87, 0x94, 0xAA, 0xCA, 0x85, 0x05, 0x02, 0x00]
ARROW_BODY = [0x00, 0x00, 0x40, 0x60, 0x70, 0x78, 0x7C, 0x7E, 0x78, 0x68, 0x44, 0x04, 0x02, 0x02, 0x00, 0x00]
BUSY_Q, BUSY_X, BUSY_Y = 42, 9, 10
PAPER, INK = 0xF3EFE6, 0x141413


def sprite_px(px, py, q, z, th, share, t_ms, motion):
    """kit/wheel.ci sprite_px: 0xAARRGGBB, AA the coverage in sixteenths."""
    n = q * z
    st, ln = span(share, t_ms, motion)
    counts = [0, 0, 0]
    for j in range(4):
        sy = 4 * py + j
        for i in range(4):
            sx = 4 * px + i
            if sx < n and sy < n:
                c = classify(192 * sx + 96 - 96 * n, 96 * n - (192 * sy + 96), n, st, ln)
                if c > 0:
                    counts[c - 1] += 1
    tot = sum(counts)
    if tot == 0:
        return 0
    w = tot << 24
    for k in range(3):
        sh = 8 * k
        v = sum(((col >> sh) & 255) * cnt for col, cnt in zip(COLORS[th], counts))
        w |= (v // tot) << sh
    return w


def blend(under, px):
    """kit/wheel.ci blend, src/cursor.ci blend."""
    a = (px >> 24) & 255
    if a <= 0:
        return under
    a = min(a, 16)
    out = 0
    for k in range(3):
        sh = 8 * k
        c, u = (px >> sh) & 255, (under >> sh) & 255
        out |= ((c * a + u * (16 - a)) // 16) << sh
    return out


def busy_row(row, y, x0, y0, z, t_ms, motion):
    """kit/wheel.ci busy_row: the sprite blended, then the arrow."""
    side = (BUSY_Q * z + 3) // 4
    sx0, sy0 = x0 + BUSY_X * z, y0 + BUSY_Y * z
    if sy0 <= y < sy0 + side:
        for px in range(side):
            x = sx0 + px
            if 0 <= x < len(row):
                row[x] = blend(row[x], sprite_px(px, y - sy0, BUSY_Q, z, 0, -1, t_ms, motion))
    j = (y - y0) // z
    if 0 <= j < 16 and y >= y0:
        for i in range(8):
            m = 0x80 >> i
            c = INK if ARROW_BODY[j] & m else PAPER if ARROW_EDGE[j] & m else None
            if c is not None:
                for k in range(z):
                    x = x0 + i * z + k
                    if 0 <= x < len(row):
                        row[x] = c


def sprite_sum(z, t):
    side = (BUSY_Q * z + 3) // 4
    s = 0
    for py in range(side):
        for px in range(side):
            s = (s * 31 + sprite_px(px, py, BUSY_Q, z, 0, -1, t, True)) % 1000000007
    return s


# the frames tests/dn37/wheel_test.ci pins: (size in quarter pixels, share, t ms)
FRAMES = [(q, s, 0) for q in (64, 96, 128) for s in (0, 25, 50, 100)] + \
         [(q, -1, t) for q in (64, 96, 128) for t in (0, 300, 600, 900)]
GROUND = {0: 0x1E2124, 1: 0xF4F2EE}


def frame_sum(q, z, th, share, t):
    n = q * z
    px = (n + 3) // 4
    s = 0
    for y in range(px):
        row = [GROUND[th]] * px
        row_at(row, y, 0, 0, q, z, th, share, t, True)
        for x in range(px):
            s = (s * 31 + row[x]) % 1000000007
    return s


def busy_sum(z, t):
    w, h = 30 * z, 30 * z
    s = 0
    for y in range(h):
        row = [GROUND[1]] * w
        busy_row(row, y, 0, 0, z, t, True)
        for x in range(w):
            s = (s * 31 + row[x]) % 1000000007
    return s


def sums():
    out = []
    for q, sh, t in FRAMES:
        for th in (0, 1):
            for z in (1, 2):
                out.append(frame_sum(q, z, th, sh, t))
    print("frames", out)
    print("busy", [busy_sum(z, t) for z in (1, 2) for t in (0, 600)])
    print("sprite", [sprite_sum(z, t) for z in (1, 2) for t in (0, 600)])


def check():
    s = open(KIT).read()
    a = s.index("// --- tables (tools/wheel.py) ---\n") + len("// --- tables (tools/wheel.py) ---\n")
    b = s.index("// --- end of tables ---")
    if s[a:b] != tables():
        print("FAIL  wheel: user/ci/kit/wheel.ci's tables are not tools/wheel.py's")
        return 1
    print("PASS  wheel: user/ci/kit/wheel.ci's tables are tools/wheel.py's")
    return 0


def write():
    s = open(KIT).read()
    a = s.index("// --- tables (tools/wheel.py) ---\n") + len("// --- tables (tools/wheel.py) ---\n")
    b = s.index("// --- end of tables ---")
    open(KIT, "w").write(s[:a] + tables() + s[b:])
    return 0


def proof(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import png
    z, pad = 2, 16
    cells = []
    for th in (0, 1):
        line = [(q, s, 0) for q in (64, 96, 128) for s in (0, 25, 50, 100)]
        cells.append((th, line))
        cells.append((th, [(q, -1, t) for q in (64, 96, 128) for t in (0, 300, 600, 900)]))
    cw = 32 * z + pad
    w = pad + 12 * cw + 2 * 30 * z + 2 * pad
    h = pad + len(cells) * cw
    rows = [[0x808080] * w for _ in range(h)]
    for r, (th, line) in enumerate(cells):
        y0 = pad + r * cw
        for y in range(y0 - pad // 2, y0 + 32 * z + pad // 2):
            for x in range(pad // 2, pad + 12 * cw - pad // 2):
                rows[y][x] = GROUND[th]
        for c, (q, s, t) in enumerate(line):
            x0 = pad + c * cw
            for y in range(y0, y0 + 32 * z):
                row_at(rows[y], y, x0, y0, q, z, th, s, t, True)
    bx = pad + 12 * cw + pad
    for k, t in enumerate((0, 600)):
        y0 = pad + 2 * k * cw
        for y in range(y0, y0 + 30 * z):
            for x in range(bx + k * 30 * z, bx + (k + 1) * 30 * z):
                rows[y][x] = GROUND[1 - k]
            busy_row(rows[y], y, bx + k * 30 * z + 4, y0 + 4, z, t, True)
    big = []
    for r in rows:
        line = [c for c in r for _ in range(2)]
        big.append(line)
        big.append(list(line))
    png.write(path, 2 * w, 2 * h, big)
    print("wheel proof: %s" % path)
    return 0


def main(argv):
    if argv[:1] == ["--write"]:
        return write()
    if argv[:1] == ["--check"]:
        return check()
    if argv[:1] == ["--sums"]:
        return sums()
    if argv[:1] == ["--proof"]:
        return proof(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
