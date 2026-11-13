# 08 Audio

Daphnis provides `/dev/dsp` with a supported Intel HDA controller. The interface
takes signed 16-bit little-endian stereo PCM at 48 kHz. Opening the device
requires the Audio grant.

## Test in QEMU

`check-audio.sh` boots the `cish` test image with QEMU's Intel HDA device and
WAV backend. Its `atone` program plays a test signal with `grant audio ./atone`.
The check compares the captured WAV samples with the kernel's mix.

The development [Doom image](05-doom.md) also supports sound effects in QEMU.
`check-opl.sh` compares the separate OPL3 implementation with ymfm.
