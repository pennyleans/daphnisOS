#!/usr/bin/env bash
# tools/build-iso.sh KERNEL ISO [MODULE]: a GRUB CD image that boots KERNEL (ELF64) through
# Multiboot 2, with MODULE (the user image, U1-5) as its first module when given. Needs
# grub-mkrescue, xorriso and GRUB's i386-pc modules. The menu has no timeout and GRUB writes only
# to the VGA console under BIOS. With x86_64-efi modules and mtools installed, grub-mkrescue
# also builds the UEFI boot image; HW-1 retains OVMF's serial prefix separately (ruling A).
set -euo pipefail
kernel=$1 iso=$2 module=${3:-}
root=$(dirname "$iso")/iso-root
rm -rf "$root"
mkdir -p "$root/boot/grub"
cp "$kernel" "$root/boot/kernel.elf"
modline=""
if [ -n "$module" ]; then
    cp "$module" "$root/boot/initrd.cpio"
    modline="    module2 /boot/initrd.cpio initrd"
fi
cat > "$root/boot/grub/grub.cfg" <<CFG
set timeout=0
set default=0
if [ "\$grub_platform" = efi ]; then
    insmod efi_gop
    set gfxpayload=keep
fi
menuentry "Daphnis" {
    multiboot2 /boot/kernel.elf
$modline
    boot
}
CFG
grub-mkrescue -o "$iso" "$root" 2> "$iso.log"
