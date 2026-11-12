#!/usr/bin/env bash
# check-release.sh [STICK]: the release gate (RG-1). l 2026-11-12 07:53Z, of candidate 90055086, whose image had no
# network and lacked five apps of the app list while every test passed on programs the tests added themselves: "make
# sure this mistake never happens again". So this gate boots the release stick as tools/build-release-stick.sh makes
# it, adds nothing to it, and fails on any drift between the app list and what ships.
#   With no STICK it builds one from HEAD (tools/build-release-stick.sh; since PR 481 `make` builds every program of
#   release.cpio from source on a clean checkout). With STICK it checks that file, which must be HEAD's.
#   from source  every program of the release image is built from source at HEAD, none the committed user/bin
#            (tools/check-image-apps.py, PR 481; it replaces the RG-1 fresh guard, which had nothing left to check)
#   home     the stick's volume before any boot holds opt/cint, src, out, .daphnis, log and lost+found, nothing
#            else: no test fixture (tools/check-release-volume.py)
#   words    the approved words of tests/release/approved-words.tsv are in the image's bytes, the app table in note
#            71's order (tools/check-approved-words.py, design's RG-1 guard; approved-words-not-built.tsv is data,
#            the rows for units not yet built, moved over as each lands)
#   stale    no retired desk design in the release initrd's bytes (tools/check-stale-design.py --image; DN-46)
#   bar names  every window by its app's approved name (tests/rs/winname_test.ci, hosted; NAMES-28, note 28)
#   recipe, apps, doom, names, rows   the stick's initrd against the Makefile's recipe, user/ci/kit/apps.ci, the /bin
#            paths its programs' sources name, and the host rows user/ci/build.sh gives each program by its direct
#            imports (tools/check-release.py)
#   the boot: the stick's own kernel and initrd, taken from its ESP, under QEMU -kernel with the release boot line
#            less daphnis.uart=0 (so the console reaches the serial port), the stick as a usb-storage device on
#            qemu-xhci (HW-4m), 512 MiB (the floor), RDRAND (CPU=max: first boot's Argon2id salt needs getrandom, as
#            every board has it), QEMU's user network with a MAC other than QEMU's default (NW-5: the default asks
#            for no network). tools/check-release.py drives first boot, every app with a program from the Super
#            plane, Print and the shut down, then reads the transcript and the volume QEMU left.
#   firmware boot  the same stick as a reader boots it: OVMF and its own GRUB, no -kernel, two boots of one file, S5
#            at each Shut Down (tools/check-firmware-boot.sh; its transcript is $B/firmware.log)
#   ledger   docs/release/0.1.0/LEDGER.tsv, one row per approved item and third-party part: every IN row's artifacts
#            are in the image and reached from their entry point, and no row is MISSING or PARTIAL (RG-1).
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-release-check), cleared as the gates clear their own.
set -u
cd "$(dirname "$0")"
B=$(realpath -m "${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-release-check}")
QEMU_WAIT=1200
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
    if [ "$1" = ok ]; then echo "PASS  $2"; else echo "FAIL  $2"; fi >> "$B/gate.log"   # the ledger's `pass` items
}
fail_exit() { echo "check-release.sh: $*"; echo "RESULT: FAIL"; exit 1; }
count() { grep -c "^$1  " "$2"; }   # PASS or FAIL lines of a helper's output, added to this gate's own

for t in qemu-system-x86_64 python3 git make cint objcopy mcopy sfdisk debugfs dd sha256sum; do   # OVMF: firmware boot
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/src" "$B/run"; : > "$B/.daphnis-build"
head=$(git rev-parse --verify HEAD)
git -c core.autocrlf=false archive --format=tar "$head" | tar -x -C "$B/src"   # the tree the stick is built from
echo "HEAD: $head"
fold() { cat "$1"; grep -E '^(PASS|FAIL)  ' "$1" >> "$B/gate.log"; passes=$((passes + $(count PASS "$1"))); fails=$((fails + $(count FAIL "$1"))); }

# 1. this gate's own parsers on made-up images, then design's guards
python3 tests/release/test_check_release.py > "$B/self.log" 2>&1 \
    && line ok "self: tests/release/test_check_release.py, $(grep -o '^Ran [0-9]* tests' "$B/self.log" | cut -d' ' -f2) tests" \
    || line bad "self: tests/release/test_check_release.py" "see $B/self.log"
# RG-1, PR 481: every program of the release image is built from source at HEAD (O/ubin), none taken from the
# committed user/bin (tools/check-image-apps.py, run on the tree the stick is built from)
if (cd "$B/src" && python3 tools/check-image-apps.py) > "$B/source.log" 2>&1; then
    line ok "from source: $(tail -1 "$B/source.log" | sed 's/^check-image-apps: //')"
else
    sed 's/^/  /' "$B/source.log"
    line bad "from source: every program of the release image is built from source at HEAD (check-image-apps.py)" \
        "$(head -1 "$B/source.log")"
fi

