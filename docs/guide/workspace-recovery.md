# workspace recovery acceptance

`tools/check-workspace.py` is the scripted receipt that user work survives a reboot and a failed build, and that
acknowledged `sync` survives an abrupt stop of the machine. it is a standalone guest acceptance, separate from
`check-build.sh` and `check-disk.sh`, which establish pieces of it and are not substitutes.

it does not qualify editor ux, account isolation, encrypted snapshots, physical storage or unsynced crash
consistency. physical boot stays with the hw task.

## run

```sh
CINT_TOOLCHAIN=/path/to/cint.toolchain python3 -B tools/check-workspace.py --out /absolute/fresh-results
python3 -B -m unittest discover -s tests/workspace -p 'test_*.py'    # lightweight, no qemu
```

`--out` must be absolute, must not exist and must not be within the checkout. there is no option that takes an
existing disk or device. `CINT_TOOLCHAIN` must be set explicitly. kvm, qemu, `mke2fs`, `debugfs`, `e2fsck`, gcc,
clang, musl-gcc, cint and the toolchain pins of `toolchain.pin` are required; a missing one is reported as unrun
(exit 3), never as success. exit 0 is a pass, 1 a failure, 2 a refusal.

## what runs

the kernels are the existing disk flavor builds (`make FLAVORS=disk`) for gcc and clang. the initrd is a scratch
`tools/mkcpio.py` archive: cish as `/sh` and `/bin/sh`, the grant tool, the native core commands in `/bin` and
`/fx/expected.txt`. no busybox. each kernel gets its own volume from `tools/mkcintvol.sh`, which carries the bundled
toolchain at `/home/opt/cint`; the volume is never mounted on the host. no host compiler builds the tested program.

qemu is started by the test with kvm, no display, serial on stdout and the volume as virtio with
`cache=writeback` (flush respecting, never `cache=unsafe`).

| boot | script | what it does |
| --- | --- | --- |
| 1 | `tests/workspace/phase1.sh` | creates `/home/work/proj one` and a source by shell editing, keeps a backup, builds it with `/home/opt/cint/cib` into `out-1`, runs it, hashes, `sync`, ends normally |
| 2 | `tests/workspace/phase2.sh` | verifies the saved source, backup and `out-1` and runs it; appends a syntax error and builds `out-bad` (must exit nonzero, diagnostic kept); verifies backup and `out-1` and runs it again; restores the source from the backup, builds `out-2`, compares bytes and output with `out-1`; writes a final marker, `sync`, prints `ws-marker final-synced` and waits |
| stop | the test | after the marker, stops its own qemu child handle with no guest shutdown, then runs `e2fsck -fn` on the image (never a repair) |
| 3 | `tests/workspace/phase3.sh` | new qemu process on the same volume: final marker, source, backup, both executables and both runs; ends normally; `e2fsck -fn` again |

`cib` is run into a fresh output name every time. a failing build never writes over an earlier executable.
this is not the atomic build-job publication of the later framework.

## receipts

the guest prints `ws-step NAME STATUS`, `ws-hash LABEL SHA256 FILE`, `ws-marker NAME` and `ws-phase ...`. the host
parses only these and never writes a guest result. a run fails on a missing phase marker, a missing step, hash or
marker, a duplicate or malformed line, any nonzero native command other than `cib-bad`, a `cib-bad` that returns 0,
an empty compiler diagnostic, a wrong digest, a guest exit that is not 33 on boots 1 and 3, an exit of boot 2 before
the marker, or anything on qemu stderr. every required name is listed in `BOOT1`, `BOOT2`, `BOOT3` and every
comparison in `EQUAL`; comparing only what was produced fails.

## results directory

`summary.json` and `report.txt` (phases, compiler legs, abrupt stop, e2fsck), `logs/` (every command with its full
argv, cwd, status and time), per leg `bootN.in`, `bootN.serial`, `bootN.stderr`, `e2fsck-*.log`, the volume image
and its digests before and after each boot, the kernels, the initrd, the compiler executable and source identity,
and the sha256 of every file of the bundled toolchain. images stay in the results directory and are not committed.
