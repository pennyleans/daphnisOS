#!/usr/bin/env python3
"""tools/svgicons.py [--check]: the desk's icons of DN-5, DN-8, DN-9 and DN-12 (the app icons of draft 3 and the file
icons), rasterized from their SVG sources in tools/icons-v3/ and written to the kit tables user/ci/kit/icons3.ci (app
icons) and fileicons.ci (file icons), drawn by user/ci/kit/iconrle.ci; tools/iconwin.py is the twin.
Standard library only, integer arithmetic only: the same sources give the same tables on any machine.

Sources. tools/icons-v3/SOURCES.md holds each vendored file's sha256 and its studio-assets branch and commit, and the
manifest: one row an icon, its name, its kind (app or file), its 64 unit drawing and its sizes. At 16 px a hand-drawn
NAME_16.svg beside a drawing replaces it (DN-8, DN-12's general rule), at 1x and at 2x, where it is drawn at 32
device px; a row of the At table names another source for one size and scale. An icon NAME with a NAME_light
beside it in the manifest draws NAME_light on a light ground (program and program_light).

Geometry read: svg (a square viewBox from 0 0), g, rect (rx, ry equal), circle, path (M L H V A C Q Z, absolute and
relative), transform translate, uniform scale and rotate (DN-30's multiples of 45 exactly; DN-46 (d)'s other angles by
the rational rotation nearest them, tan of the half angle over at most 64), fill, fill-opacity, stroke, stroke-width, stroke-opacity,
stroke-linecap and stroke-linejoin; metadata is skipped. Anything else stops the tool. A stroke is drawn as a region:
an open subpath as the union of round-capped segments and arcs (round caps; round joins where it has two or more), a closed
one as the ring between its two offsets with miter joins (no corner on an arc, miter limit 4).

Raster. Every coordinate is an exact rational, then an integer on a grid of 2 * FINE units a sample; a pixel holds
16 x 16 samples at their centers, an outline crosses each sample row by nonzero winding (lines exactly, arcs by
integer square roots), as tools/ttf.py's coverage fill does. Layers are then laid shape by shape, as librsvg does:
coverage 0 to 256 to an 8-bit mask, times the layer's 8-bit opacity, over the layer below in 8-bit premultiplied
alpha with cairo's rounding. The baked shadow is two layers of the drawing (MS-R1: no runtime icon shadow).

Storage (the size budget of DN-5: under about 1 MB of hdesk's growth). Full RGBA would be 4.6 MB: 136 rasters,
1.16 M pixels. A raster is stored once a (source, device px), so 16 px at 2x is the 32 px table unless a hand-drawn
16 px drawing stands in. Each pixel is its exact (rgb, alpha) as one entry of a palette of the module, and a row
is 16-bit tokens: one pixel, or a run and its color; a row's trailing clear pixels are dropped. That is about 0.36
bytes a pixel, all sizes kept exact (no size is resampled from another). One module a kind, apps and files, so a
program that draws only file icons does not carry the app icons. The tables' sizes are in each module's header.

--check redraws everything, compares the generated modules and checks each source against its SOURCES.md sum, and
that every SVG in tools/icons-v3/ is listed there."""
import hashlib
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction as Q

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "icons-v3")
KIT = os.path.join(HERE, "..", "user", "ci", "kit")
SVG_NS = "{http://www.w3.org/2000/svg}"
FINE = 4096          # grid units a half sample: a sample center is at (2 k + 1) * FINE
SS = 16              # samples a pixel, across and down
SPDX = "// SPDX-License-Identifier: Apache-2.0"


def die(msg):
    raise SystemExit("svgicons.py: " + msg)


# ---- numbers ----------------------------------------------------------------------------------------------------

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def num(s):
    """A decimal string as an exact rational."""
    s = s.strip()
    if not NUM.fullmatch(s):
        die("not a number: %r" % s)
    return Q(s)