# 2. the stick
if [ $# -ge 1 ]; then
    stick=$(realpath "$1")
    [ -f "$stick" ] || fail_exit "$stick is not a file"
    echo "stick: $stick, given"
else
    stick=$B/stick.img
    if DAPHNIS_BUILD=$B/build tools/build-release-stick.sh "$stick" > "$B/build.log" 2>&1; then
        line ok "build: $(grep '^build-release-stick: /' "$B/build.log" | cut -d' ' -f2-)"
    else
        sed 's/^/  /' "$B/build.log" | tail -8
        line bad "build: tools/build-release-stick.sh made no stick" "see $B/build.log"
        echo "RESULT: FAIL ($fails failing lines)"; exit 1
    fi
fi
# The ESP is partition 1 (HW-8): its kernel and initrd are what the board boots.
esp=$(sfdisk -d "$stick" 2>/dev/null | sed -n 's/^[^:]*1 : start= *\([0-9]*\),.*/\1/p')
[ -n "$esp" ] || fail_exit "$stick has no partition 1"
export MTOOLSRC=/dev/null MTOOLS_SKIP_CHECK=1
mcopy -n -i "$stick@@$((esp * 512))" ::/daphnis/kernel.elf "$B/kernel.elf" \
    && mcopy -n -i "$stick@@$((esp * 512))" ::/daphnis/initrd.cpio "$B/initrd.cpio" \
    || fail_exit "the stick's ESP has no /daphnis/kernel.elf and initrd.cpio"
mdir -/ -b -i "$stick@@$((esp * 512))" ::/ > "$B/esp.txt"
objcopy -O elf32-i386 "$B/kernel.elf" "$B/kernel32.elf"   # QEMU's -kernel takes Multiboot 1 as ELF32 (Makefile)
echo "kernel: sha256 $(sha256sum < "$B/kernel.elf" | cut -c1-64); initrd: $(stat -c %s "$B/initrd.cpio") bytes, sha256 $(sha256sum < "$B/initrd.cpio" | cut -c1-64)"
# The volume is partition 2 (HW-8), read before any boot: a fresh install's home holds opt/cint, src, out, .daphnis,
# log and lost+found, and nothing else; a test volume's fixtures (tools/mkdisk.sh) never reach it
vol0=$(sfdisk -d "$stick" 2>/dev/null | sed -n 's/^[^:]*2 : start= *\([0-9]*\), size= *\([0-9]*\),.*/\1 \2/p')
[ -n "$vol0" ] || fail_exit "$stick has no partition 2"
dd if="$stick" of="$B/volume-built.img" bs=512 skip="${vol0% *}" count="${vol0#* }" status=none
if python3 tools/check-release-volume.py "$B/volume-built.img" "$B/src" > "$B/home.log" 2>&1; then
    line ok "home: $(tail -1 "$B/home.log" | sed 's/^check-release-volume: //')"
else
    sed 's/^/  /' "$B/home.log" | tail -20
    line bad "home: the release volume holds release files only (tools/check-release-volume.py)" "$(tail -1 "$B/home.log")"
fi

# 3. the image against the recipe and the app list, and the approved words
# The initrd target build-release-stick.sh hands tools/build-esp.sh (hdesk/initrd.cpio before HW-17, hdesk/release.cpio after)
cpio=$(sed -n 's|^ARGS=$args tools/build-esp.sh .* "$B/o/\([^"]*\)"$|\1|p' "$B/src/tools/build-release-stick.sh")
[ -n "$cpio" ] || fail_exit "no initrd target on tools/build-release-stick.sh's build-esp.sh line"
echo "recipe: \$(O)/$cpio, the target tools/build-release-stick.sh ships"
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
(cd "$B/src" && env -i PATH="$PATH" HOME="$HOME" LC_ALL=C make -s -n -B O="$B/recipe" COMPILERS=gcc FLAVORS=hdesk \
    CINT_TOOLCHAIN="$CINT_TOOLCHAIN" DOOM_ROOT="$B/recipe/doom" "$B/recipe/$cpio") > "$B/recipe.txt" 2> "$B/recipe.err"
python3 tools/check-release.py --static "$B/initrd.cpio" "$B/recipe.txt" "$B/src" > "$B/static.log" 2>&1
fold "$B/static.log"
if python3 tools/check-approved-words.py "$B/src/tests/release/approved-words.tsv" --image "$B/initrd.cpio" > "$B/words.log" 2>&1; then
    line ok "words: $(tail -1 "$B/words.log") in the image, the app table in note 71's order"
else
    sed 's/^/  /' "$B/words.log"
    line bad "words: the approved words are in the image" "$(tail -1 "$B/words.log")"
fi
# DN-46 (show, don't tell; the retired desk design): no retired string in the release image's bytes
if python3 tools/check-stale-design.py --image "$B/initrd.cpio" > "$B/stale.log" 2>&1; then
    line ok "stale design: $(tail -1 "$B/stale.log") (tools/check-stale-design.py --image, DN-46)"
else
    sed 's/^/  /' "$B/stale.log"
    line bad "stale design: no retired desk design in the release image" "$(tail -1 "$B/stale.log")"
fi
# NAMES-28 (note 28): every window by its app's approved name in the bar and the window lists (kit/winname.ci,
# PR 477), the hosted test on the tree the stick is built from
if (cd "$B/src" && cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/rs/winname_test.ci) \
    > "$B/winname.log" 2>&1; then
    line ok "bar names: tests/rs/winname_test.ci, every window by its app's name ($(tail -1 "$B/winname.log"))"
else
    line bad "bar names: tests/rs/winname_test.ci" "see $B/winname.log"
fi

# 4. the boot
guid=$(sed -n 's/^guid=//p' "$B/src/tools/build-release-stick.sh")
args=$(sed -n 's/^args="\(.*\)"$/\1/p' "$B/src/tools/build-release-stick.sh")
args=${args//\$guid/$guid}
boot=$(echo " $args " | sed 's/ daphnis\.uart=0 / /; s/^ *//; s/ *$//')
echo "boot line: $boot (the release line less daphnis.uart=0)"
cp "$stick" "$B/run/stick.img"
t=$B/run/desk.txt
python3 tools/check-release.py --drive "$B/run/desk.mon" "$t" "$B/src/user/ci/kit/apps.ci" "$B/run" > "$B/drive.log" 2>&1 &
drv=$!
CPU=max MEM=512 MODE=1920x1080 QEMU_TIMEOUT=$QEMU_WAIT INITRD=$B/initrd.cpio APPEND=$boot MONITOR=$B/run/desk.mon \
    NET=user NET_MAC=52:54:00:12:34:57 \
    QEMU_EXTRA="-device qemu-xhci -drive if=none,id=u0,file=$B/run/stick.img,format=raw,cache=unsafe -device usb-storage,drive=u0" \
    tools/run-qemu.sh "$B/kernel32.elf" "$t" > "$t.rc"
wait "$drv"
fold "$B/drive.log"
[ "$(cat "$t.rc")" = 33 ] && line ok "boot: QEMU exit status 33, the desk shut down" \
    || line bad "boot: QEMU exit status" "$(cat "$t.rc") (124: the ${QEMU_WAIT} s watchdog), see $t"
grep -q '^daphnis: /home mounted$' "$t" && grep -q '^daphnis: usb: storage .*, writes on$' "$t" \
    && line ok "volume: the stick's volume partition mounts as /home, writes on (HW-12: the boot line names its GUID)" \
    || line bad "volume: /home mounted with writes on" "see $t"
vol=$(sfdisk -d "$B/run/stick.img" 2>/dev/null | sed -n 's/^[^:]*2 : start= *\([0-9]*\), size= *\([0-9]*\),.*/\1 \2/p')
dd if="$B/run/stick.img" of="$B/run/volume.img" bs=512 skip="${vol% *}" count="${vol#* }" status=none
python3 tools/check-release.py --after "$t" "$B/initrd.cpio" "$B/run/volume.img" rel > "$B/after.log" 2>&1
fold "$B/after.log"
# RG-1 (l 2026-11-12 17:16Z, the QEMU road first): the stick through OVMF and GRUB, unmodified (a copy of $stick)
if DAPHNIS_BUILD=$B/firmware tools/check-firmware-boot.sh "$stick" > "$B/firmware.log" 2>&1; then
    line ok "firmware boot: $(grep -c '^PASS  ' "$B/firmware.log") lines of tools/check-firmware-boot.sh, $(sed -n 's/^accel: //p' "$B/firmware.log"), $(sed -n 's/^memory: //p' "$B/firmware.log"): the Parent, a file, S5, the sign-in and the file read back"
else
    grep -E '^(FAIL|RESULT)' "$B/firmware.log" | sed 's/^/  /'
    line bad "firmware boot: tools/check-firmware-boot.sh" "$(grep -m1 '^FAIL  ' "$B/firmware.log" | cut -c7-) (see $B/firmware.log)"
fi
python3 tools/check-release.py --ledger "$B/src/docs/release/0.1.0/LEDGER.tsv" "$B/initrd.cpio" "$B/esp.txt" \
    "$B/run/volume.img" "$B/src/user/ci/kit/apps.ci" "$t" "$B/gate.log" "$B/src/docs/DECISIONS.md" > "$B/ledger.log" 2>&1
fold "$B/ledger.log"

apps=$(python3 tools/check-release.py --count "$B/src/user/ci/kit/apps.ci")
want=$((26 + 2 * apps))   # self, from source, build, home, recipe, apps, doom, names, rows, words, stale design, bar names,
                          # first boot, the Console on the bar, 2 an app, shut down, QEMU, volume, network, image, keys, shot,
                          # firmware boot, ledger form, cover, in, open
[ $# -eq 0 ] || want=$((want - 1))   # no build line with STICK
echo "elapsed: $((SECONDS - start)) s"
[ "$passes" = "$want" ] && [ "$fails" = 0 ] \
    && line ok "gate: $passes PASS lines above, the count for $apps apps with a program ($want)" \
    || line bad "gate: count" "$passes PASS lines above, $want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
