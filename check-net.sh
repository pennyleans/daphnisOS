#!/usr/bin/env bash
# check-net.sh: the gate of stage N (docs/specs/2026-11-05-n-net.md section 5), on its own budget beside
# check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   N-1: the net flavor (src/main_net.ci) on gcc and clang. Replays of the committed journals (tests/net/) are
#   pinned transcripts; a boot without a device says so. Live, with QEMU's user network: the kernel sends one
#   ARP request for the gateway and records the reply; tools/netjournal.py turns the transcript into
#   net.journal, and a boot with it in the image, on either compiler, gives the live transcript but for the
#   mode line. A QEMU without the user network SKIPs the live legs.
#   N-2: with mudp (O/ubin/mudp) in the image the kernel runs it against the host's UDP echo at 10.0.2.2:50007
#   (tools/nethost.py): eight datagrams and their replies through the stack in cint. The committed n2 journal
#   replays to a pinned transcript; live, each transcript's mudp lines are the ones the same binary prints on
#   this Linux host against the same echo at 127.0.0.1:50007 (DU-1).
#   N-3: with sh and mtcp in the image as well, sh runs `./fetch -o - | md5sum` of the host's 256 KiB file
#   (tools/nethost.py http, 10.0.2.2:8080) and mtcp echoes one TCP connection on port 7007, which tools/nethost.py
#   tcp makes through QEMU's forward from 127.0.0.1:50008. Live, the digest is the file's and Linux's, and the echo
#   comes back whole.
#   N-4: with grant in the image as well, mudp, sh and mtcp each run under `grant net` (GR-1 A), and then sh
#   runs fetch without it: its socket is -EACCES, `fetch: socket: Permission denied` as O/ubin/fetch prints it on
#   this Linux host when strace makes socket(2) fail with EACCES. The grant word is in each state digest.
#   BU-5 (docs/specs/2026-11-07-bu5-fetch.md section 4): sh's two runs are `./fetch -o -`. The committed n3 journal,
#   recorded with busybox wget, replays with fetch: every frame both ways and the MD5 are net-n3.serial's, so fetch
#   sends busybox wget's bytes and writes its body; tests/expected/net-fetch.serial is its transcript. Live, fetch
#   without the grant is refused; on this Linux host fetch writes the file's bytes and prints the refusal line of
#   every live transcript.
#   DOS-3 (unit 4b): no image holds busybox. sh is cish with the native tools of the Makefile's SH_TOOLS in /bin, so
#   every image that ran busybox-net's wget holds fetch. With CORE_ORACLE naming the busybox tarball, busybox-net's
#   wget, built by user/busybox/oracle.sh, is fetch's oracle on this Linux host as well (same bytes); without it,
#   the committed net-n3.serial and the file's MD5 stand in.
#   NW-0 (docs/specs/2026-11-07-nw-window.md section 3): tools/nw-measure.sh boots each net kernel with mtcp as
#   `mt` and a go.sh that runs `mt -r` against `tools/nethost.py source` and `mt -s` against `tools/nethost.py
#   sink`, NW_BYTES (default 256 KiB) each way; each direction must move the bytes whole (the guest's SHA-256 is the
#   host's), and the line carries the speed, guest ticks and host seconds. The same two runs of O/ubin/mtcp on
#   this Linux host move the same bytes (DU-1). Live only, nothing pinned: the numbers are the host's speed.
#   HW-7 (docs/specs/2026-11-06-hw-hardware.md row HW-7): the live boot again on QEMU's e1000 and e1000e, through
#   src/e1000.ci behind src/net.ci: the programs print what they print on virtio-net, and each run's journal replays
#   with no device to its live transcript but for the mode line.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-net), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-net}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=240   # 180 until HW-7; its eight legs add about 40 s (QEMU's e1000 holds received frames for 1 s after RCTL is written)
# the PASS lines before the last one, the live legs left out; they add live_pass, or one SKIP line instead
gate_want=17   # 18 until DOS-3 (unit 4b) took the n3 replays with busybox wget in the image; +1 HW-7 part 2, the hosted I219-V tests
live_pass=28   # 20, +8 HW-7 (e1000 and e1000e, gcc and clang: a live leg and its replay each)
PORT=50007   # the echo's port: mudp's second argument in src/main_net.ci
HTTP=8080    # the file's port (src/main_net.ci)
FWD=50008    # the host's end of the forward to mtcp's port 7007
SH_TOOLS=$(sed -n 's/^SH_TOOLS := //p' Makefile)
SH="sh=$UB/cish bin/ bin/sh=$UB/cish $(for t in $SH_TOOLS; do printf 'bin/%s=%s/%s ' "$t" "$UB" "$t"; done)"
NW_BYTES=${NW_BYTES:-262144}   # NW-0: the bytes of each direction of the speed legs
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-net.sh: $*"; echo "RESULT: FAIL"; exit 1; }
boot() { # image transcript [NET] [INITRD]: QEMU's exit status 33 and nothing on stderr
    local rc
    rc=$(NET=${3:-none} INITRD=${4:-} tools/run-qemu.sh "$1" "$2")
    [ "$rc" = 33 ] && [ ! -s "$2.err" ]
}

