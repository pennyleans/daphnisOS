# Results: Daphnis K3 (memory, isolation hardening) and K4 (tasks and grants)

Tested commit: the head of branch `opencode/k3` (based on `opencode/k0-k1`; see the
branch note in `docs/notes.md`). The commits after it change documentation only; the branch head
is in the board handoff. The log in the last section is `./check.sh` from a fresh `git clone` of
that commit on the machine below. Result: **PASS, 209 PASS lines, 0 FAIL, 94 s**
(budget 300 s).

## Environment

| | |
| --- | --- |
| machine | CachyOS x86-64 (the task says Arch; host name mbp, called meep on the board) |
| gcc | gcc (GCC) 16.2.1 20260810 |
| clang | clang version 23.1.3 |
| ld | GNU ld (GNU Binutils) 2.47 |
| QEMU | QEMU emulator version 11.1.2, TCG (`-accel tcg`); 64 MiB, and 128 MiB for the `mem` flavor |
| cint | a pre-release slice; executable sha256 `42d15d580a5e2272d3f8ebc08434923add1b14ba3325c7289aa6f4383b865309` |
| cint compiler source identity | `18620842d9aa78bf9c1ca72316ef3e1a9ddd44c91143ebf6439c4952a1dc2a0e` |
| `cint_rt.h` sha256 | `1f1be52c0c96c69c87dd50342bfc0f3516f325b553f9c911bd1505da9911e9c8` |

`cint --version` does not exist (a usage error); the identity is the SHA-256 of the toolchain
file's `compiler_sources`, which `check.sh` prints and pins (`toolchain.pin`, unchanged).

## Commands

```
git clone "$REPO" clean-checkout    # clean checkout of this repository
cd clean-checkout && git checkout TESTED_COMMIT
nohup ./check.sh > LOG 2>&1 &     # about 100 s: outputs under $DAPHNIS_BUILD, cint cache under it
```

`check.sh` uses `CINT_TOOLCHAIN` (the pinned toolchain file) and `DAPHNIS_BUILD` (the output
directory), and refuses to clear a directory that is not empty and has no `.daphnis-build`
marker. Pieces: `make` (emit with `cint emit-c`, compile with
`tools/build-image.sh`, link with `ld`, `objcopy -O elf32-i386`), `tools/audit-symbols.sh`,
`tools/run-qemu.sh`, the decoders `tools/compare-fault.py`, `check-trap.py`, `check-records.py`,
`compare-faults.py`, `check-mem.py`, and `cint test` / `cint build` for the hosted tests and twins.
The shell of the harness stops a command after two minutes, so the gate was run in the background.

## The K3 gate, line by line

| K3 gate item | Result | Where in the log |
| --- | --- | --- |
| every existing line still passes | PASS | the K0 to K2 checks are all still in `check.sh` and pass; the loops gained flavors, no check was removed or loosened. The audit count is now computed (5 per build times the builds) instead of the literal 30 |
| the new flavors boot on gcc and clang | PASS | `boot ...-stackover`, `-nullptr`, `-faults`, `-mem` (QEMU status 33 on both runs, nothing on stderr); and `-coop`, `-preempt` |
| transcripts byte-identical across compilers and reruns | PASS | `serial <flavor>: ...` lines (`cmp`), hashes below, for all nine flavors |
| fault records decode and match hosted twins where they exist | PASS | `faults gcc` and `faults clang`: runs 0 to 9 are byte-identical to the hosted runtime's records (68 checks each); `tests/fuel_twin.ci` for the shape of the fuel fault; `mem`: six allocator hashes equal the hosted twin's; `tasks`: the task lines equal the hosted twin's |
| allocator hash before and after a refused allocation is equal | PASS | `mem gcc` and `mem clang` (74 checks each, including six bad-address runs and a boot at `-m 64`: the hash pairs are compared by the decoder from the transcript, not trusted from the `yes` the kernel prints); also the hosted tests |
| stack overflow, NMI gate, #DF and #PF each a record on its IST stack | PASS | `stackover gcc` and `stackover clang` (30 checks each) |
| null access is a #PF record | PASS | `nullptr gcc` and `nullptr clang` (16 checks each) |
| a write to a read-only page and a fetch from a no-execute page are fault records | PASS | `mem`: error codes 3 and `0x11`, CR2 the virtual address |
| the whole check stays under 5 minutes | PASS, 94 s | `time:` line |

K4 (stretch), line by line:

| K4 item | Result | Where in the log |
| --- | --- | --- |
| two or more kernel tasks, cooperative | PASS | `coop`: three tasks, the schedule (`run task N` seven times each) is in the transcript and the golden |
| preemptive on the PIT, context switch in a small asm stub | PASS | `preempt`: `arch/x86_64/task.S` (26 lines); quantum 3 ticks; the transcript says `a preempted task was resumed and finished: yes` and `quantum respected: yes` |
| immutable grants fixed at task start | PASS | rt keeps a mask per task from `task_create`; nothing changes it; tasks 1, 2 and 3 hold `console.input`, `console.raw` and both |
| one service behind a grant, denied in the OQ-304 shape | PASS with a deviation | it is `console.read_line`, not console write (below); a call no grant covers returns the error alternative `denied`, not a fault; the three task lines equal the hosted runtime's run with the same grant sets; task 2, which holds no `console.input`, reads `-1` |
| byte-identical across compilers | PASS | `serial coop` and `serial preempt` lines (the preempt transcript holds only what does not depend on where the timer ends a turn) |
| deterministic schedule, preemption on tick counts | PASS, with a limit | the cooperative schedule is exact; a preempted turn ends after a quantum of timer ticks, but under TCG the instruction at which it ends varies, so the preemptive transcript prints no interleaving (below) |

