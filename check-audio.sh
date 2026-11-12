#!/usr/bin/env bash
# check-audio.sh: gates 1, 2, 4 and 5 of stage AU (docs/specs/2026-11-06-au-audio.md section 6), the HDA driver and
# /dev/dsp, on its own budget beside check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   On Linux: O/ubin/atone (musl, static) is the bytes of tests/expected/atone.sha256; `atone --out`
#   writes atone's signal (tools/check-audio.py signal), and the chain of those bytes is the stream line of
#   tests/expected/audio.digests.
#   Under Daphnis: the cish flavor boots on gcc and clang with an image of cish, grant and atone, QEMU's intel-hda
#   and hda-output, and the wav backend at 48,000 Hz; cish runs `./grant disk,audio ./atone`, then `./atone`.
#   Both runs (pid 1, and pid 2 on other frames) print the hda line, the stream line of tests/expected/audio.digests
#   and, for atone without the grant, error 13 (EACCES). The capture, every all-zero frame removed, is the bytes of
#   the kernel's `audio: mix nonzero` lines (tools/check-audio.py wav). A gcc boot without the device prints no
#   `audio:` line and has no /dev/dsp: atone gets error 2 (ENOENT), with the grant and without.
#   AU-5: the image also holds doom and its bundle with sfx.wad, and cish then runs `./grant disk,audio ./doom
#   --sealed --headless --sound sfx.wad`: its 48 kHz stream closes with the chain of the Linux build's --sound-out
#   file, its capture is in the wav check with atone's, and its sealed lines are tests/expected/doom.tics, in both
#   runs; without the device doom says it has no /dev/dsp and plays the same chain, silent.
#   The device boots run under -icount (shift 0, sleep off): QEMU's hda-output and its wav backend then advance on
#   the guest's instruction count, so the capture is the same bytes on every host and every run. On QEMU's real-time
#   clock a busy host makes the backend late, and hda-output drops the 8 KiB it holds (QEMU trace event
#   hda_audio_overrun; `-D FILE -trace hda_audio_overrun` shows it): the capture then lacks up to 2,048 frames of
#   the mix, the flake of 2026-11-07. KVM=1 boots under KVM (on Arch), on real time, without -icount.
#   Cost: the seconds of the boots are printed (`cost:` lines, not gated).
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-audio), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-audio}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=240   # -icount costs about 30 s of TCG on a 4-core box (180 s before)
gate_want=25   # the PASS lines before the last one
want=$(cat tests/expected/audio.digests)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-audio.sh: $*"; echo "RESULT: FAIL"; exit 1; }
# DS-3: the Doom port, its data and its pins come from freedoom-ci at doom.pin's commit (tools/doom/fetch.sh)
D=$(tools/doom/fetch.sh) || fail_exit "tools/doom/fetch.sh: no freedoom-ci at doom.pin's commit"
export DOOM_ROOT=$D
ms() { date +%s%N | cut -c1-13; }
cost() { # label start_ms
    local t=$(( $(ms) - $2 ))
    printf 'cost: %s %d.%03d s\n' "$1" $((t / 1000)) $((t % 1000))
}

for t in cint gcc clang as ld objcopy qemu-system-x86_64 python3 sha256sum timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in atone cish grant; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"

# 1. Linux: the committed build, its signal and its chain
sed 's#  user/bin/#  #' tests/expected/atone.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: O/ubin/atone is the bytes of tests/expected/atone.sha256" || line bad "bin" "see $B/bin.log"
"$UB"/atone --out "$B/atone.pcm" > "$B/atone.out" 2>&1
python3 tools/check-audio.py signal "$B/atone.pcm" > "$B/signal.cmp" 2>&1 && grep -qx 'atone: frames 96000' "$B/atone.out" \
    && line ok "linux signal: atone --out writes 96,000 frames of its signal, none silent (tools/check-audio.py)" \
    || line bad "linux signal" "$(cat "$B/signal.cmp" "$B/atone.out" | tr '\n' ' ')"
[ "$(python3 tools/check-audio.py stream "$B/atone.pcm")" = "$want" ] \
    && line ok "linux receipt: the chain of atone's file is the stream line of tests/expected/audio.digests" \
    || line bad "linux receipt" "$(python3 tools/check-audio.py stream "$B/atone.pcm")"
(cd "$D/data" && "$D/bin/doom" --sealed --headless --sound sfx.wad --sound-out "$B/doom.pcm" > "$B/doom-linux.txt" 2>&1) \
    && [ "$(wc -c < "$B/doom.pcm")" = 1920000 ] \
    && line ok "linux doom: doom --sound-out writes 480,000 frames (350 tics at 48 kHz)" || line bad "linux doom" "see $B/doom-linux.txt"
want_doom=$(python3 tools/check-audio.py stream "$B/doom.pcm")

# 2. Daphnis: the cish flavor on gcc and clang, an image of cish, grant and atone
make -s -j"$(nproc)" O="$B" FLAVORS=cish CINT_TOOLCHAIN="$CINT_TOOLCHAIN" > "$B/make.log" 2>&1 \
    && line ok "build: the cish flavor for gcc and clang (make FLAVORS=cish)" \
    || { line bad "build: make FLAVORS=cish" "see $B/make.log"; echo "RESULT: FAIL"; exit 1; }
d="$D/data"
python3 tools/mkcpio.py "$B/audio.cpio" cish=$UB/cish grant=$UB/grant atone=$UB/atone doom="$D/bin/doom" \
    e1m6.wad=$d/e1m6.wad tables.bin=$d/tables.bin info.bin=$d/info.bin sfx.wad=$d/sfx.wad > "$B/cpio.log" 2>&1 \
    && line ok "image: cish, grant, atone, doom and its bundle with sfx.wad (tools/mkcpio.py)" || line bad "image" "see $B/cpio.log"
