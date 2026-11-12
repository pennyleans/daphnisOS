#!/usr/bin/env bash
# check-agent.sh: the gate of stage A (docs/specs/2026-11-06-a-agent.md section 5), on its own budget beside
# check-net.sh. One PASS or FAIL line per check; exit status 1 if any FAIL. Each unit boots the net flavor
# (src/main_net.ci) with an image of sh, grant and the unit's program; sh pipes two lines into the
# program under `grant net`, and the program speaks to a host end that answers each turn with a fixed function of
# it, so nothing leaves the host:
#   A-0: talk (`talk 10.0.2.2 7070`) and tools/claudebridge.py --fake, the day-one bridge.
#   A-1: agent (`agent 10.0.2.2 8080`) and tools/apihost.py, the mock Messages API: two turns of a conversation
#   over HTTP/1.1, the event stream chunked, its text with escapes and UTF-8; the mock checks each request and
#   answers 400 to one the API would refuse.
#   A-2: agent by name: the image's go.sh (tests/agent/a2.sh) runs `agent -d 10.0.2.2:5353 api.mock 8080`, and the
#   mock answers the DNS query too (a CNAME, then the A record: 10.0.2.2 for Daphnis, 127.0.0.1 for Linux).
#   A-4: the A-2 session over TLS 1.2: go.sh (tests/agent/a4.sh) runs `agent -d 10.0.2.2:5353 -t api.mock 8443`,
#   and the mock (apihost.py --cert tests/tls/api.mock.pem) speaks TLS 1.2 only with a certificate by the mock root
#   (user/tls/roots/mock.pem). The handshake draws on getrandom, so the live legs run under -cpu max and the replays
#   take rng.journal beside net.journal (tests/net/a4-rng.journal committed). On this Linux host the same binary
#   refuses a certificate out of its dates and one by a root it does not hold, each with BearSSL's error; in
#   Daphnis, live, it refuses the first, and without an entropy source (no -cpu max) it opens no session at all.
#   A-5: tools: go.sh (tests/agent/a5.sh) runs `agent -x 10.0.2.2 8080` and answers y, y, y, y, n, y to the
#   mock's six calls (sh, write_file, edit_file and read_file on note.txt, write_file of refused.txt, sh removing
#   note.txt), then a plain turn; the mock checks every tool_result against its tool_use. On Linux the oracle runs
#   in an empty directory of its own, which it leaves empty.
# The journal goes last in a replay's image, so every other member keeps the inode it has in the live image (a2's
# go.sh is open in sh while the state digest is taken, and the digest holds its inode).
# For each: the committed journal (tests/net/UNIT.journal) replays to a pinned transcript on gcc and clang; live,
# on gcc and clang, the program's lines are the ones the same binary prints on this Linux host against the same
# host end (DU-1), and each live journal replays on both compilers.
#   A-3: mrng, with no network: getrandom of 64 bytes and the CLOCK_REALTIME seconds. The committed rng journal
#   (tests/net/a3.journal: the `rtc` line and the draw) replays to a pinned transcript; with neither a journal
#   nor RDRAND, getrandom is -ENOSYS and the date the fixed epoch (a pinned transcript); live under QEMU's
#   -cpu max (RDRAND), the draw is recorded, mrng prints the record's bytes and the `rtc` seconds, and each live
#   rng journal replays on both compilers. On Linux mrng draws 64 bytes (DU-1: the shape; the bytes are random).
#   K-6b: the date alone. With daphnis.rtc=1 and no RDRAND, under QEMU's CMOS clock fixed at RTC_BASE, the boot
#   prints one `rtc S` line within a minute of it, mrng's realtime is S and getrandom stays -ENOSYS; masked (the
#   `rtc` line dropped; mrng's realtime and the state digest, which holds mrng's memory, as words) the transcript is
#   tests/expected/net-a3-none.serial, and its journal (the `rtc` line alone) replays on both compilers, state too.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-agent), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
here=$PWD
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-agent}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=180
gate_want=39   # the PASS lines before the last one, the live legs left out; they add live_pass, or one SKIP line
live_pass=37
UNITS="a0 a1 a2 a4 a5"
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-agent.sh: $*"; echo "RESULT: FAIL"; exit 1; }
boot() { # image transcript [NET] [INITRD] [CPU]: QEMU's exit status 33 and nothing on stderr
    local rc
    rc=$(CPU=${5:-} NET=${3:-none} INITRD=${4:-} QEMU_TIMEOUT=60 tools/run-qemu.sh "$1" "$2")
    [ "$rc" = 33 ] && [ ! -s "$2.err" ]
}
prog() { [ "$1" = a0 ] && echo talk || echo agent; }
port() { case $1 in a0) echo 7070 ;; a4) echo 8443 ;; *) echo 8080 ;; esac; }
cpu() { [ "$1" = a4 ] && echo max; }   # A-4: the handshake needs getrandom's source (RDRAND)
journals() { # unit net-journal: the journal members of a replay's image, last
    echo "net.journal=$2$([ "$1" = a4 ] && echo " rng.journal=${2%.journal}-rng.journal")"
}
first() { [ "$1" = a0 ] && echo "talk: connected" || echo "mock turn 1:"; }
last() { [ "$1" = a0 ] && echo "talk: 2 lines sent" || echo "agent: 2 turns"; }
# DOS-3 (unit 4b): sh is cish, and /bin holds it as sh and the native tools of the Makefile's SH_TOOLS (A-5's sh
# tool runs /bin/sh and rm); no image holds busybox
SH_TOOLS=$(sed -n 's/^SH_TOOLS := //p' Makefile)
SH="sh=$UB/cish bin/ bin/sh=$UB/cish $(for t in $SH_TOOLS; do printf 'bin/%s=%s/%s ' "$t" "$UB" "$t"; done)"
members() { echo "$SH $(prog "$1")=$UB/$(prog "$1") grant=$UB/grant$(case $1 in a2 | a4 | a5) echo " go.sh=tests/agent/$1.sh" ;; esac)"; }
linux_run() { # unit: the program on this Linux host against the host end, the same two lines
    if [ "$1" = a2 ]; then
        printf 'hello Daphnis\nbye\n' | $UB/agent -d 127.0.0.1:5353 api.mock 8080
    elif [ "$1" = a4 ]; then
        printf 'hello Daphnis\nbye\n' | $UB/agent -d 127.0.0.1:5353 -t api.mock 8443
    elif [ "$1" = a5 ]; then
        rm -rf "$B/run/a5-wd"; mkdir -p "$B/run/a5-wd"
        (cd "$B/run/a5-wd" && printf 'hello Daphnis\ny\ny\ny\ny\nn\ny\nbye\n' | "$UB/agent" -x 127.0.0.1 8080)
    else
        printf 'hello Daphnis\nbye\n' | "$UB/$(prog "$1")" 127.0.0.1 "$(port "$1")"
    fi
}
app_lines() { # transcript first last: the lines from the one holding first to the one holding last, the kernel's
    # net records taken out (a frame can arrive mid-line)
    python3 -c '
import re, sys
t = open(sys.argv[1], encoding="latin-1").read()
t = re.sub(r"(net tx \d+ sha256 [0-9a-f]{64}|net rx \d+ \d+ [0-9a-f]+|rng \d+ [0-9a-f]+)\n", "", t)
i, j = t.find(sys.argv[2]), t.find(sys.argv[3])
if i < 0 or j < 0:
    sys.exit(1)
i = t.rfind("\n", 0, i) + 1
sys.stdout.write(t[i:t.index("\n", j) + 1])' "$1" "$2" "$3"
}
server() { # unit output [answer [cert]]: starts the unit's host end and waits until it listens
    if [ "$1" = a0 ]; then
        python3 tools/claudebridge.py --fake --port 7070 --seconds 120 > "$2" 2>&1 &
    elif [ "$1" = a2 ]; then
        python3 tools/apihost.py --port 8080 --seconds 120 --dns 5353 --answer "${3:-10.0.2.2}" > "$2" 2>&1 &
    elif [ "$1" = a4 ]; then
        python3 tools/apihost.py --port 8443 --seconds 120 --dns 5353 --answer "${3:-10.0.2.2}" --turns "${5:-2}" \
            --cert "tests/tls/${4:-api.mock}.pem" --key tests/tls/api.mock.key > "$2" 2>&1 &
    elif [ "$1" = a5 ]; then
        python3 tools/apihost.py --port 8080 --seconds 120 --turns 8 > "$2" 2>&1 &
    else
        python3 tools/apihost.py --port 8080 --seconds 120 > "$2" 2>&1 &
    fi
    for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q 'listening on' "$2" 2>/dev/null && return 0; sleep 0.2; done
    fail_exit "the $1 host end did not bind its port (see $2)"
}
served() { # unit output: the host end saw two good turns and ended
    if [ "$1" = a0 ]; then
        grep -qx 'claudebridge: 2 turns, connection closed' "$2"
    else
        [ "$(grep -c '^apihost: request [0-9]*, .*: 200, ' "$2")" = "$([ "$1" = a5 ] && echo 8 || echo 2)" ]
    fi
}

