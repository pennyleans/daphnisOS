#!/usr/bin/env python3
"""tools/shadow.py [--check | --sizes | --prove [R...]]: MS-3 and MS-3b (docs/specs/2026-11-10-ms-motion-shadows.md,
law 2 and section 3; MS-R2 B), the desk's shadow tables, written to user/ci/kit/shadow.ci, which user/ci/kit/shade.ci
draws from. With --check, exits 1 if user/ci/kit/shadow.ci is not what this file writes (making it proves every
threshold, below); --sizes prints the entry counts; --prove sweeps every corner pixel of radii R (default the radii
in use, PROVE_RADII) at every factor, level and theme and exits 1 if the draw-time count differs from the exact
quarter anywhere (about 20 s, so check.sh runs the threshold proof, not the sweep).

Three levels, two layers each: a contact line (dy, blur 0) and an ambient layer (dy, b). b is a CSS box-shadow blur
radius (design note 13, DN-13): the ambient layer is the shape blurred by a Gaussian of sigma b / 2, made exactly as
the binomial kernel of b^2 + 1 taps. Tables are at device pixels for each Size factor in SCALES (dy and the cut times
the factor), for both themes; each value is the layer's alpha times its coverage, rounded half up to a whole 256th (0 to 256), the alpha that kit/blend.ci's mix_px takes toward
the theme's shadow color. At factor s a layer is the same shadow as at 1x on finer pixels: each device pixel takes
the 1x profile at its center's logical position (its distance over s).

Coverage, in exact integers, never at run time:
  taps     n = b^2 trials, w_j = C(n, j + n/2) / 2^n for j = -n/2..n/2 (variance b^2 / 4, sigma b / 2), each spread
           evenly over its pixel, so the edge profile H(u) (the kernel's mass beyond a signed distance u outside the
           edge) is the tail sum S_d at the half pixel d - 1/2 and the straight line between
  cut      a layer's cut c (at 1x) is the first pixel d >= 1 outside the edge where alpha x H(d - 1/2) x 255 falls
           below 2 (section 3: "within 2 of 255"); its extent below the shape is dy + c: 21, 43 and 55 px for the
           dark ambient layers. Past the cut the table is 0, and inside -c it is the full alpha
  edge     a device pixel d pixels outside a straight edge (d = 1 is the first outside; d <= 0 inside) has its
           center at u = (d - 1/2) / s logical pixels, so its coverage is H(u); 2cs + 2 entries, d = -cs - 1..cs,
           the first the full alpha (every d inside -cs reads it)
  corner   a corner quarter of radius r at 1x: device pixel (i, j) of the (r + c)s x (r + c)s box counted out from
           the arc's center has its center sqrt((i + 1/2)^2 + (j + 1/2)^2) from it, taken by isqrt to 2^-21 px; its
           coverage is H(u) at u = (that - rs) / s, cut as the edge is (0 past u = c - 1/(2s), full before
           -c - 1/(2s)). That value depends on the pixel only through p = D - rs 2^21 (D its distance in 2^-21 px),
           and falls as p grows, so MS-R2 B keeps, per factor, level and theme, the thresholds P_v (the largest p
           still worth v, v = 1 to the full alpha): kit/shadow.ci counts the thresholds a pixel's p lies within, any
           radius, nothing cached. thresholds() proves each P_v exactly (the value at P_v is at least v and at
           P_v + 1 below it, P falling, the ends full and 0), so the count is the quarter's value at every p
  contact  blur 0 is a hard offset copy of the shape: its profile is the one full entry, and its corner quarter is
           counted as hdesk.ci's cut_corners counts a float's own corner: 4 x 4 samples a pixel inside the arc,
           (8i + 2s + 1)^2 + (8j + 2t + 1)^2 <= 64 r^2, out of 16, so the contact line's arc agrees with the shape's
           anti-aliased arc; kit/shadow.ci counts the samples at draw time and reads the alpha of that count"""
