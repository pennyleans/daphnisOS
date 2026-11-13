# Ring 3: user processes (U1-1 to U1-5)

Specs: `docs/specs/2026-11-05-u1-1-ring3.md`, `docs/specs/2026-11-05-u1-2-musl.md`, `docs/specs/2026-11-05-u1-3-files.md`, `docs/specs/2026-11-05-u1-4-procs.md`, `docs/specs/2026-11-05-u1-5-shell.md`. This file says how it is built.
The `user` flavor runs static ELF64 Linux programs in ring 3 and serves their system calls in cint.

## 1. One turn

```
cint kernel (src/proc.ci)          rt/user.c                   arch/x86_64/user.S          ring 3
  user.user_enter(pid, root) --->  sanitize the saved frame -->  save kernel regs, RSP, CR3
                                                                 fxrstor, FS base, CR3 = root
                                                                 copy frame to entry stack, iretq -->  runs
                                                                                              syscall / fault / IRQ
                                   rt_user_trap(frame)  <------  trap_common (trap.S)  <-----
                                   fxsave, save frame, events
  <--- kind (1, 2, 3)  <---------  user_leave(kind): kernel CR3, RSP, regs, ret
  serve it in cint, pick the next process, enter again
```

| kind | cause | the kernel does |
| --- | --- | --- |
| 1 | `syscall` (the entry builds a ring 3 frame, vector 256) | `proc.syscall`: RAX is the number, RDI RSI RDX R10 R8 R9 the arguments; the result goes back in RAX |
| 2 | an exception (vector, error code, CR2 for `#PF`) | prints it and ends the process with the signal Linux would send |
| 3 | the timer or a spurious PIC interrupt | moves the process to the back of the round robin |

Interrupts are enabled only in ring 3 (the saved RFLAGS always has IF; rt forces it and clears IOPL, TF, NT and AC).
The kernel runs with IF clear, as in every other flavor. The return to ring 3 is always `iretq`. Selectors follow
Linux: user data `0x2B`, user code `0x33` (GDT slots `0x28`, `0x30`, after the TSS); STAR also holds `0x20` in
bits 63:48 for a later `sysretq`. TSS.RSP0 is the top of a 16 KiB entry stack in `rt/user.c`, abandoned at every
`user_leave`. `#PF` and `#DF` keep their IST stacks.

The FPU and SSE (U1-2): `user_cpu_init` clears CR0.EM and TS, sets CR0.MP, CR4.OSFXSR and OSXMMEXCPT. The kernel is
built `-mgeneral-regs-only`, so it never touches that state: rt `fxsave`s it into the process's 512-byte area when a
turn ends and `user_enter` `fxrstor`s it when one starts. A new process starts as Linux starts one: FCW `0x37F`,
MXCSR `0x1F80`, everything else 0. The FS base (`arch_prctl`, thread-local storage) is a per-process word written to
`MSR_FS_BASE` on every entry.

## 2. Memory

| range | what | rights |
| --- | --- | --- |
| `[0, 2 MiB)` | the kernel image's low window (code, data, tables, stacks), boot.S's page table under PD[0]; the high window at 2 to 4 MiB and the state pool after it (to at most 6 MiB) are not in a user space | supervisor only: no U bit |
| `[2 MiB, ...)` | the program's `PT_LOAD` segments, then the break (`brk`) from the page after them, up to the mmap area | U; W if `PF_W`; no-execute unless `PF_X`; the break RW |
| `(..., 0x7FFF00000000)` | `mmap`: anonymous pages from the top down, a bump pointer per process, never reused | the `prot` asked |
| `[0x7FFFFFFDF000, 0x7FFFFFFFF000)` | the stack, 128 KiB | U, W, no-execute |

Every table and page is a pool frame (`src/frames.ci`, `[32 MiB, 96 MiB)` since G-0), zeroed when taken; a process may hold
15,360 (60 MiB, `uvm.MAX_FRAMES`: the pool less `frames.RESERVE`, the 1,024 frames kept for the kernel's own takers; M-1,
`docs/specs/2026-11-06-m-memory.md`; 16,384 at G-0, 2,048 at U1). That is the one limit: `mmap`, `brk` and `execve` have no
size of their own and fail with `-ENOMEM` (the break as it is, for `brk`) where the quota or the pool ends; `getrlimit`
and `prlimit64` report it as `RLIMIT_AS` (and the stack as `RLIMIT_STACK`), fixed, `-EPERM` on a change.

The pool is the machine's (M-3, `docs/specs/2026-11-06-m-memory.md` section 9): with `daphnis.pool=max` on the loader's
line (`tools/run-qemu.sh POOL=max`, `tools/play.sh` always) the kernel takes every usable frame of the memory map from
32 MiB to 8 GiB, the frames that are not RAM and the region 1 to 2 GiB (`src/paging.ci`'s and the fault probes')
taken from the start, and prints `daphnis: pool N frames usable of 2088960 to M MiB`; the quota (`frames.quota()`)
and `RLIMIT_AS` follow. Without the word the pool is the 16,384 frames of the gates. At 512 MiB the pool is 480 MiB,
at 4 GB about 3 GB (the 1 GiB region and the PCI hole are out).

