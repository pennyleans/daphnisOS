#!/usr/bin/env bash
# check-tiler.sh: the gate of stage W (docs/specs/2026-11-05-w-tiler.md section 5), on its own budget beside
# check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   W-1, on Linux: O/ubin/tiler (musl, static) is the bytes of tests/expected/tiler.sha256; it and
#   the same emitted C built by the host's gcc and clang (glibc, static) each draw every case of
#   tools/check-tiler.py (2x2, 3x2, 3x7, the mark, the face, the terminal's escapes of E-2, its scroll region, bold and colors of BU-3, a refusal) as its Python
#   does; one digest a case.
#   W-2 and W-3, under Daphnis: the tile flavor (src/main_tile.ci) boots on gcc and clang: mcifb fullscreen, then
#   `tiler --start mcifb`, then three mkeys clients with keys and chords typed through the QEMU monitor
#   (tools/sendkeys.py); tools/check-tiler.py --boot checks the client's surface, the screens, what each client
#   read and the focus moves, and every transcript is tests/expected/tile.serial.
#   W-4, under Daphnis: the desk flavor (src/main_desk.ci) boots on gcc and clang; once the tiler reports the shell's
#   first output (its prompt), `ls; ./doom --sealed; exit` is typed into the shell as one line; tools/check-tiler.py --desk checks the terminal's rows against doom.tics,
#   doom's tile against the last frame of a Linux run (1x) and the screen, and every transcript is
#   tests/expected/desk.serial.
#   AC-1a, under Daphnis: the desk flavor boots on gcc and clang with O/ubin/mlogin as its first process; its lines
#   (the uid calls, login's one-way door, the grant ceiling, grant_ask's refusals) are tests/expected/ac-mlogin.out.
#   KILL-Z: O/ubin/mzkill, the same way: a signal to an ended child not yet waited for is 0 and changes nothing
#   (it faulted the kernel), a running child still ends by SIGKILL; its lines are Linux's, tests/expected/k-mzkill.out.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-tiler), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-tiler}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=180   # the desk boot plays 350 tics in a tile: 100 s on the cloud, Arch slower under CI load
gate_want=39   # the PASS lines before the last one (27, +2 FS-R3 C: mstamp, +2 KF-3b: mfacts on gcc and clang, +2 GV-1a: mrevoke, +2 KILL-Z: mzkill on gcc and clang, +2 AC-T2: mexepath on gcc and clang, +2 RS-SURF: mresize on gcc and clang)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-tiler.sh: $*"; echo "RESULT: FAIL"; exit 1; }
# DS-3: the Doom port, its data and its pins come from freedoom-ci at doom.pin's commit (tools/doom/fetch.sh)
D=$(tools/doom/fetch.sh) || fail_exit "tools/doom/fetch.sh: no freedoom-ci at doom.pin's commit"
export DOOM_ROOT=$D
tiler() { # label checkfile binary
    python3 tools/check-tiler.py "$3" > "$2" 2>&1
    sed 's/^/  /' "$2" | grep -v '^  PASS\|^  digest' || true
    [ "$(grep -c '^PASS' "$2")" = 12 ] && ! grep -q '^FAIL' "$2" && line ok "$1" || line bad "$1" "see $2"
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
make -s -j"$(nproc)" O="$B" $(for p in tiler mlogin mperm mstamp mfacts mrevoke mzkill mexepath sleep mresize; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"

# 1. the committed build
sed 's#  user/bin/#  #' tests/expected/tiler.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/tiler is the bytes of tests/expected/tiler.sha256" || line bad "bin" "see $B/bin.log"
tiler "linux: O/ubin/tiler draws every case of tools/check-tiler.py as the Python does" "$B/musl.cmp" $UB/tiler

# 2. the same emitted C from the host's gcc and clang
for cc in gcc clang; do
    CI_CC=$cc CI_OUT=$B/$cc bash user/ci/build.sh tiler > "$B/$cc.log" 2>&1 \
        && line ok "linux $cc: the tiler's emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/$cc.log"
    tiler "linux $cc: the $cc build draws every case as the Python does" "$B/$cc.cmp" "$B/$cc/tiler"
done

# 3. one number a case on every build
grep -h '^digest' "$B/musl.cmp" > "$B/digests.musl"
same=1
for cc in gcc clang; do grep -h '^digest' "$B/$cc.cmp" | cmp -s - "$B/digests.musl" || same=0; done
[ $same = 1 ] && [ "$(wc -l < "$B/digests.musl")" = 9 ] \
    && line ok "digests: musl, gcc and clang give one digest for each of the 9 surfaces" \
    || line bad "digests" "differ across builds (see $B/*.cmp)"
sed 's/^/  /' "$B/digests.musl"

# 4. W-2 under Daphnis: the tile flavor on gcc and clang
make -s -j"$(nproc)" O="$B" FLAVORS="tile desk" > "$B/make.log" 2>&1 \
    && line ok "build: the tile and desk flavors for gcc and clang and their images (make FLAVORS=\"tile desk\")" \
    || line bad "build: make FLAVORS=\"tile desk\"" "see $B/make.log"
data="$D/data"
(cd "$data" && "$D/bin/doom" --sealed --headless --frame-out "$B/doom.frame" > "$B/linux-sealed.txt" 2>&1) \
    && cmp -s "$B/linux-sealed.txt" "$D/tests/expected/doom.tics" \
    && line ok "linux: bin/doom --sealed --headless plays tests/expected/doom.tics; its last frame is the desk's pin" \
    || line bad "linux: doom --sealed" "see $B/linux-sealed.txt"
mkdir -p "$B/run"
# W-3: a, b, c for client 0; Super+Right, then a, b, c for client 1; Super+Left, Super+Down, a, Super+q for client 2
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ ${#t} -le 100 ] || fail_exit "monitor socket path $t.mon is too long for a unix socket; set a shorter DAPHNIS_BUILD"
    (python3 tools/sendkeys.py "$t.mon" "$t" "tiler: start client 2 in tile 0,1" a,b,c \
        "tiler: client 0 in tile 0,0 ended" meta_l-right,a,b,c \
        "tiler: client 1 in tile 1,0 ended" meta_l-left,meta_l-down,a,meta_l-q > "$t.keys" 2>&1 &
     QEMU_TIMEOUT=60 INITRD=$B/tile/initrd.cpio MONITOR=$t.mon MEM=128 tools/run-qemu.sh "$B/$cc-tile/kernel32.elf" "$t" \
        > "$t.rc"; wait) &
    # W-4: after the shell's prompt, `ls; ./doom --sealed; exit` as one line, so no key is typed while a program
    # runs and every echo follows the prompt (W-4b)
    d=$B/run/desk-$cc.txt
    (SENDKEYS_WAIT=110 python3 tools/sendkeys.py "$d.mon" "$d" "tiler: desk shell first output" \
        l,s,semicolon,spc,dot,slash,d,o,o,m,spc,minus,minus,s,e,a,l,e,d,semicolon,spc,e,x,i,t,ret > "$d.keys" 2>&1 &
     QEMU_TIMEOUT=110 INITRD=$B/desk/initrd.cpio MONITOR=$d.mon MEM=128 tools/run-qemu.sh "$B/$cc-desk/kernel32.elf" "$d" \
        > "$d.rc"; wait) &
done
wait
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    python3 tools/check-tiler.py --boot "$t" > "$B/boot-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/boot-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/boot-$cc.cmp")" = 8 ] && ! grep -q '^FAIL' "$B/boot-$cc.cmp" \
        && line ok "tile $cc: mcifb fullscreen and in a tile, the frames and screens are the Python's; keys reach the focused client only" \
        || line bad "tile $cc" "see $B/boot-$cc.cmp"
    cmp -s tests/expected/tile.serial "$t" \
        && line ok "serial $cc: the transcript equals tests/expected/tile.serial" \
        || line bad "serial $cc: vs tests/expected/tile.serial" "differ"
done
for cc in gcc clang; do
    d=$B/run/desk-$cc.txt
    [ "$(cat "$d.rc")" = 33 ] && [ ! -s "$d.err" ] \
        && line ok "boot desk $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot desk $cc" "status $(cat "$d.rc"), stderr $(wc -c < "$d.err") bytes"
    python3 tools/check-tiler.py --desk "$d" "$B/doom.frame" "$data/e1m6.wad" "$D/tests/expected/doom.tics" > "$B/desk-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/desk-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/desk-$cc.cmp")" = 5 ] && ! grep -q '^FAIL' "$B/desk-$cc.cmp" \
        && line ok "desk $cc: sh on a pty in the terminal, doom --sealed from it in tile 1: the chain is doom.tics', the tile the Linux frame 1x, the screen the Python's" \
        || line bad "desk $cc" "see $B/desk-$cc.cmp"
    cmp -s tests/expected/desk.serial "$d" \
        && line ok "serial desk $cc: the transcript equals tests/expected/desk.serial" \
        || line bad "serial desk $cc: vs tests/expected/desk.serial" "differ"
done

# AC-1a (docs/specs/2026-11-08-ac-accounts.md section 5): the desk flavor's kernel with an image whose tiler is
# O/ubin/mlogin, so the probe is the first process and can become the desk: its lines are tests/expected/ac-mlogin.out
# FS-1 (ruling FSP-1 A, docs/superpowers/specs/2026-11-09-filesystem-security-intake.md): O/ubin/mperm boots the same
# way beside it: directory search and read by the account's bits, no uid 0 bypass, creator ownership; its lines are
# tests/expected/fs-mperm.out
python3 tools/mkcpio.py "$B/mlogin.cpio" tiler=$UB/mlogin > "$B/mlogin-cpio.log" 2>&1
python3 tools/mkcpio.py "$B/mperm.cpio" tiler=$UB/mperm > "$B/mperm-cpio.log" 2>&1
# FS-4 with FS-R3 C (docs/specs/2026-11-07-bu2-meta.md section 4.6): O/ubin/mstamp boots the same way: a file written
# second by a fresh program is not stamped earlier than one written first by a program that ran longer; its lines are
# tests/expected/fs-mstamp.out
python3 tools/mkcpio.py "$B/mstamp.cpio" tiler=$UB/mstamp > "$B/mstamp-cpio.log" 2>&1
# KF-3b (docs/specs/2026-11-11-kf-facts.md section 2): O/ubin/mfacts boots the same way: who sees a process record
# of facts(2, slot): the desk every one; a child that login made a user, itself and its own child, and its parent's
# slot as the bytes of a slot with no process; its lines are tests/expected/kf-mfacts.out
python3 tools/mkcpio.py "$B/mfacts.cpio" tiler=$UB/mfacts > "$B/mfacts-cpio.log" 2>&1
# GV-1a (docs/specs/2026-11-11-gv-revoke.md section 2a): O/ubin/mrevoke boots the same way: only the desk revokes;
# a revoke reaches a whole window and no other; the bits cannot be taken back without the prompt; a child forked
# later and an orphan are covered; its lines are tests/expected/gv-mrevoke.out
python3 tools/mkcpio.py "$B/mrevoke.cpio" tiler=$UB/mrevoke > "$B/mrevoke-cpio.log" 2>&1
# KILL-Z: O/ubin/mzkill signals an ended child it has not waited for (the kernel faulted on it), then a running
# one; its lines are Linux's, tests/expected/k-mzkill.out
python3 tools/mkcpio.py "$B/mzkill.cpio" tiler=$UB/mzkill > "$B/mzkill-cpio.log" 2>&1
# AC-T2: O/ubin/mexepath boots the same way with /bin/sleep beside it and reads FBIO_TILE_INFO kinds 13 and 14 (the
# program a window's process runs, as loaded) beside kinds 0 and 1's comm: tests/expected/ac-mexepath.out
python3 tools/mkcpio.py "$B/mexepath.cpio" tiler=$UB/mexepath bin/ bin/sleep=$UB/sleep > "$B/mexepath-cpio.log" 2>&1
# RS-SURF: O/ubin/mresize is the desk and one pixel client; the client takes new sizes after its first map
# (munmap, FBIO_TILE_WANT, mmap) and the screen is read back at each step: tests/expected/rs-mresize.out
python3 tools/mkcpio.py "$B/mresize.cpio" tiler=$UB/mresize > "$B/mresize-cpio.log" 2>&1
for cc in gcc clang; do
    for p in mlogin mperm mstamp mfacts mrevoke mzkill mexepath mresize; do
        m=$B/run/$p-$cc.txt
        (MODE=640x480 QEMU_TIMEOUT=60 INITRD=$B/$p.cpio MEM=128 tools/run-qemu.sh "$B/$cc-desk/kernel32.elf" "$m" > "$m.rc") &
    done
done
wait
for cc in gcc clang; do
    m=$B/run/mlogin-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mlogin:' "$m")" = "$(cat tests/expected/ac-mlogin.out)" ] \
        && line ok "accounts $cc: mlogin's 20 lines are tests/expected/ac-mlogin.out (login's door, the ceiling, the uid calls)" \
        || line bad "accounts $cc: mlogin vs tests/expected/ac-mlogin.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mperm-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mperm:' "$m")" = "$(cat tests/expected/fs-mperm.out)" ] \
        && line ok "permissions $cc: mperm's lines are tests/expected/fs-mperm.out (search, directory read, no uid 0 bypass)" \
        || line bad "permissions $cc: mperm vs tests/expected/fs-mperm.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mstamp-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mstamp:' "$m")" = "$(cat tests/expected/fs-mstamp.out)" ] \
        && line ok "stamps $cc: mstamp's 12 lines are tests/expected/fs-mstamp.out (FS-R3 C: one time for stamps, a later file never earlier)" \
        || line bad "stamps $cc: mstamp vs tests/expected/fs-mstamp.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mfacts-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mfacts:' "$m")" = "$(cat tests/expected/kf-mfacts.out)" ] \
        && line ok "process records $cc: mfacts's 33 lines are tests/expected/kf-mfacts.out (a child reads its parent's slot as an empty one; another user's too; a Parent and the desk see all)" \
        || line bad "process records $cc: mfacts vs tests/expected/kf-mfacts.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mrevoke-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mrevoke:' "$m")" = "$(cat tests/expected/gv-mrevoke.out)" ] \
        && line ok "revoke $cc: mrevoke's 34 lines are tests/expected/gv-mrevoke.out (the desk alone; a whole window and no other; no way back without the prompt; a later child; an orphan)" \
        || line bad "revoke $cc: mrevoke vs tests/expected/gv-mrevoke.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mzkill-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mzkill:' "$m")" = "$(cat tests/expected/k-mzkill.out)" ] \
        && line ok "kill $cc: mzkill's lines are tests/expected/k-mzkill.out (a signal to an ended child is 0 and changes nothing, as on Linux)" \
        || line bad "kill $cc: mzkill vs tests/expected/k-mzkill.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mexepath-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mexepath:' "$m")" = "$(cat tests/expected/ac-mexepath.out)" ] \
        && line ok "image path $cc: mexepath's lines are tests/expected/ac-mexepath.out (kinds 13 and 14 name the program as loaded; prctl moves only the comm)" \
        || line bad "image path $cc: mexepath vs tests/expected/ac-mexepath.out" "status $(cat "$m.rc"), see $m"
done

for cc in gcc clang; do
    m=$B/run/mresize-$cc.txt
    [ "$(cat "$m.rc")" = 33 ] && [ "$(grep -a '^mresize:' "$m")" = "$(cat tests/expected/rs-mresize.out)" ] \
        && line ok "resize $cc: mresize's lines are tests/expected/rs-mresize.out (a placed client takes a new size after its map; the old picture until its first frame)" \
        || line bad "resize $cc: mresize vs tests/expected/rs-mresize.out" "status $(cat "$m.rc"), see $m"
done

# 5. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 3 minutes" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