import os
import sys
from math import comb, isqrt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "user", "ci", "kit", "shadow.ci")
SCALES = [1, 2, 3, 4, 5, 6]   # DN-13 and MS-R2 B: every Size factor 1x to 6x
PROVE_RADII = [8, 12, 16, 18]  # the radii in use (DN-6, board 20261110T053139Z), which --prove sweeps
CHUNK = 60000              # cint 0.2.18 refuses an array literal of 65,536 entries or more (C9102), so the data is cut
FRAC = 21                  # corner distances to 2^-21 px
# level 1 low, 2 mid, 3 high: (dy, b) of the contact and the ambient layer (section 3)
LAYERS = [((1, 0), (6, 14)), ((2, 0), (12, 28)), ((2, 0), (16, 36))]
# alpha in percent, [theme][level - 1] = (contact, ambient); theme 0 dark (#000000), 1 light (#141413)
ALPHA = [[(30, 35), (35, 45), (35, 45)],
         [(12, 12), (20, 24), (20, 28)]]
EXTENTS_DARK = [21, 43, 55]   # section 3's extents, dy + the cut of the dark ambient layers


class Kernel:
    """The binomial of b^2 trials as integers: tap j (j = -m..m, m = b^2 / 2) weighs W[j + m] out of T = 2^(b^2), and
    S[d + m] is the tail sum of the taps j >= d (S[2m + 1] = 0)."""

    def __init__(self, b):
        n = b * b
        assert n % 2 == 0, "b^2 + 1 taps centered on a pixel needs b^2 even"
        self.m = m = n // 2
        self.T = 1 << n
        self.W = [comb(n, j + m) for j in range(-m, m + 1)]
        self.S = [0] * (2 * m + 2)
        for k in range(2 * m, -1, -1):
            self.S[k] = self.S[k + 1] + self.W[k]
        assert self.S[0] == self.T

    def tail(self, d):
        """S_d, the mass of the taps j >= d, out of T."""
        if d <= -self.m:
            return self.T
        if d > self.m:
            return 0
        return self.S[d + self.m]

    def h(self, p, q):
        """H(p / q) as the integer X with H = X / (2 q T): the mass beyond u = p / q (q > 0), each tap spread evenly
        over [j - 1/2, j + 1/2]."""
        m = self.m
        j = (2 * p + q) // (2 * q)          # u lies in [j - 1/2, j + 1/2)
        if j < -m:
            return 2 * q * self.T
        if j > m:
            return 0
        return 2 * q * self.tail(j + 1) + self.W[j + m] * ((2 * j + 1) * q - 2 * p)


def to256(alpha, x, den):
    """The alpha (percent) times the coverage x / den, in 256ths rounded half up."""
    return (2 * alpha * 256 * x + 100 * den) // (2 * 100 * den)


def full(alpha):
    return to256(alpha, 1, 1)


KERNELS = {}


def kernel(b):
    if b not in KERNELS:
        KERNELS[b] = Kernel(b)
    return KERNELS[b]


def cut(lv, th, k):
    """The layer's cut at 1x: 0 for a contact layer; for an ambient one the first d >= 1 with
    alpha x S_d / T x 255 < 2."""
    b = LAYERS[lv][k][1]
    if b == 0:
        return 0
    a, kn = ALPHA[th][lv][k], kernel(b)
    d = 1
    while a * 255 * kn.tail(d) >= 2 * 100 * kn.T:
        d += 1
    return d


def profile(lv, th, k, s):
    """The edge profile at factor s: 2cs + 2 entries, d = -cs - 1..cs, the first the full alpha; a contact layer's
    is its two full entries, d = -1 and 0."""
    b, a, c = LAYERS[lv][k][1], ALPHA[th][lv][k], cut(lv, th, k)
    if b == 0:
        return [full(a), full(a)]
    kn = kernel(b)
    return [full(a)] + [to256(a, kn.h(2 * d - 1, 2 * s), 2 * (2 * s) * kn.T) for d in range(-c * s, c * s + 1)]


def dist2(i, j):
    """sqrt((i + 1/2)^2 + (j + 1/2)^2) times 2^FRAC, rounded down."""
    return isqrt(((2 * i + 1) ** 2 + (2 * j + 1) ** 2) << (2 * FRAC - 2))


