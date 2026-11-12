#!/usr/bin/env bash
# check-hybrid.sh: the gate of stage H (docs/specs/2026-11-05-h-hybrid.md section 7), on its own budget beside
# check.sh and check-tiler.sh, which keeps every 640 x 480 pin. One PASS or FAIL line per check; exit status 1 if
# any FAIL.
#   H-R3, under Daphnis at 1920 x 1080 (run-qemu.sh MODE, HX-0 A): the tile flavor and the desk flavor boot on gcc
#   and clang with check-tiler.sh's keys; tools/check-tiler.py --boot and --desk take the size from the transcript
#   and check the same things at that size (mcifb fullscreen and in its tile, the frames, the input, the terminal's
#   rows, doom's tile at 1x, the screens); the transcripts are tests/expected/tile-1080.serial and
#   tests/expected/desk-1080.serial. At 2560 x 1440 and 3840 x 2160, and at RES-1's widest and tallest, 5120 x 1440
#   and 2160 x 3840, the tile flavor boots once on gcc: mcifb fullscreen maps the whole framebuffer (above
#   MAP_LIMIT, H-R2b), and the tiler's frame is the Python's.
#   H-1, on Linux: user/ci/hlayout.ci, built with musl-gcc, gcc and clang, prints its Python twin's lines.
#   H-2, under Daphnis at 1920 x 1080 on gcc and clang: the hyb flavor (src/main_hyb.ci), `tiler --place` over
#   three mcifb; tools/check-tiler.py --place composes the screen (2x, two 1x rectangles, hidden) and checks it.
#   Its client 0 at 2x is more than one timed copy's budget, so the copies resume across ticks.
#   H-3a, under Daphnis at 1920 x 1080 on gcc and clang: the hdesk flavor (src/main_hdesk.ci) with a typed script
#   (a second terminal, doom in it, Alt+Tab, monocle, desktop 2, the exits); tools/check-hdesk.py checks every layout
#   against layout.ci's twin, every placement, the steps, doom's surface and the screen after the desk. H-3b adds to
#   the script an OSC 2 title (the bar's variable), Alt+`, a sticky Alt+Ctrl+Tab, the Super plane (FF-5: a minimized
#   window restored by search), monocle, a swap and a float moved and grown. Then Settings (HX-13, HX-14) from the
#   plane, the keyboard on its sidebar (ST-K1): Right into Display, Tab to Screen shape and Right twice to portrait,
#   Tab to Resolution, Enter, Down and Enter switch live to 1080 x 1920 (HX-12 A); Enter keeps it (DN-10: no volume,
#   so the bar says the save failed until the message goes); Tab past Restore Defaults back to the sidebar, Right into
#   Theme and Right to Warm Paper (K-3), Esc closes. The screen after the desk is checked at that size in that theme.
#   K-6: the bar's
#   clock (the fixed epoch) and Super+c's calendar, a month on and back, left open over the screen after the desk. K-5:
#   the 28 px bar; the pointer moves up to the bar, which draws no DISK pill (DN-72).
#   K-7: tiles 8 px apart and from the plane's edges; hlayout also prints the color mark's fingerprint at 20, 440
#   and 480 px (the emblem, KD-2 B) against the SVG's Python twin.
#   K-1: after the portrait boot, a second boot at 1080 x 1920 opens six terminals and the sticky switcher, moves a
#   row with Down to the first terminal and chooses it; every switcher frame is E2-2's 520 px card (KD-3 A).
#   WB-5, DN-23: the bars run clicks the 24 px buttons on the 32 px bar; user/ci/kit/wbbtn.ci is what tools/wbbtn.py
#   writes from agy's bitmaps (user/ci/kit/wbbtn/).
#   FF-4: two more boots on gcc open a second terminal; FF-R6 B: Super+Shift+Q twice within 2 s shuts down (the
#   first press opens the plane, `Shut Down` armed), and Super+Shift+R arms `Restart`, lapses after 2 s, and a click
#   on the action restarts: reboot(2) ends every process, the desk last with status 0, and the machine ends through the exit
#   port (status 33, `daphnis: shut down` before `daphnis: done`) or through the 8042's reset (QEMU's -no-reboot:
#   status 0, `daphnis: restart` last).
#   SP-1 to SP-3 (docs/specs/2026-11-08-sp-system-panel.md) on the DN-34 panel: the panel run, with an audio device,
#   opens the system panel by click while `grant audio` holds a stream, sets the volume by Left and by a click on its
#   slider, and leaves the panel open over the screen after the desk; the sound run clicks the panel's Sound Settings
#   link. Every click in these runs goes where the desk's own lines place its target (the clock's line for the
#   squares and the chevron, the overlay's frame line for a panel's or a plate's row: tools/sendkeys.py `@`), never a
#   fixed offset. The tray run, with stepped frames (daphnis.stepframes: a Shift press a frame), hides `tray cat`'s
#   window, opens the Super plane (its machine region leaves the tray's window out) and closes it, screendumps the
#   chevron at frames 0, 8 and 16, restores the window from the plate's cell, quits it by a right click, and ends with
#   the plate open at rest and the window's 200 ms grow over; the plate takes Enter, so Ctrl+J ends the shell's line.
#   tools/check-hdesk.py --panel and --tray.
#   MS-7 (DN-54): the slide run, with stepped frames, switches with Super+2 and Super+1, screendumps Super+1's
#   frames 0 and 12 and both desks at rest, jumps from the window list to the terminal on desktop 2 and goes back;
#   tools/check-hdesk.py --slide.
#   MS-9a (l's MS-R4 A): spec section 6's gates 4, 7 and 8 on the stepped clock, dark and light in one boot each:
#   the system panel opening and closing, a float moved by key, the bar message in and out; each screendump waits
#   on `hdesk: step K of motion N` and equals tools/check-hdesk.py --motion's frame in motion. Gate 6, a desktop
#   switch, is the slide run above (MS-7, DN-54).
#   FF-5: the Super plane replaces the Super menu; the hdesk legs' `hdesk: ff` lines (pids as N) equal
#   tests/expected/hdesk-ff.out on gcc and clang. The desk now holds the file index (FF-1), and cint 0.2.16 keeps a zero
#   image of each module's state in the binary: the hdesk image (31.6 MB) passes the 28 MiB below the pool, so every
#   hdesk leg boots with daphnis.pool=max (POOL=max), as tools/play.sh and check-disk.sh's home legs do.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-hybrid), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-hybrid}
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=1800    # includes serial approval cases with the real 120 s deadline; cloud: 536 s before H-3a (the desk scrolls a 239-column terminal); the hdesk legs add about 200 s; 900 until FF-6b (937 s on the cloud at FF-5b; FF-6b adds a finder boot)
gate_want=64   # the PASS lines before the last one (44 at the base, +1 MS-7's slide, +2 the desk stack, +12 AC on PR 250, +2 RES-1's widest and tallest, +3 MS-9a's gates 4, 7 and 8)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-hybrid.sh: $*"; echo "RESULT: FAIL"; exit 1; }
# DS-3: the Doom port, its data and its pins come from freedoom-ci at doom.pin's commit (tools/doom/fetch.sh)
D=$(tools/doom/fetch.sh) || fail_exit "tools/doom/fetch.sh: no freedoom-ci at doom.pin's commit"
export DOOM_ROOT=$D

for t in cint gcc clang musl-gcc as ld objcopy qemu-system-x86_64 python3 sha256sum cmp timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B"; : > "$B/.daphnis-build"
git_state_before=$(git status --porcelain 2>/dev/null)

# 1. the flavors, and doom's Linux run (the desk's pin)
# HW-17: every hdesk boot takes the release image, hdesk/release.cpio, but the one that types ./doom (initrd.cpio)
make -s -j"$(nproc)" O="$B" FLAVORS="tile desk hyb hdesk" all "$B/hdesk/release.cpio" > "$B/make.log" 2>&1 \
    && line ok "build: the tile, desk, hyb and hdesk flavors for gcc and clang and the release image (make FLAVORS=\"tile desk hyb hdesk\" all hdesk/release.cpio)" \
    || line bad "build: make FLAVORS=\"tile desk hyb hdesk\" all hdesk/release.cpio" "see $B/make.log"
# RG-1: the programs the images take, built from source at HEAD into $B/ubin (the Makefile's RELEASE_PROGS), not the
# committed user/bin; the golden's names stay user/bin/NAME and are read as $B/ubin/NAME
sed 's#  user/bin/#  #' tests/expected/hdesk.sha256 | (cd "$B/ubin" && sha256sum --quiet -c -) > "$B/bin.log" 2>&1 \
    && line ok "bin: hdesk, mwin and finder as the images take them (O/ubin, built from source) are the bytes of tests/expected/hdesk.sha256" \
    || line bad "bin" "see $B/bin.log"
data="$D/data"
(cd "$data" && "$D/bin/doom" --sealed --headless --frame-out "$B/doom.frame" > "$B/linux-sealed.txt" 2>&1) \
    && cmp -s "$B/linux-sealed.txt" "$D/tests/expected/doom.tics" \
    && line ok "linux: bin/doom --sealed --headless plays tests/expected/doom.tics; its last frame is the desk's pin" \
    || line bad "linux: doom --sealed" "see $B/linux-sealed.txt"

