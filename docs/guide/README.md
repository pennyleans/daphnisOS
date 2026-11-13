# Daphnis guide

Daphnis is an experimental x86-64 operating system. Start with the
[project README](../../README.md) for the 0.1.1 disk image and boot instructions.
The image includes the desktop, cish, native command-line utilities, ced, and
other desktop apps. It boots through UEFI and has a writable home volume.
See the [hardware notes](../hw/README.md) for board-specific information.

## Using Daphnis

- [Desktop and shortcuts](02-desk.md)
- [cish shell](03-cish.md)
- [ced text editor](04-ced.md)
- [Files, home volume, and grants](06-files.md)
- [Networking](07-network.md)

## Building and testing

These walkthroughs use source builds or test images. Each page names the image
or script it needs.

- [Build and boot from source](01-build.md)
- [Launch a development desktop with a persistent volume](desktop-launch.md)
- [Run the workspace recovery checks](workspace-recovery.md)
- [Play Doom in the separate development image](05-doom.md)
- [Test audio and OPL3](08-audio.md)
- [Try the network and API client demos](09-agent.md)
- [Create a capture recovery key](capture-keys.md)
- [Record and replay a capture test image](capture-run.md)
