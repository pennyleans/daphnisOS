#!/usr/bin/env bash
# tools/build-esp.sh KERNEL ESP [MODULE]: a FAT32 EFI image, through mtools, no root.
# This writes an ordinary image file only, never a device. HW-8 wraps it in a GPT image.
# ARGS (HW-2): words for the kernel's boot line, as run-qemu.sh's APPEND (daphnis.acpi=1, daphnis.poweroff=1,
# daphnis.console=screen); letters, digits and . = , _ - only.
set -euo pipefail
kernel=$1 esp=$2 module=${3:-}
args=${ARGS:-}
case "$args" in *[!A-Za-z0-9.=,_\ -]*) echo "build-esp: ARGS holds a character GRUB would read" >&2; exit 1;; esac
for t in grub-mkstandalone mformat mmd mcopy truncate mktemp; do
    command -v "$t" >/dev/null || { echo "build-esp: $t not found" >&2; exit 1; }
done
[ -f "$kernel" ] && { [ -z "$module" ] || [ -f "$module" ]; } \
    || { echo "build-esp: kernel or module not a regular file" >&2; exit 1; }
esp=$(realpath -m "$esp")
log=$esp.log
for dest in "$esp" "$log"; do
    case "$(realpath -m "$dest")" in /dev/*|/dev) echo "build-esp: refuses /dev output" >&2; exit 1;; esac
    [ ! -e "$dest" ] || [ -f "$dest" ] || { echo "build-esp: output is not a regular file" >&2; exit 1; }
    for input in "$kernel" ${module:+"$module"}; do
        if [ "$(realpath -m "$dest")" = "$(realpath "$input")" ] || [ "$dest" -ef "$input" ]; then
            echo "build-esp: output aliases an input" >&2; exit 1
        fi
    done
done
if [ "$(realpath -m "$esp")" = "$(realpath -m "$log")" ] || [ "$esp" -ef "$log" ]; then
    echo "build-esp: image and log alias each other" >&2; exit 1
fi
mkdir -p "$(dirname "$esp")"
work=$(mktemp -d "$(dirname "$esp")/.esp-XXXXXXXX")
finish() {
    rc=$?
    trap - EXIT
    # Replace the directory entry, never follow a log symlink. Preserve failure diagnostics.
    if [ -f "$work/build.log" ]; then mv -T -- "$work/build.log" "$log" || rc=1; fi
    rm -rf -- "$work"
    exit "$rc"
}
trap finish EXIT
cat > "$work/grub.cfg" <<'CFG'
set timeout=0
set default=0
insmod efi_gop
insmod part_gpt
insmod part_msdos
insmod fat
set gfxpayload=keep
insmod regexp
insmod search_fs_file
# cmdpath names this EFI binary's device, never the running system's ESP.
if regexp --set=1:root '^\(([^)]+)\)' "$cmdpath"; then
    # HW-8: on a GPT stick GRUB may name the whole disk ((hd0)/EFI/BOOT); the ESP is then partition 1 of that disk.
    if [ ! -f "($root)/daphnis/kernel.elf" -a -f "($root,gpt1)/daphnis/kernel.elf" ]; then
        set root="$root,gpt1"
    fi
fi
# Ubuntu 24.04's GRUB under its OVMF leaves $cmdpath without a device on a bare ESP image: the ESP is then the one
# disk that holds Daphnis's kernel (the running system's ESP has no /daphnis).
if [ ! -f "($root)/daphnis/kernel.elf" ]; then
    search --no-floppy --file --set=root /daphnis/kernel.elf
fi
if [ ! -f "($root)/daphnis/kernel.elf" ]; then
    echo "Daphnis: cannot locate the boot ESP"
    halt
fi
menuentry "Daphnis" {
CFG
echo "    multiboot2 /daphnis/kernel.elf${args:+ $args}" >> "$work/grub.cfg"
if [ -n "$module" ]; then
    echo '    module2 /daphnis/initrd.cpio initrd' >> "$work/grub.cfg"
fi
printf '    boot\n}\n' >> "$work/grub.cfg"
grub-mkstandalone -O x86_64-efi --locales= --fonts= --themes= \
    -o "$work/BOOTX64.EFI" "boot/grub/grub.cfg=$work/grub.cfg" 2> "$work/build.log"
bytes=$(stat -Lc %s "$kernel")
[ -z "$module" ] || bytes=$((bytes + $(stat -Lc %s "$module")))
bytes=$((bytes + $(stat -c %s "$work/BOOTX64.EFI") + 8388608))
[ "$bytes" -ge 67108864 ] || bytes=67108864
truncate -s "$bytes" "$work/image"
export MTOOLSRC=/dev/null MTOOLS_SKIP_CHECK=1
mformat -i "$work/image" -F -c 1 -N 0 -v DAPHNIS ::
mmd -i "$work/image" ::/EFI ::/EFI/BOOT ::/daphnis
mcopy -i "$work/image" "$work/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$work/image" "$kernel" ::/daphnis/kernel.elf
[ -z "$module" ] || mcopy -i "$work/image" "$module" ::/daphnis/initrd.cpio
# The image is published last. On an earlier failure the previous image remains intact.
mv -T -- "$work/build.log" "$log"
mv -T -- "$work/image" "$esp"
