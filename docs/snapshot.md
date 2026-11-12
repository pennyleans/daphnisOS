# K5: tasks that can be saved, the journal, the state tree and the snapshot (DAPH0001)

K5 makes two promises true for cint tasks, and this file says how, byte by byte, and where the
promises stop. Nothing is claimed that `check.sh` does not test (section 11 lists the tests).

1. **Unsaved work is never lost.** Kill the machine anywhere, restore from the last snapshot that is
   whole plus the journal after it, finish, and the final root equals the root of the run that was
   never killed (so does every commit root after the restore point).
2. **The forensics clean room.** A recording (the journal) made on one compiler replays on another,
   at another optimization level and under another fuel quantum, to the same final root and the
   same journal. Two runs can be compared root by root, and the first commit and task where they
   part is named.

## 1. The commit point: a task is a step function

K4.5 tasks were `main` run once on a stack of their own that could block inside a host call. A stack
and a register file depend on the compiler, so such a task cannot be saved. K5 tasks are **step
functions**, the recommended shape of the brief, and the reason is stated here: the only state that
is the same bytes on gcc and clang at every `-O` level is cint values, so a task must have nothing
else between the moments the kernel looks at it.

* The kernel runs one **step** of a task: the program's `main` (the same cint program for the
  kernel and the tasks, the role is the first argument digit) is called once on a fresh stack, in
  the task's own address space, as one entry of the task's own context (`rt_task_step`,
  `rt/task.c`). The stack is gone when the step returns.
* A step ends by calling the extern `request(kind, a, b, v)` exactly once (a step that does not is
  the fault `host.error.step`, a second call is refused). The request is what the task wants the
  kernel to do next; the kernel (cint, `src/kern.ci`) serves it between steps and puts the answer in
  the task's `args` for its next step. Channel operations, blocking, `select`, input and page grants
  are therefore cint code in the kernel, with ordinary module variables, and rt has no channel code
  in this flavor.
* **A commit point is the end of every turn** (a turn is the steps one task takes in a row, ended when
  it blocks, ends, yields, or has used its fuel quantum). Between steps the machine is exactly:
  the module variables of each task, its owned pages, its total fuel count (summed over steps, since
  fuel is per entry), and the kernel's tables. All of that is cint values. No stack, register,
  address, frame number or padding byte is in any of it.
* The fuel quantum is therefore at step granularity: a turn ends at the first step boundary at or
  after `q` fuel units. (K4.5's `shep` flavor ends turns inside host calls, which is why it cannot
  be saved; it is unchanged.) The quantum is a property of the schedule, not of the state: it is in
  no hash.

Request kinds (`src/ts_work.ci`): 0 done, 1 yield, 2 send(channel, value), 3 receive(channel), 4
select(mask of channels), 5 input, 6 give(peer, my slot), 7 take(peer, my slot). A request that cannot
be served yet (a full channel, an empty one, no peer waiting) leaves the task waiting; the scheduler
does not run it until the request can be served.

## 2. What is a task's state

* **Module variables** of the modules whose path begins `src/ts_` (`rt/state.c`; 200 bytes in this program). rt walks the state
  descriptors that cintc emits (variable, tag, offset, extents) and writes each element little endian
  at its own width, in descriptor order. A block the task has not touched yet is encoded as its
  initial image, so the bytes do not depend on when a block was made. Scalars and integer or Bool
  arrays are supported; anything else makes the size -1.
* **Pages** it owns (section 6): its slot number and its non-zero words.
* **Total fuel**, and a flag: 0 live, 1 done, 2 faulted.
* The task's pending request and the answer it will see are the kernel's, so they are in the
  kernel tables (below), not the task's.

## 3. The state tree

* Leaf of task `t` = SHA-256 of its **preimage**: `00 | t | flags | fuel (u64) | state length (u32) |
  state bytes | number of pages (u8) | per page: slot (u8) | non-zero words (u16) | per word: index
  (u16) | the word (u64)`. All integers little endian.
