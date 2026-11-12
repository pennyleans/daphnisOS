#!/usr/bin/env bash
# tools/mkcintvol.sh OUT [SIZE [INODES]]: the volume of unit BU-4c (docs/specs/2026-11-07-bu4-toolchain.md sections
# 2, 4.3 and 6), SIZE (default 128M) of ext2 that mounts at /home (BU-4h2: 256M, for cint's own rebuild, about
# 105 MB, and its trees): opt/cint/, the pinned toolchain of user/cint/opt (BU4-1 A: /home/opt/cint),
# and src/, the sources cib builds there (every module of tests/image/build-sources.txt, at its path in the tree:
# msha, mci, the core set, cish and hdesk with all they import), plus out/, empty. Built as tools/mkdisk.sh builds the test volume: staged with modes 0755 (directories and
# the six executables) and 0644, mke2fs with every feature named, a fixed UUID, hash seed and clock, then debugfs
# sets every owner to 0:0 and every time to 1; so the bytes are a function of the inputs (one pinned digest,
# tests/expected/cint-volume.sha256). The volume is never in git. INODES (default 4096, every gate volume and its pin)
# is mke2fs's -N (HW-15): the release stick's 512 MiB home takes 32768, one per 16 KiB; tests/fs/ext2_big_test.ci
# mounts and writes that volume.
set -eu
export PATH=$PATH:/usr/sbin:/sbin   # mke2fs and debugfs, for a gate run by a user whose PATH has no sbin
out=$1
size=${2:-128M}
inodes=${3:-4096}
case $inodes in
    ''|0*|*[!0-9]*) echo "mkcintvol.sh: INODES must be a count, not '$inodes'" >&2; exit 2 ;;
esac
D=$(cd "$(dirname "$0")/.." && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/opt" "$stage/src" "$stage/out"
cp -RP "$D/user/cint/opt" "$stage/opt/cint"
for f in $(cat "$D/tests/image/build-sources.txt"); do
    mkdir -p "$stage/src/$(dirname "$f")"
    cp "$D/$f" "$stage/src/$f"
done
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
for x in cint qbe as ld cib make; do chmod 0755 "$stage/opt/cint/$x"; done
export E2FSPROGS_FAKE_TIME=1 MKE2FS_CONFIG=/dev/null
rm -f "$out"
mke2fs -q -F -t ext2 -b 4096 -I 128 -N "$inodes" -m 0 -O none,dir_index,filetype,sparse_super \
    -U 6461706e-6869-7300-0000-000000000003 -E hash_seed=6461706e-6869-7300-0000-000000000004,root_owner=0:0 \
    -L daphnis-cint -d "$stage" "$out" "$size" > "$out.log" 2>&1 || { cat "$out.log" >&2; exit 1; }
rm -f "$out.log"
paths=$( (cd "$stage" && find . -mindepth 1 | sed 's|^\.||'; echo /lost+found) | LC_ALL=C sort)
for p in / $paths; do
    echo "sif $p uid 0"
    echo "sif $p gid 0"
    for f in atime ctime mtime; do echo "sif $p $f 1"; done
done | debugfs -w -f - "$out" > "$out.dbg" 2>&1 || { cat "$out.dbg" >&2; exit 1; }
rm -f "$out.dbg"
