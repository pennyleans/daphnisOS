#!/usr/bin/env python3
"""tools/check-basics.py: the oracles of stage BP (docs/specs/2026-11-07-bp-basics.md section 5).

  check-basics.py fixtures DIR      writes the image fixtures of tests/basics/tree/img (PNG of every color type, bit
                                    depth, filter and Adam7; QOI; Netpbm P2, P3, P5, P6; and broken files), the same
                                    bytes on every host: zlib level 9 and fixed patterns
  check-basics.py digest FILE...    for each image, `cview: FILE WxH rgba SHA256` as cview -d prints it, decoded here
                                    with Python's zlib and this file's own PNG, QOI and Netpbm reader
  check-basics.py calc CASES TREE BIN
                                    each case of CASES (`ARGS | STDIN | DIFF`, as tools/check-core.py reads them) run
                                    under BIN prints on descriptors 1 and 2, with the status, what this file's model of
                                    ccalc's arithmetic (Python's integers) prints
  check-basics.py pty BIN FILE KEYS OUT
                                    runs BIN FILE on a pty of 80 x 24, types each line of KEYS (escapes as in Python
                                    bytes, one write a line, the output drained between), writes the bytes the
                                    terminal got to OUT; exit 1 unless the status is 0 and the terminal's mode after
                                    is the mode before

Exit status 0 on success, 1 with the reason on stderr."""
import hashlib
import json
import os
import select
import struct
import sys
import zlib

# ---------------------------------------------------------------- PNG, QOI, Netpbm: writers


def chunk(t, data):
    return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)


CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
ADAM7 = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]


def pattern(x, y, c, depth):
    top = (1 << depth) - 1
    return (x * 37 + y * 101 + c * 59 + x * y * 7) % (top + 1)


def pack_row(samples, depth):
    if depth == 8:
        return bytes(samples)
    if depth == 16:
        return b"".join(struct.pack(">H", s) for s in samples)
    out = bytearray()
    acc = 0
    n = 0
    for s in samples:
        acc = (acc << depth) | s
        n += depth
        if n == 8:
            out.append(acc)
            acc = n = 0
    if n:
        out.append(acc << (8 - n))
    return bytes(out)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filt(f, line, prior, bpp):
    out = bytearray()
    for i, x in enumerate(line):
        a = line[i - bpp] if i >= bpp else 0
        b = prior[i] if prior else 0
        c = prior[i - bpp] if prior and i >= bpp else 0
        pred = [0, a, b, (a + b) // 2, paeth(a, b, c)][f]
        out.append((x - pred) & 255)
    return bytes([f]) + bytes(out)


def png(w, h, ct, depth, interlace=0, npal=0, trns=None):
    ch = CHANNELS[ct]
    bpp = max(1, ch * depth // 8)
    raw = bytearray()
    passes = ADAM7 if interlace else [(0, 0, 1, 1)]
    k = 0
    for sx, sy, dx, dy in passes:
        xs = list(range(sx, w, dx))
        ys = list(range(sy, h, dy))
        if not xs or not ys:
            continue
        prior = None
        for y in ys:
            samples = []
            for x in xs:
                for c in range(ch):
                    if ct == 3:
                        samples.append((x * 3 + y * 5) % npal)
                    else:
                        samples.append(pattern(x, y, c, depth))
            line = pack_row(samples, depth)
            raw += filt(k % 5, line, prior, bpp)
            k += 1
            prior = line
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ct, 0, 0, interlace))
    if ct == 3:
        out += chunk(b"PLTE", bytes((i * 53 + j * 91) % 256 for i in range(npal) for j in range(3)))
    if trns is not None:
        out += chunk(b"tRNS", trns)
    out += chunk(b"tEXt", b"Comment\x00skipped by cview")
    z = zlib.compress(bytes(raw), 9)
    half = len(z) // 2
    out += chunk(b"IDAT", z[:half]) + chunk(b"IDAT", z[half:])   # two IDATs: the stream spans chunks
    return out + chunk(b"IEND", b"")


