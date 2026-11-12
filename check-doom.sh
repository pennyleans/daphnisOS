#!/usr/bin/env bash
# check-doom.sh: the gate of the sealed run (R-2d, docs/specs/2026-11-05-r-desync.md section 7), on its own
# budget beside check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   Track 1 on Linux: freedoom-ci's bin/doom, and the same emitted C built by the host's gcc and clang
#   (glibc, static), play `doom --sealed --headless` to tests/expected/doom.tics; the canary desyncs.
#   Daphnis: the doom flavor (src/main_doom.ci) boots with tests/image/churn.txt as its serial input, on gcc,
#   clang and, with grub-mkrescue, each through GRUB: `doom --sealed` alone, the shell's churn (cish, DOS-3) then
#   `./doom --sealed` as its child, `doom --sealed --canary`, then `doom` unsealed; freedoom-ci's tools/check-doom.py
#   --sealed checks the chains and the surfaces, freedoom-ci's tools/check-doom.py checks the unsealed run against
#   tests/expected/doomref.txt (moved here from check.sh, R-2c), and every transcript is tests/expected/doom.serial.
#   P-3: each leg boots with a fresh copy of the test volume of tools/mkdisk.sh (its pin checked first) on /home,
#   and the churn writes there through `./grant disk` (cp, mkdir, rm); the chains are the same, the volume's
#   digest at the end is in doom.serial (one digest on every leg), and e2fsck -fn finds the volume clean.
#   N-4: each leg boots with virtio-net on QEMU's user network attached as well (src/main_doom.ci does not
#   drive it: the pool's headroom); the churn's `./fetch` has no net grant, so its socket is -EACCES
#   (`fetch: socket: Permission denied`, status 1); the chains are the same.
#   G-1: the live flavor (src/main_live.ci) boots on gcc and clang with the QEMU monitor open; the gate types
#   a script once `doom --live` has started (forward held, a turn on the keys and one on the mouse, Ctrl and
#   the left button, Esc), and tools/check-live.py checks the player moved, turned and fired. Not pinned.
#   G-4: the live run records to the volume under `grant disk` and replays itself at its end; `doom --sealed
#   --demo` then reads the record back and must print the live run's chain and end in its pose.
#   AU-5, gate 6 (docs/specs/2026-11-06-au-audio.md section 6): `doom --sealed --sound sfx.wad --sound-ref` with 3
#   and 8 channels prints the reference tool's steptable line and its 11,025 Hz mix digest per tic
#   (tests/expected/doomref-sfx3.txt, doomref-sfx8.txt), and its other lines are tests/expected/doom.tics; the
#   steptable is floor(2^((i + 896) / 64)), checked in integers; the 48 kHz stream of `--sound-out` is the pin of
#   tests/expected/doom-sfx48.sha256, its chain doom.tics; the gcc and clang builds give the same bytes.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-doom), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-doom}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=360
WATCHDOG=240   # one boot plays four runs of 350 tics: about 70 s alone under TCG, the legs boot together
# the PASS lines before the last one, the GRUB legs left out; they add iso_pass, or one SKIP line instead
gate_want=34
iso_pass=11
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-doom.sh: $*"; echo "RESULT: FAIL"; exit 1; }
# DS-3: the Doom port, its data and its pins come from freedoom-ci at doom.pin's commit (tools/doom/fetch.sh)
D=$(tools/doom/fetch.sh) || fail_exit "tools/doom/fetch.sh: no freedoom-ci at doom.pin's commit"
export DOOM_ROOT=$D
sealed() { # label checkfile S C transcript [frame]
    python3 "$D/tools/check-doom.py" --sealed "$3" "$4" "$5" "$D/tests/expected/doom.tics" "$D/data/e1m6.wad" ${6:+--frame "$6"} > "$2" 2>&1 \
        && line ok "$1" || line bad "$1" "see $2"
}

command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy python3 sha256sum cmp timeout git mke2fs debugfs e2fsck; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"