command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy python3 sha256sum cmp timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in cish $SH_TOOLS grant talk agent mrng; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"

# 1. build, and the committed programs
make -s -j"$(nproc)" O="$B" FLAVORS=net CINT_TOOLCHAIN="$CINT_TOOLCHAIN" > "$B/make.log" 2>&1 \
    && line ok "build: the net flavor for gcc and clang (make FLAVORS=net)" \
    || { line bad "build: make FLAVORS=net" "see $B/make.log"; echo "RESULT: FAIL"; exit 1; }
sed 's#  user/bin/#  #' tests/expected/agent.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/pin.log" 2>&1 \
    && line ok "programs: O/ubin/talk, O/ubin/agent and O/ubin/mrng are the bytes of tests/expected/agent.sha256 (DU-2)" \
    || line bad "programs: pin" "see $B/pin.log"

# 2. the committed journals: well formed, and their replays are the pinned transcripts
for u in $UNITS; do
    # shellcheck disable=SC2046
    python3 tools/netjournal.py journal "tests/net/$u.journal" "$B/$u.journal" > /dev/null 2> "$B/$u-journal.log" \
        && cmp -s "tests/net/$u.journal" "$B/$u.journal" \
        && { [ "$u" != a4 ] || { python3 tools/netjournal.py rng tests/net/a4-rng.journal "$B/a4-rng.journal" > /dev/null \
            && cmp -s tests/net/a4-rng.journal "$B/a4-rng.journal"; }; } \
        && python3 tools/mkcpio.py "$B/$u.cpio" $(members "$u") $(journals "$u" "tests/net/$u.journal") \
        && python3 tools/mkcpio.py "$B/$u-live.cpio" $(members "$u") \
        && line ok "journal: tests/net/$u.journal is a well-formed record$([ "$u" = a4 ] && echo ", and tests/net/a4-rng.journal")" || line bad "journal $u" "see $B/$u-journal.log"
    for cc in gcc clang; do
        boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-$u.txt" none "$B/$u.cpio" \
            && cmp -s "tests/expected/net-$u.serial" "$B/run/$cc-$u.txt" \
            && line ok "replay $cc: tests/net/$u.journal ($(prog "$u")'s two turns) gives tests/expected/net-$u.serial" \
            || line bad "replay $cc: $u" "status, stderr or the transcript differs from tests/expected/net-$u.serial"
    done
done

# 2b. A-3: the draw and the date (mrng), no network; the live legs need only QEMU's -cpu max
drawn() { # transcript: one `rng 64` record whose bytes mrng printed, and mrng's realtime is the `rtc` line's plus the
    # last `wal S` before it (RS-CLK2: the PIT seconds since the date)
    python3 -c '
import re, sys
t = open(sys.argv[1], encoding="latin-1").read()
rec = re.findall(r"^rng 64 ([0-9a-f]{128})$", t, re.M)
got = re.findall(r"^mrng: getrandom 64 ([0-9a-f]{128})$", t, re.M)
rtc = re.findall(r"^rtc ([0-9]+)$", t, re.M)
real = re.findall(r"^mrng: realtime ([0-9]+)$", t, re.M)
at = t.find("mrng: realtime ")
wal = [int(w) for w in re.findall(r"^wal ([0-9]+) [0-9]+$", t[:at if at >= 0 else len(t)], re.M)] or [0]
sys.exit(not (len(rec) == 1 and got == rec and len(rtc) == 1 and real == [str(int(rtc[0]) + wal[-1])]
              and int(rtc[0]) > 1767225600))' "$1"
}
mrng=mrng=$UB/mrng
python3 tools/netjournal.py rng tests/net/a3.journal "$B/a3.journal" > /dev/null 2> "$B/a3-journal.log" \
    && cmp -s tests/net/a3.journal "$B/a3.journal" \
    && python3 tools/mkcpio.py "$B/a3.cpio" rng.journal=tests/net/a3.journal "$mrng" \
    && python3 tools/mkcpio.py "$B/a3-live.cpio" "$mrng" \
    && line ok "journal: tests/net/a3.journal is a well-formed draw record (one rtc line, one draw)" || line bad "journal a3" "see $B/a3-journal.log"
for cc in gcc clang; do
    boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-a3.txt" none "$B/a3.cpio" \
        && cmp -s tests/expected/net-a3.serial "$B/run/$cc-a3.txt" \
        && line ok "replay $cc: tests/net/a3.journal (mrng's draw and the date) gives tests/expected/net-a3.serial" \
        || line bad "replay $cc: a3" "status, stderr or the transcript differs from tests/expected/net-a3.serial"
    boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-a3-none.txt" none "$B/a3-live.cpio" \
        && cmp -s tests/expected/net-a3-none.serial "$B/run/$cc-a3-none.txt" \
        && line ok "no source $cc: without a journal or RDRAND, getrandom is -ENOSYS and the date the fixed epoch (tests/expected/net-a3-none.serial)" \
        || line bad "no source $cc: a3" "status, stderr or the transcript differs from tests/expected/net-a3-none.serial"
done
"$UB"/mrng > "$B/run/linux-a3.txt" 2>&1 && grep -qE '^mrng: getrandom 64 [0-9a-f]{128}$' "$B/run/linux-a3.txt" \
    && line ok "oracle a3: O/ubin/mrng on this Linux host draws 64 bytes" || line bad "oracle a3" "see $B/run/linux-a3.txt"
for cc in gcc clang; do
    t=$B/run/$cc-a3-live.txt
    boot "$B/$cc-net/kernel32.elf" "$t" none "$B/a3-live.cpio" max \
        && drawn "$t" \
        && python3 tools/netjournal.py rng "$t" "$B/$cc-a3-live.journal" > /dev/null \
        && python3 tools/mkcpio.py "$B/$cc-a3-live.cpio" rng.journal="$B/$cc-a3-live.journal" "$mrng" \
        && line ok "live $cc a3: under -cpu max mrng draws 64 bytes, the record's, and its realtime is the rtc line's; journaled" \
        || line bad "live $cc a3" "see $t"
done
for cc in gcc clang; do
    for from in gcc clang; do
        boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-a3-replay-$from.txt" none "$B/$from-a3-live.cpio" \
            && python3 tools/netjournal.py same "$B/run/$from-a3-live.txt" "$B/run/$cc-a3-replay-$from.txt" > /dev/null \
            && line ok "replay $cc of the $from a3 live journal, without RDRAND: the live transcript but for the mode line" \
            || line bad "replay $cc of the $from a3 live journal" "see $B/run/$cc-a3-replay-$from.txt"
    done
done

# 2b'. K-6b: daphnis.rtc=1 reads the CMOS clock without RDRAND; masked in the compare, replayed from its journal
RTC_BASE=2026-07-04T12:00:00 RTC_S=1783166400
dated() { # transcript: one `rtc S` line, S in [RTC_S, RTC_S + 60], mrng's realtime S plus the last `wal W` before it,
    # no draw; masked (RS-CLK2: the `wal` lines too), the none golden
    python3 -c '
import re, sys
t = open(sys.argv[1], encoding="latin-1").read()
base = int(sys.argv[3])
rtc = re.findall(r"^rtc ([0-9]+)$", t, re.M)
real = re.findall(r"^mrng: realtime ([0-9]+)$", t, re.M)
at = t.find("mrng: realtime ")
wal = [int(w) for w in re.findall(r"^wal ([0-9]+) [0-9]+$", t[:at if at >= 0 else len(t)], re.M)] or [0]
ok = (len(rtc) == 1 and real == [str(int(rtc[0]) + wal[-1])] and base <= int(rtc[0]) <= base + 60
      and not re.search(r"^rng ", t, re.M))
def mask(x):
    x = re.sub(r"^rtc [0-9]+\n", "", x, flags=re.M)
    x = re.sub(r"^wal [0-9]+ [0-9]+\n", "", x, flags=re.M)
    x = re.sub(r"^mrng: realtime [0-9]+$", "mrng: realtime D", x, flags=re.M)
    return re.sub(r"^daphnis: state [0-9a-f]{64}$", "daphnis: state H", x, flags=re.M)
sys.exit(not (ok and mask(t) == mask(open(sys.argv[2], encoding="latin-1").read())))' "$1" tests/expected/net-a3-none.serial "$RTC_S"
}
for cc in gcc clang; do
    t=$B/run/$cc-a3-date.txt
    rc=$(RTC=1 QEMU_EXTRA="-rtc base=$RTC_BASE" INITRD="$B/a3-live.cpio" QEMU_TIMEOUT=60 tools/run-qemu.sh "$B/$cc-net/kernel32.elf" "$t")
    [ "$rc" = 33 ] && [ ! -s "$t.err" ] && dated "$t" \
        && python3 tools/netjournal.py rng "$t" "$B/$cc-a3-date.journal" > /dev/null \
        && python3 tools/mkcpio.py "$B/$cc-a3-date.cpio" rng.journal="$B/$cc-a3-date.journal" "$mrng" \
        && line ok "date $cc: daphnis.rtc=1 without RDRAND reads the CMOS clock once (one rtc line, mrng's realtime, getrandom -ENOSYS); masked, tests/expected/net-a3-none.serial" \
        || line bad "date $cc" "see $t"
done
for cc in gcc clang; do
    for from in gcc clang; do
        boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-a3-date-replay-$from.txt" none "$B/$from-a3-date.cpio" \
            && python3 tools/netjournal.py same "$B/run/$from-a3-date.txt" "$B/run/$cc-a3-date-replay-$from.txt" > /dev/null \
            && line ok "replay $cc of the $from date journal (the rtc line alone): the live transcript but for the mode line" \
            || line bad "replay $cc of the $from date journal" "see $B/run/$cc-a3-date-replay-$from.txt"
    done
done

# 2c. A-4's refusals on this Linux host: a certificate out of its dates, one by a root agent does not hold
refused() { # transcript code: agent's line for the error, then the failed turn
    app_lines "$1" "agent: api.mock is" "agent: the turn failed" | grep -q "^> agent: tls: error $2,"
}
for c in expired:1054 stranger:1062; do
    cert=${c%:*} code=${c#*:}
    server a4 "$B/a4-linux-$cert.out" 127.0.0.1 "$cert" 1
    printf 'hello Daphnis\n' | $UB/agent -d 127.0.0.1:5353 -t api.mock 8443 > "$B/run/linux-a4-$cert.txt" 2>&1
    rc=$?
    wait
    [ "$rc" = 1 ] && refused "$B/run/linux-a4-$cert.txt" "$code" && grep -q '^apihost: request 1, tls: ' "$B/a4-linux-$cert.out" \
        && line ok "refusal a4 $cert: on this Linux host agent refuses tests/tls/$cert.pem in the handshake (error $code) and sends no request" \
        || line bad "refusal a4 $cert" "see $B/run/linux-a4-$cert.txt and $B/a4-linux-$cert.out"
done

# 3. live, with QEMU's user network, and the Linux oracle
if qemu-system-x86_64 -netdev help 2>/dev/null | grep -qx user; then
    for u in $UNITS; do
        server "$u" "$B/$u-linux.out" 127.0.0.1
        linux_run "$u" > "$B/run/linux-$u.txt" 2>&1
        wait
        served "$u" "$B/$u-linux.out" && grep -q "^$(last "$u")" "$B/run/linux-$u.txt" \
            && { [ "$u" != a5 ] || [ -z "$(ls -A "$B/run/a5-wd")" ]; } \
            && line ok "oracle $u: O/ubin/$(prog "$u") on this Linux host, two turns" || line bad "oracle $u" "see $B/run/linux-$u.txt"
        app_lines "$B/run/linux-$u.txt" "$(first "$u")" "$(last "$u")" > "$B/run/linux-$u.lines"
        for cc in gcc clang; do
            t=$B/run/$cc-$u-live.txt
            server "$u" "$B/$u-$cc.out"
            # shellcheck disable=SC2046
            boot "$B/$cc-net/kernel32.elf" "$t" user "$B/$u-live.cpio" "$(cpu "$u")" \
                && grep -qx 'daphnis: net tcp connections open 0, resets sent 0' "$t" \
                && { [ "$u" != a2 ] && [ "$u" != a4 ] || grep -qx 'agent: api.mock is 10.0.2.2' "$t"; } \
                && [ -s "$B/run/linux-$u.lines" ] && app_lines "$t" "$(first "$u")" "$(last "$u")" | cmp -s - "$B/run/linux-$u.lines" \
                && wait && served "$u" "$B/$u-$cc.out" \
                && python3 tools/netjournal.py journal "$t" "$B/$cc-$u-live.journal" > /dev/null \
                && { [ "$u" != a4 ] || python3 tools/netjournal.py rng "$t" "$B/$cc-$u-live-rng.journal" > /dev/null; } \
                && python3 tools/mkcpio.py "$B/$cc-$u-live.cpio" $(members "$u") $(journals "$u" "$B/$cc-$u-live.journal") \
                && line ok "live $cc $u: $(prog "$u") under grant net, two turns, the lines of Linux's run (DU-1), every connection closed; journaled" \
                || line bad "live $cc $u" "see $t and $B/$u-$cc.out"
            wait
        done
        for cc in gcc clang; do
            for from in gcc clang; do
                boot "$B/$cc-net/kernel32.elf" "$B/run/$cc-$u-replay-$from.txt" none "$B/$from-$u-live.cpio" \
                    && python3 tools/netjournal.py same "$B/run/$from-$u-live.txt" "$B/run/$cc-$u-replay-$from.txt" > /dev/null \
                    && line ok "replay $cc of the $from $u live journal: the live transcript but for the mode line" \
                    || line bad "replay $cc of the $from $u live journal" "see $B/run/$cc-$u-replay-$from.txt"
            done
        done
    done
    # A-4 in Daphnis: the expired certificate refused (gcc, -cpu max), and no session without an entropy source
    # (clang, QEMU's default CPU has no RDRAND): getrandom is -ENOSYS and agent sends no ClientHello
    server a4 "$B/a4-gcc-expired.out" 10.0.2.2 expired 1
    boot "$B/gcc-net/kernel32.elf" "$B/run/gcc-a4-expired.txt" user "$B/a4-live.cpio" max \
        && refused "$B/run/gcc-a4-expired.txt" 1054 && wait && grep -q '^apihost: request 1, tls: ' "$B/a4-gcc-expired.out" \
        && line ok "refusal live gcc a4 expired: in Daphnis agent refuses tests/tls/expired.pem in the handshake (error 1054)" \
        || line bad "refusal live gcc a4 expired" "see $B/run/gcc-a4-expired.txt and $B/a4-gcc-expired.out"
    wait
    server a4 "$B/a4-clang-none.out" 10.0.2.2 api.mock 1
    boot "$B/clang-net/kernel32.elf" "$B/run/clang-a4-none.txt" user "$B/a4-live.cpio" \
        && refused "$B/run/clang-a4-none.txt" 38 && ! grep -q '^rng ' "$B/run/clang-a4-none.txt" && wait \
        && grep -q '^apihost: request 1, tls: ' "$B/a4-clang-none.out" \
        && line ok "no source live clang a4: without RDRAND getrandom is -ENOSYS and agent opens no TLS session (error 38)" \
        || line bad "no source live clang a4" "see $B/run/clang-a4-none.txt and $B/a4-clang-none.out"
    wait
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
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 3 minutes" || line bad "time" "$elapsed s"
want_total=$((gate_want + live_ran * live_pass)); want_skips=$((1 - live_ran))
[ "$passes" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $live_pass with the live legs)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
