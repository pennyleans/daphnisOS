# Daphnis K0 to K2. All outputs go under $(O), never in the repository.
#
#   make                 build both compilers, all three flavors (k1, fault, trap)
#   make COMPILERS=clang one compiler
#   make FAULT=1         the FAULT=1 flavor only (deliberate I64 overflow)
#   make hello           boot and print: kernel32.elf (Multiboot 1) and daphnis.iso (Multiboot 2, GRUB);
#                        `make` builds hello's kernel32.elf with the other flavors, the ISO needs grub-mkrescue
#   make audit           K0 symbol audit on every object and image
#   ./check.sh           the whole gate

O ?= $(or $(TMPDIR),/tmp)/daphnis-build
# RG-1: every image takes its programs from UB, built from source at HEAD (the $(UB)/% rules below), never from the
# committed user/bin; tools/check-image-apps.py refuses an image recipe that reads or writes user/bin
UB := $(O)/ubin
CINT ?= cint
CINT_TOOLCHAIN ?= $(dir $(realpath $(shell command -v $(CINT))))cint.toolchain
CINT_INC := $(shell awk '$$1=="include" {print $$2}' $(CINT_TOOLCHAIN))
CAPTURE ?= 0
ifneq ($(CAPTURE),0)
ifneq ($(CAPTURE),1)
$(error CAPTURE must be 0 or 1)
endif
endif
ifneq ($(wildcard $(O)/.capture-mode-$(if $(filter 1,$(CAPTURE)),0,1)),)
$(error capture mode changed: use a fresh O directory)
endif
ifeq ($(CAPTURE),1)
ifeq ($(wildcard $(O)/.capture-mode-1),)
ifneq ($(wildcard $(O)/*/kernel*.elf $(O)/*/daphnis.iso),)
$(error capture mode unknown for existing images: use a fresh O directory)
endif
endif
endif

COMPILERS ?= gcc clang
ifeq ($(FAULT),1)
FLAVORS ?= fault
else
FLAVORS ?= hello k1 fault trap stackover nullptr faults mem coop preempt shep k5 user
endif

