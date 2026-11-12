#!/usr/bin/env python3
"""tools/fontproof.py OUTDIR < proof-output: FONT-1's proof sheet (F5). Reads what a build of tests/font/proof.ci
prints (frames of run-length rows, drawn by the kit's ctext.ci and mtext.ci on the host) and writes each frame as
OUTDIR/ref_daphnis_fonts_proof_NAME.png. The pixels are the kit's; this file only packs them."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import png  # noqa: E402


def main():
    out = sys.argv[1]
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
                raise SystemExit("fontproof.py: %s row %d is %d px, not %d" % (cur[0], len(cur[3]), len(row), cur[1]))
            cur[3].append(row)
    for name, w, h, rows in frames:
        if len(rows) != h:
            raise SystemExit("fontproof.py: %s has %d rows, not %d" % (name, len(rows), h))
        path = os.path.join(out, "ref_daphnis_fonts_proof_%s.png" % name.replace("-", "_"))
        png.write(path, w, h, rows)
        print("wrote", path)


if __name__ == "__main__":
    main()