# 1b. H-1, on Linux: user/ci/hlayout.ci (the layout of user/ci/kit/layout.ci) built with musl-gcc, gcc and clang
#     prints the lines of its Python twin, tools/check-layout.py, byte for byte
for cc in musl-gcc gcc clang; do
    CI_CC=$cc CI_OUT=$B/layout-$cc bash user/ci/build.sh hlayout > "$B/layout-$cc.log" 2>&1 \
        && python3 tools/check-layout.py "$B/layout-$cc/hlayout" > "$B/layout-$cc.cmp" 2>&1 \
        && line ok "layout $cc: tiling 1 to 8, floats and their rectangles, monocle, desktops, the refusal past 32, the switcher's order, Daphnis Sans at 1x and 2x (K-4): the Python's lines" \
        || line bad "layout $cc" "see $B/layout-$cc.log, $B/layout-$cc.cmp"
done

# 2. 1920 x 1080: the tile and the desk on gcc and clang, the keys of check-tiler.sh
mkdir -p "$B/run"
M=1920x1080
# at this size a client reads its queue more slowly: 2.4 s of monitor no-ops between `a` and Super+q, so the client
# has read all 4 events before it ends (the queue's count line; check-tiler.sh's 640 x 480 runs need none). The desk
# waits for the shell's prompt, then types `ls; ./doom --sealed; exit` as one line: a key typed while a program ran,
# or before the first prompt, was echoed before or after that program's output as the host's load fell (W-4b)
# `mkdir notes; cd notes`: the second terminal's variable (H-3b) is the OSC 2 cish writes before each prompt, the
# working directory (K-9), which also writes over a title a program set; `cd ..` before doom
osc="m,k,d,i,r,spc,n,o,t,e,s,semicolon,spc,c,d,spc,n,o,t,e,s"
pause="info version,info version,info version,info version,info version,info version,info version,info version"
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ ${#t} -le 100 ] || fail_exit "monitor socket path $t.mon is too long for a unix socket; set a shorter DAPHNIS_BUILD"
    (SENDKEYS_WAIT=170 python3 tools/sendkeys.py "$t.mon" "$t" "tiler: start client 2 in tile 0,1" a,b,c \
        "tiler: client 0 in tile 0,0 ended" meta_l-right,a,b,c \
        "tiler: client 1 in tile 1,0 ended" "meta_l-left,meta_l-down,a,$pause,meta_l-q" > "$t.keys" 2>&1 &
     MODE=$M QEMU_TIMEOUT=180 INITRD=$B/tile/initrd.cpio MONITOR=$t.mon MEM=128 \
        tools/run-qemu.sh "$B/$cc-tile/kernel32.elf" "$t" > "$t.rc"; wait) &
    d=$B/run/desk-$cc.txt
    (SENDKEYS_WAIT=350 python3 tools/sendkeys.py "$d.mon" "$d" "tiler: desk shell first output" \
        l,s,semicolon,spc,dot,slash,d,o,o,m,spc,minus,minus,s,e,a,l,e,d,semicolon,spc,e,x,i,t,ret > "$d.keys" 2>&1 &
     MODE=$M QEMU_TIMEOUT=360 INITRD=$B/desk/initrd.cpio MONITOR=$d.mon MEM=128 \
        tools/run-qemu.sh "$B/$cc-desk/kernel32.elf" "$d" > "$d.rc"; wait) &
done
wait
for cc in gcc clang; do
    t=$B/run/$cc.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $M $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $M $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    python3 tools/check-tiler.py --boot "$t" > "$B/boot-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/boot-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/boot-$cc.cmp")" = 8 ] && ! grep -q '^FAIL' "$B/boot-$cc.cmp" \
        && line ok "tile $M $cc: mcifb fullscreen and in a tile, the frames and screens are the Python's; keys reach the focused client only" \
        || line bad "tile $M $cc" "see $B/boot-$cc.cmp"
    cmp -s tests/expected/tile-1080.serial "$t" \
        && line ok "serial $M $cc: the transcript equals tests/expected/tile-1080.serial" \
        || line bad "serial $M $cc: vs tests/expected/tile-1080.serial" "differ"
done
for cc in gcc clang; do
    d=$B/run/desk-$cc.txt
    [ "$(cat "$d.rc")" = 33 ] && [ ! -s "$d.err" ] \
        && line ok "boot desk $M $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot desk $M $cc" "status $(cat "$d.rc"), stderr $(wc -c < "$d.err") bytes"
    python3 tools/check-tiler.py --desk "$d" "$B/doom.frame" "$data/e1m6.wad" "$D/tests/expected/doom.tics" > "$B/desk-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/desk-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/desk-$cc.cmp")" = 5 ] && ! grep -q '^FAIL' "$B/desk-$cc.cmp" \
        && line ok "desk $M $cc: the terminal, doom's chain and its 1x tile, the screen are the Python's" \
        || line bad "desk $M $cc" "see $B/desk-$cc.cmp"
    cmp -s tests/expected/desk-1080.serial "$d" \
        && line ok "serial desk $M $cc: the transcript equals tests/expected/desk-1080.serial" \
        || line bad "serial desk $M $cc: vs tests/expected/desk-1080.serial" "differ"
done

