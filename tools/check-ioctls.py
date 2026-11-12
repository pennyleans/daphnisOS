#!/usr/bin/env python3
"""tools/check-ioctls.py: the FBIO_TILE family's numbers, one name to one number (AM-2, RES-1).

Reads every `FBIO_TILE...` constant in src/tile.ci and in user/ci (the kernel's table and each program's copy) and
fails when two names share a number, or one name has two numbers. Run by check.sh, hosted; a clash shows at merge.
"""
import os
import re
import sys

PAT = re.compile(r"\bconst\s+[IU]64\s+(FBIO_TILE\w*)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;")


def scan(root):
    """Each (name, number, file, line) of the family under root."""
    files = [os.path.join(root, "src", "tile.ci")]
    for d, _, names in os.walk(os.path.join(root, "user", "ci")):
        files += [os.path.join(d, n) for n in sorted(names) if n.endswith(".ci")]
    out = []
    for f in files:
        if not os.path.exists(f):
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, text in enumerate(fh, 1):
                if text.lstrip().startswith("//"):
                    continue
                for m in PAT.finditer(text):
                    out.append((m.group(1), int(m.group(2), 0), os.path.relpath(f, root), i))
    return out


def main(argv):
    root = argv[0] if argv else "."
    seen = scan(root)
    by_name, by_num = {}, {}
    for name, num, f, i in seen:
        by_name.setdefault(name, set()).add(num)
        by_num.setdefault(num, {}).setdefault(name, "%s:%d" % (f, i))
    bad = 0
    for name, nums in sorted(by_name.items()):
        if len(nums) > 1:
            print("FAIL  %s has %s" % (name, ", ".join("0x%04X" % n for n in sorted(nums))))
            bad += 1
    for num, names in sorted(by_num.items()):
        if len(names) > 1:
            print("FAIL  0x%04X is %s" % (num, ", ".join("%s (%s)" % (n, w) for n, w in sorted(names.items()))))
            bad += 1
    if bad == 0:
        print("PASS  ioctls: %d FBIO_TILE names, %d numbers, no two names share one" % (len(by_name), len(by_num)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
