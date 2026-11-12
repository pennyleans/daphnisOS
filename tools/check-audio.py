#!/usr/bin/env python3
"""tools/check-audio.py: gates 1, 2 and 5 of stage AU (docs/specs/2026-11-06-au-audio.md section 6).

A chain is the kernel's digest of a byte stream (src/dsp.ci): H = 32 zero bytes, H = SHA-256(H | block) for each
whole 1,024-byte block, and the chain is SHA-256(H | the rest), the rest possibly empty.

  check-audio.py signal PCM            PASS when PCM is atone's signal: frame i is left 1 + (i * 7919 mod 32767),
                                       right its negative, 16-bit little-endian
  check-audio.py stream PCM            the line the kernel prints when a stream of PCM's bytes closes:
                                       `audio: stream 0 frames K chain W`
  check-audio.py wav WAV TRANSCRIPT    PASS when the WAV is 48,000 Hz, 2 channels, 16-bit PCM and its data, read
                                       to the end of the file with every all-zero frame removed, is the bytes of
                                       the transcript's `audio: mix nonzero M chain Z` lines, in order: M frames
                                       each, chain Z each, nothing left over
"""
import hashlib
import re
import struct
import sys


def chain(b):
    h = bytes(32)
    i = 0
    while len(b) - i >= 1024:
        h = hashlib.sha256(h + b[i:i + 1024]).digest()
        i += 1024
    return hashlib.sha256(h + b[i:]).hexdigest()


def signal(path):
    b = open(path, "rb").read()
    if len(b) % 4:
        return "FAIL  %s: %d bytes, not whole frames" % (path, len(b))
    for i in range(len(b) // 4):
        left = 1 + (i * 7919) % 32767
        if b[4 * i:4 * i + 4] != struct.pack("<hh", left, -left):
            return "FAIL  %s: frame %d is not atone's" % (path, i)
    return "PASS  %s: %d frames of atone's signal, none silent" % (path, len(b) // 4)


def stream(path):
    b = open(path, "rb").read()
    return "audio: stream 0 frames %d chain %s" % (len(b) // 4, chain(b))


def wav(path, transcript):
    w = open(path, "rb").read()
    if w[0:4] != b"RIFF" or w[8:12] != b"WAVE":
        return "FAIL  %s: not a WAV file" % path
    fmt = data = None
    i = 12
    while i + 8 <= len(w):
        cid = w[i:i + 4]
        n = struct.unpack("<I", w[i + 4:i + 8])[0]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", w[i + 8:i + 24])
        if cid == b"data":
            data = w[i + 8:]   # to the end: the header's size may be 0 when QEMU ends without the backend's close
            break
        i += 8 + n
    if fmt != (1, 2, 48000, 192000, 4, 16) or data is None:
        return "FAIL  %s: format %s, not 48,000 Hz 2-channel 16-bit PCM with data" % (path, fmt)
    data = data[:len(data) - len(data) % 4]
    nz = b"".join(data[k:k + 4] for k in range(0, len(data), 4) if data[k:k + 4] != b"\0\0\0\0")
    want = [(int(m), z) for m, z in re.findall(r"^audio: mix nonzero (\d+) chain ([0-9a-f]{64})$",
                                                open(transcript).read(), re.M)]
    if not want:
        return "FAIL  %s: no `audio: mix nonzero` line" % transcript
    at = 0
    for k, (m, z) in enumerate(want):
        seg = nz[at:at + 4 * m]
        if len(seg) != 4 * m or chain(seg) != z:
            return "FAIL  %s: segment %d of %d frames is not the kernel's mix (chain %s)" % (path, k, m, chain(seg))
        at += 4 * m
    if at != len(nz):
        return "FAIL  %s: %d nonzero frames after the kernel's %d" % (path, (len(nz) - at) // 4, at // 4)
    return "PASS  %s: %d nonzero frames, the kernel's %d mix segments byte for byte" % (path, at // 4, len(want))


def main(a):
    if len(a) == 2 and a[0] == "signal":
        out = signal(a[1])
    elif len(a) == 2 and a[0] == "stream":
        out = stream(a[1])
    elif len(a) == 3 and a[0] == "wav":
        out = wav(a[1], a[2])
    else:
        sys.exit(__doc__)
    print(out)
    return 1 if out.startswith("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
