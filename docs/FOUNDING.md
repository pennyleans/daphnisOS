# Daphnis

Founding document, revision 0.7 draft (baseline: `main` of 2026-11-06; revision 0.7, 2026-11-06: section 5's
containment bullet and law 4 for stacked floating windows, rulings HX-1 B and HX-9 A, `docs/specs/2026-11-05-h-hybrid.md`).
Revision 0.5 is l's Google Doc of 2026-11-05 (baseline of 2026-11-05). This copy is the repository's; section 8 lists
every edit made to 0.5 and why, so l can accept or reverse each one. The Google Doc stays the draft surface;
this file is what the tree is built against.

A verifiable Unix workstation for people leaving macOS.

## 1. Why Daphnis exists

Engineers, designers, writers and researchers stayed on macOS for a simple reason: a Unix userland beneath a
coherent, quiet graphical environment. Over the past decade Apple turned that workstation into a metered client.
Launching a local binary triggers remote notarization checks. Background daemons open network connections
outside user control, OS updates entangle local storage with cloud identity, and system services inspect screen
and file state by default.

Users leaving macOS face a bad trade:

- Desktop Linux restores local ownership at the cost of structural coherence: thirty million lines of unchecked
  kernel C, stacked X11, Wayland, GTK, Qt and Electron layers, inconsistent typography, and configuration
  scattered across dozens of text files.
- High-assurance systems (Qubes, OpenBSD, seL4 builds) take isolation seriously but treat daily work like a
  containment drill, imposing hypervisor memory overhead, slow graphics paths, or spartan interfaces that wear
  down eight-hour engineering and design sessions.

Daphnis is a general-purpose, security-focused personal operating system written in cint (integer C), pairing a
Linux-compatible ring 3 ABI with a direct-to-framebuffer graphical desk. It gives macOS departures full local
ownership, familiar Unix tools at boot, a receipt for every verified run, and a visual environment governed by
Josef Albers' economy of form and Paul Klee's structural laws.

## 2. Design law: Albers and Klee as system architecture

Daphnis does not treat visual design as a skin painted over kernel internals. Four formal laws from Josef Albers
and Paul Klee govern the kernel, the execution model and the display surface alike.

**Economy of form (Albers).** Albers measured design by the ratio of effort to effect: maximum structural
clarity from minimum material, where a single boundary edge defines two adjacent forms at once. Conventional
desktops stack kernel drivers, display servers, compositors, widget toolkits and browser engines just to put text
inside a rectangle. Daphnis reduces the workstation to a small checked-integer kernel, isolated ring 3 processes
and a linear framebuffer. Nothing runs solely to translate state between middlemen.

**Factual spec against actual execution (Albers).** In Interaction of Color, Albers separated factual fact (what
an element claims to be in isolation) from actual fact (how it behaves under active interaction with its
neighbors). Mainstream OS security markets factual claims (code signatures, sandboxes, permission checkboxes)
that fail in actual execution under C undefined behavior, silent integer wrap or resource contention. Daphnis
pins actual execution: SHA-256 digests over process state, transcripts and hardware surfaces, verified byte for
byte across gcc and clang.

**Dividual substrate, individual organism (Klee).** In his Pedagogical Sketchbook and The Thinking Eye, Klee
distinguished dividual structure (a uniform, repeatable integer rhythm that can be subdivided without changing
its rule) from individual form (a bounded organism whose integrity breaks if a single part is altered). Daphnis
builds a strict dividual substrate (checked integer arithmetic, no floating-point path in system code, 4 KiB page
boundaries, deterministic scheduling ticks and integer screen subdivisions) so every individual ring 3 process
executes intact. Flip one canary bit and the receipt desyncs at the first tic after it, in the open, instead of
the run continuing as if nothing happened.

**Polyphonic isolation (Klee).** Klee defined pictorial polyphony as independent voices occupying one plane
simultaneously while keeping each contour distinct. Multitasking on macOS and Linux routinely turns into
acoustic mud: background indexers, fork storms and sibling tasks bleed latency and side effects into foreground
work. Daphnis enforces polyphonic isolation in ring 3: concurrent workloads share the machine while verified
foreground execution stays bit-invariant.

