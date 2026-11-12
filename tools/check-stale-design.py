#!/usr/bin/env python3
"""tools/check-stale-design.py [--image FILE ...]: no retired desk design ships (l 2026-11-11 00:00Z).

The Super plane of frame 1 (DN-49) replaced the old hdesk panel ("THE MACHINE", the "Super+P pin" hint rows, the
"New Terminal" footer). Board stick 7 still carried the old panel: the hdesk binary committed then lagged its source.
This check fails on any of the retired strings:

- with no argument, in the shipped sources (src/, rt/, user/), run by check.sh, hosted;
- with --image, in the bytes of each file named (a stick image, a volume, an hdesk binary), run by every board or
  release image build before the image leaves the build machine.

DN-46 (show, don't tell) adds the explanatory hints design retired (2026-11-12 10:15Z); "for good" is checked in
image bytes only, since comments in the shipped sources use the words.

Tests may name a retired string to prove it is gone; docs may quote it. Neither ships.
"""
import os
import sys

RETIRED = [
    b"THE MACHINE",
    b"Capability Grants & Calendar",
    b"Tab preview  Super+P pin",
    b"programs & paths . Super+P pins)",
    b"New Terminal",
    # DN-46 (show, don't tell): the hints design retired; design 2026-11-12 10:15Z, RG-1
    b"Consoles stay dark in both.",
    b"Scales text and controls together.",
    b"Windows and icons ease into place.",
    b"Picks which sizes are listed.",
    b"Changes apply at once.",
    b"Set by the machine.",
    b"This cannot be undone.",
]
# In built programs only: comments in the shipped sources use these words (rt/task.c, trash.ci, cish/run.ci).
RETIRED_BYTES = [
    b"for good",
]
SHIPPED = ("src", "rt", "user")


def hits(data, image=False):
    return [s.decode() for s in RETIRED + (RETIRED_BYTES if image else []) if s in data]


def scan_tree(root):
    bad = []
    for top in SHIPPED:
        for d, _, names in os.walk(os.path.join(root, top)):
            for n in sorted(names):
                f = os.path.join(d, n)
                with open(f, "rb") as fh:
                    for s in hits(fh.read()):
                        bad.append("%s: %r" % (os.path.relpath(f, root), s))
    return bad


def scan_images(paths):
    bad = []
    for p in paths:
        found = set()
        tail = b""
        with open(p, "rb") as fh:
            while True:
                block = fh.read(1 << 22)
                if not block:
                    break
                found.update(hits(tail + block, image=True))
                tail = block[-64:]
        bad += ["%s: %r" % (p, s) for s in sorted(found)]
    return bad


def main(argv):
    if argv[:1] == ["--image"]:
        if len(argv) < 2:
            print("usage: tools/check-stale-design.py [--image FILE ...]")
            return 2
        bad = scan_images(argv[1:])
        what = "%d image file(s)" % (len(argv) - 1)
    else:
        bad = scan_tree(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        what = "src/, rt/, user/"
    for b in bad:
        print("retired desk design: " + b)
    if bad:
        print("FAIL: %d retired string(s) in %s" % (len(bad), what))
        return 1
    print("no retired desk design in %s" % what)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
