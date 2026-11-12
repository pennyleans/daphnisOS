#!/usr/bin/env python3
"""tools/acscreen_proof.py OUTPUT DIR: the frames of tests/ac/screens_proof.ci (kit/acscreen.ci, frame 12) as PNGs in
DIR, each under the bar of login, lock and first boot (DN-41 (a): the roundel and the clock, nothing else), the bar
drawn by tools/check-hdesk.py's twin of hdesk's bar, so each image is the whole screen at 1024 x 768 at its scale."""
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
                    raise SystemExit("acscreen_proof.py: %s: a row of %d, not %d" % (name, len(r), w))
                rows.append(r)
                if len(rows) == h:
                    out.append((name, w, h, rows))
    return out


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: tools/acscreen_proof.py OUTPUT DIR")
    hd = load("hd", "check-hdesk.py")
    png = load("png", "png.py")
    os.makedirs(argv[1], exist_ok=True)
    hd.use_theme(0)
    for name, w, h, rows in frames(argv[0]):
        s = w // 1024
        bar = []
        for yd in range(28 * s):
            z = hd.dn_tz(s)
            r1 = [hd.T["BAR"]] * (1024 * z)
            hd.bar_1x(r1, yd // s, 1024, 1, {1}, {}, b"", b"", 0, 0, b"01:59", False, z=z, dy=yd // (s // z),
                      bare=True)
            line = hd.spread_by(r1, s // z)[:w]
            if 4 * s <= yd < 24 * s:
                line[9 * s:29 * s] = hd.roundel(s, hd.T["BAR"])[yd - 4 * s]
            bar.append(line)
        png.write(os.path.join(argv[1], name + ".png"), w, h + 28 * s, bar + rows)
        print("wrote %s.png, %dx%d" % (name, w, h + 28 * s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