command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy python3 sha256sum cmp timeout git strace; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in cish $SH_TOOLS grant mudp mtcp fetch; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
BB=$(user/busybox/oracle.sh) || fail_exit "CORE_ORACLE: busybox did not build from $CORE_ORACLE (user/busybox/oracle.sh)"
echo "oracle: ${BB:-none (CORE_ORACLE unset: the committed goldens stand in)}"
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"

# 1. build
make -s -j"$(nproc)" O="$B" FLAVORS=net CINT_TOOLCHAIN="$CINT_TOOLCHAIN" > "$B/make.log" 2>&1 \
    && line ok "build: the net flavor for gcc and clang (make FLAVORS=net)" \
    || { line bad "build: make FLAVORS=net" "see $B/make.log"; echo "RESULT: FAIL"; exit 1; }

tools/audit-symbols.sh "$B" "gcc clang" net > "$B/audit.log" 2>&1
[ $? = 0 ] && [ "$(grep -c '^PASS' "$B/audit.log")" = 10 ] && ! grep -q '^FAIL' "$B/audit.log" \
    && line ok "K0: symbol audit of the net flavor (10 checks, 5 per build, gcc and clang)" || line bad "K0: symbol audit" "see $B/audit.log"
sed 's#  user/bin/#  #' tests/expected/core.sha256 | grep '  fetch$' | (cd "$UB" && sha256sum --quiet -c -) > "$B/pin.log" 2>&1 \
    && line ok "program: O/ubin/fetch is the bytes of its line in tests/expected/core.sha256 (DU-2; BU-5a)" || line bad "program: fetch pin" "see $B/pin.log"
CINT_TOOLCHAIN="$CINT_TOOLCHAIN" tests/hw/run-hosted.sh "$B" > "$B/i219.log" 2>&1 \
    && line ok "hosted: tests/hw/i219_test.ci, the I219-V's PCH layer against a model of the device (HW-7 part 2; $(tail -1 "$B/i219.log"))" \
    || line bad "hosted: tests/hw/i219_test.ci" "see $B/i219.log"

# 2. the committed journals: well formed, and their replays are the pinned transcripts
ok=1
for j in n1 n1-late n2 n3; do
    python3 tools/netjournal.py journal "tests/net/$j.journal" "$B/$j.journal" > /dev/null 2>> "$B/journal.log" \
        && cmp -s "tests/net/$j.journal" "$B/$j.journal" || ok=0
