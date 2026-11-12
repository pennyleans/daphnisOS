#!/usr/bin/env python3
"""tools/ease.py [--check]: MS-2 (docs/specs/2026-11-10-ms-motion-shadows.md, section 4), the desk's two easing
curves as 65-entry tables in thousandths, written to user/ci/kit/ease.ci, which user/ci/kit/anim.ci reads. With
--check, exits 1 if user/ci/kit/ease.ci is not what this file writes.

Each curve is a cubic Bezier from (0, 0) to (1, 1) with control points (x1, y1) and (x2, y2), as CSS
cubic-bezier() writes it: out (.2, .8, .2, 1) and in (.4, 0, 1, 1). Entry i is its progress y at time x = i / 64,
rounded half up to a whole thousandth. The tool finds it with exact rationals, no float: it bisects the curve's
parameter s on dyadic fractions until both ends of the bracket round to the same thousandth (x(s) and y(s) never
fall on [0, 1] for these control points, so the bracket holds the answer). tools/check-hdesk.py loads this file
for its twin of anim.ci, so the twin reads the same tables."""
import os
import sys
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "ease.ci")
N = 64                                   # steps; a table has N + 1 entries
CURVES = [("out", (F(1, 5), F(4, 5), F(1, 5), F(1))),    # anim.ci OUT = 0
          ("in", (F(2, 5), F(0), F(1), F(1)))]           # anim.ci IN = 1


def bez(p1, p2, s):
    """One coordinate of the cubic Bezier from 0 to 1 with inner control values p1, p2, at parameter s."""
    r = 1 - s
    return 3 * r * r * s * p1 + 3 * r * s * s * p2 + s * s * s


def thousandths(y):
    """y rounded half up to a whole thousandth."""
    v = y * 1000 + F(1, 2)
    return v.numerator // v.denominator


def entry(ctl, x):
    """The curve's progress at time x, in thousandths."""
    x1, y1, x2, y2 = ctl
    lo, hi = F(0), F(1)
    for _ in range(400):
        a, b = thousandths(bez(y1, y2, lo)), thousandths(bez(y1, y2, hi))
        if a == b:
            return a
        mid = (lo + hi) / 2
        xm = bez(x1, x2, mid)
        if xm == x:
            return thousandths(bez(y1, y2, mid))
        if xm < x:
            lo = mid
        else:
            hi = mid
    raise AssertionError("no thousandth found at x = %s" % x)


def tables():
    """The two tables in anim.ci's curve order."""
    t = [[entry(ctl, F(i, N)) for i in range(N + 1)] for _, ctl in CURVES]
    for c in t:
        assert len(c) == N + 1 and c[0] == 0 and c[N] == 1000, c
        assert all(c[i] <= c[i + 1] for i in range(N)), c
    return t


def emit():
    out = ["// user/ci/kit/ease.ci: written by tools/ease.py; do not edit. MS-2: the easing curves out (0), cubic",
           "// Bezier (.2, .8, .2, 1), and in (1), (.4, 0, 1, 1), each 65 entries in thousandths at time i / 64, curve",
           "// k's entry i at 65 * k + i. user/ci/kit/anim.ci reads them."]
    w = [v for c in tables() for v in c]
    out.append("I64[%d] tab = [" % len(w))
    for k in range(0, len(w), 13):
        out.append("    " + ", ".join("%d" % v for v in w[k:k + 13]) + ("," if k + 13 < len(w) else "];"))
    out += ["",
            "// Entry i (0 to 64) of curve k (0 or 1), in thousandths.",
            "export I64 at(I64 k, I64 i) {",
            "    return tab[%d * k + i];" % (N + 1),
            "}",
            "// SPDX-License-Identifier: Apache-2.0",
            ""]
    return "\n".join(out)


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        sys.exit(0 if os.path.exists(OUT) and open(OUT).read() == emit() else 1)
    with open(OUT, "w") as f:
        f.write(emit())
