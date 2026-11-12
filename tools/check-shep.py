#!/usr/bin/env python3
"""check-shep.py TRANSCRIPT TWIN_ROOT

Checks the transcript of the shep flavor (K4.5). Each "net N q Q:" line carries the number of
turns, a digest of the schedule and a root of the tasks' event logs.
  before the runs: the kernel read the page table and found 12 of 12 guard pages (two under each
    of 3 task stacks and 3 IST stacks) not present and 6 of 6 stacks with their first page present.
  net 0 (a network that follows the rules): 7 runs under 7 fuel quanta; one root in all of them
    and it is TWIN_ROOT, which the hosted runtime computed with no scheduler; 7 different schedule
    digests (the runs really did interleave differently, so the single root is not a consequence
    of one schedule); the root is not the root of an empty log. Two of the runs print their turns:
    the digest is recomputed here from them (it is a function of what is printed), each task's
    fuel never goes down, each task's quantum turns end in a later window of the quantum than the
    one before (and the k-th one at a count of at least k times the quantum), at least one turn of each
    run ends by the quantum, and every task ends once, as its last turn.
  net 1 (the control: the receiver takes whichever channel has a value): at least 2 different
    roots, so the same checks, on a network that breaks the rule, fail.
  net 2: both runs end in a deadlock that names task 1 and task 2.
  net 3: task 1 receives on a channel it is not the receiver of and task 2 sends on one it is not the
    sender of: host.error.chan_recv and host.error.chan_send, code 10, one I64 operand 2
    (CINT_REFUSED), at the call in src/main_shep.ci, the same bytes in both runs.
  net 4: tasks 1 and 2 each count with a module variable. The context of each task has its
    own copy, so each logs the counts 1 to 24: the root is computed here with hashlib, from that
    rule and nothing the kernel printed, and it is the root of both runs (2 quanta). Shared
    copies would interleave the counts.
  net 5: task 1 runs 28,672 bytes of frames on a 16 KiB stack and faults, in both runs, with the
    same record: code 10, host.error.task_stack, the one operand I64 1 (the task number). The
    record has no address and no offset, since where the first touch lands depends on the size of
    the compiler's frames. Tasks 2 and 3 end normally (3 turns).
  net 6: a probe runs task 2's stack into its guard pages and returns: the record is the one a
    stack overflow of the boot stack has (host.error.trap_stack, vector 14, the error code of a
    write to a page that is not present, an offset of 8,184 in the two guard pages, IST 3), and
    the same bytes in both runs.
  net 7: every task starts with 64 bytes of stack, so each overflows before any cint call is
    live: three records host.error.task_stack, operands I64 1, 2, 3, a position that encodes, no
    stack, the same bytes in both runs.
  net 8: task 1 calls task_quantum, an extern of the kernel: host.error.task_quantum, status 2, at
    the call in src/main_shep.ci, the same bytes in both runs.
Prints PASS or FAIL per check; exits 1 on any FAIL."""
import hashlib
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


text = open(sys.argv[1]).read()
twin = sys.argv[2].strip()
SRC = open("src/main_shep.ci").read().split("\n")
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
I64 = lambda v: (0x14, v.to_bytes(8, "little"))  # noqa: E731
U64 = lambda v: (0x24, v.to_bytes(8, "little"))  # noqa: E731
runs = {}
for m in re.finditer(r"^net (\d) q (\d+): turns (\d+) sched ([0-9a-f]{64}) root ([0-9a-f]{64})$", text, re.M):
    runs.setdefault(int(m[1]), []).append((int(m[2]), int(m[3]), m[4], m[5]))
REC = r"fault: cint-core-1/fault/v2 (\d+) bytes\n([0-9a-f]+)\n"

check("\nguard pages not present, of 12: 12\nstack pages present, of 6: 6\n" in text,
      "the kernel read the page table: 12 of 12 guard pages not present, 6 of 6 stack pages present")

