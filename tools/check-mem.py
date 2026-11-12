#!/usr/bin/env python3
"""check-mem.py TRANSCRIPT CINT_PROGRAM_C

Checks the transcript of the mem flavor. Runs 0 to 5 are canonical faults of the view shim
(the null page, an address outside the windows, a write to the boot PML4, a misaligned range, a
wrapping range, and a vm_store64 into the identity map): code 10, operation host.error.<extern>, the
one operand I64 2 (CINT_REFUSED), at the call in src/main_mem.ci, called from main. Run 6 is
the demo. In it: three #PF trap records (a store to a read-only page, a fetch from a
no-execute page, a load from an unmapped page) decoded against a table (error codes 3, 0x11
and 0, CR2 the virtual address, IST 3) with the call site and the two-entry stack searched in
the source; the refusal lines; and the hash lines: the hash before equals the hash after each
refused request (computed here from the transcript, not trusted from the 'yes' line), the
empty and final hashes differ from the others, and the page-table frames are the only ones
left. Prints PASS or FAIL per check; exits 1 on any FAIL."""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faultrec import decode  # noqa: E402

I64, U64 = 0x14, 0x24
SRC = "src/main_mem.ci"
fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


def find(needle, token, nth=1):
    seen = 0
    for n, l in enumerate(open(SRC).read().split("\n"), 1):
        if needle in l:
            seen += 1
            if seen == nth:
                return n, l.index(needle) + needle.index(token) + 1
    raise SystemExit("check-mem.py: %r not found in %s" % (needle, SRC))


transcript, program_c = sys.argv[1:3]
lines = open(transcript).read().split("\n")
m = re.search(r"cg_revision\[32\] = \{(.*?)\};", open(program_c).read(), re.S)
rev = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))


def record_after(index):
    announced = int(lines[index].split()[2])
    raw = bytes.fromhex(lines[index + 1])
    ok = lines[index] == "fault: cint-core-1/fault/v2 %d bytes" % announced and len(raw) == announced
    return ok, announced, decode(raw)


check([l for l in lines if re.match(r"^run \d+$", l)] == ["run %d" % i for i in range(7)], "runs 0 to 6, once each, in order")
check(lines[-2].startswith("runs: 6 faulted, then one entry returned") and lines[-1] == "", "the loop ended at run 6, which returned normally")

# runs 0 and 1: refusals of the view shim, as host.error faults
for run, op, needle, token, callee in ((0, "phys_read8", "phys.phys_read8(0 as U64, buf);", "phys_read8", "bad_null();"),
                                       (1, "phys_write64", "phys.phys_write64(0x00200000 as U64, w);", "phys_write64", "bad_window();"),
                                       (2, "phys_write64", "phys.phys_write64(trap.vm_root(), w);", "phys_write64", "bad_table();"),
                                       (3, "phys_read64", "phys.phys_read64(0x02000004 as U64, w);   // misaligned, inside the pool", "phys_read64", "bad_align();"),
                                       (4, "phys_read64", "phys.phys_read64(0xFFFFFFFFFFFFFFF8 as U64, w);", "phys_read64", "bad_wrap();"),
                                       (5, "vm_store64", "trap.vm_store64(0x00100000 as U64, 1 as U64);", "vm_store64", "bad_vm();")):
    k = lines.index("run %d" % run)
    ok, n, r = record_after(k + 1)
    check(ok, "run %d: header and %d hex bytes agree" % (run, n))
    ln, col = find(needle, token)
    cln, ccol = find(callee, callee[:-3])
    check(r["domain"] == "cint-core-1/fault/v2" and r["code"] == 10 and r["operation"] == "host.error." + op,
          "run %d: code 10, operation host.error.%s" % (run, op), "%r %r" % (r["code"], r["operation"]))
    check(r["operands"] == [(I64, struct.pack("<q", 2))] and r["exact"] is None and r["limit"] is None,
          "run %d: one operand, I64 2 (CINT_REFUSED), no exact or limit" % run, repr(r["operands"]))
    check(r["position"] == (SRC, ln, col) and r["stack"] == [(SRC, cln, ccol)],
          "run %d: position %s:%d:%d, called from %s:%d:%d" % (run, SRC, ln, col, SRC, cln, ccol), "%r %r" % (r["position"], r["stack"]))
    check(r["revision"] == rev, "run %d: revision equals cg_revision of the emitted program" % run)

