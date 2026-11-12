#!/usr/bin/env python3
"""tests/bg/bgread_run.py BGREAD: user/ci/bgread.ci built for the host (BG-1), run on pictures made here.

Checks: a PNG wider than the screen is cropped at its center, one taller covers it, an RGBA PNG drops its alpha, the
stream is exactly the header (u32 W, u32 H) and W x H little-endian 0x00RRGGBB words with status 0; a link to the
picture, a FIFO (no wait: O_NONBLOCK), a directory, a file that is not PNG and an empty file give status 1 and no
byte; another number of words, a width past 3840, a height of 0 and a relative path give status 2. One line a check
that fails, then "bgread: N checks, F failed"; exit status 1 if any failed.
"""
import os
import struct
import subprocess
import sys
import tempfile
import zlib

checks = 0
failed = 0


def check(ok, what):
    global checks, failed
    checks += 1
    if not ok:
        failed += 1
        print("FAIL", what)


def png(w, h, px, alpha=False):
    """A PNG of w x h from px, a list of rows of (r, g, b[, a]) tuples, filter 0."""
    ch = 4 if alpha else 3
    raw = b"".join(b"\x00" + b"".join(bytes(p[:ch]) for p in row) for row in px)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    hdr = struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", hdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def run(prog, *args):
    try:
        p = subprocess.run([prog, *args], capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return -1, b""
    return p.returncode, p.stdout


def word(r, g, b):
    return struct.pack("<I", (r << 16) | (g << 8) | b)


def main():
    prog = sys.argv[1]
    d = tempfile.mkdtemp()
    wide = os.path.join(d, "wide.png")         # 4 x 2: columns red, green, blue, white
    cols = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    with open(wide, "wb") as f:
        f.write(png(4, 2, [cols, cols]))
    st, out = run(prog, wide, "2", "2")        # cover 2 x 2: the middle two columns, green and blue
    want = struct.pack("<II", 2, 2) + (word(0, 255, 0) + word(0, 0, 255)) * 2
    check(st == 0 and out == want, "a wide picture is cropped at its center")
    tall = os.path.join(d, "tall.png")         # 1 x 3: rows red, green, blue; cover 3 x 1: the middle row
    with open(tall, "wb") as f:
        f.write(png(1, 3, [[(255, 0, 0)], [(0, 255, 0)], [(0, 0, 255)]]))
    st, out = run(prog, tall, "3", "1")
    check(st == 0 and out == struct.pack("<II", 3, 1) + word(0, 255, 0) * 3, "a tall picture covers, its middle row")
    rgba = os.path.join(d, "rgba.png")
    with open(rgba, "wb") as f:
        f.write(png(1, 1, [[(10, 20, 30, 0)]], alpha=True))
    st, out = run(prog, rgba, "2", "1")
    check(st == 0 and out == struct.pack("<II", 2, 1) + word(10, 20, 30) * 2, "alpha is dropped")
    st, out = run(prog, wide, "1920", "1080")
    check(st == 0 and len(out) == 8 + 1920 * 1080 * 4, "the stream is exactly the header and the pixels")
    link = os.path.join(d, "link.png")
    os.symlink(wide, link)
    st, out = run(prog, link, "2", "2")
    check(st == 1 and out == b"", "a link is refused, nothing written")
    fifo = os.path.join(d, "fifo.png")
    os.mkfifo(fifo)
    st, out = run(prog, fifo, "2", "2")
    check(st == 1 and out == b"", "a FIFO is refused without waiting")
    st, out = run(prog, d, "2", "2")
    check(st == 1 and out == b"", "a directory is refused")
    text = os.path.join(d, "text.png")
    with open(text, "wb") as f:
        f.write(b"not a picture at all\n")
    st, out = run(prog, text, "2", "2")
    check(st == 1 and out == b"", "a file that is not PNG is refused")
    empty = os.path.join(d, "empty.png")
    open(empty, "wb").close()
    st, out = run(prog, empty, "2", "2")
    check(st == 1 and out == b"", "an empty file is refused")
    st, out = run(prog, wide, "2")
    check(st == 2 and out == b"", "two words: usage")
    st, out = run(prog, wide, "3841", "2")
    check(st == 2 and out == b"", "a width past 3840: usage")
    st, out = run(prog, wide, "2", "3841")
    check(st == 2 and out == b"", "a side past 3840: usage")
    st, out = run(prog, wide, "3840", "2161")
    check(st == 2 and out == b"", "an area past 3840 x 2160: usage")
    st, out = run(prog, wide, "2", "0")
    check(st == 2 and out == b"", "a height of 0: usage")
    st, out = run(prog, "wide.png", "2", "2")
    check(st == 2 and out == b"", "a relative path: usage")
    print("bgread: %d checks, %d failed" % (checks, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
