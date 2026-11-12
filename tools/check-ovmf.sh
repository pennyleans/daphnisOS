#!/usr/bin/env bash
# HW-1 gate helper, called after check.sh's kernels are built. Never masks kernel bytes.
set -u
B=$1
unset DISK QEMU_EXTRA NET NET_FWD PLAY PLAY_DISPLAY KVM CPU SOUND
unset INITRD MODE POOL RTC APPEND
unset STDIN_FILE STDIN_AFTER MONITOR MEM QEMU_TIMEOUT SENDKEYS_WAIT QEMU_FOREGROUND
boot() { # cc flavor kind memory
    local cc=$1 fl=$2 kind=$3 mem=$4
    local t=$B/ovmf/$cc-$fl-$kind-$mem.txt
    local typer="" mon="" stdin=/dev/null after=""
    : > "$t"   # a rerun must never feed input against the preceding run's markers
    if [ "$fl" = user ]; then
        mon=$t.mon
        [ ${#mon} -le 100 ] || { echo "FAIL  ovmf: monitor path too long: $mon"; return 1; }
        rm -f -- "$mon"
        stdin=tests/image/stdin.txt
        after='Daphnis F: ring 3'
        mouse='mouse_move 10 -5,mouse_button 1,mouse_button 0,mouse_button 2,mouse_button 0'
        SENDKEYS_WAIT=90 python3 tools/sendkeys.py "$mon" "$t" \
            'daphnis: run mkeys pid 38 (device)' a,b,c 'daphnis: run mkeys pid 39 (device)' a,b,c \
            'daphnis: run mmouse pid 40 (device)' "$mouse" 'daphnis: run mmouse pid 41 (device)' "$mouse" > "$t.keys" 2>&1 &
        typer=$!
    fi
    FW=ovmf QEMU_FOREGROUND=1 MEM=$mem QEMU_TIMEOUT=90 STDIN_AFTER="$after" STDIN_FILE="$stdin" MONITOR="$mon" \
        tools/run-qemu.sh "$B/$cc-$fl/daphnis.$kind" "$t" > "$t.rc"
    local keys_rc=0
    [ -z "$typer" ] || wait "$typer" || keys_rc=$?
    if [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && [ "$keys_rc" = 0 ] \
        && python3 tools/fw-split.py "$t" "tests/expected/$fl.serial" > "$t.split" 2>&1 \
        && cmp -s "tests/expected/$fl.serial" "$t.kernel"; then
        echo "PASS  ovmf: $cc $fl $kind -m $mem, exit 33, kernel bytes equal golden, firmware retained"
    else
        echo "FAIL  ovmf: $cc $fl $kind -m $mem (see $t); stop, never lower memory to hide module placement"
        return 1
    fi
}
if [ "${2:-}" = --case ]; then
    boot "$3" "$4" "$5" "$6"
    exit $?
fi
mkdir -p "$B/ovmf"
ok=1
for cc in gcc clang; do
    tools/build-iso.sh "$B/$cc-hello/kernel.elf" "$B/$cc-hello/daphnis.iso" > "$B/ovmf/$cc-hello-iso.log" 2>&1 || ok=0
    tools/build-iso.sh "$B/$cc-user/kernel.elf" "$B/$cc-user/daphnis.iso" "$B/user/initrd.cpio" > "$B/ovmf/$cc-iso.log" 2>&1 || ok=0
    for fl in hello user; do
        module=()
        [ "$fl" = user ] && module=("$B/user/initrd.cpio")
        bash tools/build-esp.sh "$B/$cc-$fl/kernel.elf" "$B/$cc-$fl/daphnis.esp" "${module[@]}" > "$B/ovmf/$cc-$fl-esp.log" 2>&1 || ok=0
    done
done
if [ "$ok" = 1 ]; then
    echo "PASS  ovmf: built hello/user ESPs and user ISOs, gcc and clang"
else
    echo "FAIL  ovmf: image build (see $B/ovmf)"
    exit 1
fi
exec python3 tools/ovmf-jobs.py "$B"
