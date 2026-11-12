#!/usr/bin/env python3
"""tools/glyphs.py [--check]: the kit's coverage glyphs (stage K, FONT-1, F3; docs/specs/2026-11-07-k-kit2.md
section 3e) from the bundled TTFs (tools/fonts/inter/, tools/fonts/jetbrains-mono/; sums in tools/fonts/SOURCES.md),
one cint module a face, size, weight and scale under user/ci/kit/, so a program carries only the tables it draws.
With --check, exits 1 if a module is not what this file writes, or a font's sum is not the one SOURCES.md records.

Every pixel is the count of its 16 x 16 samples inside the outline (tools/ttf.py, nonzero winding, integer
arithmetic), stored as coverage 0 to 15 (count * 15 / 256, rounded half up): 4 bits a pixel. No hinting, no kerning.

Two kinds of module:

- cell (JetBrains Mono in the terminal): every glyph fills the W x H cell (8 x 16 at 1x, 16 x 32 at 2x). The advance
  (600 units) maps to W; the vertical scale puts the x-height (550 units) on exactly 7 px a scale step, the baseline
  on row 12 (24 at 2x); ink past the cell is cut. Box drawing (U+2500 to U+259F) maps the font's line box, descender
  to ascender, onto the cell's full height, so blocks fill it exactly; U+2500 to U+257F but the arcs and diagonals
  (U+256D to U+2573) are moved so the light stroke sits on a pixel row and column and are cut at half coverage, so
  their lines are whole pixels and meet the next cell's. A code point the module lacks draws as U+FFFD.
- prop (Inter in chrome, JetBrains Mono for paths in chrome): each glyph is its ink box, w x h at (x0, y0) from the
  pen on the baseline, y down, and an advance in whole pixels: round(advance * size / upem), plus the tracking of the
  size's row (0.08 em for the section labels) added before the rounding. The vertical scale puts the x-height on a
  whole pixel (round(x-height * size / upem)), within 4% of the true scale. ASCENT and DESCENT are the line box in
  whole pixels. Each face and size moves its outlines right by the sixteenths of a pixel that put the most stem
  pixels of H I l n m u E F L T h b d p q at full coverage (shift(); the same for every glyph, so spacing holds).
  A code point the module lacks draws as '?'.

Module layout: codes[N] sorted code points; for cell, cov holds W * H * 4 / 64 words a glyph, row 0 first, column 0
in a word's top nibble; for prop, box[g] = offset << 32 | w << 24 | h << 16 | (x0 + 128) << 8 | (y0 + 128), with
offset the glyph's first word in cov, rows packed in order, w * h nibbles from the top nibble; adv[g] the advance."""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ttf  # noqa: E402

FONTS = os.path.join(HERE, "fonts")
KIT = os.path.join(HERE, "..", "user", "ci", "kit")
S = 16      # samples a pixel side
LEVELS = 15

# The glyph sets the orders name (board 20261110T024708Z F5, 20261110T000138Z M3): ASCII, Latin-1, the quotes,
# dashes, the ellipsis (DN-49: a clipped pin name) and euro; the terminal adds box drawing, blocks and U+FFFD.
TEXT = list(range(32, 127)) + list(range(0xA0, 0x100)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x20AC]
TERM = TEXT + list(range(0x2500, 0x25A0)) + [0xFFFD]

INTER = {400: "inter/Inter-Regular.ttf", 500: "inter/Inter-Medium.ttf", 600: "inter/Inter-SemiBold.ttf"}
MONO = {400: "jetbrains-mono/JetBrainsMono-Regular.ttf", 600: "jetbrains-mono/JetBrainsMono-SemiBold.ttf"}