def qoi_encode(w, h, chs, pix):
    out = bytearray(b"qoif" + struct.pack(">IIBB", w, h, chs, 0))
    index = [(0, 0, 0, 0)] * 64
    prev = (0, 0, 0, 255)
    run = 0
    for i, px in enumerate(pix):
        if px == prev:
            run += 1
            if run == 62 or i == len(pix) - 1:
                out.append(0xC0 | (run - 1))
                run = 0
            continue
        if run:
            out.append(0xC0 | (run - 1))
            run = 0
        hsh = (px[0] * 3 + px[1] * 5 + px[2] * 7 + px[3] * 11) % 64
        if index[hsh] == px:
            out.append(hsh)
        else:
            index[hsh] = px
            if px[3] == prev[3]:
                dr = (px[0] - prev[0] + 128) % 256 - 128
                dg = (px[1] - prev[1] + 128) % 256 - 128
                db = (px[2] - prev[2] + 128) % 256 - 128
                drg, dbg = dr - dg, db - dg
                if -2 <= dr <= 1 and -2 <= dg <= 1 and -2 <= db <= 1:
                    out.append(0x40 | ((dr + 2) << 4) | ((dg + 2) << 2) | (db + 2))
                elif -32 <= dg <= 31 and -8 <= drg <= 7 and -8 <= dbg <= 7:
                    out += bytes([0x80 | (dg + 32), ((drg + 8) << 4) | (dbg + 8)])
                else:
                    out += bytes([0xFE, px[0], px[1], px[2]])
            else:
                out += bytes([0xFF]) + bytes(px)
        prev = px
    return bytes(out + b"\x00" * 7 + b"\x01")


def fixtures(d):
    os.makedirs(d, exist_ok=True)
    files = {}
    for ct, depths in ((0, (1, 2, 4, 8, 16)), (2, (8, 16)), (3, (1, 2, 4, 8)), (4, (8, 16)), (6, (8, 16))):
        for depth in depths:
            npal = min(1 << depth, 200) if ct == 3 else 0
            for il in (0, 1):
                files["png-c%d-d%d-i%d.png" % (ct, depth, il)] = png(13, 7, ct, depth, il, npal)
    files["png-trns-gray.png"] = png(9, 9, 0, 8, 0, 0, struct.pack(">H", pattern(0, 0, 0, 8)))
    files["png-trns-rgb.png"] = png(9, 9, 2, 16, 0, 0, struct.pack(">HHH", *(pattern(0, 0, c, 16) for c in range(3))))
    files["png-trns-pal.png"] = png(9, 9, 3, 4, 1, 16, bytes(range(0, 160, 10)))
    files["png-1x1.png"] = png(1, 1, 6, 8, 1)
    files["png-wide.png"] = png(300, 2, 2, 8)
    good = files["png-c2-d8-i0.png"]
    bad = bytearray(good)
    bad[40] ^= 1
    files["bad-crc.png"] = bytes(bad)
    files["bad-short.png"] = good[: len(good) - 30]
    files["bad-form.png"] = b"GIF89a not an image of cview's\n"
    pix = [((x * 9) % 256, (y * 17) % 256, ((x ^ y) * 5) % 256, 255 if (x + y) % 7 else 128) for y in range(11) for x in range(23)]
    pix[5:40] = [pix[5]] * 35   # a run
    files["qoi-rgba.qoi"] = qoi_encode(23, 11, 4, pix)
    files["qoi-rgb.qoi"] = qoi_encode(23, 11, 3, [(r, g, b, 255) for r, g, b, _ in pix])
    files["pnm-p2.pgm"] = b"P2\n# a comment\n5 3\n15\n" + b"\n".join(b" ".join(b"%d" % ((x + y * 5) % 16) for x in range(5)) for y in range(3)) + b"\n"
    files["pnm-p3.ppm"] = b"P3 4 2 255\n" + b" ".join(b"%d %d %d" % ((x * 60) % 256, (y * 90) % 256, 200) for y in range(2) for x in range(4)) + b"\n"
    files["pnm-p5.pgm"] = b"P5\n6 4\n255\n" + bytes((x * 40 + y * 10) % 256 for y in range(4) for x in range(6))
    files["pnm-p6-16.ppm"] = b"P6\n3 2\n1000\n" + b"".join(struct.pack(">HHH", (x * 300) % 1001, (y * 700) % 1001, 1000) for y in range(2) for x in range(3))
    for name, data in sorted(files.items()):
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    print("check-basics.py: %d fixtures in %s" % (len(files), d))

# ---------------------------------------------------------------- readers


