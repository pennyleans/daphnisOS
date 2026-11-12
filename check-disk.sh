#!/usr/bin/env bash
# check-disk.sh: the gate of stage P (docs/specs/2026-11-05-p-disk.md section 5), on its own budget beside
# check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL.
#   The volume: tools/mkdisk.sh builds the test volume from tests/disk/ and its digest must be the pin
#   (tests/expected/disk.sha256) before anything boots.
#   P-1, P-2: the disk flavor (src/main_disk.ci) boots with a fresh copy of the volume as a virtio disk and
#   tests/image/disk.txt as its serial input, on gcc, clang and, with grub-mkrescue, each through GRUB;
#   tools/check-disk.py checks the two volume digests the kernel read through the device, the write probe, the
#   file QEMU left, and the shell's session on /home against Linux on a debugfs dump of the volume with
#   debugfs's inodes in its stat lines; every transcript is tests/expected/disk.serial. The gcc kernel boots
#   once more without a disk: tests/expected/disk-none.serial.
#   P-3: each leg boots another fresh copy twice, on tests/image/disk-write.txt (writes refused without the
#   grant, then `./grant disk ./sh` writes) and on tests/image/disk-list.txt (the next boot lists what the first
#   wrote); tools/check-disk.py --write checks both sessions against Linux, the digests and e2fsck -fn; the
#   transcripts are tests/expected/disk-write.serial and disk-list.serial on every leg, so the written volume
#   has one digest on gcc, clang and both through GRUB.
#   FF-1: the gcc and clang kernels boot a fresh copy on tests/image/disk-index.txt with the image of O/ubin/ix
#   (make's $B/ix/initrd.cpio): ix takes /dev/fsidx, builds the index of /home by the walk, runs a granted session
#   (creates, writes, renames of a file and a directory, a rename over a name, unlinks, a truncate), applies the
#   ring and prints `ix: equal` when what the ring kept is the index of a fresh walk; a second session posts past
#   the ring's 4,096 entries, so the ring answers LOST and the index is rebuilt by the walk. Both transcripts are
#   tests/expected/disk-index.serial: the same ring, the same index, the same state digest on both compilers.
#   BU-2a: those two boots take the user image with O/ubin/mmeta (make's $B/meta/initrd.cpio), and the granted
#   session runs it on meta (the image tree) and home/meta (the volume): every metadata call, Linux's bytes.
#   FS-3 (RV-1 A, FS-R1 A): the hybrid desk boots twice on gcc and clang, each leg on its own fresh copy of the
#   volume, at 512 MiB with the pool from the memory map: the first boot's shell starts in /home with the disk
#   grant, writes 1 MiB and more of seq there, copies it into the ramfs, and ced puts a line at its top and saves;
#   the second boot of the same volume reads it back. tools/check-home.py checks both transcripts and the volume.
#   HW-4m (docs/specs/2026-11-06-hw-hardware.md section 6): the gcc and clang kernels boot the same sessions with
#   the volume as a usb-storage device on qemu-xhci and no virtio disk, the boot line naming it
#   (daphnis.disk.write=QEMU_HARDDISK): tools/check-disk.py holds them to the same checks, and each transcript is its
#   virtio golden once the lines that name the device are set aside (usb_same). The gcc kernel boots once more
#   without the name: the disk is read only, the console says the boot line does not name its model, the write probe
#   is refused and the volume is the pin's bytes. And once with
#   a stick that answers late (QEMU's throttle at 512 bytes a second, so the second READ (10) takes 8 s): the transfer
#   times out, the endpoint is stopped and the disk dropped, the boot goes on without /home, and hello, run on frames
#   the failed mount gave back, has the golden's state digest: no late answer reached a frame the pool handed on.
#   The stick (HW-8's layout): tools/build-stick.sh lays a 1 MiB stand-in ESP and the volume out as GPT; the gcc kernel
#   boots it as the usb-storage device, the boot line naming the volume partition's unique GUID as lsblk prints it
#   (HW-12): the volume is partition 2, writes are on, its digests are that partition's bytes, the write probe
#   restores them and the image file ends as it began. A copy whose table CRC is broken gives no volume and the image
#   stays as it was. A copy named by its model only stays read only, the console says the boot line does not name the
#   volume partition's GUID, the probe is refused and the image is unchanged: a model never names a disk with a table.
#   Without sfdisk the three are one SKIP line.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-disk), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-disk}
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
BUDGET=240
WATCHDOG=120
# the PASS lines before the last one, the GRUB legs left out; they add iso_pass, or one SKIP line instead
gate_want=38   # 26, +12 HW-4m (5 a compiler, the read-only boot, the late stick)
iso_pass=11
stick_pass=3   # the stick, the broken table and the stick named by its model (HW-12), when sfdisk is here
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check-disk.sh: $*"; echo "RESULT: FAIL"; exit 1; }

