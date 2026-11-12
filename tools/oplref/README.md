# tools/oplref: the OPL3 reference tool (AU-7)

ymfm (Aaron Giles, BSD-3-Clause, github.com/aaronsgiles/ymfm at `81aec25`) built on the host, headless, its YMF262
playing a register script and writing every chip-rate sample (spec `docs/specs/2026-11-06-au-audio.md` section 6,
gate 7). Host only; nothing of it enters the image. The port it checks is `user/ci/opl/opl3.ci`.

    sh tools/oplref/fetch.sh WORK/ymfm                   # the source at the pinned commit
    sh tools/oplref/build.sh WORK/ymfm/src WORK/ref      # CXX=clang++ for the other compiler
    WORK/ref/oplref tools/oplref/walk.txt WORK/walk.raw
    python3 tools/check-opl.py lines WORK/walk.raw       # the lines opltest must print
    OPLREF=WORK/ref/oplref ./check-opl.sh                # the gate with the reference leg

- `ref.cpp` constructs a `ymfm::ymf262`, resets it, and plays the script: a write goes through the address port
  (0, or 2 for 0x100 and up) and the data port, as on the bus; a sample is `generate` once, its four outputs A, B,
  C, D as 16-bit little-endian.
- `mkwalk.py` writes the script, `walk.txt`, and the same events as cint data, `user/ci/oplwalk.ci`; `--check`
  compares both with what it would write. The walk's 14 parts cover every waveform, both 2-operator connections and
  the four 4-operator ones, every attack, decay and release rate with and without key scaling, every sustain,
  feedback, total and key scale level, the multiples, blocks and note select, tremolo and vibrato at both depths,
  the output routing bits, the rhythm section, clipping, the bank and mode registers, and 4,000 seeded random
  writes: 442,462 samples, 8.9 s at the chip's 49,715.9 Hz.
- `tools/check-opl.py lines` digests ymfm's samples part by part and resamples them to 48 kHz by the rule of
  `user/ci/opl/rate.ci`, independently; `tests/expected/opl.digests` holds its lines, made once from this tool.
