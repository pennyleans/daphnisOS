#!/bin/sh
# tools/doom/fetch.sh [DIR]: freedoom-ci at doom.pin's commit into DIR (default $DOOM_ROOT, else freedoom-ci in
# the user cache, ${XDG_CACHE_HOME:-~/.cache}) and prints DIR. A DIR already at the commit with a clean tree is used
# as it is; a DIR at another commit is checked out again. Refuses a tree other than doom.pin's. $FREEDOOM_CI names
# another clone to fetch from (a local bare clone until DS-4).
set -eu
pin=$(dirname "$0")/../../doom.pin
val() { sed -n "s/^$1=//p" "$pin"; }
url=${FREEDOOM_CI:-$(val url)} commit=$(val commit) tree=$(val tree)
dir=${1:-${DOOM_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/freedoom-ci}}
if [ ! -d "$dir/.git" ]; then
    [ -e "$dir" ] && [ -n "$(ls -A "$dir")" ] && { echo "fetch.sh: $dir exists and is not a git clone" >&2; exit 1; }
    git clone -q --no-checkout "$url" "$dir" >&2
fi
if [ "$(git -C "$dir" rev-parse -q --verify HEAD 2>/dev/null)" != "$commit" ] || [ -n "$(git -C "$dir" status --porcelain)" ]; then
    git -C "$dir" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$dir" fetch -q "$url" >&2
    git -C "$dir" checkout -q --force --detach "$commit" >&2
    git -C "$dir" clean -qfdx >&2
fi
[ "$(git -C "$dir" rev-parse "HEAD^{tree}")" = "$tree" ] || { echo "fetch.sh: $dir is not tree $tree" >&2; exit 1; }
echo "$dir"