* Leaf of the kernel = SHA-256 of `01 |` per task: request kind (u8, 0 none, else kind + 1), its three
  arguments and the fuel count it was made at (u64 each), the value and the tag of the answer (u64,
  u8), the journal's length (u32) and chain head (32 bytes); then per channel: open, sender,
  receiver, count (u8 each), two values (u64 each, zero past the count); then the bytes of input
  consumed (u64) and per task the mask of its page slots (u8). 326 bytes. Stale values are cleared
  when a request is served and a value is taken from a channel: a kernel leaf that held old bytes
  would differ between schedules for no reason (found by the cross-quantum replay test).
* Node = SHA-256(`02` | left | right). The root over the four leaves is
  `node(node(task 0, task 1), node(task 2, kernel))`.
* The leaves of a task are recomputed when that task ran or a page moved to or from it; the kernel
  leaf at every commit; the other leaves are cached. A snapshot recomputes all four and requires
  them to equal the cache (a cached leaf that is not the leaf of the state halts the machine).
* The **scheduler's place** (the next task, whether a task ran in this pass, the commit number) and
  the **quantum** are not in the root: they depend on the quantum. They are in the snapshot, so that a
  restore continues the same schedule, and the digest of the snapshot covers them.
* Frame numbers, page-table frames and the allocator's bitmap are in no hash and no snapshot: a restore
  allocates again and the root does not change.

Each commit prints `C <number> <task that ran> <root> <leaf 0> <leaf 1> <leaf 2> <kernel leaf>`.

## 4. The journal

A task result that the schedule could change is either forbidden (K4.5: tasks share nothing, receives
name their channel) or written to the journal. There is no third kind. Two things are journaled:

* **select** over a mask of channel ends: which end won. In record mode the first end of the mask
  that has a value wins, so what wins depends on how far the producers got, that is, on the schedule.
* **input**: a chunk of the serial script. The kernel reads up to 7 bytes, or fewer if a line end
  comes first (the line end is consumed and is not in the chunk). The chunk is a function of the byte
  stream only, not of when the bytes arrived.

An entry is `task (u8) | sequence number (u32, the task's own count) | kind (u8, 4 select, 5 input) |
payload length (u8) | payload | fuel (u64)`; the payload of a select is the winner (1 byte), of an
input the flag "line end consumed" and the bytes. The **fuel stamp** is the task's total fuel at the
moment it made the request: a point in the source, not in machine instructions, so it is the same on
every compiler and every schedule. The chain of a task is `SHA-256(previous chain | entry)` from 32 zero
bytes. The journal is **per task**: a global chain would depend on the interleaving, and the same run
under another quantum would have another journal. The canonical journal is the merge by (task, sequence).

* **Write ahead.** The kernel prints the entry (`J <entry hex> <chain hex>`) before it applies what the
  entry decides (takes the value out of the channel, hands over the input).
* **Replay.** The kernel is given entries (a blob, section 8) and, for a task that has entries left, asks the
  entry instead of the schedule or the device: it must be the task's next sequence number, of the kind it
  is serving, with the same fuel stamp, and its chain must be the chain the kernel computes; else the
  kernel prints `diverged: ...` and halts. A select with a recorded winner waits until that channel has a
  value (it will: the run that was recorded completed), so another quantum works. Input is not read from
  the device. A task whose entries are used up goes live (record mode) with its chain continuing.
* Write ahead makes a torn entry harmless: the kernel is deterministic, so a restored machine that did not
  get the entry makes the same choice again; the journal is needed for the input bytes already consumed.

## 5. The snapshot, DAPH0001

Printed after every 5th commit (5 is prime to the three tasks, so snapshots fall at every place of the round robin) and once at the end, as `S begin <commit>`, one line of hex, `S end
<commit>`. The bytes, all integers little endian, no padding:

| Part | Bytes |
| --- | --- |
| magic | `DAPH0001` |
| revision | 32 bytes: the program's revision, the same on every compiler for one source (a snapshot of another program is refused) |
| scheduler | next task (u8), ran in this pass (u8), commit number (u32), walks (u32), task leaves rehashed (u32): statistics, in the digest and in no root |
| task 0, 1, 2 | the preimage of its leaf (section 3) |
| kernel | the preimage of the kernel's leaf (326 bytes) |
| journals | per task: length in bytes (u32) and its entries, each as a length byte and the entry |
| trailer | the four leaves, the root, SHA-256 of everything above, `DAPHEND0` (200 bytes) |

