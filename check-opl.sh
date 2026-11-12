#!/usr/bin/env bash
# check-opl.sh: gate 7 of stage AU (docs/specs/2026-11-06-au-audio.md section 6), the OPL3 of user/ci/opl/, on its
# own budget beside check.sh. One PASS, FAIL or SKIP line per check; exit status 1 if any FAIL.
#   The walk: tools/oplref/walk.txt and user/ci/oplwalk.ci are what tools/oplref/mkwalk.py writes.
#   On Linux: O/ubin/opltest (musl, static) is the bytes of tests/expected/opltest.sha256; it and the
#   same emitted C built by the host's gcc and clang (glibc, static) play the walk and print
#   tests/expected/opl.digests: each part's chip-rate samples, all of them and the 48 kHz resample, made once from
#   ymfm's samples by tools/check-opl.py.
#   The reference: with OPLREF set to a built tools/oplref binary (tools/oplref/fetch.sh, then build.sh), ymfm's
#   samples of the walk give tests/expected/opl.digests again; without it, one SKIP line.
#   Under Daphnis: the cish flavor boots on gcc and clang with an image of cish and opltest and runs `./opltest`;
#   both runs (pid 1, and pid 2 on other frames) print tests/expected/opl.digests and do not desync.
#   Cost: the seconds of each leg are printed (`cost:` lines, not gated). KVM=1 boots under KVM (on Arch).
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-opl), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-opl}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=180
gate_want=17   # the PASS lines before the last one, the reference leg left out; it adds 1, or one SKIP line
ref_pass=1
want=tests/expected/opl.digests
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-opl.sh: $*"; echo "RESULT: FAIL"; exit 1; }
ms() { date +%s%N | cut -c1-13; }
cost() { # label start_ms
    local t=$(( $(ms) - $2 ))
    printf 'cost: %s %d.%03d s\n' "$1" $((t / 1000)) $((t % 1000))
}

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
make -s -j"$(nproc)" O="$B" $(for p in cish opltest; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"

# 1. the walk
python3 tools/oplref/mkwalk.py --check > "$B/walk.log" 2>&1 \
    && line ok "walk: tools/oplref/walk.txt and user/ci/oplwalk.ci are what tools/oplref/mkwalk.py writes" \
    || line bad "walk" "$(cat "$B/walk.log")"

# 2. Linux: the committed build, then the host's gcc and clang
sed 's#  user/bin/#  #' tests/expected/opltest.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/opltest is the bytes of tests/expected/opltest.sha256" || line bad "bin" "see $B/bin.log"
for cc in gcc clang; do
    CI_CC=$cc CI_OUT=$B/$cc bash user/ci/build.sh opltest > "$B/$cc.log" 2>&1 \
        && line ok "linux $cc: opltest's emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/$cc.log"
done
for k in musl gcc clang; do
    b=$B/$k/opltest
    [ $k = musl ] && b=$UB/opltest
    t0=$(ms)
    "$b" > "$B/linux-$k.out" 2>&1
    cost "linux $k opltest, the whole walk" "$t0"
    python3 tools/check-opl.py compare "$want" "$B/linux-$k.out" > "$B/linux-$k.cmp" 2>&1 \
        && line ok "linux $k: opltest plays the walk and prints $want (ymfm's samples, sample for sample)" \
        || line bad "linux $k: opltest vs $want" "$(head -2 "$B/linux-$k.cmp" | tr '\n' ' ')"
done

# 3. the reference
if [ -n "${OPLREF:-}" ]; then
    t0=$(ms)
    "$OPLREF" tools/oplref/walk.txt "$B/ref.raw" > "$B/ref.log" 2>&1
    cost "oplref (ymfm), the whole walk" "$t0"
    python3 tools/check-opl.py lines "$B/ref.raw" > "$B/ref.digests" 2>&1 && cmp -s "$B/ref.digests" "$want" \
        && line ok "reference: ymfm ($OPLREF) plays the walk to $want" \
        || line bad "reference: ymfm vs $want" "see $B/ref.digests"
else
    skip "reference: OPLREF not set (tools/oplref/fetch.sh DIR; tools/oplref/build.sh DIR/src OUT; OPLREF=OUT/oplref)"
fi

# 4. Daphnis: the cish flavor on gcc and clang, an image of cish and opltest
make -s -j"$(nproc)" O="$B" FLAVORS=cish > "$B/make.log" 2>&1 \
    && line ok "build: the cish flavor for gcc and clang (make FLAVORS=cish)" \
    || line bad "build: make FLAVORS=cish" "see $B/make.log"
python3 tools/mkcpio.py "$B/opl.cpio" cish=$UB/cish opltest=$UB/opltest > "$B/cpio.log" 2>&1 \
    && line ok "image: cish and opltest (tools/mkcpio.py)" || line bad "image" "see $B/cpio.log"
printf './opltest\n\004' > "$B/opl.in"
mkdir -p "$B/run"
t0=$(ms)
for cc in gcc clang; do
    t=$B/run/$cc.txt
    (QEMU_TIMEOUT=150 INITRD=$B/opl.cpio STDIN_FILE=$B/opl.in MEM=128 \
        tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
done
wait
cost "daphnis gcc and clang boots side by side, the walk twice in each$([ "${KVM:-0}" = 1 ] && echo ', KVM' || echo ', TCG')" "$t0"
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
    ok=1
    for pid in 1 2; do
        sed -n "/^daphnis: run cish pid $pid\$/,/^daphnis: exit/p" "$t" > "$B/run/$cc-$pid.out"
        grep -qx 'daphnis: exit 0' "$B/run/$cc-$pid.out" \
            && python3 tools/check-opl.py compare "$want" "$B/run/$cc-$pid.out" > "$B/run/$cc-$pid.cmp" 2>&1 || ok=0
    done
    [ $ok = 1 ] && line ok "daphnis $cc: opltest under Daphnis prints $want, in both runs" \
        || line bad "daphnis $cc: opltest vs $want" "see $B/run/$cc-*.cmp"
    grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
        && line ok "desync $cc: the run on other frames does not desync" || line bad "desync $cc" "see $t"
done

# 5. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 3 minutes" || line bad "time" "$elapsed s"
total=$gate_want want_skips=1
[ -n "${OPLREF:-}" ] && { total=$((gate_want + ref_pass)); want_skips=0; }
[ "$passes" = "$total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $ref_pass with OPLREF)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
