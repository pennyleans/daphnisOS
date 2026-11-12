#!/usr/bin/env bash
# tools/check-firmware-boot.sh [STICK]: the release image booted as a reader boots it under QEMU (RG-1; l 2026-11-12
# 17:16Z, the QEMU road first). Linux hosts only. With no STICK it builds one from HEAD with tools/build-release-stick.sh
# (the file export publishes); with STICK it boots that file. Either way it boots a copy, so STICK never changes, and
# records the file's SHA-256. No -kernel and nothing added: OVMF finds the stick's GRUB on the removable path
# (EFI/BOOT/BOOTX64.EFI) and GRUB boots the release line, daphnis.poweroff=1 among it. tools/check-firmware-boot.py
# drives two boots of the same file through the screen, each with a fresh OVMF variable store (no NVRAM passes between
# them): the Parent, a saved file and Shut Down, which must end QEMU on its own through ACPI S5; then the sign-in, the
# file read back and Shut Down again.
#   OVMF: $OVMF (a combined image) first; else the first CODE and VARS pair of the list below (CODE read-only, VARS a
#   fresh copy each boot); else the first combined image (a fresh copy each boot). None found: FAIL, never a pass.
#   FW_ACCEL: kvm or tcg; default kvm when /dev/kvm is readable and writable, else tcg. FW_MEM: -m, default 4G (the
#   memory target's minimum).
# The transcript prints the host, KVM or TCG, -m, the QEMU and OVMF versions, the image's SHA-256 and the exact QEMU
# command once (the release text's QEMU requirements are built from these lines), then one PASS or FAIL line a check
# and RESULT. Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-firmware-boot), cleared first.
set -u
cd "$(dirname "$0")/.."
B=$(realpath -m "${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-firmware-boot}")
export PYTHONDONTWRITEBYTECODE=1
fail_exit() { echo "FAIL  firmware boot: $*"; echo "RESULT: FAIL"; exit 1; }

[ "$(uname -s)" = Linux ] || fail_exit "Linux hosts only ($(uname -s))"
for t in qemu-system-x86_64 python3 sfdisk debugfs sha256sum; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"

# OVMF: the paths Debian and Ubuntu (ovmf), Fedora (edk2-ovmf) and Arch (edk2-ovmf) install.
code=- vars=
if [ -n "${OVMF:-}" ]; then
    [ -f "$OVMF" ] || fail_exit "OVMF=$OVMF is not a file"
    vars=$OVMF
else
    for pair in /usr/share/OVMF/OVMF_CODE_4M.fd:/usr/share/OVMF/OVMF_VARS_4M.fd \
        /usr/share/OVMF/OVMF_CODE.fd:/usr/share/OVMF/OVMF_VARS.fd \
        /usr/share/edk2/ovmf/OVMF_CODE.fd:/usr/share/edk2/ovmf/OVMF_VARS.fd \
        /usr/share/edk2/x64/OVMF_CODE.4m.fd:/usr/share/edk2/x64/OVMF_VARS.4m.fd; do
        [ -f "${pair%%:*}" ] && [ -f "${pair#*:}" ] && { code=${pair%%:*} vars=${pair#*:}; break; }
    done
    if [ -z "$vars" ]; then
        for fw in /usr/share/qemu/OVMF.fd /usr/share/ovmf/OVMF.fd /usr/share/edk2/x64/OVMF.4m.fd; do
            [ -f "$fw" ] && { vars=$fw; break; }
        done
    fi
fi
[ -n "$vars" ] || fail_exit "no OVMF: set OVMF, or install the distribution's package (ovmf, edk2-ovmf)"

accel=${FW_ACCEL:-}
[ -n "$accel" ] || { [ -r /dev/kvm ] && [ -w /dev/kvm ] && accel=kvm || accel=tcg; }
case $accel in kvm|tcg) ;; *) fail_exit "FW_ACCEL is kvm or tcg, not $accel";; esac
mem=${FW_MEM:-4G}

if [ $# -ge 1 ]; then
    stick=$(realpath "$1")
    [ -f "$stick" ] || fail_exit "$stick is not a file"
else
    stick=$B/stick.img
    DAPHNIS_BUILD=$B/build tools/build-release-stick.sh "$stick" > "$B/build.log" 2>&1 \
        || { tail -8 "$B/build.log"; fail_exit "tools/build-release-stick.sh made no stick (see $B/build.log)"; }
    grep '^build-release-stick: /' "$B/build.log"
fi
sum=$(sha256sum < "$stick" | cut -c1-64)
cp "$stick" "$B/run/stick.img"
[ "$(sha256sum < "$B/run/stick.img" | cut -c1-64)" = "$sum" ] || fail_exit "the copy of $stick differs from it"

ovmf_pkg=$( { dpkg-query -W -f='${Package} ${Version}' ovmf || rpm -q edk2-ovmf || pacman -Q edk2-ovmf; } 2>/dev/null | head -1)
. /etc/os-release 2>/dev/null
echo "host: ${PRETTY_NAME:-unknown}, $(uname -sr), $(uname -m)"
echo "accel: $( [ "$accel" = kvm ] && echo KVM || echo TCG )"
echo "memory: -m $mem"
echo "qemu: $(qemu-system-x86_64 --version | head -1)"
echo "ovmf: ${ovmf_pkg:-no package record}; $( [ "$code" = - ] && echo "$vars (combined)" || echo "$code with $vars" ), sha256 $(sha256sum < "${code/#-/$vars}" | cut -c1-64)"
echo "image: $stick, $(stat -c %s "$stick") bytes, sha256 $sum (booted as a copy)"
python3 tools/check-firmware-boot.py "$B/run/stick.img" "$code" "$vars" "$mem" "$accel" "$B/run" | tee "$B/drive.log"
rc=${PIPESTATUS[0]}
fails=$(grep -c '^FAIL  ' "$B/drive.log")
passes=$(grep -c '^PASS  ' "$B/drive.log")
if [ "$rc" = 0 ] && [ "$fails" = 0 ] && [ "$passes" = 8 ]; then
    echo "RESULT: PASS"
else
    echo "RESULT: FAIL ($fails failing lines, $passes of 8 PASS)"
    exit 1
fi