## Deviations from the task, and limits

* **Branch base.** `opencode/k3` is based on `opencode/k0-k1`, not `main`: when the work started
  `origin/main` held only the design commit.
* **Console write cannot be gated at the pin.** The standard `console` module publishes `write`
  under no capability (OQ-299), and `requires console.write` is `C3041`. K4 gates
  `console.read_line` (and `raw`) behind `console.input` and `console.raw` and answers `write` for
  every task (`docs/cint-gaps.md` 9). The grants of the kernel's three tasks are `console.input`,
  `console.raw` and both; the hosted twin is run with exactly those sets (a hosted run cannot be
  given an empty set: no `--grant` grants the whole manifest, an empty line is refused).
* **The preemptive schedule is not deterministic, only its transcript is.** A turn ends after a
  quantum of timer ticks, but under TCG the instruction at which it ends varies, so the transcript
  prints no interleaving: the three task lines, that a preempted task was resumed and finished, and
  that no turn ended before the quantum (turns * 2 <= ticks). `-icount` would make a single image
  reproducible but not gcc against clang.
* **Page tables:** cint adds a page directory and tables under slot 1 of the boot PDPT and edits
  them; it does not build a root or load CR3. Image pages are not protected or split.
* **Out of memory** is shown as clean refusals: a request larger than the pool, and one frame more
  than are free, each with the state hash unchanged; no case of a fragmented pool.
* **The view shim is a copy window** (`phys_read64` and friends with `in` and `out` views), because
  an extern cannot return a view and cannot hold one past the call. Ranges are fixed in
  `rt/phys.c` (`docs/memory.md`). Whether this is what l meant by the shim is l's call.
* **Error unions across modules and `Grants` across modules are refused by cintc (`C9102`)**, so
  the allocators return negative status codes and the service-calling code is in the root module,
  copied into the hosted twin and compared between markers (`docs/cint-gaps.md` 7 and 8).
* **The overflow is an assembly probe**, because whether a cint function chain with local arrays
  survives optimization is the compiler's choice. `int 2` stands for the NMI; the #DF case relies on
  QEMU TCG escalating a failed #PF delivery (`docs/traps.md`).
* **The `faults` flavor** runs eleven entries in a loop (`rt/ctx.c`); the hosted twin runs the same
  program once per entry (`--arg i`). Run 10, fuel, has no byte-identical twin: a hosted run has no
  fuel option (`docs/cint-gaps.md` 11).
* **`coop` and `preempt` are one program** built with `RT_TASK_MODE` 0 and 1 (a constant of `rt/`).
* **`-m 128M` only for the `mem` flavor**; the K0 to K2 flavors keep `-m 64`.
* `docs/notes.md` lists what was not done (guard pages for task and IST stacks, hardware, K5).

## Transcripts and images

| flavor | QEMU status | transcript sha256 (gcc run 1, run 2, clang run 1, run 2 all equal) |
| --- | --- | --- |
| k1 | 33 | `ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37` |
| fault | 35 | `b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f` |
| trap | 33 | `96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d` |
| stackover | 33 | `e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183` |
| nullptr | 33 | `e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23` |
| faults | 33 | `5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12` |
| mem | 33 | `1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f` |
| coop | 33 | `ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a` |
| preempt | 33 | `19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64` |

The `coop` transcript, whole (a task line is what the task wrote with `console.write`; task 2 has
no `console.input` grant):

```
run 0
Daphnis K4: cooperative tasks
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
run task 1
run task 2
run task 3
task 1 total 1180 read 7 raw -1
task 2 total 1693 read -1 raw 0
task 3 total 1433 read 7 raw 0
coop: done
```

The `preempt` transcript, whole:

```
run 0
Daphnis K4: preemptive tasks
task 1 total 100561 read 7 raw -1
task 2 total 100453 read -1 raw 0
task 3 total 102685 read 7 raw 0
a preempted task was resumed and finished: yes
quantum respected: yes
preempt: done
```

The `mem` flavor's hash lines (the first six are what the hosted twin reproduces):

```
hash empty:          9cb547ab7a51cd28d0a83cd8f21dbe21575b852de5714900ed0f99bb38cfb83c
hash before refusals: d6197baf57270f651e31122e1b4a5acabb37f40e2de9bd88e32d0b1575017fe3
hash after refusals:  d6197baf57270f651e31122e1b4a5acabb37f40e2de9bd88e32d0b1575017fe3
hash before big object: 3cbc65300dfd69a2fbc65b56266055cded2912ea8ce3b464e2c9b1f182ff80e8
hash after big object:  3cbc65300dfd69a2fbc65b56266055cded2912ea8ce3b464e2c9b1f182ff80e8
hash final:           4a3d921d7f2ac195c5942b69c80ffc0a712a41dbd26f93ac1032c8779743db52
final state hash: 4f419a5281cc83fe7fa02b90d49374a36b65d8b72f49543c4c453f0906699939
```

Image sha256 (`kernel.elf`, byte-identical across two builds in different directories, which the
gate checks):