# modules of each flavor, in dependency order, the root last
SRC_k1 := src/portio.ci src/serial.ci src/sha256.ci src/text.ci src/main.ci
SRC_fault := src/portio.ci src/serial.ci src/overflow.ci src/main_fault.ci
SRC_stackover := src/portio.ci src/serial.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/main_stackover.ci
SRC_nullptr := src/portio.ci src/serial.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/main_nullptr.ci
SRC_faults := src/probes.ci src/main_faults.ci
SRC_mem := src/portio.ci src/serial.ci src/sha256.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/phys.ci src/bootinfo.ci src/memmap.ci src/bits.ci src/frames.ci src/heap.ci src/memstate.ci src/allocdemo.ci src/pte.ci src/paging.ci src/main_mem.ci
# the coop and preempt images are one program; rt/ is built with the mode as a constant
SRC_tasks := src/portio.ci src/serial.ci src/sha256.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/pit.ci src/taskapi.ci src/taskwork.ci src/sched.ci src/main_tasks.ci
# K4.5: the shepherd; the same rt/ (RT_TASK_MODE 0), a different program
SRC_shep := src/portio.ci src/serial.ci src/sha256.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/taskapi.ci src/taskwork.ci src/shepwork.ci src/shep.ci src/ownstate.ci src/hogleaf.ci src/hog.ci src/phys.ci src/pte.ci src/guards.ci src/main_shep.ci
# K5: tasks as step functions, a journal, a state tree and snapshots (docs/snapshot.md)
SRC_k5 := src/portio.ci src/serial.ci src/serialrx.ci src/sha256.ci src/text.ci src/trap.ci src/gate.ci src/tss.ci src/cpu.ci src/report.ci src/taskapi.ci src/taskwork.ci src/phys.ci src/pte.ci src/bits.ci src/frames.ci src/ownstate.ci src/stepapi.ci src/taskside.ci src/kio.ci src/ts_work.ci src/kspace.ci src/kleaf.ci src/kern.ci src/main_k5.ci
RTDEF_k5 := -DRT_RUN_FUEL=4000000000000 -DRT_TASK_STACK=32768u -DRT_STATE_POOL_BYTES=17408u   # FB: 272 KiB less the 255 KiB frame bitmap, now in pool frames
SRC_coop := $(SRC_tasks)
SRC_preempt := $(SRC_tasks)
RTDEF_coop := -DRT_TASK_MODE=0
RTDEF_preempt := -DRT_TASK_MODE=1
RTDEF_shep := -DRT_TASK_STACK=16384u
# boot and print: Multiboot 1 (kernel32.elf, QEMU -kernel) and Multiboot 2 (daphnis.iso, GRUB); `make hello`
SRC_hello := src/portio.ci src/serial.ci src/main_hello.ci
# U1-1: ring 3 (docs/user.md); the user programs are built once, by the system assembler and
# linker, into one cpio image that both compilers' kernels embed, so they run the same bytes
# N-2: the network stack is under fs and proc (a socket is a description; every system call is a network tick)
SRC_netstack := src/portwide.ci src/pci.ci src/virtio.ci src/e1000.ci src/net.ci src/eth.ci src/ip.ci src/tcp.ci src/dhcp.ci src/udp.ci
SRC_user := src/portio.ci src/serial.ci src/serialrx.ci src/bootarg.ci src/text.ci src/sha256.ci src/trap.ci src/k12.ci src/gate.ci src/tss.ci src/cpu.ci src/pit.ci src/phys.ci src/bits.ci src/frames.ci src/pte.ci src/user.ci src/uvm.ci src/keyrep.ci src/inq.ci src/input.ci src/job.ci src/ptyown.ci src/pty.ci src/surfsize.ci src/seat.ci src/tile.ci src/cpio.ci src/elf.ci $(SRC_netstack) src/usbhid.ci src/usbscsi.ci src/gpt.ci src/xhci.ci src/usbms.ci src/blk.ci src/ext2.ci src/mmio.ci src/hda.ci src/dsp.ci src/fsidx.ci src/statfs.ci src/grants.ci src/fs.ci src/sock.ci src/rng.ci src/stamp.ci src/civil.ci src/cmos.ci src/sysinfo.ci src/facts.ci src/exepath.ci src/proc.ci src/surface.ci src/pool.ci src/acpitab.ci src/acpi.ci src/main_user.ci
RTDEF_user := -DRT_USER -DRT_RUN_FUEL=4000000000000 -DRT_TASK_STACK=16384u -DRT_STATE_POOL_BYTES=262144u -DRT_MAX_TASKS=1u   # HW-4 with the desk tip: 256 KiB, their module state together is 221 KiB (tile 67, proc 44, pty 25, fs 25, acpi 16). FB: 193 KiB, AU-3's 448 KiB less the 255 KiB frame bitmap, which is in pool frames now (docs/specs/2026-11-08-fb-frame-bitmap.md). AU-3: M-3's 384 KiB (the frame bitmap beside H-3a's 128 KiB, 8 pty pairs) and the 12 KiB of src/hda.ci and src/dsp.ci with room; the pool follows the high window, [2 MiB, 4 MiB), and may run on to 6 MiB (arch/x86_64/linker.ld). U1-5: the module state (fs, proc) passed 64 KiB. F-1: no kernel task runs here (main runs ring 3 processes), and the two spare tasks' stacks and records made room for the surface
RT_C_user := rt/user.c rt/fb.c rt/ps2.c rt/mmio.c
ASM_user := arch/x86_64/user.S arch/x86_64/initrd.S arch/x86_64/rng.S
# U1-5: the shell of the user image and of the images made from it. DOS-3 (unit 4b): busybox is in no image; sh is
# cish (CSH-2 A), at the root and as /bin/sh, and /bin holds the native tools the scripts of tests/image call, directly
# or through xargs (echo)
SH_TOOLS := cat cp echo find grep head ls md5sum mkdir mv rm rmdir seq sort stat sync tail tr truncate wc xargs
SH_BIN := sh=$(UB)/cish bin/ bin/sh=$(UB)/cish $(foreach t,$(SH_TOOLS),bin/$(t)=$(UB)/$(t))
USER_PROGS := hello args efault nosys segv ud spin
# U1-2: one static musl binary (musltest, from user/c/musltest.c, ruling DU-2 A) under eight names
MUSL_PROGS := mprintf mmalloc mbrk mprot mclock mtls ssea sseb mcat mls mwrite mfd mstdin mlitter mfork mpipe mexec mpipeline mfb mkeys mmouse mdirs mlimit mpoll
# R-1: committed static musl builds of cint programs (user/ci/build.sh, ruling DU-2 A); P-3: grant (GR-1 A)
CI_PROGS := mci mcifb msha grant cvim   # CV-4a: cvim, built by user/ci/build.sh cvim (DU-2)
# R-2a: the cint doom program and its bundle, the cut WAD and the engine's tables (data/SOURCES.md of freedoom-ci).
# DS-3: they are freedoom-ci at doom.pin's commit (docs/specs/2026-11-08-doom-split.md), which tools/doom/fetch.sh
# checks out at DOOM_ROOT (default: freedoom-ci in the user cache, as fetch.sh's); the stamp under O is each Doom
# image's prerequisite, so a new pin fetches and rebuilds
# the Doom stamp rule below comes before all:
.DEFAULT_GOAL := all
DOOM_PROGS := doom
DOOM_FILES := e1m6.wad tables.bin info.bin
DOOM_ROOT ?= $(or $(XDG_CACHE_HOME),$(HOME)/.cache)/freedoom-ci
DOOM_STAMP := $(O)/freedoom-ci.pinned
$(DOOM_STAMP): doom.pin tools/doom/fetch.sh
	@mkdir -p $(@D)
	@tools/doom/fetch.sh $(DOOM_ROOT) > /dev/null
	@touch $@