def qsqrt(v):
    """The square root of a rational v >= 0: exact when v is a square, else to within 2^-48, rounded down."""
    if v < 0:
        die("square root of a negative")
    v = Q(v)
    n, d = v.numerator, v.denominator
    rn, rd = math.isqrt(n), math.isqrt(d)
    if rn * rn == n and rd * rd == d:
        return Q(rn, rd)
    k = 1 << 48
    return Q(math.isqrt(n * k * k // d), k)


def rnd(v):
    """A rational to the nearest integer, halves up."""
    return math.floor(v + Q(1, 2))


# ---- the SVG reader ---------------------------------------------------------------------------------------------

def color(s):
    s = s.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", s):
        return int(s[1:], 16)
    if re.fullmatch(r"#[0-9a-fA-F]{3}", s):
        return int("".join(c * 2 for c in s[1:]), 16)
    die("not a color: %r" % s)


# DN-30: a rotation's cosine and sine as exact rationals: whole quarter turns exactly, the half quarter (45 degrees)
# as sqrt(2) / 2 to 18 decimals by an integer square root, so the tables stay the same on any machine.
HALF_SQRT2 = Q(math.isqrt(2 * 10 ** 36), 2 * 10 ** 18)
ROT = {0: (Q(1), Q(0)), 45: (HALF_SQRT2, HALF_SQRT2), 90: (Q(0), Q(1)), 135: (-HALF_SQRT2, HALF_SQRT2),
       180: (Q(-1), Q(0)), 225: (-HALF_SQRT2, -HALF_SQRT2), 270: (Q(0), Q(-1)), 315: (HALF_SQRT2, -HALF_SQRT2)}


def transform(s):
    """translate(tx ty), scale(s [s]) and rotate(a [cx cy]) for a a multiple of 45 degrees (DN-30), in order, as
    (k, c, s, tx, ty): p -> k R p + t, R the rotation by (c, s). Uniform scale only."""
    ops = re.findall(r"(\w+)\(([^)]*)\)", s)
    if re.sub(r"(\w+)\(([^)]*)\)", "", s).strip():
        die("transform %r" % s)
    m = (Q(1), Q(1), Q(0), Q(0), Q(0))
    for op, args in ops:
        a = [num(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if op == "translate" and len(a) in (1, 2):
            t = (Q(1), Q(1), Q(0), a[0], a[1] if len(a) == 2 else Q(0))
        elif op == "scale" and (len(a) == 1 or (len(a) == 2 and a[0] == a[1])):
            t = (a[0], Q(1), Q(0), Q(0), Q(0))
        elif op == "rotate" and len(a) in (1, 3):
            if a[0] % 45 == 0:
                c, sn = ROT[int(a[0] % 360)]
            else:
                # DN-46 (d): any other angle as an exact rational rotation: tan of half the angle as the nearest
                # fraction of denominator at most 64 (14 degrees: 7/57, 14.003 degrees), so every point stays rational
                half = Q(math.tan(math.radians(float(a[0]) / 2))).limit_denominator(64)
                c, sn = (1 - half * half) / (1 + half * half), 2 * half / (1 + half * half)
            cx, cy = (a[1], a[2]) if len(a) == 3 else (Q(0), Q(0))
            t = (Q(1), c, sn, cx - (c * cx - sn * cy), cy - (sn * cx + c * cy))   # about (cx, cy)
        else:
            die("transform %r: only translate, uniform scale and rotate" % s)
        m = compose(m, t)
    return m


def compose(outer, inner):
    """outer after inner: k_o R_o (k_i R_i p + t_i) + t_o."""
    ko, co, so, xo, yo = outer
    ki, ci, si, xi, yi = inner
    return (ko * ki, co * ci - so * si, so * ci + co * si, ko * (co * xi - so * yi) + xo, ko * (so * xi + co * yi) + yo)


def apply(m, p):
    k, c, s, tx, ty = m
    return (k * (c * p[0] - s * p[1]) + tx, k * (s * p[0] + c * p[1]) + ty)


PAINT = ("fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin")
SHAPE_ATTRS = {"rect": {"x", "y", "width", "height", "rx", "ry"}, "circle": {"cx", "cy", "r"}, "path": {"d"},
               "g": set()}
INHERIT = {"fill": "#000", "fill-opacity": "1", "stroke": "none", "stroke-width": "1", "stroke-opacity": "1",
           "stroke-linecap": "butt", "stroke-linejoin": "miter"}


class Layer:
    """One painted region: contours (lists of segments) filled by nonzero winding, an RGB and an opacity."""
    def __init__(self, contours, rgb, opacity):
        self.contours, self.rgb, self.opacity = contours, rgb, opacity


def read_svg(path):
    """(viewBox side, layers in paint order)."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        die("%s: %s" % (path, e))
    if root.tag != SVG_NS + "svg":
        die("%s: not an svg" % path)
    for a in root.attrib:
        if a not in ("viewBox",):
            die("%s: svg attribute %s" % (path, a))
    vb = [num(v) for v in root.get("viewBox", "").split()]
    if len(vb) != 4 or vb[0] or vb[1] or vb[2] != vb[3] or vb[2] <= 0:
        die("%s: viewBox must be 0 0 V V" % path)
    layers = []

    def walk(el, m, paint):
        for ch in el:
            tag = ch.tag[len(SVG_NS):] if ch.tag.startswith(SVG_NS) else None
            if tag == "metadata":
                continue
            if tag not in SHAPE_ATTRS:
                die("%s: element %s" % (path, ch.tag))
            p = dict(paint)
            cm = m
            for a, v in ch.attrib.items():
                if a in PAINT:
                    p[a] = v
                elif a == "transform":
                    cm = compose(m, transform(v))
                elif a not in SHAPE_ATTRS[tag]:
                    die("%s: %s attribute %s" % (path, tag, a))
            if tag == "g":
                walk(ch, cm, p)
            else:
                shape(path, tag, ch.attrib, cm, p, layers)

    walk(root, (Q(1), Q(1), Q(0), Q(0), Q(0)), INHERIT)
    return vb[2], layers


def opacity(s):
    v = num(s)
    if not 0 <= v <= 1:
        die("opacity %s" % s)
    return v


def shape(path, tag, at, m, p, layers):
    """Adds the fill and stroke layers of one rect, circle or path."""
    if tag == "rect":
        x, y, w, h = (num(at.get(k, "0")) for k in ("x", "y", "width", "height"))
        rx = at.get("rx")
        ry = at.get("ry")
        if rx is not None and ry is not None and num(rx) != num(ry):
            die("%s: rect rx != ry" % path)
        r = num(rx if rx is not None else (ry if ry is not None else "0"))
        r = min(r, w / 2, h / 2)
        subs = [(rect_path(x, y, w, h, r), True)]
    elif tag == "circle":
        cx, cy, r = (num(at[k]) for k in ("cx", "cy", "r"))
        subs = [([("A", (cx + r, cy), (cx - r, cy), (cx, cy), r, 1),
                  ("A", (cx - r, cy), (cx + r, cy), (cx, cy), r, 1)], True)]
    else:
        subs = parse_path(path, at["d"])
    subs = [([seg_map(s, m) for s in segs], closed) for segs, closed in subs]
    if p["fill"] != "none":
        cs = [segs for segs, _ in subs if segs]
        layers.append(Layer(cs, color(p["fill"]), opacity(p["fill-opacity"])))
    if p["stroke"] != "none":
        w = num(p["stroke-width"]) * m[0]
        layers.append(Layer(stroke(path, subs, w, p["stroke-linecap"], p["stroke-linejoin"]), color(p["stroke"]),
                            opacity(p["stroke-opacity"])))


def seg_map(s, m):
    if s[0] == "L":
        return ("L", apply(m, s[1]), apply(m, s[2]))
    return ("A", apply(m, s[1]), apply(m, s[2]), apply(m, s[3]), s[4] * m[0], s[5])


def rect_path(x, y, w, h, r):
    """The rounded rect as a closed list of segments, clockwise on the screen from (x + r, y)."""
    if r <= 0:
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [("L", pts[i], pts[(i + 1) % 4]) for i in range(4)]
    out = []
    corners = [((x + w - r, y), (x + w, y + r), (x + w - r, y + r)),
               ((x + w, y + h - r), (x + w - r, y + h), (x + w - r, y + h - r)),
               ((x + r, y + h), (x, y + h - r), (x + r, y + h - r)),
               ((x, y + r), (x + r, y), (x + r, y + r))]
    start = (x + r, y)
    for a, b, c in corners:
        if start != a:
            out.append(("L", start, a))
        out.append(("A", a, b, c, r, 1))
        start = b
    return out


PATH_TOK = re.compile(r"\s*,?\s*([MmLlHhVvAaCcQqZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


def parse_path(path, d):
    """Subpaths as ([segment], closed): segments ("L", p0, p1) and ("A", p0, p1, center, r, sweep), sweep 1 the
    positive angle way (clockwise on the screen); C and Q are cut in 16 lines each."""
    toks = []
    i = 0
    d = d.strip()
    while i < len(d):
        mt = PATH_TOK.match(d, i)
        if not mt or mt.end() == i:
            if d[i:].strip(" ,") == "":
                break
            die("%s: path data at %r" % (path, d[i:i + 12]))
        toks.append(mt.group(1))
        i = mt.end()
    subs = []
    segs = []
    cur = start = (Q(0), Q(0))
    k = 0
    cmd = None

    def take():
        nonlocal k
        if k >= len(toks) or toks[k].isalpha():
            die("%s: path wants a number after %s" % (path, cmd))
        k += 1
        return Q(toks[k - 1])

    def flag():
        nonlocal k
        if k >= len(toks):
            die("%s: arc flag" % path)
        t = toks[k]
        if t in ("0", "1"):
            k += 1
            return int(t)
        if t[0] in "01" and not t.isalpha():   # flags run into the next number: "01" or "1-6"
            toks[k] = t[1:]
            return int(t[0])
        die("%s: arc flag %r" % (path, t))

    while k < len(toks):
        if toks[k].isalpha():
            cmd = toks[k]
            k += 1
        elif cmd is None:
            die("%s: path starts with a number" % path)
        c = cmd.upper()
        rel = cmd != c
        ox, oy = cur if rel else (Q(0), Q(0))
        if c == "Z":
            if cur != start:
                segs.append(("L", cur, start))
            subs.append((segs, True))
            segs = []
            cur = start
            cmd = None
            continue
        if c == "M":
            if segs:
                subs.append((segs, False))
            segs = []
            cur = start = (ox + take(), oy + take())
            cmd = "l" if rel else "L"
            continue
        if c in "LHV":
            if c == "L":
                p = (ox + take(), oy + take())
            elif c == "H":
                p = (ox + take(), cur[1])
            else:
                p = (cur[0], oy + take())
            if p != cur:
                segs.append(("L", cur, p))
            cur = p
        elif c == "A":
            rx, ry, rot = take(), take(), take()
            fa, fs = flag(), flag()
            p = (ox + take(), oy + take())
            if rx != ry or rot != 0:
                die("%s: elliptical or turned arc" % path)
            if p != cur:
                segs.append(arc_seg(cur, p, abs(rx), fa, fs))
            cur = p
        elif c in "CQ":
            n = 3 if c == "C" else 2
            pts = [cur] + [(ox + take(), oy + take()) for _ in range(n)]
            steps = 16
            prev = cur
            for t in range(1, steps + 1):
                tt = Q(t, steps)
                q = bezier(pts, tt)
                segs.append(("L", prev, q))
                prev = q
            cur = pts[-1]
        else:
            die("%s: path command %s" % (path, cmd))
    if segs:
        subs.append((segs, False))
    return subs


def bezier(pts, t):
    while len(pts) > 1:
        pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
    return pts[0]


def arc_seg(p0, p1, r, fa, fs):
    """SVG arc (F.6.5) with rx = ry = r, no rotation: its center, by an exact square root where there is one."""
    x1p, y1p = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    q = x1p * x1p + y1p * y1p
    if r * r < q:
        r = qsqrt(q)
    k = qsqrt((r * r - q) / q)
    if fa == fs:
        k = -k
    c = (k * y1p + (p0[0] + p1[0]) / 2, -k * x1p + (p0[1] + p1[1]) / 2)
    return ("A", p0, p1, c, r, fs)


# ---- strokes as regions -----------------------------------------------------------------------------------------

def tangent(s, end):
    """The direction of segment s at its start (end False) or end."""
    if s[0] == "L":
        return (s[2][0] - s[1][0], s[2][1] - s[1][1])
    p = s[2] if end else s[1]
    v = (p[0] - s[3][0], p[1] - s[3][1])
    return (-v[1], v[0]) if s[5] else (v[1], -v[0])


def unit_normal(t):
    """perp(t) / |t|, perp(t) = (-ty, tx): the left of t turned the positive angle way."""
    n = qsqrt(t[0] * t[0] + t[1] * t[1])
    return (-t[1] / n, t[0] / n)


def capsule(a, b, h):
    """The round-capped segment a to b, half width h, as one closed contour of the positive winding."""
    t = (b[0] - a[0], b[1] - a[1])
    n = unit_normal(t)
    ap, bp = (a[0] + n[0] * h, a[1] + n[1] * h), (b[0] + n[0] * h, b[1] + n[1] * h)
    am, bm = (a[0] - n[0] * h, a[1] - n[1] * h), (b[0] - n[0] * h, b[1] - n[1] * h)
    return [("L", ap, bp), ("A", bp, bm, b, h, 0), ("L", bm, am), ("A", am, ap, a, h, 0)]


def arc_capsule(path, s, h):
    """The round-capped arc s, half width h, as capsule draws a segment: the arc moved h to its left, the cap at
    its end, the arc moved h to its right back to its start, the cap at its start (DN-59's gauge)."""
    a, b, c, r, sw = s[1], s[2], s[3], s[4], s[5]
    rl, rr = (r - h, r + h) if sw else (r + h, r - h)
    if rl < 0 or rr < 0:
        die("%s: a stroke is wider than an arc's radius" % path)

    def at(p, r2):
        return (c[0] + (p[0] - c[0]) * r2 / r, c[1] + (p[1] - c[1]) * r2 / r)

    al, bl, ar, br = at(a, rl), at(b, rl), at(a, rr), at(b, rr)
    return [("A", al, bl, c, rl, sw), ("A", bl, br, b, h, 0), ("A", br, ar, c, rr, 1 - sw), ("A", ar, al, a, h, 0)]


def cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


def offset(path, segs, d):
    """The closed contour segs moved d along each segment's left normal, corners joined by miter."""
    n = len(segs)
    off = []
    for s in segs:
        if s[0] == "L":
            nn = unit_normal(tangent(s, False))
            off.append(("L", (s[1][0] + nn[0] * d, s[1][1] + nn[1] * d), (s[2][0] + nn[0] * d, s[2][1] + nn[1] * d)))
        else:
            r2 = s[4] - d if s[5] else s[4] + d
            if r2 < 0:
                die("%s: a stroke is wider than an arc's radius" % path)
            c = s[3]
            f = r2 / s[4]
            off.append(("A", (c[0] + (s[1][0] - c[0]) * f, c[1] + (s[1][1] - c[1]) * f),
                        (c[0] + (s[2][0] - c[0]) * f, c[1] + (s[2][1] - c[1]) * f), c, r2, s[5]))
    joints = []
    for i in range(n):
        a, b = segs[i], segs[(i + 1) % n]
        ta, tb = tangent(a, True), tangent(b, False)
        oa, ob = off[i], off[(i + 1) % n]
        if cross(ta, tb) == 0 and dot(ta, tb) > 0:
            joints.append(oa[2] if oa[0] == "A" else ob[1])
            continue
        if a[0] != "L" or b[0] != "L":
            die("%s: a stroke corner on an arc" % path)
        # oa: oa1 + u ta; ob: ob1 + v tb; meet at u = cross(ob1 - oa1, tb) / cross(ta, tb)
        w = (ob[1][0] - oa[1][0], ob[1][1] - oa[1][1])
        u = cross(w, tb) / cross(ta, tb)
        j = (oa[1][0] + ta[0] * u, oa[1][1] + ta[1] * u)
        v = a[2]
        if 4 * ((j[0] - v[0]) ** 2 + (j[1] - v[1]) ** 2) > 16 * (2 * d) ** 2:
            die("%s: a miter past the limit" % path)
        joints.append(j)
    out = []
    for i in range(n):
        p0, p1 = joints[i - 1], joints[i]
        s = off[i]
        if s[0] == "L":
            if dot((p1[0] - p0[0], p1[1] - p0[1]), tangent(segs[i], False)) <= 0:
                die("%s: a stroke folds over a short segment" % path)
            out.append(("L", p0, p1))
        elif s[4] > 0:
            out.append(("A", p0, p1, s[3], s[4], s[5]))
    return out


def reverse(contour):
    return [("L", s[2], s[1]) if s[0] == "L" else ("A", s[2], s[1], s[3], s[4], 1 - s[5]) for s in reversed(contour)]


def stroke(path, subs, w, cap, join):
    h = w / 2
    out = []
    for segs, closed in subs:
        if not segs:
            continue
        if closed:
            if join != "miter":
                die("%s: a closed stroke wants miter joins" % path)
            out.append(offset(path, segs, h))
            out.append(reverse(offset(path, segs, -h)))
        else:
            if cap != "round" or (len(segs) > 1 and join != "round"):
                die("%s: an open stroke wants round caps, and round joins" % path)
            for s in segs:
                out.append(capsule(s[1], s[2], h) if s[0] == "L" else arc_capsule(path, s, h))
    return out


# ---- coverage ---------------------------------------------------------------------------------------------------

def pang(x, y):
    """A pseudo angle of (x, y) in [0, 4), increasing with the angle from +x toward +y."""
    if y >= 0 and x > 0:
        return Q(y, x + y)
    if x <= 0 and y > 0:
        return 1 + Q(-x, y - x)
    if y <= 0 and x < 0:
        return 2 + Q(-y, -x - y)
    return 3 + Q(x, x - y)


def edges(contours, n, side):
    """The contours' edges on the grid of an n px raster: ("L", x0, y0, x1, y1) and ("A", cx, cy, r, s, y0, y1),
    in their order along the outline; s -1 the arc's left half, 1 its right."""
    g = Q(n * 32 * FINE) / side

    def G(p):
        return (rnd(p[0] * g), rnd(p[1] * g))

    out = []
    for cont in contours:
        for s in cont:
            if s[0] == "L":
                (x0, y0), (x1, y1) = G(s[1]), G(s[2])
                if y0 != y1:
                    out.append(("L", x0, y0, x1, y1))
                continue
            p0, p1, c = G(s[1]), G(s[2]), G(s[3])
            r = rnd(s[4] * g)
            fwd = s[5] == 1
            a, b = (p0, p1) if fwd else (p1, p0)
            a0 = pang(a[0] - c[0], a[1] - c[1])
            a1 = pang(b[0] - c[0], b[1] - c[1])
            if a1 <= a0:
                a1 += 4
            cuts = [a0] + [Q(k) for k in (1, 3, 5, 7) if a0 < k < a1] + [a1]
            pts = [a] + [(c[0], c[1] + r if k % 4 == 1 else c[1] - r) for k in cuts[1:-1]] + [b]
            pieces = []
            for i in range(len(cuts) - 1):
                mid = ((cuts[i] + cuts[i + 1]) / 2) % 4
                sd = -1 if 1 < mid < 3 else 1
                ya, yb = pts[i][1], pts[i + 1][1]
                if not fwd:
                    ya, yb = yb, ya
                if ya != yb:
                    pieces.append(("A", c[0], c[1], r, sd, ya, yb))
            out += pieces if fwd else pieces[::-1]
    return out


def coverage(contours, n, side):
    """Rows of n counts, 0 to 256, of the samples of each pixel inside the contours by nonzero winding."""
    es = edges(contours, n, side)
    rows = [[0] * n for _ in range(n)]
    if not es:
        return rows
    span = []
    for e in es:
        if e[0] == "L":
            lo, hi, d = (e[2], e[4], 1) if e[2] < e[4] else (e[4], e[2], -1)
        else:
            lo, hi, d = (e[5], e[6], 1) if e[5] < e[6] else (e[6], e[5], -1)
        span.append((lo, hi, d, e))
    ylo = min(s[0] for s in span)
    yhi = max(s[1] for s in span)
    j0 = max(0, -(-(ylo - FINE) // (2 * FINE)))
    j1 = min(SS * n, -(-(yhi - FINE) // (2 * FINE)))
    last = SS * n
    for j in range(j0, j1):
        yc = (2 * j + 1) * FINE
        cross_ = []
        for lo, hi, d, e in span:
            if lo <= yc < hi:
                if e[0] == "L":
                    x0, y0, x1, y1 = e[1], e[2], e[3], e[4]
                    x = x0 + (yc - y0) * (x1 - x0) // (y1 - y0)
                else:
                    dy = yc - e[2]
                    x = e[1] + e[4] * math.isqrt(max(0, e[3] * e[3] - dy * dy))
                cross_.append((x, d))
        if not cross_:
            continue
        cross_.sort()
        out = rows[j // SS]
        wind = 0
        start = 0
        for x, d in cross_:
            prev = wind
            wind += d
            if prev == 0 and wind != 0:
                start = x
            elif prev != 0 and wind == 0:
                k0 = max(0, -(-(start - FINE) // (2 * FINE)))
                k1 = min(last, -(-(x - FINE) // (2 * FINE)))
                if k1 <= k0:
                    continue
                p0, p1 = k0 // SS, (k1 - 1) // SS
                if p0 == p1:
                    out[p0] += k1 - k0
                else:
                    out[p0] += SS * (p0 + 1) - k0
                    out[p1] += k1 - SS * p1
                    for p in range(p0 + 1, p1):
                        out[p] += SS
    return rows


# ---- compositing, librsvg's way ---------------------------------------------------------------------------------

def mul8(a, b):
    """cairo and pixman's a * b / 255, rounded."""
    t = a * b + 128
    return (t + (t >> 8)) >> 8


def raster(path, n):
    """The n x n raster of an SVG: rows of (rgb, a), a 0 to 256 the alpha in 256ths, rgb the color unmultiplied."""
    side, layers = read_svg(path)
    pr = [[0] * n for _ in range(n)]
    pg = [[0] * n for _ in range(n)]
    pb = [[0] * n for _ in range(n)]
    pa = [[0] * n for _ in range(n)]
    for L in layers:
        cov = coverage(L.contours, n, side)
        op = rnd(L.opacity * 255)
        cr, cg, cb = L.rgb >> 16, L.rgb >> 8 & 255, L.rgb & 255
        for y in range(n):
            cy = cov[y]
            if not any(cy):
                continue
            R, G_, B, A = pr[y], pg[y], pb[y], pa[y]
            for x in range(n):
                c = cy[x]
                if not c:
                    continue
                al = mul8((c * 255 + 128) >> 8, op)
                if not al:
                    continue
                inv = 255 - al
                R[x] = mul8(cr, al) + mul8(R[x], inv)
                G_[x] = mul8(cg, al) + mul8(G_[x], inv)
                B[x] = mul8(cb, al) + mul8(B[x], inv)
                A[x] = al + mul8(A[x], inv)
    out = []
    for y in range(n):
        row = []
        for x in range(n):
            a8 = pa[y][x]
            if not a8:
                row.append((0, 0))
                continue
            un = [min(255, (v * 255 + a8 // 2) // a8) for v in (pr[y][x], pg[y][x], pb[y][x])]
            row.append(((un[0] << 16) | (un[1] << 8) | un[2], (a8 * 256 + 127) // 255))
        out.append(row)
    return out


# ---- the manifest -----------------------------------------------------------------------------------------------

MODULES = {"app": "icons3", "file": "fileicons"}


def tables(path):
    """SOURCES.md's tables by their section heading: {heading: [row cells]}."""
    out = {}
    head = None
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("## "):
                head = line[3:].strip()
                out[head] = []
            elif line.startswith("|") and head is not None:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", c) for c in cells):
                    continue
                out[head].append(cells)
    for h in out:
        out[h] = out[h][1:]      # the header row
    return out


def manifest():
    """(sums {file: sha256}, {kind: (names, sizes, {(name, size, z): source})})."""
    t = tables(os.path.join(SRC, "SOURCES.md"))
    for h in ("Files", "Manifest", "At"):
        if h not in t:
            die("SOURCES.md has no `## %s` table" % h)
    sums = {}
    for r in t["Files"]:
        if len(r) != 3 or not re.fullmatch(r"[0-9a-f]{64}", r[2].strip("`")):
            die("SOURCES.md Files row %r" % r)
        sums[r[0].strip("`")] = r[2].strip("`")
    at = {}
    for r in t["At"]:
        if len(r) != 4:
            die("SOURCES.md At row %r" % r)
        at[(r[0], int(r[1]), int(r[2]))] = r[3].strip("`")
    kinds = {}
    for r in t["Manifest"]:
        if len(r) != 4 or r[1] not in MODULES:
            die("SOURCES.md Manifest row %r" % r)
        name, kind, drawing, sizes = r[0], r[1], r[2].strip("`"), [int(v) for v in r[3].split()]
        names, allsizes, src = kinds.setdefault(kind, ([], set(), {}))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or any(name in k[0] for k in kinds.values()):
            die("SOURCES.md: icon name %r" % name)
        names.append(name)
        allsizes.update(sizes)
        hand = drawing[:-len(".svg")] + "_16.svg"
        for s in sizes:
            for z in (1, 2):
                src[(name, s, z)] = at.pop((name, s, z), hand if s == 16 and hand in sums else drawing)
    if at:
        die("SOURCES.md: At rows for no manifest size: %r" % sorted(at))
    for k in kinds:
        names, allsizes, src = kinds[k]
        kinds[k] = (names, sorted(allsizes), src)
        for f in src.values():
            if f not in sums:
                die("SOURCES.md: %s is in no Files row" % f)
    return sums, kinds


# ---- the kit tables ---------------------------------------------------------------------------------------------

def encode(names, sizes, src):
    """The tables of one module. Rasters: one a (source, device px), shared by every (icon, size, z) drawn from it.
    pal: index 0 clear, else ((a - 1) << 24) | rgb, a the alpha in 256ths (1 to 256). A raster row is tokens of 16
    bits from its start to the next row's start: t < 0x8000 one pixel of pal[t]; else a run of t - 0x8000 pixels
    of pal[next token]. A row's trailing clear pixels are not written."""
    keys = sorted(set((f, s * z) for (n, s, z), f in src.items()))
    rid = {k: i for i, k in enumerate(keys)}
    slots = []
    for n in names:
        for s in sizes:
            for z in (1, 2):
                f = src.get((n, s, z))
                slots.append(rid[(f, s * z)] if f else -1)
    pal = {(0, 0): 0}
    toks, rowat, rpx, rrow = [], [], [], []
    for f, d in keys:
        rpx.append(d)
        rrow.append(len(rowat))
        for row in raster(os.path.join(SRC, f), d):
            rowat.append(len(toks))
            end = d
            while end > 0 and row[end - 1][1] == 0:
                end -= 1
            x = 0
            while x < end:
                j = x
                while j < end and row[j] == row[x]:
                    j += 1
                c, a = row[x]
                key = (c, a) if a else (0, 0)
                if key not in pal:
                    pal[key] = len(pal)
                if j - x > 1:
                    toks.append(0x8000 + j - x)
                toks.append(pal[key])
                x = j
    rowat.append(len(toks))
    if len(pal) > 0x8000:
        die("a palette of %d colors" % len(pal))
    palv = [0] * len(pal)
    for (c, a), i in pal.items():
        palv[i] = ((a - 1) << 24) | c if i else 0
    return dict(slots=slots, rpx=rpx, rrow=rrow, pal=palv, toks=toks, rowat=rowat, keys=keys)


def pack(vals, bits):
    per = 64 // bits
    out = []
    for i in range(0, len(vals), per):
        w = 0
        for j, v in enumerate(vals[i:i + per]):
            w |= v << (64 - bits * (j + 1))
        out.append(w)
    return out


def arr(typ, name, vals, fmt, per_line, export=False):
    lines = ["%sU%d[%d] %s = [" % ("export " if export else "", typ, len(vals), name)]
    for i in range(0, len(vals), per_line):
        lines.append("    " + ", ".join(fmt % v for v in vals[i:i + per_line]) + ("," if i + per_line < len(vals) else ""))
    lines.append("];")
    return lines


def iarr(name, vals):
    lines = ["I64[%d] %s = [" % (len(vals), name)]
    for i in range(0, len(vals), 16):
        lines.append("    " + ", ".join(str(v) for v in vals[i:i + 16]) + ("," if i + 16 < len(vals) else ""))
    lines.append("];")
    return lines


LIMIT = 64000   # cint 0.2.18 takes an array of up to about 65000 initial values (C9102 past it); 63450 compiles (DN-31)


def emit(kind, names, sizes, src, sums):
    """The text of the kit module of one kind."""
    mod = MODULES[kind]
    t = encode(names, sizes, src)
    toks = pack(t["toks"], 16)
    rows = pack(t["rowat"], 32)
    # DN-46 (d): the tokens in two arrays when one would pass cint's limit (the trash icons took the app icons past
    # it); iconrle.ci reads the second from where the first ends
    toks2 = toks[LIMIT:] or [0]
    toks = toks[:LIMIT]
    for nm, v in (("toks", toks), ("toks2", toks2), ("rows", rows), ("pal", t["pal"]), ("slots", t["slots"])):
        if len(v) > LIMIT:
            die("%s.%s: %d values, past cint's limit" % (mod, nm, len(v)))
    pool, at = [], []
    for n in names:
        at.append(len(pool))
        pool += [ord(c) for c in n]
    light = [names.index(n + "_light") if n + "_light" in names else -1 for n in names]
    nbytes = 8 * (len(toks) + len(toks2) + len(rows)) + 4 * len(t["pal"]) + 8 * (len(t["slots"]) + 2 * len(t["rpx"]))
    what = {"app": "the app icons of draft 3 (DN-5; Finder and the 16 px drawings of DN-8)",
            "file": "the file icons (DN-9; the 16 px text and ci of DN-12)"}[kind]
    L = ["// user/ci/kit/%s.ci: %s," % (mod, what),
         "// written by tools/svgicons.py from tools/icons-v3/ (SOURCES.md); do not edit.",
         "// %d icons at %s px, each at 1x and natively at 2x (FONT-2 A), the shadow baked in (MS-R1)." % (
             len(names), ", ".join(str(s) for s in sizes)),
         "// %d rasters (one a source and device size), %d palette colors, %d tokens: %d bytes of tables." % (
             len(t["rpx"]), len(t["pal"]), len(t["toks"]), nbytes),
         "// Drawn by user/ci/kit/iconrle.ci through MS-1's blend; tools/iconwin.py is the twin.",
         "",
         "import user.ci.kit.iconrle;",
         "",
         "export const I64 N = %d;" % len(names)]
    for k, n in enumerate(names):
        L.append("export const I64 %s = %d;" % (n.upper(), k))
    L += ["", "export const I64 NS = %d;" % len(sizes)]
    L += iarr("sizes", sizes)
    L += ["", "U8[%d] names = [%s];" % (len(pool), ", ".join(str(c) for c in pool)),
          "I64[%d] name_at = [%s];" % (len(names) + 1, ", ".join(str(a) for a in at + [len(pool)]))]
    L += iarr("light_of", light)
    L += ["", "// slot (icon * NS + size index) * 2 + z - 1: the raster, or -1"]
    L += iarr("slots", t["slots"])
    L += ["", "// a raster's side in device px and its first row"]
    L += iarr("rpx", t["rpx"])
    L += iarr("rrow", t["rrow"])
    L += [""] + arr(32, "pal", t["pal"], "0x%08x", 8)
    L += [""] + arr(64, "rows", rows, "0x%016x", 4)
    L += [""] + arr(64, "toks", toks, "0x%016x", 4)
    L += [""] + arr(64, "toks2", toks2, "0x%016x", 4)
    L += ["",
          "// The icon named name (`%s`, ...), or -1." % names[0],
          "export I64 named(in U8[_] name) {",
          "    for k in 0..N {",
          "        I64 a = name_at[k];",
          "        I64 n = name_at[k + 1] - a;",
          "        if (len(name) == n) {",
          "            Bool same = true;",
          "            for i in 0..n {",
          "                if (name[i] != names[a + i]) { same = false; }",
          "            }",
          "            if (same) { return k; }",
          "        }",
          "    }",
          "    return -1;",
          "}",
          "",
          "// The raster of icon k at px px and scale z (1 or 2), or -1 if there is none.",
          "export I64 raster(I64 k, I64 px, I64 z) {",
          "    if (k < 0 || k >= N || z < 1 || z > 2) { return -1; }",
          "    for i in 0..NS {",
          "        if (sizes[i] == px) { return slots[(k * NS + i) * 2 + z - 1]; }",
          "    }",
          "    return -1;",
          "}",
          "",
          "// Whether icon k has a table at px px and scale z.",
          "export Bool has(I64 k, I64 px, I64 z) {",
          "    return raster(k, px, z) >= 0;",
          "}",
          ""]
    if kind == "app":
        L += ["// Icon k at px px and scale z, its top left at device (x0, y0), laid over device row y through MS-1's",
              "// mix_px; on a light ground (luma 128 or more) an icon with a NAME_light twin draws the twin. The side",
              "// is size * z device px. Nothing is drawn where there is no such table (see has).",
              "export void icon_at(inout U32[_] row, I64 y, I64 x0, I64 y0, I64 k, I64 px, I64 z, U32 ground) {",
              "    I64 kk = k;",
              "    if (k >= 0 && k < N && light_of[k] >= 0 && iconrle.light(ground)) { kk = light_of[k]; }",
              "    I64 r = raster(kk, px, z);",
              "    if (r >= 0) { iconrle.lay_row(row, y, x0, y0, rpx[r], rrow[r], rows, toks, toks2, pal); }",
              "}"]
    else:
        L += ["// File icon k at px px and scale z, its top left at device (x0, y0), laid over device row y through",
              "// MS-1's mix_px; the side is size * z device px. Nothing is drawn where there is no such table (see has).",
              "export void icon_at(inout U32[_] row, I64 y, I64 x0, I64 y0, I64 k, I64 px, I64 z) {",
              "    I64 r = raster(k, px, z);",
              "    if (r >= 0) { iconrle.lay_row(row, y, x0, y0, rpx[r], rrow[r], rows, toks, toks2, pal); }",
              "}",
              "",
              "// ASCII lower case of a byte.",
              "I64 fold(U8 c) {",
              "    I64 v = c as I64;",
              "    if (v >= 65 && v <= 90) { return v + 32; }",
              "    return v;",
              "}",
              "",
              "// Whether name[0..n] ends in ext (lower case, with its dot), letters compared without case.",
              "Bool ends(in U8[_] name, I64 n, in U8[_] ext) {",
              "    I64 m = len(ext);",
              "    if (n <= m) { return false; }",
              "    for i in 0..m {",
              "        if (fold(name[n - m + i]) != ext[i] as I64) { return false; }",
              "    }",
              "    return true;",
              "}",
              "",
              "// The file icon of the entry name[0..n] (DN-9): a directory gives DIR; .ci gives CI; .png, .qoi and .ppm",
              "// give IMAGE; .wad gives WAD; anything else gives TEXT. Extensions are matched without case.",
              "export I64 kind(in U8[_] name, I64 n, Bool dir) {",
              "    if (dir) { return DIR; }",
              "    if (ends(name, n, \".ci\")) { return CI; }",
              "    if (ends(name, n, \".png\") || ends(name, n, \".qoi\") || ends(name, n, \".ppm\")) { return IMAGE; }",
              "    if (ends(name, n, \".wad\")) { return WAD; }",
              "    return TEXT;",
              "}"]
    L.append(SPDX)
    return "\n".join(L) + "\n"


def outputs():
    """{path: text} of every module, after the sums are checked; and the list of sum failures."""
    sums, kinds = manifest()
    bad = []
    listed = set(sums)
    for f in sorted(os.listdir(SRC)):
        if f.endswith(".svg") and f not in listed:
            bad.append("%s is not in SOURCES.md" % f)
    for f, h in sorted(sums.items()):
        p = os.path.join(SRC, f)
        if not os.path.exists(p):
            bad.append("%s is missing" % f)
            continue
        with open(p, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != h:
                bad.append("%s is not its sum" % f)
    if bad:
        return {}, bad
    out = {}
    for kind in ("app", "file"):
        if kind in kinds:
            names, sizes, src = kinds[kind]
            out[os.path.join(KIT, MODULES[kind] + ".ci")] = emit(kind, names, sizes, src, sums)
    return out, bad


def main(argv):
    if argv not in ([], ["--check"]):
        die("usage: tools/svgicons.py [--check]")
    out, bad = outputs()
    if argv == ["--check"]:
        for p, text in sorted(out.items()):
            try:
                with open(p) as f:
                    if f.read() != text:
                        bad.append("%s is not what tools/svgicons.py writes" % os.path.relpath(p, os.path.join(HERE, "..")))
            except OSError:
                bad.append("%s is missing" % os.path.relpath(p, os.path.join(HERE, "..")))
        for b in bad:
            print("svgicons.py: " + b)
        n = len(manifest()[0]) if not bad else 0
        print("%s  icons3: the %s sources are their SOURCES.md sums and user/ci/kit/icons3.ci and fileicons.ci are what "
              "tools/svgicons.py draws from them" % ("FAIL" if bad else "PASS", n or "vendored"))
        return 1 if bad else 0
    if bad:
        die("; ".join(bad))
    for p, text in out.items():
        with open(p, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