def corner(r1, lv, th, k, s):
    """Radius r1 at 1x, at factor s: the n x n quarter, n = (r1 + c)s, row j (out from the center, vertically) by
    column i, j * n + i."""
    b, a, c = LAYERS[lv][k][1], ALPHA[th][lv][k], cut(lv, th, k)
    r = r1 * s
    n = r + c * s
    out = []
    if b == 0:
        for j in range(n):
            for i in range(n):
                q = sum(1 for x in range(4) for y in range(4)
                        if (8 * i + 2 * x + 1) ** 2 + (8 * j + 2 * y + 1) ** 2 <= 64 * r * r)
                out.append(to256(a, q, 16))
        return out
    kn, one = kernel(b), 1 << FRAC
    q = s * one                               # u = (D - r one) / (s one)
    hi = (2 * c * s - 1) * one                # keep while 2 s (D - r one) <= (2cs - 1) one, i.e. u <= c - 1/(2s)
    lo = -(2 * c * s + 1) * one               # full while 2 s (D - r one) < -(2cs + 1) one
    fa = full(a)
    for j in range(n):
        for i in range(n):
            p = dist2(i, j) - r * one
            if 2 * p > hi:
                out.append(0)
            elif 2 * p < lo:
                out.append(fa)
            else:
                out.append(to256(a, kn.h(p, q), 2 * q * kn.T))
    return out


def corner_p(lv, th, s, p):
    """The exact ambient value at p = D - rs 2^FRAC (D a pixel's distance to the arc's center in 2^-FRAC px, rs the
    radius at factor s): what corner() gives every pixel at that p, for any radius."""
    b, a, c = LAYERS[lv][1][1], ALPHA[th][lv][1], cut(lv, th, 1)
    one = 1 << FRAC
    if 2 * p > (2 * c * s - 1) * one:
        return 0
    if 2 * p < -(2 * c * s + 1) * one:
        return full(a)
    kn = kernel(b)
    return to256(a, kn.h(p, s * one), 2 * s * one * kn.T)


def thresholds(lv, th, s):
    """MS-R2 B: for v = 1..full, P_v, the largest p with corner_p(p) >= v. A pixel's alpha is the count of v with
    p <= P_v. Proved here, not assumed: P is non-increasing, corner_p(P_v) >= v > corner_p(P_v + 1), and the ends
    are full and 0, so the count equals corner_p at every p."""
    a, c, one = ALPHA[th][lv][1], cut(lv, th, 1), 1 << FRAC
    fa = full(a)
    lo0, hi0 = -(c * s + 1) * one, (c * s + 1) * one
    assert corner_p(lv, th, s, lo0) == fa and corner_p(lv, th, s, hi0) == 0
    out = []
    for v in range(1, fa + 1):
        lo, hi = lo0, hi0
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if corner_p(lv, th, s, mid) >= v:
                lo = mid
            else:
                hi = mid
        out.append(lo)
    for v in range(1, fa + 1):
        p = out[v - 1]
        assert corner_p(lv, th, s, p) >= v > corner_p(lv, th, s, p + 1), "threshold %d" % v
        assert v == 1 or out[v - 2] >= p, "thresholds fall"
    return out


def count(thr, p):
    """The draw-time alpha: how many thresholds p lies within (kit/shadow.ci corner)."""
    lo, hi = 0, len(thr)              # thr[:lo] hold p, thr[hi:] do not
    while lo < hi:
        mid = (lo + hi) // 2
        if p <= thr[mid]:
            lo = mid + 1
        else:
            hi = mid
    return lo


def contact_alphas(lv, th):
    """A contact corner's alpha by its count of the 16 samples inside the arc, 0 to 16."""
    return [to256(ALPHA[th][lv][0], q, 16) for q in range(17)]


MAX_BOX = 1000   # a corner box at most this many device pixels a side keeps ((2n + 1)^2 * 2) << 40 within I64


def keys():
    """Profiles by (factor, level, theme, layer); thresholds by (factor, level, theme), ambient only."""
    return ([(s, lv, th, k) for s in SCALES for lv in range(3) for th in range(2) for k in range(2)],
            [(s, lv, th) for s in SCALES for lv in range(3) for th in range(2)])


def tables():
    """(profiles, thresholds) in keys() order."""
    for lv in range(3):
        assert LAYERS[lv][1][0] + cut(lv, 0, 1) == EXTENTS_DARK[lv], "section 3's extent of level %d" % (lv + 1)
    pk, tk = keys()
    prof = [profile(lv, th, k, s) for s, lv, th, k in pk]
    thr = [thresholds(lv, th, s) for s, lv, th in tk]
    for t in prof:
        assert all(0 <= v <= 256 for v in t)
        assert all(t[i] >= t[i + 1] for i in range(len(t) - 1)), "a profile falls outward"
    return prof, thr


