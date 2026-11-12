#!/usr/bin/env python3
"""tools/symbols.py [--check] [--png DIR]: the desk's 16 px symbols (design notes 32 and 33: the right-click strip),
rasterized from the bank's SVG sources in tools/symbols-v1/ and written to user/ci/kit/symbols.ci, the symbol table.
It is its own table: the icon tables (kit/icons3.ci, kit/fileicons.ci, tools/svgicons.py) are not touched, so the
bank can grow here. Standard library only, integer arithmetic only: the same sources give the same table anywhere.

Sources. tools/symbols-v1/SOURCES.md holds each vendored file's sha256 and its studio-assets branch and commit; the
manifest below names the symbols built, in table order. A symbol of the bank is a 16 unit viewBox stroked at 1.5 with
round caps and round joins, fill none, in currentColor, with at most two accent groups (`<g style="color: #...">`,
two only of different classes: DN-46 (e)'s new folder, its folder yellow and its cross blue); a _mono file has none.

Geometry read: svg, g, rect (rx equal ry), circle, path (M L H V A Z, absolute; arcs of rx equal ry, the large arc
too, DN-47's power), a circle filled in currentColor with no stroke (info's dot: the points within its radius), the attributes the
bank writes; anything else stops the tool. An arc's center is exact where it is rational,
else its offset from the chord's middle is the integer square root at 2^-64. With round caps and round joins of one width a
stroke is exactly the set of points within half the width of its path, so a sample is covered when its distance to
some segment (a line or a circular arc) is at most 3/4: an exact test on rationals, no offset curves.

Raster. A pixel holds 16 x 16 samples at their centers; its coverage is the count of covered samples, 0 to 256, the
256ths kit/blend.ci mixes by. Three layers a symbol, the ink (currentColor), the first accent and the second (in
the file's order; most symbols have one or none), each the union of its shapes, drawn in that order. Each symbol is drawn at 16 device px (1x) and at 32 (2x), from the drawing
itself at each size (nothing is resampled). The colors are not stored: the drawing passes the ink (INK) and the
accent comes from the accent's class and the theme (DN-34: dark ground #4a88c7 and #fabd2f, light ground #1a4b8c
and #c98f00).

Storage. A layer is row-major 16-bit tokens: a coverage 1 to 256, or 0x8000 + n for n clear pixels; a row's tokens
never cross into the next row, and a row with nothing is one token. Two tokens a U32 word, low first. Each (symbol,
scale, layer) has its rows' first token in ROW0.

--check writes nothing and fails when the table differs from what the sources make, or a source differs from its sum
in SOURCES.md. --png DIR writes each symbol at 1x and 2x on both grounds as PNG (proofs; zlib from the standard
library)."""
import hashlib
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from fractions import Fraction as Q

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "symbols-v1")
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "symbols.ci")
SVG_NS = "{http://www.w3.org/2000/svg}"
SS = 16              # samples a pixel, across and down
SPDX = "// SPDX-License-Identifier: Apache-2.0"

# (constant, source file stem): the table's order. DN-33's strip: edit is Rename; folder and file stand in for New
# Folder and New File until the design sends its own.
# DN-34 adds key, display, window, speaker and info (the Grants pill and the Settings sidebar), and every symbol in
# mono (the bank's _mono files: no accent), as NAME_MONO. More symbols go at the end of each half.
COLOR = [("CUT", "cut"), ("COPY", "copy"), ("EDIT", "edit"), ("SHARE", "share"), ("TRASH", "trash"),
         ("PASTE", "paste"), ("FOLDER", "folder"), ("FILE", "file"), ("KEY", "key"), ("DISPLAY", "display"),
         ("WINDOW", "window"), ("SPEAKER", "speaker"), ("INFO", "info"),
         # DN-47: the power menu's rows; DN-46 (e): the menus' New Folder and New File (drafts, the cross nearer the middle)
         ("LOCK", "lock"), ("POWER", "power"), ("REFRESH", "refresh"), ("NEW_FOLDER", "new_folder"),
         ("NEW_FILE", "new_file"),
         # RS-SET0 (DN-58): the Settings sidebar's new pages; a pin's remove, a checkbox's mark, a menu button's chevron
         ("KEYBOARD", "keyboard"), ("NETWORK", "network"), ("CLOCK", "clock"), ("DISK", "disk"), ("USERS", "users"),
         ("CLOSE", "close"), ("CHECK", "check"), ("DOWN", "down"),
         # frame 48 (DN-66): the button before a narrow Settings page's title
         ("SIDEBAR", "sidebar"),
         # DN-55: Index's toolbar and sidebar (frames 3 and 4, from frame 18's approved set); DISK and SIDEBAR are above
         ("HOME", "home"), ("FILE_TEXT", "file_text"), ("DOWNLOAD", "download"), ("IMAGE", "image"),
         ("GRID", "grid"), ("LIST", "list"), ("SORT", "sort"), ("SEARCH", "search"),
         ("BACK", "back"), ("FORWARD", "forward"), ("UP", "up"),
         # DN-52 (d): the power menu's Sleep row (its Switch User row takes USERS above)
         ("MOON", "moon")]
