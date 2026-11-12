#!/usr/bin/env bash
# tests/rs/guest/train.sh l-1|l-2|l-3|k [--gates]: the guest legs of one train of batch l (stage RS; the lane split of
# 2026-11-11 19:10Z, section 1) or of batch k, on hyde or morp, from the train's candidate checkout; make builds every
# program the image takes from source at HEAD ($B/ubin, RG-1), never the committed user/bin. One PASS or FAIL line per check, the count computed from the legs
# this train runs (GW-1: no literal count for a PR to move), RESULT last; exit status 1 if any FAIL.
#   image (RG-1, l 2026-11-12 07:53Z): every leg boots the release image, hdesk/release.cpio (HW-17), as the Makefile
#     builds it, with the legs' scripts and files under /rs and nothing else (guest.py cpio refuses any other path).
#     /rs/ced is a copy of kern under /rs, the title leg's hostile program, never on the image's own path. No leg needs
#     Doom; it is fetched for `all`, whose gates' image, hdesk/initrd.cpio, --gates runs.
#   boot: the hdesk kernels on gcc and clang, 1920 x 1080 and 512 MiB, first; tests/rs/guest/guest.py pool reads both
#     transcripts, and a state pool fault (rt/ctx.c state_fault, `host.resource`) stops the run at once with a banner
#     naming RTDEF_user's pool (board 20261111T185628Z), since no leg after it says anything about a unit.
#   l-1 (308, 316, 319, 321, 323, AC-Q), on volumes of tests/ac/accounts.txt (tools/mkdisk.sh with ACCOUNTS):
#     store: ops/store.ops through authd from ada's terminal: as the session (/rs/s1), no store; then `kern true`
#       (the window's hold) and (/rs/s2) role, ceil, add, passwd and remove answer as RS-ROLE and RS-R4 say; then the
#       volume's store (expected/store.vol). Each answer is in /home/ada/rs.log and the scripts' stderr in rs.err,
#       both printed from the volume, with row 2's answer (authd as the session, at ring 3) on its own line.
#     homes: ada adds eve; eve's first login makes eve's home and Documents, Downloads and Pictures as eve; ada
#       removes eve (the home set aside as .removed.eve.1002) and adds eve again; eve's next login gets uid 1003 and a
#       new home (expected/homes.vol).
#     title: three refused asks for ring 0: `kern true`; a copy of kern named ced, run with exec; `kern true` after
#       the program titled its window "Parent approved" (OSC 2). The prompt's left part is one picture in all three
#       (guest.py card): a program's name is never the title (AC-T, AC-Tw), its title never in the prompt (AC-V).
#     quote: Index opens /rs/it's $(kern true); the desk types it as one quoted word and no prompt for ring 0 shows.
#     launch (AC-Q's pty case, board 20261111T191835Z): Index opens two files whose lines are `ced '/rs/NAME'` of 251
#       and 250 bytes. The desk types an app as `exec ` and its line (kit/launch.ci), so 251 is refused before any
#       byte is typed (`hdesk: launch none`) and 250 is 255 bytes and Enter on Daphnis's own pty (src/pty.ci EDIT): Edit
#       opens as the terminal's process and Ctrl+Q ends the terminal with status 0, so no byte of the line was dropped.
#   l-2 (pages and apps): view, `cview -d` of a 3840 x 2160 PNG at the 512 MiB floor, then View's window shows it
#     (guest.py color); calc, ccalc's arithmetic in the guest and Calc's window drawing `6*7=` (guest.py differ). The
#     Settings pages (304, 307, 310, 312, 315, 317, 320), RS-TZa (301), U-PNG (288) and U-SET (289) are kits with
#     hosted tests until mini wires them into the desk; no leg here sees them.
#   l-3 (kernel, Monitor, Index): monitor, Monitor's window reading the machine (two screendumps differ); quote again,
#     through the Index units; openhome (RG-1), the release image as it ships (no /rs) on a volume of
#     tests/ac/accounts.txt: ada types a note into ada's 0700 home and opens Index on it; the desk peeks it as ada
#     (runas.h RUN_PEEK) and Edit opens it: the booted frame run/openhome.txt.a.ppm. The kernel units' own guest probes (mstamp, mfacts, mrevoke, mcut) are check.sh's and
#     check-revoke.sh's: --gates runs them.
#   k (272, 282, 287, 300 on batch k's tip):
#     about_console: Console runs `sleep 15; ls -l /bin`; the About sheet (DN-43) opens over it from the App pill; ls's
#       output scrolls the window around the sheet and never over it (guest.py sheet ... moved); a line typed while it
#       is up is the sheet's, Enter closes it, and no byte reached the shell (no /tmp/leak).
#     about_read: the sheet over Read (cless) takes q and Enter: Read is still open after it closes, and ends on q.
#     about_settings: the sheet over Settings takes Down, Right and Enter: no Settings page moves, and Esc then
#       closes Settings.
#     about_index: the sheet over Index takes F5 (Index reads no directory while it is up) and stays one picture; F5
#       after it closes reads the directory again.
#     trash (FF 3h, review on PR 287): on a volume, `ln -s notes/a.txt link`, then Index's Move to Trash from the
#       keyed menu; `finder --trash` lists the link (a link that points nowhere in the trash is listed as itself); the
#       volume holds .trash/items and .trash/records 0700 and no link where it was (expected/trash.vol).
#     launch, as in l-1, on batch k's pl_path (PR 300's limits: an app's line holds 250 bytes, a command's 255).
#     PR 282's legs are check-net.sh's (DHCP, TCP): --gates runs it. Its NIC on IRQ 7 or 15 has no QEMU setting
#     (SeaBIOS routes the PCI links to IRQs 10 and 11), so no leg here sees it.
#   --gates: then each gate script the train touches, one line each from its own RESULT (FAIL if the tree lacks it),
#     with its own DAPHNIS_BUILD under this one.
# Outputs under $DAPHNIS_BUILD (default ~/daphnis-work/build-rs-TRAIN), cleared as check.sh clears its own. Keys go
# through the monitor (tools/sendkeys.py); every mark is the start of a transcript line, which sendkeys counts both
# before AC-R1 (anywhere) and after it (at a line's start). A leg types short lines (`kern true`, `sh /rs/X`) and
# keeps longer command text in /rs scripts (sh/), since a key the kernel drops garbles what it types; a transcript
# with `daphnis: input dropped` fails the leg's marks line on that (guest.py MARKS; board 20261112T012351Z). Every leg
# boots with daphnis.pool=max (POOL=max), as the hdesk legs do.
set -u
cd "$(dirname "$0")/../../.."
T=${1:-}
GATES=0
[ "${2:-}" = --gates ] && GATES=1
case "$T" in
    l-1) LEGS="store homes title quote launch"; GATE_SCRIPTS="check.sh check-hybrid.sh check-disk.sh" ;;
    l-2) LEGS="view calc"; GATE_SCRIPTS="check.sh check-basics.sh check-hybrid.sh" ;;
    l-3) LEGS="monitor quote openhome"
         GATE_SCRIPTS="check.sh check-tiler.sh check-hybrid.sh check-disk.sh check-revoke.sh" ;;
    k) LEGS="about_console about_read about_settings about_index trash launch"
       GATE_SCRIPTS="check.sh check-hybrid.sh check-net.sh" ;;
    *) echo "usage: tests/rs/guest/train.sh l-1|l-2|l-3|k [--gates]"; exit 2 ;;
