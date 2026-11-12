#!/usr/bin/env bash
# check-build.sh: the gate of unit BU-4, cint builds inside Daphnis (docs/specs/2026-11-07-bu4-toolchain.md sections
# 2, 5 and 6), on its own budget beside check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   BU-4b: every file of user/cint/opt, the toolchain the image build writes to /home/opt/cint, is the bytes of
#   tests/expected/cint-opt.sha256 (DU-2; user/cint/build.sh and user/qbe/build.sh build them again).
#   BU-4g, on Linux: the pinned cib (user/ci/cib.ci, built through the toolchain by itself) builds msha and mci with
#   those tools, their paths moved to a Linux copy of the directory (every file's bytes as pinned but for the toolchain
#   file's paths); a
#   second build of each gives the same bytes at every stage; each program prints what the gcc (musl) and clang
#   (glibc) builds of user/ci/build.sh print, with their status. The stage digests are kept for the Daphnis leg (C1).
#   BU-4c, under Daphnis: tools/mkcintvol.sh builds the volume (its pin), opt/cint and the sources; the disk flavor
#   boots on gcc and clang with it at /home and tests/image/build.txt: cib builds msha and mci on the volume under the
#   disk grant and the session prints every stage's SHA-256, then the kernel runs each built program alone twice.
#   tools/check-build.py holds the stages to the Linux leg's (C1), the runs' output and status to Linux's (C2) and the
#   two runs' state digests to one (C3); both transcripts are tests/expected/build.serial; e2fsck finds the volume
#   clean.
#   Goal 4 (review B-7): cib builds the core set, cish and hdesk on Linux, and each core tool's tests/core cases give the
#   O/ubin build's output (fetch, which needs a server, and chmod, whose cases read files they made
#   unreadable, are left to check-core.sh); then, under KVM with daphnis.pool=max (hdesk's emit-qbe maps 66 MiB, past
#   the gate pool's 60 MiB quota), the disk flavor builds all 46 on the volume with tests/image/build-core.txt, and
#   each executable is the Linux build's, byte for byte. Without /dev/kvm that leg is one SKIP line.
#   Goal 5 (BU4-3 B), BU-4h1 on Linux: `cib --self` rebuilds cint from the pinned sources (user/cint/opt/src/compiler,
#   libcli.a); the rebuilt cint passes ready() and emits the compiler's, msha's and mci's trees byte-equal to the pinned
#   cint's; rebuilt again by itself it is a fixpoint (the executable and every stage). BU-4h2, under KVM with -m 1024
#   and daphnis.pool=max: the disk flavor boots with the 256 MiB volume (tools/mkcintvol.sh, its own pin) and
#   tests/image/build-self.txt: the session prints the quota (ulimit -v), cib --self prints each step's peak (wait4's
#   ru_maxrss: the child's peak of frames) and the rebuild's every stage, then the rebuilt cint emits the three trees;
#   every digest is the Linux leg's (C1 against BU-4h1, the trees the pinned cint's). Without /dev/kvm one SKIP line.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-build), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-build}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=1200
WATCHDOG=900
KVM_WATCHDOG=1500
SELF_WATCHDOG=1500
gate_want=23   # the PASS lines before the last one
PROGS="msha mci"
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-build.sh: $*"; echo "RESULT: FAIL"; exit 1; }

for t in cint gcc clang musl-gcc python3 sha256sum cmp timeout git qemu-system-x86_64 mke2fs debugfs e2fsck awk; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in $CORE; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)

# BU-4b: the pinned toolchain
(cd user/cint/opt && sha256sum --quiet -c "$OLDPWD/tests/expected/cint-opt.sha256") > "$B/pin.log" 2>&1 \
    && [ "$(find user/cint/opt -type f | wc -l)" = "$(wc -l < tests/expected/cint-opt.sha256)" ] \
    && line ok "pin: every file of user/cint/opt is the bytes of tests/expected/cint-opt.sha256, and no other file is there" \
    || line bad "pin: user/cint/opt" "see $B/pin.log"
