#!/usr/bin/env python3
"""tools/sans.py [--check]: Daphnis Sans (stage K, K-4; E2-4 A), the proportional face of the desk's chrome: the bar,
the menus, the switcher, the calendar and Settings. Daphnis Mono (tools/face.py) stays the terminals' face. Two
drawings by agy with l, the 95 printable ASCII glyphs each: 14 x 16 cells (tools/fonts/daphnis_sans_16.txt) written
to user/ci/kit/sans.ci for odd UI scales, and 28 x 32 cells (tools/fonts/daphnis_sans_32.txt, every advance twice the
16's) written to user/ci/kit/sans2.ci for even ones. With --check, exits 1 if either table is not what this file
writes. Daphnis Sans is a Modified Version of Cascadia Code under OFL-1.1, with Fira Sans and Jost spurs: the
drawings and both tables are under OFL-1.1 (tools/fonts/OFL.txt, which carries the notices). They are copied
unchanged from pennyleans/studio-assets reference/daphnis-desk/agy/ at bd87807: edition 3, the softer, thicker face
(2 px stems at 16 px, 4 px at 32 px) l accepted 2026-11-07 (the ASSETS.json rows' sha256).

The format is tools/face.py's with a `cell W H TOP` first line, and after each code `# adv=N`: the glyph's advance in
pixels, its ink inside columns 0 to N - 1. A glyph draws from the pen's x; the pen moves on by the advance.

sans.ci holds each 16 px glyph as four U64 words of four rows, 16 bits a row; sans2.ci each 32 px glyph as sixteen
U64 words of two rows, 32 bits a row. Row 0 is in a word's top bits and column 0 in a row's top bit."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
KIT = os.path.join(HERE, "..", "user", "ci", "kit")
CODES = range(32, 127)


def read(name, w, h, top, bits):
    """({code: [h rows]}, {code: advance}); column 0 in bit bits - 1. Exits on a bad line or a missing code."""
    with open(os.path.join(FONTS, name)) as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    if lines[0].split() != ["cell", str(w), str(h), str(top)]:
        raise SystemExit("sans.py: %s starts %r, not cell %d %d %d" % (name, lines[0], w, h, top))
    glyphs, adv = {}, {}
    for line in lines[1:]:
        head, mark, a, *rows = line.split()
        code = int(head, 16)
        if mark != "#" or not a.startswith("adv=") or code in glyphs or code not in CODES or top + len(rows) > h:
            raise SystemExit("sans.py: bad glyph line %r" % line[:60])
        n = int(a[4:])
        cells = [0] * top
        for tok in rows:
            tok = "." * w if tok == "-" else tok
            if len(tok) != w or set(tok) - set("#.") or "#" in tok[n:]:
                raise SystemExit("sans.py: bad row %r of glyph %02x (advance %d)" % (tok, code, n))
            cells.append(sum(1 << (bits - 1 - i) for i, ch in enumerate(tok) if ch == "#"))
        if not 1 <= n <= w:
            raise SystemExit("sans.py: glyph %02x advance %d outside 1 to %d" % (code, n, w))
        glyphs[code], adv[code] = cells + [0] * (h - len(cells)), n
    if set(glyphs) != set(CODES):
        raise SystemExit("sans.py: glyphs missing: %s" % sorted(set(CODES) - set(glyphs)))
    return glyphs, adv


def table():
    return read("daphnis_sans_16.txt", 14, 16, 3, 16)


def table2():
    g, a = read("daphnis_sans_32.txt", 28, 32, 5, 32)
    one = table()[1]
    if any(a[c] != 2 * one[c] for c in CODES):
        raise SystemExit("sans.py: an advance of daphnis_sans_32.txt is not twice the 16's")
    return g, a


def emit(name, g, a, h, bits, ref):
    per = 64 // bits                     # rows a word
    words = []
    for c in CODES:
        for q in range(h // per):
            words.append(sum(g[c][per * q + j] << (bits * (per - 1 - j)) for j in range(per)))
    n = h // per
    lines = ["// user/ci/kit/%s.ci: Daphnis Sans %d px (stage K, K-4, E2-4 A; OFL-1.1, tools/fonts/OFL.txt), written by" % (name, h),
             "// tools/sans.py from tools/fonts/%s; do not edit. 95 glyphs, codes 32 to 126: glyph c is" % ref,
             "// bits[%d * (c - 32)] to bits[%d * (c - 32) + %d], %d rows a word of %d bits, row 0 in the top bits, column 0 in" % (n, n, n - 1, per, bits),
             "// a row's top bit; adv[c - 32] is its advance in pixels. A code outside 32 to 126 draws as '?'.",
             "",
             "export const I64 H = %d;" % h,
             "",
             "U64[%d] bits = [" % len(words)]
    for i in range(0, len(words), 4):
        lines.append("    " + ", ".join("0x%016x" % w for w in words[i:i + 4]) + ("," if i + 4 < len(words) else ""))
    lines += ["];", "", "U8[95] adv = ["]
    av = [a[c] for c in CODES]
    for i in range(0, 95, 19):
        lines.append("    " + ", ".join(str(v) for v in av[i:i + 19]) + ("," if i + 19 < 95 else ""))
    lines += ["];",
              "",
              "I64 at(I64 c) {",
              "    I64 k = c - 32;",
              "    if (k < 0 || k > 94) { k = 31; }",
              "    return k;",
              "}",
              "",
              "// Glyph c's advance in pixels.",
              "export I64 advance(I64 c) { return adv[at(c)] as I64; }",
              "",
              "// Row y (0 to %d) of glyph c, column 0 in bit %d." % (h - 1, bits - 1),
              "export I64 row(I64 c, I64 y) {",
              "    U64 word = bits[%d * at(c) + y / %d];" % (n, per),
              "    return ((word >> (%d * (%d - y %% %d)) as U64) & %d) as I64;" % (bits, per - 1, per, (1 << bits) - 1),
              "}",
              "// SPDX-License-Identifier: Apache-2.0",
              ""]
    return "\n".join(lines)


def outs():
    g, a = table()
    g2, a2 = table2()
    return ((os.path.join(KIT, "sans.ci"), emit("sans", g, a, 16, 16, "daphnis_sans_16.txt")),
            (os.path.join(KIT, "sans2.ci"), emit("sans2", g2, a2, 32, 32, "daphnis_sans_32.txt")))


def main(argv):
    if argv == ["--check"]:
        bad = 0
        for path, text in outs():
            same = os.path.exists(path) and open(path).read() == text
            print("%s  sans: user/ci/kit/%s is what tools/sans.py writes" % ("PASS" if same else "FAIL",
                                                                            os.path.basename(path)))
            bad += not same
        return 1 if bad else 0
    for path, text in outs():
        with open(path, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