def sample(row, x, c, ch, d):
    if d < 8:
        bit = x * d
        return (row[bit // 8] >> (8 - d - bit % 8)) & ((1 << d) - 1)
    if d == 8:
        return row[x * ch + c]
    i = 2 * (x * ch + c)
    return (row[i] << 8) | row[i + 1]


def eight(v, d):
    if d == 16:
        return v >> 8
    if d == 8:
        return v
    return v * 255 // ((1 << d) - 1)


def read_png(f):
    w, h, d, ct, _, _, il = struct.unpack(">IIBBBBB", f[16:29])
    at = 8
    z = b""
    pal = [(0, 0, 0, 255)] * 256
    trns = None
    while True:
        n, t = struct.unpack(">I4s", f[at:at + 8])
        data = f[at + 8:at + 8 + n]
        if zlib.crc32(t + data) & 0xFFFFFFFF != struct.unpack(">I", f[at + 8 + n:at + 12 + n])[0]:
            raise ValueError("crc")
        if t == b"PLTE":
            pal = [tuple(data[3 * i:3 * i + 3]) + (255,) for i in range(n // 3)] + pal[n // 3:]
        elif t == b"tRNS":
            trns = data
        elif t == b"IDAT":
            z += data
        elif t == b"IEND":
            break
        at += 12 + n
    if ct == 3 and trns is not None:
        pal = [p[:3] + ((trns[i],) if i < len(trns) else (255,)) for i, p in enumerate(pal)]
    raw = zlib.decompress(z)
    ch = CHANNELS[ct]
    bits = ch * d
    bpp = max(1, bits // 8)
    px = bytearray(4 * w * h)
    at = 0
    for sx, sy, dx, dy in (ADAM7 if il else [(0, 0, 1, 1)]):
        xs = list(range(sx, w, dx))
        ys = list(range(sy, h, dy))
        if not xs or not ys:
            continue
        rb = (len(xs) * bits + 7) // 8
        prior = bytes(rb)
        for j, y in enumerate(ys):
            ft = raw[at]
            line = bytearray(raw[at + 1:at + 1 + rb])
            for i in range(rb):
                a = line[i - bpp] if i >= bpp else 0
                b = prior[i] if j else 0
                c = prior[i - bpp] if j and i >= bpp else 0
                line[i] = (line[i] + [0, a, b, (a + b) // 2, paeth(a, b, c)][ft]) & 255
            at += 1 + rb
            prior = bytes(line)
            for i, x in enumerate(xs):
                if ct == 3:
                    rgba = pal[sample(line, i, 0, 1, d)]
                elif ct in (0, 4):
                    v = sample(line, i, 0, ch, d)
                    g = eight(v, d)
                    a = eight(sample(line, i, 1, ch, d), d) if ct == 4 else 255
                    if ct == 0 and trns is not None and v == struct.unpack(">H", trns[:2])[0]:
                        a = 0
                    rgba = (g, g, g, a)
                else:
                    v = [sample(line, i, c, ch, d) for c in range(3)]
                    a = eight(sample(line, i, 3, ch, d), d) if ct == 6 else 255
                    if ct == 2 and trns is not None and tuple(v) == struct.unpack(">HHH", trns[:6]):
                        a = 0
                    rgba = tuple(eight(s, d) for s in v) + (a,)
                o = 4 * (y * w + x)
                px[o:o + 4] = bytes(rgba)
    return w, h, bytes(px)


def read_qoi(f):
    w, h = struct.unpack(">II", f[4:12])
    index = [(0, 0, 0, 0)] * 64
    r, g, b, a = 0, 0, 0, 255
    at = 14
    run = 0
    px = bytearray()
    for _ in range(w * h):
        if run:
            run -= 1
        else:
            op = f[at]
            at += 1
            if op == 0xFE:
                r, g, b = f[at:at + 3]
                at += 3
            elif op == 0xFF:
                r, g, b, a = f[at:at + 4]
                at += 4
            elif op >> 6 == 0:
                r, g, b, a = index[op]
            elif op >> 6 == 1:
                r, g, b = (r + ((op >> 4) & 3) - 2) % 256, (g + ((op >> 2) & 3) - 2) % 256, (b + (op & 3) - 2) % 256
            elif op >> 6 == 2:
                dg = (op & 63) - 32
                nx = f[at]
                at += 1
                r, g, b = (r + dg - 8 + (nx >> 4)) % 256, (g + dg) % 256, (b + dg - 8 + (nx & 15)) % 256
            else:
                run = op & 63
            index[(r * 3 + g * 5 + b * 7 + a * 11) % 64] = (r, g, b, a)
        px += bytes((r, g, b, a))
    return w, h, bytes(px)


def read_pnm(f):
    form = f[1] - 48
    words = []
    at = 2
    while len(words) < 3:
        while f[at:at + 1].isspace():
            at += 1
        if f[at:at + 1] == b"#":
            while f[at:at + 1] != b"\n":
                at += 1
            continue
        s = at
        while f[at:at + 1].isdigit():
            at += 1
        words.append(int(f[s:at]))
    w, h, maxv = words
    chs = 3 if form in (3, 6) else 1
    if form in (2, 3):
        vals = []
        rest = f[at:]
        for line in rest.split(b"\n"):
            vals += [int(t) for t in line.split(b"#")[0].split()]
    else:
        body = f[at + 1:]
        if maxv > 255:
            vals = [struct.unpack(">H", body[2 * i:2 * i + 2])[0] for i in range(w * h * chs)]
        else:
            vals = list(body[:w * h * chs])
    px = bytearray()
    for k in range(w * h):
        v = [(min(s, maxv) * 255 + maxv // 2) // maxv for s in vals[k * chs:(k + 1) * chs]]
        px += bytes((v * 3)[:3] if chs == 1 else v) + b"\xff"
    return w, h, bytes(px)


def digest(paths):
    for p in paths:
        f = open(p, "rb").read()
        if f[:8] == b"\x89PNG\r\n\x1a\n":
            w, h, px = read_png(f)
        elif f[:4] == b"qoif":
            w, h, px = read_qoi(f)
        else:
            w, h, px = read_pnm(f)
        print("cview: %s %dx%d rgba %s" % (p, w, h, hashlib.sha256(px).hexdigest()))

# ---------------------------------------------------------------- ccalc's arithmetic


M = (1 << 63) - 1


class Fail(Exception):
    pass


class Calc:
    def __init__(self):
        self.scale = 9
        self.names = {}
        self.last = (0, 0, False)

    def tok(self, s):
        out = []
        i = 0
        while i < len(s):
            c = s[i]
            if c in " \t":
                i += 1
            elif s.startswith("0x", i) or s.startswith("0X", i):
                j = i + 2
                while j < len(s) and s[j] in "0123456789abcdefABCDEF":
                    j += 1
                if j == i + 2:
                    raise Fail("syntax at column %d" % (i + 3))
                if int(s[i + 2:j], 16) > M:
                    raise Fail("overflow")
                out.append(("num", int(s[i + 2:j], 16), 0, i))
                i = j
            elif c.isdigit() or c == ".":
                j = i
                pt = False
                while j < len(s) and (s[j].isdigit() or (s[j] == "." and not pt)):
                    pt = pt or s[j] == "."
                    j += 1
                txt = s[i:j]
                frac = txt.split(".")[1] if "." in txt else ""
                if len(frac) > 18:
                    raise Fail("limit: SCALE_MAX")
                m = int(txt.replace(".", "") or "0")
                if m > M:
                    raise Fail("overflow")
                out.append(("num", m, len(frac), i))
                i = j
            elif c.isalpha() or c == "_":
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                out.append(("name", s[i:j], 0, i))
                i = j
            elif s.startswith("<<", i) or s.startswith(">>", i):
                out.append(("op", s[i:i + 2], 0, i))
                i += 2
            else:
                out.append(("op", c, 0, i))
                i += 1
        return out

    def run(self, s):
        self.t = self.tok(s)
        self.k = 0
        if not self.t:
            return None
        target = None
        hexout = False
        if self.t[0] == ("name", "hex", 0, self.t[0][3]):
            hexout = True
            self.k = 1
        elif len(self.t) > 1 and self.t[0][0] == "name" and self.t[1][:2] == ("op", "="):
            target = self.t[0][1]
            if target in ("_", "sqrt", "xor", "hex") or len(target) > 16:
                raise Fail("syntax at column %d" % (self.t[0][3] + 1))
            self.k = 2
        v = self.expr(0)
        if self.k != len(self.t):
            raise Fail("syntax at column %d" % (self.t[self.k][3] + 1))
        if target == "scale":
            n = self.integer(v)
            if not 0 <= n <= 18:
                raise Fail("scale is 0 to 18")
            self.scale = n
            return None
        if target is not None:
            if target not in self.names and len(self.names) == 64:
                raise Fail("limit: NAMES_MAX")
            self.names[target] = v
            self.last = v
            return None
        self.last = v
        if hexout:
            n = self.integer(v)
            return ("-" if n < 0 else "") + "0x%x" % abs(n)
        m, s, cut = v
        a = "%0*d" % (s + 1, abs(m))
        txt = a[:len(a) - s] + ("." + a[len(a) - s:] if s else "")
        return ("~" if cut else "") + ("-" if m < 0 else "") + txt

    def peek(self):
        return self.t[self.k] if self.k < len(self.t) else ("end", None, 0, None)

    def col(self):
        p = self.peek()
        return p[3] + 1 if p[3] is not None else self.endcol

    def integer(self, v):
        m, s, _ = v
        while s and m % 10 == 0 and m:
            m //= 10 if m > 0 else 1
            s -= 1
        if s and m == 0:
            s = 0
        if s:
            raise Fail("integer expected")
        return m

    LEVELS = [("|",), ("xor",), ("&",), ("<<", ">>"), ("+", "-"), ("*", "/", "%")]

    def expr(self, lvl):
        if lvl == len(self.LEVELS):
            return self.unary()
        v = self.expr(lvl + 1)
        while True:
            p = self.peek()
            if (p[0] == "op" or (p[0] == "name" and p[1] == "xor")) and p[1] in self.LEVELS[lvl]:
                self.k += 1
                v = self.binary(p[1], v, self.expr(lvl + 1))
            else:
                return v

    def unary(self):
        p = self.peek()
        if p[:2] in (("op", "-"), ("op", "~")):
            self.k += 1
            m, s, c = self.unary()
            if p[1] == "-":
                return (-m, s, c)
            return (~self.integer((m, s, c)), 0, c)
        v = self.atom()
        if self.peek()[:2] == ("op", "^"):
            self.k += 1
            v = self.binary("^", v, self.unary())
        return v

    def atom(self):
        p = self.peek()
        if p[0] == "num":
            self.k += 1
            return (p[1], p[2], False)
        if p[:2] == ("op", "("):
            self.k += 1
            v = self.expr(0)
            if self.peek()[:2] != ("op", ")"):
                raise Fail("syntax at column %d" % self.col())
            self.k += 1
            return v
        if p[:2] == ("name", "sqrt"):
            self.k += 1
            if self.peek()[:2] != ("op", "("):
                raise Fail("syntax at column %d" % self.col())
            return self.root(self.atom())
        if p[:2] == ("name", "_"):
            self.k += 1
            return self.last
        if p[0] == "name":
            self.k += 1
            if p[1] not in self.names:
                raise Fail("unknown name " + p[1])
            return self.names[p[1]]
        raise Fail("syntax at column %d" % self.col())

    @staticmethod
    def fit(m):
        if abs(m) > M:
            raise Fail("overflow")
        return m

    def settle(self, mag, s, neg, cut):
        while s > 0 and (s > 18 or mag > M):
            cut = cut or mag % 10 != 0
            mag //= 10
            s -= 1
        return (-self.fit(mag) if neg else self.fit(mag), s, cut)

    @staticmethod
    def trim(m, s, c):
        while s and m % 10 == 0:
            m = int(m / 10)
            s -= 1
        return (m, s, c)

    def binary(self, op, a, b):
        (am, sa, ca), (bm, sb, cb) = a, b
        c = ca or cb
        if op in "+-":
            s = max(sa, sb)
            x = self.fit(am * 10 ** (s - sa)) if all(abs(am * 10 ** k) <= M for k in range(s - sa + 1)) else self.fit(M + 1)
            y = self.fit(bm * 10 ** (s - sb)) if all(abs(bm * 10 ** k) <= M for k in range(s - sb + 1)) else self.fit(M + 1)
            return (self.fit(x + y if op == "+" else x - y), s, c)
        if op == "*":
            return self.settle(abs(am * bm), sa + sb, (am < 0) != (bm < 0), c)
        if op == "/":
            if bm == 0:
                raise Fail("division by zero")
            st = max(self.scale, sa - sb)
            num = abs(am) * 10 ** (st + sb - sa)
            if num >= 1 << 128:
                raise Fail("overflow")
            q, r = divmod(num, abs(bm))
            q = self.fit(q)
            v = -q if (am < 0) != (bm < 0) else q
            return (v, st, True) if r else self.trim(v, st, c)
        if op == "^":
            n = self.integer(b)
            if not 0 <= n <= 63:
                raise Fail("exponent or shift past 0 to 63")
            v = (1, 0, False)
            for _ in range(n):
                v = self.binary("*", v, (am, sa, False))
            return (v[0], v[1], v[2] or c)
        x, y = self.integer(a), self.integer(b)
        if op == "%":
            if y == 0:
                raise Fail("division by zero")
            return (x % y, 0, c)   # floored, as cint's %
        if op in ("<<", ">>"):
            if not 0 <= y <= 63:
                raise Fail("exponent or shift past 0 to 63")
            if op == ">>":
                return (x >> y, 0, c)
            v = x
            for _ in range(y):
                if abs(v) > M // 2:
                    raise Fail("overflow")
                v *= 2
            return (v, 0, c)
        return ({"&": x & y, "|": x | y, "xor": x ^ y}[op], 0, c)

    def root(self, v):
        m, s, c = v
        if m < 0:
            raise Fail("square root of a negative")
        st = max(self.scale, (s + 1) // 2)
        n = m * 10 ** (2 * st - s)
        if n >= 1 << 128:
            raise Fail("overflow")
        import math
        r = math.isqrt(n)
        r = min(r, M)
        return self.trim(r, st, c) if r * r == n else (r, st, True)


def calc(listing, tree, binary):
    import shlex
    import subprocess
    bad = 0
    for raw in open(listing, encoding="latin-1").read().split("\n"):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        args, stdin, _ = [x.strip() for x in raw.rsplit("|", 2)]
        words = shlex.split(args)
        feed = open(os.path.join(tree, stdin), "rb").read() if stdin != "-" else b""
        r = subprocess.run([binary] + words, input=feed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        model = Calc()
        texts = [" ".join(words)] if words else feed.decode("latin-1").split("\n")
        if not words and texts and texts[-1] == "":
            texts.pop()
        out, err, status = "", "", 0
        for t in texts:
            model.endcol = len(t) + 1
            try:
                v = model.run(t)
                if v is not None:
                    out += v + "\n"
            except Fail as e:
                err += "ccalc: %s\n" % e
                status = 1
        if (r.stdout.decode("latin-1"), r.stderr.decode("latin-1"), r.returncode) != (out, err, status):
            print("check-basics.py: ccalc %r: model %r %r %d, tool %r %r %d" % (args, out, err, status, r.stdout, r.stderr, r.returncode), file=sys.stderr)
            bad += 1
    return 1 if bad else 0

# ---------------------------------------------------------------- the pager on a pty


def pty_run(binary, path, keys, out):
    import pty
    import termios
    import fcntl
    pid, m = pty.fork()
    if pid == 0:
        os.execv(binary, [binary, path])
    fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    got = bytearray()

    def drain(t):
        while True:
            r, _, _ = select.select([m], [], [], t)
            if not r:
                return
            try:
                d = os.read(m, 65536)
            except OSError:
                return
            if not d:
                return
            got.extend(d)
    before = termios.tcgetattr(m)
    drain(0.5)
    for line in open(keys, encoding="latin-1").read().split("\n"):
        if line:
            os.write(m, line.encode("latin-1").decode("unicode_escape").encode("latin-1"))
            drain(0.3)
    _, st = os.waitpid(pid, 0)
    drain(0.1)
    after = termios.tcgetattr(m)
    open(out, "wb").write(bytes(got))
    if st != 0 or before != after:
        print("check-basics.py: pty: status %d, mode %s" % (st, "kept" if before == after else "changed"), file=sys.stderr)
        return 1
    return 0


def main(argv):
    if argv[:1] == ["fixtures"] and len(argv) == 2:
        fixtures(argv[1])
        return 0
    if argv[:1] == ["digest"]:
        digest(argv[1:])
        return 0
    if argv[:1] == ["calc"] and len(argv) == 4:
        return calc(*argv[1:])
    if argv[:1] == ["pty"] and len(argv) == 5:
        return pty_run(*argv[1:])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