| flavor | gcc | clang |
| --- | --- | --- |
| k1 | `ebced493dba2604a8db627743d152ef2b96f99aa12ffbc4440fbd69231f38be5` | `867016f0588aef39ac4b6c931b0fe3e2675d2f7accd5205ec7ef493b2f38904a` |
| fault | `17d368286035a5c6a684f0c5492e4d8f070ce061a29c50ab31c58ef95b947b08` | `95c3b92002734e97d1346ac69b4a7ff643d6dd68838a72bfb8855294d7ff62ee` |
| trap | `b1398419503414dce2e1a99f2ec857dbe1693be296c2ac1ecfdb8a5f9d449be9` | `d62d4b73859aca6e49f2eed868c0902ac2c92ecd0a4ff4c9d1cd49eb303c873e` |
| stackover | `3fc183d9fb53337a360e77c7b280bf94e1723e9b6712e33715816cff0a9d54ac` | `c8950b3fcf0b6c1c7fbf2a975bfc4a5df878633c57db1b5ae3b376130b27337c` |
| nullptr | `54f68cfeb100c1b93ac451d8d589e9b27b9e2e7bbfb2c4af3f7053a30d0192ce` | `b191aec16eb07656e5c9e050c6c2dfe05d3eb1706436726d5c353201624a4c56` |
| faults | `709e33ce4f365c8037c52c183ea7ece7762a1c8596a3c6d8e107357aa201cade` | `d3e93da3d8de94264e67a16a2e8ed3a064173ac7bb4c19c2dc2e62e3f989f419` |
| mem | `24130a67591f01a9342c2c79a1ded8a206fb97daf27394d76c8580f5c6b1bdad` | `b10b42ca6fb0ffd268465e0c868a834366550e1cc4ced711a0aa461beba6fdf8` |
| coop | `9af420248efba7032e357c6a1ceb0f23da066864076c1fde6e54aacb85deccf2` | `342cfe72ca36f55482640480cd3b47d74a8c67355aa26204115c993b461cf89d` |
| preempt | `af930a853f27ec3e38fb7b3155b14fe64a905f72b49cb5fc715d58228668c1c2` | `a23329660c1ed4753f24d4f318f0e358512bd2ddef0ec7148b3ef2bddfdf6ee5` |

## Records, decoded

Stack overflow in the `stackover` flavor (the third operand is the offset of CR2 in the guard
page, so no image address is in the record; the fourth is the IST stack the frame was on):

```
domain     cint-core-1/fault/v2
code       10
operation  host.error.trap_stack
operands   I64 14, U64 2, U64 4088, U64 3
position   src/main_stackover.ci:15:10
stack      empty
revision   the program's cg_revision (32 bytes), no source map, no address
```

A store to a read-only page in the `mem` flavor (error code 3: present, write; CR2 the address;
the stack is main, demo, paging_demo):

```
domain     cint-core-1/fault/v2
code       10
operation  host.error.trap_pf
operands   I64 14, U64 3, U64 1073741824, U64 3
position   src/main_mem.ci:150:10
stack      [('src/main_mem.ci', 302, 9), ('src/main_mem.ci', 238, 5)]
revision   the program's cg_revision (32 bytes), no source map, no address
```

## Sizes

Hand-written, in lines: `rt/` C 1590 (`ctx.c` 327, `fault.c` 431, `host.c` 278, `mem.c` 47, `phys.c` 44, `serial.c` 35, `start.c` 25, `task.c` 190, `trap.c` 213); asm 352 (`boot.S` 142, `portio.S` 37, `probe.S` 58, `task.S` 26, `trap.S` 89, each under the
150-line cap); cint 1956 in 32 modules (`sha256.ci` and `main_mem.ci` are the largest). `kernel32.elf`: coop clang 99604, coop gcc 105844, fault clang 41328, fault gcc 41108, faults clang 40736, faults gcc 40364, k1 clang 55168, k1 gcc 55456, mem clang 156544, mem gcc 175368, nullptr clang 63528, nullptr gcc 66316, preempt clang 99604, preempt gcc 105844, stackover clang 64192, stackover gcc 66956, trap clang 60440, trap gcc 62448.

## What the gate catches (mutations of the new checks)

Mutations were run in copies of the tree, each a full `check.sh` with its own build directory, by
a driver that applies one literal edit (`/tmp/opencode/mut`, not in the repository). `OK` means the
gate gave the expected result. **A row marked `INVALID` is not evidence**: the
edit did not compile (`-Werror`), the gate failed for the wrong reason, and the mutation was redone
under the same name with an edit that compiles (`m16`, `m20`, `m24`, `m27`, `r2`, `r5`); `m19` had a
pattern that did not match and was redone. The later row of the same name is the valid one. Two
runs were instructive: `m08_no_invlpg_unmap` was **missed** on the first tree (a missing `invlpg`
after an unmap passed because nothing touched the page since the last flush), and the demo now
loads through the mapping before the unmap, which the re-run catches; and a reviewer's six
mutations (`r1` to `r6`: the timer switch removed, `raw` ignoring grants, the shim's alignment and
overflow checks, the fuel allowance, the quantum, a hard-coded RAM size) all **passed** on the tree
before the review fixes (a preemption proof, a `raw` probe, bad-address runs, a fuel limit check and
a `-m 64` boot were added); the rows below are their re-runs. `m19` is an invariance check: it
adds clang-only padding to `rt/mem.c` and the gate must still pass.

