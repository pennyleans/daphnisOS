#!/usr/bin/env python3
"""tests/shot/shot_run.py SHOT: RS-SHOT's writer, user/ci/shot.ci built for the host, run as the desk's child runs it
(no arguments, no environment, in a home) on shots made here. Each picture it writes is read back by
tools/check-png.py's strict reader and must equal the pixels sent; the name is the header's date, never the program's
clock; every refusal must leave no file; a taken name or a planted link is never written over or through, and a
second, a tenth or a hundredth shot of one second each takes the next free number. Standard library only."""
import importlib.util
import os
import re
import stat
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("check_png", os.path.join(ROOT, "tools", "check-png.py"))
check_png = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_png)

NAME = re.compile(r"^Screenshot \d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}( [1-9]\d{0,3})?\.png$")
T0 = 1794441600 + 3 * 3600 + 25 * 60 + 9    # 2026-11-12 03.25.09 UTC: the bar's date the desk sends


def shot_bytes(w, h, stride=None, seed=0, t=T0):
    rows = bytearray()
    for y in range(h):
        for x in range(w):
            rows += bytes(((x * 7 + seed) & 255, (y * 3) & 255, (x ^ y ^ seed) & 255, 0x5A))
    return struct.pack("<IIIQ", w, h, 4 * w if stride is None else stride, t) + rows


def rgb_of(shot):
    w, h = struct.unpack("<II", shot[:8])
    px = shot[20:]
    out = bytearray()
    for i in range(w * h):
        b, g, r = px[4 * i], px[4 * i + 1], px[4 * i + 2]
        out += bytes((r, g, b))
    return w, h, bytes(out)


def run(binary, home, data):
    p = subprocess.run([binary], input=data, cwd=home, env={}, capture_output=True, timeout=120)
    return p.returncode, p.stdout.decode("ascii", "replace"), p.stderr.decode("ascii", "replace")


def pictures(home):
    d = os.path.join(home, "Pictures")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def stamp(t):
    return time.strftime("Screenshot %Y-%m-%d %H.%M.%S", time.gmtime(t))


