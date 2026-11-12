#!/usr/bin/env python3
"""tools/face.py [--check]: the kit's face, Daphnis Mono (stage K, K-2; F-1 to F-7 A), the 95 printable ASCII glyphs
drawn twice by agy with l: 8 x 16 cells (tools/fonts/daphnis_mono_8x16.txt, F-1) written to user/ci/kit/face.ci, and
16 x 32 cells (tools/fonts/daphnis_mono_16x32.txt, F-2) written to user/ci/kit/face2.ci, the tables the cint kit
draws from. With --check, exits 1 if either table is not what this file writes. The drawings and both tables are
under OFL-1.1 (F-7; tools/fonts/OFL.txt); they are copied unchanged from pennyleans/studio-assets
reference/daphnis-desk/agy/ at bd87807 (edition 3, the softer and thicker face l accepted 2026-11-07; the ASSETS.json
rows' sha256).

The drawings: a humanist face with rounded bowls, stems 2 px at 8 x 16 and 4 px at 16 x 32. At 8 x 16, rows 0
to 2 are clear and a
glyph's body is columns 1 to 6; column 7 is always clear, so two glyphs stand at least 1 px apart. At 16 x 32, rows 0
to 5 are clear and columns 14 and 15 are.

The format: one glyph a line, its code in hex, then its rows from row TOP down, separated by spaces: '#' is ink,
'.' paper, '-' a clear row; missing rows at the end are clear. A file other than the 8 x 16 one starts with a line
`cell W H TOP`, and each row is W marks. In the 8 x 16 file TOP is 3 and a token of 6 marks is columns 1 to 6, one of
7 columns 0 to 6.

face.ci holds each 8 x 16 glyph as two U64 words (rows 0 to 7, rows 8 to 15), row 0 in the top byte and column 0 in a
byte's top bit, the order of the VGA text font. face2.ci holds each 16 x 32 glyph as eight U64 words of four rows,
row 0 in the top 16 bits and column 0 in a row's top bit."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "face.ci")


FONTS = os.path.join(HERE, "fonts")


def parse(text, w, h, top, codes):
    """{code: [h rows]} for the glyph lines of text, column 0 in bit w - 1; exits on a bad line or a missing code."""
    glyphs = {}
    for line in text.strip().splitlines():
        head, *rows = line.split()
        code = int(head, 16)
        if code in glyphs or code not in codes or top + len(rows) > h:
            raise SystemExit("face.py: bad glyph line %r" % line)
        cells = [0] * top
        for tok in rows:
            if tok == "-":
                tok = "." * w
            if w == 8 and len(tok) in (6, 7):
                tok = ("." + tok if len(tok) == 6 else tok) + "."
            if len(tok) != w or set(tok) - set("#."):
                raise SystemExit("face.py: bad row %r of glyph %02x" % (tok, code))
            cells.append(sum(1 << (w - 1 - i) for i, ch in enumerate(tok) if ch == "#"))
        glyphs[code] = cells + [0] * (h - len(cells))
    if set(glyphs) != set(codes):
        raise SystemExit("face.py: glyphs missing: %s" % sorted(set(codes) - set(glyphs)))
    return glyphs


def read(name, w, h, top):
    with open(os.path.join(FONTS, name)) as f:
        text = f.read()
    first, _, rest = text.partition("\n")
    if first.split()[:1] == ["cell"]:
        if [int(v) for v in first.split()[1:]] != [w, h, top]:
            raise SystemExit("face.py: %s is %s, not cell %d %d %d" % (name, first, w, h, top))
        text = rest
    return parse(text, w, h, top, set(range(32, 127)))


def table():
    """{code: [16 row bytes]} for codes 32 to 126, column 0 in bit 7."""
    return read("daphnis_mono_8x16.txt", 8, 16, 3)


def table2():
    """{code: [32 rows of 16 bits]} for codes 32 to 126, column 0 in bit 15."""
    return read("daphnis_mono_16x32.txt", 16, 32, 6)


def emit():
    g = table()
    words = []
    for code in range(32, 127):
        rows = g[code]
        words.append(int.from_bytes(bytes(rows[:8]), "big"))
        words.append(int.from_bytes(bytes(rows[8:]), "big"))
    lines = ["// user/ci/kit/face.ci: the kit's face, Daphnis Mono 8 x 16 (stage K, K-2; OFL-1.1, tools/fonts/OFL.txt),",
             "// written by tools/face.py from tools/fonts/daphnis_mono_8x16.txt; do not edit. 95 glyphs, codes 32 to",
             "// 126, of 8 x 16 pixels: glyph c is",
             "// bits[2 * (c - 32)] (rows 0 to 7) and bits[2 * (c - 32) + 1] (rows 8 to 15), row 0 in the top byte,",
             "// column 0 in a byte's top bit. A code outside 32 to 126 draws as '?'.",
             "",
             "export const I64 W = 8;",
             "export const I64 H = 16;",
             "",
             "U64[190] bits = ["]
    for i in range(0, len(words), 4):
        chunk = ", ".join("0x%016x" % w for w in words[i:i + 4])
        lines.append("    " + chunk + ("," if i + 4 < len(words) else ""))
    lines += ["];",
              "",
              "// Row y (0 to 15) of glyph c as a byte, column 0 in bit 7.",
              "export I64 row(I64 c, I64 y) {",
              "    I64 k = c - 32;",
              "    if (k < 0 || k > 94) { k = 31; }",
              "    U64 word = bits[2 * k + y / 8];",
              "    return ((word >> (8 * (7 - y % 8)) as U64) & 255) as I64;",
              "}",
              "// SPDX-License-Identifier: Apache-2.0",
              ""]
    return "\n".join(lines)


def emit2():
    g = table2()
    words = []
    for code in range(32, 127):
        rows = g[code]
        for q in range(8):
            words.append(sum(rows[4 * q + j] << (16 * (3 - j)) for j in range(4)))
    lines = ["// user/ci/kit/face2.ci: Daphnis Mono 16 x 32 (stage K, K-2, F-2 A; OFL-1.1, tools/fonts/OFL.txt), the",
             "// face's own drawing at 2x, written by tools/face.py from tools/fonts/daphnis_mono_16x32.txt; do not edit.",
             "// 95 glyphs, codes 32 to 126, of 16 x 32 pixels: glyph c is bits[8 * (c - 32)] to bits[8 * (c - 32) + 7],",
             "// four rows a word, row 0 in the top 16 bits, column 0 in a row's top bit. A code outside 32 to 126 draws",
             "// as '?'.",
             "",
             "export const I64 W = 16;",
             "export const I64 H = 32;",
             "",
             "U64[760] bits = ["]
    for i in range(0, len(words), 4):
        chunk = ", ".join("0x%016x" % w for w in words[i:i + 4])
        lines.append("    " + chunk + ("," if i + 4 < len(words) else ""))
    lines += ["];",
              "",
              "// Row y (0 to 31) of glyph c as 16 bits, column 0 in bit 15.",
              "export I64 row(I64 c, I64 y) {",
              "    I64 k = c - 32;",
              "    if (k < 0 || k > 94) { k = 31; }",
              "    U64 word = bits[8 * k + y / 4];",
              "    return ((word >> (16 * (3 - y % 4)) as U64) & 65535) as I64;",
              "}",
              "// SPDX-License-Identifier: Apache-2.0",
              ""]
    return "\n".join(lines)


OUTS = ((OUT, emit), (os.path.join(HERE, "..", "user", "ci", "kit", "face2.ci"), emit2))


def main(argv):
    if argv == ["--check"]:
        bad = 0
        for path, fn in OUTS:
            with open(path) as f:
                same = f.read() == fn()
            print("%s  face: user/ci/kit/%s is what tools/face.py writes" % ("PASS" if same else "FAIL",
                                                                            os.path.basename(path)))
            bad += not same
        return 1 if bad else 0
    for path, fn in OUTS:
        with open(path, "w") as f:
            f.write(fn())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
