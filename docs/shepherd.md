# K4.5: the shepherd

The goal of this stage: a result that does not depend on when a task's turn ended. The plan
(drafted by l before this stage) was to close the three doors through which
a schedule can change a result (shared memory, message order, effect order) and to journal what
cannot be closed. This file says what was built, what is checked, and what is deliberately not
here. Nothing is claimed that `check.sh` does not test.

## The three doors

| Door | What closes it | What checks it |
| --- | --- | --- |
| Shared memory | cint has no pointers; each task context has a module-state table and pool of its own (`rt/task.c`: `blocks`, `pool`), made anew when the task is; a task may call only the externs on `task_allowed` in `rt/host.c` (the console service, its channels, its event log, the yield, its own stack probe) and any other is refused with `host.error.<name>`. What tasks share is the channel rings and the event logs, both in `rt/`, reached only through those externs | `net 4`: two tasks count with one module variable and each logs 1 to 24; the root is computed in Python from that rule (mutation: share the table, or let a task call a kernel extern in that net, and it fails). `net 8`: a task calling `task_quantum` is refused. `check.sh` also asserts that the only emitted C file that asks for module state is `src/ownstate.c` |
| Message order | a channel has one sender and one receiver, fixed by `chan_open`; a receive names its channel and blocks (`rt/chan.c`) | `net 0` (below) gives one root under 7 schedules, and the hosted twin, which has no scheduler, gives the same root. `net 1` is the control: its receiver takes whichever channel has a value, and its roots differ with the schedule, so the same check can fail. `net 3`: a task that is not the receiver (sender) of a channel faults with `host.error.chan_recv` (`chan_send`) |
| Effect order | each task's visible effects are events `(kind, value)` in a log of its own, placed by `(task, sequence number)`; the root is the SHA-256 of the logs in that order | `net 0` again: the root covers every event, and a mutation that drops or truncates an event changes it |

The transcript prints what depends on the schedule (a digest of it) beside what does not (the
root), so the gate can require that the first varies and the second does not. A root that is the
same under one schedule proves nothing; here it is the same under 7 different ones. The digest is
itself checked: two runs print their turns, and `tools/check-shep.py` recomputes the digest from them
and checks the turns against the quantum rule (what stays golden-only is the exact count at which a turn ends).

## The fuel quantum, with no change to cintc