printf './grant disk,audio ./atone\n./atone\n./grant disk,audio ./doom --sealed --headless --sound sfx.wad\n\004' > "$B/audio.in"
t0=$(ms)
clock="-icount shift=0,sleep=off"
[ "${KVM:-0}" = 1 ] && clock=""
for cc in gcc clang none; do
    k=$cc icount=$clock dev="-device intel-hda -device hda-output,audiodev=a0,mixer=off"
    dev="$dev -audiodev wav,id=a0,path=$B/run/$cc.wav,out.frequency=48000,out.format=s16,out.channels=2,out.fixed-settings=on"
    [ $cc = none ] && { k=gcc dev="" icount=""; }
    t=$B/run/$cc.txt
    (QEMU_EXTRA="$dev $icount" QEMU_TIMEOUT=220 INITRD=$B/audio.cpio STDIN_FILE=$B/audio.in MEM=128 \
        tools/run-qemu.sh "$B/$k-cish/kernel32.elf" "$t" > "$t.rc") &
done
wait
cost "daphnis gcc and clang with the device and gcc without, side by side, atone twice in each$([ "${KVM:-0}" = 1 ] && echo ', KVM' || echo ', TCG')" "$t0"
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err" 2>/dev/null) bytes"
    grep -Eq '^audio: hda 8086:2668 codec 0 1af4:[0-9a-f]{4} pin [0-9]+ dac [0-9]+ 48000 Hz$' "$t" \
        && line ok "device $cc: the driver finds QEMU's intel-hda, walks hda-output to a pin and a DAC, 48 kHz" \
        || line bad "device $cc" "no hda line in $t"
    ok=1 eacces=1 dok=1
    for pid in 1 2; do
        sed -n "/^daphnis: run cish pid $pid\$/,/^daphnis: exit/p" "$t" > "$B/run/$cc-$pid.out"
        [ "$(grep -c '^audio: stream ' "$B/run/$cc-$pid.out")" = 2 ] && grep -qxF "$want" "$B/run/$cc-$pid.out" \
            && grep -qx 'atone: frames 96000' "$B/run/$cc-$pid.out" || ok=0
        grep -qx 'atone: cannot open /dev/dsp: error 13' "$B/run/$cc-$pid.out" || eacces=0
        grep -qxF "$want_doom" "$B/run/$cc-$pid.out" || dok=0
        sed -n '/^doom: wad /,/^doom: end tics /p' "$B/run/$cc-$pid.out" | grep -v '^doom: sound \|^audio: ' > "$B/run/$cc-$pid.doom"
        python3 "$D/tools/check-doom.py" --sealed 1 0 "$B/run/$cc-$pid.doom" "$D/tests/expected/doom.tics" "$D/data/e1m6.wad" \
            >> "$B/run/$cc-doom.cmp" 2>&1 || dok=0
    done
    [ $dok = 1 ] && line ok "doom $cc: doom --sound under grant disk,audio closes its stream with the chain of the Linux build's 48 kHz file and plays tests/expected/doom.tics, in both runs" \
        || line bad "doom $cc" "see $B/run/$cc-doom.cmp and $B/run/$cc-*.out"
    [ $ok = 1 ] && line ok "receipt $cc: atone under grant disk,audio closes its stream with the line of tests/expected/audio.digests, in both runs" \
        || line bad "receipt $cc" "see $B/run/$cc-*.out"
    [ $eacces = 1 ] && line ok "grant $cc: atone without the audio grant cannot open /dev/dsp (EACCES), in both runs" \
        || line bad "grant $cc" "see $B/run/$cc-*.out"
    python3 tools/check-audio.py wav "$B/run/$cc.wav" "$t" > "$B/run/$cc-wav.cmp" 2>&1 \
        && line ok "capture $cc: QEMU's capture, silent frames removed, is the kernel's mix byte for byte (tools/check-audio.py)" \
        || line bad "capture $cc" "$(cat "$B/run/$cc-wav.cmp")"
    grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" && grep -qx 'cish: done' "$t" \
        && line ok "desync $cc: the run on other frames does not desync" || line bad "desync $cc" "see $t"
done
t=$B/run/none.txt
[ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -qx 'daphnis: desync cish pid 2 (other frames) against pid 1: none' "$t" \
    && line ok "boot without the device: QEMU exit status 33, nothing on stderr, no desync" \
    || line bad "boot without the device" "status $(cat "$t.rc"), see $t"
[ "$(grep -c '^audio:' "$t")" = 0 ] && [ "$(grep -cx 'atone: cannot open /dev/dsp: error 2' "$t")" = 4 ] \
    && line ok "no device: no audio line and no /dev/dsp; atone gets ENOENT with the grant and without, in both runs" \
    || line bad "no device" "see $t"
dok=1
for pid in 1 2; do
    sed -n "/^daphnis: run cish pid $pid\$/,/^daphnis: exit/p" "$t" > "$B/run/none-$pid.out"
    grep -qx 'doom: no /dev/dsp, no sound' "$B/run/none-$pid.out" || dok=0
    sed -n '/^doom: wad /,/^doom: end tics /p' "$B/run/none-$pid.out" > "$B/run/none-$pid.doom"
    python3 "$D/tools/check-doom.py" --sealed 1 0 "$B/run/none-$pid.doom" "$D/tests/expected/doom.tics" "$D/data/e1m6.wad" \
        >> "$B/run/none-doom.cmp" 2>&1 || dok=0
done
[ $dok = 1 ] && line ok "no device, doom: doom --sound says it has no /dev/dsp and plays tests/expected/doom.tics silent, in both runs" \
    || line bad "no device, doom" "see $B/run/none-doom.cmp"

# 3. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
