#!/usr/bin/env bash
# Qualify the shared encrypted serial sink with synthetic QEMU provisioning.
set -euo pipefail
cd "$(dirname "$0")"
: "${CINT_TOOLCHAIN:?set CINT_TOOLCHAIN}"
: "${DAPHNIS_BUILD:?set DAPHNIS_BUILD outside the repository}"
B=$(realpath -m "$DAPHNIS_BUILD")
case "$B/" in "$PWD/"*) echo 'build outputs must be outside the repository' >&2; exit 2 ;; esac
mkdir -p "$B"
export PYTHONDONTWRITEBYTECODE=1
trap 'echo "RESULT: FAIL (see build output)" >&2' ERR
echo "source $(git rev-parse HEAD)"
cint --version
python3 -B tests/capture/check_sink.py --build "$B/writer" --cint "$(command -v cint)" \
    --toolchain "$CINT_TOOLCHAIN" > "$B/writer.log" 2>&1
cat "$B/writer.log"
python3 -B tests/capture/check_replay.py --build "$B/replay" > "$B/replay.log" 2>&1
cat "$B/replay.log"
python3 -B tests/capture/check_key.py > "$B/key.log" 2>&1
cat "$B/key.log"
python3 -B tests/capture/check_input.py --out "$B/input" --cint "$(command -v cint)" \
    --toolchain "$CINT_TOOLCHAIN" > "$B/input.log" 2>&1
cat "$B/input.log"
python3 -B tests/capture/check_host.py --out "$B/host" --toolchain "$CINT_TOOLCHAIN" > "$B/host.log" 2>&1
cat "$B/host.log"
python3 -B tests/capture/check_boot.py --out "$B/boot" --toolchain "$CINT_TOOLCHAIN" > "$B/boot.log" 2>&1
cat "$B/boot.log"
make -s -j4 O="$B/normal" CAPTURE=0 FLAVORS='hello fault trap' all > "$B/build-normal.log" 2>&1
make -s -j4 O="$B/encrypted" CAPTURE=1 FLAVORS='hello fault trap captureports net' \
    SRC_captureports='src/portio.ci src/serial.ci tests/capture/ports.ci' \
    RTDEF_hello=-DBOOT_TRACE all > "$B/build-encrypted.log" 2>&1
if make -s O="$B/normal" CAPTURE=1 FLAVORS=hello all > "$B/mode-refusal.log" 2>&1; then
    echo 'capture mode change unexpectedly reused a build directory' >&2
    exit 1
fi
grep -q 'capture mode changed: use a fresh O directory' "$B/mode-refusal.log"
if make -s O="$B/encrypted" CAPTURE=0 FLAVORS=hello all > "$B/reverse-mode-refusal.log" 2>&1; then
    echo 'reverse capture mode change unexpectedly reused a build directory' >&2
    exit 1
fi
grep -q 'capture mode changed: use a fresh O directory' "$B/reverse-mode-refusal.log"
mkdir -p "$B/unmarked/gcc-hello"
touch "$B/unmarked/gcc-hello/kernel32.elf"
if make -s O="$B/unmarked" CAPTURE=1 FLAVORS=hello all > "$B/unmarked-refusal.log" 2>&1; then
    echo 'capture accepted an unmarked existing image' >&2
    exit 1
fi
grep -q 'capture mode unknown for existing images: use a fresh O directory' "$B/unmarked-refusal.log"
mkdir -p "$B/iso-only/gcc-hello"
touch "$B/iso-only/gcc-hello/daphnis.iso"
if make -s O="$B/iso-only" CAPTURE=1 FLAVORS=hello "$B/iso-only/gcc-hello/daphnis.iso" > "$B/iso-refusal.log" 2>&1; then
    echo 'capture accepted an unmarked existing ISO' >&2
    exit 1
fi
grep -q 'capture mode unknown for existing images: use a fresh O directory' "$B/iso-refusal.log"
echo 'pass: capture mode changes require a fresh build directory'
python3 -B tests/capture/check_guest.py --out "$B" > "$B/guest.log" 2>&1
cat "$B/guest.log"
for cc in gcc clang; do
    python3 -B tests/capture/check_tls.py --kernel "$B/encrypted/$cc-net/kernel32.elf" \
        --out "$B/tls-$cc" --key-file "$B/synthetic-recovery.key" > "$B/tls-$cc.log" 2>&1
    cat "$B/tls-$cc.log"
    for flavor in hello fault trap captureports net; do
        test ! -s "$B/encrypted/$cc-$flavor/emitted-c-warnings.log"
    done
done
echo 'RESULT: PASS'
