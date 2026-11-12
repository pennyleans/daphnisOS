"""tools/ttf.py: a TrueType outline reader and coverage rasterizer in plain Python (stage K, FONT-1, F3).

Reads the tables a static glyf font needs (head, maxp, hhea, hmtx, cmap formats 4 and 12, loca, glyf, OS/2), turns
a glyph into contours (composites resolved, implied on-curve points made explicit) and fills it at a scale given as a
rational p / q pixels per font unit (across and down apart) with nonzero winding, S x S samples a pixel. Every step is integer arithmetic:
the same font and arguments give the same coverage on any machine. No hinting and no kerning (FONT-1, section 3e).
Anything else (CFF outlines, other cmap formats, a variable font's glyph data) stops with an error."""
import struct


class Font:
    def __init__(self, data):
        self.data = data
        version, n = struct.unpack(">IH", data[:6])
        if version != 0x00010000:
            raise SystemExit("ttf.py: not a TrueType glyf font (sfnt version %08x)" % version)
        self.tables = {}
        for i in range(n):
            tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
            self.tables[tag.decode("latin-1")] = (off, length)
        if "fvar" in self.tables or "CFF " in self.tables:
            raise SystemExit("ttf.py: a variable or CFF font; static glyf fonts only")
        for need in ("head", "maxp", "hhea", "hmtx", "cmap", "loca", "glyf"):
            if need not in self.tables:
                raise SystemExit("ttf.py: no %s table" % need)
        head = self.table("head")
        self.upem = struct.unpack(">H", head[18:20])[0]
        self.long_loca = struct.unpack(">h", head[50:52])[0] == 1
        self.glyphs = struct.unpack(">H", self.table("maxp")[4:6])[0]
        hhea = self.table("hhea")
        self.ascender, self.descender, self.line_gap = struct.unpack(">hhh", hhea[4:10])
        nh = struct.unpack(">H", hhea[34:36])[0]
        hmtx = self.table("hmtx")
        self.adv, self.lsb = [], []
        for g in range(self.glyphs):
            if g < nh:
                a, l = struct.unpack(">Hh", hmtx[4 * g: 4 * g + 4])
            else:
                a = self.adv[nh - 1]
                l = struct.unpack(">h", hmtx[4 * nh + 2 * (g - nh): 4 * nh + 2 * (g - nh) + 2])[0]
            self.adv.append(a)
            self.lsb.append(l)
        loca = self.table("loca")
        if self.long_loca:
            self.loca = list(struct.unpack(">%dI" % (self.glyphs + 1), loca[: 4 * (self.glyphs + 1)]))
        else:
            self.loca = [2 * v for v in struct.unpack(">%dH" % (self.glyphs + 1), loca[: 2 * (self.glyphs + 1)])]
        self.cmap = self.read_cmap()
        self.os2 = {}
        if "OS/2" in self.tables:
            o = self.table("OS/2")
            self.os2["weight"] = struct.unpack(">H", o[4:6])[0]
            self.os2["typo"] = struct.unpack(">hhh", o[68:74])
            self.os2["win"] = struct.unpack(">HH", o[74:78])
            if struct.unpack(">H", o[0:2])[0] >= 2:
                self.os2["xheight"], self.os2["capheight"] = struct.unpack(">hh", o[86:90])

    def table(self, tag):
        off, length = self.tables[tag]
        return self.data[off: off + length]

    def read_cmap(self):
        cmap = self.table("cmap")
        n = struct.unpack(">H", cmap[2:4])[0]
        best = None
        for i in range(n):
            pid, eid, off = struct.unpack(">HHI", cmap[4 + 8 * i: 12 + 8 * i])
            fmt = struct.unpack(">H", cmap[off: off + 2])[0]
            rank = {(3, 10, 12): 0, (0, 4, 12): 1, (3, 1, 4): 2, (0, 3, 4): 3}.get((pid, eid, fmt))
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, off, fmt)
        if best is None:
            raise SystemExit("ttf.py: no Unicode cmap in format 4 or 12")
        _, off, fmt = best
        out = {}
        if fmt == 4:
            segs = struct.unpack(">H", cmap[off + 6: off + 8])[0] // 2
            base = off + 14
            ends = struct.unpack(">%dH" % segs, cmap[base: base + 2 * segs])
            starts = struct.unpack(">%dH" % segs, cmap[base + 2 * segs + 2: base + 4 * segs + 2])
            deltas = struct.unpack(">%dh" % segs, cmap[base + 4 * segs + 2: base + 6 * segs + 2])
            ro_at = base + 6 * segs + 2
            ros = struct.unpack(">%dH" % segs, cmap[ro_at: ro_at + 2 * segs])
            for s in range(segs):
                for c in range(starts[s], ends[s] + 1):
                    if c == 0xFFFF:
                        continue
                    if ros[s] == 0:
                        g = (c + deltas[s]) & 0xFFFF
                    else:
                        at = ro_at + 2 * s + ros[s] + 2 * (c - starts[s])
                        g = struct.unpack(">H", cmap[at: at + 2])[0]
                        if g:
                            g = (g + deltas[s]) & 0xFFFF
                    if g:
                        out[c] = g
        else:
            groups = struct.unpack(">I", cmap[off + 12: off + 16])[0]
            for k in range(groups):
                s, e, g0 = struct.unpack(">III", cmap[off + 16 + 12 * k: off + 28 + 12 * k])
                for c in range(s, e + 1):
                    out[c] = g0 + c - s
        return out

    def glyph(self, code):
        if code not in self.cmap:
            raise SystemExit("ttf.py: U+%04X is not in the font" % code)
        return self.cmap[code]

    def contours(self, g, depth=0):
        """The contours of glyph g in font units, y up: lists of (x, y, on), x and y rational as (num, den) pairs
        reduced to integers with a common denominator 16384 (F2Dot14 transforms stay exact)."""
        if depth > 8:
            raise SystemExit("ttf.py: composite nesting too deep at glyph %d" % g)
        start, end = self.loca[g], self.loca[g + 1]
        if start == end:
            return []
        off = self.tables["glyf"][0] + start
        d = self.data
        nc = struct.unpack(">h", d[off: off + 2])[0]
        if nc >= 0:
            return self.simple(off, nc)
        out = []
        p = off + 10
        while True:
            flags, sub = struct.unpack(">HH", d[p: p + 4])
            p += 4
            if flags & 1:
                a, b = struct.unpack(">hh", d[p: p + 4])
                p += 4
            else:
                a, b = struct.unpack(">bb", d[p: p + 2])
                p += 2
            if not flags & 2:
                raise SystemExit("ttf.py: composite glyph %d places by points, not offsets" % g)
            xx, xy, yx, yy = 16384, 0, 0, 16384
            if flags & 8:
                xx = yy = struct.unpack(">h", d[p: p + 2])[0]
                p += 2
            elif flags & 0x40:
                xx, yy = struct.unpack(">hh", d[p: p + 4])
                p += 4
            elif flags & 0x80:
                xx, xy, yx, yy = struct.unpack(">hhhh", d[p: p + 8])
                p += 8
            for c in self.contours(sub, depth + 1):
                out.append([((x * xx + y * yx) // 16384 + a * 16384, (x * xy + y * yy) // 16384 + b * 16384, on)
                            for x, y, on in c])
            if not flags & 0x20:
                break
        return out

    def simple(self, off, nc):
        d = self.data
        ends = struct.unpack(">%dH" % nc, d[off + 10: off + 10 + 2 * nc])
        npts = ends[-1] + 1 if nc else 0
        p = off + 10 + 2 * nc
        ilen = struct.unpack(">H", d[p: p + 2])[0]
        p += 2 + ilen
        flags = []
        while len(flags) < npts:
            f = d[p]
            p += 1
            flags.append(f)
            if f & 8:
                r = d[p]
                p += 1
                flags.extend([f] * r)
        flags = flags[:npts]
        coords = []
        for short, same in ((2, 16), (4, 32)):
            v, vals = 0, []
            for f in flags:
                if f & short:
                    dv = d[p]
                    p += 1
                    v += dv if f & same else -dv
                elif not f & same:
                    v += struct.unpack(">h", d[p: p + 2])[0]
                    p += 2
                vals.append(v)
            coords.append(vals)
        out, s = [], 0
        for e in ends:
            out.append([(coords[0][i] * 16384, coords[1][i] * 16384, bool(flags[i] & 1)) for i in range(s, e + 1)])
            s = e + 1
        return out


def flatten(contour, steps):
    """A closed polygon of the contour's on-curve points and its quadratic curves cut in `steps` pieces each."""
    n = len(contour)
    if n == 0:
        return []
    pts = list(contour)
    # Make implied on-curve points explicit: the midpoint of two off-curve points.
    full = []
    for i in range(n):
        x, y, on = pts[i]
        nx, ny, non = pts[(i + 1) % n]
        full.append((x, y, on))
        if not on and not non:
            full.append(((x + nx) // 2, (y + ny) // 2, True))
    k = next(i for i, q in enumerate(full) if q[2])
    full = full[k:] + full[:k]
    poly = []
    i = 0
    m = len(full)
    while i < m:
        x0, y0, _ = full[i]
        poly.append((x0, y0))
        cx, cy, con = full[(i + 1) % m]
        if con:
            i += 1
            continue
        x2, y2, _ = full[(i + 2) % m]
        for t in range(1, steps):
            u = steps - t
            poly.append(((x0 * u * u + 2 * cx * t * u + x2 * t * t) // (steps * steps),
                         (y0 * u * u + 2 * cy * t * u + y2 * t * t) // (steps * steps)))
        i += 2
    return poly


FINE = 4096  # sub-sample grid: an outline point lands on 1 / (s * FINE) of a pixel, rounded down


def coverage(font, code, sx, sy=None, dx=(0, 1), dy=(0, 1), s=16, steps=8):
    """Glyph `code` filled at sx = (p, q) pixels per font unit across and sy down (sy defaults to sx), the outline
    moved dx and dy pixels (rationals (num, den)) right and down: (x0, y0, w, h, rows), (x0, y0) the box's top left
    from the pen on the baseline, y down, and rows of coverage, the count of the s * s samples of each pixel inside
    the outline by nonzero winding. Integer arithmetic throughout."""
    sy = sy or sx
    g = s * FINE
    polys = [flatten(c, steps) for c in font.contours(font.glyph(code))]
    polys = [pl for pl in polys if len(pl) > 2]
    if not polys:
        return (0, 0, 0, 0, [])
    # x in font units carries ttf.py's 16384 (exact composite transforms).
    def X(x):
        return (x * sx[0] * g * dx[1] + dx[0] * g * sx[1] * 16384) // (sx[1] * 16384 * dx[1])
    def Y(y):
        return (-y * sy[0] * g * dy[1] + dy[0] * g * sy[1] * 16384) // (sy[1] * 16384 * dy[1])
    edges, xs, ys = [], [], []
    for pl in polys:
        mp = [(X(x), Y(y)) for x, y in pl]
        for i in range(len(mp)):
            (x0, y0), (x1, y1) = mp[i], mp[(i + 1) % len(mp)]
            xs.append(x0)
            ys.append(y0)
            if y0 != y1:
                edges.append((x0, y0, x1, y1) if y0 < y1 else (x1, y1, x0, y0, ))
                edges[-1] = edges[-1] + (1 if y0 < y1 else -1,)
    px0, px1 = min(xs) // g, -(-max(xs) // g)
    py0, py1 = min(ys) // g, -(-max(ys) // g)
    w, h = px1 - px0, py1 - py0
    acc = [[0] * w for _ in range(h)]
    half = FINE // 2
    for row in range(py0 * s, py1 * s):
        yc = row * FINE + half
        cross = []
        for x0, y0, x1, y1, d in edges:
            if y0 <= yc < y1:
                cross.append((x0 + (yc - y0) * (x1 - x0) // (y1 - y0), d))
        if not cross:
            continue
        cross.sort()
        wind = 0
        out = acc[row // s - py0]
        start = 0
        for x, d in cross:
            prev = wind
            wind += d
            if prev == 0 and wind != 0:
                start = x
            elif prev != 0 and wind == 0:
                # sample columns c whose center c * FINE + half lies in [start, x)
                c0 = -(-(start - half) // FINE)
                c1 = -(-(x - half) // FINE)
                for c in range(c0, c1):
                    out[c // s - px0] += 1
    return (px0, py0, w, h, acc)