A granted page is a promise (M-2): the last-level entry is not present, holds no frame and carries bit 11 (`LAZY`)
with the rights in its W, NX and U bits; the pool holds a free frame for it (`frames.held`, which `frames.alloc`
leaves alone, so a promise is always kept). The first touch backs it with a zero frame: from ring 3, a not-present
page fault on a lazy page (`uvm.back`), after which the process goes on with nothing printed; from the kernel,
`translate` backs the page before it copies (a `read` into fresh memory, the loader's bytes, the tiler's compose).
A page `mprotect`ed to `PROT_NONE` keeps its promise (bits 9 and 11), as a backed page keeps its frame. `fork`
promises again what the parent only promised and copies what it backed. The state digest hashes a promise as the
zero page it will be, with its rights, and counts it, so the digest is of the memory a process was granted: it is
the same whether a page was backed at the call or at the touch, and no timing (the kernel's compose, the timer)
reaches it. Linux's oracle sees the same: `mmap` succeeds or is `-ENOMEM` at the call, never later. The tables are the whole record of a process's memory: a last-level entry is a page (present, U), a
reserved page (not present, bit 9: `PROT_NONE`, keeping the frame it had if `mprotect` took its rights, so they can
come back), a promise (not present, bit 11, below), or nothing. When a process ends, `uvm.destroy` walks the tree and gives back every table and page it
finds; the transcript ends with `fs tables T frames held` and `pool frames free F of N`, F + T = N (FS-4: the
filesystem's entry table and its 1,024 open file descriptions lie in pool frames, so the pool is whole but for them). cint reaches user memory only by walking the
process's own tables (`uvm.translate`, the P and U bits at every level and W at the page) and copying through the
view shim, so a bad user pointer is `-EFAULT`, never a kernel fault.

The initial stack is the Linux one: `argc` 1, `argv[0]` the name, an empty environment, and the auxiliary vector
`AT_PHDR`, `AT_PHENT`, `AT_PHNUM`, `AT_PAGESZ`, `AT_ENTRY`, `AT_UID` to `AT_EGID` (0), `AT_SECURE` 0, `AT_RANDOM`
(16 fixed bytes), `AT_NULL`. Without the four ids musl takes its secure path.

## 3. System calls

| nr | call | does |
| --- | --- | --- |
| 1, 20 | `write`, `writev` | by what the descriptor is: the console (COM1; held and printed afterwards when processes run together) or a file; a bad buffer `-EFAULT` |
| 9, 10, 11 | `mmap`, `mprotect`, `munmap` | anonymous memory, section 2; `mmap` of `/dev/fb0`, section 11 |
| 12 | `brk` | section 2; a failure returns the break as it is, as Linux does |
| 97, 302 | `getrlimit`, `prlimit64` | `RLIMIT_AS` the quota and `RLIMIT_STACK` the stack, fixed (M-1, section 2); a new limit `-EPERM`, another pid `-ESRCH`, any other resource `-ENOSYS` |
| 13 | `rt_sigaction` | K-10 (`src/job.ci`): records `SIG_IGN`; any other handler reads back as `SIG_DFL`, since no handler frame is built; `sigsetsize` not 8, a signal past 64, or `SIGKILL` or `SIGSTOP` given an action `-EINVAL`. Fork and `execve` keep what is ignored. `kill`, `SIGPIPE` and a pty's `ISIG` (section 9a) pass over an ignored signal; a fault's signal does not |
| 14, 28 | `rt_sigprocmask`, `madvise` | 0 |
| 109, 111, 112, 121, 124 | `setpgid`, `getpgrp`, `setsid`, `getpgid`, `getsid` | K-10: groups and sessions named by the pids the family sees; a process the kernel starts leads its own; fork keeps both; `setpgid` moves the caller or its child within the session (a session leader `-EPERM`; no `EACCES` after `execve`); `setsid` `-EPERM` when a group of the caller's pid exists; KF edition 14: `getpgid` and `getsid` of a process the caller may not see (`facts.sees`) `-ESRCH` |
| 16 | `ioctl` | the two `FBIOGET` calls on `/dev/fb0` (section 11); `-ENOTTY` on anything else open (the serial line is a byte stream, as the oracle's pipe is), else `-EBADF` |
| 35, 228, 230 | `nanosleep`, `clock_gettime`, `clock_nanosleep` | the virtual clock: per process, 0 at its start, read then 1 us on, moved by what a sleep asks; `CLOCK_REALTIME` is the boot's base (2026-01-01T00:00:00Z, or the machine's date under A-3) plus the system's time line where the program started plus the process's clock (RS-CLK2): a program started after another slept reads after it, and no file stamped before it started is in its future (the stamp time of FS-R3 C is the same line); a running process reads no earlier than that line either. On a boot that took a date (A-3) the system's time is instead the whole seconds the PIT has run since the date was taken, the desk's clock, so `date` in Console and the bar agree; a process's own sleeps move only its own reads. Those seconds are printed and journaled `wal S N` as they pass, and a replay takes them from the journal, never the PIT; on the fixed epoch the timer never reaches it. A timespec with seconds below 0 (signed) or nanoseconds of a second or more is `-EINVAL`; any other is a sleep, one past what the clock holds sleeping to its end. On a live boot that took the machine's date (RS-SLEEP, U1-2 edition 2) a sleep also waits that time on the PIT before it returns; the clock still moves by exactly what it asked. Beyond that one case the timer and the host never reach the clock, with one exception: `clock_gettime(CLOCK_BOOTTIME)` (G-2) reads the wall clock, the PIT's ticks since boot in nanoseconds (10.0002 ms a tick; real time under KVM, dilated under TCG). It is not a function of the process's own history; no digest holds it, and a process that never asks for it is as deterministic as before (`doom --live` asks; `doom --sealed` never does). The same holds for three counts of `facts` (1007, ruling KF-R1): the processor's busy and idle time (kind 1, bytes 64 and 72) and a process's CPU time (kind 2, byte 88), in whole timer ticks; they are wall time, never in a snapshot, a digest or the volume, and a replay does not reproduce them. Monitor reads them; no gate transcript may print them |
| 227 | `clock_settime` | RS-CLK: `CLOCK_REALTIME` only, every other id `-EINVAL`; in Linux's order, a bad pointer `-EFAULT`, nanoseconds of a second or more or seconds at or past Linux's settimeofday bound (8277292036, in 2232) `-EINVAL`, then a caller neither uid 0 nor holding `GRANT_KERN` `-EPERM`. From then on every process, running or started after, reads the seconds set and runs on from them by its own clock (RS-CLK2), the desk's clock shows them, and the stamp time of FS-R3 C runs from them, back or forward. On a boot that took a date (A-3) the set prints `clk S` and is journaled; a replay takes the journal's seconds, and a boot that read the CMOS clock writes the set back to it, so it survives a restart. On the fixed epoch the set lasts for the boot |
| 0, 2, 3, 4, 5, 6, 8, 17, 19, 21, 32, 33, 72, 79, 80, 87, 217, 257, 262, 263, 269, 292 | files and descriptors (U1-3) | section 8 |
| 22, 57, 59, 61, 62, 110, 293 | `pipe`, `fork`, `execve`, `wait4`, `kill`, `getppid`, `pipe2` | processes and pipes (U1-4); KF edition 14: `kill` of a live process the caller may not see `-ESRCH`, as for none (Linux: `-EPERM`) | section 9 |
| 157, 186, 102, 104, 107, 108 | `prctl`, `gettid`, `getuid`, `getgid`, `geteuid`, `getegid` | the comm (U1-5, section 10); the pid the process sees; 0 |
| 39, 218 | `getpid`, `set_tid_address` | the pid the process sees: 1 alone, its number from 1 among processes started together (the kernel's slot is not shown; stage R's sealed pid 1) |
| 60, 231 | `exit`, `exit_group` | ends the process |
| 158 | `arch_prctl` | `ARCH_SET_FS`, `ARCH_GET_FS` |
| 41, 49, 44, 45, 51, 54 | `socket`, `bind`, `sendto`, `recvfrom`, `getsockname`, `setsockopt` | N-2: `AF_INET` `SOCK_DGRAM` (`SOCK_NONBLOCK`, `SOCK_CLOEXEC`), address 10.0.2.15; a socket is a descriptor of kind 11 (`KIND_SOCK`; the volume holds 9 and 10) with a receive ring of 8 datagrams (`src/udp.ci`, `src/sock.ci`); `recvfrom` without a datagram waits for the device as `read` of the event stream does, or `-EAGAIN` when non-blocking; `setsockopt` is accepted and ignored. N-4: without the net grant (`grant net CMD`, GR-1 A) `socket` is `-EACCES`, after the family and type checks, as Linux's security hook places it The network ticks at the scheduler's halt, when every process is blocked (docs/specs/2026-11-05-n-net.md section 9, N-3) |
| 42, 50, 43, 288, 52, 48 | `connect`, `listen`, `accept`, `accept4`, `getpeername`, `shutdown` | N-3: `SOCK_STREAM`, a descriptor of kind 12 (`KIND_TCP`) over `src/tcp.ci` (8 connections, one segment in flight); `read`, `write`, `readv`, `writev`, `sendto` and `recvfrom` work on it; a write sends at most one segment and returns that count; a call that must wait for the peer waits for the device, or `-EAGAIN` (`connect`: `-EINPROGRESS`) when non-blocking |
| 7, 271 | `poll`, `ppoll` | E-1: each descriptor's events as a read or a write of it would wait (pipe ends and pty ends as Linux answers them, a UDP socket by its queue; files, directories, the console, a TCP socket and the input device ready), `POLLNVAL` for a closed one, a negative one skipped; at most 256. Nothing ready and a wait above 0 parks the call. It expires, returning 0 and moving the clock on by the wait, only when every process waits; after one expiry with nothing ready since, the next waits for a device, so an idle editor does not spin (`docs/specs/2026-11-06-e-editor.md` 4a). `ppoll`'s mask is ignored |
| other | | `-ENOSYS` (-38) |

## 4. Programs and the image

`user/*.S` are seven static ELF64 programs, no libc, assembled and linked once by the system `as` and `ld` with
`user/user.ld`, stripped. `user/bin/musltest` is one static musl binary (`user/c/musltest.c`, built once by
`user/c/build.sh`, ruling DU-2 A) that does what its name says and sits in the image under eight names: `mprintf`,
`mmalloc`, `mbrk`, `mprot`, `mclock`, `mtls`, `ssea`, `sseb`. `tools/mkcpio.py` packs them into a cpio `newc`
archive with fixed inode numbers, owner, mode and mtime, one file under several names as one inode with that many
links (its bytes with the last member, as Linux writes hard links; `proc.lookup` follows them). `arch/x86_64/initrd.S`
embeds the archive (`.incbin`) in the user image only, so the gcc and the clang kernel run the same bytes.
`tests/expected/user.sha256` pins all fifteen. U1-5 made the archive a loader module.

## 5. The canonical state digest

SHA-256 of `0x54 | 22 words (u64) | the FPU state (345 bytes) | the open descriptors (FS-4: a count u16, then for each open one its number u8 and 19 bytes) | the working directory
(filesystem u8, 1 the ramfs, 2 the volume; inode u64) | the grant word (u64, 0 until P-3) | the surface (kind u8, 0 none,
1 the framebuffer, 2 private; w, h, stride u32; the tile input queue's length u8, 0 until W-3) | the comm (16 bytes) |
the sockets (N-2: 24 bytes per descriptor that holds one, in descriptor order; none for a process without) | the ring
of the volume's changes (FF-1: entries posted u64, entries waiting u64, the loss flag u8, for a process that holds
`/dev/fsidx`; none for a process without) | per page
in address order: address (u64), rights (u8), its 4,096 bytes if it has a frame, the dead stack as zeros | page count
(u32)`, all little endian (edition 9, FS-4: the open descriptors only, each with its number, since a table of 256
would be mostly zeros; edition 8, FF-1: the ring record; a process without `/dev/fsidx` digests as in edition 7;
edition 7, W-4: the bytes of the 128 KiB stack below RSP and its 128-byte red zone count as
zeros, since they follow the order in which independent events reached the process; edition 6, W-2; edition 5, P-0 and N-2, had no surface; edition 4, tag `0x53`, had no working directory and
no grant word). The words are the 15 general
registers, RIP, RSP, `RFLAGS & 0xCD5`, the FS base, the break base, the break and the clock. The FPU state is FCW, FSW,
the abridged FTW, MXCSR, ST0 to ST7 (10 bytes each) and XMM0 to XMM15; FOP, FIP and FDP are left out, since
processors differ in when they write them. A descriptor is its kind (u8: 0 closed, 1 the console in, 2 out, 3 a file,
4 a directory), the entry's inode (u64; 0 for the console and the root), the description's offset (u64), its flags (u8: access mode, bit 2
`O_APPEND`) and the descriptor's (u8: `FD_CLOEXEC`); no description index. Rights are 1 W and 2 X for a page, `0x80` for a reserved page plus
`0x40` if it keeps a frame. Nothing physical is in it. The gate shows no desync for `hello`, `mmalloc` on other frames
for `spin` and `ssea` under another schedule and for `mcat` after `mlitter`
and the filesystem reset, and a DESYNC for the two 1-bit canaries (RBX bit 0, MXCSR bit 0).

## 6. The oracle

`tools/check-user.py` reads each `daphnis: run NAME pid P` block of the transcript and runs the same file on the
host's Linux with `argv[0]` NAME, in a fresh directory unpacked from the image, with `tests/image/stdin.txt` (minus
its final 0x04) as stdin: stdout bytes and exit status or signal must be equal (37 blocks). Directory members of the
image are made as directories, and the temporary directory's own path in Linux's output reads as `/`, the root
Daphnis shows (P-0: `pwd` and `getcwd`). A canary block is not a
Linux run and is skipped by its form; so is a device block, `daphnis: run NAME pid P (device)` (section 11).

## 7. Limits of U1-5

One CPU. Thirty-two processes. Output of a process run together with others is held (256 bytes) and printed after
they end, in pid order, so the transcript does not depend on the timer. Sixteen children at once (slots 48 to 63);
a signal ends a process, there are no handlers; no `mremap` (`-ENOSYS`, musl copies instead); pages come eagerly, there
is no demand paging. The K5 journal does not cover user processes yet.

## 8. Files and descriptors (U1-3)

`src/fs.ci`. One flat root directory. Its files are the image's members, read where they lie in the image, with the
inode numbers the image gives them, in the image's order; a program may create files and write image files, which
copies them into frames first. FS-3: a file's bytes lie in a chain of pool frames, map frames each naming 511 data
frames and the next map; a page no write reached has no frame and reads as zeros, and a file grows to the process
quota (M-2 A) or until the pool is out (`-ENOSPC`). `fs.reset()` drops every created file and
copy and clears every description: the image's view again, so what a program left in the filesystem never reaches a
later run (stage R's sealed view). A process has 256 descriptors (FS-4, RV-4 A), a table in one pool frame taken at its first open and freed at
its end, the lowest free one given out; the system has 1,024 open file descriptions (`-ENFILE` past them) in 10
pool frames taken at boot, each on an open file
description (offset, flags, references) that `dup` shares; descriptions 0 and 1 are the console, shared by every
process. fd 0 reads the serial line as bytes arrive (`serialrx`, polled; the FIFO stays off, and `serial_init`'s
FIFO clear is not run, so no byte is lost); a byte 0x04 ends the input for good. `struct stat` is Linux's 144-byte
layout with device 1, times 0, block size 4,096; `getdents64` gives `.`, `..`, then the files in slot order. Since
P-0 the root holds directories too (section 15). No tty: `ioctl` is `-ENOTTY` on everything but the surface, which is what the oracle's pipe says too.

## 9. Processes and pipes (U1-4)

`fork` takes a free child slot (48 to 63) and copies the parent into it: every mapped page and reserved page through
`uvm.clone` (new frames, the same addresses), the saved frame, FPU state and FS base through `user_copy`, the
descriptor table through `fs.proc_clone` (the descriptions gain a reference), the break and the clock. The child
sees the next number of its family as its pid, its parent's number from `getppid`. `execve` reads the name and
`argv` out of the caller, destroys its space and loads the named image into a fresh one with those arguments and no
environment; descriptors marked `FD_CLOEXEC` close, the rest cross. `wait4` reaps a zombie child and writes Linux's
status word; a call that has to wait (an empty pipe with a writer open, a full pipe with a reader open, a child not
yet ended) returns `WOULD_BLOCK` inside the kernel, the frame is left as it is, and the scheduler makes the call
again before each pick, so the process resumes exactly where it asked. If nothing is ready and no waiting call can
ever be answered, the first such process ends with SIGKILL and the transcript says so. A pipe is a 4,096-byte ring in
one pool frame, held while either end is open; `write` with no reader is `-EPIPE` and the process ends with SIGPIPE,
`read` with no writer gives 0. A child that ends stays a zombie until reaped; a parent that ends first leaves its
children parentless, and the kernel reaps them. After the exit line of a process that forked, the transcript says
`daphnis: pid P forked N`. The pool is whole again once every process has ended.

## 10. The shell and the image as a module (U1-5)

busybox 1.36.1 (`user/bin/busybox`, static, musl, built by `user/busybox/build.sh` with `user/busybox/config.fragment`)
is `sh` in the image and runs the scripted session of `tests/image/stdin.txt`. The image is no longer embedded:
it is the loader's first module (QEMU `-initrd` under Multiboot 1, GRUB `module2` under Multiboot 2), found by
`rt/boot.c` in the information block and taken only when it lies above the image's end and below the pool, so a
kernel's bytes do not depend on the programs it runs and the two windows `boot.S` maps (to 4 MiB, the state pool to at most 6 MiB) hold the kernel alone. The
scripted input is read once at boot (up to a byte 0x04, or two seconds without a byte) into the kernel, and every
process the kernel starts reads it from its start through its own console-in description, which its children
share: each program sees the whole input, as the oracle's do. A process has a 16-byte comm (`prctl`
`PR_SET_NAME`, `PR_GET_NAME`), its name at start and `execve`; `execve("/proc/self/exe")` runs the process's own
image again with the comm `exe`, which is how busybox's standalone shell runs its applets. The digest (edition 4,
tag `0x53`) ends with the comm.

