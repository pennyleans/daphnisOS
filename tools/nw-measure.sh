#!/usr/bin/env bash
# tools/nw-measure.sh KERNEL BYTES DIR: NW-0 (docs/specs/2026-11-07-nw-window.md section 3). Boots KERNEL (a net
# flavor kernel32.elf) once with QEMU's user network and an image of sh (cish, DOS-3), grant, mtcp (as mt, so the
# kernel's own mtcp echo does not run) and a go.sh of two lines: `./mt -r 10.0.2.2 SRC`, BYTES down from
# `tools/nethost.py source`, then `./mt -s BYTES 10.0.2.2 SNK`, BYTES up to `tools/nethost.py sink`. Work files
# go in DIR. KERNEL `linux` runs the same two lines on this host against 127.0.0.1 instead (DU-1). Prints one
# line a direction,
#   nw: down BYTES bytes, guest T ticks, host S s, R KB/s
# R being BYTES / S / 1000 by the host's clock, and exits 0 when each direction moved BYTES bytes whole (the
# guest's and the host's SHA-256 agree and the connection is closed). Nothing is pinned: the numbers are the
# host's speed. KVM=1 runs QEMU under KVM (Arch, on l's go); QEMU_TIMEOUT (default 900 s) bounds the boot.
# NW_SRC and NW_SNK (default 50011 and 50012) are the host's ports.
set -u
cd "$(dirname "$0")/.."
[ $# = 3 ] || { echo "usage: tools/nw-measure.sh KERNEL BYTES DIR" >&2; exit 2; }
kernel=$1 bytes=$2 dir=$3
UB=${UB:?"set UB to the programs built from source at HEAD, the Makefile's O/ubin (RG-1)"}
src=${NW_SRC:-50011} snk=${NW_SNK:-50012}
wait_s=${QEMU_TIMEOUT:-900}
mkdir -p "$dir"
printf '# NW-0: down from nethost.py source, then up to nethost.py sink\n./mt -r 10.0.2.2 %s\n./mt -s %s 10.0.2.2 %s\n' \
    "$src" "$bytes" "$snk" > "$dir/go.sh"
SH_TOOLS=$(sed -n 's/^SH_TOOLS := //p' Makefile)   # the Makefile's SH_BIN: no image holds busybox (unit 4b)
python3 tools/mkcpio.py "$dir/nw.cpio" sh="$UB"/cish bin/ bin/sh="$UB"/cish \
    $(for t in $SH_TOOLS; do printf 'bin/%s=%s/%s ' "$t" "$UB" "$t"; done) grant="$UB"/grant mt="$UB"/mtcp go.sh="$dir/go.sh"
python3 tools/nethost.py source "$src" "$bytes" "$wait_s" > "$dir/source.out" 2> "$dir/source.err" &
sp=$!
python3 tools/nethost.py sink "$snk" "$wait_s" > "$dir/sink.out" 2> "$dir/sink.err" &
kp=$!
for _ in $(seq 50); do
    grep -q '^nethost: source on' "$dir/source.out" 2>/dev/null && grep -q '^nethost: sink on' "$dir/sink.out" 2>/dev/null && break
    sleep 0.1
done
t=$dir/serial.txt
ok=0
if [ "$kernel" = linux ]; then
    { "$UB"/mtcp -r 127.0.0.1 "$src" && "$UB"/mtcp -s "$bytes" 127.0.0.1 "$snk"; } > "$t" 2> "$t.err" || ok=1
    wait "$sp" "$kp" 2>/dev/null
else
    rc=$(QEMU_TIMEOUT=$wait_s NET=user INITRD="$dir/nw.cpio" tools/run-qemu.sh "$kernel" "$t")
    wait "$sp" "$kp" 2>/dev/null
    [ "$rc" = 33 ] && [ ! -s "$t.err" ] && grep -qx 'daphnis: net tcp connections open 0, resets sent 0' "$t" || ok=1
fi
# the guest's lines in go.sh's order: down, then up
mapfile -t g_n < <(sed -n 's/^mtcp: \([0-9]*\) bytes in \([0-9]*\) ticks$/\1 \2/p' "$t")
mapfile -t g_h < <(sed -n 's/^mtcp: sha256 //p' "$t")
i=0
for dirn in down up; do
    f=$dir/source.out; [ $dirn = up ] && f=$dir/sink.out
    h=$(sed -n 's/^nethost: [a-z]* \([0-9]*\) bytes in \([0-9.]*\) s, sha256 \([0-9a-f]*\)$/\1 \2 \3/p' "$f")
    read -r hn hs hh <<< "$h"
    read -r gn gt <<< "${g_n[$i]:-}"
    if [ -n "$h" ] && [ "${gn:-}" = "$bytes" ] && [ "$hn" = "$bytes" ] && [ "${g_h[$i]:-}" = "$hh" ]; then
        echo "nw: $dirn $bytes bytes, guest $gt ticks, host $hs s, $(python3 -c "print(round($bytes / $hs / 1000))") KB/s"
    else
        echo "nw: $dirn FAILED (guest '${g_n[$i]:-}' '${g_h[$i]:-}', host '$h'; see $dir)"
        ok=1
    fi
    i=$((i + 1))
done
exit $ok
