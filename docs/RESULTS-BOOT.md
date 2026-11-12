# Boot and print at cint-v0.2.12

Sprint plan, section 4. Measured 2026-11-04 in a cloud
container (Ubuntu 24.04, x86-64). QEMU is the triage tier (ruling of 2026-10-26), not evidence.

## Result

| compiler | loader | image | QEMU status | serial transcript | transcript sha256 |
| --- | --- | --- | --- | --- | --- |
| gcc 13.3.0 | Multiboot 1, `-kernel` | `gcc-hello/kernel32.elf` | 33 (ok) | `hello from Daphnis\n` | `565e6cf0...7e6413` |
| gcc 13.3.0 | Multiboot 2, GRUB 2.12 `-cdrom` | `gcc-hello/daphnis.iso` | 33 (ok) | `hello from Daphnis\n` | `565e6cf0...7e6413` |
| clang 18.1.3 | Multiboot 1, `-kernel` | `clang-hello/kernel32.elf` | 33 (ok) | `hello from Daphnis\n` | `565e6cf0...7e6413` |
| clang 18.1.3 | Multiboot 2, GRUB 2.12 `-cdrom` | `clang-hello/daphnis.iso` | 33 (ok) | `hello from Daphnis\n` | `565e6cf0...7e6413` |

Four boots, one transcript, 19 bytes, nothing before it. The stub halts on any magic but the two Multiboot ones, and
GRUB's `multiboot2` command hands over only the Multiboot 2 magic, so status 33 from the ISO is the Multiboot 2 path.

| measure | value |
| --- | --- |
| images built at the pin | 24 of 24 (12 flavors, gcc and clang) |
| K0 symbol audit (`tools/audit-symbols.sh`) | 120 PASS, 0 FAIL: no undefined symbol, no libc symbol, mem functions only from `rt/mem.c`, no SSE, AVX or x87 |
| hello `kernel.elf` text, data, bss (gcc) | 32,010, 8,204, 843,904 bytes |
| hello `kernel.elf` text, data, bss (clang) | 36,398, 8,208, 842,848 bytes |
| K1 and K3 under Multiboot 1 | K1 transcript unchanged on both compilers; mem transcript equals `tests/expected/mem.skeleton` on both (`-m 128`) |
| K3 mem under Multiboot 2 | faults at its memory-map read, as designed: `src/memmap.ci` reads the Multiboot 1 layout only |
| `check.sh` at this pin, clean clone of that commit | 308 PASS, 0 FAIL, `RESULT: PASS` (gcc, clang, QEMU 8.2.2; the K5 replays and kill-restore included) |
| Multiboot info address | QEMU `-kernel`: 38,144 (`0x9500`, 591 bytes), inside the read window of `rt/phys.c`. GRUB `multiboot2`: 1,048,680 (`0x100068`), in the header page of the image itself, outside that window: a probe flavor measured both, not committed |

## Toolchain

| item | value |
| --- | --- |
| cint | `cint-v0.2.12`, built here with `python3 tools/cint_bootstrap.py --leg gcc --out DIR` |
| `cint --version` | `cint 0.2.12`, compiler source identity `6cf79840...67dd65cb`, runtime contract `cint-rt-3` |
| QEMU | 8.2.2 (Ubuntu `qemu-system-x86`) |
| GRUB | 2.12 (`grub-pc-bin`, `grub-common`, `xorriso`, `mtools`) |

## What the re-pin took

cint-v0.2.12 emits lean calls (cint OQ-320). Its C calls two runtime entry points the old pin never named, and its
header declares a third:

| entry point | emitted at v0.2.12 | where in this tree |
| --- | --- | --- |
| `cint_rt_lean_fail` | yes (faults, mem, k5 flavors) | `rt/ctx.c` |
| `cint_rt_lean_unwind` | yes (faults, mem, k5 flavors) | `rt/ctx.c` |
| `cint_rt_fault_arith_cold` | no (declared in `cint_rt_lean.h`) | `rt/fault.c` |

Each is the hosted `rt/cint_rt.c` body, unchanged. Without them 6 of 22 images fail to link. Nothing else changed:
`cint_rt.h` still includes only `limits.h`, `stdbool.h`, `stddef.h` and `stdint.h`, and now also `cint_rt_lean.h`.

## Commands

```
python3 tools/cint_bootstrap.py --leg gcc --out PIN          # in a cint checkout at cint-v0.2.12
export PATH=PIN:$PATH
make O=BUILD CINT_TOOLCHAIN=PIN/cint.toolchain all hello
tools/audit-symbols.sh BUILD "gcc clang" "hello k1 fault trap stackover nullptr faults mem coop preempt shep k5"
tools/run-qemu.sh BUILD/gcc-hello/kernel32.elf T1.txt         # Multiboot 1
tools/run-qemu.sh BUILD/gcc-hello/daphnis.iso T2.txt          # Multiboot 2, GRUB
```

## Gaps for cint 0.4

Item 17 of `docs/cint-gaps.md`.