# (module, kind, font, size at 1x, tracking in thousandths of an em, use). Each is written at 1x and 2x (suffix 1, 2).
# RS-SET0: a face that draws only a clock carries only the clock's glyphs (and '?', every module's stand-in).
CLOCK = sorted(set(ord(c) for c in " 0123456789:?AMP"))
MANIFEST = [
    ("jbm_r", "cell", MONO[400], 8, 0, "the terminal, 400"),
    ("jbm_b", "cell", MONO[600], 8, 0, "the terminal, SGR bold, 600"),
    ("jbm12_r", "prop", MONO[400], 12, 0, "paths and sizes in chrome, 12 px 400"),
    ("inter13_r", "prop", INTER[400], 13, 0, "chrome body and labels, 13 px 400"),
    ("inter13_m", "prop", INTER[500], 13, 0, "chrome names (Super plane 'Sans medium'), 13 px 500"),
    ("inter11_s", "prop", INTER[600], 11, 80, "section labels, uppercase, 11 px 600, tracking 0.08 em"),
    ("inter16_r", "prop", INTER[400], 16, 0, "search field and empty-state titles, 16 px 400 (the approved sheet: search input 16 px regular)"),
    ("inter20_s", "prop", INTER[600], 20, 0, "preview titles, 20 px 600 (the approved sheet: type specimen 20 px semibold)"),
    ("inter13_s", "prop", INTER[600], 13, 0, "the window bar's name and selected names, 13 px 600 (DN-23)"),
    ("inter12_r", "prop", INTER[400], 12, 0, "the tray's tooltip, 12 px 400 (DN-20, design note 20)"),
    ("jbm13_s", "prop", MONO[600], 13, 0, "the elevation prompt's command, mono 13 px 600 (design note 24, FV-1)"),
    ("jbm11_r", "prop", MONO[400], 11, 0, "the right-click menu's shortcuts, mono 11 px 400 (design note 32)"),
    ("inter16_s", "prop", INTER[600], 16, 0, "the About sheet's app name, 16 px 600 (design note 43)"),
    ("jbm40_s", "prop", MONO[600], 40, -10, "the Date and Time page's clock (frame 36) and the account screens' (frame 12), mono 40 px 600, tracking -0.01 em, digits",
     CLOCK),
    ("inter11_r", "prop", INTER[400], 11, 0, "a slider's end words (frame 37) and pinned names of 10 or 11 characters (DN-52 (e)), 11 px 400"),
    ("inter10_r", "prop", INTER[400], 10, 0, "pinned names of 12 characters or more, 10 px 400 (DN-52 (e))"),
    ("inter12_m", "prop", INTER[500], 12, 0, "a small button's name, 12 px 500 (frame 38's Empty Trash)"),
]

# The apps' own faces (stage RS: Calc and Monitor, frames 39, 42 and 45), kept out of faces.ci so no chrome program
# carries their tables: kit/appfaces.ci names them by role and kit/apptext.ci draws them. The figure faces hold only
# the code points their figures use (FIGURES, KEYS); any other draws as '?'.
FIGURES = sorted(set(ord(c) for c in " %+-./0123456789:?~BGKMTabcdefiksx"))
ASCII = list(range(32, 127))
KEYS = sorted(set(ord(c) for c in "()+.0123456789=?C") | {0x00D7, 0x00F7, 0x2212})
APP_MANIFEST = [
    ("jbm28_s", "prop", MONO[600], 28, 0, "Calc's result, mono 28 px 600 (frame 39)", FIGURES),
    ("jbm32_s", "prop", MONO[600], 32, 0, "Monitor's figure, mono 32 px 600 (frames 42 and 45)", FIGURES),
    ("inter17_m", "prop", INTER[500], 17, 0, "Calc's keys, 17 px 500 (frame 39)", KEYS),
    ("jbm13_r", "prop", MONO[400], 13, 0, "Monitor's facts, mono 13 px 400 (frames 42 and 45)", TEXT),
    ("inter12_s", "prop", INTER[600], 12, 0, "Monitor's End Process button, 12 px 600 (frame 42)", ASCII),
]