# the three #PF records of run 6
demo_ln, demo_col = find("        demo();", "demo")
pd_ln, pd_col = find("    paging_demo();", "paging_demo")
stack = [(SRC, demo_ln, demo_col), (SRC, pd_ln, pd_col)]
for label, needle, token, error, cr2 in (
        ("write to a read-only page", "trap.vm_store64(VA0, 0xDEAD as U64);", "vm_store64", 3, 0x40000000),
        ("fetch from a no-execute page", "trap.vm_exec(VA1);", "vm_exec", 0x11, 0x40001000),
        ("load from an unmapped page", "_ = trap.vm_load64(VA0);", "vm_load64", 0, 0x40000000)):
    try:
        k = lines.index(label)
        if label.startswith("fetch"):
            ln, col = find(needle, token, 2)
        else:
            ln, col = find(needle, token)
        ok, n, r = record_after(k + 1)
    except (ValueError, IndexError) as e:
        check(False, "%s: record present" % label, repr(e))
        continue
    check(ok, "%s: header and %d hex bytes agree" % (label, n))
    want = [(I64, struct.pack("<q", 14)), (U64, struct.pack("<Q", error)), (U64, struct.pack("<Q", cr2)), (U64, struct.pack("<Q", 3))]
    check(r["code"] == 10 and r["operation"] == "host.error.trap_pf" and r["operands"] == want,
          "%s: trap_pf, vector 14, error %#x, CR2 %#x, IST 3" % (label, error, cr2), "%r %r %r" % (r["code"], r["operation"], r["operands"]))
    check(r["position"] == (SRC, ln, col) and r["stack"] == stack, "%s: position %s:%d:%d, stack main > demo > paging_demo" % (label, SRC, ln, col),
          "%r %r" % (r["position"], r["stack"]))
    check(r["revision"] == rev and r["exact"] is None and r["limit"] is None and r["srcmap"] is None, "%s: revision, no exact, limit or source map" % label)

# lines of the demo
def value(prefix):
    for l in lines:
        if l.startswith(prefix):
            return l[len(prefix):]
    return None


def hashes():
    got = [l.split()[-1] for l in lines if l.startswith("hash ")]
    return got


h = hashes()
check(len(h) == 6 and all(re.fullmatch(r"[0-9a-f]{64}", x) for x in h), "six allocator hashes of 64 hex digits", repr(h))
if len(h) == 6:
    check(h[1] == h[2], "hash before the frame refusals equals the hash after")
    check(h[3] == h[4], "hash before the refused object equals the hash after")
    check(len({h[0], h[1], h[3], h[5]}) == 4, "the empty, allocated, arena and final hashes all differ")
for label, want in (("ram: MiB ", "128"), ("pool 32 MiB to 96 MiB usable: ", "yes"), ("free after refusals: ", "16365"), ("refused: free count plus one ", "-1"),
                    ("free at the end: ", "16383"), ("refused: too many ", "-1"), ("refused: zero ", "-2"),
                    ("refused: not owned ", "-3"), ("refused: off the pool ", "-2"), ("refused: object too big ", "-14"),
                    ("frame refusals changed nothing: ", "yes"), ("heap refusal changed nothing: ", "yes"),
                    ("pattern written through the mapping, read through the physical window: ", "yes"),
                    ("pattern read through the mapping: ", "yes"), ("the refused store left the word unchanged: ", "yes"),
                    ("a fetch from the executable page returned: ", "yes"), ("pattern after the remap: ", "yes"), ("a load through the mapping before the unmap works: ", "yes"),
                    ("map over a mapped page is refused: ", "-24"), ("map outside the region is refused: ", "-22"),
                    ("unmap of an unmapped page is refused: ", "-25"), ("arena object written and read back: ", "yes"),
                    ("arena: a request of 4,097 bytes is refused: ", "-14"), ("the refused request changed nothing: ", "yes"),
                    ("frames in use at the end (the bitmap, page directory and table): ", "3")):
    check(value(label) == want, "%s%s" % (label, want), repr(value(label)))
fh = value("final state hash: ")
check(fh is not None and re.fullmatch(r"[0-9a-f]{64}", fh) is not None and "mem: done" in lines, "a final state hash and the closing line")
sys.exit(fail)
