#!/usr/bin/env python3
"""tools/oplref/mkwalk.py [--check]: the register walk of gate 7 (docs/specs/2026-11-06-au-audio.md section 6).

Writes tools/oplref/walk.txt, the script tools/oplref/ref.cpp plays on ymfm, and user/ci/oplwalk.ci, the same
events as a cint module for user/ci/opltest.ci. --check writes nothing and exits 1 if either file differs.

Script lines: `p K NAME` starts part K, `w RRR VV` writes register RRR (hex, 0x100 and up the second bank) with
VV, `s N` takes N samples. The walk covers every waveform, both connections and the four 4-operator ones, every
attack, decay and release rate with and without key scaling, every sustain level, every feedback level, total
level and key scale level, the multiples, blocks and note select, tremolo and vibrato at both depths, the
output routing bits, the rhythm section, clipping, the bank and mode registers, then a seeded random part.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TXT = os.path.join(HERE, "walk.txt")
CI = os.path.join(ROOT, "user", "ci", "oplwalk.ci")

ev = []          # ("p", k, name) | ("w", reg, val) | ("s", n)
part_names = []


def part(name):
    part_names.append(name)
    ev.append(("p", len(part_names), name))


def w(r, v):
    assert 0 <= r < 0x200 and 0 <= v < 0x100
    ev.append(("w", r, v))


def s(n):
    assert n > 0
    ev.append(("s", n))


def ops(ch):
    """The register offsets of a 2-operator channel's modulator and carrier (channel 0 to 17)."""
    bank, c = divmod(ch, 9)
    o = (c % 3) + 8 * (c // 3)
    return o + 0x100 * bank, o + 3 + 0x100 * bank


def choff(ch):
    bank, c = divmod(ch, 9)
    return c + 0x100 * bank


def op_regs(o, am=0, vib=0, eg=1, ksr=0, mult=1, ksl=0, tl=0, ar=15, dr=4, sl=4, rr=6, wf=0):
    w(0x20 + o, (am << 7) | (vib << 6) | (eg << 5) | (ksr << 4) | mult)
    w(0x40 + o, (ksl << 6) | tl)
    w(0x60 + o, (ar << 4) | dr)
    w(0x80 + o, (sl << 4) | rr)
    w(0xE0 + o, wf)


def voice(ch, mod=None, car=None, fb=0, alg=0, lr=0x30):
    m, c = ops(ch)
    op_regs(m, **(mod or {}))
    op_regs(c, **(car or {}))
    w(0xC0 + choff(ch), lr | (fb << 1) | alg)


def key(ch, fnum, block, on=True):
    k = choff(ch)
    w(0xA0 + k, fnum & 0xFF)
    w(0xB0 + k, (0x20 if on else 0) | (block << 2) | (fnum >> 8))


def off(ch, fnum=0x200, block=4):
    key(ch, fnum, block, on=False)


def hush(n=1200):
    """Every channel keyed off with a fast release, then n samples."""
    for ch in range(18):
        m, c = ops(ch)
        w(0x80 + m, 0x0F)
        w(0x80 + c, 0x0F)
        off(ch)
    w(0xBD, 0x00)
    s(n)


def build():
    # 1. OPL2 compatibility mode (NEW = 0): two operators, every feedback level, the four OPL2 waveforms.
    part("opl2 mode: feedback 0 to 7, waveforms 0 to 3")
    w(0x105, 0x00)
    w(0x01, 0x20)
    for fb in range(8):
        voice(0, mod={"tl": 12}, car={}, fb=fb)
        key(0, 0x244, 4)
        s(1500)
        off(0, 0x244, 4)
        s(300)
    for wf in range(8):   # 4 to 7 are masked to 2 bits without NEW
        voice(0, mod={"tl": 20, "wf": wf}, car={"wf": wf}, fb=3)
        key(0, 0x1C9, 5)
        s(1000)
        off(0, 0x1C9, 5)
        s(200)
    hush()

    # 2. OPL3 mode: the eight waveforms on the carrier alone (additive, modulator silent) and as the modulator.
    part("opl3 waveforms 0 to 7, carrier and modulator")
    w(0x105, 0x01)
    for wf in range(8):
        voice(1, mod={"tl": 63}, car={"wf": wf}, alg=1)
        key(1, 0x158, 4)
        s(1200)
        off(1, 0x158, 4)
        s(200)
    for wf in range(8):
        voice(1, mod={"tl": 8, "wf": wf}, car={"wf": 0}, fb=2)
        key(1, 0x158, 4)
        s(1200)
        off(1, 0x158, 4)
        s(200)
    hush()

    # 3. Output routing: the 16 settings of C0 bits 4 to 7, on a bank 1 and a bank 2 channel.
    part("output routing A B C D")
    for ch in (2, 13):
        for lr in range(16):
            voice(ch, mod={"tl": 30}, car={}, fb=1, lr=lr << 4)
            key(ch, 0x2AE, 4)
            s(400)
            off(ch, 0x2AE, 4)
            s(100)
    hush()

    # 4. Attack rates 0 to 15, key scaling off and on, at a low and a high block; one key off mid-attack.
    part("attack rates, key scale rate")
    for ksr in (0, 1):
        for block in (1, 7):
            for ar in range(16):
                voice(3, mod={"tl": 63}, car={"ar": ar, "dr": 0, "sl": 0, "rr": 8, "ksr": ksr}, alg=1)
                key(3, 0x300, block)
                s(900)
                off(3, 0x300, block)
                s(150)
    voice(3, mod={"tl": 63}, car={"ar": 6, "dr": 2, "sl": 2, "rr": 3}, alg=1)
    key(3, 0x200, 4)
    s(400)
    off(3, 0x200, 4)
    s(800)
    key(3, 0x200, 4)
    s(400)
    hush()

    # 5. Decay rates and sustain levels (held, EG type 1), release rates (EG type 0 decays through sustain).
    part("decay rates, sustain levels, release rates, EG type")
    for dr in range(16):
        voice(4, mod={"tl": 63}, car={"ar": 15, "dr": dr, "sl": 8, "rr": 15}, alg=1)
        key(4, 0x240, 5)
        s(700)
        off(4, 0x240, 5)
        s(100)
    for sl in range(16):
        voice(4, mod={"tl": 63}, car={"ar": 14, "dr": 12, "sl": sl, "rr": 15}, alg=1)
        key(4, 0x240, 5)
        s(500)
        off(4, 0x240, 5)
        s(100)
    for rr in range(16):
        voice(4, mod={"tl": 63}, car={"ar": 15, "dr": 0, "sl": 0, "rr": rr}, alg=1)
        key(4, 0x240, 5)
        s(300)
        off(4, 0x240, 5)
        s(700)
    for eg in (0, 1):
        voice(4, mod={"tl": 63}, car={"ar": 15, "dr": 9, "sl": 5, "rr": 9, "eg": eg}, alg=1)
        key(4, 0x240, 5)
        s(1500)
        off(4, 0x240, 5)
        s(500)
    hush()

    # 6. Total level and key scale level: TL in steps of 7, KSL 0 to 3 at every block.
    part("total level, key scale level")
    for tl in range(0, 64, 7):
        voice(5, mod={"tl": 63}, car={"tl": tl}, alg=1)
        key(5, 0x1A0, 4)
        s(300)
    for ksl in range(4):
        voice(5, mod={"tl": 24, "ksl": ksl}, car={"ksl": ksl}, fb=1)
        for block in range(8):
            for f4 in range(16):   # the top 4 bits of FNUM pick the key scale step
                key(5, (f4 << 6) | 0x2A, block)
                s(60)
    off(5, 0x3EA, 7)
    hush()

    # 7. Pitch: the 16 multiples, every block, FNUM across its range, note select.
    part("multiples, blocks, FNUM, note select")
    for mult in range(16):
        voice(6, mod={"tl": 28, "mult": mult}, car={"mult": (15 - mult)}, fb=2)
        key(6, 0x181, 3)
        s(400)
    for block in range(8):
        for fnum in (0x001, 0x0FF, 0x200, 0x3FF):
            key(6, fnum, block)
            s(120)
    for ns in (0x00, 0x40):
        w(0x08, ns)
        for fnum in (0x100, 0x2FF):
            voice(7, mod={"tl": 63}, car={"ar": 9, "ksr": 1, "dr": 5, "sl": 3}, alg=1)
            key(7, fnum, 6)
            s(600)
            off(7, fnum, 6)
            s(100)
    w(0x08, 0x00)
    hush()

    # 8. Tremolo and vibrato at both depths, over more than one LFO period each.
    part("tremolo and vibrato, both depths")
    for depth in (0x00, 0x40, 0x80, 0xC0):
        w(0xBD, depth)
        voice(9, mod={"tl": 30, "am": 1, "vib": 1}, car={"am": 1, "vib": 1}, fb=1)
        voice(10, mod={"tl": 63}, car={"am": 1, "vib": 0}, alg=1)
        voice(11, mod={"tl": 63}, car={"am": 0, "vib": 1, "mult": 4}, alg=1)
        key(9, 0x2D0, 4)
        key(10, 0x1F0, 5)
        key(11, 0x3A0, 6)
        s(14000)
    w(0xBD, 0x00)
    hush()

    # 9. Four operators: 0x104 pairs all on, a different connection on each pair, then each connection alone.
    part("four-operator connections")
    w(0x104, 0x3F)
    pairs = [0, 1, 2, 9, 10, 11]
    for i, ch in enumerate(pairs):
        cnt = i % 4
        voice(ch, mod={"tl": 20, "wf": i % 8}, car={"tl": 10}, fb=i + 1, alg=cnt & 1)
        voice(ch + 3, mod={"tl": 16}, car={"tl": 6, "wf": (i + 3) % 8}, alg=cnt >> 1)
        key(ch, 0x200 + 0x31 * i, 3 + (i % 3))
    s(6000)
    for cnt in range(4):
        hush(300)
        voice(0, mod={"tl": 18}, car={"tl": 8}, fb=5, alg=cnt & 1)
        voice(3, mod={"tl": 12}, car={"tl": 4}, alg=cnt >> 1)
        key(0, 0x2B0, 4)
        s(2500)
        key(3, 0x2B0, 4)   # a key on a channel of a pair does nothing
        s(200)
    w(0x104, 0x00)   # back to 2-operator mode with keys still down
    s(1500)
    hush()

    # 10. The rhythm section: bass drum, snare, tom, cymbal and high hat, alone and together.
    part("rhythm section")
    voice(6, mod={"tl": 10, "ar": 15, "dr": 6}, car={"ar": 15, "dr": 5, "sl": 15}, fb=4)
    voice(7, mod={"tl": 0, "ar": 15, "dr": 7}, car={"ar": 15, "dr": 6})
    voice(8, mod={"tl": 0, "ar": 15, "dr": 7}, car={"ar": 15, "dr": 8})
    key(6, 0x158, 2, on=False)
    key(7, 0x1C9, 3, on=False)
    key(8, 0x180, 3, on=False)
    for bits in (0x10, 0x08, 0x04, 0x02, 0x01, 0x1F, 0x11, 0x0A, 0x15):
        w(0xBD, 0x20 | bits)
        s(1200)
        w(0xBD, 0x20)
        s(300)
    voice(6, mod={"tl": 10}, car={"sl": 15}, fb=4, alg=1)   # the bass drum ignores operator 1 in connection 1
    w(0xBD, 0x30)
    s(1500)
    w(0xBD, 0x00)
    hush()

    # 11. All 18 channels at full level: the sums pass 16 bits and clamp.
    part("eighteen channels, clipping")
    for ch in range(18):
        voice(ch, mod={"tl": 0, "wf": ch % 8}, car={"tl": 0, "wf": (ch * 3) % 8}, alg=1, lr=0xF0)
        key(ch, 0x150 + 0x20 * ch, 4 + (ch % 3))
    s(5000)
    hush()

    # 12. The bank and mode registers: second-bank writes without NEW fall into the first bank; NEW toggled
    # with keys down; writes to the mode register 0x04.
    part("bank masking, NEW toggled, mode register")
    w(0x105, 0x00)
    voice(12, mod={"tl": 20}, car={}, fb=2)   # without NEW: lands on channel 3's registers
    key(12, 0x230, 4)
    s(1500)
    w(0x105, 0x01)
    voice(12, mod={"tl": 20}, car={}, fb=2, lr=0x10)
    key(12, 0x230, 4)
    s(1000)
    w(0x105, 0x00)
    s(800)
    w(0x105, 0x01)
    w(0x04, 0x60)
    w(0x04, 0x80)
    w(0x02, 0x40)
    w(0x03, 0x10)
    w(0x04, 0x03)
    s(600)
    hush()

    # 13. Seeded random writes to every register group, with short sample runs between them.
    part("random")
    x = 20261106
    groups = []
    for bank in (0, 0x100):
        for lo, hi in ((0x20, 0x35), (0x40, 0x55), (0x60, 0x75), (0x80, 0x95), (0xE0, 0xF5),
                       (0xA0, 0xA8), (0xB0, 0xB8), (0xC0, 0xC8)):
            groups.append((bank + lo, bank + hi))
    groups += [(0xBD, 0xBD), (0x104, 0x104), (0x08, 0x08), (0x105, 0x105)]
    for _ in range(4000):
        x = (x * 1103515245 + 12345) % (1 << 31)
        lo, hi = groups[(x >> 8) % len(groups)]
        x = (x * 1103515245 + 12345) % (1 << 31)
        r = lo + (x >> 8) % (hi - lo + 1)
        x = (x * 1103515245 + 12345) % (1 << 31)
        v = (x >> 11) & 0xFF
        if r == 0x105:
            v &= 1
        if r == 0x104:
            v &= 0x3F
        w(r, v)
        x = (x * 1103515245 + 12345) % (1 << 31)
        s(1 + (x >> 9) % 48)
    w(0x105, 0x01)
    hush()

    # 14. Silence: keys off, every operator released, past the 4,096-sample prepare.
    part("release to silence")
    s(9000)


def render():
    build()
    total = sum(e[1] for e in ev if e[0] == "s")
    txt = ["# tools/oplref/walk.txt: the register walk of gate 7, written by tools/oplref/mkwalk.py; do not edit.",
           "# p K NAME: part K; w RRR VV: register RRR (hex) gets VV; s N: N samples. %d samples." % total]
    words = []
    for e in ev:
        if e[0] == "p":
            txt.append("p %d %s" % (e[1], e[2]))
            words.append((3 << 24) | e[1])
        elif e[0] == "w":
            txt.append("w %03x %02x" % (e[1], e[2]))
            words.append((1 << 24) | (e[1] << 8) | e[2])
        else:
            txt.append("s %d" % e[1])
            words.append((2 << 24) | e[1])
    ci = ["// user/ci/oplwalk.ci: the register walk of gate 7 (tools/oplref/walk.txt) as data, written by",
          "// tools/oplref/mkwalk.py; do not edit. An event is kind << 24 | data: kind 1 a write, data the register",
          "// << 8 | the value; kind 2 samples, data the count; kind 3 a part, data its number.",
          "",
          "export const I64 EVENTS = %d;" % len(words),
          "export const I64 PARTS = %d;" % len(part_names),
          "export const I64 SAMPLES = %d;" % total,
          "",
          "I64[%d] EV = [" % len(words)]
    for i in range(0, len(words), 8):
        ci.append("    " + ", ".join("0x%07x" % v for v in words[i:i + 8]) + ("," if i + 8 < len(words) else ""))
    ci += ["];", "", "export I64 event(I64 i) {", "    return EV[i];", "}", "// SPDX-License-Identifier: Apache-2.0", ""]
    return "\n".join(txt) + "\n", "\n".join(ci)


def main():
    txt, ci = render()
    check = "--check" in sys.argv[1:]
    bad = 0
    for path, body in ((TXT, txt), (CI, ci)):
        if check:
            try:
                same = open(path).read() == body
            except OSError:
                same = False
            if not same:
                print("mkwalk: %s differs from tools/oplref/mkwalk.py" % os.path.relpath(path, ROOT))
                bad = 1
        else:
            with open(path, "w") as f:
                f.write(body)
    if not check:
        print("mkwalk: %d events, %d parts" % (len(ev), len(part_names)))
    return bad


if __name__ == "__main__":
    sys.exit(main())
