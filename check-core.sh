#!/usr/bin/env bash
# check-core.sh: the gate of the native core set (docs/specs/2026-11-06-c-core.md section 6), gate 13, on its own
# budget beside check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   bin: each committed O/ubin/TOOL (musl, static) is the bytes of tests/expected/core.sha256.
#   linux: each tool's emitted C builds with the host's gcc and clang (glibc, static); for each tool, the cases of
#   tests/core/TOOL.cases run under the committed build print tests/expected/core-TOOL.out, and the gcc and clang
#   builds print the same bytes.
#   oracle: with CORE_ORACLE naming the busybox tarball (DOS-3, unit 4b: the repository holds no busybox),
#   user/busybox/oracle.sh builds busybox-oracle (user/busybox/oracle.fragment) and each case's stdout and status
#   agree with busybox's, apart from the rows of tests/core/DIFFS.md (gate 1). Without it, SKIP: the committed
#   outputs stand in.
#   http (CT-5, BU-5a, D-57): O/ubin/fetch's fetches from a loopback HTTP/1.0 server serving the fixture tree print
#   tests/expected/core-fetch.http, and busybox-net's wget (built the same way, through tools/core-fetch-oracle.sh;
#   fetch's cases take it as their oracle too) fetches the same bytes with the same status; SKIP without it.
#   session: tests/core/session.sh under the committed cish, in a directory holding the core image (cish, /bin with
#   the native tools and no busybox, the fixture tree as /t, CT-3's tests/core/search as /s), prints
#   tests/expected/core-session.out.
#   daphnis: the cish flavor's kernel boots the core image on gcc and clang with the session as its input; cish's
#   block is the Linux bytes, the second run (other frames) does not desync, every transcript is
#   tests/expected/core.serial.
#   table (CT-5a): an image of 102 members (cish, t/ and 100 files) boots on gcc and clang and cish reads the last
#   file and the first; FS-4: an image of 302 members, past the old FILES of 256, boots too, cish reads its last
#   file and its first, and the entry table is 39 pool frames (before FS-4 it failed the boot by name, status 63).
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-core), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-core}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=240   # CT-5: 40 tools; 180 s held the 27 of CT-0 to CT-4
TOOLS=$(sed -n 's/^CORE_TOOLS := //p' Makefile)
ntools=$(echo $TOOLS | wc -w)
gate_want=$((19 + 2 * ntools))   # the PASS lines before the last one, without the oracle (CT-5: and http)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-core.sh: $*"; echo "RESULT: FAIL"; exit 1; }

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
BB=$(user/busybox/oracle.sh) || fail_exit "CORE_ORACLE: busybox did not build from $CORE_ORACLE (user/busybox/oracle.sh)"
ORACLE=${BB:+$BB/busybox-oracle}
echo "tools:  $TOOLS"
echo "oracle: ${ORACLE:-none}"

