# 06 Files, home volume, and grants

The root filesystem is in RAM and resets at boot. The release image has an
ext2 volume mounted at `/home`. Each account has a directory under that mount,
such as `/home/alex`. Save files under `$HOME` in a signed-in session to keep
them across reboots.

## Development volumes

Development images that mount a volume use the same `/home` path. See
[Launch a persistent development desktop](desktop-launch.md) to attach an
existing ext2 image to QEMU.

## Grants

Grants control access to the persistent volume, network, and sound device.
The desktop manages grants for signed-in sessions. From a shell, `grant`
requests access for one command and its children, subject to the session's
permissions.

| Grant | Access |
| --- | --- |
| `disk` | Write under `/home`, subject to file permissions. |
| `net` | Open network sockets. |
| `audio` | Open the sound device `/dev/dsp` when available. |

`check-disk.sh` exercises ext2 reads, writes, and persistence in its test image.