$(DOOM_ROOT)/bin/%: | $(DOOM_STAMP) ;
$(DOOM_ROOT)/data/%: | $(DOOM_STAMP) ;
IMAGE_FILES := hello.txt lines.txt   # U1-3: text files of the image, tests/image
IMAGE_TREE := etc/ etc/motd          # P-0: a directory member and a member under it, tests/image
IMAGE_TREE_ARGS := $(foreach t,$(IMAGE_TREE),$(if $(filter %/,$(t)),$(t),$(t)=tests/image/$(t)))
# Frame 31 (DN-53): the release image's /etc/daphnis (version, build, compiler: the About page's) and /etc/notices.txt
# (Licenses'), made by tools/mkabout.py at every make and written only when their bytes change
ABOUT_DIR := $(O)/hdesk/about
ABOUT_FILES := $(ABOUT_DIR)/daphnis $(ABOUT_DIR)/notices.txt
ABOUT_ARGS := etc/daphnis=$(ABOUT_DIR)/daphnis etc/notices.txt=$(ABOUT_DIR)/notices.txt
INITRD_user := $(O)/user/initrd.cpio   # built with the user kernel, loaded as a module (U1-5), not embedded
# R-2d: the sealed run (src/main_doom.ci), the user kernel with another main and the user image plus doom, its
# bundle and the churn program; not in the default FLAVORS: check-doom.sh builds and boots it on its own budget
SRC_doom := $(filter-out src/main_user.ci,$(SRC_user)) src/main_doom.ci
RTDEF_doom := $(RTDEF_user)
RT_C_doom := $(RT_C_user)
ASM_doom := $(ASM_user)
CHURN_PROGS := mchurn
CHURN_NET := fetch   # N-4, BU-5a: the churn runs fetch without the net grant (-EACCES); DOS-3: no busybox-net
INITRD_doom := $(O)/doom/initrd.cpio
# G-1: live play (src/main_live.ci), the doom flavor's kernel with another main and the doom flavor's image:
# `doom --live` from the keyboard and mouse; not in the default FLAVORS: check-doom.sh boots it and types
SRC_live := $(filter-out src/main_user.ci,$(SRC_user)) src/main_live.ci
RTDEF_live := $(RTDEF_user)
RT_C_live := $(RT_C_user)
ASM_live := $(ASM_user)
INITRD_live := $(O)/doom/initrd.cpio
# G-5: the episode played live (src/main_play.ci): the live flavor's kernel reading its skill and first map from
# the boot line (RT_PLAY: src/bootarg.ci), and the doom image with the whole of E1 (e1.wad) beside it; not in the
# default FLAVORS: tools/play.sh builds it and boots it under KVM with a display
SRC_play := $(filter-out src/main_user.ci,$(SRC_user)) src/main_play.ci
RTDEF_play := $(RTDEF_user) -DRT_PLAY
RT_C_play := $(RT_C_user)
ASM_play := $(ASM_user)
INITRD_play := $(O)/play/initrd.cpio
# W-2: tiles in the kernel (src/main_tile.ci, src/tile.ci), the user kernel with another main and an image of the
# tiler, mcifb and mkeys; not in the default FLAVORS: check-tiler.sh builds and boots it on its own budget
SRC_tile := $(filter-out src/main_user.ci,$(SRC_user)) src/main_tile.ci
RTDEF_tile := $(RTDEF_user)
RT_C_tile := $(RT_C_user)
ASM_tile := $(ASM_user)
INITRD_tile := $(O)/tile/initrd.cpio
# H-2: placement (src/main_hyb.ci), the tile flavor's kernel with another main and its image: tiler --place over
# three mcifb; not in the default FLAVORS: check-hybrid.sh builds and boots it
SRC_hyb := $(filter-out src/main_user.ci,$(SRC_user)) src/main_hyb.ci
RTDEF_hyb := $(RTDEF_user)
RT_C_hyb := $(RT_C_user)
ASM_hyb := $(ASM_user)
INITRD_hyb := $(O)/tile/initrd.cpio
# H-3a: the hybrid desk (src/main_hdesk.ci), the user kernel with another main and an image of hdesk, cish as sh (CS-5),
# doom and its bundle, mcifb and the text files; not in the default FLAVORS: check-hybrid.sh builds and boots it.
# HW-17: the release image (gcc hdesk), so it holds every program user/ci/kit/apps.ci opens: the core set with fetch
# (CISH_NET_BIN), the basics, cvim, calc and shot (HDESK_CPIO below); check.sh's guard (tools/check-image-apps.py)
# fails when a /bin program the desk's sources name is not in the image
SRC_hdesk := $(filter-out src/main_user.ci,$(SRC_user)) src/main_hdesk.ci
RTDEF_hdesk := $(RTDEF_user)
RT_C_hdesk := $(RT_C_user)
ASM_hdesk := $(ASM_user)
INITRD_hdesk := $(O)/hdesk/initrd.cpio
# G-5b: the episode played in a desk window (src/main_deskplay.ci), the hybrid desk's kernel with the play image:
# the hdesk image plus grant, e1.wad, menu.wad, sfx.wad (AU-5) and tests/play/doom.sh; not in the default FLAVORS: tools/play.sh
# builds it and boots it under KVM with a display
SRC_deskplay := $(filter-out src/main_user.ci,$(SRC_user)) src/main_deskplay.ci
RTDEF_deskplay := $(RTDEF_user)
RT_C_deskplay := $(RT_C_user)
ASM_deskplay := $(ASM_user)
INITRD_deskplay := $(O)/deskplay/initrd.cpio
# W-4: the desk (src/main_desk.ci), the user kernel with another main and an image of the tiler, a shell as /sh, doom
# and its bundle, mcifb and the text files; not in the default FLAVORS: check-tiler.sh builds and boots it. CS-4: the
# shell is cish; CT-5: /bin holds the native core set
SRC_desk := $(filter-out src/main_user.ci,$(SRC_user)) src/main_desk.ci
RTDEF_desk := $(RTDEF_user)
RT_C_desk := $(RT_C_user)
ASM_desk := $(ASM_user)
INITRD_desk := $(O)/desk/initrd.cpio
# CS-1: the cish flavor (src/main_cish.ci), the user kernel with another main; its image is cish, /bin holding cish as
# sh and the native tool under each name busybox's applets had (DOS-3, unit 4b), and the text files of the user
# image; check-cish.sh boots it
SRC_cish := $(filter-out src/main_user.ci,$(SRC_user)) src/main_cish.ci
RTDEF_cish := $(RTDEF_user)
RT_C_cish := $(RT_C_user)
ASM_cish := $(ASM_user)
INITRD_cish := $(O)/cish/initrd.cpio
CISH_TOOLS := basename cat cp cut dirname echo false find grep head ls md5sum mkdir mv printf rev rm rmdir seq sort stat sync tail tee test tr true truncate uniq wc xargs
# CT-0 to CT-5 (docs/specs/2026-11-06-c-core.md): the native core set, each tool its own static binary (CORE-1 A);
# BU-5a (docs/specs/2026-11-07-bu5-fetch.md): fetch in the place of CT-5's wget; BU-2b
# (docs/specs/2026-11-07-bu2-meta.md section 6): tier C-2's ln, chmod, touch and uname
CORE_TOOLS := cat wc ls head tail stat du tee mktemp mkdir rmdir rm cp mv find xargs env echo sleep date grep sort uniq cut tr cmp sha256sum true false test bracket printf basename dirname sync seq rev truncate md5sum fetch ln chmod touch uname df ps
# CT-5: the program bracket is /bin/[ in an image (a file name cint cannot give a module)
core_name = $(if $(filter bracket,$(1)),[,$(1))
CORE_BIN := $(foreach t,$(CORE_TOOLS),bin/$(call core_name,$(t))=$(UB)/$(t))
# CS-5 (CSH-2 A): an image a person or the agent uses has cish as /sh and /bin/sh. CT-5 (CORE-4 A): its /bin holds the
# native core set (desk, hdesk, deskplay without fetch, desknet with it). DOS-3 (unit 4b): no image holds busybox; it
# runs only on Linux, as the gates' oracle, built from its tarball by user/busybox/oracle.sh
CISH_BIN := sh=$(UB)/cish bin/ bin/sh=$(UB)/cish $(filter-out bin/fetch=%,$(CORE_BIN))
CISH_NET_BIN := sh=$(UB)/cish bin/ bin/sh=$(UB)/cish $(CORE_BIN)
# BP-5 (docs/specs/2026-11-07-bp-basics.md section 1): the basics (BP-1 to BP-3) in /bin of the images a person
# boots, deskplay (tools/play.sh), desknet (tools/run-desk-agent.sh) and, since HW-17, hdesk (the release image); the
# desk gate image stays as it is, since its image must end below the pool at 32 MiB
BASICS_TOOLS := cless ccalc cview
BASICS_BIN := $(foreach t,$(BASICS_TOOLS),bin/$(t)=$(UB)/$(t))
# HW-17: the hdesk images' members, one list that the recipes and tools/check-image-apps.py read (`make -s
# print-hdesk-release`). HDESK_RELEASE_CPIO is the release image, hdesk/release.cpio, which
# tools/build-release-stick.sh ships: the core set with fetch (CISH_NET_BIN), cish at /bin/cish too (Console's
# program; one inode), the basics, and HDESK_APPS: CVim, Calc's window (calc, RS-CALC, the Calc row's program) and
# shot (RS-SHOT, which the desk runs for a screenshot); no Doom (l 2026-11-12 07:59Z: the port is GPL-2.0, SW-1 C).
# HDESK_CPIO, the gates' hdesk image (check-hybrid's doom cases, the guest legs), is the same and Doom.
HDESK_APPS := cvim calc shot
# RG-1: the hdesk images take no committed user/bin, and since the export lane's read of l-3-recut no image does.
# Each program of RELEASE_PROGS, as every other image's, is built from its source at HEAD into $(UB) (rules below):
# user/ci/build.sh for the cint programs, user/c/build.sh for the C probes,
# tools/build-ced.sh for ced at its pin (user/ced, SOURCES.sha256), so a stale binary cannot ship.
RELEASE_PROGS := hdesk cish $(CORE_TOOLS) $(BASICS_TOOLS) $(HDESK_APPS) ced finder monitor setkey bgread grant authd accounts kern tray mcifb mwin
HDESK_RELEASE_CPIO = hdesk=$(UB)/hdesk sh=$(UB)/cish bin/ bin/sh=$(UB)/cish $(foreach t,$(CORE_TOOLS),bin/$(call core_name,$(t))=$(UB)/$(t)) bin/cish=$(UB)/cish $(foreach t,$(BASICS_TOOLS) $(HDESK_APPS) ced finder monitor setkey bgread grant authd accounts kern tray,bin/$(t)=$(UB)/$(t)) mcifb=$(UB)/mcifb mwin=$(UB)/mwin $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS) $(ABOUT_ARGS) tmp/@1777
HDESK_CPIO = $(HDESK_RELEASE_CPIO) $(foreach p,$(DOOM_PROGS),$(p)=$(DOOM_ROOT)/bin/$(p)) $(foreach f,$(DOOM_FILES),$(f)=$(DOOM_ROOT)/data/$(f))
# A-0: the desk with the network (src/main_desknet.ci), the desk's kernel with another main and an image of the
# tiler, cish as sh with the native core set and fetch in /bin (CS-5, CT-5, BU-5a), talk and grant; not in the default FLAVORS and in no gate: tools/run-desk-agent.sh boots it
SRC_desknet := $(filter-out src/main_user.ci,$(SRC_user)) src/rtc.ci src/main_desknet.ci
RTDEF_desknet := $(RTDEF_user)
RT_C_desknet := $(RT_C_user)
ASM_desknet := $(ASM_user)
INITRD_desknet := $(O)/desknet/initrd.cpio
# N-1: the network device and its record (docs/specs/2026-11-05-n-net.md); not in the default FLAVORS: check.sh
# replays the committed journal and check-net.sh boots it live on its own budget. RT_USER for the image (net.journal)
SRC_net := $(filter-out src/main_user.ci src/surface.ci,$(SRC_user)) src/rtc.ci src/main_net.ci   # A-3: rtc for the agent's legs
RTDEF_net := $(RTDEF_user)
RT_C_net := $(RT_C_user)
ASM_net := $(ASM_user)
# P-1, P-2: the block device and the volume (src/main_disk.ci), the user kernel with another main;
# not in the default FLAVORS: check-disk.sh builds it and boots it with the volume of tools/mkdisk.sh
SRC_disk := $(filter-out src/main_user.ci src/surface.ci,$(SRC_user)) src/main_disk.ci
RTDEF_disk := $(RTDEF_user)
RT_C_disk := $(RT_C_user)
ASM_disk := $(ASM_user)
INITRD_disk := $(INITRD_user)
SRC_trap := src/portio.ci src/serial.ci src/text.ci src/trap.ci src/gate.ci src/idt.ci src/pit.ci src/main_trap.ci

