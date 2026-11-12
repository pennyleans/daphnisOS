#!/usr/bin/env python3
"""tools/check-fb.py W H [TRANSCRIPT]: the surface digest of F-1 (docs/specs/2026-11-05-f-surface.md
section 3): SHA-256 over the W * H pixels mfb draws, row by row, 4 little-endian bytes a pixel (XRGB8888:
red x * 255 / (W - 1), green y * 255 / (H - 1), blue (x ^ y) & 255), never the padding past 4 * W.
Without a transcript, prints the digest. With one, every `daphnis: surface WxH stride S sha256 HEX`
line before the doom run (whose surface freedoom-ci tools/check-doom.py checks) must carry it: one PASS or FAIL line
each, FAIL with none; exits 1 on any FAIL."""
import hashlib
import re
import sys


def digest(w, h):
    rows = bytearray(4 * w * h)
    at = 0
    for y in range(h):
        g = y * 255 // (h - 1)
        for x in range(w):
            rows[at] = (x ^ y) & 255
            rows[at + 1] = g
            rows[at + 2] = x * 255 // (w - 1)
            at += 4
    return hashlib.sha256(rows).hexdigest()


def main(argv):
    w, h = int(argv[0]), int(argv[1])
    want = digest(w, h)
    if len(argv) < 3:
        print(want)
        return 0
    with open(argv[2], "rb") as f:
        data = f.read().split(b"daphnis: run doom ")[0]
    lines = re.findall(rb"^daphnis: surface (\d+)x(\d+) stride (\d+) sha256 ([0-9a-f]{64})$", data, re.M)
    fails = 0
    for tw, th, stride, got in lines:
        ok = (int(tw), int(th)) == (w, h) and got.decode() == want and int(stride) >= 4 * w
        print("%s  surface %sx%s stride %s %s" % ("PASS" if ok else "FAIL", tw.decode(), th.decode(), stride.decode(),
                                              "equals the pattern's digest" if ok else "differs: want " + want))
        fails += not ok
    if not lines:
        print("FAIL  surface: no surface line in %s" % argv[2])
        fails += 1
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
