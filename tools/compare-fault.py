#!/usr/bin/env python3
"""compare-fault.py TRANSCRIPT HOSTED_RECORD CINT_PROGRAM_C

Checks the cint-core-1/fault/v2 record the kernel printed (TRANSCRIPT) against the record
the hosted runtime wrote for the same overflow (HOSTED_RECORD, tests/fault_probe.ci):
  - the hex line decodes to exactly the byte count the kernel announced;
  - equal between kernel and hosted: domain, code, operation, operands, exact, limit, the
    source-map digest, the address, the fault position (both are src/overflow.ci:7:23),
    and the stack depth;
  - NOT compared with the hosted record, because the two programs differ in source: the
    revision (instead the kernel's equals cg_revision of its own emitted cint-program.c,
    CINT_PROGRAM_C) and the stack entry (instead the kernel's is the call site of
    max_plus_one in src/main_fault.ci, found by searching the source).
Prints one line per check, PASS or FAIL. Exits 1 on any FAIL."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faultrec import decode  # noqa: E402

fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


def find(path, needle, within=None):
    """(line, column) of `within` (default needle) on the first line of `path` that holds needle."""
    for n, l in enumerate(open(path).read().split("\n"), 1):
        if needle in l:
            return n, l.index(within or needle) + 1
    raise SystemExit("compare-fault.py: %r not found in %s" % (needle, path))


transcript, hosted_path, program_c = sys.argv[1:4]
lines = open(transcript).read().split("\n")
try:
    i = next(k for k, l in enumerate(lines) if l.startswith("fault: cint-core-1/fault/v2 "))
    announced = int(lines[i].split()[2])
    kbytes = bytes.fromhex(lines[i + 1])
except (StopIteration, ValueError, IndexError):
    check(False, "fault record present in transcript", "no 'fault: ...' header and hex line")
    sys.exit(1)
check(len(kbytes) == announced, "kernel record length matches its header (%d bytes)" % announced,
      "hex line is %d bytes" % len(kbytes))
try:
    k = decode(kbytes)
    h = decode(open(hosted_path, "rb").read())
except ValueError as e:
    check(False, "records decode", str(e))
    sys.exit(1)
check(True, "both records decode as cint-core-1/fault/v2")
for field in ("domain", "code", "operation", "operands", "exact", "limit", "srcmap", "address_present", "position"):
    check(k[field] == h[field], "kernel equals hosted: %s" % field, "%r vs %r" % (k[field], h[field]))
ln, col = find("src/overflow.ci", "big + 1", "+")
check(k["position"] == ("src/overflow.ci", ln, col), "kernel position is src/overflow.ci:%d:%d" % (ln, col), repr(k["position"]))
check(len(k["stack"]) == len(h["stack"]) == 1, "kernel and hosted stacks both have one entry",
      "%d vs %d" % (len(k["stack"]), len(h["stack"])))
ln, col = find("src/main_fault.ci", "overflow.max_plus_one", "max_plus_one")
check(k["stack"] == [("src/main_fault.ci", ln, col)], "kernel stack is the call site src/main_fault.ci:%d:%d" % (ln, col),
      repr(k["stack"]))
m = re.search(r"cg_revision\[32\] = \{(.*?)\};", open(program_c).read(), re.S)
rev = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1))) if m else None
check(rev is not None and len(rev) == 32 and k["revision"] == rev, "kernel revision equals cg_revision of its emitted program",
      "%r vs %r" % (k["revision"], rev))
check(h["revision"] is not None and h["revision"] != k["revision"], "hosted revision is present and differs (different program)",
      "hosted %r" % (h["revision"],))
sys.exit(fail)