# CT-4: steps 3 to 5 need only the committed bytes, so they run from the start beside the builds and the cases
# (the budget holds the gate's wall time): the image, then the Linux session and both Daphnis boots
mkdir -p "$B/run"
printf '\004' | cat tests/core/session.sh - > "$B/session.in"
(
    make -s -j"$(nproc)" O="$B" FLAVORS=cish all "$B/core/initrd.cpio" > "$B/make.log" 2>&1
    echo $? > "$B/make.rc"
    [ "$(cat "$B/make.rc")" = 0 ] || exit 0
    python3 tools/check-cish.py linux "$B/core/initrd.cpio" tests/core/session.sh "$B/session.linux" \
        "$UB/cish" > "$B/session.log" 2>&1 &
    # the hang guard, not the speed bar: the session boots share the CPUs with the tool builds below, and the
    # C-2 block (BU-2b) took one run on 4 vCPUs past 120 s; the budget line still holds the wall time
    for cc in gcc clang; do
        t=$B/run/$cc.txt
        (QEMU_TIMEOUT=200 INITRD=$B/core/initrd.cpio STDIN_FILE=$B/session.in MEM=128 \
            tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$t" > "$t.rc") &
    done
    wait
) &
image_pid=$!

# 1. the committed builds, and the same emitted C from the host's gcc and clang
sed 's#  user/bin/#  #' tests/expected/core.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/{$TOOLS} are the bytes of tests/expected/core.sha256" || line bad "bin" "see $B/bin.log"
# one build.sh per tool and compiler, nproc at a time (CT-2: nine tools built one by one took 110 s of the budget)
mkdir -p "$B/logs"
for cc in gcc clang; do for t in $TOOLS; do echo "$cc $t"; done; done \
    | xargs -P "$(nproc)" -n 2 sh -c 'CI_CC=$1 CI_OUT=$0/$1 bash user/ci/build.sh "$2" > "$0/logs/$1-$2.log" 2>&1 || : > "$0/logs/$1-$2.bad"' "$B"
for cc in gcc clang; do
    cat "$B"/logs/"$cc"-*.log > "$B/$cc.log"
    ok=1
    for t in $TOOLS; do [ -f "$B/logs/$cc-$t.bad" ] && ok=0; done
    [ $ok = 1 ] && line ok "linux $cc: the tools' emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/$cc.log"
done

# 2. the cases of each tool: the committed bytes, the three builds, the oracle
mkdir -p "$B/cases"
oracle_for() { [ -n "$ORACLE" ] && [ -x "$ORACLE" ]; }
# CT-5, BU-5a: the oracle has no wget; busybox-net's wget (built beside it by user/busybox/oracle.sh) stands in for
# fetch through tools/core-fetch-oracle.sh
NET_ORACLE=${BB:+$BB/busybox-net}
# CT-5: the oracle has no `[` either: tools/core-bracket-oracle.sh runs its ash's builtin `[` (busybox's test_main)
oracle_of() { case "$1" in fetch) echo "$PWD/tools/core-fetch-oracle.sh" ;; bracket) echo "$PWD/tools/core-bracket-oracle.sh" ;; *) echo "$ORACLE" ;; esac; }
applet_of() { case "$1" in bracket) echo "$ORACLE" ;; fetch) echo "$NET_ORACLE" ;; *) echo "$1" ;; esac; }
# CT-3: the search tools run in their own tree, tests/core/search, so the listings of tests/core/tree stay as they were
tree_of() { case "$1" in grep|sort|uniq|cut|tr|cmp|sha256sum|md5sum) echo tests/core/search ;; *) echo tests/core/tree ;; esac; }
# CT-4: every run of every tool, nproc at a time (a run is one tool's cases under one build, or the oracle)
for t in $TOOLS; do
    dir=$(tree_of "$t")
    echo "$t musl $dir $UB/$t"
    echo "$t gcc $dir $B/gcc/$t"
    echo "$t clang $dir $B/clang/$t"
    if oracle_for; then echo "$t oracle $dir $(oracle_of "$t") $(applet_of "$t")"; fi
done | B=$B xargs -P "$(nproc)" -L 1 sh -c \
    'python3 tools/check-core.py cases "tests/core/$0.cases" "$2" "$B/cases/$0.$1" "$3" $4'
for t in $TOOLS; do
    cmp -s "$B/cases/$t.musl" "tests/expected/core-$t.out" \
        && line ok "cases $t: tests/core/$t.cases prints tests/expected/core-$t.out" \
        || line bad "cases $t: vs tests/expected/core-$t.out" "see $B/cases/$t.musl"
    same=1
    for cc in gcc clang; do
        cmp -s "$B/cases/$t.$cc" "$B/cases/$t.musl" || same=0
    done
    [ $same = 1 ] && line ok "builds $t: musl, gcc and clang print the same bytes for each case" \
        || line bad "builds $t" "differ (see $B/cases/$t.*)"
    if oracle_for; then
        python3 tools/check-core.py compare "tests/core/$t.cases" "$B/cases/$t.musl" "$B/cases/$t.oracle" \
            > "$B/cases/$t.compare" 2>&1 \
            && line ok "oracle $t: stdout and status agree with busybox, apart from tests/core/DIFFS.md" \
            || line bad "oracle $t" "see $B/cases/$t.compare"
        gate_want=$((gate_want + 1))
    else
        echo "SKIP  oracle $t: no busybox (CORE_ORACLE unset); tests/expected/core-$t.out stands in"
    fi
done

# 2b. CT-5, BU-5a, D-57: fetch over a loopback HTTP/1.0 server serving the fixture tree
python3 tools/check-core.py http tests/core/tree "$B/http.musl" "$UB/fetch"
cmp -s "$B/http.musl" tests/expected/core-fetch.http \
    && line ok "http: fetch's fetches from a loopback server print tests/expected/core-fetch.http" \
    || line bad "http: vs tests/expected/core-fetch.http" "see $B/http.musl"