command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy python3 sha256sum cmp timeout git mke2fs debugfs e2fsck; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B/run"; : > "$B/.daphnis-build"
# RG-1: the programs this gate runs or packs, built from source at HEAD into O/ubin by the Makefile's rules,
# never the committed user/bin (which holds none); a build that fails says so here, and its users fail below
make -s -j"$(nproc)" O="$B" $(for p in cish mmeta mexe mvfork ix; do printf '%s ' "$UB/$p"; done) > "$B/ubin.log" 2>&1 \
    || line bad "build: the programs this gate takes, into O/ubin" "see $B/ubin.log"
git_state_before=$(git status --porcelain 2>/dev/null)
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"
echo "mke2fs: $(mke2fs -V 2>&1 | head -1)"

# 1. the volume
tools/mkdisk.sh "$B/disk.img" > "$B/mkdisk.log" 2>&1 \
    && line ok "volume: tools/mkdisk.sh builds the test volume from tests/disk" || line bad "volume: mkdisk.sh" "see $B/mkdisk.log"
(cd "$B" && sha256sum --quiet -c "$OLDPWD/tests/expected/disk.sha256") > "$B/pin.log" 2>&1 \
    && line ok "volume: its bytes are the pin of tests/expected/disk.sha256" || line bad "volume: pin" "see $B/pin.log"

sed 's#  user/bin/#  #' tests/expected/mmeta.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/mmeta.log" 2>&1 \
    && line ok "bin: O/ubin/mmeta is the bytes of tests/expected/mmeta.sha256 (BU-2a)" || line bad "bin: mmeta" "see $B/mmeta.log"
sed 's#  user/bin/#  #' tests/expected/mexe.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/mexe.log" 2>&1 \
    && line ok "bin: O/ubin/mexe is the bytes of tests/expected/mexe.sha256 (BU-4f)" || line bad "bin: mexe" "see $B/mexe.log"
sed 's#  user/bin/#  #' tests/expected/mvfork.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/mvfork.log" 2>&1 \
    && line ok "bin: O/ubin/mvfork is the bytes of tests/expected/mvfork.sha256 (BU-4a)" || line bad "bin: mvfork" "see $B/mvfork.log"

# 2. the disk flavor, gcc and clang, and through GRUB when grub-mkrescue is here
sed 's#  user/bin/#  #' tests/expected/ix.sha256 | (cd "$UB" && sha256sum --quiet -c -) > "$B/ix.log" 2>&1 \
    && line ok "bin: O/ubin/ix is the bytes of tests/expected/ix.sha256 (FF-1)" || line bad "bin: ix" "see $B/ix.log"

make -s -j"$(nproc)" O="$B" FLAVORS="disk hdesk" all "$B/meta/initrd.cpio" "$B/ix/initrd.cpio" "$B/hdesk/release.cpio" > "$B/make.log" 2>&1 \
    && line ok "build: the disk and hdesk flavors for gcc and clang, their images and the images with mmeta (BU-2a, FS-3) and ix (FF-1)" \
    || line bad "build: make FLAVORS=disk" "see $B/make.log"
