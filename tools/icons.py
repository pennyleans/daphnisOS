#!/usr/bin/env python3
"""tools/icons.py [--check]: the desk's icons (docs/specs/2026-11-07-ff-super-plane.md section 3a, FF-0), fifteen
drawings by agy with l, each at 32 x 32 (1x) and its own 64 x 64 (2x), written to user/ci/kit/icons.ci, the table the
cint kit draws from. The drawings are tools/icons/icon_NAME_SIZE.txt, copied unchanged from pennyleans/studio-assets
reference/daphnis-desk/agy/icons/ at bd87807 (desk edition 3, accepted by l 2026-11-07; the ASSETS.json rows'
sha256 are tools/icons/SHA256SUMS). With --check, exits 1 if a drawing is not its sum or icons.ci is not what
this file writes.

The format (studio-assets PR 28, D-1): the first line `icon NAME SIZE`, then SIZE rows of SIZE marks, one a pixel:
'.' clear (the ground shows), and one letter a kit token, P paper, I ink, U ultramarine, S sienna, O ochre,
C cadmium. Tokens, not colors, so an icon takes the theme it is drawn in (K-3); cadmium is for faults (KD-4 A).

icons.ci holds a pixel as a 4-bit token, 0 clear and 1 to 6 the letters in the order above, sixteen to a U64 word,
column 0 in the top nibble: a 32 px row is 2 words, a 64 px row 4. Icon k at 32 starts at word 64 k; at 64, at
word 64 N + 256 k."""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "icons")
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "icons.ci")

NAMES = ("terminal", "editor", "finder", "settings", "doom", "cview", "ccalc", "cless", "fetch", "program", "dir",
         "text", "ci", "image", "wad")
TOKENS = ".PIUSOC"
SIZES = (32, 64)


def sums():
    rows = {}
    with open(os.path.join(SRC, "SHA256SUMS")) as f:
        for line in f:
            h, name = line.split()
            rows[name] = h
    return rows


def drawing(name, size):
    path = os.path.join(SRC, "icon_%s_%d.txt" % (name, size))
    with open(path) as f:
        lines = f.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if lines[0] != "icon %s %d" % (name, size) or len(lines) != size + 1:
        raise SystemExit("icons.py: %s: not `icon %s %d` and %d rows" % (path, name, size, size))
    rows = []
    for r in lines[1:]:
        if len(r) != size or any(c not in TOKENS for c in r):
            raise SystemExit("icons.py: %s: bad row %r" % (path, r))
        rows.append([TOKENS.index(c) for c in r])
    return rows


def words():
    out = []
    for size in SIZES:
        for name in NAMES:
            for r in drawing(name, size):
                for j in range(0, size, 16):
                    out.append(sum(t << (4 * (15 - i)) for i, t in enumerate(r[j:j + 16])))
    return out


def emit():
    w = words()
    pool = []
    at = []
    for n in NAMES:
        at.append(len(pool))
        pool += [ord(c) for c in n]
    lines = ["// user/ci/kit/icons.ci: the desk's icons (docs/specs/2026-11-07-ff-super-plane.md section 3a, FF-0), drawn",
             "// by agy with l, written by tools/icons.py from tools/icons/; do not edit. Fifteen icons at 32 x 32 and",
             "// 64 x 64; a pixel is a token, CLEAR or a kit token, so the caller's theme colors it.",
             "",
             "export const I64 N = %d;" % len(NAMES)]
    for k, n in enumerate(NAMES):
        lines.append("export const I64 %s = %d;" % (n.upper(), k))
    lines += ["",
              "export const I64 CLEAR = 0;",
              "export const I64 PAPER = 1;",
              "export const I64 INK = 2;",
              "export const I64 ULTRAMARINE = 3;",
              "export const I64 SIENNA = 4;",
              "export const I64 OCHRE = 5;",
              "export const I64 CADMIUM = 6;",
              "",
              "U8[%d] names = [%s];" % (len(pool), ", ".join(str(c) for c in pool)),
              "I64[%d] name_at = [%s];" % (len(NAMES) + 1, ", ".join(str(a) for a in at + [len(pool)])),
              "",
              "U64[%d] bits = [" % len(w)]
    for i in range(0, len(w), 4):
        lines.append("    " + ", ".join("0x%016x" % v for v in w[i:i + 4]) + ("," if i + 4 < len(w) else ""))
    lines += ["];",
              "",
              "// The icon named name (`terminal`, `doom`, ...), or -1.",
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
              "// The token of pixel (x, y) of icon k at size px, 32 or 64; CLEAR outside it.",
              "export I64 tok(I64 k, I64 px, I64 x, I64 y) {",
              "    if (k < 0 || k >= N || x < 0 || y < 0 || x >= px || y >= px) { return CLEAR; }",
              "    I64 base = 0;",
              "    if (px == 32) {",
              "        base = 64 * k;",
              "    } else if (px == 64) {",
              "        base = 64 * N + 256 * k;",
              "    } else {",
              "        return CLEAR;",
              "    }",
              "    U64 word = bits[base + y * (px / 16) + x / 16];",
              "    return ((word >> (4 * (15 - x % 16)) as U64) & 15) as I64;",
              "}",
              "",
              "// Icon k at size px, 32 or 64, from (x0, y0), on row y: token t in pal[t] (pal[1] to pal[6], the theme's",
              "// paper, ink, ultramarine, sienna, ochre and cadmium); a clear pixel is left as it is.",
              "export void icon_at(inout U32[_] row, I64 y, I64 x0, I64 y0, I64 k, I64 px, in U32[_] pal) {",
              "    if (y < y0 || y >= y0 + px) { return; }",
              "    for x in 0..px {",
              "        I64 t = tok(k, px, x, y - y0);",
              "        if (t != CLEAR) { draw.put(row, x0 + x, pal[t]); }",
              "    }",
              "}",
              "// SPDX-License-Identifier: Apache-2.0",
              ""]
    lines.insert(4, "import user.ci.kit.draw;")
    lines.insert(5, "")
    return "\n".join(lines)


def main(argv):
    if argv == ["--check"]:
        want = sums()
        bad = 0
        for size in SIZES:
            for name in NAMES:
                f = "icon_%s_%d.txt" % (name, size)
                with open(os.path.join(SRC, f), "rb") as fh:
                    bad += hashlib.sha256(fh.read()).hexdigest() != want.get(f)
        with open(OUT) as f:
            same = f.read() == emit()
        ok = same and not bad and len(want) == len(NAMES) * len(SIZES)
        print("%s  icons: the %d drawings are studio-assets' and user/ci/kit/icons.ci is what tools/icons.py writes"
              % ("PASS" if ok else "FAIL", len(NAMES) * len(SIZES)))
        return 0 if ok else 1
    with open(OUT, "w") as f:
        f.write(emit())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