esac
if [ $# -gt 2 ] || { [ $# = 2 ] && [ $GATES = 0 ]; }; then
    echo "usage: tests/rs/guest/train.sh l-1|l-2|l-3|k [--gates]"; exit 2
fi
B=${DAPHNIS_BUILD:-$HOME/daphnis-work/build-rs-$T}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$HOME/cint-work/build-pin/out/cint.toolchain}
G=tests/rs/guest
BUDGET=1500   # the legs run at once; homes is the longest (four Argon2id runs at DS-6's 64 MiB under TCG)
M=1920x1080
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 want=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
plan() { want=$((want + $1)); }   # the lines a check block prints, counted before it runs
fail_exit() { echo "train.sh $T: $*"; echo "RESULT: FAIL"; exit 1; }
gx() { python3 "$G/guest.py" "$@"; }
kt() { gx keys "$1" || fail_exit "guest.py keys: $1"; }
rc() { cat "$1.rc" 2>/dev/null || echo none; }
ran() { [ "$(rc "$1")" = 33 ] && [ ! -s "$1.err" ]; }   # QEMU shut down cleanly and wrote nothing to its stderr
qs() { echo "QEMU status $(rc "$1")$([ -s "$1.err" ] && echo ", stderr $(head -c 200 "$1.err" | tr '\n' ' ')")"; }
wstat() { grep -a "^hdesk: terminal $2 ended, status " "$1" | sed -n "${3:-1}p" | sed 's/.* status //'; }
rsfile() { debugfs -R "cat /ada/$2" "$1" 2>/dev/null; }   # a file of ada's home on volume $1
rslog() { rsfile "$1" rs.log | tr '\n' ';' | head -c 600; }   # ada's answers, by row
rsback() { # LEG VOLUME: rs.log and rs.err from ada's home, as the leg left them
    echo "  $1 rs.log: $(rslog "$2")"
    echo "  $1 rs.err: $(rsfile "$2" rs.err | tr '\n' ';' | head -c 600)"
}

D=$(tools/doom/fetch.sh) || fail_exit "tools/doom/fetch.sh: no freedoom-ci at doom.pin's commit"
export DOOM_ROOT=$D
for t in cint gcc clang musl-gcc as ld objcopy qemu-system-x86_64 python3 mke2fs debugfs e2fsck cmp timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
case " $LEGS " in *" store "*|*" homes "*|*" title "*|*" openhome "*)
    grep -q ' name=ada role=parent ' tests/ac/accounts.txt \
        || fail_exit "tests/ac/accounts.txt names no parent ada: the accounts legs need PR 351 (B6) in the train" ;;
