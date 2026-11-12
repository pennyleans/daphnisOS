# Board: arch

Measured 2026-11-07 by HW-0 on the Arch box, read only, as a normal user (no cached sudo). Raw output
is in `docs/hw/arch/`, scrubbed. The running system booted 2026-11-01 under Linux 7.3.0-4-cachyos.

| Question | Answer | File |
|---|---|---|
| Boots UEFI or BIOS | UEFI 2.70, AMI 5.13 (BIOS A.30, 01/22/2019). `/sys/firmware/efi` present | `firmware-efi.txt`, `firmware-bootloader.txt`, `firmware-dmi.txt` |
| 64-bit EFI | Yes. `fw_platform_size` is 64, firmware arch x64 | `firmware-efi.txt`, `firmware-bootloader.txt` |
| Secure Boot | Disabled, Setup Mode on (`SecureBoot` = 0, `SetupMode` = 1). `mokutil` not installed, read from the efivars | `firmware-efi.txt` |
| Current boot loader | systemd-boot 262-1-arch, entry `cachyos-linux.efi`, ESP is partition 1 of the NVMe disk | `firmware-bootloader.txt` |
| [1 MiB, 128 MiB) usable RAM | **Not shown reserved.** One entry covers it: `0x100000-0x3fffffff` System RAM (1 MiB to 1 GiB) in the e820 map the kernel was handed, and no reserved range inside. The nearest reserved ranges are `0xa0000-0xfffff` (legacy VGA and ROM area, below 1 MiB) and `0x40000000-0x403fffff` (4 MiB at 1 GiB). The sysfs map and the kernel's `BIOS-e820` lines agree. The UEFI memory map at loader time was not read (needs root), and e820 counts boot-services memory as RAM, so this does not show whether firmware holds pages in the range while a loader runs | `memmap-sysfs.txt`, `memmap-dmesg.txt` |
| CPU | Intel Core i7-8700K, 6 cores, 12 threads, 1 socket, 39-bit physical address, x2APIC flag present | `cpu-ram.txt` |
| RAM | 32018 MiB reported by `free -m` (32 GiB installed) | `cpu-ram.txt` |
| PCIe ECAM (MCFG) | Present. ECAM at `0xe0000000`, 256 MiB, domain 0, buses 00-ff. The ECAM range is reserved in the e820 map | `acpi.txt`, `memmap-sysfs.txt` |
| 8042 | FADT `IAPC_BOOT_ARCH` not read (the table is root-only). Kernel: `i8042: PNP: No PS/2 controller found.` and no PS/2 input device registered. Whether the board has a PS/2 port cannot be told from software | `acpi.txt`, `legacy.txt`, `input.txt` |
| COM1 | Yes, in the firmware's ACPI description: `ttyS0 I/O:0x3f8 (irq = 4, base_baud = 115200) is a 16550A`. A second, `ttyS1` at `0x2f8`, irq 3. Whether either is wired to a header on the board cannot be told from software | `legacy.txt` |
| Display | The firmware surface was handed to `simple-framebuffer` (simpledrm) at boot, then relocated by the NVIDIA driver (firmware framebuffer in the GPU's `0xa0000000-0xa1ffffff` window). The boot log has no `efifb` line and no GOP address, size or mode line for the firmware surface. Derived from the relocation line: base `0xa1000000` (`0xa0000000` plus `0x1000000`), inside BAR3. Current console: `nvidia-drmdrmfb`, 1920x1080, 32 bits per pixel, stride 7680. Read as the mode GOP chose only with that caveat | `display.txt`, `legacy.txt` |
| GPU | NVIDIA GP104 GeForce GTX 1070 `10de:1b81` at 01:00.0 (BAR0 `a2000000` 16 MiB, BAR1 `90000000` 256 MiB prefetchable, BAR3 `a0000000` 32 MiB). No iGPU is listed (the CPU has one but no Intel display device appears in `lspci`) | `pci.txt`, `pci-vv.txt` |
| xHCI | Intel `8086:a36d` (300 series USB 3.1 xHCI) at 00:14.0, BAR0 `a3320000` 64 KiB, driver xhci_hcd. USB 2.0 side 16 ports, USB 3.0 side 10 ports | `pci.txt`, `pci-vv.txt`, `usb.txt` |
| Keyboard and mouse root ports | Both are the one 2.4 GHz dongle "I-CHIP YUNZII B75 PRO MAX 2.4G" (`056d:c077`) on bus 1 root port 5, no hub in the way. **Both of its HID interfaces report class 03, subclass 01, protocol 01 (boot keyboard); neither is 03:01:02 (boot mouse).** The kernel still registers a mouse from interface 1, from its report descriptor. Each interface has an interrupt IN endpoint (`0x81`, `0x82`) The only hub (Genesys `05e3:0608`) is on root port 13 and carries the Corsair H115i cooler, not an input device | `usb.txt`, `usb-hid.txt`, `input.txt` |
| Storage controllers | NVMe: Samsung `144d:a808` (SM981/PM981/PM983) at 02:00.0, BAR0 `a3200000` 16 KiB. AHCI: Intel `8086:a352` at 00:17.0, no disk attached. System disk: Samsung SSD 970 EVO Plus 1TB (nvme0n1, 931.5 GiB), ESP is partition 1, root is btrfs on partition 2 | `pci.txt`, `pci-vv.txt`, `storage.txt` |
| NIC | Intel I219-V `8086:15bc` at 00:1f.6, driver `e1000e`. It is the PCH I219 family named in ruling HW-4, not an 8254x or 82574. A second network device, Intel CNVi Wi-Fi `8086:a370`, uses iwlwifi | `pci.txt`, `pci-vv.txt` |
| HPET | Present. ACPI HPET table, base `0xfed00000`, 8 comparators, 64-bit, 24 MHz counter | `legacy.txt`, `acpi.txt` |
| IOAPIC count | 1 (`IOAPIC[0]`, id 2, address `0xfec00000`, GSI 0-119) | `legacy.txt`, `acpi.txt` |

## Not collected

- `dmidecode` (not installed) and the root-only commands: the DMI fields came from `/sys/class/dmi/id`
  instead, with serial and UUID files left unread.
- `dmesg` (restricted) was replaced with `journalctl -k -b -o cat` for this boot's kernel log.
- `mokutil`, `nvme` and `setserial` are not installed. Secure Boot was read from the efivars.
- The FADT (`FACP`) read and the capability lists in `lspci -vv` (both need root).

## Boot records

Every boot of Daphnis on this board: the commit, the firmware, what the screen showed and the result.

| date | commit | firmware | image | result |
| --- | --- | --- | --- | --- |
| 2026-11-10 18:30Z | the HW-8a stick branch (PR 265 on 263, 261, 259) | MSI A.30 (2019-01-22), UEFI, Secure Boot off | `tools/build-stick.sh` stick: the doom flavor (gcc, public cint v0.2.18), `daphnis.console=screen daphnis.acpi=1`, written by l to the USB stick, sha256 `1e4feae2...9703c` | **HW-8a pass.** GRUB, the machine block and `doom --sealed` on the GOP surface at 1920 x 1080 (stride 7680). On screen at the end: `chain 42cf14b2a5882df3750d3c434455d19879f4d496efdf74c15bd8739b01e68fa6`, equal to tic 350 of `tests/expected/doom.tics`; `doom: end tics 350`; `daphnis: done`. Photo by l in the project chat. No keyboard (no PS/2 port; HW-4 next) |
