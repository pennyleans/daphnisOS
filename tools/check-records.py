#!/usr/bin/env python3
"""check-records.py FLAVOR TRANSCRIPT CINT_PROGRAM_C

Checks the trap records in the transcript of a K3 flavor (stackover, nullptr). Each record
is a label line, a header line `fault: cint-core-1/fault/v2 N bytes` and a hex line; it is
decoded and compared with a table kept here, independent of the program: domain, code 10
(E_UNSUPPORTED), operation host.error.<name>, the operands (I64 vector, U64 error code, U64
CR2 or an offset, U64 IST index), no exact, limit, source-map digest or address, the position
of the call of the probe in the flavor's main (found by searching the source), an empty
stack, and the revision of the emitted program (CINT_PROGRAM_C). The number and order of the
records is checked too. Prints PASS or FAIL per check; exits 1 on any FAIL."""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faultrec import decode  # noqa: E402

I64, U64 = 0x14, 0x24

# label -> (operation, [vector, error code, CR2 or guard offset, IST], probe to find, which call of it)
CASES = {
    "stackover": ("src/main_stackover.ci", [
        ("trap stack", "trap_stack", [14, 2, 0xFF8, 3], "trap_probe_stack", 1),
        ("trap nmi", "trap_nmi", [2, 0, 0, 2], "trap_probe_nmi", 1),
        ("trap df", "trap_df", [8, 0, 0, 1], "trap_probe_pf", 1),
        ("trap pf", "trap_pf", [14, 2, 0x50000018, 3], "trap_probe_pf", 2),
    ], ["Daphnis K3: stack overflow and interrupt stacks", "stackover: done"]),
    "nullptr": ("src/main_nullptr.ci", [
        ("null write", "trap_pf", [14, 2, 0x18, 3], "trap_probe_pf", 1),
        ("null read", "trap_pf", [14, 0, 0, 3], "vm_load64", 1),
    ], ["Daphnis K3: null page", "nullptr: done"]),
}

fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


def find(path, needle, nth):
    seen = 0
    for n, l in enumerate(open(path).read().split("\n"), 1):
        at = l.find("." + needle)
        if at >= 0:
            seen += 1
            if seen == nth:
                return n, at + 2
    raise SystemExit("check-records.py: call %d of %s not found in %s" % (nth, needle, path))


flavor, transcript, program_c = sys.argv[1:4]
main_src, cases, bookends = CASES[flavor]
lines = open(transcript).read().split("\n")
m = re.search(r"cg_revision\[32\] = \{(.*?)\};", open(program_c).read(), re.S)
rev = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))
check(lines[0] == bookends[0] and lines[-2] == bookends[1] and lines[-1] == "", "%s: first and last line" % flavor, repr((lines[0], lines[-2:])))
labels = [l for l in lines if re.match(r"^(trap|null) ", l)]
check(labels == [c[0] for c in cases], "%s: exactly these records, in this order" % flavor, repr(labels))
for label, op, operands, probe, nth in cases:
    try:
        i = lines.index(label)
        announced = int(lines[i + 1].split()[2])
        raw = bytes.fromhex(lines[i + 2])
        check(lines[i + 1] == "fault: cint-core-1/fault/v2 %d bytes" % announced and len(raw) == announced,
              "%s: header and %d hex bytes agree" % (label, announced), lines[i + 1])
        r = decode(raw)
    except (ValueError, IndexError) as e:
        check(False, "%s: record present and decodable" % label, repr(e))
        continue
    check(r["domain"] == "cint-core-1/fault/v2" and r["code"] == 10, "%s: v2 record, code 10" % label, "%r %r" % (r["domain"], r["code"]))
    check(r["operation"] == "host.error." + op, "%s: operation host.error.%s" % (label, op), r["operation"])
    want = [(I64, struct.pack("<q", operands[0]))] + [(U64, struct.pack("<Q", v)) for v in operands[1:]]
    check(r["operands"] == want, "%s: operands %s" % (label, [hex(v) for v in operands]), repr(r["operands"]))
    check(r["exact"] is None and r["limit"] is None and r["srcmap"] is None and not r["address_present"],
          "%s: no exact, limit, source-map digest or address" % label)
    ln, col = find(main_src, probe, nth)
    check(r["position"] == (main_src, ln, col) and r["stack"] == [], "%s: position %s:%d:%d, empty stack" % (label, main_src, ln, col),
          "%r %r" % (r["position"], r["stack"]))
    check(r["revision"] == rev, "%s: revision equals cg_revision of the emitted program" % label)
sys.exit(fail)