esac
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
[ ${#B} -le 80 ] || fail_exit "$B is too long for the monitor sockets under it; set a shorter DAPHNIS_BUILD"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run" "$B/rs"; : > "$B/.daphnis-build"
git_state_before=$(git status --porcelain 2>/dev/null)

# 0. the kit's hosted tests
plan 1
python3 -B "$G/test_guest.py" > "$B/kit.log" 2>&1 \
    && line ok "kit: tests/rs/guest/test_guest.py ($(grep -a '^Ran ' "$B/kit.log" | cut -d' ' -f2) hosted tests of guest.py)" \
    || { line bad "kit: tests/rs/guest/test_guest.py" "see $B/kit.log"; fail_exit "the kit the legs read with fails"; }

# 1. the hdesk flavor for gcc and clang and the release image, and the train's image: the release image with /rs (the
#    legs' scripts and files). HW-17: the apps the legs open are the Makefile's own members (tools/check-image-apps.py
#    holds them there), so the legs boot the image that ships and add no program to it
plan 2
make -s -j"$(nproc)" O="$B" FLAVORS=hdesk all "$B/hdesk/release.cpio" > "$B/make.log" 2>&1 \
    && line ok "build: the hdesk flavor for gcc and clang and the release image (make FLAVORS=hdesk all hdesk/release.cpio)" \
    || { line bad "build: make FLAVORS=hdesk all hdesk/release.cpio" "see $B/make.log"
         fail_exit "nothing boots without the build"; }
gx ops "$G/ops/store.ops" "$B/rs/session.sh" - && gx ops "$G/ops/store.ops" "$B/rs/store.sh" k \
    && gx ops "$G/ops/add.ops" "$B/rs/add.sh" && gx ops "$G/ops/rm.ops" "$B/rs/rm.sh" || fail_exit "guest.py ops"
gx png "$B/rs/4k.png" 3840 2160 2a6f97 /rs/4k.png || fail_exit "guest.py png"
printf 'a note whose name holds a quote and a command substitution\n' > "$B/rs/note"
seq 1 200 > "$B/rs/read.txt"
w250=w250$(printf 'x%.0s' $(seq 236)); w251=w251$(printf 'x%.0s' $(seq 237))   # `ced '/rs/NAME'`: 250 and 251 bytes
members="rs/ rs/session.sh=$B/rs/session.sh rs/store.sh=$B/rs/store.sh rs/add.sh=$B/rs/add.sh rs/rm.sh=$B/rs/rm.sh rs/view.sh=$G/sh/view.sh"
members="$members rs/calc.sh=$G/sh/calc.sh rs/4k.png=$B/rs/4k.png rs/4k.png.want=$B/rs/4k.png.want rs/ced=$B/ubin/kern"
members="$members rs/read.txt=$B/rs/read.txt rs/$w250=$B/rs/note rs/$w251=$B/rs/note"
members="$members rs/s1=$G/sh/store1.sh rs/s2=$G/sh/store2.sh rs/title=$G/sh/title.sh rs/noleak=$G/sh/noleak.sh"
members="$members rs/t1=$G/sh/trash1.sh rs/t2=$G/sh/trash2.sh"
# shellcheck disable=SC2086   # the members are words without spaces; the note's name, which has them, is its own word
gx cpio "$B/hdesk/release.cpio" "$B/rs.cpio" $members "rs/it's \$(kern true)=$B/rs/note" > "$B/cpio.log" 2>&1 \
    && line ok "image: the release image with /rs (ops tables as scripts, a 3840 x 2160 PNG, a copy of kern named ced, a hostile name, names of 240 and 241 bytes)" \
    || { line bad "image" "$(tail -1 "$B/cpio.log")"; fail_exit "no image"; }

pause="info version,info version,info version,info version,info version,info version,info version,info version"
har=$(kt sevenhorsesrun)
four=$(kt four)
exitk=$(kt exit)
# the pointer to the bar's App pill and a click (hdesk.ci bar_click: x in [44, 44 + app_w) at 1x): up and left to the
# corner, where the desk holds it, then 60,14
pill="mouse_move -200 -200,mouse_move -200 -200,mouse_move -200 -200,mouse_move -200 -200,mouse_move -200 -200"
pill="$pill,mouse_move -200 -200,mouse_move 60 14,mouse_button 1,mouse_button 0"
qemu() { # transcript timeout [VAR=VALUE...]: the release image with /rs (QIMG: another image) on gcc at 1920 x 1080,
         # 512 MiB, pool max
    local x=$1 to=$2; shift 2
    env "$@" MODE=$M POOL=max MEM=512 QEMU_TIMEOUT="$to" INITRD="${QIMG:-$B/rs.cpio}" MONITOR="$x.mon" \
        tools/run-qemu.sh "${KERNEL:-$B/gcc-hdesk/kernel32.elf}" "$x" > "$x.rc"
}

# 2. boot, gcc and clang at once; a state pool fault ends the run here
legs_start=$SECONDS
for cc in gcc clang; do
    x=$B/run/boot-$cc.txt
    (SENDKEYS_WAIT=200 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" "$pause,meta_l-shift-q" \
        "hdesk: ff armed 3" meta_l-shift-q > "$x.keys" 2>&1 &
     KERNEL=$B/$cc-hdesk/kernel32.elf qemu "$x" 200; wait) &
done
wait
plan 3
gx pool -m Makefile "$B/run/boot-gcc.txt" "$B/run/boot-clang.txt" > "$B/boot-pool.cmp" 2>&1
pool_rc=$?
sed 's/^/  /' "$B/boot-pool.cmp"
case $pool_rc in
    0) line ok "pool: neither boot faults on the state pool (host.resource)" ;;
    1) line bad "pool: a boot faulted on the state pool" "see the banner above"; fail_exit "state pool fault at boot" ;;
    *) line bad "pool: a boot left no transcript" "see $B/run"; fail_exit "QEMU did not run" ;;
