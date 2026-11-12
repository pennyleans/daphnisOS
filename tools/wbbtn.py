#!/usr/bin/env python3
"""tools/wbbtn.py [--check]: WB-5, a float's four bar buttons (minimize, fullscreen, tile, close) as agy drew them,
1-bit, 16 x 16 for 1x and 32 x 32 for 2x (user/ci/kit/wbbtn/, from studio-assets l/daphnis-wm-bars 10b094c,
reference/daphnis-wm/agy/ui_wb_btn_*.txt, accepted by l 2026-11-07), written to user/ci/kit/wbbtn.ci as the table
hdesk draws from. With --check, exits 1 if user/ci/kit/wbbtn.ci is not what this file writes.

A row is one word, column 0 in the word's top bit: bit (n - 1 - x) of row y is pixel (x, y) of the n x n button."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "user", "ci", "kit")
NAMES = ["minimize", "fullscreen", "tile", "close"]


def button(name, n):
    """Rows of '#' and '.' of button name at n x n."""
    with open(os.path.join(KIT, "wbbtn", "ui_wb_btn_%s_%d.txt" % (name, n))) as f:
        lines = f.read().splitlines()
    assert lines[0] == "# button %s %dx%d" % (name, n, n), lines[0]
    rows = lines[1:1 + n]
    assert len(rows) == n and all(len(r) == n and set(r) <= {"#", "."} for r in rows), name
    return rows


def words(n):
    return [int(r.replace("#", "1").replace(".", "0"), 2) for name in NAMES for r in button(name, n)]


def emit():
    out = ["// user/ci/kit/wbbtn.ci: written by tools/wbbtn.py from user/ci/kit/wbbtn/ (the design's table);",
           "// do not edit. WB-5: the bar's four buttons, 0 minimize, 1 fullscreen, 2 tile, 3 close; a row a word,",
           "// column 0 in the top bit."]
    for n in (16, 32):
        w = words(n)
        out.append("U32[%d] b%d = [" % (len(w), n))
        for k in range(0, len(w), 8):
            out.append("    " + ", ".join("0x%08x" % v for v in w[k:k + 8]) + ("," if k + 8 < len(w) else "];"))
    out += ["",
            "// Pixel (x, y) of button k at n x n (n 16 or 32): inked or not.",
            "export Bool at(I64 k, I64 n, I64 x, I64 y) {",
            "    if (n == 32) { return ((b32[32 * k + y] as I64 >> (31 - x)) & 1) == 1; }",
            "    return ((b16[16 * k + y] as I64 >> (15 - x)) & 1) == 1;",
            "}", "// SPDX-License-Identifier: Apache-2.0", ""]
    return "\n".join(out)


if __name__ == "__main__":
    path = os.path.join(KIT, "wbbtn.ci")
    if sys.argv[1:] == ["--check"]:
        sys.exit(0 if os.path.exists(path) and open(path).read() == emit() else 1)
    with open(path, "w") as f:
        f.write(emit())
