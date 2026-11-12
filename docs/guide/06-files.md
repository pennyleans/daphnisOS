# 06 Files, the volume, grants

## The root

The image's files sit at their cpio paths in a RAM filesystem (`/etc/motd`, `/bin/ls`). Programs make, move and
remove files and directories there; every process has a working directory. Linux's file calls work as a static
musl program makes them (`open`, `openat` and the other `*at` calls, `read`, `write`, `lseek`, `stat`,
`getdents64`, `rename`, `mkdir`, `rmdir`, `unlink`, `dup`, `fcntl`, `poll`). 16 descriptors a process. The root is
gone at power off.

A file made inside Daphnis holds at most 64 KiB today.

## `/disk`

Boot with a raw ext2 volume and it mounts at `/disk` (virtio block):

```
tools/mkdisk.sh $B/play.img                 # a 4 MiB test volume, pinned digest
DISK=$B/play.img tools/run-qemu.sh ...      # any flavor that mounts it (hdesk, deskplay, disk)
```

Any ext2 volume with 4 KiB blocks works; `mke2fs` and `debugfs` on the host read and write the same bytes. Reads need
nothing. Writes need the grant.

## Grants

A process starts with no grants. `grant` sets them for one command and its children:

```
grant disk ced /disk/notes.txt
grant net wget http://10.0.2.2:8000/file
grant disk,audio ./doom ...
```

| grant | without it |
| --- | --- |
| `disk` | a write under `/disk` fails with `EACCES` |
| `net` | `socket` fails with `EACCES` |
| `audio` | opening `/dev/dsp` fails with `EACCES` |

The grant word is part of the process's canonical state, inherited by `fork`. The desk rings a window whose
foreground holds `disk` (sienna) or `net` (ochre).

Checked by `check.sh` (files, directories, processes, pipes against Linux) and `check-disk.sh` (16: ext2 read and
write, a second boot sees the first boot's writes, the grant's refusal, the Doom chain unchanged with a volume).