esac
for cc in gcc clang; do
    x=$B/run/boot-$cc.txt
    ran "$x" && gx marks "$x" "$G/expected/boot.marks" > "$x.cmp" 2>&1 \
        && line ok "boot $cc: the desk at $M and 512 MiB; Super+Shift+Q twice shuts down, QEMU status 33" \
        || line bad "boot $cc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
done

# 3. the legs, at once. kern's hold (R0-R4 B) is set on the asking window's shell, and what that shell starts holds
#    ring 0 with it, so a terminal sends a table's - rows (as the session) before `kern true` and its k rows after.
store_line='sh /rs/s1; kern true; sh /rs/s2; exit $?'
leg_store() {
    local x=$B/run/store.txt
    ACCOUNTS=tests/ac/accounts.txt tools/mkdisk.sh "$x.img" > /dev/null
    (SENDKEYS_WAIT=900 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: accounts 2" "$har,ret" \
        "hdesk: login ada uid 1000" "$pause,$pause,meta_l-ret" \
        "hdesk: terminal 1 slot 1" "$pause,$(kt "$store_line"),ret" \
        "hdesk: approval ask want 8 uid 1000" "$pause,$har,ret,$pause,$pause,$pause,$pause,screendump $x.s.ppm" \
        "hdesk: terminal 1 ended" "$pause,$exitk,ret" \
        "hdesk: logout ada" meta_l-esc > "$x.keys" 2>&1 &
     qemu "$x" 900 CPU=max DISK="$x.img"; wait) &
}
check_store() {
    local x=$B/run/store.txt w
    plan 3
    ran "$x" && gx marks "$x" "$G/expected/store.marks" > "$x.cmp" 2>&1 \
        && line ok "store gcc: one approval, then ada's terminal ends with status 0; no passphrase on the serial line" \
        || line bad "store gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    w=$(wstat "$x" 1)
    [ -n "$w" ] && gx status "$G/ops/store.ops" "$w" > "$x.ops" 2>&1 \
        && line ok "store requests gcc: authd as the session reads no store; in a kern hold role, ceil, passwd, add and remove answer as ops/store.ops says (RS-ROLE, RS-R4; RS-R1 A)" \
        || line bad "store requests gcc" "$(if [ -n "$w" ]; then cat "$x.ops"; else echo "no end of terminal 1"; fi); rs.log: $(rslog "$x.img"); the screen 10 s after the approval: $x.s.ppm"
    gx vol "$x.img" "$G/expected/store.vol" > "$x.vol" 2>&1 \
        && line ok "store volume gcc: sam a parent, ivy gone and 1002 never given again, e2fsck clean (expected/store.vol)" \
        || line bad "store volume gcc" "$(tr '\n' ' ' < "$x.vol")"
    echo "  store row 2, authd as the session at ring 3: $(rsfile "$x.img" rs.log | grep '^row 2 ' \
        || echo 'no line, so session.sh never reached it')"
    rsback store "$x.img"
}

