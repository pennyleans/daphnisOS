#!/usr/bin/env bash
# FS-3's two home boots. IMAGE INITRD DISK_COPY PREFIX [WATCHDOG]. No volume creation:
# the caller supplies a fresh ordinary image copy, never a host device.
set -u
image=$1 initrd=$2 disk=$3 h=$4 watchdog=${5:-120}
[ -f "$image" ] && [ -f "$initrd" ] && [ -f "$disk" ] || { echo "home-boots: inputs must be regular files" >&2; exit 1; }
mkdir -p "$(dirname "$h")"
rm -f -- "$h.2.blocked" "$h.1.txt.rc" "$h.2.txt.rc" "$h.1.keys.rc" "$h.2.keys.rc"
export POOL=max INITRD="$initrd" MEM=512 DISK="$disk"
ready='hdesk: bar desktop 1 |Console| var |/home| grants |DISK 1|'
boot() {
    local n=$1 limit=$2 t=$h.$1.txt typer driver_rc=0
    : > "$t"
    rm -f -- "$t.mon"
    if [ "$n" = 1 ]; then
        SENDKEYS_WAIT=$limit python3 tools/sendkeys.py "$t.mon" "$t" "$ready" \
            "$(python3 tools/check-home.py --keys 1)" \
            'hdesk: bar desktop 1 |Edit| var |/home|' "$(python3 tools/check-home.py --keys 2)" > "$h.$n.keys" 2>&1 &
    else
        SENDKEYS_WAIT=$limit python3 tools/sendkeys.py "$t.mon" "$t" "$ready" \
            "$(python3 tools/check-home.py --keys 3)" > "$h.$n.keys" 2>&1 &
    fi
    typer=$!
    QEMU_TIMEOUT=$limit MONITOR=$t.mon tools/run-qemu.sh "$image" "$t" > "$t.rc"
    # Do not leave a driver waiting on a guest that has already failed.
    if [ "$(cat "$t.rc")" != 33 ] || [ -s "$t.err" ]; then
        kill "$typer" 2>/dev/null || true
    fi
    wait "$typer" || driver_rc=$?
    echo "$driver_rc" > "$h.$n.keys.rc"
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && [ "$driver_rc" = 0 ]
}
if ! boot 1 "$((watchdog + 60))"; then
    echo "blocked: first guest or input driver failed; persistence-reading boot did not run" > "$h.2.blocked"
    exit 1
fi
boot 2 "$watchdog"