def prove(radii):
    """--prove: the order's literal sweep, every corner pixel of every radius in radii at every factor, level and
    theme: the draw-time count (thresholds, contact samples) equals corner()'s exact quarter."""
    n_px = bad = 0
    one = 1 << FRAC
    for s in SCALES:
        for lv in range(3):
            for th in range(2):
                thr = thresholds(lv, th, s)
                ca = contact_alphas(lv, th)
                for r1 in radii:
                    for k in range(2):
                        exact = corner(r1, lv, th, k, s)
                        n = (r1 + cut(lv, th, k)) * s
                        r = r1 * s
                        for j in range(n):
                            for i in range(n):
                                if k == 0:
                                    q = sum(1 for x in range(4) for y in range(4)
                                            if (8 * i + 2 * x + 1) ** 2 + (8 * j + 2 * y + 1) ** 2 <= 64 * r * r)
                                    got = ca[q]
                                else:
                                    got = count(thr, dist2(i, j) - r * one)
                                n_px += 1
                                bad += got != exact[j * n + i]
    return n_px, bad


def words(name, ty, vals, per=24):
    out = ["%s[%d] %s = [" % (ty, len(vals), name)]
    for k in range(0, len(vals), per):
        out.append("    " + ", ".join("%d" % v for v in vals[k:k + per]) + ("," if k + per < len(vals) else "];"))
    return out