leg_homes() {
    local x=$B/run/homes.txt
    ACCOUNTS=tests/ac/accounts.txt tools/mkdisk.sh "$x.img" > /dev/null
    (SENDKEYS_WAIT=1200 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: accounts 2" "$har,ret" \
        "hdesk: login ada uid 1000" "$pause,$pause,meta_l-ret" \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'kern true; sh /rs/add.sh; exit $?'),ret" \
        "hdesk: approval ask want 8 uid 1000" "$pause,$har,ret,$pause,$pause,$pause,$pause,screendump $x.s1.ppm" \
        "hdesk: terminal 1 ended" "$pause,$exitk,ret" \
        "hdesk: logout ada" "$pause,down,down,$four,ret" \
        "hdesk: login eve uid 1002" "$pause,$pause,$exitk,ret" \
        "hdesk: logout eve" "$pause,$har,ret" \
        "hdesk: login ada uid 1000@@2" "$pause,$pause,meta_l-ret" \
        "hdesk: terminal 1 slot 1@@2" "$pause,$(kt 'kern true; sh /rs/rm.sh; exit $?'),ret" \
        "hdesk: approval ask want 8 uid 1000@@2" "$pause,$har,ret,$pause,$pause,$pause,$pause,screendump $x.s2.ppm" \
        "hdesk: terminal 1 ended@@2" "$pause,$exitk,ret" \
        "hdesk: logout ada@@2" "$pause,down,down,$four,ret" \
        "hdesk: login eve uid 1003" "$pause,$pause,$exitk,ret" \
        "hdesk: logout eve@@2" meta_l-esc > "$x.keys" 2>&1 &
     qemu "$x" 1200 CPU=max DISK="$x.img"; wait) &
}
check_homes() {
    local x=$B/run/homes.txt w o k=1
    plan 4
    ran "$x" && gx marks "$x" "$G/expected/homes.marks" > "$x.cmp" 2>&1 \
        && line ok "homes gcc: ada adds eve, eve logs in, ada removes and adds eve, eve logs in as 1003" \
        || line bad "homes gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    for o in add rm; do
        w=$(wstat "$x" 1 $k)
        [ -n "$w" ] && gx status "$G/ops/$o.ops" "$w" > "$x.$o" 2>&1 \
            && line ok "homes requests $o gcc: ops/$o.ops answered as written (RS-R4, RS-R3)" \
            || line bad "homes requests $o gcc" \
                "$(if [ -n "$w" ]; then cat "$x.$o"; else echo "no end of terminal 1 (session $k)"; fi); rs.log: $(rslog "$x.img"); the screen 10 s after the approval: $x.s$k.ppm"
        k=2
    done
    gx vol "$x.img" "$G/expected/homes.vol" > "$x.vol" 2>&1 \
        && line ok "homes volume gcc: each home and its three folders 0700 as the account (RS-HOME); eve's first aside as .removed.eve.1002 (RS-R3)" \
        || line bad "homes volume gcc" "$(tr '\n' ' ' < "$x.vol")"
    rsback homes "$x.img"
}

leg_title() {
    local x=$B/run/title.txt
    ACCOUNTS=tests/ac/accounts.txt tools/mkdisk.sh "$x.img" > /dev/null
    (SENDKEYS_WAIT=600 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: accounts 2" "$har,ret" \
        "hdesk: login ada uid 1000" "$pause,$pause,meta_l-ret" \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'kern true'),ret" \
        "hdesk: approval ask want 8 uid 1000" "$pause,$pause,screendump $x.a.ppm,$pause,esc" \
        "hdesk: kern refused pid" "$pause,meta_l-ret" \
        "hdesk: terminal 2 slot 2" "$pause,$(kt 'exec /rs/ced true'),ret" \
        "hdesk: approval ask want 8 uid 1000@@2" "$pause,$pause,screendump $x.b.ppm,$pause,esc" \
        "hdesk: terminal 2 ended" "$pause,meta_l-ret" \
        "hdesk: terminal 2 slot 2@@2" "$pause,$(kt 'sh /rs/title; kern true'),ret" \
        "hdesk: approval ask want 8 uid 1000@@3" "$pause,$pause,screendump $x.c.ppm,$pause,esc" \
        "hdesk: kern refused pid@@3" "$pause,$(kt 'exit 0'),ret" \
        "hdesk: terminal 2 ended@@2" "$pause,$exitk,ret" \
        "hdesk: terminal 1 ended" "$pause,$exitk,ret" \
        "hdesk: logout ada" meta_l-esc > "$x.keys" 2>&1 &
     qemu "$x" 600 CPU=max DISK="$x.img"; wait) &
}
check_title() {
    local x=$B/run/title.txt
    plan 3
    ran "$x" && gx marks "$x" "$G/expected/title.marks" > "$x.cmp" 2>&1 \
        && line ok "title gcc: three asks from three terminals, each refused with Esc; the exec'd copy ends with status 256" \
        || line bad "title gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx card "$x" "$x.a.ppm" "$x.b.ppm" > "$x.card" 2>&1 \
        && line ok "title prompt gcc: the prompt's left part is one picture for kern and for a program named ced (AC-T, AC-Tw)" \
        || line bad "title prompt gcc" "$(cat "$x.card" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
    [ -s "$x.a.ppm" ] && [ -s "$x.c.ppm" ] && gx card "$x" "$x.a.ppm" "$x.c.ppm" > "$x.cardv" 2>&1 \
        && line ok "title variable gcc: a window titled \"Parent approved\" by its program asks, and the prompt holds none of it (AC-V)" \
        || line bad "title variable gcc (AC-V)" "$(cat "$x.cardv" 2>/dev/null), see $x.a.ppm and $x.c.ppm"
}

