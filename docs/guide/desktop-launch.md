# Launching a persistent development desktop

`tools/desk.sh` starts a source-built desktop in QEMU using a kernel, initrd, and
existing volume image. For the downloadable disk image, see the
[project README](../../README.md).

## Prepare a development volume

Build the development desktop and create a scratch volume.

```
B="${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-hdesk}"
make FLAVORS=hdesk COMPILERS=gcc O="$B"
tools/mkcintvol.sh "$B/scratch.img" 256M
```

Reuse the same volume path on a later launch to keep files written under
`/home`.

## Launch

```
bash tools/desk.sh --kernel /abs/gcc-hdesk/kernel32.elf --initrd /abs/hdesk/initrd.cpio \
    --volume /abs/work.img --out /abs/runs/2026-11-09-a --mode 1920x1080 --accel kvm
```

all four of `--kernel`, `--initrd`, `--volume` and `--out` are required and absolute. `exit` in the desk's first
terminal ends the desk (qemu status 33).

| option | meaning |
| --- | --- |
| `--mode WxH` | framebuffer, 640x480 to 3840x2160, default 1920x1080 |
| `--accel kvm\|tcg` | default kvm; kvm that is not usable is an error, never a quiet switch to tcg |
| `--timeout N` | stop qemu after N seconds; default 0, no watchdog, for interactive use |
| `--headless` | no window (`-display none`), for automation; without it a display is required |
| `--monitor` | also open a qemu monitor as a unix socket at `DIR/monitor.sock` so a script can type keys (`tools/sendkeys.py`); default is no monitor |
| `--dry-run` | validate everything, print the full qemu command, start nothing, write nothing |
| `--qemu PATH` | the qemu to run instead of the one on PATH |
| `--kvm-device PATH` | the node checked for kvm, default /dev/kvm |

`--help` works without qemu, a compiler or a display.

fixed on every run: 4096 MiB, `daphnis.pool=max`, `daphnis.rtc=1`, `-cpu max`, no network, no audio, no monitor unless `--monitor` is given,
`-no-reboot`, the volume as a virtio drive with `cache=writeback` so the guest's flushes are honored. runner
variables from the environment (`QEMU_EXTRA`, `NET`, `SOUND`, `PLAY`, `MEM`, `DISK` and the rest) are cleared and
change nothing; only the options above do.

## what it refuses

before qemu starts, with exit status 2:

- a missing, unreadable, empty or nonregular kernel, initrd or volume; a volume that is not writable
- kernel, initrd and volume that are the same file (also through symlinks and hard links)
- an output directory that already exists (each boot gets a fresh one, so no receipt is overwritten), whose parent
  is missing, or that resolves inside this checkout (also through a symlink)
- a mode outside the supported range or not exactly `WxH`
- missing qemu, an unusable kvm device, or no display without `--headless`

host paths may hold spaces, quotes, dollar signs, semicolons and commas. each stays one argument, and a comma in the
volume path is doubled inside qemu's `-drive` option value, which is the one place qemu parses punctuation.

## the run directory

`DIR/receipt.json` is written before qemu starts (`state: started`) and replaced when it ends (`state: finished`),
so it exists even when qemu fails. it holds the launcher's source head and whether the tree was modified, the given
and resolved paths and sha-256 of the kernel, initrd and volume (and of the volume after the run), the settings, the
exact qemu argument list and command (the monitor socket, when asked for, is in both), start and end times, the raw qemu status, the result and the serial log's size
and hash. `serial.log` is the guest's serial stream. `qemu.err` is qemu's stderr; on a failed end its tail is
printed, so a display that failed to start shows qemu's own message.

| qemu status | result | launcher exit |
| --- | --- | --- |
| 33 | `guest-shutdown` (the desk ended itself) | 0 |
| timeout reached | `timeout` | 124 |
| 126, 127 | `launch-failed` | 1 |
| 0 | `qemu-exited-without-guest-shutdown` (for example the window was closed) | 1 |
| anything else | `abnormal-exit` | 1 |

the raw status is kept in the receipt. starting qemu is never reported as a successful boot; the result is only
what qemu returned.

## tests

```
bash -n tools/desk.sh
python3 -B -m unittest discover -s tests/tools -p test_desk_launcher.py
```

the tests use a fake qemu that records its arguments and never evaluates them. opening a window is not part of them.
