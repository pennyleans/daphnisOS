#!/usr/bin/env python3
"""tools/mark.py [--check]: the kit's mark (docs/specs/2026-11-05-w-tiler.md section 2) as the 1-bit table
user/ci/kit/mark.ci, 16 px high, which the kit draws at 1x and at 2x. Ruling MK-1 (2026-11-05): this miniature
1-bit mark is Daphnis's mark in the OS; the opencut lockup in pennyleans/studio-assets is the large and promo
mark, not drawn here.

The mark: a 16 x 16 counter-change disc (the left half ink with a paper half disc, the right half paper with an
ink half disc, radius 6) and, 8 px on, "daphnis" cropped to its ink. The wordmark keeps the letters of the first
face (W-1), drawn below in tools/face.py's format; Daphnis Mono did not move it (F-6 A, stage K, K-2).

With --check, exits 1 if user/ci/kit/mark.ci is not what this file writes."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "mark.ci")
H = 16
WORD = r"""
61 - - - .##### #....# #....# #....# #....# #....# .#####
64 .....# .....# .....# .##### #....# #....# #....# #....# #....# .#####
68 #..... #..... #..... #####. #....# #....# #....# #....# #....# #....#
69 - ..#... - .##... ..#... ..#... ..#... ..#... ..#... .###..
6e - - - #####. #....# #....# #....# #....# #....# #....#
70 - - - #####. #....# #....# #....# #....# #....# #####. #..... #..... #.....
73 - - - .##### #..... #..... .####. .....# .....# #####.
"""


def figure():
    sys.path.insert(0, HERE)
    import face
    g = face.parse(WORD, 8, 16, 3, set(b"adhinps"))
    rows = [[0] * (16 + 8 + 8 * 7) for _ in range(H)]
    for y in range(H):
        for x in range(16):
            inside = (2 * x - 15) ** 2 + (2 * y - 15) ** 2 <= 144
            rows[y][x] = int(inside) if x >= 8 else int(not inside)
        for k, ch in enumerate("daphnis"):
            for b in range(8):
                rows[y][24 + 8 * k + b] = (g[ord(ch)][y] >> (7 - b)) & 1
    return crop(rows)


def crop(rows):
    xs = [x for r in rows for x, v in enumerate(r) if v]
    ys = [y for y, r in enumerate(rows) if any(r)]
    if not xs:
        raise SystemExit("mark.py: the figure has no ink")
    return [r[min(xs):max(xs) + 1] for r in rows[min(ys):max(ys) + 1]]


def emit(rows):
    w = len(rows[0])
    wpr = (w + 63) // 64
    words = []
    for r in rows:
        bits = r + [0] * (64 * wpr - w)
        for j in range(wpr):
            words.append(sum(v << (63 - i) for i, v in enumerate(bits[64 * j:64 * j + 64])))
    lines = ["// user/ci/kit/mark.ci: the kit's mark (docs/specs/2026-11-05-w-tiler.md section 2, ruling MK-1), written",
             "// by tools/mark.py; do not edit. The counter-change disc and \"daphnis\" in the kit's face.",
             "// W x H pixels, row y as WPR words from bits[y * WPR], column 0 in the first word's top bit.",
             "",
             "export const I64 W = %d;" % w,
             "export const I64 H = %d;" % H,
             "const I64 WPR = %d;" % wpr,
             "",
             "U64[%d] bits = [" % len(words)]
    for i in range(0, len(words), 4):
        lines.append("    " + ", ".join("0x%016x" % v for v in words[i:i + 4]) + ("," if i + 4 < len(words) else ""))
    lines += ["];",
              "",
              "// True when pixel (x, y) of the mark is ink.",
              "export Bool ink(I64 x, I64 y) {",
              "    U64 word = bits[y * WPR + x / 64];",
              "    return ((word >> (63 - x % 64) as U64) & 1) == 1;",
              "}",
              "// SPDX-License-Identifier: Apache-2.0",
              ""]
    return "\n".join(lines)


def main(argv):
    text = emit(figure())
    if "--check" in argv:
        with open(OUT) as f:
            same = f.read() == text
        print("%s  mark: user/ci/kit/mark.ci is what tools/mark.py writes" % ("PASS" if same else "FAIL"))
        return 0 if same else 1
    with open(OUT, "w") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
