# The freestanding runtime (`rt/`)

The emitted C of every cint program calls `cint_rt_*` functions that the hosted runtime
(`rt/cint_rt.c` of the cint pin, 3,276 lines on libc) provides. `rt/` is the minimal
replacement for a program that has no libc and no allocation: one context for the kernel's
own entry, one more per task (below), and no threads. It
compiles against the pin's own `cint_rt.h` (hash-pinned in `toolchain.pin`); it does not
copy it. Nothing in `rt/` uses floating point, `__int128`, or inline asm.

## Entry points reimplemented, and why

These are the undefined symbols of the emitted C (K0 audit), after the emitted program's own
symbols, over the optimization levels tried. At `-O2` the emitted C references only `memset`
of the four `mem*` functions and not `cint_rt_fault_shift`; `fault_shift` appears at `-O0`,
`-O1` and `-Os`, `memcpy` at `-O0`. `memmove` and `memcmp` are referenced by nothing, but
EMIT-31 allows exactly the four and a compiler may emit any of them:

| Symbol | File | Why emitted C needs it |
| --- | --- | --- |
| `memcpy`, `memmove`, `memset`, `memcmp` | `mem.c` | EMIT-31 allows exactly these four; gcc and clang insert them for array and struct copies and zeroing |
| `cint_program_run_args` | `ctx.c` | the `main` in `cint-program.c` calls it. Here it creates the context, binds externs, runs the entry, and prints the record on a fault |
| `cint_rt_entry_begin`, `cint_rt_entry_end` | `ctx.c` | every module's `cg_*_run` brackets the entry with them (fuel, depth, fault status) |
| `cint_rt_call_enter_slow` | `ctx.c` | the call protocol's slow path (depth and fuel faults) |
| `cint_mem_frame_charge`, `cint_mem_frame_mark`, `cint_mem_frame_release` | `ctx.c` | local arrays are charged against the frame arena; accounting only, the arrays live on the C stack |
| `cint_rt_arg_scalar`, `cint_rt_result_init` | `ctx.c` | build the argument and result values of an `extern` call |
| `cint_rt_arg_view` | `ctx.c` | builds a rank-1 `in` or `out` view argument of an `extern` (the view shim, `docs/memory.md`); a copy of the hosted function, with host memory |
| `cint_rt_state_slow` | `ctx.c` | module state: the first access of a module's variables makes its block from the image, in a static pool; blocks survive a fault (SPEC-03 A-7) |
| `cint_ctx_args`, `cint_program_run_argv` | `ctx.c` | a program whose `main` takes `in U8[_] args`: the run loop below |
| `cint_program_requires` | `ctx.c` | the program's `requires` manifest; recorded (`rt_program_requires`), not used to grant |
| `cint_rt_host_call` | `host.c` | every `extern` call. Looks up the bound row, checks argument and result types, charges a unit of fuel, runs it |
| `cint_rt_fault_arith`, `_shift`, `_narrow`, `_index`, `_fuel` | `fault.c` | the checked operations' fault writers |

`fault.c` also holds the record builder and the canonical encoder (below); `serial.c` is the
raw COM1 sink of the fault path; `trap.c` is K2 and the K3 hardening (`docs/traps.md`);
`phys.c` is the view shim's windows (`docs/memory.md`); `task.c` is the K4 task mechanism;
`start.c` joins the boot stub to `main` and leaves through isa-debug-exit.

Not implemented, because the programs in this tree do not need them: wide integer types
(I128 and up) and their fault writers, `cint_rt_scratch*` (see the stack budget), dispatch,
the print statement (`cint_rt_print_*`: tasks write with `console.write` instead), fixed point,
handles and pools. A program that needs one fails at link
time with an undefined symbol, which the audit would also name. Example: a local `U8[20000]`
fails to link on `cint_rt_scratch*`.

## The run loop, tasks and the console service (K3, K4)

* **Run loop.** A program whose `main` takes `in U8[_] args` is run by `cint_program_run_argv`
  as a loop: entry `i` gets the decimal `i` and a NUL as its argument (as a hosted `-- i` gives),
  a fault ends the entry and its record is printed (`run i`, then the record), and the loop
  goes on with `i + 1`; it ends at the first entry that returns normally. The context is
  cleared between entries (the record is single-use), the module state is kept. Every entry has
  a finite fuel allowance of 1,000,000, so a probe that loops forever ends in a fuel fault. The
  `faults` and `mem` flavors use it; a program without `args` runs once, as in K1.