| what worked on early macOS | what broke | Daphnis mechanism |
| --- | --- | --- |
| real Unix shell and a unified desktop | notarization call-homes, cloud lock-in, opaque daemons | ring 3 Linux ABI, a kernel with no network by default |
| direct input-to-glass response | multi-layer compositor lag and background indexing | checked-integer cint kernel, direct linear framebuffer |
| coherent visual defaults | permission pop-up fatigue and Linux toolkit sprawl | integer cell tiling, Albers and Klee relational state |
| everyday system safety | unverifiable vendor assurances | pinned SHA-256 process and surface digests |

## 3. Baseline today (`main` of 2026-11-06)

The kernel, the ring 3 ABI, the stage F hardware surfaces and the desync harness run and are gated:

- Checked-integer kernel: a compact x86-64 Unix-like kernel written in cint. Boots from ISO via GRUB and under
  QEMU's `-kernel`, and passes 369 gate lines on the Arch runner and on the cloud leg (`check.sh`).
- Ring 3 Linux ABI parity: unprivileged programs run in ring 3. Unmodified static busybox boots to a shell, and
  a scripted session (pipes, redirection, loops, forks) matches Linux byte for byte across gcc and clang builds.
- Stage F pinned surfaces: a linear framebuffer, a PS/2 keyboard and a PS/2 mouse, each pinned by a surface or
  transcript digest.
- R-1 cross-OS process parity: native cint programs built as static musl binaries give identical output and
  process digests on Linux and on Daphnis, across memory fault lines, a 4 MiB SHA-256 pass and framebuffer
  drawing.
- R-2a to R-2c workload parity: a cint port of linuxdoom-1.10 loads Freedoom E1M6, simulates its 350-tic demo
  and renders every frame. Every level count, every tic's player words and random index, and every frame's
  digest equal a host reference tool's, on Linux and under Daphnis, gcc and clang alike; the chain
  `H_t = SHA-256(H_(t-1) | t | S_t | F_t)` runs over 686,956 state bytes and a 64,001-byte frame a tic.
- Canary guards: the 1-bit canary desyncs the chain at tic 1 and at every tic after.

Known limits at that baseline:

1. No persistent filesystem: storage runs in memory from the boot image, in one flat root directory.
2. No networking: builds run air-gapped with no network stack.
3. Gate headroom: the Arch gate ran 294 to 338 s of its 360 s budget under CI runner load; it needs widening
   before major subsystem growth (the R-2d gate gets a script and budget of its own).
4. Not yet run on hardware: every gate runs under QEMU TCG; the display is QEMU's standard VGA and the input is
   PS/2.

## 4. Public proof: Break the Receipt

Daphnis tests its isolation claim in public through an open adversarial challenge, Break the Receipt.

The bundle is a small Daphnis ISO with Freedoom, and the pin is one SHA-256 of machine state recorded after a
sealed timedemo. Anyone who produces a different valid state hash without editing the source, the WAD or the
demo wins.

- Track 1, compiler and CPU invariance (attacking `cintc`): build the bundle with any conforming C17 compiler,
  flag combination or supported CPU and produce a divergent state hash.
- Track 2, ring 3 polyphony under load (attacking the kernel): from the shell, launch any unprivileged load
  (memory pressure, filesystem churn, timer floods, process forks), run Doom, and make its final state hash
  differ by one bit.

Practical meaning for daily users: if hostile shell workloads and compiler flag changes cannot shift a real-time
simulation by one bit, background tasks cannot silently alter a writer's draft or the foreground state behind
the user's back. The receipt is evidence of integrity, not of confidentiality: it shows that the foreground run
was not changed, not that nothing could read it. Nothing here is public until l's go and the voice review.

## 5. Visual grammar and the framebuffer desk

Every element on screen derives from the open-cut Daphnis mark and renders straight to the linear framebuffer
without widget toolkits or compositing blur.