```
OK | m01_ist_offset | expect FAIL | gate FAIL | 18 FAIL lines | FAIL  boot gcc-stackover: QEMU exit status 33: got 0 and 0
OK | m02_no_ist_gates | expect FAIL | gate FAIL | 18 FAIL lines | FAIL  boot gcc-stackover: QEMU exit status 33: got 0 and 0
OK | m03_nmi_not_ist | expect FAIL | gate FAIL | 7 FAIL lines | FAIL  hosted: cint test tests/src_test.ci: see /tmp/opencode/mut/build-m03_nmi_not_ist/hosted.log
OK | m04_null_mapped | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial nullptr: gcc vs tests/expected/nullptr.skeleton: differ
OK | m05_stale_record | expect FAIL | gate FAIL | 24 FAIL lines | FAIL  boot gcc-trap: QEMU exit status 33: got 63 and 63
OK | m06_no_nxe | expect FAIL | gate FAIL | 6 FAIL lines | FAIL  boot gcc-mem: QEMU exit status 33: got 63 and 63
OK | m07_no_wp | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
MISSED | m08_no_invlpg_unmap | expect FAIL | gate PASS | 0 FAIL lines | 
OK | m09_no_invlpg_protect | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
OK | m10_frame_refusal_mutates | expect FAIL | gate FAIL | 6 FAIL lines | FAIL  hosted: cint test tests/src_test.ci: see /tmp/opencode/mut/build-m10_frame_refusal_mutates/hos
OK | m11_heap_refusal_mutates | expect FAIL | gate FAIL | 5 FAIL lines | FAIL  hosted: cint test tests/src_test.ci: see /tmp/opencode/mut/build-m11_heap_refusal_mutates/host
OK | m12_null_window_open | expect FAIL | gate FAIL | 7 FAIL lines | FAIL  boot gcc-mem: QEMU exit status 33: got 0 and 0
OK | m13_no_ctx_reset | expect FAIL | gate FAIL | 13 FAIL lines | FAIL  boot gcc-faults: QEMU exit status 33: got 63 and 63
OK | m14_wrong_fault_kind | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  faults gcc: records: see /tmp/opencode/mut/build-m14_wrong_fault_kind/faults-gcc.cmp
OK | m15_shift_limit | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  faults gcc: records: see /tmp/opencode/mut/build-m15_shift_limit/faults-gcc.cmp
INVALID (build error, not evidence) | m16_ist_operand | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-m16_ist_operand/build.log
OK | m17_gate_not_restored | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  stackover gcc: records: see /tmp/opencode/mut/build-m17_gate_not_restored/stackover-gcc.cmp
OK | m18_mem_wrong_m | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
PATTERN MISSING | m19_clang_pad
INVALID (build error, not evidence) | m20_cr2_masked | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-m20_cr2_masked/build.log
OK | m21_sentinel_run_short | expect FAIL | gate FAIL | 5 FAIL lines | FAIL  faults: hosted twin: records missing; see /tmp/opencode/mut/build-m21_sentinel_run_short/fault
OK | m08_no_invlpg_unmap | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
OK | m16_ist_operand | expect FAIL | gate FAIL | 6 FAIL lines | FAIL  stackover gcc: records: see /tmp/opencode/mut/build-m16_ist_operand/stackover-gcc.cmp
OK | m19_clang_pad | expect PASS | gate PASS | 0 FAIL lines | 
OK | m20_cr2_masked | expect FAIL | gate FAIL | 6 FAIL lines | FAIL  trap gcc: records or ticks: see /tmp/opencode/mut/build-m20_cr2_masked/trap-gcc.cmp
OK | m23_grant_swap | expect FAIL | gate FAIL | 8 FAIL lines | FAIL  serial coop: gcc vs tests/expected/coop.serial: differ
INVALID (build error, not evidence) | m24_always_covered | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-m24_always_covered/build.log
INVALID (build error, not evidence) | m27_preempt_never | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-m27_preempt_never/build.log
OK | m29_service_block_diff | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  tasks: service block: src/main_tasks.ci and tests/task_twin.ci differ between the markers
OK | m30_task_stack_misaligned | expect FAIL | gate FAIL | 12 FAIL lines | FAIL  boot gcc-coop: QEMU exit status 33: got 0 and 0
OK | m31_task_zero | expect FAIL | gate FAIL | 10 FAIL lines | FAIL  serial preempt: gcc vs clang (cmp): differ
OK | m32_coop_no_yield | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  serial coop: gcc vs tests/expected/coop.serial: differ
OK | m34_denied_is_fault | expect FAIL | gate FAIL | 8 FAIL lines | FAIL  serial coop: gcc vs tests/expected/coop.serial: differ
OK | m24_always_covered | expect FAIL | gate FAIL | 8 FAIL lines | FAIL  serial coop: gcc vs tests/expected/coop.serial: differ
INVALID (build error, not evidence) | m27_preempt_never | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-m27_preempt_never/build.log
OK | m36_remap_over | expect FAIL | gate FAIL | 4 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
OK | m38_release_unowned | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  hosted: cint test tests/src_test.ci: see /tmp/opencode/mut/build-m38_release_unowned/hosted.lo
OK | m27_preempt_never | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  serial preempt: gcc vs tests/expected/preempt.serial: differ
OK | r1_no_switch | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  serial preempt: gcc vs tests/expected/preempt.serial: differ
INVALID (build error, not evidence) | r2_raw_ignores_grants | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-r2_raw_ignores_grants/build.log
OK | r3a_no_align_check | expect FAIL | gate FAIL | 7 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
OK | r3b_no_overflow_check | expect FAIL | gate FAIL | 9 FAIL lines | FAIL  boot gcc-mem: QEMU exit status 33: got 0 and 0
OK | r4_fuel | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  faults gcc: records: see /tmp/opencode/mut/build-r4_fuel/faults-gcc.cmp
INVALID (build error, not evidence) | r5_quantum_ignored | expect FAIL | gate FAIL | 1 FAIL lines | FAIL  build: make: see /tmp/opencode/mut/build-r5_quantum_ignored/build.log
OK | r6_ram_hardcoded | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  mem gcc: -m 64: the summary does not follow the machine (status 33)
OK | r7_vm_unrestricted | expect FAIL | gate FAIL | 7 FAIL lines | FAIL  serial mem: gcc vs tests/expected/mem.skeleton: differ
OK | r2_raw_ignores_grants | expect FAIL | gate FAIL | 8 FAIL lines | FAIL  serial coop: gcc vs tests/expected/coop.serial: differ
OK | r5_quantum_ignored | expect FAIL | gate FAIL | 2 FAIL lines | FAIL  serial preempt: gcc vs tests/expected/preempt.serial: differ
```

