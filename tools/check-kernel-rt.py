#!/usr/bin/env python3
"""check-kernel-rt.py INC RT DIR...: every cint_rt_* function a kernel's emitted C calls is defined where the kernel
links: inline or as a macro in the toolchain's headers (INC), in the kernel's own runtime (RT/*.c, RT/*.h), or in the
emitted C itself. The hosted runtime defines more (cint_rt_scratch, cint_rt_scratch_mark and _release, for a large
local array); a call to one of those builds hosted and fails the kernel's link (board 20261110T213349Z). Prints each
missing name with the emitted file that calls it; status 1 if any."""
import glob
import os
import re
import sys

NAME = re.compile(r"\b(cint_rt_\w+)\s*\(")
MACRO = re.compile(r"#\s*define\s+(cint_rt_\w+)")


def bodies(text):
    """The cint_rt_* names text defines with a body (or as a macro)."""
    out = set(MACRO.findall(text))
    for m in NAME.finditer(text):
        i = m.end()
        depth = 1
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if text.startswith("{", i):
            out.add(m.group(1))
    return out


def sources(d):
    return [f for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
            if os.path.isfile(f) and f.endswith((".c", ".h"))]


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    inc, rt, dirs = sys.argv[1], sys.argv[2], sys.argv[3:]
    have = set()
    for f in glob.glob(os.path.join(inc, "*.h")) + sources(rt):
        have |= bodies(open(f, errors="replace").read())
    called = {}
    for d in dirs:
        for f in sources(d):
            t = open(f, errors="replace").read()
            have |= bodies(t)
            for n in set(re.findall(r"\bcint_rt_\w+", t)):
                called.setdefault(n, f)
    missing = sorted(n for n in called if n not in have and NAME.search(n + "("))
    # a name used only as a type or a constant (no call) is the headers' business, not the link's
    missing = [n for n in missing if re.search(r"\b" + n + r"\s*\(", open(called[n], errors="replace").read())]
    for n in missing:
        print("MISSING %s (called in %s): the kernel runtime does not define it" % (n, os.path.relpath(called[n])))
    print("kernel rt: %d runtime names called, %d not defined for the kernel" % (len(called), len(missing)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