leg_quote() {
    local x=$B/run/quote.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" "$(kt 'finder /rs'),ret" \
        "hdesk: bar desktop 1 |Index| var |/rs| " "$pause,screendump $x.a.ppm,k,e,r,n" \
        "finder: filter |kern| items 1" "$pause,ret" \
        "hdesk: ff runs " "$pause,$pause,meta_l-shift-q" \
        "hdesk: ff armed 3" meta_l-shift-q > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_quote() {
    local x=$B/run/quote.txt
    plan 1
    ran "$x" && gx marks "$x" "$G/expected/quote.marks" > "$x.cmp" 2>&1 \
        && line ok "quote gcc: Index opens /rs/it's \$(kern true) in ced as one quoted word; nothing asks for ring 0 (AC-Q)" \
        || line bad "quote gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x and Index before the keys, $x.a.ppm"
}

leg_openhome() {
    local x=$B/run/openhome.txt
    ACCOUNTS=tests/ac/accounts.txt tools/mkdisk.sh "$x.img" > /dev/null
    (SENDKEYS_WAIT=900 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: accounts 2" "$har,ret" \
        "hdesk: login ada uid 1000" "$pause,$pause,meta_l-ret" \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'echo a note >/home/ada/notes.txt;exec finder /home/ada'),ret" \
        "...| var |/home/ada| " "$pause,n,o,t,e,s" \
        "finder: filter |notes| items 1" "$pause,ret" \
        "...| var |notes.txt|" "$pause,$pause,screendump $x.a.ppm,$pause,meta_l-shift-q" \
        "hdesk: ff armed 3" meta_l-shift-q > "$x.keys" 2>&1 &
     QIMG=$B/hdesk/release.cpio qemu "$x" 900 CPU=max DISK="$x.img"; wait) &
}
check_openhome() {
    local x=$B/run/openhome.txt
    plan 1
    ran "$x" && gx marks "$x" "$G/expected/openhome.marks" > "$x.cmp" 2>&1 && [ -s "$x.a.ppm" ] \
        && line ok "openhome gcc: ada's Index opens a note in ada's 0700 home; the desk peeks it as ada and Edit \
opens it, the desk's rights unchanged (RG-1)" \
        || line bad "openhome gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x and the frame $x.a.ppm"
}

leg_view() {
    local x=$B/run/view.txt
    (SENDKEYS_WAIT=600 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'sh /rs/view.sh; exit $?'),ret" \
        "hdesk: terminal 1 ended" "$pause,$(kt 'cview /rs/4k.png'),ret" \
        "hdesk: pixel 1 pid" "$pause,$pause,$pause,screendump $x.ppm,$pause,q" \
        "hdesk: pixel 1 ended" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 600; wait) &
}
check_view() {
    local x=$B/run/view.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/view.marks" > "$x.cmp" 2>&1 \
        && line ok "view gcc: at 512 MiB, cview -d of a 3840 x 2160 PNG prints its digest; View opens it and q ends it (RS-VIEW)" \
        || line bad "view gcc" "$(qs "$x"), view.sh $(wstat "$x" 1) (256: cview -d failed, 512: another digest), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.ppm" ] && gx color "$x" "$x.ppm" 2a6f97 > "$x.color" 2>&1 \
        && line ok "view picture gcc: the middle of View's window is the picture's color at 512 MiB" \
        || line bad "view picture gcc" "$(cat "$x.color" 2>/dev/null), see $x.ppm"
}

leg_calc() {
    local x=$B/run/calc.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'sh /rs/calc.sh; exit $?'),ret" \
        "hdesk: terminal 1 ended" "$pause,$(kt calc),ret" \
        "hdesk: pixel 1 pid" "$pause,$pause,$pause,screendump $x.a.ppm,$pause,$(kt '6*7='),$pause,$pause,screendump $x.b.ppm,$pause,meta_l-shift-q" \
        "hdesk: ff armed 3" meta_l-shift-q > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_calc() {
    local x=$B/run/calc.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/calc.marks" > "$x.cmp" 2>&1 \
        && line ok "calc gcc: ccalc's arithmetic in the guest is the hosted test's (sh/calc.sh); Calc's window opens (RS-CALC)" \
        || line bad "calc gcc" "$(qs "$x"), calc.sh $(wstat "$x" 1) (K * 256: case K), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx differ "$x" "$x.a.ppm" "$x.b.ppm" > "$x.differ" 2>&1 \
        && line ok "calc window gcc: Calc draws 6*7= (its window differs before and after)" \
        || line bad "calc window gcc" "$(cat "$x.differ" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
}

