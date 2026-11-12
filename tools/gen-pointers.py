#!/usr/bin/env python3
# tools/gen-pointers.py: the pointer shapes of frame 26 (DN-51, design sheet "Pointer and drag feedback", generator
# gen/f25.py's CUR table) as src/cursor.ci's 24 x 24 tables at 1x. Each shape is the frame's dark strokes, 1.75
# wide with round caps and joins on a 24 unit grid, turned about (12, 12) where the frame turns it: a pixel is ink
# where they cover half of it or more (8 x 8 samples a pixel), and paper where it touches ink, a side or a corner,
# and is not ink itself: the frame's "dark core with a 1 px light edge". The Arrow keeps H-4's 8 x 16 table and
# Busy its sprite.
#   python3 tools/gen-pointers.py          the tables, as src/cursor.ci carries them
#   python3 tools/gen-pointers.py --check  exit 1 unless src/cursor.ci carries exactly these tables
#   python3 tools/gen-pointers.py --show   each shape in text: '#' ink, '+' paper
import math
import re
import sys

DARK = 1.75
N = 24
SS = 8

RH = [[(4, 12), (20, 12)], [(7.5, 8.5), (4, 12), (7.5, 15.5)], [(16.5, 8.5), (20, 12), (16.5, 15.5)]]
# (name, polylines, circles (cx, cy, r), turn in degrees, clockwise as SVG's rotate)
SHAPES = [
    ('TEXT', [[(9.5, 4.5), (14.5, 4.5)], [(12, 4.5), (12, 19.5)], [(9.5, 19.5), (14.5, 19.5)]], [], 0),
    ('MOVE', [[(12, 3.5), (12, 20.5)], [(3.5, 12), (20.5, 12)], [(9.5, 6), (12, 3.5), (14.5, 6)],
              [(9.5, 18), (12, 20.5), (14.5, 18)], [(6, 9.5), (3.5, 12), (6, 14.5)],
              [(18, 9.5), (20.5, 12), (18, 14.5)]], [], 0),
    ('WIDTH', RH, [], 0),
    ('HEIGHT', RH, [], 90),
    ('CORNER_NWSE', RH, [], 45),
    ('CORNER_NESW', RH, [], -45),
    ('AIM', [[(12, 4), (12, 10)], [(12, 14), (12, 20)], [(4, 12), (10, 12)], [(14, 12), (20, 12)]], [], 0),
    ('NOT_HERE', [[(7.25, 7.25), (16.75, 16.75)]], [(12, 12, 7)], 0),
]


def turn(p, deg):
    a = math.radians(deg)
    x, y = p[0] - 12, p[1] - 12
    return (12 + x * math.cos(a) - y * math.sin(a), 12 + x * math.sin(a) + y * math.cos(a))


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def inside(px, py, segs, circles, width):
    for a, b in segs:
        if seg_dist(px, py, a, b) <= width / 2:
            return True
    for cx, cy, r in circles:
        if abs(math.hypot(px - cx, py - cy) - r) <= width / 2:
            return True
    return False


def raster(lines, circles, deg):
    segs = []
    for pl in lines:
        q = [turn(p, deg) for p in pl]
        segs += list(zip(q, q[1:]))
    ink = [[False] * N for _ in range(N)]
    for j in range(N):
        for i in range(N):
            dark = 0
            for sy in range(SS):
                for sx in range(SS):
                    if inside(i + (sx + 0.5) / SS, j + (sy + 0.5) / SS, segs, circles, DARK):
                        dark += 1
            ink[j][i] = 2 * dark >= SS * SS
    edge = []
    body = []
    for j in range(N):
        e = 0
        b = 0
        for i in range(N):
            m = 1 << (N - 1 - i)
            if ink[j][i]:
                b |= m
            elif any(ink[y][x] for y in range(max(0, j - 1), min(N, j + 2)) for x in range(max(0, i - 1), min(N, i + 2))):
                e |= m
        edge.append(e)
        body.append(b)
    return edge, body


def tables():
    edge = []
    body = []
    for _, lines, circles, deg in SHAPES:
        e, b = raster(lines, circles, deg)
        edge += e
        body += b
    return edge, body


def words(v):
    out = []
    line = '   '
    for k, x in enumerate(v):
        w = ' 0x%06X,' % x
        if len(line) + len(w) > 118:
            out.append(line)
            line = '   '
        line += w
    out.append(line.rstrip(','))
    return '\n'.join(out)


def text():
    e, b = tables()
    return ('U32[%d] edge24 = [\n%s\n];\nU32[%d] body24 = [\n%s\n];\n' % (len(e), words(e), len(b), words(b)))


def main():
    if '--show' in sys.argv:
        e, b = tables()
        for k, s in enumerate(SHAPES):
            print(s[0])
            for j in range(N):
                r = ''
                for i in range(N):
                    m = 1 << (N - 1 - i)
                    r += '#' if b[N * k + j] & m else ('+' if e[N * k + j] & m else '.')
                print(r)
        return 0
    if '--check' in sys.argv:
        src = open('src/cursor.ci').read()
        m = re.search(r'U32\[\d+\] edge24 = \[.*?\];\nU32\[\d+\] body24 = \[.*?\];\n', src, re.S)
        if m is None or m.group(0) != text():
            print('src/cursor.ci: the pointer tables differ from tools/gen-pointers.py')
            return 1
        print('src/cursor.ci: the pointer tables are tools/gen-pointers.py\'s')
        return 0
    sys.stdout.write(text())
    return 0


if __name__ == '__main__':
    sys.exit(main())
