#!/bin/sh
# tools/oplref/fetch.sh DIR: ymfm (Aaron Giles, BSD-3-Clause) from aaronsgiles/ymfm at the pinned commit, into
# DIR (DIR/src is the source directory tools/oplref/build.sh takes).
set -eu
dir=$1
commit=81aec25ccbb98f4873a255f7551ac4dadac59b4a
git clone -q https://github.com/aaronsgiles/ymfm "$dir"
git -C "$dir" checkout -q "$commit"
echo "$dir/src"
