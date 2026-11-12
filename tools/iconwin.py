"""tools/iconwin.py: the Python twin of the kit's icons of DN-5, DN-8, DN-9 and DN-12: user/ci/kit/icons3.ci (app
icons), fileicons.ci (file icons) and iconrle.ci (their drawing), with MS-1's blend (kit/blend.ci). It reads the
tables tools/svgicons.py writes (svgicons.py --check holds them to the SVG sources), so it draws what cint draws,
pixel for pixel; tools/check-hdesk.py and the other twins may import it.

`python3 tools/iconwin.py --proof OUTPUT [DIR]` checks a run of tests/ff/icons3_proof.ci: it draws the same sheets and
sums, compares them and, given DIR, writes the kit's sheets as PNGs (sheet-dark-1x.png and so on)."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "user", "ci", "kit")


def _arrays(name):
    with open(os.path.join(KIT, name + ".ci")) as f:
        text = f.read()
    out = {}
    for m in re.finditer(r"^(?:export )?const I64 (\w+) = (-?\d+);", text, re.M):
        out[m.group(1)] = int(m.group(2))
    for m in re.finditer(r"^(?:export )?(?:U8|U32|U64|I64)\[(\d+)\] (\w+) = \[(.*?)\];", text, re.M | re.S):
        vals = [int(v, 0) for v in m.group(3).replace("\n", " ").split(",") if v.strip()]
        if len(vals) != int(m.group(1)):
            raise SystemExit("iconwin.py: %s.%s holds %d, not %s" % (name, m.group(2), len(vals), m.group(1)))
        out[m.group(2)] = vals
    if "toks2" in out:                   # DN-46 (d): the second half of the tokens, after the first
        out["toks"] = out["toks"] + out["toks2"]
    return out


_CACHE = {}


def table(name):
    if name not in _CACHE:
        _CACHE[name] = _arrays(name)
    return _CACHE[name]


def mix_px(p, c, a):
    """MS-1 (kit/blend.ci mix_px): pixel p toward color c by a / 256, a clamped to 0..256, channel by channel."""
    a = max(0, min(256, a))
    out = 0
    for sh in (16, 8, 0):
        v, w = p >> sh & 255, c >> sh & 255
        out |= (v - ((v - w) * a >> 8)) << sh
    return out


def light(ground):
    """kit/iconrle.ci light: luma 0.299 R + 0.587 G + 0.114 B of 128 or more."""
    g = ground & 0xFFFFFF
    return 299 * (g >> 16 & 255) + 587 * (g >> 8 & 255) + 114 * (g & 255) >= 128000


def lay_row(row, y, x0, y0, d, r0, t):
    """kit/iconrle.ci lay_row: device row y of the d x d raster whose first row is r0, over row from (x0, y0)."""
    if y < y0 or y >= y0 + d:
        return
    rows, toks, pal = t["rows"], t["toks"], t["pal"]

    def u32(i):
        return rows[i >> 1] >> (32 - 32 * (i & 1)) & 0xFFFFFFFF

    def tok(i):
        return toks[i >> 2] >> (48 - 16 * (i & 3)) & 0xFFFF

    n = len(row)
    i, i1 = u32(r0 + y - y0), u32(r0 + y - y0 + 1)
    x = x0
    while i < i1 and x < n:
        v = tok(i)
        k = 1
        if v >= 0x8000:
            k = v - 0x8000
            i += 1
            v = tok(i)
        i += 1
        if v:
            e = pal[v]
            a, c = (e >> 24) + 1, e & 0xFFFFFF
            for p in range(max(x, 0), min(x + k, n)):
                row[p] = mix_px(row[p], c, a)
        x += k


def named(mod, name):
    """icons3.named / fileicons.named: the icon named name, or -1."""
    t = table(mod)
    pool = t["names"]
    at = t["name_at"]
    for k in range(t["N"]):
        if bytes(pool[at[k]:at[k + 1]]) == name.encode():
            return k
    return -1


def raster(mod, k, px, z):
    """icons3.raster / fileicons.raster: the raster of icon k at px and scale z, or -1."""
    t = table(mod)
    if k < 0 or k >= t["N"] or z < 1 or z > 2:
        return -1
    for i, s in enumerate(t["sizes"]):
        if s == px:
            return t["slots"][(k * t["NS"] + i) * 2 + z - 1]
    return -1


def has(mod, k, px, z):
    return raster(mod, k, px, z) >= 0


def icon_at(row, y, x0, y0, k, px, z, ground):
    """kit/icons3.ci icon_at: app icon k at px and scale z from device (x0, y0) over device row y; on a light ground
    an icon with a NAME_light twin draws the twin."""
    t = table("icons3")
    kk = k
    if 0 <= k < t["N"] and t["light_of"][k] >= 0 and light(ground):
        kk = t["light_of"][k]
    r = raster("icons3", kk, px, z)
    if r >= 0:
        lay_row(row, y, x0, y0, t["rpx"][r], t["rrow"][r], t)


def file_at(row, y, x0, y0, k, px, z):
    """kit/fileicons.ci icon_at: file icon k at px and scale z from device (x0, y0) over device row y."""
    t = table("fileicons")
    r = raster("fileicons", k, px, z)
    if r >= 0:
        lay_row(row, y, x0, y0, t["rpx"][r], t["rrow"][r], t)


def kind(name, is_dir):
    """kit/fileicons.ci kind: the file icon of an entry name (bytes)."""
    t = table("fileicons")
    if is_dir:
        return t["DIR"]
    low = bytes(c + 32 if 65 <= c <= 90 else c for c in name)

    def ends(ext):
        return len(low) > len(ext) and low.endswith(ext)

    if ends(b".ci"):
        return t["CI"]
    if ends(b".png") or ends(b".qoi") or ends(b".ppm"):
        return t["IMAGE"]
    if ends(b".wad"):
        return t["WAD"]
    return t["TEXT"]


# --- the proof: tests/ff/icons3_proof.ci ----------------------------------------------------------------------------

DARK, LIGHT = 0x141413, 0xECEEF2
PAD, GAP, ROW = 16, 16, 96
COLS = [80, 72, 64, 56, 32, 16]


def sheet(z, g):
    """The proof sheet at scale z on ground g, as tests/ff/icons3_proof.ci sheet draws it: (w, h, rows)."""
    na, nf = table("icons3")["N"], table("fileicons")["N"]
    n = na + nf
    w = z * (2 * PAD + 6 * GAP + sum(COLS))
    h = z * (2 * PAD + n * ROW)
    out = []
    for y in range(h):
        row = [g] * w
        r = (y // z - PAD) // ROW
        if y >= z * PAD and r < n:
            foot = z * (PAD + (r + 1) * ROW)
            x = z * PAD
            for s in COLS:
                y0 = foot - z * s
                if r < na:
                    icon_at(row, y, x, y0, r, s, z, g)
                else:
                    file_at(row, y, x, y0, r - na, s, z)
                x += z * (s + GAP)
        out.append(row)
    return w, h, out


def sums(f, k, s, z, g):
    """tests/ff/icons3_proof.ci sums: the two hashes, cut by the left and the right edge."""
    d = s * z
    out = []
    for at in (0, 1):
        x0 = -(d // 2) - 3 if at == 0 else 200 - d // 2 + 5
        y0 = 7
        h = 0
        for y in range(y0 - 1, y0 + d + 1):
            row = [g] * 200
            if f == 0:
                icon_at(row, y, x0, y0, k, s, z, g)
            else:
                file_at(row, y, x0, y0, k, s, z)
            for c in row:
                h = (h * 1000003 + c) % 1000000007
        out.append(h)
    return out


def read_proof(path):
    frames, got = {}, {}
    name, rows = None, None
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "frame":
                name, rows = p[1], []
                frames[name] = (int(p[2]), int(p[3]), rows)
            elif p[0] == "r":
                row = []
                for i in range(1, len(p), 2):
                    row += [int(p[i], 16)] * int(p[i + 1])
                rows.append(row)
            elif p[0] == "sum":
                got[tuple(int(v) for v in p[1:7])] = int(p[7])
    return frames, got


def check_proof(path, outdir=None):
    frames, got = read_proof(path)
    bad = 0
    want_frames = 0
    for z in (1, 2):
        for gi, g in enumerate((DARK, LIGHT)):
            name = "sheet-%s-%dx" % ("dark" if gi == 0 else "light", z)
            want_frames += 1
            w, h, rows = sheet(z, g)
            if name not in frames:
                print("iconwin.py: %s: no frame %s" % (path, name))
                bad += 1
                continue
            fw, fh, frows = frames[name]
            if (fw, fh) != (w, h) or frows != rows:
                diff = [y for y in range(min(h, len(frows))) if frows[y] != rows[y]]
                print("iconwin.py: %s differs from the twin (%d rows, first %s)" % (name, len(diff), diff[:1]))
                bad += 1
            if outdir:
                sys.path.insert(0, HERE)
                import png
                png.write(os.path.join(outdir, name + ".png"), fw, fh, frows)
    nsum = 0
    for gi, g in enumerate((DARK, LIGHT)):
        for z in (1, 2):
            for f, mod in ((0, "icons3"), (1, "fileicons")):
                for k in range(table(mod)["N"]):
                    for s in COLS:
                        if f == 1 and not has(mod, k, s, z):
                            continue
                        for at, v in enumerate(sums(f, k, s, z, g)):
                            nsum += 1
                            key = (f, k, s, z, gi, at)
                            if got.get(key) != v:
                                print("iconwin.py: sum %s: kit %s, twin %s" % (key, got.get(key), v))
                                bad += 1
    if len(got) != nsum:
        print("iconwin.py: %d sums from the kit, %d from the twin" % (len(got), nsum))
        bad += 1
    print("%s  icons3: tests/ff/icons3_proof.ci's %d sheets and %d sums are tools/iconwin.py's twin, pixel for pixel"
          % ("FAIL" if bad else "PASS", want_frames, nsum))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) in (3, 4) and sys.argv[1] == "--proof":
        sys.exit(check_proof(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None))
    raise SystemExit("usage: tools/iconwin.py --proof OUTPUT [DIR]")