# Freestanding flags. -mgeneral-regs-only: no SSE, which boot.S does not enable.
# -mcmodel=small (not kernel): the image links at 1 MiB, inside the low 2 GiB that the small
# model assumes, and boot.S identity maps it (docs/boot.md). CINT_RT_HELPERS_PORTABLE:
# cint_rt.h's portable helpers, so no __int128 and no libgcc routine (docs/runtime.md).
# BU4-4 A2 (docs/specs/2026-11-07-bu4-toolchain.md 9a): the emitted modules of EMCOLD, which no measured path keeps
# busy, at -Os, every other module and the runtime at OPT, -O2. The high window [2 MiB, 4 MiB) of arch/x86_64/linker.ld
# holds every emitted module, and at -O2 gcc 16 filled it; -Os for all of them made gcc's kernel about 3 times slower
# under TCG. A module's name in EMCOLD is its file's name without .ci; main_% stands for every flavor's main.
OPT ?= -O2
# The network stack (net tcp udp sock eth ip) and virtio, its transport and blk's, joined the list with K12 and K13
# (BU-4a, BU-4e): check-net and check-agent kept their times (136 s against 140 s, 120 s against 117 s).
EMCOLD ?= hda dsp memmap pool bootarg bootinfo pci mmio rng cursor input job ext2 main_% net tcp dhcp udp sock eth ip virtio statfs sysinfo facts grants stamp civil cmos keyrep inq e1000
FFLAGS := -std=c17 $(OPT) -ffreestanding -nostdlib -fno-builtin -fno-stack-protector \
          -mno-red-zone -mcmodel=small -fno-pic -fno-pie -mgeneral-regs-only -fcf-protection=none \
          -fno-asynchronous-unwind-tables -fno-unwind-tables -fstack-clash-protection -DCINT_RT_HELPERS_PORTABLE -I$(CINT_INC)
