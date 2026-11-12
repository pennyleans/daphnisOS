# K2: traps and the timer

Flavor `trap` (`src/main_trap.ci`). It installs an IDT, provokes a divide error (#DE), an
invalid opcode (#UD) and a page fault (#PF), prints each as a fault record from cint, then
counts PIT ticks and prints the count.

## How an exception becomes a record

cint code never executes the faulting instruction directly. Each probe is an asm function
reached as an extern (`trap_probe_de`, `trap_probe_ud`, `trap_probe_pf(addr)`,
`arch/x86_64/trap.S`): `div` by zero, `ud2`, a load from `addr`. The exception enters the stub
of its vector, which saves all general registers and calls `rt_trap_dispatch` (`rt/trap.c`).
The dispatcher recognizes a fault whose saved RIP lies inside the probe block, builds the
record, sets the saved RIP to `trap_resume` (a `ret`), and returns; `iretq` resumes at the
`ret`, which returns from the probe to `cint_rt_host_call`. The cint code then asks for the
record through two externs (`trap_record_len`, `trap_record_byte(i)`) and prints it with its
own hex formatter (`src/text.ci`), in the same form `rt/ctx.c` uses for a real cint fault:

    trap de
    fault: cint-core-1/fault/v2 148 bytes
    <hex>

This is the "printed from cint" part: the bytes come from rt, the printing is cint.

## The record: an extension, not a cint fault

Hosted cint has no #DE; it checks a divisor before dividing. So there is no hosted record to
match, and the trap records are an extension in the shape of the only hosted analogue, the
boundary fault of a host call (SPEC-03 A-6, as `cint_rt_host_call` writes it):

* domain `cint-core-1/fault/v2`, code 10 (`E_UNSUPPORTED`);
* operation `host.error.trap_de`, `host.error.trap_ud`, `host.error.trap_pf`;
* operands: `I64` vector (0, 6, 14), `U64` error code, `U64` CR2 (0 unless #PF; the page fault
  probe makes both nonzero, below);
* no `exact`, no `limit`, no source-map digest, no address;
* position: the site of the extern call that ran the probe (`src/main_trap.ci`, the probe's
  line and column); stack: the context's (empty at the entry); revision: the program's.

The record never holds RIP or any address of the image: stub addresses differ between a gcc
and a clang link, and the transcript must not. A trap record is kept apart from
`rt_ctx.fault`, which belongs to real cint faults and is single-use. SPEC-03 A-6 (Proposed, SPEC-03:437) gives `host.error.<function>`, an entry sequence number
and the host status. These records differ: the name is `trap_de`, not the extern's name
`trap_probe_de`, there is no sequence number, and the operands are the vector, the error code
and CR2. That is the extension.

**This does not meet the K2 gate as DESIGN.html words it** ("provoked faults give the same
fault records as the hosted runtime, the same cint-core-1/fault bytes"). Hosted cint checks a
divisor before dividing and has no page fault, so there is no hosted record of these faults to
be equal to. What is delivered instead: the records are valid v2 records (decoded and
field-checked by `tools/check-trap.py`) and equal byte for byte between gcc and clang and
between runs.

The #PF probe is a write to `0x40000AB0 + 0x18`: the boot page tables map exactly the first
1 GiB, so this address is unmapped. A supervisor write to a non-present page has error code 2
(write, not present, supervisor), and CR2 is `0x40000AC8`. The displacement and the nonzero
error code make the record catch a handler that drops the error code, masks CR2, or reports a
register instead (the earlier read at a page-aligned address did not).

## IDT

`src/gate.ci` builds the two words of a 64-bit interrupt gate (pure, tested hosted);
`src/idt.ci` installs gates for vectors 0 to 47 through `trap_stub` (the stub address table of
`trap.S`) and `idt_set` (stores into the static IDT of `rt/trap.c`), then `idt_load`. Selector
`0x08`, type `0xE`, DPL 0, IST 0 (in the `trap` flavor, which loads no TSS; K3 below): an
interrupt gate clears IF, and a CPL 0 to CPL 0 trap does no stack switch. Vector 39 and 47 (spurious PIC interrupts) are ignored without an EOI. Any other vector, or a
fault outside the probe block, prints the vector and error code in decimal and panics (exit
63). A fault inside the dispatcher is such a trap: measured, a read of an unmapped address
there gives `unexpected trap, vector 14` and exit 63. Only a fault while the CPU is delivering
an exception triple-faults, for example the stack running into its guard page in an image
with no TSS (QEMU status 0, which the gate treats as a failure since it wants 33). K3 fixes
that for the images that load the TSS.

The dispatcher panics on a frame that is not 16-byte aligned or whose CS is not `0x08`, and a
probe fault with IF set (`rt_trap_dispatch`): interrupts must be off outside `cpu_wait_irq` (in the `preempt` image tasks run with them on, and
no probe runs then: `rt_probe` panics in a preemptible task),
and a last probe after the tick loop checks it.

Stack alignment in the stubs: 15 saved registers (120) + vector (8) + error code or dummy (8)
+ the hardware frame (40) = 176, a multiple of 16, and the CPU aligns RSP before pushing.

## Timer

`src/pit.ci` remaps the two 8259 PICs to vectors 32 to 47, unmasks only IRQ 0, and programs
PIT channel 0 as a rate generator with divisor 1193 (about 1 kHz), then reads the status back
(read-back command `0xE2`) and the count, and prints a line if it is not mode 2, lo/hi, with a
count within the divisor. The BIOS leaves the PIT at 18.2 Hz, so a timer never programmed
would otherwise still reach 100 ticks, only slower. Interrupts are off
everywhere except between the `sti` and the `cli` of `cpu_wait_irq` (`sti; hlt; cli; ret`), so
the IRQ handler (`rt_trap_dispatch`, vector 32: increment a counter, EOI) never interrupts
cint code, the serial driver, or a record in progress. cint loops 100 times calling
`cpu_wait_irq`, then prints `ticks: 100`.

What is printed is the number of waits the cint code made, not the handler's counter. After
`iretq` with IF set, a second pending timer edge could in principle be taken before the `cli`
runs (a vCPU descheduled for over a millisecond), making the handler's count 101. The cint
code instead checks that the handler count is at least the number of waits and prints a
shortfall line otherwise, which the check treats as a failure. No elapsed time, tick rate, or
address reaches the transcript. How long the 100 ticks take on the host varies; the bytes do
not. If interrupts never arrive (for example, no EOI), `hlt` hangs and the 30 second watchdog
(status 124) fails the check; with four boots that case takes about 150 s, still under the
budget.

## In the gate

`check.sh` boots the `trap` image on gcc and clang twice each: exit status 33, byte-identical
transcripts (gcc against clang, run against run), the transcript equal to
`tests/expected/trap.skeleton` with the record hex masked (the hex carries the program
revision, which changes with any source change), and `tools/check-trap.py`, 26 checks that
decode each record and compare every field, the position, the empty stack and the revision
with what the probe must produce.

## K3 hardening: the TSS, IST stacks, the null page (`stackover`, `nullptr`)

A 64-bit TSS (`rt/trap.c`, 128 bytes) holds three 16 KiB interrupt stacks: IST1 for #DF, IST2
for the NMI gate (vector 2), IST3 for #PF. `src/tss.ci` builds the descriptor words (pure,
tested hosted, with the IST offsets 36, 44, 52 written out as constants, not computed by the
formula under test: the first version stored them at the wrong byte offsets and triple-faulted,
which a review found); `src/cpu.ci` writes the descriptor into GDT slot `0x18` through
`gdt_set`, points the IST entries at their stacks (`tss_set_ist`, `ist_top`), loads it
(`tss_load`, `ltr`, once: a second `ltr` is a #GP because the first marks the descriptor busy)
and installs gates with `src/gate.ci`'s `gate_lo_attr(offset, selector, ist, attr)`
(IST in bits 32 to 34, attribute 0x8E present or 0x0E not present).

When the TSS is loaded, a trap record has a **fourth operand**: `U64` the IST index the frame
was on (0 to 3), and `rt_trap_dispatch` panics if a #DF, NMI or #PF frame is not inside its
IST stack. The K2 `trap` flavor loads no TSS and keeps its three operands. The probes moved to
`arch/x86_64/probe.S`; each saves RSP at entry, and a fault in a probe is recorded and resumed
at a `ret` with RSP restored from that saved value, so a probe returns after even a stack
overflow or a failed instruction fetch. A fault is accepted only while a probe runs
(`rt_probe_active`), with RIP inside the probe block, or, for a failed fetch (error code bit 4,
RIP the called address), only if RIP equals CR2 and the call's return address is the resume
point; a #DF's RIP is undefined by the architecture, so it is not checked; a second fault in
one probe panics.

`stackover` flavor, four records (`tools/check-records.py`):

| Record | Operation | Operands (vector, error code, CR2 or offset, IST) |
| --- | --- | --- |
| stack overflow: push until the guard page | `host.error.trap_stack` | 14, 2, `0xFF8` (the offset of CR2 inside the guard page: no image address enters the record), 3 |
| `int 2` | `host.error.trap_nmi` | 2, 0, 0, 2 |
| a #PF while the #PF gate is not present | `host.error.trap_df` | 8, 0, 0, 1 |
| a #PF, gate restored | `host.error.trap_pf` | 14, 2, `0x50000018`, 3 |

`int 2` is a software interrupt through the NMI gate, not a real NMI (no NMI blocking, no
local APIC); it shows the gate and its IST stack. The #DF case relies on QEMU TCG escalating a
#PF whose delivery fails (a not-present gate raises #NP, which after a #PF is a double fault);
the escalation itself is architectural (SDM table 6-5: a #PF followed by a contributory
exception is a #DF), but a #DF is an abort: its RIP is undefined and resuming after it is not
defined on hardware, which QEMU TCG happens to allow. Checked on QEMU 11.1.2 only.

`nullptr` flavor, two records: the null page (PT entry 0) is not present. A write at `0x18`
is a #PF with error 2, CR2 `0x18`; a load from 0 is a #PF with error 0, CR2 0. Only the first
4 KiB are unmapped (that page holds the real-mode vector table and the BIOS data area, which
nothing reads); the rest of low memory stays writable, and the loader's structures (QEMU puts
them at `0x9000`) are read through the shim's low window, which starts at `0x1000`.

A stack overflow *outside* a probe on the boot stack, in an image with the TSS, is a #PF in the guard page
that the dispatcher turns into `panic: kernel stack overflow (guard page) outside a probe`, exit 63, instead
of a triple fault. No flavor provokes it from cint code on the boot stack, because whether a chain of local
arrays survives optimization is the compiler's choice (the array may be removed), so the `stackover` flavor
overflows with an assembly probe. K4.5 provokes a task's overflow from cint code (below), with the arrays
passed to a function of another module so that no compiler can drop them.

## K4.5: guard pages under task and IST stacks (`shep` flavor)

* Every task stack and every IST stack has a guard of two pages below it, not present in the boot
  page table (`rt_guard_pages`, `rt/phys.c`: it clears the entries of boot.S's `pt`, which cint
  reads and never writes). Two pages, because a frame holds at most a 4,096 byte array and a few
  words and could step over one; and `-fstack-clash-protection` makes a larger frame touch each page.
  `src/guards.ci` reads the page table through the view shim and the gate requires 12 of 12 guard
  pages absent and the first page of each of the 6 stacks present.
* A #PF in a task's guard while no probe runs: `rt_task_stack_overflow` (on the IST3 stack,
  interrupts off) gives the task the record `host.error.task_stack` with one operand, `I64` the task
  number (1 based), position the first call of the task's entry (or, when no call is live, the first
  site of the root module, `rt_placeholder_site`: a zero site does not encode and the print would panic),
  no stack, and ends its turn as faulted; the IST3 stack is free again at once. No address, offset, error code or fuel count is in
  it: where the first touch falls depends on the compiler's frames. The scheduler prints `task N faulted`
  and the record like any other fault. Check: `net 5`, same bytes on every compiler and `-O` level.
* A probe that runs a task's stack into its guard (`net 6`) is recorded as `host.error.trap_stack`
  as in `stackover`, with CR2 as an offset in the two guard pages (8184: the first push below the
  stack), IST 3. K3 made this record from the kernel's context; K4.5 makes every trap record from the
  context that is running (`rt_task_ctx`), so a task's record holds the task's stack. Found by `net 6`:
  the record differed by which kernel line had started the run.
* An overflow of an IST stack itself is not provoked: it would be a #DF on IST1 and the
  kernel's panic path. The guards are present and checked, and nothing overflows them.
