#!/usr/bin/env bash
# check.sh: the exit gate of K0 to K5 and U1-1. One PASS or FAIL line per check; exit status 1 if any FAIL.
# Outputs go under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build), which this script clears
# first, and only if it is empty, absent, or carries the marker this script writes.
#   ./check.sh
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build}
export CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
CINT_INC=$(awk '$1=="include" {print $2}' "$CINT_TOOLCHAIN" 2>/dev/null)   # the toolchain's runtime headers
BUDGET=480   # 2026-11-06: 360 s ran 312 to 345 s on the cloud after G-0, W-4, G-1 and H-R1; widened on l's pace rule (merge on cloud gates, major tests later)
FL="hello k1 fault trap stackover nullptr faults mem coop preempt shep k5 user"   # every flavor; each is built with gcc and clang
audit_want=$((5 * 2 * $(echo $FL | wc -w)))
# the PASS lines this script prints before its last line, the ISO leg left out; the ISO leg adds
# iso_pass of them, or prints one SKIP line instead. A gate that silently runs fewer checks fails.
gate_want=501   # +1 HW-2 S5 on a laptop (acpi_test: _S5 encodings, the FADT handshake fields), +1 RG-1 the images from a clean copy of the tree (user/bin NOTICE alone), +2 HW-2 S5 for RT_EXIT_OK only (exit_s5 gcc and clang, the read of PR 489), +2 RS-TTL section 6 (winvar_test gcc and clang), +1 HX-1 (check-raise.py), +1 RG-1 an app in its own window is a program that asks one (check-pixel-apps.py), +1 RG-1 settings read (setkey_run.py), +1 MS-7 (slide_test), +1 RG-1 bar names (winname_test), +1 RS-TTL wired (termsosc_test), +1 DN-51 frames 23 and 25 (fault_test), +2 RS-SURF's first box (surfopen_test gcc and clang), +1 HW-17 (check-image-apps.py), +1 RS-KR wired (inq_test), +1 the host rows within their caps (check-rows.py), +1 the overlay's asks and the Storage page's facts end with the session (check-session-end.py; sessionend_test rides tests/rs), +2 AC-D4 and the kernel prompt's window (cooldown_test, check-cooldown.py), +1 BG-1 (bgread_run), +2 the runs as the account (runas_test gcc and clang), +1 RS-KR (PR 372: keyrep_test), +1 LO-1 (PR 399: seat_test), +1 the busybox guard (unit 4b), +1 RS-ROLE (check-authop), +2 RS-HOME (homedirs gcc, clang), +1 AC-T (prompttitle_test), +2 AC-Tw (check-prompt-title.py, prompt_record_pty.py), +2 AC-Q (shquote_test, quote_pty.py), +1 AC-V (check-prompt-words.py), +1 RS-AQ (acctform_test), +1 RS-AQ (acctask_test), +1 stage RS (tests/rs/*_test.ci, one line: the RS kit's stroke_test and the Settings pages, RS-SET0), +2 RS-TZa (tz_test, tz_twin), +2 U-PNG (png_test, png_twin), +2 U-SET (settings_test, check-settings.py), +4 RS-SHOT (shotsel_test, rows_test gcc and clang, shot_run), +9 the kernel stack (KP-1 2, FS-4 2, KF-1, KF-2, KF-3a, FS-5, GV-1a), +2 HW-4m (usbscsi_test, gpt_test), +1 AC-T2 (exepath_test), +1 DN-55 Index's chrome (indexui_test), +1 Index's Grid and List (indexbody_test), +1 AM-4 (appitems_test), +1 RS-TTL (bartitle_test), +1 Index's kits of frame 32 (tests/ix, one line), +1 AC-V-R1 (reqtext_test), +1 P1 pty owner (PR 393: own_test), +1 DN-52 (PR 283: screens_test), +1 FF-1 x FS-4 (index_test: a folder's time read again) on 430: 386 on main (379 at the merge base, +6 the HW-1 probes, +1 the HW-1 tools), +38 the desk since that base; on the desk, 395 at the stack's base, +8 the desk stack (SP-5/6 tray_test, MS-3 2, DN-32 2, AM-2 2, AM-3 1), +4 AC on PR 250, +1 SP-7 (tooltip), +1 DN-21 (winrule), +2 RES-1 (fbmode gcc, clang), +1 SPDX (PR 231), +1 K-11b (keymap_test), +1 MS-5 (plate_test), +1 the kernel runtime guard (PR 270), +1 the pty flood test (PR 276), +1 the retired design guard (l 11-11 00:00Z), +3 NW-5 (PR 282: the hosted DHCP clock test, the PIC low-line probe on gcc and clang), +2 the launch fix (PR 300: launch_test, cish_pty), +1 FF 3h the Trash store (PR 287: trash_test)
iso_pass=5
ovmf_pass=13
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0 skips=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
fail_exit() { echo "check.sh: $*"; echo "RESULT: FAIL"; exit 1; }

# 0. environment
command -v qemu-system-x86_64 >/dev/null || fail_exit "qemu-system-x86_64 not found"
for t in cint gcc clang as ld objcopy objdump readelf nm python3 sha256sum cmp timeout git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B"; : > "$B/.daphnis-build"
export O=$B
git_state_before=$(git status --porcelain 2>/dev/null)

inc=$(awk '$1=="include" {print $2}' "$CINT_TOOLCHAIN")
srcs=$(awk '$1=="compiler_sources" {print $2}' "$CINT_TOOLCHAIN")
pin() { sed -n "s/^$1=//p" toolchain.pin; }
cint_bin=$(readlink -f "$(command -v cint)")
echo "gcc:    $(gcc --version | head -1)"
echo "clang:  $(clang --version | head -1)"
echo "qemu:   $(qemu-system-x86_64 --version | head -1)"
echo "ld:     $(ld --version | head -1)"
echo "cint compiler source identity: $(sha256sum "$srcs" | cut -d' ' -f1)"
echo "cint executable sha256:        $(sha256sum "$cint_bin" | cut -d' ' -f1)"
echo "cint_rt.h sha256:              $(sha256sum "$inc/cint_rt.h" | cut -d' ' -f1)"

[ "$(sha256sum "$inc/cint_rt.h" | cut -d' ' -f1)" = "$(pin cint_rt_h_sha256)" ] \
    && line ok "toolchain: cint_rt.h matches toolchain.pin" || line bad "toolchain: cint_rt.h matches toolchain.pin" "differs from pin"
[ "$(sha256sum "$srcs" | cut -d' ' -f1)" = "$(pin compiler_source_identity)" ] \
    && line ok "toolchain: compiler source identity matches toolchain.pin" \
    || line bad "toolchain: compiler source identity matches toolchain.pin" "differs from pin"
[ "$(sha256sum "$cint_bin" | cut -d' ' -f1)" = "$(awk '$1=="executable_sha256" {print $2}' "$CINT_TOOLCHAIN")" ] \
    && line ok "toolchain: the cint on PATH is the executable the toolchain file names" \
    || line bad "toolchain: cint on PATH" "sha256 differs from executable_sha256 of $CINT_TOOLCHAIN"

# 1. hosted tests of the pure modules (cache kept under the build directory). FB-2 A
# (docs/specs/2026-11-08-fb-frame-bitmap.md): src/frames.ci reaches its words through src/bits.ci, whose kernel
# version calls the view shim, and cint test starts no program that imports an extern; the hosted builds (this one and
# the mem twin, section 4) run from a copy of the modules they import with tests/hosted/src/bits.ci as src/bits.ci.
for cc in gcc clang; do for probe in boot_tags fb_pixels fb_surface pic_route exit_s5; do
    support=()
    if [ "$probe" = fb_surface ]; then
        if ! "$cc" -std=c17 -Wall -Wextra -Wpedantic -Werror -DRT_USER -ffunction-sections -fdata-sections \
            -I"$inc" -c tests/hw/idle_boundary.c -o "$B/idle-$cc.o" > "$B/idle-$cc.log" 2>&1; then
            line bad "HW-1 $probe $cc" "see $B/idle-$cc.log"; continue
        fi
        support=("$B/idle-$cc.o" -Wl,--gc-sections)
    fi
    if "$cc" -std=c17 -Wall -Wextra -Wpedantic -Werror -fsanitize=address,undefined -fno-pie -no-pie \
        -I"$inc" "tests/hw/$probe.c" "${support[@]}" -o "$B/$probe-$cc" > "$B/$probe-$cc.log" 2>&1 \
        && "$B/$probe-$cc" >> "$B/$probe-$cc.log" 2>&1; then
        line ok "HW-1 $probe $cc: ASan/UBSan parser, native pixels or real shadow/mode implementation"
    else
        line bad "HW-1 $probe $cc" "see $B/$probe-$cc.log"
    fi
done; done
if python3 -B tests/hw/run.py > "$B/fw-split.log" 2>&1; then
    line ok "HW-1 tools: explicit test suite, firmware split, safe ESP failures and bounded input cleanup"
else
    line bad "firmware splitter" "see $B/fw-split.log"
fi
# The kernel's run loop keeps its state pool's fill from one entry to the next (rt/ctx.c run_once), hosted
pool_ok=1
for cc in gcc clang; do
    "$cc" -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Werror -DCINT_RT_HELPERS_PORTABLE -Irt -I"$inc" \
        tests/hosted/ctx_pool_test.c -o "$B/ctx-pool-$cc" > "$B/ctx-pool-$cc.log" 2>&1 \
        && "$B/ctx-pool-$cc" >> "$B/ctx-pool-$cc.log" 2>&1 || pool_ok=0
done
if [ $pool_ok = 1 ]; then
    line ok "hosted: gcc and clang tests/hosted/ctx_pool_test.c, the run loop's state pool ($(tail -1 "$B/ctx-pool-gcc.log"))"
else
    line bad "hosted: tests/hosted/ctx_pool_test.c" "see $B/ctx-pool-gcc.log and $B/ctx-pool-clang.log"