A snapshot is **whole** only with its `S end` line; a snapshot cut by a kill has none and is not used. A
reader checks the digest, recomputes the four leaves from the preimages it holds, checks the root, and
checks the journals against the chain heads in the kernel preimage. `tools/k5lib.py` does exactly this
with `hashlib`, and `tools/check-k5.py` runs it over every snapshot of a run and also compares the
last one with a model of the network written from the script and the journal alone.

## 6. Address spaces, single owner, W^X

* Each task has its own page tables: PML4, PDPT, a PD for the first 4 MiB whose two entries are the boot page
  tables `pt` and `pt_high` (so the image, both its windows, the stacks, the IDT, the TSS and the guard pages are what the kernel maps), and a PD
  and PT for a private region at `0x40000000` with 8 page slots. The kernel builds them in cint in frames
  of the pool (`src/kspace.ci`) through the view shim. rt only loads the task's CR3 around a step.
* A task's space does not contain the frame pool or the rest of RAM. A page is in it only if the kernel put
  it there. A task reaches its pages with `page_load(slot, word)` and `page_store(slot, word, v)`, which
  rt performs with the hardware through the task's CR3; it never holds an address. A page that is not in
  its tables is a #PF, and the trap record is the task's fault record (the same bytes on every schedule).
* A **grant** (`give`/`take`) is a rendezvous: when giver and receiver are both waiting for each other the
  kernel clears the giver's entry first, then maps the page into the receiver. No page is ever in transit,
  so no snapshot sees one.
* **The walk** (`kspace.walk`), at every commit: no frame of the pool is mapped writable in two task spaces;
  no entry is both writable and executable; each space holds exactly the five tables it should (read in full,
  ignoring the accessed and dirty bits the CPU sets); and the pages the tables show are the pages the kernel
  says each task owns. Networks 2 and 3 corrupt a space on purpose and the walk refuses them.
* **What this does not claim.** The kernel's own space is not a task space: it maps all RAM. Tasks are ring 0
  kernel threads that cannot form a pointer, and every task space maps the whole image (the code, the
  stacks and the tables of every task are in it). The hardware check covers exactly the pages the kernel
  grants, reached through the two externs. Isolation of a task from kernel memory is ring 3, which is U1's.
* **W^X** (`rt_wx_init`, `arch/x86_64/linker.ld`): code, read-only data and data start on their own pages;
  code is present and read only, everything else is no-execute, and the 2 MiB entries of the rest of RAM
  are no-execute. The k5 kernel reads the boot tables and prints that no leaf is both writable and
  executable, and shows the hardware enforcing it: a store into the code traps with error code 3, a jump
  into a page of data with 17 (0x11).

## 7. The kernel's other tables

Channels (4, capacity 2, one sender and one receiver each), the pending request of each task, the answer a
task will see, the journals, the bytes of input consumed, which page slots each task owns. They are module
variables of `src/kern.ci`, so between turns the kernel holds no stack either.

## 8. The run blob and the modes

QEMU's loader puts a file at 96 MiB (`-device loader,file=BLOB,addr=0x6000000,force-raw=on`; 40 MiB before G-0); rt lets cint read
that 1 MiB and nothing else outside the pool and the boot tables (`rt/phys.c`). The blob is a 32-byte
descriptor (`DAPH0RUN`, then u32: version 1, mode, quantum, network, snapshot length) followed by an optional
snapshot and then the journal entries to replay: per task a u32 count, then each entry as a length byte, the
entry and its 32-byte chain. Modes: 1 record (live), 2 replay (journal, no snapshot: the machine starts
again and the journal brings it where it was), 3 restore (snapshot, then the journal after it). After the
journal is used up the machine goes live. The serial input is the script; a replay never reads it.

## 9. Kill and restore

