#!/usr/bin/env python3
"""tools/check-png.py OUTPUT: U-PNG's writers read by an independent reader (docs/specs/2026-11-11-u-png.md).

OUTPUT is what tests/png/png_twin.ci prints. Each `zlib` stream must inflate with the host's zlib, whole and with
nothing after it, to the bytes put in. Each `png` file must read with the strict reader below (signature, IHDR first,
IDAT, IEND last and empty, every CRC, 8-bit RGB or RGBA, no interlace, the five filters undone as the PNG
specification gives them) to the pixels put in; where Pillow is installed it must read them the same. Standard library
only, Pillow optional."""
import struct
import sys
import zlib


def inflate_whole(data):
    d = zlib.decompressobj()
    out = d.decompress(data) + d.flush()
    if not d.eof or d.unused_data:
        raise ValueError("the stream does not end where the data ends")
    return out


def unfilter(raw, w, h, bpp):
    rb = w * bpp
    if len(raw) != h * (rb + 1):
        raise ValueError(f"{len(raw)} inflated bytes, {h * (rb + 1)} wanted")
    out = bytearray(h * rb)
    for y in range(h):
        f = raw[y * (rb + 1)]
        line = raw[y * (rb + 1) + 1:(y + 1) * (rb + 1)]
        for i in range(rb):
            a = out[y * rb + i - bpp] if i >= bpp else 0
            b = out[(y - 1) * rb + i] if y > 0 else 0
            c = out[(y - 1) * rb + i - bpp] if y > 0 and i >= bpp else 0
            if f == 0:
                p = 0
            elif f == 1:
                p = a
            elif f == 2:
                p = b
            elif f == 3:
                p = (a + b) // 2
            elif f == 4:
                q = a + b - c
                pa, pb, pc = abs(q - a), abs(q - b), abs(q - c)
                p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            else:
                raise ValueError(f"row {y}: filter {f}")
            out[y * rb + i] = (line[i] + p) & 255
    return bytes(out)


def read_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("signature")
    at, chunks = 8, []
    while at < len(data):
        if at + 12 > len(data):
            raise ValueError("a chunk runs past the end")
        n, kind = struct.unpack(">I4s", data[at:at + 8])
        body = data[at + 8:at + 8 + n]
        (want,) = struct.unpack(">I", data[at + 8 + n:at + 12 + n])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != want:
            raise ValueError(f"{kind!r}: CRC")
        chunks.append((kind, body))
        at += 12 + n
    kinds = [k for k, _ in chunks]
    if kinds[0] != b"IHDR" or kinds[-1] != b"IEND" or chunks[-1][1] or set(kinds[1:-1]) != {b"IDAT"}:
        raise ValueError(f"chunk order {kinds}")
    if len(chunks[0][1]) != 13:
        raise ValueError("IHDR length")
    w, h, depth, ct, comp, filt, lace = struct.unpack(">IIBBBBB", chunks[0][1])
    if depth != 8 or ct not in (2, 6) or comp or filt or lace or w == 0 or h == 0:
        raise ValueError(f"IHDR {w} {h} {depth} {ct} {comp} {filt} {lace}")
    bpp = 3 if ct == 2 else 4
    return w, h, bpp, unfilter(inflate_whole(b"".join(b for _, b in chunks[1:-1])), w, h, bpp)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        from PIL import Image
        import io
    except ImportError:
        Image = None
    lines = open(sys.argv[1]).read().split("\n")
    bad, n_z, n_p, n_pil = 0, 0, 0, 0
    i = 0
    while i < len(lines):
        head = lines[i].split()
        if not head:
            i += 1
            continue
        if head[0] == "zlib":
            name, n = head[1], int(head[2])
            src = bytes.fromhex(lines[i + 1].split(" ", 1)[1] if n else "")
            out = bytes.fromhex(lines[i + 2].split(" ", 1)[1])
            try:
                if len(src) != n or out[:2] != b"\x78\x9c" or inflate_whole(out) != src:
                    raise ValueError("inflates to other bytes")
                print(f"ok    zlib {name}: {n} bytes in, {len(out)} out")
            except (ValueError, zlib.error) as e:
                print(f"FAIL  zlib {name}: {e}")
                bad += 1
            n_z += 1
            i += 3
        elif head[0] == "png":
            name, w, h, ch = head[1], int(head[2]), int(head[3]), int(head[4])
            px = bytes.fromhex(lines[i + 1].split(" ", 1)[1])
            data = bytes.fromhex(lines[i + 2].split(" ", 1)[1])
            try:
                gw, gh, gch, got = read_png(data)
                if (gw, gh, gch) != (w, h, ch) or got != px:
                    raise ValueError("reads to other pixels")
                said = ""
                if Image is not None:
                    im = Image.open(io.BytesIO(data))
                    im.load()
                    if im.size != (w, h) or im.mode != ("RGB" if ch == 3 else "RGBA") or im.tobytes() != px:
                        raise ValueError("Pillow reads other pixels")
                    said = ", Pillow agrees"
                    n_pil += 1
                print(f"ok    png {name}: {w} x {h} x {ch}, {len(data)} bytes{said}")
            except (ValueError, zlib.error) as e:
                print(f"FAIL  png {name}: {e}")
                bad += 1
            n_p += 1
            i += 3
        else:
            print(f"FAIL  line {i + 1}: {lines[i][:40]!r}")
            bad += 1
            i += 1
    if n_z == 0 or n_p == 0:
        print("FAIL  no cases")
        bad += 1
    pil = f", {n_pil} by Pillow" if Image is not None else ", Pillow not installed"
    print(f"{n_z} zlib streams and {n_p} PNG files read back by the host's zlib and a strict reader{pil}; {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
