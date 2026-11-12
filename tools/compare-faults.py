#!/usr/bin/env python3
"""compare-faults.py TRANSCRIPT HOSTED_DIR CINT_PROGRAM_C

Checks the transcript of the faults flavor. The kernel ran src/main_faults.ci eleven times
(runs 0 to 10) and printed a canonical fault record for each, then a final entry (run 11)
returned normally. For runs 0 to 9 the hosted runtime ran the same program (same source, so the
same revision, positions and stack) and wrote HOSTED_DIR/rec<i>.bin: the kernel's record must
be byte-identical to it. Run 10 (fuel) has no hosted record file (a hosted run has unbounded
fuel; tests/fuel_twin.ci covers its shape in the hosted text). Independent of both, a table
here says what each run must fault with, so a probe that faults the wrong way cannot pass by
matching its own twin: the code, the operation, and the position found by searching
src/probes.ci. Also checked: the runs appear once each in order, the loop ended at run 11, the
revision is cg_revision of the emitted program, and the stack's first entry is the call of
probes.run in src/main_faults.ci. Prints PASS or FAIL per check; exits 1 on any FAIL."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faultrec import decode  # noqa: E402

# run -> (code, operation, a line of src/probes.ci that holds the fault, the token on it)
TABLE = [
    (1, "add.checked.i64", "I64 x = big + (zero + 1);", "+"),
    (1, "sub.checked.u8", "U8 c = a - b;", "-"),
    (1, "mul.checked.i32", "I32 c = a * b;", "*"),
    (1, "neg.checked.i8", "I8 q = -m;", "-"),
    (2, "div.checked.i64", "return 100 / zero;", "/"),
    (2, "rem.checked.i64", "return 100 % zero;", "%"),
    (5, "shl.checked.u32", "U32 s = one << (32 + zero);", "<<"),
    (6, "as.checked.i64.u8", "U8 b = big as U8;", "as"),
    (3, "index.checked.u8", "a[i] = 1;", "["),
    (12, "call.enter", "return probe_depth(d + 1) + 1;", "probe_depth"),
    (9, "fuel.charge", "while (true) {", "while"),
]
fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


def locate(path, needle, token):
    for n, l in enumerate(open(path).read().split("\n"), 1):
        if needle in l:
            return n, l.index(needle) + needle.index(token) + 1
    raise SystemExit("compare-faults.py: %r not found in %s" % (needle, path))


transcript, hosted_dir, program_c = sys.argv[1:4]
lines = open(transcript).read().split("\n")
m = re.search(r"cg_revision\[32\] = \{(.*?)\};", open(program_c).read(), re.S)
rev = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))
runs = [int(l.split()[1]) for l in lines if re.match(r"^run \d+$", l)]
check(runs == list(range(12)), "runs 0 to 11 appear once each, in order", repr(runs))
check("runs: 11 faulted, then one entry returned" in lines and lines[-1] == "" and lines[-2].startswith("runs: 11"),
      "the loop ended at run 11, which returned normally")
call_ln, call_col = locate("src/main_faults.ci", "probes.run(args);", "run")
for i, (code, op, needle, token) in enumerate(TABLE):
    tag = "run %d (%s)" % (i, op)
    try:
        k = lines.index("run %d" % i)
        announced = int(lines[k + 1].split()[2])
        raw = bytes.fromhex(lines[k + 2])
        check(lines[k + 1] == "fault: cint-core-1/fault/v2 %d bytes" % announced and len(raw) == announced,
              "%s: header and %d hex bytes agree" % (tag, announced), lines[k + 1])
        r = decode(raw)
    except (ValueError, IndexError) as e:
        check(False, "%s: record present and decodable" % tag, repr(e))
        continue
    ln, col = locate("src/probes.ci", needle, token)
    check(r["code"] == code and r["operation"] == op, "%s: code %d, operation %s" % (tag, code, op), "%r %r" % (r["code"], r["operation"]))
    check(r["position"] == ("src/probes.ci", ln, col), "%s: position src/probes.ci:%d:%d" % (tag, ln, col), repr(r["position"]))
    check(r["stack"][:1] == [("src/main_faults.ci", call_ln, call_col)], "%s: stack starts at the call of probes.run" % tag, repr(r["stack"][:1]))
    if i == 10:
        check(r["operands"] == [] and r["exact"] is None and r["limit"] == (0x14, (1000000).to_bytes(8, "little")),
              "%s: no operands, no exact, limit I64 1000000 (the kernel's allowance)" % tag, repr((r["operands"], r["limit"])))
    check(r["revision"] == rev and r["srcmap"] is None and not r["address_present"], "%s: revision of the emitted program, no source map, no address" % tag)
    if i <= 9:
        hosted = open(os.path.join(hosted_dir, "rec%d.bin" % i), "rb").read()
        check(raw == hosted, "%s: kernel record is byte-identical to the hosted runtime's (%d bytes)" % (tag, len(raw)),
              "%d vs %d bytes" % (len(raw), len(hosted)))
sys.exit(fail)