* **The `faults` flavor** (`src/probes.ci`, `src/main_faults.ci`): entry `i` runs probe `i`. Probes
  0 to 9 are an `I64` add overflow, a `U8` subtraction, an `I32` multiplication, an `I8` negation,
  a division and a remainder by zero, a shift by 32 of a `U32`, a narrowing of 300 to `U8`, an
  index out of bounds, and unbounded recursion (depth, a 6,499-byte record with 255 stack
  entries); probe 10 loops forever (fuel); entry 11 returns, which ends the loop. The hosted twin
  is the same `main_faults.ci` built and run once per `i`; `tools/compare-faults.py` requires
  records 0 to 9 to be byte-identical to the hosted runtime's and checks a table of what each
  must fault with, so a probe that faults the wrong way cannot pass by matching its twin.
* **Tasks** (`rt/task.c`, `arch/x86_64/task.S`, 26 lines of asm). A task is the program's `main`
  run with the argument `id + 1`, on a stack of its own (128 KiB under a guard of two pages, K4.5), with its own `cint_ctx`
  (depth, fuel, call stack and fault record are per context). The mechanism is a callee-saved
  register switch; the policy (create, run, who is next) is cint, `src/sched.ci`. `task_run`
  returns when the task yields, ends, faults or is preempted. Preemption (the `preempt` image,
  `RT_TASK_MODE` 1) ends a turn from the timer interrupt (vector 32) after a quantum of ticks:
  the handler switches back to the scheduler on the task's own stack, so a later switch
  finishes the handler and `iret`s. Interrupts are on only while a task runs; the scheduler and
  the kernel's own entry run with them off. State written by the timer path is stored with
  interrupts off (a store before `cli` once let a tick overwrite a task's `faulted` state and
  lose its record, a defect found by review and verified). Probes and the first access of module
  state panic in a preemptible task, because they use globals shared by every context.
* **Console service** (`host.c`, the five `console/1.*` rows of the pinned `lib/console.ci`).
  The grants of a task are a mask fixed at `task_create` (1 `console.input`, 2 `console.raw`);
  nothing changes it. `read`, `read_line` and `window` need `console.input`, `raw` needs
  `console.raw`, and a call no grant covers returns `denied` (error 1 of
  `console.ConsoleError`), a value of the error union, not a fault (SPEC-07 SEC-CAP-13).
  `write` has no covering capability (OQ-299), so it never returns `denied`; it appends to
  the task's buffer, and the kernel prints the buffers in task order. Input is one canned
  line, `daphnis`.
  The hosted twin (`tests/task_twin.ci`) gives task 2 `--grant console.raw`: with no `--grant`
  the hosted runtime grants the whole manifest (RT-OQ-80), and an empty grant line is refused,
  so a grant that does not cover the call is the way to a hosted `denied`. Two differences from
  the kernel's masks: the twin's task 2 holds `console.raw` (its program never calls `raw`), and
  the twin's task 3 holds only `console.input` where the kernel's holds both.

## K4.5: the quantum, channels and event logs (`rt/task.c`, `rt/chan.c`; `docs/shepherd.md`)

* **`task_run` returns** 0 yielded, 1 done, 2 preempted (timer), 3 faulted (its record is printed),
  4 blocked on a channel, 5 its fuel quantum ended, 6 still blocked and not run (nothing happened),
  -1 no such task. `task_create` makes a task anew when the scheduler is not inside a turn, so a
  task that blocked for good can be dropped; the module state of each task is a table and a 4 KiB pool
  of its own, so nothing is shared and a task made anew starts from the image. A task may call only
  the externs of `task_allowed` (`rt/host.c`); any other row is refused with `host.error.<name>`, status 2.
  `task_stack_budget(bytes)` limits the stack a task made next may use (64 is the least).
* **Fuel quantum.** `task_quantum(q)`: a turn ends at the first host call after the task has used
  `q` more fuel units (`rt_task_quantum_point`, called by `cint_rt_host_call` before it charges
  the call). `fuel_limit` is never touched. A task that computes without a host call is not
  interrupted. See `docs/shepherd.md` for why a soft `fuel_limit` does not work (EMIT-28).
