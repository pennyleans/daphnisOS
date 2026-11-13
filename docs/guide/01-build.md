# 01 Build and boot from source

For the downloadable 0.1.1 image, see the [project README](../../README.md).
The commands below build development and test images from source on Linux.

## Build tools

| Tool | Use |
| --- | --- |
| cint v0.2.18 and its `cint.toolchain` | Compile `.ci` sources. See [toolchain.pin](../../toolchain.pin) for the public repository and exact revision. |
| GCC, Clang, GNU binutils, make, Python 3 | Build the kernel and assemble images. |
| musl-gcc | Build userspace programs. |
| QEMU (`qemu-system-x86_64`) | Boot the images. Interactive examples using `PLAY=1` require access to `/dev/kvm`. |
| GRUB, xorriso, mtools | Build the optional Multiboot 2 ISO. |
| e2fsprogs | Prepare and inspect ext2 volumes. |

Set `CINT_TOOLCHAIN` to the full path of the toolchain file when it is stored
separately from the `cint` executable. `make` uses `O` for its output directory,
which defaults to `daphnis-build` under `TMPDIR` or `/tmp`. Many helper scripts
accept `DAPHNIS_BUILD` and use their own default directories.

## Build and boot

```sh
B="${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-hello}"
make FLAVORS=hello COMPILERS=gcc O="$B"
tools/run-qemu.sh "$B/gcc-hello/kernel32.elf" "$B/hello.txt"
```

The runner uses QEMU software emulation without a display and saves the serial
output to `hello.txt`. A flavor selects a kernel entry point and, where needed,
an initial filesystem archive. See [The desktop](02-desk.md) for a graphical
boot with an archive and [Files](06-files.md) for a separate data volume.

## Checks

`./check.sh` runs the main regression suite. The top-level `check-*.sh` scripts
cover individual areas such as the desktop, shell, native utilities, storage,
and networking. Each script prints the checks it ran and its final result.
`python3 tools/check-image-apps.py` checks the release image recipe against
the desktop source. The full `check-release.sh` script also requires a release
ledger and decision records absent from this public source tree. See the
[project README](../../README.md) for the checks run on the 0.1.1 disk image.
