"""faultrec.py: a decoder for the cint-core-1/fault/v2 record (SPEC-01 IM-149), shared by
compare-fault.py and check-trap.py. Scalar tags I8 to U64 and Z only."""
import struct


def decode(b):
    pos = 0

    def take(n):
        nonlocal pos
        if pos + n > len(b):
            raise ValueError("truncated record")
        v = b[pos:pos + n]
        pos += n
        return v

    def u32():
        return struct.unpack("<I", take(4))[0]

    def tvalue():
        tag = take(1)[0]
        if tag == 0x0F:
            n = u32()
            return (tag, bytes(take(n)))
        width = {1: 1, 2: 2, 3: 4, 4: 8}[tag & 0x0F]
        return (tag, bytes(take(width)))

    def position():
        n = u32()
        path = bytes(take(n)).decode()
        line = u32()
        col = u32()
        return (path, line, col)

    r = {}
    r["domain"] = bytes(take(u32())).decode()
    r["code"] = struct.unpack("<H", take(2))[0]
    r["operation"] = bytes(take(u32())).decode()
    r["operands"] = [tvalue() for _ in range(u32())]
    r["exact"] = tvalue() if take(1)[0] else None
    r["limit"] = tvalue() if take(1)[0] else None
    r["position"] = position()
    r["revision"] = bytes(take(32)) if take(1)[0] else None
    r["srcmap"] = bytes(take(32)) if take(1)[0] else None
    r["address_present"] = take(1)[0]
    r["stack"] = [position() for _ in range(u32())]
    if pos != len(b):
        raise ValueError("%d trailing bytes" % (len(b) - pos))
    return r