fi
hr=$B/hosted-root
mkdir -p "$hr/src" "$hr/tests" "$hr/user/ci"
cp src/*.ci "$hr/src/" && cp tests/src_test.ci tests/mem_twin.ci "$hr/tests/" && cp user/ci/keymap.ci "$hr/user/ci/" \
    && cp tests/hosted/src/bits.ci "$hr/src/bits.ci"
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hr" tests/src_test.ci > "$B/hosted.log" 2>&1; then
    line ok "hosted: cint test tests/src_test.ci ($(tail -1 "$B/hosted.log"))"
else
    line bad "hosted: cint test tests/src_test.ci" "see $B/hosted.log"
fi
# FS-4 (ruling FS-R2, docs/specs/2026-11-07-bu2-meta.md section 4.6): src/ext2.ci as it is, hosted, on mke2fs's volume
# (tests/fs/ext2_vol.ci, which tools/ext2fixture.py makes and checks here) in the hosted disk: every call that changes
# the volume sets the times it should and no other
hf=$B/hosted-fs
mkdir -p "$hf/src" "$hf/tests/fs"
cp src/*.ci "$hf/src/" && cp tests/hosted/src/*.ci "$hf/src/" && cp tests/fs/*.ci "$hf/tests/fs/"
# HW-15: and the 512 MiB volume of 32,768 inodes tools/mkcintvol.sh makes for the release stick's home
# (tests/fs/ext2_big.ci, from tools/ext2bigfixture.py, checked here): a file in its last group, on the device
if python3 tools/ext2fixture.py --check tests/fs/ext2_vol.ci > "$B/hosted-fs.log" 2>&1 \
    && cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hf" tests/fs/times_test.ci >> "$B/hosted-fs.log" 2>&1 \
    && python3 tools/ext2bigfixture.py --check tests/fs/ext2_big.ci >> "$B/hosted-fs.log" 2>&1 \
    && cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hf" tests/fs/ext2_big_test.ci >> "$B/hosted-fs.log" 2>&1; then
    line ok "hosted: cint test tests/fs/times_test.ci and ext2_big_test.ci, FS-4's times on a volume and HW-15's 32,768 inodes ($(tail -1 "$B/hosted-fs.log"))"
else
    line bad "hosted: cint test tests/fs/times_test.ci and ext2_big_test.ci" "see $B/hosted-fs.log"
fi
# FS-R3 C: the stamp time (src/stamp.ci) never falls, whatever the clocks and the boot's base do
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/fs/stamp_test.ci > "$B/hosted-stamp.log" 2>&1; then
    line ok "hosted: cint test tests/fs/stamp_test.ci, FS-R3 C's stamp time ($(tail -1 "$B/hosted-stamp.log"))"
else
    line bad "hosted: cint test tests/fs/stamp_test.ci" "see $B/hosted-stamp.log"
fi
# KF-1 (docs/specs/2026-11-11-kf-facts.md section 2): statfs's record, and its counts for that volume against the ones
# dumpe2fs printed for it (tests/fs/ext2_vol.ci carries them), in the same hosted root
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hf" tests/fs/statfs_test.ci > "$B/hosted-statfs.log" 2>&1; then
    line ok "hosted: cint test tests/fs/statfs_test.ci, KF-1's record and dumpe2fs's counts ($(tail -1 "$B/hosted-statfs.log"))"
else
    line bad "hosted: cint test tests/fs/statfs_test.ci" "see $B/hosted-statfs.log"
fi
# GV-1a (docs/specs/2026-11-11-gv-revoke.md section 2a): the grant word's arithmetic (src/grants.ci) over every word,
# ceiling and revoke: the bits leave both, nothing else moves, and none comes back without the desk's yes
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/gv/grants_test.ci > "$B/hosted-grants.log" 2>&1; then
    line ok "hosted: cint test tests/gv/grants_test.ci, GV-1a's revoke arithmetic ($(tail -1 "$B/hosted-grants.log"))"
else
    line bad "hosted: cint test tests/gv/grants_test.ci" "see $B/hosted-grants.log"
fi
# FS-5 (docs/specs/2026-11-07-bu2-meta.md section 4.9): O_NOFOLLOW's answers are Linux's: user/c/mnofollow.c built with
# this host's gcc, run in a fresh directory, prints tests/expected/fs-mnofollow.out, the lines the guest leg asks of
# Daphnis on both trees
mkdir -p "$B/nofollow/d"
if gcc -std=c17 -Wall -Wextra -O2 -o "$B/nofollow/mnofollow" user/c/mnofollow.c > "$B/nofollow.log" 2>&1 \
    && "$B/nofollow/mnofollow" "$B/nofollow/d" > "$B/nofollow/out" 2>> "$B/nofollow.log" \
    && cmp -s "$B/nofollow/out" tests/expected/fs-mnofollow.out; then
    line ok "hosted: user/c/mnofollow.c on this Linux host prints tests/expected/fs-mnofollow.out (FS-5: O_NOFOLLOW, 15 lines)"
else
    line bad "hosted: mnofollow on Linux vs tests/expected/fs-mnofollow.out" "see $B/nofollow.log, $B/nofollow/out"
fi
# KF-2: sysinfo's record (src/sysinfo.ci), each field of Linux's struct at its offset
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/kf/sysinfo_test.ci > "$B/hosted-sysinfo.log" 2>&1; then
    line ok "hosted: cint test tests/kf/sysinfo_test.ci, KF-2's record ($(tail -1 "$B/hosted-sysinfo.log"))"
else
    line bad "hosted: cint test tests/kf/sysinfo_test.ci" "see $B/hosted-sysinfo.log"
fi
# KF-3a: the records of the facts call (src/facts.ci) and the share of one a short buffer gets
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/kf/facts_test.ci > "$B/hosted-facts.log" 2>&1; then
    line ok "hosted: cint test tests/kf/facts_test.ci, KF-3's records ($(tail -1 "$B/hosted-facts.log"))"
else
    line bad "hosted: cint test tests/kf/facts_test.ci" "see $B/hosted-facts.log"
fi
# P1 (the plan, 2026-11-11): whose a pty's slave is (src/ptyown.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/pty/own_test.ci > "$B/ptyown.log" 2>&1; then
    line ok "hosted: cint test tests/pty/own_test.ci, whose a pty's slave is ($(tail -1 "$B/ptyown.log"))"
else
    line bad "hosted: cint test tests/pty/own_test.ci" "see $B/ptyown.log"
fi
# RS-KR: key repeat from the timer tick (src/keyrep.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/kr/keyrep_test.ci > "$B/hosted-keyrep.log" 2>&1; then
    line ok "hosted: cint test tests/kr/keyrep_test.ci, RS-KR's key repeat ($(tail -1 "$B/hosted-keyrep.log"))"
else
    line bad "hosted: cint test tests/kr/keyrep_test.ci" "see $B/hosted-keyrep.log"
fi
# RS-KR wired: the input path of /dev/input/event0 (src/inq.ci), from PS/2 bytes and USB key events at timer ticks to
# the events a reader gets, the repeats included
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/kr/inq_test.ci > "$B/hosted-inq.log" 2>&1; then
    line ok "hosted: cint test tests/kr/inq_test.ci, RS-KR's input path ($(tail -1 "$B/hosted-inq.log"))"
else
    line bad "hosted: cint test tests/kr/inq_test.ci" "see $B/hosted-inq.log"
fi
# RES-1: the screen sizes rt/fb.c programs (rt/fbmode.h, the header the kernel includes), hosted, with each compiler
for cc in gcc clang; do
    if $cc -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Werror -Irt tests/hosted/fbmode_test.c \
            -o "$B/fbmode-$cc" > "$B/fbmode-$cc.log" 2>&1 && "$B/fbmode-$cc" >> "$B/fbmode-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/hosted/fbmode_test.c, the screen sizes of RES-1 ($(tail -1 "$B/fbmode-$cc.log"))"
    else
        line bad "hosted: $cc tests/hosted/fbmode_test.c" "see $B/fbmode-$cc.log"
    fi
done
# RS-HOME: the three folders of a home (user/ci/homedirs.h, the header user/ci/host.c's home row includes), hosted, with
# each compiler, the login replaced by the test's own
for cc in gcc clang; do
    if $cc -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Werror -Iuser/ci \
            tests/hosted/homedirs_test.c -o "$B/homedirs-$cc" > "$B/homedirs-$cc.log" 2>&1 \
            && TMPDIR="$B" "$B/homedirs-$cc" >> "$B/homedirs-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/hosted/homedirs_test.c, the folders of a home ($(tail -1 "$B/homedirs-$cc.log"))"
    else
        line bad "hosted: $cc tests/hosted/homedirs_test.c" "see $B/homedirs-$cc.log"
    fi
done
# The desk's runs as the account (user/ci/runas.h, the header user/ci/host.c's run rows include), hosted, with each
# compiler, the login, the chdir and the programs replaced by the test's own
for cc in gcc clang; do
    if $cc -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Werror -Iuser/ci \
            tests/hosted/runas_test.c -o "$B/runas-$cc" > "$B/runas-$cc.log" 2>&1 \
            && TMPDIR="$B" "$B/runas-$cc" >> "$B/runas-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/hosted/runas_test.c, the desk's runs as the account ($(tail -1 "$B/runas-$cc.log"))"
    else
        line bad "hosted: $cc tests/hosted/runas_test.c" "see $B/runas-$cc.log"
    fi
done
# Every kernel's emitted C calls only runtime functions the kernel links (board 20261110T213349Z: a 9 KiB local array
# in src/tile.ci emitted the hosted rt's cint_rt_scratch calls, so the hdesk kernel did not link).
krt_bad=""
for m in src/main*.ci; do
    k=$(basename "$m" .ci)
    rm -rf "$B/kemit-$k" "$B/kemit-$k.stage-0"
    if ! cint emit-c --toolchain "$CINT_TOOLCHAIN" --root . --out "$B/kemit-$k" "$m" > "$B/kemit-$k.log" 2>&1 ||
        ! python3 tools/check-kernel-rt.py "$CINT_INC" rt "$B/kemit-$k" "$B/kemit-$k.stage-0" >> "$B/kemit-$k.log" 2>&1; then
        krt_bad="$krt_bad $k"
    fi
done
if [ -z "$krt_bad" ]; then
    line ok "hosted: every kernel's emitted C calls only runtime functions the kernel defines (tools/check-kernel-rt.py)"
else
    line bad "hosted: kernel runtime calls" "not defined for$krt_bad; see $B/kemit-*.log"
fi
# The pty's queues under a key flood (board 20261110T234031Z): src/pty.ci hosted with tests/hosted/pty's stand-ins.
pr=$B/hosted-pty
rm -rf "$pr" && mkdir -p "$pr/src" "$pr/tests"
cp tests/hosted/pty/src/*.ci src/ptyown.ci src/pty.ci "$pr/src/" && cp tests/hosted/pty/pty_test.ci "$pr/tests/"
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$pr" tests/pty_test.ci > "$B/pty-test.log" 2>&1; then
    line ok "hosted: cint test tests/hosted/pty/pty_test.ci, the pty's queues under a key flood ($(tail -1 "$B/pty-test.log"))"
else
    line bad "hosted: cint test tests/hosted/pty/pty_test.ci" "see $B/pty-test.log"
fi
# NW-5 under NW-1: src/dhcp.ci's retransmits and lease count net.timers(), not net.ticks(), with
# tests/hosted/dhcp's stand-ins for serial, bootarg, net, eth and ip
dr=$B/hosted-dhcp
rm -rf "$dr" && mkdir -p "$dr/src" "$dr/tests"
cp tests/hosted/dhcp/src/*.ci src/dhcp.ci src/text.ci "$dr/src/" && cp tests/hosted/dhcp/dhcp_test.ci "$dr/tests/"
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$dr" tests/dhcp_test.ci > "$B/dhcp-test.log" 2>&1; then
    line ok "hosted: cint test tests/hosted/dhcp/dhcp_test.ci, DHCP's clock in timer wakes ($(tail -1 "$B/dhcp-test.log"))"
else
    line bad "hosted: cint test tests/hosted/dhcp/dhcp_test.ci" "see $B/dhcp-test.log"
fi
# HW-4m: the bytes of USB mass storage (src/usbscsi.ci), hosted
# HW-2 (the kernel read's P1 on PR 493): \_S5 in the encodings firmware compiles it to, and the FADT's SMI_CMD and
# ACPI_ENABLE, the PM1 event and GPE blocks, on fake tables' bytes (src/acpitab.ci); rt/start.c's handshake, clears and
# PM1 writes are tests/hw/exit_s5.c's
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/hw/acpi_test.ci > "$B/acpi.log" 2>&1; then
    line ok "hosted: cint test tests/hw/acpi_test.ci, _S5, the ACPI mode handshake and the event blocks of HW-2 ($(tail -1 "$B/acpi.log"))"
else
    line bad "hosted: cint test tests/hw/acpi_test.ci" "see $B/acpi.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/hw/usbscsi_test.ci > "$B/usbscsi.log" 2>&1; then
    line ok "hosted: cint test tests/hw/usbscsi_test.ci, the wrappers, commands and descriptor walk of HW-4m ($(tail -1 "$B/usbscsi.log"))"
else
    line bad "hosted: cint test tests/hw/usbscsi_test.ci" "see $B/usbscsi.log"
fi
# HW-4m: the stick's GUID partition table (src/gpt.ci), hosted, with tables that lie
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/hw/gpt_test.ci > "$B/gpt.log" 2>&1; then
    line ok "hosted: cint test tests/hw/gpt_test.ci, the stick's partition table of HW-4m ($(tail -1 "$B/gpt.log"))"
else
    line bad "hosted: cint test tests/hw/gpt_test.ci" "see $B/gpt.log"
fi
# LO-1 (the plan, 2026-11-11): whose the desk's seat is (src/seat.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/seat/seat_test.ci > "$B/seat.log" 2>&1; then
    line ok "hosted: cint test tests/seat/seat_test.ci, whose the desk's seat is ($(tail -1 "$B/seat.log"))"
else
    line bad "hosted: cint test tests/seat/seat_test.ci" "see $B/seat.log"
fi
# FF-2: the Super plane's matcher (user/ci/kit/match.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/match_test.ci > "$B/match.log" 2>&1; then
    line ok "hosted: cint test tests/ff/match_test.ci, the matcher of FF-2 ($(tail -1 "$B/match.log"))"
else
    line bad "hosted: cint test tests/ff/match_test.ci" "see $B/match.log"
fi
# AC-T2: the record of FBIO_TILE_INFO kinds 13 and 14, the program a window's process runs (src/exepath.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/exepath_test.ci > "$B/exepath.log" 2>&1; then
    line ok "hosted: cint test tests/ac/exepath_test.ci, AC-T2's image path record ($(tail -1 "$B/exepath.log"))"
else
    line bad "hosted: cint test tests/ac/exepath_test.ci" "see $B/exepath.log"
fi
# K-11b: the keyboard layouts and dead keys (user/ci/keymap.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/k/keymap_test.ci > "$B/keymap.log" 2>&1; then
    line ok "hosted: cint test tests/k/keymap_test.ci, the layouts and dead keys of K-11b ($(tail -1 "$B/keymap.log"))"
else
    line bad "hosted: cint test tests/k/keymap_test.ci" "see $B/keymap.log"
fi
# FF-3: the Super plane's open table (user/ci/kit/opener.ci), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/opener_test.ci > "$B/opener.log" 2>&1; then
    line ok "hosted: cint test tests/ff/opener_test.ci, the open table of FF-3 ($(tail -1 "$B/opener.log"))"
else
    line bad "hosted: cint test tests/ff/opener_test.ci" "see $B/opener.log"
fi
# FF-0: the desk's icons (user/ci/kit/icons.ci from tools/icons.py and the drawings in tools/icons/)
if python3 tools/icons.py --check > "$B/icons.log" 2>&1; then
    line ok "icons: user/ci/kit/icons.ci is what tools/icons.py writes from the 30 drawings, each its studio-assets sum"
else
    line bad "icons: tools/icons.py --check" "see $B/icons.log"
fi
# OPEN-SOURCE unit 5 (SPDX-1 A): every Daphnis-owned .ci ends with its SPDX line; generated files get it from their generators
if python3 tools/spdx.py --check > "$B/spdx.log" 2>&1; then
    line ok "spdx: $(tail -1 "$B/spdx.log")"
else
    line bad "spdx: tools/spdx.py --check" "see $B/spdx.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/icons_test.ci > "$B/icons-test.log" 2>&1; then
    line ok "hosted: cint test tests/ff/icons_test.ci, the icons of FF-0 ($(tail -1 "$B/icons-test.log"))"
else
    line bad "hosted: cint test tests/ff/icons_test.ci" "see $B/icons-test.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/plane_test.ci > "$B/plane.log" 2>&1; then
    line ok "hosted: cint test tests/ff/plane_test.ci, the Super plane's kit of FF-5 ($(tail -1 "$B/plane.log"))"
else
    line bad "hosted: cint test tests/ff/plane_test.ci" "see $B/plane.log"
fi
# FF edition 14 (section 3g): the app descriptors, user/ci/kit/apps.ci, hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/apps_test.ci > "$B/apps.log" 2>&1; then
    line ok "hosted: cint test tests/ff/apps_test.ci, the app descriptors of FF 3g ($(tail -1 "$B/apps.log"))"
else
    line bad "hosted: cint test tests/ff/apps_test.ci" "see $B/apps.log"
fi
# FONT-1, F3 (docs/specs/2026-11-07-k-kit2.md section 3e): the coverage glyphs (user/ci/kit/jbm*.ci, inter*.ci) from
# the bundled TTFs (tools/fonts/SOURCES.md), and their hosted test
if python3 tools/glyphs.py --check > "$B/glyphs.log" 2>&1; then
    line ok "glyphs: the 34 coverage modules, faces.ci and appfaces.ci are what tools/glyphs.py writes from the 5 TTFs, each its recorded sum"
else
    line bad "glyphs: tools/glyphs.py --check" "see $B/glyphs.log"
fi
# DN-23: the window bar's stroked button glyphs, user/ci/kit/wbglyph.ci, are what tools/wbglyph.py writes
if python3 tools/wbglyph.py --check > "$B/wbglyph.log" 2>&1; then
    line ok "wbglyph: user/ci/kit/wbglyph.ci is what tools/wbglyph.py writes (DN-23's four 1.5 px glyphs at 1x, 2x, 3x)"
else
    line bad "wbglyph: tools/wbglyph.py --check" "see $B/wbglyph.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/font/glyphs_test.ci > "$B/glyphs-test.log" 2>&1; then
    line ok "hosted: cint test tests/font/glyphs_test.ci, the coverage glyphs of FONT-1 ($(tail -1 "$B/glyphs-test.log"))"
else
    line bad "hosted: cint test tests/font/glyphs_test.ci" "see $B/glyphs-test.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/font/text_test.ci > "$B/text-test.log" 2>&1; then
    line ok "hosted: cint test tests/font/text_test.ci, the coverage text path of FONT-1 F4 ($(tail -1 "$B/text-test.log"))"
else
    line bad "hosted: cint test tests/font/text_test.ci" "see $B/text-test.log"
fi
# FONT-2 A (docs/specs/2026-11-07-k-kit2.md section 3i): the chrome's pen (user/ci/kit/pen.ci) at 1x and natively at
# 2x, the calendar, the system panel and the chevron equal to tools/check-hdesk.py's twin
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/font/chrome2x_test.ci > "$B/chrome2x.log" 2>&1; then
    line ok "hosted: cint test tests/font/chrome2x_test.ci, the chrome at 2x of FONT-2 A ($(tail -1 "$B/chrome2x.log"))"
else
    line bad "hosted: cint test tests/font/chrome2x_test.ci" "see $B/chrome2x.log"
fi
# DN-20 and DN-21: a new float's size, place and cascade, and the restore's frames (kit/winrule.ci), the twin's numbers
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn20/winrule_test.ci > "$B/dn20-winrule.log" 2>&1; then
    line ok "hosted: cint test tests/dn20/winrule_test.ci ($(tail -1 "$B/dn20-winrule.log"))"
else
    line bad "hosted: cint test tests/dn20/winrule_test.ci" "see $B/dn20-winrule.log"
fi
# Board 20261111T170652Z, DN-60: the desk types an app into its new terminal as `exec CMD`, a command as is, Console
# as nothing (kit/launch.ci); a terminal that ends with the shell's 126 or 127 after exec could not start its app
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/launch/launch_test.ci > "$B/launch.log" 2>&1; then
    line ok "hosted: cint test tests/launch/launch_test.ci, an app typed as exec, a command as is, Console as nothing ($(tail -1 "$B/launch.log"))"
else
    line bad "hosted: cint test tests/launch/launch_test.ci" "see $B/launch.log"
fi
# DN-6 (design note 6): the desk's frames 8 to 11 drawn by hdesk.ci, at UI scale 1 and 2 (and 3 where named) in both
# themes, equal to tools/check-hdesk.py's dn_ twin; one PASS line a frame group (prompt_ac: AC-1c's approval prompt in
# frame 8's parts)
for t in float prompt prompt_ac panel switcher finder settings tray tooltip; do
    if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn6/${t}_test.ci > "$B/dn6-$t.log" 2>&1; then
        line ok "hosted: cint test tests/dn6/${t}_test.ci, DN-6's $t equal to its twin ($(tail -1 "$B/dn6-$t.log"))"
    else
        line bad "hosted: cint test tests/dn6/${t}_test.ci" "see $B/dn6-$t.log"
    fi
done
# MS-1 (docs/specs/2026-11-10-ms-motion-shadows.md, law 1): the one blend, user/ci/kit/blend.ci, hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ms/blend_test.ci > "$B/blend.log" 2>&1; then
    line ok "hosted: cint test tests/ms/blend_test.ci, the one blend of MS-1 ($(tail -1 "$B/blend.log"))"
else
    line bad "hosted: cint test tests/ms/blend_test.ci" "see $B/blend.log"
fi
# K-2b: the terminal's UTF-8 decode (user/ci/terms.ci; docs/specs/2026-11-07-k-kit2.md section 3f), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/k/terms_test.ci > "$B/terms.log" 2>&1; then
    line ok "hosted: cint test tests/k/terms_test.ci, the terminal's UTF-8 decode of K-2b ($(tail -1 "$B/terms.log"))"
else
    line bad "hosted: cint test tests/k/terms_test.ci" "see $B/terms.log"
fi
# FONT-1 swap (docs/specs/2026-11-07-k-kit2.md section 3f, as built): the terminal's cells are kit/mtext.ci's, hosted,
# and tools/check-tiler.py's terminal twin draws what terms.ci draws on a small case
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/font/term_cells_test.ci > "$B/term-cells.log" 2>&1; then
    line ok "hosted: cint test tests/font/term_cells_test.ci, the terminal's mtext cells of the FONT-1 swap ($(tail -1 "$B/term-cells.log"))"
else
    line bad "hosted: cint test tests/font/term_cells_test.ci" "see $B/term-cells.log"
fi
if cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/k/term_twin.ci > "$B/term-twin.out" 2> "$B/term-twin.log" \
    && python3 tools/check-tiler.py --hosted "$B/term-twin.out" >> "$B/term-twin.log" 2>&1; then
    line ok "hosted: tests/k/term_twin.ci's terminal at 1x and 2x is tools/check-tiler.py's twin, pixel for pixel"
else
    line bad "hosted: tests/k/term_twin.ci against tools/check-tiler.py --hosted" "see $B/term-twin.log"
fi
# AM-2, RES-1: one FBIO_TILE name to one number, across src/tile.ci and every copy in user/ci (a clash fails here)
if python3 tools/check-ioctls.py . > "$B/ioctls.log" 2>&1; then
    line ok "hosted: tools/check-ioctls.py, the FBIO_TILE family's numbers ($(tail -1 "$B/ioctls.log"))"
else
    line bad "hosted: tools/check-ioctls.py" "$(head -1 "$B/ioctls.log"), see $B/ioctls.log"
fi
# l 2026-11-11 00:00Z: no retired desk design ships; the old hdesk panel's strings in src/, rt/ or user/ (a stale
# committed user/bin/hdesk included) fail here; every board or release image runs the same tool with --image
if python3 tools/check-stale-design.py > "$B/stale-design.log" 2>&1; then
    line ok "hosted: tools/check-stale-design.py, no retired desk design in src/, rt/, user/"
else
    line bad "hosted: tools/check-stale-design.py" "$(tail -1 "$B/stale-design.log"), see $B/stale-design.log"
fi
# DOS-3, CORE-4 A (unit 4b): this tree tracks no busybox binary; a gate that wants busybox as its Linux oracle builds it
# from the pinned tarball (user/busybox/oracle.sh with CORE_ORACLE), never from user/bin. RG-1: nor any other program:
# user/bin holds NOTICE alone, and every image and gate takes its programs from O/ubin, built from source at HEAD.
# tools/check-user-bin.sh on this tree, and on two it must refuse, so the line is known to fail when it should (the
# merge lane's P1 on PR 492: a grep with nothing to print exits 1, and the line before it failed on a right tree):
# a stray program tracked beside NOTICE, and no NOTICE
ubn="$B/user-bin-refused"
stray="$ubn/stray/user/bin"
mkdir -p "$stray" "$ubn/bare"
git -C "$ubn/stray" init -q && : > "$stray/NOTICE" && : > "$stray/cish" && git -C "$ubn/stray" add user/bin \
    && git -C "$ubn/bare" init -q
if bb=$(tools/check-user-bin.sh .) && ! tools/check-user-bin.sh "$ubn/stray" > /dev/null \
    && ! tools/check-user-bin.sh "$ubn/bare" > /dev/null; then
    line ok "tree: no program tracked under user/bin, NOTICE alone; a stray or no NOTICE refused (DOS-3, RG-1)"
else
    line bad "tree: no program tracked under user/bin, NOTICE alone (DOS-3, RG-1)" "${bb:-a tree it must refuse passed}"
fi
# FF edition 14 (section 3g): the Super plane drawn by the kit (user/ci/kit/plane.ci, shape.ci) on the host at 1x
# and 2x on the three screens, against tools/check-hdesk.py's twin, pixel for pixel
if cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/plane_proof.ci > "$B/plane-proof.out" 2> "$B/plane-proof.log" \
    && python3 tools/check-hdesk.py --plane-proof "$B/plane-proof.out" >> "$B/plane-proof.log" 2>&1; then
    line ok "hosted: tests/ff/plane_proof.ci's Super plane, resting and with a query, is tools/check-hdesk.py's twin, pixel for pixel"
else
    line bad "hosted: tests/ff/plane_proof.ci against tools/check-hdesk.py --plane-proof" "see $B/plane-proof.log"
fi
# DN-37, DN-38: the loading wheel (user/ci/kit/wheel.ci): its tables are tools/wheel.py's, and its frames the twin's
if python3 tools/wheel.py --check > "$B/wheel.log" 2>&1 \
    && cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn37/wheel_test.ci >> "$B/wheel.log" 2>&1 \
    && cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn37/busy_test.ci >> "$B/wheel.log" 2>&1; then
    line ok "hosted: the loading wheel of DN-37 and DN-38 is tools/wheel.py's twin ($(tail -1 "$B/wheel.log"))"
else
    line bad "hosted: the loading wheel (tools/wheel.py --check, tests/dn37/wheel_test.ci)" "see $B/wheel.log"
fi
# DN-5, DN-8, DN-9, DN-12: the icons of draft 3 and the file icons (user/ci/kit/icons3.ci and fileicons.ci, written by
# tools/svgicons.py from the SVGs in tools/icons-v3/, drawn by kit/iconrle.ci), hosted, and against tools/iconwin.py
if python3 tools/svgicons.py --check > "$B/svgicons.log" 2>&1; then
    line ok "icons3: user/ci/kit/icons3.ci and fileicons.ci are what tools/svgicons.py draws from tools/icons-v3/, each SVG its sum"
else
    line bad "icons3: tools/svgicons.py --check" "see $B/svgicons.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/icons3_test.ci > "$B/icons3-test.log" 2>&1; then
    line ok "hosted: cint test tests/ff/icons3_test.ci, the icons of DN-5 and DN-9 ($(tail -1 "$B/icons3-test.log"))"
else
    line bad "hosted: cint test tests/ff/icons3_test.ci" "see $B/icons3-test.log"
fi
if cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/icons3_proof.ci > "$B/icons3-proof.out" 2> "$B/icons3-proof.log" \
    && python3 tools/iconwin.py --proof "$B/icons3-proof.out" >> "$B/icons3-proof.log" 2>&1; then
    line ok "hosted: tests/ff/icons3_proof.ci's icons at every size, scale and ground are tools/iconwin.py's twin, pixel for pixel"
else
    line bad "hosted: tests/ff/icons3_proof.ci against tools/iconwin.py --proof" "see $B/icons3-proof.log"
fi
# MS-2 (the same spec, law 3, section 4): the easing curves out and in (user/ci/kit/ease.ci from tools/ease.py) and the animations,
# user/ci/kit/anim.ci, hosted
if python3 tools/ease.py --check > "$B/ease.log" 2>&1; then
    line ok "ease: user/ci/kit/ease.ci is what tools/ease.py writes, the curves out and in of MS-2"
else
    line bad "ease: tools/ease.py --check" "see $B/ease.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ms/anim_test.ci > "$B/anim.log" 2>&1; then
    line ok "hosted: cint test tests/ms/anim_test.ci, the animations of MS-2 ($(tail -1 "$B/anim.log"))"
else
    line bad "hosted: cint test tests/ms/anim_test.ci" "see $B/anim.log"
fi
# MS-3 (the same spec, law 2, section 3): the shadow tables (user/ci/kit/shadow.ci from tools/shadow.py) and
# shade_row, user/ci/kit/shade.ci, hosted
if python3 tools/shadow.py --check > "$B/shadow.log" 2>&1; then
    line ok "shadow: user/ci/kit/shadow.ci is what tools/shadow.py writes, the three levels of MS-3"
else
    line bad "shadow: tools/shadow.py --check" "see $B/shadow.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ms/shadow_test.ci > "$B/shadow-test.log" 2>&1; then
    line ok "hosted: cint test tests/ms/shadow_test.ci, the shadows of MS-3 ($(tail -1 "$B/shadow-test.log"))"
else
    line bad "hosted: cint test tests/ms/shadow_test.ci" "see $B/shadow-test.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ms/slide_test.ci \
    > "$B/slide-test.log" 2>&1; then
    line ok "hosted: cint test tests/ms/slide_test.ci, the desktop slide of MS-7 ($(tail -1 "$B/slide-test.log"))"
else
    line bad "hosted: cint test tests/ms/slide_test.ci" "see $B/slide-test.log"
fi
# AM-2 and DN-43: the app menu's declaration on the program's side and the About sheet (kits appmenu and about)
for t in appmenu about ondesk unsaved appitems bartitle termsosc; do   # AM-3: ondesk, the desk terminal guard; AM
    # section 7: unsaved, the ask; AM-4: appitems, an app's own rows; RS-TTL: bartitle, the title in the bars, and
    # termsosc, its wiring in terms.ci
    if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/am/${t}_test.ci > "$B/am-$t.log" 2>&1; then
        line ok "hosted: cint test tests/am/${t}_test.ci ($(tail -1 "$B/am-$t.log"))"
    else
        line bad "hosted: cint test tests/am/${t}_test.ci" "see $B/am-$t.log"
    fi
done
# RG-1 (NAMES-28, note 28): every window by its app's approved name in the bar and the window lists, and its icon by
# the same program (P2-b) (kit/winname.ci)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/rs/winname_test.ci \
    > "$B/winname.log" 2>&1; then
    line ok "bar names: Console, Edit, View, Read, Calc, CVim, Index, Monitor, Fetch and Settings by every title their \
windows carry (bin/NAME, an argument), each window's icon its app's (CVim in a terminal is CVim's, P2-b), a Console \
running sh as Console in Grants, Web Browser with no program \
($(tail -1 "$B/winname.log"))"
else
    line bad "bar names: tests/rs/winname_test.ci" "see $B/winname.log"
fi
# Stage RS (docs/specs/2026-11-11-rs-rel-s1-units.md): the stroked lines and areas of the apps' symbols and graphs
# (user/ci/kit/stroke.ci) and the Settings pages as kit modules (RS-SET0 to RS-SET6), hosted, every tests/rs/*_test.ci
# in one line, so a stage RS pull request adds its test file and leaves this gate's count alone
rs_n=0 rs_bad=""
for f in tests/rs/*_test.ci; do
    rs_n=$((rs_n + 1))
    t=$(basename "$f" .ci)
    cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . "$f" > "$B/rs-$t.log" 2>&1 || rs_bad="$rs_bad $t"
done
if [ -z "$rs_bad" ]; then
    line ok "hosted: cint test tests/rs/*_test.ci, stage RS's strokes and the Settings pages ($rs_n files)"
else
    line bad "hosted: cint test tests/rs/*_test.ci" "failed:$rs_bad, see $B/rs-*.log"
fi
# DN-32 and DN-33 (design notes 32 and 33): the symbol table (user/ci/kit/symbols.ci from tools/symbols.py) and the
# right-click menu kit, user/ci/kit/ctxmenu.ci, hosted against tools/check-hdesk.py's twin
if python3 tools/symbols.py --check > "$B/symbols.log" 2>&1; then
    line ok "symbols: user/ci/kit/symbols.ci is what tools/symbols.py writes from tools/symbols-v1"
else
    line bad "symbols: tools/symbols.py --check" "see $B/symbols.log"
fi
# DN-46 (c): the one pin store's key and Index's copy (user/ci/kit/taskbar.ci)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn32/taskbar_test.ci > "$B/taskbar.log" 2>&1; then
    line ok "hosted: cint test tests/dn32/taskbar_test.ci, the one pin store of DN-46 (c) ($(tail -1 "$B/taskbar.log"))"
else
    line bad "hosted: cint test tests/dn32/taskbar_test.ci" "see $B/taskbar.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn32/ctxmenu_test.ci > "$B/ctxmenu.log" 2>&1; then
    line ok "hosted: cint test tests/dn32/ctxmenu_test.ci, the right-click menu of DN-32 and DN-33 ($(tail -1 "$B/ctxmenu.log"))"
else
    line bad "hosted: cint test tests/dn32/ctxmenu_test.ci" "see $B/ctxmenu.log"
fi
# MS-5 (the same spec, sections 4 and 6): a plate's open and close and the bar message's in and out (kit/plate.ci)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ms/plate_test.ci > "$B/plate-test.log" 2>&1; then
    line ok "hosted: cint test tests/ms/plate_test.ci, the plates and the bar message of MS-5 ($(tail -1 "$B/plate-test.log"))"
else
    line bad "hosted: cint test tests/ms/plate_test.ci" "see $B/plate-test.log"
fi
# AC-1b: BLAKE2b and Argon2id (user/ci/blake2b.ci, argon2.ci; RFC 7693, RFC 9106), hosted; authd on the host against
# tools/ac-vectors.py (docs/specs/2026-11-08-ac-accounts.md section 6)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/blake2b_test.ci > "$B/blake2b.log" 2>&1; then
    line ok "hosted: cint test tests/ac/blake2b_test.ci, BLAKE2b of AC-1b ($(tail -1 "$B/blake2b.log"))"
else
    line bad "hosted: cint test tests/ac/blake2b_test.ci" "see $B/blake2b.log"
fi
# DN-41 (a): the bar of the account screens (hdesk.ci bar_items)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/bar_test.ci > "$B/acbar.log" 2>&1; then
    line ok "hosted: cint test tests/ac/bar_test.ci, login, lock and first boot show the roundel and the clock only ($(tail -1 "$B/acbar.log"))"
else
    line bad "hosted: cint test tests/ac/bar_test.ci" "see $B/acbar.log"
fi
# AC-T (docs/specs/2026-11-11-ac-t-prompt-title.md): the approval prompt's title (user/ci/kit/prompttitle.ci) is a name
# of kit/apps.ci by the desk's own record, never the name a program gives itself
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/prompttitle_test.ci > "$B/prompttitle.log" 2>&1; then
    line ok "hosted: cint test tests/ac/prompttitle_test.ci, the approval prompt's title of AC-T ($(tail -1 "$B/prompttitle.log"))"
else
    line bad "hosted: cint test tests/ac/prompttitle_test.ci" "see $B/prompttitle.log"
fi
# AC-V-R1 (docs/specs/2026-11-11-ac-v-prompt-words.md edition 2): the request text the prompts show and log is
# printable ASCII only (user/ci/kit/reqtext.ci); tools/check-prompt-words.py holds the desk to that one writer
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/reqtext_test.ci > "$B/reqtext.log" 2>&1; then
    line ok "hosted: cint test tests/ac/reqtext_test.ci, the request text of AC-V-R1 ($(tail -1 "$B/reqtext.log"))"
else
    line bad "hosted: cint test tests/ac/reqtext_test.ci" "see $B/reqtext.log"
fi
# AC-Tw: the desk's wiring of it: kp_title has one writer, prompttitle.title over the desk's own record (lx_app)
if python3 tools/check-prompt-title.py > "$B/prompt-title.log" 2>&1; then
    line ok "hosted: tools/check-prompt-title.py, $(tail -1 "$B/prompt-title.log")"
else
    line bad "hosted: tools/check-prompt-title.py" "$(head -1 "$B/prompt-title.log"), see $B/prompt-title.log"
fi
# AC-D4: the 30 s cooldown after a refused prompt is the window's and ends with it; a new window in the slot is asked.
# A kernel prompt whose window closes holds no window: a yes gives the asker its bit and no other tree the hold
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/cooldown_test.ci > "$B/cooldown.log" 2>&1; then
    line ok "hosted: cint test tests/ac/cooldown_test.ci, a closed window's cooldown and hold ($(tail -1 "$B/cooldown.log"))"
else
    line bad "hosted: cint test tests/ac/cooldown_test.ci" "see $B/cooldown.log"
fi
# HX-1: every way a window takes the focus raises it (raise(); the rank rule hosted in tests/rs/raise_test.ci)
if python3 -B tools/check-raise.py > "$B/raise.log" 2>&1; then
    line ok "hosted: tools/check-raise.py, $(tail -1 "$B/raise.log")"
else
    line bad "hosted: tools/check-raise.py" "$(head -1 "$B/raise.log"), see $B/raise.log"
fi
if python3 tools/check-cooldown.py > "$B/cooldown-wiring.log" 2>&1; then
    line ok "hosted: tools/check-cooldown.py, $(tail -1 "$B/cooldown-wiring.log")"
else
    line bad "hosted: tools/check-cooldown.py" "$(head -1 "$B/cooldown-wiring.log"), see $B/cooldown-wiring.log"
fi
# What a session leaves on the overlay ends with it: logout and lock close Storage's Empty Trash ask, logout closes
# AM section 7's unsaved ask, logout and a login forget the Storage page's walk and count (tests/rs/sessionend_test.ci)
if python3 tools/check-session-end.py > "$B/session-end.log" 2>&1; then
    line ok "hosted: tools/check-session-end.py, $(tail -1 "$B/session-end.log")"
else
    line bad "hosted: tools/check-session-end.py" "$(head -1 "$B/session-end.log"), see $B/session-end.log"
fi
# Every user program binds its host rows within its CI_MAX_ROWS (user/ci/host.h); past it, it cannot start
if python3 tools/check-rows.py > "$B/rows.log" 2>&1; then
    line ok "hosted: tools/check-rows.py, $(tail -1 "$B/rows.log")"
else
    line bad "hosted: tools/check-rows.py" "$(head -1 "$B/rows.log"), see $B/rows.log"
fi
# RG-1: an app runs in its own window (its terminal never shown) exactly when its program asks a window of the desk
if python3 tools/check-pixel-apps.py > "$B/pixel-apps.log" 2>&1; then
    line ok "hosted: tools/check-pixel-apps.py, $(tail -1 "$B/pixel-apps.log")"
else
    line bad "hosted: tools/check-pixel-apps.py" "$(head -1 "$B/pixel-apps.log"), see $B/pixel-apps.log"
fi
# AC-V (docs/specs/2026-11-11-ac-v-prompt-words.md): the approval prompts draw the desk's record, no program-set byte
if python3 tools/check-prompt-words.py > "$B/prompt-words.log" 2>&1; then
    line ok "hosted: tools/check-prompt-words.py, $(tail -1 "$B/prompt-words.log")"
else
    line bad "hosted: tools/check-prompt-words.py" "$(head -1 "$B/prompt-words.log"), see $B/prompt-words.log"
fi
# HW-17: the release image (hdesk/release.cpio, the Makefile's own list) holds every /bin program the desk's sources
# name and no Doom file, and the release kernel's main brings up the network
if python3 tools/check-image-apps.py > "$B/image-apps.log" 2>&1; then
    line ok "hosted: tools/check-image-apps.py, $(tail -1 "$B/image-apps.log" | sed 's/^check-image-apps: //')"
else
    line bad "hosted: tools/check-image-apps.py" "$(head -1 "$B/image-apps.log"), see $B/image-apps.log"
fi
# RG-1 (the kernel read of PR 490): every image of the Makefile built by make alone from a clean copy of the tracked
# tree whose user/bin holds NOTICE alone; a recipe that reads user/bin fails make, one that writes it leaves more there
cl="$B/clean"
mkdir -p "$cl/src"
git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$cl/src"
find "$cl/src/user/bin" -type f ! -name NOTICE -delete
imgs=$(grep -oE '^\$\(O\)/[a-z0-9]+/(initrd|release)\.cpio' Makefile | sed "s#^\$(O)#$cl/o#" | sort -u)
if make -s -C "$cl/src" -j"$(nproc)" O="$cl/o" $imgs > "$B/clean.log" 2>&1 && [ "$(ls -A "$cl/src/user/bin")" = NOTICE ] \
    && ( for i in $imgs; do test -s "$i" || exit 1; done ); then
    line ok "hosted: the $(echo $imgs | wc -w) images build from a clean copy of the tree whose user/bin holds NOTICE alone (RG-1)"
else
    line bad "hosted: the images from a clean copy of the tree, user/bin NOTICE alone (RG-1)" \
        "see $B/clean.log; user/bin holds $(ls -A "$cl/src/user/bin" | tr '\n' ' ')"
fi
# AC-Q (docs/specs/2026-11-11-ac-q-launch-quoting.md): every path the desk types is one quoted word, every line plain
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/launch/shquote_test.ci > "$B/shquote.log" 2>&1; then
    line ok "hosted: cint test tests/launch/shquote_test.ci, the desk's quoting of AC-Q ($(tail -1 "$B/shquote.log"))"
else
    line bad "hosted: cint test tests/launch/shquote_test.ci" "see $B/shquote.log"
fi
# DN-51 frames 23 and 25: the fault record a desk terminal keeps, the Fault window's keys, "not answering"'s keys
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/dn51/fault_test.ci > "$B/dn51-fault.log" 2>&1; then
    line ok "hosted: cint test tests/dn51/fault_test.ci, frames 23 and 25's record and keys ($(tail -1 "$B/dn51-fault.log"))"
else
    line bad "hosted: cint test tests/dn51/fault_test.ci" "see $B/dn51-fault.log"
fi
# RG-1: the pty cases run cish as the images take it, built from source at HEAD ($B/ubin/cish, the Makefile's rule),
# never the committed user/bin/cish; a build that fails leaves no cish, and each case below fails on it
make -s -j"$(nproc)" O="$B" "$B/ubin/cish" "$B/ubin/authd" "$B/ubin/tiler" > "$B/ubin-cish.log" 2>&1
if python3 -B tests/launch/quote_pty.py "$B/ubin/cish" > "$B/quote-pty.log" 2>&1; then
    line ok "launch: tests/launch/quote_pty.py, a pinned folder's name opens it or nothing ($(grep -c '^ok' "$B/quote-pty.log") checks)"
else
    line bad "launch: tests/launch/quote_pty.py" "see $B/quote-pty.log"
fi
# AC-Tw on a Linux host: a line the record takes as plain, typed into cish ($B/ubin) on a pty, starts the app alone
if python3 -B tests/ac/prompt_record_pty.py "$B/ubin/cish" > "$B/prompt-record.log" 2>&1; then
    line ok "prompt: tests/ac/prompt_record_pty.py, a plain line's first process is the app ($(grep -c '^ok' "$B/prompt-record.log") checks)"
else
    line bad "prompt: tests/ac/prompt_record_pty.py" "see $B/prompt-record.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/acct_test.ci > "$B/acct.log" 2>&1; then
    line ok "hosted: cint test tests/ac/acct_test.ci, the account store of AC-1c ($(tail -1 "$B/acct.log"))"
else
    line bad "hosted: cint test tests/ac/acct_test.ci" "see $B/acct.log"
fi
# FF 3h: the Trash store (user/ci/trash.ci over the real user/ci/trashfs.ci, design note 52's rules) on an in-memory
# volume: tests/hosted/trash's shctl, corectl and dirctl stand in for the externs, with the real calls' contracts
tr=$B/hosted-trash
rm -rf "$tr" && mkdir -p "$tr/user/ci" "$tr/tests"
cp user/ci/trash.ci user/ci/trashfs.ci tests/hosted/trash/memfs.ci tests/hosted/trash/shctl.ci tests/hosted/trash/corectl.ci \
    tests/hosted/trash/dirctl.ci "$tr/user/ci/" && cp tests/hosted/trash/trash_test.ci "$tr/tests/"
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$tr" tests/trash_test.ci > "$B/trash-test.log" 2>&1; then
    line ok "hosted: cint test tests/hosted/trash/trash_test.ci, the Trash store ($(tail -1 "$B/trash-test.log"))"
else
    line bad "hosted: cint test tests/hosted/trash/trash_test.ci" "see $B/trash-test.log"
fi
# FF-1 x FS-4: the desk's index (user/ci/kit/index.ci, its walk user/ci/core/path.ci) on an in-memory volume that
# stamps a folder's time when a name is added, removed or moved in it: the kept table is the walk's after each change
ti=$B/hosted-index
rm -rf "$ti" && mkdir -p "$ti/user/ci/core" "$ti/user/ci/kit" "$ti/src" "$ti/tests"
cp user/ci/kit/index.ci "$ti/user/ci/kit/" && cp user/ci/core/path.ci user/ci/core/msg.ci user/ci/core/put.ci "$ti/user/ci/core/" \
    && cp src/sha256.ci "$ti/src/" && cp tests/hosted/index/memfs.ci tests/hosted/index/corectl.ci \
    tests/hosted/index/shctl.ci tests/hosted/index/dev.ci "$ti/user/ci/" && cp tests/hosted/index/index_test.ci "$ti/tests/"
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$ti" tests/index_test.ci > "$B/index-test.log" 2>&1; then
    line ok "hosted: cint test tests/hosted/index/index_test.ci, the index's folder times ($(tail -1 "$B/index-test.log"))"
else
    line bad "hosted: cint test tests/hosted/index/index_test.ci" "see $B/index-test.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/acctask_test.ci > "$B/acctask.log" 2>&1; then
    line ok "hosted: cint test tests/ac/acctask_test.ci, the Accounts page's requests to authd ($(tail -1 "$B/acctask.log"))"
else
    line bad "hosted: cint test tests/ac/acctask_test.ci" "see $B/acctask.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/acctform_test.ci > "$B/acctform.log" 2>&1; then
    line ok "hosted: cint test tests/ac/acctform_test.ci, frame 49's account forms ($(tail -1 "$B/acctform.log"))"
else
    line bad "hosted: cint test tests/ac/acctform_test.ci" "see $B/acctform.log"
fi
# DN-52, DN-53: frame 12 (kit/acscreen.ci): the rule line is the store's minimum, the words, the layout at three sizes
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/screens_test.ci > "$B/screens.log" 2>&1; then
    line ok "hosted: cint test tests/ac/screens_test.ci, frame 12's login, lock and first boot ($(tail -1 "$B/screens.log"))"
else
    line bad "hosted: cint test tests/ac/screens_test.ci" "see $B/screens.log"
fi
if python3 tools/check-account-store.py --toolchain "$CINT_TOOLCHAIN" --out "$B/account-store" > "$B/account-store.log" 2>&1; then
    line ok "hosted: account-store recovery and read failures ($(tail -1 "$B/account-store.log"))"
else
    line bad "hosted: account-store recovery and read failures" "see $B/account-store.log"
fi
# RS-ROLE (docs/specs/2026-11-11-rs-role.md), RS-R3 and RS-R4 (docs/specs/2026-11-11-rs-accounts-ops.md): authd's
# store operations as they are (authop, acctio, acctput, homeaside, authver, Argon2id at 8 KiB) over a volume in
# memory: the last parent, the approver's own passphrase, two passphrases in one request, the home set aside, write
# failures
if python3 tools/check-authop.py --toolchain "$CINT_TOOLCHAIN" --out "$B/authop" > "$B/authop.log" 2>&1; then
    line ok "hosted: authd's store operations: role, ceiling, remove, add, passwd, the last parent, the home set aside ($(tail -1 "$B/authop.log"))"
else
    line bad "hosted: authd's store operations (tools/check-authop.py)" "see $B/authop.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ac/argon2_test.ci > "$B/argon2.log" 2>&1; then
    line ok "hosted: cint test tests/ac/argon2_test.ci, Argon2id of AC-1b with RFC 9106's vector ($(tail -1 "$B/argon2.log"))"
else
    line bad "hosted: cint test tests/ac/argon2_test.ci" "see $B/argon2.log"
fi
if tests/ac/authd.sh "$B/ubin/authd" > "$B/authd.log" 2>&1; then
    line ok "authd: derive equals tools/ac-vectors.py at 8 KiB, 1 MiB and 4 MiB; enroll, verify and refusals; the store operations over a real directory ($(grep -c '^ok' "$B/authd.log") checks$(grep -q '^skip' "$B/authd.log" && echo ', the directory leg skipped'))"
else
    line bad "authd: tests/ac/authd.sh" "see $B/authd.log"
fi
# Board 20261111T170652Z on a Linux host: those bytes typed into cish ($B/ubin) on a pty, its pid waited on as the desk does
if python3 -B tests/launch/cish_pty.py "$B/ubin/cish" > "$B/launch-pty.log" 2>&1; then
    line ok "launch: cish as the images take it (O/ubin) on a pty runs an exec'd app as its own pid and ends with it; a command's shell outlives it and keeps its output (DN-60); SIGTERM, Ctrl-C, a missing program (127) ($(grep -c '^ok' "$B/launch-pty.log") checks)"
else
    line bad "launch: tests/launch/cish_pty.py" "see $B/launch-pty.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/finder_test.ci > "$B/finder.log" 2>&1; then
    line ok "hosted: cint test tests/ff/finder_test.ci, the Finder app's model of FF-6a ($(tail -1 "$B/finder.log"))"
else
    line bad "hosted: cint test tests/ff/finder_test.ci" "see $B/finder.log"
fi
# DN-55: Index's chrome (kit/indexui.ci): where each control of frames 3 and 4 is, the sidebar's groups, the crumbs that
# fit, the window bar's folder name
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/indexui_test.ci > "$B/indexui.log" 2>&1; then
    line ok "hosted: cint test tests/ff/indexui_test.ci, Index's toolbar, sidebar and status bar of DN-55 ($(tail -1 "$B/indexui.log"))"
else
    line bad "hosted: cint test tests/ff/indexui_test.ci" "see $B/indexui.log"
fi
# DN-55, design note 65: Index's Grid and List (kit/indexbody.ci): columns in any box, cells and rows, the List's
# columns, their header and narrow drops, the scroll
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/ff/indexbody_test.ci > "$B/indexbody.log" 2>&1; then
    line ok "hosted: cint test tests/ff/indexbody_test.ci, Index's Grid and List of DN-55 ($(tail -1 "$B/indexbody.log"))"
else
    line bad "hosted: cint test tests/ff/indexbody_test.ci" "see $B/indexbody.log"
fi
# Frame 32, Index remainder (design notes 52, 58): the kits of lane INDEX KIT (rename in place, Properties, the rubber
# band and drop ring, the Trash view), every tests/ix/*_test.ci; one line for all, so a new kit test moves no count
ix_bad="" ix_n=0
for f in tests/ix/*_test.ci; do
    l="$B/ix-$(basename "$f" .ci).log"
    if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . "$f" > "$l" 2>&1; then
        ix_n=$((ix_n + $(tail -1 "$l" | awk '{print $1}')))
    else
        ix_bad="$ix_bad $f"
    fi
done
if [ -z "$ix_bad" ]; then
    line ok "hosted: cint test tests/ix/*_test.ci, Index's kits of frame 32 ($ix_n tests passed)"
else
    line bad "hosted: cint test tests/ix/*_test.ci" "failed:$ix_bad (logs $B/ix-*.log)"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/tz/tz_test.ci > "$B/tz-test.log" 2>&1; then
    line ok "hosted: cint test tests/tz/tz_test.ci, RS-TZa's names, UTC, the ends and the calendar ($(tail -1 "$B/tz-test.log"))"
else
    line bad "hosted: cint test tests/tz/tz_test.ci" "see $B/tz-test.log"
fi
if cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/tz/tz_twin.ci > "$B/tz-twin.out" 2> "$B/tz-twin.log" \
    && python3 tools/check-tz.py "$B/tz-twin.out" >> "$B/tz-twin.log" 2>&1; then
    line ok "hosted: tests/tz/tz_twin.ci against zdump, 2026 to 2027 line for line and 1970 to 2037 by SHA-256 (tools/check-tz.py)"
else
    line bad "hosted: tests/tz/tz_twin.ci against tools/check-tz.py" "see $B/tz-twin.log"
fi
# U-PNG (docs/specs/2026-11-11-u-png.md): the PNG writer, user/ci/core/deflate.ci and png.ci, round trips through
# inflate.ci and img.ci, then read by an independent reader (the host's zlib, a strict PNG reader, Pillow if present)
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/png/png_test.ci > "$B/png-test.log" 2>&1; then
    line ok "hosted: cint test tests/png/png_test.ci, the PNG writer of U-PNG through inflate.ci and img.ci ($(tail -1 "$B/png-test.log"))"
else
    line bad "hosted: cint test tests/png/png_test.ci" "see $B/png-test.log"
fi
if cint run --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/png/png_twin.ci > "$B/png-twin.out" 2> "$B/png-twin.log" \
    && python3 tools/check-png.py "$B/png-twin.out" >> "$B/png-twin.log" 2>&1; then
    line ok "hosted: tests/png/png_twin.ci's streams and files read back by tools/check-png.py ($(tail -1 "$B/png-twin.log"))"
else
    line bad "hosted: tests/png/png_twin.ci against tools/check-png.py" "see $B/png-twin.log"
fi
# U-SET (docs/specs/2026-11-11-u-set.md): an account's settings, user/ci/kit/settings.ci (pure) and setfile.ci (the
# file, over the volume in memory of tests/set/fs_shctl.ci in an isolated root), hosted
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/set/settings_test.ci > "$B/settings.log" 2>&1; then
    line ok "hosted: cint test tests/set/settings_test.ci, the settings store of U-SET ($(tail -1 "$B/settings.log"))"
else
    line bad "hosted: cint test tests/set/settings_test.ci" "see $B/settings.log"
fi
if python3 tools/check-settings.py --toolchain "$CINT_TOOLCHAIN" --out "$B/settings-file" > "$B/settings-file.log" 2>&1; then
    line ok "hosted: the settings file of U-SET, its folders, rename and failures ($(tail -1 "$B/settings-file.log"))"
else
    line bad "hosted: tools/check-settings.py, the settings file of U-SET" "see $B/settings-file.log"
fi
# RS-SHOT (docs/specs/2026-11-11-rs-rel-s1-units.md): the area select and the picture plate (kit/shotsel.ci); the
# desk's rows of host.c (fb_hold, fb_peek, shot_as, shot_end) with each compiler, every child refused at its login on
# the host; user/ci/shot.ci built for the host and run as the desk's child runs it, each picture read back as PNG
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/shot/shotsel_test.ci \
        > "$B/shotsel.log" 2>&1; then
    line ok "hosted: cint test tests/shot/shotsel_test.ci, RS-SHOT's area select and plate ($(tail -1 "$B/shotsel.log"))"
else
    line bad "hosted: cint test tests/shot/shotsel_test.ci" "see $B/shotsel.log"
fi
for cc in gcc clang; do
    if $cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$CINT_INC" -Iuser/ci tests/shot/rows_test.c -o "$B/shot-rows-$cc" \
            > "$B/shot-rows-$cc.log" 2>&1 && "$B/shot-rows-$cc" >> "$B/shot-rows-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/shot/rows_test.c, the desk's shot rows ($(tail -1 "$B/shot-rows-$cc.log"))"
    else
        line bad "hosted: $cc tests/shot/rows_test.c" "see $B/shot-rows-$cc.log"
    fi
done
# RS-SURF: host.c's window rows against a desk that lays the window out before the open returns; a win_resize asked
# before fb_open reaches the first box, and View, Index and Monitor ask it there (tests/rs/surfopen_test.c)
for cc in gcc clang; do
    if $cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$CINT_INC" -Iuser/ci tests/rs/surfopen_test.c -o "$B/surfopen-$cc" \
            > "$B/surfopen-$cc.log" 2>&1 && "$B/surfopen-$cc" >> "$B/surfopen-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/rs/surfopen_test.c, RS-SURF's first box ($(tail -1 "$B/surfopen-$cc.log"))"
    else
        line bad "hosted: $cc tests/rs/surfopen_test.c" "see $B/surfopen-$cc.log"
    fi
done
# RS-TTL section 6: host.c's win_var row passes a name's first 64 bytes (src/tile.ci VAR_LEN), where a name past its
# buffer was dropped whole and View's bar showed no screenshot's name (tests/rs/winvar_test.c)
for cc in gcc clang; do
    if $cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$CINT_INC" -Iuser/ci tests/rs/winvar_test.c -o "$B/winvar-$cc" \
            > "$B/winvar-$cc.log" 2>&1 && "$B/winvar-$cc" >> "$B/winvar-$cc.log" 2>&1; then
        line ok "hosted: $cc tests/rs/winvar_test.c, a bar name past 32 bytes ($(tail -1 "$B/winvar-$cc.log"))"
    else
        line bad "hosted: $cc tests/rs/winvar_test.c" "see $B/winvar-$cc.log"
    fi
done
# BG-1: bgread, the account's background picture read and fitted as the account, built for the host and run on
# pictures tests/bg/bgread_run.py makes (a crop, a cover, alpha dropped, the exact stream; a link, a FIFO, a directory,
# a file that is not PNG and an empty one refused; the usages)
if CI_CC=gcc CI_OUT="$B/bgread-bin" user/ci/build.sh bgread > "$B/bgread-build.log" 2>&1 \
    && python3 tests/bg/bgread_run.py "$B/bgread-bin/bgread" > "$B/bgread-run.log" 2>&1; then
    line ok "hosted: user/ci/bgread.ci for the host, run by tests/bg/bgread_run.py ($(tail -1 "$B/bgread-run.log"))"
else
    line bad "hosted: user/ci/bgread.ci against tests/bg/bgread_run.py" "see $B/bgread-build.log and $B/bgread-run.log"
fi
# RG-1: setkey --print, the account's settings as the desk's run as the account reads them (runas.h RUN_PREFS: the desk
# cannot open a 0700 home), built for the host and run by tests/rg/setkey_run.py
if CI_CC=gcc CI_OUT="$B/setkey-bin" user/ci/build.sh setkey > "$B/setkey-build.log" 2>&1 \
    && python3 tests/rg/setkey_run.py "$B/setkey-bin/setkey" > "$B/setkey-run.log" 2>&1; then
    line ok "hosted: user/ci/setkey.ci --print for the host, run by tests/rg/setkey_run.py ($(tail -1 "$B/setkey-run.log"))"
else
    line bad "hosted: user/ci/setkey.ci against tests/rg/setkey_run.py" "see $B/setkey-build.log and $B/setkey-run.log"
fi
if CI_CC=gcc CI_OUT="$B/shot-bin" user/ci/build.sh shot > "$B/shot-build.log" 2>&1 \
    && python3 tests/shot/shot_run.py "$B/shot-bin/shot" > "$B/shot-run.log" 2>&1; then
    line ok "hosted: user/ci/shot.ci for the host, run by tests/shot/shot_run.py ($(tail -1 "$B/shot-run.log"))"
else
    line bad "hosted: user/ci/shot.ci against tests/shot/shot_run.py" "see $B/shot-build.log and $B/shot-run.log"
fi

# KP-1: the state pool check (tools/check-state-pool.py) on images made here with the pinned cint_rt.h: a fit, an exact
# fit, a block over, a byte that takes a block, no pool, no symbol table
if python3 -B tests/kp/run.py --inc "$inc" --out "$B/kp" > "$B/kp.log" 2>&1; then
    line ok "KP-1: the state pool check reads cint_state as gcc and clang lay it out ($(tail -1 "$B/kp.log"))"
else
    line bad "KP-1: tests/kp/run.py" "see $B/kp.log"
fi
# 2. build
if make -s -j"$(nproc)" O="$B" > "$B/build.log" 2>&1; then
    line ok "build: gcc and clang, flavors $FL (make)"
else
    line bad "build: make" "see $B/build.log"; tail -20 "$B/build.log"; echo "RESULT: FAIL"; exit 1
fi
# KP-1: a flavor whose module state passes its pool is not built: the mem flavor, with a pool 16 bytes under what the
# build above measured for it, fails make, says by how much and leaves no image
kp_need=$(sed -n 's/.* modules need \([0-9]*\) of .*/\1/p' "$B/gcc-mem/state-pool.txt" 2>/dev/null)
kp_pool=$((${kp_need:-0} - 16))
if [ "$kp_pool" -lt 16 ]; then
    line bad "KP-1: a short pool" "no state count for the mem flavor in $B/gcc-mem/state-pool.txt"