if [ -n "$NET_ORACLE" ] && [ -x "$NET_ORACLE" ]; then
    python3 tools/check-core.py http tests/core/tree "$B/http.oracle" "$PWD/tools/core-fetch-oracle.sh" "$NET_ORACLE"
    cmp -s "$B/http.musl" "$B/http.oracle" \
        && line ok "oracle http: busybox-net's wget fetches the same bytes with the same status as fetch" \
        || line bad "oracle http" "see $B/http.musl, $B/http.oracle"
    gate_want=$((gate_want + 1))
else
    echo "SKIP  oracle http: no busybox-net (CORE_ORACLE unset); tests/expected/core-fetch.http stands in"
fi

# 3. the cish flavor's kernel and the core image
wait "$image_pid"
[ "$(cat "$B/make.rc" 2>/dev/null)" = 0 ] \
    && line ok "build: the cish flavor for gcc and clang and the core image" \
    || line bad "build: make FLAVORS=cish core/initrd.cpio" "see $B/make.log"

# 4. the session on Linux
cat "$B/session.log" 2>/dev/null
cmp -s "$B/session.linux" tests/expected/core-session.out \
    && line ok "session linux: cish and the native tools print tests/expected/core-session.out" \
    || line bad "session linux: vs tests/expected/core-session.out" "see $B/session.linux"

# 5. Daphnis: the core image on gcc and clang
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
    cmp -s tests/expected/core.serial "$t" \
        && line ok "serial $cc: the transcript equals tests/expected/core.serial" \
        || line bad "serial $cc: vs tests/expected/core.serial" "differ"
done

# 6. the file table (CT-5a): an image past 64 members; FS-4: an image past the old FILES of 256, the table in pool frames
mkdir -p "$B/table/f"
for i in $(seq 1 300); do echo "file $i" > "$B/table/f/f$i"; done
# shellcheck disable=SC2046
python3 tools/mkcpio.py "$B/table/wide.cpio" cish=$UB/cish t/ $(for i in $(seq 1 100); do echo "t/f$i=$B/table/f/f$i"; done)
# shellcheck disable=SC2046
python3 tools/mkcpio.py "$B/table/over.cpio" cish=$UB/cish t/ $(for i in $(seq 1 300); do echo "t/f$i=$B/table/f/f$i"; done)
printf 'cd t\nread x < f100; echo $x\nread x < f1; echo $x\n\004' > "$B/table/wide.in"
printf 'cd t\nread x < f300; echo $x\nread x < f1; echo $x\n\004' > "$B/table/over.in"
for cc in gcc clang; do
    (QEMU_TIMEOUT=120 INITRD=$B/table/wide.cpio STDIN_FILE=$B/table/wide.in MEM=128 \
        tools/run-qemu.sh "$B/$cc-cish/kernel32.elf" "$B/table/wide-$cc.txt" > "$B/table/wide-$cc.rc") &
done
(QEMU_TIMEOUT=120 INITRD=$B/table/over.cpio STDIN_FILE=$B/table/over.in MEM=128 \
    tools/run-qemu.sh "$B/gcc-cish/kernel32.elf" "$B/table/over.txt" > "$B/table/over.rc") &
wait
for cc in gcc clang; do
    t=$B/table/wide-$cc.txt
    [ "$(cat "$B/table/wide-$cc.rc")" = 33 ] \
        && [ "$(sed -n '/^daphnis: run cish pid 1$/{n;p;n;p;}' "$t")" = "$(printf 'file 100\nfile 1')" ] \
        && line ok "table $cc: an image of 102 members boots and cish reads its last file and its first" \
        || line bad "table $cc" "see $t"
done
t=$B/table/over.txt
[ "$(cat "$B/table/over.rc")" = 33 ] \
    && [ "$(sed -n '/^daphnis: run cish pid 1$/{n;p;n;p;}' "$t")" = "$(printf 'file 300\nfile 1')" ] \
    && grep -qx 'daphnis: fs tables 49 frames held' "$t" && grep -qx 'daphnis: pool frames free 16334 of 16383' "$t" \
    && line ok "table over: an image of 302 members, past the old FILES, boots; cish reads its last file and its first; the entry table is 39 pool frames (38 of 8 entries, 1 map) beside the descriptions' 10" \
    || line bad "table over" "status $(cat "$B/table/over.rc"), see $B/table/over.txt"

# 7. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
