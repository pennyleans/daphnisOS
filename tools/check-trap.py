#!/usr/bin/env python3
"""check-trap.py TRANSCRIPT CINT_PROGRAM_C

Checks the K2 transcript of the trap flavor: three fault records (divide error, invalid
opcode, page fault) printed by cint, each decoded and compared with what the probe must
produce, and the tick line. Per record: domain cint-core-1/fault/v2, code 10 (E_UNSUPPORTED),
operation host.error.trap_<name>, operands [I64 vector, U64 error code, U64 CR2], no exact,
no limit, position the call of the probe in src/main_trap.ci, an empty stack, and the revision
of the emitted program (CINT_PROGRAM_C). Prints PASS or FAIL per check; exits 1 on any FAIL."""
import os
import re
import struct
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
    for n, l in enumerate(open(path).read().split("\n"), 1):
        if needle in l:
            return n, l.index(within or needle) + 1
    raise SystemExit("check-trap.py: %r not found in %s" % (needle, path))


def u64(v):
    return (0x24, struct.pack("<Q", v))


def i64(v):
    return (0x14, struct.pack("<q", v))


transcript, program_c = sys.argv[1:3]
lines = open(transcript).read().split("\n")
m = re.search(r"cg_revision\[32\] = \{(.*?)\};", open(program_c).read(), re.S)
rev = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))
cases = [
    ("de", "trap_de", "trap_probe_de", 0, 0, 0),
    ("ud", "trap_ud", "trap_probe_ud", 6, 0, 0),
    ("pf", "trap_pf", "trap_probe_pf", 14, 2, 0x40000AC8),
]
for short, op, probe, vec, err, cr2 in cases:
    try:
        i = lines.index("trap " + short)
        header = lines[i + 1].split()
        announced = int(header[2])
        raw = bytes.fromhex(lines[i + 2])
        check(lines[i + 1].startswith("fault: cint-core-1/fault/v2 ") and lines[i + 1].endswith(" bytes"),
              "trap %s: record header line" % short, lines[i + 1])
        check(len(raw) == announced, "trap %s: hex line has the %d bytes announced" % (short, announced), "%d bytes" % len(raw))
        r = decode(raw)
    except (ValueError, IndexError, KeyError) as e:
        check(False, "trap %s: record present and decodable" % short, repr(e))
        continue
    check(r["domain"] == "cint-core-1/fault/v2" and r["code"] == 10, "trap %s: domain v2, code 10 (E_UNSUPPORTED)" % short,
          "%r %r" % (r["domain"], r["code"]))
    check(r["operation"] == "host.error." + op, "trap %s: operation host.error.%s" % (short, op), r["operation"])
    check(r["operands"] == [i64(vec), u64(err), u64(cr2)], "trap %s: operands vector %d, error code %d, CR2 %#x" % (short, vec, err, cr2),
          repr(r["operands"]))
    check(r["exact"] is None and r["limit"] is None and r["srcmap"] is None and not r["address_present"],
          "trap %s: no exact, limit, source-map digest or address" % short)
    ln, col = find("src/main_trap.ci", "trap." + probe, probe)
    check(r["position"] == ("src/main_trap.ci", ln, col) and r["stack"] == [],
          "trap %s: position src/main_trap.ci:%d:%d, empty stack" % (short, ln, col), "%r %r" % (r["position"], r["stack"]))
    check(r["revision"] == rev, "trap %s: revision equals cg_revision of the emitted program" % short)
check("ticks: 100" in lines and "timer: fewer ticks than waits" not in lines and "timer: PIT not programmed" not in lines,
      "timer: the transcript says 'ticks: 100' after 100 waits and no shortfall line")
check(lines.count("Daphnis K2: traps and timer") == 1 and lines[-2:] == ["ticks: 100", ""],
      "transcript: banner once, and it ends with the tick line")
sys.exit(fail)
