# Changelog

## 0.1.1 · 2026-11-13

A small desktop and build maintenance release following 0.1.0.

### Changes

- All ten desktop apps are pinned in the Super plane on first boot.
- Long previews wrap over as many as three lines. Pin names use the full cell.
- Network settings show the automatic QEMU configuration and report when no
  network device is available. Copy Details stays disabled while clipboard
  support is unfinished.

### Fixes

- Keyboard repeat controls respond to presses, dragging and arrow keys.
- Grants lists each windowed application once.
- Window contents and shadows respect rounded corners.
- The display resolution menu arrow lines up with the other menus.
- Editor modules link in a fixed order, and boot partition timestamps use UTC.
- Parallel agent builds wait for BearSSL. Release checks accept screenshot names
  containing spaces, and process and network checks recognize current records.

### Known limits

Daphnis remains experimental. QEMU is the tested virtual machine. The system
uses one processor core, has no SATA or NVMe driver, and does not encrypt its
volume. The sound volume slider responds to a press but not to dragging. Doom is
not included in the release image.

Some older test fixtures still need updating for current output. That work is
scheduled for 0.1.2; this release does not claim a fresh pass of every test suite.

### Verification

The release image passed `check-release.sh`: 44 checks, including eight firmware
boot checks. Those checks cover initial account setup, a saved file read back
after a second boot, and ACPI shutdown on both boots. The compiler was pinned to
cint 0.2.18. See the release's `CHECKS.txt` and `SHA256SUMS` for the image receipt.

## 0.1.0 · 2026-11-12

The first public release: a bootable x86-64 UEFI image with the desktop,
applications, user accounts, persistent files and the hosted cint toolchain.
See the [0.1.0 release](https://github.com/pennyleans/daphnisOS/releases/tag/v0.1.0)
for its original notes and downloads.
