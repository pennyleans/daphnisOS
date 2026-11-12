<p align="center">
  <b>Daphnis</b>
  <br>
  A small operating system written in cint.
  <br><br>
  <a href="https://github.com/pennyleans/daphnisOS/releases/latest"><img src="https://img.shields.io/github/v/release/pennyleans/daphnisOS" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/platform-x86--64%20UEFI-blue" alt="x86-64 UEFI">
</p>

# Daphnis

Daphnis is a small operating system for x86-64 PCs. Its kernel, desk and programs are written in [cint](https://github.com/pennyleans/cint-public-build), where every integer operation is checked: an overflow or an out-of-range conversion stops with a fault, never a wrong value. Every pixel the desk draws, its text, shadows and motion included, comes from integer arithmetic. A small C runtime and a few short assembly stubs remain.

Static Linux x86-64 programs run unmodified on the part of the Linux system call set Daphnis implements. The cint toolchain runs inside Daphnis, and cint rebuilds itself there. No C compiler, busybox or GPL program is part of the system; the drive's boot loader is GNU GRUB.

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

[Download the latest release](https://github.com/pennyleans/daphnisOS/releases/latest): one compressed disk image for QEMU or a USB drive, `daphnis-0.1.0-x86_64.img.xz`, and `SHA256SUMS`. Unpack it beside the download and check both files:

```sh
xz -dk daphnis-0.1.0-x86_64.img.xz
sha256sum -c SHA256SUMS
```

To run it in a window, install QEMU and its UEFI firmware (`qemu-system-x86` and `ovmf` on Ubuntu 24.04), then:

```sh
cp /usr/share/OVMF/OVMF_VARS_4M.fd daphnis-vars.fd
qemu-system-x86_64 -accel tcg -cpu max -m 4G \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=daphnis-vars.fd \
  -vga none -device bochs-display,edid=on,xres=1920,yres=1080 \
  -device qemu-xhci \
  -drive if=none,id=stick,format=raw,file=daphnis-0.1.0-x86_64.img \
  -device usb-storage,drive=stick
```

The first boot asks for a name and a password and makes a Parent account. Every later boot ends at the login screen. Shut Down is under the power button in the Super plane; tap Super to open it. Accounts and files stay in the image file, so the same command starts it again.

To run it on a PC, write the image to a whole USB drive (this erases the drive), turn Secure Boot off and choose the drive's UEFI entry in the firmware's boot menu:

```sh
sudo dd if=daphnis-0.1.0-x86_64.img of=/dev/sdX bs=4M conv=fsync status=progress
```

## Build from source

Daphnis builds only with public cint 0.2.18 (commit `a14a03f3`). Bootstrap it from [cint v0.2.18](https://github.com/pennyleans/cint-public-build/releases/tag/v0.2.18), put `cint` on `PATH` and set `CINT_TOOLCHAIN` to the `cint.toolchain` beside it. On Debian or Ubuntu, with gcc, clang, musl-tools, QEMU, OVMF, grub-efi-amd64-bin, mtools, e2fsprogs, fdisk and python3:

```sh
make
tools/build-release-stick.sh daphnis-0.1.0-x86_64.img
```

`make` builds the kernels, programs and images. `tools/build-release-stick.sh` builds the release image from the committed tree. Builds write to `$TMPDIR`, never into the repository. `./check.sh` and the other `check-*.sh` scripts are the gates; `./check-release.sh` boots the release image.

## Documentation

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

The author sets the requirements, specifications and acceptance thresholds and reviews the results. Much of the code and documentation was written with AI coding agents. The tests and gate scripts are included, so results can be checked from source.

## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE) for third-party components.
