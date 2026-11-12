#!/usr/bin/env python3
"""tools/proofpng.py OUT.png [IN]: a proof run (`frame W H`, then a row a line as `r RGB COUNT ...`, the shape
tests/am/about_proof.ci and tests/rs/*_proof.ci print) as a PNG. Standard library only. Reads standard input when IN
is left out."""
import struct
import sys
import zlib


def png(path, w, h, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    src = open(sys.argv[2]) if len(sys.argv) > 2 else sys.stdin
    w = h = None
    rows = []
    for line in src:
        p = line.split()
        if not p:
            continue
        if p[0] == "frame":
            w, h = int(p[1]), int(p[2])
        elif p[0] == "r":
            out = bytearray()
            for k in range(1, len(p), 2):
                c = int(p[k], 16)
                out += bytes(((c >> 16) & 255, (c >> 8) & 255, c & 255)) * int(p[k + 1])
            if len(out) != 3 * w:
                raise SystemExit("proofpng.py: row %d is %d pixels, not %d" % (len(rows), len(out) // 3, w))
            rows.append(bytes(out))
    if w is None or len(rows) != h:
        raise SystemExit("proofpng.py: %s rows of %s" % (len(rows), h))
    png(sys.argv[1], w, h, rows)


if __name__ == "__main__":
    main()