RTFLAGS := $(FFLAGS) -Irt -Wall -Wextra -Wpedantic -Werror

RT_C := rt/boot.c rt/mem.c rt/serial.c rt/console.c rt/fault.c rt/ctx.c rt/host.c rt/trap.c rt/phys.c rt/task.c rt/chan.c rt/state.c rt/start.c
ASM := arch/x86_64/boot.S arch/x86_64/portio.S arch/x86_64/trap.S arch/x86_64/probe.S arch/x86_64/task.S

# Confidential capture currently uses a separate QEMU fixture key file.
ifeq ($(CAPTURE),1)
RTFLAGS += -DRT_CAPTURE -DDAPH_CAPTURE_PRIVATE_HIGH
RT_C += rt/capture_boot.c rt/capture_sink.c rt/capture_replay.c rt/capture_crypto.c vendor/monocypher/monocypher.c
endif

IMAGES := $(foreach c,$(COMPILERS),$(foreach f,$(FLAVORS),$(O)/$(c)-$(f)/kernel32.elf))

all: $(O)/.capture-mode-$(CAPTURE) $(IMAGES)

.PHONY: all hello audit clean about-facts print-hdesk-release
.SECONDARY:
.SECONDEXPANSION:

# Never reuse plaintext products when confidential capture was requested.
$(O)/.capture-mode-$(CAPTURE):
	@mkdir -p $(O)
	@if test -e $(O)/.capture-mode-$(if $(filter 1,$(CAPTURE)),0,1); then echo 'capture mode changed: use a fresh O directory' >&2; exit 1; fi
	@touch $@

# emitted C: independent of the host compiler, so emitted once per flavor. emit-c takes at most 64 modules (cint
# v0.2.18), and SRC_desknet lists 66; a module that a listed module imports is resolved by emit-c itself, so these
# stay prerequisites and are not named: src/seat.ci and src/keyrep.ci, which src/proc.ci imports, src/inq.ci,
# which src/input.ci imports, and src/acpitab.ci, which src/acpi.ci imports
EMIT_IMPLIED := src/seat.ci src/keyrep.ci src/inq.ci src/acpitab.ci
$(O)/emit-%/stamp: $$(SRC_$$*) $(CINT_TOOLCHAIN)
	@echo "emit $*"
	@rm -rf $(@D)
	@mkdir -p $(@D)
	@$(CINT) emit-c --toolchain $(CINT_TOOLCHAIN) --root . --out $(@D)/out $(filter-out $(EMIT_IMPLIED),$(SRC_$*))
	@cp -r $(@D)/$$(cut -d" " -f1 $(@D)/out/MANIFEST.ref) $(@D)/c
	@touch $@

# KP-1: an image whose module state does not fit its state pool (rt/ctx.c, RT_STATE_POOL_BYTES) is not built: the
# check reads both sizes from the linked image, and on a miss prints the count and removes the image, so nothing
# boots a kernel that would fault at its first module past the pool. Each image's line stays in state-pool.txt
define build_rules
$(O)/$(1)-$(2)/kernel.elf: $(O)/.capture-mode-$(CAPTURE) $(O)/emit-$(2)/stamp $(RT_C) $(RT_C_$(2)) $(ASM) $(ASM_$(2)) arch/x86_64/linker.ld rt/rt.h rt/fbmode.h rt/fb_pixels.h rt/face.h rt/capture_crypto.h rt/capture_sink.h rt/capture_replay.h tools/build-image.sh tools/check-state-pool.py $(INITRD_$(2))
	@echo "build $(1)-$(2)"
	@FFLAGS="$(FFLAGS)" EMCOLD="$(EMCOLD)" RTFLAGS="$(RTFLAGS) $(RTDEF_$(2))" RT_C="$(RT_C) $(RT_C_$(2))" ASM="$(ASM) $(ASM_$(2))" tools/build-image.sh $(1) $(2) $(O)
	@python3 tools/check-state-pool.py $(O)/$(1)-$(2)/kernel.elf > $(O)/$(1)-$(2)/state-pool.txt \
	    || { cat $(O)/$(1)-$(2)/state-pool.txt >&2; rm -f $(O)/$(1)-$(2)/kernel.elf; exit 1; }