MANIFEST = ([(c, "ui_daphnis_sym_" + f) for c, f in COLOR] +
            [(c + "_MONO", "ui_daphnis_sym_" + f + "_mono") for c, f in COLOR])
SCALES = (1, 2)
# accent classes: (name, the color the bank writes, dark ground, light ground)
ACCENTS = [("BLUE", 0x4a88c7, 0x4a88c7, 0x1a4b8c), ("YELLOW", 0xfabd2f, 0xfabd2f, 0xc98f00)]


def die(msg):
    raise SystemExit("symbols.py: " + msg)


NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def num(s):
    s = s.strip()
    if not NUM.fullmatch(s):
        die("number %r" % s)
    if "e" in s or "E" in s:
        m, e = re.split("[eE]", s)
        return Q(m) * Q(10) ** int(e)
    return Q(s)


def isqrt_q(v):
    """The exact square root of a nonnegative rational, or None."""
    if v < 0:
        return None
    import math
    a, b = v.numerator, v.denominator
    ra, rb = math.isqrt(a), math.isqrt(b)
    return Q(ra, rb) if ra * ra == a and rb * rb == b else None


def root_q(v):
    import math
    return Q(math.isqrt(v.numerator * 4 ** 64 // v.denominator), 2 ** 64)


# ---- reading ----------------------------------------------------------------------------------------------------

def arc_center(p0, p1, r, fa, fs, where):
    """SVG F.6.5 with rx = ry = r and no rotation: the center, exactly (the bank's arcs have rational centers)."""
    mx, my = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    d2 = mx * mx + my * my
    if d2 == 0:
        die("%s: an empty arc" % where)
    if d2 > r * r:
        # F.6.6: the radius scaled up until the arc just spans its ends, a half circle on the chord's middle, exactly;
        # the scaled radius is the chord's half, 2^-64 below its root when that is not a square (the moon's inner arc)
        rr = isqrt_q(d2)
        if rr is None:
            rr = root_q(d2)
        return ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), rr
    k = isqrt_q((r * r - d2) / d2)
    if k is None:
        k = root_q((r * r - d2) / d2)    # not a square: 2^-64 below the root, the same on any machine
    if fa == fs:
        k = -k
    cx = k * my + (p0[0] + p1[0]) / 2
    cy = -k * mx + (p0[1] + p1[1]) / 2
    return (cx, cy), r


def parse_path(d, where):
    toks = re.findall(r"[MLHVAZmlhvaz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    segs, i, cur, start, cmd = [], 0, None, None, None

    def take():
        nonlocal i
        if i >= len(toks) or toks[i].isalpha():
            die("%s: path data %r" % (where, d))
        i += 1
        return num(toks[i - 1])
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "mlhvaz":
                die("%s: a relative path command" % where)
            if cmd == "Z":
                if cur != start:
                    segs.append(("L", cur, start))
                cur = start
                continue
        if cmd == "M":
            cur = start = (take(), take())
            cmd = "L"
        elif cmd == "L":
            p = (take(), take())
            segs.append(("L", cur, p))
            cur = p
        elif cmd == "H":
            p = (take(), cur[1])
            segs.append(("L", cur, p))
            cur = p
        elif cmd == "V":
            p = (cur[0], take())
            segs.append(("L", cur, p))
            cur = p
        elif cmd == "A":
            rx, ry, rot = take(), take(), take()
            fa, fs = int(take()), int(take())
            p = (take(), take())
            if rx != ry or rot != 0:
                die("%s: an elliptical or turned arc" % where)
            c, r = arc_center(cur, p, rx, fa, fs, where)
            segs.append(("A", cur, p, c, r, fs, fa))
            cur = p
        else:
            die("%s: path command %r" % (where, cmd))
    return segs


def rect_segs(x, y, w, h, r):
    if r == 0:
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [("L", pts[k], pts[(k + 1) % 4]) for k in range(4)]
    a, b, c, d = x + r, x + w - r, y + r, y + h - r
    return [("L", (a, y), (b, y)), ("A", (b, y), (x + w, c), (b, c), r, 1),
            ("L", (x + w, c), (x + w, d)), ("A", (x + w, d), (b, y + h), (b, d), r, 1),
            ("L", (b, y + h), (a, y + h)), ("A", (a, y + h), (x, d), (a, d), r, 1),
            ("L", (x, d), (x, c)), ("A", (x, c), (a, y), (a, c), r, 1)]


def color_of(style):
    m = re.fullmatch(r"\s*color:\s*#([0-9a-fA-F]{6})\s*;?\s*", style or "")
    if not m:
        die("style %r" % style)
    return int(m.group(1), 16)


def read_svg(path):
    """[(layer, segments)]: layer 0 the ink, else 1 + the accent class."""
    root = ET.parse(path).getroot()
    where = os.path.basename(path)
    if root.tag != SVG_NS + "svg" or root.get("viewBox") != "0 0 16 16":
        die("%s: not a 16 unit symbol" % where)
    want = {"fill": "none", "stroke": "currentColor", "stroke-width": "1.5", "stroke-linecap": "round",
            "stroke-linejoin": "round"}
    for k, v in want.items():
        if root.get(k) != v:
            die("%s: %s is %r, not %r" % (where, k, root.get(k), v))
    out = []

    def walk(el, layer):
        for ch in el:
            tag = ch.tag.replace(SVG_NS, "")
            if tag == "metadata":
                continue
            for a in ch.attrib:
                if a not in ("x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "d", "style", "stroke", "fill"):
                    die("%s: attribute %r" % (where, a))
            filled = ch.get("fill") == "currentColor" and ch.get("stroke") == "none"
            if ch.get("stroke", "currentColor") != "currentColor" and not filled:
                die("%s: a stroke not in currentColor" % where)
            if ch.get("fill", "none") != "none" and not (filled and tag == "circle"):
                die("%s: a fill other than a filled circle" % where)
            if tag == "g":
                if layer != 0:
                    die("%s: a group in a group" % where)
                c = color_of(ch.get("style"))
                cls = [k for k, a in enumerate(ACCENTS) if a[1] == c]
                if not cls:
                    die("%s: accent #%06x is not a class" % (where, c))
                walk(ch, 1 + cls[0])
            elif tag == "path":
                out.append((layer, parse_path(ch.get("d"), where)))
            elif tag == "rect":
                rx, ry = ch.get("rx", ch.get("ry", "0")), ch.get("ry", ch.get("rx", "0"))
                if num(rx) != num(ry):
                    die("%s: rx and ry differ" % where)
                out.append((layer, rect_segs(num(ch.get("x", "0")), num(ch.get("y", "0")), num(ch.get("width")),
                                             num(ch.get("height")), num(rx))))
            elif tag == "circle" and filled:
                out.append((layer, [("D", (num(ch.get("cx")), num(ch.get("cy"))), num(ch.get("r")))]))
            elif tag == "circle":
                cx, cy, r = num(ch.get("cx")), num(ch.get("cy")), num(ch.get("r"))
                c = (cx, cy)
                pts = [(cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)]
                out.append((layer, [("A", pts[k], pts[(k + 1) % 4], c, r, 1) for k in range(4)]))
            else:
                die("%s: element %r" % (where, tag))
    walk(root, 0)
    return out


# ---- coverage ---------------------------------------------------------------------------------------------------

H = Q(3, 4)          # half the stroke
H2 = H * H


def near_line(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    wx, wy = px - a[0], py - a[1]
    L = dx * dx + dy * dy
    t = wx * dx + wy * dy
    if L == 0 or t <= 0:
        return wx * wx + wy * wy <= H2
    if t >= L:
        ex, ey = px - b[0], py - b[1]
        return ex * ex + ey * ey <= H2
    c = wx * dy - wy * dx            # distance^2 = c^2 / L
    return c * c <= H2 * L


def near_arc(px, py, s):
    _, p0, p1, c, r, fs = s[:6]
    fa = s[6] if len(s) > 6 else 0          # DN-47's power: a large arc, more than half a turn
    vx, vy = px - c[0], py - c[1]
    v0 = (p0[0] - c[0], p0[1] - c[1])
    v1 = (p1[0] - c[0], p1[1] - c[1])
    a = v0[0] * vy - v0[1] * vx
    b = vx * v1[1] - vy * v1[0]
    inside = (a >= 0 and b >= 0) if fs else (a <= 0 and b <= 0)
    if fa:                                  # a large arc: all but the small sector the other way round
        inside = not ((a < 0 and b < 0) if fs else (a > 0 and b > 0))
    if inside:
        d2 = vx * vx + vy * vy
        lo = r - H
        return d2 <= (r + H) ** 2 and (lo <= 0 or d2 >= lo * lo)
    for p in (p0, p1):
        ex, ey = px - p[0], py - p[1]
        if ex * ex + ey * ey <= H2:
            return True
    return False


def in_disc(px, py, s):
    """A filled circle: the sample within its radius."""
    return (px - s[1][0]) ** 2 + (py - s[1][1]) ** 2 <= s[2] * s[2]


def bbox(segs):
    xs, ys = [], []
    for s in segs:
        if s[0] == "D":
            xs += [s[1][0] - s[2], s[1][0] + s[2]]
            ys += [s[1][1] - s[2], s[1][1] + s[2]]
        elif s[0] == "L":
            xs += [s[1][0], s[2][0]]
            ys += [s[1][1], s[2][1]]
        else:
            xs += [s[3][0] - s[4], s[3][0] + s[4]]
            ys += [s[3][1] - s[4], s[3][1] + s[4]]
    return min(xs) - H, min(ys) - H, max(xs) + H, max(ys) + H


def raster(shapes, z, layers):
    """{layer: [rows of coverage 0..256]} at 16 z device px."""
    n = 16 * z
    out = {L: [[0] * n for _ in range(n)] for L in range(layers)}
    for L in range(layers):
        segs = [(s, bbox([s])) for lay, ss in shapes if lay == L for s in ss]
        for py in range(n):
            for sy in range(SS):
                fy = Q(2 * (py * SS + sy) + 1, 2 * SS * z)       # the sample's center in units
                live = [(s, b) for s, b in segs if b[1] <= fy <= b[3]]
                if not live:
                    continue
                for px in range(n):
                    for sx in range(SS):
                        fx = Q(2 * (px * SS + sx) + 1, 2 * SS * z)
                        for s, b in live:
                            if b[0] <= fx <= b[2] and (near_line(fx, fy, s[1], s[2]) if s[0] == "L"
                                                       else in_disc(fx, fy, s) if s[0] == "D"
                                                       else near_arc(fx, fy, s)):
                                out[L][py][px] += 1
                                break
    return out


# ---- table ------------------------------------------------------------------------------------------------------

def sources():
    """{file: sha256} from SOURCES.md, and its checked header."""
    sums = {}
    with open(os.path.join(SRC, "SOURCES.md")) as f:
        for line in f:
            m = re.match(r"\|\s*`([^`]+\.svg)`\s*\|\s*([0-9a-f]{64})\s*\|", line)
            if m:
                sums[m.group(1)] = m.group(2)
    return sums


def build():
    sums = sources()
    listed = sorted(f for f in os.listdir(SRC) if f.endswith(".svg"))
    for f in listed:
        if f not in sums:
            die("%s is not in SOURCES.md" % f)
    syms = []
    for const, stem in MANIFEST:
        p = os.path.join(SRC, stem + ".svg")
        data = open(p, "rb").read()
        if hashlib.sha256(data).hexdigest() != sums.get(stem + ".svg"):
            die("%s differs from its SOURCES.md sum" % stem)
        shapes = read_svg(p)
        acc = []
        for lay, _ in shapes:
            if lay > 0 and lay not in acc:
                acc.append(lay)        # the accents in the file's order
        if len(acc) > 2:
            die("%s: more than two accent classes" % stem)
        cls = (acc[0] - 1 if acc else -1, acc[1] - 1 if len(acc) > 1 else -1)
        norm = [(0 if lay == 0 else 1 + acc.index(lay), ss) for lay, ss in shapes]
        syms.append((const, stem, cls, {z: raster(norm, z, 3) for z in SCALES}))
    return syms


def tokens_of(rows):
    toks, row0 = [], []
    for r in rows:
        row0.append(len(toks))
        x = 0
        while x < len(r):
            if r[x] == 0:
                e = x
                while e < len(r) and r[e] == 0:
                    e += 1
                toks.append(0x8000 + (e - x))
                x = e
            else:
                toks.append(r[x])
                x += 1
    return toks, row0


def emit(syms):
    toks, row0, firsts = [], [], []
    for const, stem, cls, ras in syms:
        for z in SCALES:
            for L in (0, 1, 2):
                t, r0 = tokens_of(ras[z][L])
                firsts.append(len(row0))
                row0 += [len(toks) + k for k in r0]
                toks += t
    if len(toks) % 2:
        toks.append(0x8000)
    words = [toks[k] | (toks[k + 1] << 16) for k in range(0, len(toks), 2)]
    L = ["// user/ci/kit/symbols.ci: the desk's 16 px symbols (design notes 32 and 33), the symbol table: coverage",
         "// masks at 1x (16 px) and 2x (32 px), an ink layer and two accent layers each; written by tools/symbols.py",
         "// from tools/symbols-v1/ (studio-assets symbols-v1); do not edit. Its own table: the icon tables are",
         "// not touched. %d symbols, %d tokens in %d words, %d row starts." % (len(syms), len(toks), len(words),
                                                                             len(row0)),
         "import user.ci.kit.blend;", ""]
    for k, (const, stem, cls, _) in enumerate(syms):
        L.append("export const I64 %s = %d;   // %s" % (const, k, stem))
    L.append("export const I64 N = %d;" % len(syms))
    for k, a in enumerate(ACCENTS):
        L.append("export const I64 %s = %d;   // accent #%06x dark, #%06x light" % (a[0], k, a[2], a[3]))
    L.append("")
    L.append("U32[%d] tok = [" % len(words))
    for k in range(0, len(words), 9):
        L.append("    " + " ".join("0x%08x," % w for w in words[k:k + 9]))
    L[-1] = L[-1].rstrip(",") + "];"
    L.append("U32[%d] row0 = [" % len(row0))
    for k in range(0, len(row0), 14):
        L.append("    " + " ".join("%d," % w for w in row0[k:k + 14]))
    L[-1] = L[-1].rstrip(",") + "];"
    L.append("I64[%d] first = [%s];" % (len(firsts), ", ".join(str(f) for f in firsts)))
    L.append("I64[%d] cls = [%s];" % (len(syms), ", ".join(str(s[2][0]) for s in syms)))
    L.append("I64[%d] cls2 = [%s];" % (len(syms), ", ".join(str(s[2][1]) for s in syms)))
    L.append("U32[%d] accents = [%s];" % (2 * len(ACCENTS), ", ".join("0x%08x" % c for a in ACCENTS
                                                                       for c in (a[2], a[3]))))
    L += ["",
          "// Symbol k's accent class (BLUE, YELLOW), or -1 when it has none.",
          "export I64 accent_class(I64 k) { return cls[k]; }",
          "",
          "// Accent class c's color on theme th (0 dark ground, 1 light ground).",
          "export U32 accent(I64 c, I64 th) { return accents[2 * c + th]; }",
          "",
          "I64 token(I64 i) {",
          "    U32 w = tok[i / 2];",
          "    if (i % 2 == 1) { return ((w >> 16) & 0xFFFF) as I64; }",
          "    return (w & 0xFFFF) as I64;",
          "}",
          "",
          "// Layer L (0 ink, 1 and 2 the accents) of symbol k at scale z (1 or 2): its row r drawn on row from x0,",
          "// each pixel moved toward c by its coverage times a (256ths: 256 full, the strip's 35 percent is 90).",
          "void layer_row(inout U32[_] row, I64 r, I64 x0, I64 k, I64 z, I64 L, U32 c, I64 a) {",
          "    I64 f = first[(k * 2 + (z - 1)) * 3 + L];",
          "    I64 n = 16 * z;",
          "    I64 i = row0[f + r] as I64;",
          "    I64 x = 0;",
          "    while (x < n) {",
          "        I64 t = token(i);",
          "        i = i + 1;",
          "        if (t >= 0x8000) {",
          "            x = x + t - 0x8000;",
          "        } else {",
          "            I64 px = x0 + x;",
          "            if (px >= 0 && px < len(row)) { row[px] = blend.mix_px(row[px], c, (t * a + 128) >> 8); }",
          "            x = x + 1;",
          "        }",
          "    }",
          "}",
          "",
          "// Row y of symbol k at scale z, its 16 z px square's top left at (x0, y0): the ink layer in ink, then the",
          "// accent layers in their classes' colors on theme th, all at opacity a (256ths).",
          "export void row_at(inout U32[_] row, I64 y, I64 x0, I64 y0, I64 k, I64 z, U32 ink, I64 th, I64 a) {",
          "    if (k < 0 || k >= N || (z != 1 && z != 2)) { return; }",
          "    I64 r = y - y0;",
          "    if (r < 0 || r >= 16 * z) { return; }",
          "    layer_row(row, r, x0, k, z, 0, ink, a);",
          "    if (cls[k] >= 0) { layer_row(row, r, x0, k, z, 1, accent(cls[k], th), a); }",
          "    if (cls2[k] >= 0) { layer_row(row, r, x0, k, z, 2, accent(cls2[k], th), a); }",
          "}",
          "",
          SPDX, ""]
    return "\n".join(L)


# ---- proofs -----------------------------------------------------------------------------------------------------

def png(path, w, h, px):
    raw = b"".join(b"\0" + b"".join(struct.pack(">BBB", (v >> 16) & 255, (v >> 8) & 255, v & 255)
                                    for v in px[y * w:(y + 1) * w]) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def mix(p, c, a):
    out = 0
    for sh in (16, 8, 0):
        pp, cc = (p >> sh) & 255, (c >> sh) & 255
        out |= (pp - ((pp - cc) * a >> 8)) << sh
    return out


def proofs(syms, d):
    os.makedirs(d, exist_ok=True)
    grounds = [(0, 0x282a2c, 0xf3efe6), (1, 0xe8eaee, 0x141413)]   # SURF2 and INK by theme
    for th, ground, ink in grounds:
        for z in SCALES:
            n, pad = 16 * z, 8 * z
            W = pad + len(syms) * (n + pad)
            Hh = 2 * pad + n
            px = [ground] * (W * Hh)
            for k, (_, _, cls, ras) in enumerate(syms):
                for r in range(n):
                    for x in range(n):
                        i = (pad + r) * W + pad + k * (n + pad) + x
                        px[i] = mix(px[i], ink, ras[z][0][r][x])
                        for L in (1, 2):
                            if cls[L - 1] >= 0:
                                px[i] = mix(px[i], ACCENTS[cls[L - 1]][2 + th], ras[z][L][r][x])
            png(os.path.join(d, "symbols-%s-%dx.png" % (("dark", "light")[th], z)), W, Hh, px)


def main(argv):
    syms = build()
    text = emit(syms)
    if "--png" in argv:
        proofs(syms, argv[argv.index("--png") + 1])
    if "--check" in argv:
        have = open(OUT).read() if os.path.exists(OUT) else ""
        if have != text:
            die("user/ci/kit/symbols.ci differs from what the sources make")
        print("symbols.py: user/ci/kit/symbols.ci is the table of %d symbols" % len(syms))
        return 0
    with open(OUT, "w") as f:
        f.write(text)
    print("symbols.py: wrote user/ci/kit/symbols.ci, %d symbols" % len(syms))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