done
python3 tools/mkcpio.py "$B/n1.cpio" net.journal=tests/net/n1.journal
python3 tools/mkcpio.py "$B/n1-late.cpio" net.journal=tests/net/n1-late.journal
python3 tools/mkcpio.py "$B/n2.cpio" net.journal=tests/net/n2.journal mudp=$UB/mudp grant=$UB/grant
python3 tools/mkcpio.py "$B/live.cpio" mudp=$UB/mudp $SH mtcp=$UB/mtcp grant=$UB/grant fetch=$UB/fetch
python3 tools/mkcpio.py "$B/n3-fetch.cpio" net.journal=tests/net/n3.journal mudp=$UB/mudp $SH mtcp=$UB/mtcp grant=$UB/grant fetch=$UB/fetch
python3 tools/mkcpio.py "$B/live-fetch.cpio" $SH grant=$UB/grant fetch=$UB/fetch
# BU-5: a transcript but for the lines that name the program (the run lines, the refusal) and the state digests
frames() { grep -v -e '^daphnis: run ' -e '^daphnis: state ' -e ': socket: Permission denied$' "$1"; }
[ $ok = 1 ] && line ok "journals: tests/net/n1.journal, n1-late.journal, n2.journal and n3.journal are well-formed records (one net mac line, ticks in order, lengths that match)" \
            || line bad "journals" "see $B/journal.log"
for cc in gcc clang; do
    img=$B/$cc-net/kernel32.elf
    boot "$img" "$B/run/$cc-n1.txt" none "$B/n1.cpio" && cmp -s tests/expected/net.serial "$B/run/$cc-n1.txt" \
        && line ok "replay $cc: tests/net/n1.journal (the gateway's reply at tick 1) gives tests/expected/net.serial" \
        || line bad "replay $cc: n1" "status, stderr or the transcript differs from tests/expected/net.serial"
    boot "$img" "$B/run/$cc-n1-late.txt" none "$B/n1-late.cpio" && cmp -s tests/expected/net-late.serial "$B/run/$cc-n1-late.txt" \
        && line ok "replay $cc: tests/net/n1-late.journal (another frame at tick 2, the reply at tick 5) gives tests/expected/net-late.serial" \
        || line bad "replay $cc: n1-late" "status, stderr or the transcript differs from tests/expected/net-late.serial"
    boot "$img" "$B/run/$cc-n2.txt" none "$B/n2.cpio" && cmp -s tests/expected/net-n2.serial "$B/run/$cc-n2.txt" \
        && line ok "replay $cc: tests/net/n2.journal with mudp (eight datagrams to the echo, eight replies) gives tests/expected/net-n2.serial" \
        || line bad "replay $cc: n2" "status, stderr or the transcript differs from tests/expected/net-n2.serial"
    boot "$img" "$B/run/$cc-n3-fetch.txt" none "$B/n3-fetch.cpio" && cmp -s tests/expected/net-fetch.serial "$B/run/$cc-n3-fetch.txt" \
        && frames tests/expected/net-n3.serial | cmp -s - <(frames "$B/run/$cc-n3-fetch.txt") \
        && grep -qx 'fetch: socket: Permission denied' "$B/run/$cc-n3-fetch.txt" \
        && line ok "replay $cc: tests/net/n3.journal with fetch in place of wget gives tests/expected/net-fetch.serial: every frame both ways and the MD5 of net-n3.serial (BU-5)" \
        || line bad "replay $cc: n3 with fetch" "the transcript differs from tests/expected/net-fetch.serial, or its frames from net-n3.serial"
    boot "$img" "$B/run/$cc-nodev.txt" none \
        && printf 'Daphnis N: the network device\ndaphnis: net no device\nnet: done\n' | cmp -s - "$B/run/$cc-nodev.txt" \
        && line ok "no device $cc: without virtio-net and without a journal the kernel says so and ends" \
        || line bad "no device $cc" "see $B/run/$cc-nodev.txt"
done