legs="gcc clang"
if command -v grub-mkrescue >/dev/null && command -v xorriso >/dev/null; then
    iso_ran=1
    ok=1
    for cc in gcc clang; do
        tools/build-iso.sh "$B/$cc-disk/kernel.elf" "$B/$cc-disk/daphnis.iso" "$B/user/initrd.cpio" >> "$B/iso.log" 2>&1 || ok=0
        tools/build-iso.sh "$B/$cc-disk/kernel.elf" "$B/$cc-disk/daphnis-meta.iso" "$B/meta/initrd.cpio" >> "$B/iso.log" 2>&1 || ok=0
    done
    [ $ok = 1 ] && line ok "iso: daphnis.iso (and daphnis-meta.iso, BU-2a) of the disk flavor for gcc and clang, the image as the GRUB module" \
                || line bad "iso: build-iso.sh" "see $B/iso.log"
    legs="gcc clang gcc-iso clang-iso"
else
    iso_ran=0
    skip "iso: grub-mkrescue and xorriso are not both on PATH; the GRUB boots of the disk flavor did not run"
fi
for leg in $legs; do
    cc=${leg%-iso}
    image=$B/$cc-disk/kernel32.elf
    wimage=$image
    [ "$leg" != "$cc" ] && image=$B/$cc-disk/daphnis.iso && wimage=$B/$cc-disk/daphnis-meta.iso
    cp "$B/disk.img" "$B/run/$leg.img"
    cp "$B/disk.img" "$B/run/$leg-w.img"
    (QEMU_TIMEOUT=$WATCHDOG DISK=$B/run/$leg.img INITRD=$B/user/initrd.cpio STDIN_FILE=tests/image/disk.txt \
        tools/run-qemu.sh "$image" "$B/run/$leg.txt" > "$B/run/$leg.txt.rc") &
    (export QEMU_TIMEOUT=$WATCHDOG DISK=$B/run/$leg-w.img INITRD=$B/meta/initrd.cpio
     STDIN_FILE=tests/image/disk-write.txt tools/run-qemu.sh "$wimage" "$B/run/$leg-w.txt" > "$B/run/$leg-w.txt.rc"
     STDIN_FILE=tests/image/disk-list.txt tools/run-qemu.sh "$wimage" "$B/run/$leg-l.txt" > "$B/run/$leg-l.txt.rc") &
