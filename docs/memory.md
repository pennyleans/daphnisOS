# K3: memory

Flavor `mem` (`src/main_mem.ci`), booted with `-m 128M`. Everything below is cint except the
few externs of `rt/` named in each section.

## The view shim

cint has no pointers, and an extern can take scalars and rank-1 `in` or `out` views and return
a scalar, never a view (CINTC-OQ-66). So the shim is a copy window, in `src/phys.ci` and
`rt/phys.c`:

    extern unrestricted void phys_read64(U64 base, out U64[_] dst);   // and phys_write64, phys_read8, phys_write8

A call copies `extent` elements between the physical range `[base, base + extent * width)` and
the view. `rt/phys.c` allows exactly these ranges to the `phys_*` externs and refuses everything else with the status
`CINT_REFUSED`, which `cint_rt_host_call` writes as the record the hosted runtime writes for a
host function that does not return OK (RT-OQ-70): code 10, operation
`host.error.<extern name>`, one `I64` operand, the status:

| Range | Access | What it is |
| --- | --- | --- |
| `[0x1000, 1 MiB)` | read | the Multiboot info structure and memory map (boot.S saves the pointer) |
| `[32 MiB, 96 MiB)`, or to the pool's end once `src/pool.ci` set it (M-3, up to 8 GiB) | read, write | the frame pool of `src/frames.ci` (16 MiB to 32 MiB before G-0) |
| the six boot page-table pages | read | `pml4`, `pdpt`, `pd`, `pt`, `pt_high`, `pt_high2` of `boot.S`, contiguous |
| the boot PDPT page | read, write | all `paging.ci` writes there is slot 1; the other three boot pages cannot be written, so cint cannot unmap the kernel's own mappings |

Arithmetic on the range is overflow-checked, the width must equal the view's stride, and the
base must be aligned to the width. The null page is outside every window. The six refusals (`phys_read8` at 0, `phys_write64` at 2 MiB, `phys_write64` to the boot PML4, a
misaligned `phys_read64`, a `phys_read64` whose range wraps the address space, and `vm_store64`
into the identity map) are runs 0 to 5 of the `mem` flavor.

The probes that make an access through the page tables take an integer address, so they are
held to the same discipline: `vm_load64`, `vm_store64`, `vm_exec` and `trap_probe_pf` accept only
the null page and the region `paging.ci` manages (`0x40000000` to `0x7FFFFFFF`); an address in the
identity-mapped kernel is `CINT_REFUSED` like a bad window (run 5).

The shim is a copy, not a shared view: the data a view holds is valid for the call only
(SPEC-03 A-15), and a page-table edit is a read of 512 words, a change, and a write. It is
the smallest construct that fits the spec as pinned. A real view over a physical range, or
registered buffers (SPEC-03 6a), would avoid the copies; the pinned toolchain has no way to
make cintc emit one for the kernel.

## The memory map

`boot.S` asks for the map (Multiboot header flag bit 1) and saves the pointer; `src/memmap.ci`
parses it from bytes (pure, tested hosted on a fixed array); `src/main_mem.ci` reads it through
`phys_read8`. QEMU 11.1.2 passes a map with RAM from 1 MiB to just under 128 MiB and reserved
entries above, including a region near 1 TiB (the PCI hole). The summary prints only what
`-m 128M` fixes:

    mmap: valid
    ram: MiB 128
    pool 32 MiB to 96 MiB usable: yes

`ram` is the end of the highest *usable* (type 1) entry rounded up to a whole MiB, so QEMU's
exact reservation at the top of RAM does not show. Reserved entries are left out (the first
version counted them and printed 1,048,576). The entry count, the low-memory edges and the
address of the structures are never printed.

## Multiboot 2 information: one buffer, one extern

Ruling BN-1 (A) of `docs/specs/2026-11-04-boot-next.md`. The loader's information block sits where the
loader chose:

| loader | protocol | block at | size |
| --- | --- | --- | --- |
| QEMU `-kernel` | Multiboot 1 | `0x9500`, inside the `[0x1000, 1 MiB)` read window | 591 bytes (the fixed structure and what it points at) |
| GRUB 2.12 `multiboot2` | Multiboot 2 | `0x100068`, in the image's own header page, outside the window | `total_size` |