# 1. the bundle: the client, the WAD (its demo is a lump) and the engine's tables are the pinned bytes
(cd "$D" && sha256sum --quiet -c tests/expected/doom.sha256) > "$B/bundle.log" 2>&1 \
    && line ok "bundle: bin/doom, the WAD and the tables are the bytes of tests/expected/doom.sha256" \
    || line bad "bundle" "see $B/bundle.log"
tools/mkdisk.sh "$B/disk.img" > "$B/mkdisk.log" 2>&1 && (cd "$B" && sha256sum --quiet -c "$OLDPWD/tests/expected/disk.sha256") >> "$B/mkdisk.log" 2>&1 \
    && line ok "volume: tools/mkdisk.sh builds the test volume, the pin of tests/expected/disk.sha256" \
    || line bad "volume: mkdisk.sh and its pin" "see $B/mkdisk.log"

# 2. Track 1 on Linux, headless
data="$D/data"
(cd "$data" && "$D/bin/doom" --sealed --headless --frame-out "$B/doom.frame" > "$B/run/linux-sealed.txt" 2>&1)
sealed "linux: bin/doom --sealed --headless plays tests/expected/doom.tics" "$B/linux-sealed.cmp" 1 0 "$B/run/linux-sealed.txt"
(cd "$data" && "$D/bin/doom" --sealed --canary --headless > "$B/run/linux-canary.txt" 2>&1)
sealed "linux: bin/doom --sealed --canary desyncs at tic 1 and every tic after" "$B/linux-canary.cmp" 0 1 "$B/run/linux-canary.txt"
# R-2a to R-2c, unsealed: the level's counts and every tic's player words, random indexes and frame digests are
# the reference tool's (tests/expected/doomref.txt); its last frame is the one the Daphnis surfaces must show
(cd "$data" && "$D/bin/doom" --headless --frame-out "$B/doom-ref.frame" > "$B/run/linux-doom.txt" 2>&1) \
    && python3 "$D/tools/check-doom.py" "$B/run/linux-doom.txt" "$D/tests/expected/doomref.txt" "$D/data/e1m6.wad" > "$B/linux-doom.cmp" 2>&1 \
    && line ok "linux: bin/doom plays 350 tics whose player words, random indexes and frame digests equal the reference tool's" \
    || line bad "linux: doom vs tests/expected/doomref.txt" "see $B/linux-doom.cmp"
for cc in gcc clang; do
    DOOM_CC=$cc DOOM_OUT=$B/doom-$cc bash "$D/src/build.sh" > "$B/doom-$cc.log" 2>&1 \
        && line ok "linux $cc: the doom program's emitted C builds with the host's $cc (glibc, static, -O2)" \
        || line bad "linux $cc: build" "see $B/doom-$cc.log"
    (cd "$data" && "$B/doom-$cc" --sealed --headless > "$B/run/linux-$cc.txt" 2>&1)
    sealed "linux $cc: the $cc build plays tests/expected/doom.tics" "$B/linux-$cc.cmp" 1 0 "$B/run/linux-$cc.txt"
done

# 2b. AU-5, gate 6: the sound. The 11,025 Hz mix per tic is the reference tool's; the sound moves no chain line.
sound_lines() { grep '^doom: sound steptable \|^doom: tic [0-9]* audio sha256 ' "$1" | sed 's/^doom: /ref /'; }
other_lines() { grep -v '^doom: sound \|^doom: tic [0-9]* audio sha256 ' "$1"; }
for n in 3 8; do
    t=$B/run/linux-sfx$n.txt
    (cd "$data" && "$D/bin/doom" --sealed --headless --sound sfx.wad --sound-ref --channels $n > "$t" 2>&1)
    sound_lines "$t" | cmp -s - "$D/tests/expected/doomref-sfx$n.txt" \
        && line ok "sound $n: doom --sound-ref with $n channels prints tests/expected/doomref-sfx$n.txt, the reference tool's steptable and 350 tic mix digests" \
        || line bad "sound $n: vs tests/expected/doomref-sfx$n.txt" "differ"
    other_lines "$t" > "$t.other"
    sealed "sound $n: the run's other lines play tests/expected/doom.tics: the sound moves no state" "$B/linux-sfx$n.cmp" 1 0 "$t.other"