elif make -s O="$B/kp-short" COMPILERS=gcc FLAVORS=mem RTDEF_mem="-DRT_STATE_POOL_BYTES=${kp_pool}u" \
    > "$B/kp-short.log" 2>&1; then
    line bad "KP-1: a short pool" "make built the mem flavor with a pool of $kp_pool bytes, see $B/kp-short.log"
elif grep -q "need $kp_need bytes, the pool is $kp_pool: 16 bytes over" "$B/kp-short.log" \
    && [ ! -e "$B/kp-short/gcc-mem/kernel.elf" ]; then
    line ok "KP-1: make refuses the mem flavor with a state pool 16 bytes short ($kp_pool for $kp_need): no image"
else
    line bad "KP-1: a short pool" "make failed for another reason or left an image, see $B/kp-short.log"
fi
for cc in gcc clang; do
    want=$([ $cc = gcc ] && echo 'GCC: ' || echo 'clang version')
    ok=1
    for o in "$B/$cc-k1"/obj/em_*.o "$B/$cc-k1"/obj/rt_*.o; do
        readelf -p .comment "$o" 2>/dev/null | grep -q "$want" || ok=0
    done
    [ $ok = 1 ] && line ok "build: every $cc-k1 object was compiled by $cc (.comment names it)" \
                || line bad "build: $cc-k1 objects" ".comment does not name $cc"
