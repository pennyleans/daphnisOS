# 08 Audio

| piece | state |
| --- | --- |
| device | Intel HDA (QEMU `intel-hda` with `hda-output`), driver in cint (`src/hda.ci`), the device is the clock |
| interface | `/dev/dsp`: S16LE, stereo, 48 kHz; up to 4 streams, mixed by the kernel each tick |
| access | `grant audio`; without it `open("/dev/dsp")` is `EACCES` |
| OPL3 | a YMF262 in cint (`user/ci/opl/opl3.ci`), ported from ymfm (BSD-3-Clause), equal to ymfm sample for sample |
| Doom sound effects | not yet (AU-5) |
| Doom music | not yet (AU-8: MIDI and MUS through the OPL3) |
| listening on a real speaker | not yet (AU-6) |

## Try it

`atone` plays a test signal. Under QEMU with the HDA device:

```
./grant audio ./atone
```

`check-audio.sh` boots the `cish` flavor with QEMU's `wav` backend and checks that the captured file is the kernel's
mix byte for byte.

Checked by `check-audio.sh` (21) and `check-opl.sh` (17: a 442,462-sample walk of every OPL3 feature against
ymfm).