* **Channels** (`chan_open(id, sender, receiver)`, `chan_send`, `chan_recv`): 4 channels of
  capacity 2, one sender task and one receiver task each; a send to a full one and a receive from
  an empty one block the task; a task that is not the end it uses is refused (the record
  `host.error.chan_send` or `chan_recv`, status 2). `chan_recv_any` is the control that breaks the
  rule. A blocked task is not run until its channel can serve it; a whole pass that runs nothing
  is a deadlock, which the cint scheduler names.
* **Event log** (`emit(kind, value)`, `log_len`, `log_kind`, `log_val`): up to 256 events per task,
  in the order the task made them. The root of a run is the SHA-256 of the logs in the order
  (task, sequence number); the schedule digest is a SHA-256 of the turns.
* **`task_net(n)`** makes the second digit of a task's argument, and `task_guard(id)` returns the
  address of its guard pages, which `src/guards.ci` checks in the page table.

## K5: steps, requests, spaces, the state walker (`rt/task.c`, `rt/state.c`; `docs/snapshot.md`)

* **`task_step(id)`** runs one step of a task: its stack is armed again (a fresh frame, the context and the module
  state kept), the CR3 of its address space is loaded, the program's `main` runs once as one entry of the task's
  context, CR3 is the kernel's again. Returns 0 (it ended with a request), 3 (it faulted; the record is printed as
  `task_run` does) or -1. Fuel is per entry, so `fuel_total` adds the steps (`task_fuel_total`).
* **`request(kind, a, b, v)`** (task side) records the step's one request; no request is the fault `host.error.step`
  (position: a placeholder site of the root module, no stack), a second one is refused. The kernel reads it with
  `task_req(id, i)` and puts the answer into the next step's `args` (`task_args_set`, up to 14 bytes after the role
  and network digits).
* **`page_load(slot, i)`, `page_store(slot, i, v)`** (task side): a word of one of 8 private pages, accessed by the
  hardware through the task's CR3 under a probe; a #PF is adopted as the task's fault (`RT_ST_TRAP`,
  `rt_trap_adopt`). **`task_space(id, root)`** (kernel) sets the CR3 of a task (only a frame of the pool).
* **The state walker** (`rt/state.c`): `task_state_size/read` encode the module variables of the `src/ts_` modules
  as little endian values in descriptor order, `task_state_stage/apply` decode; scalars and integer arrays only.
  The descriptor table is the `state` argument of `cint_program_run_argv`, which used to be ignored.
