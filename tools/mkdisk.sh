#!/usr/bin/env bash
# tools/mkdisk.sh OUT: the test volume of stage P (docs/specs/2026-11-05-p-disk.md section 4), 4 MiB of ext2
# with 4 KiB blocks and 128-byte inodes built from tests/disk/ and two generated files, one pinned digest (tests/expected/disk.sha256)
# whatever the checkout's times, owners and umask and whatever /etc/mke2fs.conf says:
#   - the tree is staged with modes 0755 (directories) and 0644 (files), and two files are made there:
#     big, 1 MiB through the direct and single indirect maps, byte i = (7i + i/509) mod 256, and sparse,
#     6 MiB with data only from 5 MiB on (4 KiB) and in its last 100 bytes, through the double indirect
#     map with holes before it (P-2);
#   - mke2fs reads no configuration file (MKE2FS_CONFIG=/dev/null), every feature and size is named, the
#     UUID and the directory hash seed are fixed, and the clock is 1 (E2FSPROGS_FAKE_TIME; e2fsprogs 1.47.0
#     takes 0 as unset and reads the real clock);
#   - then debugfs, on the same clock, sets every inode's owner to 0:0 and its three times to 1.
# The volume is never in git: the gate builds it on each run and checks the pin before booting it.
# AC-1c (docs/specs/2026-11-08-ac-accounts.md): with ACCOUNTS set the volume is one for accounts: it holds /.daphnis
# (the desk's /home/.daphnis), and ACCOUNTS, when it names a file, is copied in as its account store; empty, the desk
# meets first boot. Such a volume is not the pinned one; without ACCOUNTS nothing changes.
set -eu
out=$1
src=$(cd "$(dirname "$0")/../tests/disk" && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -RP "$src/." "$stage/"
if [ -n "${ACCOUNTS+set}" ]; then
    mkdir "$stage/.daphnis"
    [ -n "$ACCOUNTS" ] && cp "$ACCOUNTS" "$stage/.daphnis/accounts"
fi
python3 - "$stage" <<'PY'
import sys
d = sys.argv[1]
with open(d + "/big", "wb") as f:
    f.write(bytes((7 * i + i // 509) & 0xFF for i in range(1 << 20)))
with open(d + "/sparse", "wb") as f:
    f.seek(5 << 20)
    f.write(bytes((i * 13 + 5) & 0xFF for i in range(4096)))
    f.seek((6 << 20) - 100)
    f.write(b"the end of a sparse file, past the single indirect map, read through the double one.\n".ljust(100, b"."))
PY
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
export E2FSPROGS_FAKE_TIME=1 MKE2FS_CONFIG=/dev/null
rm -f "$out"
mke2fs -q -F -t ext2 -b 4096 -I 128 -N 64 -m 0 -O none,dir_index,filetype,sparse_super \
    -U 6461706e-6869-7300-0000-000000000001 -E hash_seed=6461706e-6869-7300-0000-000000000002,root_owner=0:0 \
    -L daphnis -d "$stage" "$out" 4M > "$out.log" 2>&1 || { cat "$out.log" >&2; exit 1; }
rm -f "$out.log"
paths=$( (cd "$stage" && find . -mindepth 1 | sed 's|^\.||'; echo /lost+found) | LC_ALL=C sort)
for p in / $paths; do
    echo "sif $p uid 0"
    echo "sif $p gid 0"
    for f in atime ctime mtime; do echo "sif $p $f 1"; done
done | debugfs -w -f - "$out" > /dev/null 2>&1