`tools/killrun.py`. A reference run is made and its transcript kept. For each of 20 kill points chosen by a
seeded generator from the length of that transcript (four kinds in turn: anywhere, inside a journal line,
inside a commit line, inside a snapshot) the machine is started and killed with SIGKILL once it has written
that many bytes to the serial port; the transcript is cut at exactly that byte, so the cut lands mid-line
and the class of the cut depends on the seed and not on how fast the machine ran. The restore blob is made
from the cut transcript alone (the last snapshot that is whole and verifies, and the journal entries after it
that are whole and chain), the rest of the script (after the input bytes the journal consumed) goes on the
serial port, and the machine runs to its end. Then:

* the final root is the reference's,
* the commit lines (every root and every leaf) of the cut run up to the snapshot, followed by those of the
  restored run, are exactly the reference's commit lines,
* the journal of the cut run merged with the restored run's is exactly the reference's,
* every snapshot the restored run prints is byte for byte the reference's of the same commit.

A kill before the first snapshot restores from the journal alone (mode 2). `killrun.py ... all` makes one cut just after
each snapshot of a run instead, so the machine is restored from every snapshot it wrote (the gate does it for the runs
under q=250 and q=1: about 100 restores). The promise stops where the
design brief said it would: work is safe up to the last journal entry that reached the serial port; input
that the machine had read from the device and not journaled is typed again (the script supplies it), and
a device that fails is outside the promise.

## 10. Replay across builds (the forensics claim)

A run is recorded (the final root, the journal) under one quantum; `tools/k5blob.py replay` builds a blob from
its journal, verified; the same program built by the other compiler, or by gcc and clang at `-O0`, replays it
under another quantum. Equal: the final root, the journal (all `J` lines as a set), the final leaves. The
reverse direction (record on clang, replay on gcc) is tested too, and a journal whose fuel stamp is wrong by
one is refused.

## 11. The networks and what `check.sh` tests

The kernel runs one network per boot, named by the descriptor (and an audit flag: with it the kernel makes every cached leaf again at every commit and halts on a stale one). Network 0 is the workload: task 0 sends 24
SHA-256 round values on channel 0; task 1, the editor, takes 12 chunks of input into a page of its own, sends
a running checksum of the page on channel 1 after each, and gives the page to task 2; task 2 selects between
the two channels 36 times, folds the values in the order the select returns them (the fold depends on the order),
takes the page and folds its words. It is the select version of K4.5's racy control (net 1 there): the roots
under different quanta differ, and the journal makes each of them replay. Networks 1 to 8 are tests: 1 a write into a page of another task's space (and the check that no task can read the record of another's fault), 2, 3, 5 and 6 four corrupt spaces
the walk must refuse (a frame in two spaces; writable and executable; an entry in an upper table; a page the
kernel does not know of), 4 a grant after which the giver's write faults, 7 a task that touches module state
outside the `src/ts_` modules (the kernel refuses the commit: that state would not be in any snapshot), 8 the most
negative value but one sent through a channel, an inbox and a snapshot. `docs/RESULTS-K5.md` has every gate line and the mutation table.

## 12. Limits and what the kernel does when something is wrong

* A request the kernel cannot honor (a send on a channel the task is not the sender of, a grant with a bad
  slot) ends the task with a printed line (`refused: ...`), not a fault record: the kernel is cint and cannot
  make an rt record. The page faults are fault records (trap records of the running context).
* Replay or restore that does not fit (`diverged: ...`, `restore: ...`) halts the machine with the reason
  printed and no final root, and a halted machine commits and snapshots nothing more (a snapshot whose cached
  leaves are not the leaves of the state is left without its closing line). A restore checks, besides the digest
  and the leaves, the sizes it reads (journal length, channel counts, flags) and that each journal ends in the
  chain head the tables say.

* Three tasks, four channels, eight page slots per task, a journal of 1 KiB per task, a module state of at most
  4 KiB per task. Fixed, and the kernel halts rather than overflow.
* Task state is scalars and integer arrays; the walker refuses anything else.
* The quantum is at step granularity; a step that computes for long is not interrupted (cint #512, gap 13).
* Input is one serial port, one reader.
* Nothing ran on KVM or on real hardware; the instrument is QEMU TCG.
* The tool chain's own determinism is assumed: the same cint source gives the same emitted C.
