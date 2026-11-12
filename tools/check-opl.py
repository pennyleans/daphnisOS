#!/usr/bin/env python3
"""tools/check-opl.py: gate 7 of stage AU (docs/specs/2026-11-06-au-audio.md section 6), the OPL3 against ymfm.

  check-opl.py lines RAW [PARTS]       the lines opltest prints, made from ymfm's samples (RAW, written by
                                       tools/oplref's `oplref tools/oplref/walk.txt RAW`) for the first PARTS parts
                                       of the walk (all of them by default); the 48 kHz stream is resampled here,
                                       by the rule of user/ci/opl/rate.ci, from the same samples
  check-opl.py compare WANT GOT        PASS when every `opl:` line of GOT is the line of WANT, in order, and
                                       nothing is missing; else the first difference and the part it falls in
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WALK = os.path.join(HERE, "oplref", "walk.txt")
NUM = 14318180    # the chip's clock
DEN = 13824000    # 288 x 48,000


def parts_of_walk():
    """[(part, samples)] in order."""
    out = []
    for line in open(WALK):
        if line.startswith("p "):
            out.append([int(line.split()[1]), 0])
        elif line.startswith("s "):
            out[-1][1] += int(line.split()[1])
    return out


def lines(raw, parts):
    data = open(raw, "rb").read()
    walk = parts_of_walk()
    if parts is None:
        parts = len(walk)
    out = []
    at = 0
    for k, n in walk[:parts]:
        chunk = data[at:at + 8 * n]
        if len(chunk) != 8 * n:
            raise SystemExit("check-opl: %s ends inside part %d" % (raw, k))
        out.append("opl: part %d samples %d sha256 %s" % (k, n, hashlib.sha256(chunk).hexdigest()))
        at += 8 * n
    chip = data[:at]
    samples = at // 8
    out.append("opl: chip samples %d sha256 %s" % (samples, hashlib.sha256(chip).hexdigest()))
    v = struct.unpack("<%dh" % (4 * samples), chip)
    frames = bytearray()
    k = 0
    while True:
        base, frac = divmod(k * NUM, DEN)
        if base + 1 > samples - 1:
            break
        for c in (0, 1):
            a = v[4 * base + c]
            b = v[4 * (base + 1) + c]
            frames += struct.pack("<h", a + (b - a) * frac // DEN)
        k += 1
    out.append("opl: 48000 frames %d sha256 %s" % (k, hashlib.sha256(bytes(frames)).hexdigest()))
    return out


def compare(want_path, got_path):
    want = [l.rstrip("\n") for l in open(want_path) if l.startswith("opl: ")]
    got = [l.rstrip("\n") for l in open(got_path) if l.startswith("opl: ")]
    for i, w in enumerate(want):
        g = got[i] if i < len(got) else "(missing)"
        if g != w:
            print("FAIL  line %d: want %s" % (i + 1, w))
            print("                got  %s" % g)
            return 1
    if len(got) != len(want):
        print("FAIL  %d lines, want %d" % (len(got), len(want)))
        return 1
    print("PASS  %d lines equal" % len(want))
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "lines":
        for l in lines(argv[1], int(argv[2]) if len(argv) > 2 else None):
            print(l)
        return 0
    if len(argv) == 3 and argv[0] == "compare":
        return compare(argv[1], argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
