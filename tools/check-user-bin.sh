#!/usr/bin/env bash
# tools/check-user-bin.sh [ROOT]: DOS-3 and RG-1 on the tree at ROOT (default .): it tracks user/bin/NOTICE and
# nothing else under user/bin, so no image, gate or leg can take a committed program. Exit 0, silent, when that holds;
# else 1, with the tracked strays on one line, or why it cannot tell.
set -u
cd "${1:-.}" || exit 1
fl=$(git ls-files -- user/bin) || { echo "git ls-files failed"; exit 1; }
strays=$(printf '%s\n' "$fl" | grep -vx -e user/bin/NOTICE -e '' || true)   # grep with nothing to print exits 1
if [ -n "$strays" ]; then
    echo $strays
    exit 1
fi
if ! printf '%s\n' "$fl" | grep -qx user/bin/NOTICE; then
    echo "user/bin/NOTICE is not tracked"
    exit 1
fi
exit 0
# SPDX-License-Identifier: Apache-2.0
