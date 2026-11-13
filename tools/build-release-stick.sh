#!/usr/bin/env bash
# tools/build-release-stick.sh OUT [SIZE]: the release stick as an image file, the one g25 and the RV-1 board leg
# boot. HW-8's layout (tools/build-stick.sh): partition 1 the EFI system partition, tools/build-esp.sh's image of
# the gcc hdesk kernel and image behind GRUB with the release boot line; partition 2 the volume, tools/mkcintvol.sh's
# toolchain volume of SIZE (default 512M: the 256M of BU-4h2, which cint's own rebuild needs, and as much again for
# a user's files; whole MiB or GiB, as 512M or 1G) with one inode per 16 KiB (HW-15: 32768 at 512M) and an empty
# /.daphnis, so the desk meets first boot. The ESP also carries LICENSES/: LICENSE, NOTICE and every license or
# notice text NOTICE names, at its path in the tree, and GRUB's package and copyright file (GRUB.txt).
# This writes an ordinary file only, never a device: l writes the image to a stick (a typed go).
# The release boot line:
#   daphnis.pool=max      the hdesk image runs past the 32 MiB window below the pool; without it the loader drops it
#   daphnis.uart=0        HW-14: the console leaves COM1 alone, so a board with a real serial port does not stall
#   daphnis.disk.write=G  HW-12: the volume partition's unique GUID, the one tools/build-stick.sh gives it
#   daphnis.poweroff=1    HW-2: Shut Down ends the machine through ACPI S5 (rt/start.c); without it a board halts on
# The image is a function of HEAD and the pinned toolchain only. The first stage, in the checkout, unpacks
# `git archive HEAD` under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-release, cleared first as the gates clear
# their own) and runs the second stage from that copy under `env -i`: PATH, HOME, LC_ALL=C, TMPDIR, CINT_TOOLCHAIN,
# DOOM_ROOT (tools/doom/fetch.sh holds it to doom.pin) and the commit's time, nothing else. So no change, untracked
# file, index flag or exported variable (INITRD, OPT, MAKEFLAGS) in the checkout's shell reaches the image. The image
# takes no committed user/bin (RG-1): make builds each of its programs from the commit's source (RELEASE_PROGS, with
# the host's musl-gcc, as user/ci/build.sh says) and BearSSL for fetch from its tarball (BEARSSL_TARBALL, else
# fetched with curl and checked against user/tls/build.sh's SHA-256). It prints HEAD beside the size and SHA-256.
set -euo pipefail
guid=6461706e-6869-7300-0000-000000000005
args="daphnis.pool=max daphnis.uart=0 daphnis.disk.write=$guid daphnis.poweroff=1"
if [ -z "${RELEASE_STICK_HEAD:-}" ]; then
    # Stage one, in the checkout. For 0.1.0 the stick is built on Debian or Ubuntu only, before any work: its GRUB is
    # the grub-efi-amd64-bin package, which dpkg names so the release publishes that exact source (stage two, GRUB.txt).
    [ "$(dpkg-query -W -f='${db:Status-Abbrev}' grub-efi-amd64-bin 2>/dev/null)" = "ii " ] \
        || { echo "build-release-stick: needs Debian or Ubuntu with grub-efi-amd64-bin; see NOTES.md" >&2; exit 1; }
    [ $# -ge 1 ] || { echo "usage: tools/build-release-stick.sh OUT [SIZE]" >&2; exit 2; }
    out=$(realpath -m "$1") size=${2:-512M}
    case $size in
        [1-9]*M|[1-9]*G) n=${size%?}; case $n in *[!0-9]*) n=;; esac ;;
        *) n= ;;
    esac
    [ -n "$n" ] || { echo "build-release-stick: SIZE is whole MiB or GiB (512M, 1G), not '$size'" >&2; exit 2; }
    case $size in *M) inodes=$((n * 64));; *G) inodes=$((n * 65536));; esac   # one inode per 16 KiB (HW-15)
    case "$out" in /dev/*) echo "build-release-stick: refuses /dev output" >&2; exit 1;; esac
    [ ! -e "$out" ] || [ -f "$out" ] || { echo "build-release-stick: $out is not a regular file" >&2; exit 1; }
    B=$(realpath -m "${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-release}")
    cd "$(dirname "$0")/.."
    for t in git tar env cint; do
        command -v "$t" >/dev/null || { echo "build-release-stick: $t not found" >&2; exit 1; }
    done
    if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
        echo "build-release-stick: $B is not empty and is not a Daphnis build directory (no .daphnis-build);" \
            "set DAPHNIS_BUILD" >&2
        exit 1
    fi
    head=$(git rev-parse --verify HEAD)
    rm -rf -- "$B"; mkdir -p "$B/src" "$B/release" "$(dirname "$out")"; : > "$B/.daphnis-build"
    git -c core.autocrlf=false -c core.attributesFile=/dev/null archive --format=tar "$head" | tar -x -C "$B/src"
    exec env -i PATH="$PATH:/usr/sbin:/sbin" HOME="${HOME:?}" LC_ALL=C TZ=UTC0 TMPDIR="${TMPDIR:-/tmp}" \
        CINT_TOOLCHAIN="${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}" \
        DOOM_ROOT="${DOOM_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/freedoom-ci}" \
        ${BEARSSL_TARBALL:+BEARSSL_TARBALL="$(realpath "$BEARSSL_TARBALL")"} \
        SOURCE_DATE_EPOCH="$(git log -1 --format=%ct "$head")" RELEASE_STICK_HEAD="$head" \
        bash "$B/src/tools/build-release-stick.sh" "$out" "$size" "$inodes" "$B"
fi
# Stage two, in $B/src, the commit's copy, with only the environment above. PATH has /usr/sbin and /sbin for mke2fs,
# debugfs and sfdisk. SOURCE_DATE_EPOCH is the commit's time: mtools stamps the ESP's directory entries with it, so the
# ESP is a function of the commit (GRUB's BOOTX64.EFI and the volume already are). FAT keeps local time, so TZ=UTC0
# holds those stamps to UTC whatever the build host's time zone (HW-16).
out=$1 size=$2 inodes=$3 B=$4 head=$RELEASE_STICK_HEAD
cd "$(dirname "$0")/.."
[ "$PWD" = "$(cd "$B/src" 2>/dev/null && pwd)" ] \
    || { echo "build-release-stick: stage two runs only from the build's copy of the commit" >&2; exit 1; }
for t in make cint gcc musl-gcc python3 mke2fs debugfs sfdisk grub-mkstandalone mformat mmd mcopy dpkg-query sha256sum; do
    command -v "$t" >/dev/null || { echo "build-release-stick: $t not found" >&2; exit 1; }
done
# The release is built by the pinned cint only, as check.sh refuses any other (toolchain.pin), with cint_rt_lean.h
# held to the digest toolchain.pin records too (HW-16).
[ -f "$CINT_TOOLCHAIN" ] || { echo "build-release-stick: cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)" >&2; exit 1; }
pin() { sed -n "s/^$1=//p" toolchain.pin; }
tc() { awk -v k="$1" '$1==k {print $2}' "$CINT_TOOLCHAIN"; }
[ "$(sha256sum < "$(tc compiler_sources)" | cut -c1-64)" = "$(pin compiler_source_identity)" ] \
    && [ "$(sha256sum < "$(tc include)/cint_rt.h" | cut -c1-64)" = "$(pin cint_rt_h_sha256)" ] \
    && [ "$(sha256sum < "$(tc include)/cint_rt_lean.h" | cut -c1-64)" = "$(pin cint_rt_lean_h_sha256)" ] \
    && [ "$(sha256sum < "$(readlink -f "$(command -v cint)")" | cut -c1-64)" = "$(tc executable_sha256)" ] \
    || { echo "build-release-stick: the cint on PATH is not toolchain.pin's" >&2; exit 1; }

make -s -j"$(nproc)" O="$B/o" COMPILERS=gcc FLAVORS=hdesk OPT=-O2 CAPTURE=0 CINT_TOOLCHAIN="$CINT_TOOLCHAIN" \
    DOOM_ROOT="$DOOM_ROOT" ${BEARSSL_TARBALL:+BEARSSL_TARBALL="$BEARSSL_TARBALL"} \
    "$B/o/gcc-hdesk/kernel.elf" "$B/o/hdesk/release.cpio" > "$B/make.log" 2>&1 \
    || { tail -20 "$B/make.log" >&2; exit 1; }
# HW-17: the release image, hdesk/release.cpio: every program the desk opens and no Doom (the gates' hdesk image keeps it)
ARGS=$args tools/build-esp.sh "$B/o/gcc-hdesk/kernel.elf" "$B/release/esp.img" "$B/o/hdesk/release.cpio"
# LICENSES/ on the ESP, the partition any computer reads. The texts are the ones NOTICE names (every path in it whose
# file name holds LICENSE, LICENCE, COPYING, NOTICE or OFL), so the stick follows NOTICE; a named text missing from
# the tree stops the build. GRUB is the one program on the stick built outside the tree: GRUB.txt names its package
# and source package, and GRUB-copyright.txt is that package's copyright file.
grub_pkg=$(dpkg-query -W -f='${Package} ${Version}' grub-efi-amd64-bin 2>/dev/null) \
    && grub_src=$(dpkg-query -W -f='${source:Package} ${source:Version}' grub-efi-amd64-bin) \
    && [ -f /usr/share/doc/grub-efi-amd64-bin/copyright ] \
    || { echo "build-release-stick: no dpkg record of grub-efi-amd64-bin; the stick must name its GRUB" >&2; exit 1; }
texts=$({ echo LICENSE; echo NOTICE; grep -oE '[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+' NOTICE | sed 's/\.*$//'; } \
    | grep -E '(^|/)[^/]*(LICEN[CS]E|COPYING|NOTICE|OFL)[^/]*$' | sort -u)
for p in $texts; do
    [ -f "$p" ] || { echo "build-release-stick: NOTICE names $p, which is not in the tree" >&2; exit 1; }
done
printf '%s\n' "EFI/BOOT/BOOTX64.EFI on this stick is GNU GRUB, made by tools/build-esp.sh with grub-mkstandalone." \
    "Package: $grub_pkg, on the machine that built this image." \
    "License: GNU General Public License, version 3 or later (tools/grub/LICENSE-GPL-3.0.txt here)." \
    "The package's copyright file: GRUB-copyright.txt." \
    "Source: the source package $grub_src, published beside this image with each Daphnis release." \
    > "$B/release/GRUB.txt"
export MTOOLSRC=/dev/null MTOOLS_SKIP_CHECK=1
mmd -i "$B/release/esp.img" ::/LICENSES $(for p in $texts; do d=$(dirname "$p")
    while [ "$d" != . ]; do echo "$d"; d=$(dirname "$d"); done; done | sort -u | sed 's|^|::/LICENSES/|')
for p in $texts; do mcopy -i "$B/release/esp.img" "$p" "::/LICENSES/$p"; done
mcopy -i "$B/release/esp.img" "$B/release/GRUB.txt" ::/LICENSES/GRUB.txt
mcopy -i "$B/release/esp.img" /usr/share/doc/grub-efi-amd64-bin/copyright ::/LICENSES/GRUB-copyright.txt
tools/mkcintvol.sh "$B/release/volume.img" "$size" "$inodes"
# /.daphnis, empty: the desk's /home/.daphnis with no account store, so the first boot asks for the first account.
# Owner, mode and times as mkcintvol.sh sets every other inode, so the volume's bytes stay a function of the inputs.
export E2FSPROGS_FAKE_TIME=1
printf '%s\n' 'mkdir /.daphnis' 'sif /.daphnis mode 040755' \
    'sif /.daphnis uid 0' 'sif /.daphnis gid 0' \
    'sif /.daphnis atime 1' 'sif /.daphnis ctime 1' 'sif /.daphnis mtime 1' \
    'sif / atime 1' 'sif / ctime 1' 'sif / mtime 1' | debugfs -w -f - "$B/release/volume.img" > "$B/release/volume.dbg" 2>&1
debugfs -R "stat /.daphnis" "$B/release/volume.img" 2>/dev/null | grep -q "Type: directory" \
    || { echo "build-release-stick: /.daphnis not made on the volume" >&2; exit 1; }
VOLUME_GUID=$guid tools/build-stick.sh "$B/release/esp.img" "$B/release/volume.img" "$out"
echo "build-release-stick: $out, HEAD $head, $(stat -c %s "$out") bytes, sha256 $(sha256sum "$out" | cut -c1-64)"
echo "build-release-stick: boot line: $args"
echo "build-release-stick: host: $grub_pkg, $(mformat --version | head -1), $(mke2fs -V 2>&1 | head -1)," \
    "$(sfdisk --version)"