done
# HW-4m: the same volume behind qemu-xhci, named on the boot line; then unnamed, read only
usb() { echo "-device qemu-xhci -drive if=none,id=u0,file=$1,format=raw,cache=unsafe -device usb-storage,drive=u0"; }
for cc in gcc clang; do
    cp "$B/disk.img" "$B/run/$cc-usb.img"
    cp "$B/disk.img" "$B/run/$cc-usb-w.img"
    (export QEMU_TIMEOUT=$WATCHDOG APPEND=daphnis.disk.write=QEMU_HARDDISK INITRD=$B/user/initrd.cpio
     QEMU_EXTRA=$(usb "$B/run/$cc-usb.img") STDIN_FILE=tests/image/disk.txt \
        tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc-usb.txt" > "$B/run/$cc-usb.txt.rc") &
    (export QEMU_TIMEOUT=$WATCHDOG APPEND=daphnis.disk.write=QEMU_HARDDISK INITRD=$B/meta/initrd.cpio
     export QEMU_EXTRA=$(usb "$B/run/$cc-usb-w.img")
     STDIN_FILE=tests/image/disk-write.txt tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc-usb-w.txt" > "$B/run/$cc-usb-w.txt.rc"
     STDIN_FILE=tests/image/disk-list.txt tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc-usb-l.txt" > "$B/run/$cc-usb-l.txt.rc") &
done
cp "$B/disk.img" "$B/run/usb-ro.img"
cp "$B/disk.img" "$B/run/usb-late.img"
(QEMU_TIMEOUT=$WATCHDOG QEMU_EXTRA="$(usb "$B/run/usb-late.img" | sed 's/cache=unsafe/cache=unsafe,throttling.bps-total=512/')" \
    APPEND=daphnis.disk.write=QEMU_HARDDISK INITRD=$B/user/initrd.cpio STDIN_FILE=tests/image/disk.txt \
    tools/run-qemu.sh "$B/gcc-disk/kernel32.elf" "$B/run/usb-late.txt" > "$B/run/usb-late.txt.rc") &
(QEMU_TIMEOUT=$WATCHDOG QEMU_EXTRA=$(usb "$B/run/usb-ro.img") INITRD=$B/user/initrd.cpio STDIN_FILE=tests/image/disk.txt \
    tools/run-qemu.sh "$B/gcc-disk/kernel32.elf" "$B/run/usb-ro.txt" > "$B/run/usb-ro.txt.rc") &
(QEMU_TIMEOUT=$WATCHDOG INITRD=$B/user/initrd.cpio STDIN_FILE=tests/image/disk.txt \
    tools/run-qemu.sh "$B/gcc-disk/kernel32.elf" "$B/run/none.txt" > "$B/run/none.txt.rc") &
for cc in gcc clang; do
    cp "$B/disk.img" "$B/run/$cc-ix.img"
    (QEMU_TIMEOUT=$WATCHDOG DISK=$B/run/$cc-ix.img INITRD=$B/ix/initrd.cpio STDIN_FILE=tests/image/disk-index.txt \
        tools/run-qemu.sh "$B/$cc-disk/kernel32.elf" "$B/run/$cc-ix.txt" > "$B/run/$cc-ix.txt.rc") &
done
# FS-3: the home, two boots of one volume a leg
for cc in gcc clang; do
    h=$B/run/home-$cc
    [ ${#h} -le 92 ] || fail_exit "monitor socket path $h.1.txt.mon is too long for a unix socket; set a shorter DAPHNIS_BUILD"
    cp "$B/disk.img" "$h.img"
    (bash tools/home-boots.sh "$B/$cc-hdesk/kernel32.elf" "$B/hdesk/release.cpio" "$h.img" "$h" "$WATCHDOG" \
        > "$h.boot.log" 2>&1; echo $? > "$h.boot.rc") &
done
wait
for cc in gcc clang; do
    t=$B/run/$cc-ix.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && cmp -s tests/expected/disk-index.serial "$t" \
        && [ "$(grep -c '^ix: equal$' "$t")" = 2 ] && grep -q '^ix: ring [0-9]* lost ' "$t" \
        && line ok "index $cc: status 33; the ring kept the walk's index after the session and after its loss (two \`ix: equal\`); the transcript equals tests/expected/disk-index.serial" \
        || line bad "index $cc" "status $(cat "$t.rc"), see $t"
done
for leg in $legs; do
    t=$B/run/$leg.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && line ok "boot $leg: QEMU exit status 33, nothing on stderr" \
        || line bad "boot $leg" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes"
    python3 tools/check-disk.py "$t" "$B/run/$leg.img" tests/expected/disk.sha256 \
        --session $UB/cish "$B/user/initrd.cpio" tests/image/disk.txt > "$B/$leg.cmp" 2>&1 \
        && line ok "disk $leg: both volume digests read through the device are the pin, the write probe read back and restored, the file QEMU left is the pin, the session on /home is Linux's and debugfs's" \
        || line bad "disk $leg" "see $B/$leg.cmp"
    cmp -s tests/expected/disk.serial "$t" \
        && line ok "serial $leg: the transcript equals tests/expected/disk.serial" \
        || line bad "serial $leg: vs tests/expected/disk.serial" "differ"
    python3 tools/check-disk.py --write "$B/run/$leg-w.txt" "$B/run/$leg-l.txt" "$B/disk.img" "$B/run/$leg-w.img" \
        tests/expected/disk.sha256 $UB/cish "$B/meta/initrd.cpio" tests/image/disk-write.txt \
        tests/image/disk-list.txt > "$B/$leg-w.cmp" 2>&1 \
        && line ok "write $leg: refused without the grant, the written session and the next boot's are Linux's, the digests, e2fsck -fn clean" \
        || line bad "write $leg" "see $B/$leg-w.cmp"
    [ "$(cat "$B/run/$leg-w.txt.rc")" = 33 ] && [ ! -s "$B/run/$leg-w.txt.err" ] \
        && [ "$(cat "$B/run/$leg-l.txt.rc")" = 33 ] && [ ! -s "$B/run/$leg-l.txt.err" ] \
        && cmp -s tests/expected/disk-write.serial "$B/run/$leg-w.txt" && cmp -s tests/expected/disk-list.serial "$B/run/$leg-l.txt" \
        && line ok "serial $leg write: both boots status 33, the transcripts equal tests/expected/disk-write.serial and disk-list.serial" \
        || line bad "serial $leg write" "status $(cat "$B/run/$leg-w.txt.rc") and $(cat "$B/run/$leg-l.txt.rc"), see $B/run/$leg-w.txt and $leg-l.txt"
done
for cc in gcc clang; do
    h=$B/run/home-$cc
    if [ -f "$h.2.blocked" ] || [ ! -f "$h.1.txt.rc" ] || [ ! -f "$h.2.txt.rc" ]; then
        line bad "home $cc: boots" "first boot/setup failed; persistence-reading leg blocked (see $h.boot.log and input logs)"
        line bad "home $cc: checks" "prerequisite boots did not complete; no persistence result claimed"
        continue
    fi
    [ "$(cat "$h.boot.rc")" = 0 ] && [ "$(cat "$h.1.txt.rc")" = 33 ] && [ ! -s "$h.1.txt.err" ] \
        && [ "$(cat "$h.2.txt.rc")" = 33 ] && [ ! -s "$h.2.txt.err" ] \
        && [ "$(cat "$h.1.keys.rc")" = 0 ] && [ "$(cat "$h.2.keys.rc")" = 0 ] \
        && line ok "home $cc: both boots and input drivers succeeded, QEMU exit status 33, nothing on stderr" \
        || line bad "home $cc" "status $(cat "$h.1.txt.rc") and $(cat "$h.2.txt.rc"), see $h.1.txt and $h.2.txt"
    python3 tools/check-home.py --check "$h.1.txt" "$h.2.txt" "$h.img" > "$B/home-$cc.cmp" 2>&1
    sed 's/^/  /' "$B/home-$cc.cmp" | grep -v '^  PASS' || true
    [ "$(grep -c '^PASS' "$B/home-$cc.cmp")" = 6 ] && ! grep -q '^FAIL' "$B/home-$cc.cmp" \
        && line ok "home $cc: the desk starts in /home with the disk grant; ced's 1 MiB file there is the same bytes on the next boot and on the volume, e2fsck clean; a 1 MiB file in the ramfs" \
        || line bad "home $cc" "see $B/home-$cc.cmp"
done
# HW-4m: a USB transcript is its virtio golden but for the controller's and the disk's own lines, the line that names
# the device and its frames, and the pool's free count (the controller's rings are pool frames)
usb_lines() { grep -v -e '^daphnis: usb: ' -e '^daphnis: disk [a-z-]*, [0-9]* sectors, [0-9]* frames held$' -e '^daphnis: pool frames free ' "$1"; }
usb_same() { cmp -s <(usb_lines "$1") <(usb_lines "$2"); }
for cc in gcc clang; do
    t=$B/run/$cc-usb.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^daphnis: usb: port [0-9]* speed [0-9]*: mass storage$' "$t" \
        && grep -q '^daphnis: usb: storage QEMU_HARDDISK, 8192 sectors, writes on$' "$t" \
        && line ok "usb $cc: QEMU exit status 33, nothing on stderr; the disk is the usb-storage device, named on the boot line (HW-4m)" \
        || line bad "usb $cc" "status $(cat "$t.rc"), stderr $(wc -c < "$t.err") bytes, see $t"
    python3 tools/check-disk.py "$t" "$B/run/$cc-usb.img" tests/expected/disk.sha256 \
        --session "$UB"/cish "$B/user/initrd.cpio" tests/image/disk.txt > "$B/$cc-usb.cmp" 2>&1 \
        && line ok "usb disk $cc: both volume digests read through READ (10) are the pin, the write probe read back and restored through WRITE (10), the file QEMU left is the pin, the session on /home is Linux's and debugfs's" \
        || line bad "usb disk $cc" "see $B/$cc-usb.cmp"
    usb_same tests/expected/disk.serial "$t" \
        && line ok "usb serial $cc: the transcript is tests/expected/disk.serial but for the device's lines" \
        || line bad "usb serial $cc: vs tests/expected/disk.serial" "differ"
    python3 tools/check-disk.py --write "$B/run/$cc-usb-w.txt" "$B/run/$cc-usb-l.txt" "$B/disk.img" "$B/run/$cc-usb-w.img" \
        tests/expected/disk.sha256 "$UB"/cish "$B/meta/initrd.cpio" tests/image/disk-write.txt \
        tests/image/disk-list.txt > "$B/$cc-usb-w.cmp" 2>&1 \
        && line ok "usb write $cc: refused without the grant, the written session and the next boot's are Linux's, the digests, e2fsck -fn clean" \
        || line bad "usb write $cc" "see $B/$cc-usb-w.cmp"
    [ "$(cat "$B/run/$cc-usb-w.txt.rc")" = 33 ] && [ ! -s "$B/run/$cc-usb-w.txt.err" ] \
        && [ "$(cat "$B/run/$cc-usb-l.txt.rc")" = 33 ] && [ ! -s "$B/run/$cc-usb-l.txt.err" ] \
        && usb_same tests/expected/disk-write.serial "$B/run/$cc-usb-w.txt" && usb_same tests/expected/disk-list.serial "$B/run/$cc-usb-l.txt" \
        && line ok "usb serial $cc write: both boots status 33, the transcripts are tests/expected/disk-write.serial and disk-list.serial but for the device's lines" \
        || line bad "usb serial $cc write" "status $(cat "$B/run/$cc-usb-w.txt.rc") and $(cat "$B/run/$cc-usb-l.txt.rc"), see $B/run/$cc-usb-w.txt and $cc-usb-l.txt"
done
t=$B/run/usb-ro.txt
[ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^daphnis: usb: storage QEMU_HARDDISK, 8192 sectors, read only$' "$t" \
    && grep -q "^daphnis: usb: storage: read only: the boot line does not name this disk's model\$" "$t" \
    && grep -q '^daphnis: disk write probe: a request failed$' "$t" \
    && [ "$(grep -c "^daphnis: disk 8192 sha256 $(cut -d' ' -f1 tests/expected/disk.sha256)\$" "$t")" = 2 ] \
    && (cd "$B/run" && sed 's/disk.img/usb-ro.img/' "$OLDPWD/tests/expected/disk.sha256" | sha256sum --quiet -c -) > "$B/usb-ro.log" 2>&1 \
    && line ok "usb gcc unnamed: read only, the line says the boot line does not name its model (HW-12), the write probe refused, both digests and the file QEMU left are the pin (HW-4m)" \
    || line bad "usb gcc unnamed" "status $(cat "$t.rc"), see $t"
# HW-4m: the stick, GPT as tools/build-stick.sh lays it out, and a copy with its table broken
if command -v sfdisk >/dev/null; then
    stick_ran=1
    head -c 1048576 /dev/zero > "$B/run/stick-esp.img"
    tools/build-stick.sh "$B/run/stick-esp.img" "$B/disk.img" "$B/run/stick.img" > "$B/stick.log" 2>&1 || : > "$B/run/stick.img"
    stick_vol=$(dd if="$B/run/stick.img" bs=1M skip=2 count=4 status=none | sha256sum | cut -d' ' -f1)
    stick_sum=$(sha256sum < "$B/run/stick.img" | cut -d' ' -f1)
    cp "$B/run/stick.img" "$B/run/stick-bad.img"
    printf '\043' | dd of="$B/run/stick-bad.img" bs=1 seek=552 conv=notrunc status=none   # LBA 1 byte 40: the CRC no longer holds
    bad_sum=$(sha256sum < "$B/run/stick-bad.img" | cut -d' ' -f1)
    cp "$B/run/stick.img" "$B/run/stick-model.img"
    for s in stick stick-bad stick-model; do
        name=6461706e-6869-7300-0000-000000000005   # tools/build-stick.sh's VOLUME_GUID by default, as lsblk prints it
        [ "$s" != stick-model ] || name=QEMU_HARDDISK
        QEMU_TIMEOUT=$WATCHDOG QEMU_EXTRA=$(usb "$B/run/$s.img") APPEND=daphnis.disk.write=$name INITRD=$B/user/initrd.cpio \
            STDIN_FILE=tests/image/disk.txt tools/run-qemu.sh "$B/gcc-disk/kernel32.elf" "$B/run/$s.txt" > "$B/run/$s.txt.rc"
    done
    t=$B/run/stick.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^daphnis: usb: storage: volume partition 2 at sector 4096$' "$t" \
        && grep -q '^daphnis: usb: storage QEMU_HARDDISK, 8192 sectors, writes on$' "$t" \
        && [ "$(grep -c "^daphnis: disk 8192 sha256 $stick_vol\$" "$t")" = 2 ] \
        && grep -q '^daphnis: disk write probe: the pattern read back equal, the sectors restored$' "$t" \
        && grep -q '^daphnis: /home mounted' "$t" && [ "$(sha256sum < "$B/run/stick.img" | cut -d' ' -f1)" = "$stick_sum" ] \
        && line ok "usb stick gcc: named by the volume partition's GUID (HW-12), the volume is GPT partition 2 at sector 4096, writes on, both digests are its bytes, /home mounts, the probe restores, the image file is unchanged (HW-4m)" \
        || line bad "usb stick gcc" "status $(cat "$t.rc"), see $t and $B/stick.log"
    t=$B/run/stick-bad.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
        && grep -q '^daphnis: usb: storage: the GUID partition table is not sound; no volume$' "$t" \
        && grep -q '^daphnis: disk found, not set up$' "$t" && [ "$(sha256sum < "$B/run/stick-bad.img" | cut -d' ' -f1)" = "$bad_sum" ] \
        && line ok "usb stick gcc, table broken: no volume, nothing written, the boot goes on (HW-4m)" \
        || line bad "usb stick gcc, table broken" "status $(cat "$t.rc"), see $t"
    t=$B/run/stick-model.txt
    [ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && grep -q '^daphnis: usb: storage QEMU_HARDDISK, 8192 sectors, read only$' "$t" \
        && grep -q "^daphnis: usb: storage: read only: the boot line does not name the volume partition's GUID\$" "$t" \
        && grep -q '^daphnis: disk write probe: a request failed$' "$t" \
        && [ "$(grep -c "^daphnis: disk 8192 sha256 $stick_vol\$" "$t")" = 2 ] \
        && [ "$(sha256sum < "$B/run/stick-model.img" | cut -d' ' -f1)" = "$stick_sum" ] \
        && line ok "usb stick gcc named by its model: read only, the line says the boot line does not name the volume partition's GUID, the probe refused, both digests are its bytes, the image file is unchanged (HW-12)" \
        || line bad "usb stick gcc named by its model" "status $(cat "$t.rc"), see $t"
else
    stick_ran=0
    skip "usb stick: sfdisk is not on PATH; tools/build-stick.sh cannot lay out the stick (HW-4m)"
fi
t=$B/run/usb-late.txt
hello_state=$(grep -A2 '^daphnis: run hello pid 1$' tests/expected/disk.serial | grep '^daphnis: state ')
[ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] \
    && [ "$(grep -c 'daphnis: usb: storage: no answer in 5 s, the disk is dropped$' "$t")" = 1 ] \
    && grep -q '^daphnis: /home not mounted' "$t" && grep -A2 '^daphnis: run hello pid 1$' "$t" | grep -qx "$hello_state" \
    && grep -q '^daphnis: done$' "$t" \
    && (cd "$B/run" && sed 's/disk.img/usb-late.img/' "$OLDPWD/tests/expected/disk.sha256" | sha256sum --quiet -c -) > "$B/usb-late.log" 2>&1 \
    && line ok "usb late gcc: a read with no answer in 5 s stops the endpoint and drops the disk; hello after it has the golden's state digest, the volume is the pin (HW-4m)" \
    || line bad "usb late gcc" "status $(cat "$t.rc"), see $t"
t=$B/run/none.txt
[ "$(cat "$t.rc")" = 33 ] && [ ! -s "$t.err" ] && cmp -s tests/expected/disk-none.serial "$t" \
    && line ok "boot gcc without a disk: status 33, the transcript equals tests/expected/disk-none.serial" \
    || line bad "boot gcc without a disk" "status $(cat "$t.rc"), see $t"

# 3. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 4 minutes" || line bad "time" "$elapsed s"
want_total=$((gate_want + iso_pass * iso_ran + stick_pass * stick_ran)); want_skips=$((2 - iso_ran - stick_ran))
[ "$passes" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $passes PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $iso_pass with the GRUB legs, $stick_pass with the stick)" \
    || line bad "gate: fixed count" "$passes PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
