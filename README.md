# Daphnis

Daphnis is an experimental desktop operating system for x86-64 PCs, written in
[cint](https://github.com/pennyleans/cint-public-build). It has its own kernel,
window system, shell and applications. The desktop draws its text, shadows and
animation with integer arithmetic. A small C runtime and assembly boot code
connect it to the machine.

This is an early system for exploring and building. QEMU is the easiest place to
try it. Hardware support is limited, and it is not ready for everyday use.

[Download 0.1.1](https://github.com/pennyleans/daphnisOS/releases/tag/v0.1.1) ·
[Changelog](CHANGELOG.md) · [User guide](docs/guide/README.md)

## What runs

The system includes a desktop with floating and tiled windows, persistent user
accounts and files, a shell, editors and basic network tools. The cint compiler
and toolchain run inside Daphnis. Static Linux x86-64 programs can run when they
use the subset of Linux system calls the kernel implements.

| App | What it is |
| --- | --- |
| Console | `cish`, a POSIX shell, in a terminal |
| Edit | `ced`, the text editor |
| CVim | a modal editor with Vim's grammar |
| Read | `cless`, the pager |
| View | PNG pictures |
| Calc | a calculator |
| Monitor | processor, memory, disk, network and processes |
| Index | the file browser |
| Fetch | downloads over HTTPS |
| Settings | display, desk, sound, keyboard, network, date and time, storage, accounts and grants |

## Get started

[Download the latest release](https://github.com/pennyleans/daphnisOS/releases/latest): one compressed disk image for QEMU or a USB drive, `daphnis-0.1.1-x86_64.img.xz`, and `SHA256SUMS`. Check the compressed image, then unpack and check the disk image:

```sh
grep '  daphnis-0.1.1-x86_64.img.xz$' SHA256SUMS | sha256sum -c -
xz -dk daphnis-0.1.1-x86_64.img.xz
grep '  daphnis-0.1.1-x86_64.img$' SHA256SUMS | sha256sum -c -
```

To run it in a window, install QEMU and its UEFI firmware (`qemu-system-x86` and `ovmf` on Ubuntu 24.04), then:

```sh
cp /usr/share/OVMF/OVMF_VARS_4M.fd daphnis-vars.fd
qemu-system-x86_64 -accel tcg -cpu max -m 4G \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=daphnis-vars.fd \
  -vga none -device bochs-display,edid=on,xres=1920,yres=1080 \
  -device qemu-xhci \
  -drive if=none,id=stick,format=raw,file=daphnis-0.1.1-x86_64.img \
  -device usb-storage,drive=stick
```

The first boot asks for a name and a password and makes a Parent account. Every later boot ends at the login screen. Shut Down is under the power button in the Super plane; tap Super to open it. Accounts and files stay in the image file, so the same command starts it again.

To run it on a PC, write the image to a whole USB drive (this erases the drive), turn Secure Boot off and choose the drive's UEFI entry in the firmware's boot menu:

```sh
sudo dd if=daphnis-0.1.1-x86_64.img of=/dev/sdX bs=4M conv=fsync status=progress
```

## Build from source

Use the pinned public cint 0.2.18 (commit `a14a03f3`). Bootstrap it from [cint v0.2.18](https://github.com/pennyleans/cint-public-build/releases/tag/v0.2.18), put `cint` on `PATH` and set `CINT_TOOLCHAIN` to the `cint.toolchain` beside it. On Debian or Ubuntu, with git, curl, gcc, clang, musl-tools, QEMU, OVMF, grub-efi-amd64-bin, mtools, e2fsprogs, fdisk and python3:

```sh
tools/build-release-stick.sh daphnis-0.1.1-x86_64.img
```

`tools/build-release-stick.sh` builds the release image from the committed tree.
Use a Git checkout at `v0.1.1`; the script reads `HEAD`. Build intermediates go
under `$TMPDIR`. Plain `make` also builds development images, some of which need
the separate Doom checkout described in the guide.

The `check-*.sh` scripts cover individual parts of the system. The full
`check-release.sh` also reads development acceptance records that are not in this
public export. Its results for the published image are recorded in `CHECKS.txt`.

## Documentation

- [Changelog](CHANGELOG.md): changes and verification for the current release.
- [Release notes](https://github.com/pennyleans/daphnisOS/releases): what each version contains and its known limits.
- [Guide](docs/guide/README.md): building, booting, the shell, the editor, files, network and sound.
- [NOTICE](NOTICE): third-party components and their licenses.

## Source

| Directory | Contents |
| --- | --- |
| `src/` | Kernel, drivers, file system and network stack, in cint |
| `arch/`, `rt/` | Boot stubs and the small C runtime |
| `user/ci/` | Desk, apps, shell and core commands, in cint |
| `user/cint/`, `user/qbe/` | The toolchain that runs inside Daphnis |
| `user/ced/`, `user/cvim/` | The editors |
| `tools/`, `tests/` | Build, run and image tools; tests and expected outcomes |

## Status

Daphnis is in development, and versions before 1.0 may change anything. It runs on one processor core. It has no NVMe or SATA driver and never writes a computer's internal drives. Nothing on its volume is encrypted. Of virtual machines, only QEMU is tested.

The Doom port is a separate repository, [freedoom-ci](https://github.com/pennyleans/freedoom-ci).

## Development

Development uses AI coding agents, with human direction and review. Source, build scripts and tests are available here. Each release is a source snapshot; the public repository does not contain the full development history. See [Contributing](CONTRIBUTING.md) for bug reports and patches.

## Release contents

Each release includes the disk image, checksums and a source archive. The three
`grub2-unsigned` files beside the image are the corresponding source package for
its GNU GRUB boot loader. They are not needed to boot the image. Other bundled
components and their source locations are listed in [NOTICE](NOTICE).

## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE) for third-party components.
