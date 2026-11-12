#!/usr/bin/env python3
"""tools/index_proof.py OUTPUT DIR: the frames of tests/ff/index_proof.ci (kit/indexui.ci and kit/indexbody.ci, DN-55)
as PNGs in DIR: NAME.png at 1x, and NAME-2x.png as the desk shows Index at UI scale 2, each pixel doubled (FD-2X A:
Index draws at 1x and the desk places its surface at scale 2)."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def frames(path):
    out, name, w, h, rows = [], None, 0, 0, None
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "name":
                name = p[1]
            elif p[0] == "frame":
                w, h, rows = int(p[1]), int(p[2]), []
            elif p[0] == "r":
                r = []
                for i in range(1, len(p), 2):
                    r += [int(p[i], 16)] * int(p[i + 1])
                if len(r) != w:
                    raise SystemExit("index_proof.py: %s: a row of %d, not %d" % (name, len(r), w))
                rows.append(r)
                if len(rows) == h:
                    out.append((name, w, h, rows))
    return out


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: tools/index_proof.py OUTPUT DIR")
    png = load("png", "png.py")
    os.makedirs(argv[1], exist_ok=True)
    for name, w, h, rows in frames(argv[0]):
        png.write(os.path.join(argv[1], name + ".png"), w, h, rows)
        two = []
        for r in rows:
            d = [p for p in r for _ in (0, 1)]
            two += [d, d]
        png.write(os.path.join(argv[1], name + "-2x.png"), 2 * w, 2 * h, two)
        print("wrote %s.png, %dx%d, and %s-2x.png" % (name, w, h, name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