grep -q "^qbe_sha256 $(sha256sum user/cint/opt/qbe | cut -d' ' -f1)$" user/cint/opt/cpu-qbe.toolchain \
    && grep -q "^executable_sha256 $(sha256sum user/cint/opt/cint | cut -d' ' -f1)$" user/cint/opt/cpu-qbe.toolchain \
    && line ok "pin: the toolchain file names the digests of its cint and its qbe" \
    || line bad "pin: cpu-qbe.toolchain" "a digest differs from its file's"

# BU-4g: the Linux leg
lin=$B/lin
cp -R user/cint/opt "$lin"
sed "s|/home/opt/cint|$lin|g" user/cint/opt/cpu-qbe.toolchain > "$lin/cpu-qbe.toolchain"
mkdir -p "$B/gcc" "$B/clang" "$B/q1" "$B/q2"
{ CI_OUT=$B/gcc user/ci/build.sh $PROGS \
    && CI_OUT=$B/clang CI_CC=clang user/ci/build.sh $PROGS; } > "$B/build.log" 2>&1 \
    && line ok "build: the gcc (musl) and clang (glibc) builds of $PROGS, by user/ci/build.sh" \
    || line bad "build: user/ci/build.sh" "see $B/build.log"
ok=1
for round in q1 q2; do
    for p in $PROGS; do
        timeout 120 "$lin/cib" -t "$lin/cpu-qbe.toolchain" "$B/$round/$p" "user/ci/$p.ci" > "$B/$round/$p.log" 2>&1 || ok=0
    done
done
[ $ok = 1 ] && line ok "cib: builds $PROGS twice with the pinned toolchain (emit-qbe, QBE, cint-as, cint ld), status 0" \
            || line bad "cib" "see $B/q1/*.log and $B/q2/*.log"
# stages DIR NAME: SHA-256 and path of the executable and every file cib left in NAME.cib, one line each
stages() { (cd "$1" && { sha256sum "$2"; find "$2.cib" -type f | LC_ALL=C sort | xargs sha256sum; }); }
ok=1
for p in $PROGS; do
    stages "$B/q1" "$p" > "$B/$p.stages" 2>/dev/null || ok=0
    stages "$B/q2" "$p" > "$B/$p.stages2" 2>/dev/null || ok=0
    cmp -s "$B/$p.stages" "$B/$p.stages2" || ok=0
done
[ $ok = 1 ] && line ok "stages: the second build's .ssa, .s, .o and executable are the first's, byte for byte ($(cat "$B"/*.stages | wc -l) files)" \
            || line bad "stages" "differ, see $B/*.stages and *.stages2"
# run DIR PROG: stdout, stderr and the status of DIR/PROG run in an empty directory
run() {
    rm -rf "$B/run"; mkdir "$B/run"
    (cd "$B/run" && timeout 60 "$1/$2" > "$B/out" 2> "$B/err" < /dev/null; echo "status $?" >> "$B/err")
    cat "$B/out" "$B/err"
}
for p in $PROGS; do
    run "$B/q1" "$p" > "$B/$p.q1.run"
    run "$B/gcc" "$p" > "$B/$p.gcc.run"
    run "$B/clang" "$p" > "$B/$p.clang.run"
    cmp -s "$B/$p.q1.run" "$B/$p.gcc.run" && cmp -s "$B/$p.q1.run" "$B/$p.clang.run" \
        && line ok "run $p: the cib build prints what the gcc and clang builds print, with their status ($(wc -c < "$B/$p.q1.run") bytes, $(tail -1 "$B/$p.q1.run"))" \
        || line bad "run $p" "see $B/$p.q1.run, .gcc.run and .clang.run"
done

