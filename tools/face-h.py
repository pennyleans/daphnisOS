#!/usr/bin/env python3
"""tools/face-h.py: rt/face.h from user/ci/kit/face.ci (HW-3: the screen console's glyphs, the kit's face in C)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "user/ci/kit/face.ci").read_text()
vals = re.findall(r"0x[0-9a-fA-F]{16}", src[src.index("U64[190] bits = ["):])[:190]
if len(vals) != 190:
    sys.exit("face-h: user/ci/kit/face.ci does not hold 190 words")
out = ["/* rt/face.h: Daphnis Mono 8 x 16 (stage K, K-2; OFL-1.1, tools/fonts/OFL.txt), the bits of user/ci/kit/face.ci for",
       " * rt/console.c (HW-3), written by tools/face-h.py; do not edit. Glyph c (32 to 126) is face_bits[2 * (c - 32)] (rows",
       " * 0 to 7) and face_bits[2 * (c - 32) + 1] (rows 8 to 15), row 0 in the top byte, column 0 in a byte's top bit. */",
       "static const uint64_t face_bits[190] = {"]
for i in range(0, 190, 4):
    out.append("    " + ", ".join(v + "u" for v in vals[i:i + 4]) + ",")
out.append("};")
(ROOT / "rt/face.h").write_text("\n".join(out) + "\n")