Equilibrium and counter-change in the mark:

- Asymmetric balance (the color lockup): constructed like Klee's balance studies across a central vertical
  split. On the left, open warm ground holds an ink-black lintel bar, a suspended yellow ochre disc, an
  ultramarine half-ring around a black core, and an intersecting ochre wedge at the lower chord. On the right, a
  solid cadmium-red vertical slab is cut open by a warm-ground semicircle. Together they read as a lowercase d
  and as the moon Daphnis clearing its gap in Saturn's rings, anchored by a black baseline rule and the tracked
  geometric wordmark daphnis.
- 1-bit counter-change lockup: applies Albers' figure-ground economy across the vertical axis. Every edge
  defines black and white forms simultaneously without grayscale antialiasing or drop shadows, keeping the mark
  legible at 16 px bar height, on the 640 x 480 boot surface, and in monochrome receipt headers.
- Inner-core split: the color cut leaves the right inner half-circle open to the warm paper ground so the red
  stem stays calm; the 1-bit cut inverts the inner core across the central axis to preserve concentric ring
  structure without hue contrast.

The lockup is in `pennyleans/studio-assets` at `promo/logo/ui_daphnis_logo_opencut_mono.svg` and `_bauhaus.svg`
(the PNG masters beside them in LFS, 1024 x 1024; merged 2026-11-05). The mono mark is six primitives in a
400 x 400 box (two rings, a slab, a wedge, a bar, a dot, an even-odd fill) plus a ground rule and the wordmark,
so stage W draws the symbol from that geometry in checked integers at any size and never from a bitmap.