Not covered by any mutation: the `closed` result of a full task buffer, a second page table, the
fetch-fault recognition in `rt_trap_dispatch` beyond what the `mem` flavor reaches, and the
race in `task_entry` that review found and fixed (a tick between the state store and `cli`): it is
timing-dependent and no flavor provokes it.

## Known gaps and hazards

* Task stacks and IST stacks have no guard page: an overflow of either is not detected.
* The timer handler runs on the task's own stack; a preempted turn's end is timing-dependent
  (hence no interleaving in the transcript), and nothing proves two runs end it at the same tick.
* Only QEMU 11.1.2 TCG; not KVM, not hardware (a #DF's RIP is undefined by the architecture).
* A real NMI was not injected; the null page is the first 4 KiB only; the PIC is initialized
  without I/O delays; the frame pool is a fixed 16 MiB.
* `-O2` only in `check.sh` (`-O0`, `-O1`, `-O3`, `-Os` were checked by hand for K2).
* Globals shared by every context are not safe under preemption: `rt_host_site`, the module-state
  pool and the trap record. Probes and the first access of module state panic in a preemptible
  task; nothing else is guarded, and no task flavor uses module state.
* A #PF taken while already on IST3 (a fault inside the dispatcher) would overwrite the live frame;
  not detected.
* The whole first 2 MiB is read-write-execute, including the text, the IDT, the GDT and the IST stacks.
* The shim can write only the boot PDPT, but cint can still map one frame twice or alias a page
  within the managed region.
* No memory event was seen (`docs/notes.md`).

## The log

```
gcc:    gcc (GCC) 16.2.1 20260810
clang:  clang version 23.1.3
qemu:   QEMU emulator version 11.1.2
ld:     GNU ld (GNU Binutils) 2.47
cint compiler source identity: 18620842d9aa78bf9c1ca72316ef3e1a9ddd44c91143ebf6439c4952a1dc2a0e
cint executable sha256:        42d15d580a5e2272d3f8ebc08434923add1b14ba3325c7289aa6f4383b865309
cint_rt.h sha256:              1f1be52c0c96c69c87dd50342bfc0f3516f325b553f9c911bd1505da9911e9c8
PASS  toolchain: cint_rt.h matches toolchain.pin
PASS  toolchain: compiler source identity matches toolchain.pin
PASS  toolchain: the cint on PATH is the executable the toolchain file names
PASS  hosted: cint test tests/src_test.ci (13 of 13 tests passed)
PASS  build: gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt (make)
PASS  build: every gcc-k1 object was compiled by gcc (.comment names it)
PASS  build: every clang-k1 object was compiled by clang (.comment names it)
PASS  build: the gcc and clang images differ (two different compilers built them)
image sha256:
  gcc-k1  ebced493dba2604a8db627743d152ef2b96f99aa12ffbc4440fbd69231f38be5
  gcc-fault  17d368286035a5c6a684f0c5492e4d8f070ce061a29c50ab31c58ef95b947b08
  gcc-trap  b1398419503414dce2e1a99f2ec857dbe1693be296c2ac1ecfdb8a5f9d449be9
  gcc-stackover  3fc183d9fb53337a360e77c7b280bf94e1723e9b6712e33715816cff0a9d54ac
  gcc-nullptr  54f68cfeb100c1b93ac451d8d589e9b27b9e2e7bbfb2c4af3f7053a30d0192ce
  gcc-faults  709e33ce4f365c8037c52c183ea7ece7762a1c8596a3c6d8e107357aa201cade
  gcc-mem  24130a67591f01a9342c2c79a1ded8a206fb97daf27394d76c8580f5c6b1bdad
  gcc-coop  9af420248efba7032e357c6a1ceb0f23da066864076c1fde6e54aacb85deccf2
  gcc-preempt  af930a853f27ec3e38fb7b3155b14fe64a905f72b49cb5fc715d58228668c1c2
  clang-k1  867016f0588aef39ac4b6c931b0fe3e2675d2f7accd5205ec7ef493b2f38904a
  clang-fault  95c3b92002734e97d1346ac69b4a7ff643d6dd68838a72bfb8855294d7ff62ee
  clang-trap  d62d4b73859aca6e49f2eed868c0902ac2c92ecd0a4ff4c9d1cd49eb303c873e
  clang-stackover  c8950b3fcf0b6c1c7fbf2a975bfc4a5df878633c57db1b5ae3b376130b27337c
  clang-nullptr  b191aec16eb07656e5c9e050c6c2dfe05d3eb1706436726d5c353201624a4c56
  clang-faults  d3e93da3d8de94264e67a16a2e8ed3a064173ac7bb4c19c2dc2e62e3f989f419
  clang-mem  b10b42ca6fb0ffd268465e0c868a834366550e1cc4ced711a0aa461beba6fdf8
  clang-coop  342cfe72ca36f55482640480cd3b47d74a8c67355aa26204115c993b461cf89d
  clang-preempt  a23329660c1ed4753f24d4f318f0e358512bd2ddef0ec7148b3ef2bddfdf6ee5
PASS  build: a second build in another directory gives byte-identical images
PASS  audit gcc-k1: every object's undefined symbols are defined in this build
PASS  audit gcc-k1: image has no undefined symbol (nm -u empty)
PASS  audit gcc-k1: no libc symbol in any object or the image
PASS  audit gcc-k1: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-k1: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-fault: every object's undefined symbols are defined in this build
PASS  audit gcc-fault: image has no undefined symbol (nm -u empty)
PASS  audit gcc-fault: no libc symbol in any object or the image
PASS  audit gcc-fault: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-fault: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-trap: every object's undefined symbols are defined in this build
PASS  audit gcc-trap: image has no undefined symbol (nm -u empty)
PASS  audit gcc-trap: no libc symbol in any object or the image
PASS  audit gcc-trap: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-trap: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-stackover: every object's undefined symbols are defined in this build
PASS  audit gcc-stackover: image has no undefined symbol (nm -u empty)
PASS  audit gcc-stackover: no libc symbol in any object or the image
PASS  audit gcc-stackover: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-stackover: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-nullptr: every object's undefined symbols are defined in this build
PASS  audit gcc-nullptr: image has no undefined symbol (nm -u empty)
PASS  audit gcc-nullptr: no libc symbol in any object or the image
PASS  audit gcc-nullptr: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-nullptr: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-faults: every object's undefined symbols are defined in this build
PASS  audit gcc-faults: image has no undefined symbol (nm -u empty)
PASS  audit gcc-faults: no libc symbol in any object or the image
PASS  audit gcc-faults: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-faults: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-mem: every object's undefined symbols are defined in this build
PASS  audit gcc-mem: image has no undefined symbol (nm -u empty)
PASS  audit gcc-mem: no libc symbol in any object or the image
PASS  audit gcc-mem: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-mem: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-coop: every object's undefined symbols are defined in this build
PASS  audit gcc-coop: image has no undefined symbol (nm -u empty)
PASS  audit gcc-coop: no libc symbol in any object or the image
PASS  audit gcc-coop: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-coop: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-preempt: every object's undefined symbols are defined in this build
PASS  audit gcc-preempt: image has no undefined symbol (nm -u empty)
PASS  audit gcc-preempt: no libc symbol in any object or the image
PASS  audit gcc-preempt: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-preempt: no SSE, AVX or x87 instruction in any object
PASS  audit clang-k1: every object's undefined symbols are defined in this build
PASS  audit clang-k1: image has no undefined symbol (nm -u empty)
PASS  audit clang-k1: no libc symbol in any object or the image
PASS  audit clang-k1: mem functions are exactly the four of rt/mem.c
PASS  audit clang-k1: no SSE, AVX or x87 instruction in any object
PASS  audit clang-fault: every object's undefined symbols are defined in this build
PASS  audit clang-fault: image has no undefined symbol (nm -u empty)
PASS  audit clang-fault: no libc symbol in any object or the image
PASS  audit clang-fault: mem functions are exactly the four of rt/mem.c
PASS  audit clang-fault: no SSE, AVX or x87 instruction in any object
PASS  audit clang-trap: every object's undefined symbols are defined in this build
PASS  audit clang-trap: image has no undefined symbol (nm -u empty)
PASS  audit clang-trap: no libc symbol in any object or the image
PASS  audit clang-trap: mem functions are exactly the four of rt/mem.c
PASS  audit clang-trap: no SSE, AVX or x87 instruction in any object
PASS  audit clang-stackover: every object's undefined symbols are defined in this build
PASS  audit clang-stackover: image has no undefined symbol (nm -u empty)
PASS  audit clang-stackover: no libc symbol in any object or the image
PASS  audit clang-stackover: mem functions are exactly the four of rt/mem.c
PASS  audit clang-stackover: no SSE, AVX or x87 instruction in any object
PASS  audit clang-nullptr: every object's undefined symbols are defined in this build
PASS  audit clang-nullptr: image has no undefined symbol (nm -u empty)
PASS  audit clang-nullptr: no libc symbol in any object or the image
PASS  audit clang-nullptr: mem functions are exactly the four of rt/mem.c
PASS  audit clang-nullptr: no SSE, AVX or x87 instruction in any object
PASS  audit clang-faults: every object's undefined symbols are defined in this build
PASS  audit clang-faults: image has no undefined symbol (nm -u empty)
PASS  audit clang-faults: no libc symbol in any object or the image
PASS  audit clang-faults: mem functions are exactly the four of rt/mem.c
PASS  audit clang-faults: no SSE, AVX or x87 instruction in any object
PASS  audit clang-mem: every object's undefined symbols are defined in this build
PASS  audit clang-mem: image has no undefined symbol (nm -u empty)
PASS  audit clang-mem: no libc symbol in any object or the image
PASS  audit clang-mem: mem functions are exactly the four of rt/mem.c
PASS  audit clang-mem: no SSE, AVX or x87 instruction in any object
PASS  audit clang-coop: every object's undefined symbols are defined in this build
PASS  audit clang-coop: image has no undefined symbol (nm -u empty)
PASS  audit clang-coop: no libc symbol in any object or the image
PASS  audit clang-coop: mem functions are exactly the four of rt/mem.c
PASS  audit clang-coop: no SSE, AVX or x87 instruction in any object
PASS  audit clang-preempt: every object's undefined symbols are defined in this build
PASS  audit clang-preempt: image has no undefined symbol (nm -u empty)
PASS  audit clang-preempt: no libc symbol in any object or the image
PASS  audit clang-preempt: mem functions are exactly the four of rt/mem.c
PASS  audit clang-preempt: no SSE, AVX or x87 instruction in any object
PASS  K0: symbol audit ran and passed (90 checks, 5 per build, gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt)
PASS  boot gcc-k1: QEMU exit status 33 on both runs
PASS  boot gcc-k1: QEMU wrote nothing to stderr
PASS  boot gcc-fault: QEMU exit status 35 on both runs
PASS  boot gcc-fault: QEMU wrote nothing to stderr
PASS  boot gcc-trap: QEMU exit status 33 on both runs
PASS  boot gcc-trap: QEMU wrote nothing to stderr
PASS  boot gcc-stackover: QEMU exit status 33 on both runs
PASS  boot gcc-stackover: QEMU wrote nothing to stderr
PASS  boot gcc-nullptr: QEMU exit status 33 on both runs
PASS  boot gcc-nullptr: QEMU wrote nothing to stderr
PASS  boot gcc-faults: QEMU exit status 33 on both runs
PASS  boot gcc-faults: QEMU wrote nothing to stderr
PASS  boot gcc-mem: QEMU exit status 33 on both runs
PASS  boot gcc-mem: QEMU wrote nothing to stderr
PASS  boot gcc-coop: QEMU exit status 33 on both runs
PASS  boot gcc-coop: QEMU wrote nothing to stderr
PASS  boot gcc-preempt: QEMU exit status 33 on both runs
PASS  boot gcc-preempt: QEMU wrote nothing to stderr
PASS  boot clang-k1: QEMU exit status 33 on both runs
PASS  boot clang-k1: QEMU wrote nothing to stderr
PASS  boot clang-fault: QEMU exit status 35 on both runs
PASS  boot clang-fault: QEMU wrote nothing to stderr
PASS  boot clang-trap: QEMU exit status 33 on both runs
PASS  boot clang-trap: QEMU wrote nothing to stderr
PASS  boot clang-stackover: QEMU exit status 33 on both runs
PASS  boot clang-stackover: QEMU wrote nothing to stderr
PASS  boot clang-nullptr: QEMU exit status 33 on both runs
PASS  boot clang-nullptr: QEMU wrote nothing to stderr
PASS  boot clang-faults: QEMU exit status 33 on both runs
PASS  boot clang-faults: QEMU wrote nothing to stderr
PASS  boot clang-mem: QEMU exit status 33 on both runs
PASS  boot clang-mem: QEMU wrote nothing to stderr
PASS  boot clang-coop: QEMU exit status 33 on both runs
PASS  boot clang-coop: QEMU wrote nothing to stderr
PASS  boot clang-preempt: QEMU exit status 33 on both runs
PASS  boot clang-preempt: QEMU wrote nothing to stderr
transcript sha256:
  gcc-k1 run 1  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  gcc-k1 run 2  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  gcc-fault run 1  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  gcc-fault run 2  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  gcc-trap run 1  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  gcc-trap run 2  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  gcc-stackover run 1  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  gcc-stackover run 2  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  gcc-nullptr run 1  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  gcc-nullptr run 2  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  gcc-faults run 1  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  gcc-faults run 2  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  gcc-mem run 1  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  gcc-mem run 2  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  gcc-coop run 1  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  gcc-coop run 2  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  gcc-preempt run 1  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  gcc-preempt run 2  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  clang-k1 run 1  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  clang-k1 run 2  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  clang-fault run 1  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  clang-fault run 2  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  clang-trap run 1  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  clang-trap run 2  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  clang-stackover run 1  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  clang-stackover run 2  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  clang-nullptr run 1  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  clang-nullptr run 2  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  clang-faults run 1  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  clang-faults run 2  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  clang-mem run 1  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  clang-mem run 2  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  clang-coop run 1  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  clang-coop run 2  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  clang-preempt run 1  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  clang-preempt run 2  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
PASS  serial k1: gcc and clang transcripts byte-identical (cmp)
PASS  serial k1: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial k1: clang run 1 and run 2 byte-identical (cmp)
PASS  serial fault: gcc and clang transcripts byte-identical (cmp)
PASS  serial fault: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial fault: clang run 1 and run 2 byte-identical (cmp)
PASS  serial trap: gcc and clang transcripts byte-identical (cmp)
PASS  serial trap: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial trap: clang run 1 and run 2 byte-identical (cmp)
PASS  serial stackover: gcc and clang transcripts byte-identical (cmp)
PASS  serial stackover: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial stackover: clang run 1 and run 2 byte-identical (cmp)
PASS  serial nullptr: gcc and clang transcripts byte-identical (cmp)
PASS  serial nullptr: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial nullptr: clang run 1 and run 2 byte-identical (cmp)
PASS  serial faults: gcc and clang transcripts byte-identical (cmp)
PASS  serial faults: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial faults: clang run 1 and run 2 byte-identical (cmp)
PASS  serial mem: gcc and clang transcripts byte-identical (cmp)
PASS  serial mem: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial mem: clang run 1 and run 2 byte-identical (cmp)
PASS  serial coop: gcc and clang transcripts byte-identical (cmp)
PASS  serial coop: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial coop: clang run 1 and run 2 byte-identical (cmp)
PASS  serial preempt: gcc and clang transcripts byte-identical (cmp)
PASS  serial preempt: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial preempt: clang run 1 and run 2 byte-identical (cmp)
PASS  sha256: gcc kernel prints the FIPS 180-4 vector for "abc"
PASS  serial k1: gcc transcript equals tests/expected/k1.serial
PASS  serial fault: gcc banner and record header equal tests/expected/fault.head
PASS  sha256: clang kernel prints the FIPS 180-4 vector for "abc"
PASS  serial k1: clang transcript equals tests/expected/k1.serial
PASS  serial fault: clang banner and record header equal tests/expected/fault.head
PASS  serial trap: gcc transcript equals tests/expected/trap.skeleton (record hex masked)
PASS  trap gcc: #DE, #UD and #PF records printed from cint decode as expected; PIT ticks counted (26 checks)
PASS  serial trap: clang transcript equals tests/expected/trap.skeleton (record hex masked)
PASS  trap clang: #DE, #UD and #PF records printed from cint decode as expected; PIT ticks counted (26 checks)
PASS  serial stackover: gcc transcript equals tests/expected/stackover.skeleton (record hex masked)
PASS  stackover gcc: records decode and match the table (30 checks)
PASS  serial stackover: clang transcript equals tests/expected/stackover.skeleton (record hex masked)
PASS  stackover clang: records decode and match the table (30 checks)
PASS  serial nullptr: gcc transcript equals tests/expected/nullptr.skeleton (record hex masked)
PASS  nullptr gcc: records decode and match the table (16 checks)
PASS  serial nullptr: clang transcript equals tests/expected/nullptr.skeleton (record hex masked)
PASS  nullptr clang: records decode and match the table (16 checks)
PASS  faults: the hosted runtime wrote a record for each of probes 0 to 9
PASS  faults gcc: 11 probes, 10 records byte-identical to the hosted runtime's, table and positions (68 checks)
PASS  serial faults: gcc transcript equals tests/expected/faults.skeleton (record hex masked)
PASS  faults clang: 11 probes, 10 records byte-identical to the hosted runtime's, table and positions (68 checks)
PASS  serial faults: clang transcript equals tests/expected/faults.skeleton (record hex masked)
PASS  faults: the hosted fuel fault has the kernel's shape (E_FUEL, fuel.charge, no operands, no exact, at src/probes.ci:75:5)
PASS  serial mem: gcc transcript equals tests/expected/mem.skeleton (record hex masked)
PASS  mem gcc: bad addresses, #PF records, refusals and hashes check out (74 checks)
PASS  serial mem: clang transcript equals tests/expected/mem.skeleton (record hex masked)
PASS  mem clang: bad addresses, #PF records, refusals and hashes check out (74 checks)
PASS  mem gcc: booted with -m 64 the summary says 'ram: MiB 64' and nothing else changes
PASS  mem clang: booted with -m 64 the summary says 'ram: MiB 64' and nothing else changes
PASS  mem: the hosted runtime, running src/allocdemo.ci, reproduces all six allocator-state hashes of the kernel
PASS  mem: the twin refuses a hash that differs in one digit (it can fail)
PASS  serial coop: gcc transcript equals tests/expected/coop.serial
PASS  serial coop: clang transcript equals tests/expected/coop.serial
PASS  serial preempt: gcc transcript equals tests/expected/preempt.serial
PASS  serial preempt: clang transcript equals tests/expected/preempt.serial
PASS  tasks: the service block of src/main_tasks.ci is byte-identical to the hosted twin's
PASS  tasks coop gcc: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks coop clang: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks preempt gcc: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks preempt clang: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  fault: hosted runtime wrote its record for tests/fault_probe.ci
  [gcc] PASS  kernel record length matches its header (187 bytes)
  [gcc] PASS  both records decode as cint-core-1/fault/v2
  [gcc] PASS  kernel equals hosted: domain
  [gcc] PASS  kernel equals hosted: code
  [gcc] PASS  kernel equals hosted: operation
  [gcc] PASS  kernel equals hosted: operands
  [gcc] PASS  kernel equals hosted: exact
  [gcc] PASS  kernel equals hosted: limit
  [gcc] PASS  kernel equals hosted: srcmap
  [gcc] PASS  kernel equals hosted: address_present
  [gcc] PASS  kernel equals hosted: position
  [gcc] PASS  kernel position is src/overflow.ci:7:23
  [gcc] PASS  kernel and hosted stacks both have one entry
  [gcc] PASS  kernel stack is the call site src/main_fault.ci:11:22
  [gcc] PASS  kernel revision equals cg_revision of its emitted program
  [gcc] PASS  hosted revision is present and differs (different program)
PASS  fault gcc: record printed, decodes, and matches the hosted record
  [clang] PASS  kernel record length matches its header (187 bytes)
  [clang] PASS  both records decode as cint-core-1/fault/v2
  [clang] PASS  kernel equals hosted: domain
  [clang] PASS  kernel equals hosted: code
  [clang] PASS  kernel equals hosted: operation
  [clang] PASS  kernel equals hosted: operands
  [clang] PASS  kernel equals hosted: exact
  [clang] PASS  kernel equals hosted: limit
  [clang] PASS  kernel equals hosted: srcmap
  [clang] PASS  kernel equals hosted: address_present
  [clang] PASS  kernel equals hosted: position
  [clang] PASS  kernel position is src/overflow.ci:7:23
  [clang] PASS  kernel and hosted stacks both have one entry
  [clang] PASS  kernel stack is the call site src/main_fault.ci:11:22
  [clang] PASS  kernel revision equals cg_revision of its emitted program
  [clang] PASS  hosted revision is present and differs (different program)
PASS  fault clang: record printed, decodes, and matches the hosted record
PASS  repository: this run changed no file in the checkout
elapsed: 94 s (budget 300 s)
PASS  time: whole check in 94 s, under 5 minutes
RESULT: PASS
```
