#!/usr/bin/env bash
# check-basics.sh: the gate of stage BP (docs/specs/2026-11-07-bp-basics.md section 5), gate 14, on its own budget
# beside check-core.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   bin: O/ubin/cless, ccalc and cview are the bytes of tests/expected/basics.sha256.
#   linux: each tool's emitted C builds with the host's gcc and clang (glibc, static); the cases of
#   tests/basics/TOOL.cases (tools/check-core.py cases, over tests/basics/tree) under the committed build print
#   tests/expected/basics-TOOL.out, and the gcc and clang builds print the same bytes.
#   oracle: cview -d of every good fixture equals tools/check-basics.py digest (Python's zlib and a reader of its
#   own); ccalc's cases print what tools/check-basics.py calc's model of the arithmetic prints.
#   fixtures: tools/check-basics.py fixtures writes the committed tests/basics/tree/img byte for byte.
#   pty: cless on a pty of 80 x 24 with tests/basics/cless.keys writes tests/expected/basics-cless.pty, and the
#   terminal's mode after is the mode before.
#   read: cless on the desk (RS-RE): tools/check-read.py works out each screen from the fixture's bytes.
#   session: tests/basics/session.sh under the committed cish in the basics image prints
#   tests/expected/basics-session.out.
#   daphnis: the cish flavor's kernel boots the basics image on gcc and clang with the session as its input; cish's
#   block is the Linux bytes, the second run (other frames) does not desync, every transcript is
#   tests/expected/basics.serial.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-basics), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-basics}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=120
TOOLS=$(sed -n 's/^BASICS_TOOLS := //p' Makefile)
ntools=$(echo $TOOLS | wc -w)
gate_want=$((20 + 2 * ntools))   # the PASS lines before the last one (+1 RS-RE, read)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-basics.sh: $*"; echo "RESULT: FAIL"; exit 1; }

for t in cint gcc clang musl-gcc as ld objcopy qemu-system-x86_64 python3 sha256sum cmp timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in cish $TOOLS; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "tools:  $TOOLS"

