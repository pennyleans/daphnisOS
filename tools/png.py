"""tools/png.py: write an RGB image as a PNG with the standard library only (zlib), for proofs (FONT-1 F5)."""
import struct
import zlib


def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write(path, w, h, px):
    """px: a list of h rows, each a list of w 0xRRGGBB words."""
    raw = bytearray()
    for row in px:
        raw.append(0)
        for c in row:
            raw += bytes(((c >> 16) & 255, (c >> 8) & 255, c & 255))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)
