# Results: K4.5 (the shepherd)

Branch `opencode/k45`, from `main` of that day. Code and docs under test: the branch head (a clean
clone of it, in `/tmp/opencode/k45/clean`, built into a fresh directory); the commits after it
(this file and a wording fix in the notes) change only docs. What the stage built and what it claims is `docs/shepherd.md`.

## The gate

`./check.sh` from the clean clone: **240 PASS, 0 FAIL, 123 s** (budget 300 s), `RESULT: PASS`.
Earlier runs of the same stage on the working tree: 240 PASS each time, 123 to 129 s; no result failed
to reproduce, so nothing is logged as a possible memory event. The count did not grow with the new
checks because the shep checks are decoded by `tools/check-shep.py` into one PASS line per compiler
(23 checks each, `tests/expected/record-checks`).

Machine: CachyOS, gcc 16.2.1, clang 23.1.3, GNU ld 2.47, QEMU 11.1.2 (TCG), cint at the pin
(a pre-release cint slice, compiler source identity `18620842d9aa...`).

What the K4.5 lines of the gate say (section 5f of `check.sh` and the generic boot checks): the hosted
twin ran the network with no scheduler and wrote its root; the transcript of the shep flavor equals
`tests/expected/shep.skeleton` on gcc and clang; `tools/check-shep.py` passes 23 checks on each; only
`src/ownstate.c` asks for module state; and the transcript of gcc and clang at `-O0`, `-O1`, `-O3` and
`-Os` equals the `-O2` one byte for byte (8 builds), so the 10 builds of the flavor agree.

## The transcript (shep flavor, gcc `-O2`, run 1; digests cut to 12 digits)

```
guard pages not present, of 12: 12
stack pages present, of 6: 6
net 0 q 0: turns 36 sched ba7081b07e61... root 6359768015cb...
net 0 q 1: turns 237 sched 65a18510c8f2... root 6359768015cb...
net 0 q 250: turns 75 sched 61a115d13c28... root 6359768015cb...
net 0 q 500: turns 63 sched 0fdd6a149267... root 6359768015cb...
net 0 q 1000: turns 39 sched 4a540b3571ff... root 6359768015cb...
net 0 q 2000: turns 39 sched aad7602f6e07... root 6359768015cb...
net 0 q 8000: turns 36 sched 0e429002ff4d... root 6359768015cb...
net 1 q 0: turns 36 sched ba7081b07e61... root 4b96f68ffb15...
net 1 q 1: turns 197 sched 325ed9d9ccb8... root d9c68f9de4f1...
net 1 q 250: turns 75 sched 61a115d13c28... root 6359768015cb...
net 1 q 500: turns 63 sched 0fdd6a149267... root 24e5653ceaeb...
net 1 q 1000: turns 39 sched 4a540b3571ff... root 445146d9fd5a...
net 1 q 2000: turns 39 sched aad7602f6e07... root ed5d700571e8...
net 1 q 8000: turns 36 sched 0e429002ff4d... root 4b96f68ffb15...
deadlock: waiting: task 1 task 2
net 2 q 0: deadlock
deadlock: waiting: task 1 task 2
net 2 q 1: deadlock
net 3 q 0: turns 3 sched 4cd0a7bea55b... root e3b0c44298fc...
net 3 q 1: turns 5 sched 58ad90527a0f... root e3b0c44298fc...
net 4 q 0: turns 3 sched 437219f37ccc... root 7f6181ef67ec...
net 4 q 20: turns 9 sched f9bbd2e8da91... root 7f6181ef67ec...
net 5 q 0: turns 3 sched 6e685030a945... root e3b0c44298fc...
net 5 q 1: turns 3 sched 6e685030a945... root e3b0c44298fc...
net 6 q 0: turns 3 sched b7225a5c4223... root 08afccbc84a6...
net 6 q 1: turns 326 sched ebf3b837ba4f... root 08afccbc84a6...
net 7 q 0: turns 3 sched 562e66a710e9... root e3b0c44298fc...
net 7 q 1: turns 3 sched 562e66a710e9... root e3b0c44298fc...
net 8 q 0: turns 3 sched e755475b5aea... root e3b0c44298fc...
net 8 q 1: turns 4 sched b55351030b0f... root e3b0c44298fc...
```

Net 0 (rule-following): one root `6359768015cb...` in 7 runs under 7 quanta with 7 different schedule
digests, equal to the root the hosted runtime computes with no scheduler. Net 1 (the control): 6
different roots in 7 runs. Nets 2 to 8 are described in `docs/shepherd.md`. The `deadlock:` lines and the
`task N faulted` records are in the full transcript and are decoded by the checker.

## Mutation tests of the new checks