endef
$(foreach c,$(COMPILERS),$(foreach f,$(sort $(FLAVORS) hello),$(eval $(call build_rules,$(c),$(f)))))

# QEMU's -kernel takes Multiboot 1 only as ELF32
$(O)/%/kernel32.elf: $(O)/%/kernel.elf
	@objcopy -O elf32-i386 $< $@

# Multiboot 2: GRUB boots the ELF64 kernel.elf directly (tools/build-iso.sh)
$(O)/%/daphnis.iso: $(O)/%/kernel.elf tools/build-iso.sh
	@echo "iso $*"
	@tools/build-iso.sh $< $@

# the user programs (U1-1): static ELF64, no libc, Linux system calls; user/user.ld fixes the layout
# and -s drops the symbol table, so the bytes do not depend on how the host binutils was configured
$(O)/user/%: user/%.S user/user.ld
	@mkdir -p $(@D)
	@as --64 -o $@.o $<
	@ld -m elf_x86_64 -static -nostdlib --build-id=none -z noexecstack -s -T user/user.ld -o $@ $@.o

$(foreach p,$(MUSL_PROGS),$(O)/user/$(p)): $(UB)/musltest
	@mkdir -p $(@D)
	@cp $< $@

$(O)/user/sh: $(UB)/cish
	@mkdir -p $(@D)
	@cp $< $@

$(foreach p,$(CI_PROGS),$(O)/user/$(p)): $(UB)/$$(notdir $$@)
	@mkdir -p $(@D)
	@cp $< $@

USER_CPIO := $(foreach p,$(USER_PROGS),$(p)=$(O)/user/$(p)) $(foreach p,$(MUSL_PROGS),$(p)=$(UB)/musltest) $(SH_BIN) $(foreach p,$(CI_PROGS),$(p)=$(UB)/$(p)) $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS)
$(O)/user/initrd.cpio: $(addprefix $(O)/user/,$(USER_PROGS) $(MUSL_PROGS) sh $(CI_PROGS)) $(addprefix $(UB)/,$(SH_TOOLS)) $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) tools/mkcpio.py
	@echo "initrd user"
	@python3 tools/mkcpio.py $@ $(USER_CPIO)

# BU-2a (docs/specs/2026-11-07-bu2-meta.md section 7): the user image and the metadata probe mmeta; check-disk.sh's
# P-3 boots and their Linux run take it. BU-4f (docs/specs/2026-11-07-bu4-toolchain.md 4.5): the probe mexe, at the
# root and under bin/. BU-4a (4.8): the probe mvfork, and pdpmake, whose recipes run through system()'s /bin/sh (the
# user image's cish)
$(O)/meta/initrd.cpio: $(O)/user/initrd.cpio $(UB)/mmeta $(UB)/mexe $(UB)/mvfork user/cint/opt/make
	@echo "initrd meta"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(USER_CPIO) mmeta=$(UB)/mmeta mexe=$(UB)/mexe mvfork=$(UB)/mvfork \
	    make=user/cint/opt/make bin/mexe=$(UB)/mexe

# BU-4c (docs/specs/2026-11-07-bu4-toolchain.md section 6): the user image and the core set's sha256sum; check-build.sh
# boots the disk flavor with it on the volume of tools/mkcintvol.sh
$(O)/build/initrd.cpio: $(O)/user/initrd.cpio $(UB)/sha256sum
	@echo "initrd build"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(USER_CPIO) sha256sum=$(UB)/sha256sum

# FF-1 (docs/specs/2026-11-07-ff-super-plane.md section 4): the user image and the index probe ix; check-disk.sh's
# index boots take it
$(O)/ix/initrd.cpio: $(O)/user/initrd.cpio $(UB)/ix
	@echo "initrd ix"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(USER_CPIO) ix=$(UB)/ix

DOOM_CPIO := $(foreach p,$(USER_PROGS),$(p)=$(O)/user/$(p)) $(foreach p,$(MUSL_PROGS),$(p)=$(UB)/musltest) $(SH_BIN) $(foreach p,$(CI_PROGS),$(p)=$(UB)/$(p)) $(foreach p,$(DOOM_PROGS),$(p)=$(DOOM_ROOT)/bin/$(p)) $(foreach p,$(CHURN_PROGS),$(p)=$(UB)/$(p)) $(foreach p,$(CHURN_NET),$(p)=$(UB)/$(p)) $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(foreach f,$(DOOM_FILES),$(f)=$(DOOM_ROOT)/data/$(f)) $(IMAGE_TREE_ARGS)
$(O)/doom/initrd.cpio: $(INITRD_user) $(DOOM_STAMP) $(addprefix $(DOOM_ROOT)/bin/,$(DOOM_PROGS)) $(addprefix $(UB)/,$(CHURN_PROGS) $(CHURN_NET)) $(addprefix $(DOOM_ROOT)/data/,$(DOOM_FILES)) tools/mkcpio.py
	@echo "initrd doom"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(DOOM_CPIO)

# G-5: the doom image and e1.wad; G-5b: menu.wad, the menu's lumps
$(O)/play/initrd.cpio: $(INITRD_user) $(DOOM_STAMP) $(addprefix $(DOOM_ROOT)/bin/,$(DOOM_PROGS)) $(addprefix $(UB)/,$(CHURN_PROGS) $(CHURN_NET)) $(addprefix $(DOOM_ROOT)/data/,$(DOOM_FILES) e1.wad menu.wad) tools/mkcpio.py
	@echo "initrd play"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(DOOM_CPIO) e1.wad=$(DOOM_ROOT)/data/e1.wad menu.wad=$(DOOM_ROOT)/data/menu.wad

$(O)/tile/initrd.cpio: $(UB)/tiler $(UB)/mcifb $(UB)/musltest tools/mkcpio.py
	@echo "initrd tile"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ tiler=$(UB)/tiler mcifb=$(UB)/mcifb mkeys=$(UB)/musltest

