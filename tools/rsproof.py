#!/usr/bin/env python3
"""tools/rsproof.py OUTDIR [PREFIX] < proof-output: stage RS's proof twins (docs/specs/2026-11-11-rs-rel-s1-units.md
section 5). Reads what a run of a tests/rs/*_proof.ci prints (`frame NAME W H`, then H rows of runs `r RGB COUNT
...`, drawn by the kit on the host) and writes each frame as OUTDIR/PREFIXNAME.png. The pixels are the kit's; this
file only packs them."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import png  # noqa: E402


def main():
    out = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""
    frames, cur = [], None
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "frame":
            cur = (parts[1], int(parts[2]), int(parts[3]), [])
            frames.append(cur)
        elif parts[0] == "r":
            row = []
            for k in range(1, len(parts), 2):
                row += [int(parts[k], 16)] * int(parts[k + 1])
            if len(row) != cur[1]:
                raise SystemExit("rsproof.py: %s row %d is %d px, not %d" % (cur[0], len(cur[3]), len(row), cur[1]))
            cur[3].append(row)
    for name, w, h, rows in frames:
        if len(rows) != h:
            raise SystemExit("rsproof.py: %s has %d rows, not %d" % (name, len(rows), h))
        path = os.path.join(out, prefix + name + ".png")
        png.write(path, w, h, rows)
        print("wrote", path)


if __name__ == "__main__":
    main()