## 11. The surface (F-1)

`docs/specs/2026-11-05-f-surface.md`. `/dev/fb0` is a character device (29:0, 020666) that exists only when the kernel
found a framebuffer at boot (`daphnis: framebuffer 640x480 stride 2560`; else `daphnis: no framebuffer`). `ioctl`
`FBIOGET_VSCREENINFO` (0x4600, 160 bytes) and `FBIOGET_FSCREENINFO` (0x4602, 80 bytes) give the five words: 640, 480,
stride 2,560, XRGB8888, `smem_len` stride times height. `mmap(0, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0)` maps
the framebuffer as device pages (`src/uvm.ci`: bit 10 of the entry, user, writable, no-execute, caching off): not pool
frames, not in the process digest, the same pages in a fork, cleared by `munmap`, `execve` and the end of the process;
the kernel never copies for a process through them (`translate` refuses). `read`, `write`, `lseek` and any other
`ioctl` on the device are `-EINVAL`; `mmap` with any other descriptor is `-ENODEV`.

After a device block (`proc.run_device`) the kernel prints `daphnis: surface WxH stride S sha256 HEX`: SHA-256 over the
w x h pixels row by row, 4 bytes a pixel, never the padding (`src/surface.ci`, read back through the framebuffer window
of `rt/phys.c`). `mfb` draws red x * 255 / (w - 1), green y * 255 / (h - 1), blue (x ^ y) & 255; `tools/check-fb.py 640 480
TRANSCRIPT` computes the same digest on the host and checks every surface line. Two runs of `mfb`, the second with 37
frames held, give one surface and one process digest.