# 3. 2560 x 1440 and 3840 x 2160: one tile boot each on gcc, until the tiler's frame (no keys);
#    3b. H-2: placement at 1920 x 1080, gcc and clang; the four boots at once (four cores)
# (the boots run beside section 3c's; see there)
# 3c. H-3a: the hybrid desk at 1920 x 1080, gcc and clang at once, the script typed through the monitor; beside them,
#     one after another on the other two cores: a boot straight into 1080 x 1920 portrait (HX-12 A) on gcc, a second
#     terminal stacked under the first, clicks and a Super drag (H-4), the second ended; `mwin 160 100 notes` asks its
#     size, sets its variable and ends at its first resize event, a float (H-3c3); a click on the App Title opens its
#     dropdown and a click on monocle chooses it (H-4c); WB-1 and WB-4: a float's bar dragged, each button, a double
#     click, F11, and close ending a session of sh, a background sleep and cat; WB-2: three terminals, the third
#     dropped at the left edge, the right, the top left corner and the top, the first Super-dragged to the bottom right
#     corner; then section 3's smokes; then 3b's
#     placement boots. Their checks follow in section order.
p=$B/run/portrait.txt
( (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$p.mon" "$p" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: terminal 1 slot 1" "$pause,mouse_move -100 -100,mouse_move -100 -100,mouse_button 1,mouse_button 0" \
    "hdesk: click 340,760 button 0 window 0" "$pause,sendkey meta_l 6000,mouse_button 1,mouse_move 20 40,mouse_move 20 0,mouse_button 0" \
    "hdesk: drop 0" "$pause,mouse_move 0 100,mouse_move 0 100,mouse_move 0 100,mouse_button 1,mouse_button 0" \
    "hdesk: click 380,1100 button 0 window 1" "$pause,e,x,i,t,ret" \
    "hdesk: terminal 1 ended" "$pause,dot,slash,m,w,i,n,spc,1,6,0,spc,1,0,0,spc,n,o,t,e,s,ret" \
    "...|mwin| var |notes|" "$pause,meta_l-f" \
    "hdesk: pixel 1 ended" "$pause,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move -100 0,mouse_move -100 0,mouse_move -100 0,mouse_move -20 0,mouse_button 1,mouse_button 0" \
    "hdesk: app menu open" "$pause,mouse_move 0 95,$pause,mouse_move 240 55,mouse_button 1,mouse_button 0" "hdesk: app menu chose" "$pause,e,x,i,t,ret" > "$p.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=240 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$p.mon MEM=128 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$p" > "$p.rc"; wait)
 v=$B/run/switcher.txt
 (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$v.mon" "$v" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: win 1 kind 1" "$pause,meta_l-ret" "hdesk: win 2 kind 1" "$pause,meta_l-ret" \
    "hdesk: win 3 kind 1" "$pause,meta_l-ret" "hdesk: win 4 kind 1" "$pause,meta_l-ret" \
    "hdesk: win 5 kind 1" "$pause,ctrl-alt-tab" "hdesk: switcher 1 of 6" "$pause,down" \
    "hdesk: switcher 5 of 6, window 0" "$pause,ret" "hdesk: switcher chose 0" "$pause,e,x,i,t,ret" > "$v.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=240 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$v.mon MEM=128 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$v" > "$v.rc"; wait)
 w=$B/run/bars.txt
 (SENDKEYS_WAIT=300 python3 tools/sendkeys.py "$w.mon" "$w" "hdesk: bar desktop 1 |Console| var |/|" meta_l-f \
    "...frame 270,501 540x946" "$pause,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -50,mouse_button 1,mouse_move 20 16,mouse_move 20 16,mouse_button 0" \
    "hdesk: drop 0 desktop 1 frame 310,533 540x946" "$pause,mouse_button 1,mouse_button 0,mouse_button 1,mouse_button 0" \
    "hdesk: bar double 0" "$pause,f11,$pause,mouse_move 100 0,mouse_move 100 0,mouse_button 1,mouse_button 0" \
    "hdesk: bar button 1 window 0" "$pause,meta_l-z,$pause,mouse_move 20 0,mouse_button 1,mouse_button 0" \
    "hdesk: bar button 2 window 0" "$pause,meta_l-f,$pause,mouse_move -84 -32,mouse_button 1,mouse_move 0 100,mouse_button 0,mouse_move 0 -100,mouse_button 1,mouse_button 0" \
    "hdesk: bar button 0 window 0" "$pause,meta_l-shift-m,$pause,meta_l-f,$pause,s,l,e,e,p,spc,9,9,9,spc,shift-7,ret,$pause,c,a,t,ret,$pause,$pause,h,i,ret" \
    "...|bin/cat| var" "$pause,mouse_move 84 0,mouse_button 1,mouse_button 0" > "$w.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=300 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$w.mon MEM=128 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$w" > "$w.rc"; wait)
 z=$B/run/zones.txt
 (SENDKEYS_WAIT=300 python3 tools/sendkeys.py "$z.mon" "$z" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: terminal 1 slot 1" "$pause,meta_l-ret" "hdesk: terminal 2 slot 2" "$pause,meta_l-f" \
    "...frame 270,501 540x946" "$pause,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -50,mouse_button 1,mouse_move -250 0,mouse_move -250 0,mouse_move -38 0,mouse_button 0" \
    "hdesk: zone 2 1" "$pause,meta_l-f,$pause,mouse_move 250 0,mouse_move 250 0,mouse_move 38 0,mouse_button 1,mouse_move 250 0,mouse_move 250 0,mouse_move 39 0,mouse_button 0" \
    "hdesk: zone 2 2" "$pause,meta_l-f,$pause,mouse_move -250 0,mouse_move -250 0,mouse_move -39 0,mouse_button 1,mouse_move -250 -240,mouse_move -250 -240,mouse_move -38 0,mouse_button 0" \
    "hdesk: zone 2 3" "$pause,meta_l-f,$pause,mouse_move 250 240,mouse_move 250 240,mouse_move 38 0,mouse_button 1,mouse_move -240 -240,mouse_move 0 -240,mouse_button 0" \
    "hdesk: zone 2 7" "$pause,f11,$pause,mouse_move -200 270,sendkey meta_l 6000,mouse_button 1,mouse_move 140 232,mouse_move 140 232,mouse_move 140 232,mouse_move 140 232,mouse_move 140 232,mouse_move 140 232,mouse_move 140 232,mouse_button 0" \
    "hdesk: zone 0 6" "$pause,e,x,i,t,ret" > "$z.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=300 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$z.mon MEM=128 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$z" > "$z.rc"; wait)
 w=$B/run/power-shutdown.txt
 (SENDKEYS_WAIT=120 python3 tools/sendkeys.py "$w.mon" "$w" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: win 1 kind 1" "$pause,meta_l-shift-q" "hdesk: ff armed 3" "meta_l-shift-q" > "$w.keys" 2>&1 &
 QEMU_TIMEOUT=150 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$w.mon MEM=128 MODE=1920x1080 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$w" > "$w.rc"; wait)
 w=$B/run/power-restart.txt
 mv=$(for k in 1 2; do printf 'mouse_move 100 0,'; done)
 (SENDKEYS_WAIT=120 python3 tools/sendkeys.py "$w.mon" "$w" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: win 1 kind 1" "$pause,meta_l-shift-r" "hdesk: ff armed 2" "$pause" \
    "hdesk: ff disarmed" "$pause,${mv}mouse_move 100 0,mouse_move 26 0,mouse_move 0 -70,mouse_button 1,mouse_button 0" \
    "hdesk: ff power menu" "$pause,mouse_move -70 -40,mouse_button 1,mouse_button 0" \
    > "$w.keys" 2>&1 &
 QEMU_TIMEOUT=150 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$w.mon MEM=128 MODE=1920x1080 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$w" > "$w.rc"; wait)
 f=$B/run/finder.txt
 (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$f.mon" "$f" "hdesk: bar desktop 1 |Console| var |/|" "f,i,n,d,e,r,spc,slash,ret" \
    "...|Index| var |/| " "$pause,screendump $B/run/finder-root.ppm,$pause,e,t,c,ret" \
    "...|Index| var |/etc| " "$pause,$pause,backspace,$pause,$pause,alt-left,$pause,$pause,ret" \
    "hdesk: ff runs " "$pause,$pause,meta_l-shift-q" "hdesk: ff armed 3" "meta_l-shift-q" > "$f.keys" 2>&1 &
 QEMU_TIMEOUT=200 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$f.mon MEM=128 MODE=1920x1080 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$f" > "$f.rc"; wait)
 m=$B/run/finder-menu.txt
 (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$m.mon" "$m" "hdesk: bar desktop 1 |Console| var |/|" "f,i,n,d,e,r,spc,slash,ret" \
    "...|Index| var |/| " "$pause,shift-z,shift-z,shift-z" \
    "finder: filter |ZZZ| items 0" "$pause,menu" \
    "finder: menu EMPTY at " "$pause,down,right,down,down,ret" \
    "finder: sort size" "$pause,menu" \
    "finder: menu EMPTY at " "$pause,right,down,$pause,screendump $B/run/finder-menu-view.ppm,ret" \
    "finder: view table" "$pause,esc" \
    "finder: filter || items " "$pause,menu" \
    "finder: menu FOLDER at " "$pause,screendump $B/run/finder-menu.ppm,down,down,down,ret" \
    "finder: menu |Copy as Path| not built" "$pause,shift-f10" \
    "finder: menu FOLDER at " "$pause,esc,$pause,menu" \
    "finder: menu FOLDER at " "$pause,ret" \
    "finder: menu chose |Open|" "$pause,$pause,esc" \
    "finder: ended" "$pause,meta_l-shift-q" "hdesk: ff armed 3" "meta_l-shift-q" > "$m.keys" 2>&1 &
 QEMU_TIMEOUT=200 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$m.mon MEM=128 MODE=1920x1080 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$m" > "$m.rc"; wait)
 r=$B/run/kern.txt
 (SENDKEYS_WAIT=300 python3 tools/sendkeys.py "$r.mon" "$r" "hdesk: bar desktop 1 |Console| var |/|" \
    "k,e,r,n,spc,minus,s,ret,$pause,k,e,r,n,spc,k,e,r,n,spc,minus,s,ret" \
    "hdesk: kern ask 0 pid 4 |kern -s|" "$pause,esc" \
    "hdesk: kern refused pid 4" "$pause,k,e,r,n,spc,k,e,r,n,spc,minus,s,ret" \
    "hdesk: kern ask 0 pid 5 |kern -s|" "$pause,meta_l-ret" \
    "hdesk: kern 0 pid 5" "$pause,$pause,k,e,r,n,spc,minus,s,ret" \
    "hdesk: kern hold 0 ended" "$pause,k,e,r,n,spc,minus,s,ret,$pause,k,e,r,n,spc,k,e,r,n,spc,minus,s,ret" \
    "hdesk: kern ask 0 pid 8 |kern -s|" "$pause,meta_l-ret" \
    "hdesk: kern 0 pid 8" "$pause,$pause,e,x,i,t,ret" > "$r.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=300 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$r.mon MEM=128 APPEND=daphnis.kernhold=20 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$r" > "$r.rc"; wait)
 s4="shift,shift,shift,shift"
 a=$B/run/panel.txt
 (SENDKEYS_WAIT=300 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: bar desktop 1 |Console| var |/|" \
    "g,r,a,n,t,spc,a,u,d,i,o,spc,s,h,spc,minus,c,spc,shift-apostrophe,c,a,t,spc,shift-dot,spc,slash,d,e,v,slash,d,s,p,shift-apostrophe,ret,$pause,@squares,mouse_button 1,mouse_button 0" \
    "...|bin/cat| streams 1" "$pause,left,left,left" \
    "hdesk: volume 85" "$pause,@ov 152 180,mouse_button 1,mouse_button 0" \
    "hdesk: volume 50" "$pause,esc" \
    "hdesk: panel closed" "$pause,ctrl-d,$pause,$pause,@squares,mouse_button 1,mouse_button 0" \
    "...level 50 player 0 || streams 0 net 0 animations 1" "$pause,e,x,i,t,ret" > "$a.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=300 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$a.mon MEM=128 SOUND=wav,path=$B/run/panel.wav \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait)
 u=$B/run/sound.txt
 (SENDKEYS_WAIT=300 python3 tools/sendkeys.py "$u.mon" "$u" "hdesk: bar desktop 1 |Console| var |/|" \
    "$pause,@squares,mouse_button 1,mouse_button 0" \
    "hdesk: panel open" "$pause,@ov 280 76,mouse_button 1,mouse_button 0" \
    "hdesk: settings page 2" "$pause,right,left,left,left" \
    "hdesk: volume 85" "$pause,right" \
    "hdesk: volume 90@@2" "$pause,tab,ret" \
    "hdesk: settings defaults" "$pause,esc" \
    "hdesk: settings closed" "$pause,e,x,i,t,ret" > "$u.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=300 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$u.mon MEM=128 SOUND=wav,path=$B/run/sound.wav \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$u" > "$u.rc"; wait)
 g=$B/run/traymin.txt
 (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$g.mon" "$g" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: terminal 1 slot 1" "$pause,t,r,a,y,spc,minus,m,spc,c,a,t,ret,$pause,$pause,meta_l-m" \
    "hdesk: tray 1 in" "$pause,meta_l-shift-q" "hdesk: ff armed 3" "meta_l-shift-q" > "$g.keys" 2>&1 &
 MODE=1920x1080 QEMU_TIMEOUT=200 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$g.mon MEM=128 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$g" > "$g.rc"; wait)
 y=$B/run/tray.txt
 (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$y.mon" "$y" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
    "hdesk: terminal 1 slot 1" "$pause,t,r,a,y,spc,c,a,t,ret" \
    "hdesk: tray 1 in" "$pause,meta_l" \
    "hdesk: ff open" "$pause,esc" \
    "hdesk: ff closed" "$pause,@chevron,mouse_button 1,mouse_button 0" \
    "hdesk: tray row 0 window 1 ring 3 |bin/cat - /|" "$pause,mouse_move 0 600,$pause,screendump $B/run/tray-0.ppm,$pause,$s4,$s4" \
    "hdesk: turn step 8 angle" "$pause,screendump $B/run/tray-8.ppm,$pause,$s4,$s4" \
    "hdesk: turn step 16 angle" "$pause,screendump $B/run/tray-16.ppm,$pause,@ov 20 20,mouse_button 1,mouse_button 0" \
    "hdesk: tray opened 1" "$pause,$s4,$s4,$s4,$s4" \
    "hdesk: turn step 16 angle 0" "$pause,@chevron,mouse_button 1,mouse_button 0" \
    "hdesk: tray row 0 window 1 ring 3 |bin/cat - /|@@2" "$pause,$s4,$s4,$s4,$s4,$pause,@ov 20 20,mouse_button 2,mouse_button 0" \
    "hdesk: terminal 1 ended" "$pause,meta_l-ret" \
    "hdesk: terminal 1 slot 1@@2" "$pause,t,r,a,y,spc,c,a,t,ret" \
    "hdesk: tray 1 in@@2" "$pause,@chevron,mouse_button 1,mouse_button 0" \
    "hdesk: tray row 0 window 1 ring 3 |bin/cat - /|@@3" "$pause,mouse_move 0 600,$pause,$s4,$s4" \
    "hdesk: turn step 8 angle@@4" "$pause,$s4,$s4" \
    "hdesk: turn step 16 angle@@4" "$pause,$s4" \
    "hdesk: step 20 of motion@@2" "$pause,e,x,i,t,ctrl-j" > "$y.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=400 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$y.mon MEM=128 APPEND=daphnis.stepframes \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$y" > "$y.rc"; wait)
 v=$B/run/slide.txt
 s12="$s4,$s4,$s4"
 (SENDKEYS_WAIT=600 python3 tools/sendkeys.py "$v.mon" "$v" \
    "hdesk: bar desktop 1 |Console| var |/|" "$pause,l,s,ret,$pause,meta_l-2" \
    "hdesk: slide 1 to 2" "$pause,$s12,$s12" \
    "hdesk: slide ended desktop 2" "$pause,meta_l-ret" \
    "hdesk: terminal 1 slot 1" "$pause,e,c,h,o,spc,t,w,o,ret,$pause,$pause,mouse_move -2000 -2000,$pause,$pause,\
screendump $B/run/slide-rest2.ppm,$pause,meta_l-1" \
    "hdesk: slide 2 to 1" "$pause,$pause,screendump $B/run/slide-start.ppm,$s12" \
    "hdesk: slide step 12 at@@2" "$pause,screendump $B/run/slide-mid.ppm,$s12" \
    "hdesk: slide ended desktop 1" "$pause,$pause,screendump $B/run/slide-end.ppm,$pause,meta_l,c,o,n,down,ret" \
    "hdesk: ff chose win" "$pause,$s12,$s12" \
    "hdesk: slide ended desktop 2@@2" "$pause,e,x,i,t,ret" \
    "hdesk: terminal 1 ended" "$pause,meta_l-1" \
    "hdesk: slide 2 to 1@@2" "$pause,$s12,$s12" \
    "hdesk: slide ended desktop 1@@2" "$pause,e,x,i,t,ret" > "$v.keys" 2>&1 &
 MODE=1920x1080 QEMU_TIMEOUT=600 POOL=max INITRD=$B/hdesk/initrd.cpio MONITOR=$v.mon MEM=128 APPEND=daphnis.stepframes \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$v" > "$v.rc"; wait)
 # MS-9a (l's MS-R4 A), section 6 gate 4 on the stepped clock: the system panel opening (8 and 16 steps) and
 # closing (5 and 10), dark, then light after Settings; each dump waits on `hdesk: step K of motion N`, the line
 # hdesk prints once that step's frame is on the screen. tools/check-hdesk.py --motion 4 composes each.
 s8="$s4,$s4"
 s5="shift,shift,shift,shift,shift"
 v4=$B/run/g4.txt
 (SENDKEYS_WAIT=900 python3 tools/sendkeys.py "$v4.mon" "$v4" "hdesk: bar desktop 1 |Console| var |/|" \
    "$pause,$pause,screendump $B/run/g4-dark-rest.ppm,$pause,@squares,mouse_button 1,mouse_button 0" \
    "hdesk: panel open" "$pause,$s8" \
    "hdesk: step 8 of motion 1"$'\n' "$pause,screendump $B/run/g4-dark-o8.ppm,$pause,$s8" \
    "hdesk: step 16 of motion 1"$'\n' "$pause,screendump $B/run/g4-dark-o16.ppm,$pause,esc" \
    "hdesk: panel closed" "$pause,$s5" \
    "hdesk: step 5 of motion 2"$'\n' "$pause,screendump $B/run/g4-dark-c5.ppm,$pause,$s5" \
    "hdesk: step 10 of motion 2"$'\n' "$pause,screendump $B/run/g4-dark-c10.ppm,$pause,meta_l,s,e,t,t,ret" \
    "hdesk: settings 1" "$pause,right,right" \
    "hdesk: theme 1" "$pause,esc" \
    "hdesk: settings closed" "$pause,mouse_button 1,mouse_button 0" \
    "hdesk: panel open@@2" "$pause,$s8" \
    "hdesk: step 8 of motion 3"$'\n' "$pause,screendump $B/run/g4-light-o8.ppm,$pause,$s8" \
    "hdesk: step 16 of motion 3"$'\n' "$pause,screendump $B/run/g4-light-o16.ppm,$pause,esc" \
    "hdesk: panel closed@@2" "$pause,$s5" \
    "hdesk: step 5 of motion 4"$'\n' "$pause,screendump $B/run/g4-light-c5.ppm,$pause,$s5" \
    "hdesk: step 10 of motion 4"$'\n' "$pause,screendump $B/run/g4-light-c10.ppm,$pause,e,x,i,t,ret" > "$v4.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=900 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$v4.mon MEM=128 APPEND=daphnis.stepframes \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$v4" > "$v4.rc"; wait)
 s56="$s12,$s12,$s12,$s12,$s4,$s4"
 # MS-9a, gate 8: the bar message (MS-5): in after 8 and 16 steps; after its hold (400 steps from the message) it
 # fades out, 10 and 20 steps. Eight terminals fill the slots (seven moved to desktop 2 with motion off, then motion
 # on; the strip's hold waited out with motion still off, so it hides at once and nothing else moves), so a ninth
 # Super+Enter says "No free Console"; dark, then light; then every shell exits.
 s10="$s5,$s5"
 s16="$s8,$s8"
 s384="$s56,$pause,$s56,$pause,$s56,$pause,$s56,$pause,$s56,$pause,$s56,$pause,$s16,$pause,$s16,$pause,$s16"   # paused chunks: a burst can outrun the guest
 v8=$B/run/g8.txt
 (SENDKEYS_WAIT=2400 python3 tools/sendkeys.py "$v8.mon" "$v8" "hdesk: bar desktop 1 |Console| var |/|" "$pause,meta_l,s,e,t,t,ret" \
    "hdesk: settings 1" "$pause,right,tab,tab,ret" \
    "hdesk: animations off" "$pause,esc" \
    "hdesk: settings closed" "$pause,meta_l-ret" \
    "hdesk: terminal 1 slot 1" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 2 slot 2" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 3 slot 3" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 4 slot 4" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 5 slot 5" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 6 slot 6" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,meta_l-ret" \
    "hdesk: terminal 7 slot 7" "$pause,meta_l-shift-2,$pause,meta_l-1,$pause,$s56,$pause,$s12,$pause,$s12" \
    "hdesk: strip hidden" "$pause,meta_l,s,e,t,t,ret" \
    "hdesk: settings 8" "$pause,right,tab,tab,ret" \
    "hdesk: animations on" "$pause,esc" \
    "hdesk: settings closed@@2" "$pause,meta_l-ret" \
    "hdesk: message |No free" "$pause,$s8" \
    "hdesk: step 8 of motion 1"$'\n' "$pause,screendump $B/run/g8-dark-m8.ppm,$pause,$s8" \
    "hdesk: step 16 of motion 1"$'\n' "$pause,screendump $B/run/g8-dark-m16.ppm,$pause,$s384" \
    "hdesk: message gone" "$pause,$s10" \
    "hdesk: step 10 of motion 2"$'\n' "$pause,screendump $B/run/g8-dark-g10.ppm,$pause,$s10" \
    "hdesk: step 20 of motion 2"$'\n' "$pause,screendump $B/run/g8-dark-g20.ppm,$pause,meta_l,s,e,t,t,ret" \
    "hdesk: settings 8@@2" "$pause,right,right" \
    "hdesk: theme 1" "$pause,esc" \
    "hdesk: settings closed@@3" "$pause,meta_l-ret" \
    "hdesk: message |No free@@2" "$pause,$s8" \
    "hdesk: step 8 of motion 3"$'\n' "$pause,screendump $B/run/g8-light-m8.ppm,$pause,$s8" \
    "hdesk: step 16 of motion 3"$'\n' "$pause,screendump $B/run/g8-light-m16.ppm,$pause,$s384" \
    "hdesk: message gone@@2" "$pause,$s10" \
    "hdesk: step 10 of motion 4"$'\n' "$pause,screendump $B/run/g8-light-g10.ppm,$pause,$s10" \
    "hdesk: step 20 of motion 4"$'\n' "$pause,screendump $B/run/g8-light-g20.ppm,$pause,meta_l-2,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,e,x,i,t,ret,$pause,meta_l-1,$pause,e,x,i,t,ret" > "$v8.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=2400 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$v8.mon MEM=128 APPEND=daphnis.stepframes \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$v8" > "$v8.rc"; wait)
 # MS-9a, gate 7: a float moved by key (MS-8; MS-R5: float to tile and back is an instant snap): Super+f snaps window
 # 0 to its floating frame at once (0 steps), then Super+Shift+Right moves it a cell, 10 and 20 steps; light after
 # Settings, a cell right again, then Super+f snaps it back to its tile at once (0 steps; a cell left rounds down onto
 # its target by step 10, so its mid frame would be the end's).
 v7=$B/run/g7.txt
 (SENDKEYS_WAIT=900 python3 tools/sendkeys.py "$v7.mon" "$v7" "hdesk: bar desktop 1 |Console| var |/|" "$pause,meta_l-f" \
    "hdesk: win 0 kind 1 desktop 1 mode 1 rank 2 frame 270,501 540x946 rects 1 270,501,540x946"$'\n'"hdesk: bar desktop 1 |Console|" "$pause,screendump $B/run/g7-dark-f0.ppm,$pause,meta_l-shift-right,$pause,$s10" \
    "hdesk: step 10 of motion 1"$'\n' "$pause,screendump $B/run/g7-dark-m10.ppm,$pause,$s10" \
    "hdesk: step 20 of motion 1"$'\n' "$pause,screendump $B/run/g7-dark-m20.ppm,$pause,meta_l,s,e,t,t,ret" \
    "hdesk: settings 1" "$pause,right,right" \
    "hdesk: theme 1" "$pause,esc" \
    "hdesk: settings closed" "$pause,meta_l-shift-right,$pause,$s10" \
    "hdesk: step 10 of motion 2"$'\n' "$pause,screendump $B/run/g7-light-m10.ppm,$pause,$s10" \
    "hdesk: step 20 of motion 2"$'\n' "$pause,screendump $B/run/g7-light-m20.ppm,$pause,meta_l-f" \
    "hdesk: win 0 kind 1 desktop 1 mode 0 rank 4 frame 8,36 1064x1876 rects 1 8,36,1064x1876"$'\n'"hdesk: bar desktop 1 |Console|" "$pause,screendump $B/run/g7-light-t0.ppm,$pause,e,x,i,t,ret" > "$v7.keys" 2>&1 &
 MODE=1080x1920 QEMU_TIMEOUT=900 POOL=max INITRD=$B/hdesk/release.cpio MONITOR=$v7.mon MEM=128 APPEND=daphnis.stepframes \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$v7" > "$v7.rc"; wait)
 for m in 2560x1440 3840x2160 5120x1440 2160x3840; do
     s=$B/run/smoke-$m.txt
     MODE=$m QEMU_TIMEOUT=60 INITRD=$B/tile/initrd.cpio MEM=128 tools/run-qemu.sh "$B/gcc-tile/kernel32.elf" "$s" > "$s.rc" &
 done
 wait
 for cc in gcc clang; do
     p=$B/run/hyb-$cc.txt
     MODE=$M QEMU_TIMEOUT=120 INITRD=$B/tile/initrd.cpio MEM=128 \
         tools/run-qemu.sh "$B/$cc-hyb/kernel32.elf" "$p" > "$p.rc" &
 done
 wait) &
for cc in gcc clang; do
    q=$B/run/hdesk-$cc.txt
    (SENDKEYS_WAIT=410 python3 tools/sendkeys.py "$q.mon" "$q" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
        "hdesk: terminal 1 slot 1" "$pause,$osc,ret" \
        "hdesk: bar desktop 1 |Console| var |/notes|" "$pause,c,d,spc,dot,dot,semicolon,spc,dot,slash,d,o,o,m,spc,minus,minus,s,e,a,l,e,d,ret" \
        "hdesk: pixel 2 ended" "$pause,alt-tab" \
        "hdesk: switcher chose 0" "$pause,alt-grave_accent" \
        "hdesk: switcher chose 1" "$pause,ctrl-alt-tab,right,right,ret" \
        "hdesk: switcher chose 0 (sticky)" "meta_l-m,meta_l,c,o,n,down,ret" \
        "hdesk: ff chose win |Console - /| window 0" "$pause,meta_l-z" \
        "hdesk: win 0 kind 1 desktop 1 mode 2" "meta_l-2" \
        "hdesk: layout desktop 2 focus -1" "$pause,meta_l-1,meta_l-z,meta_l-shift-right,meta_l-shift-left,meta_l-f" \
        "...mode 1 rank 4 frame 480,291 960x526" "meta_l-shift-right,meta_l-shift-right,meta_l-ctrl-down,meta_l-ctrl-right" \
        "...frame 496,291 968x542" "meta_l-f,meta_l-left,$pause,e,x,i,t,ret" \
        "hdesk: terminal 1 ended" "$pause,meta_l,s,e,t,t,ret" \
        "hdesk: settings 1" "right,tab,tab,tab,right,right,tab,ret,down,ret" \
        "hdesk: revert ask 1080x1920 from 1920x1080" "ret" \
        "hdesk: message gone" "tab,tab,right,right" \
        "hdesk: theme 1" "esc" \
        "hdesk: settings closed" "$pause,e,x,e,c,spc,g,r,a,n,t,spc,d,i,s,k,spc,s,h,ret" \
        "hdesk: grant 0 1" "$pause,mouse_move -104 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -100,mouse_move 0 -26,$pause,$pause,meta_l-m" \
        "...desktop 1 mode 3 rank 5" "$pause,meta_l-shift-m,$pause,meta_l-equal,meta_l-equal" \
        "hdesk: scale 3" "$pause,meta_l-minus,$pause,meta_l-c" \
        "hdesk: calendar open" "$pause,right" \
        "hdesk: calendar 2026-02" "$pause,left,$pause,e,x,i,t,ret" > "$q.keys" 2>&1 &
     MODE=$M QEMU_TIMEOUT=420 POOL=max INITRD=$B/hdesk/initrd.cpio MONITOR=$q.mon MEM=128 \
        tools/run-qemu.sh "$B/$cc-hdesk/kernel32.elf" "$q" > "$q.rc"; wait) &
done
wait
for m in 2560x1440 3840x2160 5120x1440 2160x3840; do
    s=$B/run/smoke-$m.txt
    python3 - "$s" <<'EOF' > "$s.cmp" 2>&1
import hashlib, importlib.util, re, sys
spec = importlib.util.spec_from_file_location("ct", "tools/check-tiler.py")
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
text = open(sys.argv[1], encoding="ascii", errors="replace").read()
at = ct.screen_of(text)
full = hashlib.sha256(ct.pattern(ct.W, ct.H)).hexdigest()
frame = hashlib.sha256(ct.surface("tiles", 2, 2)).hexdigest()
shots = re.findall(at, text, re.M)
own = re.findall(at.replace("daphnis: surface", "tiler: surface"), text, re.M)
ok = shots[:1] == [full] and own[:1] == [frame] and "mcifb: drawn" in text
print("PASS" if ok else "FAIL", ct.W, ct.H, "fullscreen", full[:16], "frame", frame[:16], shots[:1], own[:1])
EOF
    grep -q '^PASS' "$s.cmp" \
        && line ok "smoke $m gcc: mcifb maps and draws the whole framebuffer; the tiler's 2x2 frame is the Python's" \
        || line bad "smoke $m gcc" "$(cat "$s.cmp")"
done

for cc in gcc clang; do
    p=$B/run/hyb-$cc.txt
    [ "$(cat "$p.rc")" = 33 ] && [ ! -s "$p.err" ] \
        && line ok "boot hyb $M $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot hyb $M $cc" "status $(cat "$p.rc"), stderr $(wc -c < "$p.err") bytes"
    python3 tools/check-tiler.py --place "$p" > "$B/hyb-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/hyb-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/hyb-$cc.cmp")" = 4 ] && ! grep -q '^FAIL' "$B/hyb-$cc.cmp" \
        && line ok "place $M $cc: 2x, two 1x rectangles and a hidden window; the screen is the Python's" \
        || line bad "place $M $cc" "see $B/hyb-$cc.cmp"
done

for cc in gcc clang; do
    q=$B/run/hdesk-$cc.txt
    [ "$(cat "$q.rc")" = 33 ] && [ ! -s "$q.err" ] \
        && line ok "boot hdesk $M $cc: QEMU exit status 33, nothing on stderr" \
        || line bad "boot hdesk $M $cc" "status $(cat "$q.rc"), stderr $(wc -c < "$q.err") bytes"
    python3 tools/check-hdesk.py "$q" "$B/doom.frame" "$data/e1m6.wad" > "$B/hdesk-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/hdesk-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/hdesk-$cc.cmp")" = 8 ] && ! grep -q '^FAIL' "$B/hdesk-$cc.cmp" \
        && line ok "hdesk $M $cc: layouts, placements, the steps, the clock and calendar, doom and the screen are the Python's" \
        || line bad "hdesk $M $cc" "see $B/hdesk-$cc.cmp"
done
for cc in gcc clang; do
    q=$B/run/hdesk-$cc.txt
    grep -a '^hdesk: ff ' "$q" | sed 's/pid [0-9]*/pid N/g' > "$B/hdesk-ff-$cc.out"
    cmp -s tests/expected/hdesk-ff.out "$B/hdesk-ff-$cc.out" \
        && line ok "plane $M $cc: the Super plane's \`hdesk: ff\` lines (its opens, queries, rows and choices, pids as N) equal tests/expected/hdesk-ff.out (FF-5)" \
        || line bad "plane $M $cc: vs tests/expected/hdesk-ff.out" "see $B/hdesk-ff-$cc.out"
done
p=$B/run/portrait.txt
[ "$(cat "$p.rc")" = 33 ] && python3 tools/check-hdesk.py --smoke "$p" > "$B/portrait.cmp" 2>&1 \
    && line ok "portrait 1080x1920 gcc: the desk boots straight into portrait and stacks two terminals (HX-12 A)" \
    || line bad "portrait 1080x1920 gcc" "status $(cat "$p.rc"), see $B/portrait.cmp"
w=$B/run/bars.txt
[ "$(cat "$w.rc")" = 33 ] && python3 tools/check-hdesk.py --bars "$w" > "$B/bars.cmp" 2>&1 \
    && line ok "bars 1080x1920 gcc: a float's bar drags it, a double click and F11 toggle fullscreen, each button acts on release, close ends the whole session (WB-1, WB-4)" \
    || line bad "bars 1080x1920 gcc" "status $(cat "$w.rc"), see $B/bars.cmp"
z=$B/run/zones.txt
[ "$(cat "$z.rc")" = 33 ] && python3 tools/check-hdesk.py --zones "$z" > "$B/zones.cmp" 2>&1 \
    && line ok "zones 1080x1920 gcc: drops at the left and right edges, a corner and the top tile or fill as WB-2 says; a Super-dragged tile re-tiled at a corner (WB-R1 A, WB-R3 A)" \
    || line bad "zones 1080x1920 gcc" "status $(cat "$z.rc"), see $B/zones.cmp"
v=$B/run/switcher.txt
[ "$(cat "$v.rc")" = 33 ] && python3 tools/check-hdesk.py --switcher "$v" > "$B/switcher.cmp" 2>&1 \
    && line ok "switcher 1080x1920 gcc: six terminals, E2-2's 520 px card on the screen, Down a row (K-1)" \
    || line bad "switcher 1080x1920 gcc" "status $(cat "$v.rc"), see $B/switcher.cmp"
r=$B/run/kern.txt
[ "$(cat "$r.rc")" = 33 ] && python3 tools/check-hdesk.py --kern "$r" > "$B/kern.cmp" 2>&1 \
    && line ok "kern 1080x1920 gcc: kern asks the desk; Esc refuses, Super+Enter runs in ring 0, the window holds it with no prompt until its hold ends; the cadmium window, with no KERN pill (DN-72), is the Python's screen (R0-1 to R0-3)" \
    || line bad "kern 1080x1920 gcc" "status $(cat "$r.rc"), see $B/kern.cmp"
a=$B/run/panel.txt
[ "$(cat "$a.rc")" = 33 ] && python3 tools/check-hdesk.py --panel "$a" > "$B/panel.cmp" 2>&1 \
    && line ok "panel 1080x1920 gcc: the device read at desk start (P2-c); the system panel by click names the program holding the audio stream; Left and a click on the slider set the volume; each click where the desk's lines place it; the open panel, the squares and the chevron are the Python's screen (SP-1, DN-34)" \
    || line bad "panel 1080x1920 gcc" "status $(cat "$a.rc"), see $B/panel.cmp"
u=$B/run/sound.txt
[ "$(cat "$u.rc")" = 33 ] && python3 tools/check-accounts.py "$u" "hdesk: panel open" "hdesk: panel sound settings" \
    "hdesk: panel closed" "hdesk: settings page 2" "hdesk: volume 95" "hdesk: volume 90" "hdesk: volume 85" \
    "hdesk: volume 90" "hdesk: volume 100" "hdesk: settings defaults" "hdesk: settings closed" > "$u.cmp" 2>&1 \
    && line ok "sound 1080x1920 gcc: the panel's Sound Settings opens Settings on the Sound page and closes the panel; Right goes from the sidebar into the page at Volume (ST-K1), Left steps the volume 5 at a time to 85, Right to 90, Tab and Enter on Restore Defaults back to 100 (DN-24, DN-25)" \
    || line bad "sound 1080x1920 gcc" "status $(cat "$u.rc"), $(cat "$u.cmp"), see $u"
g=$B/run/traymin.txt
[ "$(cat "$g.rc")" = 33 ] && [ "$(grep -a '^hdesk: tray 1 \(minimized\|in\)$' "$g" | tr '\n' '/')" = "hdesk: tray 1 minimized/hdesk: tray 1 in/" ] \
    && line ok "tray -m gcc: \`tray -m cat\` asks that its window minimize to the tray (bit 33): it stays on the desk, and Super+M sends it to the tray, not to the desk's minimized windows (SP-6, DN-16)" \
    || line bad "tray -m gcc" "status $(cat "$g.rc"), see $g"
y=$B/run/tray.txt
[ "$(cat "$y.rc")" = 33 ] && python3 tools/check-hdesk.py --tray "$y" "$B/run/tray-0.ppm" "$B/run/tray-8.ppm" "$B/run/tray-16.ppm" > "$B/tray.cmp" 2>&1 \
    && line ok "tray 1080x1920 gcc: tray cat hides its window in the tray, and the Super plane leaves it out; the chevron's frames 0, 8 and 16 of its 160 ms turn are the Python's; the plate's cell restores it, a right click quits it; the plate open at rest is the Python's screen (SP-2, DN-14, DN-15)" \
    || line bad "tray 1080x1920 gcc" "status $(cat "$y.rc"), see $B/tray.cmp"
v=$B/run/slide.txt
[ "$(cat "$v.rc")" = 33 ] && python3 tools/check-hdesk.py --slide "$v" "$B/run/slide-rest2.ppm" \
    "$B/run/slide-start.ppm" "$B/run/slide-mid.ppm" "$B/run/slide-end.ppm" > "$B/slide.cmp" 2>&1 \
    && line ok "slide 1920x1080 gcc: Super+1 to 9 and the window list's jump slide the desks 240 ms on the out \
curve; Super+1's frames 0 and 12 are the Python's; the jump focuses its window when the slide ends (MS-7, DN-54)" \
    || line bad "slide 1920x1080 gcc" "status $(cat "$v.rc"), see $B/slide.cmp"
[ "$(cat "$v4.rc")" = 33 ] && python3 tools/check-hdesk.py --motion 4 "$v4" "$B/run" > "$B/g4.cmp" 2>&1 \
    && line ok "gate 4 1080x1920 gcc: the system panel opening after 8 and 16 steps and closing after 5 and 10, dark and light, each the Python's frame in motion (MS-5, MS-9a)" \
    || line bad "gate 4 1080x1920 gcc" "see $B/g4.cmp"
[ "$(cat "$v8.rc")" = 33 ] && python3 tools/check-hdesk.py --motion 8 "$v8" "$B/run" > "$B/g8.cmp" 2>&1 \
    && line ok "gate 8 1080x1920 gcc: the bar message in after 8 and 16 steps and fading out after its hold, 10 and 20 steps, dark and light, each the Python's frame in motion (MS-5, MS-9a)" \
    || line bad "gate 8 1080x1920 gcc" "see $B/g8.cmp"
[ "$(cat "$v7.rc")" = 33 ] && python3 tools/check-hdesk.py --motion 7 "$v7" "$B/run" > "$B/g7.cmp" 2>&1 \
    && line ok "gate 7 1080x1920 gcc: Super+f snaps to float and back at once (MS-R5), and a float moved by key a cell right after 10 and 20 steps, dark and light, equals the Python's frame (MS-8, MS-9a)" \
    || line bad "gate 7 1080x1920 gcc" "see $B/g7.cmp"
python3 tools/wbbtn.py --check \
    && line ok "wbbtn: user/ci/kit/wbbtn.ci is what tools/wbbtn.py writes from agy's button bitmaps (WB-5)" \
    || line bad "wbbtn" "regenerate user/ci/kit/wbbtn.ci with tools/wbbtn.py"
w=$B/run/power-shutdown.txt
[ "$(cat "$w.rc")" = 33 ] && [ "$(grep -a '^hdesk: ff a' "$w" | tr '\n' '/')" = "hdesk: ff armed 3/hdesk: ff action 3/" ] \
    && ! grep -q '^hdesk: end ' "$w" \
    && [ "$(tail -2 "$w" | tr '\n' '/')" = "daphnis: shut down/daphnis: done/" ] \
    && [ "$(grep -c '^daphnis: exit 0$' "$w")" = 1 ] \
    && line ok "shut down gcc: Super+Shift+Q arms \`Shut Down\` (no window ends), again within 2 s ends both terminals and the desk (exit 0), then the machine, status 33 (FF-4, FF-R6 B)" \
    || line bad "shut down gcc" "status $(cat "$w.rc"), see $w"
f=$B/run/finder.txt
fv=$(grep -a '^hdesk: bar desktop 1 |Index| var ' "$f" | sed 's/.* var |\([^|]*\)|.*/\1/' | uniq | tr '\n' ' ')
[ "$(cat "$f.rc")" = 33 ] && [ "$fv" = "/ /etc / /etc " ] && [ -s "$B/run/finder-root.ppm" ] \
    && grep -q '^hdesk: open |/etc/motd| window 1$' "$f" && grep -Fqx "hdesk: ff runs |ced '/etc/motd'|" "$f" \
    && line ok "finder gcc: \`finder /\` names / on the bar; \`etc\` and Enter go into /etc (the filter keeps it), Backspace up, Alt+Left back; Enter on motd asks the desk, which opens it in ced (FF-6b, FF-6c); Super+Shift+Q twice shuts down" \
    || line bad "finder gcc" "status $(cat "$f.rc"), bar variables |$fv|, see $f"
m=$B/run/finder-menu.txt
mv=$(grep -a '^hdesk: bar desktop 1 |Index| var ' "$m" | sed 's/.* var |\([^|]*\)|.*/\1/' | uniq | tr '\n' ' ')
[ "$(cat "$m.rc")" = 33 ] && [ "$(grep -ac '^finder: menu FOLDER at ' "$m")" = 3 ] && [ -s "$B/run/finder-menu.ppm" ] \
    && [ "$(grep -ac '^finder: menu EMPTY at ' "$m")" = 2 ] && grep -q '^finder: sort size$' "$m" \
    && grep -q '^finder: view table$' "$m" && [ -s "$B/run/finder-menu-view.ppm" ] \
    && grep -q '^finder: menu chose |Copy as Path|$' "$m" && grep -q '^finder: menu chose |Open|$' "$m" \
    && [ "$(echo "$mv" | cut -d' ' -f1)" = / ] && [ "$(echo "$mv" | cut -d' ' -f2)" != / ] && [ -n "$(echo "$mv" | cut -d' ' -f2)" ] \
    && line ok "finder menu gcc: with nothing kept the Menu key opens EMPTY, Sort By Size and View Table apply (DN-35); the Menu key opens DN-32's menu on the selected folder, Down three times and Enter choose Copy as Path (not built yet), Shift+F10 opens it and Esc closes it, Enter on Open goes in (DN-32, DN-33)" \
    || line bad "finder menu gcc" "status $(cat "$m.rc"), bar variables |$mv|, see $m"
w=$B/run/power-restart.txt
[ "$(cat "$w.rc")" = 0 ] && [ "$(grep -a '^hdesk: ff a\|^hdesk: ff disarmed' "$w" | tr '\n' '/')" = "hdesk: ff armed 2/hdesk: ff disarmed/hdesk: ff action 2/" ] \
    && [ "$(tail -1 "$w")" = "daphnis: restart" ] && [ "$(grep -c '^daphnis: exit 0$' "$w")" = 1 ] \
    && line ok "restart gcc: Super+Shift+R arms \`Restart\`, which lapses after 2 s; a click on the power button, then on Restart in its menu (DN-47), ends the desk (exit 0), then the 8042 resets the machine, QEMU status 0 (FF-4, FF-R6 B)" \
    || line bad "restart gcc" "status $(cat "$w.rc"), see $w"

# AC-1c (docs/specs/2026-11-08-ac-accounts.md section 6): the desk on a volume for accounts (tools/mkdisk.sh with
# ACCOUNTS), five boots at once, keys through the monitor, -cpu max so authd draws its salts (A-3):
#   child: sam logs in (one wrong passphrase on the lock), `grant net` asks PARENT APPROVAL and ada's passphrase
#     answers it; sam's `kern` is refused with Esc, and asked again at once is refused with no prompt (AC-D4);
#     Super+L locks; `cat /home/.daphnis/accounts || exit` is refused by the kernel, so the shell ends: log out;
#   parent: ada's own `kern` takes their passphrase (L9); in its hold `kern accounts add ivy child net` enrolls a
#     child, whom the login screen offers after the log out, and who logs in;
#   first: an empty store is first boot: a parent made at DS-6's parameters, logged in, logged out.
#   elev: the desk side of elevation: sam's `grant net` brings PARENT APPROVAL in frame 8's parts (screendumped and
#     measured: tools/check-hdesk.py --approval); Super+Enter with the field empty and then a wrong passphrase answer
#     nothing; ada's passphrase grants the net bit, once; sam's `kern` asks again and Super+L refuses it and
#     locks (AC-D5); sam's passphrase unlocks with no prompt back; log out.
#   idle (AC-D5): ada sets sam's idle to 1 minute (`kern accounts idle sam 1`, ada's passphrase); sam logs in and
#     does nothing until the desk locks (`hdesk: idle lock after 1 min`, the clock's minute, -cpu max's live date);
#     sam unlocks, opens the plane with a Super tap, opens the power menu (the restart leg's aim) and clicks Lock, its
#     first row (DN-47), which locks as Super+L; sam unlocks and logs out.
sam=s,a,m,minus,p,a,s,s
har=s,e,v,e,n,h,o,r,s,e,s,r,u,n
ivy=i,v,y,minus,p,a,s,s
for r in child parent first elev idle; do
    a=$B/run/ac-$r.txt
    if [ $r = first ]; then ACCOUNTS= tools/mkdisk.sh "$a.img" > /dev/null; else
        ACCOUNTS=tests/ac/accounts.txt tools/mkdisk.sh "$a.img" > /dev/null; fi
done
a=$B/run/ac-child.txt
(SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: accounts 2" "down,$sam,ret" \
    "hdesk: bar desktop 1 |Console|" "$pause,g,r,a,n,t,spc,n,e,t,spc,e,c,h,o,spc,o,k,ret" \
    "hdesk: approval ask want 2 uid 1001" "$har,ret" \
    "hdesk: grant 2 to pid" "$pause,k,e,r,n,spc,e,c,h,o,spc,x,ret" \
    "hdesk: approval ask want 8 uid 1001" "esc" \
    "hdesk: kern refused pid" "$pause,k,e,r,n,spc,e,c,h,o,spc,x,ret" \
    "hdesk: refused at once pid" "$pause,meta_l-l" \
    "hdesk: lock sam" "x,ret" \
    "hdesk: auth refused sam" "$sam,ret" \
    "hdesk: unlock sam" "$pause,c,a,t,spc,slash,h,o,m,e,slash,dot,d,a,p,h,n,i,s,slash,a,c,c,o,u,n,t,s,spc,shift-backslash,shift-backslash,spc,e,x,i,t,ret" \
    "hdesk: logout sam" "meta_l-esc" > "$a.keys" 2>&1 &
 CPU=max POOL=max MEM=512 QEMU_TIMEOUT=420 INITRD=$B/hdesk/release.cpio MONITOR=$a.mon DISK=$a.img \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait) &
a=$B/run/ac-parent.txt
(SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: accounts 2" "$har,ret" \
    "hdesk: bar desktop 1 |Console|" "$pause,k,e,r,n,spc,e,c,h,o,spc,y,ret" \
    "hdesk: approval ask want 8 uid 1000" "$har,ret" \
    "hdesk: kern 0 pid" "$pause,k,e,r,n,spc,a,c,c,o,u,n,t,s,spc,a,d,d,spc,i,v,y,spc,c,h,i,l,d,spc,n,e,t,ret,$pause,$ivy,ret,$pause,$ivy,ret,$pause,e,x,i,t,ret" \
    "hdesk: accounts 3" "down,down,$ivy,ret" \
    "hdesk: login ivy uid 1002" "$pause,e,x,i,t,ret" \
    "hdesk: logout ivy" "meta_l-esc" > "$a.keys" 2>&1 &
 CPU=max POOL=max MEM=512 QEMU_TIMEOUT=420 INITRD=$B/hdesk/release.cpio MONITOR=$a.mon DISK=$a.img \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait) &
a=$B/run/ac-first.txt
(SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: accounts first boot" \
    "a,d,a,tab,$har,tab,$har,ret" "hdesk: bar desktop 1 |Console|" "$pause,e,x,i,t,ret" \
    "hdesk: logout ada" "meta_l-esc" > "$a.keys" 2>&1 &
 CPU=max POOL=max MEM=512 QEMU_TIMEOUT=420 INITRD=$B/hdesk/release.cpio MONITOR=$a.mon DISK=$a.img \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait) &
a=$B/run/ac-idle.txt
(SENDKEYS_WAIT=600 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: accounts 2" "$har,ret" \
    "hdesk: bar desktop 1 |Console|" "$pause,k,e,r,n,spc,a,c,c,o,u,n,t,s,spc,i,d,l,e,spc,s,a,m,spc,1,ret" \
    "hdesk: approval ask want 8 uid 1000" "$har,ret" \
    "hdesk: kern 0 pid" "$pause,$pause,e,x,i,t,ret" \
    "hdesk: logout ada" "down,$sam,ret" \
    "hdesk: login sam uid 1001" "$pause" \
    "hdesk: idle lock after 1 min" "$sam,ret" \
    "hdesk: unlock sam" "$pause,meta_l" \
    "hdesk: ff open" "$pause,mouse_move 100 0,mouse_move 100 0,mouse_move 100 0,mouse_move 26 0,mouse_move 0 -70,mouse_button 1,mouse_button 0" \
    "hdesk: ff power menu" "$pause,mouse_move -70 -152,mouse_button 1,mouse_button 0" \
    "hdesk: lock sam@@2" "$sam,ret" \
    "hdesk: unlock sam@@2" "$pause,e,x,i,t,ret" \
    "hdesk: logout sam" "meta_l-esc" > "$a.keys" 2>&1 &
 CPU=max POOL=max MEM=512 QEMU_TIMEOUT=600 INITRD=$B/hdesk/release.cpio MONITOR=$a.mon DISK=$a.img MODE=1920x1080 \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait) &
a=$B/run/ac-elev.txt
(SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$a.mon" "$a" "hdesk: accounts 2" "down,$sam,ret" \
    "hdesk: bar desktop 1 |Console|" "$pause,g,r,a,n,t,spc,n,e,t,spc,e,c,h,o,spc,o,k,ret" \
    "hdesk: approval ask want 2 uid 1001" "$pause,screendump $a.ppm,$pause,meta_l-ret,$pause,x,x,x,x,ret" \
    "hdesk: approval wrong passphrase" "$har,ret" \
    "hdesk: grant 2 to pid" "$pause,k,e,r,n,spc,e,c,h,o,spc,x,ret" \
    "hdesk: approval ask want 8 uid 1001" "$pause,meta_l-l" \
    "hdesk: lock sam" "$sam,ret" \
    "hdesk: unlock sam" "$pause,e,x,i,t,ret" \
    "hdesk: logout sam" "meta_l-esc" > "$a.keys" 2>&1 &
 CPU=max POOL=max MEM=512 QEMU_TIMEOUT=420 INITRD=$B/hdesk/release.cpio MONITOR=$a.mon DISK=$a.img \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$a" > "$a.rc"; wait) &
wait
a=$B/run/ac-child.txt
[ "$(cat "$a.rc")" = 33 ] && python3 tools/check-accounts.py "$a" "hdesk: accounts 2" "hdesk: login sam uid 1001" \
    "hdesk: approval ask want 2 uid 1001" "hdesk: approved by ada" "hdesk: grant 2 to pid" \
    "hdesk: approval ask want 8 uid 1001" "hdesk: kern refused pid" "hdesk: refused at once pid" "hdesk: lock sam" \
    "hdesk: auth refused sam" "hdesk: unlock sam" "hdesk: logout sam" "hdesk: shut down from the account screen" \
    '!sevenhorsesrun' '!sam-pass' > "$a.cmp" 2>&1 \
    && line ok "accounts child gcc: login, PARENT APPROVAL for net by a parent's passphrase, kern refused then refused at once (AC-D4), lock with a wrong passphrase, the store refused to the child, log out" \
    || line bad "accounts child gcc" "status $(cat "$a.rc"), $(cat "$a.cmp"), see $a"
a=$B/run/ac-parent.txt
[ "$(cat "$a.rc")" = 33 ] && python3 tools/check-accounts.py "$a" "hdesk: accounts 2" "hdesk: login ada uid 1000" \
    "hdesk: approval ask want 8 uid 1000" "hdesk: approved by ada" "hdesk: kern 0 pid" "hdesk: logout ada" \
    "hdesk: accounts 3" "hdesk: login ivy uid 1002" "hdesk: logout ivy" '!sevenhorsesrun' '!ivy-pass' > "$a.cmp" 2>&1 \
    && line ok "accounts parent gcc: a parent's own kern takes their passphrase (L9); \`kern accounts add\` enrolls a child who logs in" \
    || line bad "accounts parent gcc" "status $(cat "$a.rc"), $(cat "$a.cmp"), see $a"
a=$B/run/ac-first.txt
[ "$(cat "$a.rc")" = 33 ] && python3 tools/check-accounts.py "$a" "hdesk: accounts first boot" "hdesk: first boot enroll" \
    "hdesk: first parent ada uid 1000" "hdesk: login ada uid 1000" "hdesk: logout ada" \
    '!sevenhorsesrun' > "$a.cmp" 2>&1 \
    && line ok "accounts first gcc: an empty store is first boot; the parent is enrolled at DS-6's parameters and logs in" \
    || line bad "accounts first gcc" "status $(cat "$a.rc"), $(cat "$a.cmp"), see $a"
a=$B/run/ac-idle.txt
[ "$(cat "$a.rc")" = 33 ] && python3 tools/check-accounts.py "$a" "hdesk: screen 1920x1080" "hdesk: accounts 2" \
    "hdesk: login ada uid 1000" "hdesk: approval ask want 8 uid 1000" "hdesk: approved by ada" \
    "hdesk: logout ada" "hdesk: login sam uid 1001" "hdesk: idle lock after 1 min" "hdesk: lock sam" \
    "hdesk: unlock sam" "hdesk: ff open" "hdesk: ff action 4" "hdesk: lock sam" "hdesk: unlock sam" \
    "hdesk: logout sam" "hdesk: shut down from the account screen" '!sevenhorsesrun' '!sam-pass' > "$a.cmp" 2>&1 \
    && [ "$(grep -c '^hdesk: idle lock' "$a")" = 1 ] \
    && line ok "accounts idle gcc: \`kern accounts idle sam 1\` (AC-D5); sam's session idle a minute locks and takes sam's passphrase back; the plane's Lock locks as Super+L does" \
    || line bad "accounts idle gcc" "status $(cat "$a.rc"), $(cat "$a.cmp"), see $a"
a=$B/run/ac-elev.txt
[ "$(cat "$a.rc")" = 33 ] && [ -s "$a.ppm" ] && python3 tools/check-hdesk.py --approval "$a" "$a.ppm" > "$a.cmp" 2>&1 \
    && line ok "accounts elevation gcc: PARENT APPROVAL in frame 8's parts on sam's desk; Super+Enter with an empty field and a wrong passphrase answer nothing; ada's passphrase grants net once; Super+L refuses sam's kern and locks (AC-D5)" \
    || line bad "accounts elevation gcc" "status $(cat "$a.rc"), $(cat "$a.cmp"), see $a"

# 4. housekeeping
python3 -B tools/check-auth-helper.py "$B" "$B/auth-helper" > "$B/auth-helper.log" 2>&1 \
    && line ok "accounts helper gcc: no inherited disk access; login and logout complete" \
    || line bad "accounts helper gcc" "see $B/auth-helper.log"

python3 -B tools/check-account-recovery.py "$B" "$B/account-recovery" > "$B/account-recovery.log" 2>&1 \
    && line ok "accounts recovery gcc: complete backup login; unreadable stores refuse enrollment" \
    || line bad "accounts recovery gcc" "see $B/account-recovery.log"

CINT="$(command -v cint)" CINT_TOOLCHAIN="$CINT_TOOLCHAIN" python3 -B tools/check-accounts-helper.py "$B" "$B/accounts-enroll-helper" --use-initrd-accounts > "$B/accounts-enroll-helper.log" 2>&1 \
    && line ok "accounts enroll helper gcc: inherited grants removed; failures preserve the store" \
    || line bad "accounts enroll helper gcc" "see $B/accounts-enroll-helper.log"

python3 -B tools/check-raw-input.py "$B" "$B/account-boundaries" > "$B/account-boundaries.log" 2>&1 \
    && line ok "account boundaries gcc: raw input denied, session fds closed, pipe reads nonblocking, signals isolated" \
    || line bad "account boundaries gcc" "see $B/account-boundaries.log"

python3 -B tools/test_approval_evidence.py > "$B/approval-evidence.log" 2>&1 && APPROVAL_USE_BUNDLED=1 python3 -B tools/check-approval-binding.py "$B" "$B/approval-binding" > "$B/approval-binding.log" 2>&1 \
    && line ok "approval binding gcc: canceled, exited, locked, logged out and expired verdicts cannot grant authority" \
    || line bad "approval binding gcc" "see $B/approval-binding.log"

# PR 225 P1: authd's "ok" for an unlock asked before a log out arrives after it (the session's first shell ends while
# the probe holds the verify): the desk drops it (`hdesk: auth stale ignored`), stays at the names, and Super+Enter
# then starts no shell; with accounts on and no session new_term refuses (`hdesk: no session, no shell`).
python3 -B tools/check-unlock-race.py "$B" "$B/unlock-race" > "$B/unlock-race.log" 2>&1 \
    && line ok "unlock race gcc: a stale unlock after the log out is ignored; no session, no shell, no uid-0 process" \
    || line bad "unlock race gcc" "see $B/unlock-race.log"

# PR 225 review P1: a closed terminal window gives its pty pair back (8 in the kernel): 9 terminals opened and ended
# in one session, and 9 sessions logged in and out, each opens its terminal.
python3 -B tools/check-pty-reuse.py "$B" "$B/pty-reuse" > "$B/pty-reuse.log" 2>&1 \
    && line ok "pty reuse gcc: 9 terminals and 9 sessions each open a terminal; every closed window gives its pair back" \
    || line bad "pty reuse gcc" "see $B/pty-reuse.log"

[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, within $BUDGET s" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