done
[ "$(sha256sum < "$B/gcc-k1/kernel.elf")" != "$(sha256sum < "$B/clang-k1/kernel.elf")" ] \
    && line ok "build: the gcc and clang images differ (two different compilers built them)" \
    || line bad "build: gcc and clang images" "identical"
echo "image sha256:"
for cc in gcc clang; do for fl in $FL; do
    echo "  $cc-$fl  $(sha256sum "$B/$cc-$fl/kernel.elf" | cut -d' ' -f1)"
done; done
if make -s -j"$(nproc)" O="$B/rebuild" > "$B/rebuild.log" 2>&1; then
    same=1
    for cc in gcc clang; do for fl in $FL; do
        cmp -s "$B/$cc-$fl/kernel.elf" "$B/rebuild/$cc-$fl/kernel.elf" || same=0
    done; done
    [ $same = 1 ] && line ok "build: a second build in another directory gives byte-identical images" \
                  || line bad "build: reproducibility" "images differ between two builds"
else
    line bad "build: second build" "see $B/rebuild.log"
fi

# 3. K0 symbol audit
tools/audit-symbols.sh "$B" "gcc clang" "$FL" > "$B/audit.log" 2>&1
audit_rc=$?
cat "$B/audit.log"
[ "$(grep -c '^PASS' "$B/audit.log")" = "$audit_want" ] && [ "$audit_rc" = 0 ] && ! grep -q '^FAIL' "$B/audit.log" \
    && line ok "K0: symbol audit ran and passed ($audit_want checks, 5 per build, gcc and clang, flavors $FL)" \
    || line bad "K0: symbol audit" "exit $audit_rc, $(grep -c '^PASS' "$B/audit.log") PASS lines of $audit_want expected"

