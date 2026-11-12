#!/usr/bin/env bash
# tools/deskplay-time.sh [WxH] [SECONDS]: DS D-FB (docs/specs/2026-11-07-ds-desk-speed.md section 2a), Doom's frame
# rate in a desk window with no one at the keyboard. Builds the deskplay flavor as tools/play.sh does, boots it with
# no display (KVM unless KVM=0) at WxH (default 1920x1080), lets Doom's title run SECONDS (default 60), then through
# the monitor closes Doom's menu, quits it (F10 y) and ends the shell, and reads Doom's own count from the desk's
# terminal dump: `doom: live frames F wall tics T`, the frames Doom drew in T tics of 1/35 s. Prints that line and
# the rate, 35 F / T. No volume is kept and no record is made. Outputs under $DAPHNIS_BUILD (default
# $TMPDIR/daphnis-build-dstime): time.txt (the serial transcript).
set -eu
cd "$(dirname "$0")/.."
mode=${1:-1920x1080}
secs=${2:-60}
case $mode in [0-9]*x[0-9]*) ;; *) echo "deskplay-time.sh: WxH, as 1920x1080"; exit 2;; esac
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-dstime}
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    echo "deskplay-time.sh: $B exists, is not empty and is not a Daphnis build directory (no .daphnis-build)"
    exit 2
fi
mkdir -p "$B"; : > "$B/.daphnis-build"
make -s -j"$(nproc)" O="$B" FLAVORS=deskplay COMPILERS=gcc
rm -f "$B/time.img"; tools/mkdisk.sh "$B/time.img" > /dev/null
python3 - "$B/mon.sock" "$B/time.txt" "$secs" <<'EOF' &
import socket, sys, time
sock, transcript, secs = sys.argv[1], sys.argv[2], float(sys.argv[3])
end = time.monotonic() + 600
def placed():
    try:
        return b"hdesk: place 1" in open(transcript, "rb").read()
    except OSError:
        return False
while time.monotonic() < end and not placed():
    time.sleep(0.5)
time.sleep(secs)
s = socket.socket(socket.AF_UNIX)
s.connect(sock)
for item in ["esc", "f10", "y"] + list("exit") + ["ret"]:
    s.sendall(("sendkey %s 100\n" % item).encode())
    time.sleep(3 if item in ("esc", "f10", "y") else 0.3)
EOF
keys=$!
KVM=${KVM:-1} RTC=1 CPU=${CPU:-max} QEMU_TIMEOUT=$((secs + 900)) POOL=max MEM=${MEM:-4096} MODE="$mode" \
    MONITOR="$B/mon.sock" INITRD="$B/deskplay/initrd.cpio" DISK="$B/time.img" \
    tools/run-qemu.sh "$B/gcc-deskplay/kernel32.elf" "$B/time.txt" > /dev/null
wait "$keys" 2> /dev/null || true
line=$(grep -ao 'doom: live frames [0-9]* wall tics [0-9]*' "$B/time.txt" | tail -1)
[ -n "$line" ] || { echo "deskplay-time.sh: no frames line in $B/time.txt"; exit 1; }
set -- $line
echo "$line"
echo "mode $mode: $(( 35 * $4 / ($7 > 0 ? $7 : 1) )) frames a second ($(( 350 * $4 / ($7 > 0 ? $7 : 1) % 10 )) tenths)"