def main():
    binary = os.path.abspath(sys.argv[1])
    fails = []
    n = 0

    def check(ok, what):
        nonlocal n
        n += 1
        if not ok:
            fails.append(what)

    with tempfile.TemporaryDirectory() as home:
        # a picture: Pictures made 0700, one new file at 0644, its name the only line, its pixels the shot's
        data = shot_bytes(300, 200, seed=11)
        rc, out, err = run(binary, home, data)
        name = out[:-1] if out.endswith("\n") else ""
        check(rc == 0 and out.count("\n") == 1 and NAME.match(name), f"a 300 x 200 shot: rc {rc}, {out!r} {err!r}")
        check(name == "Screenshot 2026-11-12 03.25.09.png", f"the name is not the header's date: {name!r}")
        check(stat.S_IMODE(os.stat(os.path.join(home, "Pictures")).st_mode) == 0o700, "Pictures is not 0700")
        f = os.path.join(home, "Pictures", name)
        check(os.path.isfile(f) and stat.S_IMODE(os.stat(f).st_mode) == 0o644, "the file is not a 0644 file")
        w, h, bpp, px = check_png.read_png(open(f, "rb").read())
        check((w, h, bpp, px) == (300, 200, 3) + (rgb_of(data)[2],), "the picture read back is not the shot")
        # 1 x 1 and a wide one, each a second on
        for (sw, sh, t) in ((1, 1, T0 + 1), (1920, 3, T0 + 2)):
            data = shot_bytes(sw, sh, seed=sw, t=t)
            before = set(pictures(home))
            rc, out, err = run(binary, home, data)
            new = sorted(set(pictures(home)) - before)
            ok = rc == 0 and len(new) == 1 and out == new[0] + "\n" and new[0] == stamp(t) + ".png"
            if ok:
                w, h, bpp, px = check_png.read_png(open(os.path.join(home, "Pictures", new[0]), "rb").read())
                ok = (w, h, px) == rgb_of(data)
            check(ok, f"a {sw} x {sh} shot: rc {rc}, {out!r} {err!r}")

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as away:
        # the header's name taken, a link to a file elsewhere: shot takes " 2", writes nothing through the link and
        # leaves it where it was
        os.mkdir(os.path.join(home, "Pictures"), 0o700)
        target = os.path.join(away, "kept")
        open(target, "wb").write(b"kept")
        os.symlink(target, os.path.join(home, "Pictures", stamp(T0) + ".png"))
        rc, out, err = run(binary, home, shot_bytes(4, 4))
        check(rc == 0 and out == stamp(T0) + " 2.png\n", f"a taken name: rc {rc}, {out!r} {err!r}")
        check(open(target, "rb").read() == b"kept", "a planted link was written through")
        links = [x for x in pictures(home) if os.path.islink(os.path.join(home, "Pictures", x))]
        check(len(links) == 1, "a planted link was moved or replaced")

    with tempfile.TemporaryDirectory() as home:
        # one second, many shots (a boot on the fixed epoch sends every shot the same date): each takes the next free
        # number, " 2" to " 12" in turn, and nothing is written over
        sent = []
        for i in range(12):
            data = shot_bytes(2, 2, seed=i)
            rc, out, err = run(binary, home, data)
            sent.append(data)
            want = stamp(T0) + ("" if i == 0 else f" {i + 1}") + ".png"
            check(rc == 0 and out == want + "\n", f"shot {i + 1} of one second: rc {rc}, {out!r} {err!r}")
        for i, data in enumerate(sent):
            f = os.path.join(home, "Pictures", stamp(T0) + ("" if i == 0 else f" {i + 1}") + ".png")
            ok = os.path.isfile(f)
            if ok:
                w, h, bpp, px = check_png.read_png(open(f, "rb").read())
                ok = (w, h, px) == rgb_of(data)
            check(ok, f"shot {i + 1} of one second was written over")
        # the 100th and the 1000th of one second: " 100" and " 1000"
        for k in list(range(13, 100)) + list(range(101, 1000)):
            open(os.path.join(home, "Pictures", f"{stamp(T0)} {k}.png"), "wb").write(b"")
        for want in (100, 1000):
            rc, out, err = run(binary, home, shot_bytes(2, 2))
            ok = rc == 0 and out == f"{stamp(T0)} {want}.png\n"
            check(ok, f"shot {want} of one second: rc {rc}, {out!r} {err!r}")
        # every number to 9999 taken: status 1, nothing new
        for k in range(1001, 10000):
            open(os.path.join(home, "Pictures", f"{stamp(T0)} {k}.png"), "wb").write(b"")
        before = pictures(home)
        rc, out, err = run(binary, home, shot_bytes(2, 2))
        check(rc == 1 and out == "" and pictures(home) == before, f"every name of one second taken: rc {rc}, {out!r}")

    with tempfile.TemporaryDirectory() as home:
        # the date: the first second, the last the clock can be set to, and one past 2^32
        for t in (0, 8277292035, 4294967296 + 59):
            rc, out, err = run(binary, home, shot_bytes(1, 1, t=t))
            check(rc == 0 and out == stamp(t) + ".png\n", f"a shot dated {t}: rc {rc}, {out!r} {err!r}")

    # refusals: status 2 and no file
    bad = [
        ("no input", b""),
        ("a short header", struct.pack("<II", 4, 4)),
        ("a header without its date", struct.pack("<III", 4, 4, 16) + bytes(64)),
        ("a date past the clock's bound", shot_bytes(4, 4, t=8277292036)),
        ("a date past 2^33", shot_bytes(4, 4, t=1 << 33)),
        ("a date with its top bit set", shot_bytes(4, 4, t=(1 << 64) - 1)),
        ("width 0", shot_bytes(0, 4)),
        ("height 0", shot_bytes(4, 0)),
        ("width 3841", struct.pack("<IIIQ", 3841, 1, 4 * 3841, T0)),
        ("height 2161", struct.pack("<IIIQ", 1, 2161, 4, T0)),
        ("a stride that is not 4 x width", shot_bytes(4, 4, stride=17)),
        ("rows that end early", shot_bytes(8, 8)[:-5]),
        ("a byte after the last row", shot_bytes(8, 8) + b"\0"),
    ]
    for what, data in bad:
        with tempfile.TemporaryDirectory() as home:
            rc, out, err = run(binary, home, data)
            check(rc == 2 and out == "" and pictures(home) == [], f"{what}: rc {rc}, {out!r}, {pictures(home)}")

    # a call that fails: Pictures is a file, so nothing can be made; status 1, nothing left
    with tempfile.TemporaryDirectory() as home:
        open(os.path.join(home, "Pictures"), "wb").write(b"")
        rc, out, err = run(binary, home, shot_bytes(4, 4))
        kept = os.path.getsize(os.path.join(home, "Pictures")) == 0
        check(rc == 1 and out == "" and kept, f"Pictures a file: rc {rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"{n - len(fails)} of {n} checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