# 4. boot
mkdir -p "$B/run" "$B/k5"
# K5 images take a run descriptor (a blob QEMU's loader puts at 40 MiB: record, quantum 250, network 0) and
# the scripted keys on the serial port (docs/snapshot.md)
python3 tools/k5blob.py desc "$B/k5/boot.blob" 1 250 0
cp tests/k5/script.txt "$B/k5/boot.in"
MOUSE="mouse_move 10 -5,mouse_button 1,mouse_button 0,mouse_button 2,mouse_button 0"   # F-3: a move, a left click, a right click (QEMU: 1 left, 2 right, 4 middle)
boot_run() { # flavor image transcript
    local extra="" stdin=/dev/null initrd="" mon="" typer="" watchdog=30
    [ "$1" = k5 ] && { extra="-device loader,file=$B/k5/boot.blob,addr=0x6000000,force-raw=on"; stdin="$B/k5/boot.in"; }
    [ "$1" = user ] && { stdin=tests/image/stdin.txt; initrd=$B/user/initrd.cpio; watchdog=60; }   # U1-3: the serial line as stdin, ends with 0x04; U1-5: the image as a module
    if [ "$1" = user ]; then   # F-2: a, b, c typed through the monitor once each mkeys run line shows
        mon=$3.mon
        [ ${#mon} -le 100 ] || fail_exit "monitor socket path $mon is ${#mon} bytes; a unix socket path holds 107, so set a shorter DAPHNIS_BUILD"
        python3 tools/sendkeys.py "$mon" "$3" "daphnis: run mkeys pid 38 (device)" a,b,c "daphnis: run mkeys pid 39 (device)" a,b,c \
            "daphnis: run mmouse pid 40 (device)" "$MOUSE" "daphnis: run mmouse pid 41 (device)" "$MOUSE" > "$3.keys" 2>&1 &
        typer=$!
    fi
    QEMU_TIMEOUT=$watchdog QEMU_EXTRA="$extra" STDIN_FILE="$stdin" INITRD="$initrd" MONITOR="$mon" MEM="${BOOT_MEM:-128}" POOL="${BOOT_POOL:-}" tools/run-qemu.sh "$2" "$3"   # M-3: the pool check boots at -m 512 with daphnis.pool=max
    [ -n "$typer" ] && wait "$typer"
    return 0
}
want_hello=33 want_k1=33 want_fault=35 want_trap=33 want_stackover=33 want_nullptr=33 want_faults=33 want_mem=33 want_coop=33 want_preempt=33 want_shep=33 want_k5=33 want_user=33   # isa-debug-exit value v gives (v << 1) | 1: 0x10 -> 33, 0x11 -> 35
for cc in gcc clang; do for fl in $FL; do for n in 1 2; do
    t=$B/run/$cc-$fl.$n.txt
    boot_run $fl "$B/$cc-$fl/kernel32.elf" "$t" > "$t.rc"   # every flavor boots with -m 128M (G-0)
done; done; done
for cc in gcc clang; do for fl in $FL; do
    eval want=\$want_$fl
    ok=1; for n in 1 2; do [ "$(cat "$B/run/$cc-$fl.$n.txt.rc")" = "$want" ] || ok=0; done
    [ $ok = 1 ] && line ok "boot $cc-$fl: QEMU exit status $want on both runs" \
                || line bad "boot $cc-$fl: QEMU exit status $want" "got $(cat "$B/run/$cc-$fl.1.txt.rc") and $(cat "$B/run/$cc-$fl.2.txt.rc")"
    [ ! -s "$B/run/$cc-$fl.1.txt.err" ] && [ ! -s "$B/run/$cc-$fl.2.txt.err" ] \
        && line ok "boot $cc-$fl: QEMU wrote nothing to stderr" || line bad "boot $cc-$fl: QEMU stderr" "not empty"
done; done
echo "transcript sha256:"
for cc in gcc clang; do for fl in $FL; do for n in 1 2; do
    echo "  $cc-$fl run $n  $(sha256sum "$B/run/$cc-$fl.$n.txt" | cut -d' ' -f1)"
done; done; done
for fl in $FL; do
    cmp -s "$B/run/gcc-$fl.1.txt" "$B/run/clang-$fl.1.txt" \
        && line ok "serial $fl: gcc and clang transcripts byte-identical (cmp)" \
        || line bad "serial $fl: gcc vs clang (cmp)" "differ"
    for cc in gcc clang; do
        cmp -s "$B/run/$cc-$fl.1.txt" "$B/run/$cc-$fl.2.txt" \
            && line ok "serial $fl: $cc run 1 and run 2 byte-identical (cmp)" \
            || line bad "serial $fl: $cc run 1 vs run 2 (cmp)" "differ"
    done
done
vec='sha256("abc") = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
for cc in gcc clang; do
    cmp -s tests/expected/hello.serial "$B/run/$cc-hello.1.txt" \
        && line ok "serial hello: $cc transcript equals tests/expected/hello.serial" \
        || line bad "serial hello: $cc vs tests/expected/hello.serial" "differ"
    grep -qxF "$vec" "$B/run/$cc-k1.1.txt" \
        && line ok "sha256: $cc kernel prints the FIPS 180-4 vector for \"abc\"" \
        || line bad "sha256: $cc kernel line" "vector line absent"
    cmp -s tests/expected/k1.serial "$B/run/$cc-k1.1.txt" \
        && line ok "serial k1: $cc transcript equals tests/expected/k1.serial" \
        || line bad "serial k1: $cc vs tests/expected/k1.serial" "differ"
    head -n 2 "$B/run/$cc-fault.1.txt" | cmp -s - tests/expected/fault.head \
        && line ok "serial fault: $cc banner and record header equal tests/expected/fault.head" \
        || line bad "serial fault: $cc vs tests/expected/fault.head" "differ"
done

# 4b. the ISO leg: hello (here) and mem (block 5d) through GRUB (Multiboot 2, tools/build-iso.sh), on a
# machine that has the tools
if command -v grub-mkrescue >/dev/null && command -v xorriso >/dev/null; then
    iso_ran=1
    make -s O="$B" hello "$B/gcc-mem/daphnis.iso" "$B/clang-mem/daphnis.iso" > "$B/iso.log" 2>&1 \
        && [ -f "$B/gcc-hello/daphnis.iso" ] && [ -f "$B/clang-hello/daphnis.iso" ] && [ -f "$B/gcc-mem/daphnis.iso" ] && [ -f "$B/clang-mem/daphnis.iso" ] \
        && line ok "iso: make built daphnis.iso of hello and mem for gcc and clang (grub-mkrescue, xorriso)" \
        || line bad "iso: make hello" "see $B/iso.log"
    for cc in gcc clang; do
        rc=$(tools/run-qemu.sh "$B/$cc-hello/daphnis.iso" "$B/run/$cc-hello-iso.txt")
        [ "$rc" = "$want_hello" ] && [ ! -s "$B/run/$cc-hello-iso.txt.err" ] && cmp -s tests/expected/hello.serial "$B/run/$cc-hello-iso.txt" \
            && line ok "boot iso $cc-hello: GRUB, Multiboot 2, QEMU exit status $want_hello, nothing on stderr, transcript equals tests/expected/hello.serial" \
            || line bad "boot iso $cc-hello" "status $rc, or stderr not empty, or the transcript differs from tests/expected/hello.serial"
    done
else
    iso_ran=0
    skip "iso: grub-mkrescue and xorriso are not both on PATH; the Multiboot 2 (GRUB) boots of hello and mem did not run"
fi

# HW-1: hello and user through UEFI, ISO and ESP, gcc and clang. Firmware output is kept
# separately under ruling A (board 20261108T193709Z); every kernel byte still equals the golden.
ovmf_ran=0
ovmf_missing=""
for t in grub-mkrescue grub-mkstandalone xorriso mformat mmd mcopy; do
    command -v "$t" >/dev/null || ovmf_missing="${ovmf_missing:+$ovmf_missing, }$t"
done
[ -d /usr/lib/grub/x86_64-efi ] || ovmf_missing="${ovmf_missing:+$ovmf_missing, }GRUB x86_64-efi modules"
if [ -z "${OVMF:-}" ]; then
    for fw in /usr/share/edk2/x64/OVMF.4m.fd /usr/share/ovmf/OVMF.fd /usr/share/OVMF/OVMF.fd; do
        [ ! -f "$fw" ] || { OVMF=$fw; break; }
    done
elif [ ! -f "$OVMF" ]; then
    fail_exit "explicit OVMF=$OVMF does not exist"
fi
[ -f "${OVMF:-}" ] || ovmf_missing="${ovmf_missing:+$ovmf_missing, }edk2-ovmf (Arch) or ovmf (Ubuntu)"
if [ -z "$ovmf_missing" ]; then
    ovmf_ran=1
    OVMF="$OVMF" TMPDIR="$B" bash tools/check-ovmf.sh "$B" > "$B/ovmf.log" 2>&1
    ovmf_rc=$?
    cat "$B/ovmf.log"
    passes=$((passes + $(grep -c '^PASS' "$B/ovmf.log")))
    if [ "$ovmf_rc" != 0 ] || [ "$(grep -c '^PASS' "$B/ovmf.log")" != "$ovmf_pass" ] || grep -q '^FAIL' "$B/ovmf.log"; then
        fail_exit "OVMF leg failed; stop before later units (see $B/ovmf.log)"
    fi
else
    skip "ovmf: missing $ovmf_missing; UEFI ISO/ESP hello/user boots did not run"
fi

# 4c. N-1 (docs/specs/2026-11-05-n-net.md): the net flavor replays the committed journal on both compilers, no
# device attached; its live legs and the rest of stage N's checks are check-net.sh's
python3 tools/mkcpio.py "$B/net.cpio" net.journal=tests/net/n1.journal
ok=1
make -s O="$B" FLAVORS=net > "$B/net.log" 2>&1 || ok=0
for cc in gcc clang; do
    [ $ok = 1 ] && [ "$(INITRD=$B/net.cpio tools/run-qemu.sh "$B/$cc-net/kernel32.elf" "$B/run/$cc-net.txt")" = 33 ] \
        && [ ! -s "$B/run/$cc-net.txt.err" ] && cmp -s tests/expected/net.serial "$B/run/$cc-net.txt" || ok=0
done
[ $ok = 1 ] && line ok "net: the gcc and clang net flavors replay tests/net/n1.journal to tests/expected/net.serial" \
            || line bad "net: replay of tests/net/n1.journal" "see $B/net.log and $B/run/*-net.txt"

# 5. K2: traps and timer (the trap flavor)
for cc in gcc clang; do
    # record hex lines carry the program revision, which changes with any source change: mask them
    sed -E 's/^[0-9a-f]{64,}$/HEX/' "$B/run/$cc-trap.1.txt" | cmp -s - tests/expected/trap.skeleton \
        && line ok "serial trap: $cc transcript equals tests/expected/trap.skeleton (record hex masked)" \
        || line bad "serial trap: $cc vs tests/expected/trap.skeleton" "differ"
    python3 tools/check-trap.py "$B/run/$cc-trap.1.txt" "$B/emit-trap/c/cint-program.c" > "$B/trap-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/trap-$cc.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/trap-$cc.cmp")" = 26 ] && ! grep -q '^FAIL' "$B/trap-$cc.cmp" \
        && line ok "trap $cc: #DE, #UD and #PF records printed from cint decode as expected; PIT ticks counted (26 checks)" \
        || line bad "trap $cc: records or ticks" "see $B/trap-$cc.cmp"
done

# 5b. K3 hardening: records of the stackover and nullptr flavors, decoded against a table
for fl in stackover nullptr; do
    for cc in gcc clang; do
        sed -E 's/^[0-9a-f]{64,}$/HEX/' "$B/run/$cc-$fl.1.txt" | cmp -s - "tests/expected/$fl.skeleton" \
            && line ok "serial $fl: $cc transcript equals tests/expected/$fl.skeleton (record hex masked)" \
            || line bad "serial $fl: $cc vs tests/expected/$fl.skeleton" "differ"
        python3 tools/check-records.py $fl "$B/run/$cc-$fl.1.txt" "$B/emit-$fl/c/cint-program.c" > "$B/$fl-$cc.cmp" 2>&1
        sed "s/^/  [$cc] /" "$B/$fl-$cc.cmp" | grep -v PASS || true
        [ "$(grep -c '^PASS' "$B/$fl-$cc.cmp")" = "$(sed -n "s/^$fl=//p" tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/$fl-$cc.cmp" \
            && line ok "$fl $cc: records decode and match the table ($(grep -c '^PASS' "$B/$fl-$cc.cmp") checks)" \
            || line bad "$fl $cc: records" "see $B/$fl-$cc.cmp"
    done
done

# 5c. K3 fault writers: the faults flavor against the hosted runtime, probe by probe
mkdir -p "$B/faults-twin"
cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . --out "$B/faults-twin" src/main_faults.ci > "$B/faults-twin.log" 2>&1
for i in 0 1 2 3 4 5 6 7 8 9; do
    timeout 20 "$B/faults-twin/main_faults" "$B/faults-twin/rec$i.bin" --arg $i > /dev/null 2>&1
done
[ "$(ls "$B"/faults-twin/rec*.bin 2>/dev/null | wc -l)" = 10 ] && [ -z "$(find "$B"/faults-twin -name 'rec*.bin' -size 0)" ] \
    && line ok "faults: the hosted runtime wrote a record for each of probes 0 to 9" || line bad "faults: hosted twin" "records missing; see $B/faults-twin.log"
for cc in gcc clang; do
    python3 tools/compare-faults.py "$B/run/$cc-faults.1.txt" "$B/faults-twin" "$B/emit-faults/c/cint-program.c" > "$B/faults-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/faults-$cc.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/faults-$cc.cmp")" = "$(sed -n 's/^faults=//p' tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/faults-$cc.cmp" \
        && line ok "faults $cc: 11 probes, 10 records byte-identical to the hosted runtime's, table and positions ($(grep -c '^PASS' "$B/faults-$cc.cmp") checks)" \
        || line bad "faults $cc: records" "see $B/faults-$cc.cmp"
    sed -E 's/^[0-9a-f]{64,}$/HEX/' "$B/run/$cc-faults.1.txt" | cmp -s - tests/expected/faults.skeleton \
        && line ok "serial faults: $cc transcript equals tests/expected/faults.skeleton (record hex masked)" \
        || line bad "serial faults: $cc vs tests/expected/faults.skeleton" "differ"
done
cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/fuel_twin.ci > "$B/fuel-twin.log" 2>&1
fl=$(grep -n 'while (true) {' src/probes.ci | head -1 | cut -d: -f1)
if grep -q "^fault\[E_FUEL\]" "$B/fuel-twin.log" && grep -q -- "--> src/probes.ci:$fl:5\$" "$B/fuel-twin.log" \
    && grep -q 'operation: fuel.charge' "$B/fuel-twin.log" && grep -q 'operand-count: 0' "$B/fuel-twin.log" \
    && grep -q 'exact:   none' "$B/fuel-twin.log" && grep -q 'limit:   I64 1000000000' "$B/fuel-twin.log"; then
    line ok "faults: the hosted fuel fault has the kernel's shape (E_FUEL, fuel.charge, no operands, no exact, at src/probes.ci:$fl:5)"
else
    line bad "faults: hosted fuel twin" "see $B/fuel-twin.log"
fi

# 5d. K3 memory: the mem flavor (boots with -m 128M, as every flavor), its checker, and the hosted allocator twin
for cc in gcc clang; do
    sed -E 's/^[0-9a-f]{64,}$/HEX/' "$B/run/$cc-mem.1.txt" | cmp -s - tests/expected/mem.skeleton \
        && line ok "serial mem: $cc transcript equals tests/expected/mem.skeleton (record hex masked)" \
        || line bad "serial mem: $cc vs tests/expected/mem.skeleton" "differ"
    python3 tools/check-mem.py "$B/run/$cc-mem.1.txt" "$B/emit-mem/c/cint-program.c" > "$B/mem-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/mem-$cc.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/mem-$cc.cmp")" = "$(sed -n 's/^mem=//p' tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/mem-$cc.cmp" \
        && line ok "mem $cc: bad addresses, #PF records, refusals and hashes check out ($(grep -c '^PASS' "$B/mem-$cc.cmp") checks)" \
        || line bad "mem $cc: checks" "see $B/mem-$cc.cmp"
done
# under GRUB (Multiboot 2, the ISO leg of block 4b): the memory map comes from the tags of the block rt/boot.c
# copied, and the transcript is the same skeleton
if [ "$iso_ran" = 1 ]; then
    for cc in gcc clang; do
        rc=$(MEM=128 tools/run-qemu.sh "$B/$cc-mem/daphnis.iso" "$B/run/$cc-mem-iso.txt")
        sed -E 's/^[0-9a-f]{64,}$/HEX/' "$B/run/$cc-mem-iso.txt" | cmp -s - tests/expected/mem.skeleton && [ "$rc" = 33 ] \
            && line ok "serial mem iso: $cc, GRUB, Multiboot 2, -m 128: status 33, transcript equals tests/expected/mem.skeleton (record hex masked)" \
            || line bad "serial mem iso: $cc vs tests/expected/mem.skeleton" "status $rc, or the transcript differs"
    done
fi
# the summary follows the machine: the same image at -m 64 differs from the golden in the ram line and the pool
# line only (the pool, 32 to 96 MiB since G-0, is not all RAM at 64 MiB; the run takes only its first frames)
for cc in gcc clang; do
    rc64=$(MEM=64 tools/run-qemu.sh "$B/$cc-mem/kernel32.elf" "$B/run/$cc-mem64.txt")
    sed -E 's/^[0-9a-f]{64,}$/HEX/; s/^ram: MiB 64$/ram: MiB 128/; s/^(pool 32 MiB to 96 MiB usable: )no$/\1yes/' "$B/run/$cc-mem64.txt" | cmp -s - tests/expected/mem.skeleton \
        && grep -qx 'ram: MiB 64' "$B/run/$cc-mem64.txt" && grep -qx 'pool 32 MiB to 96 MiB usable: no' "$B/run/$cc-mem64.txt" && [ "$rc64" = 33 ] \
        && line ok "mem $cc: booted with -m 64 the summary says 'ram: MiB 64', the pool is not all usable, and nothing else changes" \
        || line bad "mem $cc: -m 64" "the summary does not follow the machine (status $rc64)"
done
mkdir -p "$B/mem-twin"
cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hr" --out "$B/mem-twin" tests/mem_twin.ci > "$B/mem-twin.log" 2>&1
mem_hashes=$(grep '^hash ' "$B/run/gcc-mem.1.txt" | awk '{print $NF}' | tr -d '\n')
if [ "${#mem_hashes}" = 384 ] && [ "$("$B/mem-twin/mem_twin" "$B/mem-twin/record.bin" --arg "$mem_hashes" 2>/dev/null)" = match ]; then
    line ok "mem: the hosted runtime, running src/allocdemo.ci, reproduces all six allocator-state hashes of the kernel"
else
    line bad "mem: hosted allocator twin" "its hashes differ from the kernel's, or it did not run; see $B/mem-twin.log"
fi
if [ "$("$B/mem-twin/mem_twin" "$B/mem-twin/record.bin" --arg "${mem_hashes:0:383}0" 2>/dev/null)" != match ]; then
    line ok "mem: the twin refuses a hash that differs in one digit (it can fail)"
else
    line bad "mem: hosted allocator twin" "accepted a wrong hash"
fi

# 5e. K4: tasks. The coop and preempt transcripts equal their goldens exactly (the schedule of
# the cooperative one is in it; the preemptive one holds only what does not depend on timing),
# the service block is the one the hosted twin runs, and the hosted runtime, run with the same
# grants, writes the very lines the kernel's tasks wrote, the denied one included.
for fl in coop preempt; do
    for cc in gcc clang; do
        cmp -s "tests/expected/$fl.serial" "$B/run/$cc-$fl.1.txt" \
            && line ok "serial $fl: $cc transcript equals tests/expected/$fl.serial" \
            || line bad "serial $fl: $cc vs tests/expected/$fl.serial" "differ"
    done
done
blk() { sed -n '/^\/\/ BEGIN service block/,/^\/\/ END service block/p' "$1"; }
[ -n "$(blk src/main_tasks.ci)" ] && [ "$(blk src/main_tasks.ci)" = "$(blk tests/task_twin.ci)" ] \
    && line ok "tasks: the service block of src/main_tasks.ci is byte-identical to the hosted twin's" \
    || line bad "tasks: service block" "src/main_tasks.ci and tests/task_twin.ci differ between the markers"
mkdir -p "$B/task-twin"
cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . --out "$B/task-twin" tests/task_twin.ci > "$B/task-twin.log" 2>&1
for pair in "coop 6" "preempt 400"; do
    set -- $pair
    rounds=${pair#* }
    exp=$( (for t in "1:console.input" "2:console.raw" "3:console.input console.raw"; do
        me=${t%%:*}; set -- ${t#*:}; gr=()
        for g in "$@"; do gr+=(--grant "$g"); done
        printf 'daphnis\n' | "$B/task-twin/task_twin" "$B/task-twin/record.bin" "${gr[@]}" --arg "$me" --arg "$rounds" 2>/dev/null
    done) )
    fl=${pair% *}
    for cc in gcc clang; do
        got=$(grep '^task ' "$B/run/$cc-$fl.1.txt")
        [ -n "$got" ] && [ "$got" = "$exp" ] && [ "$(echo "$got" | wc -l)" = 3 ] && echo "$got" | grep -q 'task 2 total [0-9]* read -1 raw 0$' \
            && line ok "tasks $fl $cc: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0" \
            || line bad "tasks $fl $cc: task lines vs the hosted twin" "kernel: $(echo $got | tr '\n' '|') hosted: $(echo $exp | tr '\n' '|')"
    done
done

# 5f. K4.5: the shepherd. Network 0 gives one root under 7 fuel quanta, the root the hosted
# runtime computes with no scheduler; the schedule digests differ (the runs interleaved
# differently); the control network, which breaks the receive rule, does not give one root; a
# deadlock is named and a channel misuse is a fault record. The transcript is the same bytes on
# gcc and clang at -O0, -O1, -O2, -O3 and -Os: a turn ends at a fuel count, and cint charges
# fuel by its semantics, not by machine instructions.
mkdir -p "$B/shep-twin"
cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . --out "$B/shep-twin" tests/shep_twin.ci > "$B/shep-twin.log" 2>&1
twin_root=$("$B/shep-twin/shep_twin" "$B/shep-twin/record.bin" 2>/dev/null)
[ "${#twin_root}" = 64 ] && line ok "shep: the hosted twin ran the network with no scheduler and wrote its root ($twin_root)" \
    || line bad "shep: hosted twin" "no root; see $B/shep-twin.log"
for cc in gcc clang; do
    sed -E 's/^[0-9a-f]{64,}$/HEX/; s/^probe record: [0-9a-f]+$/probe record: HEX/' "$B/run/$cc-shep.1.txt" | cmp -s - tests/expected/shep.skeleton \
        && line ok "serial shep: $cc transcript equals tests/expected/shep.skeleton (record hex masked)" \
        || line bad "serial shep: $cc vs tests/expected/shep.skeleton" "differ"
    python3 tools/check-shep.py "$B/run/$cc-shep.1.txt" "$twin_root" > "$B/shep-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/shep-$cc.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/shep-$cc.cmp")" = "$(sed -n 's/^shep=//p' tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/shep-$cc.cmp" \
        && line ok "shep $cc: one root under 7 schedules (the twin's), digests differ, control splits, deadlock and fault as expected" \
        || line bad "shep $cc: network checks" "see $B/shep-$cc.cmp"
done
[ "$(grep -rl 'cint_rt_state' "$B/emit-shep/c" | sed "s|$B/emit-shep/c/||")" = src/ownstate.c ] \
    && line ok "shep: only src/ownstate.c (the module-state test) asks for module state; the network's modules ask for none" \
    || line bad "shep: module state" "files that call cint_rt_state: $(grep -rl 'cint_rt_state' "$B/emit-shep/c" | tr '\n' ' ')"
for o in O0 O1 O3 Os; do
    (make -s O="$B/opt-$o" OPT=-$o FLAVORS=shep > "$B/opt-$o.log" 2>&1 \
        && for cc in gcc clang; do tools/run-qemu.sh "$B/opt-$o/$cc-shep/kernel32.elf" "$B/opt-$o/$cc.txt" > "$B/opt-$o/$cc.rc"; done) &
done
wait
for o in O0 O1 O3 Os; do
    for cc in gcc clang; do
        [ "$(cat "$B/opt-$o/$cc.rc" 2>/dev/null)" = 33 ] && cmp -s "$B/run/gcc-shep.1.txt" "$B/opt-$o/$cc.txt" \
            && line ok "shep -$o $cc: boots (status 33) and the transcript equals the -O2 one byte for byte" \
            || line bad "shep -$o $cc" "status $(cat "$B/opt-$o/$cc.rc" 2>/dev/null), or the transcript differs from -O2; see $B/opt-$o.log"
    done
done

# 5g. K5: tasks as step functions, a journal, a state tree (docs/snapshot.md). Network 0 is racy on
# purpose (a sink selects between a producer and an editor), so recordings under different fuel quanta
# differ; the journal makes every one of them replay exactly, on the other compiler, at another -O
# level and under another quantum, with the same final root. Everything Python can recompute it does.
K5SCRIPT=tests/k5/script.txt
k5run() { # image blob transcript [stdin]: prints QEMU's status
    QEMU_EXTRA="-device loader,file=$2,addr=0x6000000,force-raw=on" STDIN_FILE="${4:-/dev/null}" tools/run-qemu.sh "$1" "$3"
}
K5Q="0 1 100 250 2000"
make -s O="$B/opt-k5-O0" OPT=-O0 FLAVORS=k5 > "$B/opt-k5-O0.log" 2>&1 &
for q in $K5Q; do
    python3 tools/k5blob.py desc "$B/k5/rec-$q.blob" 1 $q 0
    for cc in gcc clang; do k5run "$B/$cc-k5/kernel32.elf" "$B/k5/rec-$q.blob" "$B/k5/rec-$cc-$q.txt" "$K5SCRIPT" > "$B/k5/rec-$cc-$q.rc"; done
done
wait
roots=""
for q in $K5Q; do
    cmp -s "$B/k5/rec-gcc-$q.txt" "$B/k5/rec-clang-$q.txt" && [ "$(cat "$B/k5/rec-gcc-$q.rc")" = 33 ] && [ "$(cat "$B/k5/rec-clang-$q.rc")" = 33 ] \
        && line ok "k5 record q=$q: gcc and clang transcripts byte-identical, both exit 33" \
        || line bad "k5 record q=$q: gcc vs clang" "differ or bad status"
    python3 tools/check-k5.py "$B/k5/rec-gcc-$q.txt" "$K5SCRIPT" > "$B/k5/check-$q.cmp" 2>&1
    sed "s/^/  [q=$q] /" "$B/k5/check-$q.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/k5/check-$q.cmp")" = "$(sed -n 's/^k5=//p' tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/k5/check-$q.cmp" \
        && line ok "k5 record q=$q: Merkle roots, journal chains, the input chunking and the counts recomputed in Python" \
        || line bad "k5 record q=$q: check-k5" "see $B/k5/check-$q.cmp"
    roots="$roots $(sed -n 's/^final root //p' "$B/k5/rec-gcc-$q.txt")"
done
[ "$(echo $roots | tr ' ' '\n' | sort -u | wc -l)" -ge 3 ] \
    && line ok "k5 control: the racy network gives $(echo $roots | tr ' ' '\n' | sort -u | wc -l) different final roots under 5 quanta (the schedule shows)" \
    || line bad "k5 control" "the final roots do not vary with the quantum: $roots"
set -- $K5Q
qs=($K5Q)
for i in "${!qs[@]}"; do
    rq=${qs[$i]}; q1=${qs[$(( (i + 1) % 5 ))]}; q2=${qs[$(( (i + 3) % 5 ))]}
    ok=1; why=""
    # (record compiler, replay image, replay quantum): both directions, and gcc and clang at -O0
    for spec in "gcc clang $B/clang-k5 $q1" "clang gcc $B/gcc-k5 $q1" "gcc gcc-O0 $B/opt-k5-O0/gcc-k5 $q2" "clang clang-O0 $B/opt-k5-O0/clang-k5 $q2"; do
        set -- $spec
        python3 tools/k5blob.py replay "$B/k5/rec-$1-$rq.txt" "$B/k5/rp.blob" $4 0 || ok=0
        k5run "$3/kernel32.elf" "$B/k5/rp.blob" "$B/k5/rp-$rq-$2.txt" > /dev/null
        [ "$(sed -n 's/^final root //p' "$B/k5/rp-$rq-$2.txt")" = "$(sed -n 's/^final root //p' "$B/k5/rec-$1-$rq.txt")" ] || { ok=0; why="$why final root of $2 q=$4;"; }
        [ "$(grep '^J ' "$B/k5/rp-$rq-$2.txt" | sort | md5sum)" = "$(grep '^J ' "$B/k5/rec-$1-$rq.txt" | sort | md5sum)" ] || { ok=0; why="$why journal of $2 q=$4;"; }
        python3 tools/diverge.py "$B/k5/rec-$1-$rq.txt" "$B/k5/rp-$rq-$2.txt" --final > /dev/null || { ok=0; why="$why final leaves of $2;"; }
    done
    [ $ok = 1 ] && line ok "k5 replay of the q=$rq recording: on clang (q=$q1), on gcc from the clang recording (q=$q1), on gcc -O0 and clang -O0 (q=$q2): same final root, same journal, same final leaves" \
                || line bad "k5 replay of the q=$rq recording" "$why"
done
# the page tables: network 1 writes to a page that is in another task's space (a fault record, the same
# bytes under every schedule); networks 2, 3, 5 and 6 corrupt a space on purpose and the walk must refuse them;
# network 7 has a task touch state outside the task modules, which the kernel must refuse; network 8 sends
# the most negative value but one through a channel, an inbox and a snapshot
for net in 1 2 3 4 5 6 7 8; do
    for q in 0 1; do
        python3 tools/k5blob.py desc "$B/k5/net$net-$q.blob" 1 $q $net
        for cc in gcc clang; do k5run "$B/$cc-k5/kernel32.elf" "$B/k5/net$net-$q.blob" "$B/k5/net$net-$cc-$q.txt" "$K5SCRIPT" > "$B/k5/net$net-$cc-$q.rc"; done
    done
    ok=1
    for q in 0 1; do
        cmp -s "$B/k5/net$net-gcc-$q.txt" "$B/k5/net$net-clang-$q.txt" && [ "$(cat "$B/k5/net$net-gcc-$q.rc")" = 33 ] && [ "$(cat "$B/k5/net$net-clang-$q.rc")" = 33 ] || ok=0
    done
    [ $ok = 1 ] && line ok "k5 net $net: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33" \
                || line bad "k5 net $net: gcc vs clang" "differ or bad status"
    for q in 0 1; do
        python3 tools/check-k5.py "$B/k5/net$net-gcc-$q.txt" "$K5SCRIPT" $net > "$B/k5/net$net-check-$q.cmp" 2>&1
        sed "s/^/  [net $net q=$q] /" "$B/k5/net$net-check-$q.cmp" | grep -v PASS || true
    done
    want=$(sed -n "s/^k5net$net=//p" tests/expected/record-checks)
    [ "$(grep -c '^PASS' "$B/k5/net$net-check-0.cmp")" = "$want" ] && [ "$(grep -c '^PASS' "$B/k5/net$net-check-1.cmp")" = "$want" ] \
        && ! grep -q '^FAIL' "$B/k5/net$net-check-0.cmp" "$B/k5/net$net-check-1.cmp" \
        && line ok "k5 net $net: decoded and recomputed in Python ($want checks under each of two quanta)" \
        || line bad "k5 net $net: check-k5" "see $B/k5/net$net-check-*.cmp"
done
for net in 1 4; do
    rec() { sed -n '/^fault:/{n;p}' "$1"; }
    for cc in gcc clang; do k5run "$B/opt-k5-O0/$cc-k5/kernel32.elf" "$B/k5/net$net-0.blob" "$B/k5/net$net-$cc-O0.txt" "$K5SCRIPT" > /dev/null; done
    r=$(rec "$B/k5/net$net-gcc-0.txt")
    [ -n "$r" ] && [ "$r" = "$(rec "$B/k5/net$net-gcc-1.txt")" ] && [ "$r" = "$(rec "$B/k5/net$net-gcc-O0.txt")" ] && [ "$r" = "$(rec "$B/k5/net$net-clang-O0.txt")" ] \
        && line ok "k5 net $net: the fault record of the refused page access is the same bytes under q=0 and q=1, on gcc and clang, at -O2 and -O0" \
        || line bad "k5 net $net: record" "differs between schedules, compilers or -O levels, or absent"
done

# kill and restore: the machine is killed at 20 seeded points of the serial stream (anywhere, mid journal
# line, mid commit line, mid snapshot), restored from the last whole snapshot and the journal after it, and
# must end in the root of the run that was never killed, with every commit root, the journal and the
# snapshots the same (tools/killrun.py); on gcc at q=250 and on clang, under another schedule, at q=1
python3 tools/killrun.py "$B/gcc-k5/kernel32.elf" "$B/k5/rec-gcc-250.txt" "$K5SCRIPT" "$B/k5/kill-gcc" 5 20 250 0 8 > "$B/k5/kill-gcc.log" 2>&1
sed 's/^/  [kill gcc] /' "$B/k5/kill-gcc.log" | grep -v ': ok$' | grep -v '^  \[kill gcc\] PASS' || true
grep -q '^PASS: 20 of 20 kill points restored' "$B/k5/kill-gcc.log" \
    && line ok "k5 kill and restore (gcc, q=250): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots" \
    || line bad "k5 kill and restore (gcc)" "see $B/k5/kill-gcc.log"
python3 tools/killrun.py "$B/clang-k5/kernel32.elf" "$B/k5/rec-clang-1.txt" "$K5SCRIPT" "$B/k5/kill-clang" 7 20 1 0 8 > "$B/k5/kill-clang.log" 2>&1
sed 's/^/  [kill clang] /' "$B/k5/kill-clang.log" | grep -v ': ok$' | grep -v '^  \[kill clang\] PASS' || true
grep -q '^PASS: 20 of 20 kill points restored' "$B/k5/kill-clang.log" \
    && line ok "k5 kill and restore (clang, q=1): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots" \
    || line bad "k5 kill and restore (clang)" "see $B/k5/kill-clang.log"
# the same restore on the networks that fault a task (1, 4) and that carry extreme values (8): the last kill
# point of each is just after the final snapshot, so the machine is restored from its final state
for net in 1 4 8; do
    python3 tools/killrun.py "$B/gcc-k5/kernel32.elf" "$B/k5/net$net-gcc-0.txt" "$K5SCRIPT" "$B/k5/kill-net$net" 3 8 0 $net 8 > "$B/k5/kill-net$net.log" 2>&1
    grep -q '^PASS: 8 of 8 kill points restored' "$B/k5/kill-net$net.log" \
        && line ok "k5 kill and restore (network $net): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run" \
        || line bad "k5 kill and restore (network $net)" "see $B/k5/kill-net$net.log"
done
# every cached leaf checked at every commit (the audit flag of the descriptor): nothing is stale, and the audit adds no byte
for q in 250 1; do
    python3 tools/k5blob.py desc "$B/k5/audit-$q.blob" 1 $q 0 1
    k5run "$B/gcc-k5/kernel32.elf" "$B/k5/audit-$q.blob" "$B/k5/audit-$q.txt" "$K5SCRIPT" > /dev/null
    ok=1
    cmp -s "$B/k5/audit-$q.txt" "$B/k5/rec-gcc-$q.txt" || ok=0
    ! grep -q '^audit:' "$B/k5/audit-$q.txt" || ok=0
    [ $ok = 1 ] && line ok "k5 audit q=$q: every cached leaf equals the leaf made again from the state at every commit, and the audit adds no byte to the transcript" \
                || line bad "k5 audit q=$q" "a stale leaf, or the transcript differs"
done
# the machine restored from EVERY snapshot it wrote (under q=1 there are many, and some hold an inbox that a task
# has been given and not yet used)
for q in 1 250; do
    python3 tools/killrun.py "$B/gcc-k5/kernel32.elf" "$B/k5/rec-gcc-$q.txt" "$K5SCRIPT" "$B/k5/kill-all-$q" 1 all $q 0 8 > "$B/k5/kill-all-$q.log" 2>&1
    grep -q '^PASS: [0-9]* of [0-9]* kill points restored' "$B/k5/kill-all-$q.log" \
        && line ok "k5 restore from every snapshot (gcc, q=$q): $(sed -n 's/^PASS: \([0-9]*\) of.*/\1/p' "$B/k5/kill-all-$q.log") snapshots, each restored and finished to the uninterrupted run" \
        || line bad "k5 restore from every snapshot (q=$q)" "see $B/k5/kill-all-$q.log"
done
# a snapshot is checked before it is trusted: a flipped digit, a snapshot of another build and a journal that is not the
# one the tables say (its digest made again), are refused
for how in flip rev journal; do
    python3 tools/k5blob.py restore "$B/k5/rec-gcc-250.txt" "$B/k5/bad-$how.blob" 250 0 $how
    k5run "$B/clang-k5/kernel32.elf" "$B/k5/bad-$how.blob" "$B/k5/bad-$how.txt" "$K5SCRIPT" > /dev/null
done
grep -q '^restore: the digest of the snapshot is wrong$' "$B/k5/bad-flip.txt" && grep -q '^restore failed$' "$B/k5/bad-flip.txt" && ! grep -q '^final root' "$B/k5/bad-flip.txt" \
    && line ok "k5 restore: a snapshot with one flipped digit is refused (its digest is wrong), nothing runs" \
    || line bad "k5 restore: flipped digit" "not refused"
grep -q '^restore: a journal is not the one the tables say$' "$B/k5/bad-journal.txt" && grep -q '^restore failed$' "$B/k5/bad-journal.txt" && ! grep -q '^final root' "$B/k5/bad-journal.txt" \
    && line ok "k5 restore: a snapshot whose journal is not the one its tables say (digest made again) is refused, nothing runs" \
    || line bad "k5 restore: altered journal" "not refused"
grep -q '^restore: the snapshot is of another program$' "$B/k5/bad-rev.txt" && grep -q '^restore failed$' "$B/k5/bad-rev.txt" && ! grep -q '^final root' "$B/k5/bad-rev.txt" \
    && line ok "k5 restore: a snapshot whose program revision is another build's is refused, nothing runs" \
    || line bad "k5 restore: other revision" "not refused"

# recordings made at -O0 replay on the other compiler at -O2, under another quantum (the reverse of the matrix above)
for cc in gcc clang; do
    k5run "$B/opt-k5-O0/$cc-k5/kernel32.elf" "$B/k5/rec-250.blob" "$B/k5/rec-$cc-O0-250.txt" "$K5SCRIPT" > /dev/null
    other=$([ $cc = gcc ] && echo clang || echo gcc)
    python3 tools/k5blob.py replay "$B/k5/rec-$cc-O0-250.txt" "$B/k5/rp.blob" 1 0 || true
    k5run "$B/$other-k5/kernel32.elf" "$B/k5/rp.blob" "$B/k5/rp-O0-$cc.txt" > /dev/null
    [ -n "$(sed -n 's/^final root //p' "$B/k5/rp-O0-$cc.txt")" ] && [ "$(sed -n 's/^final root //p' "$B/k5/rp-O0-$cc.txt")" = "$(sed -n 's/^final root //p' "$B/k5/rec-$cc-O0-250.txt")" ] \
        && [ "$(grep '^J ' "$B/k5/rp-O0-$cc.txt" | sort | md5sum)" = "$(grep '^J ' "$B/k5/rec-$cc-O0-250.txt" | sort | md5sum)" ] \
        && line ok "k5 replay of a recording made by $cc at -O0, on $other at -O2 under q=1: same final root, same journal" \
        || line bad "k5 replay of the $cc -O0 recording" "differs"
done
# a replay is checked against the source: a stamp that is one fuel unit off is refused, in the task and at the entry
python3 tools/k5blob.py tamper "$B/k5/rec-gcc-250.txt" "$B/k5/tamper.blob" 250 0 2 5
k5run "$B/clang-k5/kernel32.elf" "$B/k5/tamper.blob" "$B/k5/tamper.txt" > /dev/null
grep -qx 'diverged: task 2 entry 5' "$B/k5/tamper.txt" && ! grep -q '^final root' "$B/k5/tamper.txt" \
    && ! sed -n '/^diverged:/,$p' "$B/k5/tamper.txt" | grep -q '^C \|^S ' \
    && line ok "k5 replay: a journal whose fuel stamp is one off is refused at the entry (diverged: task 2 entry 5), the run halts, no commit or snapshot follows" \
    || line bad "k5 replay: tampered stamp" "not refused"
python3 tools/k5blob.py tamper "$B/k5/rec-gcc-250.txt" "$B/k5/tamper-chain.blob" 250 0 2 5 chain
k5run "$B/gcc-k5/kernel32.elf" "$B/k5/tamper-chain.blob" "$B/k5/tamper-chain.txt" > /dev/null
grep -qx 'diverged: journal chain' "$B/k5/tamper-chain.txt" && ! grep -q '^final root' "$B/k5/tamper-chain.txt" \
    && line ok "k5 replay: an entry whose chain is one bit off is refused (diverged: journal chain), the run halts" \
    || line bad "k5 replay: tampered chain" "not refused"
# the divergence finder, on a planted mutation: one byte of the script changed
sed 's/^golf$/golx/' "$K5SCRIPT" > "$B/k5/script-mutated.txt"
k5run "$B/gcc-k5/kernel32.elf" "$B/k5/rec-250.blob" "$B/k5/mutated.txt" "$B/k5/script-mutated.txt" > /dev/null
python3 tools/check-diverge.py "$B/k5/rec-gcc-250.txt" "$B/k5/mutated.txt" > "$B/k5/diverge.cmp" 2>&1
sed 's/^/  [diverge] /' "$B/k5/diverge.cmp" | grep -v PASS || true
[ "$(grep -c '^PASS' "$B/k5/diverge.cmp")" = 4 ] && ! grep -q '^FAIL' "$B/k5/diverge.cmp" \
    && line ok "k5 diverge: the divergence finder names the planted mutation (commit, task, leaves) and agrees on a run with itself" \
    || line bad "k5 diverge" "see $B/k5/diverge.cmp"

# 5f. U1-1: ring 3 (docs/user.md). The user programs are the bytes pinned in tests/expected/user.sha256
# (built by this host's as and ld: a different binutils that lays them out differently fails here, by
# name, before any transcript can differ); the transcript equals its golden on both compilers (it
# holds each process's canonical state digest, the two desync checks that must say none and the canary
# that must say DESYNC); and each program run unchanged on this host's Linux writes the same bytes and
# ends the same way (tools/check-user.py).
(cd "$B/user" && sha256sum --quiet -c "$OLDPWD/tests/expected/user.sha256") > "$B/user-pin.log" 2>&1 \
    && line ok "user: the $(wc -l < tests/expected/user.sha256) programs built here are the bytes of tests/expected/user.sha256" \
    || line bad "user: programs" "differ from tests/expected/user.sha256 (see $B/user-pin.log)"
# M-3 (docs/specs/2026-11-06-m-memory.md section 9): the user flavor booted at -m 512 with daphnis.pool=max takes
# its pool from the memory map (122,848 frames: 480 MiB less the map's top) and every process but mlimit, whose
# output is the quota by design, ends in the state the golden pins: the pool's size is not process state.
t=$B/run/gcc-user-pool.txt
BOOT_MEM=512 BOOT_POOL=max boot_run user "$B/gcc-user/kernel32.elf" "$t" > "$t.rc"   # the golden's run (keys and mouse typed) at 512 MiB
without_mlimit() { awk '/^daphnis: run mlimit /{skip=1} /^daphnis: state /{if(!skip)print} /^daphnis: (exit|signal) /{skip=0}' "$1"; }
grep -q '^daphnis: pool 122848 frames usable of 2088960 to 511 MiB$' "$t" && grep -q '^user: done$' "$t" \
    && cmp -s <(without_mlimit tests/expected/user.serial) <(without_mlimit "$t") \
    && line ok "pool: gcc user at -m 512 with daphnis.pool=max: 122,848 frames from the memory map, every state line but mlimit's as the golden" \
    || line bad "pool: gcc user at -m 512 with daphnis.pool=max" "see $t"
# W-1: the kit and the tiler on this host's Linux (docs/specs/2026-11-05-w-tiler.md section 5): the tiler built from
# source at HEAD (O/ubin) draws every case of tools/check-tiler.py (the grid, the mark, the face, the terminal) as its Python does;
# check-tiler.sh adds the gcc and clang builds
python3 tools/check-tiler.py "$B/ubin/tiler" > "$B/tiler.cmp" 2>&1 && [ "$(grep -c '^PASS' "$B/tiler.cmp")" = 12 ] \
    && line ok "tiler linux: O/ubin/tiler draws the grid, the mark, the face and the terminal as tools/check-tiler.py does" \
    || line bad "tiler linux" "see $B/tiler.cmp"
for cc in gcc clang; do
    cmp -s tests/expected/user.serial "$B/run/$cc-user.1.txt" \
        && line ok "serial user: $cc transcript equals tests/expected/user.serial (state digests, no desync, the canary desyncs)" \
        || line bad "serial user: $cc vs tests/expected/user.serial" "differ"
    python3 tools/check-user.py "$B/run/$cc-user.1.txt" "$B/user" --image "$B/user/initrd.cpio" --stdin tests/image/stdin.txt > "$B/user-oracle-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/user-oracle-$cc.cmp" | grep -v PASS || true
    [ "$(grep -c '^PASS' "$B/user-oracle-$cc.cmp")" = "$(sed -n 's/^user=//p' tests/expected/record-checks)" ] && ! grep -q '^FAIL' "$B/user-oracle-$cc.cmp" \
        && line ok "user oracle $cc: each program's output and exit status or signal equal the same file run on Linux" \
        || line bad "user oracle $cc" "see $B/user-oracle-$cc.cmp"
    # F-1: the surface digest the kernel printed after each mfb run is the digest of the pattern mfb draws
    python3 tools/check-fb.py 640 480 "$B/run/$cc-user.1.txt" > "$B/user-fb-$cc.cmp" 2>&1
    [ "$(grep -c '^PASS' "$B/user-fb-$cc.cmp")" = 3 ] && ! grep -q '^FAIL' "$B/user-fb-$cc.cmp" \
        && line ok "surface $cc: the two mfb runs and mcifb leave the surface whose digest tools/check-fb.py computes (640x480)" \
        || line bad "surface $cc" "see $B/user-fb-$cc.cmp"
    # F-2: both mkeys runs saw a, b, c pressed and released, in order, each key event followed by EV_SYN
    [ "$(grep -c '^key [0-9]* [01]$' "$B/run/$cc-user.1.txt")" = 12 ] && [ "$(grep -c '^syn 6$' "$B/run/$cc-user.1.txt")" = 2 ] \
        && [ "$(grep '^key ' "$B/run/$cc-user.1.txt" | tr '\n' ' ')" = "key 30 1 key 30 0 key 48 1 key 48 0 key 46 1 key 46 0 key 30 1 key 30 0 key 48 1 key 48 0 key 46 1 key 46 0 " ] \
        && line ok "keys $cc: both mkeys runs read a, b, c pressed and released in order (twelve key events, six EV_SYN each)" \
        || line bad "keys $cc" "the key events differ (see $B/run/$cc-user.1.txt and .keys)"
    # F-3: both mmouse runs read the move by (10, -5), the left and the right click, in order
    [ "$(grep '^button \|^rel ' "$B/run/$cc-user.1.txt" | tr '\n' ';')" = "button 272 1;button 272 0;button 273 1;button 273 0;rel x 10 y -5, syn 5;button 272 1;button 272 0;button 273 1;button 273 0;rel x 10 y -5, syn 5;" ] \
        && line ok "mouse $cc: both mmouse runs read the move by (10, -5) and the left and right clicks in order (five packets, five EV_SYN each)" \
        || line bad "mouse $cc" "the mouse events differ (see $B/run/$cc-user.1.txt and .keys)"
    # R-1: cint in ring 3 (docs/user.md section 13): mci's fault line and status, once more on other
    # frames with one digest; msha's digest is the host's over the same bytes; mcifb's surface is mfb's
    [ "$(grep -c '^fault\[E_OVERFLOW\]: add.checked.i64 at user/ci/mci.ci:10:19$' "$B/run/$cc-user.1.txt")" = 2 ] \
        && grep -q '^daphnis: desync mci pid 43 (other frames) against pid 42: none$' "$B/run/$cc-user.1.txt" \
        && line ok "ci $cc: both mci runs fault add.checked.i64 at user/ci/mci.ci:10:19 with status 1 and one digest" \
        || line bad "ci $cc" "mci's fault line or digest differs (see $B/run/$cc-user.1.txt)"
    [ "$(grep '^msha: ' "$B/run/$cc-user.1.txt")" = "msha: 4 MiB sha256 $(python3 -c 'import hashlib; print(hashlib.sha256(bytes(((i * 7 + (i >> 8)) & 255) for i in range(1 << 22))).hexdigest())')" ] \
        && line ok "ci sha $cc: msha's digest of 4 MiB in cint is the host's over the same bytes" \
        || line bad "ci sha $cc" "msha's digest differs (see $B/run/$cc-user.1.txt)"
    grep -q '^daphnis: desync surface pid 45 (cint) against pid 37: none$' "$B/run/$cc-user.1.txt" \
        && line ok "ci surface $cc: mcifb draws mfb's pattern from cint, the same surface digest" \
        || line bad "ci surface $cc" "mcifb's surface differs from mfb's (see $B/run/$cc-user.1.txt)"
done

# 6. FAULT=1: the record, against the hosted runtime's record of the same overflow
mkdir -p "$B/hosted-probe"
cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . --out "$B/hosted-probe" tests/fault_probe.ci > "$B/probe.log" 2>&1 \
    && "$B/hosted-probe/fault_probe" "$B/hosted-probe/record.bin" > /dev/null 2>&1
[ -s "$B/hosted-probe/record.bin" ] && line ok "fault: hosted runtime wrote its record for tests/fault_probe.ci" \
    || line bad "fault: hosted twin" "no record; see $B/probe.log"
for cc in gcc clang; do
    python3 tools/compare-fault.py "$B/run/$cc-fault.1.txt" "$B/hosted-probe/record.bin" "$B/emit-fault/c/cint-program.c" > "$B/fault-$cc.cmp" 2>&1
    sed "s/^/  [$cc] /" "$B/fault-$cc.cmp"
    [ "$(grep -c '^PASS' "$B/fault-$cc.cmp")" -ge 12 ] && ! grep -q '^FAIL' "$B/fault-$cc.cmp" \
        && line ok "fault $cc: record printed, decodes, and matches the hosted record" \
        || line bad "fault $cc: record" "see $B/fault-$cc.cmp"
done

# 7. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, under 8 minutes" || line bad "time" "$elapsed s"
# the fixed count: every PASS line printed above (the audit's included), and the SKIP line only when the ISO leg did not run
total=$((passes + $(grep -c '^PASS' "$B/audit.log")))
want_total=$((gate_want + iso_ran * iso_pass + ovmf_ran * ovmf_pass)); want_skips=$((2 - iso_ran - ovmf_ran))
[ "$total" = "$want_total" ] && [ "$skips" = "$want_skips" ] \
    && line ok "gate: $total PASS lines and $skips SKIP line(s) above, the fixed count ($gate_want, plus $iso_pass ISO and $ovmf_pass OVMF)" \
    || line bad "gate: fixed count" "$total PASS lines and $skips SKIP line(s) above, $want_total and $want_skips expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