leg_monitor() {
    local x=$B/run/monitor.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" "$(kt monitor),ret" \
        "hdesk: pixel 1 pid" "$pause,$pause,$pause,screendump $x.a.ppm,$pause,$pause,screendump $x.b.ppm,$pause,q" \
        "hdesk: pixel 1 ended" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_monitor() {
    local x=$B/run/monitor.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/monitor.marks" > "$x.cmp" 2>&1 \
        && line ok "monitor gcc: Monitor's window opens over the kernel train's facts and q ends it (RS-MON)" \
        || line bad "monitor gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx differ "$x" "$x.a.ppm" "$x.b.ppm" > "$x.differ" 2>&1 \
        && line ok "monitor reads gcc: Monitor redraws as it reads the machine once a second (its window differs 5 s apart)" \
        || line bad "monitor reads gcc" "$(cat "$x.differ" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
}

leg_launch() {
    local x=$B/run/launch.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" "$(kt 'finder /rs'),ret" \
        "hdesk: bar desktop 1 |Index| var |/rs| " "$pause,w,2,5,1" \
        "finder: filter |w251| items 1" "$pause,ret" \
        "hdesk: launch none " "$pause,esc,$pause,w,2,5,0" \
        "finder: filter |w250| items 1" "$pause,ret" \
        "hdesk: terminal 2 slot " "$pause,$pause,$pause,ctrl-q" \
        "hdesk: terminal 2 ended" "$pause,meta_l-shift-q" \
        "hdesk: ff armed 3" meta_l-shift-q > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_launch() {
    local x=$B/run/launch.txt
    plan 1
    ran "$x" && gx marks "$x" "$G/expected/launch.marks" > "$x.cmp" 2>&1 \
        && line ok "launch gcc: a 251-byte line is refused before a byte is typed; a 250-byte line, 255 with exec, opens Edit on Daphnis's pty and Ctrl+Q ends it with status 0" \
        || line bad "launch gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
}

leg_about_console() {
    local x=$B/run/about_console.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'sleep 15; ls -l /bin'),ret,$pill" \
        "hdesk: app menu open" "down,ret" \
        "hdesk: about 1" "$pause,screendump $x.a.ppm,$pause,$pause,$pause,$pause,$pause,$pause,screendump $x.b.ppm,$pause,$(kt 'touch /tmp/leak'),ret" \
        "hdesk: about closed" "$pause,ctrl-c,$pause,$(kt 'sh /rs/noleak; exit $?'),ret" \
        "hdesk: terminal 1 ended" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_about_console() {
    local x=$B/run/about_console.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/about_console.marks" > "$x.cmp" 2>&1 \
        && line ok "about console gcc: the About sheet from the App pill over Console; a line typed under it and its Enter are the sheet's, no byte reaches the shell (DN-43)" \
        || line bad "about console gcc" "$(qs "$x"), terminal 1 $(wstat "$x" 1) (256: /tmp/leak was made), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx sheet "$x" 1 "$x.a.ppm" "$x.b.ppm" moved > "$x.sheet" 2>&1 \
        && line ok "about console sheet gcc: ls's output scrolls Console around the sheet, which stays one picture (review on PR 272)" \
        || line bad "about console sheet gcc" "$(cat "$x.sheet" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
}

leg_about_read() {
    local x=$B/run/about_read.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" meta_l-ret \
        "hdesk: terminal 1 slot 1" "$pause,$(kt 'cless /rs/read.txt; exit 7'),ret,$pause,$pause,$pill" \
        "hdesk: app menu open" "down,ret" \
        "hdesk: about 1" "$pause,q,$pause,ret" \
        "hdesk: about closed" "$pause,$pause,q" \
        "hdesk: terminal 1 ended" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_about_read() {
    local x=$B/run/about_read.txt
    plan 1
    ran "$x" && gx marks "$x" "$G/expected/about_read.marks" > "$x.cmp" 2>&1 \
        && line ok "about read gcc: the sheet over Read takes q and Enter; Read is open after it and ends on the next q (DN-43)" \
        || line bad "about read gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
}

leg_about_settings() {
    local x=$B/run/about_settings.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" meta_l-comma \
        "hdesk: settings 1" "$pause,$pill" \
        "hdesk: app menu open" "down,ret" \
        "hdesk: about 1" "$pause,screendump $x.a.ppm,down,down,right,$pause,screendump $x.b.ppm,$pause,ret" \
        "hdesk: about closed" "$pause,esc" \
        "hdesk: settings closed" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_about_settings() {
    local x=$B/run/about_settings.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/about_settings.marks" > "$x.cmp" 2>&1 \
        && line ok "about settings gcc: the sheet over Settings takes Down, Right and Enter; no page moves under it, Esc then closes Settings (DN-43)" \
        || line bad "about settings gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx sheet "$x" 1 "$x.a.ppm" "$x.b.ppm" > "$x.sheet" 2>&1 \
        && line ok "about settings sheet gcc: the sheet is one picture before and after the keys it took" \
        || line bad "about settings sheet gcc" "$(cat "$x.sheet" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
}

