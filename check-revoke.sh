#!/usr/bin/env bash
# check-revoke.sh: the gate of GV-1b (docs/specs/2026-11-11-gv-revoke.md section 3, option A), on its own budget beside
# check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   A revoke cuts what a window already has open. O/ubin/mcut boots as the desk and prints one line a fact:
#   desknet (gcc and clang), with QEMU's user network, the host's HTTP server (tools/nethost.py http, 10.0.2.2:8080)
#   and the gate's volume on /home: a TCP connection in the middle of a download and a UDP socket are shut (a read
#   ends, a write fails, no new socket); a write and a truncate through an open file on /home fail and a read through
#   it still reads. Its lines are tests/expected/gv-mcut-desknet.out.
#   hdesk (gcc and clang), with an HDA device and the volume: a write and an ioctl on an open /dev/dsp fail, and the
#   file on /home as above. Its lines are tests/expected/gv-mcut-hdesk.out.
#   GV-1c (section 2b): O/ubin/mring boots as the desk in the desknet flavor (gcc and clang): a grant taken under
#   ring 0, a revoked one among them, is gone when ring 0 ends, by the desk's word or by the process's own grant
#   call, and a connection opened under ring 0 is shut. Its lines are tests/expected/gv-mring-desknet.out.
#   A QEMU without the user network SKIPs the desknet legs.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-revoke), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-revoke}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=240
gate_want=5      # the PASS lines before the last one: the build, hdesk on two compilers, the checkout, the time
net_pass=4       # and desknet on two compilers, with the user network: mcut, then mring (GV-1c)
HTTP=8080
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-revoke.sh: $*"; echo "RESULT: FAIL"; exit 1; }

command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy python3 cmp timeout git mke2fs debugfs; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in mcut mring; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
DOOM_ROOT=$(tools/doom/fetch.sh) || fail_exit "the Doom bundle the desk images hold could not be fetched"
export DOOM_ROOT

make -s -j"$(nproc)" O="$B" FLAVORS="desknet hdesk" CINT_TOOLCHAIN="$CINT_TOOLCHAIN" > "$B/make.log" 2>&1 \
    && line ok "build: the desknet and hdesk flavors for gcc and clang (make FLAVORS=\"desknet hdesk\")" \
    || { line bad "build: make FLAVORS=\"desknet hdesk\"" "see $B/make.log"; echo "RESULT: FAIL"; exit 1; }
tools/mkdisk.sh "$B/vol.img" > "$B/mkdisk.log" 2>&1 || fail_exit "tools/mkdisk.sh failed (see $B/mkdisk.log)"
python3 tools/mkcpio.py "$B/mcut-desknet.cpio" tiler=$UB/mcut
python3 tools/mkcpio.py "$B/mcut-hdesk.cpio" hdesk=$UB/mcut
python3 tools/mkcpio.py "$B/mring-desknet.cpio" tiler=$UB/mring

for cc in gcc clang; do
    m=$B/run/mcut-hdesk-$cc.txt
    cp "$B/vol.img" "$B/run/hdesk-$cc.img"
    rc=$(SOUND=none DISK=$B/run/hdesk-$cc.img MODE=640x480 QEMU_TIMEOUT=90 INITRD=$B/mcut-hdesk.cpio MEM=128 \
        tools/run-qemu.sh "$B/$cc-hdesk/kernel32.elf" "$m")
    [ "$rc" = 33 ] && [ "$(grep -a '^mcut:' "$m")" = "$(cat tests/expected/gv-mcut-hdesk.out)" ] \
        && line ok "cut hdesk $cc: mcut's lines are tests/expected/gv-mcut-hdesk.out (an open /dev/dsp and an open file on /home after a revoke)" \
        || line bad "cut hdesk $cc: mcut vs tests/expected/gv-mcut-hdesk.out" "status $rc, see $m"
done

if qemu-system-x86_64 -netdev help 2>/dev/null | grep -qx user; then
    python3 tools/nethost.py http "$HTTP" "$((BUDGET + 120))" > "$B/http.out" 2> "$B/http.err" &
    http_pid=$!
    for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q '^nethost: http on' "$B/http.out" 2>/dev/null && break; sleep 0.2; done
    grep -q '^nethost: http on' "$B/http.out" || fail_exit "the HTTP server did not bind port $HTTP (see $B/http.err)"
    for cc in gcc clang; do
        m=$B/run/mcut-desknet-$cc.txt
        cp "$B/vol.img" "$B/run/desknet-$cc.img"
        rc=$(NET=user DISK=$B/run/desknet-$cc.img MODE=640x480 QEMU_TIMEOUT=90 INITRD=$B/mcut-desknet.cpio MEM=128 \
            tools/run-qemu.sh "$B/$cc-desknet/kernel32.elf" "$m")
        [ "$rc" = 33 ] && [ "$(grep -a '^mcut:' "$m")" = "$(cat tests/expected/gv-mcut-desknet.out)" ] \
            && line ok "cut desknet $cc: mcut's lines are tests/expected/gv-mcut-desknet.out (a TCP download, a UDP socket and an open file on /home after a revoke)" \
            || line bad "cut desknet $cc: mcut vs tests/expected/gv-mcut-desknet.out" "status $rc, see $m"
    done
    for cc in gcc clang; do
        m=$B/run/mring-desknet-$cc.txt
        rc=$(NET=user MODE=640x480 QEMU_TIMEOUT=90 INITRD=$B/mring-desknet.cpio MEM=128 \
            tools/run-qemu.sh "$B/$cc-desknet/kernel32.elf" "$m")
        [ "$rc" = 33 ] && [ "$(grep -a '^mring:' "$m")" = "$(cat tests/expected/gv-mring-desknet.out)" ] \
            && line ok "ring 0 desknet $cc: mring's lines are tests/expected/gv-mring-desknet.out (a grant taken under ring 0 is gone when ring 0 ends, by the desk or by the process's own call)" \
            || line bad "ring 0 desknet $cc: mring vs tests/expected/gv-mring-desknet.out" "status $rc, see $m"
    done
    kill "$http_pid" 2>/dev/null; wait "$http_pid" 2>/dev/null
    net_ran=1
else
    net_ran=0
    skip "desknet: this QEMU has no user network (-netdev help lists no user); the socket legs did not run"
fi

[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
want_total=$((gate_want + net_ran * net_pass)); want_skips=$((1 - net_ran))
[ "$passes" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $net_pass with the network)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
