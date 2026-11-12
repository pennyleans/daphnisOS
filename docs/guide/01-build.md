# 01 Build, boot, check

## Needs

| tool | why |
| --- | --- |
| cint at `cint-v0.2.12`, built with its `cint.toolchain` | every `.ci` file; `check.sh` refuses any other cint (`toolchain.pin`) |
| gcc and clang, binutils (`as`, `ld`, `objcopy`, `objdump`, `readelf`, `nm`) | the two compiler legs of every flavor |
| `qemu-system-x86_64` | every boot; TCG in the gates, KVM for play |
| `musl-gcc` | rebuilding a committed program (`user/ci/build.sh`, `user/c/build.sh`); the gates use the committed bytes |
| `grub-mkrescue`, `xorriso`, `mtools` | the Multiboot 2 ISO leg (`make hello`); without them that leg prints one SKIP |
| `mke2fs`, `debugfs` (e2fsprogs) | the `/disk` volume (`tools/mkdisk.sh`) |
| python3 | the decoders and oracles under `tools/` |

Public cint is 0.2.8 today. Daphnis needs 0.2.12, so an outside build waits on a public cint at or past the pin.

## Paths

| variable | default | holds |
| --- | --- | --- |
| `CINT_TOOLCHAIN` | the `cint.toolchain` beside the `cint` on `PATH`; `user/ci/build.sh` run by hand needs it set | the pinned toolchain file |
| `DAPHNIS_BUILD` | `daphnis-build` in `$TMPDIR` (`/tmp` when it is unset); each script its own `daphnis-build-*` | every output; never the repository |

A build directory carries a `.daphnis-build` marker. A script refuses to clear a non-empty directory without it.

## Build

```
make                          # the 13 gate flavors, gcc and clang
make COMPILERS=clang          # one compiler
make hello                    # kernel32.elf (Multiboot 1) and daphnis.iso (Multiboot 2, GRUB)
make FLAVORS=hdesk COMPILERS=gcc O=$DAPHNIS_BUILD     # one flavor
```

A flavor is the kernel (`src/main_*.ci` picks the main) plus its image (a cpio the loader hands over as the first
module). 23 mains exist; 13 are the default `make`; the rest are built by the gate or script that boots them.

## Boot one flavor by hand

```
tools/run-qemu.sh IMAGE TRANSCRIPT       # TCG, no display, 30 s watchdog; serial to TRANSCRIPT
```

| variable | effect |
| --- | --- |
| `INITRD=$B/<flavor>/initrd.cpio` | the image (required for ring 3 flavors) |
| `PLAY=1` | KVM and a window (needs `/dev/kvm`) |
| `QEMU_TIMEOUT=0` | no watchdog |
| `MODE=WxH` | framebuffer size, for example `1080x1920` |
| `POOL=max MEM=4096` | the memory pool sized from RAM (ced and Doom need it) |
| `DISK=file.img` | a volume at `/disk` |
| `NET=user` | QEMU's user network, one virtio-net |
| `MONITOR=path` | QEMU monitor socket (`tools/sendkeys.py` types through it) |

## Check

| gate | PASS lines, 2026-11-06 cloud run | seconds | what it covers |
| --- | --- | --- | --- |
| `./check.sh` | 370 | 380 | K0 to K5, U1, F, P-0, R-1, every default flavor on gcc and clang |
| `./check-tiler.sh` | 24 | 121 | stage W: kit, tiler, tiles, focus, the first desk |
| `./check-hybrid.sh` | 32 | 422 | stage H: `hdesk`, portrait, Settings, mouse, menus |
| `./check-cish.sh` | 50 | 128 | `cish` against busybox `ash` on Linux |
| `./check-editor.sh` | 19 | 136 | `ced` on a pty and in the desk |
| `./check-disk.sh` | 28 | 50 | virtio-blk, ext2 read and write, `grant disk` |
| `./check-net.sh` | 25 | 92 | virtio-net, UDP, TCP, `grant net` |
| `./check-agent.sh` | 71 | 131 | `talk`, `agent` against mocks, DNS, TLS, tools |
| `./check-doom.sh` | 38 | 273 | the sealed run on Linux and Daphnis, one chain |
| `./check-episode.sh` | 21 | 149 | all of E1, Linux only, against linuxdoom |
| `./check-audio.sh` | 22 | 40 | HDA, `/dev/dsp`, the mix, `grant audio` |
| `./check-opl.sh` | 18 (1 SKIP: reference leg needs ymfm built) | 74 | the OPL3 against ymfm |

Each prints one `PASS` or `FAIL` line per check and a last `RESULT:` line. A gate that runs fewer checks than its
fixed count fails; the GRUB, live and ISO legs add their lines when their tools are present. All 12 passed in the
cloud on 2026-11-06 (gcc and clang, QEMU 8.2.2 TCG, 4 vCPU): 738 PASS, 0 FAIL, 1 SKIP, 1,976 s.
