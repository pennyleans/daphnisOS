#!/usr/bin/env bash
# tools/play.sh [WxH]: G-5b (docs/specs/2026-11-06-g-menu.md section 5), l plays the episode in a Daphnis desk
# window. Builds the deskplay flavor (src/main_deskplay.ci, gcc) and a fresh volume (tools/mkdisk.sh, or the one
# kept from the last run, so doom.cfg's settings carry over), boots them under KVM in a window at WxH (default
# 1080x1920, Arch's portrait screen; the desk's Settings switches it live) with no watchdog, then copies the record
# and the settings off the volume and replays the record on this host, sealed.
# SOUND= picks QEMU's audio backend (AU-6); by default pa (WSLg, or pipewire-pulse) when this QEMU has it, else
# pipewire; none for no device. Doom plays its sound effects (AU-5) through /dev/dsp; the boot's `audio:` line in
# play.txt shows that the driver found the device.
# The desk's clock shows the CMOS date (K-6b: daphnis.rtc=1 on the boot line, with any CPU= model); -cpu max also
# gives the guest RDRAND (A-3).
# Needs /dev/kvm, a display, cint on PATH, QEMU, musl-gcc, e2fsprogs (mke2fs, debugfs). Outputs under
# $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-play): play.txt (the serial transcript), play.img (the volume),
# g.lmp (the record), doom.cfg. Next: freedoom-ci's tools/episode-cut.sh $DAPHNIS_BUILD/g.lmp.
set -eu
cd "$(dirname "$0")/.."
mode=${1:-1080x1920}
case $mode in [0-9]*x[0-9]*) ;; *) echo "play.sh: WxH, as 1080x1920"; exit 2;; esac
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-play}
D=$(tools/doom/fetch.sh)   # DS-3: the Doom port from freedoom-ci at doom.pin's commit
export DOOM_ROOT=$D
for t in cint qemu-system-x86_64 musl-gcc mke2fs debugfs python3; do
    command -v "$t" >/dev/null || { echo "play.sh: $t not found"; exit 2; }
done
if [ -z "${SOUND:-}" ]; then
    have=$(qemu-system-x86_64 -audiodev help 2>/dev/null)
    for b in pa pipewire; do printf '%s\n' "$have" | grep -qx "$b" && { SOUND=$b; break; }; done
    [ -n "${SOUND:-}" ] || { SOUND=none; echo "play.sh: this QEMU has no pipewire or pa audio backend; playing with no sound device"; }
fi
[ "$SOUND" = none ] && SOUND=
[ -r /dev/kvm ] && [ -w /dev/kvm ] || { echo "play.sh: /dev/kvm is not open to this user (the kvm group)"; exit 2; }
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    echo "play.sh: $B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
    exit 2
fi
mkdir -p "$B"; : > "$B/.daphnis-build"
[ ! -e "$B/g.lmp" ] || mv "$B/g.lmp" "$B/g.lmp.$(date +%Y%m%dT%H%M%S)"   # never lose a record
make -s -j"$(nproc)" O="$B" FLAVORS=deskplay COMPILERS=gcc
[ -f "$B/play.img" ] || tools/mkdisk.sh "$B/play.img" > /dev/null
debugfs -w -R "rm /g.lmp" "$B/play.img" > /dev/null 2>&1 || true
cat <<'KEYS'
Daphnis boots its desk with Doom in a window. Click into QEMU to give it the keyboard (Ctrl+Alt+G lets go).
  Doom's menu: arrows and Enter, Esc opens and closes it, Backspace goes back. New Game picks the skill.
  Options: Messages, Screen Size (or - and =), Mouse Sensitivity, Sound Volume (or F4). Key Bindings: Enter on a row, then a key.
  Play: arrows turn and move, Alt strafes, , and . strafe, Shift runs, Ctrl fires, Space uses, 1 to 8 weapons.
  F10 then y quits Doom and writes the record; `. /doom.sh` in the terminal plays again; `exit` ends the desk.
  Super opens the desk's menu (Settings: the screen size). The mouse reaches Doom once the desk passes it (H-4).
KEYS
rc=$(SOUND="$SOUND" PLAY=1 RTC=1 CPU=${CPU:-max} QEMU_TIMEOUT=0 POOL=max MEM=${MEM:-4096} MODE="$mode" INITRD="$B/deskplay/initrd.cpio" \
    DISK="$B/play.img" tools/run-qemu.sh "$B/gcc-deskplay/kernel32.elf" "$B/play.txt")
echo "QEMU exit status $rc (33 is Daphnis's own end)"
debugfs -R "dump /doom.cfg $B/doom.cfg" "$B/play.img" 2> /dev/null || true
debugfs -R "dump /g.lmp $B/g.lmp" "$B/play.img" 2> /dev/null || true
if [ ! -s "$B/g.lmp" ]; then
    echo "play.sh: no record on the volume (was a game begun, and quit with F10 y?); transcript $B/play.txt"
    exit 1
fi
echo "record: $B/g.lmp, $(wc -c < "$B/g.lmp") bytes"
grep -aE '^doom: (live end|live tics|replay end|the replay|DESYNC|desync)' "$B/play.txt" || true
grep -ao 'doom: live frames [0-9]* wall tics [0-9]*' "$B/play.txt" | tail -1 || true   # DS D-FB: frames drawn in T tics of 1/35 s
(cd "$D/data" && "$D/bin/doom" --sealed --headless --demo "$B/g.lmp" e1.wad > "$B/replay.txt" 2>&1) || true
echo "this host's replay: $(grep -a '^doom: replay end' "$B/replay.txt" || tail -1 "$B/replay.txt")"
echo "next: $D/tools/episode-cut.sh $B/g.lmp (in freedoom-ci)"