n0, n1 = runs.get(0, []), runs.get(1, [])
QS = [0, 1, 250, 500, 1000, 2000, 8000]
check(len(n0) == 7 and [r[0] for r in n0] == QS, "net 0: seven runs, under the quanta %s" % QS, "got %s" % [r[0] for r in n0])
check(len({r[3] for r in n0}) == 1 and n0 and n0[0][3] == twin,
      "net 0: one root in all 7 runs, and it is the hosted twin's (%s...)" % twin[:12],
      "roots %s, twin %s" % (sorted({r[3][:12] for r in n0}), twin[:12]))
check(len({r[2] for r in n0}) == 7, "net 0: seven different schedule digests (%d)" % len({r[2] for r in n0}),
      "only %d" % len({r[2] for r in n0}))
check(len({r[1] for r in n0}) >= 4, "net 0: the number of turns varies with the quantum (%s)" % sorted({r[1] for r in n0}))
check(n0 and n0[0][3] != EMPTY, "net 0: the root is not the root of an empty log")

traces = re.findall(r"((?:turn \d+ \d+ \d+\n)+)net 0 q (\d+): turns (\d+) sched ([0-9a-f]{64})", text)
ok, why = len(traces) == 2, "%d traced runs" % len(traces)
for block, q, turns, digest in traces:
    q = int(q)
    rows = [tuple(int(x) for x in l.split()[1:]) for l in block.strip().split("\n")]
    h = hashlib.sha256()
    for task, st, fuel in rows:
        h.update(bytes([task, st]) + fuel.to_bytes(8, "little"))
    if len(rows) != int(turns) or h.hexdigest() != digest:
        ok, why = False, "q %d: digest recomputed from %d printed turns is %s, printed %s" % (q, len(rows), h.hexdigest()[:12], digest[:12])
    for t in range(3):
        mine = [r for r in rows if r[0] == t]
        if [r[2] for r in mine] != sorted(r[2] for r in mine):
            ok, why = False, "q %d task %d: fuel goes down" % (q, t)
        quantum = [r[2] for r in mine if r[1] == 5]
        wins = [f // q for f in quantum]
        if any(b <= a for a, b in zip(wins, wins[1:])) or any(f < (k + 1) * q for k, f in enumerate(quantum)):
            ok, why = False, "q %d task %d: quantum turns end at %s" % (q, t, quantum[:6])
        if not mine or mine[-1][1] != 1 or sum(1 for r in mine if r[1] == 1) != 1:
            ok, why = False, "q %d task %d does not end once, last" % (q, t)
    if not any(r[1] == 5 for r in rows):
        ok, why = False, "q %d: no turn ended by the quantum" % q
check(ok, "net 0: the digest of the two traced runs is recomputed from their printed turns, and their quantum turns obey the rule", why)

check(len(n1) == 7 and len({r[3] for r in n1}) >= 2,
      "net 1 (control): the roots differ with the schedule (%d different in 7 runs), so the check can fail" % len({r[3] for r in n1}),
      "%d runs, %d roots" % (len(n1), len({r[3] for r in n1})))

h = hashlib.sha256()
for t in (0, 1):
    for i in range(24):
        h.update(bytes([t]) + i.to_bytes(2, "little") + bytes([4]) + (i + 1).to_bytes(8, "little"))
n4 = runs.get(4, [])
check(len(n4) == 2 and {r[3] for r in n4} == {h.hexdigest()} and len({r[1] for r in n4}) == 2,
      "net 4: two runs with different turns, and both roots are the one computed from 'each task counts 1 to 24' (module state is not shared)",
      "%d runs, roots %s, want %s" % (len(n4), sorted({r[3][:12] for r in n4}), h.hexdigest()[:12]))

dead = re.findall(r"^deadlock: waiting: task 1 task 2\nnet 2 q (\d+): deadlock$", text, re.M)
check(dead == ["0", "1"], "net 2: both runs end in a deadlock naming task 1 and task 2", "got %s" % dead)


def records(net, tasks):
    """The records printed before the 'net N' line, per run: [(q, [(task, bytes)])]"""
    pat = r"".join(r"task %d faulted\n" % t + REC for t in tasks) + r"net %d q (\d+): turns" % net
    out = []
    for m in re.finditer(pat, text):
        g = m.groups()
        out.append((g[-1], [bytes.fromhex(g[2 * i + 1]) for i in range(len(tasks))], [int(g[2 * i]) for i in range(len(tasks))]))
    return out


def same_in_both(rs):
    return len(rs) == 2 and [r[0] for r in rs] == [rs[0][0], rs[1][0]] and rs[0][1] == rs[1][1]


def line_has(position, needle):
    return position[0] == "src/main_shep.ci" and needle in SRC[position[1] - 1]


r3 = records(3, [1, 2])
check(same_in_both(r3), "net 3: tasks 1 and 2 faulted in both runs and the records are the same bytes", "%d runs" % len(r3))
if r3:
    a, b = (decode(x) for x in r3[0][1])
    check(all(len(x) == n for x, n in zip(r3[0][1], r3[0][2])), "net 3: the announced lengths are the records'")
    check(a["code"] == 10 and a["operation"] == "host.error.chan_recv" and a["operands"] == [I64(2)] and line_has(a["position"], "taskapi.chan_recv(0)")
          and b["code"] == 10 and b["operation"] == "host.error.chan_send" and b["operands"] == [I64(2)] and line_has(b["position"], "taskapi.chan_send(0, 1)"),
          "net 3: task 1 is refused chan_recv and task 2 chan_send, code 10, one I64 operand 2 (CINT_REFUSED), at their calls in src/main_shep.ci",
          str((a["operation"], a["operands"], a["position"], b["operation"], b["operands"], b["position"])))

r5 = records(5, [1])
check(same_in_both(r5) and [r[0] for r in r5] == ["0", "1"], "net 5: task 1 faulted in both runs with the same record bytes", "%d runs" % len(r5))
if r5:
    x = decode(r5[0][1][0])
    check(x["code"] == 10 and x["operation"] == "host.error.task_stack" and x["operands"] == [I64(1)],
          "net 5: code 10, host.error.task_stack, the one operand I64 1", str((x["code"], x["operation"], x["operands"])))
check(sorted(r[1] for r in runs.get(5, [])) == [3, 3], "net 5: tasks 2 and 3 end normally (3 turns in each run)")

recs6 = re.findall(r"^probe record: ([0-9a-f]+)$", text, re.M)
check(len(recs6) == 2 and recs6[0] == recs6[1], "net 6: the probe returned a record in both runs, the same bytes", "%d records" % len(recs6))
if recs6:
    r6 = decode(bytes.fromhex(recs6[0]))
    want = [I64(14), U64(2), U64(8184), U64(3)]
    check(r6["code"] == 10 and r6["operation"] == "host.error.trap_stack" and r6["operands"] == want,
          "net 6: host.error.trap_stack, vector 14, error 2, offset 8184 in the guard pages, IST 3", str((r6["operation"], r6["operands"])))

r7 = records(7, [1, 2, 3])
check(same_in_both(r7) and [r[0] for r in r7] == ["0", "1"], "net 7: tasks 1, 2 and 3 faulted in both runs, the same bytes", "%d runs" % len(r7))
if r7:
    ds = [decode(x) for x in r7[0][1]]
    check(all(d["code"] == 10 and d["operation"] == "host.error.task_stack" and d["operands"] == [I64(i + 1)] and d["stack"] == []
              and d["position"][0] == "src/main_shep.ci" for i, d in enumerate(ds)),
          "net 7: host.error.task_stack with the operands I64 1, 2, 3, no stack, and a position that encodes",
          str([(d["operation"], d["operands"], d["stack"], d["position"]) for d in ds]))

r8 = records(8, [1])
check(same_in_both(r8) and [r[0] for r in r8] == ["0", "1"], "net 8: task 1 faulted in both runs, the same bytes", "%d runs" % len(r8))
if r8:
    x = decode(r8[0][1][0])
    check(x["code"] == 10 and x["operation"] == "host.error.task_quantum" and x["operands"] == [I64(2)] and line_has(x["position"], "taskapi.task_quantum(0)"),
          "net 8: a task is refused task_quantum (an extern of the kernel), status 2, at its call", str((x["operation"], x["operands"], x["position"])))

check(text.endswith("shep: done\nruns: 0 faulted, then one entry returned\n"), "the run loop ends after one entry that returned normally")
sys.exit(fail)
