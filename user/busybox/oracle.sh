#!/usr/bin/env bash
# user/busybox/oracle.sh: the busybox oracle of the gates (DOS-3, unit 4b). The repository holds no busybox. When
# CORE_ORACLE names the pinned tarball (busybox-1.36.1.tar.bz2, https://busybox.net/downloads/), this builds
# busybox, busybox-net and busybox-oracle with user/busybox/build.sh into BUSYBOX_CACHE (default
# ~/daphnis-work/busybox), once per recipe (the directory is named by the digest of build.sh and the three
# fragments), and prints that directory. With CORE_ORACLE unset or empty it prints nothing: each gate then checks
# its committed goldens in the oracle's place. Exit status 1 when the tarball is not the pinned one or a build fails.
set -euo pipefail
[ -n "${CORE_ORACLE:-}" ] || exit 0
here=$(cd "$(dirname "$0")" && pwd)
key=$(cat "$here/build.sh" "$here/config.fragment" "$here/net.fragment" "$here/oracle.fragment" | sha256sum | cut -c1-16)
dir=${BUSYBOX_CACHE:-$HOME/daphnis-work/busybox}/$key
for v in '' net oracle; do
    [ -x "$dir/busybox${v:+-$v}" ] || "$here/build.sh" "$CORE_ORACLE" "$dir" $v > /dev/null
done
echo "$dir"