def sums():
    """{path under tools/fonts: sha256} from SOURCES.md's table."""
    out = {}
    with open(os.path.join(FONTS, "SOURCES.md")) as f:
        for line in f:
            cells = [c.strip().strip("`") for c in line.split("|")]
            if len(cells) > 3 and cells[1].endswith(".ttf"):
                out[cells[1]] = cells[3]
    return out


def load(rel, want):
    with open(os.path.join(FONTS, rel), "rb") as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != want.get(rel):
        raise SystemExit("glyphs.py: %s is not the file SOURCES.md records" % rel)
    return ttf.Font(data)


def q(count):
    return (count * LEVELS + S * S // 2) // (S * S)


def cell_glyph(font, code, z):
    """W x H rows of coverage for code in the terminal cell at scale z."""
    w, h = 8 * z, 16 * z
    adv = font.adv[font.glyph(0x30)]
    sx = (w, adv)
    lo, hi = font.descender, font.ascender
    snap = 0x2500 <= code <= 0x257F and not 0x256D <= code <= 0x2573
    if 0x2500 <= code <= 0x259F:
        sy = (h, hi - lo)
        dy = (hi * h, hi - lo)                      # font y = ascender lands on row 0
        dx = (0, 1)
        if code <= 0x257F:
            # The light stroke's center (y 370, the middle of U+2500's 320 to 420) onto a pixel center; the
            # vertical stroke's center (x = advance / 2, a pixel edge for even w) half a pixel left.
            num, den = (hi - 370) * h, hi - lo
            fl = num // den
            dy = (hi * h * 2 + (2 * fl + 1) * den - 2 * num, 2 * den)
            dx = (-1, 2)
    else:
        sy = (7 * z, font.os2["xheight"])
        dy = (12 * z, 1)
        dx = (-z, 4)                                # a quarter pixel left a scale step: the most whole-pixel stems
    x0, y0, gw, gh, rows = ttf.coverage(font, code, sx, sy, dx, dy, s=S)
    out = [[0] * w for _ in range(h)]
    for j in range(gh):
        for i in range(gw):
            x, y = x0 + i, y0 + j
            if 0 <= x < w and 0 <= y < h:
                c = rows[j][i]
                out[y][x] = (LEVELS if 2 * c >= S * S else 0) if snap else q(c)
    return out


STEMS = [ord(c) for c in "HIlnmuEFLThbdpq"]   # letters whose vertical stems the shift is chosen on


def shift(font, size):
    """The face's stem shift at `size` px, in sixteenths of a pixel to the right, 0 to 15: the one that puts the
    most stem pixels at full coverage, the least shift on a tie. Chosen by measurement, so it moves with the font."""
    best, at = None, 0
    for k in range(16):
        full = 0
        for c in STEMS:
            x0, y0, w, h, rows = raster(font, c, size, k)
            full += sum(1 for r in rows for v in r if q(v) == LEVELS)
        if best is None or full > best:
            best, at = full, k
    return at


def raster(font, code, size, k):
    up = font.upem
    xh = font.os2["xheight"]
    sy = ((xh * size * 2 + up) // (2 * up), xh)
    return ttf.coverage(font, code, (size, up), sy, (k, 16), (0, 1), s=S)


SHIFTS = {}


def prop_glyph(font, code, size, track):
    """(x0, y0, w, h, rows, advance) for code at `size` px, rows of coverage trimmed to the ink."""
    up = font.upem
    key = (id(font), size)
    if key not in SHIFTS:
        SHIFTS[key] = shift(font, size)
    x0, y0, w, h, rows = raster(font, code, size, SHIFTS[key])
    rows = [[q(c) for c in r] for r in rows]
    # trim clear rows and columns
    while rows and not any(rows[0]):
        rows.pop(0)
        y0 += 1
    while rows and not any(rows[-1]):
        rows.pop()
    if rows:
        while not any(r[0] for r in rows):
            rows = [r[1:] for r in rows]
            x0 += 1
        while not any(r[-1] for r in rows):
            rows = [r[:-1] for r in rows]
    else:
        x0 = y0 = 0
    h = len(rows)
    w = len(rows[0]) if rows else 0
    a = font.adv[font.glyph(code)] * 1000 + track * up
    adv = (2 * a * size + 1000 * up) // (2000 * up)
    return x0, y0, w, h, rows, adv


def words(nibbles):
    out = []
    for k in range(0, len(nibbles), 16):
        chunk = nibbles[k:k + 16] + [0] * (16 - len(nibbles[k:k + 16]))
        v = 0
        for n in chunk:
            v = (v << 4) | n
        out.append(v)
    return out


def arr(kind, name, vals, fmt, per):
    lines = ["%s[%d] %s = [" % (kind, len(vals), name)]
    for i in range(0, len(vals), per):
        lines.append("    " + ", ".join(fmt % v for v in vals[i:i + per]) + ",")
    return lines + ["];", ""]


LOOKUP = """// The glyph of code point cp, or the stand-in's.
export I64 index(I64 cp) {
    I64 lo = 0;
    I64 hi = N;
    while (lo < hi) {
        I64 mid = (lo + hi) / 2;
        if ((codes[mid] as I64) < cp) { lo = mid + 1; } else { hi = mid; }
    }
    if (lo < N && (codes[lo] as I64) == cp) { return lo; }
    return MISSING;
}
"""


def cell_module(name, font, rel, z, use):
    w, h = 8 * z, 16 * z
    per = w * h * 4 // 64
    cov = []
    for c in TERM:
        nib = [v for r in cell_glyph(font, c, z) for v in r]
        cov += words(nib)
    n = len(TERM)
    head = ["// user/ci/kit/%s.ci: JetBrains Mono in the %d x %d terminal cell (FONT-1; %s), coverage 0 to 15 a pixel;" % (name, w, h, use),
            "// written by tools/glyphs.py from tools/fonts/%s; do not edit. OFL-1.1: tools/fonts/jetbrains-mono/OFL.txt." % rel,
            "",
            "export const I64 W = %d;" % w, "export const I64 H = %d;" % h, "export const I64 N = %d;" % n,
            "export const I64 MISSING = %d;   // U+FFFD" % TERM.index(0xFFFD), ""]
    body = arr("U32", "codes", TERM, "0x%04x", 12) + arr("U64", "cov", cov, "0x%016x", 4)
    tail = [LOOKUP,
            "// Coverage 0 to 15 of pixel (x, y) of glyph g, 0 <= x < W, 0 <= y < H.",
            "export I64 at(I64 g, I64 x, I64 y) {",
            "    I64 bit = (y * W + x) * 4;",
            "    U64 word = cov[g * %d + bit / 64];" % per,
            "    return ((word >> ((60 - bit % 64) as U64)) & 15) as I64;",
            "}"]
    return "\n".join(head + body + tail) + "\n// SPDX-License-Identifier: OFL-1.1\n", len(cov)   # the fonts' data, their license


def prop_module(name, font, rel, size, track, z, use, family, lic, wanted=TEXT):
    sz = size * z
    codes = [c for c in wanted if c in font.cmap]
    box, adv, cov = [], [], []
    for c in codes:
        x0, y0, w, h, rows, a = prop_glyph(font, c, sz, track)
        if not (-128 <= x0 < 128 and -128 <= y0 < 128 and w < 256 and h < 256 and a < 256):
            raise SystemExit("glyphs.py: U+%04X of %s does not fit the box word" % (c, name))
        box.append(len(cov) << 32 | w << 24 | h << 16 | (x0 + 128) << 8 | (y0 + 128))
        adv.append(a)
        cov += words([v for r in rows for v in r])
    up = font.upem
    asc = (font.ascender * sz + up - 1) // up
    desc = (-font.descender * sz + up - 1) // up
    n = len(codes)
    head = ["// user/ci/kit/%s.ci: %s %d px at %dx (FONT-1; %s), coverage 0 to 15 a pixel;" % (name, family, sz, z, use),
            "// written by tools/glyphs.py from tools/fonts/%s; do not edit. OFL-1.1: tools/fonts/%s." % (rel, lic),
            "",
            "export const I64 SIZE = %d;" % sz, "export const I64 ASCENT = %d;" % asc, "export const I64 DESCENT = %d;" % desc,
            "export const I64 N = %d;" % n, "export const I64 MISSING = %d;   // '?'" % codes.index(0x3F), ""]
    body = (arr("U32", "codes", codes, "0x%04x", 12) + arr("U64", "box", box, "0x%016x", 4)
            + arr("U8", "adv", adv, "%d", 24) + arr("U64", "cov", cov, "0x%016x", 4))
    tail = [LOOKUP,
            "// Glyph g's advance in whole pixels.",
            "export I64 advance(I64 g) { return adv[g] as I64; }", "",
            "// Glyph g's ink box: left and top from the pen on the baseline (y down), width and height.",
            "export I64 left(I64 g) { return ((box[g] >> 8) & 255) as I64 - 128; }",
            "export I64 top(I64 g) { return (box[g] & 255) as I64 - 128; }",
            "export I64 width(I64 g) { return ((box[g] >> 24) & 255) as I64; }",
            "export I64 height(I64 g) { return ((box[g] >> 16) & 255) as I64; }", "",
            "// Coverage 0 to 15 of pixel (x, y) of glyph g's box, 0 <= x < width(g), 0 <= y < height(g).",
            "export I64 at(I64 g, I64 x, I64 y) {",
            "    I64 bit = (y * width(g) + x) * 4;",
            "    U64 word = cov[(box[g] >> 32) as I64 + bit / 64];",
            "    return ((word >> ((60 - bit % 64) as U64)) & 15) as I64;",
            "}"]
    return "\n".join(head + body + tail) + "\n// SPDX-License-Identifier: OFL-1.1\n", len(cov)   # the fonts' data, their license


# The chrome faces by role, in this order: kit/faces.ci's face numbers (F4).
ROLES = [("PATH", "jbm12_r"), ("BODY", "inter13_r"), ("NAME", "inter13_m"), ("LABEL", "inter11_s"),
         ("SEARCH", "inter16_r"), ("TITLE", "inter20_s"), ("NAME_BOLD", "inter13_s"), ("SMALL", "inter12_r"),
         ("MONO_BOLD", "jbm13_s"), ("SHORTCUT", "jbm11_r"),
         ("NAME_LARGE", "inter16_s"), ("CLOCK", "jbm40_s"), ("CAPTION", "inter11_r"), ("SMALL_NAME", "inter12_m"),
         ("PIN11", "inter11_r"), ("PIN10", "inter10_r")]


# The apps' faces by role (stage RS), kit/appfaces.ci's face numbers.
APP_ROLES = [("FIGURE", "jbm28_s"), ("FIGURE_LARGE", "jbm32_s"), ("KEY", "inter17_m"), ("FACT", "jbm13_r"),
             ("BUTTON", "inter12_s")]


def faces_module(roles=ROLES, manifest=MANIFEST, head=None):
    """kit/faces.ci: one entry a chrome face and scale over the prop modules, so ctext.ci names a face by role."""
    mods = [m for _, m in roles]
    L = head or ["// user/ci/kit/faces.ci: the chrome faces of FONT-1 by role (F4), each at 1x and 2x, over the modules",
                 "// tools/glyphs.py writes; written by tools/glyphs.py; do not edit. kit/ctext.ci draws with it."]
    for m in dict.fromkeys(mods):   # a module two roles share is imported once
        L += ["import user.ci.kit.%s1;" % m, "import user.ci.kit.%s2;" % m]
    L.append("")
    ROLES_ = roles
    for k, (role, m) in enumerate(roles):
        use = next(r[5] for r in manifest if r[0] == m)
        L.append("export const I64 %s = %d;%s// %s" % (role, k, " " * max(1, 8 - len(role)), use))
    L += ["export const I64 FACES = %d;" % len(roles), ""]

    def fn(sig, call, doc, default="0"):
        out = ["// %s" % doc, "export I64 %s {" % sig]
        for k, (_, m) in enumerate(ROLES_):
            out.append("    if (f == %d) { if (z == 2) { return %s2.%s; } return %s1.%s; }" % (k, m, call, m, call))
        return out + ["    return %s;" % default, "}", ""]
    L += fn("index(I64 f, I64 z, I64 cp)", "index(cp)", "The glyph of code point cp in face f at scale z (1 or 2), or the face's stand-in.")
    L += fn("advance(I64 f, I64 z, I64 g)", "advance(g)", "Glyph g's advance in whole pixels.")
    L += fn("left(I64 f, I64 z, I64 g)", "left(g)", "Glyph g's ink box from the pen on the baseline, y down: left, top, width, height.")
    L += fn("top(I64 f, I64 z, I64 g)", "top(g)", "")
    L += fn("width(I64 f, I64 z, I64 g)", "width(g)", "")
    L += fn("height(I64 f, I64 z, I64 g)", "height(g)", "")
    L += fn("at(I64 f, I64 z, I64 g, I64 x, I64 y)", "at(g, x, y)", "Coverage 0 to 15 of pixel (x, y) of glyph g's box.")
    L += fn("ascent(I64 f, I64 z)", "ASCENT", "The face's line box above and below the baseline, whole pixels.")
    L += fn("descent(I64 f, I64 z)", "DESCENT", "")
    L = [l for l in L if l != "// "]
    return "\n".join(L).rstrip("\n") + "\n// SPDX-License-Identifier: Apache-2.0\n"   # SPDX-1 A: the role table is Daphnis's


def modules():
    want = sums()
    fonts = {}
    out = []
    for row in MANIFEST + APP_MANIFEST:
        name, kind, rel, size, track, use = row[:6]
        wanted = row[6] if len(row) > 6 else TEXT
        if rel not in fonts:
            fonts[rel] = load(rel, want)
        font = fonts[rel]
        for z in (1, 2):
            mod = "%s%d" % (name, z)
            if kind == "cell":
                text, nw = cell_module(mod, font, rel, z, use)
            else:
                inter = rel.startswith("inter/")
                text, nw = prop_module(mod, font, rel, size, track, z, use, "Inter" if inter else "JetBrains Mono",
                                       "inter/LICENSE.txt" if inter else "jetbrains-mono/OFL.txt", wanted)
            if nw >= 65536:
                raise SystemExit("glyphs.py: %s needs %d words, past the array cap" % (mod, nw))
            out.append((mod, text, nw))
    out.append(("faces", faces_module(), 0))
    out.append(("appfaces", faces_module(APP_ROLES, APP_MANIFEST, [
        "// user/ci/kit/appfaces.ci: the apps' faces by role (stage RS: Calc and Monitor), each at 1x and 2x, over the",
        "// modules tools/glyphs.py writes; written by tools/glyphs.py; do not edit. kit/apptext.ci draws with it."]), 0))
    return out


def main():
    check = sys.argv[1:] == ["--check"]
    bad = 0
    for mod, text, nw in modules():
        path = os.path.join(KIT, mod + ".ci")
        if check:
            try:
                with open(path) as f:
                    same = f.read() == text
            except OSError:
                same = False
            if not same:
                bad += 1
            print("%s  glyphs: user/ci/kit/%s.ci%s is what tools/glyphs.py writes" % ("PASS" if same else "FAIL", mod, " (%d words)" % nw if nw else ""))
        else:
            with open(path, "w") as f:
                f.write(text)
            print("wrote user/ci/kit/%s.ci%s" % (mod, ", %d words" % nw if nw else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