# the image, the Linux session and both Daphnis boots need only the committed bytes, so they start first
mkdir -p "$B/run"
printf '\004' | cat tests/basics/session.sh - > "$B/session.in"
(
    make -s -j"$(nproc)" O="$B" FLAVORS=cish all "$B/basics/initrd.cpio" > "$B/make.log" 2>&1
    echo $? > "$B/make.rc"
    [ "$(cat "$B/make.rc")" = 0 ] || exit 0
    python3 tools/check-cish.py linux "$B/basics/initrd.cpio" tests/basics/session.sh "$B/session.linux" \
        "$UB/cish" > "$B/session.log" 2>&1 &
    for cc in gcc clang; do
        t=$B/run/$cc.txt
        (QEMU_TIMEOUT=100 INITRD=$B/basics/initrd.cpio STDIN_FILE=$B/session.in MEM=128 \
            tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
    done
    wait
) &
image_pid=$!

# 1. the committed builds, and the same emitted C from the host's gcc and clang
sed 's#  user/bin/#  #' tests/expected/basics.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/{$TOOLS} are the bytes of tests/expected/basics.sha256" || line bad "bin" "see $B/bin.log"
mkdir -p "$B/logs"
for cc in gcc clang; do for t in $TOOLS; do echo "$cc $t"; done; done \
    | xargs -P "$(nproc)" -n 2 sh -c 'CI_CC=$1 CI_OUT=$0/$1 bash user/ci/build.sh "$2" > "$0/logs/$1-$2.log" 2>&1 || : > "$0/logs/$1-$2.bad"' "$B"
for cc in gcc clang; do
    ok=1
    for t in $TOOLS; do [ -f "$B/logs/$cc-$t.bad" ] && ok=0; done
    [ $ok = 1 ] && line ok "linux $cc: the tools' emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/logs"
done

# 2. the cases under the committed bytes and the two builds
mkdir -p "$B/cases"
for t in $TOOLS; do
    echo "$t musl $UB/$t"
    echo "$t gcc $B/gcc/$t"
    echo "$t clang $B/clang/$t"
done | B=$B xargs -P "$(nproc)" -L 1 sh -c \
    'python3 tools/check-core.py cases "tests/basics/$0.cases" tests/basics/tree "$B/cases/$0.$1" "$2"'
for t in $TOOLS; do
    cmp -s "$B/cases/$t.musl" "tests/expected/basics-$t.out" \
        && line ok "cases $t: tests/basics/$t.cases prints tests/expected/basics-$t.out" \
        || line bad "cases $t: vs tests/expected/basics-$t.out" "see $B/cases/$t.musl"
    same=1
    for cc in gcc clang; do
        cmp -s "$B/cases/$t.$cc" "$B/cases/$t.musl" || same=0
    done
    [ $same = 1 ] && line ok "builds $t: musl, gcc and clang print the same bytes for each case" \
        || line bad "builds $t" "differ (see $B/cases/$t.*)"
done

# 3. the oracles
good=$(cd tests/basics/tree && ls img/* | grep -v '^img/bad-')
(cd tests/basics/tree && for f in $good; do "$UB/cview" -d "$f"; done) > "$B/cview.digests" 2>&1
(cd tests/basics/tree && python3 -I "$OLDPWD/tools/check-basics.py" digest $good) > "$B/py.digests" 2>&1
[ -s "$B/py.digests" ] && cmp -s "$B/cview.digests" "$B/py.digests" \
    && line ok "oracle cview: the $(echo $good | wc -w) good fixtures decode to the RGBA of tools/check-basics.py digest" \
    || line bad "oracle cview" "see $B/cview.digests, $B/py.digests"
python3 -I tools/check-basics.py calc tests/basics/ccalc.cases tests/basics/tree "$UB/ccalc" > "$B/calc.log" 2>&1 \
    && line ok "oracle ccalc: every case prints what the model of the arithmetic prints, with its status" \
    || line bad "oracle ccalc" "see $B/calc.log"
python3 -I tools/check-basics.py fixtures "$B/img" > /dev/null 2>&1 && diff -r -q "$B/img" tests/basics/tree/img > "$B/img.diff" 2>&1 \
    && line ok "fixtures: tools/check-basics.py fixtures writes tests/basics/tree/img byte for byte" \
    || line bad "fixtures" "see $B/img.diff"

# 4. the pager on a pty
python3 -I tools/check-basics.py pty "$UB/cless" tests/basics/tree/lines.txt tests/basics/cless.keys \
    "$B/cless.pty" > "$B/pty.log" 2>&1 && cmp -s "$B/cless.pty" tests/expected/basics-cless.pty \
    && line ok "pty: cless pages, searches and quits as tests/expected/basics-cless.pty, the terminal's mode given back" \
    || line bad "pty: vs tests/expected/basics-cless.pty" "see $B/pty.log, $B/cless.pty"
python3 -I tools/check-read.py "$UB/cless" tests/basics/tree > "$B/read.log" 2>&1 \
    && line ok "read: cless on the desk: title, rows, place bar, find line, count and open as tools/check-read.py" \
    || line bad "read: tools/check-read.py" "see $B/read.log"

# 5. the cish flavor's kernel and the basics image
wait "$image_pid"
[ "$(cat "$B/make.rc" 2>/dev/null)" = 0 ] \
    && line ok "build: the cish flavor for gcc and clang and the basics image" \
    || line bad "build: make FLAVORS=cish basics/initrd.cpio" "see $B/make.log"
cat "$B/session.log" 2>/dev/null
cmp -s "$B/session.linux" tests/expected/basics-session.out \
    && line ok "session linux: cish and the basics print tests/expected/basics-session.out" \
    || line bad "session linux: vs tests/expected/basics-session.out" "see $B/session.linux"
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
    python3 tools/check-cish.py daphnis "$t" 1 "$B/run/$cc.block" > "$B/run/$cc.cmp" 2>&1 \
        && cmp -s "$B/run/$cc.block" "$B/session.linux" \
        && line ok "daphnis $cc: cish's block is the Linux run's bytes and status" \
        || line bad "daphnis $cc: cish's block vs Linux" "see $B/run/$cc.block"
    grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
        && line ok "desync $cc: the session with other frames does not desync" || line bad "desync $cc" "see $t"
    cmp -s tests/expected/basics.serial "$t" \
        && line ok "serial $cc: the transcript equals tests/expected/basics.serial" \
        || line bad "serial $cc: vs tests/expected/basics.serial" "differ"
done

# 6. the checkout, the time, the count
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the checkout changed"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ $elapsed -le $BUDGET ] && line ok "time: whole check in $elapsed s, under 2 minutes" \
    || line bad "time" "$elapsed s, past the $BUDGET s budget"
[ $passes -eq $gate_want ] && [ $fails -eq 0 ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ $fails -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