leg_about_index() {
    local x=$B/run/about_index.txt
    (SENDKEYS_WAIT=400 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console| var |/|" "$(kt 'finder /'),ret" \
        "hdesk: bar desktop 1 |Index| var |/| " "$pause,$pause,$pill" \
        "hdesk: app menu open" "down,ret" \
        "hdesk: about 1" "$pause,screendump $x.a.ppm,$pause,f5,$pause,$pause,screendump $x.b.ppm,$pause,ret" \
        "hdesk: about closed" "$pause,f5" \
        "finder: dir |/| items@@2" "$pause,esc" \
        "hdesk: pixel 1 ended" "$pause,$exitk,ret" > "$x.keys" 2>&1 &
     qemu "$x" 400; wait) &
}
check_about_index() {
    local x=$B/run/about_index.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/about_index.marks" > "$x.cmp" 2>&1 \
        && line ok "about index gcc: the sheet over Index takes F5 (no directory read while it is up); F5 after it reads again (DN-43)" \
        || line bad "about index gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    [ -s "$x.a.ppm" ] && [ -s "$x.b.ppm" ] && gx sheet "$x" 1 "$x.a.ppm" "$x.b.ppm" > "$x.sheet" 2>&1 \
        && line ok "about index sheet gcc: the sheet over Index stays one picture through F5 (review on PR 272)" \
        || line bad "about index sheet gcc" "$(cat "$x.sheet" 2>/dev/null), see $x.a.ppm and $x.b.ppm"
}

leg_trash() {
    local x=$B/run/trash.txt
    tools/mkdisk.sh "$x.img" > /dev/null
    (SENDKEYS_WAIT=500 python3 tools/sendkeys.py "$x.mon" "$x" "hdesk: bar desktop 1 |Console|" "$pause,$(kt 'sh /rs/t1'),ret" \
        "hdesk: bar desktop 1 |Index| var |/home/rs| " "$pause,l,i,n,k" \
        "finder: filter |link| items 1" "$pause,shift-f10" \
        "finder: menu FILE " "$pause,up,right,right,right,right,$pause,ret" \
        "finder: trash |" "$pause,esc,$pause,esc" \
        "hdesk: pixel 1 ended" "$pause,$(kt 'finder --trash'),ret" \
        "finder: dir |/home/.trash/items|" "$pause,$pause,esc" \
        "hdesk: pixel 1 ended@@2" "$pause,$(kt 'sh /rs/t2; exit $?'),ret" > "$x.keys" 2>&1 &
     qemu "$x" 500 DISK="$x.img"; wait) &
}
check_trash() {
    local x=$B/run/trash.txt
    plan 2
    ran "$x" && gx marks "$x" "$G/expected/trash.marks" > "$x.cmp" 2>&1 \
        && line ok "trash gcc: a link moved to the Trash from Index's keyed menu is listed there, as itself (FF 3h, review on PR 287)" \
        || line bad "trash gcc" "$(qs "$x"), $(cat "$x.cmp" 2>/dev/null), see $x"
    gx vol "$x.img" "$G/expected/trash.vol" > "$x.vol" 2>&1 \
        && line ok "trash volume gcc: .trash/items and .trash/records 0700, the link gone from /rs, e2fsck clean (expected/trash.vol)" \
        || line bad "trash volume gcc" "$(tr '\n' ' ' < "$x.vol")"
}

for l in $LEGS; do "leg_$l"; done
wait
for l in $LEGS; do "check_$l"; done
plan 1
# shellcheck disable=SC2046
gx pool -m Makefile $(for l in $LEGS; do echo "$B/run/$l.txt"; done) > "$B/pool.cmp" 2>&1 \
    && line ok "pool: no leg faults on the state pool (host.resource)" \
    || { sed 's/^/  /' "$B/pool.cmp"; line bad "pool: a leg faulted on the state pool or left no transcript" "see above"; }
legs_s=$((SECONDS - legs_start))

# 4. --gates: the train's gate scripts, one at a time, each its own build directory
if [ $GATES = 1 ]; then
    for s in $GATE_SCRIPTS; do
        plan 1
        [ -f "$s" ] || { line bad "gate $s" "not in this tree: the train's candidate lacks a gate it must pass"; continue; }
        DAPHNIS_BUILD=$B/gate-${s%.sh} CINT_TOOLCHAIN=$CINT_TOOLCHAIN bash "$s" > "$B/gate-${s%.sh}.log" 2>&1 \
            && line ok "gate $s: $(tail -1 "$B/gate-${s%.sh}.log")" \
            || line bad "gate $s" "$(tail -1 "$B/gate-${s%.sh}.log"), see $B/gate-${s%.sh}.log"
    done
fi

plan 2
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s, the legs $legs_s s (budget $BUDGET s for the boots and legs)"
[ "$legs_s" -le "$BUDGET" ] \
    && line ok "time: the boots and legs in $legs_s s, within $BUDGET s" || line bad "time" "the boots and legs took $legs_s s"
[ $((passes + fails)) = "$want" ] \
    && line ok "gate: $passes PASS lines and $fails FAIL lines above, the $want the legs of $T print" \
    || line bad "gate: count" "$((passes + fails)) lines above, $want planned: a check block did not run"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