done
python3 -c '
import sys
v = [int(w) for w in open(sys.argv[1]).read().split("\n")[0].split()[3:]]
def fl(k):   # the largest y with y ** 64 <= 2 ** k
    lo, hi = 1, 1 << 20
    while lo < hi:
        m = (lo + hi + 1) // 2
        lo, hi = (m, hi) if m ** 64 <= 2 ** k else (lo, m - 1)
    return lo
sys.exit(0 if len(v) == 256 and all(v[i] == fl(i + 896) for i in range(256)) else 1)' "$D/tests/expected/doomref-sfx8.txt" \
    && line ok "sound: the steptable line is floor(2^((i + 896) / 64)) for i = 0 to 255, in integers" \
    || line bad "sound: steptable" "not the formula"
t=$B/run/linux-sfx48.txt
(cd "$data" && "$D/bin/doom" --sealed --headless --sound sfx.wad --sound-out "$B/sfx48.pcm" > "$t" 2>&1)
other_lines "$t" > "$t.other"
(cd "$B" && sha256sum --quiet -c "$D/tests/expected/doom-sfx48.sha256") > "$B/sfx48.log" 2>&1 \
    && python3 "$D/tools/check-doom.py" --sealed 1 0 "$t.other" "$D/tests/expected/doom.tics" "$D/data/e1m6.wad" >> "$B/sfx48.log" 2>&1 \
    && [ "$(wc -c < "$B/sfx48.pcm")" = 1920000 ] \
    && line ok "sound 48k: the 48 kHz stream of --sound-out is 480,000 frames, the pin of tests/expected/doom-sfx48.sha256, and the run plays tests/expected/doom.tics" \
    || line bad "sound 48k" "see $B/sfx48.log"
for cc in gcc clang; do
    (cd "$data" && "$B/doom-$cc" --sealed --headless --sound sfx.wad --sound-ref --channels 8 > "$B/run/linux-$cc-sfx8.txt" 2>&1 \
        && "$B/doom-$cc" --sealed --headless --sound sfx.wad --sound-out "$B/sfx48-$cc.pcm" > /dev/null 2>&1)
    sound_lines "$B/run/linux-$cc-sfx8.txt" | cmp -s - "$D/tests/expected/doomref-sfx8.txt" && cmp -s "$B/sfx48-$cc.pcm" "$B/sfx48.pcm" \
        && line ok "sound $cc: the $cc build's 11,025 Hz digests and 48 kHz stream are the committed build's" \
        || line bad "sound $cc" "differ"
done

# 3. Daphnis: the doom flavor, gcc and clang, and through GRUB when grub-mkrescue is here
make -s -j"$(nproc)" O="$B" FLAVORS="doom live" > "$B/make.log" 2>&1 \
    && line ok "build: the doom and live flavors for gcc and clang and their image (make FLAVORS=\"doom live\")" \
    || line bad "build: make FLAVORS=\"doom live\"" "see $B/make.log"
legs="gcc clang"
if command -v grub-mkrescue >/dev/null && command -v xorriso >/dev/null; then
    iso_ran=1
    ok=1
    for cc in gcc clang; do
        tools/build-iso.sh "$B/$cc-doom/kernel.elf" "$B/$cc-doom/daphnis.iso" "$B/doom/initrd.cpio" >> "$B/iso.log" 2>&1 || ok=0
    done
    [ $ok = 1 ] && line ok "iso: daphnis.iso of the doom flavor for gcc and clang, the image as the GRUB module" \
                || line bad "iso: build-iso.sh" "see $B/iso.log"
    legs="gcc clang gcc-iso clang-iso"
else
    iso_ran=0
    skip "iso: grub-mkrescue and xorriso are not both on PATH; the GRUB boots of the doom flavor did not run"