$(O)/desk/initrd.cpio: $(UB)/ced $(UB)/tiler $(UB)/cish $(addprefix $(UB)/,$(filter-out fetch,$(CORE_TOOLS))) $(UB)/mcifb $(DOOM_STAMP) $(addprefix $(DOOM_ROOT)/bin/,$(DOOM_PROGS)) $(addprefix $(DOOM_ROOT)/data/,$(DOOM_FILES)) $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) tools/mkcpio.py
	@echo "initrd desk"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ tiler=$(UB)/tiler $(CISH_BIN) bin/ced=$(UB)/ced mcifb=$(UB)/mcifb $(foreach p,$(DOOM_PROGS),$(p)=$(DOOM_ROOT)/bin/$(p)) $(foreach f,$(DOOM_FILES),$(f)=$(DOOM_ROOT)/data/$(f)) $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS)

# About (frame 31): /etc/daphnis and /etc/notices.txt, written by tools/mkabout.py when their bytes change
$(ABOUT_FILES) &: about-facts
	@python3 tools/mkabout.py $(ABOUT_DIR)

about-facts: ;

$(O)/hdesk/initrd.cpio: $(addprefix $(UB)/,$(RELEASE_PROGS)) $(DOOM_STAMP) $(addprefix $(DOOM_ROOT)/bin/,$(DOOM_PROGS)) $(addprefix $(DOOM_ROOT)/data/,$(DOOM_FILES)) $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) $(ABOUT_FILES) tools/mkcpio.py
	@echo "initrd hdesk"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(HDESK_CPIO)

# HW-17: the release image: the hdesk image without Doom, from the same list
$(O)/hdesk/release.cpio: $(addprefix $(UB)/,$(RELEASE_PROGS)) $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) $(ABOUT_FILES) tools/mkcpio.py
	@echo "initrd hdesk release"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ $(HDESK_RELEASE_CPIO)

# HW-17: the release image's members, then Doom's names, for tools/check-image-apps.py; then the programs built
# from source for it (RG-1)
print-hdesk-release:
	@echo $(HDESK_RELEASE_CPIO)
	@echo $(DOOM_PROGS) $(DOOM_FILES)
	@echo $(RELEASE_PROGS)

# RG-1: a program of the hdesk images, built from its source at HEAD: its whole import closure (user/ci/build.sh
# --deps, the closure rows_for walks), main.c, host.c, host.h, build.sh and the toolchain. Each build's log is beside
# it; a failed build leaves no program. fetch links BearSSL (A-4), built from the Ubuntu archive's tarball, which
# user/tls/build.sh checks against its SHA-256; BEARSSL_TARBALL names a copy already on disk.
UB_COMMON := user/ci/build.sh user/ci/main.c user/ci/host.c user/ci/host.h $(CINT_TOOLCHAIN)
BEARSSL_URL := https://archive.ubuntu.com/ubuntu/pool/universe/b/bearssl/bearssl_0.6+dfsg.1.orig.tar.xz
BEARSSL_TARBALL ?= $(O)/tls/bearssl_0.6+dfsg.1.orig.tar.xz
$(UB)/%: $$(shell bash user/ci/build.sh --deps $$*) $(UB_COMMON)
	@echo "build $*"
	@mkdir -p $(@D)
	@CINT_TOOLCHAIN=$(CINT_TOOLCHAIN) CI_OUT=$(UB) CI_TLS=$(O)/tls bash user/ci/build.sh $* > $@.log 2>&1 \
	    || { cat $@.log >&2; rm -f $@; exit 1; }
