# Boot, build flags and exit codes

## Boot method: Multiboot 1 with QEMU's `-kernel`, and Multiboot 2 with GRUB

From `cint-v0.2.12` `boot.S` carries both headers. `make hello` also builds `daphnis.iso`: GRUB 2.12
(`tools/build-iso.sh`, `grub-mkrescue`) boots the ELF64 `kernel.elf` through its `multiboot2` command, and
`tools/run-qemu.sh` boots a `.iso` with `-cdrom`. The entry takes either magic and saves it (`mb_magic`) with `ebx`
(`mb_info`); `rt/boot.c` copies the loader's information block once before `main`, and the `mem` flavor reads
the memory map from the copy under Multiboot 2 (`docs/memory.md`, Multiboot 2 information). Results:
`docs/RESULTS-BOOT.md`. The text below predates that and covers the Multiboot 1 path every gate uses.

### In the gate: hello, and the ISO leg

`hello` is a flavor of `check.sh` like the others (`FL`, the Makefile's `FLAVORS`): built by gcc and clang, audited
(5 checks per build), booted twice per compiler from `kernel32.elf` with `-kernel` (status 33), and each transcript
compared to `tests/expected/hello.serial` (19 bytes, `hello from Daphnis\n`).

The ISO leg (block 4b) runs when `grub-mkrescue` and `xorriso` are both on PATH: `make hello` builds `daphnis.iso`
and `mem` per compiler (`tools/build-iso.sh`, which also needs GRUB's `i386-pc` modules and `mtools`). Each hello
ISO boots once with `-cdrom`: status 33, nothing on stderr, the transcript equal to the same golden. Each mem ISO
boots once with `-m 128` in block 5d: status 33, the transcript equal to `tests/expected/mem.skeleton` (record hex
masked), the memory map read from the Multiboot 2 tags. That is 5 PASS lines. Without the tools the leg prints
one `SKIP` line naming them instead.

The last line of `check.sh` counts what it printed: the PASS lines (the audit's included) must equal a fixed number
(`gate_want`, plus `iso_pass` when the ISO leg ran), and the `SKIP` line must be there exactly when the leg did not
run. A gate that runs fewer checks than it should, the ISO leg skipped on a machine that has the tools included,
fails there.

| machine | tools | ISO leg | PASS lines |
| --- | --- | --- | --- |
| Arch (QEMU 11.1.2), before B-3 | no GRUB, no `xorriso` | one `SKIP` line | 328 |
| Arch (QEMU 11.1.2, gcc 16.2.1, clang 23.1.3), B-3 | `grub` 2:2.16-1.1, `libisoburn` 1.5.8.2-1.1 (`xorriso` 1.5.8.pl02; Arch has no package named `xorriso`), `mtools` 1:4.0.50-1.1; pulled in: `libburn` 1.5.8-1.1, `libisofs` 1.5.8.2-2.1 | runs, 5 PASS lines | 333, measured twice, 338 s and 294 s (CI runners busy, load 10 to 14) |
| cloud container (Ubuntu 24.04, QEMU 8.2.2, GRUB 2.12) | `grub-pc-bin`, `grub-common`, `xorriso`, `mtools` (Arch names: `grub`, `xorriso`, `mtools`) | runs, 3 PASS lines (B-1) | 331, measured in 219 s |
| the same, after B-2 | the same | runs, 5 PASS lines (the mem ISO boots of block 5d) | 333, measured in 225 s: mem under GRUB equals `mem.skeleton` on gcc and clang |

QEMU loads a Multiboot 1 image directly, in 32-bit protected mode, with no boot loader and no
disk. This box has no `grub-mkrescue` or `xorriso`, and nothing may be installed beyond QEMU,
so a GRUB image (Multiboot 2) was never an option; the direct load is also the smallest.
Multiboot 1 has one catch: QEMU's loader refuses an ELF64 image ("Cannot load x86-64 image,
give a 32bit one"). So the link produces `kernel.elf` (x86-64) and `objcopy -O elf32-i386`
turns it into `kernel32.elf`, which is what QEMU boots. The code is still 64-bit code: the
conversion only changes the ELF container, which is why everything links below 4 GiB.

`arch/x86_64/boot.S` (142 lines) does the rest:

1. `cli`, `cld`, the magic in `eax` saved (`mb_magic`), a check that it is one of the two Multiboot
   magics (else halt), and the information pointer (`ebx`) saved (`mb_info`) for `rt/boot.c`. The
   Multiboot 1 header asks for the map (flag bit 1).
2. Clear `.bss` (it holds the page tables and the stack, so they start zeroed).
3. Build the page tables: PML4 -> PDPT -> PD. PD entry 0 points at a page table of 4 KiB
   pages over the first 2 MiB (the image's low window: the runtime's code and data, tables, stack),
   PD entry 1 at one over 2 to 4 MiB (the high window: all of the emitted cint, then the module-state
   pool, which may run on into PD entry 2); every other PD entry is a 2 MiB page, so the first 1 GiB is identity mapped. The 4 KiB page just below the stack is left *not
   present*: a stack overflow takes a page fault instead of overwriting the page tables. The
   null page (PT entry 0) is not present either: a null access is a #PF. Without a TSS the CPU
   cannot deliver the guard-page fault on the overflowed stack, so it is a triple fault (QEMU
   status 0, see Exit codes); with the TSS of K3 (`docs/traps.md`) it is delivered on IST3.
4. CR4.PAE, EFER.LME and EFER.NXE (bit 63 of an entry means no-execute), CR0.PG, CR0.WP (a write
   to a read-only page faults in ring 0 too) and CR0.PE; load a GDT in `.data` (null, 64-bit
   code `0x08`, data `0x10`, and a free 16-byte slot at `0x18` that cint fills with the TSS
   descriptor, `src/tss.ci`); far jump to 64-bit code, load the data selectors, set RSP, call
   `rt_start`.

`rt_start` (`rt/start.c`) calls the `main` that cintc emitted. That `main` calls
`cint_program_run_args`, which `rt/ctx.c` implements: it sets up the one context, binds the
externs (`rt/host.c`), runs the cint entry, and on a fault prints the record. `rt_start` then
writes the exit value to the isa-debug-exit port `0xF4` and halts.

Build with `-DBOOT_TRACE` to have the stub write `B` (entry) and `L` (long mode) to COM1; this
is for placing a triple fault. The default image writes nothing before cint code runs, so the
transcript starts with the cint banner.

Memory map: image at 1 MiB (`arch/x86_64/linker.ld`, two PT_LOAD segments: text, rodata and data are
RWE, `.bss` is RW; a linker `ASSERT` keeps the low window below 2 MiB), then `.bss`: page tables, one guard page, a 128 KiB stack.
The high window starts at 2 MiB: the code, read-only data, data and bss of every `em_*.o` (`.high_text`,
`.high_rodata`, `.high_data`, `.high_bss`, which `boot.S` clears with `.bss`); a second `ASSERT` ends it by
4 MiB. The pool comes last (`.high_pool`: the state pool of `rt/ctx.c` and the capture keys, every `.high.data`
input): it follows the high window and may run past 4 MiB into PD entry 2's 2 MiB page, writable and
no-execute after `rt_wx_init`; a third `ASSERT` ends the image by 6 MiB. It left the window's bound when gcc 16
emitted the cint of `gcc-user` about 80 KiB larger than gcc 13 and the window, holding the 256 KiB pool too,
ran 12 KiB past 4 MiB (PR 346). A user space maps only the low window (`docs/user.md`), so the high one and
the pool hold only what is touched under the kernel's own tables.

## Compiler flags and why

| Flag | Why |
| --- | --- |
| `-std=c17 -O2` | the emitted C is C17 (EMIT-01). The audit and boot also pass at `-O0`, `-O1`, `-O3`, `-Os` (checked once by hand, not part of `check.sh`) |
| `-ffreestanding -nostdlib -fno-builtin` | no hosted environment, no libc, no builtin lowering of `mem*` and friends to calls we did not write |
| `-fno-stack-protector` | no `__stack_chk_fail` |
| `-mno-red-zone` | required once interrupts run on the kernel stack (K2) |
| `-fno-pic -fno-pie` | the image is linked at a fixed address |
| `-mcmodel=small` instead of `-mcmodel=kernel` | the brief named `kernel`. That model assumes the image sits in the top 2 GiB of the address space. This image links at 1 MiB, identity mapped, which is the small model's assumption exactly. A higher-half kernel (later stage) needs `kernel` and a different loader |
| `-mgeneral-regs-only` | no SSE or x87 instruction, so no FPU or SSE state to enable at boot or to save in trap stubs. Enforced by an objdump scan in the audit |
| `-fcf-protection=none` | no `endbr64` landing pads or CET notes |
| `-fno-asynchronous-unwind-tables -fno-unwind-tables` | no `.eh_frame` |
| `-DCINT_RT_HELPERS_PORTABLE` | selects `cint_rt.h`'s portable helpers. The default on gcc and clang is the builtin mode, which uses `__int128` and may call `__udivti3` from libgcc |
| `-fno-tree-loop-distribute-patterns` (gcc) | stops gcc turning the byte loops of `rt/mem.c` into calls to themselves |

The linker is GNU `ld` for both compilers, called directly (not through the compiler driver):
`ld -m elf_x86_64 -nostdlib -z max-page-size=0x1000 -z noexecstack --no-warn-rwx-segments
--orphan-handling=error -T arch/x86_64/linker.ld`. One linker removes a variable from the
gcc-versus-clang comparison. The `.got`, `.iplt` and `.rela.*` sections the linker creates for
static code are discarded in the script; any other orphan section fails the link.
`--no-warn-rwx-segments` only silences the warning for the flat RWE segment.

Assembler stubs go through `-x assembler-with-cpp` with the compiler under test, so gcc builds
use GNU as and clang builds use clang's integrated assembler. Both images pass.

## QEMU command and two deviations from the brief

```
qemu-system-x86_64 -display none -serial stdio -monitor none -nic none -accel tcg -m 128 \
    -no-reboot -device isa-debug-exit,iobase=0xf4,iosize=0x04 -kernel IMAGE < /dev/null
```

(`tools/run-qemu.sh`, with a 30 second watchdog.) The brief listed `-nographic -serial stdio
-no-reboot -no-shutdown`. Two of those do not work on QEMU 11.1.2, both measured here:

* `-nographic` sends SeaBIOS's console text to the serial port: the transcript starts with
  `ESC c ... SeaBIOS (version Arch Linux 1.17.0-2-2)` and `Booting from ROM..`. `-display none`
  with the default VGA keeps BIOS text on the (invisible) VGA console. `-nic none` removes the
  iPXE banner.
* `-no-shutdown` makes `isa-debug-exit` pause the VM instead of exiting: with it the same image
  runs until the watchdog (status 124), without it the status is 33. isa-debug-exit goes through
  QEMU's shutdown request, which `-no-shutdown` turns into a pause.

`-accel tcg` keeps host CPU features out of the picture; `-m 128` (every flavor since G-0, the
pool ending at 96 MiB; `MEM` in `tools/run-qemu.sh`), no network, no monitor, and
stdin from `/dev/null` keep the run closed.

## Exit codes

isa-debug-exit makes QEMU exit with status `(value << 1) | 1`, so a status of 0 cannot be
requested: **"exit QEMU with code 0" is not achievable, and an exit status of 0 means
something else.** With `-no-reboot`, a triple fault ends QEMU with status 0 (measured: a ud2
with no IDT installed). A guest crash would therefore look like success if success were 0. The
mapping used:

| Guest writes to port 0xF4 | QEMU status | Meaning |
| --- | --- | --- |
| `0x10` | 33 | clean exit (K1 banner and SHA-256 done; K2 traps and ticks done) |
| `0x11` | 35 | a cint fault ended the entry; the record was printed |
| `0x1F` | 63 | rt panic: unresolved extern, a record that does not encode, an unexpected trap, or an entry that ended neither OK nor in a fault (rt prints `daphnis: entry status N`) |
| (none) | 0 | triple fault or other QEMU-level reset (the images without the TSS, on a stack overflow) |
| (none) | 124 | the 30 second watchdog fired: a hang |
| (none) | 1 | QEMU itself failed to start |

## What the symbol audit means

`tools/audit-symbols.sh`, per compiler and flavor: (1) in every object, each undefined symbol is
defined by another object of the same build (the emitted `cg_`, `ci_`, `cm_` symbols and the
`rt/` entry points) or by the linker script (`__bss_start`, `__bss_end`); (2) the linked image
has an empty `nm -u`; (3) no libc symbol in any object or the image, against a deny list that
includes the string and I/O functions, `__stack_chk_*`, `__udivti3`-family, soft-float
helpers; (4) the `mem*` functions in the image are exactly `memcpy`, `memmove`, `memset`,
`memcmp`, all defined by `rt/mem.c`; (5) no SSE, AVX or x87 instruction in any object.
The image-level `nm -u` is nearly redundant, since `ld` refuses undefined symbols; it only
catches weak undefined ones. Check (1) is the one that proves the objects need only `rt/`.