## 12. The input stream (F-2)

`/dev/input/event0` (13:64, 020666) is the keyboard as Linux `input_event`s: `rt/ps2.c` takes each scancode byte on
IRQ 1 into a ring; a `read` decodes the ring (`src/input.ci`: set-1 make and break codes to `EV_KEY` with the Linux
key code and value 1 or 0, `E0` arrows and right modifiers, `EV_SYN` after each) and copies as many whole 24-byte
events as fit, at least one, stamped with the reader's clock as `CLOCK_REALTIME` shows it. With nothing queued the
process waits: the scheduler, with nothing ready, halts until an interrupt and retries (1,500 halts, then SIGKILL and
`daphnis: input timeout`), so a device waiter never counts as a deadlock; under `O_NONBLOCK` the read is `-EAGAIN`.
`write`, `lseek` and `ioctl` on the device are `-EINVAL`, but for RS-KR's key repeat control: `EVIOCGREP` reads two
u32, the delay before the first repeat and the period between repeats in ms (500 and 33 at boot), and `EVIOCSREP`
sets them, the desk alone (`-EPERM` for any other; `-EINVAL` for a delay outside 100 to 2000 or a period outside 10
to 1000). `src/keyrep.ci` makes the repeats from the timer tick, for the PS/2 and the USB keyboard alike, as presses
(value 1): the device's queue, `src/inq.ci`, hands it each key event and asks it at each pull of `src/input.ci`, so a
repeat reaches a reader within a tick of being due; it drops the PS/2 keyboard's own repeats, and a modifier or a lock
key never repeats. When the USB keyboard goes, its held keys go up and the repeat ends. A named divergence from Linux (plan call,
2026-11-11 20:27Z): Linux's input core sends a repeat as value 2; Daphnis sends 1, as the PS/2 keyboard's own repeats
always reached the desk, so a reader tells a held key's repeats from a second press only by the release between
them. To revisit the day a program other than the desk reads the device and must tell a repeat from a press. The
gate types `a`, `b`, `c` through QEMU's monitor
(`tools/sendkeys.py`, `MONITOR=` of `tools/run-qemu.sh`) once the transcript shows each `mkeys` run line; `mkeys`
prints the six key events and the `EV_SYN` count, and two runs give one process digest.

The mouse (F-3) is on the same stream: IRQ 12 bytes go to a second ring; a three-byte packet becomes `EV_REL`
`REL_X` and `REL_Y` (down-positive) for the motion that is not 0, `EV_KEY` `BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE` for
each button that changed, then `EV_SYN`. The gate moves by (10, -5) and clicks left then right through the monitor;
`mmouse` prints the four button events, the motion sum and the `EV_SYN` count.

## 13. cint in ring 3 (R-1)

