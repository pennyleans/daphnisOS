#!/usr/bin/env python3
"""diverge.py A B [--final]: where two K5 runs first part, from the commit lines they printed.

A K5 kernel prints one line per commit: its number, the task that ran, the root of the state tree
and the four leaves (tasks 0, 1, 2 and the kernel's tables). Two runs that agree print the same
lines. This names the first commit at which they differ, the task that ran in it, and which leaves
differ (a task's state, or the kernel's tables).

  diverge.py A B           compare commit by commit (right for two runs of one schedule: a recording
                           and its replay at the same quantum, a run and its restore)
  diverge.py A B --final   compare only the last commit of each run, leaf by leaf (right for runs under
                           different quanta, whose commits do not line up: it says which task's final
                           state, or the kernel's tables, differ)

A and B are transcripts (or files of C lines). Exit status 0 if the runs agree, 1 if they part (the
answer is printed), 2 on a usage error."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k5lib  # noqa: E402

NAMES = ["task 0 (state)", "task 1 (state)", "task 2 (state)", "kernel tables"]


def load(path):
    return k5lib.commits(open(path).read())


def by_commit(a, b):
    for i in range(min(len(a), len(b))):
        if a[i][2:] != b[i][2:] or a[i][1] != b[i][1]:
            diff = [NAMES[k] for k in range(4) if a[i][3][k] != b[i][3][k]]
            print("first divergence at commit %d: task %d ran in A, task %d in B; differing leaves: %s" % (a[i][0], a[i][1], b[i][1], ", ".join(diff) or "none (roots differ)"))
            print("  root A %s" % a[i][2])
            print("  root B %s" % b[i][2])
            return 1
    if len(a) != len(b):
        print("the runs agree on %d commits, then %s ends" % (min(len(a), len(b)), "B" if len(a) > len(b) else "A"))
        return 1
    print("the runs agree on all %d commits" % len(a))
    return 0


def final(a, b):
    if not a or not b:
        print("a run printed no commits")
        return 1
    x, y = a[-1], b[-1]
    diff = [NAMES[k] for k in range(4) if x[3][k] != y[3][k]]
    if not diff:
        print("the final states agree (root %s)" % x[2])
        return 0
    print("the final states differ in: %s" % ", ".join(diff))
    return 1


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    a, b = load(args[0]), load(args[1])
    sys.exit((final if "--final" in sys.argv else by_commit)(a, b))
