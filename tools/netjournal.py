#!/usr/bin/env python3
"""tools/netjournal.py: the frame record of stage N (docs/specs/2026-11-05-n-net.md sections 2 and 4).

  netjournal.py journal TRANSCRIPT OUT   the `net mac` line and the `net rx` lines of a live transcript, in
                                         order, as net.journal: the member that makes a boot replay
  netjournal.py rng TRANSCRIPT OUT       A-3: the `rtc S` line (if any), the `rng N HEX` lines, the `clk S`
                                         lines (RS-CLK, a set of the clock) and the `wal S` lines (RS-CLK2, the
                                         PIT seconds the system's time took) of a live transcript, in order, as
                                         rng.journal: the member that replays the draws, the date, its sets and
                                         the machine's clock (src/rng.ci, src/rtc.ci)
  netjournal.py same LIVE REPLAY         the two transcripts are equal but for the mode lines (those that start
                                         `daphnis: net virtio-net`, `daphnis: net e1000` (HW-7), `daphnis: net
                                         replay`, `daphnis: rng rdrand` or `daphnis: rng replay`)

Exit status 0 on success; 1 with the reason on stderr. The journal is checked as it is written: one `net
mac` line first, then `net rx TICK LEN HEX` lines with ticks that never fall (frames a live tick took together share it), LEN at most 1514 and 2 * LEN
lowercase hex digits. A `net rx` record that a program's unfinished line precedes on the same line counts from
its `net rx` (A-1: an agent streams text without a newline while frames arrive). The rng journal is checked the
same way: at most one `rtc S` line, first, then `rng N HEX` records with N from 1 to 256 and 2 * N lowercase hex
digits, each at the end of its line (a draw can come while a program's line is open), and `clk S` and `wal S`
records the same way, after the `rtc` line. K-6b: the `rtc` line alone, or with `clk` or `wal` lines and no draw,
is a journal, the record of a boot with daphnis.rtc=1 and no RDRAND."""
import re
import sys

MAC = re.compile(rb"net mac [0-9a-f]{2}(:[0-9a-f]{2}){5}")
RX = re.compile(rb"net rx ([1-9][0-9]*) ([0-9]+)(?: (0|[1-9][0-9]*))? ([0-9a-f]*)")
MODE = (b"daphnis: net virtio-net", b"daphnis: net e1000", b"daphnis: net replay", b"daphnis: rng rdrand",
        b"daphnis: rng replay")
RTC = re.compile(rb"rtc (0|[1-9][0-9]*)")
RNG = re.compile(rb"rng ([1-9][0-9]*) ([0-9a-f]+)$")
# RS-CLK2: the kernel prints a `clk` or `wal` record on a line of its own (src/rng.ci own_line), so only a whole line
# is one; text a program prints that ends the same way is not. `wal S N`: the PIT seconds S the system's time took on
# a dated boot, at wall_take's call N.
CLK = re.compile(rb"clk (0|[1-9][0-9]*)")
WAL = re.compile(rb"wal (0|[1-9][0-9]*) ([1-9][0-9]*)")


def journal(transcript, out):
    lines = open(transcript, "rb").read().split(b"\n")
    macs = [l for l in lines if l.startswith(b"net mac ")]
    if len(macs) != 1 or not MAC.fullmatch(macs[0]):
        sys.exit("netjournal: %s: want one `net mac` line, found %d" % (transcript, len(macs)))
    rec, last, last_timer, has_timer = [macs[0]], 0, 0, None
    for l in lines:
        at = l.find(b"net rx ")   # A-1: a frame can arrive while a program's line is open, mid-line
        if at < 0 or l.startswith(b"daphnis: "):   # the kernel's count line, `daphnis: net rx N tx M ...`
            continue
        l = l[at:]
        m = RX.fullmatch(l)
        if not m:
            sys.exit("netjournal: malformed record: %r" % l[:60])
        tick, n, tm, hx = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        if has_timer is None:
            has_timer = tm is not None
        elif has_timer != (tm is not None):
            sys.exit("netjournal: mixed timer formats at tick %d" % tick)
        if tick < last or tick < 1 or n > 1514 or len(hx) != 2 * n:
            sys.exit("netjournal: record out of order or bad length at tick %d" % tick)
        if tm is not None:
            timer = int(tm)
            if timer < last_timer:
                sys.exit("netjournal: timer fell at tick %d" % tick)
            last_timer = timer
        last = tick
        rec.append(l)
    with open(out, "wb") as f:
        f.write(b"\n".join(rec) + b"\n")
    print("netjournal: %s: 1 mac line, %d frames" % (out, len(rec) - 1))


def rng(transcript, out):
    lines = open(transcript, "rb").read().split(b"\n")
    rtcs = [l for l in lines if RTC.fullmatch(l)]
    if len(rtcs) > 1:
        sys.exit("netjournal: %s: want at most one `rtc` line, found %d" % (transcript, len(rtcs)))
    if rtcs and lines.index(rtcs[0]) > min([i for i, l in enumerate(lines) if CLK.fullmatch(l)] or [len(lines)]):
        sys.exit("netjournal: %s: a `clk` line before the `rtc` line" % transcript)
    if rtcs and lines.index(rtcs[0]) > min([i for i, l in enumerate(lines) if WAL.fullmatch(l)] or [len(lines)]):
        sys.exit("netjournal: %s: a `wal` line before the `rtc` line" % transcript)
    rec = list(rtcs)
    sets = walls = 0
    wal_s, wal_n = 0, 0   # a `wal` record's seconds rise until a set starts them again; its call count always rises
    for l in lines:
        if l.startswith(b"daphnis: "):
            continue
        if CLK.fullmatch(l):
            rec.append(l)
            sets += 1
            wal_s = 0
            continue
        m = WAL.fullmatch(l)
        if m:
            if not rtcs:
                sys.exit("netjournal: %s: `wal` lines without an `rtc` line" % transcript)
            s, n = int(m.group(1)), int(m.group(2))
            if s <= wal_s or n <= wal_n:
                sys.exit("netjournal: %s: a `wal` record out of order: %r" % (transcript, l))
            wal_s, wal_n = s, n
            rec.append(l)
            walls += 1
            continue
        m = RNG.search(l)
        if not m:
            continue
        n = int(m.group(1))
        if n > 256 or len(m.group(2)) != 2 * n:
            sys.exit("netjournal: malformed draw: %r" % l[m.start():m.start() + 60])
        rec.append(l[m.start():])
    if not rec:
        sys.exit("netjournal: %s: no `rtc` line and no `rng` record" % transcript)
    if sets and not rtcs:
        sys.exit("netjournal: %s: `clk` lines without an `rtc` line" % transcript)
    with open(out, "wb") as f:
        f.write(b"\n".join(rec) + b"\n")
    print("netjournal: %s: %d rtc line, %d draws, %d clock sets, %d wal seconds"
          % (out, len(rtcs), len(rec) - len(rtcs) - sets - walls, sets, walls))


def same(live, replay):
    a = [l for l in open(live, "rb").read().split(b"\n") if not l.startswith(MODE)]
    b = [l for l in open(replay, "rb").read().split(b"\n") if not l.startswith(MODE)]
    if a != b:
        sys.exit("netjournal: %s and %s differ beyond the mode line" % (live, replay))
    print("netjournal: %s equals %s but for the mode line" % (replay, live))


def main(argv):
    if len(argv) == 3 and argv[0] == "journal":
        journal(argv[1], argv[2])
    elif len(argv) == 3 and argv[0] == "rng":
        rng(argv[1], argv[2])
    elif len(argv) == 3 and argv[0] == "same":
        same(argv[1], argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
