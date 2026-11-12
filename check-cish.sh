#!/usr/bin/env bash
# check-cish.sh: the gate of cish (docs/specs/2026-11-06-cish-shell.md section 9), on its own budget beside check.sh.
# One PASS or FAIL line per check; exit status 1 if any FAIL.
#   CS-1, without rows: tests/cish/lexparse.ci runs the lexer and the parser under `cint run`; its output is
#   tests/expected/cish-lexparse.out.
#   CS-1, on Linux: O/ubin/cish (musl, static) is the bytes of tests/expected/cish.sha256; it and the
#   same emitted C built by the host's gcc and clang (glibc, static) run each session in a directory holding the
#   cish flavor's image: descriptors 1 and 2 and the status are the same bytes for all three, and for
#   tests/cish/s1.sh they are tests/expected/cish-s1.out. DOS-3 (unit 4b): with CORE_ORACLE naming the busybox
#   tarball, busybox ash (built by user/busybox/oracle.sh) runs each session the same way and prints the same bytes
#   (DU-1: Linux is the oracle); without it, SKIP: the committed outputs, which ash printed, stand in.
#   CS-1, under Daphnis: the cish flavor (src/main_cish.ci) boots on gcc and clang with tests/cish/s1.sh as its input;
#   cish's block is the Linux run's bytes, the second run (other frames) does not desync, and every transcript is
#   tests/expected/cish.serial.
#   CS-2: tests/cish/s2.sh (compound commands, functions, echo, test, printf) the same way: its Linux bytes are
#   tests/expected/cish-s2.out, and its boots' transcripts tests/expected/cish-s2.serial.
#   CS-3: tests/cish/s3.sh (expansions, substitutions, arithmetic, IFS, globbing, here-documents) the same way; and
#   the refusal corpus tests/cish/refuse.txt, each line under `cish -c`, every status 2, the bytes
#   tests/expected/cish-refuse.out.
#   CS-4: tests/cish/s4.sh (eval, ., read, wait, &, exec) the same way: tests/expected/cish-s4.out and
#   tests/expected/cish-s4.serial.
#   CT-5b: tests/cish/s5.sh (the environment a child gets; Linux only until execve passed envp) the same way:
#   tests/expected/cish-s5.out and tests/expected/cish-s5.serial.
#   K-10: O/ubin/ctrlc runs a shell on a pty and types Ctrl-C at a running program and at a pipeline in a loop, and
#   Ctrl-\ at a running program. On Linux it runs cish (musl, gcc, clang) in the cish image, and busybox ash with the
#   oracle: the same lines, tests/expected/cish-ctrlc.out. Under Daphnis the cish flavor boots with daphnis.ctrlc=1
#   on gcc and clang from an image of cish, ctrlc and the native /bin/cat: ctrlc's block is those bytes, the second
#   run does not desync, and the transcript is tests/expected/cish-ctrlc.serial.
#   K-9: O/ubin/keyed types at cish's line editor (Ctrl+L, Up and Down, the moves, the kills, Tab, Ctrl+C at PS1 and
#   PS2, a line past a row, Ctrl+D) in an image of cish, keyed, /bin/cat and kd/. On Linux cish from musl, gcc and
#   clang prints the lines of tests/expected/cish-keyed.out, and the terminal's last screen, the logged bytes drawn in
#   the twin of tools/check-tiler.py, is tests/expected/cish-keyed.screen. Under Daphnis the cish flavor boots with
#   daphnis.keyed=1 on gcc and clang: keyed's block is those lines, no desync, tests/expected/cish-keyed.serial.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-cish), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-cish}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=180
gate_want=72   # the PASS lines before the last one, without the oracle (78 until DOS-3 made ash's six lines optional)
SESSIONS="s1 s2 s3 s4 s5"      # tests/cish/NAME.sh
BOOTS="s1 s2 s3 s4 s5"      # the sessions booted under Daphnis; NAME's transcript golden is serial_of NAME
serial_of() { if [ "$1" = s1 ]; then echo tests/expected/cish.serial; else echo "tests/expected/cish-$1.serial"; fi; }
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-cish.sh: $*"; echo "RESULT: FAIL"; exit 1; }

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
make -s -j"$(nproc)" O="$B" $(for p in cish ctrlc keyed cat; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
BB=$(user/busybox/oracle.sh) || fail_exit "CORE_ORACLE: busybox did not build from $CORE_ORACLE (user/busybox/oracle.sh)"
echo "oracle: ${BB:-none (CORE_ORACLE unset: the committed outputs stand in)}"
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"

# 1. the lexer and the parser alone
cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cache" --root . tests/cish/lexparse.ci > "$B/lexparse.out" 2>&1 \
    && cmp -s "$B/lexparse.out" tests/expected/cish-lexparse.out \
    && line ok "lexparse: tests/cish/lexparse.ci under cint run prints tests/expected/cish-lexparse.out" \
    || line bad "lexparse" "see $B/lexparse.out"

# 2. the committed build, and the same emitted C from the host's gcc and clang
sed 's#  user/bin/#  #' tests/expected/cish.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/cish, O/ubin/ctrlc and O/ubin/keyed are the bytes of tests/expected/cish.sha256" || line bad "bin" "see $B/bin.log"
for cc in gcc clang; do
    CI_CC=$cc CI_OUT=$B/$cc bash user/ci/build.sh cish > "$B/$cc.log" 2>&1 \
        && line ok "linux $cc: cish's emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/$cc.log"
done

# 3. the cish flavor and its image
make -s -j"$(nproc)" O="$B" FLAVORS=cish > "$B/make.log" 2>&1 \
    && line ok "build: the cish flavor for gcc and clang and its image (make FLAVORS=cish)" \
    || line bad "build: make FLAVORS=cish" "see $B/make.log"

# 4. Linux: cish from musl, gcc and clang on each session; then busybox ash, with the oracle
mkdir -p "$B/linux"
for s in $SESSIONS; do
    same=1
    for k in musl gcc clang; do
        b=$B/$k/cish
        [ $k = musl ] && b=$UB/cish
        python3 tools/check-cish.py linux "$B/cish/initrd.cpio" "tests/cish/$s.sh" "$B/linux/$s.$k" "$b"
        cmp -s "$B/linux/$s.$k" "tests/expected/cish-$s.out" || same=0
    done
    [ $same = 1 ] \
        && line ok "linux $s: cish (musl, gcc, clang) prints tests/expected/cish-$s.out, bytes and status, for tests/cish/$s.sh" \
        || line bad "linux $s: vs tests/expected/cish-$s.out" "differ (see $B/linux/$s.*)"
    if [ -n "$BB" ]; then
        python3 tools/check-cish.py linux "$B/cish/initrd.cpio" "tests/cish/$s.sh" "$B/linux/$s.ash" "$BB/busybox" sh
        cmp -s "$B/linux/$s.ash" "tests/expected/cish-$s.out" \
            && line ok "oracle $s: busybox ash prints the same bytes and status for tests/cish/$s.sh" \
            || line bad "oracle $s: busybox ash vs tests/expected/cish-$s.out" "see $B/linux/$s.ash"
        gate_want=$((gate_want + 1))
    else
        echo "SKIP  oracle $s: no busybox (CORE_ORACLE unset); tests/expected/cish-$s.out stands in"
    fi
done

python3 tools/check-cish.py refuse "$B/cish/initrd.cpio" tests/cish/refuse.txt "$B/linux/refuse.out" "$UB/cish" \
    > "$B/linux/refuse.log" 2>&1 \
    && cmp -s "$B/linux/refuse.out" tests/expected/cish-refuse.out \
    && line ok "refuse: every line of tests/cish/refuse.txt is refused by name, status 2, as tests/expected/cish-refuse.out" \
    || line bad "refuse" "see $B/linux/refuse.out"

# 4b. K-10 on Linux: ctrlc at cish from musl, gcc and clang, then at busybox ash with the oracle (no core file for
# Ctrl-\). ctrlc runs SHELL by its path, and busybox takes the applet sh from the name it runs under
ulimit -c 0
same=1
for k in musl gcc clang; do
    b=$B/$k/cish
    [ $k = musl ] && b=$UB/cish
    python3 tools/check-cish.py linux "$B/cish/initrd.cpio" /dev/null "$B/linux/ctrlc.$k" "$UB/ctrlc" "$b" bin
    cmp -s "$B/linux/ctrlc.$k" tests/expected/cish-ctrlc.out || same=0
done
[ $same = 1 ] \
    && line ok "linux ctrlc: Ctrl-C and Ctrl-\\ at cish (musl, gcc, clang) give the lines of tests/expected/cish-ctrlc.out" \
    || line bad "linux ctrlc: vs tests/expected/cish-ctrlc.out" "differ (see $B/linux/ctrlc.*)"
if [ -n "$BB" ]; then
    mkdir -p "$B/ash" && ln -sf "$BB/busybox" "$B/ash/sh"
    python3 tools/check-cish.py linux "$B/cish/initrd.cpio" /dev/null "$B/linux/ctrlc.ash" "$UB/ctrlc" "$B/ash/sh" bin
    cmp -s "$B/linux/ctrlc.ash" tests/expected/cish-ctrlc.out \
        && line ok "oracle ctrlc: Ctrl-C and Ctrl-\\ at busybox ash give the same lines" \
        || line bad "oracle ctrlc: busybox ash vs tests/expected/cish-ctrlc.out" "see $B/linux/ctrlc.ash"
    gate_want=$((gate_want + 1))
else
    echo "SKIP  oracle ctrlc: no busybox (CORE_ORACLE unset); tests/expected/cish-ctrlc.out stands in"
fi

# 4c. K-9 on Linux: keyed at cish from musl, gcc and clang in keyed's image, each logging what the terminal showed
python3 tools/mkcpio.py "$B/keyed.cpio" cish=$UB/cish keyed=$UB/keyed bin/ bin/cat=$UB/cat \
    kd/ kd/alpha=/dev/null kd/alps=/dev/null kd/beta/ > "$B/keyed.log" 2>&1
same=1
for k in musl gcc clang; do
    b=$B/$k/cish
    [ $k = musl ] && b=$UB/cish
    python3 tools/check-cish.py linux "$B/keyed.cpio" /dev/null "$B/linux/keyed.$k" "$UB/keyed" "$b" bin \
        "$B/linux/keyed.$k.log"
    python3 tools/check-cish.py screen "$B/linux/keyed.$k.log" "$B/linux/keyed.$k.screen"
    { cmp -s "$B/linux/keyed.$k" "$B/linux/keyed.musl" && cmp -s "$B/linux/keyed.$k.screen" "$B/linux/keyed.musl.screen"; } \
        || same=0
done
[ $same = 1 ] && cmp -s "$B/linux/keyed.musl" tests/expected/cish-keyed.out \
    && line ok "linux keyed: the line editor of cish (musl, gcc, clang) gives the lines of tests/expected/cish-keyed.out" \
    || line bad "linux keyed" "differ (see $B/linux/keyed.*)"
[ $same = 1 ] && cmp -s "$B/linux/keyed.musl.screen" tests/expected/cish-keyed.screen \
    && line ok "linux keyed: the terminal's last screen in the twin of tools/check-tiler.py is tests/expected/cish-keyed.screen" \
    || line bad "linux keyed: screen" "differ (see $B/linux/keyed.*.screen)"

# 5. Daphnis: the cish flavor on gcc and clang, one boot for each session, one with daphnis.ctrlc=1 (K-10) and one with
# daphnis.keyed=1 (K-9)
mkdir -p "$B/run"
printf '\004' > "$B/ctrlc.in"
python3 tools/mkcpio.py "$B/ctrlc.cpio" cish=$UB/cish ctrlc=$UB/ctrlc bin/ bin/cat=$UB/cat > "$B/ctrlc.log" 2>&1
for cc in gcc clang; do
    t=$B/run/ctrlc-$cc.txt
    (QEMU_TIMEOUT=120 INITRD=$B/ctrlc.cpio STDIN_FILE=$B/ctrlc.in MEM=128 APPEND=daphnis.ctrlc=1 \
        tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
    t=$B/run/keyed-$cc.txt
    (QEMU_TIMEOUT=120 INITRD=$B/keyed.cpio STDIN_FILE=$B/ctrlc.in MEM=128 APPEND=daphnis.keyed=1 \
        tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
done
for s in $BOOTS; do
    printf '\004' | cat "tests/cish/$s.sh" - > "$B/$s.in"
    for cc in gcc clang; do
        t=$B/run/$s-$cc.txt
        (QEMU_TIMEOUT=120 INITRD=$B/cish/initrd.cpio STDIN_FILE=$B/$s.in MEM=128 \
            tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
    done
done
wait
for s in $BOOTS; do
    for cc in gcc clang; do
        t=$B/run/$s-$cc.txt
        [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
            && line ok "boot $s $cc: QEMU exit status 33, nothing on stderr" \
            || line bad "boot $s $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
        python3 tools/check-cish.py daphnis "$t" 1 "$B/run/$s-$cc.block" > "$B/run/$s-$cc.cmp" 2>&1 \
            && cmp -s "$B/run/$s-$cc.block" "tests/expected/cish-$s.out" \
            && line ok "daphnis $s $cc: cish's block is the Linux bytes and status, tests/expected/cish-$s.out" \
            || line bad "daphnis $s $cc: cish's block vs Linux" "see $B/run/$s-$cc.block"
        grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
            && line ok "desync $s $cc: cish with other frames does not desync" || line bad "desync $s $cc" "see $t"
        cmp -s "$(serial_of $s)" "$t" \
            && line ok "serial $s $cc: the transcript equals $(serial_of $s)" \
            || line bad "serial $s $cc: vs $(serial_of $s)" "differ"
    done
done

for cc in gcc clang; do
    t=$B/run/ctrlc-$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot ctrlc $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot ctrlc $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
    python3 tools/check-cish.py daphnis "$t" 1 "$B/run/ctrlc-$cc.block" ctrlc > "$B/run/ctrlc-$cc.cmp" 2>&1 \
        && cmp -s "$B/run/ctrlc-$cc.block" tests/expected/cish-ctrlc.out \
        && line ok "daphnis ctrlc $cc: ctrlc's block at cish is its lines on Linux, tests/expected/cish-ctrlc.out" \
        || line bad "daphnis ctrlc $cc: ctrlc's block vs Linux" "see $B/run/ctrlc-$cc.block"
    grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
        && line ok "desync ctrlc $cc: ctrlc with other frames does not desync" || line bad "desync ctrlc $cc" "see $t"
    cmp -s tests/expected/cish-ctrlc.serial "$t" \
        && line ok "serial ctrlc $cc: the transcript equals tests/expected/cish-ctrlc.serial" \
        || line bad "serial ctrlc $cc: vs tests/expected/cish-ctrlc.serial" "differ"
done

for cc in gcc clang; do
    t=$B/run/keyed-$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot keyed $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot keyed $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
    python3 tools/check-cish.py daphnis "$t" 1 "$B/run/keyed-$cc.block" keyed > "$B/run/keyed-$cc.cmp" 2>&1 \
        && cmp -s "$B/run/keyed-$cc.block" "$B/linux/keyed.musl" \
        && line ok "daphnis keyed $cc: keyed's block at cish is its lines at cish on Linux" \
        || line bad "daphnis keyed $cc: keyed's block vs Linux" "see $B/run/keyed-$cc.block"
    grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
        && line ok "desync keyed $cc: keyed with other frames does not desync" || line bad "desync keyed $cc" "see $t"
    cmp -s tests/expected/cish-keyed.serial "$t" \
        && line ok "serial keyed $cc: the transcript equals tests/expected/cish-keyed.serial" \
        || line bad "serial keyed $cc: vs tests/expected/cish-keyed.serial" "differ"
done

# 6. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 3 minutes" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