* `rev_byte(i)`: the program's revision (a snapshot of another build is refused). `wx_probe(kind)`: the evidence of
  W^X. `RT_RUN_FUEL`, `RT_TASK_STACK` and `RT_STATE_POOL_BYTES` can be set per flavor (the k5 image: unbounded
  fuel for the kernel's entry, 32 KiB task stacks and a 16 KiB pool, which keeps the `-O0` image under 2 MiB).
  KP-1: the build checks the pool. `tools/check-state-pool.py` reads, from each linked image, every module's state
  record (`cint_state.bytes`, a block of 16-byte units each) and the size of `state_pool`; an image whose blocks
  do not all fit is removed and `make` fails with the sum and the modules, largest first. Before this an image a
  few bytes over built and faulted at boot (`host` `resource`) at the first module past the pool. Each image's
  count is in `state-pool.txt` beside it. A task's own pool (`TASK_POOL`, 4 KiB) is not checked: what a task asks
  for depends on the modules its code reaches.
* A task may call, besides the K4.5 list, `request`, `page_load`, `page_store`; every other row of the table is
  the kernel's. `ctx->host_site` replaces the global `rt_host_site`: the site of the extern call a context is running.

## Where this departs from the hosted runtime

* **One context, static.** `struct cint_ctx` (`rt.h`) starts with `cint_rt_head`, as the
  inline helpers of `cint_rt.h` require.
* **Externs are bound by name at boot** (`rt_host_bind`, `host.c`), against a static table of
  name, parameter count, and type tags. A misspelled extern links and then panics at boot (exit
  63), not at link time. The hosted runtime also compares the effect class and a SHA-256 of
  the canonical signature (SPEC-03 A-10, A-23); this one checks name, count and the type tags
  of arguments and result on each call (and, for a view, its element type and direction), not
  the class or the hash. A row function returns a status; anything but OK becomes the record
  `host.error.<name>` with the status as an `I64` operand, the shape of the hosted runtime.
* **Fault records** are `cint-core-1/fault/v2`, the version the hosted `cint-rt-3` writes for
  every run-time record except `dot.checked.i1024.*` (SPEC-01 IM-149, read through
  `cint_lookup_id`, line 1180). The brief asked for v1 "as close as the
  freestanding path allows"; v1 is what `cint-rt-1` writes and is not what the pinned
  toolchain's hosted runtime writes, so v2 is the one that can match it byte for byte. The
  encoder is the layout of the hosted `cint_fault_encode` with the same field order; it covers
  scalar types I8 to U64, no kernel address (always absent), no source-map digest (absent, as
  in cint-rt-3, RT-OQ-28). The `exact` value is computed on two 64-bit limbs, so there is no
  `__int128`.
* **Printing the record**: on a cint fault, `ctx.c` prints `fault: cint-core-1/fault/v2 N
  bytes` and the record as lowercase hex on COM1, streaming it (count pass, then emit pass), so
  there is no buffer to overflow on a deep stack. The hosted runtime prints a rendered text
  form; the hex line is the canonical bytes themselves. This is the one place the fault path
  is C rather than cint: a faulted entry cannot run more cint code.
* **Tests of the pure modules run on the hosted runtime in its builtin helper mode**
  (`-DCINT_RT_HELPERS_BUILTIN`); the kernel uses the portable helpers. Different helper code
  runs in each; the hosted twin of the fault test compares records, not arithmetic.
* **`rt/mem.c`**: plain byte loops. Nothing here is fast.

## Stack budget

The boot stack is 128 KiB above a guard page, and each task's is 128 KiB above a guard of two
pages (16 KiB in the shep flavor, so a test can overrun it). Emitted C puts a local array on the C
stack when it is at most 4,096 bytes and calls `cint_rt_scratch*` otherwise (not implemented, so
a bigger local array fails at link time).

What checks the total, measured with `cint emit-c` at the pin: `cint_mem_frame_charge` is
emitted in every function with local arrays, by element count, when the program has a call
cycle, and (measured at K4.5, see [compiler notes](cint-gaps.md#14-frame-arena-charges-depend-on-where-the-callee-is-k45)) also when an array's function calls into
another module: the same two functions with a `U8[4000]` each, in one module, have no charge, and
with a callee in a second module have two. `RT_FRAME_ARENA_ELEMENTS` is 4,096 elements, so a
charged program's live arrays total at most 32 KiB when the elements are 8 bytes (checked: five
nested frames of `U8[2000]` fault `E_BOUNDS arena.alloc` with operands 2000, 4000, 4096; two of
`U8[4000]` with 4000, 4000, 4096). A program with no charge has arrays bounded by the program text,
and nothing compares that bound with the stack: it can overrun the stack and hit a guard.

What a guard does. In an image that loads the TSS (every image but `k1`, `fault` and `trap`) the
page fault is delivered on its own stack (IST3). Outside a probe, on the boot stack, it stops with
`panic: kernel stack overflow (guard page) outside a probe` (exit 63); on a task's stack it is
the task's fault, with the record `host.error.task_stack` (the task number, nothing else) and
the kernel goes on (`docs/traps.md`, K4.5). The `stackover` flavor provokes the boot stack case in
a probe and gets a record; `net 6` of the shep flavor does the same on a task's stack, and `net 5`
runs a task off its stack with seven 4,096 byte frames. In an image that does not load the TSS
the delivery has no stack, so it is a triple fault and QEMU exits with status 0 (`docs/boot.md`).
All emitted C and `rt/` are built with `-fstack-clash-protection`: without it a compiler that
inlines a chain of calls into one frame of 28,672 bytes steps over a guard of two pages in one
subtraction (found by `net 5`; removing the flag makes it fail). Whether a program overruns a
stack depends on the compiler's frames, so an overflow is outside the determinism claim; the
record for it names the task only, and the task's fuel is stamped as 0.