| id | mutation | caught by |
| --- | --- | --- |
| M1 | no quantum point in `cint_rt_host_call` | one schedule digest, golden |
| M2 | module-state table shared between tasks | net 4 root, golden |
| M3 | net 0 receives with `chan_recv_any` | net 0 root differs from the twin's, golden |
| M4 | channel end not checked (either end) | net 3, golden |
| M5 | net 0 receive order swapped | net 0 root differs from the twin's, golden |
| M6 | quantum fires one count late | golden only |
| M7 | channel capacity 3 | golden only |
| M8 | a send ignores a full channel | net 0, golden |
| M9 | quantum point after the charge | golden only |
| M10 | blocked tasks always look ready | net 2 (no deadlock line), golden |
| M11 | quantum start not set at create | golden only |
| M12 | events dropped | net 0 root, golden |
| M13 | event value truncated to 8 bits | net 0 root, golden |
| M14 | a refused channel operation returns OK | net 3, golden |
| M15 | receiver check done as the sender check | net 0 and net 3, golden |
| H1 | task guard pages not installed | boot status 63, net 5, golden |
| H2 | IST guard pages not installed | page table check (12 of 12), golden |
| H3 | no `-fstack-clash-protection` | boot status 63, net 5, golden |
| H4 | trap record from the kernel's context | net 6 records differ, golden |
| H5 | guard of one page | net 6 offset, golden |
| H6 | overflow keeps its fuel count | golden only (and gcc against clang) |
| H7 | overflow of a task is a panic | boot status 63, net 5, golden |
| H8 | stack-overflow record names the wrong task | net 5, golden |
| K1 | receiver end not checked | net 3, golden |
| K2 | digest drops the reason for a turn's end | digest recomputed from the printed turns, golden |
| K3 | quantum boundary not aligned | golden only |
| K4 | a task of net 4 calls a kernel extern | net 4, golden |
| K5 | placeholder site is zero | boot status 63, net 7, golden |
| K6 | every extern allowed to tasks | net 8, golden |
| K7 | stack budget ignored | net 7, golden |
| K8 | tasks use the kernel's state table | net 4, golden |
| K9 | printed turn state is wrong | digest recomputed from the printed turns, golden |
| K10 | net 7 budget not applied | net 7, golden |
| K11 | channels not closed between nets | golden only |

All 34 were caught. Rows marked INVALID by the driver (a build error under `-Werror`, which fails
a gate for the wrong reason) were redone: M4 (first form), K6 and K7 (first forms). Each
mutation was a one-place edit in a copy under `/tmp/opencode`, built with gcc only, and run through
`tools/run-qemu.sh`, `tools/check-shep.py` and the golden. "Golden only" rows change where a turn
ends, not a property of the network: the golden transcript is what pins that. Two advisors also
ran 8 and 12 mutations of their own in copies (their findings are in `docs/notes.md`); they are
not in this table.

## Findings that changed the work

* My first design for the quantum (a soft `fuel_limit` and a yield inside `cint_rt_fault_fuel`) is unsound:
  EMIT-28 leaf functions drop the slow path's result. Found by review, confirmed in the emitted C
  (`docs/shepherd.md`); filed as pennyleans/cint#512. The quantum ends a turn at host calls instead.
* QEMU `-icount shift=0` makes one binary reproducible and not portable: 6, 7, 232 and 233 preemptions for gcc and
  clang at `-O2` and `-O0`, against 4 or 5 with no `-icount` (`docs/shepherd.md`).
* A guard page alone is not enough: at `-O2` gcc inlined a chain into one frame of 28,672 bytes and one
  subtraction stepped over the guard. A guard of two pages and `-fstack-clash-protection` fix it; removing the flag
  makes `net 5` fail.