Rather than a read window per loader, `rt/` copies the block once and cint reads the copy:

1. `arch/x86_64/boot.S` saves the magic (`mb_magic`) and `ebx` (`mb_info`) under either protocol.
2. `rt/boot.c`, `rt_boot_init`, the first call of `rt_start` (before `rt_wx_init` and `main`): Multiboot 1
   copies 128 bytes of the fixed structure from `mb_info` through `rt_phys_copy`, the window rules above;
   Multiboot 2 reads `total_size` at `mb_info` and copies that many bytes, or refuses a block larger than
   `RT_BOOT_INFO_BYTES` (8,192) and records status -2. The source must lie in `[0x1000, 1 GiB)` (the null
   page is not mapped; `boot.S` identity maps the first 1 GiB) and, under Multiboot 2, be 8-byte aligned.
   The copy is in `.bss`.
3. `rt/host.c`, one row: `boot_info(out U8[n] dst) -> I64` (`src/bootinfo.ci`, its own module so that
   the other flavors keep their program revision and their goldens) fills `dst` with as much of the
   copy as fits and returns the protocol, 1 or 2, or a negative status with `dst` untouched: -1 no loader
   block (another magic, a source outside the range, a `total_size` under 8), -2 the block was larger
   than the buffer.
4. `src/main_mem.ci`, `memory_map()`: protocol 1 reads the structure and the map where the loader put
   them, through `phys_read8`, as before (the K3 goldens read it); protocol 2 walks the tags of the copy;
   a negative status prints `mmap: no loader block, status N`. Both protocols print the same three lines.
   The view is 3,072 bytes: the frame arena holds 4,096 elements and `memory_map_mb1` needs 576 below
   it. A Multiboot 2 block larger than the view prints `mmap: length out of range`.

The Multiboot 2 walker (`src/memmap.ci`, `mb2_*`, pure, tested hosted): the block is `total_size U32`,
a reserved `U32`, then tags. A tag is `type U32`, `size U32` (without its padding) and a body; the next
tag starts at the next multiple of 8; type 0 ends the list. Type 6 is the memory map: `entry_size U32`
at 8, `entry_version U32` at 12, then entries `entry_size` apart of `base U64, length U64, type U32,
reserved U32`. `mb2_ram_mib` and `mb2_usable_covers` give the answers `ram_mib` and `usable_covers` give
for the Multiboot 1 map of the same machine. The walk refuses a tag shorter than its head or one that
runs past `total_size`, and a map whose entries are shorter than 24 bytes.

## The frame allocator

`src/frames.ci`: a bitmap over 16,384 frames of 4 KiB at 32 MiB (a 64 MiB pool, G-0; 4,096 frames at 16 MiB
before), 256 `U64` words,
first fit over contiguous runs. Why a bitmap: the state is 64 words, a scan is bounded, a
refusal needs no repair, and the digest is the words themselves. A free list would be faster
and would put the state in the memory it manages. The pool is fixed, not "everything above the
image", because the images of gcc and clang end at different addresses and a printed free
count must not depend on that. The linker script asserts the image ends by 6 MiB, so the pool
never overlaps it.

The state is module state (SPEC-03 A-7: it survives a fault), so no function takes a state
parameter. This needed `cint_rt_state_slow` in `rt/ctx.c`.

* `alloc(n)` returns the first frame's index or a negative status; `release(first, n)` the free
  count or a status; `frame_addr(f)` the physical address. The statuses are `ERR_EXHAUSTED -1`,
  `ERR_BAD_COUNT -2`, `ERR_NOT_OWNED -3`, `ERR_BAD_FRAME -4`. (An error union returned across
  modules is refused by this cintc, `docs/cint-gaps.md` 7.)
* **Two phases**: a search that only reads, then the stores. Every refusal returns before the
  first store.
* Every index and address computation is checked cint arithmetic: `POOL_BASE + f * 4096`
  faults rather than wraps.
* `digest()`: SHA-256 of the 64 bitmap words, the free count and the operation count, each as 8
  little-endian bytes. The operation count is in the hash on purpose: a refusal that counted
  itself would change it.

## The heap