A cint program runs in ring 3 as any static ELF does: `user/ci/build.sh` emits it to C with the pinned `cint emit-c`
(as the kernel is emitted), renames the emitted main and builds it with `user/ci/main.c`, `user/ci/host.c`, the
toolchain's hosted runtime `cint_rt.c` (portable helpers) and musl, static, stripped. The same bytes run on Linux
and under Daphnis: the runtime's output is `write` on descriptor 1, a checked-arithmetic fault is one line on
descriptor 2, `fault[E_CODE]: operation at path:line:column`, with exit status 1 (`mci` overflows `fib(93)` on
purpose: `add.checked.i64 at user/ci/mci.ci:10:19`, and again on other frames with one process digest). The oracle
takes descriptors 1 and 2 together, as the console does. The externs of `user/ci/dev.ci` are rows of `host.c`,
each a few Linux calls: `fb_open` (`/dev/fb0`, the two `ioctl`s, `mmap`), `fb_word` (the five words, section 11),
`fb_row` (one row of XRGB pixels into the mapping), `ev_read` (one `input_event`, `O_NONBLOCK`), `clock_ns`
(`CLOCK_MONOTONIC`, the virtual clock here) and `exit_now`; `main.c` binds them by name, with the effect class and
the type signature of the import row cintc wrote (SPEC-03 A-10). `mcifb` draws `mfb`'s pattern from cint and the
surface digest is the pin of section 11; `msha` digests 4 MiB with `src/sha256.ci` in 58 timer ticks (about
0.6 s under QEMU's TCG here, 44 ms on the host), the measure that sizes the stage R chain. The binaries are
committed under `user/bin` (ruling DU-2 A); a module array holds at most 65,536 elements, so a program streams
larger data through a buffer, and the frame arena is 1 MiB (`user/ci/host.h`), well under a process's quota.

## 14. The doom program (R-2a to R-2d)

`doom` (`user/ci/doom/`, GPL-2.0) is the cint port of linuxdoom-1.10's load side: the WAD directory, the engine's
tables, the textures, flats, sprites and colormaps, and the level (`docs/specs/2026-11-05-r-desync.md` sections 6
and 10). It opens `e1m6.wad`, `tables.bin` and `info.bin` from the current directory, the image's root under Daphnis,
and the program reads them through two host rows, `file_size` and `file_read`, into its module arrays, so the WAD
(2.5 MB) is held once in cint; the process holds about 11 MB and a process may now hold 16,384 frames (64 MiB,
`uvm.MAX_FRAMES`, G-0). It prints the sizes, the level's counts, `H_0` (SHA-256 over the WAD then the demo lump) and the
store digest (SHA-256 over every loaded word), the same five lines on Linux and here; `tools/check-doom.py` checks
the counts against the reference tool's record (`tests/expected/doomref.txt`) and `H_0` against the host's digest
of the files. `lseek` and `pread` take any offset up to 2 GiB (`SEEK_MAX`); before R-2a the bound was the 64 KiB a
created file may reach, which no image file past that size could be read through.

R-2b plays the demo: `g_game.ci` reads the demo lump's header and ticcmds and `p_logic.ci` is the engine's
simulation (thinkers, map objects, movement and collision, specials, the player and weapons, the monsters) in one
module, with the random table of `m_random.ci`. The client calls the program's `tic` entry 350 times; each tic the
program prints the player's `x`, `y`, `z`, `angle`, health, both random indexes and the palette index, and the
client hashes the state modules' variables (444,082 bytes) into the chain, `H_t = SHA-256(H_{t-1} | t | S_t)` from
`H_0`, and ends the line with it; `doom: end tics 350` closes the run. `tools/check-doom.py` checks every tic's
words against the reference tool's; the chain is pinned by `user.serial`. The port's departures from the engine, none of
them reached by this demo, are listed in the spec's section 10.

R-2c draws: `r_bsp.ci`, `r_segs.ci`, `r_plane.ci` and `r_things.ci` are the engine's renderer, `v_video.ci` the
screen with the column and span drawers, `st_stuff.ci` the status bar and `hu_stuff.ci` the message line. Each tic
the frame `F_t` (the 320 x 200 screen and the palette number, 64,001 bytes) joins the chain after `S_t` (686,956
bytes over eleven state modules), and the tic line carries the screen's own SHA-256 as `frame`, which
`tools/check-doom.py` checks against the reference tool's at every tic: the port draws what vanilla Doom draws,
pixel for pixel. The client writes the frame 2x at the top left of the surface through PLAYPAL after every tic
(`--headless` skips the surface; `--frame-out PATH` writes the last frame), and under Daphnis `doom` runs as a
device program, so the kernel's surface digest after the run is pinned by the transcript and checked against the
blit of that frame. The 350 tics take 1.75 s on Linux and the user flavor boots in 26 s under TCG (its QEMU
watchdog is 60 s).

R-2d seals it. `doom --sealed` prints the load lines, then `doom: tic T sha256 H_t` for each tic, the challenge's
line, and `--canary` flips bit 0 of the play random index after the load, so its chain differs from tic 1 on.
`check-doom.sh` is the sealed run's own gate: on Linux the committed client, and the same emitted C built by the
host's gcc and clang, play `tests/expected/doom.tics`; under Daphnis the doom flavor (`src/main_doom.ci`) runs
`doom --sealed` alone, then busybox sh runs the churn of `tests/image/churn.txt` (`mchurn`'s maps, files, pipe,
forks and kills and full descriptor table, the shell's own files and pipelines, three descriptors left open)
and `./doom --sealed` as its child, then the canary, on gcc, clang and both through GRUB. Both sealed runs are
`doom.tics` line for line, the surface after each is the last frame 2x, the canary desyncs at every tic, and every
transcript is `tests/expected/doom.serial`. The kernel hands a started program its arguments
(`proc.push_arg`); a program the shell starts gets them through `execve` as before.

The budget split (2026-11-05): every doom run is in the doom flavor, on `check-doom.sh`'s budget.
The budget widened (2026-11-06): `check.sh`'s
budget is 480 s; it ran 312 to 345 s of 360 on the cloud after G-0, W-4, G-1 and H-R1, so a merge could fail on time alone.
The checked R-2c run left the user flavor (pid 46) for the doom flavor's fourth run, `doom` unsealed (pid 4),
whose level counts, tic words, frame digests and surface `tools/check-doom.py` checks against
`tests/expected/doomref.txt` on all four legs; the Linux run against the same record moved with it. Its chain
equals `doom.tics` at all 350 tics. The client and its bundle left the user image (909,036 bytes, from 4,892,372),
so only the doom flavor's image carries them, and `check.sh` no longer runs doom.

Live play (G-1, `docs/specs/2026-11-05-g-episode.md`): `doom --live [--skill N] [--warp M]` starts a new game
(skill 1 to 5, default 3; map 1 to 9, default 1; the E1M6 bundle carries map 6 only until G-3's `e1.wad`) and
plays it from `/dev/input/event0`, read non-blocking through `ev_read` by `user/ci/doom/d_event.ci`: vanilla's
default bindings (arrows, `,` and `.` strafe, Ctrl fires, Space uses, Alt strafes, Shift runs, 1 to 8 weapons,
Pause; the mouse turns and moves, left fires, right strafes, middle moves forward, a double click uses), Esc
ends the run. Each ticcmd goes through the demo's byte form, so a record of it replays it (G-4). d_event is not a
state module, and a sealed run never reads the device: `doom.tics` is unchanged. The live flavor
(`src/main_live.ci`, `make FLAVORS=live`) runs `doom --live --warp 6` as pid 1; `check-doom.sh` types a script
through the QEMU monitor and `tools/check-live.py` checks the player moved, turned and fired.
G-2: the live run's tics follow `clock_gettime(CLOCK_BOOTTIME)` at 35 Hz (TryRunTics: every tic due, at most five,
then one draw). G-4: `--record PATH` writes the run's ticcmds as a demo (version 109); at its end the run replays
its own record sealed in a fresh context and prints `doom: live tics T sha256 H_T`; `doom --sealed --demo PATH`
plays a record in place of the WAD's DEMO1 and prints the same chain.

Stage G-3 (`docs/specs/2026-11-05-g-episode.md` section 8): the episode. `g_game.ci` runs vanilla's game states,
so a demo crosses level exits (the secret exit too), the intermission (`wi_stuff.ci`), deaths and reloads, and the
E1M8 finale (`f_finale.ci`), with the screen wipe between states (`f_wipe.ci`) and the fast and nightmare tables.
`user/ci/doom/data/e1.wad` is all of E1. `doom --demo PATH` plays a demo file in place of the WAD's DEMO1;
`--exit-at N[s],...` is the test exits' list; an intermission or finale tic prints `doom: tic T wi|fi rnd R prnd P
pal I`, and each melt step of a wipe `doom: wipe T K frame HEX`. `check-episode.sh` (Linux only) plays the three
test demos of `tests/episode/` on the committed client and on the host's gcc and clang builds against the
reference tool's records, line for line.

Stage G-5: playing the episode. The play flavor (`src/main_play.ci`, `make FLAVORS=play`) carries `e1.wad` in its
image and reads `daphnis.skill=N`, `daphnis.warp=M` and `daphnis.seal=1` from the boot line (`src/bootarg.ci`,
a row of the play kernel only). `tools/play.sh [SKILL [MAP]]` builds it and a volume, boots it under KVM in a
window (`tools/run-qemu.sh` with `PLAY=1`), and copies the record `g.lmp` off the volume when Esc has ended the
run; `tools/episode-cut.sh g.lmp` cuts it into `e1.wad` as DEMO1 and writes `tests/expected/episode.tics`, which
`check-episode.sh` then plays on every build.

## 15. Directories (P-0)

`docs/specs/2026-11-05-p-disk.md`, unit P-0. A slot of `src/fs.ci` is one directory entry: a name of up to 255
bytes (FS-4; 31 before), the directory holding it (a slot, or the root, which has none) and either a file's bytes or a directory.
The image's members are placed by their cpio paths: `tools/mkcpio.py` takes `DIR/` for a directory member (mode
040755), which comes before what it holds, and the image carries `etc/` and `etc/motd`. A path is walked component
by component from the root (a leading `/`), the process's working directory, or the directory open on an `*at`
call's descriptor: `.` stays, `..` goes up and the root's parent is the root; every component but the last must be
a directory that exists (`-ENOENT`, `-ENOTDIR`), a component past 255 bytes (`NAME_MAX`) is `-ENAMETOOLONG`, and so is a path
of 4,096 bytes or more (`PATH_MAX`, with its NUL; FS-4, RV-4 A); the slots lie in pool frames, eight to a frame,
so their number is bounded by the pool, not by a constant; an empty path is `-ENOENT`. Devices keep their absolute names.

The working directory is a slot or the root, inherited by `fork`, kept by `execve`, the root again for every
process after `fs.reset()`; a directory open on a descriptor or held as a working directory stays until the last
holder lets it go, and once removed it lists nothing, `getcwd` in it is `-ENOENT` and nothing can be made in it.
The calls are Linux's: `mkdir`, `mkdirat`, `rmdir` (`-ENOTEMPTY`, `-EINVAL` on `.`, `-EBUSY` on the root),
`unlinkat` with `AT_REMOVEDIR`, `unlink` of a directory `-EISDIR`, `rename`, `renameat` and `renameat2` without
flags (the entry keeps its slot and inode; a file or an empty directory under the new name goes; a directory
into itself `-EINVAL`), `chdir`, `fchdir`, `getcwd` (walked up through the parents), `openat`, `newfstatat`
(`AT_EMPTY_PATH` is `fstat`) and `faccessat` with a directory descriptor, `open` with `O_DIRECTORY`, and
`getdents64` of any directory (`.`, `..`, then its entries in slot order, `DT_DIR` or `DT_REG`). A directory's
`stat` has 2 links and one more for each directory in it, size 0. `execve` walks its path the same way to an
image member; a file a program made is `-ENOENT` as before, a directory `-EACCES`.

The gate: `mdirs` (pid 47) makes, walks, opens by a directory descriptor, moves, refuses and removes directories,
with the working directory through `chdir`, `fchdir`, a forked child and a removed directory, and prints each
result and `errno`; the scripted session adds `mkdir -p`, `cd`, `pwd`, `mv`, nested paths, `ls -R` and `rmdir`
(busybox gains `mkdir`, `rmdir`, `mv` and `ls -R` in `user/busybox/config.fragment`). Both are Linux's byte for
byte on gcc and clang. `mls` prints `dir` for a directory, whose size is the host filesystem's own number.

## 16. The kit and the tiler (W-1)

The kit (`user/ci/kit/`) is what every Daphnis program draws with (`docs/specs/2026-11-05-w-tiler.md` sections 2
and 3): `grid.ci` cuts a screen into cells by checked integer division, the remainder to the last column and row,
and gives the last pixel of each cell to its 1 px hairline, so a 2 x 2 grid of 640 x 480 has insides of 319 x 239;
`face.ci` is one bitmap face, 8 x 16, the 95 printable ASCII glyphs, written by `tools/face.py` from its drawing
(monoline, cap height 10, x-height 7, a glyph's body in columns 1 to 6); `tokens.ci` is the six colors as one table
of XRGB words; `mark.ci` is Daphnis's 1-bit mark in the OS (ruling MK-1), 16 px high, a counter-change disc and
"daphnis" in the face, written by `tools/mark.py`; `draw.ci` paints a rectangle, a frame, a line of the face and the mark at 1x or
2x into one row of a surface at a time, since a module array holds at most 65,536 elements and the surface contract
hands rows over. The tokens are the opencut lockup's five words (ruling W-2 A: paper `F3EFE6`, ink `141413`,
ultramarine `1A4B8C`, yellow ochre `E5A900`, cadmium red `D62828`). The first tiler did not use the burnt sienna token.

`tiler [--cols N] [--rows N] [--mark-only | --face-only] [--surface-out PATH]` draws the grid: paper, the ink
hairlines, a title band in each tile (its column, row and inside size, a rule under it), the mark before the title
of tile 0,0 and the 2 px ultramarine focus frame around it. It prints each tile's place and inside, then
`tiler: surface WxH stride S sha256 HEX` over the pixels row by row; `--surface-out` writes the same bytes to a
file, through the rows `out_open` and `out_put` of `user/ci/outfile.ci`. `main.c` now hands a program its
arguments (`main(in U8[_] args)`, SPEC-04 LS-221), and a `main` without the parameter never reads them.
`tools/check-tiler.py` draws the same rules in Python and checks eight cases (the face and mark tables against
their generators, 2 x 2, 3 x 2, 3 x 7, the mark, the face glyph by glyph, the five digests against
`tests/expected/tiler.digests`, a refusal); `check.sh` runs it on the
committed `user/bin/tiler`, and `check-tiler.sh` adds the host's gcc and clang builds and checks the three give one
digest a case. W-1 runs on Linux only.

## 17. Tiles in the kernel (W-2)

Every process has a surface (`src/tile.ci`, ruling WT-1 A): none, the framebuffer, or a private surface of its own
pages. A process that opens `/dev/fb0` gets the framebuffer, as in stage R, until one asks `FBIO_TILER` (`0x4680`) on
it: that process is the tiler until it ends. The tiler sets the next client's tile with `FBIO_TILE_NEXT` (`0x4681`,
four u32: w, h, x, y, inside the screen), then starts the client; the client's `open("/dev/fb0")` takes that tile, and
`FBIOGET_VSCREENINFO` and `FBIOGET_FSCREENINFO` answer with its size and a stride of `4 * w`, so a stage R client
(`mcifb`, whose committed bytes did not change) draws into it unmodified. Its `mmap` of the surface gives fresh pages
of its own, read and write, in its canonical state as any page. While the tiler has the screen, an open with no tile
set is `-EBUSY`. The tiler waits in `FBIO_TILE_SYNC` (`0x4683`) while a client is bound; on each sync, at most once
every second timer tick, the kernel copies every bound client's surface into its tile through `fb_put` (`rt/fb.c`,
the kernel's one write to the framebuffer, bounded by it). Not every tick: the kernel runs with interrupts off, so a
tick that comes during the copies ends the next client's turn at once, and a copy longer than a tick (a slow host, a
large tile) copied again at every retry and left the clients no time (the tiler livelock, fixed after W-4). When a client ends, or `execve`s, its pages still mapped, the kernel
copies it once more and prints `daphnis: tile surface WxH at X,Y sha256 HEX` over its pixels, so the tile keeps the
client's last frame and the screen's digest at the end never depends on the timer.

`tiler --start PROG` (on the framebuffer only) claims the screen, draws the grid as W-1 does, sets tile 0,0's client
area (inside the focus frame, under the band's rule: 315 x 216 at 2,21 in 2 x 2) and runs PROG there through three
host rows of `user/ci/tilectl.ci` (`tile_ctl`, `spawn`, `reap`). The tile flavor (`src/main_tile.ci`, not in the
default flavors) boots `mcifb` fullscreen, then `tiler --start mcifb`; `check-tiler.sh` boots it on gcc and clang,
`tools/check-tiler.py --boot` checks the fullscreen surface (F-1's pin), the tiler's frame (the frozen 2 x 2 digest),
the client's surface (`mcifb`'s pattern at 315 x 216) and the screen (the frame with that pattern in the tile), and
each transcript is `tests/expected/tile.serial`.

## 18. Input to the focused tile (W-3)

While the tiler has the screen, another process's open of `/dev/input/event0` gives it a tile queue of 64 events in
place of the device (`src/tile.ci`), so a stage R client reads its tile's input at the path it already opens; a full
queue drops and counts. The tiler reads the device itself. `FBIO_TILE_SYNC` returns 1 when the device has an event,
2 when a process has ended since the tiler's last sync, and otherwise waits for the device as a reader of it does
(the copies of W-2 go on at each sync, at most once every second tick). The tiler routes each event to the client of the
focused tile with `FBIO_TILE_INPUT` (`0x4684`: u32 pid as the tiler sees it, u16 type, u16 code, i32 value), an
`EV_SYN` only after an event it routed. Super (`KEY_LEFTMETA` or `KEY_RIGHTMETA`, set-1 `E0 5B` and `E0 5C`) is the
tiler's: with it an arrow moves the focus frame (`tiler: focus C,R`) and q ends the focused client with `SIGTERM`
(`tiler: end client K in tile C,R`); neither Super nor a key pressed with it reaches a client. A tile set with
`FBIO_TILE_NEXT` is the tiler's next child's from its fork and stays across `execve`. At a queued client's end the
kernel prints `daphnis: tile queue N events given, U unread`; a queue's unread count is in the canonical state.

The tile flavor's third run starts three `mkeys` clients; `check-tiler.sh` types a, b, c, then Super+Right and a, b, c,
then Super+Left, Super+Down, a and Super+q through the QEMU monitor, and `tools/check-tiler.py --boot` checks that each
client read only what was typed while its tile had the focus, that no client read a chord, and the screen.

## 19. The desk (W-4)

The desk flavor (`make FLAVORS=desk`, `src/main_desk.ci`) boots to `daphnis: desk` and runs `tiler --cols 1
--rows 2 --desk` as the first process. The tiler opens a pty pair, draws a terminal of 79 x 13 cells in tile 0,0's
inside, starts busybox `sh` on the pair's slave, and offers tile 0,1 to the next client the shell starts: a tile of
320 x 200 at the center of its inside (`tiler: desk tile 1 at 159,269 inside 320x200 for the next client (0)`). The
tiler turns each key typed while the focus is on tile 0,0 into the bytes a US keyboard sends (Shift, Ctrl, Enter is
CR, Backspace is DEL; the arrows, Home, End, PgUp, PgDn, Insert, Delete and F3 as xterm sends them, with Shift and
Ctrl as `ESC [ 1 ; m`, E-3) and writes a key's bytes to the master in one write; it draws what the shell writes with `user/ci/terms.ci`, the
terminal both desks use (E-2, `docs/specs/2026-11-06-e-editor.md` section 5): printable ASCII, a UTF-8 sequence as
one `?`, CR, NL, BS and HT; the cursor moves (with CUU, CUD, CUF and CUB since K-9), erases, reverse video and the cursor's visibility of CSI; the scroll
region (BU-3: `ESC [ t ; b r`, `ESC D`, `ESC M`, `ESC E`, `ESC [ n S`, `T`, `L` and `M`); bold and the ANSI colors of SGR
as the kit's six tokens (ED-2 B); an OSC read whole; every other sequence dropped. `tools/check-tiler.py` checks it against its model through `tiler --term-only`. The desk ends when the shell ends: the tiler prints the shell's status, the
count and SHA-256 of the bytes it read from the master, and the 13 rows of the terminal as text.

A pty (`src/pty.ci`, two pairs) is `open("/dev/ptmx")` (`KIND_PTM`, 13) and `open("/dev/pts/N")` (`KIND_PTS`, 14), as
musl's `openpty` does it (`TIOCSPTLCK`, `TIOCGPTN`). The slave has a canonical line discipline: `ICANON`, `ECHO`,
`ECHOE`, `ICRNL` and `ONLCR`, `VERASE` DEL, `VKILL` Ctrl+U, `VEOF` Ctrl+D; `TCGETS`, `TCSETS`, `TCSETSW`, `TCSETSF`,
`TIOCGWINSZ` and `TIOCSWINSZ` work and any other request gives `ENOTTY`. K-10 adds `ISIG` (on by default): `VINTR`
Ctrl+C and `VQUIT` Ctrl+\\ raise `SIGINT` and `SIGQUIT` for the pair's foreground group and, unless `NOFLSH`, drop the
line being edited, the unread input and the master's unread output; nothing is echoed for them. A session leader
with no terminal that opens the slave without `O_NOCTTY` (the desk's `pty_spawn` does, after `setsid`), or asks
`TIOCSCTTY`, makes the pair its controlling terminal; `TIOCGPGRP` and `TIOCSPGRP` read and set the foreground group.
Whose the slave is (the plan's P1 of 2026-11-11, `src/ptyown.ci`): a pair keeps the uid that opened `/dev/ptmx` and,
from the first open of its slave by a process that is not the desk, that process's session as its owner. Before
that open only the desk or a holder of the pair's master (the maker, or its child before `execve`: the desk opens
the master `O_CLOEXEC`) may open the slave; after it, an open of `/dev/pts/N` and `TCSETS`, `TCSETSW`,
`TCSETSF`, `TIOCSWINSZ`, `TIOCSCTTY` and `TIOCSPGRP` on the slave are the desk's, the controlling session's and the
owner session's (its background jobs included), and any other caller gets `EACCES`, the same account's process in
another window too. Linux checks only the slave's mode, 0620 with the maker as its owner, so there the same account
may open any of its own terminals: a divergence kept so no window can read what is typed in another or write to
its screen. No request puts bytes in a slave's input (`TIOCSTI` is `ENOTTY`). A process that is not the desk opens
`/dev/ptmx` only while fewer than 6 of the pairs in use are its uid's (`ENOSPC` past that), so the desk always has two
for a Console, whatever a program of an account that logged out left running (a log out sends `SIGTERM`, which a
program may ignore).
No signal stops a process and none is sent on hangup. A read of the master returns at most one
write of the slave (its echo counts as one): output is kept as records, so what the reader of the master does never
depends on how the slave's writes were batched. `FBIO_TILE_SYNC` returns 3 when the master has bytes to read, and an
end (2) once a return. A doom started with a surface under 640 x 400 draws its frame 1x.

`check-tiler.sh` boots the desk on gcc and clang, types `ls`, `./doom --sealed` and `exit` through the QEMU monitor,
and `tools/check-tiler.py --desk` checks the terminal's rows (the doom tic lines are `tests/expected/doom.tics`'s), the
doom tile against the Linux build's last frame drawn 1x, and the screen; the transcript is `tests/expected/desk.serial`.

## 20. The editor (E-4)

ced, the cint editor, is Daphnis's one bundled editor (`docs/specs/2026-11-06-e-editor.md`). `user/ced/` holds its
sources as `pennyleans/ced-dev` has them at the commit of `user/ced/CED_PIN`: the modules, their tests and lint, the
licenses (Apache-2.0 or MIT) and `VERSION`, each file the bytes `user/ced/SOURCES.sha256` names, nothing changed.
Taking a newer ced is a pin bump: copy the files, rewrite both lists, rebuild.

`tools/build-ced.sh` emits `ced.ci` and its modules with the pinned `cint emit-c`, wraps the emitted main as `cint build
--app --frame-arena 67108864` does (every word after `ced` is its argument; an 8 MiB file), and builds it with musl-gcc,
static, against the toolchain's runtime, which carries cint's console and fs services. The committed `user/bin/ced`
is the bytes of `tests/expected/ced.sha256` (DU-2). ced reads its file through the grant `/arg1`, the directory of its
argument, and writes it back through a temporary file and a rename. With no argument (the plane's Edit row, "An
untitled file") ced opens Untitled and its first Save asks for a name (ced RUN-8); the wrapped main then gives ced's
own manifest lines as `--grant`s with `/arg1` on the working directory, the home, since cint derives `/arg1` only
from an argument.

`check-editor.sh` checks the sources against the list, runs ced's own checks (`user/ced/tests/run.py`: its lint, its
unit tests and its key replays) on the pinned cint, and has the committed build and the host's gcc and clang builds
each take `tools/check-editor.py`'s keys on a pty of 80 x 24: two lines, Ctrl+W twice, a selection typed over, Ctrl+S
and Ctrl+Q. Each saves `first line`, `second LINE` and a final NL, and all three write the same bytes to the terminal.

The desk, hybrid desk, play, cish and desk-with-network images carry `ced` (E-5; `bin/ced` in cish's). ced takes about
57 MiB, so it starts where the pool comes from the memory map (`tools/run-qemu.sh POOL=max`, `tools/play.sh`); in the
gates' fixed 64 MiB pool it is refused at its start. `check-editor.sh` boots the desk at 512 MiB on gcc and clang,
types `$EDITOR notes.txt`, the same keys and `cat notes.txt`, and checks that the file is Linux's and the transcript is
`tests/expected/editor.serial`. Both desks start their shell with `EDITOR=/ced` and `VISUAL=/ced` (E-6). A file
made in Daphnis grows to the process quota (FS-3), so ced saves up to its own cap of 8 MiB.

## 21. The home (FS-3)

Review B-1, rulings RV-1 A and FS-R1. The volume, when the device holds one, is mounted at `/home` in every flavor:
the volume is the home, as Linux puts a person's files there. A desk (`hdesk` in the hybrid and play flavors, the
tiler in the desk-with-network one) starts through `proc.run_desk`: `fs.home` sets its working directory to the
volume's root and, when this kernel writes the volume, gives it the disk grant (bit 0 of the grant word, GR-1), and
the boot says `daphnis: the desk starts in /home, the disk grant held`. Its shells inherit both by `fork`, so the
first terminal is in `/home`, writes there without `grant disk`, and carries the sienna `DISK` pill from boot
(FOUNDING section 5). hdesk starts each shell with `HOME=/home`, or `HOME=/` without a volume. What a program writes
outside `/home` lives in the ramfs and is gone at the next boot; the home is the one plane that persists. The play flavor's `/doom.sh` runs Doom
from the root with its settings and record in the home.

`check-disk.sh` boots the hybrid desk twice on one fresh copy of the test volume, on gcc and clang, at 512 MiB with
the pool from the memory map: the first boot writes `seq 1 170000` (1,078,895 bytes) to `big.txt` in the home, copies
it into the ramfs, opens it in ced, types a line at its top and saves; the second boot of the same volume reads it
back. `tools/check-home.py` checks the start in `/home`, both sha256sums, the volume's dump and `e2fsck -fn`.