fi
for leg in $legs; do
    cc=${leg%-iso}
    image=$B/$cc-doom/kernel32.elf
    [ "$leg" != "$cc" ] && image=$B/$cc-doom/daphnis.iso
    cp "$B/disk.img" "$B/run/$leg.img"
    (QEMU_TIMEOUT=$WATCHDOG STDIN_FILE=tests/image/churn.txt INITRD=$B/doom/initrd.cpio MEM=128 DISK=$B/run/$leg.img NET=user \
        tools/run-qemu.sh "$image" "$B/run/$leg.txt" > "$B/run/$leg.txt.rc") &
done
wait
for leg in $legs; do
    t=$B/run/$leg.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $leg: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $leg" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    sed -n '/^daphnis: run doom pid 4 /,$p' "$t" > "$t.ref"   # the unsealed run and the lines after it
    python3 "$D/tools/check-doom.py" "$t.ref" "$D/tests/expected/doomref.txt" "$D/data/e1m6.wad" --frame "$B/doom-ref.frame" > "$B/$leg-ref.cmp" 2>&1 \
        && line ok "doom $leg: the unsealed run's level counts and every tic's player words, random indexes and frame digest equal the reference tool's, H_0 is the host's digest of the WAD and the demo, the surface is the last frame 2x" \
        || line bad "doom $leg: unsealed vs tests/expected/doomref.txt" "see $B/$leg-ref.cmp"
    sealed "doom $leg: two sealed runs (alone; after the churn, the shell's child) play tests/expected/doom.tics, the canary desyncs, the surfaces are the last frame 2x, the pool is whole" \
        "$B/$leg.cmp" 2 1 "$t" "$B/doom.frame"
    cmp -s tests/expected/doom.serial "$t" \
        && line ok "serial $leg: the transcript equals tests/expected/doom.serial" \
        || line bad "serial $leg: vs tests/expected/doom.serial" "differ"
    e2fsck -fn "$B/run/$leg.img" > "$B/$leg-fsck.log" 2>&1 \
        && line ok "volume $leg: e2fsck -fn finds the volume the churn wrote clean" \
        || line bad "volume $leg: e2fsck -fn" "see $B/$leg-fsck.log"
done

# 3b. G-1, live play: the live flavor on gcc and clang, a key and mouse script typed through the monitor; G-4:
# each leg with a fresh copy of the test volume, the record written there, then replayed sealed from it
for cc in gcc clang; do
    t=$B/run/live-$cc.txt
    cp "$B/disk.img" "$B/run/live-$cc.img"
    [ ${#t} -le 100 ] || fail_exit "monitor socket path $t.mon is too long for a unix socket; set a shorter DAPHNIS_BUILD"
    (python3 tools/sendkeys.py "$t.mon" "$t" "doom: live start" "sendkey up 2500,sendkey left 600,mouse_move 60 0,ctrl,mouse_button 1,mouse_button 0,ctrl,esc" > "$t.keys" 2>&1 &
     QEMU_TIMEOUT=120 INITRD=$B/doom/initrd.cpio MONITOR=$t.mon MEM=128 DISK=$B/run/live-$cc.img tools/run-qemu.sh "$B/$cc-live/kernel32.elf" "$t" > "$t.rc"; wait) &
done
wait
for cc in gcc clang; do
    t=$B/run/live-$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot live $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot live $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes; keys: $(tr '\n' ' ' < "$t.keys")"
    python3 tools/check-live.py "$t" > "$B/live-$cc.cmp" 2>&1 \
        && line ok "live $cc: doom --live from the keyboard and mouse: the player moved, turned and fired at 35 Hz, Esc ended the run; its record on /home replays to its chain and pose, sealed" \
        || line bad "live $cc" "see $B/live-$cc.cmp"
done

# 4. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 6 minutes" || line bad "time" "$elapsed s"
want_total=$((gate_want + iso_ran * iso_pass)); want_skips=$((1 - iso_ran))
[ "$passes" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $iso_pass with the GRUB legs)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