# 3. live, with QEMU's user network
if qemu-system-x86_64 -netdev help 2>/dev/null | grep -qx user; then
    python3 tools/nethost.py udp "$PORT" "$((BUDGET + 120))" > "$B/echo.out" 2> "$B/echo.err" &
    echo_pid=$!
    python3 tools/nethost.py http "$HTTP" "$((BUDGET + 120))" > "$B/http.out" 2> "$B/http.err" &
    http_pid=$!
    for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q '^nethost: udp echo on' "$B/echo.out" 2>/dev/null && grep -q '^nethost: http on' "$B/http.out" 2>/dev/null && break; sleep 0.2; done
    grep -q '^nethost: udp echo on' "$B/echo.out" || fail_exit "the UDP echo did not bind port $PORT (see $B/echo.err)"
    grep -q '^nethost: http on' "$B/http.out" || fail_exit "the HTTP server did not bind port $HTTP (see $B/http.err)"
    md5=$(python3 tools/nethost.py md5)
    for cc in gcc clang; do
        t=$B/run/$cc-live.txt
        python3 tools/nethost.py tcp "$FWD" "$t" "mtcp: listening" > "$t.client" 2>&1 &
        client=$!
        export NET_FWD="tcp:127.0.0.1:$FWD-:7007"
        boot "$B/$cc-net/kernel32.elf" "$t" user "$B/live.cpio" \
            && [ "$(grep -c '^net mac ' "$t")" = 1 ] \
            && grep -qx "net tx 42 sha256 $(sed -n 's/^net tx 42 sha256 //p' tests/expected/net.serial)" "$t" \
            && grep -q '^net rx ' "$t" && grep -q '^daphnis: net gateway 10.0.2.2 is at ' "$t" \
            && grep -qx 'mudp: 8 of 8 replies equal their datagrams' "$t" \
            && grep -qx "$md5" "$t" && wait "$client" && grep -qx 'nethost: tcp sent 10000, got back 10000, equal' "$t.client" \
            && grep -qx 'daphnis: net tcp connections open 0, resets sent 0' "$t" \
            && grep -qx 'fetch: socket: Permission denied' "$t" \
            && python3 tools/netjournal.py journal "$t" "$B/$cc-live.journal" > /dev/null \
            && python3 tools/mkcpio.py "$B/$cc-live.cpio" mudp=$UB/mudp $SH mtcp=$UB/mtcp grant=$UB/grant fetch=$UB/fetch net.journal="$B/$cc-live.journal" \
            && line ok "live $cc: the boot ARP; mudp's eight replies; fetch | md5sum prints the file's MD5; mtcp's echo whole; fetch without the net grant refused; every connection closed; journaled" \
            || line bad "live $cc" "see $t"
    done
    # HW-7 (docs/specs/2026-11-06-hw-hardware.md row HW-7): the same boot on QEMU's e1000 (82540EM) and e1000e
    # (82574L) through src/e1000.ci. What the programs print is what they print on virtio-net; the journal of each
    # run replays, no device attached, to the live transcript but for the mode line.
    for model in e1000 e1000e; do
        for cc in gcc clang; do
            t=$B/run/$cc-live-$model.txt
            python3 tools/nethost.py tcp "$FWD" "$t" "mtcp: listening" > "$t.client" 2>&1 &
            client=$!
            NET_MODEL=$model boot "$B/$cc-net/kernel32.elf" "$t" user "$B/live.cpio" \
                && grep -qx 'daphnis: net e1000, live' "$t" && [ "$(grep -c '^net mac ' "$t")" = 1 ] \
                && grep -q '^daphnis: net gateway 10.0.2.2 is at ' "$t" \
                && grep -qx "$md5" "$t" && wait "$client" && grep -qx 'nethost: tcp sent 10000, got back 10000, equal' "$t.client" \
                && grep -qx 'daphnis: net tcp connections open 0, resets sent 0' "$t" \
                && grep -e '^mudp: ' -e '^mtcp: ' -e '^fetch: ' "$t" | cmp -s - <(grep -e '^mudp: ' -e '^mtcp: ' -e '^fetch: ' "$B/run/$cc-live.txt") \
                && python3 tools/netjournal.py journal "$t" "$B/$cc-live-$model.journal" > /dev/null \
                && python3 tools/mkcpio.py "$B/$cc-live-$model.cpio" mudp=$UB/mudp $SH mtcp=$UB/mtcp grant=$UB/grant fetch=$UB/fetch net.journal="$B/$cc-live-$model.journal" \
                && line ok "live $cc on $model (HW-7): the boot ARP answered; the MD5, the echo and the mudp, mtcp and fetch lines of the virtio-net run; every connection closed; journaled" \
                || line bad "live $cc on $model" "see $t"
            boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-replay-$model.txt" none "$B/$cc-live-$model.cpio" \
                && python3 tools/netjournal.py same "$t" "$B/run/$cc-replay-$model.txt" > /dev/null \
                && line ok "replay $cc of its $model journal (HW-7): the live transcript but for the mode line, no device attached" \
                || line bad "replay $cc of its $model journal" "see $B/run/$cc-replay-$model.txt"
        done
    done
    for cc in gcc clang; do
        t=$B/run/$cc-live-fetch.txt
        boot "$B/$cc-net/kernel32.elf" "$t" user "$B/live-fetch.cpio" \
            && grep -qx "$md5" "$t" && grep -qx 'fetch: socket: Permission denied' "$t" \
            && grep -qx 'daphnis: net tcp connections open 0, resets sent 0' "$t" \
            && python3 tools/netjournal.py journal "$t" "$B/$cc-live-fetch.journal" > /dev/null \
            && python3 tools/mkcpio.py "$B/$cc-live-fetch.cpio" $SH grant=$UB/grant fetch=$UB/fetch net.journal="$B/$cc-live-fetch.journal" \
            && line ok "live $cc: fetch | md5sum under the net grant prints the file's MD5; fetch without it refused; every connection closed; journaled (BU-5)" \
            || line bad "live $cc: fetch" "see $t"
    done
    for cc in gcc clang; do
        for from in gcc clang; do
            boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-replay-fetch-$from.txt" none "$B/$from-live-fetch.cpio" \
                && python3 tools/netjournal.py same "$B/run/$from-live-fetch.txt" "$B/run/$cc-replay-fetch-$from.txt" > /dev/null \
                && line ok "replay $cc of the $from live fetch journal: the live transcript but for the mode line (BU-5)" \
                || line bad "replay $cc of the $from live fetch journal" "see $B/run/$cc-replay-fetch-$from.txt"
        done
    done
    for cc in gcc clang; do
        for from in gcc clang; do
            boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-replay-$from.txt" none "$B/$from-live.cpio" \
                && python3 tools/netjournal.py same "$B/run/$from-live.txt" "$B/run/$cc-replay-$from.txt" > /dev/null \
                && line ok "replay $cc of the $from live journal: the live transcript but for the mode line, no device attached" \
                || line bad "replay $cc of the $from live journal" "see $B/run/$cc-replay-$from.txt"
        done
    done
    for cc in gcc clang linux; do
        img=$B/$cc-net/kernel32.elf who="live $cc"
        [ $cc = linux ] && img=linux who="oracle: O/ubin/mtcp on this Linux host"
        UB=$UB tools/nw-measure.sh "$img" "$NW_BYTES" "$B/nw-$cc" > "$B/run/$cc-nw.txt" 2>&1 \
            && line ok "$who: NW-0 $NW_BYTES bytes down from nethost.py source (mtcp -r) and up to nethost.py sink (mtcp -s), whole both ways; $(tr '\n' ';' < "$B/run/$cc-nw.txt" | sed 's/;$//; s/;/; /g')" \
            || line bad "$who: NW-0 speed legs" "see $B/run/$cc-nw.txt"
    done
    $UB/mudp 127.0.0.1 "$PORT" > "$B/run/linux-mudp.txt" 2>&1
    ok=1
    for cc in gcc clang; do
        grep '^mudp: ' "$B/run/$cc-live.txt" | cmp -s - "$B/run/linux-mudp.txt" || ok=0
    done
    [ $ok = 1 ] && [ "$(wc -l < "$B/run/linux-mudp.txt")" = 9 ] \
        && line ok "oracle: O/ubin/mudp on this Linux host against the same echo prints the mudp lines of both live transcripts (DU-1)" \
        || line bad "oracle: Linux mudp" "see $B/run/linux-mudp.txt"
    ok=1
    env -i PATH="$UB" "$UB"/cish -c "fetch -o - http://127.0.0.1:$HTTP/f | md5sum" > "$B/run/linux-fetch-md5.txt" 2>&1
    [ "$(cat "$B/run/linux-fetch-md5.txt")" = "$md5" ] || ok=0
    $UB/mtcp 7007 > "$B/run/linux-mtcp.txt" 2>&1 &
    mt=$!
    python3 tools/nethost.py tcp 7007 "$B/run/linux-mtcp.txt" "mtcp: listening" > "$B/run/linux-mtcp.client" 2>&1 || ok=0
    wait "$mt" || ok=0
    for cc in gcc clang; do
        grep '^mtcp: ' "$B/run/$cc-live.txt" | cmp -s - "$B/run/linux-mtcp.txt" || ok=0
    done
    [ $ok = 1 ] \
        && line ok "oracle: on this Linux host cish's fetch | md5sum (O/ubin) prints the same MD5 ($md5), and O/ubin/mtcp prints the mtcp lines of both live transcripts for the same client" \
        || line bad "oracle: Linux fetch | md5sum and mtcp" "see $B/run/linux-fetch-md5.txt, linux-mtcp.txt"
    strace -f -q -o /dev/null -e trace=socket -e inject=socket:error=EACCES \
        $UB/fetch -o - "http://127.0.0.1:$HTTP/f" > "$B/run/linux-fetch-eacces.txt" 2>&1
    ok=$?
    for cc in gcc clang; do
        grep -qxF "$(cat "$B/run/linux-fetch-eacces.txt")" "$B/run/$cc-live.txt" || ok=9
    done
    [ $ok = 1 ] && [ "$(wc -l < "$B/run/linux-fetch-eacces.txt")" = 1 ] \
        && line ok "oracle: on this Linux host, with socket(2) failing EACCES (strace), O/ubin/fetch prints the line of both live transcripts and ends with status 1 (N-4)" \
        || line bad "oracle: Linux fetch with EACCES, live" "see $B/run/linux-fetch-eacces.txt"
    # DOS-3: with the oracle, fetch's bytes are busybox-net wget's; without it, the file's MD5 stands in
    $UB/fetch -o - "http://127.0.0.1:$HTTP/f" > "$B/run/linux-fetch.bin" 2> "$B/run/linux-fetch.err" \
        && { [ -z "$BB" ] || { "$BB/busybox-net" wget -q -O - "http://127.0.0.1:$HTTP/f" > "$B/run/linux-wget.bin" \
            && cmp -s "$B/run/linux-fetch.bin" "$B/run/linux-wget.bin"; }; } \
        && [ ! -s "$B/run/linux-fetch.err" ] && [ "$(md5sum < "$B/run/linux-fetch.bin")" = "$md5" ] \
        && line ok "oracle: on this Linux host O/ubin/fetch -o - writes the file's bytes$([ -n "$BB" ] && echo ", busybox-net wget -q -O -'s"), silent, status 0 (BU-5, DU-1)" \
        || line bad "oracle: Linux fetch" "see $B/run/linux-fetch.bin, linux-fetch.err"
    strace -f -q -o /dev/null -e trace=socket -e inject=socket:error=EACCES \
        $UB/fetch -o - "http://127.0.0.1:$HTTP/f" > "$B/run/linux-fetch-eacces.txt" 2>&1
    ok=$?
    for cc in gcc clang; do
        grep -qxF "$(cat "$B/run/linux-fetch-eacces.txt")" "$B/run/$cc-live-fetch.txt" || ok=9
    done
    [ $ok = 1 ] && [ "$(cat "$B/run/linux-fetch-eacces.txt")" = 'fetch: socket: Permission denied' ] \
        && line ok "oracle: on this Linux host, with socket(2) failing EACCES (strace), O/ubin/fetch prints the refusal line of both live fetch transcripts and ends with status 1 (BU-5)" \
        || line bad "oracle: Linux fetch with EACCES" "see $B/run/linux-fetch-eacces.txt"
    kill "$echo_pid" "$http_pid" 2>/dev/null; wait "$echo_pid" "$http_pid" 2>/dev/null
    live_ran=1
else
    live_ran=0
    skip "live: this QEMU has no user network (-netdev help lists no user); the live legs did not run, the replays did"
fi

# 4. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
want_total=$((gate_want + live_ran * live_pass)); want_skips=$((1 - live_ran))
[ "$passes" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $live_pass with the live legs)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