# The programs that import user/ci/tls.ci (fetch, agent) link BearSSL from $(O)/tls
$(UB)/fetch $(UB)/agent: $(O)/tls/libbearssl.a user/tls/anchors.h
# The C probes (user/c, musl-gcc as user/c/build.sh builds them): a static pattern, so the cint rule above is not tried
C_PROGS := $(basename $(notdir $(wildcard user/c/*.c)))
$(addprefix $(UB)/,$(C_PROGS)): $(UB)/%: user/c/%.c user/c/build.sh
	@echo "build $*"
	@mkdir -p $(@D)
	@CI_OUT=$(UB) bash user/c/build.sh $* > $@.log 2>&1 || { cat $@.log >&2; rm -f $@; exit 1; }
$(UB)/ced: tools/build-ced.sh user/ced/SOURCES.sha256 $(wildcard user/ced/*.ci) $(CINT_TOOLCHAIN)
	@echo "build ced"
	@mkdir -p $(@D)
	@CINT_TOOLCHAIN=$(CINT_TOOLCHAIN) CI_OUT=$(UB) bash tools/build-ced.sh > $@.log 2>&1 \
	    || { cat $@.log >&2; rm -f $@; exit 1; }
$(O)/tls/bearssl_0.6+dfsg.1.orig.tar.xz:
	@mkdir -p $(@D)
	@curl -sSfL -o $@.part $(BEARSSL_URL) && mv $@.part $@
$(O)/tls/libbearssl.a: $(BEARSSL_TARBALL) user/tls/build.sh
	@echo "build bearssl"
	@mkdir -p $(O)/tls
	@bash user/tls/build.sh $(BEARSSL_TARBALL) $(O)/tls > $(O)/tls-build.log 2>&1 \
	    || { cat $(O)/tls-build.log >&2; exit 1; }

$(O)/deskplay/initrd.cpio: $(UB)/ced $(UB)/hdesk $(UB)/finder $(UB)/monitor $(UB)/setkey $(UB)/bgread $(UB)/cish $(addprefix $(UB)/,$(filter-out fetch,$(CORE_TOOLS))) $(addprefix $(UB)/,$(BASICS_TOOLS)) $(UB)/mcifb $(UB)/grant $(UB)/authd $(UB)/accounts $(UB)/kern $(UB)/tray $(DOOM_STAMP) $(addprefix $(DOOM_ROOT)/bin/,$(DOOM_PROGS)) $(addprefix $(DOOM_ROOT)/data/,$(DOOM_FILES) e1.wad menu.wad sfx.wad) tests/play/doom.sh $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) tools/mkcpio.py
	@echo "initrd deskplay"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ hdesk=$(UB)/hdesk $(CISH_BIN) $(BASICS_BIN) bin/ced=$(UB)/ced bin/finder=$(UB)/finder bin/monitor=$(UB)/monitor bin/setkey=$(UB)/setkey bin/bgread=$(UB)/bgread bin/grant=$(UB)/grant bin/authd=$(UB)/authd bin/accounts=$(UB)/accounts bin/kern=$(UB)/kern bin/tray=$(UB)/tray mcifb=$(UB)/mcifb $(foreach p,$(DOOM_PROGS),$(p)=$(DOOM_ROOT)/bin/$(p)) $(foreach f,$(DOOM_FILES) e1.wad menu.wad sfx.wad,$(f)=$(DOOM_ROOT)/data/$(f)) doom.sh=tests/play/doom.sh $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS) tmp/@1777

$(O)/cish/initrd.cpio: $(UB)/ced $(UB)/cish $(addprefix $(UB)/,$(CISH_TOOLS)) $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) tools/mkcpio.py
	@echo "initrd cish"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ cish=$(UB)/cish bin/ bin/ced=$(UB)/ced bin/sh=$(UB)/cish $(foreach t,$(CISH_TOOLS),bin/$(t)=$(UB)/$(t)) $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS)

# CT-0 (docs/specs/2026-11-06-c-core.md section 6): the core image, booted by the cish flavor's kernel; cish, /bin
# holding the native core tools and no busybox, and the fixture tree tests/core/tree as /t; check-core.sh boots it
# CT-1: the tree's directories first (parents before what they hold), then its files; a name with a space stays out of
# the image (make splits words on spaces; the Linux cases hold it), and src/fs.ci holds 64 entries in all
CORE_TREE_DIRS := $(sort $(patsubst tests/core/tree/%,%,$(shell find tests/core/tree -mindepth 1 -type d ! -name '* *')))
CORE_TREE := $(sort $(patsubst tests/core/tree/%,%,$(shell find tests/core/tree -mindepth 1 -type f ! -name '* *')))
# CT-3: the search tools' tree tests/core/search as /s
CORE_SEARCH_DIRS := $(sort $(patsubst tests/core/search/%,%,$(shell find tests/core/search -mindepth 1 -type d)))
CORE_SEARCH := $(sort $(patsubst tests/core/search/%,%,$(shell find tests/core/search -mindepth 1 -type f)))
$(O)/core/initrd.cpio: $(UB)/cish $(addprefix $(UB)/,$(CORE_TOOLS)) $(addprefix tests/core/tree/,$(CORE_TREE)) $(addprefix tests/core/search/,$(CORE_SEARCH)) tools/mkcpio.py
	@echo "initrd core"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ cish=$(UB)/cish bin/ $(foreach t,$(CORE_TOOLS),bin/$(call core_name,$(t))=$(UB)/$(t)) t/ $(foreach d,$(CORE_TREE_DIRS),t/$(d)/) $(foreach f,$(CORE_TREE),t/$(f)=tests/core/tree/$(f)) s/ $(foreach d,$(CORE_SEARCH_DIRS),s/$(d)/) $(foreach f,$(CORE_SEARCH),s/$(f)=tests/core/search/$(f))

# BP (docs/specs/2026-11-07-bp-basics.md section 5): the basics image for check-basics.sh: cish, /bin with the three
# tools and cat, and tests/basics/tree as /b
BASICS_TREE_DIRS := $(sort $(patsubst tests/basics/tree/%,%,$(shell find tests/basics/tree -mindepth 1 -type d)))
BASICS_TREE := $(sort $(patsubst tests/basics/tree/%,%,$(shell find tests/basics/tree -mindepth 1 -type f)))
$(O)/basics/initrd.cpio: $(UB)/cish $(UB)/cat $(addprefix $(UB)/,$(BASICS_TOOLS)) $(addprefix tests/basics/tree/,$(BASICS_TREE)) tools/mkcpio.py
	@echo "initrd basics"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ cish=$(UB)/cish bin/ bin/cat=$(UB)/cat $(foreach t,$(BASICS_TOOLS),bin/$(t)=$(UB)/$(t)) b/ $(foreach d,$(BASICS_TREE_DIRS),b/$(d)/) $(foreach f,$(BASICS_TREE),b/$(f)=tests/basics/tree/$(f))

$(O)/desknet/initrd.cpio: $(UB)/ced $(UB)/tiler $(UB)/cish $(addprefix $(UB)/,$(CORE_TOOLS)) $(addprefix $(UB)/,$(BASICS_TOOLS)) $(UB)/talk $(UB)/agent $(UB)/grant $(addprefix tests/image/,$(IMAGE_FILES) $(filter-out %/,$(IMAGE_TREE))) tools/mkcpio.py
	@echo "initrd desknet"
	@mkdir -p $(@D)
	@python3 tools/mkcpio.py $@ tiler=$(UB)/tiler $(CISH_NET_BIN) $(BASICS_BIN) bin/ced=$(UB)/ced bin/grant=$(UB)/grant bin/talk=$(UB)/talk bin/agent=$(UB)/agent $(foreach t,$(IMAGE_FILES),$(t)=tests/image/$(t)) $(IMAGE_TREE_ARGS)

hello: $(foreach c,$(COMPILERS),$(O)/$(c)-hello/kernel32.elf $(O)/$(c)-hello/daphnis.iso)

audit: all
	tools/audit-symbols.sh $(O) "$(COMPILERS)" "$(FLAVORS)"

clean:
	rm -rf $(O)
