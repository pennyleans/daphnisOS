#!/usr/bin/env bash
# check-editor.sh: the gate of ced, the bundled editor (docs/specs/2026-11-06-e-editor.md section 2), on its own
# budget beside check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   E-4, on Linux: user/ced/ is ced-dev at the commit of user/ced/CED_PIN, file for file (user/ced/SOURCES.sha256);
#   ced's own checks (user/ced/tests/run.py: its lint, its unit tests and every key replay) pass on the pinned cint;
#   O/ubin/ced (musl, static) is the bytes of tests/expected/ced.sha256; it and the same emitted C
#   built by the host's gcc and clang (glibc, static) each take tools/check-editor.py's keys on a pty and save its
#   file, and all three write the same bytes to the terminal; the gcc and clang builds, started with no FILE, save
#   under the working directory only inside HOME, else under HOME (tools/check-untitled.py, RUN-8).
#   E-5, under Daphnis: the desk flavor, whose image carries ced, boots on gcc and clang at 512 MiB with the pool from
#   the memory map (POOL=max: ced takes about 57 MiB); `$EDITOR notes.txt` (E-6), tools/check-editor.py's keys, `cat
#   notes.txt` and `exit` are typed through the QEMU monitor; tools/check-editor.py --boot checks the file through cat
#   and the ends, and every transcript, but for the terminal's byte count and digest (which follow how the keys
#   fall into ced's reads, E-5b), is tests/expected/editor.serial.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-editor), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-editor}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
export CINT_TOOLCHAIN
BUDGET=240   # the boots wait for ced to start and end between keys
gate_want=20   # the PASS lines before the last one
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-editor.sh: $*"; echo "RESULT: FAIL"; exit 1; }

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
make -s -j"$(nproc)" O="$B" $(for p in ced; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "ced:    ced-dev $(cat user/ced/CED_PIN), $(cat user/ced/VERSION)"

# 1. the sources and ced's own checks
(cd user/ced && sha256sum --strict --quiet -c SOURCES.sha256) > "$B/sources.log" 2>&1 \
    && line ok "sources: user/ced/ is the $(wc -l < user/ced/SOURCES.sha256) files of ced-dev $(cut -c1-8 user/ced/CED_PIN), unchanged" \
    || line bad "sources" "see $B/sources.log"
CINT_BUILD=$B/ced-tests python3 user/ced/tests/run.py > "$B/ced-tests.log" 2>&1 \
    && line ok "ced: user/ced/tests/run.py on the pinned cint ($(tail -1 "$B/ced-tests.log"))" \
    || line bad "ced: user/ced/tests/run.py" "$(tail -1 "$B/ced-tests.log"); see $B/ced-tests.log"

# 2. the committed build, and the same emitted C from the host's gcc and clang
sed 's#  user/bin/#  #' tests/expected/ced.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/ced is the bytes of tests/expected/ced.sha256" || line bad "bin" "see $B/bin.log"
edit() { # label build
    mkdir -p "$B/$1"
    python3 tools/check-editor.py "$2" "$B/$1" > "$B/$1.cmp" 2>&1
    sed 's/^/  /' "$B/$1.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/$1.cmp")" = 3 ] && ! grep -q '^FAIL' "$B/$1.cmp" \
        && line ok "linux $1: ced on a pty takes the keys, saves notes.txt and leaves the screen as it found it" \
        || line bad "linux $1" "see $B/$1.cmp"
}
edit musl $UB/ced
for cc in gcc clang; do
    CI_CC=$cc CI_OUT=$B/bin-$cc bash tools/build-ced.sh > "$B/build-$cc.log" 2>&1 \
        && line ok "linux $cc: ced's emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/build-$cc.log"
    edit "$cc" "$B/bin-$cc/ced"
    python3 tools/check-untitled.py "$B/bin-$cc/ced" > "$B/untitled-$cc.log" 2>&1 \
        && line ok "linux $cc: an Untitled ced's /arg1 is the working directory in the home, else the home (RUN-8)" \
        || line bad "linux $cc: Untitled's grant" "see $B/untitled-$cc.log"
done
cmp -s "$B/musl/screen.bin" "$B/gcc/screen.bin" && cmp -s "$B/musl/screen.bin" "$B/clang/screen.bin" \
    && line ok "screen: musl, gcc and clang write the same $(wc -c < "$B/musl/screen.bin") bytes to the terminal" \
    || line bad "screen" "the bytes differ across builds (see $B/*/screen.bin)"

# 3. E-5 under Daphnis: the desk with ced, on gcc and clang, at 512 MiB with the pool from the memory map
make -s -j"$(nproc)" O="$B" FLAVORS=desk > "$B/make.log" 2>&1 \
    && line ok "build: the desk flavor for gcc and clang and its image, ced in it (make FLAVORS=desk)" \
    || line bad "build: make FLAVORS=desk" "see $B/make.log"
keys=$(python3 tools/check-editor.py --keys)
mkdir -p "$B/run"
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ ${#t} -le 100 ] || fail_exit "monitor socket path $t.mon is too long for a unix socket; set a shorter DAPHNIS_BUILD"
    (SENDKEYS_WAIT=150 python3 tools/sendkeys.py "$t.mon" "$t" "tiler: desk shell first output" "$keys" > "$t.keys" 2>&1 &
     POOL=max QEMU_TIMEOUT=150 INITRD=$B/desk/initrd.cpio MONITOR=$t.mon MEM=512 \
        tools/run-qemu.sh "$B/$cc-desk/kernel32.elf" "$t" > "$t.rc"; wait) &
done
wait
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    python3 tools/check-editor.py --boot "$t" > "$B/boot-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/boot-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/boot-$cc.cmp")" = 2 ] && ! grep -q '^FAIL' "$B/boot-$cc.cmp" \
        && line ok "desk $cc: ced in the desk's terminal takes the keys and saves notes.txt as on Linux; the desk ends whole" \
        || line bad "desk $cc" "see $B/boot-$cc.cmp"
    grep -v '^tiler: term bytes ' "$t" | cmp -s tests/expected/editor.serial - \
        && line ok "serial $cc: the transcript, but for its terminal byte line, equals tests/expected/editor.serial" \
        || line bad "serial $cc: vs tests/expected/editor.serial" "differ"
done

# 4. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
