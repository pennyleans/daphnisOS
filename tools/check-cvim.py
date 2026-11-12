#!/usr/bin/env python3
"""tools/check-cvim.py: the files of cvim's buffer gate (docs/specs/2026-11-07-cv-cvim.md gate 3, CV-1).

  check-cvim.py make DIR        big.txt: 64 MiB exactly, about 987,000 lines of a fixed generator, ending in a
                                newline; want.txt: big.txt with the 1,000 bytes cvbuf types (a to z in turn) at the
                                start of line lines // 2 (from 0); over.txt: one byte past 64 MiB.
  check-cvim.py read LOG        cvbuf's `name value` lines; prints them, exit 1 unless every key took under 16 ms.
"""
import random
import sys

SIZE = 67108864
KEY_NS = 16000000


def make(d):
    r = random.Random(1)
    out = bytearray()
    i = 0
    while len(out) < SIZE:
        w = r.randint(20, 116)
        out += (f"{i:07d} " + "".join(chr(97 + (i * 7 + j) % 26) for j in range(w - 9))).encode() + b"\n"
        i += 1
    out = out[:SIZE - 1] + b"\n"
    lines = out.count(b"\n") + 1
    at = -1
    for _ in range(lines // 2):
        at = out.index(b"\n", at + 1)
    pos = at + 1
    typed = bytes(97 + k % 26 for k in range(1000))
    open(f"{d}/big.txt", "wb").write(out)
    open(f"{d}/want.txt", "wb").write(out[:pos] + typed + out[pos:])
    open(f"{d}/over.txt", "wb").write(b"a" * (SIZE + 1))
    print(f"big.txt {len(out)} bytes, {lines - 1} line feeds; typed at {pos}")


def read(log):
    v = dict(line.split() for line in open(log) if line.strip())
    for k, n in v.items():
        print(f"{k} {n}")
    return 0 if int(v["key_worst_ns"]) < KEY_NS and int(v["bytes"]) == SIZE else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "make":
        make(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "read":
        sys.exit(read(sys.argv[2]))
    else:
        sys.exit(__doc__)