`task_quantum(q)` makes a task's turn end at the first host call after its fuel count has reached
the next multiple of `q` (the boundary moves to the next multiple above the count at each turn's end). The scheduler (cint, `src/shep.ci`) runs the tasks round robin, and stamps a digest of
each turn: the task, why the turn ended and the task's fuel count then.

Why this is deterministic: cint charges fuel by its own semantics (SPEC-01 10.2), not by machine
instructions, and `rt/host.c` reads the count in a context head that is exact at a host call. The
digest is the same bytes on gcc and clang at `-O0`, `-O1`, `-O2`, `-O3` and `-Os` (10 builds,
`check.sh`). No timer is involved: a turn can only end where the task asks the runtime for
something, so the interleaving is a function of the program.

What was tried first and does not work: a soft `fuel_limit`, so that the inline
`cint_fuel_charge` calls `cint_rt_fault_fuel` at a quantum boundary, which yields and returns true.
The generated code ignores the return value: a function that has no calls keeps its fuel in
locals (`fu`, `fcap`, EMIT-28) and on a failed charge does `(void)cint_fuel_charge(...); goto
fault;`, so the task would end as "done" with half its output and no record. Two advisors found
this independently from the emitted C of this tree (`build/.../taskwork.c`). A yield inside such a
function needs a cintc change; none is needed for what is built here, because output only happens
at host calls. `docs/cint-gaps.md` item 13 has the reproducer; it is filed as pennyleans/cint#512.

What this does not do: a task that computes without a host call is never interrupted (its real
fuel limit still stops it). That cannot change a result, since the task shares nothing; it only
matters for latency. The timer preemption of K4 (`preempt`) is unchanged and is not part of this
stage's claim.

## The networks (`src/shep.ci`, `src/main_shep.ci`)

Each is run from the kernel entry under quanta 0 (none), 1, 250, 500, 1000, 2000 and 8000 for
nets 0 and 1 (seven different schedules), and under two quanta for the others (net 4: 0 and 20; the rest 0 and 1).

| Net | What | Checked |
| --- | --- | --- |
| 0 | tasks 1 and 2 send 24 SHA-256 round values each on their own channel (capacity 2, so senders block), task 3 receives channel 0 then channel 1, each round, and folds in order | one root in 7 runs, equal to the hosted twin's (`tests/shep_twin.ci`, `src/shepwork.ci` `reference_root`: it re-derives the event sequence by hand and shares only `round`, `fold`, `init_block` and `root_event` with the tasks); 7 different schedule digests; the digest of two printed traces recomputed |
| 1 | as 0, but task 3 takes whichever channel has a value (`chan_recv_any`) | at least 2 different roots in 7 runs (the control) |
| 2 | tasks 1 and 2 each wait for the other | both runs end in `deadlock: waiting: task 1 task 2`, found by the scheduler when a whole pass runs nothing |
| 3 | task 1 receives on a channel it is not the receiver of, task 2 sends on one it is not the sender of | `task 1 faulted` and `task 2 faulted`, the records `host.error.chan_recv` and `host.error.chan_send` with status 2 (`CINT_REFUSED`), same bytes in both runs |
| 4 | module variable per task | above |
| 5 | task 1 nests seven 4,096 byte frames on a 16 KiB stack | `task 1 faulted`, the record `host.error.task_stack` with the task number; tasks 2 and 3 finish (3 turns) |
| 6 | a probe runs task 2's stack into its guard pages and returns | the trap record `host.error.trap_stack`: vector 14, error 2, offset 8184 in the two guard pages, IST 3, and the stack of the task, not the kernel |
| 7 | every task starts with 64 bytes of stack (`task_stack_budget`) | three `task_stack` records, the first call of each task falling in its guard before its program began: the position is a placeholder site of the root module, which encodes, and the stack is empty |
| 8 | task 1 calls `task_quantum` | the record `host.error.task_quantum`, status 2: the extern belongs to the kernel |

`net 1` is a control and not a feature: `chan_recv_any` exists so that the gate has a program that
breaks the rule, and a network must not use it.

## QEMU `-icount` (the plan's G5): a finding

`-icount shift=0` makes one binary reproducible and does not make it portable. The `preempt` image
(timer ticks, quantum 3) was changed in a scratch copy to print its preemption count, and run
under TCG:

| Build | no `-icount`, 8 runs | `-icount shift=0,sleep=off` |
| --- | --- | --- |
| gcc `-O2` | 4 runs 4 preemptions, 4 runs 5 | 8 of 8 runs: 6 preemptions, 22 ticks |
| clang `-O2` | not run | 3 of 3: 7, 25 |
| gcc `-O0` | not run | 3 of 3: 232, 700 |
| clang `-O0` | not run | 3 of 3: 233, 703 |

So under `-icount` a timer interrupt lands at the same instruction on every run of one binary, and
at a different place in a binary built by another compiler or at another optimization level (the
count counts machine instructions). The fuel quantum is the portable clock; `-icount` is a useful
instrument for the K4 `preempt` image and was not added to the gate, since the transcript of that
image omits the interleaving on purpose. Measured once, on QEMU 11.1.2, with the command above.

## Hardening carried from K3

* A guard of two pages under every task stack and every IST stack, not present in the boot page
  table (`rt_guard_pages`, `rt/phys.c`). `src/guards.ci` reads the page table through the view shim
  and the gate requires 12 of 12 guard pages absent and the 6 stack pages next to them present.
* `-fstack-clash-protection` for everything. Found by the test: at `-O2` the compiler inlined a chain
  of calls into one frame of 28,672 bytes and a single subtraction stepped over a guard of two
  pages; without the flag the first touch landed in the next object. Mutation: remove the flag, `net 5` fails.
* A stack overflow of a task, outside a probe, is the task's fault (`rt_task_stack_overflow`,
  delivered on the IST stack of the #PF), not a panic. Its record names the task and nothing else (its
  position is the first call of the entry, or a placeholder site if none is live):
  where the first touch lands depends on the compiler's frames, and so does the fuel the task had
  used, which is stamped as 0.
* A trap record is made from the context that is running. It used the kernel's (`rt_ctx`), so a
  probe in a task recorded the kernel's call stack, which differs from one run to the next.
* The task stack is 128 KiB (the budget of the boot stack, `docs/runtime.md`), 16 KiB in the shep
  flavor so that the test can overrun it.
* W^X for the first 2 MiB was not done in K4.5; K5 did it (`docs/memory.md`).

## Known limits (from review, not fixed)

* `chan_open` does not refuse while a task waits on that channel, and a woken task does not re-check
  its end; the scheduler always re-creates tasks after opening channels, so it is not reachable.
* A task blocked inside a host call has its stack dropped when it is made anew; nothing there needs
  unwinding (no heap, no locks), and the context is cleared.
* `rt_host_site` was a global that a woken task finds changed; since K5 it is `ctx->host_site`, one per context.
* A probe in a task whose `call` pushes its return address into the guard has a RIP outside the probe
  block and panics ("fault outside a probe"). The task's own overflow outside a probe is the case handled.
* The channel rings and counters are not tick safe: a channel operation in a preemptible task panics
  (`rt/chan.c`); no image combines the timer with channels.
* The quantum rule is checked by recomputation and invariants; the exact count at which a turn ends (a
  boundary one count late, or after the charge) is pinned by the golden transcript only.

## What is not here, on purpose

* The journal, commit points, the Merkle state tree and kill-and-restore: K5 (`docs/snapshot.md`). Without a
  `select` and without input there is no choice to journal, and a snapshot needs the K5 machinery. Both
  advisors' reviews said to leave these to K5.
* Single owner per page: K5 (`docs/snapshot.md` section 6). Door 1 is closed for cint tasks by construction
  (above) and, in the K5 flavor, by page tables as well.
* Foreign (non-cint) tasks, so the fuel quantum is cint only, as the plan said.
* A hosted twin for the quantum itself. cint's hosted runtime cannot be given a fuel allowance
  (#508); the twin computes the root, not the schedule.