`src/heap.ci`: arenas. An arena is a run of contiguous frames and a bump offset;
`arena_alloc(slot, bytes, align)` returns a physical address inside the run and the caller
reaches it through the shim. Reset forgets the objects, free returns the frames. Four arenas.
Why arenas and not pools: out-of-memory is then one comparison against a known extent, and a
refusal is a return before any store. A request that does not fit (`bytes > extent - start`)
is `ERR_EXHAUSTED -14`; a refused one leaves the heap digest unchanged. `src/memstate.ci`
hashes both digests together: that is "the allocator-state hash" below.

## Refusals leave state unchanged

`src/allocdemo.ci` runs a fixed sequence (allocate 8, 4, 1 frames; free the middle one;
allocate 5 and 4; then five refused frame requests (the fifth asks for one frame more than are free); an arena, two objects, one refused
object; free everything) and takes six snapshots of the allocator-state hash. The hash before
the five refused frame requests equals the hash after; the hash before the refused 9,000-byte
object equals the hash after. `tools/check-mem.py` compares the printed hashes itself; it does
not trust the `yes` the kernel prints. `tests/mem_twin.ci` runs the same function on the hosted
runtime and `check.sh` requires its six hashes to equal the kernel's, so the checked arithmetic
of both runtimes agrees. The twin also fails when one hex digit differs (checked in the gate).
A canonical fault is the other allowed outcome for out-of-memory: the shim's refusals above
are faults; the allocators refuse cleanly.

## Page tables

`src/pte.ci` (pure, tested hosted) builds entries: present bit 0, writable bit 1, no-execute
bit 63, address bits 12 to 51. `src/paging.ci` edits tables through the shim.

The boot tables identity-map the first GiB. K3 does not rebuild them and does not switch CR3:
it adds mappings in an unused range, virtual `0x40000000` to `0x7FFFFFFF` under slot 1 of the
boot PDPT. `init` links a page directory frame there; `map` allocates a page table frame when a
2 MiB slot has none; the leaves are 4 KiB. Operations: `map(va, pa, flags)`, `unmap(va)`,
`protect(va, flags)`, `translate(va)`, each checking before it stores and each ending, when it
changed an entry, with `invlpg` (`vm_invlpg`, `arch/x86_64/probe.S`). Statuses
`ERR_NOT_READY -21`, `ERR_BAD_ADDRESS -22`, `ERR_NO_MEMORY -23`, `ERR_MAPPED -24`,
`ERR_NOT_MAPPED -25`, `ERR_EXISTS -26`. Image pages are not split or protected by paging.ci (that would
print image-dependent results); since K5 `rt_wx_init` gives the first 2 MiB the rights of their sections, and the high window at 2 to 6 MiB those of its two (below).

Hardware enforcement: `boot.S` sets CR0.WP (a write to a read-only page faults in ring 0 too)
and EFER.NXE (bit 63 means no-execute). Accesses go through the paging hardware with three
probes (`src/trap.ci`, `probe.S`): `vm_load64`, `vm_store64`, `vm_exec` (a call to the
address). A fault in a probe is recorded as in `docs/traps.md` and the probe returns.