Interaction of color in the framebuffer. Following Albers, color perception depends on ground, proportion and
temperature interval. Most of the Daphnis workspace stays neutral warm paper and carbon ink. To keep authority
legible over eight-hour sessions, Daphnis pairs Klee's and Albers' two iron-earth pigments to separate local disk
mutation from off-machine network reach: yellow ochre marks writable local storage (ring 1), burnt sienna marks
live network apertures (ring 2), cool receding ultramarine marks active input focus (ring 3), and high-chroma
cadmium red marks a hard invariant fault or a process in the ring 0 mode (WB-R5 A and stage R0, l 2026-11-07
23:13Z; the rings are the design table's).

| field or token | value | structural role |
| --- | --- | --- |
| paper ground and ink | warm archival off-white and carbon black | resting workspace plane, 1 px dividual grid hairlines, body and terminal type |
| 1-bit seal | the miniature counter-change mark of W-1 (the disc and `daphnis` in the kit face, 1x and 2x; MK-1, l 2026-11-05) | boot stamp, top-left system anchor, verified receipt indicator; the opencut lockup is the large and promo mark |
| ultramarine | deep relational blue | the active focus frame receiving keyboard and pointer input |
| yellow ochre | hydrated mineral yellow | ring 1: an explicit local persistence grant on a plane (a mounted writable path; stays on the machine) |
| burnt sienna | calcined iron earth | ring 2: an explicit network grant on a plane (an open socket or off-machine channel) |
| cadmium red | high-salience vermilion | a hard invariant fault (a canary trip, a digest desync, a killed ring 3 violation) or ring 0: a process in the ring 0 mode (stage R0) |

The pixel values: the opencut lockup fixes five of the six, paper `F3EFE6`, ink `141413`, ultramarine `1A4B8C`,
yellow ochre `E5A900`, cadmium red `D62828`; burnt sienna is not in the lockup and comes from agy's kit (W-2 A, l 2026-11-05: the five pinned now).
Stage W reads them from one table.

Planar nesting and dividual tiling:

- Co-planar containment (homage to the square): no drop shadows or translucent blur. Following Albers' nested
  squares, containment is literal on a flat plane: a ring 3 compartment sits inside its parent frame, and its
  border hue states its active authority. Floating windows may stack opaquely over the tiled plane (revision 0.7,
  HX-1 B); the top system bar then names every covered window that holds a grant or a fault (law 4).
- Dividual integer grid (Klee): the tiler subdivides screen geometry by exact checked-integer ratios, so there is
  no subpixel drift and every layout is pinned to a surface digest.
- Silent capability state: file and network grants bind to a compartment's frame rather than to modal permission
  dialogs. A writer or compiler touching a local disk path carries a calm burnt sienna border; a compartment
  holding an open socket adds a nested yellow ochre band, so local-only and networked planes never blur.

## 6. Engineering sequence: kernel to workstation

Stage 1, the sealed run and the challenge (stage R of `DESIGN.html`): R-2b and R-2c are built; R-2d (the
sealed run, the canary, the Track 2 churn script, the pinned chain) is building. Then the gate headroom, and the
public receipt and the rules of Break the Receipt after l's go and the voice review.

Stages 2 to 4 run in parallel from here, each under its own spec in `docs/specs/` and its own units:

- Stage 2, the native cint tiling desk (`docs/specs/2026-11-05-w-tiler.md`): the direct-framebuffer tiler on
  Klee's integer subdivision, a bitmap face, keyboard and pointer control, the color tokens and the mark. Native
  panel resolutions (UEFI GOP through GRUB's framebuffer tag, integer HiDPI scaling) and USB HID come after the
  first hardware boot, as their own lane.
- Stage 3, persistence (`docs/specs/2026-11-05-p-disk.md`): a persistent filesystem on a virtio block device,
  the base system verified at boot by its image digest, writable paths as explicit grants surfaced in burnt
  sienna. Atomic rollback (two boot slots) and encrypted home partitions follow, each its own ruling.
- Stage 4, capability networking (`docs/specs/2026-11-05-n-net.md`): a small cint network stack on a virtio
  network device, every received frame journaled so a run replays, and socket creation under an explicit
  per-process grant surfaced in yellow ochre. No process gets ambient network authority.

Stage 5, cross-ISA reach and Mac migration: AArch64 beside x86-64 (cint emits C, so the kernel's cint is the
same; the boot, trap, context and port stubs under `arch/` are per ISA), and the daily tools: terminal, file
navigator, document reader, macOS archive and key import, sandboxed Linux binaries for browsers and compilers.

The c family of native tools (l, 2026-11-06 03:16Z): `cish` the shell, first (`docs/specs/2026-11-06-cish-shell.md`);
`ced` the editor (`pennyleans/ced`); `cvim` the modal editor and the IDE for cint (`docs/specs/2026-11-07-cv-cvim.md`;
l, 2026-11-07 17:46Z: "cvim ... as the IDE", so `cide`'s scope is `cvim`'s). Busybox stays for its utilities.

## 7. Operating laws

1. Default completeness: a person leaving macOS never edits a config file to get legible type, sane shortcuts or
   clean tile proportions. If a workflow needs a dotfile knob to feel right, the default is unfinished.
2. Preserve the receipt: storage, networking and display drivers keep verified ring 3 workloads deterministic
   rather than trading isolation invariants for quick ports. Every device input is journaled or replayable.
3. Zero unsolicited I/O: Daphnis never opens a socket, sends telemetry, uploads a crash dump or phones a remote
   server to check a local binary. Every packet traces to an explicit user-granted capability.
4. Planar honesty: active focus, capability grants and fault boundaries stay visible on the flat tiling plane,
   never buried under overlapping windows, system trays or silent daemons. A grant or fault on a covered,
   minimized or other-desktop window is named, title and pid, one click from the bar (KD-1 A, l 2026-11-07): the
   disk and network grants in the system panel (SP-R1 B, l 2026-11-08), ring 0 counted on the bar itself (KERN).
5. Linux ABI as bridge, cint as standard: static Linux binaries keep Unix muscle memory working from day one;
   native cint software sets the bar for auditability, footprint and bit-exact verification.
6. No claim without evidence (SPEC-07 section 14): public copy states what a gate measured, names the commit,
   and makes no security or certification claim beyond it.
7. Memory targets (l, 2026-11-06): 512 MiB is the floor for booting the native cint desk, 4 GB the official
   minimum for a daily-driver workstation, 8 GB the recommended size. The pool is the machine's usable RAM
   (`docs/specs/2026-11-06-m-memory.md` M-3); a fixed 64 MiB pool is for the gates only.

## 8. Reconciliation of revision 0.5 with the tree

Each row is an edit made in this copy, or a gap left open. "Ruling" rows are asked one at a time in
`docs/DECISIONS.md`.

| # | in 0.5 | in the tree at the 0.7 baseline | done here |
| --- | --- | --- | --- |
| 1 | baseline of 0.5, R-2a built, R-2b next; 368 checks | R-2b and R-2c merged (PRs 20, 21), R-2d building; 369 lines | section 3 and section 6 stage 1 updated |
| 2 | "Mutate one canary bit and execution halts cleanly" | the canary desyncs the chain at tic 1 and after; nothing halts | reworded in section 2 |
| 3 | "cryptographic proof of process isolation"; hostile loads "cannot leak across a developer's signing keys" | the receipt proves the foreground run's integrity under churn; it says nothing about confidentiality | reworded in sections 1 and 4; law 6 added (SPEC-07 section 14) |
| 4 | Stage 1 "verified 320x200 framebuffer rendering" | the engine draws 320x200 and the client blits it 2x into the 640x480 surface (R-2c) | section 3 states what is built |
| 5 | Stage 1 "widen timing headroom on the Arch gate" | R-2d gives the doom gate its own script and budget; the user gate is at 269 s of 360 on the cloud leg | kept as limit 3; a gate lane follows R-2d |
| 6 | Stage 3: content-addressed Merkle base, atomic rollback, encrypted home | `DESIGN.html` U2 says virtio block and ext2 first; the base is already one hashed image | FS-2 C (l, 2026-11-05 17:51Z): ext2 now, a Merkle base its own later stage; rollback and encryption deferred to their own rulings |
| 7 | Stage 4: "a small, auditable cint network stack" | `DESIGN.html` left the stack (cint, or a C stack outside the checked boundary) as its own ruling | NET-1 A (l, 2026-11-05 18:18Z): the cint stack |
| 8 | Stage 2: UEFI GOP, KMS, HiDPI, USB HID | nothing has booted on hardware; display is Bochs VGA or the GRUB tag, input is PS/2 | limit 4 added; hardware boot is its own later lane |
| 9 | the two headlines of `DESIGN.html` (the forensics clean room; unsaved work never lost through the K5 snapshot and journal) are absent | K5's snapshot and journal exist; the journal is what law 2 and the network lane need | POS-1 A (l, 2026-11-05 17:49Z): this document leads; the snapshot and journal are mechanisms under law 2 |
| 10 | "We ship" | public text never says we, our or us | "The bundle is" |
| 11 | em dashes, "grayscale" spelled "greyscale", "320x200 Stage F boot screens" | house style: no em dashes, American spelling; the boot surface is 640 x 480 | edited |
| 12 | the 1-bit lockup figure is in Drive; color tokens have names, no values | the lockups are in `studio-assets` `promo/logo/` (l, 2026-11-05 18:19Z); the SVG fixes five token values | section 5 names the files and the five words; burnt sienna by W-2 |
| 13 | "passes 368 automated checks on local Arch hardware and in cloud CI" | CI runs only on self-hosted runners; the cloud gate is run by threads, not by CI | "the Arch runner and the cloud leg" |
| 14 | Stage 5 AArch64 "cint cross-ISA determinism" | not measured anywhere; `rt/cint_rt.h` asserts 64-bit pointers, `arch/x86_64/*.S` is x86 only | stated as the per-ISA stub set, no determinism claim |
| 15 | section 5 "no overlapping floating windows"; law 4 "visible on the flat tiling plane" | l ruled stacked floats (HX-1 B) and that the bar names a covered window's grant or fault (HX-9 A, 2026-11-06 00:35Z) | revision 0.7: section 5's containment bullet and law 4 rewritten |