# Goal 5, BU-4h1: cint rebuilds itself on Linux, then again with the rebuilt cint
# self_list DIR: in DIR, the SHA-256 of every file the session of tests/image/build-self.txt digests, in its order;
# the toolchain file's with its paths moved back to /home/opt/cint
self_list() {
    local LC_ALL=C
    (cd "$1" && for f in s/cint s/cint.toolchain s/cint.cib/e/MANIFEST.ref s/cint.cib/e.stage-0/* s/cint.cib/*.s \
        s/cint.cib/*.o s/cint.cib/m.a t/*/MANIFEST.ref t/*.stage-0/* t/*.stage-0/*/* t/*.stage-0/*/*/*; do
        if [ "$f" = s/cint.toolchain ]; then
            echo "$(sed "s|$lin|/home/opt/cint|g" "$f" | sha256sum | cut -d' ' -f1)  $f"
        elif [ -f "$f" ]; then sha256sum "$f"; fi
    done)
}
# self_emit CINT TOOLCHAIN DIR: CINT emits the compiler, msha and mci into DIR/t as the session does
self_emit() {
    mkdir -p "$3/t"
    "$1" emit-qbe --toolchain "$2" --root "$lin/src/compiler" --out "$3/t/comp" main.ci \
        && for p in msha mci; do "$1" emit-qbe --toolchain "$2" --root . --out "$3/t/$p" "user/ci/$p.ci" || return 1; done
}
ok=1
for d in self ref fix; do mkdir -p "$B/$d/s"; done
(cd "$B/self" && timeout 600 "$lin/cib" --self -t "$lin/cpu-qbe.toolchain" s/cint) > "$B/self.log" 2>&1 || ok=0
[ $ok = 1 ] && self_emit "$B/self/s/cint" "$B/self/s/cint.toolchain" "$B/self" >> "$B/self.log" 2>&1 || ok=0
self_emit "$lin/cint" "$lin/cpu-qbe.toolchain" "$B/ref" >> "$B/self.log" 2>&1 || ok=0
self_list "$B/self" > "$B/self.linux"
(cd "$B/ref" && export LC_ALL=C && for f in t/*/MANIFEST.ref t/*.stage-0/* t/*.stage-0/*/* t/*.stage-0/*/*/*; do if [ -f "$f" ]; then sha256sum "$f"; fi; done) > "$B/self.ref"
grep -q ' t/comp.stage-0/back_c.ssa$' "$B/self.ref" && cmp -s "$B/self.ref" <(grep '  t/' "$B/self.linux") || ok=0
[ $ok = 1 ] && line ok "self linux: cib --self rebuilds cint (emit-qbe, QBE, cint-as, cint ld, libcli.a); it passes ready() and emits the compiler's, msha's and mci's trees as the pinned cint does ($(wc -l < "$B/self.ref") files)" \
            || line bad "self linux" "see $B/self.log, $B/self.linux and $B/self.ref"
ok=1
(cd "$B/fix" && timeout 600 "$lin/cib" --self -t "$B/self/s/cint.toolchain" s/cint) > "$B/fix.log" 2>&1 || ok=0
(cd "$B/fix" && for f in s/cint s/cint.cib/e/MANIFEST.ref s/cint.cib/e.stage-0/* s/cint.cib/*.s s/cint.cib/*.o s/cint.cib/m.a; do sha256sum "$f"; done) > "$B/fix.stages" 2>/dev/null || ok=0
(cd "$B/self" && for f in s/cint s/cint.cib/e/MANIFEST.ref s/cint.cib/e.stage-0/* s/cint.cib/*.s s/cint.cib/*.o s/cint.cib/m.a; do sha256sum "$f"; done) > "$B/self.stages" 2>/dev/null || ok=0
[ $ok = 1 ] && cmp -s "$B/fix.stages" "$B/self.stages" \
    && line ok "self linux: rebuilt by the rebuilt cint, a fixpoint: the executable and every stage the same bytes ($(wc -l < "$B/self.stages") files)" \
    || line bad "self linux: fixpoint" "see $B/fix.log, $B/fix.stages against $B/self.stages"

# BU-4c: the Daphnis leg
{ tools/mkcintvol.sh "$B/vol.img" && tools/mkcintvol.sh "$B/self.img" 256M; } > "$B/mkcintvol.log" 2>&1 && (cd "$B" && sha256sum --quiet -c "$OLDPWD/tests/expected/cint-volume.sha256") >> "$B/mkcintvol.log" 2>&1 \
    && line ok "volume: tools/mkcintvol.sh builds opt/cint and the sources into the bytes of tests/expected/cint-volume.sha256 (128 MiB, and 256 MiB for goal 5)" \
    || line bad "volume: mkcintvol.sh" "see $B/mkcintvol.log"
make -s -j"$(nproc)" O="$B" FLAVORS=disk "$B/gcc-disk/kernel32.elf" "$B/clang-disk/kernel32.elf" "$B/build/initrd.cpio" > "$B/make.log" 2>&1 \
    && line ok "build: the disk flavor for gcc and clang, and the image with sha256sum" \
    || line bad "build: make FLAVORS=disk" "see $B/make.log"
# Goal 4, Linux: cib builds the core set, cish and hdesk; the core tools' cases
CORE=$(sed -n 's/^CORE_TOOLS := //p' Makefile)
mkdir -p "$B/core" "$B/cases"
ok=1
for t in $CORE cish hdesk; do
    timeout 120 "$lin/cib" -t "$lin/cpu-qbe.toolchain" "$B/core/$t" "user/ci/$t.ci" > "$B/core/$t.log" 2>&1 || ok=0
done
(cd "$B/core" && for t in $CORE cish hdesk; do sha256sum "$t"; done) > "$B/core.linux" 2>/dev/null || ok=0
[ $ok = 1 ] && line ok "core linux: cib builds the $(echo $CORE | wc -w) core tools, cish and hdesk with the pinned toolchain" \
            || line bad "core linux: cib" "see $B/core/*.log"
tree_of() { case "$1" in grep|sort|uniq|cut|tr|cmp|sha256sum|md5sum) echo tests/core/search ;; *) echo tests/core/tree ;; esac; }
ok=1 n=0
for t in $CORE; do
    case $t in fetch|chmod) continue ;; esac
    python3 tools/check-core.py cases "tests/core/$t.cases" "$(tree_of "$t")" "$B/cases/$t.gcc" "$UB/$t" > /dev/null 2>&1
    python3 tools/check-core.py cases "tests/core/$t.cases" "$(tree_of "$t")" "$B/cases/$t.qbe" "$B/core/$t" > /dev/null 2>&1
    if [ -s "$B/cases/$t.gcc" ] && cmp -s "$B/cases/$t.gcc" "$B/cases/$t.qbe"; then n=$((n + 1)); else ok=0; echo "      $t: cases differ"; fi
done
[ $ok = 1 ] && line ok "core linux: each of $n core tools built by cib gives the O/ubin build's output on its tests/core cases" \
            || line bad "core linux: cases" "see $B/cases"

mkdir -p "$B/run"
for cc in gcc clang; do
    cp "$B/vol.img" "$B/run/$cc.img"
    (QEMU_TIMEOUT=$WATCHDOG DISK=$B/run/$cc.img INITRD=$B/build/initrd.cpio STDIN_FILE=tests/image/build.txt \
        tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc.txt" > "$B/run/$cc.txt.rc") &
done
kvm=0
if [ -w /dev/kvm ]; then
    kvm=1
    for cc in gcc clang; do
        cp "$B/vol.img" "$B/run/$cc-core.img"
        (KVM=1 POOL=max MEM=512 QEMU_TIMEOUT=$KVM_WATCHDOG DISK=$B/run/$cc-core.img INITRD=$B/build/initrd.cpio \
            STDIN_FILE=tests/image/build-core.txt tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc-core.txt" \
            > "$B/run/$cc-core.txt.rc") &
    done
    cp "$B/self.img" "$B/run/self.img"
    (KVM=1 POOL=max MEM=1024 QEMU_TIMEOUT=$SELF_WATCHDOG DISK=$B/run/self.img INITRD=$B/build/initrd.cpio \
        STDIN_FILE=tests/image/build-self.txt tools/run-qemu.sh "$B/gcc-disk/kernel32.elf" "$B/run/self.txt" \
        > "$B/run/self.txt.rc") &
fi
wait
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    python3 tools/check-build.py "$t" "$B" tests/expected/cint-volume.sha256 $PROGS > "$B/$cc.cmp" 2>&1 \
        && line ok "daphnis $cc: cib built $PROGS on /home; C1 every stage is Linux's, C2 each runs as Linux's, C3 two runs one state" \
        || line bad "daphnis $cc" "see $B/$cc.cmp"
done
cmp -s "$B/run/gcc.txt" "$B/run/clang.txt" && cmp -s tests/expected/build.serial "$B/run/gcc.txt" \
    && line ok "serial: the gcc and clang transcripts equal tests/expected/build.serial" \
    || line bad "serial: vs tests/expected/build.serial" "differ"
# Goal 4, Daphnis: every executable built on the volume is the Linux build's
if [ $kvm = 1 ]; then
    ok=1
    for cc in gcc clang; do
        t=$B/run/$cc-core.txt
        [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^grant: 0$' "$t" || ok=0
        sed -n 's|^\([0-9a-f]\{64\}\)  \.\./out/\(.*\)$|\1  \2|p' "$t" > "$B/core.$cc"
        cmp -s "$B/core.$cc" "$B/core.linux" || ok=0
    done
    [ $ok = 1 ] && line ok "core daphnis: under KVM, gcc and clang kernels, cib builds all $(wc -l < "$B/core.linux") on /home, each the Linux build's bytes" \
                || line bad "core daphnis" "see $B/run/*-core.txt against $B/core.linux"
else
    echo "SKIP  core daphnis: no /dev/kvm; the 46 builds take more than an hour under TCG"
fi
# Goal 5, BU-4h2: cint's own rebuild inside Daphnis
if [ $kvm = 1 ]; then
    t=$B/run/self.txt
    grep -E '^[0-9a-f]{64}  ' "$t" > "$B/self.daphnis"
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^grant: 0$' "$t" && grep -q '^cib self: 0$' "$t" \
        && [ "$(grep -c '^emit [a-z]*: 0$' "$t")" = 3 ] && cmp -s "$B/self.daphnis" "$B/self.linux" \
        && line ok "self daphnis: under KVM, -m 1024, daphnis.pool=max: cib --self rebuilds cint on /home, every stage the Linux rebuild's (C1), and it emits the three trees as the pinned cint does ($(wc -l < "$B/self.daphnis") files)" \
        || line bad "self daphnis" "see $t against $B/self.linux"
    echo "      $(grep -m1 '^quota KiB:' "$t"); peaks KiB: $(sed -n 's/^cib: \(.*\) peak \([0-9]*\) KiB$/\1 \2/p' "$t" \
        | awk '{k=$1; v=$NF; if (k=="qbe"||k=="as") {if (v>m[k]) m[k]=v} else m[k]=v} END {printf "emit-qbe %d, qbe at most %d, as at most %d, ld %d", m["emit-qbe"], m["qbe"], m["as"], m["ld"]}')"
else
    echo "SKIP  self daphnis: no /dev/kvm; cint's own rebuild is a KVM gate (hazard 11)"
fi
e2fsck -fn "$B/run/gcc.img" > "$B/e2fsck.log" 2>&1 && e2fsck -fn "$B/run/clang.img" >> "$B/e2fsck.log" 2>&1 \
    && { [ $kvm = 0 ] || e2fsck -fn "$B/run/self.img" >> "$B/e2fsck.log" 2>&1; } \
    && line ok "e2fsck -fn finds the volumes QEMU left clean (gcc, clang, and goal 5's under KVM)" || line bad "e2fsck" "see $B/e2fsck.log"

[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under $BUDGET s" || line bad "time" "$elapsed s"
[ $kvm = 1 ] || gate_want=$((gate_want - 2))
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
