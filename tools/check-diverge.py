#!/usr/bin/env python3
"""check-diverge.py A B: tests tools/diverge.py on two recordings of one network whose scripts
differ in one byte (the planted mutation). Python finds, from the journals alone, the first entry
that differs (a task and its sequence number) and the first commit line that follows it in A; the
divergence finder must name that commit and that task, and name that task's leaf and the kernel's
tables as the ones that differ, and must say the runs agree when a run is compared with itself."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k5lib  # noqa: E402

fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


a, b = open(sys.argv[1]).read(), open(sys.argv[2]).read()
ja = k5lib.journal_lines(a)
jb = k5lib.journal_lines(b)
first = next((i for i in range(min(len(ja), len(jb))) if ja[i][0] != jb[i][0]), None)
check(first is not None, "the two journals differ (the script's byte is in an input entry)")
here = os.path.dirname(os.path.abspath(__file__))
run = lambda *args: subprocess.run([sys.executable, os.path.join(here, "diverge.py"), *args], capture_output=True, text=True)  # noqa: E731
if first is not None:
    pos = a.index("J %s %s\n" % (ja[first][0].hex(), ja[first][1].hex()))
    nxt = k5lib.commits(a[pos:])[0]
    task = ja[first][0][0]
    r = run(sys.argv[1], sys.argv[2])
    want = "first divergence at commit %d: task %d ran in A, task %d in B; differing leaves: task %d (state), kernel tables" % (nxt[0], task, task, task)
    check(r.returncode == 1 and r.stdout.startswith(want),
          "diverge.py names commit %d, where task %d first acts on the planted byte, and its leaf and the kernel's tables" % (nxt[0], task),
          r.stdout)
r = run(sys.argv[1], sys.argv[1])
check(r.returncode == 0 and "agree on all" in r.stdout, "a run compared with itself agrees", r.stdout)
r = run(sys.argv[1], sys.argv[2], "--final")
check(r.returncode == 1 and "differ in" in r.stdout, "--final names the leaves that differ at the end", r.stdout)
sys.exit(fail)