* cint's frame arena charges arrays when a call crosses a module boundary, and not in one module with no cycle
  (pennyleans/cint#500, a comment). The old statement in `docs/runtime.md` was incomplete.
* A trap record was made from the kernel's context, so a probe in a task recorded the kernel's call stack
  (found by `net 6`); now it is made from the running context.
* Review defects, all fixed: a record with no live call had no valid position and its print panicked; a task could call any
  extern; the receiver end of a channel and the content of the schedule digest were untested; two quanta gave one schedule; a check was dead.

## Deviations from the plan (`docs/shepherd.md`, "What is not here")

* No journal, commit points, Merkle tree, or kill-and-restore (G3, G4): K5's, on the advice of both advisors.
* No page-level single owner (G2): one address space, and door 1 is closed by construction and by the task-allowed list.
* G5 is a finding, with numbers, not a gate; G6 (the cintc hook) was not built because the host-call quantum does not need it.
* W^X for the first 2 MiB and the overflow of an IST stack are not done.

## Full log of the clean-clone run

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
PASS  build: gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt shep (make)
PASS  build: every gcc-k1 object was compiled by gcc (.comment names it)
PASS  build: every clang-k1 object was compiled by clang (.comment names it)
PASS  build: the gcc and clang images differ (two different compilers built them)
image sha256:
  gcc-k1  dbd422744211a54bf95f54d20426be7fa22d2b96e63ee1de58e2d668921b47f2
  gcc-fault  99295d15fd09b425537485c8fe223e6657b5150209e4ac146457014933575fce
  gcc-trap  ec6bbd6d22079ac59aa2c346c2d1f48f0c07a8f3c99c33b7a58805e1e21b6b66
  gcc-stackover  4656e9497c82d8095959d759a4ecf45d564e5a119f925f6e94d44a152344663b
  gcc-nullptr  cc5ed2624af6309ca08fe318e5dce332b07f4aa3b474eb57ea01f220f130f767
  gcc-faults  7602542f2ff75195c41f0f2dc51652ef4452edefcf985257ef3d264ad5c3118c
  gcc-mem  4a98e5628a9dbb6c7db55f7720b929881edfef3833a6b98a51aaa269a03dbf06
  gcc-coop  062505e636598d0eafb7508d84ce8fdaff8d1afe069a20ad9ca40cda9825c0f5
  gcc-preempt  a2ba83a380a893217ba6312fbc889633fdf7f3c62e4614bd1490fdbfce43d89d
  gcc-shep  b0609371dcbd0c8914db25e0ac0a9855f5f689830b4e621404fca3f849f04fe1
  clang-k1  91787c8aad19577c82744da0d86e9380ef4071056d89b1e1f36da8a0435cc2b4
  clang-fault  9528a78d909a04bcfb3ff9fbfe56c05d750f9e428adf1701bde8a33f0f137d39
  clang-trap  b31e131202ed2612631c8a2f5ccb352b178e769e15f4d671274aa76f05c0769d
  clang-stackover  c1cf99e55cd40049cb8633b4819e5a7e6de5a54c22a8b22bde8faced4d610ad2
  clang-nullptr  c5b81838d244288f6bba1a94e8d7b4a7824c0fa8ddba56a98f7b6a067a0e1d1c
  clang-faults  33bfb548a3256f4ce757af40de5b9129cb050e452514bde360bab84820048397
  clang-mem  8d78e1a157fffd2aceb4bde504daa0a71138a87be06afacd20e49489970f43ad
  clang-coop  68c301932d574c0d702c8a7945a9863567160083cb8386273b04ec4d4c9e2925
  clang-preempt  66e5825e3469475dff8598669cf4f032181aeae66cad009e6ca48d2e7ace41d1
  clang-shep  09279a399f65424f9ce4f96020641046cb93c5b01079d488b65dbad27b00e628
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
PASS  audit gcc-shep: every object's undefined symbols are defined in this build
PASS  audit gcc-shep: image has no undefined symbol (nm -u empty)
PASS  audit gcc-shep: no libc symbol in any object or the image
PASS  audit gcc-shep: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-shep: no SSE, AVX or x87 instruction in any object
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
PASS  audit clang-shep: every object's undefined symbols are defined in this build
PASS  audit clang-shep: image has no undefined symbol (nm -u empty)
PASS  audit clang-shep: no libc symbol in any object or the image
PASS  audit clang-shep: mem functions are exactly the four of rt/mem.c
PASS  audit clang-shep: no SSE, AVX or x87 instruction in any object
PASS  K0: symbol audit ran and passed (100 checks, 5 per build, gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt shep)
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
PASS  boot gcc-shep: QEMU exit status 33 on both runs
PASS  boot gcc-shep: QEMU wrote nothing to stderr
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
PASS  boot clang-shep: QEMU exit status 33 on both runs
PASS  boot clang-shep: QEMU wrote nothing to stderr
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
  gcc-shep run 1  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  gcc-shep run 2  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
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
  clang-shep run 1  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  clang-shep run 2  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
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
PASS  serial shep: gcc and clang transcripts byte-identical (cmp)
PASS  serial shep: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial shep: clang run 1 and run 2 byte-identical (cmp)
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
PASS  shep: the hosted twin ran the network with no scheduler and wrote its root (6359768015cb7e63bb670a771405a698df4e2567e23d103d298e785e82fb9b5b)
PASS  serial shep: gcc transcript equals tests/expected/shep.skeleton (record hex masked)
PASS  shep gcc: one root under 7 schedules (the twin's), digests differ, control splits, deadlock and fault as expected
PASS  serial shep: clang transcript equals tests/expected/shep.skeleton (record hex masked)
PASS  shep clang: one root under 7 schedules (the twin's), digests differ, control splits, deadlock and fault as expected
PASS  shep: only src/ownstate.c (the module-state test) asks for module state; the network's modules ask for none
PASS  shep -O0 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O0 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O1 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O1 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O3 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O3 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -Os gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -Os clang: boots (status 33) and the transcript equals the -O2 one byte for byte
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
elapsed: 123 s (budget 300 s)
PASS  time: whole check in 123 s, under 5 minutes
RESULT: PASS
```
