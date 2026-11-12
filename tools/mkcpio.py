#!/usr/bin/env python3
"""tools/mkcpio.py OUT NAME=FILE... DIR/...: a cpio "newc" archive, the format of a Linux initramfs.

Deterministic: members in the order given, inode numbers 1, 2, ... per distinct FILE and per
directory, mode 0100755 (a file) or 040755 (a directory), owner 0, mtime 0, no device numbers,
check 0, so the same inputs give the same bytes on any host. A NAME may be a path (`etc/motd`);
an argument ending in "/" is a directory member under that path, without the "/", and must come
before what it holds (P-0). `DIR/@MODE` is a directory member with the octal bits MODE (FS-2: `tmp/@1777`, the
sticky, world-writable /tmp of an image with accounts). One FILE under several NAMEs is one inode with that many links, its
bytes held by the last member only, as Linux writes hard links (U1-2: one musl binary under eight
names)."""
import sys


def member(ino, name, data, mode, nlink):
    n = name.encode() + b"\0"
    fields = [ino, mode, 0, 0, nlink, 0, len(data), 0, 0, 0, 0, len(n), 0]
    head = b"070701" + b"".join(b"%08X" % f for f in fields) + n
    head += b"\0" * (-len(head) % 4)
    return head + data + b"\0" * (-len(data) % 4)


def main(argv):
    if len(argv) < 2:
        sys.exit("usage: mkcpio.py OUT NAME=FILE... DIR/...")
    dmode = {}
    args = []
    for arg in argv[1:]:
        if "=" not in arg and "/@" in arg:
            d, _, m = arg.partition("/@")
            dmode[d + "/"] = int(m, 8)
            arg = d + "/"
        args.append(arg)
    pairs = [("", "", arg) if arg.endswith("/") and "=" not in arg else arg.partition("=") for arg in args]
    keys = []   # one per inode: a FILE, or a directory argument
    for _, _, key in pairs:
        if key not in keys:
            keys.append(key)
    last = {key: max(i for i, (_, _, k) in enumerate(pairs) if k == key) for key in keys}
    links = {key: sum(1 for _, _, k in pairs if k == key) for key in keys}
    out = b""
    for i, (name, _, key) in enumerate(pairs):
        ino = keys.index(key) + 1
        if key.endswith("/") and not name:
            out += member(ino, key.rstrip("/"), b"", 0o040000 | dmode.get(key, 0o755), 2)
            continue
        with open(key, "rb") as f:
            data = f.read() if last[key] == i else b""
        out += member(ino, name, data, 0o100755, links[key])
    out += member(len(keys) + 1, "TRAILER!!!", b"", 0, 1)
    with open(argv[0], "wb") as f:
        f.write(out)


if __name__ == "__main__":
    main(sys.argv[1:])