def emit():
    prof, thr = tables()
    po, data = [], []
    for t in prof:
        po.append(len(data))
        data += t
    assert len(data) < CHUNK
    to, tv = [], []
    for t in thr:
        to.append(len(tv))
        tv += t
    to.append(len(tv))
    lay = [v for lv in LAYERS for layer in lv for v in layer]
    cu = [cut(lv, th, k) for lv in range(3) for th in range(2) for k in range(2)]
    fu = [full(ALPHA[th][lv][k]) for lv in range(3) for th in range(2) for k in range(2)]
    ca = [v for lv in range(3) for th in range(2) for v in contact_alphas(lv, th)]
    ns, nl = len(SCALES), 3
    out = ["// user/ci/kit/shadow.ci: written by tools/shadow.py; do not edit. MS-3 and MS-3b (MS-R2 B): the shadow",
           "// tables of three levels, contact and ambient layers, both themes, at Size factors %s: each layer's" %
           ", ".join("%d" % s for s in SCALES),
           "// edge profile, and for the corners, any radius, thresholds counted at draw time. Each alpha is in 256ths",
           "// for kit/blend.ci's mix_px. user/ci/kit/shade.ci draws them (shade_row)."]
    out += words("lay", "I64", lay, 12)
    out += words("cu", "I64", cu, 12)
    out += words("fu", "I64", fu, 12)
    out += words("po", "I64", po, 12)
    out += words("pf", "U8", data)
    out += words("to", "I64", to, 12)
    out += words("tv", "I64", tv, 8)
    out += words("ca", "I64", ca, 17)
    out += ["",
            "// The index of Size factor s in the tables, or -1 when none is made.",
            "export I64 scale_index(I64 s) {",
            "    if (s >= %d && s <= %d) { return s - %d; }" % (SCALES[0], SCALES[-1], SCALES[0]),
            "    return -1;", "}", "",
            "// Whether a shape of corner radius rad (at 1x, at least 1) has corners at factor sc: tables for sc, and a",
            "// corner box ((rad + its widest cut) * sc) of at most %d px a side, which keeps a squared distance times" % MAX_BOX,
            "// 2^40 within I64.",
            "export Bool fits(I64 rad, I64 sc) {",
            "    return scale_index(sc) >= 0 && rad >= 1 && (rad + %d) * sc <= %d;" % (max(cu), MAX_BOX),
            "}", "",
            "// The same for a corner radius of r device pixels (MS-5: a plate's radius as it scales).",
            "export Bool fits_dev(I64 r, I64 sc) {",
            "    return scale_index(sc) >= 0 && r >= 1 && r + %d * sc <= %d;" % (max(cu), MAX_BOX),
            "}", "",
            "// Level lv's (1 to 3) layer k (0 contact, 1 ambient): its offset down and its blur b, at 1x.",
            "export I64 dy(I64 lv, I64 k) {",
            "    return lay[4 * (lv - 1) + 2 * k];",
            "}", "",
            "export I64 blur(I64 lv, I64 k) {",
            "    return lay[4 * (lv - 1) + 2 * k + 1];",
            "}", "",
            "// Level lv's layer k's cut in theme th at 1x: the table is 0 past it and full inside it (0 for a",
            "// contact layer). The ambient layer reaches dy + cut below the shape.",
            "export I64 cut(I64 lv, I64 th, I64 k) {",
            "    return cu[4 * (lv - 1) + 2 * th + k];",
            "}", "",
            "// Level lv's layer k's full alpha in theme th.",
            "export I64 full(I64 lv, I64 th, I64 k) {",
            "    return fu[4 * (lv - 1) + 2 * th + k];",
            "}", "",
            "// The edge profile of scale index si, level lv, theme th, layer k at d pixels outside the edge (d <= 0",
            "// inside): the full alpha inside -w, 0 past w, where w is the layer's cut times the factor.",
            "export I64 edge(I64 si, I64 lv, I64 th, I64 k, I64 w, I64 d) {",
            "    if (d > w) { return 0; }",
            "    I64 e = d;",
            "    if (e < 0 - w - 1) { e = 0 - w - 1; }",
            "    return pf[po[4 * (%d * si + lv - 1) + 2 * th + k] + e + w + 1] as I64;" % nl,
            "}", "",
            "// The corner quarter of scale index si for a radius of r device pixels, level lv, theme th, layer k at",
            "// column i and row j counted out from the arc's center, n on a side (r plus the cut times the factor); 0",
            "// outside. A contact corner counts cut_corners' 4 x 4 samples inside the arc; an ambient one takes p, the",
            "// pixel center's distance to the arc in 2^-%d px (isqrt of the exact squared distance), and counts the" % FRAC,
            "// thresholds p lies within (tools/shadow.py proves the count is the exact quarter's value).",
            "export I64 corner(I64 si, I64 r, I64 lv, I64 th, I64 k, I64 n, I64 i, I64 j) {",
            "    if (i < 0 || j < 0 || i >= n || j >= n) { return 0; }",
            "    if (k == 0) {",
            "        I64 q = 0;",
            "        for x in 0..4 {",
            "            for y in 0..4 {",
            "                I64 u = 8 * i + 2 * x + 1;",
            "                I64 v = 8 * j + 2 * y + 1;",
            "                if (u * u + v * v <= 64 * r * r) { q = q + 1; }",
            "            }",
            "        }",
            "        return ca[17 * (2 * (lv - 1) + th) + q];",
            "    }",
            "    I64 s = si + %d;" % SCALES[0],
            "    I64 c = cut(lv, th, 1);",
            "    I64 p = isqrt(((2 * i + 1) * (2 * i + 1) + (2 * j + 1) * (2 * j + 1)) << %d) - r * %d;" % (2 * FRAC - 2, 1 << FRAC),
            "    if (2 * p > (2 * c * s - 1) * %d) { return 0; }" % (1 << FRAC),
            "    if (2 * p < 0 - (2 * c * s + 1) * %d) { return full(lv, th, 1); }" % (1 << FRAC),
            "    I64 t = 2 * (%d * si + lv - 1) + th;" % nl,
            "    I64 lo = to[t];",
            "    I64 hi = to[t + 1];",
            "    I64 base = lo;",
            "    while (lo < hi) {",
            "        I64 mid = (lo + hi) / 2;",
            "        if (p <= tv[mid]) {",
            "            lo = mid + 1;",
            "        } else {",
            "            hi = mid;",
            "        }",
            "    }",
            "    return lo - base;",
            "}",
            "// SPDX-License-Identifier: Apache-2.0",
            ""]
    return "\n".join(out)


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        sys.exit(0 if os.path.exists(OUT) and open(OUT).read() == emit() else 1)
    if sys.argv[1:] == ["--sizes"]:
        prof, thr = tables()
        print("profiles %d entries, thresholds %d, contact alphas %d" % (sum(map(len, prof)), sum(map(len, thr)),
                                                                        6 * 17))
        sys.exit(0)
    if sys.argv[1:2] == ["--prove"]:
        radii = [int(v) for v in sys.argv[2:]] or PROVE_RADII
        n_px, bad = prove(radii)
        print("prove: radii %s at factors %s: %d corner pixels, %d differ" % (radii, SCALES, n_px, bad))
        sys.exit(1 if bad else 0)
    with open(OUT, "w") as f:
        f.write(emit())
