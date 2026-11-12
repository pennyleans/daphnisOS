#!/usr/bin/env bash
# tools/build-stick.sh ESP VOLUME OUT: HW-8 (docs/specs/2026-11-06-hw-hardware.md, row HW-8), the board's stick as an
# image file: GPT, partition 1 the EFI system partition (tools/build-esp.sh's image), partition 2 the ext2 volume
# (tools/mkdisk.sh's) with an empty log/ directory added for HW-4m's daphnis.log. This writes an ordinary file only,
# never a device: l writes the image to a stick (a typed go, a write to a device on l's machine).
# VOLUME_GUID (HW-12): the volume partition's unique GUID, 8-4-4-4-12 hex digits, the one the stick's boot line names
# with daphnis.disk.write=GUID so src/usbms.ci writes it; by default the fixed GUID below. A fixed GUID keeps the
# image's bytes the same on every run.
set -euo pipefail
esp=$1 volume=$2 out=$3
guid=${VOLUME_GUID:-6461706E-6869-7300-0000-000000000005}
[[ $guid =~ ^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$ ]] && [ -n "${guid//[0-]/}" ] \
    || { echo "build-stick: VOLUME_GUID is not a GUID of 8-4-4-4-12 hex digits, not all zeros" >&2; exit 1; }
for t in sfdisk debugfs truncate dd stat; do
    command -v "$t" >/dev/null || { echo "build-stick: $t not found" >&2; exit 1; }
done
[ -f "$esp" ] && [ -f "$volume" ] || { echo "build-stick: ESP or volume not a regular file" >&2; exit 1; }
case "$(realpath -m "$out")" in /dev/*|/dev) echo "build-stick: refuses /dev output" >&2; exit 1;; esac
[ ! -e "$out" ] || [ -f "$out" ] || { echo "build-stick: output is not a regular file" >&2; exit 1; }
mib=1048576
esp_mib=$(( ($(stat -Lc %s "$esp") + mib - 1) / mib ))
vol_mib=$(( ($(stat -Lc %s "$volume") + mib - 1) / mib ))
total_mib=$((1 + esp_mib + vol_mib + 1))   # 1 MiB before the first partition, 1 MiB for the backup GPT
work=$(mktemp -d "$(dirname "$(realpath -m "$out")")/.stick-XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
cp -- "$volume" "$work/volume"
debugfs -w -R "mkdir log" "$work/volume" > /dev/null 2>&1
debugfs -R "stat log" "$work/volume" 2>/dev/null | grep -q "Type: directory" \
    || { echo "build-stick: log/ not made on the volume" >&2; exit 1; }
truncate -s $((total_mib * mib)) "$work/image"
sfdisk --quiet "$work/image" <<EOF
label: gpt
label-id: 6461706E-6869-7300-0000-000000000003
first-lba: 2048
start=2048, size=$((esp_mib * 2048)), type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=6461706E-6869-7300-0000-000000000004, name="DAPHNIS ESP"
start=$((2048 + esp_mib * 2048)), size=$((vol_mib * 2048)), type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$guid, name="DAPHNIS VOLUME"
EOF
dd if="$esp" of="$work/image" bs=$mib seek=1 conv=notrunc status=none
dd if="$work/volume" of="$work/image" bs=$mib seek=$((1 + esp_mib)) conv=notrunc status=none
mv -T -- "$work/image" "$out"
echo "build-stick: $out, $total_mib MiB: ESP $esp_mib MiB at 1 MiB, volume $vol_mib MiB at $((1 + esp_mib)) MiB"