The `mem` flavor shows, in this order: map a page, write a pattern through the mapping and read
it through the physical window and back through the mapping; make it read-only (the store is
a #PF record, error code 3, CR2 the address; the word is unchanged); map an executable page
holding a `ret` and call it (no record), make it no-execute (the call is a #PF record, error
code `0x11`); load through the mapping (puts the page in the TLB), unmap, load again (#PF,
error 0); remap to another frame with the pattern copied and read it back; three refused
page-table requests (map over a mapped page -24, map outside the region -22, unmap of an
unmapped page -25).

## What the gate checks (K3 memory)

`check.sh` 5d and `tools/check-mem.py` (74 checks): the six runs of bad addresses as `host.error`
faults with the right operation, operand, position and call stack; the three #PF records
decoded against a table (vector 14; error 3, `0x11`, 0; CR2; IST 3; position; stack main >
demo > paging_demo); every refusal status; the hash pairs equal; the hash of the empty,
allocated, arena and final states all different; the free count back at 16,384 and two frames
(the page directory and one table) still held; the whole transcript equal to the golden;
the hosted twin's hashes equal. With GRUB tools on the machine (the ISO leg of `check.sh`), `mem` also
boots from `daphnis.iso` under Multiboot 2 at `-m 128` and its transcript equals the same skeleton on
gcc and clang (record hex masked). Not covered: more than one page table, a second arena
holding live data across a fault, a frame pool above 16 MiB, a map that the loader splits
differently from QEMU 11.1.2.

## Guard entries in the boot page table (K4.5)

The boot `pt` page is readable by cint and writable by nobody in cint (the window above). `rt/` clears
its entries for the guard pages of the task and IST stacks once, at start (`rt_guard_pages`), so the
page table cint reads shows those pages not present; `src/guards.ci` checks exactly that.

## K5: W^X, task address spaces, the run blob

* **W^X.** `arch/x86_64/linker.ld` starts code, read-only data and data on their own pages (`__text_end`,
  `__rodata_end`); `rt_wx_init` (`rt/phys.c`, called by `rt_start` before `main`) rewrites the entries of
  boot.S's `pt`: code present and read only (CR0.WP binds ring 0), read-only data and everything below the
  code no-execute, data, bss, tables and stacks writable and no-execute; a page that is not present (the null
  page, a guard) stays so; `pt_high` and `pt_high2`, the image's high window (2 to 6 MiB), are read and execute up to `__high_text_end`
  (the emitted code), read only and no-execute up to `__high_rodata_end`, writable and no-execute after it
  (the emitted data and bss, the state pool); the 2 MiB entries above `pd[2]` become no-execute, so the part of
  the state pool that runs past 6 MiB (`.high_pool`, `arch/x86_64/linker.ld`) is writable and no-execute too. The GDT is in `.data`, so `ltr` and the
  CPU's accessed bits still write it. Evidence, in the k5 transcript: `boot tables: no entry is both writable
  and executable` (cint reads `pd`, `pt`, `pt_high` and `pt_high2` through the window and counts), and the hardware refusing:
  a store into the code traps with error code 3, a jump into a page of data (`wx_page`, a `ret` in `.data`)
  with 17 (0x11). The 2 MiB pages of the identity map above the image hold data only; nothing executes there.
* **Task address spaces** (`src/kspace.ci`, `docs/snapshot.md` section 6): five tables per task in frames of the
  pool, the boot `pt` and `pt_high` shared for the image, a private region at `0x40000000` of 8 page slots, `walk()` at every
  commit. The pool is read and written by cint through the window as before; the tables of a task space are
  in the pool, so they were already writable by the kernel and by nobody else.
* **The run blob window**: `[96 MiB, 97 MiB)`, read only (`rt/phys.c`), where QEMU's loader puts the run descriptor,
  a snapshot and journal entries; the pool ends at 96 MiB, so they cannot overlap (40 MiB before G-0).
* **The layout, G-0** (`rt/rt.h` `RT_POOL_BASE`, `RT_POOL_END`, `RT_BLOB_BASE`; `frames.POOL_BASE`, `kern.BLOB`): the
  image to `__image_end`, the loader's module window above it to 32 MiB (`rt/boot.c` takes the first module only
  there), the pool `[32 MiB, 96 MiB)`, the run blob at 96 MiB. Every leg boots with `-m 128`. The pool moved up so
  the module window can carry the episode's WAD (stage G, G-3): below a pool at 16 MiB it held 13.6 MiB.
  AU-5: under `daphnis.pool=max` the module may run on to 96 MiB, and `src/pool.ci` starts the pool at the page
  after it (`pool_floor`, `rt_boot_pool_floor`): the play image with the native core set, the episode and the
  sound lumps is 38 MB, past the 28 MiB the window holds. Without the word the window is as above.
  g24 (unit 4b): a module the loader put outside the window and that fits in it is moved into it before anything
  else runs, to the lowest run of usable RAM from `__image_end` (`module_room`). GRUB under UEFI needs this: OVMF
  holds 8 to 9 MiB, so the 12 MB user image landed at 23.5 to 35.3 MiB, across the pool's base, and was not taken.
* Not done: an overflow of an IST stack, and ring 3 (every task space still maps the whole image).
